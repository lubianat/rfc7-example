"""Copy rfc8_collection.zarr into seven cumulative examples (EXAMPLES) and add the RFC-7 draft
channel/axis reference mechanism (ngff#580) to every multiscale: a core `coordinates` field
(next to coordinate_systems) giving the channel axis an id and one UUID per channel index. The omero rendering trait becomes
a `default_rendering` trait referencing those channel UUIDs, and the image gets a labelled
z interval (Z_INTERVALS) a biological_metadata extension trait (BIO_CHANNELS),
and the OME-XML sidecar (OME_XML) copied in with an ome_xml_sidecar extension trait (pointer)
plus an ome_xml_metadata extension trait (its fields as JSON).

Run after to_rfc8.py: uv run add_rfc7.py  (reuses uuid7 from to_rfc8.py)
"""
import json
import xml.etree.ElementTree as ET
import shutil
from pathlib import Path

from lif_to_omexml import enrich
from to_rfc8 import IMAGE, uuid7

SRC = Path("rfc8_collection.zarr")
# Four cumulative examples, all built on the RFC-8 collection
EXAMPLES = {
    Path("rfc7_1_coordinates.zarr"): set(),
    Path("rfc7_2_bio.zarr"): {"bio"},
    Path("rfc7_3_rendering.zarr"): {"bio", "rendering"},
    Path("rfc7_4_ome_metadata.zarr"): {"bio", "rendering", "ome_metadata"},
    Path("rfc7_5_sidecar.zarr"): {"bio", "rendering", "ome_metadata", "sidecar"},
    Path("rfc7_6_labels.zarr"): {"bio", "rendering", "ome_metadata", "sidecar", "labels"},
    Path("rfc7_7_collection.zarr"): {"bio", "rendering", "ome_metadata", "sidecar", "labels", "collection"},
}
RENDERING = "https://example.org/omero-rendering/"
# Sparse labels on the z axis of the image (the image node): index range at scale 0, half-open
# [start, stop) like Python slices, so planes 100..150 inclusive -> stop 151.
# ponytail: index space of scale 0; physical-unit intervals if downsampled-z pyramids show up
Z_INTERVALS = [{"start": 100, "stop": 151, "label": "middle of the organoid"}]
# Biological metadata per channel, keyed by the omero channel label (draft from ngff#580,
# entities + GO/UniProt/ChEBI CURIEs as external_id, relationships between entity names)
# OME-XML for the original image, generated from B1_C1.tif with Bio-Formats:
#   showinf -nopix -omexml-only -no-upgrade B1_C1.tif > B1_C1.ome.xml
# Enriched from its Leica original metadata (lif_to_omexml.enrich) and written into the image node
# at the bioformats2raw location OME/METADATA.ome.xml.
OME_XML = Path("B1_C1.ome.xml")
OME_XML_HREF = "OME/METADATA.ome.xml"
METADATA = "https://example.org/ome-xml-metadata/"  # ponytail: placeholder namespace
SIDECAR = "https://example.org/ome-xml-sidecar/"  # ponytail: placeholder namespace
BIO = "https://example.org/biological-metadata/"  # ponytail: placeholder namespace
BIO_CHANNELS = {
    "Dapi": {
        "entities": [{"name": "DAPI", "role": "signal", "external_id": "chebi:51231"},
                     {"name": "DNA", "role": "target", "external_id": "chebi:16991"},
                     {"name": "nucleus", "role": "observed_entity", "external_id": "go:0005634"}],
        "relationships": [{"subject": "DAPI", "relation": "stains", "object": "DNA"},
                          {"subject": "DNA", "relation": "located_in", "object": "nucleus"}],
    },
    "LaminB1": {
        # DEMO signal: dye assumed (same as the OME-XML imputation, see README), not biological
        # but completes the signal -> target chain; antibodies in between are unknown
        "entities": [{"name": "Alexa Fluor 555", "role": "signal"},
                     {"name": "Lamin B1", "role": "target",
                      "external_id": "uniprot:P14733"},  # mouse LMNB1 (Mus musculus, IDR/paper)
                     {"name": "nuclear lamina", "role": "observed_entity", "external_id": "go:0005652"}],
        "relationships": [{"subject": "Alexa Fluor 555", "relation": "tags", "object": "Lamin B1"},
                          {"subject": "Lamin B1", "relation": "located_in", "object": "nuclear lamina"}],
    },
}
# Segmentations (node name -> entities of their single channel): what each one segments
SEG_BIO = {
    # original manual Nessys segmentation (IDR: segmented channel LaminB1)
    "default_seg": [{"name": "nucleus", "role": "observed_entity", "external_id": "go:0005634"}],
    "seg_dapi": [{"name": "nucleus", "role": "observed_entity", "external_id": "go:0005634"}],
    "seg_laminb1": [{"name": "nuclear lamina", "role": "observed_entity", "external_id": "go:0005652"}],
}


def load(group: Path) -> dict:
    return json.loads((group / "zarr.json").read_text())


def multiscales(group: Path):
    """Yield every multiscale group reachable from the collection: nodes + embedded_labels."""
    ome = load(group)["attributes"]["ome"]
    if ome["type"] == "multiscale":
        yield group
    for n in ome.get("nodes", []):
        yield from multiscales(group / n["path"]["href"])
    for t in ome.get("traits", []):
        if t["type"].endswith("/embedded_labels"):
            for n in t["nodes"]:
                yield from multiscales(group / n["path"]["href"])


def add_coordinates(group: Path, features: set) -> None:
    doc = load(group)
    ome = doc["attributes"]["ome"]
    axes = ome["coordinate_systems"][0]["axes"]
    c = next(i for i, a in enumerate(axes) if a["type"] == "channel")
    n = load(group / ome["scales"][0]["path"]["href"])["shape"][c]
    values = [uuid7() for _ in range(n)]
    coords = [{"id": uuid7(), "axis": axes[c]["name"], "values": values}]
    # core field next to coordinate_systems (dict order keeps it adjacent in the JSON)
    items = list(ome.items())
    items.insert(list(ome).index("coordinate_systems") + 1, ("coordinates", coords))
    ome = dict(items)
    doc["attributes"]["ome"] = ome
    # omero rendering extension -> default_rendering, channels by UUID instead of index
    omero = next((t for t in ome["traits"] if t["type"] == RENDERING + "rendering"), None)
    if omero:  # only the image (the image node) has it
        coords.append({"id": uuid7(), "axis": "z",
                       "intervals": [{"id": uuid7(), **iv} for iv in Z_INTERVALS]})
        ome["traits"].remove(omero)
        ome["extension_manifest"] = [m for m in ome["extension_manifest"] if m["id"] != RENDERING]
        if not ome["extension_manifest"]:
            del ome["extension_manifest"]
        # ponytail: before the rendering step the omero block is just dropped (no rendering at all)
        if "rendering" in features:
            ome["traits"].append({
                "type": "default_rendering",
                "rdefs": omero["rdefs"],
                "channels": [{"channel": {"type": "channel", "ref": v}, **ch}
                             for v, ch in zip(values, omero["channels"], strict=True)],
            })  # omero["id"] (OMERO server image id) dropped: not rendering
        if "bio" in features:
            ome["traits"].append({
                "type": BIO + "biological_metadata",
                "channels": [{"channel": {"type": "channel", "ref": v}, **BIO_CHANNELS[ch["label"]]}
                             for v, ch in zip(values, omero["channels"]) if ch["label"] in BIO_CHANNELS],
            })
            ome.setdefault("extension_manifest", []).append({"id": BIO, "version": "0.1", "schemas": []})
        add_ome_xml(group, ome, values, features)
    if "bio" in features and ome["name"] in SEG_BIO:
        add_seg_bio(ome, values)
    (group / "zarr.json").write_text(json.dumps(doc, indent=2))


def add_seg_bio(ome: dict, values: list) -> None:
    """Label the single channel of a segmentation with what it segments."""
    ome["traits"].append({
        "type": BIO + "biological_metadata",
        "channels": [{"channel": {"type": "channel", "ref": values[0]}, "entities": SEG_BIO[ome["name"]]}],
    })
    ome.setdefault("extension_manifest", []).append({"id": BIO, "version": "0.1", "schemas": []})


def add_ome_xml(group: Path, ome: dict, values: list, features: set) -> None:
    """Enrich the OME-XML; optionally ship it next to the image (sidecar) and/or copy its fields in."""
    dest = group / OME_XML_HREF
    dest.parent.mkdir()
    enrich(OME_XML, dest)
    if "ome_metadata" in features:
        add_ome_xml_metadata(ome, ET.parse(dest).getroot(), values)
    if "sidecar" in features:
        ome["traits"].append({
            "type": SIDECAR + "ome_xml_sidecar",
            "path": {"type": "xml", "format": "relative", "href": f"./{OME_XML_HREF}"},
        })
        ome["extension_manifest"].append({"id": SIDECAR, "version": "0.1", "schemas": []})
    else:
        shutil.rmtree(dest.parent)  # metadata only lives in zarr.json


def snake(attrs: dict) -> dict:
    """OME-XML attributes -> snake_case JSON fields (numbers as numbers, IDs dropped)."""
    out = {}
    for k, v in attrs.items():
        if k == "ID" or k == "SamplesPerPixel":
            continue
        k = "".join(f"_{c.lower()}" if c.isupper() else c for c in k).lstrip("_").replace("_n_a", "_na")
        try:
            v = float(v) if "." in v else int(v)
        except ValueError:
            pass
        out[k] = v
    return out


def add_ome_xml_metadata(ome: dict, root: ET.Element, values: list) -> None:
    """Copy the enriched OME-XML fields into the zarr.json itself (no XML needed to read them)."""
    pixels = root.find("{*}Image/{*}Pixels")
    ome["traits"].append({
        "type": METADATA + "ome_xml_metadata",
        "microscope": snake(root.find("{*}Instrument/{*}Microscope").attrib),
        "objective": snake(root.find("{*}Instrument/{*}Objective").attrib),
        "significant_bits": int(pixels.get("SignificantBits")),
        # ponytail: name/fluor/wavelengths are DEMO values (see README), copied as-is from the XML
        "channels": [{"channel": {"type": "channel", "ref": v}, **snake(ch.attrib)}
                     for v, ch in zip(values, pixels.findall("{*}Channel"), strict=True)],
    })
    ome.setdefault("extension_manifest", []).append({"id": METADATA, "version": "0.1", "schemas": []})


def strip_labels(img: Path) -> None:
    """Drop the embedded default segmentation (labels/0 + embedded_labels trait) from the image."""
    doc = load(img)
    ome = doc["attributes"]["ome"]
    ome["traits"] = [t for t in ome["traits"] if not t["type"].endswith("/embedded_labels")]
    ome["extension_manifest"] = [m for m in ome["extension_manifest"] if "embedded-labels" not in m["id"]]
    (img / "zarr.json").write_text(json.dumps(doc, indent=2))
    shutil.rmtree(img / "labels")


def image(out: Path, features: set) -> Path:
    return out / IMAGE if "collection" in features else out


def main() -> None:
    for out, features in EXAMPLES.items():
        shutil.rmtree(out, ignore_errors=True)
        # ponytail: examples 1-6 are the bare image multiscale (no collection around it)
        shutil.copytree(SRC if "collection" in features else SRC / IMAGE, out)
        if "labels" not in features:
            strip_labels(out)
        for g in multiscales(out):
            add_coordinates(g, features)
        print(out, sorted(features))


def check(out: Path, features: set) -> None:
    """Each multiscale got one channel id per channel, all ids unique, only the asked-for traits."""
    ids, types = [], set()
    img = image(out, features)
    assert (out / "seg_dapi").exists() == ("collection" in features), out
    assert (img / "labels").exists() == ("labels" in features), out
    assert (img / OME_XML_HREF).exists() == ("sidecar" in features), out
    for g in multiscales(out):
        ome = load(g)["attributes"]["ome"]
        co, *rest = ome["coordinates"]
        shape = load(g / ome["scales"][0]["path"]["href"])["shape"]
        assert len(co["values"]) == shape[0], g
        ids += [co["id"], *co["values"]]
        for z in rest:  # z intervals fit inside the z axis
            assert all(0 <= iv["start"] < iv["stop"] <= shape[1] for iv in z["intervals"]), g
            ids += [z["id"], *(iv["id"] for iv in z["intervals"])]
        assert not any(t["type"].startswith(RENDERING) for t in ome["traits"]), g
        types |= {t["type"] for t in ome["traits"]}
        for t in ome["traits"]:
            if t["type"] == BIO + "biological_metadata":
                assert {ch["channel"]["ref"] for ch in t["channels"]} <= set(co["values"]), g
                for ch in t["channels"]:  # relationships only name entities of the same channel
                    names = {e["name"] for e in ch["entities"]}
                    assert all({r["subject"], r["object"]} <= names for r in ch.get("relationships", [])), g
            if t["type"] == SIDECAR + "ome_xml_sidecar":  # XML exists and matches the scale-0 grid
                px = ET.parse(g / t["path"]["href"]).getroot().find("{*}Image/{*}Pixels")
                sizes = [int(px.get(f"Size{a}")) for a in "CZYX"]
                assert sizes == shape, (sizes, shape)
            if t["type"] == METADATA + "ome_xml_metadata":
                assert [ch["channel"]["ref"] for ch in t["channels"]] == co["values"], g
                assert all("fluor" in ch for ch in t["channels"]), g
            if t["type"] == "default_rendering":
                assert [ch["channel"]["ref"] for ch in t["channels"]] == co["values"], g
    assert len(ids) == len(set(ids))
    trait = {"bio": BIO + "biological_metadata", "ome_metadata": METADATA + "ome_xml_metadata",
             "sidecar": SIDECAR + "ome_xml_sidecar", "rendering": "default_rendering"}
    assert types & set(trait.values()) == {trait[f] for f in features if f in trait}, (out, types)


if __name__ == "__main__":
    main()
    for out, features in EXAMPLES.items():
        check(out, features)
    print("ok")
