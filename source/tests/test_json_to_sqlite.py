import json
import sqlite3
import sys

import pytest

from tools.json_to_sqlite import convert, main


def make_row(sheet, dtc, description, system, grade="D"):
    return {
        "sheet": sheet,
        "dtc": dtc,
        "description": description,
        "warning_light": "X",
        "warning_message": "X",
        "limp_home": "X",
        "fail_safe": "X",
        "grade": grade,
        "grading_background": "bg",
        "system": system,
    }


def _write_matched_json(path, rows):
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")


def test_convert_produces_sqlite_from_already_matched_rows(tmp_path):
    matched_json = tmp_path / "matched.json"
    _write_matched_json(
        matched_json,
        [
            make_row("TCU(TransmissionControlUnit)", "P0AC200", "Desc A", "AT,CVT,AMT,IMT,DCT"),
            make_row("TCU(TransmissionControlUnit)", "P0AC200", "Desc A dup", "AT,CVT,AMT,IMT,DCT"),
            make_row("UNKNOWN(Sheet)", "P111111", "Unmapped desc", ""),
        ],
    )
    output_path = tmp_path / "out.sqlite"
    report_path = tmp_path / "report.txt"

    stats = convert(str(matched_json), str(output_path), str(report_path))

    assert stats["raw_row_count"] == 3
    assert stats["after_dedup_count"] == 2
    assert stats["unmapped_sheets"] == ["UNKNOWN(Sheet)"]

    con = sqlite3.connect(str(output_path))
    cur = con.cursor()
    cur.execute("SELECT System, DTC FROM dtc_master ORDER BY System, DTC")
    rows = cur.fetchall()
    con.close()
    assert ("AT,CVT,AMT,IMT,DCT", "P0AC200") in rows
    assert ("", "P111111") in rows

    report_text = report_path.read_text(encoding="utf-8")
    assert "UNKNOWN(Sheet)" in report_text


def test_main_exits_nonzero_when_sheets_unmapped(tmp_path, monkeypatch, capsys):
    matched_json = tmp_path / "matched.json"
    _write_matched_json(matched_json, [make_row("UNKNOWN(Sheet)", "P111111", "desc", "")])
    output_path = tmp_path / "out.sqlite"
    report_path = tmp_path / "report.txt"

    monkeypatch.setattr(
        "sys.argv",
        [
            "json_to_sqlite",
            "--matched-json", str(matched_json),
            "--output", str(output_path),
            "--report", str(report_path),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    assert "UNKNOWN(Sheet)" in capsys.readouterr().err


def test_main_exits_zero_when_no_sheets_unmapped(tmp_path, monkeypatch):
    matched_json = tmp_path / "matched.json"
    _write_matched_json(
        matched_json, [make_row("TCU(TransmissionControlUnit)", "P0AC200", "desc", "AT,CVT,AMT,IMT,DCT")]
    )
    output_path = tmp_path / "out.sqlite"
    report_path = tmp_path / "report.txt"

    monkeypatch.setattr(
        "sys.argv",
        [
            "json_to_sqlite",
            "--matched-json", str(matched_json),
            "--output", str(output_path),
            "--report", str(report_path),
        ],
    )

    main()  # must NOT raise SystemExit when there are no unmapped sheets
