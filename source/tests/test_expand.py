from dtc_transform.expand import expand_trailing_zeros
from dtc_transform.models import Row


def make_row(system="SYS", dtc="P0AC200", grade="D"):
    return Row(
        system=system, dtc=dtc, description="desc", warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade=grade,
        grading_background="bg", sheet="Sheet",
    )


def test_adds_shortened_row_for_trailing_00():
    rows = [make_row(dtc="P0AC200")]
    result = expand_trailing_zeros(rows)
    dtcs = sorted(r.dtc for r in result)
    assert dtcs == ["P0AC2", "P0AC200"]


def test_shortened_row_copies_other_fields():
    rows = [make_row(dtc="P0AC200", grade="C")]
    result = expand_trailing_zeros(rows)
    short = next(r for r in result if r.dtc == "P0AC2")
    assert short.system == "SYS"
    assert short.grade == "C"
    assert short.description == "desc"


def test_does_not_expand_dtc_not_ending_in_00():
    rows = [make_row(dtc="P0AC201")]
    result = expand_trailing_zeros(rows)
    assert len(result) == 1
    assert result[0].dtc == "P0AC201"


def test_collision_with_existing_short_code_keeps_more_severe_grade():
    rows = [make_row(dtc="P0AC200", grade="D"), make_row(dtc="P0AC2", grade="B")]
    result = expand_trailing_zeros(rows)
    assert len(result) == 2
    short = next(r for r in result if r.dtc == "P0AC2")
    assert short.grade == "B"


def test_collision_where_expanded_row_is_more_severe_wins():
    rows = [make_row(dtc="P0AC200", grade="A"), make_row(dtc="P0AC2", grade="D")]
    result = expand_trailing_zeros(rows)
    short = next(r for r in result if r.dtc == "P0AC2")
    assert short.grade == "A"


def test_different_systems_expand_independently():
    rows = [make_row(system="SYS1", dtc="P0AC200"), make_row(system="SYS2", dtc="P0AC200")]
    result = expand_trailing_zeros(rows)
    assert len(result) == 4
