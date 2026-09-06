import csv

from tools.apply_ai_suggestions import merge_ai_suggestions


def test_adds_suggestion_and_reasoning_for_matching_sheet():
    review_rows = [{"sheet": "MFSW(MultifunctionSwitch)", "system": "IBU-BCM,...", "confidence": "0.20", "hits": "10"}]
    ai_suggestions = [
        {"sheet": "MFSW(MultifunctionSwitch)", "suggested_system": "MFSW", "reasoning": "self-matching abbreviation"}
    ]

    result = merge_ai_suggestions(review_rows, ai_suggestions)

    assert result == [
        {
            "sheet": "MFSW(MultifunctionSwitch)",
            "system": "IBU-BCM,...",
            "confidence": "0.20",
            "hits": "10",
            "ai_suggestion": "MFSW",
            "ai_reasoning": "self-matching abbreviation",
        }
    ]


def test_leaves_suggestion_blank_when_no_ai_result_for_sheet():
    review_rows = [{"sheet": "SR_CMR(SVMCamera)", "system": "CCIC,CCNC", "confidence": "0.25", "hits": "4"}]
    ai_suggestions: list[dict] = []

    result = merge_ai_suggestions(review_rows, ai_suggestions)

    assert result[0]["ai_suggestion"] == ""
    assert result[0]["ai_reasoning"] == ""


def test_does_not_mutate_original_review_rows():
    review_rows = [{"sheet": "A", "system": "X", "confidence": "0.1", "hits": "1"}]
    ai_suggestions = [{"sheet": "A", "suggested_system": "Y", "reasoning": "why"}]

    merge_ai_suggestions(review_rows, ai_suggestions)

    assert "ai_suggestion" not in review_rows[0]


def test_preserves_row_order():
    review_rows = [
        {"sheet": "A", "system": "X", "confidence": "0.1", "hits": "1"},
        {"sheet": "B", "system": "Y", "confidence": "0.2", "hits": "2"},
    ]
    ai_suggestions = [{"sheet": "B", "suggested_system": "B_FIX", "reasoning": "r"}]

    result = merge_ai_suggestions(review_rows, ai_suggestions)

    assert [row["sheet"] for row in result] == ["A", "B"]
    assert result[1]["ai_suggestion"] == "B_FIX"


def test_main_writes_csv_with_extra_columns(tmp_path):
    review_csv = tmp_path / "review.csv"
    review_csv.write_text(
        "sheet,system,confidence,hits\nMFSW(MultifunctionSwitch),IBU-BCM,0.20,10\n", encoding="utf-8"
    )
    ai_json = tmp_path / "ai.json"
    ai_json.write_text(
        '[{"sheet": "MFSW(MultifunctionSwitch)", "suggested_system": "MFSW", "reasoning": "self-match"}]',
        encoding="utf-8",
    )
    output_csv = tmp_path / "output.csv"

    from tools.apply_ai_suggestions import main
    import sys

    old_argv = sys.argv
    sys.argv = [
        "apply_ai_suggestions",
        "--review-csv", str(review_csv),
        "--ai-suggestions", str(ai_json),
        "--output", str(output_csv),
    ]
    try:
        main()
    finally:
        sys.argv = old_argv

    with open(output_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["ai_suggestion"] == "MFSW"
    assert rows[0]["ai_reasoning"] == "self-match"
