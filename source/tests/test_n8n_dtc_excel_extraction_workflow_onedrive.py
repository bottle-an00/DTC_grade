import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / "n8n" / "dtc_excel_extraction_workflow_onedrive.json"

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
    assert "n8n-nodes-base.microsoftOneDrive" in node_types
    assert "n8n-nodes-base.convertToFile" in node_types
    assert "n8n-nodes-base.splitInBatches" in node_types
    assert "n8n-nodes-base.merge" in node_types
    assert "@n8n/n8n-nodes-langchain.agent" in node_types


def test_workflow_has_no_cloud_incompatible_nodes():
    data = _load()
    node_types = {node["type"] for node in data["nodes"]}
    assert node_types.isdisjoint(CLOUD_INCOMPATIBLE_TYPES)


def test_list_pending_files_scans_the_pending_folder():
    data = _load()
    node = _node(data, "List Pending Files")
    assert node["type"] == "n8n-nodes-base.microsoftOneDrive"
    assert node["parameters"]["resource"] == "folder"
    assert node["parameters"]["operation"] == "getChildren"


def test_get_rows_from_sheet_uses_raw_data_to_avoid_the_merged_header_row():
    data = _load()
    node = _node(data, "Get Rows From Sheet")
    assert node["parameters"]["options"]["rawData"] is True


def test_upload_to_onedrive_uses_the_converted_file_binary():
    data = _load()
    node = _node(data, "Upload to OneDrive")
    assert node["type"] == "n8n-nodes-base.microsoftOneDrive"
    assert node["parameters"]["binaryPropertyName"] == "data"


def test_teams_notification_links_to_the_uploaded_file():
    data = _load()
    node = _node(data, "Send Teams Notification")
    assert node["type"] == "n8n-nodes-base.httpRequest"
    assert "$json.webUrl" in node["parameters"]["jsonBody"]


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


def test_get_rows_from_sheet_references_the_current_loop_file():
    data = _load()
    node = _node(data, "Get Rows From Sheet")
    assert "Loop Over Files" in node["parameters"]["workbook"]["value"]


def test_both_branches_converge_on_merge_before_moving_the_file():
    data = _load()
    connections = data["connections"]

    success_target = connections["Send Teams Notification"]["main"][0][0]
    alert_target = connections["Send Unmapped Sheets Teams Card"]["main"][0][0]
    assert success_target == {"node": "Merge Branches", "type": "main", "index": 0}
    assert alert_target == {"node": "Merge Branches", "type": "main", "index": 1}

    assert connections["Merge Branches"]["main"][0][0]["node"] == "Move File to Completed Folder"


def test_move_file_to_completed_folder_loops_back_to_split_in_batches():
    data = _load()
    connections = data["connections"]
    target = connections["Move File to Completed Folder"]["main"][0][0]
    assert target == {"node": "Loop Over Files", "type": "main", "index": 0}


def test_move_file_uses_the_dedicated_onedrive_node_not_a_raw_http_call():
    data = _load()
    node = _node(data, "Move File to Completed Folder")
    assert node["type"] == "n8n-nodes-base.microsoftOneDrive"
    assert "Loop Over Files" in node["parameters"]["fileId"]["value"]
