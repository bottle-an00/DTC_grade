import csv
import json
import sys

from dtc_transform.models import RawRow
from tools.run_ai_review import call_ai_review_webhook, run_ai_review


def make_raw(sheet, dtc, description):
    return RawRow(
        sheet=sheet, dtc=dtc, description=description, warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade="D",
        grading_background="bg",
    )


def test_skips_webhook_call_when_no_low_confidence_sheets():
    raw_rows = [make_raw("AVN(AudioVideoNavigation)", "P100000", "desc a")]
    reference_rows = [("P100000", "desc a", "AVN")]

    def fail_if_called(context):
        raise AssertionError("webhook should not be called when nothing needs review")

    result = run_ai_review(raw_rows, reference_rows, existing_mapping=None, call_webhook=fail_if_called)

    assert result["review_rows"] == []
    assert result["mapping"]["AVN(AudioVideoNavigation)"]["system"] == "AVN"


def test_calls_webhook_with_review_context_for_low_confidence_sheets():
    raw_rows = [
        make_raw("MFSW(MultifunctionSwitch)", "P200000", "generic desc a"),
        make_raw("MFSW(MultifunctionSwitch)", "P200001", "generic desc b"),
    ]
    reference_rows = [
        ("P200000", "generic desc a", "WRONG_SYSTEM"),
        ("P200001", "generic desc b", "MFSW"),
    ]
    captured = {}

    def fake_webhook(context):
        captured["context"] = context
        return [{"sheet": "MFSW(MultifunctionSwitch)", "suggested_system": "MFSW", "reasoning": "self-match"}]

    result = run_ai_review(
        raw_rows, reference_rows, existing_mapping=None,
        call_webhook=fake_webhook, confidence_threshold=0.9,
    )

    assert captured["context"][0]["sheet"] == "MFSW(MultifunctionSwitch)"
    assert result["review_rows"][0]["ai_suggestion"] == "MFSW"
    assert result["review_rows"][0]["ai_reasoning"] == "self-match"


def test_preserves_manual_entries_from_existing_mapping():
    raw_rows = [make_raw("MFSW(MultifunctionSwitch)", "P200000", "generic desc")]
    reference_rows = [("P200000", "generic desc", "WRONG_SYSTEM")]
    existing_mapping = {
        "MFSW(MultifunctionSwitch)": {
            "system": "MFSW", "confidence": 1.0, "hits": 10,
            "source": "manual", "note": "verified",
        }
    }

    result = run_ai_review(
        raw_rows, reference_rows, existing_mapping=existing_mapping,
        call_webhook=lambda ctx: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    assert result["mapping"]["MFSW(MultifunctionSwitch)"]["source"] == "manual"
    assert result["review_rows"] == []


def test_call_ai_review_webhook_posts_context_and_returns_parsed_json(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps([{"sheet": "A", "suggested_system": "X", "reasoning": "r"}]).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("tools.run_ai_review.urllib.request.urlopen", fake_urlopen)

    context = [{"sheet": "A", "top_candidates": [], "samples": []}]
    result = call_ai_review_webhook("https://example.com/webhook", context, timeout=120)

    assert captured["url"] == "https://example.com/webhook"
    assert captured["timeout"] == 120
    assert captured["body"] == {"sheets": context}
    assert result == [{"sheet": "A", "suggested_system": "X", "reasoning": "r"}]


def test_main_writes_mapping_and_review_csv_and_notifies_teams(tmp_path, monkeypatch):
    raw_input = tmp_path / "raw.txt"
    raw_input.write_text(
        "SHEET\tDTC\tDescription\tWarning_Light\tWarning_Message\tLimp_Home\tFail_Safe\tGrade\tGrading_Background\n"
        "MFSW(MultifunctionSwitch)\tP200000\tgeneric desc a\tX\tX\tX\tX\tD\tbg\n"
        "MFSW(MultifunctionSwitch)\tP200001\tgeneric desc b\tX\tX\tX\tX\tD\tbg\n",
        encoding="utf-8",
    )

    import sqlite3

    reference_db = tmp_path / "reference.sqlite"
    con = sqlite3.connect(reference_db)
    con.execute("CREATE TABLE dtc_master (DTC TEXT, Description TEXT, System TEXT)")
    con.execute("INSERT INTO dtc_master VALUES ('P200000', 'generic desc a', 'WRONG_SYSTEM')")
    con.execute("INSERT INTO dtc_master VALUES ('P200001', 'generic desc b', 'MFSW')")
    con.commit()
    con.close()

    mapping_path = tmp_path / "mapping.json"
    review_csv = tmp_path / "review.csv"

    teams_calls = []
    monkeypatch.setattr(
        "tools.run_ai_review.send_teams_message",
        lambda url, title, text, timeout=30: teams_calls.append((url, title, text)),
    )
    monkeypatch.setattr(
        "tools.run_ai_review.call_ai_review_webhook",
        lambda url, context, timeout: [
            {"sheet": "MFSW(MultifunctionSwitch)", "suggested_system": "MFSW", "reasoning": "self-match"}
        ],
    )

    from tools.run_ai_review import main

    old_argv = sys.argv
    sys.argv = [
        "run_ai_review",
        "--raw-input", str(raw_input),
        "--reference-db", str(reference_db),
        "--mapping", str(mapping_path),
        "--review-csv", str(review_csv),
        "--n8n-webhook-url", "https://example.com/n8n",
        "--teams-webhook-url", "https://example.com/teams",
        "--confidence-threshold", "0.9",
    ]
    try:
        main()
    finally:
        sys.argv = old_argv

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    assert mapping["MFSW(MultifunctionSwitch)"]["confidence"] == 0.5

    with open(review_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["ai_suggestion"] == "MFSW"

    assert len(teams_calls) == 1
    assert teams_calls[0][0] == "https://example.com/teams"


def test_main_notifies_teams_failure_and_reraises_on_error(tmp_path, monkeypatch):
    teams_calls = []
    monkeypatch.setattr(
        "tools.run_ai_review.send_teams_message",
        lambda url, title, text, timeout=30: teams_calls.append((url, title, text)),
    )

    from tools.run_ai_review import main

    old_argv = sys.argv
    sys.argv = [
        "run_ai_review",
        "--raw-input", str(tmp_path / "missing.txt"),
        "--reference-db", str(tmp_path / "missing.sqlite"),
        "--mapping", str(tmp_path / "mapping.json"),
        "--review-csv", str(tmp_path / "review.csv"),
        "--n8n-webhook-url", "https://example.com/n8n",
        "--teams-webhook-url", "https://example.com/teams",
    ]
    try:
        raised = False
        try:
            main()
        except Exception:
            raised = True
    finally:
        sys.argv = old_argv

    assert raised
    assert len(teams_calls) == 1
    assert teams_calls[0][1] == "DTC 매핑 AI 검토 실패"
