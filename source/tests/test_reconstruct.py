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


def test_rejoins_line_broken_by_embedded_newline():
    lines = [
        "VPC(VehiclePlatformController)\tC110117\tBattery Voltage High\tX\tX\tX\tLimited operation of some functions\tC\tDrivable / CDCU system operation abnormality",
        "When the 12V battery voltage or the 12V battery charging voltage",
        "is out of range, DTC will be generated",
        "VPC(VehiclePlatformController)\tC110216\tBattery Voltage Low\tX\tX\tX\tLimited operation of some functions\tC\tDrivable / CDCU system operation abnormality",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == []
    assert len(rows) == 2
    assert rows[0].dtc == "C110117"
    assert rows[0].grading_background == (
        "Drivable / CDCU system operation abnormality "
        "When the 12V battery voltage or the 12V battery charging voltage "
        "is out of range, DTC will be generated"
    )
    assert rows[1].dtc == "C110216"


def test_leading_orphan_line_with_no_preceding_record_is_reported():
    lines = [
        "(in case of breakdown, staying display off)",
        "4WD(4WheelDrive)\tP060241\tControl Module Programming Error\tX\tX\tX\tX\tD\t(no information)",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == ["(in case of breakdown, staying display off)"]
    assert len(rows) == 1
    assert rows[0].dtc == "P060241"


def test_line_with_extra_tab_in_last_field_is_normalized():
    lines = [
        "ABSESP(Anti-lockBrakingSystem)\tC110913\tIG1 Open\tX\tX\tX\tLimited operation\tD\tsome\tbackground\ttext",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == []
    assert len(rows) == 1
    assert rows[0].grade == "D"
    assert rows[0].grading_background == "some\tbackground\ttext"


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
