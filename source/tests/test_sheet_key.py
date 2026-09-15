from dtc_transform.sheet_key import normalize_sheet_key


def test_spacing_and_parenthesis_differences_collapse_to_the_same_key():
    # The workbook and ECU DOC spell the same controller differently.
    assert normalize_sheet_key("4WD(4WheelDrive)") == normalize_sheet_key("4WD (4 Wheel Drive)")
    assert normalize_sheet_key("BSD(BlindSpotDetection)") == normalize_sheet_key("BSD (Blind Spot Detection)")


def test_case_differences_collapse():
    assert normalize_sheet_key("E-Shift(29bit)") == normalize_sheet_key("E-shift (29Bit)")


def test_full_width_characters_fold_onto_ascii():
    assert normalize_sheet_key("ＡＢＳ") == normalize_sheet_key("ABS")


def test_distinct_controllers_stay_distinct():
    assert normalize_sheet_key("IBU(IntegratedBodyUnit)") != normalize_sheet_key("BDC(BodyDomainController)")
    assert normalize_sheet_key("DSM(DigitalSideMirror)") != normalize_sheet_key("DHS(DoorHandleSensorModule)")


def test_empty_and_symbol_only_names_reduce_to_empty():
    assert normalize_sheet_key("") == ""
    assert normalize_sheet_key(" / () - ") == ""
