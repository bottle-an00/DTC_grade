from dtc_transform.models import RawRow, Row


def test_raw_row_fields():
    row = RawRow(
        sheet="TCU(TransmissionControlUnit)", dtc="P0AC200", description="desc",
        warning_light="X", warning_message="X", limp_home="X", fail_safe="X",
        grade="D", grading_background="bg",
    )
    assert row.sheet == "TCU(TransmissionControlUnit)"
    assert row.dtc == "P0AC200"


def test_row_fields():
    row = Row(
        system="AT,CVT,AMT,IMT,DCT", dtc="P0AC200", description="desc",
        warning_light="X", warning_message="X", limp_home="X", fail_safe="X",
        grade="D", grading_background="bg", sheet="TCU(TransmissionControlUnit)",
    )
    assert row.system == "AT,CVT,AMT,IMT,DCT"
    assert row.sheet == "TCU(TransmissionControlUnit)"
