import csv


def load_ecu_doc_rows(csv_path: str) -> list[tuple[str, str]]:
    """Read a 2-column (doc_code, system_name) CSV exported from the
    protected ECU DOC workbook's columns A and O. Any header row or
    malformed line is passed through as-is -- the caller resolves those
    downstream when compare-code extraction fails on them."""
    rows: list[tuple[str, str]] = []

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            doc_code, system_name = row[0].strip(), row[1].strip()
            if not doc_code or not system_name:
                continue
            rows.append((system_name, doc_code))

    return rows
