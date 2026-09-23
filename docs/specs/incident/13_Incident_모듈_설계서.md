# 13. Incident 모듈 설계서

현행 구현 계약 1.3 · 변경 목표 RCA 접수 계약 1.4 · 모듈 incident · F02/F03

## 0. 변경 기준과 구현 상태

2026-09-22 설계 변경, 2026-09-23 알람 소스와 사건 단위 확정. **Incident는 입력의 구조 파싱, 알람 중복 제거, 최초 증거의 영속 전달을 담당하고, RCA Agent가 값의 의미 해석·조사 목적·Runbook/일반 로그 분석 경로를 결정한다.** 아래는 추가 개발 기준이며 이번 변경은 문서에만 적용한다.

현재 코드는 `alertname`에 `analysis_policies`를 매칭하고 기본 `GPUAlert`에 R01/R02를 지정한다. Xid/SXid 코드 의미를 분석하는 로직은 현재도 Incident에 없다. 정책 미등록 시 RCA 미생성, 의미 있는 증거/정책 revision 변경 시 새 RCA 생성 동작은 목표에서 제거한다. 실제 전환은 [14 실행 계약](../common/14_모듈간_호출과_공통실행_계약.md)을 따른다.

이번 개정으로 사건 단위를 **알람 생명주기에서 관측 에피소드로 변경**한다. 이유는 §2.1에 있다. 기존 1.3 사건과 event_key는 그대로 보존하고 신규 경로에만 적용한다.

| 미정 항목 | 확정 전 처리 |
|---|---|
| Grafana 알림 정책의 `repeat_interval` | §2.2의 `observation_gap_seconds`를 확정하지 못함. 설정값으로 노출하고 기본값을 배포 전에 검수 |
| `reason` 문구의 변동값 포함 여부 | §1.1의 라벨/annotation 배치를 배포 전에 실측으로 확인 |
| `component` 값 전체 목록·발생 시각 갱신 계약 | 실측으로 확인. 신원 부족은 생명주기별 격리, 종료 후 새 증거가 없으면 재발 판정 보류 |

미정 값에 기본값을 채워 배포하지 않는다. 확정 전에는 해당 판정을 보류로 둔다.

### 0.1 후속 개발을 위한 코드 대조

2026-09-23 · 코드 대조 기준 `d391f3d`. §1~§5의 에피소드 설계를 현재 구현으로 읽지 않도록 아래에 출발점과 검수 연결을 기록한다. 기존 작업 중인 설계 목표·미정 운영값은 그대로 유지한다.

| 작업 | 현재 구현·코드 근거 | 문제·영향 | 업그레이드 목표·완료 조건 |
|---|---|---|---|
| IN-01 사건 신원·중복 | [ingest.go](../../../incident/service/ingest.go)는 source/cluster/fingerprint/starts_at/target의 hash로 사건을 찾는다. [004 SQL](../../../shared/migrations/004_incident.sql)은 receipt·alert event의 중복 제약과 snapshot을 관리한다 | 현재 알람 생명주기/target 기준은 새 component 에피소드와 다르다. 반복·라벨 변화·동시 수신을 새 설계대로 묶는 기능은 아직 없다 | §2의 기록 중복과 분석 중복 판정을 구현한다. 기존 행을 먼저 점검하고 [03](../common/03_데이터_설계서.md)의 추가 migration으로 이행한다. T41/T42/T49~T52에서 사건·snapshot·outbox·job 수와 원문 불변을 확인한다 |
| IN-02 요청 생산·역할 분리 | `ingest.go`는 alertname 정책으로 목적을 지정하고 적격 증거/정책 변화에 새 revision·outbox를 만든다. envelope는 1.3이다 | 정책 미등록 입력이 RCA에 도달하지 않고, Agent의 목적 선택 목표와 맞지 않는다. 신규 입력만 먼저 내보내면 JC/Worker가 거절한다 | §1의 구조 파싱과 §2의 최초 전달·생략 판단으로 전환한다. JC-01/02·RCA-01/02의 호환 구현을 선행한다. 기존 pending은 원래 키로 복구하고 1.4 최초 요청·제거 필드·재전송을 검수한다 |
| IN-03 상태·후속 소비 | [read.go](../../../incident/service/read.go)는 사건 `state`·검토 `review_status`·`alarm_status`를 분리하고 PATCH로 메모/검토/사건 상태를 변경한다 | Frontend의 사건 배지/필터와 종결 UI가 이 경계에 맞지 않는다. Ops의 기존 재발 계산도 새 사건 단위와 다르다 | §4의 상태 분리·종결/관측 종료·분석 생략 사유를 BE-01·FE-01/02·OP-02/04까지 연결한다. 검토 완료·알람 해제·RCA 완료가 사건 종결/회복으로 승격되지 않고, 종결 후 새 수신에서 §2.3의 재발 정책이 적용되는지 검사한다 |

기존 [Incident E2E](../../../incident/QA.md)와 [실제 Worker webhook 시험](../../../agents/tests/test_e2e.py)은 1.3 생산 형식·전달의 회귀 근거다. 에피소드 전환 시험의 PASS로 승계하지 않는다. 설정 원본·Helm 미러 전환과 구·신규 생산자 혼재 방지는 §5와 14의 순서를 따른다. **이번 상태: 정적 대조 완료, 신규 에피소드·migration·실환경 수신 검수 미실행.**

## 1. 역할과 진입 경로

Grafana Webhook의 유효한 알람을 구조 파싱해 관측 에피소드로 묶고, 에피소드의 최초 알람만 불변 snapshot과 outbox로 저장해 JC에 전달한다. GPU fault뿐 아니라 입력 계약을 만족하는 다른 fault도 이름별 분석 정책 없이 접수한다. 분석 지원 여부와 부족 근거는 Agent가 판단한다.

Incident는 오류 코드 의미 해석·Runbook 검색·로그 원인 분석·R01~R09 배정·증거 변화의 의미 판정·회복 판정을 하지 않는다. 입력 구조 파싱과 형식/크기/시각/scope 검증, 영속성, 전달 재시도와 사건 조회·검토 메타데이터는 기반 기능으로 유지한다. **RCA 업무 요청의 유일한 생산자**이며 GUI·Backend·보고서 Agent는 RCA를 직접 요청하지 않는다.

| Method·경로 | 처리 |
|---|---|
| POST /webhooks/grafana | 입력 검증, 4층 중복 제거와 에피소드 판정, 영속 커밋 후 202 |
| GET /internal/v1/incidents, /incidents/{id} | 에피소드 snapshot·관측 카운트·알람 상태·RCA job 연결 조회 |
| PATCH /internal/v1/incidents/{id} | 메모·acknowledged/closed 등 검토 상태. closed는 에피소드를 끝내지만 RCA를 즉시 실행하지 않음 |
| GET /internal/v1/health/live, /health/ready | 생존 / DB·입력 계약·전달 준비 |

### 1.1 알람 소스 계약

알람 생산자는 Fleet Intelligence의 component 로그를 Loki에 적재하고, Grafana alert rule이 이를 조회해 Webhook으로 전달한다. Incident는 **규칙이 라벨·annotation으로 투영한 값만** 받는다. 로그 본문(`extra_info`, `gpuInfo.gpus` 등)은 Incident에 도달하지 않으며 RCA가 Grafana MCP로 직접 조회한다.

Incident는 문자열에서 의미를 추출하지 않으므로, 필요한 식별자는 생산자가 라벨로 제공해야 한다.

| 배치 | 필드 | 용도 |
|---|---|---|
| 라벨(알람 신원·중복 키) | `cluster_id`, `machine_id`, `component` | fingerprint 재료 + `dedup_group` |
| 라벨(알람 입도) | `reason` | 알람 인스턴스 구분. **`dedup_group`에는 넣지 않는다**(§2.1) |
| annotation(증거·표시) | `k8s_node_name`, `occurred_at`, `log_message`, `suggested_actions` | snapshot 원문 보존·화면 표시 |

배치 근거:

- `machine_id`는 이름 재사용·장비 교체에 안전하다. [03 §4](../common/03_데이터_설계서.md)의 "이름 재생성·장비 교체를 이름만으로 합치지 않음"을 충족한다. `k8s_node_name`은 변경 가능하므로 신원이 아니라 표시 값이다.
- `component`는 Fleet/GPUd의 점검 담당 모듈 이름으로 값 집합이 유한하고 조치 단위와 일치한다. 값 목록은 [Fleet·GPUd component·오류 카탈로그](../rca-agent/references/fleet-gpud-error-catalog.md)를 참조한다. component 이름은 오류 번호나 Unhealthy를 뜻하지 않는다.
- `suggested_actions`는 신원에 기여하지 않고 내용이 바뀔 수 있으므로 라벨에 두지 않는다. 원문은 annotation으로 보존하며 Incident는 해석하지 않는다.
- `severity`는 신원·심각도 판정에 사용하지 않는다. 원문에서 `health=Unhealthy`와 `severity=INFO`가 동시에 관측된 사례가 있다. 상태 해석은 [03 §3.2](../common/03_데이터_설계서.md)의 정규화 계약을 따른다.

운영 검수 항목:

- 알람 규칙이 조회 실패를 드롭하면(`__error__=""` 등) 필드 경로 변경 시 알람이 전량 중단되고 이를 알리는 신호가 없다. 파싱 실패 건수를 관측하는 짝 규칙을 함께 운영한다.
- Grafana의 No Data 처리를 `OK`로 두면 진행 중 장애가 조용히 해제된다. `NoData` 또는 `Alerting`으로 설정한다.
- `DatasourceNoData`/`DatasourceError`는 수집 장애이며 장비 장애가 아니다. 사건은 기록하되 `alertname` denylist로 RCA 발행을 제외한다.
- 라벨 이름은 snake_case로 고정한다. 같은 값을 `machineID`와 `machine_id`로 혼용하지 않는다.

### 1.2 구조 파싱과 의미 해석의 경계

Incident의 파싱은 **정해진 필드를 꺼내 검증·정규화**하는 결정적 처리다. 값이 무슨 뜻인지 판단하는 해석은 RCA가 담당하며 향후 LLM 파싱으로 확장한다. Incident는 LLM을 사용하지 않는다.

| | Incident: 구조 파싱 | RCA: 의미 해석 |
|---|---|---|
| 예 | `labels.component` 복사, `startsAt` UTC 정규화, 길이·범위 검증 | `XID 79` 의미, `health` 판정, `reason` 문구 원인 추출, R01~R09 선택 |
| 실패 처리 | 422 거절 또는 null 보존 | `unknown`/`partial`/`blocked` |

경계 규칙: **값을 복사·검증·정규화만 한다. 문자열에서 의미를 추출하지 않는다.** `reason` 안의 `PCI:0000:01:00`을 정규식으로 뽑아 대상 신원을 만들지 않는다. 필요하면 생산자가 별도 라벨로 제공한다.

| 필드 | 용도 | 누락·오류 시 |
|---|---|---|
| 원문 bytes | `body_hash` (L1) | — |
| `alerts[]`, `truncatedAlerts` | 자식 분해·경고 | 422, 배치 전체 |
| `labels[cluster_id]` | 등록 검증 + 그룹 키 | 거절 `missing_alert_identity` |
| `fingerprint`, `startsAt`, `status` | L2·L3 키, 생명주기 | 거절 |
| `endsAt` | resolved 정합 검증 | `invalid_ends_at` |
| `labels[alertname]` 누락 | 필수 필드 검사 | 해당 자식을 invalid로 거절; 사건 생성 없음 |
| 유효한 `labels[alertname]`의 denylist 일치 | RCA 발행 제외 | 거절 아님. 나머지 필수 검증을 통과하면 §2.3의 `excluded` 그룹으로 기록하고 `analysis_excluded`; outbox 없음 |
| `labels[machine_id]`, `labels[component]` | `dedup_group` | 거절하지 않고 해당 알람 생명주기로 격리. `identity_incomplete` 경고 |
| `annotations[occurred_at]` | 발생 시각 파싱·원문 보존 | 누락·파싱 실패는 null. 생산자 시각 계약 미검수 시 파싱값이 있어도 `incident_time`·조회창 기준은 `startsAt`(§3) |
| 기타 대상 라벨 | `target` 조립 | null 보존. 원본에 없는 신원을 생성하지 않음 |

파싱 실패는 3단계로 격리한다. 배치 단위 실패는 422로 receipt만 남기고, 자식 단위 실패는 `alert_events(disposition=invalid, reason)`으로 기록하되 **형제 자식은 정상 처리**하며, 필드 단위 누락은 거절하지 않고 null로 보존한다.

`occurred_at` 원문은 `2026-09-22 06:17:15.743412635 +0000 UTC` 형식이며 RFC3339가 아니다. 별도 layout(`2006-01-02 15:04:05.999999999 -0700 MST`)으로 파싱하고 실패는 null 보존으로 처리한다. 발생 시각(`occurred_at`)과 탐지 시각(`startsAt`), 수신 시각을 구분해 저장한다.

## 2. 중복 제거 4층과 에피소드

중복 제거는 네 층이며 목적이 둘로 나뉜다. **L1~L3은 기록을 중복 생성하지 않는 결정적 제약이고, L4는 분석을 중복 발행하지 않는 판정이다.** 두 목적을 한 장치로 합치지 않는다.

| 층 | 막는 것 | 판단 기준 | 저장소 |
|---|---|---|---|
| L1 | 같은 배치 원문 중복 저장 | `(source, body_hash)` | `incident_webhook_receipts` |
| L2 | 같은 알람·같은 내용 원문 중복 저장 | `(source, cluster_id, fingerprint, starts_at, payload_hash)` | `alert_events` |
| L3 | 같은 알람 생명주기의 상태 중복 생성 | `(source, cluster_id, fingerprint, starts_at)` | `incident_alert_lifecycles` |
| L4 | 같은 고장의 반복 발생 | `dedup_group` + 관측 연속성 + 검토 상태 | `incidents` |

L1~L3의 신원은 DB 유일 제약으로 판정한다. **중복 원문이어도 §2.3의 수신 연속성 처리를 생략하지 않는다.** 한 생명주기는 여러 에피소드에 걸칠 수 있고 한 에피소드에는 여러 생명주기가 포함될 수 있다. 따라서 알람 자연키의 전역 유일 제약을 `incidents`에 두지 않는다. 생명주기 행은 마지막 귀속 사건과 해제 상태를 보존하고, 과거 귀속은 기존 불변 snapshot·alert event로 추적한다.

### 2.1 사건 단위: 에피소드

**사건 하나 = 한 `dedup_group`에서 연속으로 관측된 구간 하나**다.

```text
완전한 신원: ["component", source, cluster_id, machine_id, component]
신원 부족:   ["alert", source, cluster_id, fingerprint, starts_at]
분석 제외:   ["excluded", source, cluster_id, alertname, fingerprint, starts_at]
```

키는 위 순서의 문자열 배열을 공백 없는 JSON으로 직렬화하고 시각은 UTC로 정규화한다. 구분자 연결·빈 문자열 축소로 충돌시키지 않는다. `source`는 수신 소스 설정에서 결정한다. machine/component 중 하나라도 없으면 알람 생명주기로 격리하며 서로 다른 미확인 장비를 합치지 않는다. 같은 생명주기에서 뒤늦게 신원 라벨이 달라지면 기존 그룹을 이동하지 않고 `identity_conflict`로 원문을 보존·격리한다. 신규 그룹 규칙 변경은 설정 hot reload로 적용하지 않고 §5의 이행 절차를 따른다.

`reason`을 그룹 키에 넣지 않는 이유는 오류 storm이다. GPU가 버스에서 이탈하면 XID 79·45·13·31과 SXid가 수 분 내에 함께 보고되고, `reason`이 키면 물리적으로 한 건인 장애가 사건 5개·RCA 5회가 된다. 조치는 한 번이다. `component` 단위로 묶으면 같은 장애가 한 에피소드가 되고, 계층이 다른 SXid(`accelerator-nvidia-error-sxid`)는 별도 사건으로 남는다.

Grafana 알람 입도와 사건 입도는 달라도 된다. 규칙이 `reason`별 인스턴스를 보내도 L3이 각각을 정확히 중복 제거하고 L4가 하나의 에피소드로 묶는다. 같은 장비의 여러 장치가 동시에 영향을 받은 경우도 한 에피소드로 두어 같은 조사에서 함께 본다. 이름이나 로그 문구가 비슷하다는 이유로 서로 다른 그룹을 합치지 않는다.

에피소드 행은 최초 snapshot을 고정하고 관측 카운트만 누적한다. 반복 알람을 분석 증거 revision으로 누적하지 않으며 시간만 지나면 재전달하는 TTL도 두지 않는다.

### 2.2 에피소드 종료 판정

종료 신호는 두 개이며 **관측 중단이 확정하고 `resolved`는 종료 시각·사유를 보완한다.** Grafana 규칙의 평가 창이 로그 발생 주기보다 짧으면 firing/resolved가 반복될 수 있으므로, `resolved` 수신만으로 즉시 종료하지 않는다.

| 상황 | 처리 |
|---|---|
| 귀속 생명주기가 모두 `resolved`이고 `observation_gap_seconds`(K) 동안 firing 수신 없음 | 종료. `ended_at`=마지막 유효 resolved 시각, `ended_reason=alarm_resolved` |
| `resolved` 없이 K 동안 관측 없음 | 종료. `ended_at`=마지막 관측 시각, `ended_reason=observation_gap` |
| 일부 생명주기만 `resolved`, 다른 생명주기에서 firing 계속 | 에피소드 유지, 집계 `alarm_status=firing`. 일부 해제를 전체 해제로 승격하지 않음 |
| 이미 `resolved`인 동일 생명주기의 늦은 firing | 원문 보존, 수신 연속성·사건·RCA 갱신 없음. 다시 활성화하려면 새 startsAt 필요 |
| `resolved` 선접수(에피소드 없음) | 생명주기 해제 기록과 원문만 보존. 사건·snapshot·outbox 없음 |
| 운영자 종결 | 종료. `ended_reason=closed_by_operator` |

K는 **Incident의 수신 주기**를 기준으로 정한다. K ≥ 2 × 실제 `repeat_interval`을 검수하고 적용 설정 revision·K를 에피소드 최초 snapshot에 고정한다. `last_observed_at`은 미해제 firing을 마지막으로 받아들인 서버 시각이며 원천 로그 시각이 아니다. `observation_count`는 해당 그룹의 유효 firing을 포함한 HTTP 요청 횟수로, 같은 배치의 여러 자식은 그룹당 1회, 동일 bytes의 반복 요청은 요청마다 1회다. 전송 재시도와 정기 알림은 bytes만으로 구분할 수 없으므로 재시도도 포함한다. 원천 로그 건수·장비 정상 여부를 이 값으로 추정하지 않는다. resolved/invalid만 있는 요청은 이 시각·카운트를 늘리지 않는다.

종료는 회복이 아니다. 관측 중단은 장비 복구·exporter 정지·수집 단절·유지보수를 구분하지 못한다. [03 §3.2](../common/03_데이터_설계서.md)의 "로그 단절은 검사·수집 상태로 보존하고 그 사실만으로 장애나 회복을 확정하지 않는다"를 적용한다. `resolved`도 장비·업무 회복의 증명이 아니다.

gap은 갱신 전 `last_observed_at`으로 계산하고 gap > K에서 종료한다(같으면 유지). 조회의 관측 상태도 같은 식을 사용한다. 수신/종결 트랜잭션에서 종료를 영속화하며 별도 종료 스케줄러는 추가하지 않는다. 종료 후에도 허용 재전송 기간 동안 그룹·생명주기 이력을 보존한다.

### 2.3 기존 사건과 신규 사건 판정

수신 1건은 아래 순서로 판정한다. 같은 트랜잭션에서 그룹 키의 advisory transaction lock → 생명주기 → 에피소드 행 순서로 잠근다. 최초 사건은 잠글 행이 없으므로 행 잠금만으로 직렬화하지 않는다. 여러 그룹은 키 정렬 순서로 잠그며 부분 유일 인덱스로도 보호한다. 사람의 종결 PATCH도 같은 잠금 순서를 따른다.

| # | 조건 | 판정 | 기록 | RCA |
|---|---|---|---|---|
| 1 | 배치/자식의 필수 필드·형식·등록 cluster·시각 범위 오류 | 거절 | §1.2에 따라 receipt 또는 invalid 원문 | 없음 |
| 2 | 유효 입력, L1/L2 중복 포함 | 원문은 upsert, 처리 계속 | 중복 원문·snapshot 생성 없음 | 아직 없음 |
| 3 | resolved 또는 이미 해제된 생명주기의 firing | §2.2 적용 | 해제 상태·원문 보존, firing 카운트 증가 없음 | 없음 |
| 4 | 미해제 firing + 열린 에피소드 + 갱신 전 gap ≤ K | **기존 사건** | 그룹당 요청 1회 카운트·수신 시각 갱신 | 없음 |
| 5 | 열린 에피소드 + gap > K | 기존 에피소드 종료 후 6~9 적용 | 마지막 수신과 종료 사유 보존 | 아직 없음 |
| 6 | 이전 에피소드 있음 + 이미 저장된 L2 원문이거나 재발 경계 이후의 새 증거 없음 | 재발 판정 보류 | `post_episode_freshness_unknown`, 이전 사건을 다시 열지 않음 | 없음 |
| 7 | 새 증거 있음 + 직전 에피소드 `closed` | **신규 사건** | 새 행·최초 snapshot·`prior_incident_id` | 발행 |
| 8 | 새 증거 있음 + 직전 에피소드 `open`/`acknowledged` | **신규 사건** | 새 행·최초 snapshot·`prior_incident_id` | 생략 `prior_analysis_open` |
| 9 | 그룹의 첫 유효 firing | **신규 사건** | 새 행·최초 snapshot | 발행 |

denylist는 구조 오류가 아니다. 유효한 `DatasourceNoData`/`DatasourceError`는 별도의 `excluded` 그룹에서 같은 에피소드 규칙으로 기록하되 항상 `rca_eligibility_reason=analysis_excluded`, outbox 없음이다. 장비 사건의 그룹·재발 억제·발생률에 섞지 않는다. 필수 신원이 없는 수집 장애는 invalid 원문으로 남기며 등록 cluster를 추정하지 않는다.

재발 경계는 사람 종결이면 종결의 서버 시각, gap 종료이면 이전 `last_observed_at + K`다. **새 증거**는 이번에 처음 저장하는 L2 원문에서 그 경계보다 늦은 `startsAt`, 또는 발생 시각 갱신 계약이 검수된 생산자의 유효 `annotations.occurred_at`이 확인된 경우다. 허용 나이·미래 오차 검증도 통과해야 한다. 수신 시각·payload hash·reason 변경만으로는 새 증거가 되지 않는다. 이미 해제된 동일 생명주기는 3번이 우선한다. 생명주기의 마지막 처리 사유는 상태 행에 기록하며 중복 원문이나 최초 snapshot을 고쳐 쓰지 않는다.

따라서 종결 직후에도 같은 미해제 생명주기에서 **새 발생 시각이 확인되면** 새 에피소드와 RCA를 만든다. 과거 bytes를 그대로 재전송하면 새 사건을 만들지 않는다. Grafana가 발생 시각을 갱신하지 않는 경우 지속 장애와 전송 재시도를 구분할 수 없다는 한계를 표시하며 자동 재발을 단정하지 않는다. 새 에피소드 생성 이후의 수신은 4번으로 모인다. `prior_analysis_open`은 분석 발행 정책일 뿐 실제 미조치·동일 원인이 증명됐다는 뜻이 아니다.

메모·acknowledged 변경, Agent 분석 완료/실패, 설정 변경, 재시작은 중복 억제를 해제하지 않는다. 다른 source/cluster/machine/component는 별도 그룹으로 처리한다. 잘못된 입력과 허용 나이·미래 시각 범위 밖 입력은 원문과 거절 이유를 보존하고 실행하지 않으며, 분석 목적의 적격성 판정과 구분한다.

alerts 배열은 자식별로 판정한다. 식별 불가 자식은 위치·원문·이유를 보존하고 정상 자식은 처리한다. 정확한 배치 재전송도 연속성 처리를 커밋한 뒤 같은 receipt 응답을 반환한다. 부분 재전송·순서 변경에도 같은 자식 키·그룹 판정을 사용한다. 카운트는 커밋된 수신 횟수이며 응답 유실 후 재요청도 포함하므로 exactly-once 원천 관측 수로 사용하지 않는다.

### 2.4 RCA 1회 보장

에피소드당 RCA 1회는 문구가 아니라 DB 제약으로 보장한다.

| 장치 | 막는 것 |
|---|---|
| `incidents`의 `dedup_group` 부분 유일 인덱스(`ended_at IS NULL`) | 한 그룹에 열린 에피소드가 둘 생기는 것 |
| `enqueue_outbox`의 `(source_module, source_key)` 유일 + `source_key=incident:<incident_id>:first` | 에피소드당 outbox 둘 |
| `incident_evidence_versions` PK와 불변 트리거 + `revision=1` 고정 | snapshot 증가와 재분석 트리거 |

기술 재시도는 JC가 같은 job의 새 attempt로 처리하며 새 job이 아니다. 전달 재시도도 새 업무 요청이 아니고, Worker가 없으면 queued로 남는다. 동일 에피소드에서 증거 추가·목적 변경·조치 후 확인을 위해 새 RCA를 만들지 않는다. 지속 감시·자동 재분석·GUI 직접 재분석은 이번 범위에 포함하지 않는다.

## 3. 영속 전달과 입력

동시 수신·여러 복제본·재시작에도 DB 유일 제약과 트랜잭션으로 최초 접수 승자를 하나로 정한다. 에피소드 행·최초 불변 snapshot·`enqueue_outbox`를 한 트랜잭션에 저장하고 커밋 실패 시 성공 응답하지 않는다.

`source_key=incident:<incident_id>:first`는 에피소드당 하나다. 최초 snapshot의 `evidence_version=1`을 유지하고 반복 알람·정책 변경으로 증가시키지 않는다. 전달 루프는 `/internal/v1/jobs/rca`를 같은 키·같은 hash로 호출한다. 응답 유실은 JC receipt로 확인한다.

RCA 입력은 `incident_id`, `evidence_version`, `scope`, `target` 또는 확인된 사건 범위, `incident_time`, 절대 `time_range`와 불변 원본 snapshot 연결이다. labels·annotations·status·startsAt·알람 값은 원문으로 보존한다. `prior_incident_id`가 있으면 snapshot에 함께 고정해 조치 후 재발임을 Agent가 근거로 읽을 수 있게 한다. 원본에 없는 GPU UUID·Pod 신원을 생성하지 않는다. 조회 시간창은 수신 운영 설정으로 정하고 최초 접수에 고정한다.

`incident_time`과 `time_range`의 기준 시각에는 **생산자의 발생 시각 의미·갱신 계약이 검수되고 파싱·허용 시각 검증을 통과한 `occurred_at`만** 사용한다. 생산자 계약 검수 전에는 파싱 성공 여부와 무관하게 `startsAt`을 기준으로 사용한다. `occurred_at` 누락·파싱 실패도 `startsAt` 기준이며 원문·파싱값·기준 선택 사유·적용 계약 revision을 snapshot에 보존한다. 이는 §2.3의 새 증거 판단에서도 같은 신뢰 조건을 사용하는 것이며, 시각 범위 오류의 기존 거절 규칙을 우회하지 않는다. 로그 기반 알람에서 `startsAt`은 탐지 시각이며 발생 시각과 다르다. RCA는 snapshot에 고정된 기준·절대 조회창을 임의의 annotation 값으로 다시 계산하지 않는다.

machine/component 누락 시 `identity_incomplete`와 부족 필드를 최초 snapshot에 함께 보존한다. 필수 입력이 유효하면 생명주기별 격리 그룹의 첫 firing도 §2.3의 발행 조건에 따라 RCA로 전달하며, RCA의 신원 부족·일반 조사 경로는 [11 §1.1·§3.1.2](../rca-agent/11_RCA_Agent_모듈_설계서.md)를 따른다.

**신규 입력에는 Incident가 정한 `purpose_ids`와 `analysis_profile_revision`을 넣지 않는다.** 실행 한도·Agent 설정은 기존 envelope의 `execution_profile_revision` 및 claim versions로 고정한다. Agent가 파싱·목적·workflow 선택을 실행 근거에 기록한다. 기존 1.3 snapshot/hash/source_key는 변환하지 않는다.

## 4. 상태와 역할 경계

상태는 네 축이며 하나로 합치지 않는다.

| 축 | 값 | 판단 주체 | 저장 |
|---|---|---|---|
| 알람 | `firing` / `resolved` | Grafana 원문 | `alarm_status`, `alarm_resolved_at` |
| 관측 | `observing` / `ended` | 데이터(gap·resolved) | `last_observed_at`, `ended_at`, `ended_reason` |
| 검토 | `open` / `acknowledged` / `closed` | **사람** | `state` |
| 분석 | `dispatched` / `suppressed` / `completed` | 시스템 | `rca_eligibility_reason`, outbox·job 연결 |

`state=closed`는 사람만 만든다. 알람 `resolved`, 관측 종료, RCA 완료, 원천 `health=Healthy`는 종결을 만들지 않는다. RCA 결과는 권고이며 조치 수행이 아니므로 분석 완료가 회복 근거가 될 수 없다. 장비 회복 판정은 [11 §3.4](../rca-agent/11_RCA_Agent_모듈_설계서.md)의 `device_recovery_evidence`와 C08의 유효 정상 연속 관측 조건을 따르며 Incident에 저장 열을 두지 않는다. 조치 기록 추가만으로 사건을 끝내지 않으며 명시적 closed만 §2.3의 재발 경계를 만든다. 이미 관측 종료된 사건을 나중에 closed로 바꿀 때도 그 종결 시각을 별도로 보존하고, 기존 ended_at/ended_reason은 덮어쓰지 않는다.

Agent는 최초 job의 scope·기간·예산 안에서 추가 로그·지표를 조회한다. 이후 시각의 복구·후속 조치가 범위 밖이면 미평가 사유를 남긴다.

## 5. 이행과 검수

기존 `analysis_policies`와 `GPUAlert → R01/R02`는 현행 1.3 실행에만 사용한다. 신규 경로는 alertname 등록 여부로 전달을 차단하지 않으며 denylist만 적용한다. 소스 설정과 Helm 미러 제거는 소비자 전환 후 같은 구현 변경에서 수행한다. 문서 수정만으로 배포 설정을 삭제하지 않는다.

알람 신원은 생명주기 자연키, 사건 신원은 에피소드 ID로 분리한다. 신규 1.4 사건의 event_key는 null이며 기존 1.3 해시와 유일 제약은 유지한다. 이행 순서는 다음과 같다.

1. 추가 migration으로 생명주기 상태·에피소드 열·부분 유일 인덱스를 준비한다. 알람 자연키 유일성은 생명주기 테이블에만 적용한다. 기존 충돌 행은 자동 병합하지 않고 개별 판단한다.
2. 기존 사건의 신원은 최초 alert event로 확인하되 에피소드로 재분류하지 않는다(dedup_group은 null 유지). 전환 당시 생명주기는 legacy 귀속으로 등록해 재접수를 막는다. 중복 귀속은 이행 전 해소하고 기존 snapshot/hash/event_key를 보존한다.
3. JC/shared·Worker와 Backend/Frontend/Ops가 1.3과 1.4를 구분하도록 호환 소비자를 먼저 배포한다.
4. 기존 Incident 복제본을 정지·drain해 구·신규 중복 정책이 동시에 실행되지 않게 한 뒤 생산자와 Helm 설정을 전환한다.

기존 사건은 키별 snapshot/outbox/job 존재를 이행 시 확인한다. 이미 분석을 접수한 키는 다시 보내지 않고 기존 outbox는 기존 키로 완료한다. 과거 정책 미등록 사건도 자동 backfill하지 않는다. 과거 snapshot·결과·revision을 삭제하거나 덮어쓰지 않으며 새 유일 제약을 과거 행에 일괄 강제하지 않는다. DB 변경·검증·복구 순서는 03/14 및 06을 따른다.

검수는 [05](../05_테스트_검수_기준서.md)의 최초/반복/재발·동시 접수·장애 복구·계약 이행 사례와 T41~T45, 에피소드 판정 시험 T49~T54, 소비자 T55~T58 및 입력 시각 T59를 따른다. 코드 미수정 상태에서는 새 동작을 PASS로 기록하지 않는다.

[RCA](../rca-agent/11_RCA_Agent_모듈_설계서.md) · [DB](../common/03_데이터_설계서.md) · [멱등 전달](../common/14_모듈간_호출과_공통실행_계약.md) · [component 카탈로그](../rca-agent/references/fleet-gpud-error-catalog.md)
