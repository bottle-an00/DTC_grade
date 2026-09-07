# 사내 DB 기반 시트→System 매핑 생성 설계

## 배경

지금까지 `config/sheet_system_mapping.json`(Excel 시트명 → DTC 등급 마스터의
System 코드 매핑)은 `tools/derive_mapping.py`가 기존 sqlite 산출물과 새
원본 데이터를 교차 매칭해 시트별 최빈값(confidence/hits)을 통계적으로
추론하는 방식으로 생성했다.

이 방식을 폐기하고, **사내에서 관리하는 3개의 실제 DB를 조인해 결정적으로
값을 도출**하는 방식으로 교체한다. 이 3개 DB는
`docs/new_data_for_matching/`에 있다:

- **ECU DOC** (`ECU DOC (iDIMS).xlsx`) — Purview로 보호되어 있어 직접 열람
  불가. 사용자가 암호 해제된 CSV로 다시 제공하기로 함(A열: 문서 코드,
  O열: system 명칭/Excel 시트 원본 raw data).
- **진단 DB** (`진단 DB 1/{HMA,HMC,HME,KMA,KMC,KME}/*.xml`, 총 20,845개) —
  보호 없음, 직접 열람 가능. 각 파일은 `<systemtree systemid="...">`
  루트 속성을 가진다.
- **차종 DB**: 원래 형태(`차종 DB/*.mdb`, 15개)는 비밀번호로 보호되어
  있어 열람 불가. 대신 이미 암호 해제된 대체 데이터인
  `vehicle_info/vehiclesdata_*.xml`(12개)를 사용한다. 이 XML은
  `geographiczone > manufacturer > lang > vehicletype > model > modelvin
  > modelyr > engine > sysitem > syssubitem > ecuid` 계층 구조이며,
  `sysitem`의 `sysitemdesc` 속성이 진단기에 표출되는 System 명칭,
  `ecuid`의 `ecucode` 속성(4자리 영숫자)이 진단 DB 파일명과 대응하는
  ECU 코드다.

## 목표

`raw 시트명(ECU DOC의 O열) → 진단기 표출 명칭(vehicle_info의
sysitemdesc)`을 도출해, 기존과 동일한 포맷의
`config/sheet_system_mapping.json`(`{시트명: {"system": "...", ...}}`)을
생성한다. 소비하는 쪽(n8n `Attach System` 노드, `dtc_transform` 파이프라인)
의 계약은 바뀌지 않는다 — 생성 방식만 교체한다.

## 비교코드 추출 규칙 (공용)

ECU DOC의 문서 코드와 진단 DB의 `systemid`는 둘 다 `_`로 구분된 코드
문자열이다. 아래 규칙으로 **비교코드(4자리)**를 뽑아 서로 조인한다:

```
tokens = code.split("_")
second_last_token = tokens[-2]        # 마지막에서 두 번째 영역
compare_code = second_last_token[-4:]  # 그 영역의 뒤 4자리
```

예: `systemid="TEST_2009_1006101_001"` → 토큰 `[TEST, 2009, 1006101, 001]`
→ 뒤에서 두 번째 `1006101` → 뒤 4자리 `6101`.

## 처리 단계

### 1단계: 진단 DB 인덱스 생성 (`diagnostic_db.py`)

`진단 DB 1/` 하위 6개 지역 폴더를 전부 순회한다. **파일명(확장자 제외)의
마지막 2글자가 `D0` 또는 `A0`인 파일만** 대상으로 하고, 나머지는 열지도
않고 건너뛴다 (20,845개 중 약 7,542개만 실제 파싱 — 나머지 64%는 파일명만
보고 스킵해 성능을 확보한다).

대상 파일은 루트 `<systemtree>` 엘리먼트의 `systemid` 속성만 필요하므로,
전체 DOM을 메모리에 올리지 않고 스트리밍 파싱(`xml.etree.ElementTree.
iterparse`로 루트 시작 태그만 읽고 즉시 중단)으로 읽는다.

각 파일에서 `systemid` → 비교코드를 뽑아, **비교코드 → [파일명(확장자
제외), ...] 역인덱스**를 만든다(하나의 비교코드에 여러 파일이 걸릴 수
있음).

### 2단계: 차종 DB(vehicle_info) 인덱스 생성 (`vehicle_info.py`)

`vehicle_info/*.xml` 12개 파일 전부를 파싱해, 모든 `<ecuid ecucode="...">`
를 순회하며 그 조상 `<sysitem sysitemdesc="...">`의 값을 가져와
**`ecucode → sysitemdesc`** 인덱스를 만든다.

같은 `ecucode`가 서로 다른 `sysitemdesc`를 가리키는 경우(파일 간 충돌)는
에러로 막지 않고 수집해서 최종 리포트에 "충돌"로 남긴다(둘 다 후보로 남기고
3단계에서 사용하지 않음 — 사람이 확인해야 하는 항목).

### 3단계: ECU DOC 로드 및 최종 조인 (`ecu_doc.py` + `build_system_mapping.py`)

ECU DOC CSV의 각 행에서 A열(문서 코드)로 비교코드를 뽑고, O열(raw 시트명)
과 짝지은다.

시트명별로:
1. 비교코드로 1단계 역인덱스를 조회해 **후보 파일명 목록**을 얻는다.
2. 후보 파일명 중, 2단계 `ecucode` 인덱스에 **실제로 존재하는 것만** 남긴다
   (겹치는 파일이 여러 개여도, vehicle_info에 진짜로 등록된 것만 유효한
   후보로 취급).
3. 유효 후보가 정확히 1개의 `sysitemdesc`로만 좁혀지면 그 값을 최종
   System 명칭으로 채택.
4. 유효 후보가 0개(매칭 실패) 이거나, 서로 다른 `sysitemdesc`를 가리키는
   후보가 남으면(모호함) — System을 빈 문자열로 두고 **미해결 리포트**에
   사유(`no_match` / `ambiguous`)와 후보 목록을 함께 남긴다(사람이 검토).

## 출력

- `config/sheet_system_mapping.json` — 기존과 동일한 스키마로 덮어씀.
  기존에 `"source": "manual"`로 수동 보정된 항목은 `derive_mapping.py`와
  같은 방식으로 보존한다(재실행해도 덮어쓰지 않음).
- `config/sheet_system_mapping_review.csv` (또는 동일 파일명 재사용) —
  미해결 시트 목록(사유, 후보 파일명, 후보 sysitemdesc들).

n8n 쪽 반영은 기존과 동일하게 사람이 `config/sheet_system_mapping.json`
내용을 `Attach System` 노드의 `MAPPING` 객체에 수동으로 복사해 넣는다
(n8n Cloud가 저장소 파일을 읽을 수 없다는 기존 제약은 변하지 않음).

## 테스트 전략

작은 fixture 파일(2~3개 시트/파일 규모)로 각 모듈을 독립적으로 TDD 하고,
실제 20,845개 XML 전체를 도는 통합 테스트는 만들지 않는다(느리고, 원본
데이터가 `.gitignore` 대상이라 CI에서 사용할 수 없음). 대신 비교코드
추출 규칙, D0/A0 필터링, 충돌/미해결 판정 로직을 각각 유닛 테스트로
검증한다.

## 미확정 항목

- ECU DOC CSV의 정확한 컬럼 헤더명/구분자는 사용자가 파일을 제공한 뒤
  확인한다.
- vehicle_info의 `ecucode` 충돌 발생 빈도는 실데이터로 3단계 구현 후
  실측해 확인한다.
