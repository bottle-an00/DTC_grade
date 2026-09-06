import argparse
import csv
import json
import sqlite3

from dtc_transform.models import RawRow
from dtc_transform.reconstruct import reconstruct_rows
from tools.derive_mapping import count_sheet_candidates


def build_review_context(
    raw_rows: list[RawRow],
    reference_rows: list[tuple[str, str, str]],
    review_sheets: list[str],
    top_n_candidates: int = 5,
    sample_size: int = 8,
) -> list[dict]:
    """Assemble, for each sheet in review_sheets, the evidence an AI reviewer
    needs to suggest a corrected System mapping: the top candidate System
    values with their vote counts, and example (DTC, description) pairs
    drawn from that sheet's own raw rows.
    """
    candidates_by_sheet = count_sheet_candidates(raw_rows, reference_rows)

    rows_by_sheet: dict[str, list[RawRow]] = {}
    for row in raw_rows:
        rows_by_sheet.setdefault(row.sheet, []).append(row)

    context = []
    for sheet in review_sheets:
        counter = candidates_by_sheet.get(sheet)
        top_candidates = (
            [{"system": system, "votes": votes} for system, votes in counter.most_common(top_n_candidates)]
            if counter
            else []
        )

        samples = []
        seen = set()
        for row in rows_by_sheet.get(sheet, []):
            key = (row.dtc, row.description)
            if key in seen:
                continue
            seen.add(key)
            samples.append({"dtc": row.dtc, "description": row.description})
            if len(samples) >= sample_size:
                break

        context.append({"sheet": sheet, "top_candidates": top_candidates, "samples": samples})

    return context


def _load_reference_rows(reference_db_path: str) -> list[tuple[str, str, str]]:
    con = sqlite3.connect(reference_db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT DTC, Description, System FROM dtc_master")
        return cur.fetchall()
    finally:
        con.close()


def _load_review_sheets(review_csv_path: str) -> list[str]:
    with open(review_csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [row["sheet"] for row in reader]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build AI-review context (candidate votes + DTC samples) for low-confidence sheets"
    )
    parser.add_argument("--raw-input", required=True, help="Path to the raw tab-separated export")
    parser.add_argument("--reference-db", required=True, help="Path to the existing dtc_master sqlite")
    parser.add_argument("--review-csv", required=True, help="Path to the low-confidence sheets CSV")
    parser.add_argument("--output", required=True, help="Path to write the review context JSON")
    parser.add_argument("--top-n-candidates", type=int, default=5)
    parser.add_argument("--sample-size", type=int, default=8)
    args = parser.parse_args()

    with open(args.raw_input, encoding="utf-8", errors="replace") as f:
        raw_rows, _orphans, _anomalous_field_count = reconstruct_rows(f.readlines())

    reference_rows = _load_reference_rows(args.reference_db)
    review_sheets = _load_review_sheets(args.review_csv)

    context = build_review_context(
        raw_rows,
        reference_rows,
        review_sheets,
        top_n_candidates=args.top_n_candidates,
        sample_size=args.sample_size,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
