# DTC Master → SQLite 변환 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DTC 마스터 원본 텍스트(Excel에서 사람이 정당한 권한으로 추출한 tab-separated 파일)를 읽어, 시트명→System 매핑 / 등급 우선순위 기반 중복 제거 / '00' 축약 코드 확장 / 등급 고정 치환 암호화를 적용한 뒤 기존 산출물과 동일한 스키마의 sqlite 파일을 생성하고, n8n(self-hosted)에서 바로 import해 재사용할 수 있는 워크플로우를 제공한다.

**Architecture:** `source/dtc_transform/` 아래에 단계별로 분리된 순수 함수 모듈(reconstruct → mapping → dedup → expand → crypto → db_writer)을 두고, `pipeline.py`가 이를 순서대로 호출하는 CLI로 오케스트레이션한다. 시트↔System 매핑은 `tools/derive_mapping.py`가 기존 sqlite 산출물과 새 원본을 교차 매칭해 `config/sheet_system_mapping.json`으로 미리 생성해두는 정적 설정 파일이며, 파이프라인 실행 시마다 다시 계산하지 않는다. n8n 워크플로우는 Execute Command 노드로 이 CLI를 호출한다.

**Tech Stack:** Python 3.11, 표준 라이브러리만 사용(sqlite3, re, json, argparse, dataclasses, csv) — 외부 의존성 없음. pytest 9.1.1로 테스트.

**Spec:** [docs/superpowers/specs/2026-09-04-dtc-master-pipeline-design.md](../specs/2026-09-04-dtc-master-pipeline-design.md)

## Global Constraints

- Python 3.11 표준 라이브러리만 사용, 외부 pip 패키지 추가 금지 (배포 환경에 pip 설치 권한이 없을 수 있음을 가정)
- 모든 모듈은 `source/dtc_transform/` 아래에 두고, 각 파일은 단일 책임만 가진다
- 테스트는 `source/tests/`에 두고 `cd source && python -m pytest tests/ -v`로 실행
- DTC 정규식은 `^[PBCU][0-9A-F]{4,6}$` (대소문자 무시)로 전 모듈에서 동일하게 사용 (constants.py 한 곳에서만 정의)
- 등급 심각도는 A>B>C>D (A가 가장 심각) 고정
- 등급 치환표는 스펙에 명시된 4개 값 고정, 다른 값이 들어오면 예외 발생시켜 중단 (조용히 넘어가지 않음)

---

### Task 1: 프로젝트 스캐폴딩 + 공용 상수/모델

**Files:**
- Create: `source/conftest.py`
- Create: `source/dtc_transform/__init__.py`
- Create: `source/dtc_transform/constants.py`
- Create: `source/dtc_transform/models.py`
- Test: `source/tests/test_constants.py`
- Test: `source/tests/test_models.py`

**Interfaces:**
- Produces: `DTC_PATTERN: re.Pattern` (constants.py), `GRADE_SEVERITY: dict[str, int]` (constants.py), `RawRow` dataclass (models.py, fields: `sheet, dtc, description, warning_light, warning_message, limp_home, fail_safe, grade, grading_background` — 모두 `str`), `Row` dataclass (models.py, fields: `system, dtc, description, warning_light, warning_message, limp_home, fail_safe, grade, grading_background, sheet` — 모두 `str`)

- [ ] **Step 0: git 저장소 초기화 (현재 디렉터리는 git 저장소가 아님)**

```bash
git init
```

`.gitignore` 생성:
```
__pycache__/
*.pyc
.pytest_cache/
```

Run: `git add .gitignore && git commit -m "chore: initialize repository"`

- [ ] **Step 1: 디렉터리와 sys.path 설정 파일 작성**

`source/conftest.py`:
```python
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
```

`source/dtc_transform/__init__.py`: (빈 파일)

- [ ] **Step 2: 실패하는 테스트 작성 (constants)**

`source/tests/test_constants.py`:
```python
from dtc_transform.constants import DTC_PATTERN, GRADE_SEVERITY


def test_dtc_pattern_matches_valid_codes():
    assert DTC_PATTERN.match("P0AC200")
    assert DTC_PATTERN.match("b160487".upper())
    assert DTC_PATTERN.match("C152811")
    assert DTC_PATTERN.match("U002888")


def test_dtc_pattern_rejects_invalid_codes():
    assert not DTC_PATTERN.match("XYZ123")
    assert not DTC_PATTERN.match("")
    assert not DTC_PATTERN.match("Control Module Programming Error")


def test_grade_severity_order():
    assert GRADE_SEVERITY["A"] < GRADE_SEVERITY["B"] < GRADE_SEVERITY["C"] < GRADE_SEVERITY["D"]
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_constants.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dtc_transform.constants'`

- [ ] **Step 4: constants.py 구현**

`source/dtc_transform/constants.py`:
```python
import re

DTC_PATTERN = re.compile(r"^[PBCU][0-9A-F]{4,6}$", re.IGNORECASE)

GRADE_SEVERITY = {"A": 0, "B": 1, "C": 2, "D": 3}
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_constants.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 실패하는 테스트 작성 (models)**

`source/tests/test_models.py`:
```python
from dtc_transform.models import RawRow, Row


def test_raw_row_fields():
    row = RawRow(
        sheet="TCU(TransmissionControlUnit)", dtc="P0AC200", description="desc",
        warning_light="X", warning_message="X", limp_home="X", fail_safe="X",
        grade="D", grading_background="bg",
    )
    assert row.sheet == "TCU(TransmissionControlUnit)"
    assert row.dtc == "P0AC200"


def test_row_fields():
    row = Row(
        system="AT,CVT,AMT,IMT,DCT", dtc="P0AC200", description="desc",
        warning_light="X", warning_message="X", limp_home="X", fail_safe="X",
        grade="D", grading_background="bg", sheet="TCU(TransmissionControlUnit)",
    )
    assert row.system == "AT,CVT,AMT,IMT,DCT"
    assert row.sheet == "TCU(TransmissionControlUnit)"
```

- [ ] **Step 7: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dtc_transform.models'`

- [ ] **Step 8: models.py 구현**

`source/dtc_transform/models.py`:
```python
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
```

- [ ] **Step 9: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_models.py -v`
Expected: PASS (2 passed)

- [ ] **Step 10: Commit**

```bash
git add source/conftest.py source/dtc_transform/__init__.py source/dtc_transform/constants.py source/dtc_transform/models.py source/tests/test_constants.py source/tests/test_models.py
git commit -m "feat: add project scaffolding, constants, and row models"
```

---

### Task 2: 줄 재조립 (reconstruct.py)

**Files:**
- Create: `source/dtc_transform/reconstruct.py`
- Test: `source/tests/test_reconstruct.py`

**Interfaces:**
- Consumes: `DTC_PATTERN` (from `dtc_transform.constants`), `RawRow` (from `dtc_transform.models`)
- Produces: `reconstruct_rows(lines: list[str]) -> tuple[list[RawRow], list[str]]` — 두 번째 반환값은 선행 레코드 없이 등장한 복구 불가 조각 줄(orphan) 목록

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_reconstruct.py`:
```python
from dtc_transform.reconstruct import reconstruct_rows


def test_reconstructs_clean_9_field_lines():
    lines = [
        "4WD(4WheelDrive)\tP060241\tControl Module Programming Error\tX\tX\tX\tX\tD\t(no information)",
        "4WD(4WheelDrive)\tP172546\tEEPROM checksum fault\tO\tX\tX\tAWD not working\tC\tWarning lights being turned on / Drivable",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == []
    assert len(rows) == 2
    assert rows[0].sheet == "4WD(4WheelDrive)"
    assert rows[0].dtc == "P060241"
    assert rows[0].grade == "D"
    assert rows[1].dtc == "P172546"
    assert rows[1].grading_background == "Warning lights being turned on / Drivable"


def test_rejoins_line_broken_by_embedded_newline():
    lines = [
        "VPC(VehiclePlatformController)\tC110117\tBattery Voltage High\tX\tX\tX\tLimited operation of some functions\tC\tDrivable / CDCU system operation abnormality",
        "When the 12V battery voltage or the 12V battery charging voltage",
        "is out of range, DTC will be generated",
        "VPC(VehiclePlatformController)\tC110216\tBattery Voltage Low\tX\tX\tX\tLimited operation of some functions\tC\tDrivable / CDCU system operation abnormality",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == []
    assert len(rows) == 2
    assert rows[0].dtc == "C110117"
    assert rows[0].grading_background == (
        "Drivable / CDCU system operation abnormality "
        "When the 12V battery voltage or the 12V battery charging voltage "
        "is out of range, DTC will be generated"
    )
    assert rows[1].dtc == "C110216"


def test_leading_orphan_line_with_no_preceding_record_is_reported():
    lines = [
        "(in case of breakdown, staying display off)",
        "4WD(4WheelDrive)\tP060241\tControl Module Programming Error\tX\tX\tX\tX\tD\t(no information)",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == ["(in case of breakdown, staying display off)"]
    assert len(rows) == 1
    assert rows[0].dtc == "P060241"


def test_line_with_extra_tab_in_last_field_is_normalized():
    lines = [
        "ABSESP(Anti-lockBrakingSystem)\tC110913\tIG1 Open\tX\tX\tX\tLimited operation\tD\tsome\tbackground\ttext",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert orphans == []
    assert len(rows) == 1
    assert rows[0].grade == "D"
    assert rows[0].grading_background == "some\tbackground\ttext"


def test_blank_lines_are_skipped():
    lines = [
        "",
        "4WD(4WheelDrive)\tP060241\tControl Module Programming Error\tX\tX\tX\tX\tD\t(no information)",
        "",
    ]
    rows, orphans = reconstruct_rows(lines)
    assert len(rows) == 1
    assert orphans == []
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_reconstruct.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dtc_transform.reconstruct'`

- [ ] **Step 3: reconstruct.py 구현**

`source/dtc_transform/reconstruct.py`:
```python
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
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_reconstruct.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add source/dtc_transform/reconstruct.py source/tests/test_reconstruct.py
git commit -m "feat: reconstruct multi-line-broken raw DTC export rows"
```

---

### Task 3: 등급 고정 치환 (crypto.py)

**Files:**
- Create: `source/dtc_transform/crypto.py`
- Test: `source/tests/test_crypto.py`

**Interfaces:**
- Produces: `GRADE_CIPHER: dict[str, str]`, `InvalidGradeError(Exception)`, `encrypt_grade(grade: str) -> str`

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_crypto.py`:
```python
import pytest

from dtc_transform.crypto import InvalidGradeError, encrypt_grade


def test_encrypts_known_grades():
    assert encrypt_grade("A") == "GSwsyYvDA+tNLWnROM9rCg=="
    assert encrypt_grade("B") == "4CDbt0Ai5c3St5tcEQKANA=="
    assert encrypt_grade("C") == "Loxt0sBGAIWprCbYyMZIFw=="
    assert encrypt_grade("D") == "AVX59pdiJ/jHbW3BIX/SMg=="


def test_raises_on_unknown_grade():
    with pytest.raises(InvalidGradeError):
        encrypt_grade("E")


def test_raises_on_empty_grade():
    with pytest.raises(InvalidGradeError):
        encrypt_grade("")
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_crypto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dtc_transform.crypto'`

- [ ] **Step 3: crypto.py 구현**

`source/dtc_transform/crypto.py`:
```python
GRADE_CIPHER = {
    "A": "GSwsyYvDA+tNLWnROM9rCg==",
    "B": "4CDbt0Ai5c3St5tcEQKANA==",
    "C": "Loxt0sBGAIWprCbYyMZIFw==",
    "D": "AVX59pdiJ/jHbW3BIX/SMg==",
}


class InvalidGradeError(Exception):
    pass


def encrypt_grade(grade: str) -> str:
    try:
        return GRADE_CIPHER[grade]
    except KeyError:
        raise InvalidGradeError(f"Unknown grade: {grade!r}") from None
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_crypto.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add source/dtc_transform/crypto.py source/tests/test_crypto.py
git commit -m "feat: add fixed-substitution grade encryption"
```

---

### Task 4: 2단계 중복 제거 (dedup.py)

**Files:**
- Create: `source/dtc_transform/dedup.py`
- Test: `source/tests/test_dedup.py`

**Interfaces:**
- Consumes: `GRADE_SEVERITY` (from `dtc_transform.constants`), `Row` (from `dtc_transform.models`)
- Produces: `dedup(rows: list[Row]) -> list[Row]`

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_dedup.py`:
```python
from dtc_transform.dedup import dedup
from dtc_transform.models import Row


def make_row(system="SYS", dtc="P000000", grade="D", description="desc"):
    return Row(
        system=system, dtc=dtc, description=description, warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade=grade,
        grading_background="bg", sheet="Sheet",
    )


def test_same_system_dtc_grade_different_description_keeps_first():
    rows = [
        make_row(description="Control Unit Supply Voltage Open Circuit"),
        make_row(description="Open Unit Supply Voltage Open Circuit"),
    ]
    result = dedup(rows)
    assert len(result) == 1
    assert result[0].description == "Control Unit Supply Voltage Open Circuit"


def test_same_system_dtc_different_grade_keeps_more_severe():
    rows = [make_row(grade="C"), make_row(grade="D")]
    result = dedup(rows)
    assert len(result) == 1
    assert result[0].grade == "C"


def test_a_beats_all_other_grades():
    rows = [make_row(grade="D"), make_row(grade="B"), make_row(grade="A"), make_row(grade="C")]
    result = dedup(rows)
    assert len(result) == 1
    assert result[0].grade == "A"


def test_different_system_or_dtc_are_kept_separate():
    rows = [
        make_row(system="SYS1", dtc="P000000"),
        make_row(system="SYS2", dtc="P000000"),
        make_row(system="SYS1", dtc="P111111"),
    ]
    result = dedup(rows)
    assert len(result) == 3


def test_empty_input_returns_empty_list():
    assert dedup([]) == []
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_dedup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dtc_transform.dedup'`

- [ ] **Step 3: dedup.py 구현**

`source/dtc_transform/dedup.py`:
```python
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
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_dedup.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add source/dtc_transform/dedup.py source/tests/test_dedup.py
git commit -m "feat: implement two-stage grade-priority deduplication"
```

---

### Task 5: '00' 축약 코드 확장 (expand.py)

**Files:**
- Create: `source/dtc_transform/expand.py`
- Test: `source/tests/test_expand.py`

**Interfaces:**
- Consumes: `GRADE_SEVERITY` (from `dtc_transform.constants`), `Row` (from `dtc_transform.models`)
- Produces: `expand_trailing_zeros(rows: list[Row]) -> list[Row]`

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_expand.py`:
```python
from dtc_transform.expand import expand_trailing_zeros
from dtc_transform.models import Row


def make_row(system="SYS", dtc="P0AC200", grade="D"):
    return Row(
        system=system, dtc=dtc, description="desc", warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade=grade,
        grading_background="bg", sheet="Sheet",
    )


def test_adds_shortened_row_for_trailing_00():
    rows = [make_row(dtc="P0AC200")]
    result = expand_trailing_zeros(rows)
    dtcs = sorted(r.dtc for r in result)
    assert dtcs == ["P0AC2", "P0AC200"]


def test_shortened_row_copies_other_fields():
    rows = [make_row(dtc="P0AC200", grade="C")]
    result = expand_trailing_zeros(rows)
    short = next(r for r in result if r.dtc == "P0AC2")
    assert short.system == "SYS"
    assert short.grade == "C"
    assert short.description == "desc"


def test_does_not_expand_dtc_not_ending_in_00():
    rows = [make_row(dtc="P0AC201")]
    result = expand_trailing_zeros(rows)
    assert len(result) == 1
    assert result[0].dtc == "P0AC201"


def test_collision_with_existing_short_code_keeps_more_severe_grade():
    rows = [make_row(dtc="P0AC200", grade="D"), make_row(dtc="P0AC2", grade="B")]
    result = expand_trailing_zeros(rows)
    assert len(result) == 2
    short = next(r for r in result if r.dtc == "P0AC2")
    assert short.grade == "B"


def test_collision_where_expanded_row_is_more_severe_wins():
    rows = [make_row(dtc="P0AC200", grade="A"), make_row(dtc="P0AC2", grade="D")]
    result = expand_trailing_zeros(rows)
    short = next(r for r in result if r.dtc == "P0AC2")
    assert short.grade == "A"


def test_different_systems_expand_independently():
    rows = [make_row(system="SYS1", dtc="P0AC200"), make_row(system="SYS2", dtc="P0AC200")]
    result = expand_trailing_zeros(rows)
    assert len(result) == 4
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_expand.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dtc_transform.expand'`

- [ ] **Step 3: expand.py 구현**

`source/dtc_transform/expand.py`:
```python
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
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_expand.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add source/dtc_transform/expand.py source/tests/test_expand.py
git commit -m "feat: expand trailing-00 DTC codes into shortened rows"
```

---

### Task 6: sqlite 출력 (db_writer.py)

**Files:**
- Create: `source/dtc_transform/db_writer.py`
- Test: `source/tests/test_db_writer.py`

**Interfaces:**
- Consumes: `Row` (from `dtc_transform.models`), `encrypt_grade` (from `dtc_transform.crypto`)
- Produces: `write_sqlite(rows: list[Row], output_path: str) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_db_writer.py`:
```python
import sqlite3

from dtc_transform.db_writer import write_sqlite
from dtc_transform.models import Row


def make_row(system, dtc, grade="D"):
    return Row(
        system=system, dtc=dtc, description="desc", warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade=grade,
        grading_background="bg", sheet="Sheet",
    )


def test_writes_expected_schema_and_rows(tmp_path):
    output = tmp_path / "out.sqlite"
    rows = [make_row("SYS2", "P000001", grade="B"), make_row("SYS1", "P000002", grade="A")]

    write_sqlite(rows, str(output))

    con = sqlite3.connect(str(output))
    cur = con.cursor()
    cur.execute('PRAGMA table_info(dtc_master)')
    columns = [c[1] for c in cur.fetchall()]
    assert columns == [
        "No", "System", "DTC", "Description", "Warning_Light",
        "Warning_Message", "Limp_Home", "Fail_Safe", "DTC Class",
    ]

    cur.execute('SELECT "No", System, DTC, "DTC Class" FROM dtc_master ORDER BY "No"')
    result = cur.fetchall()
    con.close()

    assert result == [
        (1, "SYS1", "P000002", "GSwsyYvDA+tNLWnROM9rCg=="),
        (2, "SYS2", "P000001", "4CDbt0Ai5c3St5tcEQKANA=="),
    ]


def test_overwrites_existing_table(tmp_path):
    output = tmp_path / "out.sqlite"
    write_sqlite([make_row("SYS1", "P000001")], str(output))
    write_sqlite([make_row("SYS2", "P000002")], str(output))

    con = sqlite3.connect(str(output))
    cur = con.cursor()
    cur.execute('SELECT COUNT(*) FROM dtc_master')
    count = cur.fetchone()[0]
    con.close()

    assert count == 1
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_db_writer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dtc_transform.db_writer'`

- [ ] **Step 3: db_writer.py 구현**

`source/dtc_transform/db_writer.py`:
```python
import sqlite3

from .crypto import encrypt_grade
from .models import Row

SCHEMA = """
CREATE TABLE "dtc_master" (
    "No" INTEGER,
    "System" TEXT,
    "DTC" TEXT,
    "Description" TEXT,
    "Warning_Light" TEXT,
    "Warning_Message" TEXT,
    "Limp_Home" TEXT,
    "Fail_Safe" TEXT,
    "DTC Class" TEXT
)
"""


def write_sqlite(rows: list[Row], output_path: str) -> None:
    sorted_rows = sorted(rows, key=lambda r: (r.system, r.dtc))

    con = sqlite3.connect(output_path)
    try:
        cur = con.cursor()
        cur.execute("DROP TABLE IF EXISTS dtc_master")
        cur.execute(SCHEMA)
        for i, row in enumerate(sorted_rows, start=1):
            cur.execute(
                'INSERT INTO dtc_master VALUES (?,?,?,?,?,?,?,?,?)',
                (
                    i,
                    row.system,
                    row.dtc,
                    row.description,
                    row.warning_light,
                    row.warning_message,
                    row.limp_home,
                    row.fail_safe,
                    encrypt_grade(row.grade),
                ),
            )
        con.commit()
    finally:
        con.close()
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_db_writer.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add source/dtc_transform/db_writer.py source/tests/test_db_writer.py
git commit -m "feat: write final rows to sqlite matching reference schema"
```

---

### Task 7: 시트→System 매핑 도출 도구 (tools/derive_mapping.py)

**Files:**
- Create: `source/tools/__init__.py`
- Create: `source/tools/derive_mapping.py`
- Test: `source/tests/test_derive_mapping.py`
- Create (generated artifact, not hand-written): `source/config/sheet_system_mapping.json`

**Interfaces:**
- Consumes: `RawRow` (from `dtc_transform.models`), `reconstruct_rows` (from `dtc_transform.reconstruct`)
- Produces: `derive_mapping(raw_rows: list[RawRow], reference_rows: list[tuple[str, str, str]]) -> dict[str, dict]` — `reference_rows`는 `(dtc, description, system)` 튜플 목록. 반환값은 `{sheet: {"system": str, "confidence": float, "hits": int}}`

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_derive_mapping.py`:
```python
from dtc_transform.models import RawRow
from tools.derive_mapping import derive_mapping


def make_raw(sheet, dtc, description="desc"):
    return RawRow(
        sheet=sheet, dtc=dtc, description=description, warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade="D",
        grading_background="bg",
    )


def test_picks_majority_system_for_each_sheet():
    raw_rows = [
        make_raw("TCU(TransmissionControlUnit)", "P060241", "err a"),
        make_raw("TCU(TransmissionControlUnit)", "P060247", "err b"),
        make_raw("TCU(TransmissionControlUnit)", "P172546", "err c"),
    ]
    # (dtc, description, system) as found in the reference sqlite
    reference_rows = [
        ("P060241", "err a", "AT,CVT,AMT,IMT,DCT"),
        ("P060247", "err b", "AT,CVT,AMT,IMT,DCT"),
        ("P172546", "err c", "ENGINE"),  # generic code shared with another controller
    ]

    result = derive_mapping(raw_rows, reference_rows)

    assert result["TCU(TransmissionControlUnit)"]["system"] == "AT,CVT,AMT,IMT,DCT"
    assert result["TCU(TransmissionControlUnit)"]["hits"] == 3
    assert round(result["TCU(TransmissionControlUnit)"]["confidence"], 2) == 0.67


def test_sheet_with_no_reference_match_is_omitted():
    raw_rows = [make_raw("NEW_SHEET(NewController)", "P999999", "brand new")]
    reference_rows = [("P060241", "err a", "ENGINE")]

    result = derive_mapping(raw_rows, reference_rows)

    assert "NEW_SHEET(NewController)" not in result


def test_confidence_is_one_when_all_hits_agree():
    raw_rows = [make_raw("AVN(AudioVideoNavigation)", "P100000", "desc a")]
    reference_rows = [("P100000", "desc a", "AVN")]

    result = derive_mapping(raw_rows, reference_rows)

    assert result["AVN(AudioVideoNavigation)"]["confidence"] == 1.0
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_derive_mapping.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.derive_mapping'`

- [ ] **Step 3: derive_mapping.py 구현**

`source/tools/__init__.py`: (빈 파일)

`source/tools/derive_mapping.py`:
```python
import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict

from dtc_transform.models import RawRow
from dtc_transform.reconstruct import reconstruct_rows


def derive_mapping(
    raw_rows: list[RawRow], reference_rows: list[tuple[str, str, str]]
) -> dict[str, dict]:
    key_to_systems: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for dtc, description, system in reference_rows:
        key_to_systems[(dtc.upper(), description.strip())][system] += 1

    sheet_hits: dict[str, Counter] = defaultdict(Counter)
    for row in raw_rows:
        systems = key_to_systems.get((row.dtc, row.description))
        if not systems:
            continue
        for system, count in systems.items():
            sheet_hits[row.sheet][system] += count

    result = {}
    for sheet, counter in sheet_hits.items():
        total = sum(counter.values())
        top_system, top_count = counter.most_common(1)[0]
        result[sheet] = {
            "system": top_system,
            "confidence": top_count / total,
            "hits": total,
        }
    return result


def _load_reference_rows(reference_db_path: str) -> list[tuple[str, str, str]]:
    con = sqlite3.connect(reference_db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT DTC, Description, System FROM dtc_master")
        return cur.fetchall()
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive sheet-to-System mapping from a reference sqlite")
    parser.add_argument("--raw-input", required=True, help="Path to the raw tab-separated export")
    parser.add_argument("--reference-db", required=True, help="Path to the existing dtc_master sqlite")
    parser.add_argument("--output", required=True, help="Path to write config/sheet_system_mapping.json")
    parser.add_argument("--review-report", required=True, help="Path to write low-confidence sheets CSV")
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    args = parser.parse_args()

    with open(args.raw_input, encoding="utf-8", errors="replace") as f:
        raw_rows, _orphans = reconstruct_rows(f.readlines())

    reference_rows = _load_reference_rows(args.reference_db)
    mapping = derive_mapping(raw_rows, reference_rows)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2, sort_keys=True)

    with open(args.review_report, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sheet", "system", "confidence", "hits"])
        for sheet, entry in sorted(mapping.items()):
            if entry["confidence"] < args.confidence_threshold:
                writer.writerow([sheet, entry["system"], f"{entry['confidence']:.2f}", entry["hits"]])


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_derive_mapping.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 실제 데이터로 매핑 설정 파일 생성**

```bash
mkdir -p source/config
cd source && python -m tools.derive_mapping \
  --raw-input "../docs/260331_DTC Master_영문 (글로벌 지원) (1).txt" \
  --reference-db "../docs/dtc_master_km 3.sqlite" \
  --output config/sheet_system_mapping.json \
  --review-report config/sheet_system_mapping_review.csv
```

Expected: `source/config/sheet_system_mapping.json`에 93개 시트 항목이 생성되고, `source/config/sheet_system_mapping_review.csv`에 신뢰도 50% 미만인 약 49개 시트가 나열됨. `python -c "import json; d=json.load(open('source/config/sheet_system_mapping.json', encoding='utf-8')); print(len(d))"` 실행해 93이 출력되는지 확인.

- [ ] **Step 6: Commit**

```bash
git add source/tools/__init__.py source/tools/derive_mapping.py source/tests/test_derive_mapping.py source/config/sheet_system_mapping.json source/config/sheet_system_mapping_review.csv
git commit -m "feat: derive sheet-to-System mapping from reference sqlite"
```

---

### Task 8: 매핑 로더 + System 부착 (mapping.py)

**Files:**
- Create: `source/dtc_transform/mapping.py`
- Test: `source/tests/test_mapping.py`

**Interfaces:**
- Consumes: `RawRow`, `Row` (from `dtc_transform.models`)
- Produces: `SheetSystemMapping` class with `.load(path: str) -> SheetSystemMapping` classmethod, `.system_for(sheet: str) -> str | None`, `.low_confidence_sheets(threshold: float = 0.5) -> list[tuple[str, float]]`; `attach_system(raw_rows: list[RawRow], mapping: SheetSystemMapping) -> tuple[list[Row], list[str]]` (두 번째 반환값은 매핑에 없는 시트명 목록, 중복 제거된 정렬 리스트)

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_mapping.py`:
```python
import json

from dtc_transform.mapping import SheetSystemMapping, attach_system
from dtc_transform.models import RawRow


def make_raw(sheet, dtc="P000001"):
    return RawRow(
        sheet=sheet, dtc=dtc, description="desc", warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade="D",
        grading_background="bg",
    )


def test_load_reads_json_mapping(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(
        json.dumps({"TCU(TransmissionControlUnit)": {"system": "AT,CVT,AMT,IMT,DCT", "confidence": 0.85, "hits": 475}}),
        encoding="utf-8",
    )

    mapping = SheetSystemMapping.load(str(path))

    assert mapping.system_for("TCU(TransmissionControlUnit)") == "AT,CVT,AMT,IMT,DCT"
    assert mapping.system_for("UNKNOWN_SHEET") is None


def test_low_confidence_sheets_returns_entries_below_threshold(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(
        json.dumps(
            {
                "A": {"system": "SYS_A", "confidence": 0.9, "hits": 10},
                "B": {"system": "SYS_B", "confidence": 0.3, "hits": 5},
            }
        ),
        encoding="utf-8",
    )

    mapping = SheetSystemMapping.load(str(path))

    low = mapping.low_confidence_sheets(threshold=0.5)
    assert low == [("B", 0.3)]


def test_attach_system_fills_known_sheets_and_reports_unmapped(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(
        json.dumps({"KNOWN(Sheet)": {"system": "SYS1", "confidence": 1.0, "hits": 1}}),
        encoding="utf-8",
    )
    mapping = SheetSystemMapping.load(str(path))
    raw_rows = [make_raw("KNOWN(Sheet)"), make_raw("UNKNOWN(Sheet)")]

    rows, unmapped = attach_system(raw_rows, mapping)

    by_sheet = {r.sheet: r for r in rows}
    assert by_sheet["KNOWN(Sheet)"].system == "SYS1"
    assert by_sheet["UNKNOWN(Sheet)"].system == ""
    assert unmapped == ["UNKNOWN(Sheet)"]
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_mapping.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dtc_transform.mapping'`

- [ ] **Step 3: mapping.py 구현**

`source/dtc_transform/mapping.py`:
```python
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
            if entry.get("confidence", 1.0) < threshold
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
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_mapping.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add source/dtc_transform/mapping.py source/tests/test_mapping.py
git commit -m "feat: load sheet-to-System mapping and attach system to rows"
```

---

### Task 9: 파이프라인 CLI + 실행 리포트 (pipeline.py)

**Files:**
- Create: `source/dtc_transform/pipeline.py`
- Test: `source/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `reconstruct_rows`, `SheetSystemMapping`, `attach_system`, `dedup`, `expand_trailing_zeros`, `write_sqlite` (모두 이전 태스크에서 정의)
- Produces: `run_pipeline(input_path: str, mapping_path: str, output_path: str, report_path: str) -> dict` (반환값은 리포트에 쓰인 것과 동일한 통계 dict), `main()` CLI 진입점

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_pipeline.py`:
```python
import json
import sqlite3

from dtc_transform.pipeline import run_pipeline


def test_end_to_end_pipeline(tmp_path):
    input_path = tmp_path / "input.txt"
    input_path.write_text(
        "\n".join(
            [
                "TCU(TransmissionControlUnit)\tP0AC200\tDesc A\tX\tX\tX\tX\tD\tbg",
                "TCU(TransmissionControlUnit)\tP0AC200\tDesc A duplicate\tX\tX\tX\tX\tD\tbg",
                "TCU(TransmissionControlUnit)\tP0AC200\tDesc A\tX\tX\tX\tX\tB\tbg",
                "UNKNOWN(Sheet)\tP111111\tUnmapped desc\tX\tX\tX\tX\tC\tbg",
            ]
        ),
        encoding="utf-8",
    )

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps({"TCU(TransmissionControlUnit)": {"system": "AT,CVT,AMT,IMT,DCT", "confidence": 0.85, "hits": 3}}),
        encoding="utf-8",
    )

    output_path = tmp_path / "out.sqlite"
    report_path = tmp_path / "report.txt"

    stats = run_pipeline(
        input_path=str(input_path),
        mapping_path=str(mapping_path),
        output_path=str(output_path),
        report_path=str(report_path),
    )

    assert stats["raw_row_count"] == 4
    assert stats["after_dedup_count"] == 2  # TCU/P0AC200 (B wins over D) + UNKNOWN/P111111
    assert stats["after_expand_count"] == 3  # + TCU/P0AC2 shortened row
    assert stats["unmapped_sheets"] == ["UNKNOWN(Sheet)"]

    con = sqlite3.connect(str(output_path))
    cur = con.cursor()
    cur.execute('SELECT System, DTC, "DTC Class" FROM dtc_master ORDER BY System, DTC')
    rows = cur.fetchall()
    con.close()

    assert rows == [
        ("", "P111111", "Loxt0sBGAIWprCbYyMZIFw=="),
        ("AT,CVT,AMT,IMT,DCT", "P0AC2", "4CDbt0Ai5c3St5tcEQKANA=="),
        ("AT,CVT,AMT,IMT,DCT", "P0AC200", "4CDbt0Ai5c3St5tcEQKANA=="),
    ]

    report_text = report_path.read_text(encoding="utf-8")
    assert "UNKNOWN(Sheet)" in report_text
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dtc_transform.pipeline'`

- [ ] **Step 3: pipeline.py 구현**

`source/dtc_transform/pipeline.py`:
```python
import argparse

from .dedup import dedup
from .expand import expand_trailing_zeros
from .db_writer import write_sqlite
from .mapping import SheetSystemMapping, attach_system
from .reconstruct import reconstruct_rows


def run_pipeline(input_path: str, mapping_path: str, output_path: str, report_path: str) -> dict:
    with open(input_path, encoding="utf-8", errors="replace") as f:
        raw_rows, orphans = reconstruct_rows(f.readlines())

    mapping = SheetSystemMapping.load(mapping_path)
    rows, unmapped_sheets = attach_system(raw_rows, mapping)

    deduped = dedup(rows)
    expanded = expand_trailing_zeros(deduped)

    write_sqlite(expanded, output_path)

    low_confidence = mapping.low_confidence_sheets(threshold=0.5)

    stats = {
        "raw_row_count": len(raw_rows),
        "unrecoverable_orphan_lines": len(orphans),
        "after_dedup_count": len(deduped),
        "after_expand_count": len(expanded),
        "unmapped_sheets": unmapped_sheets,
        "low_confidence_sheets": low_confidence,
    }

    _write_report(report_path, stats, orphans)
    return stats


def _write_report(report_path: str, stats: dict, orphans: list[str]) -> None:
    lines = [
        f"raw_row_count: {stats['raw_row_count']}",
        f"unrecoverable_orphan_lines: {stats['unrecoverable_orphan_lines']}",
        f"after_dedup_count: {stats['after_dedup_count']}",
        f"after_expand_count: {stats['after_expand_count']}",
        "",
        "unmapped_sheets:",
        *[f"  - {sheet}" for sheet in stats["unmapped_sheets"]],
        "",
        "low_confidence_sheets (<50%):",
        *[f"  - {sheet}: {confidence:.0%}" for sheet, confidence in stats["low_confidence_sheets"]],
        "",
        "orphan_lines:",
        *[f"  - {line}" for line in orphans],
    ]
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Transform raw DTC master export into sqlite")
    parser.add_argument("--input", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    stats = run_pipeline(
        input_path=args.input,
        mapping_path=args.mapping,
        output_path=args.output,
        report_path=args.report,
    )
    print(f"raw={stats['raw_row_count']} dedup={stats['after_dedup_count']} "
          f"expanded={stats['after_expand_count']} "
          f"unmapped={len(stats['unmapped_sheets'])}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_pipeline.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 전체 테스트 스위트 실행**

Run: `cd source && python -m pytest tests/ -v`
Expected: 모든 테스트 PASS (약 23개)

- [ ] **Step 6: 실제 데이터로 수동 검증 실행**

```bash
cd source && python -m dtc_transform.pipeline \
  --input "../docs/260331_DTC Master_영문 (글로벌 지원) (1).txt" \
  --mapping config/sheet_system_mapping.json \
  --output "../docs/dtc_master_km_output.sqlite" \
  --report "../docs/dtc_master_run_report.txt"
```

콘솔 출력의 행 수(raw/dedup/expanded)와 `docs/dtc_master_run_report.txt`의 미매핑 시트·저신뢰도 시트 목록을 확인하고, 결과 `docs/dtc_master_km_output.sqlite`를 기존 `docs/dtc_master_km 3.sqlite`와 행 수·샘플 몇 건(예: TCU/P0AC2, VPC 관련 행)을 비교해 규칙이 기대대로 반영됐는지 육안 확인한다. 이 단계는 자동화된 테스트가 아니라 사람이 확인하는 검증 단계다.

- [ ] **Step 7: Commit**

```bash
git add source/dtc_transform/pipeline.py source/tests/test_pipeline.py
git commit -m "feat: add end-to-end pipeline CLI with run report"
```

---

### Task 10: n8n 워크플로우 (import 가능한 JSON)

**Files:**
- Create: `source/n8n/dtc_master_workflow.json`
- Test: `source/tests/test_n8n_workflow.py`

**Interfaces:**
- 이 태스크는 별도 파이썬 인터페이스를 만들지 않는다. n8n이 import할 JSON 파일 하나가 산출물이다.

- [ ] **Step 1: 실패하는 테스트 작성 (JSON 유효성 + 필수 노드 존재)**

`source/tests/test_n8n_workflow.py`:
```python
import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / "n8n" / "dtc_master_workflow.json"


def test_workflow_file_is_valid_json():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert "nodes" in data
    assert "connections" in data


def test_workflow_has_required_nodes():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    node_types = {node["type"] for node in data["nodes"]}
    assert "n8n-nodes-base.localFileTrigger" in node_types
    assert "n8n-nodes-base.executeCommand" in node_types
    assert "n8n-nodes-base.if" in node_types


def test_execute_command_node_calls_pipeline_module():
    data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    exec_nodes = [n for n in data["nodes"] if n["type"] == "n8n-nodes-base.executeCommand"]
    assert exec_nodes, "no executeCommand node found"
    commands = " ".join(n["parameters"].get("command", "") for n in exec_nodes)
    assert "dtc_transform.pipeline" in commands
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_n8n_workflow.py -v`
Expected: FAIL with `FileNotFoundError`

- [ ] **Step 3: n8n 워크플로우 JSON 작성**

`source/n8n/dtc_master_workflow.json`:
```json
{
  "name": "DTC Master Excel to SQLite",
  "nodes": [
    {
      "parameters": {
        "triggerOn": "folder",
        "path": "/data/dtc_master/incoming",
        "events": ["add", "change"]
      },
      "id": "1",
      "name": "Watch Incoming Folder",
      "type": "n8n-nodes-base.localFileTrigger",
      "typeVersion": 1,
      "position": [240, 300]
    },
    {
      "parameters": {
        "command": "cd /data/dtc_master/source && python -m dtc_transform.pipeline --input \"{{$json[\"path\"]}}\" --mapping config/sheet_system_mapping.json --output /data/dtc_master/output/dtc_master_km.sqlite --report /data/dtc_master/output/run_report.txt"
      },
      "id": "2",
      "name": "Run Transform Pipeline",
      "type": "n8n-nodes-base.executeCommand",
      "typeVersion": 1,
      "position": [460, 300]
    },
    {
      "parameters": {
        "conditions": {
          "number": [
            {
              "value1": "={{$json[\"exitCode\"]}}",
              "operation": "equal",
              "value2": 0
            }
          ]
        }
      },
      "id": "3",
      "name": "Succeeded?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 1,
      "position": [680, 300]
    },
    {
      "parameters": {
        "command": "cp /data/dtc_master/output/dtc_master_km.sqlite /data/dtc_master/publish/dtc_master_km.sqlite"
      },
      "id": "4",
      "name": "Publish Output",
      "type": "n8n-nodes-base.executeCommand",
      "typeVersion": 1,
      "position": [900, 200]
    },
    {
      "parameters": {
        "fromEmail": "dtc-pipeline@example.com",
        "toEmail": "dtc-pipeline-owners@example.com",
        "subject": "DTC Master 변환 완료",
        "text": "={{$node[\"Run Transform Pipeline\"].json[\"stdout\"]}}",
        "options": {
          "attachments": "/data/dtc_master/output/run_report.txt"
        }
      },
      "id": "5",
      "name": "Notify Success",
      "type": "n8n-nodes-base.emailSend",
      "typeVersion": 1,
      "position": [1120, 200]
    },
    {
      "parameters": {
        "fromEmail": "dtc-pipeline@example.com",
        "toEmail": "dtc-pipeline-owners@example.com",
        "subject": "DTC Master 변환 실패",
        "text": "={{$node[\"Run Transform Pipeline\"].json[\"stderr\"]}}"
      },
      "id": "6",
      "name": "Notify Failure",
      "type": "n8n-nodes-base.emailSend",
      "typeVersion": 1,
      "position": [900, 400]
    }
  ],
  "connections": {
    "Watch Incoming Folder": {
      "main": [[{ "node": "Run Transform Pipeline", "type": "main", "index": 0 }]]
    },
    "Run Transform Pipeline": {
      "main": [[{ "node": "Succeeded?", "type": "main", "index": 0 }]]
    },
    "Succeeded?": {
      "main": [
        [{ "node": "Publish Output", "type": "main", "index": 0 }],
        [{ "node": "Notify Failure", "type": "main", "index": 0 }]
      ]
    },
    "Publish Output": {
      "main": [[{ "node": "Notify Success", "type": "main", "index": 0 }]]
    }
  }
}
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_n8n_workflow.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 경로/이메일 값을 실제 환경에 맞게 안내하는 README 작성**

`source/n8n/README.md`:
```markdown
# DTC Master n8n 워크플로우 import 가이드

1. n8n 관리 화면에서 Workflows > Import from File로 `dtc_master_workflow.json`을 불러온다.
2. 아래 값을 실제 환경에 맞게 수정한다:
   - `Watch Incoming Folder` 노드의 `path`: 원본 txt가 놓일 로컬(또는 SharePoint 동기화) 폴더 경로
   - `Run Transform Pipeline` 노드의 `command`: `cd` 뒤 경로를 이 리포지토리의 `source/` 실제 배포 경로로 수정, `--output`/`--report` 경로도 배포 환경에 맞게 수정
   - `Publish Output` 노드의 복사 대상 경로
   - `Notify Success`/`Notify Failure` 노드: 이메일 발신/수신 주소, 그리고 n8n에 등록된 SMTP credential 연결
3. 각 노드를 저장하면 credential 설정을 요구하는 노드(이메일)는 n8n에서 별도로 SMTP credential을 만들어 연결해야 한다 — 이는 워크플로우 파일 자체에는 포함될 수 없는 값이다.
4. 테스트 실행: `Watch Incoming Folder`가 감시하는 폴더에 샘플 txt 파일을 넣어 전체 플로우가 끝까지 실행되는지 확인한다.
```

- [ ] **Step 6: Commit**

```bash
git add source/n8n/dtc_master_workflow.json source/n8n/README.md source/tests/test_n8n_workflow.py
git commit -m "feat: add importable n8n workflow for the DTC master pipeline"
```

---

## 사후 보정 (Task 9 실데이터 검증 중 발견, 2026-09-04)

Task 9의 실데이터 수동 검증에서 파이프라인이 크래시했다. 원인 조사 결과 두 가지 이슈가 발견되어 아래 두 작업을 추가한다. 스펙 문서(`docs/superpowers/specs/2026-09-04-dtc-master-pipeline-design.md`)의 "입력 데이터 형식"/"1단계"/"4.5단계" 섹션이 이미 갱신되었다.

### Task 2-Fix: reconstruct.py를 csv 모듈 기반으로 재구현

**Files:**
- Modify: `source/dtc_transform/reconstruct.py`
- Modify: `source/tests/test_reconstruct.py` (기존 6개 테스트를 실제 데이터의 인용 규칙에 맞게 재작성)

**배경**: 실데이터는 셀 내부 개행/따옴표가 있는 필드를 표준 CSV 인용 규칙(`"..."`)으로 감싼다. 기존 커스텀 휴리스틱(DTC 패턴으로 새 레코드 시작을 감지하고, 나머지는 마지막 필드에 이어붙임)은 셀 내부에 **탭 문자와 따옴표가 함께 있는 경우**(예: Fail_Safe 컬럼이 `"Warning lights being turned on"`처럼 따옴표로 감싸진 경우)를 처리하지 못해, 293개 라인에서 Grade/Fail_Safe 컬럼이 뒤섞이는 오염이 발생했다.

**실측 예시 (그대로 재현 가능)**:
```
ABSESP(Anti-lockBrakingSystem)	C110101	Battery Voltage High	O	O	X	"	Warning lights being turned on"	C	Delete when vehicle voltage condition is restored / Expected high frequency of occurrence
```
이 줄은 실제로는 Fail_Safe 컬럼 값이 `Warning lights being turned on`(따옴표로 감싸짐)이고 그 다음 Grade가 `C`여야 하는데, 기존 로직은 Grade를 `Warning lights being turned on"`으로, GradingBackground를 `C\tDelete when...`으로 잘못 파싱한다.

**실데이터 개행-분리 예시 (인용 규칙 확인용, 실제 파일 2397~2399번째 줄 그대로 — 3개 물리적 줄에 걸쳐 있음, 가운데 줄을 누락하지 말 것)**:
```
DSM(DigitalSideMirror)	B162100	ECU hardware Error	O	O	X	"모니터/카메라 자체 Reset(영구 고장시 Display OFF 상태 유지)
Try to reset Monitor/Camera
(in case of breakdown, staying display off)"	C	Drivable / Warning lights being turned on / Warning messages is displayed
```

- [ ] **Step 1**: `source/tests/test_reconstruct.py`를 다음 실제 사례를 검증하도록 재작성한다 (합성 예제 대신 위 두 실측 사례를 그대로 사용):
  1. 위 "C110101" 예시를 파싱했을 때 `fail_safe == "Warning lights being turned on"`, `grade == "C"`, `grading_background == "Delete when vehicle voltage condition is restored / Expected high frequency of occurrence"`가 되는지
  2. 위 "B162100" 예시(3개 물리적 줄)를 파싱했을 때 `fail_safe`가 세 구간을 `\n`으로 이어붙인 하나의 문자열(`"모니터/카메라 자체 Reset(영구 고장시 Display OFF 상태 유지)\nTry to reset Monitor/Camera\n(in case of breakdown, staying display off)"`, 따옴표는 제거된 상태)이 되고 `grade == "C"`가 되는지
  3. 기존 6개 테스트 중 여전히 유효한 것(정상 9필드 라인, blank line skip, leading-orphan-no-preceding-record)은 유지하고, "extra tab in last field"처럼 실제로는 인용 규칙 위반이 아니었던 합성 테스트는 제거하거나 실제 인용 형태로 고친다.
- [ ] **Step 2**: 테스트 실행해서 실패 확인 (`cd source && python -m pytest tests/test_reconstruct.py -v`)
- [ ] **Step 3**: `reconstruct.py`를 `csv.reader(lines, delimiter="\t")` 기반으로 재작성한다. `RawRow`를 만들기 전 필드 1이 DTC_PATTERN에 매치하는지 검증해 orphan을 걸러내는 로직은 유지한다. 공개 인터페이스(`reconstruct_rows(lines) -> tuple[list[RawRow], list[str]]`)는 변경하지 않는다 — Task 7/8/9가 이미 이 시그니처에 의존한다.
- [ ] **Step 4**: 테스트 실행해서 통과 확인
- [ ] **Step 5**: 전체 스위트 실행해서 회귀 없는지 확인 (`cd source && python -m pytest tests/ -v`)
- [ ] **Step 6**: Commit (`fix: parse raw export with csv module to handle quoted tab/newline fields`)

### Task 9-Follow-up: 비A~D 등급 필터링 + 실데이터 재검증

**Files:**
- Create: `source/dtc_transform/grade_filter.py`
- Test: `source/tests/test_grade_filter.py`
- Modify: `source/dtc_transform/pipeline.py` (dedup 이후, expand 이전에 필터 삽입, stats/리포트에 제외 건수 추가)
- Modify: `source/tests/test_pipeline.py` (필터링이 파이프라인에 실제로 연결됐는지 검증하는 케이스 추가)

**배경**: 2026-09-04 사용자 승인 — Grade가 `{A,B,C,D}`가 아닌 행(실측: E/-/공백 등)은 최종 출력에서 완전히 제외한다.

- [ ] **Step 1**: 실패하는 테스트 작성 — `source/tests/test_grade_filter.py`에 `filter_invalid_grades(rows: list[Row]) -> tuple[list[Row], list[Row]]` (첫 번째: 유효한 행, 두 번째: 제외된 행)에 대해 (a) A/B/C/D는 모두 통과, (b) `"E"`, `"-"`, `""`는 모두 제외, (c) 빈 리스트 입력 시 빈 결과.
- [ ] **Step 2**: 테스트 실패 확인
- [ ] **Step 3**: `source/dtc_transform/grade_filter.py` 구현 (기존 `dtc_transform.constants`의 유효 등급 집합 `{"A","B","C","D"}`를 재사용 — `GRADE_SEVERITY.keys()`로 참조해 이중 관리 방지).
- [ ] **Step 4**: 테스트 통과 확인
- [ ] **Step 5**: `pipeline.py`의 `run_pipeline`에서 `dedup(...)` 다음, `expand_trailing_zeros(...)` 이전에 `filter_invalid_grades`를 호출하도록 연결. 반환된 stats 딕셔너리에 `excluded_invalid_grade_count: int`와 `excluded_invalid_grade_breakdown: dict[str,int]`(등급값별 건수)를 추가. `_write_report`에도 이 정보를 사람이 읽을 수 있는 형태로 추가.
- [ ] **Step 6**: `test_pipeline.py`의 기존 end-to-end 테스트에 A/B/C/D가 아닌 grade를 가진 raw row를 하나 추가해, 최종 sqlite에 해당 DTC가 나타나지 않고 `excluded_invalid_grade_count`에 반영되는지 검증하는 케이스를 추가.
- [ ] **Step 7**: 전체 스위트 실행
- [ ] **Step 8**: Commit (`feat: exclude non-A-D grade rows from pipeline output`)
- [ ] **Step 9**: (Task 2-Fix 완료 후) 실제 데이터로 재검증 — 절대경로 사용:
  ```
  cd source && python -m dtc_transform.pipeline \
    --input "C:\Users\GIT\git_ws\DTC_grade\docs\260331_DTC Master_영문 (글로벌 지원) (1).txt" \
    --mapping config/sheet_system_mapping.json \
    --output "C:\Users\GIT\git_ws\DTC_grade\docs\dtc_master_km_output.sqlite" \
    --report "C:\Users\GIT\git_ws\DTC_grade\docs\dtc_master_run_report.txt"
  ```
  이번에는 크래시 없이 끝까지 실행되어야 한다. 결과 sqlite의 행 수를 기존 `docs/dtc_master_km 3.sqlite`(10,987행)와 비교하고, TCU 예시(`AT,CVT,AMT,IMT,DCT`) 등 몇 건을 육안으로 대조한다.

## 최종 확인 (전체 계획 완료 후)

- [ ] `cd source && python -m pytest tests/ -v` 전체 통과 확인
- [ ] Task 9 Step 6의 실제 데이터 수동 검증 결과를 사용자에게 보고 (raw/dedup/expand 행 수, 미매핑 시트 목록, 저신뢰도 매핑 시트 목록)
- [ ] `source/config/sheet_system_mapping_review.csv`를 사용자에게 전달해 저신뢰도 시트(~15개, `<50%`) 수동 검토 요청
