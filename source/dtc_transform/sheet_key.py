import re
import unicodedata


def normalize_sheet_key(name: str) -> str:
    """Collapse a sheet/system name to a comparison key.

    The same controller is written differently depending on which source
    the name came from -- the DTC master workbook uses "4WD(4WheelDrive)"
    while ECU DOC uses "4WD (4 Wheel Drive)". Stripping everything that
    isn't alphanumeric (after NFKC, so full-width characters fold onto
    their ASCII forms) makes those two forms the same key.
    """
    folded = unicodedata.normalize("NFKC", name)
    return re.sub(r"[^a-z0-9]", "", folded.lower())
