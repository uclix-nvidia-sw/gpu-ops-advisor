# Ops Report Agent — 일일·주간 집계 보고서

2026-10-13 · 원격 main `f7cf8c9` 기준 로컬 구현·검증. 운영 배포 전 검토용이다. 신규 요청에만 `report-aggregate-v1`을 적용하며 과거 보고서·일정은 변경하지 않는다.

## 무엇을 왜 바꾸는가

| 기존 기본 구성 | 신규 기본 구성 | 운영자가 확인할 내용 |
|---|---|---|
| O08 사용 패턴·GPU별 저활동 | `namespace_usage` — Namespace 활동과 변화 | 클러스터·Namespace·GPU 모델별 평균, 이전 기간 증감, 낮은 활동 시간대 |
| O01 장비·Node 수치 나열 | 신규 기본 보고서에서 제외 | 장비 진단은 기존 자산 화면·RCA에서 확인 |
| O05 장애·조사·처리 | `incident_summary` — 사건과 반복 현황 | 기간 내 저장된 사건 수, 같은 GPU·증상의 반복, 이전 기간 차이, 기존 공개 RCA 링크 |
| O11 별도 자료 신뢰도 주제 | 각 표·시간대의 자료 상태로 통합 | 확인 가능한 시간과 결측·귀속 불명 사유 |
| RCA와 공통 D 조회·원본 수집 | Ops 전용 PromQL·집계 검증·사건 snapshot | RCA D 변경에 신규 보고서 계산이 의존하지 않음 |

전용 할당·정책 대비 효율·회수 권고·에너지·조치 효과·새 장애 원인 분석은 포함하지 않는다. GPU 모델은 성능 순위가 아니라 서로 다른 장비의 활동률을 섞지 않는 비교 조건이다. 사용자 명칭은 **Ops Report Agent**, 기존 패키지·Deployment·Helm 키 `ops-agent`는 유지한다.

## 계산과 조회

기간은 Asia/Seoul 자정 경계의 24시간 또는 168시간 `[start,end)`다. 현재 기간과 직전 같은 길이의 기간을 같은 범위로 조회한다. 수동 주간은 선택한 마지막 날짜까지 7일, 자동 주간은 기존 달력 규칙의 직전 완료된 월~일이다. 월간·연간·임의 기간은 이번 신규 경로에 없다.

기본 수집은 클러스터·기간마다 아래 **3개의 range 요청**을 각각 한 번 보낸다. 연결 변경이 의심되는 시간대만 아래 추가 검증을 수행한다. `stepSeconds=3600`이고 하루는 24점, 주간은 168점이다. 15초마다 HTTP 요청하거나 시간대별로 API를 24번 호출하지 않는다. datasource discovery 요청은 별도다.

| 조회 ID | 집계 | 필요한 이유 |
|---|---|---|
| `hourly_gpu_activity` | GPU 활동률의 시간당 sum/count/min/max | 평균 재계산, 범위 검증, 시간대 그래프 |
| `hourly_pod_identity` | GPU가 연결된 Pod의 `kube_pod_info` count 및 min/max=1 | 같은 시간대의 UID·노드 연결 검증 |
| `hourly_gpu_identity_count` | 클러스터 전체에서 GPU UUID당 관측 신원 수 | 선택 Namespace 밖으로 연결이 바뀌거나 중복 관측된 GPU를 정상으로 합치지 않음 |

실제 쿼리는 [report_queries.py](../../../ops-agent/src/ops_agent/report_queries.py)가 유일한 실행 기준이다. DCGM은 `job=nvidia-dcgm-exporter`, KSM은 `job=kube-state-metrics`, 둘 다 `collection_path=alloy-direct`와 `cluster_id`를 고정한다. Namespace 선택을 두 조회에 적용하고, 신원 수 조회는 선택 GPU UUID만 반환한다. Pod 필터는 응답을 줄이지만 Mimir 내부 스캔 비용 감소를 보장하지 않는다.

`[1h] offset 1ms`와 각 시간대 끝을 평가 시각으로 써서 밀리초 정밀도 표본을 `[start,end)`에 맞춘다. 15초는 원본 수집 주기 계약이며 API 호출 간격이 아니다. 한 시간에 238~242개 표본, 고유 GPU/Pod 신원, 같은 노드, 유효 활동률 0~100을 확인한다. 짧은 누락·불규칙 수집이 표본 수만으로 완전히 검출되는 것은 아니다.

평균은 **유효 표본 활동률 합 / 유효 표본 수**다. 일평균의 단순 평균이 아니다. 이전 시간가중 평균과 산식이 달라 구버전 결과를 덮어쓰거나 혼합하지 않는다. 시간대 일부가 부족하면 유효 시간대와 부분 평균을 표시하되 이전 기간 증감·저활동 시간대 판정은 보류한다. 관측 없음·Pod 신원 변경·중복·MIG 귀속 불명은 0%가 아니다. 명시적 공유/MIG 라벨과 관측 신원 중복은 검사하지만, 공유 설정 이력 전체를 확인하지 않으므로 독점 사용량이라고 표현하지 않는다.

시간대 평균 5% 미만을 낮은 활동으로 분류하고 인접 시간대를 묶어 표시한다. 이는 구버전의 ‘GPU별 5% 미만 연속 30분’ 판정을 대체하는 새 의미이며, 모든 순간의 유휴·회수 가능성을 뜻하지 않는다.

## Namespace GPU 메모리 보조 관측 / Optional GPU memory

`gpu-memory-v1`은 기존 `namespace_usage` 주제에만 추가된다. 자동·수동 신규 집계 보고서가 같은 경로를 사용하며 RCA, 기존 활동률·이전 기간 비교·사건 계산, 주제 수, DB schema, Helm 설정은 변경하지 않는다. 과거 결과를 다시 쓰지 않는다.

- 모든 기본 활동/신원 조회와 연결 변경 검증 후 **현재 기간만 클러스터당 range 요청 1개**를 추가한다. `DCGM_FI_DEV_FB_USED/FREE` 각각의 시간당 sum/count/min/max를 원본 식별 라벨과 함께 조회한다. `[1h] offset 1ms`, step 3600을 유지한다. 15초 원본 배열은 저장하지 않는다.
- 동일 GPU UUID·Namespace·Pod·모델·노드 및 수집 라벨, 동일 시간대, 기존 활동 검증 통과, 메모리/활동 표본 수 일치(238~242)를 요구한다. 중복·신원 전환·누락·음수·비유한 값·DCGM 오류값은 메모리 판단에서 제외한다. 활동의 전환 검증을 메모리에 자동 적용하지 않는다. 표본 수 검사는 모든 순간의 동시 관측을 보장하지 않는다.
- GPU당 평균 GiB = 유효 MiB 표본 합 / 유효 표본 수 / 1024. 사용과 여유를 별도로 저장하며 장치 전체 관측이지 Namespace의 독점 사용량·할당량·예약량이 아니다. 모델별 평균을 유지한다. 메모리 값은 낮은 활동의 원인, 메모리 부족, 성능 병목, 회수 가능성을 증명하지 않는다.
- `hourly_gpu_memory` evidence에 조회식·기간·시간 집계·수집 상태를 저장한다. `rows[].gpu_memory`에는 시간대별 사용/여유 평균·표본 수·결측 사유·근거 참조와 유효 표본 가중 기간 평균을 저장한다. 해석에 선택된 기존 활동 시간대에 메모리 수치가 있으면 `memory_used/free` metric과 `finding.memory_refs`를 추가한다. 기존 metric ID/값은 유지한다. CSV/HTML은 기존 공통 exporter가 추가 metric·AI 문장을 그대로 출력한다.
- 보조 조회는 클러스터당 최대 20초, 공통 deadline 종료 30초 전까지만 사용한다. 기존 총 호출·응답 바이트 한도를 공유한다. 실패해도 기존 활동 결과·품질을 낮추거나 0으로 채우지 않는다. 메모리는 확인 불가로 남긴다. 결과 전체 크기 제한은 계속 적용된다.
- AI는 선택된 메모리 근거의 대상·시간·사용/여유 값을 토큰으로 참조한다. 활동과 메모리를 함께 보고 요청량·상주 프로세스 기록 확인을 제안할 수 있다. 정책 대비 효율·배분 변경·새 장애 진단은 하지 않는다. 형식/참조 검증 실패 시 기존 계산 요약을 유지하며 자연어의 의미 정확성은 별도 검토 대상이다.

Memory-supported interpretation fixes the observation target, time window and numeric values in code (`observation_source=calculated`). The LLM writes the meaning and suggested checks; the UI labels these separately. Invalid AI prose falls back to calculated findings. This does not change activity, comparison or incident calculations.

메모리 근거를 사용한 설명은 대상·시간·수치를 코드가 확정하고(`observation_source=calculated`), AI는 의미와 확인할 점을 작성합니다. 화면에서도 둘을 구분합니다. 검증을 통과하지 못한 AI 문장은 계산 요약으로 대체하며 기존 활동률·이전 기간 비교·사건 계산은 유지합니다.

## Namespace별 조건부 제안

`namespace-pattern-advice-v3` consumes existing hourly rows; it adds no numeric metric, source query, quality rule, allocation policy or RCA behavior. / 기존 시간대별 결과를 읽는 설명 전용 경로이며 산식·조회·품질 판정·RCA는 유지합니다.

- An eligible activity hour has finite 0–100 activity, GPU IDs, no exclusion reasons and 238–242 samples per GPU. All observed models must be eligible for the identical interval. Adjacent windows must retain each model's GPU IDs and remain within one KST date. / 모든 모델의 같은 시간·신원 근거가 필요합니다. 짧은 연결 변경 구간은 기존 활동 계산에서 유효해도 전체 시간 제안에는 사용하지 않습니다.
- Capacity review requires at least two consecutive hours with stable GPU identities, every model's hourly activity ≥80% and a positive Namespace Pending peak with all 240 workload evaluation points in each interval. Evaluation coverage is not proof of raw scrape completeness or instantaneous concurrence. It proposes checking allocation/guarantees, scheduler reasons and available cluster resources, never an additional GPU quantity. / 높은 활동과 대기가 같은 시간 구간에 집계된 경우의 조건부 확대 검토입니다.
- Other positive observed Pending peaks lead to scheduler/placement checks, including partial windows with an explicit limitation. Unknown activity cannot be described as low activity. / 활동이 낮거나 미확인인 대기를 GPU 부족이나 할당 확대 근거로 단정하지 않습니다.
- At least two consecutive eligible hours below 5% in every model, without a known positive Pending peak, can form a scheduling candidate. Unknown Pending is labelled unknown and must be checked before a trial. If any aligned model's memory ratio is ≥80%, suggest checking resident serving/cache instead. Missing memory is not zero. / 해당 Namespace의 후보 시간이며 클러스터 가용성 보장이 아닙니다.
- These are editorial selection thresholds, not changes to stored activity, low-activity-hour, memory or workload metrics. Source periods, IDs, observation, conditions, evidence/value references and supporting hours are stored in `narrative[].advice`; existing `text` fields keep HTML readers compatible. CSV and original `topics` remain unchanged.
- Preserve distinct operational questions per Namespace, reserve cluster/kind representatives and offer at most 12 candidates; the LLM prioritizes two or three distinct proposals (at most 5) and represents offered clusters when possible. It does not fill five slots with duplicate scheduler checks. It writes a concise `summary` combining observation and proposed next step, against allowed fact IDs; it does not also generate duplicate meaning/next-check prose for each candidate. Summary target/period/activity/pending/memory/completed/elapsed/pending_change tokens or exact matching literals (including same-date short period notation) are validated against that candidate; references are replaced with stored values and exact literal prose is kept unchanged; `summary_source=llm` records authorship. Unsupported numbers/names, missing context and invented job absence are rejected. Scheduling stays conditional; unknown Pending remains in stored observations/conditions and the visible pre-execution note instead of becoming zero. Legacy section meaning/next_check fields retain the same stored summaries for readers expecting those fields. The UI displays at most five summary bullets and collapses fixed observations and conditions; code still supplies fixed observations and action labels. Invalid format, invented observations or unsupported allocation claims trigger one repair, then the existing calculated fallback. Input stays ≤32KB with the existing token/deadline/cancellation budget. Candidates absent means the previous interpretation path remains active.
- Policy integration, allocation execution/quantity, multi-day recurrence and actual waiting/execution duration are not inferred. Fixed wording/claim guards cannot prove all natural-language semantics; real replies still require evidence-based review. / 정책·할당 수량·매일 반복 패턴·별도 대기/실행 시간 측정은 후속 범위입니다.


### 조건부 운영 제안의 선별·완료 연결

현재 기준과 순서는 [Ops 전용 운영 제안](../../../ops-agent/README.md#namespace별-조건부-운영-제안)이 담당한다. `namespace-pattern-advice-v3`는 기존 `topics`·수치·품질·CSV를 바꾸지 않고 narrative에 후보별 근거와 선별 요약을 저장한다. `selection.criteria`는 설명 후보의 기준 revision이며 실제 부서 정책이 아니다. `source_hours`와 `completed_jobs`는 기존 결과의 해당 대상·기간에 속하는 표본이다. 완료 표본 수·경과시간 범위와 시간대별 처음/마지막 대기 최대값은 이 표본만 참조한다. 대기 건수는 대기 시간이 아니고 경과시간은 순수 연산시간이 아니다. 앞 구간이 일부 표본이면 이를 보존하며 마지막 구간이 불완전하면 대기 변화 참조를 만들지 않는다. 근거 공백은 정상·완료 0으로 해석하지 않는다.

후보를 상한으로 잘라도 각 클러스터와 운영 질문 종류를 보존하는지, 같은 Namespace의 다른 시간대 후보가 남는지, 기간 밖 Job이 섞이지 않는지 검수한다. 모델 출력의 단위 중복·잘림·잘못된 참조는 계산 대체 상태를 유지하며 문장을 손으로 고쳐 AI 결과로 저장하지 않는다. 자동·수동은 같은 Worker 경로의 회귀 검사를 수행하되 운영 신규 발행과 구별한다.


## 사건·요약·증거

- Ops 전용 읽기 전용 repeatable-read snapshot에서 기간 내 고유 사건 ID를 센다. webhook 수신 횟수를 사건 수로 세지 않는다. 이전 기간도 같은 snapshot에서 읽는다.
- 사건의 저장된 `gpu_uuid`와 전체 동일 증상의 해시로 반복을 묶는다. 증상 표시만 512자로 제한한다. UUID가 없으면 반복 분류에서 제외한다. 같은 원인이라고 단정하지 않는다.
- RCA 결과는 공개 결과 ID/hash만 참조하고 본문·Runbook·조치 본문을 복사하지 않는다. 알람 상태는 보고서 생성 snapshot 시점이며 실시간 상태나 복구 완료가 아니다.
- 결정적 코드가 수치·판정·근거 문장을 만든 뒤 Ops 전용 `report_interpretation.py`가 주제별 1~3개 근거를 선택해 `observation`(변화), `meaning`(의미와 한계), `next_check`(대조할 사항)를 한국어로 작성한다. 수치·대상은 선택한 finding/metric 참조를 코드가 치환한다. 계산·자료 부족 판정·CSV는 변경하지 않는다. 정책·효율·회수·원인·복구 판단은 범위 밖이다.
- `ops-interpretation-v2`는 저장된 시간당 metric 중 같은 Namespace/모델/GPU 집합의 인접 유효 구간을 설명 근거로 제공합니다. 변화 폭은 근거 선택 순서에만 쓰며 새 분석 metric/이상 판정을 만들지 않습니다. null·관측 공백·구성 변화·품질 이유가 있는 구간은 이 설명용 쌍에서 제외합니다. 사용 가능한 쌍이 있으면 관측 문장에 대상·전후 기간·전후 값을 모두 참조하고 확인 문장에 같은 대상·변화 후 구간을 포함해야 합니다. 이전 기간 비교 제한을 유지하며, 이 조건은 사건 주제에 적용하지 않습니다.
- 입력은 주제별 30개 finding, 전체 32KB 이하로 한정한다. 형식·참조·지원하지 않는 주장 검증에 실패하면 최대 1회 보정 요청 후 결정적 요약으로 복귀한다. 모델 미설정·입력 상한 초과도 결정적 요약을 유지한다. 기존 원격 불확실성·취소 예외는 공통 Worker로 전파한다. 자연어 검증은 의미의 완전한 증명이 아니다.
- 성공 narrative는 주제 ID, 위 세 필드, `source_fact_ids`, `value_refs`, `evidence_refs`, 코드가 붙인 해석 한계와 HTML 호환 `text`를 저장하며 `quality.report.method=llm_interpreted`로 식별한다. 웹에서 주제별 **AI 운영 해석**으로 표시한다. 구 `llm_prioritized` 결과는 선택된 계산 문장으로 구분하고 실패는 AI로 표시하지 않는다. 기존 결과는 재작성하지 않는다.
- D 원본·Loki·Node 조건 전체 이력·메모리/에너지 원본은 신규 경로에서 조회하지 않는다. 증거에는 시간당 집계, 식별 검증, 쿼리·범위·버전·소요 시간과 간결한 사건 snapshot을 저장한다.
- 시간대별 sum/count와 관측 GPU ID, 품질, 버전을 남겨 후속 월간 재집계의 기반을 보존한다. 이번 주간은 Mimir의 7일 자료를 집계하며 기존 일일 보고서 문장을 합치지 않는다. 별도 집계 테이블·캐시·자동 재사용은 구현하지 않는다.

## 크기 제한과 영향 범위

초기 보호 상한: 요청 4클러스터, 선택 Namespace 100개/클러스터, 실제 관측 Namespace 100개/기간 전체, 고유 GPU 256개/기간 전체, 응답 250,000점/쿼리, 전체 조회 응답 8MiB, 결과 8MiB, 사건 2,000건/기간, 원격 호출 80회, 호출당 30초, 작업 계산 경로 최대 900초(공통 Worker의 더 짧은 deadline 우선). 상한 초과는 잘라서 정상으로 표시하지 않는다. 응답 예산·조회 실패는 해당 클러스터의 판단을 보류하고, 결과/식별자 상한 위반은 실패로 처리한다. **상한은 검증된 운영 수용량 보장이 아니다.** 최대 클러스터 규모·동시 실행 부하는 배포 후 별도 측정해야 한다.

RCA 코드·D 정의·프롬프트·Runbook·Incident 접수·DB schema는 변경하지 않았다. 공통 Python에는 보고서 Store 주입/claim별 설정 선택, 신규 주제 검증, CSV 대상·기간 열을 추가했다. 공통 실행·evidence 저장·Grafana transport는 재사용한다. 완전히 별도 DB나 별도 MCP 서비스로 나누는 변경은 아니다.

| 파일 | 역할 |
|---|---|
| [report_contract.py](../../../ops-agent/src/ops_agent/report_contract.py) | 기간·주제·예산·버전 |
| [report_queries.py](../../../ops-agent/src/ops_agent/report_queries.py) | Ops 소유 PromQL 및 수집 |
| [namespace_summary.py](../../../ops-agent/src/ops_agent/namespace_summary.py) | 신원 검증·시간대 집계·이전 기간 비교 |
| [incident_summary.py](../../../ops-agent/src/ops_agent/incident_summary.py), [report_store.py](../../../ops-agent/src/ops_agent/report_store.py) | 사건 snapshot과 반복 비교 |
| [aggregate_report.py](../../../ops-agent/src/ops_agent/aggregate_report.py) | 신규 보고서 조립·근거·요약 |
| [AggregateReport.tsx](../../../frontend/src/components/AggregateReport.tsx), [AggregateReportForm.tsx](../../../frontend/src/pages/AggregateReportForm.tsx) | 비교표·그래프·사건·일일/주간 요청 |
| [shared contract](../../../shared/contract/report.go), Backend proxy/validation/schedules, JC submit/config | 요청 검증·새 실행 프로필 고정·일정 |

## 배포·호환

새 프로필 `report-aggregate-v1`의 kind=report, criteria=report-aggregate-v1을 Backend가 고정한다. source/Helm/3+3 예시에도 추가했다. 기존 JC 사용자 설정에 프로필이 없을 때 새 JC의 기본 map이 보충하는 로딩 방식을 유지한다. Chart의 `configuration.jobController` 자체는 여전히 완전 교체 객체이므로 운영 values에도 새 프로필을 명시해 관리하는 것이 좋다. 기존 replica·slot·메모리·PVC 값을 덮어쓸 필요가 없다.

Frontend·Backend·JC·Ops Worker를 같은 성공한 빌드로 맞춘다. 구 Worker와 새 요청이 섞인 전환 중에는 신규 요청을 중지해야 한다. DB migration·기존 증거 삭제·과거 결과 재계산은 없다. 롤백 전 신규 큐를 비우고 기존 이미지를 복구한다. 새 결과의 표시에는 새 Frontend가 필요하다. 기존 O 주제 요청과 자동 일정은 기존 경로를 유지하므로 새 일정으로 명시적으로 전환한다.

## 검증 기록과 남은 확인

2026-10-13 로컬: Python 3.11.16, Go 1.26.2, Node 22.23, Helm 3.17.3. CI의 Python 3.12/Node 24와는 다르다. 생산 DB를 테스트에 사용하지 않았다.

- 최신 main 통합 후 두 Agent 전체 **1,150개 통과 / skip 0개**(112.91초, 기존 MCP deprecation warning 3개). 사건 snapshot의 기간 경계·Namespace 격리 사례 포함. 실제 로컬 PostgreSQL·Backend·JC·Worker·NAT·공식 Grafana MCP 프로세스 E2E 포함. Grafana/LLM upstream은 fixture다. D 설정 파일이 없어도 새 보고서가 공개되는 경로와 기존 RCA 회귀를 확인했다.
- 네 Go 모듈 vet/race/build 통과. Backend/Incident DB E2E와 UI 최종 결과는 해당 모듈 QA를 참조한다.
- Helm 렌더·패키징·mirror 검사, CI 도구 22개 통과. 운영 배포 검증을 의미하지 않는다.
- CPC-1의 2026-10-12 하루에 실제 Grafana/Mimir에서 최종 3개 쿼리를 실행했다. `kube_node_labels`는 배포 데이터에서 없어서 독점/공유 설정의 판정 근거로 사용하지 않았다.

| 같은 하루 자료 | 이전 원본 GPU+연결 Pod | 신규 집계+신원 검사 |
|---|---:|---:|
| 반환 표본 수 | 103,716 | 1,968 (98.10% 감소) |
| compact Grafana DataFrame JSON | 1,698,241 bytes | 167,175 bytes (90.16% 감소) |
| 관측한 요청 시간 | 별도 2요청 391ms+121ms | 3쿼리 총 546ms |

JSON 크기는 압축 네트워크 전송량이나 PostgreSQL 디스크 크기가 아니다. 시간 측정은 캐시·실행 순서가 통제되지 않았고, **조회 시간 단축을 입증하지 못했다**. 신규 계산 함수는 동일 원본에서 만든 집계 입력으로 20회 실행한 중앙값 약 5ms이나, 수집·LLM·저장까지 포함한 전체 보고서 시간은 아니다.

기존 시간가중 계산과 새 표본 평균의 모델별 차이: A100 40GB 약 0.000058%p, A100 80GB 약 0.001487%p. 시간대별 최대 차이는 각각 약 0.001097%p, 0.387701%p였다. 산식이 동일하다고 주장하지 않는다. 로컬 화면은 실제 계산 코드를 사용한 합성 데이터이며 운영 보고서 발행 결과가 아니다.

미검증: CPC-2 새 집계 경로 전체, 실제 7일/직전 7일의 품질·상한, 256GPU/다중 동시 부하, 운영 LLM을 포함한 신규 보고서 최종 공개·삭제·재시도, 최대 규모 Mimir 비용. 배포 후 일일 단건→주간 단건→동시 실행 순서로 확인한다. 자료 누락이나 상한이 잦으면 관측 계약/범위를 먼저 조정하고 원본 전체 조회로 되돌리지 않는다.


## Report detail producer follow-up / 보고서 상세 자료 생성 보완 — 2026-10-13

PR #113 added the presentation; this follow-up supplies its optional result fields from Ops alone. No RCA implementation, shared D registry, activity PromQL/formula, database schema or Helm setting changes.

PR #113의 화면에 필요한 결과 필드를 Ops에서 채운다. RCA 구현·공통 D·활동률 쿼리와 계산식·DB 구조·Helm 설정은 변경하지 않는다.

| Producer / 생성 파일 | Result and boundary / 결과와 조건 |
| --- | --- |
| `namespace_summary.py` | Model/hour `nodes` come from existing verified GPU Hostname–Pod node matches; model nodes union only valid hours. Previous-only/unverified nodes are not current observations. `previous_valid_hours`/`previous_expected_hours` explain comparison availability without altering means. / 기존 신원 검증을 통과한 노드만 보존하고, 이전 기간만 있거나 확인되지 않은 노드는 현재 노드로 표시하지 않는다. 비교 가능 시간 정보는 설명용이며 평균을 바꾸지 않는다. |
| `report_store.py` | Empty `symptom` falls back to recorded `target.title`; display is capped at 512 characters and the full normalized title is hashed. Read only GPU UUID, node (including `k8s_node_name` fallback), component, alert name and test marker. / 증상 누락 시 저장된 제목을 사용하며 원본 전체·RCA 본문은 추가 조회하지 않는다. |
| `incident_summary.py` | `summary.categories` groups distinct incidents by cluster and XID/SXID code, otherwise component/alertname/unknown. Includes current/previous counts, current nodes, firing/test counts and incident IDs. / 알림 종류별 현황이며 동일 원인이나 동일 GPU 반복 장애를 추론하지 않는다. 기존 UUID·동일 증상 반복 집계와 구분한다. |
| `aggregate_report.py` | Deterministic text describes up to three current categories and their nodes (up to three), previous counts and unidentified-device limitations. / 코드가 상위 알림 종류와 노드·이전 건수를 설명하며 새 LLM 해석은 추가하지 않는다. |

The merged UI shows every cluster/Namespace table row, with one graph per cluster. Namespace toggles affect charts only; all-off keeps an empty grid. Model-specific activity is not averaged across GPU models. Alarm status uses the stored `status_as_of` snapshot, not live recovery state.

화면은 클러스터·Namespace별 한 줄로 전체 표를 보여주고 그래프만 선택해서 비교한다. 모델이 다른 GPU의 활동률을 임의로 합치지 않는다. 알림 상태는 저장된 `status_as_of` 기준으로, 현재 상태나 복구 완료를 뜻하지 않는다.

Deploy the new Ops image and generate a new aggregate report to populate these fields. Existing immutable reports are not rewritten; missing source metadata stays unknown. No new settings or migration are required. Local observation snapshots and preview files are not shipped. Production generation after deployment remains to be checked.

새 Ops 이미지 배포 후 새 집계 보고서를 생성해야 추가 필드가 저장된다. 과거 보고서는 재작성하지 않으며 원천에 없는 정보는 미확인으로 유지한다. 설정 추가·마이그레이션은 없고 로컬 관측 데이터·미리보기 파일은 배포 코드에 포함하지 않는다. 운영 배포 후 신규 보고서 생성 확인은 별도로 필요하다.


## Verified GPU connection transitions / 검증된 GPU 연결 변경 — 2026-10-14

A count of two identities during an hour does not prove simultaneous duplication. Keep the hourly aggregates, then verify only selected GPU hours with more than one identity. The raw reads are instant range vectors, so they retain real scrape timestamps rather than Prometheus lookback-resampled timestamps.

한 시간 안에 식별 정보가 두 종류 나타났다는 사실만으로 동시 중복이라고 판단하지 않는다. 기본 시간별 집계는 유지하고, 선택 대상 GPU에서 여러 식별 정보가 관측된 시간대만 실제 표본 시각으로 대조한다.

- `report_queries.py`: one-hour GPU UUID-filtered and Pod-name-filtered reads, after all base aggregates, at most 16 GPUs per batch and 32 additional calls / 60 seconds per report, leaving at least 30 seconds before the calculation deadline. Existing 80-call / 8 MiB / per-call and overall deadlines still apply. Other Namespace identities participate in the transient GPU overlap check, but are not stored in the selected Namespace's evidence. A failed or skipped check never validates an hour and does not invalidate unrelated hours.
- `identity_transitions.py`: verify distinct, non-overlapping identity intervals, a continuous 238–242-sample GPU hour, 14–30-second within-series gaps, at most 30-second boundary/inter-identity gaps, unchanged physical node/model, and no conflicting aliases or explicit shared/MIG attribution. Pod records must retain one UID and node, value 1, continuous non-overlapping intervals, and cover the GPU interval within one 15-second scrape tolerance. Same-UID Pod metadata transitions are allowed; different UIDs or overlapping records remain unverified.
- `namespace_summary.py`: the proof must match the original full identity, sample sum/count/min/max, global identity count, Pod UID and Pod sample count. Only that Namespace's original observed samples contribute to the unchanged sum/count formula. Unlabelled intervals are neither assigned nor zero-filled. Existing missing/overlap/MIG/range guards remain.
- `aggregate_report.py`: explain the number of verified transition hours and the observed-sample basis. Record `quality.gpu_attribution_version=gpu-identity-transitions-v1`. The input profile/result format remains `report-aggregate-v1`; additive row/hour fields are compatible with the current UI and export.

추가 증거 `gpu_identity_transitions`에는 검증된 식별 정보, 구간의 처음·마지막 시각/표본 간격, sum/count/min/max, Pod UID·표본 수와 검증 버전을 남긴다. 원본 표본 배열은 저장하지 않는다. 실패한 조회의 원문 오류/비밀값도 저장하지 않는다. 이전 증거만 있으면 기존의 보수적인 판정을 유지한다.

**Scope / 범위:** Ops 조회·검증·설명과 테스트만 변경한다. RCA·공통 D·공통 Worker·DB·Helm은 변경하지 않는다. 기존 발행 결과와 일정은 재작성하지 않으며 새 보고서부터 적용된다. 현재/이전 기간 완전성, 전체 주제 partial 판정, 저활동·이전 기간 비교 조건은 별도로 완화하지 않는다.

**Limits / 한계:** One identity reappearing within an hour (A→B→A) can have overlapping first/last bounds and remains conservatively excluded. This bounded recovery is not a universal lifecycle or exclusive-allocation proof. Missing raw retention, large churn, or budget exhaustion retains partial analysis. It adds targeted read cost; no latency reduction is claimed. Weekly/max-size/concurrent production load and new-image publication need deployment validation.

실제 CPC-1·CPC-2의 2026-10-13 세 시간대, GPU·시간대 조합 13건에서 확인한 연결 변경은 모두 시각상 비중복이었다. 조회 성공·표본 수만으로 추정하지 않고 실제 처음/마지막 시각과 Pod UID를 대조했다. 이 결과로 ‘모든 연결 변경은 정상’이라고 일반화하지 않는다. 상세 로컬 검사 범위는 [Agent QA](../../../agents/QA.md)를 따른다.

## Ops 작업 대기·배치 완료 보조 관측

Namespace 주제의 `workloads`는 [workload_queries.py](../../../ops-agent/src/ops_agent/workload_queries.py)와 [workload_summary.py](../../../ops-agent/src/ops_agent/workload_summary.py)가 담당한다. RCA D·공통 계산·기존 활동/메모리/사건 수치는 변경하지 않는다. 자동/수동 신규 집계 보고서가 같은 경로를 사용한다. 이전 결과와 일정은 재작성하지 않는다.

| 항목 | 정의 | 제한 |
| --- | --- | --- |
| 대기 Pod | 일반 컨테이너가 `nvidia.com/gpu`를 요청하고 Pending인 Pod의 시간당 관측 최대 수 | GPU 부족 원인이 아님. init 전용 요청, MIG, Pod 생성 전 Run:ai 대기열은 대상 밖 |
| 미배치 Pod | 위 Pending 중 scheduled=false의 시간당 관측 최대 수 | 이미지 다운로드 등 배치 후 준비 대기와 구분. 각 최대값의 발생 시각이 같다고 가정하지 않음 |
| 실행 Pod | 같은 범위에서 Running인 Pod의 시간당 관측 최대 수 | 실제 연산·서빙 준비 완료 보장 아님 |
| 확인된 완료 Job | GPU 요청 Pod의 controller owner가 Job이며, 생성/시작/완료 timestamp 순서와 분석기간 내 완료가 확인된 고유 Job | 전체 완료 수가 아닌 관측된 표본. 소멸이 빠르거나 scrape 사이에 끝난 Job은 누락 가능. 같은 이름 재생성/중복/시간 충돌 제외 |
| 완료 표본 평균 소요 | 확인된 Job 각각의 completion_time − start_time 평균 | CPU 준비·대기·재시도 등이 포함될 수 있음. GPU 연산 시간이나 서빙 성능 아님 |

현재 기간에 클러스터당 range 조회 두 개를 추가한다(HTTP step 1시간). 내부 `[1h:15s]` subquery는 **같은 시각의 GPU 요청·Pod UID·상태·Job owner를 연결하기 위한 서버 내 평가**다. 시간별 최고 대기를 서로 다른 Pod의 최고값 합으로 부풀리지 않으며 15초마다 HTTP 요청을 보내지 않는다. 반환·저장은 시간 집계다. 다만 Mimir 스캔 비용은 실데이터 규모 검증이 필요하다. 보조 조회 전체는 클러스터당 20초·기존 전역 호출/바이트/표본 제한 안에 두고 AI용 시간을 남긴다.

Pod 상태는 namespace 내 GPU 요청 Pod 모두와 매칭되는 표본만 받는다. 구간 평가 수는 원본 scrape 완전성을 증명하지 않으며 관측 최대치만 제공한다. 누락은 null이며 표에서 자료 없음으로 표시한다. 완료 표본이 없다고 완료 0건으로 단정하지 않는다. Job 이름을 재사용하면 KSM Job gauge에 UID가 없으므로 해당 이름의 모호한 결과를 제외한다. 최대 Namespace 수 초과 시 보조 관측을 보류한다. 기존 Namespace 상태 판정은 그대로이며 보조 관측은 partial/unavailable로 별도 관리한다.

### Alloy 준비 및 실제 검증 경계

기존 [전송 목록 도구](../../../tools/ci/extend_observation_forwarding.py)에 `--include-report-workload`를 추가했다. 기존 지표·cluster_id·전송 목적지를 유지하면서 `kube_pod_status_phase`, `kube_pod_status_scheduled`, `kube_pod_owner`, `kube_job_created`, `kube_job_status_start_time`, `kube_job_status_completion_time`을 추가한다. 기본 실행은 읽기 전용이며 `--apply`는 별도 운영 적용이다. 기존 확장 옵션으로 재실행해도 작업 지표를 제거하지 않는다. Helm values 변경으로 외부 Alloy 설정이 자동 반영되지는 않는다.

로컬 변경은 운영 Alloy를 바꾸지 않는다. 적용 후 두 클러스터에서 Pod UID·Job 이름·실제 상태/시각과 Mimir를 대조하고, Pending → 배치 → Running → 성공 완료 순서의 표본을 확보해야 한다. init/MIG/Run:ai queue는 별도 계약 전까지 해석하지 않는다. 과거 미전송 자료의 복원은 보장하지 않는다. 보조 지표 실측 확인 후 AI의 선택 기준·문구를 종합 조정하며, 현재 연결만으로 운영 해석 품질 개선이 검증됐다고 주장하지 않는다.

KSM 의미 기준: [Pod metrics](https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/workload/pod-metrics.md), [Job metrics](https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/workload/job-metrics.md).


### Cross-metric consistency / 보조 지표 간 일관성

All additions preserve the existing activity rows, metric IDs/values, prior-period comparison, and incident totals. They share cluster/Namespace and report boundaries, but not the same population or aggregation operation.

| 지표 | 대상·집계 기준 | 함께 읽을 때 지켜야 할 범위 |
| --- | --- | --- |
| GPU 활동률 | 연결이 검증된 GPU·모델의 시간별 sum/count, 기간값도 표본 수 가중 평균 | 기존 수식·이전 기간 비교 조건을 유지 |
| GPU 메모리 | 같은 GPU 식별·시간 구간에서 used/free 표본 수가 활동률과 일치할 때 GPU당 평균 | 유효 시간만 평균하며 활동률과 유효 시간 집합이 다를 수 있음. 동일 표본 시각까지 증명하지는 않음. 전체 시간 검증 시 available, 일부 시간은 partial, 없으면 unavailable |
| 대기·미배치·실행 Pod | GPU를 요청한 일반 컨테이너를 가진 Pod의 UID 기준 상태를 같은 평가 시각에 결합 후 Namespace별 시간 최대 | 물리 GPU 수가 아님. GPU 배정 전 대기 Pod도 포함하므로 활동률 행이 없는 Namespace도 별도 보존. 각 최대치가 발생한 시각은 다를 수 있음 |
| 완료 Job·평균 소요 | 생성/시작/완료 시각과 GPU 요청 Pod의 Job owner를 확인한 표본, 이름별 중복 제거 | 완료 시각은 [보고 시작, 보고 종료)에 포함. 시작이 이전 기간이어도 전체 start→completion 소요를 사용하며 보고 기간으로 잘라 계산하지 않음. 전체 완료 수나 GPU 연산 시간이 아님 |

Memory and workload queries currently cover the current report period only; no prior-period change is inferred for them. Workload subquery evaluation counts are not raw scrape coverage. Period peaks do not establish co-occurrence with an activity dip, and successful Job samples do not measure serving throughput. Their own missing status never changes the existing activity calculation/status.

메모리와 작업 보조 지표는 현재 기간만 조회하므로 이전 기간 대비 증감을 만들지 않는다. 활동률과 메모리의 다른 유효 시간, 시간 평균과 기간 최고값, GPU와 Pod/Job 개수를 같은 기준의 수치처럼 직접 비교하지 않는다. 실제 작업과의 대조·운영 LLM 문구 검증은 별도다.

Invalid numeric samples remain in duplicate detection so an invalid duplicate cannot be discarded to accept another value. Job timestamps must come from one consistent source label set; mixed sources, changed lifetimes and ambiguous duplicates are excluded. If no valid workload state or completed Job remains, its status is unavailable. These guards affect optional Ops observations only.
