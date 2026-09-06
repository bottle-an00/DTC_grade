import csv
import io

from .constants import DTC_PATTERN
from .models import RawRow

FIELD_COUNT = 9


def reconstruct_rows(lines: list[str]) -> tuple[list[RawRow], list[str], int]:
    """Parse the raw tab-separated export into RawRow records.

    Real production exports quote cell values that contain embedded tabs
    and/or newlines using standard CSV/TSV quoting rules (RFC4180-style,
    `quotechar='"'`). We rely on Python's csv module to recover the correct
    logical fields for each record, including fields whose content spans
    multiple physical lines.

    A record is considered valid (and turned into a RawRow) only if its
    2nd field (index 1) matches DTC_PATTERN. Any csv-parsed record that
    fails this check is reported as an orphan and dropped -- this remains
    the safety net for the rare residual case where quoting is broken in
    the source data and csv parsing does not recover a clean record.

    Returns a 3-tuple ``(rows, orphans, anomalous_field_count)``. Records
    whose field count is not exactly FIELD_COUNT (9) are still recovered
    via padding/merging in `_normalize_fields`, but per spec ("1단계") this
    is an anomaly that must be visible, not silently absorbed -- callers
    should surface `anomalous_field_count` in their reports.
    """
    normalized_lines = [line.rstrip("\r\n") for line in lines]
    text = "\n".join(normalized_lines)
    reader = csv.reader(io.StringIO(text), delimiter="\t")

    rows: list[RawRow] = []
    orphans: list[str] = []
    anomalous_field_count = 0
    consumed = 0

    for fields in reader:
        start, consumed = consumed, reader.line_num

        if not fields or (len(fields) == 1 and fields[0] == ""):
            # Blank physical line outside of any quoted field.
            continue

        if len(fields) >= 2 and DTC_PATTERN.match(fields[1].strip()):
            if len(fields) != FIELD_COUNT:
                anomalous_field_count += 1
            rows.append(_fields_to_row(_normalize_fields(fields)))
        else:
            orphans.append("\n".join(normalized_lines[start:consumed]))

    return rows, orphans, anomalous_field_count


def _normalize_fields(fields: list[str]) -> list[str]:
    if len(fields) == FIELD_COUNT:
        return list(fields)
    if len(fields) > FIELD_COUNT:
        # Defensive fallback: csv already resolves quoted tabs/newlines, so
        # this path should be rare in practice (an unquoted stray tab).
        head = fields[: FIELD_COUNT - 1]
        tail = "\t".join(fields[FIELD_COUNT - 1 :])
        return head + [tail]
    return fields + [""] * (FIELD_COUNT - len(fields))


def _fields_to_row(fields: list[str]) -> RawRow:
    sheet, dtc, desc, wl, wm, lh, fs, grade, bg = fields
    return RawRow(
        sheet=sheet.strip(),
        dtc=dtc.strip().upper(),
        description=desc.strip(),
        warning_light=wl.strip(),
        warning_message=wm.strip(),
        limp_home=lh.strip(),
        fail_safe=fs.strip(),
        grade=grade.strip(),
        grading_background=bg.strip(),
    )
