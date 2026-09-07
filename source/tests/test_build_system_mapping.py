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


def test_joins_multiple_matching_candidates_with_a_comma():
    # config/sheet_system_mapping.json already stores multi-value System
    # strings this way (e.g. "ABSESC,ABSESP,ABSVDC") -- when several
    # candidates each check out against vehicle_info but disagree, that's
    # not a failure, it's a multi-system sheet like the ones already in
    # the mapping table.
    ecu_doc_rows = [("MULTI(Sheet)", "92710100_ABC_1006101_001")]
    diagnostic_index = {"6101": ["0010D0", "0011A0"]}
    vehicle_resolved = {"0010D0": "SYS_B", "0011A0": "SYS_A"}

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    assert resolved == {"MULTI(Sheet)": "SYS_A,SYS_B"}
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
