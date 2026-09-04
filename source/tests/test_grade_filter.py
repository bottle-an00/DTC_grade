from dtc_transform.grade_filter import filter_invalid_grades
from dtc_transform.models import Row


def make_row(dtc="P000000", grade="A"):
    return Row(
        system="SYS", dtc=dtc, description="desc", warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade=grade,
        grading_background="bg", sheet="Sheet",
    )


def test_a_b_c_d_rows_all_pass_through_as_valid():
    rows = [make_row(grade="A"), make_row(grade="B"), make_row(grade="C"), make_row(grade="D")]
    valid, excluded = filter_invalid_grades(rows)
    assert valid == rows
    assert excluded == []


def test_invalid_grades_are_excluded():
    rows = [make_row(grade="E"), make_row(grade="-"), make_row(grade="")]
    valid, excluded = filter_invalid_grades(rows)
    assert valid == []
    assert excluded == rows


def test_mixed_valid_and_invalid_preserve_order():
    row_a = make_row(dtc="P000001", grade="A")
    row_e = make_row(dtc="P000002", grade="E")
    row_d = make_row(dtc="P000003", grade="D")
    row_dash = make_row(dtc="P000004", grade="-")
    rows = [row_a, row_e, row_d, row_dash]
    valid, excluded = filter_invalid_grades(rows)
    assert valid == [row_a, row_d]
    assert excluded == [row_e, row_dash]


def test_empty_input_returns_empty_results():
    valid, excluded = filter_invalid_grades([])
    assert valid == []
    assert excluded == []
