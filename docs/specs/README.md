# GPU Ops Advisor 계약·명세

현재 실행 흐름은 [모듈별 안내](../README.md)에서 확인한다. 명세의 상세 계약과 미구현 목표를 구분하고, 실제 코드·테스트와 대조한다. 과거 코드 대조 결과를 현재 상태로 재사용하지 않는다.

[공통 문서 관리](../../.claude/rules/workflow.md#shared-documentation)에 따라 각 계약은 담당 문서에서만 정의한다. 미구현 사항은 남은 과제로 표시하고 영향받는 소비자와 검수 조건을 명시한다. 날짜별 변경 과정은 Git·PR 이력에서 확인한다.

## 현재 실행 계약의 진입점

- [공통 D binding](common/d-binding-runtime.md) · [D 매핑](common/d-query-mapping.md): RCA·기존 O계열 관측.
- [RCA 현재 흐름](../../rcca-agent/README.md) · [Runbook 발행](../../rcca-agent/runbooks/DB-WORKFLOW.md) · [평가 분리 설계·개발 — 미구현](rca-agent/11_RCA_Agent_모듈_설계서.md#평가-분리-설계개발--미구현).
- [신규 집계 보고서 v1](ops-agent/aggregate-report-v1.md) · [기존 보고서 흐름](../architecture/report-agent-workflow/detailed-workflow.md).
- [생산자별 메트릭 의미](rca-agent/references/metric-meaning.md) · [원천 근거](../evidence/README.md).

## 개발 문서

| 번호 | 문서 | 단일 기준으로 관리하는 내용 |
|---|---|---|
| 01 | [요구사항·범위](01_요구사항_개발범위_정의서.md) | 기능·제외 범위·개발 단계 |
| 02 | [Backend/API](backend/02_백엔드_API_작업명세서.md) | GUI API, 정기 보고서 일정과 접수 |
| 03 | [데이터](common/03_데이터_설계서.md) | D 관측 및 DB 소유권·필드·제약 |
| 04 | [공통 판단](common/04_Agent_동작_판단_명세서.md) | 계산·품질·지식·결과 스키마 |
| 05 | [테스트·검수](05_테스트_검수_기준서.md) | 시나리오·기대값·실행 증거 |
| 06 | [배포·운영](06_배포_운영_인계서.md) | 수동 자원 설정·기동·장애 복구 |
| 07 | [프론트엔드](frontend/07_프론트엔드_개발명세서.md) | 화면 상태·API 연동·클러스터 등록·보고서 출력 |
| 08 | [GUI](frontend/08_GUI_화면설계서.md) | 화면별 필드·행동·빈 상태 |
| 10 | [Job Controller](job-controller/10_Job_Controller_모듈_설계서.md) | 큐·배분·용량 제한·상태 전이 |
| 11 | [RCA Agent](rca-agent/11_RCA_Agent_모듈_설계서.md) | 현행 Runbook·관측·검증 계약, 미구현 평가 분리의 흐름·LLM 개입·함수별 개발 범위 |
| 12 | [보고서 Agent](ops-agent/12_보고서_Agent_모듈_설계서.md) | 기존 O계열 보고서의 계산·조회·검수 기준 |
| 13 | [Incident](incident/13_Incident_모듈_설계서.md) | Grafana 알람·사건·RCA 접수 |
| 14 | [모듈 간 계약](common/14_모듈간_호출과_공통실행_계약.md) | DTO·멱등·lease·완료·오류 |

## 실행과 검증

Backend는 보고서 요청·일정, Incident는 RCA 접수, JC는 작업·lease·공개, 두 Worker는 조사·보고서를 소유한다. 실제 DTO/schema/criteria 버전은 각 입력 계약과 구현에서 확인하고, 한 버전 숫자를 모든 경로에 적용하지 않는다.

[Agent QA](../../agents/QA.md) · [Frontend QA](../../frontend/QA.md) · [Backend QA](../../backend/QA.md) · [Incident QA](../../incident/QA.md) · [JC QA](../../job-controller/QA.md).

[수집 환경 근거](../evidence/README.md)는 명시된 시점·출처에서 확인한 범위다. 운영 환경의 최신 상태와 배포는 별도로 확인한다.
