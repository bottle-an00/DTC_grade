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


def test_send_teams_chat_message_posts_to_graph_chat_endpoint(monkeypatch):
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
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("tools.notify_teams.urllib.request.urlopen", fake_urlopen)

    send_teams_chat_message("TOKEN_ABC", "19:chat-id@thread.v2", "본문", timeout=15)

    assert captured["url"] == "https://graph.microsoft.com/v1.0/chats/19:chat-id@thread.v2/messages"
    assert captured["method"] == "POST"
    assert captured["authorization"] == "Bearer TOKEN_ABC"
    assert captured["body"] == {"body": {"content": "본문"}}
    assert captured["timeout"] == 15
