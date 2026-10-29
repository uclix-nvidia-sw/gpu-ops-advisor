# Incident 모듈 · Go · 기본 firing 접수 1.5 / 선택적 에피소드 접수 1.4

## R 없는 기본 접수 — 2026-10-02

기본 firing 접수 경로는 입력 계약 1.5를 사용한다. `purpose_ids`를 보내지 않으며 RCA가 Runbook으로 계획한다. 기존 알람 정책은 접수 대상과 최초 snapshot의 정책 revision을 정하는 데 사용한다. 기본 정책 revision은 `gpu-alert-runbook-v1`이다. 기존 설정의 `purpose_ids`는 읽기 호환만 유지하며 새 요청에는 전달하지 않는다. `episode_policy`의 1.4 생명주기는 그대로다. 아래 이전 R01/R02 설명은 1.3 과거 기록이다.

새 JC·Worker를 먼저 배포해야 한다. 신규 1.5 요청은 구형 Worker에 배분되지 않는다. 기존 outbox·snapshot·hash는 재작성하지 않고 원래 계약으로 전송한다. 기본 접수는 정책 revision이 바뀌어도 같은 알람 발생 구간의 RCA를 추가 생성하지 않는다. 이번 작업은 로컬 코드이며 운영 설정·DB를 변경하지 않는다.

## 분석 구간 밀리초 경계 (2026-10-01)

새 RCA 입력 `time_range`의 시작은 밀리초 올림, 끝은 밀리초 내림으로 저장한다. `incident_time`과 `received_at`은 원래 정밀도를 유지한다. Grafana MCP는 밀리초 RFC3339만 받으므로 수신 시각 `now`의 마이크로초가 끝 경계에 남으면 Loki 조회(D05·D09)가 매번 꼬리 1ms 미만을 잃고 `time_precision_reduced`/partial이 되어 RCA 충분성이 `degraded`로 떨어졌다(운영 작업 `ed730b4d`: 끝 `02:29:46.513252Z` → 요청 `.513Z`). 안쪽으로만 반올림하므로 승인 구간을 넓히지 않는다. 기존 snapshot/hash는 재작성하지 않고 새 사건부터 적용한다. DB migration 없음.

## Fleet target 투영 호환 (2026-09-30)

새 RCA 입력 target에 label의 `machine_id/component/k8s_node_name`을 보존하고 노드명은 annotation fallback도 지원한다. 노드 label/annotation 충돌은 `conflicting_node_name`으로 거부한다. 과거 1.3 event key와 evidence hash는 저장된 값을 보존하며, 현재 기본 접수의 중복 기준은 아래 발생 구간 정책을 따른다. 투영만 추가된 반복 alert는 새 incident/outbox/snapshot을 만들지 않으며 기존 snapshot/hash/target을 소급 변경하지 않는다. episode 모드도 공통 parse 투영을 재사용한다. DB migration은 없다.

이 target은 수신 단서다. RCA에서 관측의 동일 대상·시각 의미·freshness를 검증해야 fact로 쓸 수 있다. [RCA 실행 계약](../rcca-agent/README.md)을 따른다.

[13번 설계서](../docs/specs/incident/13_Incident_모듈_설계서.md)를 기준으로 개발하는 독립 프로세스입니다. 기본 접수는 1.5이며, 1.4 에피소드 생산 경로는 소비자 업그레이드 후 설정으로 전환합니다.

**Grafana → Incident → PostgreSQL outbox → Job Controller → RCA Agent** 흐름을 사용합니다. Backend는 같은 DB에서 사건과 연결된 RCA job을 읽고, 메모·검토·사건 상태 변경만 Incident로 전달합니다. 인증은 현재 범위에서 제외했습니다.

## 실행

Go 1.26와 PostgreSQL을 사용합니다. Docker가 없어도 저장소 루트에서 각각 별도 터미널로 실행할 수 있습니다.

```powershell
./backend/scripts/dev-db.ps1
./job-controller/scripts/dev-server.ps1
./incident/scripts/dev-server.ps1
./backend/scripts/dev-server.ps1
```

기본 Incident 주소는 `http://127.0.0.1:8091`입니다. Backend 개발 스크립트에 `DSX_INCIDENT_URL=http://127.0.0.1:8091`을 추가했습니다. 이미 실행 중인 Backend에는 다음 재시작 때 반영됩니다. 이 모듈 구현 과정에서 기존 Backend/JC 프로세스는 강제로 재시작하지 않습니다.

세 모듈의 `DATABASE_URL`은 같은 DB를 가리켜야 합니다. 공통 스키마에 `004_incident.sql`을 추가했으며 Incident가 자신의 마이그레이션과 운영 정책 등록을 수행합니다. JC의 queue 테이블은 변경하지 않습니다. cluster_registry는 Backend 초기화/운영 등록을 사용합니다.

`.env.example`은 환경 변수 예시이며 자동으로 읽지 않습니다. 기본값은 개발용 정책입니다. 운영 설정은 `INCIDENT_CONFIG_FILE`에 `config.example.json` 형식의 파일 경로를 지정합니다. `INCIDENT_APPLY_CONFIG`는 미지정 시 `true`이며 시작할 때 전달한 설정을 DB에 적용합니다. 모든 Incident 복제본의 설정을 맞춥니다. 이전 설정의 프로세스는 503으로 차단됩니다. 자동 적용을 끄려면 `INCIDENT_APPLY_CONFIG=false`를 명시합니다.

정책 revision의 내용은 불변입니다. 조사 목적·증거 필드 등을 바꿀 때 새 revision ID를 사용합니다. JC 주소만 바꿀 때는 `INCIDENT_JOB_CONTROLLER_URL`을 사용할 수 있지만 이것도 운영 설정 revision 변경에 해당합니다.

## 에피소드 업그레이드 · 선택적 1.4

2026-09-23에 Incident 생산 경로와 추가 migration `005_incident_episodes.sql`을 구현했습니다. **JC·Agent를 포함한 1.4 통합 배포 검수는 아직 완료하지 않았으므로 운영에서는 `episode_policy`를 생략합니다.** 아래 설정은 호환 소비자 검수 후 전체 Incident 설정에 추가하는 시험 예시입니다. 60/120초는 시험값이며 운영 기본값이 아닙니다.

```json
{
  "episode_policy": {
    "revision": "fleet-episodes-v1",
    "repeat_interval_seconds": 60,
    "observation_gap_seconds": 120
  }
}
```

- `episode_policy` 생략/null: 아래 기본 firing 단일 접수 경로. 객체 지정: 1.4 에피소드 경로. `revision`과 실제 Grafana 반복 주기를 명시하며 K ≥ 2 × repeat_interval이어야 시작합니다. 정책 내용을 바꾸면 새 revision을 사용합니다. 기존 에피소드의 K와 최초 snapshot은 유지합니다.
- 완전한 신원은 source/cluster_id/machine_id/component로 묶습니다. reason·fingerprint가 다른 알람도 같은 연속 구간에서는 사건과 최초 RCA가 하나입니다. machine_id/component가 부족하면 생명주기별로 격리하고 `identity_incomplete`를 보존합니다. 그룹 키는 2,000바이트 이하입니다.
- 1.4의 `k8s_node_name`은 labels에서 읽고 없으면 annotations를 사용합니다. 양쪽 값이 다르면 `conflicting_node_name`으로 거부합니다. 이 표시 이름으로 machine/GPU 신원을 추정하지 않으며 원문·hash와 기존 1.3 dedup은 유지합니다.
- snapshot은 revision=1, 요청 키는 `incident:<id>:first`입니다. 신규 입력에는 `purpose_ids`, `analysis_profile_revision`을 넣지 않습니다. GPUAlert 외 이름도 접수하며 DatasourceNoData/DatasourceError는 별도 사건으로 기록하고 `analysis_excluded`로 분석을 생략합니다.
- 동일 bytes의 반복 수신도 그룹당 요청 1회씩 관측 카운트를 늘립니다. 원문·receipt·snapshot은 중복 생성하지 않습니다. `last_observed_at`은 서버 수신 시각이며 원천 로그 건수나 장비 정상 여부를 뜻하지 않습니다.
- gap > K일 때 관측 종료를 판정합니다. 조회는 경과 시간을 반영하고 수신/PATCH에서 종료를 영속화합니다. 일부 생명주기의 resolved는 전체 사건 해제가 아니며, resolved 선접수와 이미 해제된 생명주기의 늦은 firing은 사건/RCA를 만들지 않습니다.
- 명시적 closed는 종료와 `closed_at`을 기록합니다. 이미 종료된 관측의 시각·사유는 보존하며, 종결한 에피소드는 다시 열지 않습니다. 종료 후 과거 bytes·문구 변경만으로 재발을 만들지 않습니다. 새 시작/검수된 발생 시각이 있어야 새 사건을 만들고, 직전 검토가 open/acknowledged이면 `prior_analysis_open`으로 RCA를 생략합니다.
- `annotations.occurred_at`은 Fleet 시각 형식 또는 RFC3339로 파싱합니다. 생산자 의미·갱신 계약을 검수한 뒤에만 `occurred_at_contract_revision`을 설정합니다. 미검수·누락·파싱 실패는 startsAt 기준이며, 검수된 발생 시각의 나이/미래 범위 위반은 invalid입니다. 원문·파싱값·선택 사유와 절대 조회창을 최초 snapshot에 고정합니다.

신규 조회 필드는 `source`, `fingerprint`, `starts_at`, `dedup_group`, `episode_started_at`, `last_observed_at`, `observation_count`, `observation_gap_seconds`, `ended_at`, `ended_reason`, `closed_at`, `prior_incident_id`, `observation_status`입니다. legacy 에피소드 필드는 null입니다. 내부 PATCH envelope는 계속 1.3이며 Backend·Frontend의 상태 표시와 Ops 집계 전환은 후속 개발 범위입니다.

### 적용 순서와 복구

1. Incident 시작 시 005의 추가 열·생명주기 테이블·부분 유일 인덱스를 적용합니다. 기존 snapshot/hash/event_key/outbox는 변경하지 않습니다. 운영 적용 전 담당자가 백업과 DB 변경 시간을 정합니다.
2. JC의 1.3/1.4 검증·Worker 지원 계약 배분, RCA의 목적 선택, Backend/Frontend/Ops 소비를 먼저 구현·검수합니다. 기본 config.example.json과 Helm 미러는 이 단계까지 1.3을 유지합니다.
3. 기존 Incident 복제본을 정지·drain한 뒤 운영의 실제 repeat/K·시각 계약을 반영한 전체 설정으로 전환합니다. Helm `configuration.incident`는 전체 객체 교체입니다. 원본 설정과 Helm 미러의 기본 전환은 소비자 개발 단계에서 함께 수행합니다.
4. 1.4 준비 단계에서 과거 원장을 생명주기에 연결합니다. 같은 생명주기가 여러 기존 사건에 귀속되면 시작을 거절하고 자동 병합하지 않습니다. 과거 정책 미등록 사건도 backfill하지 않습니다. 기존 pending은 원래 1.3 envelope로 계속 전달합니다.
5. 새 생명주기를 기록한 source를 1.3 생산자로 되돌리는 시작은 거절합니다. 문제 발생 시 신규 수신을 멈추고 호환 생산자로 전진 수정하며 pending을 보존합니다. SQL 삭제·snapshot 변환·PVC 재생성으로 복구하지 않습니다. DB 백업 복원은 별도 운영 절차로 검수해야 합니다.

현재 수신 쓰기는 기존 전역 트랜잭션 잠금을 유지하고 정렬한 그룹 잠금·생명주기·에피소드 순서로 처리합니다. 수신량이 커지면 전역 잠금 제거를 별도로 검토합니다. [검증 기록](QA.md)은 실제 PostgreSQL/기존 JC 검사와 1.4 테스트 수신기 검사를 구분합니다.

### 기본 firing 단일 접수 배포

DB 스키마 migration이나 기존 데이터 일괄 수정은 없습니다. 기본 생산자의 config revision에 `firing-once-v1`을 포함해 구·신규 생성 정책 혼용을 차단합니다. 모든 Incident 복제본을 새 버전으로 교체하고 `INCIDENT_APPLY_CONFIG=true`로 새 revision을 적용합니다. 자동 적용을 끈 환경은 승인된 설정 적용을 먼저 수행해야 하며 구 replica를 다시 시작해 revision을 되돌리지 않습니다. 기존 snapshot·보고서·pending outbox는 보존합니다. 과거 누락분 일괄 생성은 포함하지 않습니다. 롤백하면 구 중복·resolved 차단 정책도 돌아오므로 수신을 중지한 상태에서 버전·설정을 함께 전환해야 합니다.

Grafana가 firing만 보내도 새 `startsAt`은 새 사건입니다. 동일 fingerprint/startsAt은 한 발생 구간이며, 별도 resolved 수신을 재발 조건으로 요구하지 않습니다. 해제 알림이 없다는 이유로 장애 지속이나 복구를 판단하지 않습니다. 선택적 `episode_policy` 경로는 기존 관측 에피소드 계약을 유지하며 이 정책의 대상이 아닙니다.

## Grafana 연결

Grafana Contact point에서 Webhook, HTTP POST, URL을 **Incident의 `/webhooks/grafana`**로 설정합니다. 로컬 테스트 URL은 `http://127.0.0.1:8091/webhooks/grafana`입니다. Grafana가 다른 서버/컨테이너라면 그 환경에서 도달 가능한 Incident 주소를 사용해야 합니다. Backend 주소로 보내지 않습니다.

[Grafana 공식 Webhook payload](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/webhook-notifier/)의 기본 JSON을 받습니다. 커스텀 payload를 쓰면 alerts 배열과 각 alert의 필수 필드를 유지해야 합니다. 본문에 있는 externalURL 등 외부 링크를 서버가 방문하지는 않습니다.

필수 자식 필드: `fingerprint`, `status=firing|resolved`, timezone이 있는 `startsAt`, `labels.alertname`, `labels.cluster_id`. resolved는 유효한 `endsAt`도 필요합니다. namespace 라벨이 있으면 해당 Namespace 범위, 없으면 해당 cluster 전체 범위입니다. `cluster_id`는 활성 cluster_registry 항목이어야 합니다. cluster 라벨명은 설정으로 변경할 수 있습니다.

개발 기본 분석 정책은 **alertname=GPUAlert**만 처리하며, 목적은 R01/R02입니다. 실제 Grafana 규칙의 alertname에 맞춰 analysis_policies를 등록하세요. 등록 정책이 없는 알람도 사건으로 저장하지만 `analysis_policy_unconfigured` 사유로 RCA는 만들지 않습니다. Grafana의 일반 Test notification도 필수 라벨이 없으면 invalid로 보존되며 실제 사건을 만들지 않습니다.

GPU UUID는 입력 라벨에 있을 때만 보존합니다. node/pod/namespace 등 확인된 대상만 사용하며 누락된 식별자를 생성하지 않습니다.

### Grafana 알림 규칙

[grafana/alert-rules.yaml](grafana/alert-rules.yaml)은 Fleet Intelligence 로그(`job="fleet-intelligence-agent"`)로 Incident에 알림을 보내는 Grafana 관리 규칙 정의다. 설치 환경의 Grafana에 직접 적용해야 하며, 차트 배포가 규칙을 만들지는 않는다.

| uid | 알림 이름 | 입력 | Incident 처리 |
|---|---|---|---|
| `gpuops-xid-sxid-state` | `GPUAlert` | XID·SXID 상태 줄(`log_type=component_data`) 중 `health=Unhealthy`/`Degraded` | 사건 + RCA |
| `gpuops-xid-sxid-rca` | `GPUAlert` | Fleet 이벤트 줄(`log_type=event`, `error_xid`/`error_sxid`) 중 Fatal·Critical이 아닌 모든 코드(Warning·Info 등) | 사건 + RCA |
| `gpuops-component-rca` | `GPUAlert` | XID·SXID를 뺀 모든 Fleet 컴포넌트의 상태 줄 중 `health=Unhealthy`. 컴포넌트 Runbook이 없으면 일반 GPU 노드 Runbook으로 분석 | 사건 + RCA |

- Fleet은 카탈로그 event_type이 Fatal인 코드를 Unhealthy, Critical을 Degraded로 바꾸고, 상태 줄을 1분마다 다시 기록한다. 이벤트 줄은 오류 1건에 한 번만 기록되며, 내보내기 전에 SetHealthy가 실행되면 지워지고(`eventBucket.Purge`) 내보내기에서 빠질 수도 있다. 그래서 상태를 바꾸는 코드는 반드시 상태 규칙으로 받는다. 2026-10-23 운영에서 이벤트 줄만 보던 규칙이 dgx01 SXID 11001(상태는 Unhealthy)을 25분간 놓쳐 이 구성으로 바꿨다.
- 이벤트 규칙은 상태를 바꾸지 않는 코드만 맡는다. Fatal·Critical을 이벤트로도 받으면 라벨이 달라 같은 오류에 사건과 RCA가 두 번 생긴다. 이벤트 줄은 `code`(`xid:79`, `sxid:11001`)·`device`·`event_type`·`reason`(본문) 라벨을 만든다.
- XID·SXID 284종 모두 Runbook이 있어 코드를 고르지 않고 모두 RCA로 보낸다. 애플리케이션 오류가 많은 XID 13·31·43 등도 RCA가 되므로 공유 클러스터에서는 RCA 건수가 늘 수 있다. `tools/ci/tests/test_alert_rules.py`가 규칙 간 역할 분리, 모든 규칙의 `GPUAlert` 이름과 [Runbook 매니페스트](../rcca-agent/runbooks/catalog-manifest.json)의 Fleet 분류를 검사한다.
- Loki 조회가 실패하면 `execErrState: KeepLast`로 직전 상태를 유지해 조회 오류가 사건이 되지 않게 한다.
- 적용: `${GRAFANA_ORG_ID}`, `${GRAFANA_FOLDER}`, `${LOKI_DATASOURCE_UID}`, `${GPU_OPS_CONTACT_POINT}`(Incident Webhook 연락 지점 이름)를 채운 뒤 Grafana 파일 provisioning(`provisioning/alerting/`)이나 provisioning API로 만든다. 예: `envsubst < incident/grafana/alert-rules.yaml > gpu-ops-alert-rules.yaml`.
- 이벤트 규칙의 창은 10분이다. Fleet이 이벤트를 주기적으로 내보내 Loki 도착이 늦을 수 있고, 창이 평가 주기(1m)와 알림 정책 group_wait(기본 30s)보다 길어야 firing 알림이 먼저 전달된다. 이벤트 알림은 창이 지나면 해제되지만 RCA는 firing 수신 시점에 만들어진다.
- 남은 위험: 상태를 바꾸지 않는 코드는 이벤트 줄로만 받을 수 있어 이벤트가 지워지거나 내보내지지 않으면 놓친다. 이전의 상태 줄 규칙만으로는 이 코드들을 전혀 받지 못했으므로 그보다 나빠지지는 않는다. 같은 장치의 같은 오류가 Unhealthy 동안 반복되면 상태 줄 사유가 같아 새 사건 없이 기존 알림이 이어진다.
- 한계: Fleet·GPUd 카탈로그 밖 코드(XID 133, SXID 93개 외)는 Fleet이 버려 알림이 생기지 않는다. row remapping을 지원하는 GPU(Ampere 이후)에서 Fleet은 kmsg의 XID 63·64를 버린다. Fleet 로그는 `remapped-rows` 컴포넌트에 맡긴다고 쓰지만 그런 컴포넌트는 없고, 같은 고장은 DCGM 메모리 컴포넌트(`accelerator-nvidia-dcgm-mem`, 행 재매핑)로 받는다. 컴포넌트의 Degraded는 받지 않는다(예: 상시 Degraded인 전력 컴포넌트). 2026-10-23 운영 Grafana 적용 뒤 kmsg 주입으로 XID 79·48(이벤트 줄), disk(컴포넌트 상태), SXID 11001(상태 규칙)이 사건·RCA까지 이어지는 것을 확인했다.

## 수신·증거·전달 정책

아래 정책은 기본 1.5 firing 접수 경로입니다. 1.4는 위 에피소드 정책을 따릅니다.

- alerts 배열 전체를 한 DB 트랜잭션으로 처리합니다. 잘못된 자식은 위치·이유·원문으로 보존하고 다른 정상 자식은 접수합니다. 정상 JSON인데 alerts 배열 자체가 잘못된 요청은 receipt와 함께 422, JSON 문법/인코딩 오류는 400, 본문·배열 한도 초과는 413입니다.
- 같은 source/원본 body SHA-256은 같은 receipt를 반환합니다. 기본 경로는 재수신된 유효 firing의 미접수 여부를 재확인하므로, 과거 차단된 알람도 현재 적격이고 요청 이력이 없으면 한 번 접수합니다. 기존 receipt 응답·원문은 변경하지 않으며 처리 현황은 사건 상세에서 확인합니다. alert별 원장도 source/cluster/fingerprint/startsAt/payload hash로 중복을 막습니다. 정확한 webhook 바이트는 raw_body, 조회용 원문은 raw_payload에 보존합니다. PostgreSQL JSON이 표현하지 못하는 NUL이 포함된 자식은 encoded JSON으로 보존합니다.
- truncatedAlerts가 있으면 `grafana_truncated_alerts` 경고를 반환합니다. 받지 못한 알람을 정상/해제로 추정하지 않습니다.
- 기본 사건 신원은 `source/cluster_id/fingerprint/startsAt`입니다. 같은 발생 구간의 대상 보강·내용·정책 변경은 새 사건이나 RCA를 만들지 않습니다. 기존 target 기반 사건 키는 알람 원장으로 찾아 재사용하며 저장된 키·snapshot·hash는 바꾸지 않습니다.
- 기존 사건과 Namespace 범위가 다른 입력은 `identity_conflict`로 기록하고 RCA를 요청하지 않습니다. 이후 원래 범위의 적격 firing은 최초 요청을 만들 수 있습니다.
- 적격 firing에 대해 해당 발생 구간의 RCA outbox가 없을 때만 최초 요청을 만듭니다. 대기·접수·실패 outbox 모두 중복 방지에 포함합니다. 증거 선택 필드는 설정·과거 snapshot 읽기 호환으로 유지하며, 내용이나 정책 revision 변경으로 재분석하지 않습니다. 실행 실패는 기존 JC 재시도 정책을 따르며 반복 알림으로 새 작업을 만들지 않습니다.
- resolved 알림은 보존만 하고 작업을 만들지 않습니다. firing은 저장된 resolved/closed 상태와 무관하게 최초 RCA 요청을 만들 수 있습니다. 24시간보다 오래된 알람·아직 미래인 알람·정책 미등록 알람의 기존 제외 조건은 유지합니다. 허용된 시계 오차보다 미래인 timestamp는 invalid입니다. 기간·한도는 설정할 수 있습니다.
- 사건 state와 alarm_status는 분리됩니다. Grafana resolved는 alarm_status만 바꾸고 사건을 resolved/closed나 장비·업무 회복으로 자동 판정하지 않습니다. 같은 생명주기의 늦은 firing은 resolved를 되돌리지 않습니다.
- snapshot에는 완전한 RCA input과 원본 alert·정책을 고정하고 hash를 저장합니다. JC는 input·snapshot·hash를 실제 검증합니다. 신규 source_key는 `incident:<id>:first`이며 입력 계약은 1.5입니다. 과거 revision/profile 키의 outbox도 이미 요청한 것으로 간주하고 원래 envelope로 전달합니다.
- RCA는 snapshot의 `alert`를 원본 증거로 읽으며 이미 저장된 snapshot을 변환하거나 hash를 다시 쓰지 않습니다. 실제 RCA 실행까지의 회귀 검증은 [Agent 통합 테스트](../agents/tests/test_e2e.py)의 Grafana webhook 경로에 포함됩니다.
- 5초 전달 루프는 자기 outbox 행만 잠그고 같은 envelope로 재전송합니다. JC 응답 유실·기한 경과 시 receipt를 먼저 확인합니다. JC가 내려가 있어도 Webhook은 로컬 영속 저장 후 202를 반환합니다. 마감 뒤 JC receipt 조회마저 실패하면 pending을 유지합니다.
- RCA Agent가 없으면 JC 접수는 queued입니다. 실제 GPU 조사·LLM 추론을 Incident가 수행하지 않습니다.

## API

| API | 설명 |
| --- | --- |
| POST /webhooks/grafana | 202 영속 접수, receipt_id/items/invalid_alerts/warnings |
| GET /internal/v1/incidents | scope(JSON), state, limit(1~100), cursor |
| GET /internal/v1/incidents/{id} | 사건·불변 evidence_versions·outbox/job 연결 |
| PATCH /internal/v1/incidents/{id} | Backend 계약 envelope를 통한 메타데이터 변경 |
| GET /internal/v1/health/live | 프로세스 생존 |
| GET /internal/v1/health/ready | DB·마이그레이션·운영 설정·전달 구성 준비 |

Backend의 PATCH `/api/v1/incidents/{id}`는 `memo`, `review_status=unreviewed|reviewing|reviewed`, `state=open|acknowledged|closed`를 받습니다. `If-Match`와 `Idempotency-Key`가 필요하며 같은 재전송은 최초 버전으로 처리합니다. 내부 envelope는 `{contract_version:"1.3",source_module:"backend",input:{...}}`입니다. resolved는 정상 관측에 따른 별도 회복 판정이 필요하므로 수동 PATCH로 허용하지 않습니다. 메모·검토 변경은 RCA 실행 부수 효과가 없습니다.

ready는 JC의 일시 장애 때문에 수신을 중단하지 않습니다. 전달 장애는 outbox 상태와 last_error로 확인하며, GUI의 분석 결과 완료 여부와 구분합니다.

## 검증·배포

```powershell
./incident/scripts/format.ps1
./incident/scripts/test.ps1 -E2E
```

E2E는 실제 PostgreSQL의 고유 임시 schema, 실제 JC HTTP 서버, 별도 포트의 실제 Backend 바이너리를 사용합니다. 실행 중인 개발 Backend/JC와 데이터·포트를 격리합니다. Grafana 서버 자체와 실제 RCA/LLM은 실행하지 않고 기본 Webhook payload 및 Worker 프로토콜로 연동을 검증합니다.

Docker가 있는 환경에서는 저장소 루트에서 다음 명령을 사용할 수 있습니다.

```powershell
docker build -f incident/Dockerfile .
docker compose -f backend/compose.yaml -f incident/compose.yaml up --build
```

이 PC에는 Docker가 없어 이미지 빌드/컨테이너 실행은 검증하지 않았습니다. [검증 기록](QA.md)을 참고하세요.
