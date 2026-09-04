from .constants import GRADE_SEVERITY
from .models import Row

VALID_GRADES = GRADE_SEVERITY.keys()


def filter_invalid_grades(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    valid: list[Row] = []
    excluded: list[Row] = []
    for row in rows:
        if row.grade in VALID_GRADES:
            valid.append(row)
        else:
            excluded.append(row)
    return valid, excluded
