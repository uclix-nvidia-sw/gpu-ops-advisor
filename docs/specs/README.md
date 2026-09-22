# GPU Ops Advisor 개발 명세 v1.3

기준일: 2026-09-18 · 코드 대조 기준: `775ab2f`. 기존 개발 기준에 현재 구현된 초기화·클러스터 등록·보고서 수집/표시 변경을 반영했다. 전체 기능의 구현·실환경 검수 완료를 뜻하지 않는다.

GUI → Backend에서 RCA 결과를 조회하고 보고서를 요청한다. Grafana → Incident만 RCA 실행을 요청한다. Job Controller는 영속 큐와 기존 Agent에 대한 잡 배분을 맡는다. Agent 수·자원 변경은 사람이 수행하며 자동 확장은 없다. 정기 보고서 스케줄러는 Backend 내부 기능이다.

[전체 구조도](../architecture/architecture-modules-20260917-v1.3/README.md) · [PNG](../architecture/architecture-modules-20260917-v1.3/dsx-job-controller.png) · [저장소 안내](../../README.md)

## 문서 구성과 읽기 순서

이 문서는 기존 00 산출물 안내를 이어받은 현행 개발 명세의 목차다. 요구사항·검수·운영 기준은 이 폴더에, 공통 계약은 `common/`에, 모듈별 설계는 담당 폴더에 둔다. 문서 번호와 제품 계약은 유지한다.

1. [요구사항·개발 범위](01_요구사항_개발범위_정의서.md)에서 이번 작업의 범위를 확인한다.
2. 아래 목록에서 담당 모듈의 설계서와 작업에 필요한 공통 계약을 읽는다. RCA 코드는 `rcca-agent/`, 문서는 `docs/specs/rca-agent/`에 있다.
3. 변경으로 영향을 받는 다른 모듈의 계약과 [테스트·검수 기준](05_테스트_검수_기준서.md)을 함께 확인한다. 실제 구현·검증 범위는 코드·테스트·모듈 QA와 대조한다.

확정된 상세 보완 명세가 필요하면 해당 모듈 폴더에 추가하고 이 목차에서 연결한다. 공통 데이터·산식·결과 형식을 복사해 별도 기준을 만들지 않는다. 아직 합의되지 않은 내용은 초안임을 표시한다.

### RCA 설계 초안

`rca-agent/drafts/`는 검토용 제안이다. 현행 명세를 자동으로 대체하지 않으며, 해당 제안을 구현 대상으로 지정한 작업에서 참고한다. 일부 검색 코드의 구현·검증 기록은 전체 파이프라인의 통합·운영 검수 완료와 구분한다.

- [GPU 노드 RCA Runbook 설계 초안](rca-agent/drafts/gpu-node-rca-runbook-design.md)
- [Runbook-first 검색·조사 파이프라인 초안](rca-agent/drafts/gpu-node-rca-runbook-first-pipeline.md)
- [Knowledge DB 참고 설계](rca-agent/drafts/knowledge-db-reference.md)

## 개발 문서

| 번호 | 문서 | 단일 기준으로 관리하는 내용 |
|---|---|---|
| 01 | [요구사항·범위](01_요구사항_개발범위_정의서.md) | 기능·제외 범위·개발 단계 |
| 02 | [Backend/API](backend/02_백엔드_API_작업명세서.md) | GUI API, 정기 보고서 일정과 접수 |
| 03 | [데이터](common/03_데이터_설계서.md) | D01~D14, DB 소유권·필드·제약 |
| 04 | [공통 판단](common/04_Agent_동작_판단_명세서.md) | 계산·품질·지식·결과 스키마 |
| 05 | [테스트·검수](05_테스트_검수_기준서.md) | 시나리오·기대값·실행 증거 |
| 06 | [배포·운영](06_배포_운영_인계서.md) | 수동 자원 설정·기동·장애 복구 |
| 07 | [프론트엔드](frontend/07_프론트엔드_개발명세서.md) | 화면 상태·API 연동·클러스터 등록·보고서 출력 |
| 08 | [GUI](frontend/08_GUI_화면설계서.md) | 화면별 필드·행동·빈 상태 |
| 09 | [개정·정리 내역](09_통합검토_반영내역.md) | 변경 이유·삭제 범위·추적·검증 |
| 10 | [Job Controller](job-controller/10_Job_Controller_모듈_설계서.md) | 큐·배분·용량 제한·상태 전이 |
| 11 | [RCA Agent](rca-agent/11_RCA_Agent_모듈_설계서.md) | NAT·Runbook·MCP 조사, R01~R09 |
| 12 | [보고서 Agent](ops-agent/12_보고서_Agent_모듈_설계서.md) | NAT·RCA DB/기간 관측 집계, O01~O11 |
| 13 | [Incident](incident/13_Incident_모듈_설계서.md) | Grafana 알람·사건·RCA 접수 |
| 14 | [모듈 간 계약](common/14_모듈간_호출과_공통실행_계약.md) | DTO·멱등·lease·완료·오류 |

## 실행 단위와 책임

Backend, Incident, Job Controller, RCA Agent, 보고서 Agent의 5개 서버 모듈과 Frontend를 독립 실행·배포한다. 각 Agent는 NVIDIA NeMo Agent Toolkit(NAT) 워크플로를 내부에서 실행하고 Grafana MCP로 관측을 조회한다. RCA는 Runbook과 사건 증거를, 보고서는 사건·공개 RCA 결과와 기간 관측을 읽는다. 공통 코드는 두 Agent의 연결 처리·정규화·계산 등 중복 함수만 재사용하며 별도 업무 서비스가 아니다. Grafana MCP는 별도 조회 연결 구성 요소다. Agent 내부에 별도 업무 접수 API나 독립 큐를 만들지 않는다.

Chatbot/Assistant·직접 RCA 요청 화면·독립 Scheduler·HPA/자동 증설·제품 인증/RBAC/사용자 tenant는 이번 개발 범위에서 제외한다. 기존 Mimir/Loki 연결에 필요한 기술 설정은 유지한다. 과거 문서의 같은 번호·시험 ID를 현행 문서와 혼용하지 않는다.

문서 버전은 1.3, 모듈 계약은 1.3이다. 계산 기준(criteria_version)과 결과 스키마(result_schema_version)는 기존 1.1을 유지하며 RCA의 incident_id는 필수다. 2026-09-18 내용 반영은 당시 버전과 코드 동작을 기록한다. 2026-09-22에는 문서를 `docs/specs/`의 공통·모듈별 경로로 재배치했으며 기능 요구사항과 제품 계약 버전은 변경하지 않았다.

## 현재 구현과 검증 기록

| 범위 | 코드에 반영된 동작 | 확인 자료 |
|---|---|---|
| Backend·Frontend | 데모 seed 없는 기본 한도 초기화, 빈 클러스터 상태 기동, API/GUI 클러스터 등록, 서버 기반 일정·결과 조회 | [Backend QA](../../backend/QA.md), [Frontend QA](../../frontend/QA.md) |
| Incident·JC·Agent | 실제 Incident 입력의 RCA 처리, 큐·claim·완료, NAT와 공식 Grafana MCP 연결 | [Incident QA](../../incident/QA.md), [JC QA](../../job-controller/QA.md), [Agent QA](../../agents/QA.md) |
| 보고서 보완 | 대용량 응답 분할, GPU–Pod 연결 관측 집계, 수집 품질 표시, HTML/CSV 출력, LLM 예산 상향 | [보고서 Agent](ops-agent/12_보고서_Agent_모듈_설계서.md), [기존 시험 연결](05_테스트_검수_기준서.md) |

QA의 실행일·환경·범위를 기준으로 해석한다. Agent의 실제 프로세스 연동 시험은 Grafana 데이터와 LLM 응답을 fixture로 사용했으며 운영 데이터·모델 품질 검증을 뜻하지 않는다. 2026-09-18 보고서 보완에는 회귀 테스트 코드가 추가되어 있으나 이번 문서 작업에서 재실행하지 않았다. 기존 시험 전체를 일괄 PASS로 바꾸지 않는다.

## 보존한 환경 근거

[수집 환경 근거](../evidence/README.md)는 당시 확인한 범위를 기록한다. 최신 클러스터 상태나 전체 장기 이력의 확보를 보장하지 않는다. 중복 원문·ZIP·구버전 설계는 Git 이력으로 조회한다.
