from dtc_transform.constants import DTC_PATTERN, GRADE_SEVERITY


def test_dtc_pattern_matches_valid_codes():
    assert DTC_PATTERN.match("P0AC200")
    assert DTC_PATTERN.match("b160487".upper())
    assert DTC_PATTERN.match("C152811")
    assert DTC_PATTERN.match("U002888")


def test_dtc_pattern_rejects_invalid_codes():
    assert not DTC_PATTERN.match("XYZ123")
    assert not DTC_PATTERN.match("")
    assert not DTC_PATTERN.match("Control Module Programming Error")


def test_grade_severity_order():
    assert GRADE_SEVERITY["A"] < GRADE_SEVERITY["B"] < GRADE_SEVERITY["C"] < GRADE_SEVERITY["D"]
