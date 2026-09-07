import json
import urllib.request


def build_teams_message(title: str, text: str) -> dict:
    """Build a Teams Incoming Webhook MessageCard payload."""
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": title,
        "title": title,
        "text": text,
    }


def send_teams_message(webhook_url: str, title: str, text: str, timeout: float = 30) -> None:
    payload = json.dumps(build_teams_message(title, text)).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def send_teams_chat_message(access_token: str, chat_id: str, text: str, timeout: float = 30) -> None:
    """Post into a Teams 1:1/group chat via Graph API. Unlike an Incoming
    Webhook (channel-only), this can reach a personal chat."""
    payload = json.dumps({"body": {"content": text}}).encode("utf-8")
    request = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()
