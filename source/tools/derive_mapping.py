import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict

from dtc_transform.models import RawRow
from dtc_transform.reconstruct import reconstruct_rows


def derive_mapping(
    raw_rows: list[RawRow], reference_rows: list[tuple[str, str, str]]
) -> dict[str, dict]:
    key_to_systems: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for dtc, description, system in reference_rows:
        key_to_systems[(dtc.upper(), description.strip())][system] += 1

    sheet_hits: dict[str, Counter] = defaultdict(Counter)
    for row in raw_rows:
        systems = key_to_systems.get((row.dtc, row.description))
        if not systems:
            continue
        for system, count in systems.items():
            sheet_hits[row.sheet][system] += count

    result = {}
    for sheet, counter in sheet_hits.items():
        total = sum(counter.values())
        top_system, top_count = counter.most_common(1)[0]
        result[sheet] = {
            "system": top_system,
            "confidence": top_count / total,
            "hits": total,
        }
    return result


def _load_reference_rows(reference_db_path: str) -> list[tuple[str, str, str]]:
    con = sqlite3.connect(reference_db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT DTC, Description, System FROM dtc_master")
        return cur.fetchall()
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive sheet-to-System mapping from a reference sqlite")
    parser.add_argument("--raw-input", required=True, help="Path to the raw tab-separated export")
    parser.add_argument("--reference-db", required=True, help="Path to the existing dtc_master sqlite")
    parser.add_argument("--output", required=True, help="Path to write config/sheet_system_mapping.json")
    parser.add_argument("--review-report", required=True, help="Path to write low-confidence sheets CSV")
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    args = parser.parse_args()

    with open(args.raw_input, encoding="utf-8", errors="replace") as f:
        raw_rows, _orphans = reconstruct_rows(f.readlines())

    reference_rows = _load_reference_rows(args.reference_db)
    mapping = derive_mapping(raw_rows, reference_rows)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2, sort_keys=True)

    with open(args.review_report, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sheet", "system", "confidence", "hits"])
        for sheet, entry in sorted(mapping.items()):
            if entry["confidence"] < args.confidence_threshold:
                writer.writerow([sheet, entry["system"], f"{entry['confidence']:.2f}", entry["hits"]])


if __name__ == "__main__":
    main()
