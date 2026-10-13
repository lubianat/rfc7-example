# RFC-8 + RFC-7 worked example (IDR image 6001240, idr0062 Blin et al.)

> **Status: initial RFC-7 prototype, built on an imaginary base.** These examples do not follow any
> released RFC or OME-NGFF spec. The RFC-8 layer (collections, traits, UUIDv7 ids, typed refs,
> `extension_manifest`) is our reading of ongoing RFC-8 discussions, not an accepted design. The RFC-7
> parts will be rebased on whatever collection + extension mechanism RFC-8 settles on.
>
> Scope within RFC-7: **`coordinates`** (channel/axis references) and **`biological_metadata`** are the
> core. **`default_rendering`** is a stretch goal. **`ome_xml_metadata`** is a demo, outside the current
> scope. **`ome_xml_sidecar`**, the **labels** (`embedded_labels`, segmentations) and the **collection**
> are not official and not part of RFC-7. They are included only to show the RFC-7 pieces in a realistic context.

## Hydrate

The repo ships the source image (`6001240_labels.zarr`, `B1_C1.ome.xml`) in full, but only the
**metadata** (`zarr.json`, `*.ome.xml`) of the generated `rfc*.zarr` folders. To get the array chunks back:

```sh
uv run to_rfc8.py && uv run --with zarr --with scipy add_rfc7.py
```

This rebuilds every output from scratch, so ids (UUIDv7) differ from the committed ones.

## Examples

- `to_rfc8.py` -> `rfc8_collection.zarr/`: RFC-8 collection with nodes `image/` (with its original
  segmentation embedded at `image/labels/0`), `seg_dapi/` and `seg_laminb1/` (simple Otsu segmentations).
  `seg_dapi`/`seg_laminb1` are z,y,x and show the **implicit channel** coordinate (no `axis`, scalar
  `element_ids`/`element_names`); `default_seg` keeps the original size-1 `c` axis (explicit form).
- `add_rfc7.py` -> seven cumulative RFC-7 examples:

| Output | Root | Adds |
|---|---|---|
| `rfc7_1_coordinates.zarr` | multiscale | image only: core `coordinates` (channel UUIDs, labelled z interval); omero rendering dropped |
| `rfc7_2_bio.zarr` | multiscale | + `biological_metadata` extension |
| `rfc7_3_rendering.zarr` | multiscale | + `default_rendering` (omero rendering, channels by UUID) |
| `rfc7_4_ome_metadata.zarr` | multiscale | + `ome_xml_metadata` extension (OME-XML fields as JSON, no XML file) |
| `rfc7_5_sidecar.zarr` | multiscale | + `ome_xml_sidecar` extension and `OME/METADATA.ome.xml` (built by `lif_to_omexml.py`) |
| `rfc7_6_labels.zarr` | multiscale | + embedded default segmentation (`labels/0`, `embedded_labels` extension, with its `biological_metadata`) |
| `rfc7_7_collection.zarr` | collection | + collection: the image as `image/`, new `seg_dapi/`, `seg_laminb1/` nodes and `scene` |

## ⚠️ Demo values, not real metadata

Some fields were filled in **only to demonstrate the format**. They may not match the original acquisition:

- **Channel fluorophores and wavelengths** (OME-XML `Fluor`, `ExcitationWavelength`, `EmissionWavelength`):
  not present in the TIFF/OME-XML. DAPI uses textbook peaks (ex 358 / em 461 nm). The LaminB1 secondary
  antibody dye is unknown; **Alexa Fluor 555 (ex 555 / em 565 nm) is assumed**. The same assumed dye is the
  LaminB1 `signal` entity (and its `tags` relationship) in `biological_metadata`.
- **Objective** taken from the paper's S1 Table (40x/1.30 Oil); the embedded Leica metadata says 63x/1.40
  (kept as an XML comment).
- All extension namespaces (`https://example.org/...`) are placeholders.

## Viewer

`vizarr/` is a vendored copy of [biongff/vizarr](https://github.com/biongff/vizarr) (MIT, license kept)
with draft RFC-8/RFC-7 support; see `vizarr/VENDORED.md`.

### See the metadata in vizarr

Needs Node.js + pnpm, and hydrated examples (see [Hydrate](#hydrate)).

```sh
npx http-server -p 8000 --cors      # terminal 1, in this folder: serves the .zarr examples
cd vizarr && pnpm install && pnpm dev   # terminal 2: viewer on http://localhost:5173
```

Then open (ports as above; vite picks the next free port if 5173 is taken):

- [rfc7_1_coordinates](http://localhost:5173/?source=http://localhost:8000/rfc7_1_coordinates.zarr): channel names from `element_names`, channel UUID in the popover
- [rfc7_2_bio](http://localhost:5173/?source=http://localhost:8000/rfc7_2_bio.zarr): + biological metadata popover
- [rfc7_3_rendering](http://localhost:5173/?source=http://localhost:8000/rfc7_3_rendering.zarr): + colors/windows/z from `default_rendering`
- [rfc7_4_ome_metadata](http://localhost:5173/?source=http://localhost:8000/rfc7_4_ome_metadata.zarr): (OME-XML metadata not displayed yet)
- [rfc7_5_sidecar](http://localhost:5173/?source=http://localhost:8000/rfc7_5_sidecar.zarr): (sidecar not displayed yet)
- [rfc7_6_labels](http://localhost:5173/?source=http://localhost:8000/rfc7_6_labels.zarr): + embedded segmentation as a label layer
- [rfc7_7_collection](http://localhost:5173/?source=http://localhost:8000/rfc7_7_collection.zarr): collection: image + `seg_dapi` / `seg_laminb1` as label layers
- [original OME-Zarr 0.5](http://localhost:5173/?source=http://localhost:8000/6001240_labels.zarr): unchanged upstream behaviour

What to look for: channel names with a dotted underline open a popover (click) with the channel
`element_names`, UUID, and biological metadata (CURIEs link to bioregistry.io); label names under
"labels:" do the same for segmentations; the Z slider marks the labelled interval, named below it.

## AI use

Code, metadata and this README were drafted with Claude Code (Claude Opus 5.5, `claude-opus-5-5`),
using the ponytail plugin (minimal-code style) and Bio-Formats `showinf` for the OME-XML. All choices
were directed and reviewed by the human operator, who takes full responsibility for the content.
