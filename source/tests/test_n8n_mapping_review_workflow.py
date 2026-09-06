import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / "n8n" / "dtc_mapping_ai_review_workflow.json"


def test_workflow_file_is_valid_json():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert "nodes" in data
    assert "connections" in data


def test_workflow_has_required_nodes():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    node_types = {node["type"] for node in data["nodes"]}
    assert "n8n-nodes-base.manualTrigger" in node_types
    assert "n8n-nodes-base.executeCommand" in node_types
    assert "n8n-nodes-base.if" in node_types
    assert "n8n-nodes-base.httpRequest" in node_types
    assert "@n8n/n8n-nodes-langchain.agent" in node_types


def test_execute_command_nodes_call_the_three_mapping_tools():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    exec_nodes = [n for n in data["nodes"] if n["type"] == "n8n-nodes-base.executeCommand"]
    commands = " ".join(n["parameters"].get("command", "") for n in exec_nodes)
    assert "tools.derive_mapping" in commands
    assert "tools.review_context" in commands
    assert "tools.apply_ai_suggestions" in commands


def test_ai_agent_has_a_connected_language_model():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    agent_names = {n["name"] for n in data["nodes"] if n["type"] == "@n8n/n8n-nodes-langchain.agent"}
    assert agent_names, "no AI Agent node found"

    feeds_agent = False
    for source_node, outputs in data["connections"].items():
        for connection_type, targets in outputs.items():
            if connection_type != "ai_languageModel":
                continue
            for target_list in targets:
                for target in target_list:
                    if target["node"] in agent_names:
                        feeds_agent = True

    assert feeds_agent, "no node connects into the AI Agent via ai_languageModel"


def test_teams_webhook_urls_are_placeholders_not_hardcoded_real_urls():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    http_nodes = [n for n in data["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"]
    assert http_nodes
    for node in http_nodes:
        assert "REPLACE-WITH-YOUR-TEAMS-INCOMING-WEBHOOK-URL" in node["parameters"]["url"]


def test_ai_suggestions_never_write_to_sheet_system_mapping_json():
    # The AI-review workflow must only annotate the review CSV, never the
    # shipped mapping config -- humans apply accepted suggestions manually.
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    exec_nodes = [n for n in data["nodes"] if n["type"] == "n8n-nodes-base.executeCommand"]
    apply_node = next(n for n in exec_nodes if "tools.apply_ai_suggestions" in n["parameters"]["command"])
    assert "sheet_system_mapping.json" not in apply_node["parameters"]["command"]
    assert "sheet_system_mapping_review.csv" in apply_node["parameters"]["command"]
