from .constants import GRADE_SEVERITY
from .models import Row

O_MARKS = {"O", "○"}


def _o_count(row: Row) -> int:
    return sum(1 for value in (row.warning_light, row.warning_message, row.limp_home, row.fail_safe) if value in O_MARKS)


def dedup(rows: list[Row]) -> list[Row]:
    # Stage 1: same (system, dtc, grade) -> keep the row with the most "O"
    # marks across Warning_Light/Warning_Message/Limp_Home/Fail_Safe (more
    # O's means more of the safety-relevant symptoms are actually flagged,
    # so it's the more complete record among otherwise-duplicate rows).
    # Ties (including the common case of no O's on either side) keep the
    # first occurrence.
    stage1: dict[tuple[str, str, str], Row] = {}
    for row in rows:
        key = (row.system, row.dtc, row.grade)
        current = stage1.get(key)
        if current is None or _o_count(row) > _o_count(current):
            stage1[key] = row

    # Stage 2: same (system, dtc) with differing grade -> keep most severe grade.
    best: dict[tuple[str, str], Row] = {}
    for row in stage1.values():
        key = (row.system, row.dtc)
        current = best.get(key)
        if current is None or GRADE_SEVERITY.get(row.grade, 99) < GRADE_SEVERITY.get(current.grade, 99):
            best[key] = row

    return list(best.values())
