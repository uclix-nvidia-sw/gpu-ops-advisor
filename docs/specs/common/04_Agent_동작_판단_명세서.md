# 04. Agent 공통 동작·판단 명세서

이 문서는 공통 계산·품질·결과 의미를 다룬다. 현재 RCA 실행·응답 검증은 [RCA 계약](../rca-agent/11_RCA_Agent_모듈_설계서.md), 신규 기본 보고서는 [집계 계약](../ops-agent/aggregate-report-v1.md), 기존 O계열 계산은 [Ops 안내](../../../ops-agent/README.md)를 따른다. 기존 O계열의 criteria 1.1/1.2/1.3 경로를 구분하고 한 버전을 모든 경로의 현행으로 적용하지 않는다.

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
| Grafana MCP 관측 조회 | 부족한 사고 증거와 후속 조사 | 주제별 기간 지표·관련 로그, query+CPC별 병렬 task | 범위를 제한한 조회 함수·공유 예산 |
| 계산·품질·규칙 | 조사 수치·조건 확인 | 주제별 지표·통계 산출 | Python 코드 |
| 분석·설명 | 추가 수집 후 원인 후보·지지/반박·권고·재조사 제안 | 현행 fact_ids 선택; 목표는 도구 없는 단일 Synthesis의 현황·변화·개선 조언·한계 | LLM, 수치·증거 참조. RCA의 기존 증거 충분 경로는 코드로 결과 작성 |
| 검증·저장·완료 | 자기 후보·근거 | 자기 후보·근거·파일 | Worker 코드, LLM 선택 도구 아님 |

RCA의 추가 조회 선택은 11의 규칙·명시적 탐색 허용과 JSON query ID 계약을 따른다. 모델이 임의 도구를 실행하는 권한으로 해석하지 않는다. 보고서는 등록된 수집·계산 순서를 실행하며 LLM에 집계 산식을 생성시키지 않는다. NAT 호출 중에도 비동기 heartbeat가 계속 동작해야 하며 숨은 병렬 추론·중첩 재시도로 14의 한도를 초과하지 않는다.

## 3. RCA

[11 RCA](../rca-agent/11_RCA_Agent_모듈_설계서.md)의 입력·조사 계약을 따른다. incident_id는 필수다. 현재 Runbook-first 입력과 기존 목적 기반 입력의 버전·호환은 [14](14_모듈간_호출과_공통실행_계약.md)와 구현을 기준으로 구분한다. 이번 평가 분리는 입력 purpose 선택이나 Incident 에피소드 정책을 새로 도입하는 변경이 아니다.

현재 Runbook 선택·일반 조사 fallback·수집 라운드·Synthesis 검증은 [RCA README](../../../rcca-agent/README.md)와 [11의 현행 계약](../rca-agent/11_RCA_Agent_모듈_설계서.md)을 따른다. 검색 일치나 MCP 조회 성공만으로 원인 분석 품질을 판정하지 않는다. 모델 미구성·오류에서도 유효 사실과 미확정 사유를 보존하되 14의 실행 실패·슬롯 반환 계약이 우선한다. 신규 입력 계약과 기존 입력의 호환은 14를 따르며 과거 R 기반 목표를 현재 Runbook-first 흐름으로 설명하지 않는다.

구현 흐름은 [11의 평가 분리 설계](../rca-agent/11_RCA_Agent_모듈_설계서.md#평가-분리-설계개발)다. 수집 상태는 코드, 증거 의미는 코드의 명확한 검사와 LLM 해석, 분석 품질은 코드 검증과 별도 LLM 검토로 나눈다. 호출·반복 설계는 11, 공통 결과 구조는 아래 §8.1이 소유한다. 구현과 실제 모델 품질 검증 완료는 구분한다.

## 4. 보고서

[12 보고서](../ops-agent/12_보고서_Agent_모듈_설계서.md)의 O01~O11을 따른다. 즉시·정기 보고서는 같은 계산과 결과 형식을 사용한다.

현재 보고서는 **고정 DB 입력 → query+CPC 수집 계획·예산·의존성 → 병렬 Observation → 품질 검사·결정적 계산 → 검증된 사실·보고서 문장 선택 → 저장·JC 공개**다. task는 한 Worker/job/lease 안에서 실행하며 LLM을 호출하지 않는다. 부족한 판단을 위한 보완 라운드·개선 후보 기반 자유 생성형 Synthesis는 후속 목표다. 실행·예산·취소는 14, 실제 계획과 남은 범위는 12를 따른다.

계산은 기존 metrics 레지스트리를 단일 수치 원본으로 사용한다. 개선 후보·eligibility는 검증된 관측과 정책·업무 전제로 코드가 평가하고, LLM은 그 범위에서 해석·다음 확인 방법을 작성한다. 공개 RCA의 원인 수준을 승격하거나 미완료를 원인 없음으로 바꾸지 않는다. 새로운 수치·인과·정비 순위·절감 효과를 근거 없이 추가하지 않는다. 통계가 있어도 권고 전제가 없으면 해당 권고는 withheld이며 다른 통계/조언은 유지한다.

보고서 Synthesis는 도구 없이 검증된 사실·수치·후보·전제·반박·한계만 받는다. 출력은 기존 facts/findings/recommendations·value_refs/evidence_refs로 검증·변환한다. §7의 의미 검사로 확인할 수 없는 새 주장은 확정 사실로 발행하지 않는다. 설명 미설정/확정 실패/무효 출력은 유효 코드 결과와 분리하며, 원격 종료 불명과 실행권 상실은 14의 실패·슬롯 반환 계약을 우선한다. 결과 스키마 1.1·접수 계약 1.3을 유지하고 집계 의미 변경은 기존 §5.5의 criteria 1.2 목표로 구분한다.

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

2026-09-30 O08 namespace 초안(criteria 1.2)은 연결 관측 구간과 D02 활동 구간을 교차해 **연결된 GPU의 관측 평균 활동률**을 추가한다. 관측 연결만으로 namespace 실사용률을 확정하지 않는 위 원칙은 유지한다. 표본 시각 자체뿐 아니라 원본 유효시간의 겹침을 검사하고 충돌 구간만 제외한다. 동시 복수 Pod/namespace, 확인된 공유/MIG, 활동 신원 불일치, 잘못된 단위/범위는 해당 구간의 평균 귀속을 보류한다. 복수 GPU의 모델 미확인 또는 혼합 모델은 그룹 평균을 보류한다. 분모는 채택한 연결 GPU-seconds이며 전체 기대 대상 분모·비교/순위 적격성으로 바꾸지 않는다. 유효시간 밖을 0으로 채우지 않고 제외 사유를 보존한다.

O08 criteria 1.2의 클러스터 관측 요약(2026-10-02)은 Namespace 간 같은 GPU 연결 구간을 합쳐 중복을 제거한다. Namespace·Pod 라벨 부재 자체는 연결 조인 실패나 유휴의 증명이 아니다. 이를 정보 사유로 분리하고 실제 미충족 입력만 품질에 반영한다. 독점 할당 미확인은 기존 할당 계산에서는 부족 사유지만, 관측만 산출하는 이 경로에서는 해석 제한으로 유지한다. D01 조회 실패·불완전 기간·신원 미확인 시 관측되지 않은 연결을 0으로 채우지 않는다.

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

수치 주장에는 §8의 value_refs가 필수다. evidence ID가 존재하는지만 검사하지 않고 참조된 값의 대상·기간·단위·산식·source가 문장 주장과 맞는지 검사한다. `%↔비율`, `W↔kWh`, 현재 수량↔기간 합계를 임의 변환하거나 같은 숫자의 다른 대상을 인용하면 발행을 차단한다. 인과 확정은 검토된 confirmation_rule과 근거 검사로 제한하며 LLM의 자기 평가를 인과 확정의 검증 수단으로 사용하지 않는다. 11의 별도 LLM 검토는 과장·모순·누락을 찾는 보조 검토이며 이 원칙이나 코드 검증을 대체하지 않는다.

모델 제품은 아직 확정하지 않는다. 실제 서빙 가능 여부·모델/엔진·정밀도·GPU·동시 처리 수치는 C06/C07에서 평가·기록한다. 모델 교체 시 아래 동일 사례와 T30을 재검증한다.

## 8. 결과 계약

공통 최종 결과는 `job_id,kind,scope,target?,time_range,timezone,data_cutoff_at,result_schema_version,versions,result_status,measurements,facts,evidence_refs,quality,narrative_status,limitations`를 포함한다. result_schema_version은 1.1이다. scope는 02의 CPC별 namespaces 구조다. narrative_status는 complete/failed/omitted이며 작업 성공·result_status와 별개다.

facts는 `id,text,evidence_refs,value_refs`를 갖는다. 수치가 없으면 value_refs는 빈 배열이다. 수치 원본은 RCA·공통 도구의 measurements 또는 보고서 topics[].metrics 중 한 곳에만 두며 각 value의 id는 결과 전체에서 유일하다. value_refs는 그 id들의 배열이다. value는 `id,value,value_type,unit,target,period,method,quality,evidence_refs`를 포함한다. value_type은 number/integer/ratio/percentage이고 null은 quality.reason이 필수다. 백분율 값 3과 비율 0.03은 서로 다른 단위로 유지한다. measurements와 metrics를 수치 레지스트리로 해석하며 문장·HTML/CSV는 그 값을 참조해 렌더링한다.

RCA는 `incident_id,incident_time,current_checked_at,pod_relations,assessments,cause_candidates,recommendations,missing_inputs,termination_reason`을 추가한다. assessments는 purpose_id별 status·missing_inputs·evidence_refs이며 결과 상단 산출 상태 계산에 사용한다. 입력 계약별 assessment와 trace의 연결은 11/14와 현재 validator를 따른다. 평가 확장만으로 기존 목적·Runbook assessment를 재해석하지 않는다. 확인된 미적용은 not_applicable이며 미확정·근거 부족을 미적용으로 숨기지 않는다. 후보는 `id,claim,causal_status,supporting_refs,contradicting_refs,value_refs,missing_inputs,confirmation_rule_ref?`, 권고는 `text,preconditions,eligibility=eligible|withheld,reason,evidence_refs,value_refs,execution=not_performed`를 가진다.

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


### 8.1 RCA 평가 분리 결과 확장

아래는 [11의 설계·개발](../rca-agent/11_RCA_Agent_모듈_설계서.md#평가-분리-설계개발)의 결과 계약이다. `result_schema_version=1.1`의 선택적 `quality.rca_evaluation` 확장으로 생산한다. 검증·배포 상태는 Agent QA를 따른다. 기존 필드의 의미나 필수성을 바꿔야 한다면 기존 버전에 덮어쓰지 말고 별도 버전 전환으로 처리한다.

| 필드 | 형식·의미 |
|---|---|
| `schema_version` | 문자열 `"1"` 또는 `"2"`. 평가 확장 자체의 버전이며 input/result_schema 버전과 별개 |
| `collection` | `{status, reason, query_results, evidence_refs}`. status는 `complete/partial/failed/not_requested`. complete 이외에는 reason 필수 |
| `evidence` | `{execution_status, reason, evidence_refs}`. refs는 검증된 해석 기록과 기초 진단 기록. 실행 완료는 모든 의미 확인 완료가 아님 |
| `analysis_id` | 최종 발행할 초안의 hash. 코드 fallback도 ID를 생성; result content_hash와 별개 |
| `review` | `{execution_status, verdict, reason, analysis_id, evidence_refs, rubric_version, criteria}`. 최종 초안 검토와 항목별 판정만 요약. fast path는 rubric/criteria를 생략할 수 있음 |
| `investigation` | `{status:"finished", stop_reason, evidence_refs}`. 이 attempt의 조사 종료이며 사건 종결·장비 회복과 다름 |

`execution_status`는 `complete/failed/skipped`다. `reason`은 실패·생략이면 필수 문자열, 정상 완료이면 null을 허용한다. `review.verdict`는 complete일 때 `acceptable/revision_required/undetermined`, failed/skipped일 때 null이다. UI의 ‘미검토’는 failed/skipped의 표시이며 LLM 판정 값이 아니다. 참조된 해석 기록 안의 unknowns/conflicts가 비어 있지 않아도 해석 실행은 complete일 수 있다.

`review.criteria`는 11의 rubric 키별 `{status, reason, evidence_refs}`다. 항목 상태는 `pass/needs_revision/undetermined/not_applicable`; 의미 기준과 종합 판정 우선순위는 11이 소유한다. 미검토는 빈 criteria와 null verdict로 표시한다.

수집 상태는 자료의 의미나 분석 판정으로 계산하지 않는다. query_results는 계획된 조회별 `query_id`, 실행 여부 `executed/skipped`, 기존 `tool_status`(미실행은 null), complete 여부·reason·evidence_refs를 가진다. 행/청크별 세부 제한은 기존 증거의 quality가 원본이다.

- 계획된 조회가 없거나 fast path로 수집 자체가 필요 없으면 `not_requested`와 이유를 기록한다. 단순히 실제 호출이 0회라는 이유만으로 이 상태를 사용하지 않는다.
- 계획한 수집이 모두 완료되고 각 응답이 ok/empty·완전하면 `complete`다. 빈 결과는 조회 완료이며 장애 없음의 증거가 아니다.
- 일부 조회 완료(빈 응답 포함) 또는 부분 반환 자료가 있으나 잘림·실패·누락·미실행이 섞였으면 `partial`이다. 반환된 내용의 기초 검증·의미 해석 실패는 별도 축에 남긴다.
- 계획했지만 반환 자료/완료된 빈 응답이 전혀 없고 모두 실패·미실행이면 `failed`다. 미실행의 예산·정책·조건 사유를 유지한다.

`stop_reason`은 `review_accepted/no_available_followup/followup_not_selected/selection_conditions_missing/query_budget_exhausted/llm_budget_exhausted/round_limit_reached/revision_limit_reached/analysis_unresolved/no_usable_evidence/model_unavailable/fast_path` 중 하나다. 이는 발행 가능한 종료의 상세 사유이며 기존 `termination_reason` enum을 대체하지 않는다. 원격 종료 불명·취소·lease 상실·실행 deadline 초과는 이 필드로 정상 공개하지 않고 14의 실패 경로를 따른다. 검토 입력이 너무 커서 남은 예산에 들어가지 않는 경우는 `llm_budget_exhausted`와 단계 진단으로 남긴다.

schema 2는 `generation_mode=combined/separate`를 명시한다. combined의 evidence refs는 기초 진단과 `rca_synthesis`의 채택된 `interpretation`에 연결하며 독립 해석 완료 기록을 만들지 않는다. `evidence.interpretation`은 최종 자료에 남은 해석이며 실패/보류는 null일 수 있다. 초안 hash에 해석과 실제 입력 view hash를 포함한다. 원본 관측 refs와 진단 포함 input refs를 구분하고 생성된 finding ID는 별도 의존 참조다.

목적 정책 사용 시 `review.rubric_version=2`, `investigation.objective`에 고정 대상·기간, Runbook revision/hash·목적, 기준별 code/llm·required·상태·finding/원본 refs, 차단 상태·필수 근거 부족·남겨도 되는 미확인을 보존한다. `goal_achieved`는 모든 필수 기준·차단 조건과 같은 최종 자료의 acceptable 검토가 필요하다. `goal_not_met`는 목적 미달이며 가능한 필수 보완이 없는 종료다. 두 값을 기존 stop_reason에 추가한다. 원인 확정·현재 건강과 별개이며 구 schema 1에는 소급 적용하지 않는다.

`rca_result_frozen`은 보고서가 아닌 최종 RCA 근거 자료와 `material_hash`를 저장한다. `report_assembly`는 이 기록을 evidence ref와 hash로 연결한다. 보고서 구성 후 RCA 자료 hash를 다시 검사하며 판단을 바꾸면 공개하지 않는다. 동일 증거의 재작성 차단·문제 주장 보류는 기록에 남기고, 변경 자료의 review는 skipped/null(`draft_changed_after_review`)이다. 이전 검토 지적은 원본 기록에서 읽는다.

예시 값은 구조 설명용이며 실제 ID가 아니다.

```json
{
  "schema_version": "1",
  "collection": {
    "status": "partial",
    "reason": "incomplete_queries",
    "query_results": [
      {"query_id": "D09", "execution_status": "executed", "tool_status": "partial", "complete": false, "reason": "response_byte_limit", "evidence_refs": ["raw-record"]}
    ],
    "evidence_refs": ["raw-record"]
  },
  "evidence": {"execution_status": "complete", "reason": null, "evidence_refs": ["interpretation-record"]},
  "analysis_id": "final-draft-hash",
  "review": {
    "execution_status": "complete",
    "verdict": "acceptable",
    "reason": null,
    "analysis_id": "final-draft-hash",
    "evidence_refs": ["review-record"]
  },
  "investigation": {"status": "finished", "stop_reason": "no_available_followup", "evidence_refs": ["decision-record"]}
}
```

실제 결과의 query_results에는 모든 계획·실행 행을 채우고 각 참조를 저장된 evidence에 연결한다.

#### 기록의 관계와 검증

기존 evidence 저장소에 다음 stage의 구조화 기록을 추가한다. 아래 필드와 설명은 개발 계약이며 원시 모델 응답 전체나 내부 사고 과정을 저장하는 요구가 아니다.

| 기록 | 필요한 내용 |
|---|---|
| `evidence_validation` | `checks[]`: check/outcome/reason/location/evidence_refs. outcome은 pass/fail/unknown/not_applicable; 정확 일치 검사 실패를 신원 불일치 확정으로 해석하지 않음 |
| `evidence_interpretation` | `interpretation.findings[]`: id/statement/kind(observed 또는 inferred)/evidence_refs, `unknowns/conflicts/limitations`: statement와 refs의 목록. unknown은 관측 ref가 없을 수 있으나 계획·실패 기록 또는 이유가 필요 |
| `rca_analysis_draft` | analysis_id, input_view_hash, claims(id/source/statement/supporting_refs/contradicting_refs/value_refs), 권고·한계와 기존 결과 필드로의 연결 |
| `analysis_review` | analysis_id, execution_status/reason, `review.verdict/criteria`, `review.issues[]`: claim_id 또는 초안 전체 대상/reason/evidence_refs/suggested_resolution, `followup_questions[]`: question/expected_effect/query_ids |
| `investigation_decision` | action=`revise/collect/finish`, reason, 검토·초안·입력 기록 refs, 선택 query IDs, 라운드·수정 횟수·남은 예산 |

새 LLM 단계에는 `round`, `stage`, `input_evidence_refs`, 실행 상태·시작/종료 시각을 기록한다. 코드 단계의 생성 시각은 실행 소요시간으로 해석하지 않는다. 모델 호출에는 실제 사용 모델, stage, 논리 호출 번호와 전송 시도 수, 토큰 사용량·경과시간·생략 이유, 실제 입력 refs·view hash·context_selection을 연결한다. API 키·원시 예외 메시지·숨겨진 사고 과정은 저장하지 않는다. `recorded_at/record_sequence/plan_order`의 기존 의미는 유지하며 timestamp만으로 단계 간 의존성을 만들지 않는다.

검증기는 일반 `evidence_refs`뿐 아니라 `input_evidence_refs`, claim_id와 analysis_id 연결도 검사한다. LLM은 해당 호출에 실제 전달된 근거만 참조할 수 있고 존재하는 evidence라도 범위 밖·입력 미포함이면 거절한다. 상충 근거는 각 원문으로 연결한다. ID 존재 검사가 주장 진실성의 증명은 아니다. 가설·제안 query·권고를 검증된 facts/measurements에 병합하지 않는다.

최종 `review.analysis_id`는 최종 `analysis_id`와 같아야 한다. 초안이 변경되면 재검토하거나 skipped/verdict=null로 바꾸고 사유를 남긴다. 이전 검토는 이전 초안 evidence에 보존하며 최종 통과로 표시하지 않는다. 검토에서 문제가 지적된 주장을 제거하는 것도 초안 변경이다. 입력 뷰에 증거가 추가되거나 해석이 변경돼도 새 초안 ID로 검토한다.

#### 기존 소비자와의 호환

해석·검토 evidence의 snapshot과 quality에는 선택적 `request_checks[]`를 같은 순서로 저장한다. 최초와 형식 복구 요청별 `input_bytes/max_input_bytes`, `remaining_tokens/reserved_tokens/available_tokens`, `required_tokens`, `input_size_exceeded/token_budget_exhausted`, `model_called`를 담는다. `required_tokens`는 본문·프롬프트 바이트+512의 기존 보수적 사전 검사값이며, available이 이 값보다 커야 한다. 본문 바이트는 전송 envelope 전체 크기가 아니다. 전송 계산을 제공하는 모델은 `prompt_token_bound/configured_output_tokens/output_token_cap`도 남긴다. 출력 cap은 최초 전송 예정값으로, 생략된 요청의 실제 사용량이나 전송 재시도의 최종 cap이 아니다. 내용·키·응답 원문은 이 진단에 넣지 않는다.

새 상세 사유 `llm_input_size_exceeded`는 기존 `llm_token_budget_exhausted`와 구분한다. 동시 발생 시 전자를 주 사유로 하고 두 boolean을 보존한다. 최종 종료 enum은 추가하지 않으며 각각 `analysis_unresolved`/`llm_budget_exhausted`로 연결한다. 변경된 초안 재검토의 실패는 기존 `draft_changed_after_review`와 선택적 `failure_reason`으로 함께 표현한다. 관련 단계 quality와 최종 `review`에도 보존한다.

공통 `llm_usage`와 단계 usage delta의 기존 `total_tokens`는 모델 보고값을 유지한다. 선택적 `charged_tokens`는 실제 예산 차감량, `estimated_tokens`는 그중 total_tokens 미보고 응답의 보수적 차감량, `usage_missing_calls`는 해당 응답 수다. 실제 모델 측정치와 추정 차감량을 합쳐 실측 토큰이라고 표시하지 않는다. 이 추가 진단은 구 기록에 필수가 아니며 schema 1/결과 1.1의 기존 필수 필드와 공개 hash는 유지한다.

선택적 `quality.analysis.synthesis.budget_allocation`과 `rca_synthesis.snapshot.diagnostics.budget_allocation`은 분석 전 예약 결정 진단이다. 기존 요청/적용 예약·남은 예산·근거 수용 여부를 유지하며 검토 하한·산정 근거·조정 사유를 추가할 수 있다. 값이 없는 구 결과를 계산해 채우지 않는다. 수집·원인 확정·분석 검토 상태를 변경하는 필드가 아니며 실제 호출은 별도 횟수로 확인한다. 산식과 필드는 [11의 F2-A](../rca-agent/11_RCA_Agent_모듈_설계서.md)를 따른다.

Runbook 원문 evidence의 선택적 `quality.selection_evidence_id`와 조사 계획 snapshot의 `selection_evidence_id`는 같은 attempt의 선택 진단 ID다. 최초·확장 계획의 `evidence_refs`는 실제 선택한 Runbook 원문 ID를 담는다. 본문 보존과 참조 연결이며 적용/원인 확정 상태를 추가하지 않는다. 구 기록에 없는 연결은 생성 시각으로 추정하지 않는다.

- `result_status`, assessments, `quality.analysis`와 sufficiency 호환 요약, `termination_reason`, `causal_status`, `narrative_status`의 기존 의미와 값은 유지한다. 타당 판정만으로 ready/confirmed로 승격하지 않는다.
- 과거 결과에 확장이 없으면 ‘평가 분리 기록 없음’으로 표시한다. 과거 호출 실패를 추정하거나 기본 acceptable을 넣지 않는다. 알 수 없는 확장 버전은 원본 보존·지원되지 않는 평가 형식으로 표시하고 기존 결과는 읽을 수 있게 한다.
- 새 Worker는 자신이 쓰는 schema_version=1/2의 상태·refs·ID를 검증한다. Backend/JC는 기존 저장·공개 권한·hash를 검증하며 LLM 의미 평가를 대신하지 않는다.
- Ops는 공개 결과 ID/hash와 원인 수준을 그대로 인용하고 새 검토 상태·한계를 함께 전달한다. 미검토·미확정·제외된 주장을 타당·확정·실제 조치로 바꾸지 않는다.
- 결과 요약은 final draft만, 과거 초안·검토는 디버깅 기록만 참조한다. 보류 내용과 무효 모델 응답을 일반 보고서에 되살리지 않는다.
- 기존 DB JSON/evidence 경로를 재사용하고 과거 결과·snapshot·hash를 backfill하지 않는다. 생산자 활성화 전에 소비자 호환성을 확인하며 실행 순서는 14를 따른다.

### RCA 종료 후 시간 진단 — 개발 목표

[11 R10/V31](../rca-agent/11_RCA_Agent_모듈_설계서.md#실행-종료-후-소요-시간-디버깅--개발-목표)의 추가 계약이며 현재 모든 단계가 계측·저장된다는 뜻이 아니다. 기존 stage의 started_at/completed_at/elapsed_seconds를 우선 재사용하고 실제 저장 경로·필드명/버전은 S1에서 생산자·소비자가 함께 확정한다.

| 정보 | 의미·검증 규칙 |
|---|---|
| 연결 | job_id·attempt_no·stage/실행 ID, 필요 시 collection_round·revision_no·query/request/call ID·전송 시도·부모 단계. 다른 attempt의 기록 혼합 금지 |
| 시각·기간 | 시작/종료 UTC 시각과 측정 elapsed_seconds, 생산자/측정 범위·수집 상태. 같은 프로세스 기간은 단조 시계 측정값 사용, 음수·잘못된 순서 거절. recorded_at을 실행 시각으로 대체하지 않음 |
| 전체·집계 | attempt 시작부터 종료까지인지, workflow만인지 범위 명시. queue 대기는 별도. 배치 벽시계 경과와 개별 호출 합은 구분, 부모/자식·겹친 구간 중복 합산 금지 |
| 누락·미완료 | 값 없는 경우 null/누락과 미기록 사유, 명시적 미실행 상태 구분. 시작만 있으면 종료 미기록, timeout이면 기록된 중단 시점까지만. 시각 차로 보조 계산할 때 동일 시계 출처와 계산 방식 표시 |
| 실행 결과 | 완료/실패/취소/timeout/미실행과 실패 코드·사용한 시간 제한 종류/값을 실제 기록에 연결. 원격 종료 불명은 그대로 보존 |
| 진단 완전성 | 계측된 단계/누락 구간·출처와 조회 범위. 모델 서버 대기·생성 시간은 원천이 제공할 때만 분리하며 추정하지 않음 |

시간 진단은 품질·목적 달성 판정이 아니다. 결과 저장/JC 완료 시간은 불변 result/evidence hash를 나중에 고쳐 넣지 않고 연결된 실행 진단으로 제공한다. 성공 결과가 없는 경우의 진단은 공개 결과처럼 보이지 않는 개발용 attempt 조회로 연결한다. 구 결과·미지원 진단 버전·부분 기록은 그대로 읽고 시간을 생성하지 않는다. 저장/조회 책임과 실패 경로는 [14](14_모듈간_호출과_공통실행_계약.md#rca-종료-후-시간-계측--개발-목표)에 둔다.

## 9. 검수

수치 고정 사례·근거 연결·설명 실패·버전 재현은 [05](../05_테스트_검수_기준서.md), 큐 수명주기는 [14](14_모듈간_호출과_공통실행_계약.md)를 따른다. 시험 환경과 실행 결과는 각 모듈 QA를 참조하며 고정 사례 시험을 운영 데이터·모델 품질 검수로 확대 해석하지 않는다.

## 10. NAT 적용 근거

NAT의 Python 실행·사용자 정의 함수·MCP 클라이언트 기능을 사용한다. 아래는 도구 기능의 근거이며 DSX의 큐·소유권·판단 규칙은 이 설계의 결정이다. 설치 버전과 실제 모델 호환성은 C11에서 검증·고정한다.

- [NVIDIA 워크플로 실행](https://docs.nvidia.com/nemo/agent-toolkit/latest/run-workflows/about-running-workflows.html)
- [NVIDIA 사용자 정의 함수](https://docs.nvidia.com/nemo/agent-toolkit/latest/extend/custom-components/custom-functions/functions.html)
- [NVIDIA MCP 클라이언트](https://docs.nvidia.com/nemo/agent-toolkit/latest/build-workflows/mcp-client.html)
- [NVIDIA Tool Calling Agent](https://docs.nvidia.com/nemo/agent-toolkit/latest/components/agents/tool-calling-agent/index.html)
