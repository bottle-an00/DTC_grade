from .constants import DTC_PATTERN
from .models import RawRow

FIELD_COUNT = 9


def reconstruct_rows(lines: list[str]) -> tuple[list[RawRow], list[str]]:
    rows: list[RawRow] = []
    orphans: list[str] = []
    current_fields: list[str] | None = None

    for raw_line in lines:
        line = raw_line.rstrip("\n").rstrip("\r")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and DTC_PATTERN.match(parts[1].strip()):
            if current_fields is not None:
                rows.append(_fields_to_row(current_fields))
            current_fields = _normalize_fields(parts)
        else:
            if current_fields is None:
                orphans.append(line)
            else:
                current_fields[-1] = f"{current_fields[-1]} {line.strip()}"

    if current_fields is not None:
        rows.append(_fields_to_row(current_fields))

    return rows, orphans


def _normalize_fields(parts: list[str]) -> list[str]:
    if len(parts) == FIELD_COUNT:
        return list(parts)
    if len(parts) > FIELD_COUNT:
        head = parts[: FIELD_COUNT - 1]
        tail = "\t".join(parts[FIELD_COUNT - 1 :])
        return head + [tail]
    return parts + [""] * (FIELD_COUNT - len(parts))


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
