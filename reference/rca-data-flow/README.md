# RCA 데이터 흐름과 DB 확인

이 브랜치는 **main `02aec604061293be21b3d69bb3d6d9879ec2d18f` 버전의 RCA 데이터 흐름과 DB 연결을 확인하기 위한 참고 자료**를 보관한다.

- 브랜치: `codex/reference-main-02aec60-rca-data-flow`
- 기준 버전: PR #16 병합 직후의 main `02aec60`
- 용도: 배포 후 실제 데이터 흐름과 DB 읽기·쓰기 위치 대조
- 변경 범위: `reference/rca-data-flow/`의 그림·설명·샘플·조회 SQL만 추가
- 관리 원칙: main에 병합하지 않는 자료 브랜치. 제품 코드·배포 설정·기존 문서 목차 변경 없음

기준 버전의 고정 문서다. 이후 main 변경을 자동 반영하지 않는다. 이 브랜치의 자료 커밋을 제품 배포 버전으로 사용하지 않는다. 현재 CI는 main push·버전 태그·PR·수동 실행에서 동작하므로 이 자료 브랜치 push 자체로 빌드/발행하지 않는다.

다른 PC에서는 GitHub에서 이 브랜치를 선택하거나 `git fetch origin` 후 `git switch --track origin/codex/reference-main-02aec60-rca-data-flow`로 확인한다. 로컬 브랜치가 이미 있으면 `git switch codex/reference-main-02aec60-rca-data-flow`를 사용한다.

기준: `main`의 `02aec60`, 2026-09-28. 제공받은 DB 그림의 테이블을 현재 migration·실제 읽기/쓰기 코드와 대조했다. **기본 Incident 입력 1.3 → 현재 RCA Worker 경로**를 설명한다. 새 테이블이나 실행 로직을 추가한 문서가 아니다. 운영 DB에 접속하거나 사건을 발생시키지 않았다.

## 실제 점검 결과와 재시험

- [2026-09-28 XID/SXID 단계별 점검 결과](2026-09-28-flow-review.ko.md): 접수·저장·발행은 이어졌지만 D09/D05 수집 실패로 LLM 분석이 생략된 사례. Backend API 조회 근거와 직접 SQL 미확인 항목을 구분했다.
- [LLM 연결 후 재시험 보고서 양식](llm-retest-report.ko.md): 단계별 테이블·조회값·판정·근거를 기록하는 양식. 아직 재시험 결과는 없다.
- [기존 읽기 전용 조회 SQL](verify-flow.sql): 실제 Incident/Job ID를 지정해 사용한다. 공유본에 운영 주소·실제 UUID·원본 응답은 포함하지 않는다.

위 그림과 SQL은 기존 소스 기준을 유지한다. 추가 점검 보고서는 별도 현장 조회 결과이며, 배포 이미지/커밋이 기준 소스와 같다는 것을 검증한 자료는 아니다. 아래의 “운영 조회 미수행” 설명은 최초 그림·SQL 작성 당시의 범위다.

## 그림 두 장

| 그림 | 브라우저 원본 | PNG | SVG |
|---|---|---|---|
| CPC → CSC Grafana → Incident → JC → RCA → 공개 결과 | [전체 흐름](01-end-to-end.html) | [이미지](01-end-to-end.png) | [벡터](01-end-to-end.svg) |
| RCA 입력·Runbook·수집·분석·저장·공개 | [RCA 내부](02-rca-internal.html) | [이미지](02-rca-internal.png) | [벡터](02-rca-internal.svg) |

HTML의 inline SVG가 수정 원본이다. PNG는 2배 해상도로 렌더링했다. 외부 폰트 다운로드 없이 로컬 폰트로 표시하며, 이 PC에서는 한글은 맑은 고딕, 기술 표기는 Consolas를 사용했다. 다른 PC에서 동일한 모양으로 보려면 PNG를 사용한다. 그림의 `R/I/U`는 조회/추가/갱신이고, DB 상자는 별도 DB 인스턴스를 뜻하지 않는다. 서비스별 소유 테이블이 같은 제품 PostgreSQL에 있다. Loki/Mimir는 별도 관측 저장소다.

## 같은 샘플을 끝까지 추적하기

[sample-data.json](sample-data.json)은 `cpc-1 / dgx01 / XID 79`의 대표 데이터다. **운영 관측이 아닌 설명용 샘플**이며, webhook 외의 객체는 주요 필드만 발췌한 조각이다. 직접 API 요청 본문으로 사용하지 않는다. webhook의 고정 과거 시각도 현재 테스트에 그대로 보내면 stale 조건에 걸릴 수 있다.

| 약칭 | 의미 | 연결 기준 |
|---|---|---|
| I | Incident UUID | `alert_events.incident_id = incidents.id` |
| V=1 | 사건 증거 revision | `incident_evidence_versions(incident_id, revision)` |
| O | Outbox UUID | `enqueue_outbox.input_snapshot.input.incident_id=I` |
| J | Job UUID | `enqueue_outbox.job_id = jobs.id`, `jobs.incident_id=I` |
| A=1 | 시도 번호 | `job_attempts(job_id, attempt_no)`; evidence/candidate도 같은 두 키 |
| K / KR | 논리 Runbook ID / revision 행 ID | `knowledge_id`와 `knowledge_revisions.id`는 다른 값 |
| E* | 수집·분석 증거 UUID | `result_candidates.body.evidence_refs[] → evidence.id` |
| C | 결과 후보 UUID | `jobs.published_result_id = result_candidates.id` |

시각 예시는 사건 발생 `03:00:00Z`, Incident 수신 `03:00:05Z`다. 기본 조회창은 발생 30분 전부터 발생 5분 후까지지만, 수신 시각이 더 이르면 끝을 수신 시각으로 자른다. 이 예에서는 `02:30:00Z~03:00:05Z`가 된다. 실제 값은 DB의 고정 snapshot을 확인한다.

Fleet의 `reason`, `component`, `k8s_node_name`, `machine_id`, `suggested_actions`는 원문에 보존한다. 기본 1.3 Incident는 `k8s_node_name`을 DB `target.node`로 바꾸지 않는다. RCA가 runtime 대상에 node를 보충하여 D09/D02 조회를 좁힌다. 이미 저장된 Incident/Job snapshot은 수정하지 않는다. `machine_id`가 자동으로 GPU UUID가 되지도 않는다. `REBOOT_SYSTEM`은 provider 권고이며 수행 기록이 아니다.

## 단계별로 확인할 테이블

표의 SQL 번호는 [verify-flow.sql](verify-flow.sql)에 대응한다.

| 그림 단계 | 소유자와 DB 작업 | 주요 확인 필드 | 정상 진행/중단 판별 | SQL |
|---|---|---|---|---|
| 사전 설정 | Backend: cluster/Knowledge 관리. Incident: 기동 시 source/policy 저장. JC: Worker/capacity 관리 | `cluster_registry.enabled`, `incident_sources.snapshot`, `incident_analysis_profiles`, `knowledge_revisions.state/compatibility` | 클러스터 활성화, alertname 정책 일치, 실행 프로필 존재. 발행 Runbook은 사건 접수 전에 준비 | 00, 04, 10 |
| 전체 02→03: webhook | Incident I/U `incident_webhook_receipts`, I `alert_events` | 원문 `raw_payload`, `body_hash`, `receipt_id`, `disposition`, `reason` | receipt만 있고 invalid면 알람 신원·시각·클러스터 검사. 같은 본문 재전송은 기존 receipt 재사용 | 01 |
| 전체 03: 사건/증거 | Incident I/U `incidents`, I `incident_evidence_versions` | `state`, `alarm_status`, `evidence_version`, `rca_eligibility_reason`; `snapshot.input/alert`, `content_hash` | eligible이며 증거 변경 시 새 snapshot과 outbox. 반복 증거에는 새 작업이 없을 수 있음 | 02 |
| 전체 03→04: 전달 | Incident I/U `enqueue_outbox` | `source_key`, `status`, `attempts`, `next_retry_at`, `last_error`, `job_id` | pending→accepted. accepted는 JC 접수 성공이며 RCA 완료가 아님 | 03 |
| 전체 04: JC 접수 | JC R snapshot/cluster/knowledge/routing, I `jobs` | `input_snapshot`, `incident_id`, `evidence_version`, `versions.knowledge`, `request_hash` | jobs에 immutable snapshot 본문이 포함됨. source_module/source_key가 멱등 키 | 03, 04 |
| 전체 04: claim/heartbeat | JC I/U `workers`, I `job_attempts/slot_reservations`, U `jobs/capacity_state` | `queue_reason`, `attempt_no`, `stage`, lease/ended 시각, reservation state | queued→running. worker_unavailable/capacity_wait/inference_quarantined면 배분 사유 확인 | 05, 10 |
| 내부 01: context | Agent R `incident_evidence_versions`, `knowledge_revisions` | 고정 snapshot/hash; `knowledge_id,revision,content_hash` | JC 접수 시 고정된 Runbook만 읽음. claim 이후 retire된 고정본은 재현을 위해 읽을 수 있음 | 02, 04 |
| 내부 02~05: 조사/분석 | Agent 메모리, MCP는 Loki/Mimir 조회 | plan/query 응답/quality/sufficiency/synthesis | 이때 evidence 테이블에 새 행이 없어도 정상. heartbeat의 workflow stage는 세부 내부 단계를 구분하지 않음 | 05, 저장 후 06 |
| 내부 06: 저장 | Agent R `jobs/job_attempts` fence, I `evidence/result_candidates` | `(job_id,attempt_no)`, query_id, body, validation_status, hash | 두 테이블을 한 트랜잭션으로 저장. 저장 전 오류면 둘 다 없을 수 있음 | 06, 07 |
| 내부 07·전체 06: 발행 | JC R candidate, U `jobs/job_attempts/slot_reservations` | `published_result_id`, `completion_response`, `ended_at`, `released_at` | candidate 존재만으로 공개 완료 아님. 포인터와 attempt/hash 확인 | 07, 08 |
| 전체 06: Backend/보고서 | R `jobs JOIN result_candidates`, 필요 시 evidence | 공개 ID/hash, body 원인 후보·목적별 상태·부족 입력 | `jobs.succeeded`여도 body는 partial/blocked일 수 있음. 보고서는 공개 결과만 인용 | 08, 09 |

Backend의 Runbook 발행에는 `knowledge_revisions`, `review_records`, `audit_events`, `backend_receipts`가 사용된다. 이 관리 작업은 매 RCA 실행마다 발생하지 않는다. 현재 267개 JSON은 빈 compatibility의 draft 작성 원본이며 [등록·검토·발행 절차](../../rcca-agent/runbooks/DB-WORKFLOW.md)를 따른다. **새 Runbook을 나중에 발행해도 기존 J의 versions.knowledge는 바뀌지 않는다.** 새로운 입력/사건 또는 승인된 재분석 경로에서 고정 버전을 확인한다.

## 내부 결과를 어디서 읽나

`evidence.query_id`는 실제 D-query 외에도 과정 기록을 구분한다. 한 query가 여러 대상/청크/시도를 만들 수 있으므로 행 수가 query 수와 같다고 가정하지 않는다. 다음 기록은 내부 06 저장 이후에 보인다.

| query_id | snapshot/quality에서 확인할 값 |
|---|---|
| `incident_snapshot` | 최초 고정 사건 원문. `quality.immutable=true` |
| `alert_clues` | `xid:79`, 노드, provider 권고 등 검색 단서. verified_facts가 아님 |
| `runbook_selection` | revision ID, 검색 점수, invalid_contract/general_available 등 선택 진단 |
| `observation_plan` | round, assignments(query/sub_agent_id/budget), scope/target/concurrency |
| `D09`, `D05`, 선택 `D02` | input의 실제 MCP 인자, snapshot 응답, tool_status, quality.complete/reason/round/sub_agent_id |
| `sufficiency` | decision, evidence_gap, remaining_queries, remaining_budget, runbook_revision_ids |
| `rca_synthesis` | status, input_evidence_refs, hypotheses, limitations. fast path에서는 없음 |
| `runbook` | 적용 조건이 실제 충족된 Runbook의 본문. pending 계획은 이 행 없이 결과 runbook_revisions/선택 진단에만 남을 수 있음 |

RCA 결과는 별도 `rca_results` 테이블이 아니라 `result_candidates.body`에 있다. 핵심 필드는 `result_status`, `assessments`, `cause_candidates`, `missing_inputs`, `runbook_revisions`, `quality.analysis`, `evidence_refs`, `recommendations`다. `schema_version` 열은 JC 결과 계약, `body.result_schema_version`은 본문 버전이므로 두 필드를 같은 버전으로 가정하지 않는다.

현재 D05는 기본 설정에서 node target_labels가 없고 D09/D02는 node를 사용한다. 로그를 얻었다고 error_code fact가 자동 생성되지는 않는다. Synthesis에는 정규화된 health/metric/관계와 참조, Runbook 지침을 전달하며 원문 Loki 로그 전체를 직접 넘기지 않는다. **원문 로그 저장 확인과 LLM 입력 근거 확인은 별도 점검**이다. 현재 Fleet parser/실제 query binding의 미완성 범위를 이 그림이 감추지 않도록 표시했다.

## 현재 실행되지 않는 DB 쓰기

- RCA 완료는 `incidents.state`를 closed로 바꾸거나 원인을 Incident 행에 복사하지 않는다. Incident 알람 상태/수동 검토 상태와 RCA 결과 상태를 별도로 확인한다.
- 이 경로는 `allocation_observations`, `collection_observations`, `identity_history`에 자동 적재하지 않는다. RCA에서 수집한 응답의 영속 증거는 `evidence`다.
- 기본 1.3 경로는 `incident_alert_lifecycles`를 사용하지 않는다. `episode_policy`를 켠 1.4는 별도 경로이며 현재 Worker는 1.3으로 등록한다. `jobs.versions.input_contract=1.4`가 큐에 남으면 Worker 호환성부터 확인한다.
- `command_receipts`는 cancel/retry 명령에 쓰인다. complete 응답은 `job_attempts.completion_response`에 보관한다. `incident_command_receipts`도 Incident 메타데이터 변경용이며 수집/분석 완료 기록이 아니다.
- `schedules`, `schedule_revisions`, `schedule_occurrences`, `manual_report_intents`는 이후 보고서 요청 흐름에 해당한다. 자동 RCA 한 건에 생성될 것으로 기대하지 않는다.

## 조회 SQL 실행

제품 PostgreSQL의 해당 schema를 선택한다. SQL은 read-only transaction과 10초 statement timeout을 사용하며, 출력에 claim_token을 포함하지 않는다. **운영 DB에서 실행하지 않았으며 실제 행 존재 여부는 배포 후 확인 대상이다.**

먼저 아래 조회로 실제 Incident ID를 찾는다. fingerprint와 cluster는 실제 알람 값으로 바꾼다. 레코드가 없다면 시간 필터 대신 Grafana Contact point/Incident 원문 receipt부터 확인한다.

```sql
SELECT id AS alert_event_id, receipt_id, incident_id, cluster_id,
       fingerprint, starts_at, status, disposition, reason, observed_at
FROM alert_events
WHERE cluster_id = 'cpc-1'
  AND fingerprint = 'demo-xid79-dgx01'
ORDER BY observed_at DESC LIMIT 20;
```

연결 정보는 기존 PG 환경/서비스 설정을 사용한다. 비밀번호를 명령 문자열에 넣지 않는다. 저장소 루트에서:

```sh
psql -X --set=ON_ERROR_STOP=1 --set=incident_id=실제_UUID --file=reference/rca-data-flow/verify-flow.sql
# 특정 재시도/작업만 확인할 때는 --set=job_id=실제_JOB_UUID 추가
```

이 파일은 psql 변수(`:'incident_id'`)를 사용한다. DBeaver 등에서는 해당 변수를 SQL 문자열 리터럴 UUID로 바꾸고 `\if`, `\echo`, `\set` 등 psql 전용 줄은 제외한다. DB snapshot 기준의 한 번의 점검이므로 진행 상황을 보려면 종료 후 재실행한다.

## 코드 근거와 검증 범위

- [Incident 입력/정책/snapshot/outbox](../../incident/service/ingest.go), [outbox 전달](../../incident/service/delivery.go), [기동 설정 저장](../../incident/service/server.go)
- [JC 접수와 버전 고정](../../job-controller/controller/submit.go), [claim과 slot](../../job-controller/controller/claim.go), [heartbeat/complete](../../job-controller/controller/attempt.go)
- [Worker 순서](../../shared/python/src/agent_common/worker.py), [DB context/save](../../shared/python/src/agent_common/store.py)
- [Orchestrator](../../rcca-agent/src/rcca_agent/workflow.py), [Observation task](../../rcca-agent/src/rcca_agent/observation_agents.py), [MCP 수집](../../shared/python/src/agent_common/observation.py), [Synthesis](../../rcca-agent/src/rcca_agent/synthesis.py)
- [Backend 공개 결과](../../backend/internal/api/read.go), [query 프로필](../../agents/config.example.json), [Incident 기본 설정](../../incident/config.example.json), [DB ownership](../../shared/README.md)
- 스키마: [001](../../shared/migrations/001_backend.sql), [002](../../shared/migrations/002_contract_13.sql), [003](../../shared/migrations/003_job_controller.sql), [004](../../shared/migrations/004_incident.sql), [005](../../shared/migrations/005_incident_episodes.sql), [006](../../shared/migrations/006_worker_contracts.sql)

확인한 사항: 소스의 R/I/U와 표·SQL 대응, 두 그림의 브라우저 렌더링/텍스트 영역·접근성 검사, 문서 링크, 샘플 JSON 구문. 새 격리 PostgreSQL에 현재 migration을 적용하고, psql 변수를 예시 리터럴로 치환한 진단 SQL 전체 21개 명령/결과 집합을 psycopg로 실행해 테이블·컬럼·문법을 확인했다. 빈 테스트 schema에서의 성공이며 운영 행 연결 검증은 아니다. 테스트 서버는 종료했다. 운영 DB 행 조회·Grafana/Fleet/LLM 호출은 수행하지 않았다. 기존 실행 검증은 [Agent QA](../../agents/QA.md), [Backend QA](../../backend/QA.md)를 따른다. 이 문서 변경은 런타임 테스트 대상 코드 변경을 포함하지 않는다.
