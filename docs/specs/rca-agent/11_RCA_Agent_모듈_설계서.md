# 11. RCA Agent 모듈 설계서

버전 1.3 · 모듈 rca · 독립 실행·배포 · R01~R09 · NVIDIA NeMo Agent Toolkit(NAT) 적용 설계

## 1. 역할·입력

Incident가 생성하고 Job Controller가 배분한 RCA 잡만 실행한다. Backend·GUI·보고서에서 RCA를 직접 접수하는 API는 없다. 자체 업무 큐·달력·레플리카 제어도 없다. 잡 실행 관리는 JC의 register/claim/heartbeat/complete/fail을 사용하는 Worker가 담당하고, 조사 중에는 Runbook·사건 DB, Grafana MCP, 추론 endpoint를 호출한다.

입력은 incident_id, evidence_version, analysis_profile_revision, scope, target 또는 사건 범위, incident_time, time_range, purpose_ids다. 알람 증거 snapshot과 일치해야 한다. Pod/GPU 신원 일부가 미확정이면 확인된 사실과 부족 필드를 보존한다. incident_id가 없는 임의 증상 요청은 거절한다.

R01~R09는 독립 GUI 실행 메뉴가 아니라 Incident RCA의 조사 목적이다. 새 조사 목적·증거로 재분석할 필요가 있으면 Incident 정책이 새 job을 생성한다. 자동 기술 재시도는 동일 job의 새 attempt다.

## 2. 처리·저장

여유 슬롯에서 claim → 사건 증거·대상/시각 확인 → 호환 Runbook 검색·적용 조건 확인 → 부족한 증거를 Grafana MCP로 조회 → 원인 후보·지지/반박 분석 → 검증된 candidate 저장 → JC complete 순서다. 이미 충분한 증거가 있으면 추가 관측 조회를 생략할 수 있다. evidence와 result_candidates는 RCA 소유이며 jobs·사건 상태는 직접 변경하지 않는다.

04의 공통 결과에 incident_id·incident_time·current_checked_at·pod_relations·assessments·cause_candidates·recommendations·missing_inputs·termination_reason을 더한다. 숫자는 measurements 레지스트리에 저장하고 문장에서는 value_refs로 참조한다.

### 2.1 모듈 내부 구성

Worker 프로세스 안에서 NAT 사용자 정의 워크플로를 실행한다. 워크플로는 다음 업무 함수로 구성하며, 단계마다 별도 서비스나 하위 Agent를 배포하지 않는다.

| 내부 구성 | 책임 | 사용하는 자료/연결 |
|---|---|---|
| Worker 실행부 | claim·heartbeat·취소·deadline·후보 저장·완료 보고 | JC API, 자기 결과·근거 저장소 |
| 사고 입력 확인 | 불변 Incident snapshot, 사고 대상·시각 검증 | incident_evidence_versions |
| Runbook 검색·검사 | 호환 발행본 검색, 필수 증거·적용/배제 조건 확인 | knowledge_revisions; 04의 지식 계약 |
| 조사 진행 | 등록 procedure 선택, 부족한 증거에 대한 다음 조사 결정 | NAT 워크플로·LLM·허용된 조회 함수 |
| 관측 조회 | 제한된 로그·지표·당시/현재 관계 확보와 품질 정규화 | NAT MCP 클라이언트 → Grafana MCP → Grafana 데이터소스 |
| 원인 분석·검증 | 사실·후보·지지/반박·권고·한계 작성 및 검증 | 확보한 증거, 규칙, LLM |

LLM에는 등록된 다음 조사 선택만 허용한다. 도구 호출을 지원하는 모델을 검증한 뒤 NAT Tool Calling 단계를 조사 진행에 연결한다. 호출 가능한 절차, 대상, 시간창, 횟수와 종료 조건은 Python 코드가 검사한다. 저장·완료·취소 처리는 LLM 도구로 노출하지 않는다.

### 2.2 Runbook 우선 조사와 추가 조회

| 상황 | 처리 |
|---|---|
| 호환 Runbook과 필수 증거가 모두 있음 | 실제 적용·배제 조건을 검사한 뒤 근거와 권고 작성. 불필요한 추가 조회 생략 |
| Runbook은 있으나 증거 부족 | Runbook이 요구하는 로그·지표를 Grafana MCP로 조회하고 적용 여부 재검사 |
| 맞는 Runbook이 없음 | 3.2의 등록 일반 조사 procedure로 사고 전후 로그·지표·관계를 조회하고 원인 후보 분석 |
| 반박 증거·상충·데이터 부족 | 양쪽 증거를 보존하고 결론 수준을 낮추거나 미확정 종료. 다음 확인 항목 제공 |

Runbook 검색 성공은 원인 확정이나 장애 복구를 의미하지 않는다. Grafana MCP는 Runbook 실패 시에만 쓰는 보조 경로가 아니라 적용 조건을 확인하는 관측 경로이기도 하다. 알람에 충분한 증거가 있는지 먼저 검사하고, 필요한 범위만 조회한다. 조사의 반복은 procedure의 허용 단계·C07 예산 안에서만 수행한다.

관측은 Loki 로그와 Mimir의 Prometheus 호환 지표를 함께 사용한다. 실제 datasource UID·CPC 필터·원본 시각·조회 제한은 03/14 계약을 따른다. 이번 범위에서 '해결'은 원인 분석과 권고 제시까지이며 GPU reset·Pod 종료 등 실제 조치는 수행하지 않는다.

### 2.3 결과와 재현 근거

04의 기존 결과 스키마에 확인한 사실, 원인 후보, 지지/반박 근거, 적용 가능한 권고, 미충족 입력과 종료 사유를 기록한다. 사용한 Runbook revision, MCP 조회의 datasource·query revision·대상·기간·수집 시각·완전성은 03의 evidence snapshot으로 보존한다. NAT 실행 기록은 job_id·attempt_no와 연결하되 업무 DB의 결과·상태를 대체하지 않는다.

RCA 후보는 JC가 published_result_id를 확정한 뒤 Backend와 보고서 Agent가 읽는다. 분석 결과를 Runbook으로 자동 발행하거나 Incident를 자동 종결하지 않는다.

## 3. 조사 업무·판단

### 3.1 업무별 계약

‘필수’는 해당 주장의 조건이다. 표에 적힌 추가 입력이 없다고 장비 기본 조사 전체를 중단하지 않는다.

| ID | 입력·필수 데이터 | 처리·출력 | 부족 시 |
|---|---|---|---|
| R01 알려진 오류 | 원문·producer/parser 계약·장비, D01/D05/D09·KB | 코드·장비·버전으로 후보 검색 → required_evidence 검사 → 적용 가능한 권고·반박·미충족 조건 | 코드/계약 불명은 원문 보존·일반 조사. 코드 하나로 원인 확정 금지 |
| R02 GPU→Pod | D01/D08, 현재 또는 사건 시각 | 직접 매핑·같은 노드 참고 Pod·현재/당시 관계 분리 | 매핑 미확인 표시. 같은 노드 Pod를 직접 사용자로 지정하지 않음 |
| R03 Pod→GPU | Pod 신원·D08 및 가용 D02~D06/D09 | 관련 GPU와 공통 Node의 증상·활동·상태 비교 | 장치 미확정이면 Pod/배치 근거만 제공 |
| R04 작업 영향 | 사건 당시 D08·D09·D13 | 당시 관계와 실제 중단·재개·원인 연계를 별도 기록 | 현재 관계만 있으면 당시 영향 unknown/not_assessed |
| R05 미등록 증상 | 증상·대상·시각, 가용 D01~D10 | 등록 procedure로 지지/반박 가능한 후보와 추가 확인 | 원인 불명으로 종료해도 사실·부족 정보·다음 확인 제공 |
| R06 재발 위치 | D14 정규화 사건·기간, 필요 시 D08/D12 | 장비 집중/작업 이동 패턴·모델·버전·관측시간 비교 | 작업 이력 없으면 장비 사건 비교만 제공 |
| R07 공통 장애 범위 | 동시 사건·Node·매핑, 필요 시 토폴로지 | 확인된 Node/GPU/연결 범위와 관련 작업 | 토폴로지 없는 장치 영향은 미확정 |
| R08 조치 검토 대상 | 최신 D08·장비/공유/조치 범위·정책 | 현재 관련 작업·원본 시각·조치 전 확인 목록 | 매핑이 비었다고 리셋 안전 확정 금지 |
| R09 조치 후 관측 | D14 실제 조치 시각·D05/D09/D10, 업무 회복은 D13 | 장비 정상 관측·오류 재관측·작업 재개를 분리 | Healthy만 있으면 업무 복구 미확인 |

### 3.2 등록 조사와 종료

기본 procedure는 GPU 접근 이상, GPU 사건과 Pod, 작업 진행 이상, 다중 장치 사건의 네 가지를 제공한다. 각 procedure는 `procedure_id/version, accepted_symptoms, required/optional_queries, allowed_next_steps, stop_conditions, limits`를 가진 등록 함수다. 범용 YAML 해석 엔진을 만들지 않는다.

초기 시간창·최대 확대·최대 후속 조사·조회 건수·로그 크기·전체 deadline은 C07에 배포 프로필로 등록한다. 기존 예시의 전후 10분·추가 2회·최대 전후 60분은 시험용 시작안이며 실제 배포 확정값으로 사용하지 않는다.

| 종료 이유 | 의미·필수 출력 |
|---|---|
| evidence_sufficient | 현 단계의 결론을 설명할 근거 충족. 인과 확정을 자동 의미하지 않음 |
| missing_data | 부족 데이터와 수집/조회할 다음 항목 |
| conflicting_evidence | 상충 근거를 모두 보존하고 구분할 다음 검사 |
| unsupported_source | 호환 계약·파서/장비 범위와 미지원 부분 |
| budget_exhausted | 사용한 예산·중단 단계·남은 확인 |
| query_failed | 실패한 도구·범위·이미 확보한 독립 결과 |

취소·작업 마감·영구 실패는 02의 작업 상태/종료 사유로 추가 기록한다. 데이터 부족을 해결하려 무제한 재시도하지 않는다.

### 3.3 관계·영향·원인 판단

| 축 | 값 | 승격 조건 |
|---|---|---|
| relation_scope | current_mapping / incident_time_mapping / same_node_only / unknown | 해당 시각·신원·매핑 근거 |
| impact_status | not_assessed / no_impact_observed / disruption_observed / recovery_observed | 확인한 기간의 작업 상태·로그·진행 근거 |
| causal_status | undetermined / candidate / supported / confirmed | 후보별 지지·반박·확정 조건. confirmed는 검토된 조건과 증거가 있어야 함 |

`no_impact_observed`는 확인한 범위에서 영향을 보지 못했다는 뜻이다. 같은 시각에 Pod가 종료됐다는 사실만으로 GPU가 원인이라고 확정하지 않는다. 임의 확률값을 붙이지 않는다.

### 3.4 장비 상태와 검사 유효성

정규화 입력은 `raw_health,check_status,normalized_health,component,severity,target,observed_at,producer_contract,parser_revision,evidence_refs`다. raw_health는 원문 그대로 또는 null이다. check_status는 valid/unavailable/skipped/initializing/unknown, normalized_health는 healthy/degraded/unhealthy/unknown, severity는 info/warning/critical/unknown을 사용한다. 이 필드들이 Fleet 원문에 실제로 모두 존재한다는 뜻은 아니다. 배포 계약과 표본에서 검증한 것만 도출하고 불명은 unknown으로 둔다.

| 관측·검사 | 정규화·사건 처리 | 회복 근거 |
|---|---|---|
| 유효 검사에서 정상 | valid+healthy. component별 정상 근거로 저장 | C08의 유효 정상 관측 기간/횟수와 대상 일치 조건 충족 시 해당 장비 회복 근거. 업무 복구는 별도 |
| 유효 검사에서 Degraded | valid+degraded, severity는 검증된 계약 매핑 | 회복 근거 아님. C08 알림/사건 정책에 따라 생성·갱신 |
| 유효 검사에서 오류 | valid+unhealthy, 대상별 사건·증거 연결 | 회복 근거 아님 |
| 검사 불가인데 원문 Healthy | unavailable+unknown, raw_health=Healthy 보존 | 채택하지 않음. 수집/검사 문제로 표시 |
| 의도적인 검사 제외 | skipped+unknown, 제외 사유·정책 보존 | 장비 고장으로 자동 생성하지 않으며 회복 근거도 아님 |
| 초기화 중 | initializing+unknown | 초기화 대기와 실제 장애 구분. 제한 초과 판정은 C08 정책 필요 |
| 로그 단절·오래된 정상 | unknown+unknown, 마지막 유효 관측 시각 표시 | 채택하지 않음. 상태 수집 문제로 표시 |
| 미등록 상태·component·검사 의미 | unknown, 원문·미지원 계약 유지 | 정상/장애/회복으로 임의 매핑하지 않음 |

incidents 배열 등 원문에 여러 GPU 항목이 있으면 모든 자식을 각각 파싱하고 원본 위치·대상·의미 revision을 보존한다. 한 항목 실패가 다른 유효 장치의 근거를 소거하지 않는다. 정상 관측 정책값이 미지정이면 자동 회복 판정을 보류하며 운영자가 확인한 근거를 검토해 사건 상태를 변경할 수 있다.


## 4. 실행 실패·운영

Agent가 없으면 JC는 RCA 잡을 queued로 보존한다. 데이터 부족은 목적별 blocked/partial, 설명 실패는 narrative_status로 남긴다. 현 attempt의 lease·취소·deadline을 지키고 종료 불명 LLM 호출을 JC에 보고한다. final은 JC의 complete 확인 전 GUI에 노출하지 않는다.

등록된 procedure만 실행하며 임의 쉘·SQL·PromQL·장비 제어는 허용하지 않는다. 결과의 권고는 수행 사실이 아니다. Grafana resolved·Healthy·로그 부재만으로 업무 복구를 확정하지 않는다.

[공통 판단](../common/04_Agent_동작_판단_명세서.md) · [Incident](../incident/13_Incident_모듈_설계서.md) · [실행 계약](../common/14_모듈간_호출과_공통실행_계약.md)
