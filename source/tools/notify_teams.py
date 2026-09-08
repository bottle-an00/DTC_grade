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


def send_teams_chat_message(webhook_url: str, chat_id: str, title: str, text: str, timeout: float = 30) -> None:
    """POST to the n8n "Notify Teams Chat" webhook (source/n8n/dtc_notify_teams_chat_workflow.json),
    which uses n8n's own Microsoft Teams credential to post into a specific
    chat. Unlike an Incoming Webhook (channel-only), this can reach a
    personal chat -- and unlike calling Graph directly, it needs no Graph
    permission consent from this script's own login."""
    payload = json.dumps({"chatId": chat_id, "title": title, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()
