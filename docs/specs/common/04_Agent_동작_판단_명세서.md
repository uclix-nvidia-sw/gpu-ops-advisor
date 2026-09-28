# 04. Agent 공통 동작·판단 명세서

문서 버전 1.3 · 현행 criteria_version=1.1 · 보고서 집계 변경 목표 criteria_version=1.2 · result_schema_version=1.1

## 1. 공통 역할

RCA·보고서 Agent는 JC에서 배분받은 잡만 실행한다. 각 Worker 내부에 독립 NAT 워크플로를 두고 RCA는 Runbook 기반 조사, 보고서는 DB·기간 관측의 집계·설명을 수행한다. 공통 코드는 MCP 연결 처리·정규화·계산·품질 등 실제 중복 함수만 재사용하며 중앙 업무 서비스로 배포하지 않는다. LLM은 근거 해석·설명·등록 조사 선택을 담당한다. 장비 변경 도구나 일반 대화 기능은 없다.

## 2. 실행과 상태

공통 실행부는 scope·대상·기간·입력 snapshot 검증 → 버전/마감 고정 → 해당 NAT 워크플로 실행 → 결과 검증 → candidate 저장 → JC complete 순서다. 워크플로의 조사·계산 순서는 11/12를 따른다. NAT가 업무 큐·Worker lease·최종 공개를 소유하지 않는다. 인증 검사는 범위 밖이지만 입력·조회 범위·도구 허용 목록·예산·결과 검증은 유지한다.

job.status는 10, tool_status=ok/partial/empty/unavailable/parse_error는 03, 주제 상태는 ready/partial/blocked/not_applicable, 설명은 complete/failed/omitted로 구분한다. 결과 미발행이면 result_status/narrative_status는 null이다.

결과 전체 result_status는 적용 항목에서 모두 ready면 ready, 하나라도 유효 ready/partial이 있고 전부 ready가 아니면 partial, 모두 blocked면 blocked, 적용 항목이 없으면 not_applicable이다. RCA는 purpose별 assessments, 보고서는 topics를 기준으로 계산한다. 실행 성공이 데이터 충분함·원인 확정·사건 종결을 뜻하지 않는다.

### 2.1 NAT 구성과 업무 함수

각 Worker는 NAT Python 실행 기능을 내장하고 자기 워크플로만 실행한다. 두 워크플로의 설정·프롬프트·등록 함수·모델 참조를 분리한다. MCP function group은 필요한 원격 도구만 연결하며 업무 함수가 입력 범위와 응답을 검사한 뒤 호출한다. 설정은 구성 요소와 버전 연결용이며 범용 조사 YAML 해석 엔진을 추가하지 않는다.

| 함수 역할 | RCA | 보고서 | 실행 주체 |
|---|---|---|---|
| Runbook 검색·적용 검사 | 호환 발행본 검색·증거/조건 검사, 없으면 일반 조사 | 기본 흐름에서 생략 | DB 조회·결정적 검색·코드 평가; LLM 미사용 |
| Incident·공개 결과 읽기 | 고정된 사고 증거 | 기간 사건·공개 RCA 결과 | 정해진 DB 함수 |
| Grafana MCP 관측 조회 | 부족한 사고 증거와 후속 조사 | 주제별 기간 지표·관련 로그 | 범위를 제한한 조회 함수 |
| 계산·품질·규칙 | 조사 수치·조건 확인 | 주제별 지표·통계 산출 | Python 코드 |
| 분석·설명 | 추가 수집 후 원인 후보·지지/반박·권고·재조사 제안 | 기간 현황·변화·한계 | LLM, 수치·증거 참조. RCA의 기존 증거 충분 경로는 코드로 결과 작성 |
| 검증·저장·완료 | 자기 후보·근거 | 자기 후보·근거·파일 | Worker 코드, LLM 선택 도구 아님 |

RCA의 추가 조사 선택에는 도구 호출을 지원하는 모델과 NAT Tool Calling 구성을 검증해 사용한다. 보고서는 등록된 수집·계산 순서를 실행하며 LLM에 집계 산식을 생성시키지 않는다. NAT 호출 중에도 비동기 heartbeat가 계속 동작해야 하며 숨은 병렬 추론·중첩 재시도로 14의 한도를 초과하지 않는다.

## 3. RCA

[11 RCA](../rca-agent/11_RCA_Agent_모듈_설계서.md)의 입력·R01~R09 계약을 따른다. incident_id는 필수다. 변경 목표는 Incident의 에피소드별 최초 알람 전달 후 **Agent가 파싱·목적 선택·Runbook 적용/로그·지표 일반 조사를 결정**하는 구조다. Runbook과 로그 조회는 같은 workflow에서 결합할 수 있다. Incident가 목적을 정하는 기존 1.3과 목적 없는 신규 1.4 입력은 14의 이행 계약으로 구분하며 현재 구현 완료를 뜻하지 않는다.

2026-09-28에 보완한 workflow는 **Runbook DB 조회·코드 검사 → 기존 증거 충분 시 MCP·LLM 없이 결과 작성 / 부족 시 승인 계획·병렬 MCP 수집 → 코드 충분성 판정·최대 1회 재조사 → 도구 없는 Synthesis → 코드 검증·공통 저장·JC 공개**다. 전용 Runbook이 없으면 승인된 일반 Runbook으로 대체하고 그것도 없으면 조사하지 않는다. Runbook 검색 일치나 MCP 조회 성공만으로 분석 완료를 판정하지 않는다. 유효 증거가 전혀 없으면 LLM 추론을 생략하고 미확정 종료한다. 모델 미구성·오류는 유효 사실을 보존하면서 분석 미완료를 명시하고 14의 실행 실패·격리 계약을 유지한다. 상세 충분 기준·LLM 입출력·재조사 조건과 입력 1.3 구현/1.4 후속 단계 구분은 11 §2를 단일 기준으로 사용한다. Report Agent의 순차 계산·설명 흐름은 변경하지 않는다.

## 4. 보고서

[12 보고서](../ops-agent/12_보고서_Agent_모듈_설계서.md)의 O01~O11을 따른다. 즉시·정기 보고서는 같은 계산과 결과 형식을 사용한다.

## 5. 계산 기준 v1.0

절의 산식은 v1.0에서 유지한다. 추가한 후보 적격성·구간 처리까지 포함한 실행 정책 버전은 v1.1이다.

### 5.1 구간·중복·분모

전용 GPU의 같은 할당 대상·시간에 여러 컨테이너/생산자 관측이 있어도 유효 구간 합집합을 한 번 센다. 동일 물리 GPU를 여러 Namespace가 공유하면 물리 합계는 한 번, 공유 관계 수는 따로 표시한다. MIG는 구성·프로파일별 instance-hours이며 물리 GPU-hours와 합산하지 않는다.

필수 입력들의 **동시 유효 구간 교집합**을 공동 관측 구간으로 사용한다. 개별 커버리지 평균·최솟값으로 대체하지 않는다. 분모는 주장별 기대 GPU·시간, 유효 할당 대상·시간, 기대 Node·시간으로 명시한다. 기대 대상/할당 이력 자체가 없으면 분모와 전체 커버리지는 null이다.

0은 관측된 유효 0이다. 수집 실패·미지원·센티널·오래된 값은 null과 이유로 처리한다. counter 리셋·기기 교체·소스 변경 경계는 각각 검증한 구간만 계산한다.

할당 이력의 기준은 Mimir에 보존된 원본 표본 시각·관계·수집 완전성으로 복원한 구간이다. Agent는 Grafana MCP 응답을 정규화해 같은 복원 함수를 사용한다. UI를 열었는지와 관계없이 보존 기간 안의 같은 입력을 사용한다. 시각·완전성·해상도 또는 보존이 부족하면 해당 기간 계산만 보류한다. 복원 방법과 스냅샷 저장은 03의 이력 생성 계약을 따른다.

계산용 query revision은 원본 관측 시각·원본 주기·값 유지·구간 경계·chunk 겹침 제거·최대 유효시간을 고정한다. 범위 조회의 평가 시각이나 차트 점 수를 원본 샘플 수로 사용하지 않는다. 저장소가 지원하면 원본 range-vector 표본을 제한된 chunk로 조회해 사용하며, 원본성이 확인되지 않는 다운샘플 자료로 급증·시간·P95를 확정하지 않는다. UI chart_step은 표시 전용이고 이미 저장된 계산 결과를 바꾸지 않는다.

### 5.1.1 현재 구현의 GPU–Pod 연결 관측

O02/O08은 D08 할당 계약과 별도로 D01의 GPU 작업 라벨과 D06의 같은 시점 Pod UID를 사용한다. 이름 기반 조인 키는 `cluster_id+namespace+pod+node`이며, 하나의 UID만 유효한 구간을 채택한다. Pod 이름 재사용으로 UID가 겹치는 구간이나 다른 클러스터의 관계는 연결하지 않는다. 원본에 직접 포함된 pod_uid/uid가 있으면 해당 신원을 사용한다.

DCGM 활동값 0도 GPU–Pod 연결의 관측 근거가 될 수 있다. 반면 정규화된 D08 allocation-info의 0은 활성 할당 근거에서 제외한다. 이 둘을 같은 의미로 처리하지 않는다.

관측 연결은 mode=unknown, episode 없음으로 처리한다. `mapped_gpu_hours`는 cluster_id+GPU UUID별 유효 연결 구간 합집합 초를 3,600으로 나눈 값이다. O08의 Namespace별 값은 각 Namespace 안에서 같은 계산을 하므로 공유 GPU가 여러 Namespace에 나타나면 Namespace 합계가 전체 GPU 관측 시간을 넘을 수 있다.

관측 연결만으로 독점·MIG 할당량, 실사용률, 과금량이나 60분 저활동 후보를 확정하지 않는다. 현재 구현은 독점 할당 근거가 없으면 `current_allocated_gpu`, `allocated_gpu_hours`, O08의 독점 할당 그룹 값을 null로 유지한다. 가능한 관측 지표는 보존하고 해당 주제에 부족 사유를 남긴다. 필드 원본은 [03 §5.1](03_데이터_설계서.md), 구현은 [정규화](../../../shared/python/src/agent_common/normalize.py)와 [보고서 계산](../../../ops-agent/src/ops_agent/workflow.py)이다.

### 5.2 산식

| 지표 | 산식·단위 | 제한 |
|---|---|---|
| 현재 전용 할당 | 기준 시각에 유효한 전용 고유 GPU 수 | 불완전 매핑이면 확인된 수량·범위만 |
| 할당 GPU-hours | Σ(전용 GPU별 유효 할당 구간 합집합 초)/3,600 | 활동값 없어도 계산 가능, 과금 원장으로 보장하지 않음 |
| 저활동 GPU-hours | Σ(할당∩활동 유효∩util<5% 구간의 GPU·초)/3,600 | 선정된 시간창 전체로 대체하지 않음 |
| 평균 활동률 | Σ(util%×유효 GPU·초)/Σ(유효 GPU·초) | 동일 의미·모델/공유 방식, 분모 0이면 null |
| 시간 가중 P95 | 값 오름차순 누적 유효시간이 전체의 95% 이상이 되는 최소 값 | 시간 분포/장치 간 분포를 구분, 샘플 개수 동일 가중 금지 |
| 미배치 요청 | 종료/삭제 아닌 unbound Pod의 검증된 유효 요청 합 | 실제 resource 단위, init/sidecar/overhead 규칙은 배포 버전별 등록 |
| 관측 미배치 요청시간 | Σ(유효 요청량×확인된 미배치 구간 시간) | 처음 관측 전 대기는 미확인. GPU 부족 시간으로 치환 금지 |
| 미할당 GPU-hours | 인벤토리와 완전한 할당 조회에서 부재 확인된 GPU·시간 | mapping 실패/Pod 종료는 충분조건 아님 |
| 사건 발생률 | 중복 제거 사건 수/유효 사건 관측 GPU-hours×1,000 | 총 건수·모델·기간도 함께 표시 |
| GPU 에너지 | Σ(W×유효 초)/3,600,000 kWh | v1 전력 적분은 유효 유지 구간의 좌측 값. 공백·리셋 제외 |

공통 v1의 전력 적분을 구현하기 위해 좌측 유지값 방식을 채택한다. 원본 최대 유효시간을 초과해 연장하지 않는다. 검증된 누적 에너지 계수를 쓰면 구간 증가량·단위·리셋 규칙을 별도 계산 revision에 명시하고 전력 적분과 중복 합산하지 않는다.

### 5.3 품질·저활동 정책

| 항목 | v1 값 |
|---|---|
| 일반 기간 비교·순위 | 공동 커버리지 95% 이상. 핵심 사건/시간대가 빠지면 충족해도 보류 |
| 저활동 대상 | 확인된 전용 GPU 할당. 공유 장치 활동은 별도 보기 |
| 시간창 | 60분 |
| 저활동 임계값 | 정규화 GPU utilization 5% 미만 |
| 후보 조건 | 공동 커버리지 ≥95%, 유효 할당·활동 시간 중 저활동 비율 ≥90% |
| 보조 근거 | VRAM·검증된 SM·업무 유형. SM 부재만으로 일반 활동 분석 차단 안 함 |
| 예외 확인 | 초기화·체크포인트·추론 대기·예약 목적 등. 목적 불명은 일반 검토 후보 |

검증된 5% 이상 활동이 있고 저활동 후보 조건은 충족하지 않으면 active_observed다. 후보가 되면서 일부 활동도 있으면 low_activity_candidate와 활동 구간을 같이 표시한다. 품질 미달은 insufficient_data다. 저활동 후보는 낭비·회수 가능·성능 비효율 확정이 아니다.

**장시간 후보 적격성 v1.1:** 후보 단위는 `cluster_id+gpu_uuid+pod_uid+allocation_episode_key`의 전용 할당 관계다. 같은 Pod의 각 GPU는 개별 판정하며 다른 Pod A→B의 시간을 합쳐 한 후보를 만들지 않는다. episode_key는 검증된 신원·연속 관측·할당 방식과 관계 변경 경계로 정하고, 실제 할당 이벤트가 없으면 ‘관측된 episode’라고 표시한다.

검증된 관측 episode의 시작을 기준으로 겹치지 않는 60분 창을 만든다. 실제 시작이 불명확하면 최초 유효 관측을 기준으로 한 창임을 남긴다. episode가 끝나거나 분석 구간 경계로 잘린 60분 미만 구간은 관측 저활동 시간만 제공하며 장시간 후보 판정은 `insufficient_data`, 이유 `short_allocation_window`로 보류한다. 새로운 최소 시간 숫자를 더하지 않고 기존 60분 창 전체를 후보의 최소 범위로 적용한다.

60분 창 내부의 관측 공백은 공동 유효시간에서 빠지며 분모 60분에는 남는다. 따라서 58분 유효·54분 저활동의 기존 예는 그대로 후보가 된다. 5분만 할당·관측한 경우 할당 구간의 관측률이 100%일 수 있어도 장시간 후보는 아니다. 30분 A→30분 B는 각각 관측 저활동 시간만 보고한다. 유효 활동이 있는 짧은 구간의 실제 활동 사실은 별도로 제공한다.

### 5.4 고정 계산 예

아래는 시험 데이터이며 실제 CPC 측정 결과가 아니다.

| 입력 | 기대 결과 |
|---|---|
| 전용 GPU 2개, 각 8시간 유효 할당·각 5시간 저활동 | 할당 16 GPU-hours, 저활동 10 GPU-hours |
| 60분 중 공동 관측 58분, 저활동 54분 | 커버리지 96.6667%, 저활동 비율 93.1034%, 후보=true, 저활동 0.9 GPU-hours |
| 같은 정의의 G1 4건/100 GPU-hours, G2 5건/500 | 발생률 각각 40·10건/1,000 GPU-hours, 총 건수 4·5 |
| GPU 4개×10시간, 전 250W/후 200W, 전 구간 유효 | 10kWh→8kWh, 관측 감소 2kWh. 조치 인과는 별도 |
| Pending 6개, 그중 4개 bound, 2개 unbound·각 유효 GPU 요청 1 | 미배치 요청 2단위. GPU 부족량은 scheduler 근거 없으므로 null |
| 공유 G1에 A·B, G1 활동 80% | 물리 GPU 1, 공유 관계 2. A/B 실사용률 각각 null |
| 60분 중 한 Pod가 5분만 전용 할당, 그 5분은 모두 저활동 | 관측 저활동 1/12 GPU-hours. 장시간 후보 보류, short_allocation_window |
| 전용 G1이 같은 60분에 A 30분→B 30분, 각각 모두 저활동 | A/B 각각 0.5 관측 저활동 GPU-hours. 둘을 합친 장시간 후보 금지 |

### 5.5 보고서 그룹과 사건 통계 — 추가 개발 목표 1.2

이번 그룹·사건 정의 변경은 보고서 `versions.criteria=1.2`의 새 실행 프로필로 구분한다. 기존 1.1 결과·진행 중 job은 재해석하지 않고, 결과 스키마 1.1과 보고서 접수 계약 1.3은 유지한다. 숫자가 같아도 서로 다른 산식 버전의 발생률을 직접 비교하지 않는다.

`group_by`는 아래 지원 축의 조합이다. 요청 축 전체를 적용하고 cluster_id는 항상 내부 신원에 포함한다. 그룹은 표시 이름이 아닌 확인된 UID·장비 신원과 해당 시각 매핑을 사용한다. 각 metric.target과 topic.quality에 요청 축·적용 축·집계 단위를 기록한다. 유효 enum이지만 미지원 조합이면 해당 주제는 blocked, `missing_inputs=unsupported_group_by`이며 다른 주제는 계속한다. 임의 축 삭제나 cluster 집계로의 조용한 대체는 없다.

| 주제 | 지원 group_by 축 | 유지해야 할 계산 단위 |
|---|---|---|
| O01 | cluster, model, node | 장비/Node 신원, 현재 수량과 기간 변화 분리 |
| O02/O03 | cluster, model, node, namespace, pod, workload | 검증된 할당/관측 관계, 물리·MIG·공유 분리 |
| O04 | cluster, model, node, namespace, pod, workload | 같은 workload·동시 구간 안에서만 GPU 편차 계산; 서로 다른 작업을 합쳐 편차를 만들지 않음 |
| O05 | cluster, model, node | source/component/사건 정의별 구분, 재발은 같은 dedup_group 안에서만 |
| O06 | cluster, model, node, namespace, pod, workload | 사건 당시 검증된 관계. 복수 작업에 연결된 사건 수는 그룹 간 비가산임을 표시 |
| O07 | cluster, namespace, pod, workload | unbound Pod를 누락시키지 않음; node/model별 미배치 귀속은 미지원 |
| O08 | cluster, namespace, pod, workload | Namespace·Pod·소유 workload의 당시 관계, 프로젝트는 확인된 별도 근거만 |
| O09 | cluster, model, node | 물리 GPU 에너지. workload별 임의 균등 분배 없음 |
| O10 | cluster, model, node, namespace, pod, workload | 조치 ID·동일 대상·비교 가능한 전후 구간을 계속 구분 |
| O11 | cluster, model, node, namespace, pod, workload | 해당 그룹의 기대 대상·주기 분모가 있을 때만 커버리지 계산 |

지원 축도 신원/관측이 부족하면 해당 값은 null·사유, 주제는 partial/blocked다. 미확인 대상을 빈 문자열로 합쳐 정상 그룹을 만들지 않고 미귀속 건수·근거를 별도 표시한다. 고유 수는 해당 그룹에서 재중복 제거하고, 시간은 유효 구간 합집합, 평균은 유효시간 가중, 비율은 분자/분모 재계산, P95는 원본 유효시간 분포에서 다시 계산한다. 그룹 평균·P95·발생률의 단순 평균은 금지한다. 공유 관계의 그룹 합계가 물리 전체와 다를 수 있는 이유도 보존한다.

O05의 기준은 다음과 같다.

- 1.4 건수는 `episode_started_at ∈ [start,end)`인 고유 incident ID다. RCA 생략 사건도 포함하고 raw 알림·job 수는 포함하지 않는다. `analysis_excluded` 수집 장애는 별도 건수다. legacy는 occurred_at 기준 건수를 별도로 표시하며 새 에피소드 건수·발생률에 합치지 않는다.
- 재발 간격은 같은 완전한 `dedup_group`에서 연속 에피소드 시작 시각의 차이다. 모델·node 표시 그룹이 같아도 서로 다른 장비/component/source 간 간격을 만들지 않는다. 시작 시각은 수신 기준이므로 장비 고장 간격/MTBF라고 부르지 않는다. 기간 안 사건의 직전 사건 한 건은 기간 밖에서도 cutoff 안에서 읽어 간격만 계산하며 건수에는 더하지 않는다.
- 직전 사건 부재·신원 부족·시각 역전·legacy 혼합이면 그 간격은 null·사유다. 충분한 쌍이 없으면 평균도 null이며 0으로 채우지 않는다. 비교 기간은 각 `[start,end)`에 동일 규칙을 적용한다.
- 발생률은 같은 source/component·사건 정의·모델·대상 집합의 유효 관측 구간에 속한 사건 수 / 그 구간의 검증된 GPU-hours × 1,000이다. 분자와 분모가 쓰는 대상·기간을 evidence에 남긴다. 전체 사건 수와 발생률용 분자는 따로 표시하며 관측 공백의 사건을 분자에만 넣지 않는다.
- GPU 귀속·기대 대상·알람 관측 완전성이나 분모가 없으면 발생률은 null이다. machine/component 사건을 GPU별로 복제하거나 수집 장애에 GPU 분모를 붙이지 않는다. 비교·순위에는 §5.3 품질 기준도 적용한다. 검증된 분모가 있으면 §5.4의 40·10건 예처럼 계산하고 항상 null로 두지 않는다.

## 6. Knowledge 계약

| 역할 | 담을 내용 | 적용 방식 |
|---|---|---|
| Runbook | 의미·producer 계약·모델/버전·필수 증거·조건·권고·출처 | 정확 조건 후보 검색 후 권고별 적용 가능 검사 |
| 조사 procedure | 등록 ID·버전·입력·분기·종료·한도 | 코드 등록 함수. LLM이 임의 절차를 실행 코드로 등록하지 않음 |
| 운영 정책 | 품질·우선순위·조회 예산·권고 예외 | 발행 revision 사용 |
| 데이터 사전 | D 항목·원본 의미·단위·지원·query ID | 해당 source·모델·기간에 적용 |
| 참고·검증 사례 | 공식/내부 원문·실제 검토 결과·출처 | 후보·설명 보완. 검증 수준 명시 |

초안 draft→검토 요청 in_review→검토 완료 reviewed→발행 published→폐기 retired 흐름을 사용한다. 검토 action=request/approve/request_changes를 02 API로 처리하며 수정 요청·검토 후 내용 수정은 draft로 돌리고 재검토한다. 발행은 검토한 content_hash가 일치해야 한다. 발행 content는 불변이고 신규 revision으로 수정한다. 폐기는 신규 실행 선택만 막으며 과거 실행 인용은 보존한다.

지식은 분석 범위와 기술 호환성을 검사한다. 제품 권한/공개 범위 정책은 이번 범위에서 제외한다. 실제 사건 사례의 출처·검토 수준을 보존한다. 등록 procedure는 읽기 전용 메타데이터이며 화면에서 임의 실행 코드를 편집·발행하지 않는다.

지식 선택은 **호환 계약·모델·소프트웨어·정책 범위로 먼저 제한한 뒤 그 안에서 최신 발행본**을 고른다. 계약 B용 revision 2가 있다고 계약 A용 revision 1을 전역 최신 규칙으로 제거하지 않는다. supplier 권고와 DSX 정책은 출처를 구분한다. 필수 증거가 부족한 특정 권고만 보류하고 가능한 로그 확인 등의 권고는 유지한다.

LLM 결과·사용자 메모·유사도 높은 문서를 자동으로 검증된 지식에 발행하지 않는다. 결과의 근거·실제 운영 확인·검토를 거쳐 새 revision으로 등록한다.

## 7. LLM 입력·도구·출력 검사

LLM 입력에는 요청 scope·시간, 구조화 사실/수치·품질·evidence ID, 호환 발행 지식의 필요한 구간, 허용 도구·예산만 포함한다. 원시 메트릭·전체 Loki 로그를 통째로 전달하지 않는다. 로그·문서 안의 지시문은 분석 데이터로 취급하고 서버 실행 규칙을 바꾸지 않는다.

허용 도구는 자산 해석, 현재/과거 매핑, 등록 메트릭·로그 조회, 사건 이력, 제공되는 Pod 근거, Knowledge 조회다. 임의 SQL/PromQL/LogQL·쉘·장비 변경 도구를 LLM에 노출하지 않는다. MCP의 query_prometheus/query_loki_logs는 검증된 query ID·인자를 실제 쿼리로 만드는 업무 함수를 통해 호출한다. NAT의 도구 include 목록만으로 scope·시간·쿼리 내용이 제한된다고 가정하지 않는다. 도구 출력의 숫자를 다시 추정하지 않는다.

저장 전에는 JSON 스키마, 필수 필드, enum, 대상 scope, evidence ID 존재, 값·단위·기간·반올림 일치, 인과 판단 승격, 권고 선행 조건을 검사한다. 사실·수치는 구조화 값에서 렌더링하고 설명에 있는 수치 참조도 해당 필드와 연결한다. 검증 실패는 제한된 재생성 또는 설명 생략으로 처리하며 잘못된 설명을 정상 결과로 저장하지 않는다.

수치 주장에는 §8의 value_refs가 필수다. evidence ID가 존재하는지만 검사하지 않고 참조된 값의 대상·기간·단위·산식·source가 문장 주장과 맞는지 검사한다. `%↔비율`, `W↔kWh`, 현재 수량↔기간 합계를 임의 변환하거나 같은 숫자의 다른 대상을 인용하면 발행을 차단한다. 인과 확정은 검토된 confirmation_rule과 근거 검사로 제한하며 LLM의 자기 평가를 검증 수단으로 사용하지 않는다.

모델 제품은 아직 확정하지 않는다. 실제 서빙 가능 여부·모델/엔진·정밀도·GPU·동시 처리 수치는 C06/C07에서 평가·기록한다. 모델 교체 시 아래 동일 사례와 T30을 재검증한다.

## 8. 결과 계약

공통 최종 결과는 `job_id,kind,scope,target?,time_range,timezone,data_cutoff_at,result_schema_version,versions,result_status,measurements,facts,evidence_refs,quality,narrative_status,limitations`를 포함한다. result_schema_version은 1.1이다. scope는 02의 CPC별 namespaces 구조다. narrative_status는 complete/failed/omitted이며 작업 성공·result_status와 별개다.

facts는 `id,text,evidence_refs,value_refs`를 갖는다. 수치가 없으면 value_refs는 빈 배열이다. 수치 원본은 RCA·공통 도구의 measurements 또는 보고서 topics[].metrics 중 한 곳에만 두며 각 value의 id는 결과 전체에서 유일하다. value_refs는 그 id들의 배열이다. value는 `id,value,value_type,unit,target,period,method,quality,evidence_refs`를 포함한다. value_type은 number/integer/ratio/percentage이고 null은 quality.reason이 필수다. 백분율 값 3과 비율 0.03은 서로 다른 단위로 유지한다. measurements와 metrics를 수치 레지스트리로 해석하며 문장·HTML/CSV는 그 값을 참조해 렌더링한다.

RCA는 `incident_id,incident_time,current_checked_at,pod_relations,assessments,cause_candidates,recommendations,missing_inputs,termination_reason`을 추가한다. assessments는 purpose_id별 status·missing_inputs·evidence_refs이며 결과 상단 산출 상태 계산에 사용한다. 현행 1.3은 요청한 목적, 신규 1.4 목표는 11 §3.1.2의 Agent 선택·관련성 평가와 trace를 기준으로 검증한다. 확인된 미적용은 not_applicable이며 미확정·근거 부족을 미적용으로 숨기지 않는다. 후보는 `id,claim,causal_status,supporting_refs,contradicting_refs,value_refs,missing_inputs,confirmation_rule_ref?`, 권고는 `text,preconditions,eligibility=eligible|withheld,reason,evidence_refs,value_refs,execution=not_performed`를 가진다.

보고서는 `topics[]`를 추가한다. 각 주제는 `topic_id,status,metrics,facts,findings,missing_inputs,quality,evidence_refs,recommendations`를 가진다. metric은 공통 value 필드에 denominator를 추가하며 값이 null이면 이유가 필수다. O10에는 입력 action_record_ids와 비교 기간, O07에는 실제 resource/단위를 결과에 보존한다.

```json
{
  "job_id": "7af117a4-c4bb-4b57-8f0b-d08fc88bfd1c",
  "kind": "report",
  "result_schema_version": "1.1",
  "scope": {"clusters": [{"cluster_id": "cpc-2", "namespaces": ["dev"]}]},
  "time_range": {"start": "2026-09-15T01:00:00Z", "end": "2026-09-15T02:00:00Z"},
  "timezone": "Asia/Seoul",
  "data_cutoff_at": "2026-09-15T02:01:00Z",
  "versions": {"criteria": "1.1", "query": "test-v1.1", "model": "not_used"},
  "result_status": "partial",
  "measurements": [],
  "facts": [],
  "evidence_refs": ["943cb0e4-6279-4c83-8d25-536b810d35c5"],
  "quality": {"history_coverage": null},
  "narrative_status": "omitted",
  "limitations": ["기간 이력 없음"],
  "topics": [{
    "topic_id": "O02",
    "status": "partial",
    "metrics": [
      {"id": "O02.current_allocated_gpu", "value": 2, "value_type": "integer", "unit": "physical_gpu", "target": {"cluster_id": "cpc-2", "namespace": "dev"}, "period": {"at": "2026-09-15T02:00:00Z"}, "denominator": null, "method": "unique_exclusive_devices", "quality": {"scope": "observed_mapping"}, "evidence_refs": ["943cb0e4-6279-4c83-8d25-536b810d35c5"]},
      {"id": "O02.allocated_gpu_hours", "value": null, "value_type": "number", "unit": "GPU-hours", "target": {"cluster_id": "cpc-2", "namespace": "dev"}, "period": {"start": "2026-09-15T01:00:00Z", "end": "2026-09-15T02:00:00Z"}, "denominator": null, "method": "valid_interval_union", "quality": {"reason": "mapping_history_missing"}, "evidence_refs": []}
    ],
    "facts": [{"id": "F-current", "text": "현재 확인된 전용 할당 GPU는 2개다.", "value_refs": ["O02.current_allocated_gpu"], "evidence_refs": ["943cb0e4-6279-4c83-8d25-536b810d35c5"]}],
    "findings": [],
    "missing_inputs": ["mapping_history"],
    "quality": {"history_coverage": null},
    "evidence_refs": ["943cb0e4-6279-4c83-8d25-536b810d35c5"],
    "recommendations": []
  }]
}
```

예시의 현재 수량은 기간 집계와 다른 기준 시각을 명시한다. 결과에 실제 evidence·query·모델 revision을 채우는 것은 실행 책임이다. 표·파일도 저장된 값에서 생성하며 화면마다 산식을 다시 적용하지 않는다.


## 9. 검수

수치 고정 사례·근거 연결·설명 실패·버전 재현은 [05](../05_테스트_검수_기준서.md), 큐 수명주기는 [14](14_모듈간_호출과_공통실행_계약.md)를 따른다. 시험 환경과 실행 결과는 각 모듈 QA를 참조하며 고정 사례 시험을 운영 데이터·모델 품질 검수로 확대 해석하지 않는다.

## 10. NAT 적용 근거

NAT의 Python 실행·사용자 정의 함수·MCP 클라이언트 기능을 사용한다. 아래는 도구 기능의 근거이며 DSX의 큐·소유권·판단 규칙은 이 설계의 결정이다. 설치 버전과 실제 모델 호환성은 C11에서 검증·고정한다.

- [NVIDIA 워크플로 실행](https://docs.nvidia.com/nemo/agent-toolkit/latest/run-workflows/about-running-workflows.html)
- [NVIDIA 사용자 정의 함수](https://docs.nvidia.com/nemo/agent-toolkit/latest/extend/custom-components/custom-functions/functions.html)
- [NVIDIA MCP 클라이언트](https://docs.nvidia.com/nemo/agent-toolkit/latest/build-workflows/mcp-client.html)
- [NVIDIA Tool Calling Agent](https://docs.nvidia.com/nemo/agent-toolkit/latest/components/agents/tool-calling-agent/index.html)
