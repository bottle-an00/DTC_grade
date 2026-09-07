# 사내 DB 기반 시트→System 매핑 생성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `config/sheet_system_mapping.json`을 통계적 confidence/hits 매칭이 아니라, 3개 사내 DB(ECU DOC, 진단 DB XML, vehicle_info XML)를 결정적으로 조인해 생성하는 새 도구를 만든다.

**Architecture:** 4개의 순수 데이터 소스 파서/인덱서(`dtc_transform/company_db/`)와, 이들을 조인해 최종 매핑+미해결 리포트를 만드는 CLI 오케스트레이터(`tools/build_system_mapping.py`) 하나로 구성한다. n8n Cloud가 저장소 파일을 못 읽는 기존 제약은 그대로이므로, 결과 JSON은 사람이 n8n `Attach System` 노드에 수동으로 붙여넣는다(코드 범위 밖).

**Tech Stack:** Python 표준 라이브러리만 사용 (`xml.etree.ElementTree`, `csv`, `json`, `os`) — 새 의존성 없음.

**Spec:** [`docs/superpowers/specs/2026-09-07-company-db-system-mapping-design.md`](../specs/2026-09-07-company-db-system-mapping-design.md)

## Global Constraints

- 비교코드 추출 규칙(전 모듈 공용): `code.split("_")`의 뒤에서 두 번째 토큰의 뒤 4자리.
- 진단 DB XML은 파일명(확장자 제외)의 마지막 2글자가 `D0` 또는 `A0`인 것만 대상 (대소문자 무시).
- 진단 DB XML은 루트 `<systemtree systemid="...">` 속성만 읽고 나머지 DOM은 파싱하지 않는다(20,845개 중 다수가 대용량 파일이므로 성능 필수 요건).
- 기존 `config/sheet_system_mapping.json`에 `"source": "manual"`로 표시된 항목은 이번 자동 생성으로 덮어쓰지 않는다.
- 새 의존성(pip 패키지) 추가하지 않는다 — 표준 라이브러리로 충분함.

---

## Task 1: 비교코드 추출 (`code_extract.py`)

**Files:**
- Create: `source/dtc_transform/company_db/__init__.py` (빈 파일)
- Create: `source/dtc_transform/company_db/code_extract.py`
- Test: `source/tests/test_company_db_code_extract.py`

**Interfaces:**
- Produces: `extract_compare_code(code: str) -> str` — 성공 시 4자리 문자열, 규칙에 안 맞으면 `ValueError` 발생. Task 2/3/4/5가 이 함수를 그대로 가져다 쓴다.

- [ ] **Step 1: 빈 패키지 파일 생성**

```bash
mkdir -p source/dtc_transform/company_db
touch source/dtc_transform/company_db/__init__.py
```

- [ ] **Step 2: 실패하는 테스트 작성**

`source/tests/test_company_db_code_extract.py`:

```python
import pytest

from dtc_transform.company_db.code_extract import extract_compare_code


def test_extracts_last_four_chars_of_second_to_last_token():
    assert extract_compare_code("TEST_2009_1006101_001") == "6101"


def test_works_with_a_short_second_to_last_token():
    assert extract_compare_code("92710100_ABC_D2O6_001") == "D2O6"


def test_raises_when_fewer_than_two_tokens():
    with pytest.raises(ValueError):
        extract_compare_code("NOTOKENS")


def test_raises_when_second_to_last_token_is_too_short():
    with pytest.raises(ValueError):
        extract_compare_code("A_12_001")
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_company_db_code_extract.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'dtc_transform.company_db'`)

- [ ] **Step 4: 최소 구현 작성**

`source/dtc_transform/company_db/code_extract.py`:

```python
def extract_compare_code(code: str) -> str:
    """Split on '_' and take the last 4 characters of the second-to-last
    token -- the shared rule for turning an ECU DOC document code or a
    diagnostic-DB systemid into a 4-character comparison key."""
    tokens = code.split("_")
    if len(tokens) < 2:
        raise ValueError(f"code has no second-to-last token: {code!r}")

    second_last = tokens[-2]
    if len(second_last) < 4:
        raise ValueError(f"second-to-last token too short: {code!r}")

    return second_last[-4:]
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_company_db_code_extract.py -v`
Expected: PASS (4개 테스트 전부)

- [ ] **Step 6: 커밋**

```bash
git add source/dtc_transform/company_db/__init__.py source/dtc_transform/company_db/code_extract.py source/tests/test_company_db_code_extract.py
git commit -m "feat: add shared compare-code extraction rule for company DB matching"
```

---

## Task 2: 진단 DB XML 인덱스 (`diagnostic_db.py`)

**Files:**
- Create: `source/dtc_transform/company_db/diagnostic_db.py`
- Test: `source/tests/test_company_db_diagnostic_db.py`

**Interfaces:**
- Consumes: `extract_compare_code(code: str) -> str` (Task 1)
- Produces:
  - `is_target_file(filename: str) -> bool`
  - `read_systemid(xml_path: str) -> str`
  - `build_diagnostic_index(root_dir: str) -> dict[str, list[str]]` — `비교코드 -> [파일명(확장자 제외), ...]`. Task 5가 이 딕셔너리를 그대로 소비한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_company_db_diagnostic_db.py`:

```python
import os

from dtc_transform.company_db.diagnostic_db import (
    build_diagnostic_index,
    is_target_file,
    read_systemid,
)


def test_is_target_file_accepts_d0_and_a0_suffix_case_insensitive():
    assert is_target_file("0010D0.xml") is True
    assert is_target_file("0010A0.xml") is True
    assert is_target_file("0010d0.xml") is True


def test_is_target_file_rejects_other_suffixes():
    assert is_target_file("0010N0.xml") is False
    assert is_target_file("202301.xml") is False


def _write_systemtree(path, systemid):
    path.write_text(
        f'<systemtree systemid="{systemid}" mmcid="" mmctype="bcm">'
        "<commset></commset></systemtree>",
        encoding="utf-8",
    )


def test_read_systemid_returns_root_attribute(tmp_path):
    xml_path = tmp_path / "sample.xml"
    _write_systemtree(xml_path, "TEST_2009_1006101_001")

    assert read_systemid(str(xml_path)) == "TEST_2009_1006101_001"


def test_build_diagnostic_index_skips_non_target_files_without_parsing_them(tmp_path):
    region_dir = tmp_path / "HMA"
    region_dir.mkdir()

    _write_systemtree(region_dir / "0010D0.xml", "TEST_2009_1006101_001")
    _write_systemtree(region_dir / "0011A0.xml", "TEST_2009_9998888_001")
    # Not a target suffix -- must be skipped even though it would parse fine.
    _write_systemtree(region_dir / "0012N0.xml", "TEST_2009_1006101_001")
    # A target suffix but unparsable content -- must not crash the build.
    (region_dir / "0013D0.xml").write_text("not xml at all", encoding="utf-8")

    index = build_diagnostic_index(str(tmp_path))

    assert sorted(index["6101"]) == ["0010D0"]
    assert index["8888"] == ["0011A0"]
    assert "0012N0" not in [f for files in index.values() for f in files]
    assert "0013D0" not in [f for files in index.values() for f in files]


def test_build_diagnostic_index_walks_nested_region_folders(tmp_path):
    for region in ("HMA", "KMC"):
        region_dir = tmp_path / region
        region_dir.mkdir()
        _write_systemtree(region_dir / "0020D0.xml", "TEST_2009_5551234_001")

    index = build_diagnostic_index(str(tmp_path))

    assert sorted(index["1234"]) == ["0020D0", "0020D0"]
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_company_db_diagnostic_db.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 최소 구현 작성**

`source/dtc_transform/company_db/diagnostic_db.py`:

```python
import os
import xml.etree.ElementTree as ET

from .code_extract import extract_compare_code

TARGET_SUFFIXES = ("D0", "A0")


def is_target_file(filename: str) -> bool:
    stem = os.path.splitext(filename)[0]
    return stem[-2:].upper() in TARGET_SUFFIXES


def read_systemid(xml_path: str) -> str:
    """Read only the root element's systemid attribute -- stops parsing
    immediately after the root start tag so large files don't get fully
    loaded into memory just to read one attribute."""
    for _event, elem in ET.iterparse(xml_path, events=("start",)):
        return elem.get("systemid", "")
    return ""


def build_diagnostic_index(root_dir: str) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}

    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.lower().endswith(".xml"):
                continue
            if not is_target_file(filename):
                continue

            stem = os.path.splitext(filename)[0]
            try:
                systemid = read_systemid(os.path.join(dirpath, filename))
            except ET.ParseError:
                continue
            if not systemid:
                continue

            try:
                compare_code = extract_compare_code(systemid)
            except ValueError:
                continue

            index.setdefault(compare_code, []).append(stem)

    return index
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_company_db_diagnostic_db.py -v`
Expected: PASS (5개 테스트 전부)

- [ ] **Step 5: 커밋**

```bash
git add source/dtc_transform/company_db/diagnostic_db.py source/tests/test_company_db_diagnostic_db.py
git commit -m "feat: index diagnostic-DB XML files by compare code, D0/A0 only"
```

---

## Task 3: vehicle_info XML 인덱스 (`vehicle_info.py`)

**Files:**
- Create: `source/dtc_transform/company_db/vehicle_info.py`
- Test: `source/tests/test_company_db_vehicle_info.py`

**Interfaces:**
- Produces: `build_vehicle_info_index(xml_paths: list[str]) -> tuple[dict[str, str], dict[str, set[str]]]` — `(ecucode -> sysitemdesc, ecucode -> 충돌난 sysitemdesc 집합)`. Task 5가 첫 번째 딕셔너리를 소비한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_company_db_vehicle_info.py`:

```python
from dtc_transform.company_db.vehicle_info import build_vehicle_info_index

VEHICLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<vehiclesdata>
  <geographiczone geozonecode="KOR">
    <manufacturer mfrcode="HY">
      <lang langcode="ENG">
        <vehicletype vehicletypevincode="8">
          <model modeldesc="ACCENT(HC)">
            <modelvin modelvincode="C" modelcode="HC13">
              <modelyr modelyr="2022">
                <engine enginecode="157">
                  <sysitem sysitemtype="en" sysitemdesc="ENGINE">
                    <syssubitem syssubitemcode="157" syssubitemdesc="Engine Control">
                      <ecuid ecucode="E0A1" />
                    </syssubitem>
                  </sysitem>
                  <sysitem sysitemtype="ab" sysitemdesc="AIRBAG">
                    <syssubitem syssubitemcode="36" syssubitemdesc="Airbag">
                      <ecuid ecucode="D2O6" />
                    </syssubitem>
                  </sysitem>
                </engine>
              </modelyr>
            </modelvin>
          </model>
        </vehicletype>
      </lang>
    </manufacturer>
  </geographiczone>
</vehiclesdata>
"""

CONFLICTING_XML = """<?xml version="1.0" encoding="utf-8"?>
<vehiclesdata>
  <geographiczone geozonecode="USA">
    <manufacturer mfrcode="HY">
      <lang langcode="ENG">
        <vehicletype vehicletypevincode="8">
          <model modeldesc="OTHER(XX)">
            <modelvin modelvincode="X" modelcode="XX99">
              <modelyr modelyr="2023">
                <engine enginecode="1">
                  <sysitem sysitemtype="xx" sysitemdesc="SOMETHING_ELSE">
                    <syssubitem syssubitemcode="1" syssubitemdesc="Other">
                      <ecuid ecucode="E0A1" />
                    </syssubitem>
                  </sysitem>
                </engine>
              </modelyr>
            </modelvin>
          </model>
        </vehicletype>
      </lang>
    </manufacturer>
  </geographiczone>
</vehiclesdata>
"""


def test_builds_ecucode_to_sysitemdesc_index(tmp_path):
    path = tmp_path / "vehiclesdata_HMA.xml"
    path.write_text(VEHICLE_XML, encoding="utf-8")

    resolved, conflicts = build_vehicle_info_index([str(path)])

    assert resolved == {"E0A1": "ENGINE", "D2O6": "AIRBAG"}
    assert conflicts == {}


def test_same_ecucode_with_different_sysitemdesc_across_files_is_a_conflict(tmp_path):
    path_a = tmp_path / "vehiclesdata_HMA.xml"
    path_a.write_text(VEHICLE_XML, encoding="utf-8")
    path_b = tmp_path / "vehiclesdata_KMC.xml"
    path_b.write_text(CONFLICTING_XML, encoding="utf-8")

    resolved, conflicts = build_vehicle_info_index([str(path_a), str(path_b)])

    assert "E0A1" not in resolved
    assert conflicts["E0A1"] == {"ENGINE", "SOMETHING_ELSE"}
    assert resolved["D2O6"] == "AIRBAG"
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_company_db_vehicle_info.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 최소 구현 작성**

`source/dtc_transform/company_db/vehicle_info.py`:

```python
import xml.etree.ElementTree as ET


def build_vehicle_info_index(xml_paths: list[str]) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Collect every (ecucode -> sysitemdesc) pairing across all given
    files first, then resolve: a code seen with exactly one sysitemdesc is
    trustworthy, a code seen with more than one is a conflict to report
    rather than silently pick a winner for."""
    seen: dict[str, set[str]] = {}

    for path in xml_paths:
        tree = ET.parse(path)
        for sysitem in tree.getroot().iter("sysitem"):
            desc = sysitem.get("sysitemdesc", "")
            if not desc:
                continue
            for ecuid in sysitem.iter("ecuid"):
                code = ecuid.get("ecucode", "")
                if not code:
                    continue
                seen.setdefault(code, set()).add(desc)

    resolved = {code: next(iter(descs)) for code, descs in seen.items() if len(descs) == 1}
    conflicts = {code: descs for code, descs in seen.items() if len(descs) > 1}
    return resolved, conflicts
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_company_db_vehicle_info.py -v`
Expected: PASS (2개 테스트 전부)

- [ ] **Step 5: 커밋**

```bash
git add source/dtc_transform/company_db/vehicle_info.py source/tests/test_company_db_vehicle_info.py
git commit -m "feat: index vehicle_info XML ecucode -> displayed System name"
```

---

## Task 4: ECU DOC CSV 로더 (`ecu_doc.py`)

**Files:**
- Create: `source/dtc_transform/company_db/ecu_doc.py`
- Test: `source/tests/test_company_db_ecu_doc.py`

**Interfaces:**
- Produces: `load_ecu_doc_rows(csv_path: str) -> list[tuple[str, str]]` — `(system_name, doc_code)` 튜플 리스트. 헤더 행 유무를 미리 판단하지 않고 모든 행을 그대로 반환한다 — 헤더처럼 비교코드 추출이 안 되는 행은 Task 5의 조인 단계에서 자연스럽게 `bad_doc_code`로 걸러진다. Task 5가 이 리스트를 그대로 소비한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`source/tests/test_company_db_ecu_doc.py`:

```python
from dtc_transform.company_db.ecu_doc import load_ecu_doc_rows


def test_loads_doc_code_and_system_name_columns(tmp_path):
    csv_path = tmp_path / "ecu_doc.csv"
    csv_path.write_text(
        "92710100_ABC_1006101_001,4WD(4WheelDrive)\n"
        "92710100_ABC_D2O6_002,AIRBAG(Airbag)\n",
        encoding="utf-8",
    )

    rows = load_ecu_doc_rows(str(csv_path))

    assert rows == [
        ("4WD(4WheelDrive)", "92710100_ABC_1006101_001"),
        ("AIRBAG(Airbag)", "92710100_ABC_D2O6_002"),
    ]


def test_skips_blank_lines_and_strips_whitespace(tmp_path):
    csv_path = tmp_path / "ecu_doc.csv"
    csv_path.write_text(
        "\n"
        " 92710100_ABC_1006101_001 , 4WD(4WheelDrive) \n"
        "\n",
        encoding="utf-8",
    )

    rows = load_ecu_doc_rows(str(csv_path))

    assert rows == [("4WD(4WheelDrive)", "92710100_ABC_1006101_001")]
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_company_db_ecu_doc.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 최소 구현 작성**

`source/dtc_transform/company_db/ecu_doc.py`:

```python
import csv


def load_ecu_doc_rows(csv_path: str) -> list[tuple[str, str]]:
    """Read a 2-column (doc_code, system_name) CSV exported from the
    protected ECU DOC workbook's columns A and O. Any header row or
    malformed line is passed through as-is -- the caller resolves those
    downstream when compare-code extraction fails on them."""
    rows: list[tuple[str, str]] = []

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            doc_code, system_name = row[0].strip(), row[1].strip()
            if not doc_code or not system_name:
                continue
            rows.append((system_name, doc_code))

    return rows
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd source && python -m pytest tests/test_company_db_ecu_doc.py -v`
Expected: PASS (2개 테스트 전부)

- [ ] **Step 5: 커밋**

```bash
git add source/dtc_transform/company_db/ecu_doc.py source/tests/test_company_db_ecu_doc.py
git commit -m "feat: load ECU DOC doc-code/system-name pairs from CSV"
```

---

## Task 5: 조인 + CLI 오케스트레이터 (`build_system_mapping.py`)

**Files:**
- Create: `source/tools/build_system_mapping.py`
- Test: `source/tests/test_build_system_mapping.py`

**Interfaces:**
- Consumes:
  - `extract_compare_code(code: str) -> str` (Task 1)
  - `build_diagnostic_index(root_dir: str) -> dict[str, list[str]]` (Task 2)
  - `build_vehicle_info_index(xml_paths: list[str]) -> tuple[dict[str, str], dict[str, set[str]]]` (Task 3)
  - `load_ecu_doc_rows(csv_path: str) -> list[tuple[str, str]]` (Task 4)
- Produces:
  - `resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved) -> tuple[dict[str, str], list[dict]]`
  - `build_mapping_json(resolved: dict[str, str], existing: dict[str, dict]) -> dict[str, dict]`
  - `write_review_csv(path: str, unresolved: list[dict]) -> None`
  - `main()` — CLI 엔트리포인트

- [ ] **Step 1: 실패하는 테스트 작성 (조인 로직)**

`source/tests/test_build_system_mapping.py`:

```python
import csv
import json

from tools.build_system_mapping import (
    build_mapping_json,
    resolve_system_names,
    write_review_csv,
)


def test_resolves_when_exactly_one_matching_candidate_exists():
    ecu_doc_rows = [("4WD(4WheelDrive)", "92710100_ABC_1006101_001")]
    diagnostic_index = {"6101": ["0010D0", "0010A0"]}
    vehicle_resolved = {"0010D0": "4WD"}

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    assert resolved == {"4WD(4WheelDrive)": "4WD"}
    assert unresolved == []


def test_reports_no_match_when_no_candidate_is_in_vehicle_info():
    ecu_doc_rows = [("UNKNOWN(Sheet)", "92710100_ABC_1006101_001")]
    diagnostic_index = {"6101": ["0010D0"]}
    vehicle_resolved = {}

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    assert resolved == {}
    assert unresolved == [{"sheet": "UNKNOWN(Sheet)", "reason": "no_match", "candidates": ["0010D0"]}]


def test_reports_ambiguous_when_candidates_disagree():
    ecu_doc_rows = [("AMBIG(Sheet)", "92710100_ABC_1006101_001")]
    diagnostic_index = {"6101": ["0010D0", "0011A0"]}
    vehicle_resolved = {"0010D0": "SYS_A", "0011A0": "SYS_B"}

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    assert resolved == {}
    assert unresolved == [{"sheet": "AMBIG(Sheet)", "reason": "ambiguous", "candidates": ["SYS_A", "SYS_B"]}]


def test_reports_bad_doc_code_when_compare_code_extraction_fails():
    ecu_doc_rows = [("HeaderRow", "not_a_valid_code")]

    resolved, unresolved = resolve_system_names(ecu_doc_rows, {}, {})

    assert resolved == {}
    assert unresolved == [{"sheet": "HeaderRow", "reason": "bad_doc_code", "candidates": []}]


def test_build_mapping_json_preserves_manual_entries():
    resolved = {"4WD(4WheelDrive)": "4WD", "AIRBAG": "AIRBAG_NEW"}
    existing = {
        "AIRBAG": {"system": "AIRBAG_OLD", "source": "manual"},
    }

    merged = build_mapping_json(resolved, existing)

    assert merged["4WD(4WheelDrive)"] == {"system": "4WD", "source": "company_db"}
    assert merged["AIRBAG"] == {"system": "AIRBAG_OLD", "source": "manual"}


def test_write_review_csv_lists_unresolved_sheets(tmp_path):
    path = tmp_path / "review.csv"
    unresolved = [{"sheet": "AMBIG(Sheet)", "reason": "ambiguous", "candidates": ["SYS_A", "SYS_B"]}]

    write_review_csv(str(path), unresolved)

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["sheet", "reason", "candidates"]
    assert rows[1] == ["AMBIG(Sheet)", "ambiguous", "SYS_A;SYS_B"]
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd source && python -m pytest tests/test_build_system_mapping.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tools.build_system_mapping'`)

- [ ] **Step 3: 조인 로직 + 리포트 작성 함수 구현**

`source/tools/build_system_mapping.py` (1/2 — 이 단계에서는 아래 함수들만):

```python
import csv
import json

from dtc_transform.company_db.code_extract import extract_compare_code
from dtc_transform.company_db.diagnostic_db import build_diagnostic_index
from dtc_transform.company_db.ecu_doc import load_ecu_doc_rows
from dtc_transform.company_db.vehicle_info import build_vehicle_info_index


def resolve_system_names(
    ecu_doc_rows: list[tuple[str, str]],
    diagnostic_index: dict[str, list[str]],
    vehicle_resolved: dict[str, str],
) -> tuple[dict[str, str], list[dict]]:
    resolved: dict[str, str] = {}
    unresolved: list[dict] = []

    for system_name, doc_code in ecu_doc_rows:
        try:
            compare_code = extract_compare_code(doc_code)
        except ValueError:
            unresolved.append({"sheet": system_name, "reason": "bad_doc_code", "candidates": []})
            continue

        candidate_files = diagnostic_index.get(compare_code, [])
        matched_descs = {
            vehicle_resolved[stem] for stem in candidate_files if stem in vehicle_resolved
        }

        if len(matched_descs) == 1:
            resolved[system_name] = next(iter(matched_descs))
        elif len(matched_descs) == 0:
            unresolved.append({"sheet": system_name, "reason": "no_match", "candidates": candidate_files})
        else:
            unresolved.append(
                {"sheet": system_name, "reason": "ambiguous", "candidates": sorted(matched_descs)}
            )

    return resolved, unresolved


def build_mapping_json(resolved: dict[str, str], existing: dict[str, dict]) -> dict[str, dict]:
    merged = dict(existing)
    for sheet, system in resolved.items():
        current = merged.get(sheet)
        if current and current.get("source") == "manual":
            continue
        merged[sheet] = {"system": system, "source": "company_db"}
    return merged


def write_review_csv(path: str, unresolved: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sheet", "reason", "candidates"])
        for row in unresolved:
            writer.writerow([row["sheet"], row["reason"], ";".join(row["candidates"])])
```

- [ ] **Step 4: 테스트 실행해서 통과 확인 (main() 이전 함수들)**

Run: `cd source && python -m pytest tests/test_build_system_mapping.py -v`
Expected: PASS (6개 테스트 전부 — `main()`은 아직 없어도 임포트 대상이 아니므로 영향 없음)

- [ ] **Step 5: CLI 엔트리포인트 추가**

`source/tools/build_system_mapping.py`에 이어서 추가 (파일 맨 아래):

```python
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build config/sheet_system_mapping.json by joining ECU DOC, diagnostic-DB XML, and vehicle_info XML"
    )
    parser.add_argument("--ecu-doc-csv", required=True, help="CSV export of ECU DOC columns A (doc code) and O (system name)")
    parser.add_argument("--diagnostic-db-root", required=True, help="Root folder containing the region subfolders of 진단 DB XML files")
    parser.add_argument("--vehicle-info-xml", required=True, nargs="+", help="One or more vehicle_info/*.xml file paths")
    parser.add_argument("--mapping-output", required=True, help="Path to config/sheet_system_mapping.json to update")
    parser.add_argument("--review-csv", required=True, help="Path to write the unresolved-sheets review CSV")
    args = parser.parse_args()

    ecu_doc_rows = load_ecu_doc_rows(args.ecu_doc_csv)
    diagnostic_index = build_diagnostic_index(args.diagnostic_db_root)
    vehicle_resolved, _conflicts = build_vehicle_info_index(args.vehicle_info_xml)

    resolved, unresolved = resolve_system_names(ecu_doc_rows, diagnostic_index, vehicle_resolved)

    try:
        with open(args.mapping_output, encoding="utf-8") as f:
            existing = json.load(f)
    except FileNotFoundError:
        existing = {}

    merged = build_mapping_json(resolved, existing)

    with open(args.mapping_output, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2, sort_keys=True)

    write_review_csv(args.review_csv, unresolved)

    print(
        f"resolved={len(resolved)} unresolved={len(unresolved)} "
        f"mapping_output={args.mapping_output} review_csv={args.review_csv}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 전체 테스트 스위트 실행**

Run: `cd source && python -m pytest -q`
Expected: 이전까지의 전체 테스트(160여 개) + 이번에 추가한 것 모두 PASS, 실패 없음

- [ ] **Step 7: 커밋**

```bash
git add source/tools/build_system_mapping.py source/tests/test_build_system_mapping.py
git commit -m "feat: join company DBs into config/sheet_system_mapping.json with a review report for unresolved sheets"
```

---

## Task 6: 문서 갱신 (`source/README.md`)

**Files:**
- Modify: `source/README.md`

이 도구가 기존 `tools.derive_mapping`(confidence/hits 방식)을 대체한다는 것과 실행 커맨드를 문서화한다.

- [ ] **Step 1: "시트→System 매핑 재생성" 절 교체**

`source/README.md`의 "## 시트→System 매핑 재생성" 절(기존 `derive_mapping` 설명) 바로 뒤에 아래 내용 추가:

```markdown
**2026-09-07부로 위 통계적(confidence/hits) 방식은 사내 DB 3종을 조인하는 결정적 방식으로 대체되었다** (근거: [`docs/superpowers/specs/2026-09-07-company-db-system-mapping-design.md`](../docs/superpowers/specs/2026-09-07-company-db-system-mapping-design.md)):

```bash
cd source
python -m tools.build_system_mapping \
  --ecu-doc-csv "<암호 해제된 ECU DOC CSV 경로>" \
  --diagnostic-db-root "<진단 DB 1 폴더 경로>" \
  --vehicle-info-xml docs/new_data_for_matching/vehicle_info/*.xml \
  --mapping-output config/sheet_system_mapping.json \
  --review-csv config/sheet_system_mapping_review.csv
```

`--review-csv`로 나온 파일은 매칭 후보가 하나도 없거나(`no_match`) 서로 다른 System을 가리켜(`ambiguous`) 자동으로 값을 못 채운 시트 목록이다 — 사람이 확인 후 `config/sheet_system_mapping.json`에 `"source": "manual"`로 직접 추가한다 (아래 "수동 보정 규칙" 절 참고). 이미 `"source": "manual"`인 항목은 재실행해도 덮어써지지 않는다.
```

- [ ] **Step 2: 커밋**

```bash
git add source/README.md
git commit -m "docs: document the company-DB-based sheet mapping generator"
```
