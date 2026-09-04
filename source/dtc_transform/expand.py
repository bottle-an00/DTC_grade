import dataclasses

from .constants import GRADE_SEVERITY
from .models import Row


def expand_trailing_zeros(rows: list[Row]) -> list[Row]:
    by_key: dict[tuple[str, str], Row] = {(r.system, r.dtc): r for r in rows}

    for row in list(by_key.values()):
        if len(row.dtc) <= 2 or not row.dtc.endswith("00"):
            continue
        short_dtc = row.dtc[:-2]
        key = (row.system, short_dtc)
        candidate = dataclasses.replace(row, dtc=short_dtc)
        existing = by_key.get(key)
        if existing is None or GRADE_SEVERITY.get(candidate.grade, 99) < GRADE_SEVERITY.get(existing.grade, 99):
            by_key[key] = candidate

    return list(by_key.values())
