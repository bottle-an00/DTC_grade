# DTC Master 변환 파이프라인

## 개요

Kia KDS 2.0 진단기용 DTC(고장코드) 등급 마스터 데이터를, 사람이 정당한 권한으로 Excel에서 추출한 tab-separated 원본 텍스트로부터 sqlite 산출물로 변환하는 파이프라인입니다. 전체 배경·요구사항·각 단계의 규칙은 스펙 문서를 참조하세요:

- [`docs/superpowers/specs/2026-09-04-dtc-master-pipeline-design.md`](../docs/superpowers/specs/2026-09-04-dtc-master-pipeline-design.md)

원본 Excel 파일 자체는 Microsoft Purview(AIP) 민감도 레이블로 보호되어 있어 이 파이프라인이 직접 열람할 수 없습니다(스펙 문서 "범위 밖" 참고). 입력은 항상 사람이 정당한 권한으로 미리 추출해 둔 평문 tab-separated 텍스트여야 합니다.

## 파이프라인 실행

```bash
cd source
python -m dtc_transform.pipeline \
  --input "<원본 tab-separated 텍스트 파일 경로>" \
  --mapping config/sheet_system_mapping.json \
  --output "<출력 sqlite 경로>" \
  --report "<실행 리포트 텍스트 경로>"
```

- 종료 코드가 0이 아니면(미매핑 시트 발견 시 1로 종료) 결과 sqlite를 배포하지 마세요 — 리포트에 미매핑 시트 목록이 함께 기록됩니다.
- 리포트 파일에는 단계별 행 수, 이상치(비정상 필드 수) 라인 수, 제외된 비A~D 등급 건수, 미매핑/저신뢰도 시트 목록이 사람이 읽을 수 있는 텍스트로 기록됩니다.

## 시트→System 매핑 재생성

`config/sheet_system_mapping.json`은 Excel 시트명을 진단기가 사용하는 System 코드로 변환하는 정적 설정 파일입니다. 기존 sqlite 산출물과 새 원본 데이터를 교차 매칭해 시트별 최빈값(top1)을 자동으로 채택하는 방식으로 생성됩니다:

```bash
cd source
python -m tools.derive_mapping \
  --raw-input "<원본 tab-separated 텍스트 파일 경로>" \
  --reference-db "<기존 dtc_master sqlite 경로>" \
  --output config/sheet_system_mapping.json \
  --review-report config/sheet_system_mapping_review.csv
```

`--review-report`로 생성되는 CSV는 신뢰도(자동 추론 시 최빈값의 득표 비율)가 임계값(기본 50%) 미만인 시트 목록입니다 — 자동 추론이 틀렸을 가능성이 있으니 사람이 수동으로 확인·보정해야 하는 항목입니다. **`"source": "manual"`로 이미 수동 보정된 시트는 이 CSV에서 자동으로 제외됩니다** (아래 "수동 보정 규칙" 참고). 이 도구를 다시 실행해도 이미 수동 보정된 항목은 덮어써지지 않고 그대로 보존됩니다.

## AI 검토 자동화 (n8n 서버 없이)

낮은 신뢰도로 자동 추론된 시트 매핑을 AI가 먼저 검토해 제안을 붙여주는 기능은 원래 n8n 워크플로우(`source/n8n/dtc_mapping_ai_review_workflow.json`)로 만들었지만, 이건 `Execute Command`/`Local File Trigger` 노드를 쓰기 때문에 self-hosted n8n에서만 동작합니다. self-hosted n8n 서버를 구할 수 없는 환경(예: n8n Cloud만 접근 가능, 또는 n8n 자체가 아예 없는 환경)에서는 `tools.run_ai_review`를 대신 씁니다:

```bash
cd source
python -m tools.run_ai_review \
  --raw-input "<원본 tab-separated 텍스트 파일 경로>" \
  --reference-db "<기존 dtc_master sqlite 경로>" \
  --mapping config/sheet_system_mapping.json \
  --review-csv config/sheet_system_mapping_review.csv \
  --n8n-webhook-url "<n8n Cloud Webhook URL>" \
  --teams-webhook-url "<Teams Incoming Webhook URL>"
```

이 명령 하나가 하는 일:

1. `derive_mapping`으로 매핑을 재계산하고 `--mapping`에 덮어씀 (수동 보정 항목은 그대로 보존)
2. 신뢰도가 임계값(기본 50%) 미만인 시트가 있으면, 그 시트들의 근거(후보 System 득표, DTC 샘플)를 모아 `--n8n-webhook-url`로 POST
3. n8n(Cloud도 가능 — `source/n8n/dtc_mapping_ai_review_cloud_workflow.json` 참고)이 AI Agent로 시트별 제안을 만들어 동기 응답으로 돌려줌
4. 응답받은 제안을 `--review-csv`에 `ai_suggestion`/`ai_reasoning` 컬럼으로 반영
5. 성공/실패 여부를 `--teams-webhook-url`로 직접 통보 (n8n을 거치지 않음)

**서버가 전혀 없어도 됩니다** — Python 프로세스가 n8n Cloud와 Teams에 나가는 아웃바운드 HTTP 요청만 날리는 구조라, 로컬 PC 하나로 끝납니다. 정기 실행은 n8n 없이 Windows 작업 스케줄러로 등록하면 됩니다:

1. **작업 스케줄러 열기** → 작업 만들기
2. **트리거**: 원하는 주기(예: 매일 오전 8시)로 설정
3. **동작**: 프로그램/스크립트에 `python`, 인수 추가에 `-m tools.run_ai_review --raw-input ... --reference-db ... --mapping ... --review-csv ... --n8n-webhook-url ... --teams-webhook-url ...`, 시작 위치에 `source/` 폴더의 실제 경로
4. **조건/설정** 탭에서 "AC 전원에 연결된 경우에만 시작" 등 불필요한 제약은 해제 (PC가 항상 켜져 있지 않다면 매 부팅 시 놓친 실행을 다시 시도하는 옵션도 고려)

n8n Cloud 쪽 워크플로우 import·Webhook 인증 설정은 [`source/n8n/README.md`](n8n/README.md)의 "워크플로우 3" 절을 참고하세요.

## 수동 보정 규칙

`config/sheet_system_mapping.json`의 자동 추론 값이 틀린 것으로 확인되면 다음과 같이 직접 수정합니다:

1. `"system"` 값을 올바른 값으로 수정
2. `"source": "manual"` 필드 추가
3. `"confidence": 1.0`으로 설정 (자동 재계산되는 값이 아니라 "검증 완료"를 의미)
4. `"note"` 필드에 무엇이 왜 틀렸는지, 어떻게 검증했는지 기록

실제 예시 (`config/sheet_system_mapping.json`의 `i-TPMS(indirectTPMS)` 항목, 2026-09-04 보정):

```json
"i-TPMS(indirectTPMS)": {
  "confidence": 1.0,
  "hits": 409,
  "note": "auto-inferred value 'ABSESC,ABSESP,ABSVDC' (50.12% confidence, just above the 50% review threshold) was wrong -- generic 'Battery Voltage High/Low' DTCs shared with ABSESC/FR_RADAR outnumbered i-TPMS-specific codes in the majority vote. Corrected 2026-09-04 after cross-checking docs/dtc_master_km 3.sqlite, which lists C110101/C110201 under System='i-TPMS,TPMS' (self-matching the sheet name).",
  "source": "manual",
  "system": "i-TPMS,TPMS"
}
```

이렇게 표시된 항목은 `low_confidence_sheets()`(검토 리포트 생성 로직)와 `tools.derive_mapping`의 CSV 출력, 그리고 재실행 시 자동 재계산 모두에서 제외되어 실수로 되돌려지지 않습니다.

## 테스트 실행

```bash
cd source
python -m pytest tests/ -v
```

## 참고: 원본 데이터 파일 위치

`docs/*.xlsx`, `docs/*.txt`, `docs/*.sqlite`는 대용량·민감 데이터라 `.gitignore`에 등록되어 있어 이 저장소에 포함되어 있지 않습니다. `tools.derive_mapping`을 실행하거나 실데이터로 파이프라인을 검증하려면 이 파일들을 로컬에 직접 준비해야 합니다.
