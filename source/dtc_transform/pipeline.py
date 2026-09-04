import argparse

from .dedup import dedup
from .expand import expand_trailing_zeros
from .db_writer import write_sqlite
from .mapping import SheetSystemMapping, attach_system
from .reconstruct import reconstruct_rows


def run_pipeline(input_path: str, mapping_path: str, output_path: str, report_path: str) -> dict:
    with open(input_path, encoding="utf-8", errors="replace") as f:
        raw_rows, orphans = reconstruct_rows(f.readlines())

    mapping = SheetSystemMapping.load(mapping_path)
    rows, unmapped_sheets = attach_system(raw_rows, mapping)

    deduped = dedup(rows)
    expanded = expand_trailing_zeros(deduped)

    write_sqlite(expanded, output_path)

    low_confidence = mapping.low_confidence_sheets(threshold=0.5)

    stats = {
        "raw_row_count": len(raw_rows),
        "unrecoverable_orphan_lines": len(orphans),
        "after_dedup_count": len(deduped),
        "after_expand_count": len(expanded),
        "unmapped_sheets": unmapped_sheets,
        "low_confidence_sheets": low_confidence,
    }

    _write_report(report_path, stats, orphans)
    return stats


def _write_report(report_path: str, stats: dict, orphans: list[str]) -> None:
    lines = [
        f"raw_row_count: {stats['raw_row_count']}",
        f"unrecoverable_orphan_lines: {stats['unrecoverable_orphan_lines']}",
        f"after_dedup_count: {stats['after_dedup_count']}",
        f"after_expand_count: {stats['after_expand_count']}",
        "",
        "unmapped_sheets:",
        *[f"  - {sheet}" for sheet in stats["unmapped_sheets"]],
        "",
        "low_confidence_sheets (<50%):",
        *[f"  - {sheet}: {confidence:.0%}" for sheet, confidence in stats["low_confidence_sheets"]],
        "",
        "orphan_lines:",
        *[f"  - {line}" for line in orphans],
    ]
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Transform raw DTC master export into sqlite")
    parser.add_argument("--input", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    stats = run_pipeline(
        input_path=args.input,
        mapping_path=args.mapping,
        output_path=args.output,
        report_path=args.report,
    )
    print(f"raw={stats['raw_row_count']} dedup={stats['after_dedup_count']} "
          f"expanded={stats['after_expand_count']} "
          f"unmapped={len(stats['unmapped_sheets'])}")


if __name__ == "__main__":
    main()
