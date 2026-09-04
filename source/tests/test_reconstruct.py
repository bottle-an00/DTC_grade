from dtc_transform.reconstruct import reconstruct_rows


def test_reconstructs_clean_9_field_lines():
    lines = [
        "4WD(4WheelDrive)\tP060241\tControl Module Programming Error\tX\tX\tX\tX\tD\t(no information)",
        "4WD(4WheelDrive)\tP172546\tEEPROM checksum fault\tO\tX\tX\tAWD not working\tC\tWarning lights being turned on / Drivable",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == []
    assert len(rows) == 2
    assert rows[0].sheet == "4WD(4WheelDrive)"
    assert rows[0].dtc == "P060241"
    assert rows[0].grade == "D"
    assert rows[1].dtc == "P172546"
    assert rows[1].grading_background == "Warning lights being turned on / Drivable"


def test_leading_orphan_line_with_no_preceding_record_is_reported():
    lines = [
        "(in case of breakdown, staying display off)",
        "4WD(4WheelDrive)\tP060241\tControl Module Programming Error\tX\tX\tX\tX\tD\t(no information)",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == ["(in case of breakdown, staying display off)"]
    assert len(rows) == 1
    assert rows[0].dtc == "P060241"


def test_blank_lines_are_skipped():
    lines = [
        "",
        "4WD(4WheelDrive)\tP060241\tControl Module Programming Error\tX\tX\tX\tX\tD\t(no information)",
        "",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert len(rows) == 1
    assert orphans == []


def test_fewer_than_9_fields_are_padded_with_empty_strings():
    lines = [
        "4WD(4WheelDrive)\tP060241\tControl Module Programming Error\tX\tX",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == []
    assert len(rows) == 1
    assert rows[0].sheet == "4WD(4WheelDrive)"
    assert rows[0].dtc == "P060241"
    assert rows[0].description == "Control Module Programming Error"
    assert rows[0].warning_light == "X"
    assert rows[0].warning_message == "X"
    assert rows[0].limp_home == ""
    assert rows[0].fail_safe == ""
    assert rows[0].grade == ""
    assert rows[0].grading_background == ""


def test_parses_quoted_field_with_embedded_tab_and_quote_real_data():
    # Real production line (ABSESP sheet, C110101). The Fail_Safe cell is
    # quoted per RFC4180-style TSV quoting and its content happens to start
    # with a raw tab character before the text. A naive split("\t") treats
    # the lone `"` as its own field and corrupts Grade/GradingBackground;
    # csv-aware parsing must recover the correct 9 logical fields.
    lines = [
        'ABSESP(Anti-lockBrakingSystem)\tC110101\tBattery Voltage High\tO\tO\tX\t"\tWarning lights being turned on"\tC\tDelete when vehicle voltage condition is restored / Expected high frequency of occurrence',
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == []
    assert len(rows) == 1
    row = rows[0]
    assert row.sheet == "ABSESP(Anti-lockBrakingSystem)"
    assert row.dtc == "C110101"
    assert row.fail_safe == "Warning lights being turned on"
    assert row.grade == "C"
    assert row.grading_background == (
        "Delete when vehicle voltage condition is restored / Expected high frequency of occurrence"
    )


def test_parses_quoted_field_with_embedded_newline_real_data():
    # Real production line (DSM sheet, B162100). The Fail_Safe cell contains
    # an embedded newline and is quoted, so the logical record spans two
    # physical lines of the source file.
    lines = [
        'DSM(DigitalSideMirror)\tB162100\tECU hardware Error\tO\tO\tX\t"모니터/카메라 자체 Reset(영구 고장시 Display OFF 상태 유지)',
        '(in case of breakdown, staying display off)"\tC\tDrivable / Warning lights being turned on / Warning messages is displayed',
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == []
    assert len(rows) == 1
    row = rows[0]
    assert row.dtc == "B162100"
    assert row.fail_safe == (
        "모니터/카메라 자체 Reset(영구 고장시 Display OFF 상태 유지)\n"
        "(in case of breakdown, staying display off)"
    )
    assert row.grade == "C"
