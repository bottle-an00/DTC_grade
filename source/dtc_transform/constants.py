import re

DTC_PATTERN = re.compile(r"^[PBCU][0-9A-F]{4,6}$", re.IGNORECASE)

GRADE_SEVERITY = {"A": 0, "B": 1, "C": 2, "D": 3}
