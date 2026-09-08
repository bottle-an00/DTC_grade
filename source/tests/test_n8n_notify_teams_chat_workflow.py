import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / "n8n" / "dtc_notify_teams_chat_workflow.json"


def test_workflow_file_is_valid_json():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert "nodes" in data
    assert "connections" in data


def test_workflow_has_required_nodes():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    node_types = {node["type"] for node in data["nodes"]}
    assert "n8n-nodes-base.webhook" in node_types
    assert "n8n-nodes-base.microsoftTeams" in node_types
    assert "n8n-nodes-base.respondToWebhook" in node_types


def test_webhook_responds_via_response_node():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    webhook = next(n for n in data["nodes"] if n["type"] == "n8n-nodes-base.webhook")
    assert webhook["parameters"]["responseMode"] == "responseNode"


def test_teams_node_sends_a_chat_message_using_the_webhook_body_chat_id():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    teams_node = next(n for n in data["nodes"] if n["type"] == "n8n-nodes-base.microsoftTeams")
    params = teams_node["parameters"]
    assert params["resource"] == "chatMessage"
    assert params["operation"] == "create"
    assert params["chatId"]["mode"] == "id"
    assert "$json.body.chatId" in params["chatId"]["value"]


def test_webhook_flows_through_to_respond_to_webhook():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    connections = data["connections"]

    node = "Webhook"
    visited = {node}
    while node in connections:
        targets = connections[node]["main"][0]
        assert len(targets) == 1, f"expected a single linear path, branch found at {node}"
        node = targets[0]["node"]
        assert node not in visited, f"cycle detected at {node}"
        visited.add(node)

    assert node == "Respond to Webhook"
