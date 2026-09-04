from dataclasses import dataclass


@dataclass
class RawRow:
    sheet: str
    dtc: str
    description: str
    warning_light: str
    warning_message: str
    limp_home: str
    fail_safe: str
    grade: str
    grading_background: str


@dataclass
class Row:
    system: str
    dtc: str
    description: str
    warning_light: str
    warning_message: str
    limp_home: str
    fail_safe: str
    grade: str
    grading_background: str
    sheet: str
