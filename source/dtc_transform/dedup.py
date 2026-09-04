from .constants import GRADE_SEVERITY
from .models import Row


def dedup(rows: list[Row]) -> list[Row]:
    # Stage 1: same (system, dtc, grade) -> ignore description, keep first occurrence.
    stage1: dict[tuple[str, str, str], Row] = {}
    for row in rows:
        key = (row.system, row.dtc, row.grade)
        if key not in stage1:
            stage1[key] = row

    # Stage 2: same (system, dtc) with differing grade -> keep most severe grade.
    best: dict[tuple[str, str], Row] = {}
    for row in stage1.values():
        key = (row.system, row.dtc)
        current = best.get(key)
        if current is None or GRADE_SEVERITY.get(row.grade, 99) < GRADE_SEVERITY.get(current.grade, 99):
            best[key] = row

    return list(best.values())
