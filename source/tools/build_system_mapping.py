import csv
import json

from dtc_transform.company_db.code_extract import extract_compare_code
from dtc_transform.company_db.diagnostic_db import build_diagnostic_index
from dtc_transform.company_db.ecu_doc import load_ecu_doc_rows
from dtc_transform.company_db.vehicle_info import build_vehicle_info_index


def resolve_system_names(
    ecu_doc_rows: list[tuple[str, str]],
    diagnostic_index: dict[str, list[str]],
    vehicle_resolved: dict[str, str],
) -> tuple[dict[str, str], list[dict]]:
    resolved: dict[str, str] = {}
    unresolved: list[dict] = []

    for system_name, doc_code in ecu_doc_rows:
        try:
            compare_code = extract_compare_code(doc_code)
        except ValueError:
            unresolved.append({"sheet": system_name, "reason": "bad_doc_code", "candidates": []})
            continue

        candidate_files = diagnostic_index.get(compare_code, [])
        matched_descs = {
            vehicle_resolved[stem] for stem in candidate_files if stem in vehicle_resolved
        }

        if len(matched_descs) == 1:
            resolved[system_name] = next(iter(matched_descs))
        elif len(matched_descs) == 0:
            unresolved.append({"sheet": system_name, "reason": "no_match", "candidates": candidate_files})
        else:
            unresolved.append(
                {"sheet": system_name, "reason": "ambiguous", "candidates": sorted(matched_descs)}
            )

    return resolved, unresolved


def build_mapping_json(resolved: dict[str, str], existing: dict[str, dict]) -> dict[str, dict]:
    merged = dict(existing)
    for sheet, system in resolved.items():
        current = merged.get(sheet)
        if current and current.get("source") == "manual":
            continue
        merged[sheet] = {"system": system, "source": "company_db"}
    return merged


def write_review_csv(path: str, unresolved: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sheet", "reason", "candidates"])
        for row in unresolved:
            writer.writerow([row["sheet"], row["reason"], ";".join(row["candidates"])])


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build config/sheet_system_mapping.json by joining ECU DOC, diagnostic-DB XML, and vehicle_info XML"
    )
    parser.add_argument("--ecu-doc-csv", required=True, help="CSV export of ECU DOC columns A (doc code) and O (system name)")
    parser.add_argument("--diagnostic-db-root", required=True, help="Root folder containing the region subfolders of 진단 DB XML files")
    parser.add_argument("--vehicle-info-xml", required=True, nargs="+", help="One or more vehicle_info/*.xml file paths")
    parser.add_argument("--mapping-output", required=True, help="Path to config/sheet_system_mapping.json to update")
    parser.add_argument("--review-csv", required=True, help="Path to write the unresolved-sheets review CSV")
    args = parser.parse_args()

    ecu_doc_rows = load_ecu_doc_rows(args.ecu_doc_csv)
    diagnostic_index = build_diagnostic_index(args.diagnostic_db_root)
    vehicle_resolved, _conflicts = build_vehicle_info_index(args.vehicle_info_xml)

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    try:
        with open(args.mapping_output, encoding="utf-8") as f:
            existing = json.load(f)
    except FileNotFoundError:
        existing = {}

    merged = build_mapping_json(resolved, existing)

    with open(args.mapping_output, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2, sort_keys=True)

    write_review_csv(args.review_csv, unresolved)

    print(
        f"resolved={len(resolved)} unresolved={len(unresolved)} "
        f"mapping_output={args.mapping_output} review_csv={args.review_csv}"
    )


if __name__ == "__main__":
    main()
