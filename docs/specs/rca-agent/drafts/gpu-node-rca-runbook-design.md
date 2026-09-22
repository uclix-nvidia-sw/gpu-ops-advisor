# GPU 노드 RCA Agent 런북 설계 초안

상태: 팀 검토용 · 범위: CPC-1(A100), CPC-2(V100) GPU **노드** 장애 · 운영 DB 미반영

후속 결정: 조사 순서는 [Runbook-first BM25 파이프라인](gpu-node-rca-runbook-first-pipeline.md)을 우선한다. 아래 런북 항목과 관측 목록은 콘텐츠 작성 참고이며, 전체 관측 계획을 런북 검색 앞에 실행하라는 의미가 아니다.

## 요약

런북은 “증상 → 먼저 확인할 증거 → 분기 판단 → 권고 → 종료/상향 보고”를 사람이 검토한 규칙으로 기록한다. **장애 도메인**은 탐색을 위한 큰 분류이고, **런북**은 Xid 코드·장비 모델·동반 증상처럼 구체적인 조건을 가진 실행 가능한 조사 절차다. 한 사건에 여러 런북이 적용될 수 있다. Grafana Alert가 사건의 시작점이며, Alert의 문구만으로 원인을 확정하지 않는다.

초기 구현은 기존 `knowledge_revisions(kind='runbook')`와 draft → in_review → reviewed → published 절차를 사용한다. 도메인별 메트릭 우선순위와 producer binding은 [Knowledge DB 참고 설계](knowledge-db-reference.md)의 **추가 제안**이므로, 현행 Agent가 이를 자동 실행한다고 가정하지 않는다. 런북이 제시한 재시작·GPU reset·노드 재부팅 등은 **권고**이며 Agent가 수행하지 않는다.

## 1. 사건에서 런북까지

1. Grafana Alert가 Incident snapshot으로 저장된다. 사람이 웹 UI에서 요청하거나 fault injection으로 만든 사건도 **동일한 Incident 계약**을 통과한다면 조사할 수 있지만, 현재 RCA Worker는 `incident_id`가 없는 임의 증상 요청을 받지 않는다. 입력 경로와 주입 표시를 증거에 남긴다.
2. Alert의 cluster, node, GPU UUID, 시각, 오류 코드와 원본 메시지를 보존한다. 누락된 식별자는 추측하지 않고 `missing`으로 기록한다. Alert 라벨·본문은 **조사 단서**이며 검증된 사실과 구분한다.
3. 코드(Xid/SXid), 핵심 단어, producer의 상태/이벤트 종류로 후보 런북을 찾는다. 도메인 → 상세 장애 유형 → 해당 하드웨어/버전의 순서로 좁힌다. 오류 코드만으로 단일 원인을 확정하지 않는다.
4. **첫 조회 묶음**은 수집 정상 여부·동일 GPU 식별·사고 전후 이벤트를 확인한다. 다음에 런북별 2~4개의 우선 관측을 조회하고, 결과에 따라 확장한다. `no series`, stale, unsupported, query failed를 서로 다르게 남긴다.
5. 동반 Xid/SXid와 모델·Fabric Manager 상태 등을 확인해 분기한다. 확인된 증거, 반증, 빈틈, 출처를 붙인 원인 후보와 권고를 작성한다. 조치 후 상태 확인은 운영자 작업으로 분리한다.

관측 원본은 현재 Grafana MCP를 통한 **Mimir/Loki**다. Fleet Intelligence의 `/state`·`/event` 직접 API 조회는 현행 RCA 조회 경로가 아니므로, 직접 연동은 별도 설계가 필요하다. Fleet가 전송한 상태·이벤트가 Loki/Mimir에 있다면 실제 라벨·형식을 검증한 query ID를 통해 사용할 수 있다. `dcgmi dmon --list`는 Field catalog이지 활성 메트릭이나 시계열 표본이 아니다.

## 2. 런북 한 건의 구성

| 항목 | 기록할 내용 |
|---|---|
| 정체성 | 안정적인 `knowledge_key`, 제목, revision, 도메인·상세 유형, 소유자 |
| 출처 | NVIDIA/gpud/Fleet 원문 URL·고정 버전·검색 날짜, 원문 action ID/문구, 내부 번역·보충 여부 |
| 적용 범위 | CPC, GPU 모델/세대, 관련 장치, 드라이버/DCGM/Fleet 버전, MIG·NVSwitch·Fabric Manager 조건 |
| 진입 단서 | Xid/SXid 번호, Alert label, Loki 이벤트 패턴, Fleet 상태/이벤트 코드. 문자열은 정규화하되 원문 보존 |
| 첫 관측 | query ID, `meaning_id`, source binding, 조회 기간, GPU/node identity, 우선순위, freshness, 기대 단위 |
| 판단 분기 | 반드시 필요한 증거, 동반 코드, 반증·제외 조건, 정보 부족 시 다음 조회, 멈춤 조건 |
| 권고 | 출처별 suggested/repair action 원문, 적용 전제, 영향 범위, 실행 주체, 검증 방법, 벤더 상향 조건 |
| 검수 | reviewer, 검증 환경·근거, published revision, 후속 재검토 조건 |

외부 action은 **원문과 내부 해석을 다른 필드**로 보관한다. gpud의 `suggested_actions`·`repair_actions`와 Fleet가 제공하는 action이 있으면 고정된 소스 버전에서 추출해 출처를 명시한다. gpud의 action을 NVIDIA 공식 조치라고 표시하지 않는다. NVIDIA 공식 지침과 충돌하거나 장비 조건이 다르면 자동 선택하지 않고 검토 대상으로 표시한다.

## 3. 우선 조회 원칙

모든 런북의 공통 관측은 ① Alert 시각과 대상 확인 ② 수집기/시계열 freshness ③ 동일 GPU UUID의 사고 전후 Loki 이벤트 ④ 해당 producer의 상태 변화다. 장애 단서별 **첫 추가 조회**는 다음과 같다. 실제 Mimir 메트릭명은 CPC별 수신 확인을 거쳐 binding에 등록하며, 아래 이름만으로 수집 중이라고 판단하지 않는다.

| 단서/도메인 | 먼저 확인할 데이터 | 그다음 분기 |
|---|---|---|
| `COLLECTION`: 값 소실·stale | `up`, producer/collector 상태, 마지막 sample 시각, Loki collector 오류 | 실제 GPU 고장과 관측 공백을 분리 |
| `GPU_DEVICE`/Xid 79 | Loki Xid 원문·GPU UUID, GPU inventory/접근 상태, 동시 PCIe 오류 | 동일 노드 다른 GPU와 수집기 상태 대조, 벤더 상향 |
| `GPU_MEMORY`/Xid 48·63·64·92·94·95 | Xid 순서·시간, ECC/row-remap/page-retirement 데이터, GPU 모델 | **A100과 V100의 조치 분리**; 동반 코드와 작업 영향 확인 |
| `GPU_THERMAL_POWER` | `DCGM_FI_DEV_GPU_TEMP`(Field ID 150), `DCGM_FI_DEV_POWER_USAGE`(155), clocks/throttle 원인 | 부하 변화·온도 한계·전력 제한을 구분 |
| `GPU_INTERCONNECT`/Xid 74·SXid | 원문 코드·링크 ID, NVLink/PCIe 오류 counter, Fabric Manager 상태·로그 | NVSwitch 존재 및 FM 상태를 먼저 확인; 모델별 절차 선택 |
| `DRIVER_CUDA_RUNTIME` | driver/NVML 오류 로그, 드라이버·CUDA 버전, GPU 접근 결과 | 버전 불일치인지 장비 접근 상실인지 구분 |
| `NODE_SYSTEM` | CPU/메모리/디스크 상태, OOM/I/O·커널 로그 | GPU 자체 이벤트와 시간 상관 확인 |
| `NETWORK_IB` | IB 포트 상태·오류 counter, RDMA/NCCL 오류 로그 | 링크·케이블·구성·애플리케이션 원인 분리 |
| `CONTAINER_RUNTIME` | runtime/NVIDIA toolkit 오류 로그, GPU device 접근 증거 | 노드 수준의 GPU 주입/접근 문제까지 다룸; Pod scheduling 분석은 범위 밖 |

예시 이름 `DCGM_FI_DEV_*`는 dcgm-exporter 쪽 후보 이름이다. Fleet의 소문자 이름과 Field ID가 같아도 sample 시각·단위·라벨·지원 상태가 검증되기 전에는 값을 합산하거나 한 표본으로 취급하지 않는다. source별 query ID와 실패 시 fallback 조건을 별도로 등록한다.

## 4. 먼저 작성할 런북

**첫 묶음**은 실제 장애 판단과 조치가 갈리는 항목으로 제한한다. `RB-COLLECTOR-STALE`, `RB-XID-79`, `RB-XID-48-63-64`, `RB-XID-94-95-A100`, `RB-XID-74`, `RB-SXID-FABRIC`, `RB-THERMAL-THROTTLE`, `RB-IB-PORT-DEGRADED`를 후보로 제안한다. 이름은 팀 합의 전 임시 키다.

예를 들어 Xid 48 런북은 Xid 48 하나만 매칭해 reset을 권고하지 않는다. 같은 GPU에서 Xid 63/64가 이어졌는지, A100/V100 중 어느 모델인지, 작업이 종료됐는지, reset 가능 범위와 FM 상태를 확인한다. 증거가 없으면 추가 조사 또는 운영자 검토로 멈춘다. NVIDIA GPU Node Triage는 Xid 48의 **동반 코드에 따라 절차가 달라진다**고 명시한다. [공식 지침](https://docs.nvidia.com/deploy/gpu-debug-guidelines/gpu-node-triage.html)

## 5. 기존 코드와 맞추는 방법

현행 코드는 `knowledge_revisions`의 `runbook`을 읽으며, claim에 고정된 revision/hash, scope와 `compatibility`, 검토된 content hash를 확인한다. `required_evidence`, equality 형태의 `applicability_conditions`/`exclusion_conditions`, 등록된 `required_queries`, `recommendations[].preconditions`를 사용한다. Agent가 실행할 조회는 등록된 query ID로 제한되며, 권고의 `execution`은 `not_performed`다. [RCA workflow](../../../../rcca-agent/src/rcca_agent/workflow.py), [조회 레지스트리](../../../../agents/config.example.json)

따라서 위 표의 코드별 우선순위·시간 순서 판단·counter 변화량·source fallback은 **아직 실행 기능이 아니다**. 특히 현행 조건 검사는 필드의 `equals`만 지원하며, “Xid 48 다음에 63”이나 임계값·연속 상승을 표현하지 못한다. 또한 현재 등록된 `D01`~`D13` 조회는 GPU 기본 수치와 Loki 등에 한정되고 ECC·NVLink·IB용 query ID가 없다. GPU 노드용 런북을 발행하기 전에 query registry, 이벤트 파서, 조건 평가, 결과 근거 검증을 작은 단위로 추가해야 한다. 단순한 Alert 일치만으로 `causal_status=supported`를 내지 않도록 검토한다.

저장은 우선 기존 `runbook` revision을 이용하고, `content.schema_version`을 정의한다. 새 DB kind나 별도 테이블은 지금 필요성이 입증되지 않았다. 이후 조회 성능·제약 검증이 필요한 경우에만 `incident_category`·`observation_plan`을 정규화한다. 운영자 조치 기록과 사건별 RCA 결과는 런북 revision에 덮어쓰지 않는다.

## 6. 팀 검토 항목과 다음 단계

1. CPC-1/CPC-2의 실제 Fleet·Exporter 설정 및 Mimir/Loki 표본을 확인하고, 각 첫 관측의 metric/event 이름·라벨·freshness를 확정한다. Fleet `/state`·`/event`를 직접 조회할지, 수집된 복제본만 사용할지도 결정한다.
2. 초기 8개 후보의 소유자와 우선순위를 정한다. gpud/Fleet action은 고정 commit·버전에서 추출하고 NVIDIA 공식 지침과 대조한다. A100과 V100의 적용 조건을 따로 검수한다.
3. 최소 런북 JSON 스키마, query ID 목록, 코드 순서/임계값 판단 방법, evidence ref 의무를 정한다. `missing`/`stale`/`unsupported`/`query_failed` 시에는 고위험 조치를 권고하지 않는 검증 규칙을 만든다.
4. 실제 사건과 fault injection 사건으로 “맞는 런북 선택·틀린 런북 제외·증거 누락 시 보류·권고 미실행”을 시험한 후 사람 검토를 거쳐 published revision으로 승격한다.

참고: [Knowledge DB 참고 설계](knowledge-db-reference.md), [NVIDIA GPU Node Triage](https://docs.nvidia.com/deploy/gpu-debug-guidelines/gpu-node-triage.html), [NVIDIA Xid Catalog](https://docs.nvidia.com/deploy/xid-errors/latest/index.html), [gpud 고정 소스](https://github.com/leptonai/gpud/tree/9606bb8f6813fdd944cc9a349566e35075917805/components). 외부 자료는 채택 전에 해당 배포 버전과 장비 조건에 맞는지 재확인한다.
