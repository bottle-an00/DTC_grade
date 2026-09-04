import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / "n8n" / "dtc_master_workflow.json"


def test_workflow_file_is_valid_json():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert "nodes" in data
    assert "connections" in data


def test_workflow_has_required_nodes():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    node_types = {node["type"] for node in data["nodes"]}
    assert "n8n-nodes-base.localFileTrigger" in node_types
    assert "n8n-nodes-base.executeCommand" in node_types
    assert "n8n-nodes-base.if" in node_types


def test_execute_command_node_calls_pipeline_module():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    exec_nodes = [n for n in data["nodes"] if n["type"] == "n8n-nodes-base.executeCommand"]
    assert exec_nodes, "no executeCommand node found"
    commands = " ".join(n["parameters"].get("command", "") for n in exec_nodes)
    assert "dtc_transform.pipeline" in commands
