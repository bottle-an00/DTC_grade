import json

from dtc_transform.mapping import SheetSystemMapping, attach_system
from dtc_transform.models import RawRow


def make_raw(sheet, dtc="P000001"):
    return RawRow(
        sheet=sheet, dtc=dtc, description="desc", warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade="D",
        grading_background="bg",
    )


def test_load_reads_json_mapping(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(
        json.dumps({"TCU(TransmissionControlUnit)": {"system": "AT,CVT,AMT,IMT,DCT", "confidence": 0.85, "hits": 475}}),
        encoding="utf-8",
    )

    mapping = SheetSystemMapping.load(str(path))

    assert mapping.system_for("TCU(TransmissionControlUnit)") == "AT,CVT,AMT,IMT,DCT"
    assert mapping.system_for("UNKNOWN_SHEET") is None


def test_low_confidence_sheets_returns_entries_below_threshold(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(
        json.dumps(
            {
                "A": {"system": "SYS_A", "confidence": 0.9, "hits": 10},
                "B": {"system": "SYS_B", "confidence": 0.3, "hits": 5},
            }
        ),
        encoding="utf-8",
    )

    mapping = SheetSystemMapping.load(str(path))

    low = mapping.low_confidence_sheets(threshold=0.5)
    assert low == [("B", 0.3)]


def test_attach_system_fills_known_sheets_and_reports_unmapped(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(
        json.dumps({"KNOWN(Sheet)": {"system": "SYS1", "confidence": 1.0, "hits": 1}}),
        encoding="utf-8",
    )
    mapping = SheetSystemMapping.load(str(path))
    raw_rows = [make_raw("KNOWN(Sheet)"), make_raw("UNKNOWN(Sheet)")]

    rows, unmapped = attach_system(raw_rows, mapping)

    by_sheet = {r.sheet: r for r in rows}
    assert by_sheet["KNOWN(Sheet)"].system == "SYS1"
    assert by_sheet["UNKNOWN(Sheet)"].system == ""
    assert unmapped == ["UNKNOWN(Sheet)"]
