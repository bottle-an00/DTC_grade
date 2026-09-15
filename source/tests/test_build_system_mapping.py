import csv
import json

from tools.build_system_mapping import (
    build_mapping_json,
    resolve_system_names,
    write_review_csv,
)


def test_resolves_when_exactly_one_matching_candidate_exists():
    ecu_doc_rows = [("4WD(4WheelDrive)", "92710100_ABC_1006101_001")]
    diagnostic_index = {"6101": ["0010D0", "0010A0"]}
    vehicle_resolved = {"0010D0": "4WD"}

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    assert resolved == {"4WD(4WheelDrive)": "4WD"}
    assert unresolved == []


def test_reports_no_match_when_no_candidate_is_in_vehicle_info():
    ecu_doc_rows = [("UNKNOWN(Sheet)", "92710100_ABC_1006101_001")]
    diagnostic_index = {"6101": ["0010D0"]}
    vehicle_resolved = {}

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    assert resolved == {}
    assert unresolved == [{"sheet": "UNKNOWN(Sheet)", "reason": "no_match", "candidates": ["0010D0"]}]


# A 4-character compare code is shared by unrelated controllers, so the
# files behind one code can resolve to different systems. Unioning them
# used to yield mappings like "DHS_FL,ENGINE" for a door-handle sheet --
# wrong, and silent. Ambiguity is now surfaced for review instead.
def test_disagreeing_candidates_are_reported_as_ambiguous_not_joined():
    ecu_doc_rows = [("MULTI(Sheet)", "92710100_ABC_1006101_001")]
    diagnostic_index = {"6101": ["0010D0", "0011A0"]}
    vehicle_resolved = {"0010D0": "SYS_B", "0011A0": "SYS_A"}

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    assert resolved == {}
    assert unresolved == [
        {"sheet": "MULTI(Sheet)", "reason": "ambiguous_compare_code", "candidates": ["SYS_A", "SYS_B"]}
    ]


def test_several_candidate_files_agreeing_on_one_system_still_resolve():
    ecu_doc_rows = [("AGREE(Sheet)", "92710100_ABC_1006101_001")]
    diagnostic_index = {"6101": ["0010D0", "0010A0"]}
    vehicle_resolved = {"0010D0": "SYS_A", "0010A0": "SYS_A"}

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    assert resolved == {"AGREE(Sheet)": "SYS_A"}
    assert unresolved == []


def test_reports_bad_doc_code_when_compare_code_extraction_fails():
    ecu_doc_rows = [("HeaderRow", "notavalidcode")]

    resolved, unresolved = resolve_system_names(ecu_doc_rows, {}, {})

    assert resolved == {}
    assert unresolved == [{"sheet": "HeaderRow", "reason": "bad_doc_code", "candidates": []}]


def test_build_mapping_json_preserves_manual_entries():
    resolved = {"4WD(4WheelDrive)": "4WD", "AIRBAG": "AIRBAG_NEW"}
    existing = {
        "AIRBAG": {"system": "AIRBAG_OLD", "source": "manual"},
    }

    merged = build_mapping_json(resolved, existing)

    assert merged["4WD(4WheelDrive)"] == {"system": "4WD", "source": "company_db"}
    assert merged["AIRBAG"] == {"system": "AIRBAG_OLD", "source": "manual"}


def test_write_review_csv_lists_unresolved_sheets(tmp_path):
    path = tmp_path / "review.csv"
    unresolved = [{"sheet": "AMBIG(Sheet)", "reason": "ambiguous", "candidates": ["SYS_A", "SYS_B"]}]

    write_review_csv(str(path), unresolved)

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["sheet", "reason", "candidates"]
    assert rows[1] == ["AMBIG(Sheet)", "ambiguous", "SYS_A;SYS_B"]
