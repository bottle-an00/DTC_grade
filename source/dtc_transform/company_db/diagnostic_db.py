import os
import xml.etree.ElementTree as ET

from .code_extract import extract_compare_code

TARGET_SUFFIXES = ("D0", "A0")


def is_target_file(filename: str) -> bool:
    stem = os.path.splitext(filename)[0]
    return stem[-2:].upper() in TARGET_SUFFIXES


def read_systemid(xml_path: str) -> str:
    """Read only the root element's systemid attribute -- stops parsing
    immediately after the root start tag so large files don't get fully
    loaded into memory just to read one attribute."""
    for _event, elem in ET.iterparse(xml_path, events=("start",)):
        return elem.get("systemid", "")
    return ""


def build_diagnostic_index(root_dir: str) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}

    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.lower().endswith(".xml"):
                continue
            if not is_target_file(filename):
                continue

            stem = os.path.splitext(filename)[0]
            # The last 2 characters are the region/version suffix checked by
            # is_target_file (D0/A0); vehicle_info's ecucode matches the
            # remaining 4-character "document title" prefix, not the full stem.
            document_title = stem[:-2]
            try:
                systemid = read_systemid(os.path.join(dirpath, filename))
            except ET.ParseError:
                continue
            if not systemid:
                continue

            try:
                compare_code = extract_compare_code(systemid)
            except ValueError:
                continue

            index.setdefault(compare_code, []).append(document_title)

    return index
