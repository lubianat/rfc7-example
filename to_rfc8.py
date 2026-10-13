# /// script
# dependencies = ["zarr>=3", "numpy", "scipy"]
# ///
"""Build a self-contained RFC-8 collection (fall-2026 slide revision) from 6001240_labels.zarr.

  image  copy of the original image, metadata rewritten to an RFC-8 multiscale. Its default
      segmentation stays nested at ./labels/0, declared by an embedded_labels extension trait.
  seg_dapi, seg_laminb1: one new segmentation per channel (Otsu + connected
      components), RFC-8 multiscales.

Every path is relative and points down the tree, never "..".

Output:
  rfc8_collection.zarr/zarr.json             collection: nodes image, seg_dapi, seg_laminb1 + scene trait
  rfc8_collection.zarr/image/zarr.json       multiscale (arrays 0, 1, 2) + omero + embedded_labels
  rfc8_collection.zarr/image/labels/0/zarr.json multiscale + labels trait (default seg)
  rfc8_collection.zarr/seg_*/zarr.json        multiscale (arrays s0, s1, s2) + labels trait

Run: uv run to_rfc8.py
"""
import json
import os
import shutil
import time
import uuid
from pathlib import Path

import numpy as np
import zarr
from scipy import ndimage

SRC = Path("6001240_labels.zarr")
OUT = Path("rfc8_collection.zarr")
VERSION = "0.x"
IMAGE = "image"  # node names are free text; short meaningful names instead of 01, 02, ...
# node name -> (channel index from omero.channels[].label, fill holes)
SEGS = {
    "seg_dapi": (1, True),      # Dapi: solid nuclei
    "seg_laminb1": (0, False),  # LaminB1: nuclear rim, keep it hollow
}
# ponytail: placeholder extension namespaces, swap for real URIs
RENDERING_EXT = "https://example.org/omero-rendering/"
OMERO_EXT = "https://example.org/omero/"
LABELS_EXT = "https://example.org/embedded-labels/"


def manifest(*ids: str) -> list:
    return [{"id": i, "version": "0.1", "schemas": []} for i in ids]


def uuid7() -> str:
    # ponytail: stdlib uuid.uuid7 lands in Python 3.14; drop this then
    b = bytearray((time.time_ns() // 1_000_000).to_bytes(6, "big") + os.urandom(10))
    b[6] = (b[6] & 0x0F) | 0x70
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def path(href: str) -> dict:
    return {"type": "zarr", "format": "relative", "href": href}


def ref(type_: str, id_: str, href: str | None = None) -> dict:
    r = {"type": type_, "ref": id_}
    if href:
        r["path"] = path(href)
    return r


def multiscale(ms: dict, name: str, traits: list, scale_path=lambda i, ds: ds["path"]) -> dict:
    """0.5 multiscales entry -> RFC-8 multiscale node."""
    ms_id, cs_id = uuid7(), uuid7()
    scales = []
    for i, ds in enumerate(ms["datasets"]):
        s_id = uuid7()
        scales.append({
            "id": s_id,
            "path": path(f"./{scale_path(i, ds)}"),
            "coordinate_transformations": [
                {**t, "input": ref("scale", s_id), "output": ref("coordinate_system", cs_id)}
                for t in ds["coordinateTransformations"]
            ],
        })
    return {
        "version": VERSION,
        "type": "multiscale",
        "id": ms_id,
        "name": name,
        "coordinate_systems": [{"id": cs_id, "name": "physical", "axes": ms["axes"]}],
        "scales": scales,
        "traits": traits,
    }


def label_attributes(image_label: dict) -> list:
    """0.5 colors -> RFC-8 label_attributes."""
    return [{"label_value": c["label-value"], "color": c["rgba"]} for c in image_label.get("colors", [])]


def omero_rois(image_label: dict) -> dict:
    """0.5 properties (omero:roiId / omero:shapeId per label) -> omero extension trait."""
    return {"type": OMERO_EXT + "rois", "labels": [
        {"label_value": p["label-value"], "roi_id": p["omero:roiId"], "shape_id": p["omero:shapeId"]}
        for p in image_label.get("properties", []) if "omero:roiId" in p
    ]}


def set_ome(group: Path, ome: dict | None) -> None:
    f = group / "zarr.json"
    doc = json.loads(f.read_text())
    doc["attributes"] = {"ome": ome} if ome else {}
    f.write_text(json.dumps(doc, indent=2))


def otsu(x: np.ndarray) -> float:
    hist, edges = np.histogram(x, bins=256)
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    mids = (edges[:-1] + edges[1:]) / 2
    m0 = np.cumsum(hist * mids) / np.maximum(w0, 1)
    m1 = ((hist * mids).sum() - np.cumsum(hist * mids)) / np.maximum(w1, 1)
    return mids[np.argmax(w0 * w1 * (m0 - m1) ** 2)]


def segment(img: np.ndarray, fill: bool = True) -> np.ndarray:
    """Simple seg: smooth, Otsu threshold, optionally fill holes, connected components."""
    smooth = ndimage.gaussian_filter(img.astype(np.float32), 1)
    mask = smooth > otsu(smooth)
    if fill:
        mask = ndimage.binary_fill_holes(mask)
    lbl, _ = ndimage.label(mask)
    sizes = np.bincount(lbl.ravel())
    lbl[sizes[lbl] < 500] = 0  # ponytail: fixed min size in voxels, tune per dataset
    _, lbl = np.unique(lbl, return_inverse=True)  # relabel 1..n contiguously
    return lbl.reshape(img.shape).astype(np.uint32)


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    zarr.open_group(OUT, mode="w")

    # image: duplicate the original, then rewrite its metadata in place
    n1 = OUT / IMAGE
    # ponytail: RO-Crate (nested *.zarr/ro-crate-metadata.json) is not part of the spec or this demo
    shutil.copytree(SRC, n1, ignore=shutil.ignore_patterns(SRC.name))
    src_ome = json.loads((SRC / "zarr.json").read_text())["attributes"]["ome"]
    lbl_name = json.loads((SRC / "labels" / "zarr.json").read_text())["attributes"]["ome"]["labels"][0]
    lbl_ome = json.loads((SRC / "labels" / lbl_name / "zarr.json").read_text())["attributes"]["ome"]

    il = lbl_ome["image-label"]
    seg1 = multiscale(lbl_ome["multiscales"][0], "default_seg", [
        {"type": "labels", "label_attributes": label_attributes(il)},
        omero_rois(il),
    ])
    seg1["extension_manifest"] = manifest(OMERO_EXT)
    img = multiscale(src_ome["multiscales"][0], "image", [
        {"type": RENDERING_EXT + "rendering", **src_ome["omero"]},
        # labels-stay-here: segmentations nested inside this image, paths relative to it
        {"type": LABELS_EXT + "embedded_labels",
         "nodes": [{"type": "multiscale", "id": seg1["id"], "path": path(f"./labels/{lbl_name}")}]},
    ])
    img["extension_manifest"] = manifest(RENDERING_EXT, LABELS_EXT)
    set_ome(n1, img)
    set_ome(n1 / "labels", None)  # plain group now; embedded_labels replaces the 0.5 labels list
    set_ome(n1 / "labels" / lbl_name, seg1)

    # seg_*: one new segmentation per channel, from the copied image
    src = zarr.open_group(n1, mode="r")
    datasets = src_ome["multiscales"][0]["datasets"]
    nodes = [{"type": "multiscale", "id": img["id"], "name": IMAGE, "path": path(f"./{IMAGE}")}]
    transforms = []
    for node, (c, fill) in SEGS.items():
        seg = segment(src[datasets[0]["path"]][c], fill)[None]  # keep c axis, size 1
        g = zarr.open_group(OUT / node, mode="w")
        for i, ds in enumerate(datasets):
            h, w = src[ds["path"]].shape[-2:]  # source pyramid floors odd sizes
            g.create_array(f"s{i}", data=seg[..., :: 2**i, :: 2**i][..., :h, :w], chunks=(1, 10, 256, 256))
        doc = multiscale(src_ome["multiscales"][0], node, [{
            "type": "labels",
            "source": [ref("multiscale", img["id"])],  # resolves via the collection's image node
            "label_attributes": [{"label_value": v} for v in range(1, int(seg.max()) + 1)],
        }], scale_path=lambda i, ds: f"s{i}")
        set_ome(OUT / node, doc)
        nodes.append({"type": "multiscale", "id": doc["id"], "name": node, "path": path(f"./{node}")})
        transforms.append({
            "type": "identity",
            "input": ref("coordinate_system", doc["coordinate_systems"][0]["id"], f"./{node}"),
            "output": ref("coordinate_system", img["coordinate_systems"][0]["id"], f"./{IMAGE}"),
        })
        print(f"{node}: {seg.max()} objects, shape {seg.shape}")

    set_ome(OUT, {
        "version": VERSION,
        "type": "collection",
        "id": uuid7(),
        "name": SRC.stem,
        "nodes": nodes,
        "traits": [{"type": "scene", "coordinate_transformations": transforms}],
    })


if __name__ == "__main__":
    main()
    # self-check: no "..", every node / embedded node resolves by id, every scale is a real array
    def ome(p):
        return json.loads((p / "zarr.json").read_text())["attributes"]["ome"]

    text = "".join(f.read_text() for f in OUT.rglob("zarr.json"))
    assert '"../' not in text and '".."' not in text
    root = ome(OUT)
    docs = [(OUT / n["path"]["href"], n["id"]) for n in root["nodes"]]
    for t in ome(OUT / IMAGE)["traits"]:
        docs += [(OUT / IMAGE / n["path"]["href"], n["id"]) for n in t.get("nodes", [])]
    for p, id_ in docs:
        d = ome(p)
        assert d["id"] == id_, p
        for s in d["scales"]:
            assert json.loads((p / s["path"]["href"] / "zarr.json").read_text())["node_type"] == "array"
    a = zarr.open_group(OUT / IMAGE)
    for node in SEGS:
        b = zarr.open_group(OUT / node)
        assert all(a[str(i)].shape[1:] == b[f"s{i}"].shape[1:] for i in range(3)), node
    print("ok")
