# Ops Report Agent — 일일·주간 집계 보고서

Ops 전용 집계 보고서의 수집·해석 계약이다. 검증 환경과 배포 여부는 [Agent QA](../../../agents/QA.md)에서 구분한다. 신규 요청에만 `report-aggregate-v1`을 적용하며 과거 보고서·일정은 변경하지 않는다.

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
- Namespace 제안의 메모리 근거는 코드가 대상·시간·사용/여유 참조를 조립하고 기존 값으로 치환한다. 활동과 메모리를 함께 보고 요청량·상주 프로세스 기록 확인을 제안할 수 있다. 정책 대비 효율·배분 변경·새 장애 진단은 하지 않는다. 형식/참조 검증 실패 시 기존 계산 요약을 유지하며 자연어의 의미 정확성은 별도 검토 대상이다.

Memory-supported interpretation fixes the observation target, time window and numeric values in code (`observation_source=calculated`). The LLM writes the meaning and suggested checks; the UI labels these separately. Invalid AI prose falls back to calculated findings. This does not change activity, comparison or incident calculations.

메모리 근거를 사용한 설명은 대상·시간·수치를 코드가 확정하고(`observation_source=calculated`), AI는 의미와 확인할 점을 작성합니다. 화면에서도 둘을 구분합니다. 검증을 통과하지 못한 AI 문장은 계산 요약으로 대체하며 기존 활동률·이전 기간 비교·사건 계산은 유지합니다.

## Namespace별 조건부 제안

`namespace-pattern-advice-v3` consumes existing hourly rows; it adds no numeric metric, source query, quality rule, allocation policy or RCA behavior. / 기존 시간대별 결과를 읽는 설명 전용 경로이며 산식·조회·품질 판정·RCA는 유지합니다.

- An eligible activity hour has finite 0–100 activity, GPU IDs, no exclusion reasons and 238–242 samples per GPU. All observed models must be eligible for the identical interval. Adjacent windows must retain each model's GPU IDs and remain within one KST date. / 모든 모델의 같은 시간·신원 근거가 필요합니다. 짧은 연결 변경 구간은 기존 활동 계산에서 유효해도 전체 시간 제안에는 사용하지 않습니다.
- Capacity review requires at least two consecutive hours with stable GPU identities, every model's hourly activity ≥80% and a positive Namespace Pending peak with all 240 workload evaluation points in each interval. Evaluation coverage is not proof of raw scrape completeness or instantaneous concurrence. It proposes checking allocation/guarantees, scheduler reasons and available cluster resources, never an additional GPU quantity. / 높은 활동과 대기가 같은 시간 구간에 집계된 경우의 조건부 확대 검토입니다.
- Other positive observed Pending peaks lead to placement/preparation record checks using same-window unscheduled evidence, including partial windows with an explicit limitation. Unknown activity cannot be described as low activity. / 활동이 낮거나 미확인인 대기를 GPU 부족이나 할당 확대 근거로 단정하지 않습니다.
- At least two consecutive eligible hours below 5% in every model, without a known positive Pending peak, can form a scheduling candidate. Unknown Pending is labelled unknown and must be checked before a trial. If any aligned model's memory ratio is ≥80%, retain the resident serving/cache candidate and also preserve any remaining consecutive subwindow that independently satisfies the original scheduling conditions. Missing memory is not zero. / 해당 Namespace의 후보 시간이며 클러스터 가용성 보장이 아닙니다.
- Distinct `repeated_activity` and `relative_activity` candidates preserve separated observation periods and candidate/reference windows respectively; see [R1/R2 criteria and permitted choices](#반복-고활동상대적-저부하-후보). They do not relax the preceding kinds. / 별도 근거로 자원 배분 점검 또는 조건부 시간 변경 시범 검토를 제안하며 실제 LLM 유용성은 후속 검증합니다.
- These are editorial selection thresholds, not changes to stored activity, low-activity-hour, memory or workload metrics. Source periods, IDs, observation, conditions, evidence/value references and supporting hours are stored in `narrative[].advice`; existing `text` fields keep HTML readers compatible. CSV and original `topics` remain unchanged.
- Preserve distinct operational questions per Namespace, existing cluster/completion coverage and at most five writing candidates. `ops-interpretation-incident-names-v8` asks the LLM for concise observation meaning and decision reasons in `summary`; code appends the candidate-specific check purpose, prerequisites and operating action, then its canonical evidence suffix. Writing-only `option/action`, `writing_focus`, `required_checks`, `required_prose_terms` and evidence tokens are excluded from initial/partial-repair input. Stored `decision_context`, candidate criteria, calculations, source references, 360/220-character limits and one repair remain unchanged. Before final composition, raw reasons face bounded observation and reason-only checks. Direct instructions, affirmative operating predicates, recommendations, obligations and review-target classifications are rejected with one reason-only code, rather than sent through the old complete-prose prerequisite checker. Capacity shortage/cause assertions are rejected separately; negated or unknown claims are distinguished. These finite Korean patterns do not guarantee complete semantic detection. `summary_source=llm` identifies the reason author; the final summary combines LLM reasons with code-authored actions and evidence. Existing `summary_parts.decision/evidence` are exact slices, and old readers still receive the full summary. Incident v6 sections add code-authored `check_target`; `next_check` contains only LLM check prose. Legacy sections without this field retain their three-field display. See the writing and validation boundaries below.
- Policy integration, allocation execution/quantity, multi-day recurrence and actual waiting/execution duration are not inferred. Fixed wording/claim guards cannot prove all natural-language semantics; real replies still require evidence-based review. / 정책·할당 수량·매일 반복 패턴·별도 대기/실행 시간 측정은 후속 범위입니다.


### 조건부 운영 제안의 선별·완료 연결

현재 후보 기준은 `namespace_advice.py`의 기존 임계값과 자격 검사를 따릅니다. 아래는 현재 동작이며 후속 선별 목표와 구분합니다.

| 후보 | 현재 자격·범위 |
|---|---|
| 할당 확대 검토 | 같은 GPU 구성의 유효 연속 두 시간 이상 모든 관측 모델의 시간 평균 활동률이 80% 이상이며 같은 시간의 완전한 Pending 관측이 양수. 실제 할당·가용·스케줄러 사유 확인 후 조건부 검토이며 추가 수량은 산정하지 않음 |
| 실행 시간대 | 같은 구성의 유효 연속 두 시간 이상 활동률 5% 미만이며 알려진 양수 Pending이 없음. 미확인 대기·예약·가용 GPU 확인 후 시범 실행 검토 |
| 상주 메모리 | 낮은 활동 구간에 같은 시간의 장치 메모리 사용 비율 80% 이상. 상주 목적과 메모리 유지 필요성 점검이며 독점 사용·여유 자원 판정이 아님 |
| 대기 점검 | 양수 Pending과 같은 시간의 미배치 근거로 배치/준비/미확인 단계의 점검 기록을 구분. Namespace 대기는 시간·KST 날짜로 묶고 연결 변경·활동 누락 구간의 활동·메모리는 미확인 |
| 완료·대기 흐름 | 같은 Namespace의 유효 완료 표본·Job 경과와 후보 기간 Pending을 연결. 대기 변화의 마지막 시간대는 완전 관측이어야 하며 활동 연결 공백은 그대로 유지 |

`ops-operating-choices-v6`는 기존 종류별 순위를 제거하고 `decision_context()`로 운영 선택을 먼저 구분합니다. `decision`은 `choice`(선택 질문), `scope`(허용 판단), `reason`(직접 근거), `needed`(추가 확인), `option`(조건부 선택)을 포함하며 최초·보완 입력과 채택 narrative에 보존됩니다.

| 판단 범위 | 현재 의미와 선별 |
|---|---|
| `conditional_option` | 기존 자격을 만족한 할당 검토, 완전한 대기 관측이 연결된 실행 시간대 후보. 실제 조치 전 조건은 여전히 미확인 |
| `targeted_check` | 미배치/준비 단계, 낮은 활동·높은 장치 메모리, 후반 대기가 남은 완료 등 구체적인 점검 선택. 대기 단계가 미확인이거나 시간대 후보의 대기가 불완전하면 `specific_evidence=false`로 구분 |
| `observation_only` | 별도의 운영 변경을 뒷받침할 연결이 없는 완료 참고. 기존 대표 완료 조건을 충족하면 필수 포함하며 선택 가치가 높은 것처럼 과장하지 않음 |

정렬은 위 판단 범위, 구체적인 점검을 좁히는 근거, 활동 연결 여부, 관측 구간 길이, 대기 최대값, 완료 표본 수, 대상·기간·ID 순입니다. 이는 설명 후보를 정하는 재현 가능한 순서이며 긴 구간·큰 대기 수를 지연 시간이나 운영상 심각도로 해석하지 않습니다. `writing_candidates()`는 대표 완료와 각 클러스터를 확보하고, 같은 판단 범위·근거 구분 안에서 다른 선택을 우선합니다. 미확인 단계가 다른 질문이라는 이유만으로 더 구체적인 점검을 밀어내지 않습니다. 남은 자리는 기존 같은 클러스터/종류 제한 안에서 이미 선택한 것과 다른 선택만 보탭니다. 최대 12개 전달·최대 5개 출력·대표 완료 필수·클러스터 포함·완료 안의 대기 자동 제외를 유지하고 최대 5개 사전 선별의 `selection.decisions`에 전달한 선택과 필수 완료 여부를 남깁니다. 최종 전달 순서는 판단 범위·근거 정렬을 따르며 대표 완료가 반드시 첫 항목은 아닙니다. 5개 초과 클러스터에서는 기존 최대 12개 전달과 LLM 선택 경로를 유지합니다.

기존 80%·5%·80%와 연속 두 시간은 설명 후보 자격이며 운영정책·부족 판정 기준이 아닙니다. 원래 `topics`·산식·품질·CSV는 바뀌지 않습니다.

[Ops 전용 운영 제안](../../../ops-agent/README.md#namespace별-조건부-운영-제안)은 실행 흐름의 요약입니다. 지표별 의미·판단 경계·질문별 다음 확인·문장 품질과 1~4단계 기준은 이 명세의 [운영 해석 기준과 후속 설계](#운영-해석-기준과-후속-설계)에서 관리한다. 문서의 품질 목표를 런타임 검증 통과로 간주하지 않는다. `namespace-pattern-advice-v3`는 기존 `topics`·수치·품질·CSV를 바꾸지 않고 narrative에 후보별 근거와 선별 요약을 저장한다. `selection.criteria`는 설명 후보의 기준 revision이며 실제 부서 정책이 아니다. `source_hours`와 `completed_jobs`는 기존 결과의 해당 대상·기간에 속하는 표본이다. 완료 표본 수·경과시간 범위와 시간대별 처음/마지막 대기 최대값은 이 표본만 참조한다. 대기 건수는 대기 시간이 아니고 경과시간은 순수 연산시간이 아니다. 앞 구간이 일부 표본이면 이를 보존하며 마지막 구간이 불완전하면 대기 변화 참조를 만들지 않는다. 근거 공백은 정상·완료 0으로 해석하지 않는다.

후보를 상한으로 잘라도 각 클러스터와 운영 질문 종류를 보존하는지, 같은 Namespace의 다른 시간대 후보가 남는지, 기간 밖 Job이 섞이지 않는지 검수한다. 모델 출력의 단위 중복·잘림·잘못된 참조는 계산 대체 상태를 유지하며 문장을 손으로 고쳐 AI 결과로 저장하지 않는다. 자동·수동은 같은 Worker 경로의 회귀 검사를 수행하되 운영 신규 발행과 구별한다.


## 사건·요약·증거

- Ops 전용 읽기 전용 repeatable-read snapshot에서 기간 내 고유 사건 ID를 센다. webhook 수신 횟수를 사건 수로 세지 않는다. 이전 기간도 같은 snapshot에서 읽는다.
- 사건의 저장된 `gpu_uuid`와 전체 동일 증상의 해시로 반복을 묶는다. 증상 표시만 512자로 제한한다. UUID가 없으면 반복 분류에서 제외한다. 같은 원인이라고 단정하지 않는다.
- RCA 결과는 공개 결과 ID/hash만 참조하고 본문·Runbook·조치 본문을 복사하지 않는다. 알람 상태는 보고서 생성 snapshot 시점이며 실시간 상태나 복구 완료가 아니다.
- 결정적 코드가 수치·판정·근거 문장을 만든 뒤 Ops 전용 `report_interpretation.py`가 `observation`(관측), `meaning`(의미와 한계), `next_check`(대조할 사항)를 구성한다. Namespace의 기존 관측·의미·확인 경로는 1~3개 근거 선택을 유지하고, Namespace advice는 기존 후보 선별 계약을 따른다. 사건은 `incident_focus`가 사용할 근거 전체와 관측·확인 접두부를 고정하고 모델의 fact_ids·observation을 사용하지 않으며, LLM은 의미와 확인 내용만 작성한다. 수치·대상은 선택한 finding/metric 참조를 코드가 치환한다. 계산·자료 부족 판정·CSV는 변경하지 않는다. 정책·효율·회수·원인·복구 판단은 범위 밖이다.
- `ops-interpretation-v2`는 저장된 시간당 metric 중 같은 Namespace/모델/GPU 집합의 인접 유효 구간을 설명 근거로 제공합니다. 변화 폭은 근거 선택 순서에만 쓰며 새 분석 metric/이상 판정을 만들지 않습니다. null·관측 공백·구성 변화·품질 이유가 있는 구간은 이 설명용 쌍에서 제외합니다. 사용 가능한 쌍이 있으면 관측 문장에 대상·전후 기간·전후 값을 모두 참조하고 확인 문장에 같은 대상·변화 후 구간을 포함해야 합니다. 이전 기간 비교 제한을 유지하며, 이 조건은 사건 주제에 적용하지 않습니다.
- 입력은 주제별 30개 finding, 전체 32KB 이하로 한정하며, Namespace advice와 함께 보낼 때 사건은 정렬 후 최대 12개를 전달한다. 코드가 작성한 사건 관측에는 모델 문장 길이 상한을 적용하지 않고, 모델 의미·확인 내용은 각각 450자, 확인 접두부를 합친 next_check는 900자 이내로 검증한다. 형식·참조·지원하지 않는 주장 검증에 실패하면 최대 1회 보정 요청 후 결정적 요약으로 복귀한다. 모델 미설정·입력 상한 초과도 결정적 요약을 유지한다. 기존 원격 불확실성·취소 예외는 공통 Worker로 전파한다. 자연어 검증은 의미의 완전한 증명이 아니다.
- 성공 narrative는 주제 ID, 위 세 필드, `source_fact_ids`, `value_refs`, `evidence_refs`, 코드가 붙인 해석 한계와 HTML 호환 `text`를 저장하며 `quality.report.method=llm_interpreted`로 식별한다. 웹에서 주제별 **AI 운영 해석**으로 표시한다. 구 `llm_prioritized` 결과는 선택된 계산 문장으로 구분하고 실패는 AI로 표시하지 않는다. 기존 결과는 재작성하지 않는다.
- D 원본·Loki·Node 조건 전체 이력·메모리/에너지 원본은 신규 경로에서 조회하지 않는다. 증거에는 시간당 집계, 식별 검증, 쿼리·범위·버전·소요 시간과 간결한 사건 snapshot을 저장한다.
- 시간대별 sum/count와 관측 GPU ID, 품질, 버전을 남겨 후속 월간 재집계의 기반을 보존한다. 이번 주간은 Mimir의 7일 자료를 집계하며 기존 일일 보고서 문장을 합치지 않는다. 별도 집계 테이블·캐시·자동 재사용은 구현하지 않는다.

## 운영 해석 표시와 HTML

집계 보고서 제목은 ‘2026년 10월 22일 GPU 클러스터 운영 분석 보고서’처럼 분석 대상 KST 날짜를 사용한다. 주간은 시작·마지막 분석 날짜를 표시하며 작성일과 구분한다. 수집·집계 주제 수는 제목에 붙이지 않는다.

운영 콘솔과 기존 웹 상세, Backend HTML 다운로드는 저장된 `narrative[].advice`를 클러스터별 카드로 나누고 카드 안에서 Namespace로 묶는다. 공통 작성 방식·선별 근거는 한 번만 표시하며 Namespace 안에 별도 카드를 겹치지 않는다. 클러스터와 Namespace는 이름 오름차순으로 표시하고, 같은 Namespace 안의 제안은 저장된 순서를 유지한다. 이름을 확인하지 못한 대상은 마지막에 별도로 표시한다. 이 표시 순서는 운영상 중요도나 실행 우선순위가 아니다. 각 카드는 기존 해석 카드의 디자인을 유지한다. 제목은 ‘AI 운영 해석’, 다음 줄은 ‘대상 클러스터 : `cpc-1`’처럼 역할과 대상을 나눠 표시한다. 클러스터명은 음영 인라인 코드로 구분한다. 내부 Namespace 표기는 라벨·콜론·값의 열을 맞추고 보조 라벨과 이름의 굵기를 낮춰 바로 아래 제안에 연결한다. 소제목은 배경 배지 없이 유형별 색상의 글자로 표시하고 바로 아래 본문과 시작선을 맞춘다. 색상 소제목 → 저장된 AI 제안 본문 → 관측/비교 시간·GPU 모델 → 상세 근거 순서로 읽는다. 일반적인 유형 설명은 ‘판단 근거와 적용 조건’ 안으로 옮기고, 시간대 시험 제안은 과거 관측이며 반복성·실행 조건 확인이 필요하다는 짧은 안내를 첫 화면에 유지한다. 자세한 제한은 상세 근거의 해석 기준·관측 근거·적용 조건과 함께 읽는다. AI 본문은 일반 굵기로 표시하며 원문을 줄이거나 재작성하지 않는다. Namespace 사이에는 구분선과 넉넉한 간격을 두고, 같은 Namespace의 제안은 구분선 없이 간격으로 나눈다. Namespace 안의 소제목·본문·시간·상세 근거는 같은 시작선에 맞추며 모바일에서는 추가 들여쓰기를 없앤다. 현재 화면 HTML 저장은 개별 제안의 상세 근거 펼침 상태를 유지하고, 나머지 기존 상세 정보는 펼쳐 저장한다. Backend HTML은 개별 제안 상세를 접어 표시한다. 같은 대상의 떨어진 제안은 인접 표시하므로 전체 줄 순서는 바뀔 수 있다. 선별 항목 수·우선순위 계산·근거·AI 원문·CSV·저장 결과/hash는 바꾸지 않는다. 대상이 미확인인 항목은 서로 합치지 않는다. Incident 주제는 이 Namespace 묶음에 넣지 않는다.

- 모든 알려진 제안 유형에 종류별 색을 가진 소제목을 붙인다. 색은 제안 종류의 구분이며 심각도·실행 우선순위가 아니다. GPU 추가 할당, 작업 시간대 시험, 시간대 비교·시험, 시작 지연, 배치 완료·남은 대기, 메모리 점유, 여러 시간대 활동·대기를 구분한다. 미기록 유형은 기존 제안명 또는 ‘운영 점검’으로 표시한다.
- 일반형은 `period`의 관측 구간만 표시한다. `schedule_candidate`는 낮은 활동 구간만 표시하며 존재하지 않는 비교 구간을 만들지 않는다. `relative_activity`는 `reference_period`의 비교 구간과 `period`의 낮은 활동 구간을 표시한다. 두 유형 모두 과거 관측이며 향후 실행 확정 권고가 아니다.
- `repeated_activity`는 `observed_periods`를 각각 표시하고 구간 사이를 연속 관측으로 잇지 않는다. 개별 구간이 없으면 ‘관측 범위 · 연속 관측 아님’으로 표시한다. KST·날짜 경계·끝 시각 제외를 명시하며 시각이 없거나 유효하지 않으면 ‘시간 범위 미확인’으로 남긴다.
- 화면 저장은 현재 렌더링된 공개 범위를, Backend 다운로드는 공개된 결과의 전체 수치와 원문을 포함한다. 두 출력은 LLM을 재호출하지 않는다. Backend는 저장 파일을 재작성하지 않고 다운로드 요청 때 표시용 HTML을 생성한다. Worker가 이미 저장한 원본 HTML artifact는 이번 표시 변경의 대상이 아니다. 원문과 정확히 일치하는 `summary_parts`만 분리한다.

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

2026-10-13 · 원격 main `f7cf8c9` 기준 과거 로컬 검증: Python 3.11.16, Go 1.26.2, Node 22.23, Helm 3.17.3. CI의 Python 3.12/Node 24와는 다르다. 생산 DB를 테스트에 사용하지 않았다.

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
| `incident_summary.py` / `incident_findings.py` | `summary.categories` groups distinct incidents by cluster and XID/SXID code, otherwise component/alertname/unknown. Includes current/previous counts, current nodes, firing/test counts and incident IDs. / 알림 종류별 현황이며 동일 원인이나 동일 GPU 반복 장애를 추론하지 않는다. 기존 UUID·동일 증상 반복 집계와 구분한다. `incident-top-type-<cluster_id>`·`incident-top-node-<cluster_id>`는 이번 기간 클러스터 사건 합이 2건 이상일 때 생성하며, 노드는 식별된 사건이 있을 때만 생성한다. 비율의 분모는 노드 미확인 사건을 포함한 해당 클러스터의 이번 기간 저장 사건 전체이며 장비 전체 장애율이 아니다. top-type의 `top_type_cluster_count`·`top_type_cluster_previous_count`는 이번·이전 기간의 클러스터 전체 사건 수이며 target은 cluster_id만 가진다. `incident-second-node-<cluster_id>`는 식별된 노드가 둘 이상일 때 건수 내림차순·노드명 오름차순의 두 번째 노드에 `second_node_count`·`second_node_share`를 저장한다. 집계용 top-node·second-node 사실은 상세에 보존하되 AI 입력에서 제외한다. `incident_focus`의 종류별 노드 관측·확인 대상과 검증은 아래 [장애 알림 해석과 출처](#장애-알림-해석과-출처)를 따른다. 최다 종류·노드는 건수 내림차순, 동률은 종류명·노드명 오름차순으로 선택하고 클러스터 건수 내림차순으로 저장한다. |
| `aggregate_report.py` | Deterministic text describes up to three current categories and their nodes (up to three), previous counts and unidentified-device limitations. / 코드가 상위 알림 종류와 노드·이전 건수·클러스터 내 비율을 계산하고, AI 해석은 저장된 사실의 참조 토큰으로 설명한다. 0건 또는 ready가 아닌 사건 주제는 AI 입력에서 제외하며 기존 계산 문장은 유지한다. |

The merged UI shows every cluster/Namespace table row, with one graph per cluster. Namespace toggles affect charts only; all-off keeps an empty grid. Model-specific activity is not averaged across GPU models. Alarm status uses the stored `status_as_of` snapshot, not live recovery state.

화면은 클러스터·Namespace별 한 줄로 전체 표를 보여주고 그래프만 선택해서 비교한다. 모델이 다른 GPU의 활동률을 임의로 합치지 않는다. 알림 상태는 저장된 `status_as_of` 기준으로, 현재 상태나 복구 완료를 뜻하지 않는다.

Deploy the new Ops image and generate a new aggregate report to populate these fields. Existing immutable reports are not rewritten; missing source metadata stays unknown. No new settings or migration are required. Local observation snapshots and preview files are not shipped. Production generation after deployment remains to be checked.

새 Ops 이미지 배포 후 새 집계 보고서를 생성해야 추가 필드가 저장된다. 과거 보고서는 재작성하지 않으며 원천에 없는 정보는 미확인으로 유지한다. 설정 추가·마이그레이션은 없고 로컬 관측 데이터·미리보기 파일은 배포 코드에 포함하지 않는다. 운영 배포 후 신규 보고서 생성 확인은 별도로 필요하다.


### 장애 알림 해석과 출처

`ops-interpretation-incident-names-v8`는 분석기간의 저장 사건으로 다음 네 항목을 해석한다. 같은 종류가 여러 노드에서 관측됐는지, 같은 노드에 다른 종류가 있는지, 보고서 작성 당시 발생 중인지, 이전 비교기간에 같은 종류의 기록이 있었는지다. 서로 다른 알림의 공통 원인·동시 발생이나 최초 장애를 추론하지 않는다. GPU UUID 수집과 기존 반복 집계는 이미 지원하며 변경하지 않는다. UUID가 없는 사건으로 동일 GPU 반복 장애를 판정하지 않는다.

- `incident-node-*` 후보는 발생 중 건수, 같은 종류의 발생 노드 수, 해당 노드·종류 건수 내림차순, 클러스터·노드·종류 이름 오름차순으로 최대 6개를 고른다. `node_alert_rca`는 이 후보의 사건 중 공개 `result_id`가 있는 건수(events)이며 RCA 본문·원인·조치 내용은 읽지 않는다. 새 DB 조회는 없다.
- AI 입력은 후보 노드 사실을 먼저 보존하고 기간 요약·최다 종류 사실을 잇는다. 기존 30개 및 Namespace 제안 동반 시 12개 한도를 유지한다. 제외된 노드 후보·입력 사실 수는 `omitted_findings`에 기록한다. 집계 관측은 최다 종류 자체의 노드별 건수이며 클러스터 전체 노드 건수와 섞지 않는다. 선택 노드 건수 합이 종류 전체와 다르면 일부 내역이라고 명시한다. 제외된 노드를 미확인 노드나 발생 없음으로 단정하지 않는다.
- `incident_focus`는 전달된 사실에서 관측과 확인 대상을 만들며 동일한 `focus`를 최초·부분 보완 입력에 전달한다. 확인 대상은 발생 중인 첫 후보, 없으면 첫 후보다. 해당 대상의 공개 RCA 건수와 선택된 같은 노드의 다른 종류를 연결한다. 최다 종류 근거가 없는 클러스터는 선택된 노드 사실로 관측을 보완한다. 두 종류의 관측 근거가 모두 없으면 기간 요약을 사용하고, 노드 사실이 없으면 확인 대상은 비워 둔다. 해석은 선택된 근거 범위이며 전체 내역은 기존 표에서 확인한다.
- 저장 필드는 `observation`(자동 집계), `meaning`(AI 작성), `check_target`(자동 선정), `next_check`(AI 작성)이다. `observation_source=calculated`와 사용한 전체 `source_fact_ids`를 유지한다. 모델의 observation·fact_ids·check_target은 채택하지 않고 코드에서 결정한다. `next_check`는 대상 접두부 없이 AI 제안만 저장하며 원문 450자 제한을 유지한다. `text`에도 네 항목을 합쳐 Backend HTML 내보내기가 확인 대상을 보존한다. 화면은 Namespace와 같은 대상 → AI 해석·확인 제안 → 접힌 판단 근거 구조를 사용한다. 확인 대상은 저장된 `check_target`과 선택 사실의 대상이 정확히 일치할 때만 짧게 표시하며 다시 선정하지 않는다. 사실이 누락되거나 맞지 않으면 저장된 확인 대상 원문을 근거에서 제공한다. 자동 관측·확인 대상 원문·선정 기준·한계·근거 링크는 펼침에 보존하고, 아래 종류별·사건별 표는 유지한다. 화면 HTML은 DOM을 복제하며 Namespace와 같은 접힌 근거와 출처를 보존한다. Backend HTML의 기존 네 항목 표시는 바꾸지 않는다. `check_target`이 없는 과거 보고서는 기존 세 항목과 저장 문장을 그대로 표시한다.
- 장애 알림에서만 `focus.ids`로 선택된 fact의 `target.cluster_id/cluster/node/alert_type` 값과 정확히 일치하는 이름은 숫자 검사에서 제외한다. 앞뒤가 영문·숫자인 부분 일치는 허용하지 않으며 한글 조사·공백·문장부호는 허용한다. `dgx01에서`, `XID 79가`는 허용하지만 `dgx010`, `XID 790`, `xdgx01`과 선택되지 않은 숫자 포함 이름은 거절한다. 이름의 대소문자·공백은 바꾸지 않는다. 이 예외는 숫자 검사에만 적용하며 금지 표현·기호 검사와 `violation_kind` 기록은 유지한다. 건수·비율·기간은 계속 토큰으로만 쓰고 Namespace 및 다른 주제의 규칙은 유지한다.
- `meaning`은 여러 노드 발생·같은 노드의 다른 종류 동반·이전 기간 기록 유무의 운영상 의미를 설명하도록 안내한다. 자동 관측·확인 대상에 이미 있는 건수·발생 중 건수·공개 RCA 수를 반복하지 않도록 안내하며, 기존 원인·동시 발생·최초 장애 추론 금지는 유지한다. 건수 반복을 새 검증 오류로 추가하지 않는다.
- 의미의 작성 지시 복사는 `incident_meaning_required`, 자리표시자는 `template_echo`로 거절한다. 의미에 특정 단어인 종류·노드가 반드시 들어갈 필요는 없다. 신규 장애·공통 원인·동시 발생 문구는 부정문에서도 `incident_overreach`로 거절한다. 확인 대상의 RCA가 없으면 결과 유무·작업 생성 상태 확인을 제안할 수 있지만 결과 검토를 전제할 수 없다. 일부만 공개됐으면 기존 결과만 대상으로 삼으며 전체 결과 검토 문구는 `incident_rca_reference`로 거절한다. 이 검사는 제한된 한국어 표현에 대한 방어이며 모든 자연어 의미를 증명하지 않는다.

0건·ready가 아닌 사건 주제 제외, 32KB 입력 상한, 최대 두 번의 호출, 정상 Namespace 문장 보존과 부분 보완 흐름은 유지한다. 비율 문턱값과 원인 분석·자동 조치는 추가하지 않는다. 실제 LLM의 문장 품질과 배포 결과는 fixture 검증과 별도로 확인한다. 첫 응답의 `number` 실패 비율·호출 수·토큰 사용량 효과는 배포 후 여러 보고서로 따로 검수한다. 과거 첫 응답이 이름 때문에 실패했는지 다른 수치 때문인지는 확정하지 않는다.


### 주제별 해석 실패 분리

서로 다른 시도에서 모든 입력 주제가 검증을 통과하면 입력 주제 순서로 해석을 구성하고 `narrative_status=complete`, `method=llm_interpreted`, `reason=repaired`로 처리하며 `topic_statuses`는 기록하지 않는다.

v7에서 도입한 주제별 검증·보존은 v8에서도 유지한다. 주제 ID·개수·순서가 안전하게 확인된 응답에서 각 주제를 독립 검증한다. 최초 응답 또는 안전하게 정리한 포장 응답에서 검증을 통과한 주제는 보완 이후에도 그대로 보존한다. 한 주제의 재검증 실패, 보완 응답의 구조 오류·미응답·입력 상한 때문에 다른 주제의 정상 문장을 삭제하지 않는다. 모호한 중복·누락·순서 오류만 있는 응답은 새 정상 근거가 되지 않으며, 원격 종료 미확인·취소 전파와 최대 두 시도·32KB·모든 기존 검증 조건은 유지한다. 검증 전에 발생하는 설정·코드 제안 사전 검사 실패는 기존 전체 계산 요약 경로다.

부분 성공의 최상위 `narrative_status`는 기존 허용값인 `failed`를 유지한다. `quality.report.method=partial_interpretation`, `topic_statuses`의 주제별 `complete|failed`가 혼합 구성을 식별한다. 성공 주제의 기존 narrative는 보존하고, 실패 주제만 `topic_id`, `interpretation_source=deterministic_fallback`, 계산 요약 `title/text`, 원본 `source_fact_ids/evidence_refs/value_refs`를 갖는다. GUI는 성공 주제의 AI 해석과 실패 주제의 계산 요약을 각각 표시하며 부분 실패를 알린다. 목록과 Backend HTML도 부분 성공을 전체 AI 성공 또는 전체 계산 요약이라고 부르지 않는다. 모든 주제 실패·모델 미설정·0건 제외·과거 보고서의 기존 의미는 유지하며 DB·공통 상태 enum·RCA 계약은 변경하지 않는다.

`unsupported_prose`는 진단에 고정된 `topic_id`, `field`, `violation_kind`를 남긴다. 분류는 `number`(토큰 밖 숫자), `symbol`(기호·URL), `forbidden_expression`(기존 금지 표현), `missing_korean`이다. 실패 로그도 같은 코드만 남기고 모델 문장·실제 걸린 표현·민감값은 기록하지 않는다. 기존 두 번의 `unsupported_prose` 기록만으로 과거 실패 주제나 문구를 소급 판정하지 않는다. 실제 LLM의 해당 문장 작성 실패가 해결됐다는 보장이 아니라, 실패 격리와 다음 진단을 위한 변경이다.


## Verified GPU connection transitions / 검증된 GPU 연결 변경 — 2026-10-14

A count of two identities during an hour does not prove simultaneous duplication. Keep the hourly aggregates, then verify only selected GPU hours with more than one identity. The raw reads are instant range vectors, so they retain real scrape timestamps rather than Prometheus lookback-resampled timestamps.

한 시간 안에 식별 정보가 두 종류 나타났다는 사실만으로 동시 중복이라고 판단하지 않는다. 기본 시간별 집계는 유지하고, 선택 대상 GPU에서 여러 식별 정보가 관측된 시간대만 실제 표본 시각으로 대조한다.

- `report_queries.py`: one-hour GPU UUID-filtered and Pod-name-filtered reads, after all base aggregates, at most 16 GPUs per batch and 32 additional calls / 60 seconds per report, leaving at least 30 seconds before the calculation deadline. Existing 80-call / 8 MiB / per-call and overall deadlines still apply. Other Namespace identities participate in the transient GPU overlap check, but are not stored in the selected Namespace's evidence. A failed or skipped check never validates an hour and does not invalidate unrelated hours.
- `identity_transitions.py`: verify distinct, non-overlapping identity intervals, a continuous 238–242-sample GPU hour, 14–30-second within-series gaps, at most 30-second boundary/inter-identity gaps, unchanged physical node/model, and no conflicting aliases or explicit shared/MIG attribution. Across the entire matched Pod hour (including unassigned observations), require one nonempty UID, value 1, 14–30-second within-series gaps and continuous non-overlapping intervals with gaps at most 30 seconds. Only a leading prefix with absent/empty node labels is allowed, and every prefix interval must end strictly before the GPU interval starts. The remaining assigned intervals must exist, match the GPU Hostname and cover the GPU interval within the existing 15-second scrape tolerance. Sum only these assigned intervals into `pod_sample_count`, matching the saved node-specific Pod aggregate. Same-UID metadata changes such as a later `pod_ip` are allowed when those checks pass. A different UID/node, overlapping intervals, an unassigned interval after assignment, or missing coverage remains excluded.
- `namespace_summary.py`: the proof must match the original full identity, sample sum/count/min/max, global identity count, Pod UID and Pod sample count. Only that Namespace's original observed samples contribute to the unchanged sum/count formula. Unlabelled intervals are neither assigned nor zero-filled. Existing missing/overlap/MIG/range guards remain.
- `aggregate_report.py`: explain the number of verified transition hours and the observed-sample basis. Record `quality.gpu_attribution_version=gpu-identity-transitions-v2`. The input profile/result format remains `report-aggregate-v1`; additive row/hour fields are compatible with the current UI and export.

추가 증거 `gpu_identity_transitions`는 `query_version=gpu-identity-transitions-v2`로 검증된 식별 정보, 구간의 처음·마지막 시각/표본 간격, sum/count/min/max, Pod UID·배정 구간 표본 수를 남긴다. 원본 표본 배열은 저장하지 않는다. 실패한 조회의 원문 오류/비밀값도 저장하지 않는다. 기존 v1 증거도 같은 집계 대조 조건으로 읽으며, 저장 결과를 재작성하지 않는다. 새 보고서는 정상 미배정→배정 연결을 인정하고 조회 배분도 달라지므로, 같은 분석 기간의 과거 보고서와 유효 시간·활동률·저활동 구간·후보·해석 입력 및 CSV 값이 달라질 수 있다. 평균 산식과 품질 판정 기준 자체는 유지한다.

**Scope / 범위:** Ops 조회·검증·설명과 이를 소비하는 웹·Backend HTML 설명 및 테스트를 변경한다. RCA·공통 D·공통 Worker·DB·Helm은 변경하지 않는다. 기존 발행 결과와 일정은 재작성하지 않으며 새 보고서부터 적용된다. 행별 현재/이전 기간 완전성, 저활동·이전 기간 비교 조건은 유지한다. 전체 주제 판정은 아래 Namespace 귀속 기준으로 개정하며 미표기 행을 단독 partial 원인으로 사용하지 않는다.

**Limits / 한계:** One identity reappearing within an hour (A→B→A) can have overlapping first/last bounds and remains conservatively excluded. This bounded recovery is not a universal lifecycle or exclusive-allocation proof. Missing raw retention, large churn, or budget exhaustion retains partial analysis. It adds targeted read cost; no latency reduction is claimed. Weekly/max-size/concurrent production load and new-image publication need deployment validation.

실제 CPC-1·CPC-2의 2026-10-13 세 시간대, GPU·시간대 조합 13건에서 확인한 연결 변경은 모두 시각상 비중복이었다. 조회 성공·표본 수만으로 추정하지 않고 실제 처음/마지막 시각과 Pod UID를 대조했다. 이 결과로 ‘모든 연결 변경은 정상’이라고 일반화하지 않는다. 상세 로컬 검사 범위는 [Agent QA](../../../agents/QA.md)를 따른다.

### Partial observation diagnostics / 부분 산출 진단

`ops-observation-diagnostics-v3` explains the resulting exclusions without feeding diagnostic messages back into calculation or interpretation. The v2 connection validation and collection order can change eligible observations and their downstream calculations; diagnostics alone do not. `missing_inputs` retains query failures and adds `namespace_current_attribution_missing` when any requested cluster has no current-period named Namespace row. Unattributed observations remain stored but are not treated as proof of unallocated GPUs. Backend HTML translates both the new code and legacy `namespace_observations_missing` in the readable limitations while retaining stored codes in raw details.

- `hourly_gpu_activity.quality.transition_verification` records each candidate batch's hour end, selected GPU IDs, `not_checked`/`query_failed`/`checked` outcome, safe reason and first failed GPU/Pod condition group. Pod failures distinguish `pod_uid_unverified`, `pod_samples_unverified`, `pod_continuity_unverified`, `pod_node_unverified` and `pod_coverage_unverified`; old `pod_interval_unverified` audits retain their broader explanation. Query-budget and deadline exhaustion leave skipped entries without inventing query evidence. Missing datasource/base inputs record `transition_skip_reason`; the number of candidate hours is then unknown. Rejection records do not retain out-of-scope Namespace identities or raw samples. Query success alone does not mean all identities or the resulting row-hour passed.
- After all base collection, the collector verifies all current periods before previous periods. Within each period it takes one batch per cluster in request order and repeats, including when a single hour requires several 16-GPU batches; exhausted/empty/unavailable clusters do not block others. Both periods share 32 transition calls / 60 seconds. Before transition reads, reserve a maximum of four supplemental calls per requested cluster (memory 1, workload 2, context 1) plus four collector-verification calls for the report. Unavailable sources can use fewer calls; this is a maximum reservation, not promised consumption. Admit a two-call batch only when both the 32-call transition cap and the remaining 80-call allowance after reservation permit it. `transition_query_budget_reserved` distinguishes reserved capacity from `transition_query_budget_exhausted`; actual total-limit and deadline reasons remain distinct. Existing byte, point and overall deadline limits remain; calls are reserved, bytes/time are not. Skipped audit records trigger no requests. A batch can contain up to 16 GPUs; batch count, GPU-hour count, cluster-hour count and excluded Namespace/model row-hour count are different units.
- `topics[].quality.observation_diagnostics` contains a version, plain-language `summary`/`messages`, affected `rows` for current/previous periods, and per-cluster/period `collection` counts/reasons with evidence references. `checked_batches` counts completed queries even when proof fails; `failed_batches` counts unavailable query/response processing. When base inputs are unavailable, skipped hour/GPU-hour counts are null because the target set is unknown. Row reasons count distinct excluded hours, and different reasons may overlap. Transition audit reasons apply only to named Namespace rows excluded for `duplicate_or_changed_gpu_identity`, `pod_identity_unverified` or `incomplete_hour_or_sampling_interval`. Missing/conflicting labels and other exclusions that transition verification cannot repair retain their own reasons; cluster-level collection audits remain unchanged. Proof-to-aggregate mismatches are distinct from skipped/failed queries. Previous-period reasons are summarized before comparison discards old hour details.
- After interpretation, deterministic `messages` and separate `unattributed_messages` are appended to output `limitations`. Unattributed row details remain in diagnostics, but their exclusions/comparison gaps are not added to the topic cause `summary`/`messages`. `clusters_without_current_attribution` lists affected requested cluster IDs. Diagnostic messages are excluded from the writer payload; the writer receives the newly verified calculations through its existing path. The existing web component displays causes before expandable per-target details; both HTML export paths reuse limitations. CSV uses the calculated metrics, including any changed eligible observations. Stored references and prior results remain immutable. Readers tolerate absent, v1 or v2 diagnostics and do not infer historical budget exhaustion.

Acceptance requires the 7+7 current / 9+7 previous batch fixture: 28 calls cover both current periods and the remaining four calls cover one previous batch per cluster; later batches retain budget-skip audits. Include unequal/empty/unavailable clusters, more than 16 GPUs in one hour, shared deadline and cancellation, the 80-call limit, granular Pod failures, assigned-only count-to-aggregate matching, metadata/collector changes, legacy result compatibility, and automatic/manual publication with API and both HTML paths. Check intended calculation changes independently from output-only diagnostics. Verification belongs in [Agent QA](../../../agents/QA.md).

**Remaining budget work / 미구현 예산 개선:** The 32-call cap is unchanged: reservation can reduce transition reads and does not increase previous-period coverage. With full transition demand, four clusters, two single-page datasources and four collector reads, 30 transition calls leave all 16 supplements and four collector reads within 79 total calls, instead of an 81st attempted call being blocked. This bound assumes that discovery/base collection fits first; pagination or failures can change the count. The query counter includes blocked attempts. Byte/deadline exhaustion can still prevent later collection. Measure before proposing a larger transition cap, multi-hour reads or previous-period skipping; weekly/concurrent production capacity is not established.

### Namespace status basis / Namespace 활동 판정 기준

New results store `topics[].quality.namespace_status_basis=attributed_rows_with_current_cluster_coverage_v1`. Only rows with a Namespace participate in the topic's existing ready/partial/blocked calculation. Every requested cluster must also have at least one named row in the **current summary**, before current/previous comparison; a `current_not_observed` row carried from the previous period does not qualify. Ready still requires every included row to be ready/comparable and no base query errors. A missing cluster prevents ready; any remaining attributed activity yields partial, otherwise blocked. The incident-topic combination rule is unchanged.

This explicitly revises the former decision to count unattributed rows in overall topic quality. Query success with zero observations, and loss of all Namespace labels in one cluster, cannot be hidden by another cluster's valid rows. A selected Namespace scope with no current GPU activity also prevents ready: mixed observed/idle scopes become partial and wholly unobserved activity remains blocked. No new `not_applicable` state is inferred. The diagnostic says current selected-scope attribution is absent, not that a collection fault or unallocated GPU has been established.

This cluster guard detects whole-cluster gaps only. It does not prove that every Namespace/node/GPU is represented. Keep unlabelled rows, metrics, hours, evidence and CSV unchanged, with separate informational messages stating that allocation and full attribution completeness are unknown. Existing row formulas, thresholds, candidate selection and reference validation are unchanged. Workload cross-checks and automatic allocation classification are deferred.

The additive quality fields change status meaning, not the result status vocabulary or required request schema. Historical reports/artifacts remain immutable; readers display stored states and only explain the new basis when its marker is present. The same evidence can therefore produce an old partial report and a new ready report while its metrics/candidates/CSV remain identical. Verify all-missing, mixed-cluster, selected-idle, previous-only, base-failure and incident-combination cases, plus web and both HTML export paths.

### Verified KSM collector handoffs / 검증된 KSM 수집기 교체

`collector_identity.py` separates collector transport labels (`instance`, `exporter_pod`) from Pod/Job identity. A single source in disjoint hourly buckets may change collectors without creating a new Job. When multiple collectors occur in the **same hour**, their counts are never blindly summed: `report_queries.py` reads the original samples for that hour and requires disjoint, continuous source intervals, identical retained identity labels, and an exact match to each saved aggregate. Concurrent sources, gaps, duplicate timestamps/fields, contradictory values and unverified metadata changes remain excluded.

Pod 연결에는 동일 UID·노드, 값 1, 기존 238–242개 표본·시간 경계·표본 간격 조건을 유지한다. Job은 각 원천에 생성 시각 근거가 있어야 하며, 기존 생성/시작/완료 시각 안정성·순서·보고기간·이름 재사용 검사를 그대로 적용한다. 다른 원천의 불완전한 시각 필드를 조합해 완료를 만들지 않는다. 원본 snapshot은 변경하지 않고, 검증된 보기만 기존 집계에 전달한다. 평균 활동률·경과시간 산식과 LLM 검증 조건은 바꾸지 않는다.

Optional collector verification runs after existing aggregate, GPU-transition, memory, workload and context reads: at most **4 raw calls, 64 target names per call and 20 seconds per report**, with the existing 80-call / 8 MiB / per-response point limits and at least 30 seconds before the collection deadline. It does not expand or consume the separate 32-call GPU-transition allowance. Exhaustion, unavailable raw retention or failed proof preserves conservative exclusion. `quality.collector_handoffs` stores compact source/time/value bounds; `quality.collector_verification` records checked hours, verified group counts and a safe failure code. Raw sample arrays and upstream error text are not stored. Existing saved reports are not rewritten; without proof, same-hour ambiguity remains excluded.

## 저장된 작업 유형·GPU 요청 연결

`workload_context.py`는 기존 저장 지표를 현재 보고기간에만 조회하고 `namespace_usage.workload_context`에 보충 근거를 저장한다. 자동·수동 보고서는 같은 경로를 사용한다. 기존 활동률·메모리·대기·완료 수치, CSV, 후보 선별 및 LLM 검증 조건은 유지한다. 수집 설정을 바꾸거나 과거 보고서를 덮어쓰지 않는다.

| 연결 대상 | 필요한 저장 근거·연결 기준 | 허용하는 설명 / 금지하는 추론 |
|---|---|---|
| 작업 유형 | `kube_pod_labels`의 테스트 purpose/profile/execution, 같은 cluster·Namespace·Pod·UID·시간 | 서비스/연구/배치 **부하 모의 테스트** 구분. service-wave를 실제 serving, research-wave를 실제 training으로 읽지 않는다. |
| GPU 요청 | `kube_pod_container_resource_requests{resource="nvidia_com_gpu"}`, 일반 컨테이너별 중복 값 일치 후 합계 | Pod의 일반 컨테이너 요청량. init 컨테이너를 포함한 스케줄링 요청·물리 장치 실제 할당·여유 GPU 수로 바꾸지 않는다. |
| 배치 상태 | 같은 UID의 `kube_pod_info.node`와 양수 `kube_pod_status_phase` | 관측 당시 노드 배정/미배정과 Pod 상태. 노드 배정을 연산 시작, Pending을 자원 부족으로 단정하지 않는다. |
| 완료 작업 유형 | `kube_pod_owner`의 Job 연결과 기존 검증된 완료 Job의 cluster·Namespace·이름·생성~완료 기간 | 기존 완료 기록의 일부 Pod에 연결된 유형. 같은 유형만으로 같은 입력량·성능·소요시간을 보장하거나 남은 작업 종료를 예측하지 않는다. |

연결은 1시간 구간의 15초 평가 240개, 변하지 않은 요청량·연결 정보를 요구한다. 이는 원본 scrape 전체 또는 매 순간 실제 실행을 증명하지 않는다. 중복·충돌·잘못된 수치·UID 없음·시간대 안의 상태/라벨/노드 전환은 제외한다. 선택 Namespace와 조회 근거의 범위를 둘 다 검사하며 현재 라벨을 과거에 소급하지 않는다. 라벨/Job owner가 없으면 요청·상태 연결은 보존하되 유형/소유자는 미확인으로 남긴다. 관측이 바뀐 짧은 작업은 이 보충 자료에서 빠질 수 있으며 기존 완료 집계에서 삭제하지 않는다.

LLM에는 이미 선별된 후보의 정확한 시간대에 해당하는 유형·상태별 보충 자료만 전달한다. 알려진 테스트 라벨 값만 정해진 의미로 바꾸고 임의 라벨 문자열을 지시로 보내지 않는다. 일부 작업만 연결됐다는 범위를 유지한다. 테스트의 `queue_design=pod-antiaffinity`는 제출 의도이며 실제 대기 원인이 아니다. 유형이 미확인인 `runai-test1` 등을 임의로 서빙·캐시·학습으로 분류하지 않는다. 새 연결만으로 기존 제안 자격을 넓히지 않는다.

웹은 기존 보고서 안의 접힌 ‘작업 유형·GPU 요청·노드 배정 근거’에서 유형별 요청 범위, 완료 Job 연결, 작업별 관측 시각과 근거 링크를 보여준다. 요청 범위는 여러 시점의 Pod별 값이며 Namespace 동시 합계가 아니다. 자료가 없는 구 보고서는 이 영역을 표시하지 않는다. HTML/CSV 다운로드의 기존 수치 출력은 유지하며 이 보충 표의 내보내기는 아직 지원하지 않는다.

추가 조회는 기존 활동·신원·메모리·작업 조회가 끝난 뒤 클러스터당 최대 20초 범위에서 실행한다. 기존 호출·응답·결과 크기 상한은 그대로이며 초과 자료를 잘라 완전하다고 표시하지 않는다. 긴 기간/대규모 Namespace에서의 부하·결과 크기와 운영 자동 발행은 별도 검증 대상이다.

LLM 작성 입력은 연결 사실(`decision.known`)과 필요한 기록(`decision.needed`)을 구분하고 관측 현상과 판단 이유만 설명하게 한다. `writing_decision`의 작성용 완성 문장·행동은 입력에서 제외하고 코드가 응답 복사본에 점검 목적·조건·행동을 붙인다. 저장 `decision_context`는 작성용 보강과 구분한다. 일부 Pod의 테스트 유형·GPU 요청·노드 상태를 전체 업무·활동률·원인으로 확대하지 않는다. 이미 연결된 유형은 재확인하지 않고 완료 경과를 순수 실행시간이나 종료 예측으로 바꾸지 않는다. 코드 행동은 Q1의 기존 조건부 추가 할당 범위와 R1의 점검 범위를 구분한다. 대기 단계별로 요청을 충족할 노드 유무·선택 조건 또는 이미지 다운로드·초기화 기록에서 알아낼 내용을 명시하며 실패·지연을 전제하지 않는다. 후보 자격·순위·수치·참조는 유지한다.

표의 ‘연결된 라벨’ 열은 저장된 profile/execution/queue-design을 ‘작업 라벨의 의미’ 왼쪽에 표시한다. 연결 자료가 없으면 라벨이 없다고 단정하지 않으며, 임의 업무 라벨은 아직 해석하지 않는다.

**남은 근거:** 실제 업무 purpose(training/serving 등)의 표준 라벨 계약, 실제 장치 할당, 초기화 컨테이너를 포함한 스케줄링 요청, quota/예약/노드 제약, 보관된 스케줄러 이벤트. 이 정보 없이 추가 GPU 수·회수 가능량·대기 원인을 확정하지 않는다.

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

## 운영 해석 기준과 후속 설계

이 절은 운영 해석의 지표 의미·판단 경계·문장 품질과 **1~4단계 설계와 남은 목표**의 상세 기준입니다. 현재 구현은 [Namespace별 조건부 제안](#namespace별-조건부-제안)과 [Ops README](../../../ops-agent/README.md#namespace별-조건부-운영-제안)에 구분해 설명합니다. 아래 사례는 기대 판단을 검토하는 가상 자료이며 실제 LLM 결과나 운영 검증 기록이 아닙니다.

- [지표 의미와 판단 경계](#수집-지표에서-운영-판단까지)
- [1단계 · 운영 질문](#질문별로-어떤-답을-쓰는가-후속-개발-목표)
- [2단계 · 필요한 근거](#필요한-근거-정의-후속-개발-목표)
- [3단계 · 해석 범위와 S01~S25 사례](#해석-범위-정의-후속-개발-목표)
- [4단계 · 후보 선별과 T01~T14 사례](#후보-선별과-우선순위-정의-후속-개발-목표)
- [단계 간 연결과 구현 전 확인](#14단계의-연결과-구현-전-확인)
- [구현 범위와 결정 대기 항목](#구현-범위와-결정-대기-항목)
- [선별과 문장 품질 검수](#선별과-문장-품질은-별도로-확인) · [미구현 보강 항목](#현재-기준에서-추가로-발전시킬-항목)

### 수집 지표에서 운영 판단까지

[현재 후보 조건](#namespace별-조건부-제안)과 [Ops README의 현재 동작](../../../ops-agent/README.md#namespace별-조건부-운영-제안)은 **현재 코드의 기준**입니다. 아래는 그 후보를 운영자가 이해할 판단으로 설명하기 위한 기준입니다. 문장 품질 검토 기준을 제품의 통과/탈락 검사와 혼동하지 않습니다. 이번 문서 보강은 수집·계산·후보 임계값·검증 조건을 바꾸지 않습니다.

| 근거 | 현재 보고서에서 읽는 의미 | 판단에 사용하지 않는 의미 |
|---|---|---|
| GPU 활동률 | 연결 GPU의 유효 시간대별 평균. 후보 구간의 표시는 시간·모델별 평균의 최소~최대 | Namespace 독점 사용률, 실제 할당량, GPU 부족·연산 포화, 순간 최대 성능 |
| 장치 메모리 사용 비율 | 같은 GPU 신원·시간대에서 검증한 사용량 ÷ (사용량 + 여유량). 값이 있는 시간만 연결 | Namespace가 예약한 메모리, 메모리 대역폭 사용률, OOM·성능 병목 |
| Pending·미배치 Pod | GPU를 요청한 Pod 상태의 시간대별 관측 최대 개수. 상태와 배치 여부를 구분 | 대기 시간, 동일 Pod의 연속 대기, GPU 부족이라는 확정 사유 |
| 성공 완료 Job·경과시간 | 후보 구간에 성공 완료가 확인된 표본과 각 Job 시작~완료의 최소~최대. 시작은 후보 구간보다 이를 수 있음 | 순수 GPU 실행시간, 평균 대기시간, 전체 제출 대비 완료율·처리량·성능 개선 |
| 사건·노드·알림 종류 | 저장된 고유 사건의 범위·건수·작성 당시 상태와 공개 조사 참조 | 현재 장애·실제 복구·같은 GPU의 반복 원인. UUID·증상 식별 부족은 그대로 표시 |

Namespace가 같아도 보고서 하루 평균 활동률과 다른 시간대의 대기를 한 상황처럼 묶지 않습니다. `source_hours`의 같은 구간·모델·GPU 신원을 확인하고, 없는 연결은 미확인으로 둡니다. 대기 최대 7개와 평균 활동률 20%를 함께 관측했더라도 “GPU가 남는데 작업을 못 돌렸다”는 결론은 아닙니다. 대기 사유·작업 목적·정책과 연결하지 않은 값은 추가 확인 대상입니다. 표나 원천에 요청량·라벨이 존재해도 현재 `observed_values`·후보 근거에 제공되지 않은 실제 할당량·작업 목적은 LLM이 안다고 취급하지 않습니다.

**Pending과 미배치의 차이.** [Kubernetes의 Pod 단계 정의](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-phase)에서 Pending에는 스케줄 대기뿐 아니라 이미지 다운로드 등 실행 준비도 포함됩니다. 저장된 `unscheduled_peak`는 GPU 요청 Pending Pod 중 `PodScheduled=false`의 시간대 최대값입니다. [후보 구성](../../../ops-agent/src/ops_agent/namespace_advice.py)은 같은 기간의 유효 값을 `source_hours`와 선택적 요약 참조로 연결해 먼저 대조할 기록을 구분합니다. 정확한 유효성·존재/부재 조건과 한계는 [미배치 연결 범위](#구현-범위와-결정-대기-항목)를 따릅니다. 높은 활동과 양수 Pending은 현행 검토 후보 조건일 뿐, 실제 자원 부족·연산 포화의 증거가 아닙니다. Pending은 Namespace 단위이며 GPU 모델별 대기로 나뉘지 않으므로 확대할 모델도 지목하지 않습니다.

**낮은 활동의 대상.** Q3는 그 Namespace에 연결된 GPU의 낮은 활동 시간대를 검토합니다. 연결 정보만으로 독점 점유·실제 할당량을 확정하지 않으며, 클러스터의 미할당 GPU 시간대를 찾는 질문도 아닙니다. 먼저 연결된 작업이 추가 요청을 받을 수 있는지, 그 시간에 할당 유지가 필요한지, 별도 GPU를 확보할 수 있는지 확인해야 합니다. 메모리는 이 활용 가능성을 점검하는 반대·제약 근거이지, 낮으면 추가 실행이 가능하다는 증거가 아닙니다.

### 질문별로 어떤 답을 쓰는가 (후속 개발 목표)

**후속 개발 목표 · 운영 질문 정의 / Planned operational questions.** 보고서는 운영자가 우선 검토할 선택과 그 이유를 제안해야 합니다. 질문은 운영 결정에서 출발하며 현재 후보 종류가 질문의 범위를 제한하지 않습니다. 아래 정의는 현재 구현 설명과 구분하는 설계 목표입니다. 이번 문서 변경으로 실행 코드·기존 임계값·통과/탈락 조건은 바뀌지 않습니다.

| 운영 질문 | 제안할 운영 선택 | 답변이 설명할 이유와 조건 |
|---|---|---|
| **Q1. 대기가 있는 Namespace는 할당 확대와 실행 조건 점검 중 무엇을 먼저 검토할까?** | 근거에 따라 할당 확대 검토, 실행 조건 점검 우선, 또는 판단 보류를 제안합니다 | 높은 시간 평균 활동률과 양수 Pending 최대값이 각각 관측된 구간을 근거로 선택한 이유를 설명합니다. 최대값만으로 같은 Pod의 지속 대기나 동시 자원 압박을 주장하지 않습니다. 실제 할당·가용 자원·스케줄러 사유를 확인하기 전에는 GPU 부족이나 증설 수량을 확정하지 않습니다 |
| **Q2. 대기 구간의 실행 조건은 무엇부터 점검할까?** | 활동과 대기가 함께 확인된 구간은 그 대비를 점검 이유로 쓰고, 활동이 미확인이면 관측된 대기의 사유 확인으로 범위를 좁힙니다 | Q1의 선택을 구체화하는 질문이며 독립 불릿을 반드시 만들지는 않습니다. 별도로 제시하려면 대상 구간이나 점검 이유가 달라야 합니다. 낮은 활동과 미관측 활동을 구분하며, Pending·미배치·Running 상태만으로 특정 대기 원인을 정하지 않습니다 |
| **Q3. 이 Namespace에 연결된 GPU의 낮은 활동 시간대를 추가 작업에 활용할 수 있을까?** | 관측 날짜의 구간을 활용 가능성 점검 대상으로 제시하고, 조건 확인 후 시범 실행을 검토하거나 제안을 보류합니다 | 연결 작업의 추가 요청 수용·할당 유지 필요성부터 확인하고 예약·마감·가용 GPU를 대조합니다. 기존 Pod가 사용 중인 GPU를 다른 Job이 바로 쓸 수 있다고 가정하지 않습니다. Q4는 같은 결정에 대한 메모리 제약 점검이며 독립 조언을 강제하지 않습니다. 하루 관측을 반복 일정으로 일반화하지 않습니다 |
| **Q4. 연산 활동과 메모리 점유를 함께 보면 어떤 운영 선택이 필요한가?** | 작업 목적을 먼저 확인할지, 시간대 검토에 참고할지, 추가 판단을 보류할지 제안합니다 | 두 관측의 대비가 선택에 어떤 의미가 있는지 설명합니다. 낮은 활동·높은 메모리 외의 조합도 질문의 범위에 포함하되, 현재 지원 범위와 아직 필요한 기준은 아래 미구현 보강 항목에서 구분합니다. 메모리 여유만으로 공유·축소·회수를 권하지 않습니다 |
| **Q5. 완료 기록과 대기를 함께 볼 때 어떤 실행 기록을 먼저 대조할까?** | 유효한 같은 구간 대기 맥락이 있으면 실행 순서·배치 기록 대조, 없으면 완료·경과 관측 설명 또는 비교 보류로 제한합니다 | 완료 시각·경과시간·대기 최대값을 구분합니다. 경과 차이나 대기 0만으로 실행 이상·작업 조건 차이를 만들지 않습니다. 실제 실행 시작·동등한 작업 조건 없이는 성능 우열을 판단하지 않습니다 |

**공통 답변 목표는 `대상·시간 → 우선 검토할 선택 또는 보류 판단 → 그 이유 → 남은 조건`입니다.** 단순 수치 나열과 일반적인 “확인하세요”로 끝내지 않습니다. 대기/할당 검토와 작업 시간대 검토는 같은 비중으로 두고, 질문에 필요한 근거가 더 분명한 내용을 먼저 제안합니다. 메모리·완료 분석도 별도의 선택을 도울 근거가 있으면 우선할 수 있습니다. 질문별 개수를 강제로 채우지 않으며, 같은 대상·구간의 Q1·Q2가 같은 선택으로 이어지면 반복 조언으로 나열하지 않는 것을 목표로 합니다.

현재 구현의 후보별 순서·클러스터 포함·대표 완료 필수·최대 5개 조건은 [Ops README의 현재 동작 설명](../../../ops-agent/README.md#namespace별-조건부-운영-제안)을 따릅니다. 위 목표에 맞춘 후보 구성·근거 우선 선별은 [4단계 기준](#후보-선별과-우선순위-정의-후속-개발-목표)을 따르는 후속 구현 대상입니다. 새로운 통과/탈락 조건이나 구현 완료를 뜻하지 않습니다.

예를 들어 Q2의 **가상 사례 목표 문장**은 “해당 구간에는 낮은 활동률과 대기 Pod가 함께 관측됐습니다. 먼저 대기 Pod의 스케줄러 이벤트와 작업 준비 기록을 대조하세요.”입니다. 실제 답변에는 선택한 대상·기간·필수 수치 참조를 포함해야 하며, 이 예시를 실제 생성·검증 결과로 저장하거나 표시하지 않습니다.

**판단과 출력 표현의 연결.** 확대 판단을 보류한다는 내부 기준을 그대로 반환 문장에 쓰지는 않습니다. 기존 `queue_review` 검증은 “할당 확대를 우선할 근거가 부족하다”처럼 부정하는 문장도 `unsupported_capacity_recommendation`으로 거절합니다. Q2는 관측과 우선 점검 대상으로 표현하고, 조건부 확대 검토는 해당 근거가 있는 `capacity_review`에서만 표현합니다. Q3는 조건 확인 후 시범 실행 검토, Q4는 상주 목적 점검, Q5는 완료 표본·Job 경과시간과 허용된 기록 대조로 씁니다. 종류별 필수 참조·허용 확인 대상·금지 표현은 [기존 문장 검증](../../../ops-agent/src/ops_agent/namespace_advice.py)을 유지하며, 금지된 원인·미사용·대기 시간 표현도 부정문으로 우회하지 않습니다. 이는 질문의 사고 범위를 좁히는 규칙이 아니라 현재 결과 형식에 맞춘 표현 경계입니다.

### 필요한 근거 정의 (후속 개발 목표)

**2단계 · Evidence requirements.** 아래 표는 각 선택을 뒷받침할 자료와 부족할 때의 처리 목표입니다. 기존 지표 의미는 [수집 지표에서 운영 판단까지](#수집-지표에서-운영-판단까지), 쿼리·산식·유효성 조건은 [이 문서의 계산과 조회](#계산과-조회)를 따릅니다. 새로운 임계값·점수·수집 지표를 이 표에서 정하지 않습니다.

| 질문 | 판단의 출발점이 되는 저장 근거 | 선택을 더 확실히 하려면 확인할 자료 | 근거가 부족할 때의 답변 범위 |
|---|---|---|---|
| **Q1 · 자원 배분 검토** | 같은 클러스터·Namespace·시간 구간에 연결된 유효 활동률과 시간대별 Pending 최대값. 메모리·완료 기록은 해당 구간에 연결될 때 보조 근거로 사용 | 그 시간의 GPU 요청량·실제 할당량을 각각 확인하고, 가용 GPU·스케줄러 대기 사유·예약/보장 정책의 적용 여부를 대조 | 활동과 대기가 충분히 연결되면 조건부 할당 확대 검토는 가능하지만 부족 원인은 미확인으로 둡니다. 활동 연결이 없으면 확대를 우선할 근거로 쓰지 않고 Q2의 점검 또는 자료 부족 판단으로 제한합니다 |
| **Q2 · 실행 조건 점검** | GPU 요청 Pod의 Pending 관측과 관측 범위. 같은 시간대 활동·미배치·Running 관측이 있으면 점검 이유를 구체화 | 해당 Pod·시간의 스케줄러 이벤트, 배치 제약, 이미지·초기화·작업 준비 기록 | Pending만 있으면 대기 관측과 사유 확인 필요성까지만 설명합니다. 활동 미관측을 낮은 활동으로 쓰지 않고, 미배치 상태만으로 GPU 부족을 확정하지 않습니다 |
| **Q3 · 시범 실행 시간대** | 같은 GPU 구성의 연속된 유효 활동 구간과 해당 구간의 Pending 관측 여부. 같은 시간대 메모리가 있으면 상주 점유를 함께 고려 | 그 시간의 예약·작업 마감·가용 GPU, 시범 배치가 가능한 작업인지와 그 요구 조건 | 대기 미확인은 확인 전 조건으로 명시한 약한 후보이며, 완전한 대기 관측이 있는 후보보다 근거가 약합니다. 메모리 미관측을 여유로 해석하지 않습니다. 알려진 양수 대기가 있거나 활동 연결이 부족한 구간을 실행 여유 시간대로 권하지 않습니다 |
| **Q4 · 활동·메모리 대비** | 같은 GPU 신원·모델·Namespace·시간 구간의 유효 활동률과 장치 메모리 사용/여유. 사용 비율은 같은 시간대의 사용·여유 값으로 설명 | 해당 GPU에 연결된 작업 목적·상주 프로세스·캐시·메모리 요구 조건 | 한쪽 관측이 없으면 두 값의 대비를 만들지 않습니다. 두 값이 있어도 작업 목적이나 연산/메모리 병목은 추정하지 않으며, 높은 활동·낮은 메모리 등의 새 분기는 별도 기준 검증 전까지 현재 지원 분석으로 표시하지 않습니다 |
| **Q5 · 완료·경과 흐름** | GPU 요청 Pod의 Job owner 연결을 검증한 성공 완료 표본과 생성·시작·완료 시각, 저장된 Job 경과시간. 대기 변화를 언급할 때는 같은 Namespace·후보 구간의 유효 Pending 관측도 필요 | 실제 Pod 실행 시작, 재시도·실행 순서·배치 제약, 작업 유형·GPU 모델·요청량·입력 조건의 동등성 | 완료 표본만 있으면 그 표본의 완료·경과 범위까지만 설명합니다. 대기 연결이 없으면 대기 변화와 엮지 않고, 작업 조건이 다르거나 미확인이면 성능 우열을 비교하지 않습니다. 완료 표본이 없다는 이유로 완료 0건·작업 정체를 단정하지 않습니다 |

Q2의 미배치 제안은 “배치 조건 확인”만 말하지 않고, 관측된 미배치 Pod의 스케줄러 이벤트에서 **GPU 요청 미충족인지 다른 배치 제약인지** 구분할 목적을 밝힙니다. 이벤트가 없거나 보존되지 않았으면 대기 원인은 미확인입니다. Q4의 높은 장치 메모리는 연결 GPU의 관측이지 해당 Namespace 작업의 독점 점유가 아닙니다. **새 작업 배치 가능성을 판단할 때** 메모리 점유 주체와 상주 필요성을 확인하며, 관측만으로 GPU 여유를 확정하지 않습니다.

근거 연결은 다음 원칙으로 검수합니다.

1. **대상과 시간:** 클러스터·Namespace·모델·GPU 신원 및 시간 구간을 확인합니다. 하루 평균과 별도 시간대 최대 대기를 한 상태로 묶지 않습니다. 시간 평균 활동률과 상태별 최대값은 같은 순간을 뜻하지 않습니다.
2. **관측 범위:** 누락·신원 모호성·일부 표본은 그 상태로 보존합니다. 질문에 필요한 연속 구간이 유효하면 그 하위 구간으로 한정해 설명하는 것을 목표로 하며, 남은 값으로 하루 전체를 대표하거나 원래 품질 판정을 올리지 않습니다. 여기서 완전 관측은 기존 표본·집계 기준을 충족했다는 뜻이며, 측정 사이의 실제 연산을 빠짐없이 포착했다는 보장이 아닙니다.
3. **수치의 의미:** 시간대별 최대 Pending을 합해 대기 작업 총수로 쓰지 않습니다. Pending·미배치·Running 각각의 최대값을 빼거나 합쳐 동시 상태를 재구성하지 않습니다. 매시간 양수 최대값이 있어도 대기가 계속 유지됐는지·같은 Pod였는지는 알 수 없으며, 짧은 대기와 장시간 대기를 구별하는 근거로 쓰지 않습니다. Job 완료는 분석 구간 안에서 확인된 표본이며, 시작이 구간 전이면 원래 시작~완료 경과시간을 유지합니다.
4. **자료와 AI 입력:** 원천에 지표·라벨이 있는 것, 제품이 저장한 것, 해당 해석에 연결해 LLM에 전달한 것을 구분합니다. 현재 GPU 요청 지표는 작업 관측 대상 식별에도 쓰이지만 실제 할당량·정책 보장량을 검증해 설명하는 근거와 같지 않습니다. 스케줄러 사유·작업 목적·할당/예약 정보는 이 표에 필요하다고 적었다는 이유로 확보된 사실이 되지 않습니다.
5. **판단 범위:** 질문별 제안·점검·보류는 [해석 범위 정의](#해석-범위-정의-후속-개발-목표)를 따릅니다. 기존 후보 임계값과 안전 검증의 변경이 필요하면 근거와 영향 범위를 명시해 별도로 검증합니다. 한 판단의 근거가 부족해도 독립적으로 성립하는 다른 질문의 관측·점검까지 보류하지 않습니다.

이 설계의 소비 범위는 Ops 후보 구성·선별·LLM 입력·저장 narrative와 기존 화면/HTML 독자입니다. 수집·원래 계산·품질·CSV·RCA는 유지합니다. 후속 구현의 완료 조건은 같은 저장 자료에서 대상·시간·참조가 일치하고, 선택과 이유가 기존 검증을 통과하며, 자료 부족 사례에서 부당한 제안을 하지 않는 것입니다. 자동·수동 보고서의 같은 경로와 실제 LLM 문장 유용성은 별도로 검증해야 합니다.

These planned evidence requirements distinguish stored observations, evidence supplied to the LLM and additional decision context. They guide future candidate selection and operational writing; they do not add collection, thresholds, validation changes or a deployed interpretation path.

**질문별 근거 역할.** 아래 분류는 후속 선별에 쓰며 새 지표·런타임 필드를 정의하지 않습니다. 실행 전 확인 조건은 관측 충실도와 분리합니다.

| 질문 | 판단에 필수인 관측 | 반대·판단 변경 근거와 미확인 처리 | 보조 근거·실행 전 조건 |
|---|---|---|---|
| Q1 | 현행 높은 활동·양수 Pending·연속 시간·신원·표본 조건 | 미배치 없이 정상 준비 중일 가능성을 Pending만으로 배제 못함. 미배치 분기는 아래 별도 결정 대상 | 메모리·완료 결측만으로 후보를 낮추지 않음. 실제 할당·보장·가용량·대기 사유 필요 |
| Q2 | 유효한 양수 Pending 표본. 부분 관측도 존재 설명은 가능 | 활동 미확인을 낮은 활동으로 쓰지 않음. 미배치 연결로 먼저 대조할 단계를 구분하되 실제 사유는 미확인 | 활동·미배치·Running은 해당 주장에 사용할 때 필요. 스케줄러/준비 기록 대조 |
| Q3 | 유효한 낮은 활동 연속 구간, 알려진 양수 Pending 없음 | 양수 Pending은 제외. 같은 구간 높은 메모리는 Q4 우선. Pending 미확인은 반대 조건을 배제 못한 약한 후보이며 관측 확인이 먼저 | 메모리는 실행 가능성 확인 자료. 미확인은 여유도 높은 점유도 아님. 연결 작업의 수용 구조·할당 유지·예약·마감·가용 GPU 확인 |
| Q4 | 동일 신원·모델·시간의 낮은 활동과 높은 메모리 | 어느 한쪽 연결이 없으면 대비 설명 보류 | 상주 목적·캐시·작업 요구 조건. 낮은 메모리만으로 공유·회수 제안 불가 |
| Q5 | 유효 완료 표본과 시각·경과시간. 대기와 엮을 때만 해당 구간 Pending 필요 | 표본 없음은 완료 0이 아님. 경과 차이만 있거나 대기 0이면 우선 점검 사유가 되지 않음 | 동등한 작업 유형·실행 시작·재시도 자료는 별도. 개별 Job 전체 생애와 보고기간 관측을 구분 |

**완전 관측과 주장 방향.** [작업 조회](../../../ops-agent/src/ops_agent/workload_queries.py)의 상태별 240개는 일반 컨테이너의 `nvidia.com/gpu` 요청 Pod에 대한 한 시간의 subquery 평가 수입니다. 각 평가 시점에서 대상 Pod의 해당 상태 지표가 모두 연결돼야 값이 남습니다. 대상 Pod가 없어진 시점과 지표 누락·불일치 때문에 값이 없는 시점은 이 요약만으로 구분하지 못합니다. 따라서 200/240을 곧 수집 장애로 쓰지 않습니다. 완료 Pod 보존·삭제에 따른 영향 빈도는 실자료로 확인해야 하며, MIG·init 전용 GPU 요청·Pod 생성 전 대기열은 현재 범위 밖입니다.

| 주장 | 필요한 관측과 허용 범위 |
|---|---|
| 존재 | 유효한 부분 표본의 양수 최대값도 그 평가 시점에 해당 개수의 Pending이 관측됐다는 근거. 하루 전체 규모·지속 시간은 아님 |
| 부재 | 해당 상태의 240개 유효 평가와 최대 0은 평가 시점에서 관측되지 않았다는 뜻. 측정 사이 또는 대상 밖 작업의 부재는 아님 |
| 변화 | 같은 대상·주장 구간의 비교 조건을 유지. 현재 batch 전달은 전 구간 Pending 완전, 처음/마지막 값 존재, 두 값 중 하나 이상 양수여야 함. 증가·양의 차이만 허용하는 조건은 아님 |
| 연속 | Q1/Q3의 기존 인접 시간·신원·표본 조건을 유지. 양수 시간대가 이어져도 동일 Pod가 계속 기다렸다는 뜻은 아님 |

부분 표본이라는 이유만으로 존재 근거를 약하다고 순위화하지 않습니다. 존재·부재·변화 중 **실제로 하려는 주장**에 필요한 관측을 비교합니다. 표본 기준을 낮추거나 누락을 0으로 채우는 변경은 하지 않습니다.

### 해석 범위 정의 (후속 개발 목표)

**3단계 · Interpretation boundaries.** 아래는 후속 구현·LLM 비교에서 사용할 답변 기준입니다. 문서에서 정의한 범위이며 새 런타임 상태·필드·검증 조건을 추가한 것이 아닙니다. 질문·근거·해석 범위의 연결을 검수하되 실제 후보 선별 순서는 이후 작업에서 검증합니다.

| 답변 범위 | 선택할 조건 | 운영자에게 전달할 내용 |
|---|---|---|
| **관측 설명** | 유효 수치는 있지만 변경·점검을 우선할 근거는 부족함 | 확인된 대상·시간·수치와 그 범위까지만 설명합니다. 개수를 채우기 위한 조언은 붙이지 않습니다 |
| **점검 우선** | 특정 구간의 대기나 활동·메모리 대비가 확인되지만 자원·시간대 변경을 우선할 근거는 부족함 | 무엇을 먼저 점검할지와 관측에서 나온 이유를 제안합니다. 미확인 대기 원인·작업 목적은 확인할 항목으로 남깁니다 |
| **조건부 변경 검토** | 해당 질문의 관측 조건이 충족돼 할당 확대 검토 또는 특정 시간대의 시범 실행을 제안할 근거가 있음 | 제안할 선택과 이유를 먼저 쓰고, 실제 할당·예약·가용 자원 등 실행 전 확인 조건을 붙입니다. 실제 변경이나 수량은 확정하지 않습니다 |
| **판단 보류** | 그 판단에 필수인 값·시간 연결·신원이 없거나 충돌함. 또는 아직 정의·검증하지 않은 분석임 | 어느 판단을 왜 보류하는지 밝힙니다. 독립적으로 유효한 관측이나 다른 점검 제안은 유지합니다 |

이 네 범위는 신뢰도 점수나 일률적인 승급 순서가 아닙니다. 관측 설명·판단 보류를 모두 AI 제안 불릿으로 만드는 것도 아닙니다. 현재 제안 형식으로 전달할 수 없는 내용은 기존 표·상세 근거·계산 요약에 남깁니다. 같은 Namespace에서도 할당 확대는 보류하면서 대기 사유 점검은 제안할 수 있습니다. 높은 활동·낮은 활동만으로 제안을 강제하지 않습니다. 예약·배치 제약·의도된 테스트 대기 연결은 아직 입력 계약이 없는 후속 범위입니다. S15는 그 입력을 설계한 뒤 검수할 사례이며 현재 구현의 통과 조건에 포함하지 않습니다. 수치나 테스트 라벨만으로 맥락을 추측하지 않습니다.

| 질문 | 제안·점검할 조건과 해석 범위 | 해당 판단을 보류하거나 제한할 조건 |
|---|---|---|
| **Q1 · 할당 확대와 점검 중 선택** | 같은 GPU 구성의 유효한 연속 두 시간 이상에 모든 관측 모델의 시간 평균 활동률이 80% 이상이고, 각 시간대의 완전한 Pending 관측에 양수가 있으면 **조건부 할당 확대 검토** 근거입니다. 실제 할당·가용 자원·대기 사유 확인은 여전히 필요합니다 | 단일 시간, 활동 연결 부족, 불완전한 대기 근거로는 이 확대 기준을 충족하지 않습니다. Pending이 유효하면 Q2 점검은 가능합니다. 80% 미만이라고 자원이 충분하다는 결론은 내리지 않습니다 |
| **Q2 · 실행 조건 점검 우선** | 양수 Pending이 관측됐고 Q1의 확대 검토 조건이 충족되지 않으면 **실행 조건 점검**을 제안합니다. 활동이 낮은 경우와 미확인인 경우를 구분합니다. Q1과 같은 선택·이유이면 반복하지 않습니다 | Pending 자체가 미확인이면 대기가 있다고 설명하지 않습니다. 부분 관측은 해당 범위로 제한하며, 미배치·Running 최대값만으로 특정 원인을 정하지 않습니다. 미배치 연결로 먼저 대조할 기록을 구분하는 구현은 아래 범위를 따르며, 기존 필수 어휘·검증 조건은 유지합니다. |
| **Q3 · 실행 시간대 검토** | 같은 GPU 구성으로 모든 관측 모델의 활동률이 5% 미만인 유효 연속 두 시간 이상이며 알려진 양수 Pending이 없으면 **조건부 시범 실행 검토** 근거입니다. Pending 완전 관측 여부와 메모리 관측 범위를 명시합니다 | 정확히 5%인 시간은 낮은 활동 기준에 포함하지 않습니다. 대기 미확인은 실행 전 확인 조건이 있는 약한 후보입니다. 미확인 대기는 관측 확인을 먼저 제안하고 실제 시범 실행은 그 뒤의 조건부 검토로 제한합니다. 연결 작업의 추가 요청 수용·할당 유지 필요성 확인이 선행해야 합니다. 같은 구간에서 높은 메모리 점유가 확인되면 Q4 점검을 우선하며, 유효 활동 구간 부족이나 알려진 양수 대기가 있으면 이 시간대 제안을 보류합니다 |
| **Q4 · 활동·메모리 대비** | 위 낮은 활동 구간에서 같은 시간대의 유효 장치 메모리 비율이 80% 이상 관측되면 **상주 작업·캐시·목적 점검**을 우선합니다. 높은 메모리가 확인된 시간과 그 외 시간을 구분합니다 | 활동 또는 메모리 연결이 없으면 대비 판단을 보류합니다. 높은 활동·낮은 메모리 등 추가 분기는 별도 기준 검증 전까지 관측 설명으로 제한합니다. 어느 조합에서도 메모리 병목·회수 가능성은 확정하지 않습니다 |
| **Q5 · 완료 흐름·경과 비교** | 유효 완료 표본의 시각·Job 경과 차이를 설명하되, 차이 자체를 우선 점검 사유로 쓰지 않습니다. 아래의 추가 대기 맥락이 연결될 때 **실행 순서·작업 조건 대조**를 우선할 이유로 사용합니다. 대기 비교는 같은 후보 구간의 완전한 Pending 관측과 처음/마지막 시간대 최대값이 연결될 때만 포함합니다 | 단일 표본이나 같은 경과시간만으로 경과 차이를 주장하지 않습니다. 완료 표본 없음·제외 표본만 존재하면 완료 수·진행 정체 판단을 보류합니다. 대기 연결 부족은 완료 관측 자체를 지우는 사유가 아닙니다 |

**Q5의 관측과 우선 점검을 구분하는 기준.** 경과시간이 조금이라도 다르거나 완료 건수가 많다는 사실만으로 다른 제안보다 우선하지 않습니다. 현재 자료에서 별도 점검 후보의 이유로 사용할 추가 맥락은 **후보 구간의 완료 시각과, 완료가 관측된 시간 또는 이후 시간의 양수 Pending이 유효하게 연결된 경우**로 한정합니다. 이때 질문은 “완료 표본과 그 완료가 관측된 시간대 또는 이후 시간대의 대기가 각각 확인됐으므로, 해당 시간의 실행 순서·스케줄러 사유·작업 유형을 무엇부터 대조할까”입니다. 시간대 최대값이므로 완료 순간의 상태나 같은 Pod의 잔여 대기·처리 지연을 뜻하지 않습니다. 먼저 완료 표본과 Pending 각각의 관측 범위를 명시해야 합니다. 이 연결은 정상적인 순차 배치에서도 생기므로 실행 이상이나 다른 질문보다 높은 중요도를 뜻하지 않습니다. 같은 시작 시각의 Job에서 경과 차이와 완료 시각 차이는 같은 사실을 표현하므로 독립된 두 근거로 가산하지 않습니다. 이는 후속 선별에서 쓸 기록 대조 이유이며 새 계산·통과/탈락 임계값이 아닙니다.

추가 맥락이 없으면 완료·경과 차이는 관측 설명 수준으로 두며, 동등한 작업의 성능 차이를 판단하려면 별도 근거가 필요합니다. 다만 기존 기준으로 이미 적격인 대표 완료가 필수 포함되면 이를 임의로 숨기지 않습니다. 그 불릿에는 표본·경과 범위와 확인할 기록을 짧게 쓰고, 문제가 있거나 긴급한 점검인 것처럼 만들지 않습니다. 이러한 필수 포함은 운영상 우선순위가 높은 제안과 구분하며, 모든 불릿이 새로운 선택을 제시한다는 목표는 기존 계약만으로 보장할 수 없습니다.

**문서용 가상 사례와 기대 판단.** 아래 값은 실제 보고서나 LLM 실행 결과가 아닙니다. 별도 언급이 없으면 같은 클러스터·Namespace·모델·GPU 구성의 같은 시간 구간이며, 각 수치는 해당 시간대의 유효 관측입니다. 활동률은 시간 평균, 대기는 시간대 최대값이고 동시 상태를 뜻하지 않습니다. “두 시간” 사례는 인접한 두 시간 모두 제시한 조건을 충족하며, 알려진 예약·의도된 대기 등 별도 맥락은 없는 것으로 가정합니다.

| 사례 | 관측 조건 | 기대하는 판단과 이유 |
|---|---|---|
| **S01 · 값이 달라도 같은 판단** | A는 두 시간 활동률 85%·대기 3개, B는 두 시간 활동률 92%·대기 7개. 두 사례 모두 대기 완전 관측 | 둘 다 Q1의 **조건부 할당 확대 검토**입니다. 대상·수치·설명은 달라도 판단 종류는 같습니다. 대기 수로 추가 GPU 수량을 계산하지 않습니다 |
| **S02 · 높은 활동 경계** | 두 시간 대기 3개가 완전 관측됐으며, 활동률만 각각 79.9% 또는 80%로 바꿈 | 80%는 Q1 기준에 포함합니다. 79.9%는 이 확대 기준을 충족하지 않아 Q2 점검으로 제한합니다. 기준 미달을 여유 자원 판정으로 쓰지 않습니다 |
| **S03 · 지속 시간 부족** | 활동률 90%·대기 3개가 유효하지만 연결된 구간이 한 시간뿐 | Q1 확대 검토는 보류합니다. 확인된 짧은 구간의 대기 점검과 관측 설명은 가능합니다 |
| **S04 · 낮은 활동과 대기** | 두 시간 활동률 2%·대기 4개가 관측됨 | Q2 **실행 조건 점검 우선**입니다. 먼저 해당 시간대의 배치 제약·준비 기록을 대조할 이유를 설명하며 GPU 미사용이나 대기 원인을 단정하지 않습니다 |
| **S05 · 시범 실행 후보** | 두 시간 활동률 2%, 대기 0개가 완전 관측되고 같은 시간 메모리 20% | Q3 **조건부 시범 실행 검토**입니다. 관측 날짜의 후보 시간과 예약·가용 GPU·작업 요구 조건을 확인한 뒤 시험할 이유를 제시합니다 |
| **S06 · 낮은 활동 경계** | 두 시간 활동률이 정확히 5%, 대기 0개가 완전 관측됨 | Q3 시간대 제안은 이 기준으로 성립하지 않습니다. 관측 설명은 가능하지만 “자원이 없다” 또는 “실행하면 안 된다”는 결론도 아닙니다 |
| **S07 · 대기·메모리 미확인** | 두 시간 활동률 2%이나 대기·메모리 자료가 없음 | 낮은 활동 관측은 유지하되 먼저 대기 관측·연결 작업의 수용 구조를 확인합니다. 현행 약한 시간대 후보는 유지할 수 있지만 시범 실행은 확인 뒤의 조건부 검토이며 먼저 실행할 시간대로 추천하지 않습니다. 메모리 결측을 여유로 쓰지 않습니다 |
| **S08 · 메모리 점유** | 두 시간 활동률 2%, 대기 0개, 같은 시간의 유효 메모리 비율이 80% 또는 98% | 둘 다 Q4 **작업 목적·상주 메모리 점검 우선**입니다. 시범 실행 시간대보다 점검을 먼저 제안하며 메모리 부족·회수 여부를 판정하지 않습니다 |
| **S09 · 근거 품질 차이** | S01과 같은 활동률이지만 해당 대기 구간에 결측이 있음 | Q1 확대 판단은 보류하거나 유효한 하위 구간이 별도로 조건을 충족하는지 검토합니다. 관측된 양수 대기의 부분 점검은 가능하며 빈 시간을 0으로 채우지 않습니다 |
| **S10 · 완료 흐름과 경과 차이** | 시작 시각이 같은 유효 완료 Job 3개가 각각 3·6·9시간 뒤 완료됐고, 같은 후보 구간의 대기 최대값은 처음 5개→마지막 3개로 완전 관측 | 완료 표본과 후반 시간대의 양수 Pending이 함께 확인돼 Q5 **실행 순서·작업 조건 대조**를 제안합니다. 경과 차이만을 우선 점검 이유로 삼지 않으며, 완료 시각·경과 차이와 대기 최대값 비교를 구분해 설명합니다. 또한 순수 실행시간·개별 대기시간·완료에 의한 대기 해소를 주장하지 않습니다 |
| **S11 · 완료 한 건만 확인** | 유효 완료 Job 한 건의 경과시간 3시간은 확인됐으나 Pending 자료는 없음 | 해당 표본의 완료·경과시간을 **관측 설명**합니다. 경과 차이·대기 감소 판단은 보류하며 완료 표본을 삭제하지 않습니다 |
| **S12 · 완료 표본 없음** | 유효 완료 표본이 없고 원천 누락 또는 제외 표본만 있음 | 완료 건수·진행 정체 판단을 **보류**합니다. 완료 0건이나 작업이 전혀 진행되지 않았다고 쓰지 않습니다 |
| **S13 · 시간·신원 불일치** | 활동은 09~11시, 대기는 15~17시 자료이거나 같은 시간에 GPU 귀속이 모호함 | 두 관측을 묶은 Q1·Q2 해석은 **보류**합니다. 각각의 유효한 관측과 대기 사유 점검은 해당 범위에서만 유지합니다 |
| **S14 · 미정의 분석** | 같은 두 시간의 활동률 92%·메모리 비율 10%, 대기 0개가 확인됨 | 두 수치의 **관측 설명**은 가능하지만 새 조합에 대한 최적화 제안은 보류합니다. 낮은 메모리 기준을 임의로 정하거나 GPU 공유·축소·연산 병목을 제안하지 않습니다 |
| **S15 · 미구현 제약 입력 전제** | 높은 활동·양수 대기와 함께 의도된 동시 실행 제한이라는 근거가 있다고 가정. 현재 후보에는 이 입력 경로가 없음 | 향후 검증된 제약이 연결되면 기본은 제한 안의 관측 설명과 확대 판단 보류입니다. 제한 변경이 검토 대상이라는 운영자 의도가 있을 때만 조건 변경 검토를 제안합니다. 라벨만으로 확정하지 않으며 현재 코드·LLM 수용 검수에서는 미지원으로 분리합니다 |
| **S16 · 같은 최대값과 다른 실제 대기** | A는 시간마다 짧게 다른 Pod가 대기했고, B는 같은 Pod가 오래 대기했으나 저장된 시간 평균 활동률·Pending 최대값·표본 충족 조건은 같음 | 현재 요약 지표로 둘을 구별하거나 B를 더 심각하게 순위화하지 않습니다. Q1 조건을 충족해도 검토 대상 신호까지만 쓰며, 지속 대기·누적 압박이나 측정된 대기 시간을 주장하지 않습니다 |
| **S17 · 경과 차이만 존재** | 완료 Job 두 건의 경과가 1초 다르고, 같은 기간 Pending은 완전 관측 0개이며 다른 점검 맥락이 없음 | 완료·경과의 관측 설명입니다. 차이만으로 우선 점검을 제안하거나 의미 있는 성능 변화라고 쓰지 않습니다. 해당 완료 표본은 기존 상세에 유지합니다 |
| **S18 · 같은 Namespace의 다른 구간** | 오전은 Q1 조건, 오후는 낮은 활동과 양수 Pending | 서로 다른 시간의 선택을 후보 구성부터 검수합니다. 오후가 오전 Q1을 반증하는 것은 아닙니다. 현행 if/elif로 오후 Q2가 사라지는 제한과 후속 보존 목표를 구분합니다 |
| **S19 · 높은 활동과 미배치 0** | 두 시간 활동 85%, Pending 양수, 미배치는 완전 관측 최대 0 | 현행 Q1 후보는 생성될 수 있습니다. 의미 검수에서는 준비 단계 가능성을 배제할 수 없다고 기록합니다. 미배치 조건으로 Q1을 제외하는 것은 별도 기준 결정 전까지 구현 완료로 기대하지 않습니다 |
| **S20 · 짧은 메모리 점유** | 낮은 활동 6시간 중 1시간만 메모리 85%, 나머지 5시간은 유효 20%, 알려진 양수 Pending 없음 | 현재 전체 quiet 구간이 Q4로 분류되는 제한을 확인합니다. 후속은 높은 메모리 시간과 나머지 인접 구간을 분리 검수하되 Q3의 기존 두 시간 조건을 그대로 적용합니다. Q4 한 시간만으로 새 유형을 만들지 않습니다 |
| **S21 · Pod 부재와 부분 표본** | GPU 요청 Pod가 없었던 평가 시점 때문에 200/240. 남은 유효 표본에는 Pending 양수 | 존재 관측은 유지하되 공백을 수집 장애·대기 0으로 정하지 않습니다. 현재 Q1·batch 완전성 조건은 유지합니다 |
| **S22 · 사건과 대기** | 대기 구간과 같은 클러스터·시간에 GPU 노드 사건이 있음 | 클러스터·시간 일치만으로 해당 Namespace 영향이나 원인으로 연결하지 않습니다. 검증된 노드/Pod 관계와 사건 시각이 실제 입력에 연결된 뒤 기록 대조 후보로 검수합니다. 현재는 미구현 |
| **S23 · 모델별 활동 차이** | 같은 두 시간 A100 90%·T4 2%, Namespace Pending 양수 | 모든 관측 모델이 Q1 활동 조건을 충족하지 않아 Q2 범위입니다. Pending을 A100/T4에 임의로 배분하거나 확대 모델을 지목하지 않습니다 |
| **S24 · 메모리 경계** | 두 시간 낮은 활동·완전 Pending 0, 모든 모델 메모리 79.9% 또는 한 모델 80% | 전자는 Q3 후보, 후자는 Q4 점검입니다. 79.9%를 충분한 여유나 추가 작업 수용 보장으로 해석하지 않습니다 |
| **S25 · Job 생애가 보고기간 밖** | Job 시작은 보고 시작 전이며, 보고기간 안 완료와 Pending 0만 확인 | 전체 경과시간은 보존하지만 Job의 전체 생애에 대기가 없었다고 하지 않습니다. 관측 밖 시간은 비교 보류하며 작업 조건·실행 성능 차이를 추정하지 않습니다 |

추가 검수에서는 S01의 Namespace·클러스터 이름과 조건 안의 수치를 바꿔도 같은 판단 범위가 유지되는지 확인합니다. S02·S03·S06·S09·S13처럼 조건·관측 범위가 바뀌면 결론도 달라져야 합니다. 이는 같은 후보에 대한 해석 일관성 기준이며, 최종 첫 화면 포함 여부는 별도의 선별·대표성 조건에 따라 달라질 수 있습니다. 사례의 기대 판단을 문서로 정한 것과 실제 코드·LLM이 재현한 것은 별도 검증입니다.

### 반복 고활동·상대적 저부하 후보

**상태와 목적.** 아래 R1/R2는 기존 Q1~Q5의 자격을 낮추는 대체 경로가 아니라 별도의 질문과 주장 범위입니다. 기존 Q1의 모든 모델 80% 이상·연속 두 시간·완전 Pending 양수, Q3의 5% 미만·연속 두 시간 및 기존 메모리 분기는 유지합니다. `ops-pattern-comparison-v7`은 R1을 `repeated_activity`, R2를 `relative_activity`로 생성하고 기존 선별·최초/보완 입력·검증·narrative 저장 경로에 연결합니다. 신규 종류의 실제 LLM 문장 품질은 단일 저장 보고서에서 부분 개선으로 평가됐으며 운영 발행은 미검증입니다([Agent QA](../../../agents/QA.md)). 아래 수치는 초기 선별 기준입니다. R1은 **자원 배분 점검의 우선 대상**, R2는 **조건 확인 후 소규모 시간대 변경 실험**을 제안하며 확대 수량·가용 GPU·성능 개선을 판단하지 않습니다.

#### R1 · 반복 고활동과 대기가 관측된 대상

- **질문:** 연속 고활동 기준은 충족하지 않지만, 자원 배분과 배치 제약을 먼저 대조할 Namespace가 있는가?
- **성립:** 같은 클러스터·Namespace·KST 날짜·관측 모델 집합·GPU 구성에서 기존 활동 유효성 검사를 통과하고, 모든 관측 모델의 시간 평균 활동률이 80% 이상이며 해당 시간의 Pending이 240개 평가·최대 양수인 시간들을 찾습니다. 인접한 해당 시간은 한 묶음으로 세고, 서로 떨어진 묶음이 두 개 이상이면 R1입니다. 한 묶음이 Q1의 연속 두 시간을 만족하면 그 묶음은 Q1에 맡기고 나머지 독립 묶음이 두 개 이상일 때만 별도 R1을 남깁니다. 하루별로 판정하며 보고기간이 길다는 이유로 서로 다른 날짜의 한 시간씩을 합치지 않습니다.
- **공백 처리:** 묶음 사이에 제외·미관측 시간이 있어도 각 묶음의 유효 근거는 보존합니다. 처음~마지막 시간을 하나의 연속 고활동 구간으로 만들지 않고, 실제 묶음 목록과 중간 제외 사유를 별도로 전달합니다. GPU·모델 구성이 바뀌면 비교 집합을 나누며, 확인된 시간의 구성이 같다고 사이의 구성을 추정하지 않습니다. 미확인 시간을 낮은 활동·대기 해소로 메우지 않습니다.
- **허용 선택:** 다른 Namespace와 동일한 일반 점검을 나열하기보다 이 대상을 **자원 배분 점검 대상으로 먼저 검토**하도록 제안합니다. 점검 내용은 해당 구간의 GPU 요청·할당·보장/제한과 스케줄러 이벤트의 대조입니다. 이는 부족 원인·장애 심각도 순위가 아니라 반복 관측에 근거한 검토 대상 선정입니다. 미배치 양수/준비/미확인 분기는 기존 근거에 맞춰 별도로 명시합니다.
- **금지·보류:** GPU 부족, 계속 기다리는 동일 작업, 전체 구간 포화, 할당 확대 실행·수량은 말하지 않습니다. 한 묶음뿐이거나 해당 시간의 활동/대기 근거가 불완전하면 R1은 보류하고 기존 Q2의 유효 관측만 유지합니다. 의도된 테스트 제한·쿼터 원인은 실제 연결 근거 없이 라벨이나 작업 이름으로 추정하지 않습니다. 할당 확대라는 제안은 기존 Q1 또는 별도로 승인된 직접 자원 근거 계약에서만 허용합니다.

#### R2 · 같은 대상의 상대적으로 낮은 활동 시간대

- **질문:** 거의 무활동인 시간이 없어도, 이 Namespace의 작업을 옮겨 시험할 만한 상대적 저활동 구간이 있는가?
- **비교 단위:** 같은 클러스터·Namespace·KST 날짜·관측 모델 집합·GPU 구성에서 서로 겹치지 않는 연속 두 시간 구간끼리 비교합니다. 양쪽 모든 시간·모델이 기존 활동 유효성 조건을 통과하고 Pending이 240개 평가·최대 0이어야 합니다. 비교는 이 Namespace에 한정하며 다른 Namespace의 작업 이동이나 클러스터 전체 비혼잡을 제안하지 않습니다.
- **초기 비교 기준:** 모든 모델에서 후보 두 시간의 활동률 **최댓값이 비교 구간 두 시간의 최솟값의 절반 이하**이면 상대적 저부하 후보로 봅니다. 비교 구간 최솟값은 양수여야 합니다. 모델 평균끼리 상쇄하거나 기간 전체 평균을 새로 계산하지 않습니다. 절반이라는 값은 작은 수치 차이만으로 제안을 채우지 않기 위한 **새 후보의 초기 설계값**이며, 운영정책이나 효과가 입증된 경계가 아닙니다. 아래 수용 검수 전에는 제품에 활성화하지 않습니다. 기존 5% 경계는 바꾸지 않습니다.
- **메모리·반대 근거:** 후보의 모든 시간·모델에 기존 검증을 통과한 메모리 근거가 있고 장치 점유가 80% 미만이어야 R2의 시범 실행 제안을 허용합니다. 이는 추가 작업을 수용한다는 보장이 아닙니다. 높은 메모리, 양수 Pending, 후보/비교 구간의 부분 관측은 R2 제안을 보류합니다. 메모리 미확인도 R2는 보류하되 기존 Q3의 미확인 처리까지 바꾸지 않습니다. 선택한 비교 구간 밖에서 대기나 높은 활동이 있었다는 사실도 삭제하지 않습니다.
- **비교 선택:** 가능한 모든 두 시간 조합을 검사합니다. 같은 후보에 여러 비교 구간이 있으면 모델별 `비교 최솟값 - 후보 최댓값` 중 가장 작은 차이가 큰 비교 구간을 택하고, 동률이면 이른 시각을 택합니다. 차이는 후보 선별용 메타데이터이며 기존 보고서 metric·품질·CSV를 덮어쓰지 않습니다. 이 비교 구간은 하루 평균·일반적인 업무 시간대를 대표하지 않습니다.
- **표시:** 첫 화면에서 `시간대 비교 · 과거 관측`으로 구분하고 저장된 `비교 구간 (시간 범위)`과 `낮은 활동 구간 (시간 범위)`를 해당 순서로 보여줍니다. 같은 날짜는 한 번만 표시하고 원본에 초가 있거나 날짜가 바뀌면 그 정확도를 보존합니다. 관측일·KST·종료 시각 제외와 제안 기준을 명시하며 빈 GPU나 매일의 여유가 확인됐다는 뜻으로 표시하지 않습니다. 이는 확정 실행 권고가 아닙니다. 종료 시각은 포함하지 않으며 시간 범위가 없거나 잘못된 과거 기록에는 미확인을 표시합니다. 이미 지난 구간이므로 이후 같은 시간대의 반복성과 가용 GPU를 추가로 확인해야 작업 시간 변경을 검토할 수 있다고 명시합니다. 실제 LLM 문장은 임의로 고쳐 표시하지 않습니다.
- **허용 선택:** 해당 날짜의 비교 근거를 제시하고, 작업 마감·예약·가용 GPU·추가 작업의 메모리 요구를 확인한 뒤 **시간 조정이 가능한 같은 Namespace의 작업 일부를 후보 시간대로 옮겨 시범 실행할지 검토**하도록 합니다. 이미 실행 가능한 작업이나 반복되는 일일 저부하 패턴으로 단정하지 않습니다. 제출 시각을 옮기면 대기·완료시간이 좋아진다는 효과 예측은 하지 않습니다.
- **중복:** 기존 Q3가 같은 구간에 성립하면 Q3를 우선하며 새 종류로 같은 제안을 추가하지 않습니다. 겹치는 R2 구간은 위 비교 차이가 큰 구간 하나, 동률이면 이른 구간을 대표로 고릅니다. 같은 대상의 나머지 유효 구간은 상세에 보존하고 첫 화면에는 같은 운영 선택 하나만 제시합니다. 비겹침 구간도 기존 전체 후보/요약 상한 안에서 선택합니다.

#### 실제 구간에 대입한 허용 범위

다음은 저장된 **2026-10-19 00:00~10/20 00:00 KST 수동 보고서**의 시간 집계로 검토한 사례입니다. 문장은 명세 설명용 예시이며 실제 LLM 출력이나 운영 검증 완료 사례가 아닙니다. 모든 활동 수치는 시간 평균, Pending은 시간별 최대값이고 메모리는 연결된 장치 관측입니다. Namespace는 역할명으로 줄였습니다.

| 대상·실제 근거 | 새 기준에서의 판단 | 허용할 운영 제안과 남은 조건 |
|---|---|---|
| CPC-1 수요예측: 18~19시 83.25%·Pending 55개, 21~22시 83.38%·54개. 앞선 17~18시·20~21시는 각각 58.60%. 19~20시·22~23시는 신원 검증 제외 | Q1은 계속 불성립. R1은 떨어진 고활동·양수 대기 묶음 두 개로 성립. 제외 시간을 연결하지 않음 | “고활동과 대기가 여러 구간에서 관측된 이 Namespace부터 자원 배분을 점검하세요. 해당 구간의 GPU 요청·할당과 스케줄러 이벤트를 대조할 대상입니다.” 증설·지속 포화는 제안하지 않음 |
| CPC-2 수요예측: 13~14시 83.06%·55개, 16~17시 82.98%·54개, 19~20시 82.19%·53개, 22~23시 82.57%·52개. 각 다음 시간은 신원 검증 제외 | Q1은 불성립, R1은 네 묶음. Pending 감소가 같은 작업의 대기 해소나 완료 효과라는 뜻은 아님 | CPC-1과 같은 범위의 자원 배분 점검 대상. 네 묶음·큰 대기 수만으로 더 심각한 GPU 부족으로 순위화하지 않음 |
| CPC-1 서비스: 후보 21~23시 활동 21.42%·16.98%, Pending 각각 0, 메모리 11.44%·13.56%. 비교 19~21시 활동 82.80%·63.86%, Pending 각각 0 | Q3은 5% 이상이라 불성립. R2는 후보 최대 21.42%가 비교 최소 63.86%의 절반 이하라 성립 | “시간을 조정할 수 있는 이 Namespace의 작업 일부를 21~23시에 옮겨 시험하는 방안을 검토하세요. 관측한 19~21시보다 활동이 낮았습니다.” 실행 전 마감·예약·가용 GPU·작업 메모리 요구 확인. 매일 이 시간에 실행하라는 뜻은 아님 |
| CPC-2 서비스: 후보 16~18시 36.32%·13.86%, 17~19시 13.86%·28.97%, 22~24시 35.21%·13.88%. 비교 14~16시 78.95%·73.47%. 각 구간 Pending 0, 후보 메모리 12.07~17.07% | 세 R2 구간이 성립. 겹치는 앞 두 구간은 후보 최대가 더 낮은 17~19시를 대표로 남김. 22~24시는 별도 상세 후보 | 같은 Namespace에서 조정 가능한 작업의 소규모 시간 변경 실험을 검토. 해당 시간의 클러스터 여유나 성능 개선을 확정하지 않음 |
| CPC-1 상주 작업: 02~05시·06~09시 활동 0~0.42%, Pending 0, 메모리 97.97%; 12~14시·22~24시도 저활동·고메모리 | R2 보류, 기존 Q4 유지 | 새 작업을 넣을 시간으로 권하지 않음. 장치 메모리 점유 주체·추가 작업의 요구량이 먼저 필요 |
| 실행 전 GPU 활동 미관측 시간, 또는 CPC-2 수요예측 10~11시 활동 2.58%·Pending 55개 | 전자는 관측 부족, 후자는 알려진 대기 때문에 R2 불성립 | 전자를 한가한 시간으로 바꾸거나 후자를 추가 배치 시간으로 제안하지 않음 |

#### 구현 계약과 수용 검수

R1/R2는 별도 종류와 허용 선택·필수 참조 검사로 구현합니다. R1을 `capacity_review`, R2를 `schedule_candidate`로 위장하거나 기존 금지어 검사를 끄지 않습니다. 기존 종류의 자격·문장 검증과 원래 집계·RCA는 유지합니다. 후보를 찾는 로컬 검증과 실제 LLM의 유용한 문장 생성·운영 발행 검증은 구분합니다.

- **근거 계약:** `source_hours`·`observed_periods`와 R2의 `reference_period`·`reference_hours`, `criteria_revision`을 저장합니다. 최초/부분 보완 입력에는 `pattern_evidence`로 전달하고 출력의 필수 시간/수치 토큰을 검사합니다. 기존 웹/HTML은 저장된 채택 문장의 시간 목록·비교 구간을 그대로 표시하며 새 계산 metric·CSV·DB 스키마는 추가하지 않습니다. R1은 개별 고활동 묶음, 사이의 미확인 구간, 각 묶음의 활동·Pending·선택적 미배치 참조를 보존합니다. R2는 후보/비교 구간과 모델별 활동 범위, Pending 완전성, 후보 메모리, 비교 기준 revision을 보존합니다. 한 `period`로 두 비교 구간이나 떨어진 묶음을 연속 관측처럼 표현하지 않습니다. 역할이 다른 동일 수치 참조를 합치지 않습니다.
- **영향 범위:** Ops 후보 생성·선별·LLM 최초/보완 입력·추가 종류 검증·근거 저장, 웹/HTML의 복수 구간 표시와 과거 결과 읽기를 함께 검수해야 합니다. 기존 12개/5개 상한·클러스터/완료 필수·재시도/예산은 유지합니다. R1/R2라는 이유만으로 우선하지 않으며 원인 미확인 R1과 조건부 실험 R2의 판단 범위를 구분합니다.
- **경계 검수:** 기존 S01~S25의 결과 불변, R1 한 묶음 탈락/두 묶음 성립·구성 변경 분리·날짜 경계·부분 Pending 제외, R2 절반 경계의 안팎·전 모델 충족·영 분모 제외·신원/기간 불일치·메모리 결측/80%·양수 또는 부분 Pending 제외·겹침 대표·Q3 중복을 확인합니다. 제외 시간과 미관측을 0으로 채우지 않는지 검사합니다.
- **초기 기준의 검수:** 이번 사례뿐 아니라 다른 날짜·작업 구성의 저장 보고서와 반례로 R1의 두 묶음, R2의 절반 기준이 과도한 후보를 만드는지 평가합니다. 테스트의 의도된 제한도 별도 근거가 없으면 원인으로 쓰지 않습니다. 이 사례가 추천에 들어오도록 수치를 역으로 조정하지 않습니다. 검수 전에는 경계의 타당성·운영 효과가 미확인입니다.
- **LLM 수용:** 같은 자료의 전후 결과에서 대상·운영 선택·관측 이유·실행 전 조건이 읽히는지, R1이 증설 확정으로 변하지 않는지, R2가 여유/매일 반복/시간 단축 보장으로 변하지 않는지 봅니다. 참조·형식 통과와 사람의 유용성 검수를 구분하고 신규 자동·수동 발행은 별도로 검증합니다.

### 후보 선별과 우선순위 정의 (후속 개발 목표)

**후보 구성도 선별의 일부입니다.** 이전 `candidates()`는 Namespace별 최대 Pending 구간을 고르고 Q1이 있으면 Q2를 만들지 않았습니다. `ops-evidence-windows-v4`는 다른 시간의 대기 구간과 각 날짜의 유효 구간을 보존하고, 같은 대상·질문의 여러 구간보다 다른 대상·질문의 대표를 먼저 전달합니다. 기존 Q4 자격은 유지하되 높은 메모리 시간을 제외한 나머지 연속 구간이 Q3의 기존 두 시간 조건을 독립적으로 만족하면 Q3도 보존합니다. Q4가 긴 구간이면 그 안에서 메모리가 항상 높았다고 설명해서는 안 됩니다. 주간에서도 활동 패턴 구간은 KST 날짜 경계를 넘지 않으며 종류별로 고른 한 구간이 주간 전체 반복성을 뜻하지 않습니다. 완료 후보는 여러 날짜를 포함할 수 있어 이 제한과 구분합니다. 대기 후보는 GPU 신원 대신 인접 시간과 KST 날짜로 묶고 신원 변화·활동 결측이 있으면 구간 전체의 활동·메모리 참조를 보류합니다. 따라서 이미 전달된 후보만 재정렬해서는 누락된 판단을 되살릴 수 없습니다.

후속 설계는 유효 구간 구성 → 질문별 판단 → 대표 후보 비교 → 제한된 LLM 전달을 함께 검수합니다. 같은 Namespace의 다른 시간·다른 선택은 내부 검토 대상으로 보존하고 기존 시간·신원·표본 조건은 유지합니다. 높은 메모리 시간이 섞인 긴 구간에서는 나머지 구간이 독립적으로 Q3 조건을 충족하는지 검사하며, 신원/표본 기준을 낮추거나 제외를 피하려고 구간을 임의로 자르지 않습니다. GPU 수·Pod 교체가 많은 Namespace에 대한 구간 단절 편향도 함께 확인합니다.


**4단계 · Candidate selection and priority.** 첫 화면은 운영자가 우선 검토할 선택을 빠르게 읽는 곳입니다. 서로 다른 판단 3~5개를 목표로 최대 5개까지 제시하되, 유효한 제안이 적으면 더 적게 씁니다. 아래는 **선별 목표와 검수 사례**이며 현재 판단 범위 정렬의 세부 동작은 앞의 선별 계약과 구분합니다. Q1~Q5의 판단 범위는 1~3단계가 결정하고, 4단계는 그중 무엇을 먼저 보여줄지 정합니다. 선택에서 빠진 후보의 원래 수치·표·그래프·근거를 삭제하거나 값을 다시 계산하지 않습니다.

| 순서 | 정할 기준 | 기대하는 선택 |
|---|---|---|
| **① 제안 자격** | 기존 시간·신원·표본 조건으로 유효한 구간을 찾고, 3단계에서 허용한 선택·이유를 붙입니다. 실제 입력에 연결된 제약이 있으면 함께 적용합니다 | 하루 일부 결측 때문에 별도로 유효한 두 시간의 제안까지 지우지 않습니다. 단순 수치, 미정의 분석, 판단 보류를 개수 채우기용 조언으로 바꾸지 않습니다 |
| **② 주장 범위 고정** | 각 후보에 대상·구간·허용 선택·직접 근거·남은 조건을 연결합니다. 본문에서 사용할 관측과 사용할 수 없는 관측을 구분합니다 | 완료가 관측된 넓은 구간과 활동이 유효한 짧은 구간을 같은 범위처럼 설명하지 않습니다. 완료 표본은 유지하고, 유효한 활동 구간의 별도 판단도 보존합니다 |
| **③ 중복 정리** | 같은 대상·겹치는 구간에서 같은 선택과 이유로 이어지는 후보는 대표 하나를 우선합니다. 종류나 문구만 다른 것은 별도 가치로 세지 않습니다 | 의미가 같은 반복을 줄이는 목표와 기존 대상·기간 기반 자동 제외를 구분합니다. 후자는 이유가 달라도 적용되며 아래 계약 제한을 따릅니다. 서로 다른 기간의 수치를 합쳐 새 후보를 만들지 않습니다 |
| **④ 근거 우선 비교** | 아래 비교 순서를 적용합니다. 대기/할당과 시간대 검토에 고정된 종류 우선순위나 할당 개수를 두지 않습니다 | 근거가 더 분명한 시간대 후보가 약한 대기 후보보다 앞설 수 있고 반대도 가능합니다. 높은 활동·큰 대기 수·완료 건수만으로 우선하지 않습니다 |
| **⑤ 기존 필수 포함 조건** | 적격 후보 중 대표 완료와 클러스터 포함 조건을 먼저 만족할 수 있게 선택합니다. 그 안에서도 근거와 서로 다른 선택을 우선합니다 | 필수 포함은 출력 자리를 확보하는 조건이지 가장 중요한 판단이라는 뜻은 아닙니다. 대표 완료를 반드시 첫 번째 불릿으로 두지 않습니다 |
| **⑥ 개수·입력 제한** | 기존 최대 12개 전달·최대 5개 요약과 입력/실행 예산을 유지합니다. 필수 대표를 확보하고 남은 자리에 우선순위가 높은 후보를 담습니다 | Namespace·노드 수만큼 LLM 호출이나 본문을 늘리지 않습니다. 포함하지 못한 범위는 선별 근거에 남기며 일부 선택을 전체 클러스터·Namespace의 정상 판정으로 쓰지 않습니다 |
| **⑦ LLM 작성과 검수** | 코드가 허용 범위·근거·추천 순서를 제공하고 LLM은 선택과 이유를 짧게 작성합니다. 기존 검증과 별도로 사람이 의미·유용성을 대조합니다 | 문장이 자연스러워도 이유가 일반론이거나 우선 선택이 근거와 다르면 개선 검수에서 실패입니다. 기존 검증을 느슨하게 하거나 문장을 사람이 고쳐 AI 결과로 내보내지 않습니다 |

**근거가 더 분명하다는 의미와 비교 순서.** 가중 점수나 새로운 GPU 임계값을 만들지 않고 아래 순서를 사용합니다.

1. **해당 주장에 필요한 관측이 확인됐는가:** 2단계의 질문별 근거 역할·주장 방향 표로 판정합니다. 부분 표본의 양수 Pending을 그 범위의 존재로만 설명하는 Q2는 그 주장에 필요한 근거가 있습니다. 전 구간 부재·변화가 필요한 후보와 단순 표본 수로 비교하지 않습니다. 중요한 반대 조건이 미확인인 Q3는 확인을 먼저 해야 하는 후보로 구분하고, 알려진 양수 Pending·높은 메모리는 먼저 반영합니다. Q1의 보조 메모리 결측은 불이익으로 쓰지 않지만 Q4의 메모리 결측은 필수 근거 부족입니다. Q3의 메모리 결측은 실행 전 조건으로 명시하되 Pending 미확인과 같은 등급으로 임의 합산하지 않습니다. 부분 자료로 더 넓은 주장을 하려면 범위를 줄이거나 보류합니다. 실제 할당·예약 등 실행 전 조건은 별도로 명시합니다.
2. **별도로 보여줄 선택과 이유가 있는가:** 같은 관측 충실도에서는 이미 선택한 판단을 반복하지 않는 후보를 먼저 둡니다. Q5는 위에서 정의한 완료 시각·해당 시간대 또는 이후 시간대 Pending 연결을 점검 이유로 사용합니다. 완료 수나 경과 차이만으로 우선하지 않으며, 필수 대표로 선택된 사실도 높은 운영상 중요도를 뜻하지 않습니다. Q1의 조건부 확대 검토가 Q2의 점검보다 무조건 중요하지 않으며, 질문별로 한 개씩 강제하지 않습니다. 같은 종류라도 대상별 근거가 실제로 다르면 그 차이를 보존합니다.
3. **비교 가능한 후보끼리 세부 근거를 비교한다:** 같은 질문·관측 충실도·선택의 경우에만 유효하게 이어진 구간 길이를 먼저 비교합니다. 다른 종류의 '대기 7개'와 '낮은 활동 4시간'을 같은 점수로 환산하지 않습니다. 대기 수·완료 수는 설명 근거이며 대규모 Namespace를 항상 앞세우는 기준으로 쓰지 않습니다. 구간 길이는 개별 Pod의 연속 대기 시간이나 여러 날의 반복성을 뜻하지 않습니다. 이 비교는 같은 질문의 대표를 정할 때만 쓰고, 다른 질문의 대표끼리는 1·2·4번 기준으로 비교합니다.
4. **마지막 동률은 고정 순서로 처리한다:** 위 조건이 같으면 구간 시작 시각, 클러스터·Namespace·근거 ID 순으로 정해 같은 입력의 선별을 재현합니다. 이름순은 운영상 중요도나 판단 근거가 아닙니다. 이름이 달라져 마지막 자리의 선택은 바뀔 수 있어도 해당 후보의 허용 판단은 바뀌지 않아야 합니다.

동등한 취급은 질문별 고정 가중치·강제 할당량이 없다는 뜻이며, 매번 두 계열의 출력 개수가 같다는 보장은 아닙니다. 같은 등급에서 대기/할당과 시간대/메모리를 무조건 교대로 채우는 규칙은 채택하지 않습니다. 동률의 시각·이름 순서가 일부 선택을 결정한다는 한계를 명시하고 T14에서 확인합니다.

**선택 주체와 재현성.** 현재 정렬·저장 계약은 [조건부 운영 제안의 선별·완료 연결](#조건부-운영-제안의-선별완료-연결)에 정의합니다. 최대 5개 작성 후보는 응답 구조에 실제 ID를 모두 나열하고 LLM에 재선택하지 않도록 안내합니다. 원래 표·구간·근거와 모든 생성 후보는 보존하며, 전달/제외 수와 선택 질문을 narrative의 `selection`에 남깁니다. 기존 검증은 문장 유용성이나 모델의 추천 순서를 보장하지 않으므로 별도 의미 검수가 필요합니다.

**작성 범위.** 모델은 관측의 의미·판단 이유를 작성하고 코드는 후보별 점검 목적·선행 조건·행동과 수치 근거를 조립합니다. `decision` 입력에는 기존 `choice/scope/reason/needed/known`을 남기며 작성용 `option/action`과 `writing_focus`는 제외합니다. `writing_checks`는 이유 설명·관측 한계를 안내하고 `required_checks/required_prose_terms`로 행동 작성을 다시 요구하지 않습니다. `queue_context`·작업 연결·시간별 근거와 `related_observations`의 대상/기간 경계는 유지합니다. `observed_values`의 부분 미배치 영에는 일부 표본·미배정 유무 미확인을 붙이되 표본 양수와 저장 수치·참조는 보존합니다. 모델에는 수치·대상명·시각·참조 토큰·근거 문장 복사를 금지하며 후보별 행동과 근거, 두 구분 공백을 뺀 기존 360자/참조 제외 220자의 잔여 길이를 `prose_max_chars`로 전달합니다. 짧은 이유 한 문장이 기본이며 고정 최소 길이를 두지 않습니다. 최초·부분 보완은 같은 계약이고 정상 원문은 보존합니다. 조립은 복사본에만 수행하여 행동·근거가 보완 때 중복 부착되지 않습니다. 코드 행동은 모델 호출 전 기존 조건·금지 주장·길이 검사로 확인하며 실패하면 `invalid_code_advice`로 계산 요약을 유지합니다. 모델의 오류를 코드 문장으로 교체하거나 원문을 자동 윤문하지 않습니다. 부분 보완의 엄격한 ID/개수/주제 계약·JSON 모드·32KB 상한·최대 한 번 보완은 유지합니다. 사건 주제의 작성·참조 계약과 UI·RCA는 변경하지 않습니다. 해석 작성 버전으로 조립 변경을 기록하고 후보 기준 버전은 유지합니다.

**기존 계약 안에서 가능한 범위.** 전달 후보에 클러스터가 5개 이하이면 각 클러스터를 포함하고, 대표 완료가 있으면 포함하며, 같은 클러스터·종류는 하나만 선택하는 기존 조건을 유지합니다. 그래서 첫 화면의 다섯 자리를 모두 새로운 선택으로 채운다는 보장은 없습니다. 예를 들어 두 클러스터에 완료 후보만 있으면 둘 다 포함해야 할 수 있고, 한 클러스터의 같은 종류로 성립하는 여러 시간대도 모두 첫 화면에 놓을 수 없습니다. 가능한 자리에서 중복을 줄이고 제외된 근거는 상세에서 확인하게 합니다. 5개를 넘는 클러스터나 12개를 넘는 후보의 전체 대표성은 보장하지 않습니다. 필수 포함·입력 예산과 유용성 목표가 충돌하면 실제 사례를 남겨 별도 변경 여부를 결정하며, 검증 기준이나 보고서 품질을 조용히 완화하지 않습니다.

**의미 중복과 계약상 제외의 차이.** 현재 검증은 같은 Namespace에서 `batch_progress`의 기간 안에 포함된 `queue_review`를 설명 내용과 무관하게 제외합니다. 이미 적격인 완료를 반드시 포함해야 하는 경우, 그 안의 별도 대기 점검을 첫 화면에 독립적으로 보존한다는 목표는 기존 조건과 양립하지 않습니다. 남은 완료 문장에 대기 맥락을 담는 것은 그 완료 후보 자체의 시간·참조가 해당 설명을 지원할 때만 가능합니다. 넓은 완료 구간의 활동이 미확인이면 짧은 하위 구간의 활동을 전체 구간의 활동처럼 가져오지 않습니다.

기존 조건을 유지하는 첫 구현에서는 원래 시간대별 수치·표·그래프·상세 근거를 보존하고, 해당 대기 판단이 첫 화면에서 빠지는 제한을 검수 결과에 남깁니다. 독립 AI 불릿까지 보존했다고 표시하지 않습니다. 제외를 피하려고 기간을 인위적으로 자르거나 종류를 바꾸거나 필수 완료를 전달 목록에서 숨기지 않습니다. 두 판단을 독립적으로 보여주는 변경은 별도의 선택 검증 변경 검토 대상으로 남깁니다.

관측 설명·판단 보류만 성립하는 자료는 현재 제안 후보의 자격을 억지로 얻지 않습니다. 다만 이미 적격인 대표 완료의 필수 포함은 앞의 Q5 처리와 기존 계약을 따릅니다. 제안 후보가 없을 때의 기존 해석 경로, 응답 검증 실패 뒤 보완·계산 요약 경로는 유지합니다. LLM에 주는 범위와 참조는 코드로 고정하지만, 추천 순서나 문장 의미까지 기존 검증이 모두 보장하는 것은 아닙니다. 예를 들어 같은 할당 검토 후보에서도 조건부 확대 검토와 일반적인 스케줄러 점검 문장이 모두 기존 검사에 통과할 수 있습니다. 다음 검수에서는 후보의 허용 판단·우선 선택과 실제 문장에 드러난 선택을 각각 대조합니다. 일반론으로 선택이 사라진 응답은 기존 검증 통과 여부와 별도로 문장 품질 미달로 기록합니다. 자동 판정·추가 재시도·새 실패 코드를 도입한다는 뜻은 아닙니다.

**선별 가상 사례.** 아래는 3단계 S01~S25와 함께 검수할 기대 결과이며 실행 결과가 아닙니다. 별도 언급이 없으면 기존 필수 포함 조건을 만족한 뒤 남은 자리에서 비교합니다.

| 사례 | 후보 상황 | 기대 결과 |
|---|---|---|
| **T01 · 두 방향의 동등한 취급** | 관측이 충분한 Q3와 Q2가 경쟁하며, 각각 부분 표본 존재 설명 또는 전 구간 비교를 요구하는 변형도 구성 | 질문 종류 자체의 우선순위는 없습니다. 부분 Pending의 존재만 말하는 Q2를 표본 수만으로 낮추지 않습니다. 비교에 필요한 구간이 부족하면 그 비교를 보류하고 남은 관측 범위로 다시 비교합니다. 반대 조건 미확인 Q3는 확인 우선 범위로 낮춥니다 |
| **T02 · 규모·완전성만으로 정렬하지 않음** | 같은 질문의 부분 관측 Pending 30개와 완전 관측 3개. 같은 Namespace의 다른 구간·서로 다른 Namespace를 각각 구성 | Q2의 존재 주장에는 둘 다 근거가 있으므로 3개를 자동 우선하지 않고 30개를 더 심각하다고도 정하지 않습니다. 변화·연속 주장은 자체 조건으로 제한합니다. 같은 Namespace에서 최대 Pending 구간만 남기는 현행 편향과 후속 대표 선택을 별도로 검수합니다 |
| **T03 · 완료 반복과 시간대 후보** | 두 클러스터에 유사한 완료 후보가 있고, 한 클러스터에는 근거가 충분한 Q3도 있음 | 대표 완료를 포함한 뒤 다른 클러스터의 Q3로 범위를 충족할 수 있으면 그 조합을 우선합니다. 대표 완료가 Q3와 같은 클러스터라면 다른 클러스터의 완료도 필요할 수 있으며, 자리가 남으면 Q3를 더합니다. 클러스터 필수 조건을 지우지 않습니다 |
| **T04 · 질문 이름만 다른 중복** | 같은 Namespace·겹치는 구간의 Q1/Q2가 모두 같은 스케줄러 확인만 제안함 | 근거가 허용하는 우선 선택을 대표 하나로 설명합니다. 같은 구간의 완료·대기를 중복 제외하는 기존 조건도 유지합니다 |
| **T05 · 부분 기간의 유효한 선택** | 24시간 중 활동 8시간이 결측이고, 나머지에서 Q1 또는 Q3 조건을 충족하는 연속 두 시간이 있음. 별도 유효 완료 표본도 있음 | 두 시간에 한정한 판단과 완료 근거를 각각 유지합니다. 전체 하루 결론으로 확대하거나 완료 구간 전체에 활동이 연결됐다고 쓰지 않습니다 |
| **T06 · 이름·입력 순서·규모 변화** | 입력 행 순서 변경, Namespace 이름 변경, 4클러스터·100 Namespace·168시간으로 확대, 5개 초과 클러스터를 별도 구성 | 행 순서로 선별이 바뀌지 않고, 이름 변경은 최종 동률 외의 판단에 영향을 주지 않습니다. 후보/요약/입력 상한과 필수 포함 조건을 지키고 제외 범위를 남깁니다. 전부 분석·대표했다고 표현하지 않습니다 |
| **T07 · 조언이 성립하지 않음** | 기존 필수 완료 대상이 없으며, 미정의 조합·연결 실패 또는 관측 설명만 있는 자료 | 억지 제안을 만들지 않습니다. 유효 관측은 기존 상세에 남기고 기존 해석·대체 경로와 표시를 확인합니다 |
| **T08 · 다른 이유도 자동 제외됨** | 하루 완료 후보 안에 유효한 두 시간의 Q2 대기 점검이 있고, 넓은 완료 후보에는 활동 연결이 부족함. 둘의 점검 이유는 다름 | 기존 검증에서는 완료가 포함되면 Q2가 제외됩니다. 수치·상세 근거는 유지하되 첫 화면에 독립 판단이 남는다고 기대하지 않습니다. 완료 문장에 두 시간의 활동을 하루 근거처럼 붙이지 않습니다 |
| **T09 · 통과와 유용성의 차이** | 같은 Q1 후보에 대해 조건부 확대 검토 문장과 일반적인 스케줄러 점검 문장이 모두 기존 검증을 통과함 | 근거상 Q1 선택을 설명해야 하는 사례라면 일반적인 점검만 남긴 답은 문장 품질 미달입니다. 기존 검증기를 통과했다는 결과는 그대로 기록하고, 의미 검수에서 별도로 구분합니다 |
| **T10 · 필수 완료의 제한된 가치** | 유효 완료 한 건과 완전한 대기 연결로 기존 대표 완료 조건은 충족하지만, 완료 시점 및 이후의 유효 시간에 양수 Pending은 없고 별도 경과 비교도 불가능함 | 필수 완료는 유지하되 표본·경과와 확인할 기록만 짧게 설명합니다. 경과 차이·실행 이상·우선 점검 필요성을 꾸며내지 않습니다. 새로운 운영 선택으로서 가치가 제한적이라는 평가를 남깁니다 |
| **T11 · 다섯 클러스터의 필수 완료** | 후보 클러스터 5개, 필수 대표 완료와 강한 Q1이 같은 클러스터, 최대 5개 | 각 클러스터와 대표 완료를 포함하면 그 Q1의 추가 자리가 없을 수 있습니다. 별도 판단 누락을 기록하고 완료를 숨겨 해결하지 않습니다 |
| **T12 · 다섯/여섯 클러스터 경계** | 같은 후보 자료에 여섯 번째 클러스터 추가 | 현재 5개 이하 전부 포함 조건이 6개에서 적용되지 않는 불연속을 드러냅니다. 전체 커버리지로 표현하지 않으며 축소 전달안도 원래 대상·제외 범위를 비교합니다 |
| **T13 · 규모·신원 교체 편향** | GPU·Pod 교체가 많은 Namespace와 작고 안정적인 Namespace | 무효 신원을 수용하지 않습니다. 유효 하위 구간과 단절 사유를 분리 검수하고 규모만으로 열등한 운영 상태라고 하지 않습니다. 현재 selection에는 후보 생성 전 탈락 사유가 모두 남지 않는 한계도 기록합니다 |
| **T14 · 동률과 LLM 선택** | 같은 근거 등급의 대기/할당 3개와 시간대/메모리 3개, 남은 자리 3개 | 코드 동률 순서는 재현하되 강제 교대로 같은 비율을 보장하지 않습니다. 같은 전달 후보로 LLM의 포함·순서가 달라지는지 별도 대조합니다. 코드 최대 5개 전달 비교안도 전체 포함·순서 보장으로 표시하지 않습니다 |

### 1~4단계의 연결과 구현 전 확인

아래 네 단계는 **후속 개발 기준**입니다. 이 상세 명세는 검토할 기준을 정하는 문서이며 보고서 동작을 바꾸지 않습니다. 문서 검토 후 Ops 후보 구성·선별·LLM 입력을 구현하고, 고정 자료·실제 모델·운영 신규 발행 순으로 별도 검증해야 합니다. 목표는 같은 패턴의 이름·값이 달라도 같은 종류의 운영 선택을 제안하고, 관측 품질·제약이 달라지면 그에 맞게 범위를 바꾸는 것입니다. 첫 화면의 선택 여부와 문장 표현까지 항상 같다는 뜻은 아닙니다.

| 단계 | 방향 검토와 보완 | 구현 후 확인할 결과 |
|---|---|---|
| **1 · 운영 질문** | 할당 검토와 시간대 검토를 동등하게 두고, 메모리·완료는 별도 선택을 도울 때 포함합니다. Q2는 Q1과 중복되는 독립 불릿이 아니라 구체적인 점검 이유로도 사용합니다 | 운영자가 무엇을 먼저 할지 한 문장으로 읽을 수 있으며, 모든 질문을 채우거나 수치만 나열하지 않음 |
| **2 · 필요한 근거** | 각 선택의 필수·반대·보조 근거와 추가 확인 조건을 구분합니다. 부분 기간의 유효 관측을 살리고, 서로 다른 구간·순간 상태·요청량/실제 할당량을 섞지 않습니다 | 같은 수치·근거를 사용하면서 알려진 것과 추가로 확인할 것이 분리됨 |
| **3 · 해석 범위** | 조건부 검토·점검·관측·보류의 경계를 유지합니다. 높은 활동·대기만으로 GPU 부족을 확정하거나 관측 0%를 미사용으로 해석하지 않습니다 | S01~S25의 판단이 일관되며, 성립하지 않는 선택은 하지 않고 유효한 관측은 유지함 |
| **4 · 선별과 우선순위** | 후보 구성부터 근거와 다른 선택의 가치를 비교합니다. 기존 대표 완료·클러스터·최대 개수 조건으로 남는 제한도 명시했습니다 | T01~T14에서 기존 계약 안의 우선 선별을 확인하고, 자동 제외로 남길 수 없는 판단·필수 포함의 한계까지 구분함 |

**이 기준으로 기대하는 개선과 한계.** 현재 관측으로 “어느 Namespace의 어느 구간을 할당 검토 대상으로 볼지”, “어느 시간대를 시범 실행 후보로 볼지”, “그 전에 무엇을 어떤 이유로 점검할지”의 판단 기준을 정할 수 있습니다. 이를 후보와 실제 문장이 일관되게 재현하는지는 후속 검증 대상이며, 모든 유용한 판단의 첫 화면 포함이나 반복 없는 결과까지 기존 검증이 보장하지 않습니다. GPU를 몇 개 더 줄지, 내일 어느 시간이 반드시 비어 있는지, 실제 대기 원인이 무엇인지 확정하는 기준은 아닙니다. 이를 원하면 실제 할당·가용량·예약·스케줄러 사유·작업 목적의 별도 연결이 필요합니다.

다음 구현은 Ops의 후보 구성·선별·LLM 입력/작성 안내와 해당 테스트를 대상으로 합니다. 기존 저장 narrative·화면·HTML 소비와 자동/수동 공통 경로를 확인하고, 필요한 선별 사유는 기존 `selection`·`selection_basis`의 의미와 호환 범위에서 설명합니다. 수집·기존 산식·품질 판정·CSV·RCA·기존 해석 검증 조건은 변경하지 않습니다. 현재 계약으로 허용되지 않는 새 후보 형식이나 관측/보류 전용 AI 유형은 별도 작업으로 남깁니다.

완료 판단은 문서의 타당성, 코드의 후보/선별 재현, 실제 LLM의 유용성을 나눠 검수합니다. 먼저 S01~S25·T01~T14를 현재 계약 내 사례와 미지원 입력·결정 대기 사례로 나눠 고정 자료로 대조한 뒤, 같은 기간·설정의 자동/수동 저장 보고서 한 쌍, 활동 결측·Pod 생성/삭제·신원 교체가 많은 실제 보고서와 주간 보고서로 수정 전후를 비교합니다. 비교 시 원래 계산·참조·검증 조건 불변, 허용 선택과 근거 일치, 후보 우선순위 반영, 피할 수 있는 반복의 제거, 계약 때문에 남은 반복·누락, 두 문장 이내의 쉬운 표현을 각각 확인합니다. 같은 근거에서 표현만 달라진 답과 우선 선택 자체가 달라진 답을 구분하고, 대표 완료의 필수 포함을 운영상 중요도로 평가하지 않습니다. 실자료에 없는 양성 분기는 가상 사례 검증으로 남깁니다. 모델 응답이 채택돼도 운영자가 **대상·시간, 우선 선택, 그 이유, 남은 조건**을 읽을 수 없으면 개선 완료로 판단하지 않습니다. 운영 신규 발행 검증은 저장 자료 재생과 별도로 남깁니다.

Planned stages 1–4 define operator choices, evidence requirements, interpretation boundaries and evidence-first selection. Queue/allocation and scheduling receive equal consideration; existing coverage, representative-batch, size and validation constraints remain. These documentation criteria do not establish runtime implementation, live-model usefulness or production publication.

### 구현 범위와 결정 대기 항목

| 구분 | 범위와 완료 조건 |
|---|---|
| 문서에서 확정 | 지표 의미, 질문별 근거 역할, 주장별 완전성, Q3 대상, Q5의 관측/점검 구분. 문서 일치만 검증하며 실제 생성 성공을 뜻하지 않음 |
| 구현·후속 코드 변경 | 유효 구간 보존·대상/질문 대표 우선·미배치 참조/작성 안내를 구현. 운영 선택·이유·추가 근거의 `decision`과 판단 범위 정렬을 구현. 최대 5개 작성 후보는 필수 완료·클러스터 이후 다른 선택을 보태며, 아직 관측 참고뿐인 필수 완료를 숨기지 않음. 기존 임계값·필수 포함·검증·입력 상한을 유지하고 후보 기준 변경은 CRITERIA revision과 회귀 범위를 기록 |
| 저장 형식·소비자 검토 | 미배치 값/표본은 `source_hours`에 추가하며 기존 참조를 유지. 신규 숫자 metric·조회·CSV 변경 없음. 판단 이유는 `decision`에, 선별된 선택과 필수 완료 여부는 `selection.decisions`에 저장. 후보 생성 전 질문별 전체 보류/제외 사유 저장은 미구현. 후보 `**fact`가 narrative에 보존되므로 단순 프롬프트 수정이 아님. 미배치 추가 필드의 참조·저장 및 기존 결과 읽기는 로컬 회귀 범위로 확인하며, 실제 LLM·운영 신규 발행은 별도 검증 |
| 별도 결정 전 유지 | Q1의 미배치 필수화, 대표 완료 필수 포함, Q2 자동 제외 범위, 종류별 필수 어휘, 최종 목록/순서 강제. 수집·검증 조건 변경을 현재 문서 작업에 포함하지 않음 |

**미배치 연결과 Q1/Q2 분기 — 구현과 남은 결정.** 같은 시간대의 저장된 `unscheduled_peak/samples`를 후보의 `source_hours.unscheduled/unscheduled_samples`로 연결합니다. 유효 개수·평가 수와 Pending 이하 여부를 확인하며, 자료가 없거나 맞지 않으면 미확인입니다. 기존 수집·집계 결과 자체를 바꾸지 않습니다. 최초 작성과 문장 보완 모두 `queue_context.check_first`를 전달합니다. ① 유효 미배치 양수면 `placement`, ② 전 구간 미배치와 Pending의 240개 평가가 확인되고 미배치 최대 0·Pending 양수면 `preparation`, ③ 그 외는 `unknown`입니다. 부분 표본의 양수는 존재 근거로 쓰되 전 구간 부재를 말하지 않습니다. 모든 시간에 유효 미배치 값이 있을 때만 선택적 `{{unscheduled}}` 참조를 제공합니다. 기존 필수 토큰·문장 검증은 유지합니다.

이는 먼저 대조할 기록의 구분이며 원인 확정이 아닙니다. ②도 평가 시점에 `PodScheduled=false`인 Pending이 관측되지 않았다는 뜻일 뿐, 모든 Pod의 배치 완료나 이미지 장애를 증명하지 않습니다. 두 최대값을 빼서 준비 Pod 수를 만들지 않습니다. Q1의 기존 자격과 미배치 필수화 보류는 유지합니다. Q2의 준비 단계 이벤트 점검은 기존 이벤트 필수어 조건으로 검증 가능하며, 스케줄러 문구를 억지로 붙이지 않습니다. 작성 안내는 내부 분기명 대신 미배치 관측과 점검 이유를 쉬운 한국어로 쓰고, 기존 클러스터 포함 조건을 반환 전에 확인하도록 합니다. Namespace의 일반 참조(`{{target}}`, `{{period}}`)는 코드가 조립하고, 사건의 관측·확인 대상 ID 참조(`{{target:fact_id}}`, `{{period:metric_id}}`)는 코드가 작성합니다. 각 후보의 `decision`과 `writing_checks`는 허용된 판단 범위·관측 이유·한계를 제공합니다. `decision.needed`는 참고용 미확인 근거이며 조건·행동 작성 지시가 아닙니다. `summary_start`는 코드의 필수 근거 문장입니다. LLM은 관측 현상과 판단 이유만 반환하고, 코드가 점검 목적·조건·행동과 대상·기간·필수 관측 참조를 이어 붙입니다. 토큰·단위·미확인 의미와 기존 필수 어휘 검사는 조립된 문장에 그대로 적용합니다. 분기별 초점은 입력에서 한 번만 전달하며, 최종 문장에 내부 작성 지시를 복사하지 않습니다. 보완은 같은 선택·이유·필수 조건을 유지하면서 지적된 설명만 바꿉니다. 근거는 최초와 같은 코드로 조립하며 새 통과 조건을 추가하지 않습니다. 대기와 미배치 값이 같아도 서로 다른 참조를 유지하고, 준비/배치 두 분기를 나열하거나 준비 지연을 단정하지 않습니다. 기존 `conditional_scheduling_review_required`·`duplicate_summary_unit`·`unsupported_queue_cause` 오류도 동일한 문장 보완 경로로 보내며 검사 자체·최대 두 시도·예산·입력 상한은 유지합니다. 구조와 참조를 고정할 수 있는 첫 응답에서는 모든 주제를 독립 검사하고, 잘못된 Namespace 항목(`summary_repair`)과 사건 주제(`section_repair`)를 같은 두 번째 요청에 모읍니다. 정상 주제·항목은 보완 입력에서 제외하고 원문 그대로 보존합니다. 응답의 키·항목/주제 ID·개수가 요청과 일치할 때만 해당 부분을 교체한 뒤 전체 응답을 기존 검사로 재검증합니다. 잘못된 구조·중복 선택·전체 선별 오류는 기존 전체 보완으로 남기며, 부분 보완 요청 전체가 기존 32KB 상한을 넘으면 추가 호출 없이 계산 요약을 유지합니다. 이는 정상 JSON/참조에 한정된 보존 보장이며 부족한 토큰 예산을 늘리지 않습니다. 준비 단계 후보는 다른 질문과 동등하게 비교하며 특별히 우선하지 않습니다. 정상 기동과 지연을 구분할 지속 시간 근거가 없으면 지연을 단정하지 않습니다. 이는 검증 조건 추가나 채택 보장이 아닙니다. 실제 LLM 문장의 유용성·신규 발행은 로컬 코드/fixture 검증과 구분해 [Agent QA](../../../agents/QA.md)에 기록합니다.

Namespace 설명의 수치·참조 검증 뒤에는 후보별 문장 정합성을 추가 검사합니다. 미배치 관측이 불완전한데 미배정 부재나 전체 배정 완료를 단정하거나(없었습니다뿐 아니라 없었으므로·없었고·없었으며·없었지만·없었으나·없었는데·없어/없어서와 노드 접두어 없는 미배정 표현 포함), 후보 시간의 완전한 대기 관측이 모두 영인데 현재 대기 Pod 일부를 대상으로 지목하면 해당 문장만 부분 보완합니다. 할당 검토에는 스케줄러 사유·GPU 요청·실제 할당·보장량·가용 GPU·운영정책을, 시간대 시범 실행 검토에는 마감·예약·대기·가용 GPU를, 상대적 저활동 검토에는 기존 마감·예약·가용 GPU·메모리 요구를 확인·대조·점검한 뒤 최종 검토·판단하는 조건을 보존해야 합니다. 이 필수 목록은 기존 `PREREQUISITES`를 유지하며 코드 행동과 조립 결과에서 검사합니다. 코드가 붙인 메모리 관측 수치는 메모리 요구 확인 조건을 대신하지 못합니다. 코드 행동만으로 기존 후보 포함·제외 관계를 확인한 다음 원문의 직접 지시·운영 행동 서술·권고·당위형과 검토 대상 분류를 이유 전용 위반으로 거절합니다. 원문에 옛 완성 문장 검사를 적용해 필수 조건을 채우도록 요구하지 않습니다. 큐·배치 점검 중복도 같은 위반이며 정상 부정·한계·미확인 설명은 구분합니다. capacity의 긍정형 부족·부족 원인 단정은 별도 원문 검사로 거절합니다. 마지막에 중복 실행하던 원문 관측 검사는 최종 조립 전으로 이동했으며 이 순서 정리는 차단 결함 수정과 별개입니다. 관측 패턴·후보 선별·필수 조건·참조 검증은 유지합니다. 코드 행동의 오류는 모델 호출 전에 실패시키며 조건을 다시 작성하도록 요구하지 않습니다.

조건 검사는 첫 번째 '뒤' 이전의 단어만 세지 않습니다. 최종 검토·판단 전에 명시적으로 확인·대조·점검하는 구절의 조건을 모으며, 여러 단계의 점검도 합산합니다. 검토하려면 조건을 확인한 뒤 판단한다는 문장과, 기존 조건 확인 뒤 운영정책을 점검하고 검토하는 문장을 허용합니다. 앞선 관측 문장이나 분리되는 관측·이유 구절에 나온 '대기' 등은 확인 조건을 대신하지 못합니다. 낮았으며·관측됐으며 같은 관측 연결 표현, 미확인·확인하지 않음·확인 생략도 실제 확인 조건으로 세지 않습니다. 이미 확인했거나 확인을 생략하지 않는 정상 표현은 구분합니다. 변경 검토 뒤로 옮긴 점검 조건도 인정하지 않습니다. 상대적 저활동 검토의 순서는 기존 문장 간 확인 후 조건을 유지하므로, 조건을 먼저 확인한 다음 별도 문장에서 '그 뒤' 검토하는 표현도 허용합니다. 기존 `validate_advice`의 '검토'·확인 후 조건, 참조·길이·금지 주장 검사는 그대로 적용합니다. 시작 시각을 먼저 변경한 뒤/후에 검토하는 표현과 조정해 시범 실행을 검토한다는 표현은 보완 대상입니다. 다만 기존 필수 확인 조건을 만족한 조정해/조정해서/조정하고 시범 실행할지(또는 실행할지를) 검토하는 문장은 실행 여부를 묻는 조건부 선택으로 구분합니다. 이 조건형 뒤에 다시 변경한 뒤 검토한다는 구절이 있으면 계속 거절합니다. 불완전 관측에 대한 없다고 단정/판단할 수 없다는 표현도 부재 단정과 구분합니다. 한계 문장을 뒤에 붙였다는 이유만으로 앞선 부재 단정을 허용하지 않습니다. 코드 행동은 조건을 확인한 뒤 시작 시각을 조정할 수 있는 작업 일부의 시범 실행 여부를 검토하도록 구성하며 최초·부분 보완 모두 같은 행동을 사용합니다. 조정할 수 있는 작업이라는 조건부 대상 표현은 허용하며, 모델 원문을 코드가 고쳐서 통과시키지는 않습니다. 활동률의 주어를 개별 작업·Pod로 직접 단정한 표현도 보완 대상으로 삼으며, 연결 GPU의 관측과 확인된 작업 유형 맥락을 구분하도록 안내합니다. GPU에 연결된 작업이라는 표현 자체를 금지하지 않습니다.

기존 후보·계산·토큰·금지 주장·길이·보완 ID 검사는 그대로 두고, 원문을 자동 교정하거나 채택 문장으로 대체하지 않습니다. 기존 최대 한 번의 보완에도 통과하지 못하면 계산 요약을 유지합니다. 한국어 구절과 표현 패턴 검사는 모든 의미 오류를 증명하는 검사가 아니며, 새 표현의 오거절·미검출과 실제 모델의 수정 성공·운영 유용성은 별도 검수합니다.

**완료와 선택 슬롯.** Q5는 완료·경과 관측, 같은 구간 대기 기록 대조, 비교 보류를 구분합니다. 완료 표본이 있어도 마지막 구간에 대기가 관측되면 해당 Namespace의 관측 대기 Pod가 노드 배정 전인지 기동 준비 중인지 상태·이벤트로 구분하도록 제안합니다. 마지막 시간대에도 미배치가 관측됐으면 스케줄러 이벤트에서 그 사유를 먼저 확인합니다. 완료가 대기를 줄였다고 추정하거나 Job 경과시간을 순수 실행시간으로 쓰지 않습니다. 대기가 0이라는 이유로 작업 조건 쪽에 문제가 있다고 바꾸거나 완료 Job의 보고기간 밖 생애까지 무대기로 확장하지 않습니다. 현행 대표 완료는 전달된 적격 batch 중 판단 범위·근거 정렬로 정해지며, 필수 포함은 운영상 중요도와 별개입니다. 더 강한 다른 제안을 밀어내는 사례를 남기고, 필수 포함/자동 제외를 유지할지 또는 대표 선정 자체를 바꿀지는 별도 결정으로 둡니다. '다른 종류가 없는 클러스터의 완료를 대표로 선택'하는 안도 그 결정의 비교안이며 현재 기준이 아닙니다.

**판단 보류의 표시 한계.** 현재 `selection`은 만들어진 후보의 전달·제외를 집계하며 후보 생성 전 탈락한 모든 질문·사유를 저장하지 않습니다. 따라서 보고서에 조언이 없다는 사실을 정상 판정으로 읽을 수 없고, 질문별 보류가 화면에 모두 보인다고 주장하지 않습니다. 보류 건수·구간 단절 사유를 추가하려면 집계 단위·중복 방지·narrative 및 화면/HTML 소비 계약을 정해야 합니다. 첫 구현은 검수 자료에 이 공백을 기록하며 제품에 보류 표시가 추가됐다고 하지 않습니다.

**제약 입력과 S15 — 별도 후속 범위.** 최소 입력은 적용 cluster/Namespace와 유효 기간, 제약 내용·의도된 동시 실행 범위, 근거 출처와 revision, 확인 주체·시각, 유지할지 재검토할지의 운영자 의도를 포함해야 합니다. 읽기/검증·저장·LLM 전달 계약은 미정입니다. 테스트 라벨이나 사람의 설명만으로 현재 후보에 이 맥락이 연결됐다고 하지 않습니다. 제약 유지가 목적이면 관측 설명과 확대 보류가 기본이며, 제약 변경 검토가 요청된 경우에만 그 선택을 검토합니다.

**제안과 근거 표시 계약.** 채택된 Namespace `summary`에서 첫 문장과 정확한 `대상 · 기간:` 경계가 확인될 때만 `summary_parts.decision/evidence`에 원문 조각을 추가합니다. 기존 `summary`·필수 참조·검증 결과는 보존하며 분리 실패를 새 탈락 사유로 삼지 않습니다. 프런트엔드는 두 조각을 공백 없이 또는 공백 하나로 연결한 값이 원문과 정확히 같을 때만 제안과 대상부터 보여주고, 수치·기간·적용 조건·근거 링크는 항목별로 펼칩니다. 과거 형식·불일치는 전체 요약 표시로 돌아갑니다. HTML 내보내기는 기존 전체 요약을 유지합니다.

### 선별과 문장 품질은 별도로 확인

이 절은 **현재 구현과 별도 문장 품질 검수**를 설명합니다. 판단 범위 정렬은 구현됐지만 위 가상 사례 전체나 운영상 유용성이 입증됐다는 의미는 아닙니다.

1. **근거 연결:** `candidates()`·`windows()`가 같은 구간의 유효 관측을 구성합니다. 전송된 지표가 있다는 사실과 제안에 쓸 만큼 연결됐다는 판단은 다릅니다.
2. **후보 전달:** Namespace 대기는 인접 시간·KST 날짜로 묶고 GPU 신원 변화로 조각내지 않습니다. 신원 변화나 활동 누락이 있는 대기 구간 전체에는 활동·메모리 참조를 만들지 않습니다. 대신 그 안에서 같은 GPU 신원·연속 시간·KST 날짜와 기존 활동 유효성 조건을 만족하는 두 시간 이상의 구간은 별도 대기 후보로 보존합니다. 동일한 대기 표본 완전성에서는 활동이 연결된 대기 후보를 먼저 비교합니다(`candidate_revision=ops-operating-choices-v6`). 넓은 대기 후보도 유지하며 짧은 구간의 활동·메모리를 전체 구간으로 확장하지 않습니다. `select_candidates()`는 위의 판단 범위 정렬과 대표 완료 조건을 적용하며, 필수 완료 안의 대기·대안이 있는 비필수 완료를 줄이고 최대 12개를 전달합니다. 완료·대기 연결이 부족한 표본은 표에 남기되 해당 AI 후보에서 제외합니다. 노드·Namespace 수만큼 LLM 호출을 늘리지 않습니다.
3. **첫 화면 선택:** `writing_candidates()`가 필수 완료·클러스터와 서로 다른 질문을 최대 5개로 먼저 좁히고 LLM이 그 안에서 선택합니다. 기존 검증의 클러스터 포함·대표 완료 필수 조건은 유지합니다. 다른 클러스터에 다른 질문이 있으면 같은 완료 설명을 복제하기보다 그 질문을 선택하도록 작성 지시하지만, 이는 현재 중복을 완전히 차단하는 코드 규칙이 아닙니다.
4. **짧은 판단:** 한 불릿은 우선 검토할 선택과 관측에서 나온 이유를 앞에, 대상·시간·필수 관측을 뒤에 두 문장으로 연결합니다. 필수 완료는 다음 배치 계획에 경과시간을 적용하기 전 완료·대기 작업 유형 비교로 제한하며, 정상 순차 실행도 가능한 관측을 이상으로 격상하거나 제출 순서를 바꾸라고 하지 않습니다. “확인하도록 검토하세요” 대신 확인할 일은 “확인하세요”, 조건부 자원 변경·시간대 이동은 “확인한 뒤 검토하세요”로 구분하는 것을 문장 품질 목표로 둡니다. 필수 수치를 빼서 짧게 만들거나 근거 없는 이유를 덧붙이지 않습니다.
5. **의미 검수:** 근거·참조 검사 통과와 별도로 최대값/범위 표시, 완료와 대기의 다른 질문, 조언 반복, 쉬운 표현을 원문과 대조합니다. 실패한 항목은 [Agent QA](../../../agents/QA.md)에 남기며 통과율만으로 유용성을 주장하지 않습니다. 이 의미 검수 항목은 기존 런타임 검증을 추가·완화한 것이 아닙니다.

### 같은 대상의 근거 연결과 판단 일관성

작성 입력의 `related_observations`는 기존 최대 5개 작성 후보 중 같은 `cluster_id`·`namespace`의 다른 후보만 연결합니다. 후보 ID·종류·기간·GPU 모델과 기존 `decision`의 선택·범위·관측 이유를 전달하며, 새 수치·완성된 제안 문장·다른 후보용 참조는 추가하지 않습니다. 연결 순서는 후보 ID로 고정하고 최초 작성과 부분 보완에서 같은 맥락을 유지합니다. 이 연결은 이유 작성의 맥락이며 후보·선별·계산·참조/의미 조건·시도/길이/32KB 상한·저장 결과 계약을 바꾸지 않습니다. 관련 맥락 때문에 입력 상한을 넘으면 기존 계산 요약 경로를 유지합니다.

최종 문장은 모델의 관측 사실·판단 이유 → 코드의 다음 확인 목적·조건·행동을 연결합니다. `decision.needed`는 참고용 미확인 근거이며 모델에 점검 조건이나 행동을 다시 쓰라는 지시가 아닙니다. 최초·다수 클러스터 응답 틀과 보완 오류 안내 모두 이유 전용 계약을 사용합니다. 완료·대기 후보의 유형 대조는 완료 Job과 대기 Pod의 작업 유형을 비교해 완료 기록을 참고할지 확인하는 코드 행동입니다. 같은 자료에서는 표현을 바꾸더라도 허용 선택·우선 확인 기록·조건을 바꾸지 않습니다. 완료와 대기가 같은 Namespace에 있어도 같은 Pod·동시 발생·완료로 인한 대기 해소를 주장하지 않습니다. 관련 후보는 각각의 기간과 판단 범위를 유지하며 현재 항목의 참조나 권한을 넓히지 않습니다. 일부 작업 표본의 GPU 요청·노드 배정·테스트 라벨은 전체 Namespace의 실제 할당·대기 단계·업무 목적을 대신하지 않습니다.

품질 검수는 같은 저장 보고서·후보·모델 설정·예산을 고정해 전후 각각 반복 생성합니다. 계산/CSV/후보 불변과 기존 검사 채택 여부는 코드로 대조하고, 원문에서 사실 정확성·확인 목적의 구체성·중복·허용 선택/조건의 일관성을 별도로 읽습니다. 코드가 붙인 `decision.choice`가 같다는 사실만으로 모델 문장의 판단이 일관됐다고 하지 않습니다. 미배치 양수·완전한 0·부분 표본 0처럼 근거가 달라지는 분기는 구분돼야 하며 실제 자료에 없는 분기는 fixture 검증으로 표시합니다. 실패·보완 응답을 제외하지 않고, 소수 반복의 일치는 전체 기간·모델·운영 신규 발행의 품질 보장이 아닙니다. 확인 결과는 [Agent QA](../../../agents/QA.md)를 따릅니다.

### 현재 기준에서 추가로 발전시킬 항목

다음은 **미구현**이며, [현재 후보](#namespace별-조건부-제안)의 지원 범위로 표시하지 않습니다.

| 보강할 질문 | 지금의 근거로 가능한 범위와 추가 작업 |
|---|---|
| 활동은 높은데 메모리 점유는 낮은가 | 시간·신원·모델이 연결된 활동/메모리를 바탕으로 연산 활동과 장치 메모리 점유의 대비를 설명할 수 있음. 현재 별도 후보는 없음. 낮은 메모리 기준과 유효 표본 조건·선별 순서를 먼저 정의하고 경계/결측 검사를 추가해야 함. 메모리 여유만으로 GPU 공유·축소 또는 연산 병목을 권하지 않음 |
| 대기 중 GPU 활동이 낮은 시간과 높은 시간을 구분할 수 있는가 | 현재 높은 활동+대기 조건은 확대 검토, 그 외 양수 대기는 배치 제약 점검으로 분리. 더 구체적인 원인 분기는 스케줄러 이벤트·배치 제약의 저장·연결이 필요. 테스트용 의도된 대기를 자원 부족으로 바꾸지 않음 |
| 같은 종류의 작업 경과시간이 달라졌는가 | 현재는 완료 표본의 경과 범위만 설명. 작업 유형 라벨·요청 GPU/모델·입력 조건과 비교 기간을 연결해야 동등한 작업끼리 비교 가능. 현재 완료 건수와 경과 범위만으로 처리량·성능 순위를 만들지 않음 |
| 반복해서 비는 시간대로 작업을 옮길 수 있는가 | 현재는 관측한 날짜의 시간대 후보만 제시. 여러 날짜에서 같은 신원/구성·표본 조건으로 반복성을 검증하고 예약·대기·작업 마감 조건을 연결해야 반복 일정 추천으로 확장 가능 |
| 대기 구간과 노드 사건을 함께 볼 수 있는가 | 기존 사건 자료가 있어도 같은 클러스터·시간만으로 Namespace 영향은 증명되지 않음. 노드/Pod 연결·시각·출처를 검증해 Ops 입력에 연결한 뒤 기록 대조 대상으로 검토. RCA 원인 판정을 바꾸거나 미배치 Pod에 임의의 노드를 붙이지 않음 |
| 대기가 잠깐인지 오래 유지되는지 구분할 수 있는가 | 현재 시간 최대값으로는 불가. 양수 평가 수·상태 구간 또는 Pod별 생명주기 등 별도 관측 계약 필요. 양수 평가 수만으로 같은 Pod의 대기 시간을 확정하지 않음 |
| 클러스터에 쓸 수 있는 GPU가 있는가 | **2026-10-21 후속 과제: GPU 할당 여유 분석.** 같은 시각·노드·모델의 물리 GPU inventory, 배정 가능량, 배정된 Pod의 유효 GPU 요청량과 대기 작업 요구·제약을 연결. Allocatable은 잔여량이 아니고 기간 중 고유 관측 GPU 수는 동시 할당량이 아님. 미할당 GPU와 할당됐지만 활동이 낮은 GPU를 구분하며 MIG·공유 자원은 별도 계산. 조건이 맞는 미할당 GPU 활용 → 낮은 활동 작업의 점유 필요성과 재배분 점검 → 맞는 자원이 모두 할당되고 높은 활동·대기가 지속될 때 확대 검토를 구분. 미할당 자원이 있어도 대기가 남으면 노드/모델·정책 한도·배치 제약을 대조. 현재 신규 보고서에는 미구현이며 원본 지표의 실제 저장 여부부터 확인. 기존 활동률·계산·검증·RCA는 유지하고 별도 근거/집계로 추가 |
| 할당 한도와 수집 범위를 넓힐 수 있는가 | ResourceQuota·Run:ai 한도/보장 정보, MIG·init 전용 요청은 별도 의미·수집 계약 검토. 요청량·실제 할당·정책 보장은 구분하고 현재 지원으로 표시하지 않음 |

먼저 현재 지원하는 분석이 위 운영 질문에 어떤 선택과 이유를 제공할 수 있는지 실자료로 검수합니다. 새 후보는 그다음에 같은 근거 연결·선별·문장 검증 경로에 추가하며, 새 대주제나 Namespace별 무제한 설명을 만들지 않습니다. 임계값 변경은 글쓰기 수정과 분리해 비교하고 `CRITERIA` revision·QA에 남겨야 합니다.

Current runtime behavior is owned by `namespace_advice.py`; detailed interpretation criteria and planned stages 1–4 are owned by this specification. Existing gates, metrics, candidate thresholds and RCA stay unchanged. Proposed extensions are explicitly unimplemented; evidence acceptance and useful operational writing remain separate checks.
