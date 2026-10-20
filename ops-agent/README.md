# Ops Report Agent

Job Controller(JC)에서 보고서 작업을 인수해 관측·사건을 집계하고 결과와 HTML/CSV를 저장합니다. 자동·수동 신규 보고서는 같은 분석 경로를 사용하며, 기존 O계열 요청은 [workflow.py](src/ops_agent/workflow.py)에서 별도로 처리합니다. 기존 보고서·일정을 자동 변환하거나 재작성하지 않습니다.

## 신규 기본 보고서

`report-aggregate-v1`은 일일·주간 `namespace_usage`와 `incident_summary`, 직전 동일 기간 비교를 제공합니다. 쿼리·산식·표본/신원 조건·한도는 [Ops 상세 명세](../docs/specs/ops-agent/aggregate-report-v1.md)가 관리합니다.

| 단계 | 구현과 역할 |
|---|---|
| 수집 | [report_queries.py](src/ops_agent/report_queries.py): 공통 D registry와 별개인 Ops PromQL로 활동·Pod/GPU 신원을 조회합니다. [identity_transitions.py](src/ops_agent/identity_transitions.py)는 모호한 연결 변경 시간대만 추가 검증합니다. |
| 계산·근거 | [namespace_usage.py](src/ops_agent/namespace_usage.py)의 유효 표본 합계/개수로 평균을 계산합니다. [report_store.py](src/ops_agent/report_store.py)는 같은 읽기 전용 DB snapshot에서 사건과 공개 RCA ID/hash를 읽으며 새 RCA를 실행하지 않습니다. |
| 보조 관측 | 기본 활동/신원 검증 후 [gpu_memory.py](src/ops_agent/gpu_memory.py)의 GPU당 메모리와 [workload_summary.py](src/ops_agent/workload_summary.py)의 GPU 요청 Pod·완료 Job 근거를 연결합니다. |
| AI 해석 | [report_interpretation.py](src/ops_agent/report_interpretation.py)가 계산된 근거로 두 주제의 설명을 요청하고 검증합니다. 모델이 수치·품질을 계산하지 않습니다. |
| 공개·표시 | 기존 Worker/JC 공개 경로와 웹·HTML을 사용합니다. AI 문장과 계산 요약, 펼쳐 보는 상세 근거를 구분합니다. |

수집 누락·연결 모호성·잘림은 보고서 품질과 근거에 남깁니다. 응답 크기 한도는 프로세스 최대 메모리 보장이 아니며, 과거 큰 snapshot을 변환하는 migration은 없습니다.

### 주제별 AI 운영 해석 / Topic-level AI interpretation

`ops-interpretation-workload-v2`의 Namespace 후보는 아래 운영 제안 경로를 사용합니다. 후보가 없으면 기존 주제별 관측·의미·확인 경로를 유지하며, 시간 변화 설명은 같은 Namespace·모델·GPU 구성의 인접 유효 시간만 연결합니다. 사건 해석은 노드·알림 종류와 저장된 조사 기록을 대상으로 하며 원인·반복 장애·복구를 확정하지 않습니다.

성공은 `narrative_status=complete`, `quality.report.method=llm_interpreted`로 식별합니다. 입력 상한은 32KB이며 기존 deadline·토큰 예산·최대 두 번의 해석 시도를 유지합니다. 잘못된 JSON 또는 지원되는 문장 오류는 한 번 보완하고 전체 응답을 재검증합니다. 구조·참조가 안전한 응답은 주제 순서에 관계없이 잘못된 Namespace 문장과 사건 주제를 함께 찾아 한 번에 보완합니다. 정상 주제·문장은 원문 그대로 보존하고 합친 전체 응답을 기존 검사로 재검증합니다. 항목/주제·참조를 안전하게 고정할 수 없는 구조·선별 오류는 기존 전체 보완을 사용합니다. 부분 보완 요청은 기존 16KB 상한 안에서만 전송하며 넘으면 계산 요약을 유지합니다. 전송 오류·출력 잘림·예산/마감 소진은 추가 형식 보완을 유발하지 않습니다. 실패 시 계산 결과·요약을 유지하며, 시도별 `quality.report.failures`의 `attempt/reason`과 `Ops interpretation rejected` 로그로 구분합니다. 원문·민감 예외는 로그에 남기지 않고 원격 종료 미확인·취소는 기존 Worker로 전파합니다.

웹과 HTML은 같은 저장 문장을 사용합니다. 과거 `llm_prioritized`는 AI가 고른 계산 문장으로 구분합니다. 참조·형식 검사 통과가 자연어 의미와 운영 유용성을 보장하지는 않습니다.

### GPU 메모리 보강

`DCGM_FI_DEV_FB_USED/FREE`를 현재 기간만 클러스터당 한 번 시간 집계해 GPU당 사용/여유 GiB와 비율을 저장합니다. 같은 GPU·시간·신원·표본 조건을 충족한 장치 관측이며 Namespace 독점 사용량이 아닙니다. 짧은 실행·연결 변경·결측·중복은 메모리 근거를 제한할 수 있으나 기존 활동률 계산은 바꾸지 않습니다. [메모리 수집·제외 조건](../docs/specs/ops-agent/aggregate-report-v1.md#namespace-gpu-메모리-보조-관측--optional-gpu-memory)을 따릅니다.

### GPU 작업 대기·배치 완료 보조 관측

[workload_queries.py](src/ops_agent/workload_queries.py)는 일반 컨테이너의 GPU 요청과 Pod UID/Job owner를 연결해 시간별 최대 Pending·미배치·Running과 성공 완료 Job 표본을 수집합니다. 누락·모호한 이름 재사용은 제외하며, 외부 Alloy 전송 설정과 실제 저장 표본 확인은 별도입니다. [조회·근거·CSV·시간 의미](../docs/specs/ops-agent/aggregate-report-v1.md#ops-작업-대기배치-완료-보조-관측)를 따릅니다.

### Namespace별 조건부 운영 제안

[namespace_advice.py](src/ops_agent/namespace_advice.py)의 `namespace-pattern-advice-v3`는 저장된 활동·메모리·대기·완료 근거로 후보를 만듭니다. 기존 최대 12개 중간 후보에서 필수 완료·클러스터를 확보하고 서로 다른 질문을 보태 최대 5개 작성 후보를 전달합니다. 작성 후보가 최대 5개로 좁혀지면 응답 구조에 각 ID를 나열해 모두 순서대로 작성하도록 요청합니다. 5개 초과 클러스터의 기존 전달 경로에서는 LLM이 최종 항목을 선택합니다. 기존 종류 순위·대표 완료 필수·클러스터 포함·같은 클러스터/종류 중복 제한을 유지합니다. 필수 완료 구간에 포함되는 대기와 대안이 있는 비필수 완료의 전달을 줄이지만, 첫 화면의 모든 항목이 새로운 운영 선택을 제공한다고 보장하지 않습니다.

후보별 작성 초점은 **어떤 선택을 왜 검토할지 → 대상·기간·필수 관측 근거** 순으로 안내합니다. `summary_start`는 참조 안내이며 고정 첫 문장이 아닙니다. 첫 문장은 짧은 선택·이유, 둘째 문장은 필수 근거로 요청합니다. 후반 대기 관측이 양수인 완료 후보는 다음 배치의 실행 순서 점검과 작업 유형·스케줄러 대조를 연결합니다. 모델이 문장을 직접 작성하고 코드는 참조를 검증·치환하며, 문장을 사후에 운영 제안으로 다시 쓰지 않습니다. 보완에서도 선택·이유·필수 참조를 보존합니다. 전체 작성·간결성은 프롬프트 지시이며 기존 검사에 새 탈락 조건을 더하지 않습니다. 후보 종류가 허용하는 범위와 기존 검증 조건은 유지하며, 선별·문장 유용성은 [상세 기준과 사례](../docs/specs/ops-agent/aggregate-report-v1.md#운영-해석-기준과-후속-설계), 실행 증거는 [Agent QA](../agents/QA.md)에서 구분합니다.

관측 활동률 0%는 미사용의 증거가 아닙니다. Pending은 대기 시간이 아니고 Job 경과는 대기·준비를 포함할 수 있습니다. GPU 연결은 실제 할당·보장량이 아니며, 미배치만으로 GPU 부족을 확정하지 않습니다. 원래 계산·품질·CSV·RCA를 유지합니다.

#### 운영 해석 개선 방향 (후속 개발 목표)

고정 종류 순서 제거·근거 강도에 따른 질문 간 비교·질문별 보류 사유 표시·정책/실제 할당/작업 목적/스케줄러 원인 연결은 미구현입니다. 현재 전달 후보·필수 포함 조건과 별개이며, [구현 범위와 결정 대기 항목](../docs/specs/ops-agent/aggregate-report-v1.md#구현-범위와-결정-대기-항목)을 따릅니다.

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
