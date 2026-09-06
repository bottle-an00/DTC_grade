from dtc_transform.models import RawRow
from tools.review_context import build_review_context


def make_raw(sheet, dtc, description):
    return RawRow(
        sheet=sheet, dtc=dtc, description=description, warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade="D",
        grading_background="bg",
    )


def test_ranks_candidates_by_vote_count():
    raw_rows = [
        make_raw("MFSW(MultifunctionSwitch)", "P200000", "generic desc a"),
        make_raw("MFSW(MultifunctionSwitch)", "P200001", "generic desc b"),
        make_raw("MFSW(MultifunctionSwitch)", "P200002", "generic desc c"),
    ]
    reference_rows = [
        ("P200000", "generic desc a", "IBU-BCM,IBU-IMMO,IBU-SMK,IBU-TPMS"),
        ("P200001", "generic desc b", "IBU-BCM,IBU-IMMO,IBU-SMK,IBU-TPMS"),
        ("P200002", "generic desc c", "MFSW"),
    ]

    result = build_review_context(raw_rows, reference_rows, review_sheets=["MFSW(MultifunctionSwitch)"])

    assert len(result) == 1
    entry = result[0]
    assert entry["sheet"] == "MFSW(MultifunctionSwitch)"
    assert entry["top_candidates"][0] == {"system": "IBU-BCM,IBU-IMMO,IBU-SMK,IBU-TPMS", "votes": 2}
    assert entry["top_candidates"][1] == {"system": "MFSW", "votes": 1}


def test_limits_candidates_to_top_n():
    raw_rows = [make_raw("SHEET", f"P{i:06d}", f"desc {i}") for i in range(6)]
    reference_rows = [(f"P{i:06d}", f"desc {i}", f"SYSTEM_{i}") for i in range(6)]

    result = build_review_context(raw_rows, reference_rows, review_sheets=["SHEET"], top_n_candidates=3)

    assert len(result[0]["top_candidates"]) == 3


def test_samples_come_from_the_sheets_own_rows_deduped_and_limited():
    raw_rows = [
        make_raw("SHEET", "P000001", "desc a"),
        make_raw("SHEET", "P000001", "desc a"),  # exact duplicate, should not double count
        make_raw("SHEET", "P000002", "desc b"),
        make_raw("OTHER_SHEET", "P999999", "unrelated"),
    ]
    reference_rows = []

    result = build_review_context(raw_rows, reference_rows, review_sheets=["SHEET"], sample_size=2)

    samples = result[0]["samples"]
    assert samples == [
        {"dtc": "P000001", "description": "desc a"},
        {"dtc": "P000002", "description": "desc b"},
    ]


def test_only_returns_requested_sheets_in_requested_order():
    raw_rows = [
        make_raw("A", "P1", "d1"),
        make_raw("B", "P2", "d2"),
        make_raw("C", "P3", "d3"),
    ]
    reference_rows = []

    result = build_review_context(raw_rows, reference_rows, review_sheets=["C", "A"])

    assert [entry["sheet"] for entry in result] == ["C", "A"]


def test_sheet_with_no_reference_matches_still_gets_samples_but_no_candidates():
    raw_rows = [make_raw("NEW_SHEET", "P999999", "brand new")]
    reference_rows = [("P000001", "unrelated", "SOME_SYSTEM")]

    result = build_review_context(raw_rows, reference_rows, review_sheets=["NEW_SHEET"])

    entry = result[0]
    assert entry["top_candidates"] == []
    assert entry["samples"] == [{"dtc": "P999999", "description": "brand new"}]
