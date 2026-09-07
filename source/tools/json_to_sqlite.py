import argparse
import json
import sys

from dtc_transform.dedup import dedup
from dtc_transform.expand import expand_trailing_zeros
from dtc_transform.db_writer import write_sqlite
from dtc_transform.grade_filter import filter_invalid_grades
from dtc_transform.models import Row

FIELDS = [
    "system", "dtc", "description", "warning_light", "warning_message",
    "limp_home", "fail_safe", "grade", "grading_background", "sheet",
]


def rows_from_matched_json(matched_rows: list[dict]) -> list[Row]:
    """Build Row records from n8n's already-matched JSON (sheet -> System
    lookup already applied there; this only reshapes the plain dicts)."""
    return [Row(**{field: row.get(field, "") for field in FIELDS}) for row in matched_rows]


def convert(matched_json_path: str, output_path: str, report_path: str) -> dict:
    with open(matched_json_path, encoding="utf-8") as f:
        matched_rows = json.load(f)["rows"]

    rows = rows_from_matched_json(matched_rows)
    unmapped_sheets = sorted({row.sheet for row in rows if not row.system})

    deduped = dedup(rows)
    valid_grade_rows, excluded_rows = filter_invalid_grades(deduped)
    expanded = expand_trailing_zeros(valid_grade_rows)

    write_sqlite(expanded, output_path)

    stats = {
        "raw_row_count": len(rows),
        "after_dedup_count": len(deduped),
        "after_expand_count": len(expanded),
        "unmapped_sheets": unmapped_sheets,
        "excluded_invalid_grade_count": len(excluded_rows),
    }
    _write_report(report_path, stats)
    return stats


def _write_report(report_path: str, stats: dict) -> None:
    lines = [
        f"raw_row_count: {stats['raw_row_count']}",
        f"after_dedup_count: {stats['after_dedup_count']}",
        f"after_expand_count: {stats['after_expand_count']}",
        f"excluded_invalid_grade_count: {stats['excluded_invalid_grade_count']}",
        "",
        "unmapped_sheets:",
        *[f"  - {sheet}" for sheet in stats["unmapped_sheets"]],
    ]
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert the already-matched DTC JSON (downloaded from the n8n Teams link) into the sqlite grade master"
    )
    parser.add_argument("--matched-json", required=True, help="Path to the matched JSON downloaded from the Teams link")
    parser.add_argument("--output", required=True, help="Path to write the output sqlite")
    parser.add_argument("--report", required=True, help="Path to write the run report")
    args = parser.parse_args()

    stats = convert(args.matched_json, args.output, args.report)

    print(f"raw={stats['raw_row_count']} dedup={stats['after_dedup_count']} "
          f"excluded_invalid_grade={stats['excluded_invalid_grade_count']} "
          f"expanded={stats['after_expand_count']} "
          f"unmapped={len(stats['unmapped_sheets'])}")

    if stats["unmapped_sheets"]:
        print(
            "ERROR: unmapped sheets found -- these rows have an empty System "
            "and must not be auto-published:",
            file=sys.stderr,
        )
        for sheet in stats["unmapped_sheets"]:
            print(f"  - {sheet}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
