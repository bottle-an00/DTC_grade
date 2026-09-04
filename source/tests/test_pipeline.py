import json
import sqlite3

from dtc_transform.pipeline import run_pipeline


def test_end_to_end_pipeline(tmp_path):
    input_path = tmp_path / "input.txt"
    input_path.write_text(
        "\n".join(
            [
                "TCU(TransmissionControlUnit)\tP0AC200\tDesc A\tX\tX\tX\tX\tD\tbg",
                "TCU(TransmissionControlUnit)\tP0AC200\tDesc A duplicate\tX\tX\tX\tX\tD\tbg",
                "TCU(TransmissionControlUnit)\tP0AC200\tDesc A\tX\tX\tX\tX\tB\tbg",
                "UNKNOWN(Sheet)\tP111111\tUnmapped desc\tX\tX\tX\tX\tC\tbg",
            ]
        ),
        encoding="utf-8",
    )

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps({"TCU(TransmissionControlUnit)": {"system": "AT,CVT,AMT,IMT,DCT", "confidence": 0.85, "hits": 3}}),
        encoding="utf-8",
    )

    output_path = tmp_path / "out.sqlite"
    report_path = tmp_path / "report.txt"

    stats = run_pipeline(
        input_path=str(input_path),
        mapping_path=str(mapping_path),
        output_path=str(output_path),
        report_path=str(report_path),
    )

    assert stats["raw_row_count"] == 4
    assert stats["after_dedup_count"] == 2  # TCU/P0AC200 (B wins over D) + UNKNOWN/P111111
    assert stats["after_expand_count"] == 3  # + TCU/P0AC2 shortened row
    assert stats["unmapped_sheets"] == ["UNKNOWN(Sheet)"]

    con = sqlite3.connect(str(output_path))
    cur = con.cursor()
    cur.execute('SELECT System, DTC, "DTC Class" FROM dtc_master ORDER BY System, DTC')
    rows = cur.fetchall()
    con.close()

    assert rows == [
        ("", "P111111", "Loxt0sBGAIWprCbYyMZIFw=="),
        ("AT,CVT,AMT,IMT,DCT", "P0AC2", "4CDbt0Ai5c3St5tcEQKANA=="),
        ("AT,CVT,AMT,IMT,DCT", "P0AC200", "4CDbt0Ai5c3St5tcEQKANA=="),
    ]

    report_text = report_path.read_text(encoding="utf-8")
    assert "UNKNOWN(Sheet)" in report_text
