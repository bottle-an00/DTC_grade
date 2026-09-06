# DTC Master → SQLite 변환 파이프라인 설계

## 배경

Kia KDS 2.0 진단기용 DTC(고장코드) 등급 마스터 데이터는 `260331_DTC Master_영문 (글로벌 지원) (1).xlsx`로 관리되며, 이 파일은 Microsoft Purview(AIP) 민감도 레이블로 암호화되어 있어 프로그램적으로 직접 열람할 수 없다. 정당한 접근 권한을 가진 사용자가 Excel 내 Copilot/Claude 에이전트를 통해 원본 내용을 tab-separated 텍스트로 추출했으며 (`docs/260331_DTC Master_영문 (글로벌 지원) (1).txt`), 이 파일이 본 파이프라인의 입력이다.

기존 산출물 `docs/dtc_master_km 3.sqlite`(10,987행, `dtc_master` 테이블)는 동일한 변환 로직으로 이미 생성된 이전 버전이며, 본 설계의 규칙 검증에 사용했다.

메일 히스토리(`docs/mail_history/`, 2026-01-06~2026-08-06, "KDS 2.0 DTC 등급 표기 관련 건")에서 중복 제거 규칙이 2026-01-08에 기아 측 승인으로 확정되어 변경 없이 유지되어 왔음을 확인했다. 시트↔System 매핑 전체표, '00' 축약 규칙, 등급 암호화 로직은 메일에 없으며 이번에 새로 구현해야 하는 항목이다(단, 기존 sqlite 산출물에서 패턴은 확인됨).

## 목표

입력 원본 텍스트를 받아 아래 스키마의 sqlite를 생성한다 (기존 산출물과 동일 스키마):

```sql
CREATE TABLE "dtc_master" (
	"No"	INTEGER,
	"System"	TEXT,
	"DTC"	TEXT,
	"Description"	TEXT,
	"Warning_Light"	TEXT,
	"Warning_Message"	TEXT,
	"Limp_Home"	TEXT,
	"Fail_Safe"	TEXT,
	"DTC Class"	TEXT
)
```

## 입력 데이터 형식

Tab-separated, 컬럼 순서: `SheetName, DTC, Description, WarningLight, WarningMessage, LimpHome, FailSafe, Grade, GradingBackground` (9개 필드).

**알려진 결함 (2026-09-04 실데이터 검증 중 정정됨)**: 셀 내부에 줄바꿈이나 큰따옴표(`"`)가 포함된 필드는 원본이 표준 CSV/TSV 인용 규칙(RFC4180 유사)대로 큰따옴표로 감싸져 있다 — 예: `"모니터/카메라 자체 Reset(...)\n(in case of breakdown...)"`. 이 인용 규칙을 무시하고 단순 `split("\t")`으로 파싱하면, 셀 내부의 개행이나 탭이 실제 필드 경계로 오인되어 하나의 논리적 행이 여러 물리적 줄로 쪼개지거나(정상 9필드 대비 1~7필드로 조각남) Grade/FailSafe 같은 고정 위치 컬럼이 서로 밀리는 오염이 발생한다(실측: 293개 라인에서 10~11필드로 나타나며 오염 발생).

**해결**: `split("\t")` 대신 Python 표준 `csv` 모듈을 `delimiter="\t"`로 사용해 인용 규칙을 준수하며 파싱한다. 이러면 인용된 필드 내부의 줄바꿈/탭이 필드 경계로 오인되지 않고 하나의 논리적 레코드로 올바르게 합쳐진다.

## 처리 단계

### 1단계: 줄 재조립 (reconstruct)

원본 텍스트를 Python `csv` 모듈(`delimiter="\t"`, 기본 `quotechar='"'`)로 읽어, 인용 규칙에 따라 셀 내부 개행/탭을 포함한 필드를 하나의 논리적 레코드로 복원한다. 각 레코드(csv 모듈이 반환하는 필드 리스트)에서 필드 1(index 1, 0-based)이 DTC 정규식 `^[PBCU][0-9A-F]{4,6}$` (대소문자 무시)에 매치하는지로 유효한 레코드인지 검증한다. 매치하지 않는 레코드(선행 인용 규칙이 깨져 정상 복구되지 않은 극소수 잔여 이상 사례)는 orphan으로 리포트에 남기고 버린다.

필드 수가 9개보다 적거나 많은 레코드(인용되지 않은 우연한 이상치)에 대해서는 기존과 동일하게 부족분은 빈 문자열로 채우고, 초과분은 마지막 컬럼(GradingBackground)으로 합친다 — 단, csv 모듈이 인용 규칙을 이미 처리하므로 이 경로를 타는 사례는 실측상 거의 없어야 한다(발생 시 이상 사례로 리포트에 남긴다).

출력: `RawRow` 리스트 `{sheet, dtc, description, warning_light, warning_message, limp_home, fail_safe, grade, grading_background}`.

### 2단계: 시트명 → System 매핑

`config/sheet_system_mapping.json`에서 `{시트명: {"system": "...", "confidence": 0.xx, "source": "auto"|"manual"}}` 형태로 정적 매핑을 로드한다. 이 파일은 `tools/derive_mapping.py`로 기존 sqlite 산출물의 (DTC, Description) → System 값을 새 원본 데이터의 (SheetName, DTC, Description)과 교차 매칭해 시트별 최빈값(top1)을 채택하여 생성한다.

- 매칭 방법: 새 데이터의 각 (sheet, dtc, description)에 대해 기존 sqlite에서 동일한 (DTC, Description)을 가진 행들의 System 값을 모두 수집, 시트별로 집계해 최빈값을 그 시트의 System으로 채택.
- 신뢰도 = (최빈값 등장 횟수) / (해당 시트의 전체 매칭 횟수). 검증 결과 실제로 올바른 시트(예: `TCU(TransmissionControlUnit)` → `AT,CVT,AMT,IMT,DCT`, 85% 신뢰도)에서도 범용 DTC 공유로 인해 신뢰도가 100%가 되지 않는 것이 정상이므로, 신뢰도가 낮다고 자동으로 값을 버리지 않고 **그대로 채택하되 리포트에 표시**한다.
- 파이프라인 실행 중 매핑 테이블에 없는 시트를 만나면 예외를 발생시키지 않고, System을 빈 문자열로 두고 실행 리포트에 "미매핑 시트"로 기록한다(운영자가 수동으로 config에 추가).

### 3단계: 중복 제거 (기아 승인 규칙, 변경 이력 없음)

그룹 키: `(System, DTC)`.

1. **1차**: 그룹 내에서 `(System, DTC, Grade)`가 동일한 행들 중 Description이 다르더라도 Description은 무시하고 **원본에서 먼저 나온 행 1개만** 남긴다.
2. **2차**: 1차 결과로 그룹 내에 `(System, DTC)`는 같지만 Grade가 다른 행이 여러 개 남아있으면, **더 심각한 등급**을 채택한다. 심각도 순서는 `A > B > C > D` (A가 가장 심각, "Unable to drive/즉시정비", D가 가장 경미, "고객 인지 불가"). 최종적으로 `(System, DTC)`당 정확히 1행만 남는다.

검증: 기존 산출물과 대조한 실측 샘플(36건) 중 86%가 "A가 가장 심각" 가설과 일치. 나머지는 소수 예외로 규칙 자체는 그대로 적용한다.

### 4단계: '00' 확장 (중복 제거 **이후** 수행)

3단계 완료 후, 각 행의 DTC가 `00`으로 끝나면 마지막 2자리를 제거한 축약 코드(`P0AC200` → `P0AC2`)로 새 행을 추가한다. 나머지 컬럼(System, Description, Warning_*, Fail_Safe, Grade)은 원본 행과 동일하게 복사한다.

축약 코드가 이미 별도의 독립된 행(원본에 `P0AC2`가 그 자체로 존재)으로 존재하는 경우, 두 후보(원래 있던 축약 코드 행 vs 확장으로 새로 생긴 행) 중 **3단계와 동일한 등급 우선순위(A>B>C>D)로 승자를 선택**해 하나만 남긴다.

### 4.5단계: 비A~D 등급 필터링 (실데이터 검증 중 발견, 2026-09-04 사용자 승인)

실데이터(`260331_DTC Master_영문 (글로벌 지원) (1).txt`)에는 Grade가 A/B/C/D가 아닌 행이 다수 존재한다(원본 라인 기준 `E` 327건, `-` 176건, 공백 다수). `E`는 "고객 인도 후 발생 불가/공장 전용" 류의 설명이 붙어 있고, `-`는 대부분 필드가 "(no information)"인 미정 등급으로 보인다. 기존 산출물(`dtc_master_km 3.sqlite`)에는 이 값들이 전혀 없다(`DTC Class`는 A/B/C/D 4종류만 존재).

**결정**: 3단계(중복 제거) 직후, 4단계('00' 확장) 이전에 Grade가 `{A,B,C,D}`에 속하지 않는 행을 출력에서 완전히 제외한다. 제외된 행의 개수와 등급별 분포를 실행 리포트에 기록한다. 이 필터링 이후 5단계(암호화)에서 `A~D` 이외의 값을 만나면 여전히 예외를 발생시켜 중단한다(필터가 제대로 동작했다면 도달할 수 없는 코드 경로이므로, 도달 시 필터 로직 자체의 버그를 의미).

### 5단계: 등급 암호화 (고정 치환)

최종 확정된 Grade 문자를 아래 고정 테이블로 치환해 `DTC Class` 컬럼 값으로 저장한다. 실제 암호화 연산이 아니라 고정 조회 테이블이다.

| Grade | 치환값 |
|---|---|
| A | `GSwsyYvDA+tNLWnROM9rCg==` |
| B | `4CDbt0Ai5c3St5tcEQKANA==` |
| C | `Loxt0sBGAIWprCbYyMZIFw==` |
| D | `AVX59pdiJ/jHbW3BIX/SMg==` |

A~D 이외의 값이 들어오면 예외를 발생시켜 파이프라인을 중단한다(잘못된 데이터를 조용히 흘려보내지 않음).

### 6단계: sqlite 출력

최종 행 목록을 `(System, DTC)` 오름차순으로 정렬한 뒤 `No` 컬럼에 1부터 순번을 매겨 `docs/dtc_master_km 3.sqlite`와 동일한 스키마의 `dtc_master` 테이블에 기록한다. 기존 파일이 있으면 테이블을 새로 만들어 교체한다(append 아님).

## 실행 리포트

파이프라인 실행마다 다음을 담은 텍스트/CSV 리포트를 생성한다:
- 단계별 행 수 변화 (원본 → 재조립 후 → 중복 제거 후 → 00 확장 후)
- 재조립 중 복구하지 못한(선행 레코드 없는) 조각 줄 목록
- 미매핑 시트 목록
- 신뢰도 50% 미만인 매핑 시트 목록과 채택된 값

## 오케스트레이션 (n8n, self-hosted)

- **Local File Trigger** 노드: 입력 txt 파일이 있는 폴더 감시(SharePoint/Teams 폴더도 OneDrive 동기화를 통해 로컬 경로로 노출되므로 동일하게 커버됨)
- **Execute Command** 노드: `python -m dtc_transform.pipeline --input "<path>" --output "<sqlite path>" --mapping config/sheet_system_mapping.json --report "<report path>"`
- **IF** 노드: 종료 코드 확인
- 성공 시: 결과 파일을 배포 폴더로 복사하는 **Execute Command/Move File** 노드 + 이메일 알림(리포트 첨부)
- 실패 시: 에러 알림

## 범위 밖(Out of scope)

- Excel 파일 자체의 보호 해제/자동화된 복호화 — 조직 보안 정책상 본 파이프라인에서 다루지 않는다. 입력은 항상 사람이 정당한 권한으로 추출한 평문 텍스트로 가정한다.
- Power Automate 버전 구현 — n8n을 우선 구현하고, Power Automate는 필요 시 별도로 디자이너 가이드 문서로 제공한다.
