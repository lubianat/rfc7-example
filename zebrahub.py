"""Zebrahub ZSNS001 z-max time-lapse -> rfc7_zebrahub.zarr: draft RFC-8 multiscale with RFC-7
`coordinates` (channel + time intervals = somite stages), `default_rendering` and
`biological_metadata` (channel entities + a `timelapse` block annotating the intervals with ZFS).

Source: ZSNS001_zmax_lowres_0.5.zarr (see its AGENTS.md; Lange et al., Cell 2024, CC BY 4.0).
The frame -> hpf mapping is UNKNOWN; STAGES below is a rough DEMO mapping (see README).

Run: uv run --with zarr --with scipy zebrahub.py
"""
import json
import shutil
from pathlib import Path

from add_rfc7 import BIO
from to_rfc8 import manifest, multiscale, set_ome, uuid7

SRC = Path("ZSNS001_zmax_lowres_0.5.zarr")
OUT = Path("rfc7_zebrahub.zarr")
# DEMO: linear 10.33 hpf (frame 0) -> 24 hpf (last frame); Kimmel et al. 1995 stage start times
HPF0, HPF1 = 10.33, 24.0
STAGES = [  # (start hpf, ZFS label, ZFS id)
    (10.33, "segmentation:1-4 somites", "zfs:0000023"),
    (11.66, "segmentation:5-9 somites", "zfs:0000024"),
    (14.0, "segmentation:10-13 somites", "zfs:0000025"),
    (16.0, "segmentation:14-19 somites", "zfs:0000026"),
    (19.0, "segmentation:20-25 somites", "zfs:0000027"),
    (22.0, "segmentation:26+ somites", "zfs:0000028"),
]
CHANNEL_BIO = {
    "entities": [
        {"name": "mCherry", "role": "signal"},
        {"name": "H2A.Z", "role": "target", "external_id": "uniprot:Q71PD7"},  # h2az2a (h2afva)
        {"name": "nucleus", "role": "observed_entity", "external_id": "go:0005634"},
        {"name": "Danio rerio", "role": "organism", "external_id": "ncbitaxon:7955"},
    ],
    "relationships": [
        {"subject": "mCherry", "relation": "tags", "object": "H2A.Z"},
        {"subject": "H2A.Z", "relation": "located_in", "object": "nucleus"},
    ],
}


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(SRC, OUT, ignore=shutil.ignore_patterns("AGENTS.md"))
    src = json.loads((SRC / "zarr.json").read_text())["attributes"]["ome"]
    ms = src["multiscales"][0]
    n_t = json.loads((SRC / ms["datasets"][0]["path"] / "zarr.json").read_text())["shape"][0]

    frame = lambda h: round((h - HPF0) / (HPF1 - HPF0) * (n_t - 1))  # noqa: E731
    starts = [frame(h) for h, *_ in STAGES] + [n_t]
    intervals = [{"id": uuid7(), "start": a, "stop": b, "label": label}
                 for a, b, (_, label, _) in zip(starts, starts[1:], STAGES)]
    ch = uuid7()
    omero = src["omero"]
    doc = multiscale(ms, ms["name"], [
        {"type": "default_rendering", "rdefs": omero.get("rdefs", {}),
         "channels": [{"channel": {"type": "channel", "ref": ch}, **omero["channels"][0]}]},
        {"type": BIO + "biological_metadata",
         "channels": [{"channel": {"type": "channel", "ref": ch}, **CHANNEL_BIO}],
         "timelapse": [{"interval": {"type": "interval", "ref": iv["id"]},
                        "entities": [{"name": label, "role": "developmental_stage", "external_id": zfs}]}
                       for iv, (_, label, zfs) in zip(intervals, STAGES)]},
    ])
    items = list(doc.items())  # coordinates right after coordinate_systems, as in add_rfc7.py
    items.insert(list(doc).index("coordinate_systems") + 1, ("coordinates", [
        {"id": uuid7(), "type": "channel", "axis": "c", "element_ids": [ch], "element_names": ["h2az2a_mcherry"]},
        {"id": uuid7(), "type": "time", "axis": "t", "intervals": intervals},
    ]))
    doc = dict(items)
    doc["extension_manifest"] = manifest(BIO)
    set_ome(OUT, doc)


if __name__ == "__main__":
    main()
    # self-check: intervals tile the t axis, timelapse refs hit intervals, ids unique
    ome = json.loads((OUT / "zarr.json").read_text())["attributes"]["ome"]
    _, t = ome["coordinates"]
    n_t = json.loads((OUT / "0" / "zarr.json").read_text())["shape"][0]
    ivs = t["intervals"]
    assert ivs[0]["start"] == 0 and ivs[-1]["stop"] == n_t
    assert all(a["stop"] == b["start"] and a["start"] < a["stop"] for a, b in zip(ivs, ivs[1:]))
    bio = next(x for x in ome["traits"] if x["type"].endswith("biological_metadata"))
    assert [x["interval"]["ref"] for x in bio["timelapse"]] == [iv["id"] for iv in ivs]
    ids = [c["id"] for c in ome["coordinates"]] + ome["coordinates"][0]["element_ids"] + [iv["id"] for iv in ivs]
    assert len(ids) == len(set(ids))
    assert not (OUT / "AGENTS.md").exists()
    print([(iv["label"], iv["start"], iv["stop"]) for iv in ivs])
    print("ok")
