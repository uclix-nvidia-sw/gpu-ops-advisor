# GPU 노드 RCA 장애 Domain·Category·메트릭 매핑

검토 기준일: 2026-09-22

상태: 런북 작성용 참고 자료 초안 — 소스 코드 정적 대조 완료, CPC-1·CPC-2 운영 데이터 검증 미완료

## 1. 목적

이 문서는 GPU 노드 RCA Agent용 런북을 작성할 때, 검색된 런북 후보의 적용 가능성을 확인하기 위해 어떤 데이터를 어떤 순서로 관측할지 정리한 참고 자료다. Agent는 먼저 알림·로그·정규화된 fact로 런북 후보를 검색하고, 이 문서의 Domain·Category 매핑으로 추가 관측 범위를 좁힌다. 범위는 Kubernetes 스케줄링 원인 분석을 제외한 GPU 노드이며, 주요 수집원은 Fleet Intelligence, GPU Operator의 `nvidia-dcgm-exporter`, Mimir, Loki다.

현재 분류는 **9개 Domain, 31개 Category**다. 31이라는 숫자는 공식 표준이나 고정 상한이 아니다. 서로 다른 우선 관측값과 조사 절차가 필요한 운영 단위를 초기 Category로 나눈 결과다.

이 문서의 표는 바로 실행할 수 있는 런북이나 확정된 Knowledge DB seed가 아니다. 메트릭·이벤트·로그 후보와 조사 순서를 제공하며, 실제 런북으로 승격하려면 배포 환경에서 데이터 존재 여부, label·unit·type, 조회 시간 범위, query ID, 판단 조건을 검증해야 한다.

## 2. 메트릭 이름을 읽는 방법

- 소문자 `dcgm_fi_*`는 Fleet Intelligence naming이다. 표에서 별도 주의 문구가 없는 이름은 제공된 CPC-1 Mimir catalog에 있으며, `후보`로 표시한 이름은 참고 소스에는 있지만 CPC-1 실노출이 확인되지 않은 것이다.
- 대문자 `DCGM_FI_*`는 `nvidia-dcgm-exporter`의 대응 DCGM field 이름이다. 기본 CSV에서 활성·주석·미포함 여부가 서로 다르므로 실제 Mimir 노출 여부를 별도로 검증해야 한다.
- Fleet와 Exporter가 같은 DCGM Field ID를 읽는 쌍은 하나의 canonical metric으로 연결할 수 있다. 다만 source별 시계열은 유지하고 합산하지 않는다. `producer_contract`와 `metric_definition`에 source, unit, type, label mapping을 따로 등록한 뒤 우선 source와 failover source를 정한다.
- `counter`는 현재 누적값보다 사건 전후의 reset-aware 증가량을 우선한다. `gauge`는 시점 값과 지속시간을 함께 본다.
- “직접 메트릭 없음”은 조사할 수 없다는 뜻이 아니다. 현재 Agent에 연결된 Mimir·Loki 조회와 정규화된 fact를 우선 사용한다. Fleet `/v1/states`, `/v1/events`, `/machine-info`는 원천 후보이며, Agent가 직접 조회한다고 가정하지 말고 producer 계약과 수집 파이프라인 연결이 확인된 경우에만 런북 입력으로 사용한다.
- 아래 이름은 catalog·참고 소스 기준이다. 운영 적용 전 `cluster_id`, `machine_id`, `node`, `uuid`/`UUID`, `pci_bus_id`, `model_name` label과 단위·TYPE·수집 주기를 실환경에서 확정해야 한다.

문서에서 사용하는 검증 상태는 다음과 같다.

| 상태 | 의미 |
|---|---|
| `source-verified` | 소스 코드나 공식 문서에서 정의·의미를 확인함 |
| `observed` | 지정 CPC의 Mimir/Loki/Fleet 출력에서 실제 표본을 확인함 |
| `runbook-validated` | 승인된 query와 판정 조건으로 재현하거나 운영 사례에서 검토함 |
| `candidate` | 참고할 후보이며 실제 노출·지원·판정 조건이 아직 확인되지 않음 |

### 2.1 대소문자만 다른 메트릭의 소스 코드 검증 결과

**결론: 대표적인 동일 이름 쌍은 같은 DCGM Field ID의 값을 읽으므로 의미상 같은 원천 데이터다.** Fleet Intelligence는 같은 상수를 조회한 뒤 metric 이름을 소문자로 등록하고, DCGM Exporter는 CSV의 대문자 field 이름을 Prometheus metric 이름으로 사용한다.

검증 대상은 Fleet Intelligence Agent commit `8dd8826b7604386ad667125298156ddb1d1a7865`와 DCGM Exporter tag `4.4.2-4.7.0`이다.

| Fleet metric | DCGM Exporter metric | 소스 코드 판정 | 값 처리 |
|---|---|---|---|
| `dcgm_fi_dev_gpu_temp` | `DCGM_FI_DEV_GPU_TEMP` | 둘 다 `DCGM_FI_DEV_GPU_TEMP` Field ID | Fleet는 `Int64()`를 gauge에 설정하고 Exporter도 같은 DCGM 값 출력. 섭씨 |
| `dcgm_fi_dev_memory_temp` | `DCGM_FI_DEV_MEMORY_TEMP` | 같은 Field ID | 같은 원천 온도 값. 섭씨 |
| `dcgm_fi_dev_power_usage` | `DCGM_FI_DEV_POWER_USAGE` | 같은 Field ID | Fleet는 `Float64()`를 gauge에 설정하고 Exporter도 같은 DCGM 값 출력. watt |
| `dcgm_fi_dev_gpu_util` | `DCGM_FI_DEV_GPU_UTIL` | 같은 Field ID | 같은 원천 utilization 값. 수집 window 차이는 가능 |
| `dcgm_fi_dev_sm_clock` | `DCGM_FI_DEV_SM_CLOCK` | 같은 Field ID | 같은 원천 clock 값. MHz |
| `dcgm_fi_dev_fb_free` | `DCGM_FI_DEV_FB_FREE` | 같은 Field ID | 같은 원천 framebuffer 값. MB/MiB 표기 차이는 contract에서 확인 필요 |
| `dcgm_fi_dev_fb_used` | `DCGM_FI_DEV_FB_USED` | 같은 Field ID | 같은 원천 framebuffer 값 |
| `dcgm_fi_dev_pcie_replay_counter` | `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` | 둘 다 `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` Field ID | Fleet는 `Int64()`를 counter에 설정하고 Exporter도 같은 누적값 출력 |
| `dcgm_fi_dev_ecc_dbe_vol_total` | `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` | 같은 Field ID | 같은 원천 ECC counter. Exporter 기본 CSV에서는 주석 상태라 별도 활성화 필요 |
| `dcgm_fi_dev_thermal_violation` | `DCGM_FI_DEV_THERMAL_VIOLATION` | 같은 Field ID | 같은 원시 누적값. Exporter 기본 CSV에서는 주석 상태 |

전체 정적 대조 결과는 다음과 같다.

- Fleet DCGM component가 참조하는 고유 Field: **78개**
- DCGM Exporter 기본 CSV 활성 Field 중 Fleet와 겹치는 Field: **19개**
- 기본 CSV 주석 선택 항목 중 Fleet와 추가로 겹치는 Field: **13개**
- 따라서 제공 버전의 CSV 기준으로 직접 대응 가능한 고유 Field는 **32개**다.
- 나머지는 Fleet에만 있거나 해당 Exporter 기본 CSV에 없는 Field이므로 이름 변환만으로 대응시키면 안 된다.

여기서 “같은 원천 데이터”와 “Mimir에서 숫자가 항상 완전히 동일함”은 구분해야 한다.

| 비교 항목 | 확인 결과 |
|---|---|
| DCGM Field 의미 | 동일 이름 쌍은 동일 Field ID를 사용하므로 일치 |
| 기본 단위 | 원칙적으로 동일 Field 정의를 따름. HELP 문구가 다른 항목은 공식 DCGM Field 정의를 우선 |
| metric type | 대표 쌍은 대체로 gauge/counter가 일치하지만 CSV와 Fleet 선언을 개별 비교해야 함 |
| sample timestamp | 두 process의 polling·scrape 주기가 달라질 수 있어 불일치 가능 |
| label | Fleet는 `uuid`, `gpu`, `component` 중심이고 Exporter는 `UUID`, `gpu`, `pci_bus_id`, `modelName` 및 Kubernetes label 등을 사용할 수 있어 다름 |
| unsupported/sentinel 처리 | collector 구현과 버전에 따라 누락 처리 시점이 달라질 수 있음 |
| 실제 CPC 값 일치 | 아직 미검증. 제공 자료에서 Fleet 표본은 있으나 로컬 Prometheus의 `DCGM_FI_DEV_GPU_UTIL` 조회는 0건이어서 동일 GPU·동일 시간 비교 표본이 없음 |

따라서 Knowledge DB에는 두 이름을 다음처럼 등록하는 것이 적합하다.

```text
canonical_metric: gpu.temperature.celsius
  ├─ fleet-intelligence / dcgm_fi_dev_gpu_temp / labels: uuid,gpu,component
  └─ dcgm-exporter     / DCGM_FI_DEV_GPU_TEMP / labels: UUID,gpu,pci_bus_id,...

equivalence_basis: same_dcgm_field_id
equivalence_status: source_verified
runtime_value_validation: pending
merge_policy: prefer_primary_then_failover
aggregation_policy: never_sum_across_producers
```

즉, 두 metric은 별개의 장애 증거로 중복 가산하지 않는다. 동일 GPU와 시간 범위를 정규화한 뒤 primary source를 사용하고, 다른 source는 교차 확인 또는 결측 시 failover로 사용한다.

## 3. Domain 요약

| Domain | 포함 범위 | Domain 공통 대표 우선 데이터 |
|---|---|---|
| `COLLECTION` | Agent 생존, 수집 지연, 기대 장치 대비 누락 | `fleetint_agent_up`, `fleetint_agent_collection_summary`, 마지막 sample 시각, `/machine-info` |
| `GPU_DEVICE` | GPU 접근 불가, 미탐지, reset 필요 상태 | Fleet state/event, Xid, GPU UUID·PCI BDF, `dcgm_fi_dev_pcie_replay_counter` |
| `GPU_MEMORY` | ECC, row remap, page retirement | ECC 증가량, remap 상태, Xid, GPU architecture |
| `GPU_THERMAL_POWER` | 온도, thermal/power 제한, clock throttle | 온도, violation counter, power limit, clock reason·clock |
| `GPU_INTERCONNECT` | PCIe, NVLink, SXid/NVSwitch, Fabric Manager | error counter 증가량, Xid/SXid, FM state, topology |
| `DRIVER_CUDA_RUNTIME` | Driver, NVML, CUDA runtime, version 조합 | Fleet state/event, version inventory, kernel·driver·runtime 로그 |
| `NODE_SYSTEM` | CPU, host memory, disk, OS 자원 | Fleet host metric, uptime, OOM·I/O·OS 로그 |
| `NETWORK_IB` | Ethernet, InfiniBand, RDMA/RoCE | link/error/drop metric, Fleet event, IB/RDMA 도구 결과 |
| `CONTAINER_RUNTIME` | Node의 container runtime과 GPU device 노출 | Fleet state/event, runtime·NVIDIA runtime 로그, device node |

## 4. Category별 대표 우선 데이터와 메트릭

### 4.1 `COLLECTION`

| Category | 포함 내용 | 대표 우선 데이터 | 매핑 메트릭 | 보조 증거와 판정 주의 |
|---|---|---|---|---|
| `COLLECTOR_UNAVAILABLE` | Fleet Agent 정지, scrape 실패, exporter endpoint 불가 | Agent 생존 여부 → collection summary → scrape 경로 | `fleetint_agent_up`, `fleetint_agent_uptime_seconds`, `fleetint_agent_collection_summary`; scrape job이 존재할 때만 Prometheus `up` | Fleet `/v1/states`, service/process 로그. `up=0`의 대상 job과 tenant를 확인한다. |
| `DATA_STALE` | Agent는 보이지만 metric/event 갱신이 늦거나 중단 | 원천 관측 시각·scrape 시각·저장소 ingest 시각과 허용 freshness | 전용 장애 metric 없음. `timestamp(fleetint_agent_collection_summary)` 및 Category 대표 metric의 마지막 sample 시각 | `timestamp(...)`만으로 원천 이벤트의 최신성을 확정하지 않는다. 수집 주기와 ingest 지연을 확인하고 Fleet event의 원천 시각과 Loki ingest 시각을 구분한다. |
| `DEVICE_MISSING` | 기대 GPU 수·UUID 대비 시계열 또는 machine inventory 누락 | collector 정상 확인 → `/machine-info` 기대 inventory → UUID별 마지막 관측 | 존재성 기준 후보: `dcgm_fi_dev_gpu_util`, `dcgm_fi_dev_gpu_temp`, `dcgm_fi_dev_fb_total`; Exporter 후보 `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_GPU_TEMP` | 단일 metric 부재로 장치 고장을 확정하지 않는다. `target_info`, `fleetint_gpu_firmware_info`, GPU UUID·PCI BDF를 교차 확인한다. |

### 4.2 `GPU_DEVICE`

| Category | 포함 내용 | 대표 우선 데이터 | 매핑 메트릭 | 보조 증거와 판정 주의 |
|---|---|---|---|---|
| `GPU_ACCESS_LOST` | Xid 79, fallen off bus, NVML에서 GPU 접근 실패 | Xid 원문 → GPU UUID/PCI BDF → 장치 마지막 관측 → PCIe 오류 | `dcgm_fi_dev_pcie_replay_counter`, `dcgm_fi_dev_gpu_util`; Xid metric 후보 `DCGM_FI_DEV_XID_ERRORS` 또는 `DCGM_EXP_XID_ERRORS_COUNT`는 exporter 설정과 Mimir 노출 확인 후 사용 | Fleet state/event와 Loki의 NVRM Xid·PCIe/AER 로그가 핵심이다. 수집기 장애와 먼저 분리한다. |
| `GPU_NOT_DETECTED` | 부팅·재탐색 후 특정 GPU가 inventory에 없음 | 기대 inventory와 `/machine-info` 비교 → UUID series cardinality | `fleetint_agent_collection_summary`, `target_info`; 존재성 후보 `dcgm_fi_dev_fb_total`, `dcgm_fi_dev_gpu_temp` | `gpu="0"` ordinal을 전역 식별자로 쓰지 않는다. UUID·serial·PCI BDF를 사용한다. |
| `GPU_RESET_REQUIRED` | 원천 action 또는 공식 절차가 GPU reset이나 시스템 reboot 검토를 요구함 | Fleet current state의 suggested/repair action → 관련 Xid/SXid → 장비·토폴로지별 전제 | 직접 확정 metric 없음. 보조 `dcgm_fi_dev_fabric_manager_status`, `dcgm_fi_dev_pcie_replay_counter`; Xid metric은 실노출 확인 후 사용 | `REBOOT_SYSTEM`을 GPU reset 또는 복구 불가 하드웨어 장애와 동일시하지 않는다. Agent는 전제와 권고를 제시하며 reset·reboot는 사람이 승인·실행한다. |

### 4.3 `GPU_MEMORY`

| Category | 포함 내용 | 대표 우선 데이터 | 매핑 메트릭 | 보조 증거와 판정 주의 |
|---|---|---|---|---|
| `ECC_DBE` | volatile·aggregate double-bit ECC, 관련 Xid | 사고 전후 DBE 증가량 → device-memory 영역 상세 → GPU UUID·PCI BDF → Xid 시간 순서 | `dcgm_fi_dev_ecc_dbe_vol_total`, `dcgm_fi_dev_ecc_dbe_vol_dev`, `dcgm_fi_dev_ecc_dbe_agg_total`, `dcgm_fi_dev_ecc_dbe_agg_dev`; 대응 Exporter `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL`, `..._VOL_DEV`, `..._AGG_TOTAL`, `..._AGG_DEV` | DCGM field의 `_DEV`는 device memory 영역을 뜻하며 GPU 식별 label을 뜻하지 않는다. GPU는 UUID·PCI BDF로 식별한다. 과거 누적값만으로 새 장애를 만들지 않고 counter reset을 처리한다. |
| `ECC_SBE` | 반복 single-bit ECC와 증가 추세 | volatile SBE 증가율 → aggregate·device-memory 영역 → GPU UUID·PCI BDF → 동반 Xid/DBE | `dcgm_fi_dev_ecc_sbe_vol_total`, `dcgm_fi_dev_ecc_sbe_vol_dev`, `dcgm_fi_dev_ecc_sbe_agg_total`, `dcgm_fi_dev_ecc_sbe_agg_dev`; 대응 Exporter `DCGM_FI_DEV_ECC_SBE_*` | `_DEV`를 GPU별 식별자로 해석하지 않는다. 단발 SBE를 일괄 reboot로 연결하지 않고 반복률과 DBE·remap 동반 여부를 본다. |
| `ROW_REMAP` | 지원 GPU의 row remap pending/failure, remap 여유 소진 | failure/pending → uncorrectable/correctable remapped rows → bank 여유 | `dcgm_fi_dev_row_remap_failure`, `dcgm_fi_dev_row_remap_pending`, `dcgm_fi_dev_uncorrectable_remapped_rows`, `dcgm_fi_dev_correctable_remapped_rows`, `dcgm_fi_dev_banks_remap_rows_avail_{high,low,max,none,partial}`; 대응 Exporter 필드는 설정별 확인 | 이번 대상 A100에서 capability가 확인된 경우에 적용한다. 다른 모델은 지원 여부를 별도로 검증하고 상태성 값과 누적 counter를 구분한다. |
| `PAGE_RETIREMENT` | V100 계열 retired SBE/DBE page와 pending retirement | GPU architecture → retired page/pending → ECC·Xid | Fleet CPC-1 catalog에는 직접 이름 미확인. Exporter 선택 항목 후보 `DCGM_FI_DEV_RETIRED_SBE`, `DCGM_FI_DEV_RETIRED_DBE`, `DCGM_FI_DEV_RETIRED_PENDING` | 현재 exporter 기본 설정에서는 주석 항목일 수 있다. 수집하지 않으면 검토된 `nvidia-smi -q` 결과나 Fleet event가 필요하다. Row remap으로 대체하지 않는다. |

### 4.4 `GPU_THERMAL_POWER`

| Category | 포함 내용 | 대표 우선 데이터 | 매핑 메트릭 | 보조 증거와 판정 주의 |
|---|---|---|---|---|
| `OVER_TEMPERATURE` | GPU·HBM 온도 상승, 장비 한계 접근 | 현재 GPU/memory 온도 → slowdown/limit 기준 → 지속시간 | `dcgm_fi_dev_gpu_temp`, `dcgm_fi_dev_memory_temp`, `dcgm_fi_dev_slowdown_temp`; 대응 Exporter `DCGM_FI_DEV_GPU_TEMP`, `DCGM_FI_DEV_MEMORY_TEMP` | 장비별 기준을 사용한다. 모든 GPU에 동일한 고정 온도를 적용하지 않는다. |
| `THERMAL_THROTTLE` | 온도로 인한 실제 clock 제한 | thermal violation 증가 → clock reason → 온도와 clock | `dcgm_fi_dev_thermal_violation`, `dcgm_fi_dev_clocks_event_reasons`, `dcgm_fi_dev_gpu_temp`, `dcgm_fi_dev_sm_clock`, `dcgm_fi_dev_mem_clock`; 대응 Exporter 필드 활성 여부 확인 | `*_violation`의 단위와 clocks reason bitmask decoder version이 필요하다. |
| `POWER_LIMIT` | 설정 power cap 도달, power violation, 공급·board 제한 | usage와 enforced limit → power/board/reliability violation → clock | `dcgm_fi_dev_power_usage`, `dcgm_fi_dev_enforced_power_limit`, `dcgm_fi_dev_power_violation`, `dcgm_fi_dev_board_limit_violation`, `dcgm_fi_dev_reliability_violation`; 대응 Exporter `DCGM_FI_DEV_POWER_USAGE` 등 | cap 도달은 정상 정책일 수 있다. 성능 저하나 오류와 함께 판정한다. |
| `CLOCK_THROTTLE` | SM/memory clock 저하와 throttle reason | clock reason → SM/MEM clock → util·temperature·power | `dcgm_fi_dev_clocks_event_reasons`, `dcgm_fi_dev_sm_clock`, `dcgm_fi_dev_mem_clock`, `dcgm_fi_dev_gpu_util`, `dcgm_fi_dev_mem_copy_util` | idle 또는 workload 특성으로 낮은 clock일 수 있다. reason과 지속시간을 필수로 본다. |

### 4.5 `GPU_INTERCONNECT`

| Category | 포함 내용 | 대표 우선 데이터 | 매핑 메트릭 | 보조 증거와 판정 주의 |
|---|---|---|---|---|
| `PCIE_ERROR` | PCIe replay 증가, AER, PCIe 전송 이상 | replay 증가량 → PCIe RX/TX 활동 → AER/Xid와 BDF | `dcgm_fi_dev_pcie_replay_counter`, `dcgm_fi_prof_pcie_rx_bytes`, `dcgm_fi_prof_pcie_tx_bytes`; 대응 Exporter `DCGM_FI_DEV_PCIE_REPLAY_COUNTER`, `DCGM_FI_PROF_PCIE_RX_BYTES`, `DCGM_FI_PROF_PCIE_TX_BYTES` | counter 누적값보다 사건 전후 증가를 본다. BDF가 같은 GPU인지 확인한다. |
| `NVLINK_ERROR` | NVLink CRC/replay/recovery 오류와 대역폭 저하 | error counter 증가 → bandwidth/RX/TX → Xid 74와 link topology | `dcgm_fi_dev_nvlink_error_dl_crc`, `dcgm_fi_dev_nvlink_error_dl_replay`, `dcgm_fi_dev_nvlink_error_dl_recovery`, `dcgm_fi_dev_nvlink_bandwidth_total`, `dcgm_fi_prof_nvlink_rx_bytes`, `dcgm_fi_prof_nvlink_tx_bytes` | 트래픽 부재와 링크 장애를 구분한다. 지원하지 않는 V100 구성에는 억지로 적용하지 않는다. |
| `SXID_ERROR` | NVSwitch SXid와 fatal/non-fatal switch 오류 | SXid 원문 → 코드 fatality → switch/port → 동반 GPU·NVLink 상태 | 직접 SXid 숫자 metric 없음. 보조 `dcgm_fi_dev_fabric_manager_status`, NVLink error metric군 | Loki의 FM/kernel SXid 원문과 설치된 FM 문서 기준이 핵심이다. NVSwitch capability가 확인된 노드에만 적용한다. |
| `FABRIC_MANAGER_ERROR` | FM 비정상, GPU fabric 미등록, FM service 문제 | FM status → GPU fabric registration → SXid/NVLink → service log | `dcgm_fi_dev_fabric_manager_status`, `dcgm_fi_dev_nvlink_error_dl_{crc,replay,recovery}` | FM 미설치 장비의 metric 부재를 장애로 판단하지 않는다. DGX별 실제 topology와 FM mode를 확인한다. |

### 4.6 `DRIVER_CUDA_RUNTIME`

| Category | 포함 내용 | 대표 우선 데이터 | 매핑 메트릭 | 보조 증거와 판정 주의 |
|---|---|---|---|---|
| `DRIVER_ERROR` | NVIDIA kernel module·driver 초기화/접근 오류 | Fleet driver state/event → driver version → Xid/kernel log | CPC-1 catalog에 직접 health metric 없음. Exporter label 후보 `DCGM_FI_DRIVER_VERSION`; Xid field는 실제 설정 확인 | version label은 건강 상태 metric이 아니다. Loki의 NVRM·module load 오류와 함께 본다. |
| `NVML_ERROR` | NVML init/query 실패, library 접근 불가 | 실제 등록된 Fleet library/DCGM component의 state·event 또는 Loki 오류 → NVML·driver version → library log | 후보 `dcgm_fi_nvml_version`, `DCGM_FI_NVML_VERSION`, `DCGM_FI_DRIVER_VERSION`; CPC-1 실노출 미확정 | 확인한 Fleet 버전에는 `NVML`이라는 독립 등록 component가 없다. 배포 버전의 component 이름과 producer 계약을 먼저 확인하며 version 존재만으로 정상을 판정하지 않는다. |
| `CUDA_RUNTIME_ERROR` | CUDA runtime 초기화·호출 오류와 device unavailable | 실제 수집된 library/DCGM state·event 또는 Loki runtime 오류 → runtime/driver compatibility → 오류 원문 | 현재 catalog에 직접 CUDA runtime 오류 metric 없음 | 확인한 Fleet 버전에는 `CUDA`라는 독립 등록 component가 없다. Fleet event를 전제로 하지 말고 실제 producer 연결을 확인한다. workload 코드 분석은 범위 밖이지만 node runtime 증거는 남긴다. |
| `VERSION_MISMATCH` | Driver, NVML, CUDA, firmware 조합 불일치 | `/machine-info` version inventory → compatibility rule → 직후 오류 | `fleetint_gpu_firmware_info`, `fleetint_node_software_info`; 후보 `DCGM_FI_DRIVER_VERSION`, `DCGM_FI_NVML_VERSION` | 문자열·label metric을 숫자 비교하지 않는다. compatibility matrix revision과 연결한다. |

### 4.7 `NODE_SYSTEM`

| Category | 포함 내용 | 대표 우선 데이터 | 매핑 메트릭 | 보조 증거와 판정 주의 |
|---|---|---|---|---|
| `CPU_PRESSURE` | CPU 포화, 높은 load, Agent/driver 처리 지연 가능성 | CPU used → 1m/5m/15m load → core 수와 지속시간 | `cpu_used_percent`, `cpu_load_average` | load는 CPU core 수와 함께 해석한다. GPU 오류의 인과로 바로 확정하지 않는다. |
| `MEMORY_PRESSURE` | Host memory 부족, OOM 가능성 | available/used percent → used/total → OOM event | `memory_available_bytes`, `memory_used_percent`, `memory_used_bytes`, `memory_total_bytes`, `memory_free_bytes` | Loki kernel OOM과 Fleet event를 결합한다. GPU framebuffer memory와 혼동하지 않는다. |
| `DISK_ERROR` | 용량 고갈, filesystem/I/O 오류, 수집·로그 기록 실패 | free/used/total → mount/path → I/O·filesystem log | `disk_free_bytes`, `disk_used_bytes`, `disk_total_bytes`, `disk_get_usage_seconds` | `disk_get_usage_seconds`를 disk I/O latency로 해석하지 않는다. 실제 label과 의미 계약이 필요하다. |
| `HOST_OS_ERROR` | file handle/PID 고갈, zombie, reboot, OS/kernel 오류 | node uptime → file handle/PID/zombie → kernel/service log | `fleetint_node_uptime_seconds`, `os_allocated_file_handles`, `os_allocated_file_handles_percent`, `os_threshold_allocated_file_handles`, `os_running_pids`, `os_threshold_running_pids`, `os_zombie_processes`, `os_limit`, `os_used_percent` | 재부팅은 uptime reset으로 보조 확인한다. 원인은 Loki의 kernel/system 로그로 확인한다. |

### 4.8 `NETWORK_IB`

| Category | 포함 내용 | 대표 우선 데이터 | 매핑 메트릭 | 보조 증거와 판정 주의 |
|---|---|---|---|---|
| `ETHERNET_ERROR` | Ethernet link down, error/drop 증가, 통신 저하 | link 상태 → RX/TX errors·drops → traffic | `network_ethernet_link_up`, `network_ethernet_rx_errors`, `network_ethernet_tx_errors`, `network_ethernet_rx_dropped`, `network_ethernet_tx_dropped`, `network_ethernet_rx_bytes`, `network_ethernet_tx_bytes`, `network_ethernet_rx_packets`, `network_ethernet_tx_packets` | interface label과 관리망/데이터망 역할을 확인한다. counter 증가량을 사용한다. |
| `IB_PORT_ERROR` | InfiniBand port down/degraded, physical/link 오류 | port state·physical state → error counter → switch/port 연결 | 현재 제공 catalog에 전용 IB metric 이름 미확인 | Fleet IB state/event, Loki, 운영자가 제공한 `ibstat`, `perfquery`, `ibdiagnet`, `mlxlink` 결과가 필요하다. Ethernet metric으로 IB 정상 여부를 대신 판정하지 않는다. |
| `RDMA_DEGRADED` | RDMA/RoCE 오류·drop·재전송과 성능 저하 | RDMA capability → port/GID → RDMA counters → bandwidth/latency | 현재 제공 catalog에 전용 RDMA/RoCE metric 이름 미확인 | `rdma statistic`, `ib_write_bw`, `ib_write_lat`, RoCE GID/PFC/ECN 증거가 필요하다. 노드 Agent가 임의 명령을 실행하지 않고 승인된 증거를 소비하도록 한다. |

### 4.9 `CONTAINER_RUNTIME`

| Category | 포함 내용 | 대표 우선 데이터 | 매핑 메트릭 | 보조 증거와 판정 주의 |
|---|---|---|---|---|
| `CONTAINER_RUNTIME_ERROR` | containerd/CRI/runtime service 오류가 GPU 도구·수집기에 미치는 영향 | 실제 연결된 service 상태·runtime log → host pressure → Fleet 관련 state/event 존재 여부 | 현재 제공 catalog에 runtime 전용 metric 이름 미확인. 보조로 `cpu_used_percent`, `memory_used_percent`, `disk_free_bytes` | 확인한 Fleet 버전에서 runtime component가 활성 등록됐다고 가정하지 않는다. Kubernetes scheduler·Pod placement RCA는 제외하고 node runtime 자체 실패만 다룬다. |
| `GPU_DEVICE_INJECTION_ERROR` | 컨테이너에 `/dev/nvidia*`·driver library가 노출되지 않거나 NVIDIA runtime hook 실패 | Fleet container/GPU state → device node → NVIDIA runtime/toolkit log → host GPU 정상 여부 | 직접 확정 metric 없음. host GPU 보조 `dcgm_fi_dev_gpu_util`, `dcgm_fi_dev_fb_total`, `dcgm_fi_driver_version` | Host에서는 GPU가 정상인데 컨테이너에서만 실패하는지 분리한다. Pod scheduling 원인까지 확장하지 않는다. |

## 5. 런북 작성 시 매핑 표현

아래 구조는 Category와 관측 후보의 관계를 검토하기 위한 **개념 모델**이다. 새 DB 테이블을 만들라는 요구사항이 아니다. 현재 main 설계에 맞춰 우선 기존 `data_dictionary`의 versioned content 또는 런북 content 안에서 필요한 관계를 표현하고, 실행에 사용할 때는 참조 revision/hash와 허용된 query를 함께 고정한다. 별도 정규화 테이블은 실제 조회·운영 요구가 확인된 뒤 검토한다.

```text
incident_domain
  └─ incident_category
       └─ category_observation_plan
            ├─ priority_tier: immediate | primary | secondary
            ├─ sequence
            ├─ source: fleet_state | fleet_event | mimir | loki | machine_info
            ├─ metric_definition_id
            ├─ lookback
            └─ required

metric_definition
  ├─ canonical_metric_key
  ├─ producer
  ├─ source_metric_name
  ├─ metric_type
  ├─ unit
  ├─ target_label_mapping
  ├─ capability_condition
  └─ validation_state
```

예를 들어 `ECC_DBE`에는 한 행에 metric 이름 여러 개를 넣기보다 다음 순서로 각각 저장한다.

| priority | sequence | source | source metric | 목적 |
|---|---:|---|---|---|
| immediate | 1 | Loki/Fleet event | Xid 원문 | 사건 시각과 GPU 식별 |
| primary | 1 | Mimir/Fleet | `dcgm_fi_dev_ecc_dbe_vol_total` | 사고 구간 DBE 증가 확인 |
| primary | 2 | Mimir/Fleet | `dcgm_fi_dev_ecc_dbe_vol_dev` | device-memory 영역 오류 확인; GPU는 UUID·PCI BDF로 식별 |
| secondary | 1 | Mimir/Fleet | `dcgm_fi_dev_ecc_dbe_agg_total` | 장기 누적 이력 확인 |
| secondary | 2 | Fleet state | health/action | 현재 상태와 원천 조치 확인 |

## 6. 운영 적용 전에 확인할 항목

1. CPC-1과 CPC-2의 Mimir에서 위 이름을 각각 조회해 실제 존재 여부를 확정한다.
2. Fleet와 Exporter의 metric을 source별로 분리하고, 동일 GPU를 `uuid`/`UUID`와 PCI BDF로 binding한다.
3. 각 metric의 HELP, TYPE, unit, sample interval, unsupported sentinel을 기록한다.
4. A100 40GB·80GB와 V100에서 지원 Category를 capability matrix로 나눈다.
5. DGX별 NVSwitch와 Fabric Manager 사용 여부를 확인해 SXid/FM Category를 활성화한다.
6. IB/RDMA와 container runtime은 실제 수집 metric이 확인되기 전까지 Fleet event·Loki·승인된 진단 자료 기반으로 둔다.
7. Category별 Observation Plan을 운영 데이터와 승인된 query로 검증한 뒤 `validation_state=runbook-validated`로 승격한다.
8. 런북마다 실제 Agent가 실행할 수 있는 `query_id`, 허용 목록, lookback, 대상 binding, 판정 predicate를 연결한다.
9. 데이터 없음은 `healthy`와 구분하고 `unknown`, `unsupported`, `not-collected`, `stale` 중 무엇인지 기록한다.

## 7. 근거 자료

- `fleet-intelligence-metrics.md`: CPC-1 Mimir label API에서 얻은 95개 이름 목록. 이름 존재 증거이며 현재 값·지원 여부 증거는 아니다.
- `fleet_실제_메트릭_라벨_목록.txt`: CPC-2 표본의 실제 label 확인 자료. 표본 시점과 대상 범위를 함께 보존한다.
- 공동 코드 [`docs/evidence/GPU_메트릭_대조목록_20260915.md`](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/blob/d2007ff362127fb315647e17c163369341657ea1/docs/evidence/GPU_%EB%A9%94%ED%8A%B8%EB%A6%AD_%EB%8C%80%EC%A1%B0%EB%AA%A9%EB%A1%9D_20260915.md): Fleet 참고 소스와 DCGM Exporter 기본 CSV 비교
- 공동 코드 [`docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md`](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/blob/d2007ff362127fb315647e17c163369341657ea1/docs/specs/rca-agent/11_RCA_Agent_%EB%AA%A8%EB%93%88_%EC%84%A4%EA%B3%84%EC%84%9C.md): 현재 Agent 계약, 검색·적용 순서, 자동 조치 제외 원칙
- [NVIDIA GPU Debug Guidelines](https://docs.nvidia.com/deploy/gpu-debug-guidelines/index.html)와 gpud pinned commit의 Xid/SXid component
