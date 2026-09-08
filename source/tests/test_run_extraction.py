import json
import sqlite3
import sys

import pytest

from tools.run_extraction import main, run


def make_row(sheet, dtc, description, system, grade="D"):
    return {
        "sheet": sheet,
        "dtc": dtc,
        "description": description,
        "warning_light": "X",
        "warning_message": "X",
        "limp_home": "X",
        "fail_safe": "X",
        "grade": grade,
        "grading_background": "bg",
        "system": system,
    }


def _patch_resolution(monkeypatch, workbook_id="ITEM_ID_123"):
    monkeypatch.setattr("tools.run_extraction.get_access_token", lambda: "TOKEN")
    monkeypatch.setattr("tools.run_extraction.resolve_workbook_id", lambda share_url, token: workbook_id)


def test_run_fetches_converts_and_returns_stats(tmp_path, monkeypatch):
    _patch_resolution(monkeypatch)
    monkeypatch.setattr(
        "tools.run_extraction.fetch_all_extraction",
        lambda url, workbook_id, timeout, chunk_size, max_concurrency: {
            "rows": [make_row("TCU(TransmissionControlUnit)", "P0AC200", "Desc A", "AT,CVT")]
        },
    )

    output_json = tmp_path / "extraction.json"
    output_sqlite = tmp_path / "out.sqlite"
    report_path = tmp_path / "report.txt"

    result, stats = run(
        "https://example.com/n8n",
        "https://onedrive.example/file.xlsx",
        str(output_json),
        str(output_sqlite),
        str(report_path),
        timeout=120,
    )

    assert result["rows"][0]["dtc"] == "P0AC200"
    assert stats["unmapped_sheets"] == []

    con = sqlite3.connect(str(output_sqlite))
    cur = con.cursor()
    cur.execute("SELECT System, DTC FROM dtc_master")
    rows = cur.fetchall()
    con.close()
    assert ("AT,CVT", "P0AC200") in rows


def _run_main(monkeypatch, argv):
    old_argv = sys.argv
    sys.argv = argv
    try:
        main()
    finally:
        sys.argv = old_argv


def test_main_sends_success_message_when_no_unmapped_sheets(tmp_path, monkeypatch):
    _patch_resolution(monkeypatch)
    monkeypatch.setattr(
        "tools.run_extraction.fetch_all_extraction",
        lambda url, workbook_id, timeout, chunk_size, max_concurrency: {
            "rows": [make_row("TCU(TransmissionControlUnit)", "P0AC200", "Desc A", "AT,CVT")]
        },
    )
    teams_calls = []
    monkeypatch.setattr(
        "tools.run_extraction.send_teams_message",
        lambda url, title, text, timeout=30: teams_calls.append((url, title, text)),
    )

    output_sqlite = tmp_path / "out.sqlite"
    _run_main(
        monkeypatch,
        [
            "run_extraction",
            "--webhook-url", "https://example.com/n8n",
            "--workbook-url", "https://onedrive.example/file.xlsx",
            "--output-json", str(tmp_path / "extraction.json"),
            "--output", str(output_sqlite),
            "--report", str(tmp_path / "report.txt"),
            "--teams-webhook-url", "https://example.com/teams",
        ],
    )

    assert len(teams_calls) == 1
    url, title, text = teams_calls[0]
    assert "준비 완료" in title
    assert str(output_sqlite) in text


def test_main_alerts_with_ai_suggestions_and_exits_nonzero_when_unmapped(tmp_path, monkeypatch):
    _patch_resolution(monkeypatch)
    monkeypatch.setattr(
        "tools.run_extraction.fetch_all_extraction",
        lambda url, workbook_id, timeout, chunk_size, max_concurrency: {
            "rows": [make_row("UNKNOWN(Sheet)", "P111111", "desc", "")],
            "suggestions": [{"sheet": "UNKNOWN(Sheet)", "suggested_system": "NEW", "reasoning": "self-match"}],
        },
    )
    teams_calls = []
    monkeypatch.setattr(
        "tools.run_extraction.send_teams_message",
        lambda url, title, text, timeout=30: teams_calls.append((url, title, text)),
    )

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            [
                "run_extraction",
                "--webhook-url", "https://example.com/n8n",
                "--workbook-url", "https://onedrive.example/file.xlsx",
                "--output-json", str(tmp_path / "extraction.json"),
                "--output", str(tmp_path / "out.sqlite"),
                "--report", str(tmp_path / "report.txt"),
                "--teams-webhook-url", "https://example.com/teams",
            ],
        )

    assert exc_info.value.code == 1
    assert len(teams_calls) == 1
    url, title, text = teams_calls[0]
    assert "매핑" in title
    assert "UNKNOWN(Sheet)" in text
    assert "NEW" in text
    assert "self-match" in text


def test_main_also_sends_a_teams_chat_message_when_chat_id_is_given(tmp_path, monkeypatch):
    _patch_resolution(monkeypatch)
    monkeypatch.setattr(
        "tools.run_extraction.fetch_all_extraction",
        lambda url, workbook_id, timeout, chunk_size, max_concurrency: {
            "rows": [make_row("TCU(TransmissionControlUnit)", "P0AC200", "Desc A", "AT,CVT")]
        },
    )
    monkeypatch.setattr("tools.run_extraction.send_teams_message", lambda url, title, text, timeout=30: None)
    chat_calls = []
    monkeypatch.setattr(
        "tools.run_extraction.send_teams_chat_message",
        lambda webhook_url, chat_id, title, text, timeout=30: chat_calls.append((webhook_url, chat_id, title, text)),
    )

    _run_main(
        monkeypatch,
        [
            "run_extraction",
            "--webhook-url", "https://example.com/n8n",
            "--workbook-url", "https://onedrive.example/file.xlsx",
            "--output-json", str(tmp_path / "extraction.json"),
            "--output", str(tmp_path / "out.sqlite"),
            "--report", str(tmp_path / "report.txt"),
            "--teams-webhook-url", "https://example.com/teams",
            "--teams-chat-webhook-url", "https://example.com/n8n-notify-teams-chat",
            "--teams-chat-id", "19:chat-id@thread.v2",
        ],
    )

    assert len(chat_calls) == 1
    webhook_url, chat_id, title, text = chat_calls[0]
    assert webhook_url == "https://example.com/n8n-notify-teams-chat"
    assert chat_id == "19:chat-id@thread.v2"
    assert "준비 완료" in title


def test_main_skips_teams_chat_message_when_chat_id_or_its_webhook_url_is_missing(tmp_path, monkeypatch):
    _patch_resolution(monkeypatch)
    monkeypatch.setattr(
        "tools.run_extraction.fetch_all_extraction",
        lambda url, workbook_id, timeout, chunk_size, max_concurrency: {
            "rows": [make_row("TCU(TransmissionControlUnit)", "P0AC200", "Desc A", "AT,CVT")]
        },
    )
    monkeypatch.setattr("tools.run_extraction.send_teams_message", lambda url, title, text, timeout=30: None)
    chat_calls = []
    monkeypatch.setattr(
        "tools.run_extraction.send_teams_chat_message",
        lambda webhook_url, chat_id, title, text, timeout=30: chat_calls.append((webhook_url, chat_id, title, text)),
    )

    _run_main(
        monkeypatch,
        [
            "run_extraction",
            "--webhook-url", "https://example.com/n8n",
            "--workbook-url", "https://onedrive.example/file.xlsx",
            "--output-json", str(tmp_path / "extraction.json"),
            "--output", str(tmp_path / "out.sqlite"),
            "--report", str(tmp_path / "report.txt"),
            "--teams-webhook-url", "https://example.com/teams",
        ],
    )

    assert chat_calls == []


def test_main_notifies_teams_failure_and_reraises_on_error(tmp_path, monkeypatch):
    _patch_resolution(monkeypatch)
    monkeypatch.setattr(
        "tools.run_extraction.fetch_all_extraction",
        lambda url, workbook_id, timeout, chunk_size, max_concurrency: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    teams_calls = []
    monkeypatch.setattr(
        "tools.run_extraction.send_teams_message",
        lambda url, title, text, timeout=30: teams_calls.append((url, title, text)),
    )

    with pytest.raises(RuntimeError):
        _run_main(
            monkeypatch,
            [
                "run_extraction",
                "--webhook-url", "https://example.com/n8n",
                "--workbook-url", "https://onedrive.example/file.xlsx",
                "--output-json", str(tmp_path / "extraction.json"),
                "--output", str(tmp_path / "out.sqlite"),
                "--report", str(tmp_path / "report.txt"),
                "--teams-webhook-url", "https://example.com/teams",
            ],
        )

    assert len(teams_calls) == 1
    assert teams_calls[0][1] == "DTC 등급 파이프라인 실패"
