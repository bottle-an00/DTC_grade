import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / "n8n" / "dtc_mapping_ai_review_cloud_workflow.json"

# Node types unavailable on n8n Cloud -- if any of these show up here, the
# workflow can't actually run on the environment it's meant for.
CLOUD_INCOMPATIBLE_TYPES = {
    "n8n-nodes-base.executeCommand",
    "n8n-nodes-base.localFileTrigger",
    "n8n-nodes-base.readWriteFile",
}


def test_workflow_file_is_valid_json():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert "nodes" in data
    assert "connections" in data


def test_workflow_has_required_nodes():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    node_types = {node["type"] for node in data["nodes"]}
    assert "n8n-nodes-base.webhook" in node_types
    assert "n8n-nodes-base.respondToWebhook" in node_types
    assert "@n8n/n8n-nodes-langchain.agent" in node_types


def test_workflow_has_no_cloud_incompatible_nodes():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    node_types = {node["type"] for node in data["nodes"]}
    assert node_types.isdisjoint(CLOUD_INCOMPATIBLE_TYPES)


def test_webhook_responds_via_response_node():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    webhook = next(n for n in data["nodes"] if n["type"] == "n8n-nodes-base.webhook")
    assert webhook["parameters"]["responseMode"] == "responseNode"


def test_ai_agent_has_a_connected_language_model():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    agent_names = {n["name"] for n in data["nodes"] if n["type"] == "@n8n/n8n-nodes-langchain.agent"}
    assert agent_names, "no AI Agent node found"

    feeds_agent = False
    for outputs in data["connections"].values():
        for connection_type, targets in outputs.items():
            if connection_type != "ai_languageModel":
                continue
            for target_list in targets:
                for target in target_list:
                    if target["node"] in agent_names:
                        feeds_agent = True

    assert feeds_agent, "no node connects into the AI Agent via ai_languageModel"


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
