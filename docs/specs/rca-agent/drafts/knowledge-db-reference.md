# GPU 노드 RCA Agent Knowledge DB 참고 설계

> 2026-09-22 통합 안내: meaning/binding/query 정합과 단계별 개발 기준을 [11. RCA Agent 모듈 설계서](../11_RCA_Agent_모듈_설계서.md)에 반영했다. 이 문서는 제안 출처·당시 대조 기록으로 보존한다. 정적 필드 대응을 운영 수집 확인으로 해석하지 않으며 새 DB 계층 구축을 선결 조건으로 삼지 않는다.

검토일: 2026-09-21 · 상태: 팀 검토용 제안, 운영 DB 반영 전

이 문서는 첨부된 `knowledge-db-reference.md`를 2026-09-21 제공 ZIP의 코드 및 CPC-1/CPC-2 `dcgmi dmon --list` 출력과 대조해 정정한 것이다. **기존 스키마의 확정 명세나 이미 구현된 기능을 뜻하지 않는다.** GPU 노드 RCA 범위에 한정하며 Kubernetes scheduling·Pod 원인 분석은 다루지 않는다.

## 1. 핵심 결론

`dcgm_fi_dev_gpu_temp`와 `DCGM_FI_DEV_GPU_TEMP`는 단순한 대소문자 유사 이름이 아니다. 검토한 Fleet 소스와 DCGM Exporter 설정은 모두 DCGM의 GPU 온도 **Field ID 150**을 사용한다. 따라서 둘을 `gpu.temperature.celsius`라는 하나의 의미로 연결할 수 있다. 다만 서로 다른 producer의 표본 시각·라벨·지원 상태와 실제 수치 일치는 아직 검증되지 않았다. 원본 시계열을 합산하거나 하나로 덮어쓰지 않는다.

권장 관계는 다음과 같다.

```text
canonical meaning: gpu.temperature.celsius
  ├─ binding: fleet-intelligence / dcgm_fi_dev_gpu_temp / DCGM Field ID 150
  └─ binding: dcgm-exporter     / DCGM_FI_DEV_GPU_TEMP / DCGM Field ID 150

equivalence_basis: same_dcgm_field_id
equivalence_status: source_verified
runtime_value_validation: pending
selection_policy: explicit_primary_then_qualified_fallback
aggregation_policy: never_sum_across_producers
```

`canonical_metric`은 사람이 읽고 코드가 참조하는 **의미 식별자**다. DCGM Field ID는 그 의미에 연결된 **원천 필드 식별자**다. Field ID만을 canonical key로 쓰면 Fleet host metric·Loki event처럼 DCGM ID가 없는 데이터와, 같은 Field에서 파생된 rate/ratio/상태 판정을 표현하기 어렵다. 권장 키는 의미·단위·집계 범위를 명시한 `meaning_id`이며, Field ID는 binding별 `field_namespace='dcgm'`, `field_id=150`으로 저장한다.

## 2. 현재 코드와 첨부 문서의 차이

| 주제 | 제공 ZIP에서 확인한 사실 | 이 문서의 판단 |
|---|---|---|
| RCA 관측 | `rcca-agent/configs/workflow.yml`은 Grafana MCP의 Prometheus/Loki 조회 도구를 등록한다. | 현재 직접 관측 경로는 Grafana MCP → Mimir/Loki다. Fleet REST `/v1/states`·`/v1/events`를 현재 RCA가 직접 호출한다고 쓰지 않는다. 도입 시 별도 설계·구현이 필요하다. |
| 지식 저장 | `shared/migrations/001_backend.sql`의 `knowledge_revisions`는 `runbook`, `policy`, `data_dictionary`, `reference`, `case` kind와 draft→review→published 상태를 갖는다. | 기존 테이블을 활용한 첫 구현이 최소 변경이다. 아래 binding 예시는 **제안 content**이며 DB 컬럼·검증 API가 이미 있다는 뜻은 아니다. |
| RCA 산출 | 현행 RCA 모듈 명세는 호환 published Runbook을 읽고 RCA candidate를 저장한다. Runbook 자동 발행은 명시적으로 배제한다. | 첨부 Claude 문서의 “RCA가 사건별 장애 런북 초안을 반드시 생성한다”, `runbook.official`/`runbook.incident_draft` kind를 사용한다는 문장은 현행 동작으로 채택하지 않는다. 사건별 기록이 필요하면 기존 `case` 또는 별도 승인된 데이터 모델을 먼저 논의한다. |
| Knowledge API | `backend/internal/api/knowledge.go`는 위 5개 kind만 허용한다. | 새 kind와 자동 승격 절차는 migration·API·검수 계약 변경 없이는 동작하지 않는다. |
| Field catalog | 첨부 CPC-1 출력의 숫자 Field 행은 **572개**, CPC-2는 **612개**다. | `574/612`, 차이 38개라는 기재를 `572/612`, 차이 **40개**로 정정한다. 이는 `dcgmi dmon --list`가 아는 Field 수이며 수집 중인 시계열 수가 아니다. |

Claude 문서의 “19개 활성 + 13개 선택 = 32개 대응”은 고정된 **참고 Fleet commit과 Exporter 기본 CSV**의 정적 비교다. 현재 CPC 배포의 활성 CSV·실제 Mimir 수신·GPU별 지원 여부를 입증하는 수치로 사용하지 않는다. CPC-1과 CPC-2의 Exporter 활성 CSV가 각각 25/26개라는 주장도 이번에 제공된 Field catalog만으로는 재검증할 수 없다.

## 3. canonical meaning과 Field ID를 잇는 방법

두 층을 분리한다.

1. **Meaning**: `gpu.temperature.celsius`처럼 RCA가 질문하는 물리량·단위·대상 범위를 정의한다. 이름과 의미가 바뀌면 revision을 새로 만든다.
2. **Source binding**: producer, 원본 metric 이름, DCGM Field ID, cluster, 모델, unit/type, label 변환, query ID, 유효 기간, 검증 상태를 기록한다. 한 meaning에 여러 binding이 연결될 수 있다.

현재 코드와 호환되는 초기 저장 방식은 `knowledge_revisions(kind='data_dictionary')`의 `content`에 아래와 같은 **제안 형태**로 작성하고 사람 검토 후 발행하는 것이다. 기존 API는 content의 이 내부 스키마와 binding 간 일관성을 검사하지 않으므로, 실제 사용 전 validation을 구현해야 한다.

```json
{
  "schema": "gpu-metric-meaning/1.0",
  "meaning_id": "gpu.temperature.celsius",
  "entity_kind": "gpu",
  "normalized_unit": "celsius",
  "value_type": "gauge",
  "bindings": [
    {
      "source_name": "fleet-intelligence",
      "raw_field": "dcgm_fi_dev_gpu_temp",
      "field_namespace": "dcgm",
      "field_id": 150,
      "raw_unit": "celsius",
      "gpu_identity_label": "uuid",
      "equivalence_status": "source_verified",
      "runtime_value_validation": "pending"
    },
    {
      "source_name": "dcgm-exporter",
      "raw_field": "DCGM_FI_DEV_GPU_TEMP",
      "field_namespace": "dcgm",
      "field_id": 150,
      "raw_unit": "celsius",
      "gpu_identity_label": "UUID",
      "equivalence_status": "source_verified",
      "runtime_value_validation": "pending"
    }
  ],
  "selection_policy": "explicit_primary_then_qualified_fallback",
  "aggregation_policy": "never_sum_across_producers"
}
```

실제 운영 binding에는 `source_version`/image digest, `cluster_id`, `supported_models`, `query_id`, `original_period`, `max_age`, `invalid_values`, `valid_from/to`, `verification_scope`, `evidence_refs`도 필요하다. 이것들은 [03 데이터 설계서](../../common/03_데이터_설계서.md)에 적힌 데이터 사전 revision 필드와 맞춘다. 표준 의미와 원본 binding을 **서로 다른 revision 또는 정규화된 자식 행으로 둘지**는 데이터 설계 담당자와 정한다. JSON 한 행에 모든 binding을 넣는 것은 초기 제안일 뿐이다.

Field ID의 역할은 다음처럼 제한한다.

| 목적 | 사용 |
|---|---|
| 동일 Field 확인 | `field_namespace + field_id` 및 고정된 소스 코드/CSV로 증명 |
| 클러스터 지원 확인 | 해당 CPC `dcgmi dmon --list`에 ID가 있는지 확인. **목록에 있음 = 실제 GPU가 값을 제공함**은 아님 |
| 실제 수집 확인 | 활성 Exporter/Fleet 설정과 Mimir sample을 별도 확인 |
| 값 동등성 확인 | 동일 GPU UUID와 근접한 시각의 두 원본 값을 단위 변환 후 비교. gauge 허용 오차, counter reset·집계창을 Field별로 정의 |

원본 metric 이름만 lower/upper 변환해서 자동 binding하지 않는다. 반대로 같은 Field ID·같은 물리량으로 소스 검증된 쌍을 영구히 별개 의미로 취급할 이유도 없다. `source_verified`는 같은 원천 Field라는 **정적 검증**이고 `value_verified`는 현재 CPC에서의 **실측 검증**이다.

## 4. CPC Field ID 확인과 관측 우선순위

첨부된 `dcgmi dmon --list`에서 아래 ID는 CPC-1과 CPC-2 **양쪽 목록에 존재**한다.

| canonical meaning 예시 | DCGM Field ID | `dcgmi` Long Name | Fleet / Exporter 원본 이름 예시 | 확인 상태 |
|---|---:|---|---|---|
| `gpu.temperature.celsius` | 150 | `gpu_temp` | `dcgm_fi_dev_gpu_temp` / `DCGM_FI_DEV_GPU_TEMP` | Field ID·정적 소스 확인, 실값 대조 대기 |
| `gpu.power.watts` | 155 | `power_usage` | `dcgm_fi_dev_power_usage` / `DCGM_FI_DEV_POWER_USAGE` | 같은 조건 |
| `gpu.pcie.replay.total` | 202 | `pcie_replay_counter` | `dcgm_fi_dev_pcie_replay_counter` / `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` | 같은 조건. counter reset 처리 필요 |
| `gpu.utilization.percent` | 203 | `gpu_utilization` | `dcgm_fi_dev_gpu_util` / `DCGM_FI_DEV_GPU_UTIL` | 같은 조건. 표본 window 차이 가능 |
| `gpu.memory.framebuffer.used` | 252 | `fb_used` | `dcgm_fi_dev_fb_used` / `DCGM_FI_DEV_FB_USED` | 같은 Field. raw/normalized 단위 별도 확인 |

Field ID 150의 lookup은 `150 → gpu_temp`까지다. 그 다음 `gpu_temp → gpu.temperature.celsius`는 단위·값 형식·entity를 검토한 **우리 데이터 사전 결정**이다. Field ID만 보고 canonical 문자열을 기계적으로 생성하지 않는다.

RCA에서는 Incident의 cluster/GPU UUID/사고 시각으로 Category에 연결된 관측 계획을 찾는다. 해당 `meaning_id`의 binding 가운데 그 클러스터·모델에서 **실제 수신 및 freshness가 검증된** primary를 조회한다. 결과가 없으면 `missing` 또는 `stale`을 남긴다. 대체 source 사용은 미리 승인된 fallback 조건을 충족할 때만 수행하고, 결과에 실제 source·query·시각·검증 상태를 남긴다. 두 source 값을 합산하거나 평균해 하나의 GPU 상태로 만들지 않는다.

## 5. Knowledge DB와 런북의 경계

- Mimir/Loki는 원본 수치·로그의 저장소다. Knowledge DB에는 metric 의미, binding, 우선 조회 순서, 적용 조건, 근거 revision을 저장한다.
- 현재 RCA Agent는 사건 증거와 호환되는 **published Runbook**을 조회하고, 필요한 관측을 Grafana MCP로 보충한다. 모든 Field catalog를 사건마다 읽을 필요는 없다.
- `incident_category → observation_plan → meaning_id → source binding/query_id` 관계는 GPU 노드용 **추가 설계 제안**이다. 현재 `knowledge_revisions`와 기존 query registry가 이 전체 관계를 자동 실행한다고 간주하지 않는다.
- gpud/Fleet의 suggested·repair action은 원천 코드·버전·순서를 보존하고 내부 권고와 구분한다. 관측값이 같아도 조치의 실행 가능 여부는 장비·사용 상태·승인 조건을 별도로 확인한다.
- 사건별 RCA 결과는 `result_candidates`/evidence 계약을 따른다. 새 “장애 런북 초안”의 생성·승격은 현행 기능이 아니며, 팀이 필요성을 결정한 뒤 kind·저장·검토 흐름을 설계한다.

## 6. 팀이 결정하고 검증할 사항

1. `meaning_id`를 기존 `data_dictionary` revision 안에 둘지, 조회·중복 제약을 위해 별도 정규화 테이블로 분리할지 결정한다.
2. Field ID 150 등 동일 ID 쌍을 동일 GPU UUID에서 동시 조회한다. source별 sample time, unit, value, GPU/MIG identity, counter reset을 기록해 `runtime_value_validation`을 승격한다.
3. CPC별 Fleet image digest와 DCGM Exporter CSV/Pod 설정, 실제 Mimir tenant의 시계열을 확보한다. Field catalog 572/612개를 수집 활성 목록으로 쓰지 않는다.
4. Category별 `observation_plan`과 approved fallback 정책을 정의한다. 빈 결과·stale·unsupported를 구분한다.
5. RCA가 생성하는 사건별 런북이 제품 요구사항인지 결정한다. 필요하다면 현행 `kind` 제약과 사람 검토 경로를 설계한 뒤 구현한다.

## 7. 검토 근거

- 사용자 제공 `gpu-ops-advisor-main (1).zip`: `rcca-agent/configs/workflow.yml`, `rcca-agent/README.md`, `backend/internal/api/knowledge.go`, `shared/migrations/001_backend.sql`, `output/deliverables-20260917-v1.3/03_데이터_설계서.md`, `11_RCA_Agent_모듈_설계서.md`.
- CPC별 `dcgmi dmon --list` 출력: [CPC-1](../../../evidence/dcgm/cpc-1-dcgm-dmon-field-catalog.txt), [CPC-2](../../../evidence/dcgm/cpc-2-dcgm-dmon-field-catalog.txt). 숫자 Field 행과 대표 ID를 직접 대조했다. 이는 조회한 DCGM의 Field catalog이며, 실제 수집된 runtime sample이나 Mimir 시계열 목록은 아니다.
- [Fleet Intelligence Agent 고정 소스의 GPU 온도 Field 정의](https://github.com/NVIDIA/fleet-intelligence-agent/blob/8dd8826b7604386ad667125298156ddb1d1a7865/third_party/fleet-intelligence-sdk/components/accelerator/nvidia/dcgm/thermal/metrics.go), [DCGM Exporter 4.4.2-4.7.0 기본 CSV](https://github.com/NVIDIA/dcgm-exporter/blob/4.4.2-4.7.0/etc/default-counters.csv), [NVIDIA DCGM Field ID 문서](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-field-ids.html). 이 정적 소스의 배포 버전 일치는 아직 확인되지 않았다.
