from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from javsorter.core.models import MetadataRecord


def build_nfo_element(record: MetadataRecord, cover_filename: str | None = None) -> ET.Element:
    movie = ET.Element("movie")

    ET.SubElement(movie, "title").text = record.title
    ET.SubElement(movie, "originaltitle").text = record.title

    uniqueid = ET.SubElement(movie, "uniqueid", type="r18", default="true")
    uniqueid.text = record.content_id

    if record.studio:
        ET.SubElement(movie, "studio").text = record.studio

    if record.release_date:
        ET.SubElement(movie, "premiered").text = record.release_date
        year = record.release_date.split("-")[0]
        if year.isdigit():
            ET.SubElement(movie, "year").text = year

    if record.runtime_minutes:
        ET.SubElement(movie, "runtime").text = str(record.runtime_minutes)

    if record.rating is not None:
        ET.SubElement(movie, "rating").text = str(record.rating)

    if record.director:
        ET.SubElement(movie, "director").text = record.director

    for genre in record.genres:
        ET.SubElement(movie, "genre").text = genre

    for actress in record.actresses:
        actor = ET.SubElement(movie, "actor")
        ET.SubElement(actor, "name").text = actress

    if cover_filename:
        ET.SubElement(movie, "thumb").text = cover_filename

    return movie


def write_nfo(record: MetadataRecord, nfo_path: Path, cover_filename: str | None = None) -> None:
    movie = build_nfo_element(record, cover_filename=cover_filename)
    tree = ET.ElementTree(movie)
    ET.indent(tree, space="  ")
    nfo_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(nfo_path, encoding="utf-8", xml_declaration=True)
