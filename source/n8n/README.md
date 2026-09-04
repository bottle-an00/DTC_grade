# DTC Master n8n 워크플로우 import 가이드

## 설치 절차

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

## 환경 요구사항

- Python 3.11+ 및 `dtc_transform` 패키지가 n8n 실행 서버에 설치되어 있어야 함
- 워크플로우 파일의 모든 경로는 n8n 실행 서버의 로컬 파일 시스템 기준
- SMTP 서버 접근 가능 (이메일 알림 사용 시)
