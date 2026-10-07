# D binding 공통 설정 전환 — 2026-10-06

현재 공통 예제 revision은 `shared-log-context-20261007-r1`이다. RCA/Report는 동일한 binding 검증·수집기를 사용한다. D13은 원문 로그 문맥 조회이며 업무 영향 판정은 보류한다. 미검증 Node·Pod·Namespace 범위는 확대하지 않고 차단한다. [D07·D13 원천 계약 검토](../docs/evidence/d07-d13-source-review-20261007.md)를 따른다. **45개 D 중 43개는 검토된 관측 계약으로 자동 선택한다. D07·D46은 원천/단위 근거가 부족하여 후보로 유지한다.** [확장 근거·공통 전송 보강·남은 작업](../docs/evidence/d-observation-expansion-20261007.md)을 따른다. Fleet 관측은 실제 장비 측정 시각을 보장하지 않으며 forward hold는 0이다. 모든 D의 계산·Runbook 적용·운영 활성화가 완료됐다는 뜻은 아니다. datasource UID·클러스터 라벨은 MCP로 찾고 요청 cluster_id 값만 사용한다. [검증 범위와 제한](../docs/evidence/d-binding-discovery-20261007.md)을 따른다. [구현 범위·수정/적용 순서](../docs/specs/common/d-binding-runtime.md)와 [검수 기록](QA.md)을 따른다. 아래 날짜별 v3~v7 설명은 구 profile의 동작 기록이며 새 예제의 자동 활성화를 뜻하지 않는다.

## Datasource UID discovery / UID 자동 발견 — 2026-10-07

검증된 파라미터 binding에서 아래 environment 형식으로 Grafana datasource UID를
발견할 수 있다. 이는 **environment 부분 예시**이며 전체 실행 설정이 아니다.
기존 producer/type/unit/time/verification 계약도 완성돼 있어야 한다.

```json
{
  "datasource_mode": "discover",
  "datasource_uid": null,
  "scope_labels": {"cluster_id": ["cluster_id", "cluster", "k8s_cluster_name", "kubernetes_cluster", "k8s_cluster"]},
  "selector": {"job": "nvidia-dcgm-exporter", "collection_path": "alloy-direct"}
}
```

source는 binding의 `mimir`/`loki`로 결정된다. Fleet 로그에는 실제 로그의 cluster 라벨과
job/전송 조건을 사용해야 한다. UID 고정 모드는 `datasource_mode` 생략 또는 `pinned`이며
자동 발견과 동시에 지정할 수 없다. 후보는 여전히 실행되지 않는다. 동일 cluster가 여러
datasource에 있으면 임의 선택하지 않으며, 확인한 UID를 고정하는 방법으로 모호성을 해소한다.
[계약·운영 검수](../docs/specs/common/d-binding-runtime.md#datasource-uid-discovery--datasource-uid-자동-발견).

라벨 후보는 지정 순서로 조회한다. 앞선 라벨에 값이 없을 때만 다음 이름을 시도하며,
값이 있는데 요청 cluster_id가 없으면 다른 이름으로 우회하지 않는다. 클러스터 값의
별칭 변환은 하지 않는다. 실제 UID와 `resolved_cluster_selector`를 evidence에 저장한다.
Grafana 알림의 cluster_id → Incident의 불변 입력 → JC 작업 scope → RCA 조회로 전달한다.
클러스터는 기존 registry에 등록되어 있어야 한다. 알림식의 클러스터 확장은 후속 범위다.

## 공통 cluster_id 파라미터 — 2026-10-07

공통 원본은 [config.example.json](config.example.json)이고 Helm 사본도 같은 내용이다. CPC별 `config.cpc-direct.json`은 제거했다. RCA/Report는 같은 `AGENT_CONFIG_FILE`을 읽고 각 작업의 `input.scope.clusters[].cluster_id`를 binding에 전달한다. CPC 이름·개수나 전체 profile을 복제하지 않는다.

```json
{
  "environment": {
    "datasource_uid": "configured-datasource-uid",
    "scope_labels": {"cluster_id": "cluster_id"},
    "selector": {"collection_path": "alloy-direct", "job": "nvidia-dcgm-exporter"}
  }
}
```

`scope_labels`는 요청 파라미터 이름을 실제 소스 라벨 이름에 연결한다. Loki 등에서 소스 라벨이 `cluster`이면 값만 `cluster`로 지정한다. 수집기가 요청 값을 JSON 문자열로 이스케이프하여 정확 일치 selector에 넣는다. 누락·공백 cluster_id, 고정 selector와의 충돌, 대상 라벨이 cluster 라벨을 덮는 설정은 거부한다. 요청별 복사본만 해석하여 병렬 CPC 조회 사이에 값이 섞이지 않는다.

`auto_select_verified_bindings=true`이면 명시적으로 선택하지 않은 D에서 적용 가능한 verified 파라미터 binding이 정확히 하나일 때 자동 선택한다. 후보 0개는 미선택, 복수는 `multiple_verified_candidates` 사유로 차단한다. 대안 producer는 기존 동등성 근거가 필요하다. 명시적 선택이 우선하며 `clusters[cluster_id].bindings[D]=null`은 해당 범위에서 자동 선택도 차단한다. 정책을 false로 하면 기존 수동 선택 방식이다. 실제 자동 선택은 evidence의 `selection_method=automatic_verified` 및 binding ID/revision으로 확인한다. 공통 예제에서는 D02·D09만 이 조건을 만족한다. 나머지 후보를 발견 성공만으로 활성화하지 않는다.

파라미터화는 producer 의미 검증이나 클러스터 자동 등록이 아니다. 공통 binding을 선택하려면 기존 검증 필드와 함께 `verification.applicability`에 해당 datasource·고정 selector에서 계약이 적용되는 근거와 범위를 명시한다. 기존 CPC의 producer/version·단위·시간 검증을 신규 CPC에 자동 복사하지 않는다. 미검증 후보는 계속 차단한다. CPC 발견·Backend/JC 등록 정책은 이번 변경에 포함하지 않는다. 이전 literal `environment.cluster_id` 및 명시적 cluster override는 기존 배포 호환용으로 읽을 수 있지만 공통 예제는 사용하지 않는다.

배포 전 기존 Helm `configuration.agents` 전체 override를 확인한다. 기존 후보 profile 전체 override가 남으면 새 차트의 공통 설정을 가릴 수 있다. 검증된 공통 source 계약·limits를 유지한 전체 설정을 새 revision으로 작성해 두 Worker에 동시에 적용해야 한다. 코드/설정만으로 현재 운영 설정은 바뀌지 않으며, 새 작업의 실제 selector·binding 근거·결과 발행을 따로 검수한다. [과거 직접 수집 조사](../docs/evidence/d-binding-cpc-20261006.md#cpc-direct-environment-profile)는 당시 환경의 기록이다.

## 근거 기록 시각·순번 — 2026-10-02

RCA/Ops 근거를 생성할 때 `collected_at`과 프로세스 공통 단조 증가 `record_sequence`를 부여한다. 병렬 수집 결과를 병합하거나 DB에 일괄 저장할 때 새로 매기지 않는다. 저장 시 기존 `quality` JSON에 `recorded_at`·`record_sequence`를 보존하고 계획된 조회에는 `plan_order`를 기록한다. `recorded_at`은 근거 생성 시각이며 조회 시작·소요시간이나 장비 이벤트 시각이 아니다. 기존 데이터는 수정하지 않는다.

# RCA·보고서 Worker v1.3

## 온도·전력의 실제 저장 이름 — 2026-10-02

기본 프로필 `builtin-grafana-v7`의 D04/D11(`builtin-v6`)은 Fleet가 Mimir에 저장하는 `dcgm_fi_dev_gpu_temp`(섭씨), `dcgm_fi_dev_power_usage`(W)를 각각 조회합니다. GPU/Node 요청 조건은 실제 라벨 `uuid`/`node`에 연결합니다. 동일 DCGM field라는 [소스 대조](../docs/specs/rca-agent/references/domain-category-metric-mapping.md)와 10월 1일 전체 기간의 CPC-1/CPC-2 Grafana 읽기 조회를 확인했습니다. 해당 기간에는 두 소문자 지표가 있고 기존 대문자 온도·전력 지표는 없었습니다. 활동·메모리·GPU–Pod 관측(D01/D02/D03/D08)은 기존 Exporter 이름과 작업 라벨을 유지합니다. 두 생산자를 동시에 합산하거나 이름을 자동 추측하지 않습니다.

Fleet의 `uuid`는 기존 계산기가 이미 지원합니다. 실제 일부 표본에는 60/120/180초 간격의 공백이 있었으므로 최대 유지시간은 보수적인 기존 30초를 유지합니다. 에너지는 유효 관측 구간만 적분하고 `observed_gpu_seconds`를 함께 남깁니다. 하루를 조회했다고 하루 전체 소비량이 확보된 것은 아니며 공백을 0이나 직전 값으로 메우지 않습니다. 수집 주기 변경과 유지시간 확대는 별도 검증이 필요합니다.

확인한 Fleet 온도·전력에는 Namespace 라벨이 없습니다. **전체 Namespace 범위에서 조회할 수 있으며, 특정 Namespace만 선택한 경우 기존 Namespace 조건을 유지하므로 빈 근거/null로 남습니다.** 이를 Namespace 소비량으로 해석하거나 전체 클러스터로 몰래 넓히지 않습니다. Namespace GPU의 UUID와 유효시간을 투영하는 기능은 별도 구현 대상입니다. D07의 유효 대기 요청과 D12의 Node 할당 가능 용량 역시 해당 기간에 원본이 확인되지 않았습니다. Container 원시 요청량이나 `up`으로 대체하지 않습니다.

`configuration.agents`를 직접 지정한 배포는 내장 설정으로 자동 교체되지 않습니다. 전체 기존 객체에서 D04/D11의 `metric`, `target_labels`, query revision과 최상위 revision을 같이 반영해야 합니다. Exporter 전용 환경은 확인된 대문자 이름과 해당 UUID 라벨을 명시적으로 설정합니다. 배포 후 새 보고서의 저장된 조회식·표본·단위·유효시간을 확인해야 하며 과거 결과는 자동 재계산하지 않습니다. 이번 변경에는 D 구조 통합/신규 D 추가나 RCA 판단·Ops 산식 변경이 없습니다.

## Ops 전용 관측 limits — 2026-10-01

`report.limits`는 Ops만 적용하는 부분 override다. 예시는 max_queries=2048, chunk_seconds=86400, max_rows=50000, max_concurrency=3이며 공통/RCA limits는 48/3600/5000을 유지한다. 사용자 정의 `configuration.agents`는 전체 객체 교체이므로 새 블록을 직접 포함해야 한다. 없는 경우 기존 limits를 사용한다. 보고서도 의존성·예약 예산을 계획한 독립 Observation task를 병렬 실행하며 max_concurrency=1이면 순차 실행한다. 응답 크기·deadline·timeout·범위와 RCA 로직은 바꾸지 않는다. 자세한 계획·검수 계약은 [Ops 명세](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md#기간-수집예산-분리--2026-10-01)를 따른다. 이 설정은 예시이지 주간·월간 수집 성공의 보장이 아니다.

`builtin-grafana-v7`은 별도 `report.query_chunk_seconds`에 `{"D06":7200}`을 둔다. Ops의 D06(Pod 신원 이력)은 첫 조회 구간을 최대 2시간으로 제한하고, 다른 query는 기존 기본 24시간을 유지한다. 실제 적용값은 report limits를 반영한 전체 `chunk_seconds`와 query별 값 중 작은 값이며, 계획의 초기 호출량 계산과 실제 수집에 같은 값을 사용한다. 원본 표본 시각·Pod UID를 보존하고 집계나 표본 생략으로 용량을 줄이지 않는다. 2시간은 확인한 D06 하루 응답(약 32MiB)의 전송·처리량과 Agent의 2MiB·50000표본 한도를 고려해 정한 초기 상한이다. 아래 HTTP 5초 제한 보완과 함께 첫 대용량 요청 부담을 줄이며, Prometheus의 고정 10MiB 제한을 전제로 하지 않는다. 응답 밀도에 따라 추가 분할이 필요하므로 최적 구간이나 월간 완료 보장을 뜻하지 않는다. 사용자 정의 전체 프로필에도 이 맵과 최상위 revision을 함께 반영해야 하며, 맵이 없으면 기존 전체 구간 설정을 사용한다.

`11_RCA_Agent_모듈_설계서.md`, `12_보고서_Agent_모듈_설계서.md`와 두 문서가 참조하는 공통 계약 03/04/14를 기준으로 구현했습니다. 폴더 이름은 요청대로 **rcca-agent**, **ops-agent**이며 JC의 kind는 각각 `rca`, `report`입니다.

`runaiRCA`에서는 `agent/app/llm.py`의 연결 방식과 `agent/app/config.py`의 LLM 설정만 참고했습니다. 후속 요청에 따라 Dockerfile의 dependencies/build/runtime 구조도 맞췄습니다. 그 저장소의 조사·보고서·지식·업무 로직은 가져오지 않았습니다.

## 구성

| 경로 | 역할 |
| --- | --- |
| `rcca-agent` | Incident snapshot, 호환 Runbook, 네 등록 procedure, R01~R09 평가 |
| `ops-agent` | O01~O11 수집 계획·결정적 계산·공개 RCA 인용·보고서 |
| `shared/python` | JC Worker, LLM 전송, NAT MCP 연결, 정규화·공통 산식·결과 검사·저장·파일 |
| `grafana-mcp` | 공식 Grafana MCP v1.4.2, Prometheus/Mimir·Loki 읽기 도구 |
| `agents` | 공통 배포 프로필, Compose, 설치·테스트 스크립트, QA |

`agents/`는 제품의 두 Worker가 함께 사용하는 설정·테스트·실행 스크립트·문서를 담고, 실제 공통 실행 코드는 `shared/python/`에 있습니다. [.claude/rules/agents.md](../.claude/rules/agents.md)는 이 제품 코드를 수정하는 코딩 에이전트용 개발 지침입니다.

각 Worker는 독립 프로세스/이미지이고 공유 코드는 패키지입니다. 별도 업무 큐·접수 API·일정 루프·장비 조작·RCA 직접 요청은 없습니다. JC register → claim → heartbeat → candidate/evidence 저장 → complete로 실행합니다. 한 프로세스에서 한 작업씩 처리하며 JC가 전역 슬롯을 제어합니다.

## Grafana 조회와 LLM 오류 진단

Grafana MCP 1.4.2는 Loki 결과의 잘림 여부를 확인하려고 요청한 `limit`보다 한 건 더 조회합니다. Agent의 기본 `limits.max_rows=5000`을 그대로 보내면 Loki의 기본 `max_entries_limit_per_query=5000`을 넘습니다. 공통 수집기는 한 건을 예약해 기본 요청을 4999건으로 보내며, MCP가 Loki에 요청하는 수는 5000건입니다. 저장소의 MCP 서버 상한도 5000건이므로 `max_rows`를 늘려도 MCP에 보내는 `limit`은 최대 4999건으로 제한합니다. 최소 요청은 1건이고 Prometheus 표본 예산은 변경하지 않습니다. 운영 Loki의 한도가 더 작으면 Agent의 `max_rows`도 그 한도 이하로 맞춰야 하며, MCP 서버의 별도 상한도 함께 확인합니다.

요청한 행 수에 도달하거나 MCP의 `metadata.resultsTruncated=true`이면 같은 조회 조건에서 시간 구간을 줄여 다시 조회합니다. 최소 1초 구간에서도 잘리면 `partial`, `quality.complete=false`, `reason=sample_limit_exceeded`로 보존합니다. 조회 한도를 줄여 받은 일부 로그를 완전한 근거로 취급하지 않습니다.

기본 프로필 `builtin-grafana-v7`에서 D05는 D09 원본으로 파생하며 D09는 Fleet 알림의 `k8s_node_name`·`component` 단서를 JSON 본문 필터에 사용합니다. `json_target_fields`가 각각 `resources["k8s.node.name"]`, `attributes["component"]`를 지정하며, `| json`으로 본문 값을 추출한 뒤 문자열 동등 조건으로 필터링합니다. 기존 라벨과 충돌해 잘못된 값을 비교하지 않도록 임시 별칭과 `_extracted` 이름을 먼저 제거하고, JSON이 채운 쪽을 검사합니다. 이 값을 Loki에 저장된 stream label로 가정하지 않습니다. cluster/namespace와 배포 프로필의 기존 selector는 유지합니다. 대응하는 JSON 노드 단서가 있으면 D09의 기본 `node` stream label 조건 대신 JSON 조건을 사용하며, 단서가 없거나 해당 query에 JSON 필드 구성이 없으면 기존 selector 동작을 유지합니다.

알림 단서는 수집에만 사용하며 원본 Incident snapshot·해시는 바꾸지 않습니다. 새 Incident target에는 `machine_id/component/k8s_node_name`을 투영하지만 component는 검색 메타데이터이며 장비 식별 비교에서는 제외합니다. 이 투영만으로 검증된 건강 상태가 되지는 않습니다. 라벨과 annotation이 충돌한 단서는 필터에 사용하지 않습니다. 보고서 Worker처럼 알림 단서가 없는 호출에는 이 JSON 필터를 추가하지 않습니다.

Mimir/Prometheus·Loki 응답을 받은 뒤 Agent의 `max_bytes` 또는 표본 한도를 넘으면 기존 크기/표본 비율로 구간을 줄여 다시 받습니다. MCP가 `response body exceeds maximum size of ... bytes`로 거부한 경우에는 출처와 무관하게 같은 조건의 구간을 절반으로 줄입니다. 이때는 실제 응답 크기를 알 수 없습니다. 확인된 MCP 1.4.2의 원격 10MiB 상한은 Loki 경로의 제한입니다. 공식 MCP를 사용한 고정 응답 시험에서 Prometheus 11MiB 응답은 통과한 뒤 Agent 한도로 분할됐으며, Prometheus 원격 크기 초과 오류의 복구는 오류 주입 fixture로만 확인했습니다. 지표의 원본 표본·Pod UID와 D09/D13·파생 D05의 원본 로그·정의·대상 필터는 유지합니다.

정상 크기의 구간은 각각 증거로 보존하고 모든 재조회는 기존 query/deadline 예산을 소모합니다. 회복한 큰 구간의 실패를 전체 기간의 실패 근거로 중복 저장하지 않습니다. 최소 1초 구간에서도 MCP가 응답을 거부하면 빈 snapshot과 `unavailable / response_byte_limit`, 응답을 받았지만 Agent 크기 한도를 넘으면 기존 `partial / response_byte_limit`로 남습니다. 예산이 소진되면 남은 전체 시간 범위를 `unavailable / budget_exhausted`, `complete=false`로 표시하며 확보된 앞 구간은 보존합니다. `max_bytes` 기본 2MiB·표본 한도·Loki 경로의 원격 10MiB 및 행 수 상한·취소 계약은 유지합니다. 권한 오류·일반 시간 초과·연결 실패는 크기 초과처럼 같은 구간을 재조회하지 않습니다.

기존 설치에서 `configuration.agents`를 직접 지정했다면 새 내장 프로필로 자동 교체되지 않습니다. 기존 전체 프로필에 D05/D09의 `json_target_fields`, `health_contract=fleet-component-log-v1`, 새 query/profile revision과 `health_contracts`를 함께 반영해야 합니다. 이 설정은 객체 전체를 대체하므로 `--set configuration.agents.limits...`만 추가하지 않습니다. 배포 후 실제 노드의 `k8s_node_name`·`component`가 포함된 새 알림으로 검수하고, 해당 작업의 D05/D09 `query_version`, 저장된 `input.logql`, 구간별 `tool_status`·`quality.reason`을 확인합니다. 이전 작업은 자동 재분석하지 않습니다. Fleet adapter는 Loki 기록 시각을 보존한 보고 관측을 생성합니다. 기본 `loki_timestamp_is_observed_at=false`와 freshness 미등록 상태에서는 현재 건강 상태/runbook fact로 승격하지 않습니다. 운영 producer의 시각 의미와 freshness 검증은 별도로 필요합니다.

NAT 1.5.0은 MCP 조회 오류를 문자열로 반환할 수 있습니다. 수집기는 이 문자열을 정상 JSON으로 파싱하지 않고 안전한 `quality.error_code`로 구분합니다. 일반 오류는 `query_failed`, 최소 구간에서도 복구하지 못한 Mimir/Prometheus·Loki 크기 초과는 `response_byte_limit` 사유로 기록합니다. `loki_entry_limit_exceeded`는 Loki 행 제한 초과, `response_byte_limit`는 MCP 응답 크기 초과, `mcp_tool_error`는 그 밖의 MCP 실패, `invalid_mcp_response`는 JSON으로 읽을 수 없는 응답입니다. Worker의 `Grafana query unavailable` 로그에도 query ID·source·오류 종류/코드를 남깁니다. 이 수집기 진단에는 원본 응답·예외 메시지·인증 값을 넣지 않습니다. `mcp_tool_error`만으로 인증/권한/timeout 등 상위 원인을 확정할 수는 없습니다.

`Grafana query window` 로그는 구간마다 job/attempt·query·source·클러스터·Namespace 개수·조회 시작/끝·소요시간·결과/사유·표본 수·수신 바이트·다음 분할 크기·캐시 재사용 여부를 남깁니다. 원본 응답·조회식·Namespace 이름·인증 값은 기록하지 않습니다. MCP가 크기 초과로 거부한 응답은 수신 바이트를 알 수 없으므로 비워 둡니다.

두 Worker의 NAT 등록은 공통 [`grafana_mcp`](../shared/python/src/agent_common/grafana_mcp.py)를 사용합니다. NAT 1.5.0의 기본 HTTPX 읽기 제한 5초 대신 HTTP 제한을 `tool_call_timeout + 5초`(예시 30 + 5초)로 맞춥니다. 실제 조회에는 기존 도구 timeout과 남은 작업 deadline도 적용되며 LLM timeout·JC lease·전체 deadline은 늘리지 않습니다. MCP 연결의 수명을 별도 task에서 관리하여 전송 실패의 취소가 Worker 실행 루프까지 전파되지 않도록 합니다. 실패한 조회를 재실행하지 않으며, 이후 별도 예산을 배정받은 호출에서 종료된 연결을 새로 열 수 있습니다. 서버의 세션 종료 404가 SDK의 `Session terminated` 오류로 전달된 경우에도 기존 연결을 정리하고 다음 호출에서 새로 연결합니다. 이 변경은 공통 전송 경로와 양 Worker 등록에 적용되며 RCA 계산·판단 정책은 변경하지 않습니다.

등록된 상태 해석 규칙이나 유효한 관측이 없으면 `no_usable_evidence`로 원인 Synthesis를 생략할 수 있습니다. 최종 보고서는 별도로 항상 구성하고 모델 편집을 시도하며, 미설정·확정 실패에는 코드 기본 보고서를 제공합니다. 원격 종료 불명은 기존 fail/격리 계약을 유지합니다. 로그 조회 성공과 장애 원인 분석 성공은 따로 확인합니다.

Grafana MCP 1.4.2의 Prometheus·Loki 시간 파서는 마이크로초 시각(예: `2026-09-21T02:34:41.713295Z`)을 거부할 수 있습니다. 두 Worker의 공통 수집기는 MCP 탐색·조회 요청 시각을 UTC 밀리초로 변환합니다. 시작은 올림, 종료는 내림하여 요청 범위를 넓히지 않으며 원본 Incident snapshot·해시·증거 시각을 유지합니다. Loki 조회 경계의 정밀도가 줄면 `quality.reason=time_precision_reduced`, `complete=false`, 실제 `request_time_range`를 기록하고 부분 근거로 처리합니다. 조회 성공·미잘림·경고 없음이면 `observation_usable=true`로 실제 요청 구간 안의 개별 health 관측을 RCA Synthesis에 사용할 수 있습니다. 기간 전체의 완전성·오류 부재·집계는 보장하지 않으며 다른 partial 사유는 제외합니다. 밀리초 단위 조회창이 남지 않으면 조회하지 않습니다.

LLM 통신 실패는 `LLM transport failed` 로그에서 `error_type`, `cause_type`, `stage`, 시도 번호, 경과 시간과 timeout을 확인합니다. HTTP 오류는 `LLM HTTP failed`와 상태 코드를 남깁니다. 이 진단 로그에는 API 키·프롬프트·응답 본문·원본 예외 메시지를 넣지 않습니다. 이후 연결 검사가 성공해도 기존 `inference_quarantined`는 자동 해제되지 않습니다. 원격 추론 종료를 확인한 뒤 [Job Controller 운영 해제 절차](../job-controller/README.md#추론-격리와-취소)를 따릅니다.

이 처리는 공유 Python 모듈에 있으므로 배포할 때 `rcca-agent`와 `ops-agent` 이미지를 함께 다시 빌드합니다.

## 모델 호출 timeout 조정

현재 저장소에서 출발점은 [chart values](../charts/gpu-ops-advisor/values.yaml)의 `llm.requestTimeoutSeconds`이며 기본값은 300초다. 이 값은 Worker의 `LLM_REQUEST_TIMEOUT_SECONDS`로 전달된다. 실제 요청 시간에는 작업의 남은 deadline도 적용되므로 이 값만 늘린다고 전체 작업 시간이 늘어나는 것은 아니다.

timeout은 모델에 보낸 요청의 통신 대기 제한, deadline은 분석 작업 전체의 마감 시간이다. Worker는 Agent 프로필의 `limits.deadline_seconds`와 JC가 준 `deadline_at` 중 먼저 끝나는 제한을 따른다. 모델 요청에 설정하는 timeout도 남은 시간보다 길게 잡지 않는다. 예를 들어 요청 timeout이 300초여도 전체 작업에 40초만 남았다면 그 요청 때문에 300초를 더 쓸 수 있는 것은 아니다.

1. [현재 협업 규칙](../docs/team-development.md)에 따라 변경 담당자를 지정하고 추가 리뷰가 필요하면 요청한다. 담당자는 두 Agent의 호출과 deadline·슬롯·격리 정책 영향을 검증하고, C-1/C-2·B에게 관련 내용을 공유한다.
2. 변경할 원본 설정, 실제 배포에 쓰는 override, 목표 시간, 적용·복구 순서를 작업 대화·Issue 또는 PR에 적는다. 외부 모델 서버·프록시·Ingress·LiteLLM 등을 사용하는 환경이라면 해당 설정을 소유한 별도 저장소·담당자도 기록한다. 이 저장소가 그 외부 설정까지 관리한다고 가정하지 않는다.
3. 사용자 요청·승인 범위에서 main 반영과 CI 발행을 마친 뒤 지정한 사람이 별도로 승인된 배포를 수행한다. 실제 Worker 설정값, RCA·보고서 작업의 ID·상태·소요 시간·결과 공개 여부와 슬롯 상태를 확인한다. HTTP 성공만으로 검증을 끝내지 않는다.
4. timeout 뒤 원격 추론의 종료가 불명확하면 슬롯이 격리될 수 있다. 이후 요청이 성공했다고 이전 격리가 해제된 것은 아니다. [추론 격리와 취소](../job-controller/README.md#추론-격리와-취소)에 따라 원격 종료를 확인한 뒤 처리한다.

연결이 끊겼다고 모델 서버의 계산까지 멈췄다고 단정할 수는 없다. 슬롯 격리는 “기존 계산이 끝났는지 모르니 이 자리를 바로 다른 작업에 내주지 말자”는 안전장치다. 설정을 바꾸거나 새 요청을 성공시키는 것과 기존 작업의 종료 확인은 별개다.

공유 기록 예시이며, 실제 적용 결과는 아니다:

```text
변경: 모델 요청 시간 상한 조정 (기존 값 → 합의한 값)
담당/리뷰(선택): 변경 담당자 / 요청한 경우 담당자, 미요청이면 표시
적용: 커밋·CI 실행·chart 버전, 대상 환경·namespace·release, values 위치
확인: 실제 설정값, RCA·보고서 작업 ID·상태·소요 시간, 결과·슬롯 상태
미확인: 실행하지 못한 검증, 후속 담당자와 기한
복구: 변경 전 버전·설정, DB 영향 여부, 복구 순서
```

## Windows 실행

저장소 루트의 PowerShell에서 실행합니다. Python 3.12와 NAT 1.5.0을 사용합니다.

```powershell
./agents/scripts/setup.ps1 -DownloadMcp
Copy-Item agents/.env.example agents/.env
```

모델 라우팅이 없는 작업은 기존 `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`와 단계별 모델 환경변수를 사용합니다. GUI에서 RCA/보고서 모델을 지정하면 두 Worker는 작업에 고정된 모델 revision의 주소·모델명·인증 참조를 사용하며 단계별 환경변수로 덮어쓰지 않습니다. `env:LLM_API_KEY`는 실행 환경의 키를 읽고 빈 참조는 인증 없는 서버용입니다. 지정된 revision·키가 없으면 작업을 실패시키며 다른 모델로 대체하지 않습니다. GUI 경로에는 `DSX_MODEL_HOSTS`·`DSX_MODEL_CIDRS` 검증, DNS IP 고정, 원래 Host/TLS SNI 및 redirect 차단을 적용합니다. Helm은 백엔드의 허용 설정을 두 Worker에 전달합니다.

`/chat/completions`의 300초 요청 상한, 기본 4096/설명 16384/insight 1024 토큰 설정과 JC attempt budget·deadline 제한은 유지합니다. 키는 코드·이미지·작업 본문에 넣지 않습니다. 모델 라우팅이 없고 환경의 모델/주소/키도 없으면 기존처럼 LLM 설명을 생략하고 유효한 결정적 결과는 유지합니다. [키 배포와 검증](../docs/model-connection.md).

기본 실행은 `agents/config.example.json`을 읽고 검토된 D02·D09를 자동 선택합니다. `AGENT_CONFIG_FILE`은 같은 계약을 따르는 전체 설정으로 대체할 수 있습니다. verified binding은 명시적 datasource UID 또는 discover 모드·고정 selector와 요청 cluster_id의 scope label을 사용합니다. 구 profile은 기존 Grafana MCP 탐색을 유지합니다. 작업 시간 범위에서 `cluster_id`, `cluster`, `k8s_cluster_name`, `kubernetes_cluster`, `k8s_cluster` 순으로 첫 번째 값이 있는 라벨을 사용하고 작업 cluster ID와 정확히 일치시킵니다. 중복 후보·라벨 부재·조회 오류는 evidence와 Worker 로그에 원인을 남기며 전체 데이터로 범위를 넓히지 않습니다. 탐색은 작업별 캐시, 64회 기본 호출 한도, 응답 크기·타임아웃·작업 deadline 제한을 적용합니다.

Mimir tenant와 인증은 기존 Grafana 데이터소스 설정을 사용합니다. Worker에 Mimir/Loki 직접 주소·계정을 주지 않습니다. 새 binding의 datasource UID는 Grafana에 등록된 UID입니다. Grafana 토큰에는 datasource 목록과 데이터 조회 권한이 필요합니다. `cpc-2`와 `cpc2` 같은 서로 다른 cluster ID는 자동으로 동일시하지 않습니다. 고급 환경의 명시적 매핑·생산자별 의미 계약이 필요하면 `AGENT_CONFIG_FILE`로 전체 프로필을 선택적으로 지정할 수 있습니다. C07 숫자는 예시이며 운영 확정값이 아닙니다.

```powershell
$env:GRAFANA_URL='https://your-grafana'
# GRAFANA_SERVICE_ACCOUNT_TOKEN은 로컬 환경에 설정
.local/mcp-grafana/mcp-grafana.exe -t streamable-http -address 127.0.0.1:8000 -enabled-tools datasource,prometheus,loki -disable-write -max-loki-log-limit 5000
```

별도 터미널에서 JC·DB를 먼저 준비하고 Worker를 실행합니다. `agents/.env`의 Docker 호스트명 대신 로컬 접속 주소를 사용합니다. `.env`는 CLI가 자동으로 읽지 않으므로 `uv run --env-file`을 사용합니다.

```powershell
$env:DATABASE_URL='postgresql://...@127.0.0.1:5432/dsx'
$env:JC_URL='http://127.0.0.1:8090/internal/v1'
$env:GRAFANA_MCP_URL='http://127.0.0.1:8000/mcp'
uv run --no-project --python .venv/Scripts/python.exe --env-file agents/.env -m rcca_agent.main
uv run --no-project --python .venv/Scripts/python.exe --env-file agents/.env -m ops_agent.main
```

위 두 Worker는 각각 별도 터미널에서 실행합니다. 한 건 처리 후 종료하려면 `--once`를 추가합니다. 운영 클러스터는 기존 Backend/JC의 `cluster_registry`에 등록되어 있어야 합니다. Agent는 등록·일정·사건 상태를 변경하지 않습니다.

## Docker 배포

루트 build context를 사용하고 `runaiRCA/agent/Dockerfile`과 같은 Python 3.12 다단계 빌드·가상환경 복사·UID 10001 실행 구조입니다.

```powershell
docker compose --env-file agents/.env -f agents/compose.yaml up --build -d
docker compose --env-file agents/.env -f agents/compose.yaml logs -f rcca-agent ops-agent grafana-mcp
```

Compose는 로컬 개발용 PostgreSQL·JC도 포함합니다. 기존 DB/JC 배포에 붙일 때는 두 Worker의 `DATABASE_URL`, `JC_URL` 및 volume을 맞춥니다. `GRAFANA_URL`은 기존 Grafana를 가리킵니다. 데이터소스 provisioning이나 운영 tenant를 임의로 변경하지 않습니다. 보고서 파일은 `agent-artifacts` volume에 저장됩니다.

이 환경에서는 사용자의 안내대로 Linux Docker 엔진 실행을 중단했습니다. **컨테이너 빌드/기동은 검증하지 않았고**, 실제 서버/Worker 연결은 Windows 프로세스 E2E로 검증했습니다.

## 대량 결과 저장과 heartbeat — 2026-10-02

공통 Store는 결과 검증·해시와 evidence별 JSON 인코딩/해시를 `asyncio.to_thread`에서 처리한다. evidence를 한 건씩 준비해 전체 직렬화 사본을 동시에 보관하지 않고, psycopg에는 인코딩된 bytes를 넘긴다. 기존 JSON 값과 Go 호환 checksum은 유지한다. 이 변경은 RCA·Ops 양쪽 저장 경로에 적용된다.

저장 시작에는 실행 유효성을 읽고, 대량 INSERT 동안 jobs/attempts의 명시적 공유 잠금을 유지하지 않는다. 커밋 직전에 jobs → attempt 순서로 잠근 뒤 실제 현재 시각(`clock_timestamp`)으로 claim_token·현재 attempt·lease·deadline·취소를 다시 확인한다. 무효하면 evidence와 candidate 전체를 롤백한다. JC의 최종 complete 검증과 동일 candidate/hash 재전송은 유지한다. 저장 중에도 Worker는 취소·lease 상실을 감시해 저장 task를 취소하고 DB rollback을 기다린다. 취소된 준비 스레드는 계산을 마칠 수 있지만 DB 저장·공개는 수행하지 않는다.

저장 성공 로그는 job ID·evidence 건수·`prepare_seconds`·`db_seconds`만 남긴다. 원본 snapshot·claim token·접속 정보는 출력하지 않는다. JC의 FK 호환 잠금 변경과 함께 반영해야 하며 JC를 먼저 반영한 뒤 두 Worker를 교체한다. lease 시간·공유 슬롯·원격 추론 격리 정책은 바꾸지 않는다. 기존 운영 격리는 자동 해제하지 않으며 모델 서버 종료 확인 후 [운영 해제 절차](../job-controller/README.md#추론-격리와-취소)를 따른다.

## 결과·관측 계약

- 결과 본문 `result_schema_version=1.1`, 현재 JC의 candidate 봉투 `schema_version=1.3`을 구분합니다. Go `encoding/json`과 호환되는 SHA-256을 사용하며 실제 JC complete에서 재검증합니다.
- 지표는 instant range-vector query로 원본 표본 시각을 보존합니다. 기간을 chunk로 나누고 계산에서 경계 중복·공백·최대 유효시간을 처리합니다. Loki는 행 제한 도달 시 `partial`, 실패는 `unavailable`, 빈 결과는 `empty`입니다.
- scope/namespace/대상/기간은 코드가 조립·검사합니다. LLM에는 쿼리 ID만 전달하며 임의 PromQL/LogQL/SQL/쉘이나 저장·완료 함수는 노출하지 않습니다.
- 보고서는 REPEATABLE READ에서 data cutoff, Incident, 공개된 RCA ID/hash, 실제 조치 기록을 고정합니다. RCA 원인 수준은 인용한 결과 수준을 유지합니다.
- 보고서 LLM 설명은 검증된 사실 ID 선택으로 제한하고 저장된 `value_refs`로 렌더링합니다. RCA Synthesis는 수집이 끝난 뒤 도구 없이 근거 참조가 있는 원인 후보·한계를 생성합니다. 자유 문장의 숫자는 거부하고 모델의 인과 수준은 candidate로 제한합니다. 참조·형식 검증이 모델 문장 의미의 진실성을 보장하지는 않습니다.
- RCA는 승인 Runbook 계획의 query를 병렬 실행하며 `limits.max_concurrency` 기본값은 3입니다. 최대 1회 재조사 후 Synthesis하고, 조회 실패·부분 수집은 degraded로 남깁니다. 전용 Runbook 미일치는 `rca.general_runbook_key`의 승인 발행본으로 대체하며 일반 발행본까지 없으면 조사하지 않습니다. [RCA 실행 안내](../rcca-agent/README.md)와 [보완 계획](../docs/specs/rca-agent/implementation-plan-20260928.md)을 따릅니다.
- timeout/cancel 이후 추론 종료가 확인되지 않으면 `remote_call_state=unknown`으로 fail을 보내 JC의 격리 정책에 맡깁니다. 저장 실패는 succeeded가 아닙니다.
- Agent는 HTML·CSV 파일과 checksum을 저장합니다. Backend 다운로드 API는 발행된 결과에서 HTML 표와 항목별 CSV를 렌더링하며 새 조회·분석은 하지 않습니다. HTML escape와 CSV 수식 방어를 적용합니다. 화면 상단의 HTML·CSV 다운로드 버튼으로 받을 수 있습니다.

## 배포 입력이 필요한 부분

코드가 모든 R/O ID를 받아 주제별 결과와 부족 입력을 반환하지만, 실제 생산자 의미를 추정하지 않습니다. 다음 입력이 없으면 해당 판단은 `partial/blocked` 또는 null입니다.

- 새 profile의 `D02`(구 profile의 `D08`)는 `DCGM_FI_DEV_GPU_UTIL`의 Pod 라벨을 사건 구간의 D06 `kube_pod_info`와 연결하는 **관측 관계**입니다(`allocation_semantics=observed_pod_labels`). 값 0도 관측된 연결일 수 있지만 Pod/namespace가 없거나 UID가 중첩되면 관계를 만들지 않습니다. 노드가 있으면 D06과 해당 관측 query를 해당 노드로 제한합니다. 원본 시각과 최대 유지시간의 교집합만 사용합니다.
- 이 기본 관측 연결은 Ops의 독점/공유 할당량·할당 episode를 증명하지 않습니다. 실제 정규화 할당 producer를 배포한 환경은 검증된 구 D08 override를 유지하거나 별도 할당 D의 소비 계약을 확정하고 `allocation_mode`, `allocation_episode_key`, MIG 신원을 검증해야 합니다. episode가 없으면 장시간 저활동 후보를 만들지 않습니다.
- 새 profile은 D09에서 상태를 파싱합니다. 구 profile에서 D05는 D09의 파생 보기입니다. 같은 수집 라운드에서 Loki는 한 번 조회하며 원본 근거 ID를 `quality.derived_from`에 보존합니다. 같은 클러스터·시각·로그·해석 계약의 관측은 한 번 세고 근거 참조를 합칩니다. `DCGM_FI_DEV_XID_ERRORS`의 사건 구간 존재와 의미를 확인하지 못해 기본 원천으로 채택하지 않았습니다.
- O02·O08은 이 정규화 metric이 없어도 DCGM 활용률(새 D02, 구 D01)과 `kube_pod_info`(D06)의 동시 구간을 연결해 관측 GPU 수, GPU–Pod 연결 관측 시간, Namespace별 연결 관측 시간을 산출합니다. 같은 이름의 Pod UID가 중첩되는 구간은 제외합니다. 이 수치는 독점 할당량·실제 연산 시간과 구분하며 공유 GPU의 Namespace별 시간을 합산해 전체 할당량으로 사용하지 않습니다.
- Prometheus 원본 표본 수 또는 응답 크기가 한도를 넘으면 시간 구간을 자동으로 줄여 다시 조회합니다. `max_queries`와 실행시간 한도는 재조회에도 적용되며, 끝내 수집하지 못한 구간·원본 경고는 부분 수집으로 남깁니다. 결과의 주제별 관측 품질에는 조회별 상태와 표본 수가 저장됩니다.
- `D07`의 `gpu_ops_effective_unbound_request` 역시 검증된 recording rule/원본으로 교체해야 합니다. scheduler 버전별 effective request 규칙, terminal/binding, resource 단위를 확인해야 합니다.
- Fleet 상태는 `health_contracts`에 producer별 `checks`/`health`/revision 매핑을 등록한 JSON에만 의미를 부여합니다. 원본 여러 incidents 항목을 각각 보존합니다. 미등록 상태는 unknown입니다.
- 토폴로지, 현재 조치 범위, 정책·정상 관측 기간, 실제 작업 중단/재개 증거가 없는 R04/R07/R08/R09를 확정하지 않습니다. reset 안전·업무 복구를 자동 판정하지 않습니다.
- 전체 기대 대상/관측 분모가 없는 전체 커버리지·발생률·순위, 검증된 scheduler 제약이 없는 GPU 부족량, 업무량 비교가 없는 조치 인과 효과는 보류합니다.

## 테스트

```powershell
./agents/scripts/test.ps1
./agents/scripts/test.ps1 -E2E -PgBin ./backend/.local/postgres/bin/bin
```

E2E는 Windows PostgreSQL 바이너리와 Go가 필요합니다. 스크립트는 Backend·JC·Incident를 빌드합니다. `PG_BIN`, `BACKEND_BINARY`, `JC_BINARY`, `INCIDENT_BINARY`, `GRAFANA_MCP_BINARY`로 경로를 변경할 수 있습니다. 실제 Incident 웹훅 → outbox → JC → RCA Worker → 결과 발행 경로를 포함하며, 이 테스트는 snapshot을 DB에 직접 삽입하지 않습니다. 별도 legacy snapshot/Runbook 사례도 유지합니다. 오류별 Runbook 3건의 Backend 등록·검토·발행·RCA 소비 사례도 포함합니다. 등록 절차는 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)를 따릅니다. 테스트마다 별도 PostgreSQL data directory/포트를 만들고, 생성한 서비스만 종료합니다. 로그·출력은 gitignore 대상 `.local/agent-e2e/`에 남깁니다. 자세한 검증 결과는 [QA.md](QA.md)입니다.

공유 E2E DB는 stack의 JC가 기동하면서 공통 migration을 먼저 적용합니다. 이후 테스트별 Backend는 `DSX_MIGRATE=false`로 실행해 준비된 schema를 재사용합니다. 실행 중인 JC의 작업 갱신과 Backend의 반복 `ALTER TABLE`이 교착되지 않도록 하는 테스트 설정이며, Backend 자체 migration 검증은 별도 Backend DB E2E에서 유지합니다.

기술 확인 근거: [NAT MCP client](https://docs.nvidia.com/nemo/agent-toolkit/1.5/build-workflows/mcp-client.html), [NAT custom functions](https://docs.nvidia.com/nemo/agent-toolkit/1.5/extend/custom-components/custom-functions/functions.html), [공식 Grafana MCP](https://github.com/grafana/mcp-grafana/tree/v1.4.2).
