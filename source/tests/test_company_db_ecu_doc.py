from dtc_transform.company_db.ecu_doc import load_ecu_doc_rows


def test_loads_doc_code_and_system_name_columns(tmp_path):
    csv_path = tmp_path / "ecu_doc.csv"
    csv_path.write_text(
        "92710100_ABC_1006101_001,4WD(4WheelDrive)\n"
        "92710100_ABC_D2O6_002,AIRBAG(Airbag)\n",
        encoding="utf-8",
    )

    rows = load_ecu_doc_rows(str(csv_path))

    assert rows == [
        ("4WD(4WheelDrive)", "92710100_ABC_1006101_001"),
        ("AIRBAG(Airbag)", "92710100_ABC_D2O6_002"),
    ]


def test_skips_blank_lines_and_strips_whitespace(tmp_path):
    csv_path = tmp_path / "ecu_doc.csv"
    csv_path.write_text(
        "\n"
        " 92710100_ABC_1006101_001 , 4WD(4WheelDrive) \n"
        "\n",
        encoding="utf-8",
    )

    rows = load_ecu_doc_rows(str(csv_path))

    assert rows == [("4WD(4WheelDrive)", "92710100_ABC_1006101_001")]
