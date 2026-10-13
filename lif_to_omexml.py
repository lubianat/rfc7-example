"""Tiny Leica-.lif-reader stand-in: promote a few Leica OriginalMetadata key/values (already in the
OME-XML as StructuredAnnotations) into proper OME-XML fields. Sample fields only, not complete.

  Instrument: Microscope (Leica, model, inverted) + Objective (model, NA, magnification, immersion)
  Image:      InstrumentRef + ObjectiveSettings
  Channel:    Name/Fluor/Ex/Em wavelengths (DEMO values, not from the file) + AcquisitionMode + PinholeSize (image-wide confocal setting, same for every channel)

Usage: python3 lif_to_omexml.py B1_C1.ome.xml out.ome.xml
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://www.openmicroscopy.org/Schemas/OME/2016-06"
ET.register_namespace("", NS)
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
LEICA = "B1 Image|ATLConfocalSettingDefinition|"  # ponytail: series name hardcoded to this file's "B1"
# Curated values from the paper (Blin et al. 2019, S1 Table) override the embedded Leica keys,
# which say 63x/1.40 for this crop.
CURATED_OBJECTIVE = {"Model": "HC PL APO CS2 40x/1.30 Oil", "LensNA": "1.3", "NominalMagnification": "40"}
# DEMO ONLY, not from the original metadata (see README): name, dye and nm per channel index.
# DAPI: textbook peaks. LaminB1: secondary dye unknown, assumed Alexa Fluor 555 (yellow-orange).
DEMO_CHANNELS = [
    {"Name": "LaminB1", "Fluor": "Alexa Fluor 555", "ExcitationWavelength": "555", "EmissionWavelength": "565"},
    {"Name": "Dapi", "Fluor": "DAPI", "ExcitationWavelength": "358", "EmissionWavelength": "461"},
]
IMMERSION = {"OIL": "Oil", "WATER": "Water", "GLYCEROL": "Glycerol", "DRY": "Air"}


def q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def enrich(src: Path, dest: Path) -> None:
    tree = ET.parse(src)
    root = tree.getroot()
    kv = {om[0].text: om[1].text for om in root.iter(q("OriginalMetadata"))}
    leica = {k[len(LEICA):]: v.strip() for k, v in kv.items() if k.startswith(LEICA)}

    instrument = ET.Element(q("Instrument"), ID="Instrument:0")
    ET.SubElement(instrument, q("Microscope"), Manufacturer="Leica", Model=leica["MicroscopeModel"],
                  Type="Inverted" if leica.get("IsInverseMicroscopeModel") == "1" else "Upright")
    instrument.append(ET.Comment(
        f" Objective from S1 Table (Blin et al. 2019); embedded Leica metadata says "
        f"{' '.join(leica['ObjectiveName'].split())} (NA {leica['NumericalAperture']}) "))
    ET.SubElement(instrument, q("Objective"), ID="Objective:0:0", Manufacturer="Leica",
                  Immersion=IMMERSION.get(leica["Immersion"], "Other"), **CURATED_OBJECTIVE)
    root.insert(0, instrument)  # schema order: Instrument before Image

    image = root.find(q("Image"))
    pos = 1 if image[0].tag == q("Description") else 0  # schema order: Description, InstrumentRef, ObjectiveSettings
    image.insert(pos, ET.Element(q("InstrumentRef"), ID="Instrument:0"))
    image.insert(pos + 1, ET.Element(q("ObjectiveSettings"), ID="Objective:0:0"))

    image.find(q("Pixels")).set("SignificantBits", kv["B1 Image|ChannelDescription|Resolution"].strip())  # 12-bit
    pinhole_um = f"{float(leica['Pinhole']) * 1e6:.3f}"  # Leica stores metres
    pixels = image.find(q("Pixels"))
    pixels.insert(0, ET.Comment(
        " DEMO: Channel Name/Fluor/Excitation/EmissionWavelength are not from the original metadata. "
        "DAPI = textbook peaks; LaminB1 secondary dye unknown, Alexa Fluor 555 assumed. "
        "Objective from paper S1 Table. SignificantBits from Leica ChannelDescription|Resolution. "))
    for ch, demo in zip(image.iter(q("Channel")), DEMO_CHANNELS, strict=True):
        ch.attrib.update(demo, ExcitationWavelengthUnit="nm", EmissionWavelengthUnit="nm")
        ch.set("AcquisitionMode", "LaserScanningConfocalMicroscopy")
        ch.set("PinholeSize", pinhole_um)
        ch.set("PinholeSizeUnit", "µm")

    ET.indent(tree)
    tree.write(dest, encoding="UTF-8", xml_declaration=True)


if __name__ == "__main__":
    enrich(Path(sys.argv[1]), Path(sys.argv[2]))
