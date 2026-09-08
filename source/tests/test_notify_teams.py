import json

from tools.notify_teams import build_teams_message, send_teams_chat_message, send_teams_message


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


def test_send_teams_chat_message_posts_chat_id_and_text_to_the_n8n_notify_webhook(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["content_type"] = request.get_header("Content-type")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("tools.notify_teams.urllib.request.urlopen", fake_urlopen)

    send_teams_chat_message("https://example.com/n8n-notify-teams-chat", "19:chat-id@thread.v2", "제목", "본문", timeout=15)

    assert captured["url"] == "https://example.com/n8n-notify-teams-chat"
    assert captured["method"] == "POST"
    assert captured["content_type"] == "application/json"
    assert captured["body"] == {"chatId": "19:chat-id@thread.v2", "title": "제목", "text": "본문"}
    assert captured["timeout"] == 15
