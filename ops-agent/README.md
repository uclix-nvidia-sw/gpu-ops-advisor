# Ops Report Agent

JC에서 보고서 작업을 인수하고 관측·사건을 집계해 결과와 HTML/CSV를 저장한다. 신규 집계 보고서와 기존 O계열 보고서는 서로 다른 입력 계약이며 [workflow.py](src/ops_agent/workflow.py)가 분기한다. 기존 일정·결과를 자동 변환하지 않는다.

## 신규 기본 보고서

`report-aggregate-v1`은 `namespace_usage`·`incident_summary`의 일일/주간 보고서와 직전 동일 기간 비교다. [집계 보고서 계약](../docs/specs/ops-agent/aggregate-report-v1.md)이 쿼리·산식·제한·검수 기준의 담당 문서다.

- [report_queries.py](src/ops_agent/report_queries.py)의 Ops 전용 PromQL을 사용한다. 공통 D registry를 읽지 않는다. 클러스터·기간별 활동, Pod 신원, GPU 신원 3개 range 조회를 1시간 간격으로 수행한다.
- [namespace_usage.py](src/ops_agent/namespace_usage.py)는 유효 활동 합계/유효 표본 수로 평균을 계산한다. 관측 연결은 전용 할당의 증거가 아니다.
- [identity_transitions.py](src/ops_agent/identity_transitions.py)는 시간대 내 신원 변경이 모호한 GPU·시간대만 추가 조회한다. 검증 요약을 보존하고 이 추가 조회의 원본 표본 배열은 저장하지 않는다.
- [report_store.py](src/ops_agent/report_store.py)는 같은 DB snapshot에서 사건과 공개 RCA ID/hash를 읽는다. 새 RCA를 실행하지 않는다.
- [report_contract.py](src/ops_agent/report_contract.py)의 클러스터·Namespace·GPU·표본·바이트·호출·시간 한도를 따른다. 응답을 받은 뒤의 크기 검사만으로 프로세스 최대 메모리를 보장하지 않는다.
- 근거에는 시간 집계와 검증 요약을 저장한다. 수집 누락·연결 모호성·잘림은 품질과 보고서에 남긴다. 과거 큰 snapshot을 변환하는 migration은 없다.

### 주제별 AI 운영 해석 / Topic-level AI interpretation

신규 집계 보고서는 계산 후 Ops 전용 `report_interpretation.py`에서 두 주제별로 **눈에 띄는 변화 → 의미와 한계 → 확인할 점**을 작성합니다. 기존의 전체 최대 3개 계산 문장 선택을 주제별 1~3개 근거 선택과 짧은 한국어 해석으로 바꿉니다. 수치·대상은 선택한 근거의 참조를 코드가 치환하며, 계산·PromQL·품질 판정·CSV는 그대로입니다. 정책·전용 할당·효율·회수·장애 원인·복구를 판단하지 않습니다.

시간대 설명에는 이미 저장된 시간당 metric만 사용합니다. 같은 Namespace·모델·GPU 구성의 끊기지 않은 인접 시간대 중 변화 폭이 큰 쌍을 편집 우선순위로 선택합니다. 새 수치나 이상 판정을 계산하지 않으며, 자료 부족·GPU 구성 변경·관측 공백이 있는 쌍은 사용하지 않습니다. 모델은 대상·전후 시간·전후 수치와 해당 시간대에 대조할 작업 기록을 함께 적어야 합니다. 이는 보고 기간 안의 변화이지 전날 같은 시간대와의 비교가 아닙니다. 이전 기간 비교가 불가능한 행의 이전 값·차이는 모델 입력에서도 제외합니다. 근거 ID(`fact_id`)와 수치 ID(`metric_id`)를 구분하고 날짜·값·대상은 저장된 참조만 치환합니다.

성공은 `quality.report.method=llm_interpreted`와 두 주제의 narrative로 저장합니다. 참조·형식 검증에 실패하면 최대 한 번 재요청하고, 그래도 실패하거나 모델이 없으면 기존 계산 요약으로 돌아갑니다. 입력은 주제별 최대 30개 finding, 전체 32KB로 제한하고 초과 시 요약만 제공합니다. 기존 공통 LLM deadline·토큰 예산·취소·원격 상태 계약은 유지합니다. 검증은 수치 참조와 형식을 보호하며 자연어 의미의 정확성을 완전히 증명하지는 않습니다.

웹은 주제별 녹색 **AI 운영 해석** 영역과 접을 수 있는 근거를 표시하고, HTML 내보내기도 같은 저장 문장을 사용합니다. 과거 `llm_prioritized` 보고서는 **AI가 고른 주요 변화**, 실패 시 **계산 결과 요약**으로 구분합니다. 기존 결과·RCA·공통 runtime·DB·Helm 설정은 바꾸지 않습니다. [검증 범위](../agents/QA.md)를 참고하세요.

### GPU 메모리 보강

신규 집계 보고서의 Namespace 주제에 [gpu_memory.py](src/ops_agent/gpu_memory.py)의 보조 관측을 추가합니다. 기존 활동·신원 수집을 마친 뒤 현재 기간의 `DCGM_FI_DEV_FB_USED/FREE`를 클러스터당 한 번 시간 집계로 조회하고, 동일 GPU·시간·신원·표본을 검증해 GPU당 사용/여유 GiB를 저장합니다. 근거는 기존 evidence 저장 경로를 사용하고 AI에는 저장된 수치·시간 참조를 전달합니다. 메모리 결측/중복은 기존 활동 계산을 변경하지 않습니다. 자동·수동 신규 보고서 모두 적용되며 기존 결과·일정·RCA·공통 runtime·DB·Helm 변경은 없습니다. 상세 의미와 한도는 [집계 계약](../docs/specs/ops-agent/aggregate-report-v1.md)을 따릅니다.

메모리 근거를 사용한 설명은 대상·시간·수치를 코드가 확정하고(`observation_source=calculated`), AI는 의미와 확인할 점을 작성합니다. 화면에서도 둘을 구분합니다. 검증을 통과하지 못한 AI 문장은 계산 요약으로 대체하며 기존 활동률·이전 기간 비교·사건 계산은 유지합니다.

### GPU 작업 대기·배치 완료 보조 관측

`workload_queries.py`의 Ops 전용 시간 집계와 `workload_summary.py`의 검증으로 Namespace별 관측 최대 Pending/미배치/Running Pod 및 성공 완료 Job 표본·소요시간을 추가합니다. 일반 컨테이너의 GPU 요청과 Pod UID/Job owner를 연결하며 누락·모호한 이름 재사용은 제외합니다. 근거·CSV·AI 입력을 기존 저장 경로로 연결합니다. 외부 Alloy의 새 전송 목록 적용과 실제 상태 대조는 별도이며, 자료 없음은 0건이 아닙니다. 자세한 범위·제한·적용 옵션은 [집계 계약](../docs/specs/ops-agent/aggregate-report-v1.md#ops-작업-대기배치-완료-보조-관측)에 있습니다.

`ops-interpretation-workload-v2`는 같은 Namespace의 활동·메모리 근거와 작업 근거를 함께 선택합니다. Pending 최대값은 Pod 개수이며 대기 시간이 아닙니다. Job 경과시간은 시작~완료 차이로 대기·준비를 포함할 수 있습니다. 서로 다른 기간의 관측으로 동시 발생이나 대기 원인을 단정하지 않습니다. 해석 검증 실패 시 계산 결과는 유지하고 AI 실패 상태를 표시합니다.

해석 시도별 실패 코드는 `quality.report.failures`의 `attempt`·`reason`과 `Ops interpretation rejected` Worker 로그에 보존합니다. 의미 검증 뒤 JSON 형식 오류가 나더라도 앞선 사유를 지우지 않습니다. 첫 응답이 `llm_invalid_output`이면 기존 최대 두 번의 해석 시도 안에서 JSON 형식 수정을 한 번 요청합니다. HTTP 오류·출력 잘림·예산/마감 소진에는 이 추가 수정 요청을 보내지 않으며, 원격 종료 미확인·취소는 기존 실행 경로로 전파합니다. 로그·진단에는 응답 원문이나 예외 메시지를 넣지 않습니다. 자동·수동 보고서는 같은 함수를 사용하며 과거 발행 결과를 재작성하지 않습니다.

Interpretation failures retain bounded reason codes per attempt. A first malformed JSON response gets one repair within the existing two-interpretation limit; transport, deadline, token and evidence validation protections remain in force. This Ops-only recovery does not change RCA or report calculations.

완료·경과시간 설명의 기존 거절 조건은 그대로 두고, 경과시간의 Job 표기 누락(`batch_job_elapsed_required`), 실행시간과의 혼동(`batch_elapsed_is_not_execution_time`), 전체 완료·처리량·대기 해소 단정(`batch_samples_do_not_prove_throughput_or_queue_resolution`)을 구분합니다. 해당 오류의 보완 요청에는 거절된 fact_id·summary 필드와 구체적인 수정 안내를 전달합니다. 필수 토큰 누락·확인 제안 누락도 fact_id와 누락 항목 또는 후보별 작성 초점을 짚어 보완합니다. 오류가 특정 Namespace 문장을 가리키면 각 선택 문장을 기존 검증으로 점검하고 보완이 필요한 후보의 근거·이전 문장·실패 사유만 전달해 LLM이 `advice` 배열의 `fact_id/summary`를 한 번에 다시 작성합니다. 다른 후보로의 변경·필드 추가는 거절하며, 코드가 이전 응답의 해당 문장들만 교체한 뒤 전체 응답을 동일한 기존 검증으로 다시 확인합니다. 다른 올바른 문장과 사건 해석은 그대로 보존합니다. 나머지 오류는 기존 전체 응답 보완 경로를 사용합니다. 최초 작성과 문장 보완 모두에 수치 의미를 전달합니다. 시간 평균 활동과 최대 대기는 같은 구간의 별도 집계로, 완료 Job 경과시간은 최소~최대 범위로, 대기 변화는 처음→마지막 시간대 최대값 비교로 쓰도록 안내합니다. 종류별 작성 초점은 활동과 대기의 불일치, 상주 메모리 점검, 조건부 실행 시간대 검토 등 서로 다른 점검 이유를 설명하며, 표현만 바꾼 반복 조언은 피하도록 요청합니다. 대표 완료를 포함하되 다른 클러스터에 다른 종류의 근거가 있으면 같은 완료 조언을 복제하는 대신 그 근거를 선택하도록 안내하며, 다른 종류가 없으면 기존 클러스터 포함 조건을 우선합니다. 필수 완료 후보 → 아직 포함하지 않은 클러스터의 다른 종류 → 메모리·실행 시간대 질문 순으로 선택하도록 작성 지시를 정리합니다. 완료 Job별 경과 차이 점검과 Pending Pod의 배치 제약 점검을 구분하고, 한국어 문장·중복된 검토 표현도 반환 전에 점검하도록 요청합니다. 응답 형식 예시에 특정 후보 ID를 미리 넣지 않아 같은 완료 후보를 복제 선택하도록 유도하지 않으며, 실제 후보·클러스터 포함·대표 완료·최대 개수 등의 기존 선택 검증은 유지합니다. 기존 32KB 입력 상한·토큰 예산·최대 두 번의 해석 시도·통과/탈락 조건·계산·후보 선별은 유지합니다. 모델 응답을 코드가 운영 문장으로 다시 쓰지는 않습니다.

Batch explanation diagnostics distinguish a missing Job elapsed-time label, execution-time confusion, and unsupported throughput/queue-resolution claims. The same ordered checks still decide acceptance; reason codes and targeted repair guidance change. A fact-specific Namespace repair sends only the relevant evidence and prior sentence; the model supplies replacements for all individually invalid summaries in one bounded repair. Other model sentences remain unchanged and the full merged response must pass the existing validators. Both drafting and repair include value semantics: separate aggregates within a period are not simultaneous samples, Job elapsed min–max is not an average, and Pending change compares the first and last hourly maxima. The response-shape example contains no preselected candidate IDs; existing coverage, representative-batch and count checks remain unchanged. Candidate-specific guidance separates completed-Job elapsed differences from Pending Pod placement constraints, and asks the model to cover other kinds of evidence before duplicating batch advice across clusters. It also requests Korean wording and a check for repeated phrases; model wording still requires semantic review.

메모리는 단일 GPU 신원·전체 시간대의 표본 수 일치를 검증하므로 짧은 실행·연결 변경 구간이 제외될 수 있습니다.

### Namespace별 조건부 운영 제안

`namespace_advice.py`의 `namespace-pattern-advice-v3`는 저장된 활동·대기·메모리와 성공 완료 Job 표본으로 운영 질문별 후보를 만듭니다. 수집·원래 산식·품질 판정·CSV는 유지하며 자동·수동 신규 집계 보고서는 같은 Worker 경로를 사용합니다. 기존 보고서는 재작성하지 않습니다.

AI 요약 검증은 이미 단위가 든 수치 토큰 뒤에 같은 단위를 반복한 경우만 바로잡고, 완료·대기 변화 요약이 같은 대상·기간의 대기 점검을 포함하면 중복 점검 불릿을 제외합니다. 다른 단위·근거 없는 주장·필수 근거 누락은 계속 거절합니다. 저장된 관측치나 후보 산식은 바꾸지 않습니다.

| 운영 질문 | 후보 기준과 허용 범위 |
|---|---|
| 할당 확대를 검토할 대상인가 | 같은 GPU 구성의 연속 두 시간 이상, 모든 관측 모델의 시간 평균 활동률이 80% 이상이며 같은 시간의 완전한 대기 관측이 양수일 때 검토 후보. 현재 할당·보장량·가용 자원과 스케줄러 사유 확인 후 판단하며 추가 GPU 수량은 제시하지 않음 |
| 활동과 연결하지 못한 대기는 무엇을 확인할까 | 관측된 양수 Pending 구간에서 스케줄러 이벤트·배치 제약 점검. 일부 표본은 표시하고 미수집은 0으로 채우지 않음 |
| 배치 실행을 시험할 시간대가 있는가 | 같은 GPU 구성으로 두 시간 이상 모든 관측 모델의 활동률이 5% 미만이고 알려진 양수 대기가 없는 구간. 대기·예약·사용 가능한 GPU를 확인한 후 검토하며 미관측 대기의 부재를 주장하지 않음 |
| 낮은 활동 중 메모리 점유는 어떤가 | 위 구간에 같은 시간대 장치 메모리 사용 비율 80% 이상이 관측되면 상주 서빙·캐시·장기 실행 확인. 클러스터의 빈 자원이나 Namespace의 독점 사용량으로 해석하지 않음 |
| 대기 변화와 완료가 함께 관측됐는가 | 같은 Namespace의 시간대별 Pending 관측과 해당 후보 구간에 완료된 Job 표본을 연결. 처음/마지막 대기 값은 두 시간대의 관측 최대값이며 마지막 시간대는 완전한 표본이어야 함. Job 경과시간은 저장된 시작~완료 차이이며 대기·준비를 포함할 수 있음 |

80%·5%·80%와 두 시간은 설명 후보를 고르는 명시적 검토 기준이며 운영정책·자원 부족·효율 판정 기준이 아닙니다. 단일 시간의 높은 활동과 대기는 확대 후보가 되지 않습니다. 하루 안의 정적 구성 구간을 사용하며 여러 날짜의 반복 패턴을 주장하지 않습니다. 완료 표본만 있는 경우에는 완료 시각이 모인 한 시간(동률은 최신)을 선택합니다. 대기가 있는 경우에는 첫 완전한 양수 대기 시간대부터 마지막 완전한 대기 집계 시간대에 완료된 Job만 연결하며 다른 구간의 완료와 보고서 전체 평균을 섞지 않습니다. 같은 작업이 계속 기다렸는지, 완료가 대기를 줄였는지, 전체 제출 작업이 완료됐는지는 판단하지 않습니다.

Namespace당 하나로 자르지 않고 서로 다른 질문의 후보를 보존합니다. 클러스터와 분석 종류별 대표를 먼저 확보한 뒤 종류·표본 충족·대기 규모·관측 구간 수·완료 표본으로 최대 12개를 선별합니다. 종류 순서는 할당 검토, 완료·대기 변화, 대기 점검, 상주 메모리, 작업 시간대입니다. 완료·대기 후보는 해당 구간의 대기 표본이 모두 완전하고 처음·마지막 대기 변화가 확인될 때 AI에 전달합니다. 활동률 연결에 빈 시간이 있으면 후보의 활동률은 미확인으로 표시하고 함께 해석하지 않습니다. 그 외 완료 Job과 부분 관측치는 보고서 표·근거에 계속 남습니다. `selection`에 기준 revision·전체 후보 수·전달/제외 수·종류별 제외 수·대표 완료 ID를 저장하고 각 후보의 `selection_basis`에 관측 범위를 남깁니다. 사건 입력은 기존 노드·알림 종류 근거를 작성 당시 발생 중 건수, 사건 건수 순으로 선별하며 사건 계산·RCA는 변경하지 않습니다.

AI는 서로 다른 운영 판단 3~5개를 목표로 하되 근거가 부족하면 개수를 채우지 않고 짧은 `summary` 불릿을 직접 작성합니다. 클러스터별 표현을 보존하고 같은 클러스터의 같은 종류는 대표 하나만 선택합니다. 충분히 연결된 완료·대기 대표 근거가 있으면 포함합니다. 같은 완료 설명이 대기를 다루면 그 Namespace의 같은 구간 대기 점검을 중복 나열하지 않습니다. 대상·시간·수치·조건은 코드가 확인하며 `target/period/activity/pending/memory/completed/elapsed/pending_change` 중 해당 후보에서 제공된 참조만 사용합니다. 정확히 일치하는 근거 값의 직접 표기도 검증할 수 있지만 모델 문장은 다시 쓰지 않습니다. 대기 사유와 작업 목적이 확인되지 않은 상태의 제출 간격 변경 제안, 미확인 자료의 0 처리, 대기 건수와 대기 시간 혼동, 근거 없는 전체 완료·처리량·원인 주장은 거절합니다.

모델에는 수치 참조와 선별 근거만 전달해 원문 관측·공통 조건의 반복을 줄입니다. 기존 32KB 입력 상한·실행 토큰 예산·최대 두 번 요청·실패 시 계산 요약을 유지합니다. 녹색 AI 영역은 실제 모델 요약을 먼저 보여주고 상세 관측·조건·선별 기준은 접힌 근거에 둡니다. HTML도 같은 저장 문장을 사용합니다. 새 후보가 없으면 기존 해석 경로를 유지합니다. 운영정책 연계, 반복 일자 분석과 제안 실행은 범위 밖입니다.

#### 수집 지표에서 운영 판단까지

위 표는 **현재 코드의 후보 조건**입니다. 아래는 그 후보를 운영자가 이해할 판단으로 설명하기 위한 기준입니다. 문장 품질 검토 기준을 제품의 통과/탈락 검사와 혼동하지 않습니다. 이번 문서 보강은 수집·계산·후보 임계값·검증 조건을 바꾸지 않습니다.

| 근거 | 현재 보고서에서 읽는 의미 | 판단에 사용하지 않는 의미 |
|---|---|---|
| GPU 활동률 | 연결 GPU의 유효 시간대별 평균. 후보 구간의 표시는 시간·모델별 평균의 최소~최대 | Namespace 독점 사용률, 실제 할당량, GPU 부족, 순간 최대 성능 |
| 장치 메모리 사용 비율 | 같은 GPU 신원·시간대에서 검증한 사용량 ÷ (사용량 + 여유량). 값이 있는 시간만 연결 | Namespace가 예약한 메모리, 메모리 대역폭 사용률, OOM·성능 병목 |
| Pending·미배치 Pod | GPU를 요청한 Pod 상태의 시간대별 관측 최대 개수. 상태와 배치 여부를 구분 | 대기 시간, 동일 Pod의 연속 대기, GPU 부족이라는 확정 사유 |
| 성공 완료 Job·경과시간 | 후보 구간에 성공 완료가 확인된 표본과 각 Job 시작~완료의 최소~최대. 시작은 후보 구간보다 이를 수 있음 | 순수 GPU 실행시간, 평균 대기시간, 전체 제출 대비 완료율·처리량·성능 개선 |
| 사건·노드·알림 종류 | 저장된 고유 사건의 범위·건수·작성 당시 상태와 공개 조사 참조 | 현재 장애·실제 복구·같은 GPU의 반복 원인. UUID·증상 식별 부족은 그대로 표시 |

Namespace가 같아도 보고서 하루 평균 활동률과 다른 시간대의 대기를 한 상황처럼 묶지 않습니다. `source_hours`의 같은 구간·모델·GPU 신원을 확인하고, 없는 연결은 미확인으로 둡니다. 대기 최대 7개와 평균 활동률 20%를 함께 관측했더라도 “GPU가 남는데 작업을 못 돌렸다”는 결론은 아닙니다. 대기 사유·작업 목적·정책과 연결하지 않은 값은 추가 확인 대상입니다. 표나 원천에 요청량·라벨이 존재해도 현재 `summary_tokens`·후보 근거에 제공되지 않은 실제 할당량·작업 목적은 LLM이 안다고 취급하지 않습니다.

#### 질문별로 어떤 답을 쓰는가

| 기존 후보 | 설명할 운영 판단과 다음 확인 | 멈춰야 할 결론 |
|---|---|---|
| `capacity_review` | 높은 활동과 양수 대기가 이어진 대상·시간을 짚고, 스케줄러 사유·현재 할당·가용 자원을 대조한 뒤 확대 검토 | 대기만 보고 GPU 증설, 추가 GPU 수량 산정 |
| `queue_review` | 활동 근거만으로 대기를 설명할 수 없다는 점을 짚고, 해당 시간대 대기 Pod의 스케줄러 이벤트·배치 제약 확인 | 낮은 활동이므로 대기가 없어야 함, 확인하지 않은 anti-affinity·쿼터·자원 부족 원인 단정 |
| `resident_memory` | 연산 활동은 낮지만 장치 메모리가 점유된 구간을 짚고, 상주 서비스·캐시·장기 실행 목적 확인 | 빈 GPU·회수 대상·메모리 부족으로 단정 |
| `schedule_candidate` | 관측 날짜의 낮은 활동 구간을 시범 실행 검토 시간대로 제시하고, 예약·대기·가용 GPU 확인을 실행 전 조건으로 붙임 | 매일 그 시간에 작업이 없다고 일반화, 확인 없이 작업 이동 지시 |
| `batch_progress` | 처음/마지막 시간대 최대 대기와 완료 표본·Job 경과시간 범위를 구분하고, 경과 차이를 스케줄러 이력·작업 유형과 대조 | 완료 때문에 대기가 줄었다는 인과, 서로 다른 작업의 성능 비교, 경과시간을 대기시간으로 치환 |

예를 들어 시간대 후보의 **문서용 문장 예시**는 “해당 Namespace는 이 구간의 활동률이 낮았습니다. 예약·대기와 사용 가능한 GPU를 확인한 뒤 이 시간대에 배치 작업을 실행하는 것을 검토하세요.”입니다. 실제 보고서는 해당 후보의 대상·기간·필수 수치를 보존한 실제 LLM 문장을 사용합니다. 이 예시를 AI 실행 결과로 저장하거나 표시하지 않습니다.

#### 선별과 문장 품질은 별도로 확인

1. **근거 연결:** `candidates()`·`windows()`가 같은 구간의 유효 관측을 구성합니다. 전송된 지표가 있다는 사실과 제안에 쓸 만큼 연결됐다는 판단은 다릅니다.
2. **후보 전달:** `select_candidates()`가 기존 종류 순서와 클러스터·종류 대표를 보존해 최대 12개를 전달합니다. 완료·대기 연결이 부족한 표본은 표에 남기되 해당 AI 후보에서 제외합니다. 노드·Namespace 수만큼 LLM 호출을 늘리지 않습니다.
3. **첫 화면 선택:** LLM은 최대 5개 안에서 서로 다른 운영 질문을 선택합니다. 기존 검증의 클러스터 포함·대표 완료 필수 조건은 유지합니다. 다른 클러스터에 다른 질문이 있으면 같은 완료 설명을 복제하기보다 그 질문을 선택하도록 작성 지시하지만, 이는 현재 중복을 완전히 차단하는 코드 규칙이 아닙니다.
4. **짧은 판단:** 한 불릿은 대상·시간의 핵심 관측과 그 때문에 확인할 대상 하나를 두 문장 이내로 연결합니다. “확인하도록 검토하세요” 대신 확인할 일은 “확인하세요”, 조건부 자원 변경·시간대 이동은 “확인한 뒤 검토하세요”로 구분하는 것을 문장 품질 목표로 둡니다. 필수 수치를 빼서 짧게 만들거나 근거 없는 이유를 덧붙이지 않습니다.
5. **의미 검수:** 근거·참조 검사 통과와 별도로 최대값/범위 표시, 완료와 대기의 다른 질문, 조언 반복, 쉬운 표현을 원문과 대조합니다. 실패한 항목은 [Agent QA](../agents/QA.md)에 남기며 통과율만으로 유용성을 주장하지 않습니다. 이 의미 검수 항목은 기존 런타임 검증을 추가·완화한 것이 아닙니다.

#### 현재 기준에서 추가로 발전시킬 항목

다음은 **미구현**이며, 위 다섯 후보의 현재 지원 범위로 표시하지 않습니다.

| 보강할 질문 | 지금의 근거로 가능한 범위와 추가 작업 |
|---|---|
| 활동은 높은데 메모리 점유는 낮은가 | 시간·신원·모델이 연결된 활동/메모리를 바탕으로 연산 활동과 장치 메모리 점유의 대비를 설명할 수 있음. 현재 별도 후보는 없음. 낮은 메모리 기준과 유효 표본 조건·선별 순서를 먼저 정의하고 경계/결측 검사를 추가해야 함. 메모리 여유만으로 GPU 공유·축소 또는 연산 병목을 권하지 않음 |
| 대기 중 GPU 활동이 낮은 시간과 높은 시간을 구분할 수 있는가 | 현재 높은 활동+대기 조건은 확대 검토, 그 외 양수 대기는 배치 제약 점검으로 분리. 더 구체적인 원인 분기는 스케줄러 이벤트·배치 제약의 저장·연결이 필요. 테스트용 의도된 대기를 자원 부족으로 바꾸지 않음 |
| 같은 종류의 작업 경과시간이 달라졌는가 | 현재는 완료 표본의 경과 범위만 설명. 작업 유형 라벨·요청 GPU/모델·입력 조건과 비교 기간을 연결해야 동등한 작업끼리 비교 가능. 현재 완료 건수와 경과 범위만으로 처리량·성능 순위를 만들지 않음 |
| 반복해서 비는 시간대로 작업을 옮길 수 있는가 | 현재는 관측한 날짜의 시간대 후보만 제시. 여러 날짜에서 같은 신원/구성·표본 조건으로 반복성을 검증하고 예약·대기·작업 마감 조건을 연결해야 반복 일정 추천으로 확장 가능 |

먼저 기존 다섯 질문이 서로 다른 판단과 명확한 다음 확인을 짧게 내놓는지 실자료로 검수합니다. 새 후보는 그다음에 같은 근거 연결·선별·문장 검증 경로에 추가하며, 새 대주제나 Namespace별 무제한 설명을 만들지 않습니다. 임계값 변경은 글쓰기 수정과 분리해 비교하고 `CRITERIA` revision·QA에 남겨야 합니다.

Interpretation criteria are owned by `namespace_advice.py` and this section. Existing gates, metrics, candidate thresholds and RCA stay unchanged. Proposed extensions are explicitly unimplemented; evidence acceptance and useful operational writing remain separate checks.

## 기존 O계열 보고서

이전 요청 방식과 기존 일정은 [O계열 명세](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md)를 사용한다. `criteria 1.3`의 기본 주제는 O08/O01/O05/O11이며 현재 신규 화면의 기본 집계 계약과 구분한다.

- 공통 D binding과 query+CPC+기간 계획으로 조회한다. [collection.py](src/ops_agent/collection.py)가 의존성·예약 예산·병렬 수집·취소 회수를 처리한다. 실행별 관측 캐시는 같은 조회·기간의 근거를 재사용한다.
- O01 장비/Node 관측, O08 사용 패턴, O05 DB 사건·공개 RCA·조치 기록, O11 자료 신뢰도에 [operator_insights.py](src/ops_agent/operator_insights.py)의 확인 항목을 연결한다. 누적 상태와 현재 장애, 알람 해제와 복구 완료를 구분한다.
- 통합 binding과 criteria 1.3에서 O01은 불필요한 D06을, O05는 D10/D22를 조회하지 않는다. 계산에 쓰지 않는 보고서 D09/D13도 생략하며 `quality.omitted_queries`에 이유를 남긴다. 다른 계약의 조회를 임의로 줄이지 않는다.
- D06 범위 축소는 완전한 D02 신원·기간과 허용된 주제 조합에서만 적용한다. 신원 누락·공백·빈 후보·필터 한도 초과 시 넓은 기존 범위로 복귀한다. 최종 UID·Node·시간 연결 검사는 유지한다.
- O01 추가 관측은 대상별 고유 지표 ID를 사용한다. criteria 1.3은 D20 원본 구간을 결과 본문에 중복 저장하지 않고 계산 결과와 evidence refs를 유지한다. 구 결과 형식은 조회 호환용으로 유지한다.
- [report.py](src/ops_agent/report.py)는 코드가 만든 문장을 문장 ID 선택 LLM으로 편집한다. 새 수치·원인·조치를 생성하지 않으며 모델을 사용할 수 없으면 기본 보고서를 남긴다.

## 보고서 삭제와 파일 정리

사용자가 종료한 보고서를 삭제하면 JC가 DB 결과·근거를 삭제하고 `report_deletions`를 기록한다. [cleanup.py](src/ops_agent/cleanup.py)는 Worker 시작 시와 이후 30초마다 대상 1건을 처리한다. DB 행 잠금·`SKIP LOCKED`로 여러 Pod가 같은 대상을 동시에 맡지 않는다.

정규 UUID의 `ARTIFACT_DIR/<job_id>`만 처리하고 심볼릭 링크를 따라가지 않는다. 파일 삭제 후 0바이트 일반 파일로 표시해 늦게 끝난 저장 작업이 디렉터리를 다시 만들지 못하게 한다. `pending`/`failed`는 미완료, `complete`는 삭제 표시까지 생성한 상태다. 실패 시 재시도하며 DB에서 삭제한 본문이 복구되지는 않는다. migration 008 미적용 중에는 경고를 남기고 분석 루프를 유지한다. RCA에는 이 정리 루프가 없다.

## 실행·검증

[공통 실행 안내](../agents/README.md) · [Agent QA](../agents/QA.md) · [삭제 회귀](../agents/tests/test_report_cleanup.py) · [격리 DB 삭제 검증](../agents/tests/test_report_cleanup_e2e.py).

실환경 지연·최대 메모리·운영 PVC의 삭제·복구와 원인/업무 영향 해석은 각 검증 근거의 범위를 따른다. 저장소 원본이나 fixture 테스트만으로 운영 배포와 성능 개선을 확정하지 않는다.

관측 GPU 활동률이 0%여도 실제 GPU 미사용이나 연산 부재를 뜻하지 않습니다. 짧은 연산과 측정 주기가 맞물리면 표본에 잡히지 않을 수 있습니다. Namespace 운영 문장은 저장된 활동률을 관측값으로 표현하며, 미사용·활동 부재 단정은 재작성 대상으로 검증합니다. 표본 수 충족은 연산 전체를 빠짐없이 측정했다는 보장이 아닙니다. 기존 수치·기간·품질 판정 계산은 바꾸지 않습니다.
