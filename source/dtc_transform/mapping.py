import json

from .models import RawRow, Row


class SheetSystemMapping:
    def __init__(self, data: dict[str, dict]):
        self._data = data

    @classmethod
    def load(cls, path: str) -> "SheetSystemMapping":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data)

    def system_for(self, sheet: str) -> str | None:
        entry = self._data.get(sheet)
        return entry["system"] if entry else None

    def low_confidence_sheets(self, threshold: float = 0.5) -> list[tuple[str, float]]:
        return sorted(
            (sheet, entry["confidence"])
            for sheet, entry in self._data.items()
            if entry.get("source") != "manual" and entry.get("confidence", 1.0) < threshold
        )


def attach_system(
    raw_rows: list[RawRow], mapping: SheetSystemMapping
) -> tuple[list[Row], list[str]]:
    rows: list[Row] = []
    unmapped: set[str] = set()

    for raw in raw_rows:
        system = mapping.system_for(raw.sheet)
        if system is None:
            unmapped.add(raw.sheet)
            system = ""
        rows.append(
            Row(
                system=system,
                dtc=raw.dtc,
                description=raw.description,
                warning_light=raw.warning_light,
                warning_message=raw.warning_message,
                limp_home=raw.limp_home,
                fail_safe=raw.fail_safe,
                grade=raw.grade,
                grading_background=raw.grading_background,
                sheet=raw.sheet,
            )
        )

    return rows, sorted(unmapped)
