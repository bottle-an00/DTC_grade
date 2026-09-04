from dtc_transform.dedup import dedup
from dtc_transform.models import Row


def make_row(system="SYS", dtc="P000000", grade="D", description="desc"):
    return Row(
        system=system, dtc=dtc, description=description, warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade=grade,
        grading_background="bg", sheet="Sheet",
    )


def test_same_system_dtc_grade_different_description_keeps_first():
    rows = [
        make_row(description="Control Unit Supply Voltage Open Circuit"),
        make_row(description="Open Unit Supply Voltage Open Circuit"),
    ]
    result = dedup(rows)
    assert len(result) == 1
    assert result[0].description == "Control Unit Supply Voltage Open Circuit"


def test_same_system_dtc_different_grade_keeps_more_severe():
    rows = [make_row(grade="C"), make_row(grade="D")]
    result = dedup(rows)
    assert len(result) == 1
    assert result[0].grade == "C"


def test_a_beats_all_other_grades():
    rows = [make_row(grade="D"), make_row(grade="B"), make_row(grade="A"), make_row(grade="C")]
    result = dedup(rows)
    assert len(result) == 1
    assert result[0].grade == "A"


def test_different_system_or_dtc_are_kept_separate():
    rows = [
        make_row(system="SYS1", dtc="P000000"),
        make_row(system="SYS2", dtc="P000000"),
        make_row(system="SYS1", dtc="P111111"),
    ]
    result = dedup(rows)
    assert len(result) == 3


def test_empty_input_returns_empty_list():
    assert dedup([]) == []
