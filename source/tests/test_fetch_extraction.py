import json
import sys

import pytest

from tools.fetch_extraction import fetch_all_extraction, fetch_extraction, main


def test_fetch_extraction_posts_workbook_id_and_page_params(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"rows": [{"dtc": "P100000"}]}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("tools.fetch_extraction.urllib.request.urlopen", fake_urlopen)

    result = fetch_extraction("https://example.com/webhook", "ITEM_ID_123", timeout=120, offset=15, limit=15)

    assert captured["url"] == "https://example.com/webhook"
    assert captured["timeout"] == 120
    assert captured["body"] == {"workbook_id": "ITEM_ID_123", "offset": 15, "limit": 15}
    assert result == {"rows": [{"dtc": "P100000"}]}


def test_fetch_extraction_defaults_to_a_single_large_page():
    import inspect

    sig = inspect.signature(fetch_extraction)
    assert sig.parameters["offset"].default == 0
    assert sig.parameters["limit"].default >= 100


def test_fetch_extraction_raises_a_clear_error_on_a_non_json_response(monkeypatch):
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b""

    monkeypatch.setattr("tools.fetch_extraction.urllib.request.urlopen", lambda request, timeout: FakeResponse())

    with pytest.raises(RuntimeError, match="status=200"):
        fetch_extraction("https://example.com/webhook", "ITEM_ID_123", timeout=120)


def test_fetch_all_extraction_pages_through_every_sheet_and_merges_results(monkeypatch):
    calls = []

    def fake_fetch_extraction(url, workbook_id, timeout, offset=0, limit=1000):
        calls.append(offset)
        if offset == 0:
            return {"rows": [{"dtc": "P1"}, {"dtc": "P2"}], "totalSheets": 5}
        return {
            "rows": [{"dtc": "P3"}],
            "suggestions": [{"sheet": "NEW(Sheet)", "suggested_system": "NEW", "reasoning": "r"}],
            "totalSheets": 5,
        }

    monkeypatch.setattr("tools.fetch_extraction.fetch_extraction", fake_fetch_extraction)

    result = fetch_all_extraction("https://example.com/webhook", "ITEM_ID_123", timeout=120, chunk_size=2)

    # 5 sheets, 2 at a time -> pages at offsets 0, 2, 4. The remaining pages
    # (2, 4) run concurrently, so only their completion order is unpredictable.
    assert sorted(calls) == [0, 2, 4]
    assert sorted(result["rows"], key=lambda r: r["dtc"]) == [
        {"dtc": "P1"},
        {"dtc": "P2"},
        {"dtc": "P3"},
        {"dtc": "P3"},
    ]
    assert len(result["suggestions"]) == 2


def test_fetch_all_extraction_runs_chunk_requests_concurrently(monkeypatch):
    import threading
    import time

    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_fetch_extraction(url, workbook_id, timeout, offset=0, limit=1000):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        if offset == 0:
            return {"rows": [], "totalSheets": 9}
        return {"rows": []}

    monkeypatch.setattr("tools.fetch_extraction.fetch_extraction", fake_fetch_extraction)

    fetch_all_extraction(
        "https://example.com/webhook", "ITEM_ID_123", timeout=120, chunk_size=1, max_concurrency=5
    )

    assert max_active >= 2


def _run_main(monkeypatch, argv):
    old_argv = sys.argv
    sys.argv = argv
    try:
        main()
    finally:
        sys.argv = old_argv


def _patch_resolution(monkeypatch, workbook_id="ITEM_ID_123"):
    monkeypatch.setattr("tools.fetch_extraction.get_access_token", lambda: "TOKEN")
    monkeypatch.setattr("tools.fetch_extraction.resolve_workbook_id", lambda share_url, token: workbook_id)


def test_main_writes_rows_and_notifies_teams(tmp_path, monkeypatch):
    output_json = tmp_path / "extraction.json"

    _patch_resolution(monkeypatch)
    monkeypatch.setattr(
        "tools.fetch_extraction.fetch_all_extraction",
        lambda url, workbook_id, timeout, chunk_size, max_concurrency: {"rows": [{"dtc": "P100000"}, {"dtc": "P200000"}]},
    )
    teams_calls = []
    monkeypatch.setattr(
        "tools.fetch_extraction.send_teams_message",
        lambda url, title, text, timeout=30: teams_calls.append((url, title, text)),
    )

    _run_main(
        monkeypatch,
        [
            "fetch_extraction",
            "--webhook-url", "https://example.com/n8n",
            "--workbook-url", "https://onedrive.example/file.xlsx",
            "--output-json", str(output_json),
            "--teams-webhook-url", "https://example.com/teams",
        ],
    )

    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved == {"rows": [{"dtc": "P100000"}, {"dtc": "P200000"}]}

    assert len(teams_calls) == 1
    url, title, text = teams_calls[0]
    assert url == "https://example.com/teams"
    assert "준비 완료" in title
    assert str(output_json) in text
    assert "2건" in text


def test_main_sends_a_second_teams_message_when_ai_suggestions_are_present(tmp_path, monkeypatch):
    output_json = tmp_path / "extraction.json"

    _patch_resolution(monkeypatch)
    monkeypatch.setattr(
        "tools.fetch_extraction.fetch_all_extraction",
        lambda url, workbook_id, timeout, chunk_size, max_concurrency: {
            "rows": [{"dtc": "P100000"}],
            "suggestions": [{"sheet": "NEW(Sheet)", "suggested_system": "NEW", "reasoning": "self-match"}],
        },
    )
    teams_calls = []
    monkeypatch.setattr(
        "tools.fetch_extraction.send_teams_message",
        lambda url, title, text, timeout=30: teams_calls.append((url, title, text)),
    )

    _run_main(
        monkeypatch,
        [
            "fetch_extraction",
            "--webhook-url", "https://example.com/n8n",
            "--workbook-url", "https://onedrive.example/file.xlsx",
            "--output-json", str(output_json),
            "--teams-webhook-url", "https://example.com/teams",
        ],
    )

    assert len(teams_calls) == 2
    assert "매핑 필요" in teams_calls[1][1]
    assert "NEW(Sheet)" in teams_calls[1][2]
    assert "NEW" in teams_calls[1][2]


def test_main_notifies_teams_failure_and_reraises_on_error(tmp_path, monkeypatch):
    _patch_resolution(monkeypatch)
    monkeypatch.setattr(
        "tools.fetch_extraction.fetch_all_extraction",
        lambda url, workbook_id, timeout, chunk_size, max_concurrency: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    teams_calls = []
    monkeypatch.setattr(
        "tools.fetch_extraction.send_teams_message",
        lambda url, title, text, timeout=30: teams_calls.append((url, title, text)),
    )

    with pytest.raises(RuntimeError):
        _run_main(
            monkeypatch,
            [
                "fetch_extraction",
                "--webhook-url", "https://example.com/n8n",
                "--workbook-url", "https://onedrive.example/file.xlsx",
                "--output-json", str(tmp_path / "extraction.json"),
                "--teams-webhook-url", "https://example.com/teams",
            ],
        )

    assert len(teams_calls) == 1
    assert teams_calls[0][1] == "DTC 매칭 JSON 가져오기 실패"
