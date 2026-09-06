# DTC Master n8n 워크플로우 import 가이드

이 폴더에는 워크플로우 3개가 있다:

- `dtc_master_workflow.json` — 자동 반복 실행되는 메인 변환 파이프라인
- `dtc_mapping_ai_review_workflow.json` — 매핑 재생성 + AI 검토를 n8n이 처음부터 끝까지 전부 담당하는 버전
- `dtc_mapping_ai_review_cloud_workflow.json` — 위와 같은 AI 검토 기능이지만, Python 실행 부분은 로컬 스크립트(`tools.run_ai_review`)가 담당하고 n8n은 AI Agent 호출만 대행하는 버전

**앞의 두 워크플로우는 self-hosted n8n 전용이다** (`Execute Command`, `Local File Trigger`를 쓰므로 n8n Cloud 관리형 환경에서는 노드 자체가 없어서 동작하지 않는다 — import하면 해당 노드가 물음표 아이콘으로 뜨고 연결도 끊긴 것처럼 보인다). self-hosted n8n 서버가 없다면 (예: n8n Cloud 트라이얼만 있는 경우) **`dtc_mapping_ai_review_cloud_workflow.json`을 대신 쓴다** — 이건 `Webhook`/`Respond to Webhook`/AI Agent 노드만 쓰므로 n8n Cloud에서도 정상 동작한다.

## 워크플로우 1: 메인 변환 파이프라인 (`dtc_master_workflow.json`)

### 설치 절차

1. n8n 관리 화면에서 **Workflows > Import from File**로 `dtc_master_workflow.json`을 불러온다.

2. 아래 값을 실제 환경에 맞게 수정한다:

   - **Watch Incoming Folder** 노드의 `path`
     - 기본값: `/data/dtc_master/incoming`
     - 수정 필요: 원본 txt가 놓일 로컬(또는 SharePoint 동기화) 폴더 경로로 변경

   - **Run Transform Pipeline** 노드의 `command`
     - 기본값: `cd /data/dtc_master/source && python -m dtc_transform.pipeline --input "{{$json["path"]}}" --mapping config/sheet_system_mapping.json --output /data/dtc_master/output/dtc_master_km.sqlite --report /data/dtc_master/output/run_report.txt`
     - 수정 필요: `cd` 뒤 경로를 이 리포지토리의 `source/` 실제 배포 경로로 수정, `--output`/`--report` 경로도 배포 환경에 맞게 수정

   - **Publish Output** 노드의 `command`
     - 기본값: `cp /data/dtc_master/output/dtc_master_km.sqlite /data/dtc_master/publish/dtc_master_km.sqlite`
     - 수정 필요: 복사 대상 경로를 배포 환경에 맞게 수정

   - **Notify Success** 노드
     - `fromEmail`: `dtc-pipeline@example.com` → 발신 이메일 주소로 변경
     - `toEmail`: `dtc-pipeline-owners@example.com` → 수신 이메일 주소로 변경

   - **Notify Failure** 노드
     - `fromEmail`: `dtc-pipeline@example.com` → 발신 이메일 주소로 변경
     - `toEmail`: `dtc-pipeline-owners@example.com` → 수신 이메일 주소로 변경

3. 각 노드를 저장하면 credential 설정을 요구하는 노드(이메일)는 n8n에서 별도로 SMTP credential을 만들어 연결해야 한다. 이는 워크플로우 파일 자체에는 포함될 수 없는 값이다:
   - **Notify Success** 및 **Notify Failure** 노드에서 n8n SMTP credential 선택/생성

## 테스트

1. **Watch Incoming Folder**가 감시하는 폴더에 샘플 txt 파일을 넣는다.
2. 전체 워크플로우가 끝까지 실행되는지 확인한다.
3. 성공 시 이메일 알림을 수신하거나 `Publish Output`의 대상 디렉토리에 결과 파일이 생성되는지 확인한다.

## 워크플로우 흐름

```
Watch Incoming Folder
        ↓
Run Transform Pipeline
        ↓
Succeeded? (exit code = 0?)
    ↙          ↘
 YES           NO
  ↓             ↓
Publish     Notify Failure
Output
  ↓
Notify Success
```

### 환경 요구사항 (워크플로우 1)

- Python 3.11+ 및 `dtc_transform` 패키지가 n8n 실행 서버에 설치되어 있어야 함
- 워크플로우 파일의 모든 경로는 n8n 실행 서버의 로컬 파일 시스템 기준
- SMTP 서버 접근 가능 (이메일 알림 사용 시)

## 워크플로우 2: 매핑 재생성 + AI 검토 (`dtc_mapping_ai_review_workflow.json`)

신뢰도가 낮은 자동 매핑 추론(예: 표본이 적은 시트)을 AI가 먼저 검토해서 제안을 리뷰 CSV에 덧붙여주는, **사람이 필요할 때 수동으로 실행**하는 워크플로우다. 자동 반복 실행되는 워크플로우 1과는 완전히 분리되어 있다.

**중요한 원칙**: AI는 `config/sheet_system_mapping.json`을 직접 고치지 않는다. `config/sheet_system_mapping_review.csv`에 `ai_suggestion`/`ai_reasoning` 컬럼만 추가하고, 사람이 이 CSV를 열어보고 맞다고 판단되면 [`source/README.md`의 수동 보정 규칙](../README.md#수동-보정-규칙)대로 직접 반영한다.

### 흐름

```
Manual Trigger
      ↓
Regenerate Mapping (tools.derive_mapping)
      ↓
Build Review Context (tools.review_context)
      ↓
Split Sheets For Review (시트 단위로 분리)
      ↓
AI Agent (Chat Model 연결 필요) ──▶ 시트별 제안 생성
      ↓
Parse AI Suggestion → Collect Suggestions → Write Suggestions File
      ↓
Apply AI Suggestions (tools.apply_ai_suggestions)
      ↓
Succeeded? (exit code = 0?)
   ↙          ↘
 YES           NO
  ↓             ↓
Notify Teams  Notify Teams
Success       Failure
```

### 설치 절차

1. **Workflows > Import from File**로 `dtc_mapping_ai_review_workflow.json`을 불러온다.

2. 아래 경로를 실제 환경에 맞게 수정한다:
   - **Regenerate Mapping** / **Build Review Context** 노드의 `command` — `cd` 경로, `--raw-input`/`--reference-db` 경로
   - **Write Suggestions File** 노드의 `fileName`
   - **Apply AI Suggestions** 노드의 `command`

3. **Chat Model (swap as needed)** 노드에 실제 사용할 LLM credential을 연결한다:
   - 기본값은 `@n8n/n8n-nodes-langchain.lmChatAnthropic`(Claude)로 구성해뒀지만, 어떤 모델을 쓰든 상관없다 — 이 노드를 지우고 원하는 Chat Model 노드(OpenAI 등)로 교체한 뒤, **AI Agent** 노드에 `ai_languageModel` 연결로 다시 이어주면 된다.
   - n8n의 LangChain 계열 노드는 버전에 따라 세부 파라미터/타입버전이 조금씩 다를 수 있다. import 후 AI Agent 또는 Chat Model 노드에 경고 아이콘이 뜨면, 노드를 열어 모델명/credential을 다시 선택해주면 대부분 해결된다.
   - Anthropic/OpenAI API 키는 n8n의 credential 관리 화면에서 별도로 등록한다 (워크플로우 파일 자체에는 포함될 수 없다).

4. **Notify Teams Success** / **Notify Teams Failure** 노드의 `url`에 있는 `https://REPLACE-WITH-YOUR-TEAMS-INCOMING-WEBHOOK-URL`을 실제 Teams 채널의 Incoming Webhook URL로 교체한다.
   - Teams 채널 > 커넥터(Connectors) > **Incoming Webhook** 추가 > 이름 설정 후 생성되는 URL을 그대로 사용.

### 테스트

1. **Manual Trigger**로 워크플로우를 직접 실행한다.
2. 끝까지 실행되면 Teams 채널에 "DTC 매핑 AI 검토 완료" 메시지가 오는지 확인한다.
3. `config/sheet_system_mapping_review.csv`를 열어 `ai_suggestion`/`ai_reasoning` 컬럼이 채워졌는지 확인한다.
4. 제안이 맞다고 판단되면 `config/sheet_system_mapping.json`을 [수동 보정 규칙](../README.md#수동-보정-규칙)대로 직접 수정한다 — 이 워크플로우가 자동으로 반영하지 않는다.

### 환경 요구사항 (워크플로우 2)

- 워크플로우 1과 동일한 Python 환경
- n8n에 LangChain 노드(`@n8n/n8n-nodes-langchain.*`)가 활성화되어 있어야 함 (최신 n8n은 기본 포함)
- 사용할 LLM의 API 키
- Teams 채널의 Incoming Webhook URL

## 워크플로우 3: AI 검토 (n8n Cloud 호환, `dtc_mapping_ai_review_cloud_workflow.json`)

워크플로우 2와 목적은 같지만(낮은 신뢰도 매핑에 AI 제안 붙이기), self-hosted 서버 없이 **n8n Cloud만으로** 동작하도록 역할을 나눴다:

- **로컬 Python** (`python -m tools.run_ai_review`, [source/README.md](../README.md#ai-검토-자동화-n8n-서버-없이) 참고) 이 매핑 재계산, 검토 컨텍스트 생성, CSV 갱신, Teams 알림까지 전부 담당
- **n8n**은 그 중 "AI Agent 호출"만 대행 — Webhook으로 받은 시트별 컨텍스트를 AI Agent에 넘기고, 결과를 동기 응답(Respond to Webhook)으로 돌려줄 뿐 파일이나 셸 명령을 전혀 건드리지 않는다

이 워크플로우에는 `Execute Command`, `Local File Trigger`, `Manual Trigger`가 전혀 없다 — 그래서 n8n Cloud에서도 물음표 노드 없이 그대로 동작한다.

### 흐름

```
(로컬 Python: tools.run_ai_review)
   │  POST 시트별 컨텍스트
   ▼
Webhook
   ↓
Split Sheets For Review
   ↓
AI Agent (Chat Model 연결 필요) ──▶ 시트별 제안 생성
   ↓
Parse AI Suggestion → Collect Suggestions
   ↓
Respond to Webhook  ──▶ (로컬 Python이 응답을 받아 CSV/Teams 알림 처리)
```

### 설치 절차

1. **Workflows > Import from File**로 `dtc_mapping_ai_review_cloud_workflow.json`을 불러온다.
2. **Chat Model (swap as needed)** 노드에 실제 사용할 LLM credential을 연결한다 (워크플로우 2와 동일한 절차 — 위 3번 참고).
3. **Webhook** 노드를 열어 URL(Production URL)을 복사해둔다 — 이게 `tools.run_ai_review --n8n-webhook-url`에 넣을 값이다.
4. (권장) **Webhook** 노드의 Authentication을 `Header Auth`로 설정하고 임의의 토큰 credential을 만든다 — 기본값(`None`)은 URL만 알면 누구나 호출할 수 있는 공개 엔드포인트다. Header Auth를 켰다면 `tools.run_ai_review`가 그 헤더를 실어 보내도록 별도로 스크립트를 조정해야 한다.
5. 워크플로우를 **Active**로 전환한다 (Webhook은 활성화 상태여야 Production URL이 응답한다).

### 테스트

1. `source/README.md`의 `tools.run_ai_review` 명령을 `--n8n-webhook-url`에 3번에서 복사한 URL을 넣어 직접 실행한다.
2. n8n의 **Executions** 탭에서 Webhook 실행이 기록되고 AI Agent까지 정상적으로 지나갔는지 확인한다.
3. 로컬에서 지정한 `--review-csv` 파일에 `ai_suggestion`/`ai_reasoning` 컬럼이 채워졌는지, Teams 채널에 완료 메시지가 왔는지 확인한다.

### 환경 요구사항 (워크플로우 3)

- n8n Cloud 계정 (무료/트라이얼로도 충분 — Execute Command류 노드를 쓰지 않음)
- n8n에 LangChain 노드가 활성화되어 있어야 함 (n8n Cloud는 기본 포함)
- 사용할 LLM의 API 키
- `tools.run_ai_review`를 실행할 로컬 PC의 Python 환경 (워크플로우 1과 동일)
- Teams 채널의 Incoming Webhook URL (n8n이 아니라 Python이 직접 호출)
