import json

from tools.notify_teams import (
    build_simple_adaptive_card,
    build_teams_message,
    build_unmapped_sheets_adaptive_card,
    send_teams_adaptive_card,
    send_teams_message,
)


def test_build_teams_message_is_a_message_card():
    message = build_teams_message("제목", "본문")

    assert message == {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": "제목",
        "title": "제목",
        "text": "본문",
    }


def test_send_teams_message_posts_json_to_webhook_url(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"1"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["content_type"] = request.get_header("Content-type")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("tools.notify_teams.urllib.request.urlopen", fake_urlopen)

    send_teams_message("https://example.com/webhook", "제목", "본문", timeout=15)

    assert captured["url"] == "https://example.com/webhook"
    assert captured["method"] == "POST"
    assert captured["content_type"] == "application/json"
    assert captured["body"]["title"] == "제목"
    assert captured["timeout"] == 15


def test_build_simple_adaptive_card_wraps_title_and_text_in_the_bot_framework_envelope():
    card = build_simple_adaptive_card("제목", "본문")

    assert card["type"] == "message"
    content = card["attachments"][0]["content"]
    assert card["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert content["type"] == "AdaptiveCard"
    assert content["body"] == [
        {"type": "TextBlock", "text": "제목", "weight": "Bolder", "size": "Medium", "wrap": True},
        {"type": "TextBlock", "text": "본문", "wrap": True},
    ]


def test_build_unmapped_sheets_adaptive_card_wraps_a_strike_through_toggle_per_item():
    card = build_unmapped_sheets_adaptive_card(
        "제목",
        "안내문",
        [
            {"sheet": "UNKNOWN(Sheet)", "suggested_system": "NEW", "reasoning": "self-match"},
            {"sheet": "다른 시트"},
        ],
    )

    assert card["type"] == "message"
    content = card["attachments"][0]["content"]
    assert card["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert content["type"] == "AdaptiveCard"

    body = content["body"]
    assert body[0] == {"type": "TextBlock", "text": "제목", "weight": "Bolder", "size": "Medium", "wrap": True}
    assert body[1]["text"] == "안내문"

    first_item = body[2]
    assert first_item["type"] == "Container"
    normal, done = first_item["items"]
    assert "UNKNOWN(Sheet)" in normal["text"] and "NEW" in normal["text"] and "self-match" in normal["text"]
    assert normal["isVisible"] is True
    assert done["isVisible"] is False
    assert done["text"].startswith("☑ ~~") and done["text"].endswith("~~")
    assert first_item["selectAction"] == {
        "type": "Action.ToggleVisibility",
        "targetElements": [normal["id"], done["id"]],
    }

    second_item = body[3]
    assert second_item["items"][0]["text"] == "☐ 다른 시트"


def test_send_teams_adaptive_card_posts_the_card_json_to_the_webhook_url(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b""

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("tools.notify_teams.urllib.request.urlopen", fake_urlopen)

    card = {"type": "message", "attachments": []}
    send_teams_adaptive_card("https://example.com/power-automate", card, timeout=20)

    assert captured["url"] == "https://example.com/power-automate"
    assert captured["method"] == "POST"
    assert captured["body"] == card
    assert captured["timeout"] == 20
