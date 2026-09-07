# DTC Excel Extraction 파이프라인 — 현재 로직 요약

Kia KDS 2.0 DTC 등급 마스터 데이터를, Purview/AIP로 보호된 마스터 Excel 파일로부터
n8n(Excel 자격 증명) → 로컬 Python 도구 → sqlite → Teams 알림 순으로 만들어내는
웹훅 기반 파이프라인의 현재 로직을 정리한 문서입니다.

마스터 Excel 파일 자체는 이 파이프라인의 어떤 구성 요소도 직접 열람하지 않습니다.
n8n의 Microsoft Excel 노드(Graph API 인증)만 시트/행 데이터를 읽고, 로컬 Python은
그 결과 JSON과 sqlite 산출물만 다룹니다.

## 1. n8n 워크플로우 (`source/n8n/dtc_excel_extraction_workflow.json`)

```
Webhook (workbook_id, offset, limit)
  → Get Sheets            워크북 전체 시트 목록 조회
  → Slice Sheets          offset/limit 만큼만 잘라서 이후 단계로 전달
  → Get Rows From Sheet   시트당 A3:H2000 범위를 raw 데이터로 조회
  → Normalize Row         시트명 추출, DTC 없는 빈 행 제거
  → Attach System         시트명 -> System 코드 매핑 (아래 2절)
  → Aggregate All Rows ─┐
  → Build Unmapped     ─┤→ AI Agent(Gemini) → Parse AI Suggestions ─┐
     Sheets Summary                                                 │
                                                    Merge Branches ←─┘
  → Build Final Response (totalSheets 포함, alwaysOutputData)
  → Respond to Webhook
```

- **청크 단위 페이징**: 워크북 전체를 한 번에 처리하면 n8n Cloud 게이트웨이
  타임아웃(502)이 발생하므로, 호출자가 `offset`/`limit`으로 시트를 나눠서
  여러 번 호출한다.
- **Range는 A3:H2000**: 너무 좁으면(A3:H500 시절) 대형 시트(엔진 등)의 실제
  DTC가 잘려나가고, 너무 넓으면(A3:H5000) n8n 워커가 메모리 부족(OOM)으로
  죽는다. 참고본과의 실측 비교로 2000이 안전선으로 확인됨.
- **`Build Final Response`는 `alwaysOutputData: true`**: 청크에 실제 DTC
  데이터가 하나도 없으면(예: 목차/범례 시트만 있는 청크) 상류 노드들이 전부
  건너뛰어져 `Respond to Webhook`까지 실행이 안 되고 빈 200 응답이 나가는
  문제가 있었음. 이 노드만은 무조건 실행되게 해서 항상 유효한 JSON(최소
  `{"totalSheets": N}`)을 돌려주도록 함.

## 2. `Attach System` 노드의 시트 매핑 로직

시트명을 System 코드로 바꾸는 로직은 아래 순서로 적용된다.

1. **`IGNORE_PATTERNS`** — 진단 데이터가 아닌 시트를 이름 패턴으로 자동 제외
   - 기본 Excel 시트명: `Sheet1`, `Sheet2`, ...
   - 집계/요약 탭: `Total`, `Total (2)`, ...
   - 복사본 접미사로 끝나는 시트: `"X (2)"`, `"X (3)"`
2. **`IGNORE_EXACT_NAMES`** — 패턴으로 못 잡는 범례/문서용 시트를 정확한
   이름으로 제외 (예: `"dtc grade criteria"`). 새로 발견되면 이 목록에
   이름만 추가하면 됨.
3. **`MAPPING`** — `config/sheet_system_mapping.json`의 실제 매핑(93개
   시트↔System)을 그대로 반영한 정적 lookup. n8n Cloud가 저장소 파일을
   직접 읽을 수 없어서, 이 파일이 바뀔 때마다 내용을 통째로 복사해 이
   노드 코드에 다시 붙여넣어야 한다.

위 세 단계 어디에도 해당하지 않는 시트는 `system: ""`로 남고, 별도로
`Build Unmapped Sheets Summary` → `AI Agent`(Google Gemini)가 시트명과
DTC 샘플을 보고 System을 추천한다. **AI 추천은 자동 반영되지 않는다** —
사람이 검토해 `config/sheet_system_mapping.json`과 `Attach System`의
`MAPPING`에 직접 추가한 뒤 재실행해야 실제로 반영된다.

## 3. 로컬 Python 도구 (`source/tools/`)

| 파일 | 역할 |
|---|---|
| `graph_auth.py` | MSAL로 사용자 본인 계정 로그인(`Files.Read` 범위), 토큰 캐싱. Excel 파일 **내용**은 건드리지 않고 메타데이터만 접근 |
| `resolve_workbook.py` | OneDrive 공유 링크 → Graph driveItem ID / 폴더 내 `.xlsx` 목록 조회 |
| `fetch_extraction.py` | 웹훅을 청크(기본 15개 시트)씩 나눠 호출. 첫 청크는 전체 시트 수(`totalSheets`)를 알아야 하므로 단독 호출하고, 이후 나머지 청크는 최대 동시 개수(기본 5)만큼 병렬로 호출해 처리 시간을 단축 |
| `run_extraction.py` | 추출 JSON 저장 → sqlite 변환 → Teams 알림까지 한 번에 실행하는 오케스트레이터 |
| `json_to_sqlite.py` | 매칭된 JSON을 `dtc_transform` 모듈(중복 제거/등급 필터/확장/암호화)을 통해 sqlite로 변환, 실행 리포트 작성 |
| `notify_teams.py` | Teams Incoming Webhook으로 MessageCard 알림 전송 (성공/매핑 필요/실패) |
| `run_extraction_gui.py` | Tkinter GUI. 웹훅 URL, Teams 웹훅 URL, OneDrive 폴더 링크(입력값 저장됨), 파일 목록, 저장 위치(파일 탐색기), 동시 요청 수(기본 5, 저장됨)를 입력받아 백그라운드 스레드로 실행 |

미매핑 시트가 하나라도 있으면 `run_extraction.py`는 "매핑 필요" Teams
알림만 보내고 종료 코드 1로 끝난다 — sqlite 파일 자체는 생성되지만(미매핑
시트의 System은 빈 값으로), "정식 배포본"으로 취급하지 않는다.

## 4. 중복 DTC 처리 로직 (`source/dtc_transform/dedup.py`)

같은 System으로 여러 시트가 합쳐질 때(예: `EMS-DieselEngine` +
`EMS-GasolineEngine` → `ENGINE`), 동일한 DTC 코드가 시트마다 다른 내용으로
겹칠 수 있다. 이때 적용되는 결정적(deterministic) 규칙:

1. **Stage 1 — 같은 (System, DTC, 등급)인데 세부 항목만 다를 때**:
   `Warning_Light`/`Warning_Message`/`Limp_Home`/`Fail_Safe` 중 `O`(또는
   `○`) 표시가 더 많은 쪽을 채택. 동점이면 먼저 나온 행을 유지.
2. **Stage 2 — 같은 (System, DTC)인데 등급 자체가 다를 때**:
   더 심각한 등급(`A > B > C > D`)을 채택.

이후 `grade_filter.py`가 유효하지 않은 등급(A/B/C/D 외)을 가진 행을
제외하고, `expand.py`가 trailing-zero DTC 코드를 확장하며, `crypto.py`가
등급을 고정 lookup 테이블로 암호화한다.

**시트 병합 자체(예: Diesel/Gasoline을 `ENGINE` 하나로 합치는 것)는
실무진이 만든 참고본(`docs/dtc_master_km 3.sqlite`)에서도 동일하게
쓰이고 있음을 확인했다** — 파이프라인이 임의로 만든 방식이 아니라 기존
관행과 일치한다.

## 5. 검증 상태

참고본(`docs/dtc_master_km 3.sqlite`, 10,987행)과 이 파이프라인의 산출물을
비교한 결과:

- **(System, DTC) 기준 커버리지 100% 일치** — 빠지거나 추가된 DTC 없음
- 완전히 동일한 행 비중은 원본 셀 표기 차이(`O` vs `○`)와, 참고본이 위
  4절의 결정적 규칙을 따르지 않고 만들어졌던 시절의 차이로 인해 100%는
  아니지만, 위 규칙이 일관되게 적용된 지금 시점 기준으로는 이 로직을
  기준선으로 삼는다.
