from dtc_transform.dedup import dedup
from dtc_transform.models import Row


def make_row(
    system="SYS", dtc="P000000", grade="D", description="desc",
    warning_light="X", warning_message="X", limp_home="X", fail_safe="X",
):
    return Row(
        system=system, dtc=dtc, description=description, warning_light=warning_light,
        warning_message=warning_message, limp_home=limp_home, fail_safe=fail_safe, grade=grade,
        grading_background="bg", sheet="Sheet",
    )


def test_same_system_dtc_grade_different_description_keeps_first_when_tied_on_o_count():
    rows = [
        make_row(description="Control Unit Supply Voltage Open Circuit"),
        make_row(description="Open Unit Supply Voltage Open Circuit"),
    ]
    result = dedup(rows)
    assert len(result) == 1
    assert result[0].description == "Control Unit Supply Voltage Open Circuit"


def test_same_system_dtc_grade_keeps_the_row_with_more_o_marks():
    fewer_os = make_row(description="fewer", warning_light="X", limp_home="X", fail_safe="X")
    more_os = make_row(description="more", warning_light="O", limp_home="O", fail_safe="X")
    result = dedup([fewer_os, more_os])
    assert len(result) == 1
    assert result[0].description == "more"

    # order shouldn't matter
    result2 = dedup([more_os, fewer_os])
    assert result2[0].description == "more"


def test_unicode_circle_symbol_counts_as_an_o_mark_too():
    latin_o = make_row(description="latin", warning_light="O")
    unicode_circle = make_row(description="circle", warning_light="○", limp_home="○")
    result = dedup([latin_o, unicode_circle])
    assert result[0].description == "circle"


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
