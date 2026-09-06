# DTC Master 변환 파이프라인

Kia KDS 2.0 진단기용 DTC(Diagnostic Trouble Code, 고장코드) 등급 마스터 데이터를, Excel 원본에서 sqlite 산출물로 변환하는 파이프라인입니다.

## 이 프로젝트가 하는 일

기아 오너십기술개발팀이 관리하는 DTC 등급 마스터 Excel 파일(제어기별 시트로 구성)을 입력받아, 다음을 수행한 뒤 진단기가 바로 사용할 수 있는 sqlite DB로 출력합니다.

1. **시트명 ↔ System 매핑**: Excel 시트명(제어기명)을 진단기에서 쓰는 System 코드로 변환 (예: `TCU(TransmissionControlUnit)` → `AT,CVT,AMT,IMT,DCT`)
2. **중복 제거**: 동일 System+DTC가 description 차이로 여러 행에 걸쳐 있으면 등급 우선순위(A>B>C>D)로 하나만 남김 (기아 승인 규칙)
3. **비A~D 등급 제외**: 등급이 A/B/C/D가 아닌 행(E, "-", 공백 등)은 출력에서 제외
4. **'00' 축약 코드 확장**: DTC 끝자리가 `00`인 행에 대해 축약 코드 행을 추가 생성 (예: `P0AC200` → `P0AC2`)
5. **등급 치환(암호화)**: 최종 등급을 고정 치환표로 인코딩해 저장

실데이터 검증 결과, 산출물의 (System, DTC) 조합이 기존 산출물(`dtc_master_km 3.sqlite`)과 10,987/10,987 완전히 일치합니다.

## 저장소 구성

```
docs/
  superpowers/
    specs/    설계 문서 (요구사항, 각 단계 규칙의 근거)
    plans/    구현 계획 (태스크별 실행 내역)
  mail_history/  (gitignore) 요구사항 논의 메일 히스토리
  *.xlsx, *.txt, *.sqlite  (gitignore) 원본/실데이터 — 대용량·민감 데이터라 저장소에 포함되지 않음

source/
  dtc_transform/  변환 파이프라인 핵심 모듈 (reconstruct → mapping → dedup → grade_filter → expand → crypto/db_writer)
  tools/          시트↔System 매핑 도출 도구 (derive_mapping.py)
  config/         매핑 설정 (sheet_system_mapping.json) 및 검토 리포트
  tests/          pytest 테스트 스위트
  n8n/            self-hosted n8n에 바로 import 가능한 워크플로우 JSON
  README.md       파이프라인 실행·매핑 운영 상세 가이드
```

## 빠른 시작

```bash
cd source
python -m pytest tests/ -v

python -m dtc_transform.pipeline \
  --input "<원본 tab-separated 텍스트 파일 경로>" \
  --mapping config/sheet_system_mapping.json \
  --output "<출력 sqlite 경로>" \
  --report "<실행 리포트 경로>"
```

상세한 실행 방법, 매핑 재생성 및 수동 보정 절차는 [`source/README.md`](source/README.md)를 참고하세요.

## 배경 자료

- [설계 문서](docs/superpowers/specs/2026-09-04-dtc-master-pipeline-design.md) — 전체 요구사항, 각 처리 단계의 규칙과 근거
- [구현 계획](docs/superpowers/plans/2026-09-04-dtc-master-pipeline.md) — 태스크 단위 구현 내역 및 사후 보정 기록
- [n8n 워크플로우 가이드](source/n8n/README.md) — self-hosted n8n에 워크플로우를 import하는 방법

## 참고

원본 Excel 파일은 Microsoft Purview(AIP) 민감도 레이블로 보호되어 있어 프로그램적으로 직접 열람할 수 없습니다. 이 파이프라인의 입력은 항상 정당한 권한을 가진 사람이 미리 추출해 둔 평문 텍스트를 전제로 합니다.
