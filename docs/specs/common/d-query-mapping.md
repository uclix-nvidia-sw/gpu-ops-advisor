# 메트릭·쿼리별 D 매핑 설계

기준일: 2026-10-02. **목적: 기존 분석 기능·결과를 보존하면서 중복 조회 D01/D08→D02, 파생 보기 D05→D09의 상태 처리로 통합하고, D15~D49의 독립 메트릭 쿼리 35개를 추가한다. O·RCA의 이전→이후 입력과 새 산출물은 §6/§7에 정의한다.**

**확정 원칙: D 하나는 하나의 논리 쿼리 정의다. 필요한 메트릭마다 독립 D를 추가한다. D 내부에 여러 메트릭이나 D03.used/free 하위 구조를 넣지 않는다.** 기간 분할·클러스터별 실행은 같은 쿼리 정의의 반복이며 다른 메트릭을 한 D에 담는 것과 다르다.

이 문서는 기존 자료를 실제 D 번호와 연결한 **개발용 매핑 초안**이다. 신규 번호 D15~D49는 이 문서에서 제안하는 번호이며 설정에 등록되거나 발행되지 않았다. 운영 가용성·타입·단위가 미확인인 항목은 구현 시 활성화하지 않는다. 번호 배정과 실환경 사용 가능 확인을 혼동하지 않는다.

## 1. 근거와 읽는 방법

- [현행 Agent 설정](../../../agents/config.example.json): 현재 D의 실행 원본·단위·조건.
- [CPC-2 수집 기록](../../evidence/CPC-2_수집검증_20260915.md): 09-15 직접 수집 기록. KSM 세 항목, DCGM GPU_UTIL/FB_USED/FB_FREE, up/scrape_duration_seconds.
- [GPU 메트릭 대조표](../../evidence/GPU_메트릭_대조목록_20260915.md): Exporter 설정·Fleet 소스·제공 표본의 범위별 근거. 부록에서 모든 행을 매핑 또는 보류로 분류한다.
- [RCA 메트릭 참고](../rca-agent/references/domain-category-metric-mapping.md): 09-22 소스/catalog 대조. 현재 가용성을 보장하지 않는다.

아래 이름은 실제 설정/참고 자료의 이름이다. Fleet는 원본 이름과 OTel→Mimir 중앙 이름을 대조해야 한다. 대소문자 변환으로 실행 이름을 추정하지 않는다. 현행, 과거 관측, 소스 후보는 다른 근거 수준이다. 전체 표는 현재 실환경 재검증 전이다.

각 신규 D의 revision은 최초 발행 때 고정한다. 원본 이름·단위·타입·대상 의미 변경은 revision 변경 사유다. 동일 의미의 Fleet/Exporter 중 하나를 쓰려면 동등성 검증 후 실행 프로필에서 하나의 binding을 선택한다. 이번 번호 표에 없는 별도 source 쿼리가 필요하면 새 D를 정의하며, 하나의 D가 두 source를 동시 조회하지 않는다.

## 2. 조회 조건·반환 계약

| 조건 코드 | 조회 조건 | 반환 대상·필수 검사 |
|---|---|---|
| G | 지정 metric + 승인 cluster selector + 요청 GPU UUID/Node 필터 + 고정 기간의 원본 표본 | cluster+GPU UUID+원본 timestamp별 값·라벨. producer별 UUID 라벨과 단위 확인 |
| N | 지정 metric + 승인 cluster/Node 범위 + 기간 | cluster+검증된 Node 신원+timestamp. Namespace 라벨을 무조건 붙이지 않음 |
| P | 지정 metric + 승인 cluster/Namespace/Pod 범위 + 기간 | Pod/Container 신원·timestamp·원본 labels. 다른 관측과 조인은 UID·유효시간 확인 |
| T | 지정 metric + 승인 cluster와 수집 target 범위 + 기간 | target별 timestamp·값. 수집 target 수를 GPU 수로 환산하지 않음 |
| L | 등록 Loki selector + 승인 cluster/Node/component의 검증된 label/JSON 필터 + 기간 | 원문·Loki 시각·원본 사건 시각(있을 때)·대상·producer. 원문에 없는 시각/대상 추정 금지 |

Prometheus 쿼리는 현행 원본 range-vector 방식으로 metric 하나를 조회한다. 표의 조건은 의미 계약이며 실제 label 이름·selector·주기·max_hold는 환경별 근거 확인 후 고정한다. Node/target 범위 투영이 권한 내에서 불가능하면 조회 불가로 반환한다. 자동으로 전체 클러스터 조회로 넓히지 않는다.

모든 D 결과는 query_id·query_version·source·scope·기간·단위·품질·근거 ID와 원본 표본/사건을 가진다. 원본 counter의 증가량, 비율, 조인, 평균은 등록된 코드가 계산한다. 기존 출력과 구분되는 추가 출력으로 기록하며 기존 필수 입력/정책을 자동 변경하지 않는다. 빈 결과·실패·실제 0을 구분하고 필요한 D가 부족하면 의존 계산만 보류한다. 수집/계산에 LLM은 필요하지 않다.

## 3. 기존 D의 유지·통합과 기능 보존

**기존 기능 + 새로운 분석이 목표다. 기존 번호를 무조건 보존하지 않으며 같은 원본의 중복 조회는 통합한다.** 아래 통합은 저장소 기본 설정을 기준으로 한 구현 목표다. 기존 결과·발행 Runbook revision은 수정하지 않고, 새 revision의 실행 계획·정규화·소비자를 함께 전환한다.

| 기존 D | 현재 쿼리/입력 | 새 실행 설계 | 보존할 기능·소비자 전환 |
|---|---|---|---|
| D01 | DCGM_FI_DEV_GPU_UTIL | **D02로 통합** | 신원 labels·관측 장비 계산을 D02 결과에서 산출. O01/O02/O08의 기존 기능·출력 의미 유지 |
| D02 | DCGM_FI_DEV_GPU_UTIL | **유지: GPU 활동 원본 쿼리** | 활동값과 신원/작업 labels를 모두 보존. 활동·관측 신원·관측 연결은 서로 다른 코드 출력 |
| D03 | DCGM_FI_DEV_FB_USED | 유지 | 사용량 산식·출력 보존, D15/D16/D17 추가 |
| D04 | dcgm_fi_dev_gpu_temp (Fleet, builtin-v6) | **쿼리 유지, 의미를 GPU 온도로 정렬** | O01 온도 계산 보존. Host CPU는 별도 D18/D19. 과거 D04 결과 재해석 금지 |
| D05 | D09의 derived view | **D09 원문 + 기존 health parser 처리로 통합** | 상태 fact·producer/freshness 검증 유지. 새 Runbook은 D09와 요구 상태 fact를 참조. 기존 D05 evidence는 열람 가능 |
| D06 | kube_pod_info | 유지 | Pod UID·Node 관계와 시간 조인 유지 |
| D07 | gpu_ops_effective_unbound_request | 유지 | effective-v1 생산자·유효성 gate와 O07 출력 유지. 추가 D21 원시 요청을 D07 값으로 대체하지 않음 |
| D08 | DCGM_FI_DEV_GPU_UTIL, observed_pod_labels | **기본 관측 연결 조회를 D02로 통합** | D02 labels+D06 UID의 observed 모드로 기존 연결 계산 보존. 전용 할당 의미로 변경하지 않음 |
| D09 | Fleet component Loki 조회 | 유지 | 원문·대상·시간·producer와 상태 파서 입력 보존 |
| D10 | up | 유지 | 기존 수집 상태·품질 입력 유지, D22 추가 |
| D11 | dcgm_fi_dev_power_usage (Fleet, builtin-v6) | 유지 | 기존 W 적분 보존, D48/D49를 보조 출력으로 추가 |
| D12 | kube_node_status_allocatable | 유지, 의미를 Node allocatable로 명시 | resource별 기존 값/계획 유지. owner/제약까지 확보된 것으로 해석하지 않음 |
| D13 | 현재 Loki 조회 | **유지** | 기존 조회·근거·업무 영향 보류 유지. 구체 업무 필터를 확보하면 새 revision에서 보완; 원본이 같아 보여도 업무 의미 미확정 상태에서 D09와 합치지 않음 |
| D14 | 제품 DB context | 기존 DB 경로 유지 | Incident·공개 RCA·조치 참조 기능 유지. 독립 외부 D query로 만들지 않음 |

2026-10-02 현행 binding 보정: D04/D11은 실제 CPC-1/CPC-2의 10월 1일 기간에서 확인한 소문자 Fleet 이름과 `uuid`/`node` 필터를 사용한다. 단위·산식·최대 유지시간 30초는 유지하며, 표본 공백이나 Namespace 귀속을 보충하지 않는다. [범위·검수 한계와 배포 override](../../../agents/README.md#온도전력의-실제-저장-이름--2026-10-02)를 따른다. 이 보정은 아래 D 통합/신규 추가 설계의 구현 완료를 뜻하지 않는다.

### 통합에 반드시 포함할 구현 조건

- D01/D02/D08이 같은 metric 이름이라는 이유만으로 응답이 동등하다고 판단하지 않는다. datasource·필터·scope·기간·원본·단위·producer revision을 비교한다. 기본 설정에서 target_labels가 다르므로 각 소비자의 승인 대상 요구를 계획에 보존하고, 같은 인자인 호출만 재사용한다. D02라는 한 쿼리 정의도 다른 허용 인자/기간으로 여러 번 실행할 수 있다.
- D02 값 0은 활동 없음이지만 labels 기반 연결 근거로 사용할 수 있다. 신원 추출, 활동 시계열, observed 연결을 별도 함수로 처리한다. 할당용 0 해석이나 exclusive/mig mode를 D02에 자동 적용하지 않는다.
- 배포 override의 D08이 실제 할당 생산자를 가리키면 기본 설정과 다르다. 그 환경은 D08 계약을 유지하거나 별도 할당 D를 정의한 뒤 전환한다. 이 매핑으로 DCGM 관측에 덮어쓰지 않는다.
- D05의 parser binding·fact 적격성·freshness·source-position·근거 연결을 D09 처리에 이전한다. 누락된 freshness를 기본값으로 채워 상태를 승격하지 않는다. 필수 D05 검사도 원문 D09 + 필요한 fact 검사로 함께 바꾼다.
- 새 실행 계약에서만 통합한다. 과거 query_id·query_version·snapshot/hash·결과 표시와 기존 발행 revision은 보존한다. 번호만 일괄 치환하는 마이그레이션은 하지 않는다.

## 4. 신규 메트릭 → 신규 D 매핑

각 행은 독립 쿼리다. 결과 단위·타입의 ‘확인 필요’는 의도적인 미확정 상태이며 값 이름만으로 판정하지 않는다. 아래 RCA/O는 목표 활용처로서 소비 코드 구현 완료를 뜻하지 않는다.

| 신규 D | 정확한 원본 이름 | source·조건 | 반환 의미·단위/타입 확인 | 목적·활용 | 근거 수준 |
|---|---|---|---|---|---|
| D15 | DCGM_FI_DEV_FB_FREE | Exporter·G | 여유 메모리; MiB 여부 확인 | D03과 메모리 압박/점유 보조 계산, RCA·O01/O03 | CPC-2 과거 수집 |
| D16 | dcgm_fi_dev_fb_total | Fleet·G | 전체 FB 용량; 중앙 이름·용량 단위 확인 | D03/D15와 용량 대비 점유, RCA·O01 | Fleet 과거 표본 이름 |
| D17 | dcgm_fi_dev_fb_used_percent | Fleet·G | FB 점유율; 0~100 여부 확인 | 계산 점유율 교차 확인, RCA·O01 | Fleet 과거 표본 이름 |
| D18 | cpu_used_percent | Fleet·N | Host CPU 사용률; 범위·집계 확인 | 입력 공급/Host 제약 조사, RCA·O01/O04 | Fleet 과거 표본 이름 |
| D19 | cpu_load_average | Fleet·N | load; 1m/5m/15m labels별 값 | Host 부하 조사, RCA·O01/O04. percent 아님 | Fleet 과거 표본 이름 |
| D20 | kube_node_status_condition | KSM·N | condition/status별 info 값 | Node 상태·사건 맥락, RCA·O01/O06 | CPC-2 과거 수집 |
| D21 | kube_pod_container_resource_requests | KSM·P | container/resource/unit별 요청량 | 유효 요청 계산의 입력, O07 | CPC-2 과거 수집 |
| D22 | scrape_duration_seconds | scrape·T | 수집 소요시간, seconds | 수집 지연·공백 조사, D10과 O11 | CPC-2 과거 수집 |
| D23 | DCGM_FI_DEV_MEMORY_TEMP | Exporter·G | 메모리 온도; Celsius/오류값 확인 | 열 관련 RCA·O01/O05 | 소스/설정 후보 |
| D24 | DCGM_FI_DEV_SM_CLOCK | Exporter·G | SM clock; MHz 확인 | 활동·클록 제한 조사, RCA·O04 | 소스/설정 후보 |
| D25 | DCGM_FI_DEV_MEM_CLOCK | Exporter·G | memory clock; MHz 확인 | 메모리/클록 조사, RCA·O04 | 소스/설정 후보 |
| D26 | DCGM_FI_PROF_SM_ACTIVE | Exporter·G | SM 활동; ratio/정의/지원 확인 | 연산 활동 조사, RCA·O03/O04 | 소스/설정 후보 |
| D27 | DCGM_FI_PROF_SM_OCCUPANCY | Exporter·G | SM occupancy; ratio/정의 확인 | 활동과 점유 차이 조사, RCA·O04 | 소스/설정 후보 |
| D28 | DCGM_FI_PROF_PIPE_TENSOR_ACTIVE | Exporter·G | Tensor pipe 활동; ratio 확인 | 작업 연산 특성, RCA·O04 | 소스/설정 후보 |
| D29 | DCGM_FI_PROF_DRAM_ACTIVE | Exporter·G | DRAM 활동; ratio 확인 | 메모리 활동 조사, RCA·O04. 용량 아님 | 소스/설정 후보 |
| D30 | DCGM_FI_PROF_GR_ENGINE_ACTIVE | Exporter·G | engine 활동; ratio/관측 window 확인 | D02와 활동 의미 비교, RCA·O03/O04 | 소스/설정 후보 |
| D31 | DCGM_FI_PROF_PCIE_RX_BYTES | Exporter·G | PCIe 수신; 원본 rate/누적·시간 단위 확인 | 통신 관측, RCA·O04 | 소스/설정 후보 |
| D32 | DCGM_FI_PROF_PCIE_TX_BYTES | Exporter·G | PCIe 송신; 원본 rate/누적·시간 단위 확인 | 통신 관측, RCA·O04 | 소스/설정 후보 |
| D33 | dcgm_fi_prof_nvlink_rx_bytes | Fleet·G | NVLink 수신; rate/누적·시간 단위 확인 | GPU간 통신 조사, RCA·O04 | Fleet 소스 후보 |
| D34 | dcgm_fi_prof_nvlink_tx_bytes | Fleet·G | NVLink 송신; rate/누적·시간 단위 확인 | GPU간 통신 조사, RCA·O04 | Fleet 소스 후보 |
| D35 | DCGM_FI_DEV_XID_ERRORS | Exporter·G | XID 코드 관측; 발생 횟수 counter로 해석 금지 | D09 로그와 오류 조사, RCA·O05 | 소스/설정 후보 |
| D36 | dcgm_fi_dev_ecc_sbe_vol_dev | Fleet·G | SBE volatile device 값; 타입/reset 확인 | 메모리 오류 조사, RCA·O05 | Fleet 과거 표본 이름 |
| D37 | dcgm_fi_dev_ecc_sbe_vol_total | Fleet·G | SBE volatile total 값; 타입/reset 확인 | 메모리 오류 조사, RCA·O05 | Fleet 과거 표본 이름 |
| D38 | dcgm_fi_dev_ecc_sbe_agg_dev | Fleet·G | SBE aggregate device 값; 타입/reset 확인 | 누적 오류 맥락, RCA·O05 | Fleet 과거 표본 이름 |
| D39 | dcgm_fi_dev_ecc_sbe_agg_total | Fleet·G | SBE aggregate total 값; 타입/reset 확인 | 누적 오류 맥락, RCA·O05 | Fleet 과거 표본 이름 |
| D40 | dcgm_fi_dev_ecc_dbe_vol_dev | Fleet·G | DBE volatile device 값; 타입/reset 확인 | 메모리 오류 조사, RCA·O05 | Fleet 과거 표본 이름 |
| D41 | dcgm_fi_dev_ecc_dbe_vol_total | Fleet·G | DBE volatile total 값; 타입/reset 확인 | 메모리 오류 조사, RCA·O05 | Fleet 과거 표본 이름 |
| D42 | dcgm_fi_dev_ecc_dbe_agg_dev | Fleet·G | DBE aggregate device 값; 타입/reset 확인 | 누적 오류 맥락, RCA·O05 | Fleet 과거 표본 이름 |
| D43 | dcgm_fi_dev_ecc_dbe_agg_total | Fleet·G | DBE aggregate total 값; 타입/reset 확인 | 누적 오류 맥락, RCA·O05 | Fleet 과거 표본 이름 |
| D44 | DCGM_FI_DEV_PCIE_REPLAY_COUNTER | Exporter·G | replay 누적값; reset-aware 증가량 | PCIe 오류 조사, RCA·O05 | 소스/설정 후보 |
| D45 | dcgm_fi_dev_clocks_event_reasons | Fleet·G | clock event reason bitmask; 버전별 해석 확인 | D24/D25/전력·온도와 제한 조사, RCA | Fleet 과거 표본 이름 |
| D46 | dcgm_fi_dev_board_limit_violation | Fleet·G | board 제한 지표; 누적 시간/단위 확인 | 전력 제한 조사, RCA·O04 | Fleet 과거 표본 이름 |
| D47 | dcgm_fi_dev_fabric_manager_status | Fleet·G | 상태 enum; 코드표/대상 grain 확인 | fabric 상태 조사, RCA·O05 | Fleet 과거 표본 이름 |
| D48 | dcgm_fi_dev_enforced_power_limit | Fleet·G | 적용 전력 한도; W 확인 | D11 실제 소비와 비교, RCA·O09. 소비량 아님 | Fleet 과거 표본 이름 |
| D49 | DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION | Exporter·G | 누적 에너지; 단위/reset 확인 | D11 적분의 대안/교차 확인, O09/O10 | 소스/설정 후보 |

메모리/ECC의 device/total 또는 volatile/aggregate 값을 무조건 합산하지 않는다. 각각 의미가 다른 조회다. 같은 의미의 두 생산자나 D11 적분과 D49 누적 증가량도 소비량에 이중 합산하지 않는다.

## 5. Runbook·O가 여러 D를 사용하는 구체 예

| 분석 | 선택 D | 코드 처리·보류 조건 |
|---|---|---|
| 메모리 사용량 평균 | D03 | GPU별 유효시간 가중 평균 |
| 용량 대비 점유율 | D03 + D16 | 같은 GPU·겹치는 시간·호환 단위 확인 후 used/total. D16 실패 시 이 계산만 보류 |
| used+free 기반 점유율 | D03 + D15 | 합계가 전체 용량이라는 producer 계약이 확인된 경우에만 used/(used+free) |
| 메모리 문제 RCA | D03 + D15 + 관련 ECC D + D09 | 여유/오류/사건을 분리해 지지·반박. 낮은 여유만으로 원인 확정하지 않음 |
| GPU 활동 저하 조사 | D02 + D18/D19 + D26/D29 + 필요한 통신 D | 등록된 Runbook 질문에 맞춰 선택. 전체 D 일괄 수집하지 않음 |
| GPU–Pod 연결 | D02 labels + D06 | 기존 신원·유효시간 조인 기능 유지. 별도 전용 할당 근거 없이 할당량으로 승격하지 않음 |
| 전력·에너지 보고서 | 기존 D11,D10 + D22,D49 | 기존 W 적분 유지, 누적량 증가는 별도 교차 확인 출력. 단위/reset/유효시간 검증, 중복 합산 금지 |

현재 collected[D]의 단일 쿼리 구조는 유지한다. GPU 메모리라는 주제는 Runbook/O의 계획으로 D03·D15·D16을 선택한다. 반환값은 D 번호로 구분하므로 복수 metric 컨테이너나 중첩 item ID가 필요 없다. 필요한 변경은 신규 query 등록, D→fact/계산 연결, 조회 예산·소비자·표시·테스트이며 새 데이터베이스나 범용 쿼리 엔진을 전제로 하지 않는다.

## 6. O01~O11: 현재 D → 통합 후 D + 추가 D

현재 목록은 `ops-agent/src/ops_agent/workflow.py`의 PLAN/query_ids 기준이다. **‘통합 후 기본 D’로 기존 기능을 보존하고, ‘추가 D’로 새 결과를 만든다.** 신규 D의 실패가 기존 독립 결과를 지우지 않도록 출력별 필수 입력과 품질을 분리한다. 후보 source가 미검증이면 해당 추가 출력은 미지원/보류로 남긴다.

| O·목적 | 현재 D | 통합 후 기본 D | 추가 D·선택 조건 | 기존 결과 + 새 결과 |
|---|---|---|---|---|
| **O01 장비·자원 현황** | D01,D03,D04,D06 | **D02,D03,D04,D06** | 기본 추가 **D15,D16,D18,D19,D20**; 메모리 온도 상세 D23, 비율 교차 확인 D17 | 관측 GPU·VRAM·온도 유지 + 여유량·용량 대비 점유·Host CPU/load·Node 상태. 기본 변경 목록은 **D02,D03,D04,D06,D15,D16,D18,D19,D20** |
| **O02 연결·할당 시간** | D08,D01,D06,D10 | **D02,D06,D10** | **D22** 수집 지연 | D02 labels+D06으로 기존 관측 연결 기능 보존 + 수집 문제 설명. 실제 할당 producer가 따로 있으면 §3의 override 전환 적용. 할당 증거 없으면 기존 보류 유지 |
| **O03 저활동 조사** | D08,D06,D02,D10 | **D02,D06,D10** | **D03,D15** 메모리 보조; 저활동 구간이 확인되면 D18,D19,D26,D29 | 기존 저활동 판정/할당 gate 유지 + 같은 구간 메모리·Host·SM/DRAM 관측. DCGM 관측만으로 전용 할당 low_gpu_hours를 만들지 않음 |
| **O04 다중 GPU 편차** | D08,D06,D02 | **D02,D06** | **D03,D15** 메모리 보조; 관계·동시 구간 검증 후 편차가 있으면 D26,D27,D28,D29,D30; 통신 질문에 D31,D32,D33,D34; clock 질문에 D24,D25,D45,D46 | 기존 작업 내 활동 편차 유지 + 메모리·연산·통신·클록 비교. 기존 할당/공유 귀속 gate는 유지; 상관만으로 병목 확정 금지 |
| **O05 반복 사건** | D10 + DB 사건/RCA | **D10 + DB 사건/RCA** | **D09,D22**; 오류 종류에 맞는 D35,D36~D43,D44,D47; 열 사건 D04,D23 | 기존 사건 dedup·공개 RCA 인용 + 관련 로그·오류 변화·관측 품질. XID 값을 횟수로 세지 않음. 분모 없는 발생률·순위 보류 유지 |
| **O06 작업 영향** | D08,D06,D13 + DB 사건 | **D02,D06,D13 + DB 사건** | **D09,D20** | 기존 사건 당시 관계·업무 영향 보류 유지 + Node 상태·원문 사건 타임라인. D13 보존, 업무 성과 확보로 자동 승격하지 않음 |
| **O07 요청·배치 대기** | D07,D12 | **D07,D12** | **D06,D20,D21** | 기존 effective-v1 유효 요청/보류 + Container 원시 요청량·Node 상태·Pod 신원. D21 단순 합을 D07로 대체 금지. 부족량/원인은 scheduler 근거가 있어야 함 |
| **O08 Namespace 이용** | 기본 D08,D01,D06,D12; criteria 1.2 D01,D02,D06,D08 | **기본 D02,D06,D12; criteria 1.2 D02,D06** | **D10,D22**; 메모리 상세 D03,D15,D16 | 기존 두 profile의 관측 연결 기능·유효시간 산식/제외 사유 유지 + 수집 품질·연결 GPU 메모리 보조. 부서·공유 기여도·독점 할당 추정 금지 |
| **O09 전력·에너지** | D11,D10 | **D11,D10** | **D22**; 교차 확인 D49, 한도 비교 D48 | 기존 W 적분 kWh + 수집 지연·한도·누적 증가량 별도 비교. D49로 D11을 대체하거나 합산하지 않음 |
| **O10 조치 전후** | D11,D02,D13,D09 + DB 조치 | **D11,D02,D13,D09 + DB 조치** | **D10,D22**; 메모리 조치 D03,D15,D16; 열 D04,D23; Host D18,D19; clock D24,D25,D45; 에너지 교차 확인 D49 | 기존 실행 사실·전후 변화·인과 보류 + 조치 목적별 새 지표 비교. D13 유지, 업무량 없는 인과 확정 금지 |
| **O11 관측 품질** | D10 | **D10** | **D22 + 이미 수집한 모든 D의 quality** | 기존 수집시간/coverage 보류 + scrape 지연·표본 공백·신규 D별 미지원/충돌·영향 출력 표시. 모든 D 재조회 아님 |

추가 D에는 다른 O에서 이미 사용하던 D도 포함한다. 신규 쿼리 정의는 §4의 D15~D49 35개이며 활성 개수는 환경 검증 결과에 따른다. D36~D43은 8개 독립 쿼리로서 사건의 SBE/DBE·volatile/aggregate·device/total 질문에 맞춰 선택한다. 표의 조건부 조회는 등록 규칙·질문·가용성·예산으로 선택할 수 있으며 LLM이 필수는 아니다.

### O01의 입력 → 출력 계약

| 구분 | 출력 | 사용 D | 계산·실패 처리 |
|---|---|---|---|
| 기능 유지 | 기존 observed_devices | D01 대신 D02 labels | cluster+GPU UUID 중복 제거, 기존 관측 범위 의미 보존 |
| 기능 유지 | 기존 vram·temperature | D03,D04 | 기존 단위·산식·결과 이름 유지 |
| 기능 유지 | 기존 Pod 신원 근거 | D06 | 기존 수집/조인 계약 유지 |
| 추가 | gpu_memory_free_mean | D15 | 유효시간 가중 평균. D15 실패 시 이 출력만 null |
| 추가 | gpu_memory_used_ratio | D03,D16 | 같은 GPU·호환 시간/단위·total>0에서 계산. D16 실패 시 기존 vram은 유지 |
| 추가 | node_cpu_used_mean | D18 | Node별 검증된 CPU 사용률 평균 |
| 추가 | node_load_by_window | D19 | window별 분리. load를 percent로 변환하지 않음 |
| 추가 | node_condition_observations | D20 | condition/status별 시각·상태. GPU 정상으로 승격하지 않음 |
| 조건부 추가 | gpu_memory_temperature_mean | D23 | GPU 온도 D04와 별개 출력 |
| 조건부 추가 | gpu_memory_ratio_crosscheck | D03,D16,D17 | source·단위·시간 동등성이 확인된 구간만 비교 |

추가 출력 이름은 신규 결과 계약 제안이며 Backend/UI/HTML/CSV 소비까지 검증해야 한다. 기존 출력과 과거 결과를 보존한다. 기존 주제의 필수 D를 충족한 경우 신규 선택 D 실패만으로 기존 결과를 실패로 내리지 않는다. 새 결과/질문의 상태와 한계는 별도로 표시하며 전체 상태 집계 변경은 공통 결과 계약에 명시한다.

## 7. RCA Runbook의 통합·확장 매핑

현재 일반 템플릿 `rcca-agent/src/rcca_agent/general_runbook.json`은 필수 D09/D05, 선택 D02다. 새 일반 템플릿은 필수 D09 + 필요한 상태 fact, 선택 D02로 전환한다. **상태 확인 기능을 없애는 것이 아니라 D09 원문에서 기존 parser가 생산한 fact를 검사하는 것이다.** 과거 템플릿/발행본은 새 revision으로 덮어쓰지 않는다.

| Runbook 질문 | 현재 경로 | 새 기본/통합 입력 | 추가 D·목적 |
|---|---|---|---|
| 일반 장비 조사 | 일반 필수 D09,D05 / 선택 D02 | D09 + 상태/producer fact 검사, 선택 D02 | Node 질문 D20, 수집 품질 D10/D22 |
| 메모리 여유·오류 | 저장소 초안은 D09/D05 필수·D02 선택; D03 쿼리는 별도 존재 | D09 + 상태 fact, 질문에 D03 연결 | D15,D16, 해당 ECC D36~D43으로 여유·용량·오류 변화 보완 |
| 온도·클록·전력 제한 | 저장소 초안은 D09/D05 필수·D02 선택; D04/D11 쿼리는 별도 존재 | D09 + 상태 fact, 질문에 D04/D11 연결 | D23,D24,D25,D45,D46,D48로 열·클록·제한 사유·한도 조사 |
| PCIe·Fabric/NVLink | 기존 D09/D05 상태·원문 | D09 + 동일 조건의 상태 fact | D44,D47; 통신 질문 D31,D32,D33,D34. 트래픽을 오류로 해석하지 않음 |
| 사건 당시 GPU–Pod | D08+D06의 관계 처리 | 기본 설정은 D02 labels+D06의 observed 처리 | 필요 시 D20 Node 상태. 기존 UID·유효시간·공유/할당 구분 보존 |

저장소 초안 267개의 공통 조회 계획 전수 대조는 §7.2에 기록했다. 개별 조사 내용·조건·권고와 운영 발행본 revision의 전수 전환 검토는 남아 있다. 위 표는 실제 확인한 일반 템플릿/공통 처리와 새 질문별 계획이며 모든 발행본의 전수 전환 완료를 뜻하지 않는다. D→출력 fact 호환성 검사를 추가하고 수치 fact도 등록된 코드로 생산한다. 새 관측은 새 질문/판단을 보강하며, 기존 판정 gate를 임의로 완화하지 않는다.

### 7.1 XID/SXID 외의 사례에 D를 적용하는 방법

D는 오류 코드별 목록이 아니라 재사용 가능한 단일 관측 쿼리다. XID/SXID는 Runbook 검색·진입 단서 중 하나이며, 오류 코드가 없어도 증상·producer event·대상으로 조사 질문을 구성한다. 현재 search 스키마는 codes 외 producer_events/aliases/symptoms를 허용하지만, 이 사실만으로 비코드 사례의 실제 검색·판단 경로가 검수됐다고 볼 수 없다.

| 오류 코드 없는 사례·진입 단서 | 조사 질문 | 1차 D | 조건부 보완 D | 코드가 산출할 사실·미확보 근거 |
|---|---|---|---|---|
| 낮은 GPU 활동·처리 지연 | 연산·메모리·Host·통신 중 어떤 관측이 동반되는가 | D02,D03,D15,D10,D22 | Host D18/D19, 연산 D26/D29, 통신 D31~D34 | 유효 구간 활동/용량/통신 변화. 업무량·기대 성능/지연 source가 없으면 저활동 원인·성능 저하 자체의 정량 확정 보류 |
| 메모리 부족 의심 | 실제 용량 여유와 실패 사건이 함께 있는가 | D03,D15,D16,D09 | 관련 ECC D36~D43 | 용량 비율·오류 증가/사건. 할당 실패 원문·업무 메모리 요구가 없으면 OOM/누수 원인 확정 금지 |
| 고온·클록 하락 | 열·전력 제한 근거와 시간적으로 일치하는가 | D04,D23,D24,D25,D11 | D45,D46,D48,D09 | 온도/클록/전력/제한 상태의 동시 관측. 장비별 정책·지원 의미 검증 필요, 단일 임계값을 모든 모델에 적용하지 않음 |
| 작업 Pending·배치 지연 | 유효 요청과 배치 제약이 확인되는가 | D06,D07,D12,D20,D21 | 검증된 scheduler 사건의 신규 D는 미정 | 원시 요청/유효 요청 구분·Node 상태. init/sidecar/바인딩·scheduler source 부족이면 용량 부족 원인 보류 |
| Node 상태 이상 | 장비·Kubernetes·Host·수집 문제를 구분할 근거가 있는가 | D20,D18,D19,D09,D10,D22 | 대상에 맞는 GPU 오류/온도 D | condition·Host 부하·사건·수집 공백. 네트워크·runtime·storage 직접 근거가 없으면 해당 원인 미확정 |
| 데이터 공백·지표 소실 | target 수집 실패인가, 특정 장비 관측 부재인가 | D10,D22, 해당 대상의 D02/D06 | producer 로그 D09 | target 상태·표본 공백·신원 상태. 기대 inventory/주기 없으면 전체 coverage와 장비 장애를 확정하지 않음 |

위는 설계상 조사 계획이며 실제 비코드 Runbook은 아직 구현·발행하지 않았다. 기존 267개는 `investigation_only: true`인 조사 초안이다. D 추가만으로 원인 확정용 Runbook으로 승격하지 않으며, 원인 판정 범위를 넓히려면 별도로 fact·조건·충분성 검수를 완료해야 한다. 해당 질문에 대응하는 Runbook이 없으면 기존 일반 조사로 근거를 수집하고 미해결 질문을 남긴다. 신규 D 35개 추가만으로 network/storage/runtime/업무 성과 등 모든 사례를 커버한다고 주장하지 않는다. 재사용 가능한 D가 없을 때만 목적·원본·반환 사실을 정의해 독립 D를 추가하며 사례마다 같은 메트릭을 새 D로 복제하지 않는다.

현행 `runbook_contract.py`의 FACT_NAMES/SCALAR_FACTS는 제한된 상태·코드·producer 등이며 `_conditions()`는 등록된 scalar의 `field/equals`만 허용한다. 수치 시계열 비교·지속시간·부족량 계산을 문자열 fact나 임의 LLM 판정으로 우회하지 않는다. 비코드 Runbook 구현 전에 등록된 계산 함수가 생산할 typed fact/quality와 validator·판단 소비를 함께 정의한다. 원본 D→계산 fact→Runbook 적용/지지·반박→조건부 추가 D→종료/보류를 검수한다. 일반 조건 DSL을 먼저 만드는 대신 필요한 계산만 등록한다.

### 7.2 기존 Runbook 전수 조사 결과와 변경 계획

2026-10-02 저장소 `rcca-agent/runbooks/**/RB-*.json`을 파싱한 정적 대조:

| 항목 | 확인 결과 |
|---|---|
| 초안 수 | XID 173 + SXID 93 + 일반 1 = **267개** |
| required_queries | **267개 모두 D09,D05** |
| observation_plan | **267개 모두 D09 필수, D05 필수, D02 선택** |
| compatibility | **267개 모두 빈 객체**. DB 초안 등록용 작성 원본이며 실제 적용 조건은 검토·발행 전에 검증·입력 |
| 패키지 일반 템플릿 | `rcca-agent/src/rcca_agent/general_runbook.json`에도 D09/D05/D02 계획 존재, 함께 수정·동기화 필요 |

따라서 XID/SXID별 설명·문헌 내용이 있어도 현재 쿼리 선택은 동일하다. D 재설계가 코드별 조사 근거 확대에 연결되려면 단순 번호 치환과 별도로 코드/장비/producer별 관측 목적을 검토해야 한다. 운영 DB의 발행 Runbook 개수·revision은 이번에 조회하지 않았으므로 위 숫자를 운영 발행본 수로 사용하지 않는다.

| 변경 작업 | 실제 변경·검토 대상 | 완료 기준 |
|---|---|---|
| 공통 D05 통합 | 267개 초안의 required_queries/observation_plan + 패키지 일반 템플릿 | D09 항목을 한 개로 합치고 요구 fact·required 의미·purpose·priority를 보존. D09 중복 항목을 만들지 않음; 상태 fact gate 유지 |
| 추가 관측 선정 | 각 Runbook의 코드·조사 질문·장비/producer compatibility·출처 | 메모리/전력/PCIe/Fabric 등 해당 질문에 필요한 신규 D만 추가. 35개 일괄 추가 금지 |
| fact/조건/권고 점검 | required_evidence, fact_names, applicability_conditions, exclusion_conditions, recommendations.preconditions, analysis_guidance | 각 사실의 생산 D/parser/계산이 연결되고 기존 판단을 약화하지 않음. XID/SXID 코드만으로 원인 확정 금지 |
| 후속 조사 점검 | unexpected_evidence.additional_queries/fallback 및 예산/중단 | 구 D 참조 잔존·반복 조회·불가능한 fact 요구 없음. 추가 D 실패/미지원 시 보류 사유 보존 |
| source 파일/생성 경로 | Runbook JSON, 관련 생성·import/validator, 카탈로그·패키지 사본·테스트 | 재생성 시 이전 계획으로 되돌아가지 않음. 사본 동기화·문헌/코드별 내용 보존 |
| 발행본 전환 | Backend 지식 등록/검토/발행과 실제 DB revision 목록 | 별도 권한하에 새 revision 발행. 구 revision/hash는 보존, Worker 지원 profile과 순서 정합 |

파일별 전환 원장은 `knowledge_key / source_file / old_revision_or_hash / current_queries / new_queries / required_facts / parser_or_calculation / compatibility / expected_retained_behavior / added_question / fixture / review_status / publication_status`를 남긴다. 267개 구조 검사는 자동화할 수 있으나 내용 검토·운영 발행을 자동 완료로 표시하지 않는다.

검수는 (1) 모든 초안의 구조/참조/사본 검사, (2) 오류 종류별 대표 조사에서 기존 사실·판정과 추가 근거 비교, (3) 비코드 사례별 정상/이상/누락/상충 fixture, (4) 실제 producer·사건 표본의 검토로 나눈다. 지원하지 않는 사례는 일반 조사/미확정으로 종료해야 하며 LLM이 부족한 사실을 만들어서는 안 된다.

### 7.3 작성 원본에서 DB 등록·실행까지의 후속 작업

**저장소의 Runbook 초안은 나중에 DB에 등록할 작성 원본이다.** 참고 문서로만 남기는 것이 아니다. D 변경에 맞춰 이 원본과 생성 경로를 먼저 수정한 뒤, 기존 [DB 등록 절차](../../../rcca-agent/runbooks/DB-WORKFLOW.md)로 반영한다. 이번 PR은 이 절차의 설계만 남기며 JSON 수정·DB 등록·발행은 수행하지 않는다.

```text
D·메트릭·fact 계약 확정
→ 저장소 Runbook 초안·생성 경로·패키지 사본 수정
→ 구조·참조 검사 후 기존 Backend API로 DB draft 등록
→ 실제 query/parser/계산·compatibility 및 사례별 결과 검수
→ in_review → reviewed → published
→ JC가 실행에 고정한 revision/hash를 RCA Worker가 검증·소비
```

| 순서 | 작업·산출물 | 다음 단계로 넘길 조건 |
|---|---|---|
| 1. 작성 계약 | 각 Runbook의 질문, 기존→신규 D, 필수/선택 입력, 생산 fact·계산, 조건·한계 정의 | §7.2 원장을 파일별로 작성. 공통 치환과 개별 의미 검토를 구분 |
| 2. 원본 수정 | 기존 코드별 지침·문헌·knowledge_key 보존, D05 통합, 목적별 D 추가; 비코드 사례는 필요한 새 Runbook 작성 | 생성 경로·일반 패키지 사본 동기화. 기존 조사 기능·불충분 판정 유지 |
| 3. DB 초안 등록 | 기존 `runbook_import`/관리 CLI → Backend API → `knowledge_revisions` draft | 입력·profile 구조 검사. 기존 knowledge_key는 대상 DB의 knowledge_id에 연결해 새 revision 생성; 등록 receipt 보관 |
| 4. 검토 준비 | 실제 source binding·장비/producer compatibility, typed fact·계산·조건·예산·실패 처리 검수 | Python 및 영향받는 Backend 검증기가 같은 계약을 지원. 신규 D와 parser/계산이 실행 profile/Worker에 준비됨 |
| 5. 검토·발행 | 기존 draft → in_review → reviewed → published 전이 | 대상·본문 hash·검수 근거 확인. 비어 있는 compatibility나 지원되지 않는 실행 입력으로 발행하지 않음 |
| 6. 실행·회수 검수 | JC의 revision/hash 고정, RCA 계획·근거·결과, Ops의 공개 RCA 참조 확인 | 신규 실패/누락·과거 결과 열람 보존. 문제 revision은 기존 retire 절차로 신규 선택에서 제외하고 수정 revision을 검토 |

DB draft 등록과 운영 발행은 별도 단계다. 빈 compatibility는 작성 중 의도된 상태일 수 있고 초안으로 저장할 수 있지만, 운영 적용 가능성을 뜻하지 않는다. 저장소 JSON을 수정하거나 Helm을 갱신해도 DB의 발행 콘텐츠는 자동으로 바뀌지 않는다. Worker는 작성 폴더를 실행 원본으로 읽지 않는다. 패키지 일반 Runbook 사본도 동기화하되 DB 발행 절차를 대체하지 않는다.

원장에는 §7.2 항목과 함께 `target_environment / knowledge_id / draft_revision_id / content_hash / import_receipt / execution_profile_revision / validation_evidence`를 남긴다. 새 내용에는 새 batch key/receipt를 사용하며 동일 요청 재시도는 기존 등록 절차의 멱등 규칙을 따른다. DB 내용 적재에 새 테이블·직접 SQL·자동 seed를 추가하지 않는다. 기존 published revision과 실행 중 claim, 과거 evidence/result/hash는 그대로 보존한다. 실제 DB 반영 때 대상 환경·적용 순서·회수 조건을 확인한다.

## 8. 원본 미확정 요구와 제외

| 정보 | 처분·이유 |
|---|---|
| 전용/공유/MIG 할당, owner chain, init/sidecar/overhead, quota/affinity/gates | 필요하지만 구체 실행 원본·계약 미확정. D 번호를 실행 항목처럼 배정하지 않고 데이터 원장에서 보완 |
| 업무 처리량·진행률·지연, scheduler/작업 로그 | 실제 producer/stream/필드 미확정. D13이 이를 제공한다고 표시하지 않음 |
| 부서 | 이번 범위 제외 |
| 아래 GPU 카탈로그의 나머지 항목 | 누락하지 않고 보류 목록에 기록. 실제 지원·구체 질문·해석 계약 확인 후 독립 D 추가 |

## 9. 기존 GPU 대조표 전체 항목의 처분

다음 표는 기존 GPU 대조표에 있는 모든 식별자를 대조한 것이다. 대문자 식별자는 원천 대조 키이며 실행 이름은 §4를 따른다. 이 표의 소문자 대응은 기존 대조표의 Fleet 소스 명명 설명을 사용한 추적이며, 실제 중앙 binding 검증을 대체하지 않는다. 번호가 없는 항목은 이번 1차 구현 대상에서 보류하고 이유를 기록한다. 따라서 ‘전체 매핑 완료’는 아래 대조표의 행별 처분 완료를 뜻하며, 모든 운영 메트릭의 D 등록 완료가 아니다.

| 대조 식별자 | D/처분 | 설명 |
|---|---|---|
| DCGM_EXP_CLOCK_EVENTS_COUNT | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_EXP_GPU_HEALTH_STATUS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_EXP_P2P_STATUS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_EXP_XID_ERRORS_COUNT | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_BANKS_REMAP_ROWS_AVAIL_HIGH | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_BANKS_REMAP_ROWS_AVAIL_LOW | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_BANKS_REMAP_ROWS_AVAIL_MAX | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_BANKS_REMAP_ROWS_AVAIL_NONE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_BANKS_REMAP_ROWS_AVAIL_PARTIAL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_BOARD_LIMIT_VIOLATION | D46 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_BRAND | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_C2C_LINK_ERROR_REPLAY | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_CLOCKS_EVENT_REASONS | D45 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_CPU_POWER_LIMIT | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_CPU_POWER_UTIL_CURRENT | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_CPU_TEMP_CRITICAL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_CPU_TEMP_CURRENT | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_CPU_TEMP_WARNING | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_DEC_UTIL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_ECC_DBE_AGG_DEV | D42 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_ECC_DBE_AGG_TOTAL | D43 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_ECC_DBE_VOL_DEV | D40 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_ECC_DBE_VOL_TOTAL | D41 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_ECC_INFOROM_VER | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_ECC_SBE_AGG_DEV | D38 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_ECC_SBE_AGG_TOTAL | D39 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_ECC_SBE_VOL_DEV | D36 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_ECC_SBE_VOL_TOTAL | D37 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_ENC_UTIL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_ENFORCED_POWER_LIMIT | D48 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_FABRIC_MANAGER_STATUS | D47 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_FB_FREE | D15 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_FB_RESERVED | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_FB_TOTAL | D16 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_FB_USED | D03 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_FB_USED_PERCENT | D17 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_GPU_TEMP | D04 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_GPU_TEMP_LIMIT | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_GPU_UTIL | D02 (기존 D01/D08 통합) | 기본 GPU_UTIL 쿼리 기준. 별도 할당 source override는 §3의 보존 조건 적용 |
| DCGM_FI_DEV_INFOROM_CONFIG_VALID | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_INFOROM_IMAGE_VER | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_LOW_UTIL_VIOLATION | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_MEM_CLOCK | D25 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_MEM_COPY_UTIL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_MEMORY_TEMP | D23 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_NVLINK_BANDWIDTH_L0 | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_EFFECTIVE_BER_FLOAT | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_EFFECTIVE_ERRORS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_LINK_RECOVERY_FAILED_EVENTS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_LINK_RECOVERY_SUCCESSFUL_EVENTS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_LOCAL_LINK_INTEGRITY_ERRORS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_RX_BUFFER_OVERRUN_ERRORS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_RX_ERRORS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_RX_GENERAL_ERRORS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_RX_MALFORMED_PACKET_ERRORS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_RX_REMOTE_ERRORS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_RX_SYMBOL_ERRORS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_SYMBOL_BER_FLOAT | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_COUNT_TX_DISCARDS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_CRC_DATA_ERROR_COUNT_TOTAL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_ERROR_DL_CRC | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_ERROR_DL_RECOVERY | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_ERROR_DL_REPLAY | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_RECOVERY_ERROR_COUNT_TOTAL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_NVLINK_REPLAY_ERROR_COUNT_TOTAL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_OEM_INFOROM_VER | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_PCIE_REPLAY_COUNTER | D44 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_POWER_INFOROM_VER | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_POWER_USAGE | D11 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_POWER_VIOLATION | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_RELIABILITY_VIOLATION | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_RETIRED_DBE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_RETIRED_PENDING | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_RETIRED_SBE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_ROW_REMAP_FAILURE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_ROW_REMAP_PENDING | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_SERIAL | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_SLOWDOWN_TEMP | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_SM_CLOCK | D24 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_SYNC_BOOST_VIOLATION | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_THERMAL_VIOLATION | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION | D49 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_VBIOS_VERSION | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_VGPU_LICENSE_STATUS | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_DEV_XID_ERRORS | D35 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_DRIVER_VERSION | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_NVML_VERSION | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_PROF_DRAM_ACTIVE | D29 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_PROF_GR_ENGINE_ACTIVE | D30 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_PROF_NVLINK_RX_BYTES | D33 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_PROF_NVLINK_TX_BYTES | D34 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_PROF_PCIE_RX_BYTES | D31 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_PROF_PCIE_TX_BYTES | D32 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_PROF_PIPE_FP16_ACTIVE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_PROF_PIPE_FP32_ACTIVE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_PROF_PIPE_FP64_ACTIVE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_PROF_PIPE_INT_ACTIVE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_PROF_PIPE_TENSOR_ACTIVE | D28 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_PROF_PIPE_TENSOR_DFMA_ACTIVE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_PROF_PIPE_TENSOR_HMMA_ACTIVE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_PROF_PIPE_TENSOR_IMMA_ACTIVE | 보류 | 1차 선택 밖. 생산자/장비 지원·조회 목적·단위/해석 계약 확인 후 별도 D 배정 |
| DCGM_FI_PROF_SM_ACTIVE | D26 | 실행 source·이름·가용성은 위 매핑 표 참조 |
| DCGM_FI_PROF_SM_OCCUPANCY | D27 | 실행 source·이름·가용성은 위 매핑 표 참조 |

이 매핑 초안은 문서 변경만이다. 신규 D 등록·Runbook/O 전환·운영 조회는 수행하지 않았다. 후속 단계와 검수는 [개발 계획](d-contract-redesign-plan.md)을 따른다.
