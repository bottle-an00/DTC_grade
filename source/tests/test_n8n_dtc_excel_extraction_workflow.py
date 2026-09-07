import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / "n8n" / "dtc_excel_extraction_workflow.json"

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
    assert "n8n-nodes-base.webhook" in node_types
    assert "n8n-nodes-base.respondToWebhook" in node_types
    assert "n8n-nodes-base.microsoftExcel" in node_types
    assert "n8n-nodes-base.merge" in node_types
    assert "@n8n/n8n-nodes-langchain.agent" in node_types


# Every OneDrive/Teams node hit a permission wall in this tenant (OneDrive
# node needs admin consent; HTTP Request can't use n8n's "managed"
# credentials at all; the Teams node also failed live). Only the Excel
# node/credential is proven to work, so this workflow does nothing but
# read sheets and hand the matched JSON back over the webhook response --
# delivery and Teams notification are the local tools.fetch_extraction job.
def test_workflow_touches_nothing_but_the_excel_credential():
    data = _load()
    node_types = {node["type"] for node in data["nodes"]}
    assert "n8n-nodes-base.microsoftOneDrive" not in node_types
    assert "n8n-nodes-base.microsoftTeams" not in node_types
    assert "n8n-nodes-base.httpRequest" not in node_types


def test_workflow_has_no_cloud_incompatible_nodes():
    data = _load()
    node_types = {node["type"] for node in data["nodes"]}
    assert node_types.isdisjoint(CLOUD_INCOMPATIBLE_TYPES)


def test_webhook_responds_via_response_node():
    data = _load()
    node = _node(data, "Webhook")
    assert node["parameters"]["responseMode"] == "responseNode"


def test_get_rows_from_sheet_uses_raw_data_to_avoid_the_merged_header_row():
    data = _load()
    node = _node(data, "Get Rows From Sheet")
    assert node["parameters"]["options"]["rawData"] is True


# The workbook to read comes from the webhook caller as a resolved Graph
# driveItem id (this node's Workbook field only has "From list"/"By ID"
# modes, no "By URL" -- the caller resolves a share link to an id first via
# tools.resolve_workbook before posting), not a fixed "From list" selection
# -- so nobody has to open n8n and re-pick a file.
def test_workbook_is_supplied_by_the_webhook_caller_not_hardcoded():
    data = _load()
    for name in ("Get Sheets", "Get Rows From Sheet"):
        node = _node(data, name)
        workbook = node["parameters"]["workbook"]
        assert workbook["mode"] == "id"
        assert "workbook_id" in workbook["value"]


# Default Excel sheet names, leftover duplicate-sheet copies ("X (2)"), and
# roll-up/summary tabs ("Total") aren't real System data -- they should be
# dropped before mapping/AI review so they never trigger an "unmapped sheet"
# alert or land as duplicate rows in the output.
def test_attach_system_ignores_known_non_system_sheet_name_patterns():
    data = _load()
    code = _node(data, "Attach System")["parameters"]["jsCode"]
    assert "IGNORE_PATTERNS" in code
    assert ".filter(" in code
    assert code.index(".filter(") < code.index(".map(")


# Some non-System sheets (grading-rule legends, etc.) don't fit a generic
# name pattern -- these are tracked as an explicit exact-name list instead.
def test_attach_system_ignores_known_documentation_sheets_by_exact_name():
    data = _load()
    code = _node(data, "Attach System")["parameters"]["jsCode"]
    assert "IGNORE_EXACT_NAMES" in code
    assert "dtc grade criteria" in code.lower()


def test_attach_system_fans_out_to_the_main_path_and_the_unmapped_branch():
    data = _load()
    node_names = {node["name"] for node in data["nodes"]}
    assert "Build Unmapped Sheets Summary" in node_names

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


def test_both_branches_converge_before_responding():
    data = _load()
    connections = data["connections"]

    rows_target = connections["Aggregate All Rows"]["main"][0][0]
    suggestions_target = connections["Parse AI Suggestions"]["main"][0][0]
    assert rows_target == {"node": "Merge Branches", "type": "main", "index": 0}
    assert suggestions_target == {"node": "Merge Branches", "type": "main", "index": 1}

    assert connections["Merge Branches"]["main"][0][0]["node"] == "Build Final Response"
    assert connections["Build Final Response"]["main"][0][0]["node"] == "Respond to Webhook"


# A single call covering every sheet in a large workbook can trip n8n's
# gateway timeout (502) before it responds, so the caller pages through
# sheets chunk_size at a time (tools.fetch_extraction.fetch_all_extraction)
# via offset/limit in the webhook body.
def test_slice_sheets_pages_by_offset_and_limit_from_the_webhook_body():
    data = _load()
    node = _node(data, "Slice Sheets")
    assert "body.offset" in node["parameters"]["jsCode"]
    assert "body.limit" in node["parameters"]["jsCode"]

    connections = data["connections"]
    assert connections["Get Sheets"]["main"][0][0]["node"] == "Slice Sheets"
    assert connections["Slice Sheets"]["main"][0][0]["node"] == "Get Rows From Sheet"


def test_build_final_response_reports_the_total_sheet_count():
    data = _load()
    node = _node(data, "Build Final Response")
    assert "totalSheets" in node["parameters"]["jsCode"]


# A chunk whose sheets all have zero DTC rows (e.g. a legend/cover sheet with
# no data) makes every node between Normalize Row and Build Final Response
# receive 0 input items -- n8n skips executing a node when it gets no data,
# and that skip cascades all the way to Respond to Webhook, which then never
# fires and the caller gets back an empty 200 body. alwaysOutputData forces
# Build Final Response to run (and thus Respond to Webhook after it) even
# when every upstream branch was skipped.
def test_build_final_response_always_outputs_data_so_empty_chunks_still_get_a_response():
    data = _load()
    node = _node(data, "Build Final Response")
    assert node.get("alwaysOutputData") is True


def test_webhook_flows_linearly_up_to_the_fan_out_point():
    data = _load()
    connections = data["connections"]

    node = "Webhook"
    visited = {node}
    while node in connections and len(connections[node]["main"][0]) == 1:
        node = connections[node]["main"][0][0]["node"]
        assert node not in visited, f"cycle detected at {node}"
        visited.add(node)

    assert node == "Attach System"
