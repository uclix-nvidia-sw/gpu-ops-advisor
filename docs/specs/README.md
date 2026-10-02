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

### D 쿼리 통합·확장 설계

[매핑 설계](common/d-query-mapping.md)는 단일 쿼리 D의 기존 통합·신규 D15~D49·메트릭·목적·O01~O11 및 RCA 소비 관계를 정의한다. 기존 분석 기능을 보존하며 D 내부 복수 metric 구조는 사용하지 않는다. [개발 계획](common/d-contract-redesign-plan.md)은 환경별 binding 검증부터 구현·검수까지의 산출물/완료 기준을 관리한다. 03 §3.3은 이 설계로 연결한다. 문서 설계이며 런타임 변경이나 실환경 검증 완료가 아니다.

### 현재 구현 분석에서 모듈 업그레이드로 이어지는 기준

이 설계 문서는 초기 구현을 설명하는 기록과 다음 개발의 목표를 함께 관리한다. **구현이 목표와 다르다고 목표를 현재 코드에 맞춰 낮추거나, 목표가 문서에 있다고 구현 완료로 표시하지 않는다.** 모듈별로 현재 코드 근거 → 문제·영향 → 변경 목표 → 영향받는 소비자·선행 계약 → 검수 사례를 연결한다. 아직 합의가 필요한 산식·필드·운영값은 미정으로 남긴다.

2026-09-23에 코드 `d391f3d`와 작업 트리의 업그레이드 설계를 정적으로 대조했다. 아래는 주요 접수·조사·보고서·조회 경로의 1차 분석이며 전체 코드 감사나 신규 실행 검증 결과가 아니다. 작업 ID는 문서 내 추적용이며 별도 큐나 제품 상태가 아니다.

| 담당 문서 | 구현 분석·업그레이드 항목 | 선행·함께 확인할 범위 |
|---|---|---|
| [02 Backend §0](backend/02_백엔드_API_작업명세서.md#0-현재-구현-분석과-업그레이드-작업) | BE-01~03: 사건 DTO, 목적/결과 소비, Runbook 발행·검색 | Incident/JC/RCA 계약, Frontend |
| [07 Frontend §0](frontend/07_프론트엔드_개발명세서.md#0-현재-구현-분석과-업그레이드-작업) | FE-01~03: 사건 상태 정합, 종결·재발, RCA 근거 표시 | Backend/Incident, 08 화면 기준 |
| [10 JC §0](job-controller/10_Job_Controller_모듈_설계서.md#0-현재-구현-분석과-업그레이드-작업) | JC-01~03: 버전별 접수, Worker 호환, 공개 검증 경계 | shared/03/14, 두 Worker, 모든 결과 소비자 |
| [11 RCA §0.1](rca-agent/11_RCA_Agent_모듈_설계서.md#01-후속-개발을-위한-코드-대조) | RCA-01~04와 기존 P0~P6: 목적 선택, 이력 확보, Runbook/fact 연결, 결과 소비 | Incident/JC, 공통 Python, Backend/Frontend/Ops |
| [12 Ops §0](ops-agent/12_보고서_Agent_모듈_설계서.md#0-현재-구현-분석과-업그레이드-작업) | OP-01~04: 그룹·사건·당시 작업·혼합 소비; OP-05~07: 병렬 관측·종합 조언·결과 소비 | 03/04의 계산 계약, 14 실행 계약, Incident/RCA, Backend/Frontend |
| [13 Incident §0.1](incident/13_Incident_모듈_설계서.md#01-후속-개발을-위한-코드-대조) | IN-01~03: 사건 신원·중복, 최초 요청·역할 분리, 상태 소비 | DB migration/JC/Worker 선행, Backend/Frontend/Ops |

2026-09-23 추가 검토에서 개발을 막던 계약 충돌을 보완했다. 접수 버전은 jobs.versions.input_contract로 전달하고 Worker 지원 계약으로 배분한다(14). RCA는 목적 선택 전에 단일 DB 이력을 고정한다(03 §6). 보고서의 그룹 지원·사건 기간·재발·발생률 기준은 04 §5.5에 정의했다. 서로 다른 기본값을 모듈에서 임의로 만들지 않는다.

Incident는 알람 생명주기 상태와 사건 ID를 분리하고, source를 그룹에 포함하며 신원 부족은 생명주기별로 격리한다. 동일 bytes의 반복 수신도 활성 사건의 수신 연속성에 반영한다. 종료 이후는 새 발생/탐지 시각이 확인될 때만 새 에피소드를 만들고, 과거 재전송·수집 장애·resolved 선접수는 별도 규칙을 따른다(13 §2). DB 제약은 03, 기대값은 T41~T58에 맞췄다.

**구현 착수 기준은 보완했지만 배포 준비가 완료된 것은 아니다.** 실제 repeat_interval/K, 발생 시각 갱신·미래 오차·허용 나이, 원천 신원과 관측 완전성은 06 C03/C05에서 검수해야 한다. 문서에 있는 새 테이블·필드·프로토콜·산식은 아직 제품 코드에 반영되지 않았다.

이후 2026-09-23 Incident·JC 구현에서 생명주기/에피소드 migration과 선택적 1.4 생산 경로, JC의 1.3/1.4 접수·Worker 호환 배분·결과 계약 검사를 추가했다. 기본 생산자는 기존 1.3을 유지한다. Worker의 1.4 의미 검증·후속 소비자 전환·통합 배포 검수는 별도 작업이며, 상세 구현 범위·검증은 [Incident 설계 §0](incident/13_Incident_모듈_설계서.md#0-변경-기준과-구현-상태), [Incident QA](../../incident/QA.md), [JC QA](../../job-controller/QA.md)를 따른다.

우선 계약·데이터 선결 조건을 정리하고 호환 소비자를 준비한 뒤 Incident 생산자를 전환한다. RCA의 세부 개발 순서는 11 §7을 따른다. 각 작업의 테스트는 [05](05_테스트_검수_기준서.md)의 기존 T ID에 구체 사례를 연결하고, 실제 실행 후 모듈 QA에 날짜·환경·입력·예상/실제 결과를 남긴다. 이번 분석에서 제품 코드는 변경하지 않았고 제품 테스트·실환경 검수도 실행하지 않았다.

### Incident 중복 제거·Agent 판단 역할 변경

2026-09-22부터 [13 Incident](incident/13_Incident_모듈_설계서.md)와 [11 RCA](rca-agent/11_RCA_Agent_모듈_설계서.md)를 변경했다. 현재 목표는 **Incident의 적격 에피소드별 최초 알람 전달과 반복 억제**, **RCA Agent의 파싱·목적·Runbook/일반 조사 선택**이다. Incident의 alertname→R 매핑과 증거 변경 시 재분석은 신규 경로에서 제거한다.

2026-09-23에 알람 소스와 사건 단위를 확정했다. 알람은 Fleet component 로그를 Grafana 규칙이 조회해 `cluster_id`/`machine_id`/`component` 라벨로 전달하고, 사건 단위는 알람 생명주기에서 **관측 에피소드**로 바뀐다. 중복 억제(기록)와 재분석 억제(분석)를 분리해 관측이 이어지는 동안은 사건·RCA가 하나이고, 조치 후 종결된 뒤의 재발은 경과 시간과 무관하게 새 사건·새 RCA가 된다. 종결은 사람만 판단하며 관측 종료·`resolved`·RCA 완료는 회복이 아니다. 상세는 13 §1.1~§2, [03 §6](common/03_데이터_설계서.md), [05](05_테스트_검수_기준서.md) T49~T52에 있다.

이는 문서상 개발 목표다. 런타임·Helm은 여전히 1.3이며 신규 RCA 접수는 [14](common/14_모듈간_호출과_공통실행_계약.md)의 1.4 이행 계약으로 구분한다. 결과 스키마 1.1과 보고서 접수 계약은 유지한다. 01/02/03/04/05/06/10도 역할·입력·소비·검수·배포 영향을 반영했다. 기존 아키텍처 그림은 실행 경로 참고용이며 변경 상세는 11/13/14가 우선한다.

### RCA workflow·runbook 통합 기준

2026-09-28의 첨부 문서 검토와 로컬 구현은 [RCA 입력·병렬 조사·Synthesis 보완 계획](rca-agent/implementation-plan-20260928.md), [11 §2.4](rca-agent/11_RCA_Agent_모듈_설계서.md#24-현재-실행-순서와-확인된-한계), [Agent QA](../../agents/QA.md)를 따른다. 이번 구현은 입력 1.3에서 Orchestrator·병렬 관측·최대 1회 재조사·최종 Synthesis를 연결한다. 아래 9월 23일의 분석 후 반복 흐름은 이 순서로 보완했다. 1.4 목적 선택과 운영 데이터 의미 검수는 후속 단계다.

2026-09-22에 [11. RCA Agent 모듈 설계서](rca-agent/11_RCA_Agent_모듈_설계서.md)를 기준으로 아래 초안을 대조·통합했다. **현재 구현과 추가 개발 목표를 구분**하고, Runbook-first workflow, D-쿼리 재사용·선결 조건, runbook 작성/발행 계약, 구현 순서와 검수 기준을 11번 문서에서 관리한다. D01~D13·Observation·evidence 저장을 재사용하며 검색 모듈의 구현을 전체 파이프라인 통합 완료로 해석하지 않는다.

`rca-agent/drafts/`는 제안 출처·당시 검증 기록으로 보존한다. 미채택 제안과 과거 실행 명령을 현행 요구사항으로 자동 적용하지 않는다. 상세 병합 결정과 evidence 해석 보정도 11번 문서에 기록했다.

후속 코드 검토를 반영해 11번 문서 §3에 fact·health 입력 계약, §5.3에 요청 출처별 query 허용 정책, §6.2에 compatibility 컨텍스트·발행 검증·Backend 코드 검색 호환성을 구체화했다. 개발은 접수·역할 전환 P0와 P0a 데이터 계약·P0b 관측 정합부터 진행한다. 이 데이터 구조와 validator는 추가 개발 목표이며 현재 runtime/API에 모두 구현됐다는 의미는 아니다.

2026-09-23 workflow 합의를 11 §2의 Mermaid 도식·종료/LLM 계약과 Runbook 작성 문서에 반영했다. Runbook 검색·적용 검사는 DB 조회·코드로 처리하며, 기존 증거로 충분하면 MCP·LLM을 생략한다. 부족하면 **MCP 수집 → 증거 정리 → LLM 분석 → 검증·재평가 → 필요 시 재조사**하고, 단독 판단·LLM 분석·미확정 결과 모두 기존 DB 저장·JC 공개를 거쳐 이력/보고서에 사용한다. 공통 04와 검수 T33~T36도 맞췄다. 제품 코드·DB·배포 변경이나 실행 검증 완료를 뜻하지 않는다.

2026-09-23에 추가한 [rca-agent/references/](rca-agent/references/README.md)는 runbook 작성용 검토 자료다. 근거자료 카탈로그, Domain·Category 메트릭 매핑, Fleet·GPUd component·오류 카탈로그로 구성하며 실행 가능한 runbook이나 확정된 Knowledge DB seed가 아니다. 사용 단계와 `source-verified → observed → runbook-validated` 승격 기준은 11번 문서 §6.4.1에서 관리한다.

- [GPU 노드 RCA Runbook 설계 초안](rca-agent/drafts/gpu-node-rca-runbook-design.md)
- [Runbook-first 검색·조사 파이프라인 초안](rca-agent/drafts/gpu-node-rca-runbook-first-pipeline.md)
- [Knowledge DB 참고 설계](rca-agent/drafts/knowledge-db-reference.md)
- RCA evidence 조사 검토 — [11번 문서](rca-agent/11_RCA_Agent_모듈_설계서.md) §8에 해석과 점검 순서를 정리했다. 사용자 제공 운영 원문은 로컬에 보존하며 저장소에 포함하지 않는다.

### 보고서 Orchestrator·병렬 관측·조언 개발 기준

[현재 상세 흐름](../architecture/report-agent-workflow/detailed-workflow.md)과 [12 Ops](ops-agent/12_보고서_Agent_모듈_설계서.md)를 기준으로 query+CPC별 독립 Observation·의존성·공유 예산·취소 회수를 구현했다. 보고서 문장은 기존 reference-only 선택으로 편집한다. 추가 관측 라운드·자유 생성형 조언·의미 검증은 OP-05~07의 남은 목표다.

실행 계약은 [14](common/14_모듈간_호출과_공통실행_계약.md), 판단 의미는 [04](common/04_Agent_동작_판단_명세서.md), 실제 통과 범위는 [Agent QA](../../agents/QA.md)를 따른다. [T60~T65](05_테스트_검수_기준서.md) 전체 완료를 뜻하지 않는다. 접수 1.3·결과 1.1, Namespace criteria 1.2와 기존 공개 계약을 유지한다.

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
| 11 | [RCA Agent](rca-agent/11_RCA_Agent_모듈_설계서.md) | R01~R09, workflow·runbook 계약, D-쿼리 선결 조건, 개발·검수 순서 |
| 12 | [보고서 Agent](ops-agent/12_보고서_Agent_모듈_설계서.md) | O01~O11, 현재 병렬 관측·남은 조언 목표·검수 순서 |
| 13 | [Incident](incident/13_Incident_모듈_설계서.md) | Grafana 알람·사건·RCA 접수 |
| 14 | [모듈 간 계약](common/14_모듈간_호출과_공통실행_계약.md) | DTO·멱등·lease·완료·오류 |

## 실행 단위와 책임

Backend, Incident, Job Controller, RCA Agent, 보고서 Agent의 5개 서버 모듈과 Frontend를 독립 실행·배포한다. 각 Agent는 NVIDIA NeMo Agent Toolkit(NAT) 워크플로를 내부에서 실행하고 Grafana MCP로 관측을 조회한다. RCA는 Runbook과 사건 증거를, 보고서는 사건·공개 RCA 결과와 기간 관측을 읽는다. 공통 코드는 두 Agent의 연결 처리·정규화·계산 등 중복 함수만 재사용하며 별도 업무 서비스가 아니다. Grafana MCP는 별도 조회 연결 구성 요소다. Agent 내부에 별도 업무 접수 API나 독립 큐를 만들지 않는다.

Chatbot/Assistant·직접 RCA 요청 화면·독립 Scheduler·HPA/자동 증설·제품 인증/RBAC/사용자 tenant는 이번 개발 범위에서 제외한다. 기존 Mimir/Loki 연결에 필요한 기술 설정은 유지한다. 과거 문서의 같은 번호·시험 ID를 현행 문서와 혼용하지 않는다.

기존 명세 묶음과 현행 모듈 계약은 1.3이다. 신규 RCA 접수 목표는 1.4, 보고서 접수는 1.3이다. 현행 계산 기준은 1.1이며 04 §5.5의 보고서 집계 변경 목표는 criteria_version=1.2로 구분한다. 결과 스키마는 1.1을 유지하고 RCA의 incident_id는 필수다. 2026-09-18 내용은 당시 코드 동작을 기록한다. 2026-09-22 문서 재배치와 RCA 초안 통합, 2026-09-23 계약 보완은 문서 변경이며 런타임 버전을 변경하지 않았다.

## 현재 구현과 검증 기록

| 범위 | 코드에 반영된 동작 | 확인 자료 |
|---|---|---|
| Backend·Frontend | 데모 seed 없는 기본 한도 초기화, 빈 클러스터 상태 기동, API/GUI 클러스터 등록, 서버 기반 일정·결과 조회 | [Backend QA](../../backend/QA.md), [Frontend QA](../../frontend/QA.md) |
| Incident·JC·Agent | 실제 Incident 입력의 RCA 처리, 큐·claim·완료, NAT와 공식 Grafana MCP 연결 | [Incident QA](../../incident/QA.md), [JC QA](../../job-controller/QA.md), [Agent QA](../../agents/QA.md) |
| 보고서 보완 | 대용량 응답 분할, GPU–Pod 연결 관측 집계, 수집 품질 표시, HTML/CSV 출력, LLM 예산 상향 | [보고서 Agent](ops-agent/12_보고서_Agent_모듈_설계서.md), [기존 시험 연결](05_테스트_검수_기준서.md) |

QA의 실행일·환경·범위를 기준으로 해석한다. Agent의 실제 프로세스 연동 시험은 Grafana 데이터와 LLM 응답을 fixture로 사용했으며 운영 데이터·모델 품질 검증을 뜻하지 않는다. 2026-09-18 보고서 보완에는 회귀 테스트 코드가 추가되어 있으나 이번 문서 작업에서 재실행하지 않았다. 기존 시험 전체를 일괄 PASS로 바꾸지 않는다.

## 보존한 환경 근거

[수집 환경 근거](../evidence/README.md)는 당시 확인한 범위를 기록한다. 최신 클러스터 상태나 전체 장기 이력의 확보를 보장하지 않는다. 중복 원문·ZIP·구버전 설계는 Git 이력으로 조회한다.
