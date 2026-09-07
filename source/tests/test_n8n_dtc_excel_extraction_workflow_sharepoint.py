import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / "n8n" / "dtc_excel_extraction_workflow_sharepoint.json"

# Node types unavailable on n8n Cloud -- if any of these show up here, the
# workflow can't actually run on the environment it's meant for.
CLOUD_INCOMPATIBLE_TYPES = {
    "n8n-nodes-base.executeCommand",
    "n8n-nodes-base.localFileTrigger",
    "n8n-nodes-base.readWriteFile",
}


def _load():
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _node(data, name):
    return next(n for n in data["nodes"] if n["name"] == name)


def test_workflow_file_is_valid_json():
    data = _load()
    assert "nodes" in data
    assert "connections" in data


def test_workflow_has_required_nodes():
    data = _load()
    node_types = {node["type"] for node in data["nodes"]}
    assert "n8n-nodes-base.scheduleTrigger" in node_types
    assert "n8n-nodes-base.microsoftExcel" in node_types
    assert "n8n-nodes-base.microsoftSharePoint" in node_types
    assert "n8n-nodes-base.convertToFile" in node_types
    assert "n8n-nodes-base.splitInBatches" in node_types
    assert "n8n-nodes-base.merge" in node_types
    assert "@n8n/n8n-nodes-langchain.agent" in node_types


def test_workflow_has_no_cloud_incompatible_nodes():
    data = _load()
    node_types = {node["type"] for node in data["nodes"]}
    assert node_types.isdisjoint(CLOUD_INCOMPATIBLE_TYPES)


def test_workflow_avoids_the_blocked_onedrive_node_and_credential():
    data = _load()
    node_types = {node["type"] for node in data["nodes"]}
    assert "n8n-nodes-base.microsoftOneDrive" not in node_types


def test_get_pending_files_queries_unprocessed_list_items():
    data = _load()
    node = _node(data, "Get Pending Files")
    assert node["type"] == "n8n-nodes-base.microsoftSharePoint"
    assert node["parameters"]["resource"] == "item"
    assert node["parameters"]["operation"] == "getAll"
    assert "Processed" in node["parameters"]["options"]["filter"]


def test_get_rows_from_sheet_uses_raw_data_to_avoid_the_merged_header_row():
    data = _load()
    node = _node(data, "Get Rows From Sheet")
    assert node["parameters"]["options"]["rawData"] is True


def test_get_rows_from_sheet_references_the_current_loop_files_drive_item():
    data = _load()
    node = _node(data, "Get Rows From Sheet")
    assert "Loop Over Files" in node["parameters"]["workbook"]["value"]
    assert "driveItem.id" in node["parameters"]["workbook"]["value"]


def test_upload_matched_json_uses_the_sharepoint_node():
    data = _load()
    node = _node(data, "Upload Matched JSON")
    assert node["type"] == "n8n-nodes-base.microsoftSharePoint"
    assert node["parameters"]["resource"] == "file"
    assert node["parameters"]["operation"] == "upload"


def test_attach_system_fans_out_to_the_main_path_and_the_unmapped_alert():
    data = _load()
    node_names = {node["name"] for node in data["nodes"]}
    assert "Build Unmapped Sheets Summary" in node_names
    assert "Send Unmapped Sheets Teams Card" in node_names

    targets = {t["node"] for t in data["connections"]["Attach System"]["main"][0]}
    assert targets == {"Aggregate All Rows", "Build Unmapped Sheets Summary"}


def test_unmapped_sheets_ai_agent_has_a_connected_language_model():
    data = _load()
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


def test_loop_over_files_feeds_get_sheets_on_its_loop_output():
    data = _load()
    loop_outputs = data["connections"]["Loop Over Files"]["main"]
    assert len(loop_outputs) == 2, "Loop Over Files should have a 'done' and a 'loop' output"
    done_targets, loop_targets = loop_outputs
    assert done_targets == []
    assert loop_targets == [{"node": "Get Sheets", "type": "main", "index": 0}]


def test_both_branches_converge_on_merge_before_marking_processed():
    data = _load()
    connections = data["connections"]

    success_target = connections["Send Teams Notification"]["main"][0][0]
    alert_target = connections["Send Unmapped Sheets Teams Card"]["main"][0][0]
    assert success_target == {"node": "Merge Branches", "type": "main", "index": 0}
    assert alert_target == {"node": "Merge Branches", "type": "main", "index": 1}

    assert connections["Merge Branches"]["main"][0][0]["node"] == "Mark File Processed"


def test_mark_file_processed_updates_the_list_item_and_loops_back():
    data = _load()
    node = _node(data, "Mark File Processed")
    assert node["type"] == "n8n-nodes-base.microsoftSharePoint"
    assert node["parameters"]["resource"] == "item"
    assert node["parameters"]["operation"] == "update"
    assert "Loop Over Files" in node["parameters"]["itemId"]

    connections = data["connections"]
    target = connections["Mark File Processed"]["main"][0][0]
    assert target == {"node": "Loop Over Files", "type": "main", "index": 0}
