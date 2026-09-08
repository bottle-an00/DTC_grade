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


def _wrap_adaptive_card(body: list[dict]) -> dict:
    """Wrap an Adaptive Card body in the Bot Framework "attachments"
    envelope that the Power Automate "Teams webhook request received"
    trigger (a modern Incoming-Webhook replacement) expects as its request
    body -- that trigger relays whatever Adaptive Card it's given straight
    into Teams, so the caller owns the entire card layout."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                },
            }
        ],
    }


def build_simple_adaptive_card(title: str, text: str) -> dict:
    """A plain title+text Adaptive Card for the Power Automate Teams webhook
    -- used for the success/failure notifications that don't need a
    checklist."""
    return _wrap_adaptive_card(
        [
            {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
            {"type": "TextBlock", "text": text, "wrap": True},
        ]
    )


def build_unmapped_sheets_adaptive_card(title: str, intro: str, items: list[dict]) -> dict:
    """Build a Teams Adaptive Card checklist -- one entry per unmapped
    sheet's AI suggestion. Each entry renders as two overlapping TextBlocks
    (plain vs. struck through) with a click handler that swaps which one is
    visible -- Input.Toggle/Action.Submit would need a bot backend to react
    to a submission, whereas Action.ToggleVisibility does the strike-through
    entirely client-side with no round trip."""
    body = [
        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
        {"type": "TextBlock", "text": intro, "wrap": True},
    ]
    for index, item in enumerate(items):
        label = item["sheet"]
        if "suggested_system" in item:
            label += f" -> AI 추천: {item['suggested_system']} ({item['reasoning']})"
        normal_id = f"item_{index}_normal"
        done_id = f"item_{index}_done"
        body.append(
            {
                "type": "Container",
                "selectAction": {"type": "Action.ToggleVisibility", "targetElements": [normal_id, done_id]},
                "items": [
                    {"type": "TextBlock", "id": normal_id, "text": f"☐ {label}", "wrap": True, "isVisible": True},
                    {
                        "type": "TextBlock",
                        "id": done_id,
                        "text": f"☑ ~~{label}~~",
                        "wrap": True,
                        "isSubtle": True,
                        "isVisible": False,
                    },
                ],
            }
        )
    return _wrap_adaptive_card(body)


def send_teams_adaptive_card(webhook_url: str, card: dict, timeout: float = 30) -> None:
    payload = json.dumps(card).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()
