# Backend API v1.3

기준: `docs/specs/backend/02_백엔드_API_작업명세서.md`, 03·10·14 공통 계약.

접두사 `/api/v1`, JSON UTF-8, UTC timestamp, `[start,end)`. 사용자·Agent 인증 및 권한 DTO 없음. scope는 등록된 CPC의 분석 필터다. 개발 seed는 cpc-1/cpc-2이며 운영 등록은 `cluster_registry`로 관리한다.

## 공통

- 변경 요청: `Idempotency-Key`. 수정·명령: `If-Match: "1"` 또는 `1`.
- Backend 변경은 데이터·감사·receipt를 같은 트랜잭션으로 커밋한다. 동일 키·본문 재전송은 버전 검사보다 receipt 확인이 먼저다. 다른 본문은 409.
- JC/Incident 명령은 해당 소유자의 receipt·버전 검사를 위임한다.
- 오류: `{error:{code,message,retryable,details},request_id}`. 미등록 404, 충돌 409, 잘못된 입력 422, 의존성 장애 503. 일반 HTTP 형식/속도 제한에는 400/413/415/429도 사용한다.
- 목록 `items,next_cursor`, 기본 50/최대 200, created_at DESC/id DESC. cursor는 경로·필터·정렬과 결합한다.

## 경로

| 경로 | 처리 |
|---|---|
| GET /health/live, /health/ready | 프로세스 / DB·migration·필수 운영 한도. 클러스터 0건도 Ready이며 미등록 CPC 분석은 422로 거부 |
| GET /clusters | 등록 CPC 필터 목록. 미등록 상태는 빈 items 배열 |
| POST /clusters | `{ "cluster_id": "production-gpu" }` 등록. Idempotency-Key 필수, 201 생성·재전송, 409 중복·키 충돌 |
| GET /dashboard | scope·time_range JSON query 또는 from/to, 저장 사건/잡 요약 |
| GET /assets, /workloads | scope·target(JSON)·kind·at 또는 time_range, 식별 이력 |
| GET /observation-quality | scope·at 또는 time_range, 저장 수집 품질 |
| GET /incidents, /incidents/{id} | 저장 사건, 상세 RCA job 연결 |
| PATCH /incidents/{id} | memo/review_status(unreviewed/reviewing/reviewed), Incident 메타데이터 위임 |
| GET /analyses, /reports, /jobs 및 /{id} | scope/kind/status/from/to/incident_id/topic_id/target 필터. 안전한 잡/attempt DTO |
| POST /reports | JC report 커밋 후 202; job_id=report_id |
| POST /jobs/{id}/cancel, /retry | report만, reason·If-Match·키. RCA는 409 kind_not_allowed |
| GET /reports/{id}/export?format=html 또는 csv | published_result_id로 지정된 저장 결과만 렌더링. 미발행 409 |
| GET/POST /schedules, GET/PATCH /schedules/{id} | Backend 일정 생성 201, 불변 revision·effective_at·next_run_at |
| GET /schedules/{id}/occurrences | from/to/status/cursor, pending/accepted/missed/failed·job_id |
| GET /evidence/{id} | 저장 근거, 내부 object_key/실행 비밀 제외 |
| GET/POST /reviews | 불변 comment/review/action. action은 performed_by_verified=false |
| GET/POST /knowledge | 지식 목록/초안 |
| GET/PATCH /knowledge/{id}/revisions/{revision} | 초안 수정·상태·content_hash |
| POST .../review, /publish, /retire | request/approve/request_changes, 검토 해시 일치 발행·불변 발행본 |
| POST /knowledge/{id}/revisions | 기존 지식의 새 초안 revision |
| GET /procedures | 등록 조사 메타데이터, 실행 API 없음 |
| GET/POST /models, GET/PATCH /models/{id} | 비밀 원문 제외, secret_ref 표시, 불변 프로필 revision |
| POST /models/{id}/test-connection | revision·If-Match, allowlist endpoint transport/schema 검사 |
| GET/PATCH /model-routes | rca/report 모델 ID·revision만. in-use 모델 비활성화 409 |
| GET/PATCH /settings/{id} | 등록 C02/C03/C04/C06 설정. description/poll_interval_ms/max_backoff_ms/enabled 등 검증 필드 |
| GET /service-status | JC 큐/Worker 응답·의존성·내부 스케줄러 상태, 용량 읽기 전용 |

제거: `/me`, 권한 설정, 대화, dispatches, Grafana webhook 중계, POST /analyses, GUI 용량/C07 변경. Grafana는 Incident에 직접 연결한다.
기존 화면의 저장 관측 조회를 위해 POST `/observations/query`, `/mappings/query`, `/dashboard/query`만 읽기 전용 호환 경로로 남긴다. 이 경로는 잡을 만들지 않는다.

## 모델 등록

`POST /models`의 최소 본문은 `{"endpoint_url":"https://llm.example.com/v1","model_name":"internal-model"}`이다. 기존 Idempotency-Key와 목적지 허용 목록 검사는 유지한다. 표시 이름은 생략하거나 빈 문자열이면 model_name을 사용하고, limits_profile_id·capabilities를 생략하면 각각 C07·빈 객체를 사용한다. C07은 실제 활성 프로필이어야 한다. artifact_revision·engine_revision·precision은 선택 문자열이며 미입력 값을 만들어 채우지 않는다. PATCH에서 생략한 값과 secret_ref, 과거 불변 revision은 보존한다.

인증은 `secret_ref="env:LLM_API_KEY"`로 배포된 키를 선택하거나 빈 문자열로 해제한다. API 키 원문과 다른 환경변수 참조는 422로 거부한다. 참조를 생략한 PATCH는 기존 값을 유지한다. 키는 프로필·revision·감사·작업 본문에 저장하지 않는다. 신규 설치에서도 빈 model-routes 행을 생성하며 기존 라우팅은 덮어쓰지 않는다.

test-connection은 선택한 인증으로 `/chat/completions`에 짧은 요청(최대 출력 128토큰, 대기 30초)을 보낸다. `transport`는 HTTP 도달 여부, `schema`는 비어 있지 않은 답변 수신 여부다. 401은 authentication_failed, 403은 permission_denied, 404는 model_or_endpoint_not_found로 구분한다. 응답 본문은 반환·감사 기록에 남기지 않는다. 키 미구성은 MODEL_AUTH_NOT_CONFIGURED로 실패한다. 호스트·사설 CIDR·DNS 고정·redirect 차단은 유지한다.

RCA/보고서 모델 지정 후 새로 접수된 작업은 JC가 고정한 모델 ID·revision의 스냅샷을 두 Worker가 읽어 호출한다. 과거 작업은 고정 revision을 유지하며 키는 실행 환경에서 해석한다. 지정된 모델/키가 없으면 다른 모델로 대체하지 않는다. 모델 지정이 없는 작업만 기존 LLM_BASE_URL·LLM_MODEL·단계별 모델 설정을 사용한다. 배포·확인 절차는 [모델 인증 연결](../docs/model-connection.md)을 따른다.

## Runbook 지식 검증과 검색

`kind=runbook`, `content.schema=gpu-rca-runbook/1.0`은 생성/PATCH에서 허용 필드·조건·출처·관측 계획·호환성 형식을 검사한다. 승인(approve)과 발행(publish)은 빈 `compatibility`를 422로 거부한다. schema 없는 legacy 콘텐츠의 기존 처리는 유지하며, 미지원 schema는 거부한다. query 등록·procedure 허용 여부는 관리 CLI와 RCA Worker의 실행 프로필로 검증한다. Backend 형식 검사가 실제 환경 검수를 대신하지 않는다.

`GET /knowledge?kind=runbook&code=xid%3A79`는 legacy `content.code` 또는 v1 `content.search.codes`의 정확한 값을 조회한다. `xid:79`와 `sxid:79`는 별개다. 기존 상태·scope·cursor 필터와 revision/hash·멱등 처리·발행본 불변 규칙을 유지한다.

기존 `knowledge_revisions`의 JSONB 필드를 사용하며 테이블·컬럼·migration을 추가하지 않았다. 오류별 Runbook은 서로 다른 knowledge_key이며 변경 이력은 같은 knowledge_id의 새 revision이다. CLI 명령·초안/발행 경계는 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)를 따른다.

## 보고서/일정

보고서 입력은 scope/time_range/timezone/topic_ids(O01~O11)/group_by와 선택 comparison_range/action_record_ids/resource_selectors/parent_job_id다. 새 수동 보고서와 comparison_range는 최소 24시간·24시간 정수 배수로 검증하며, 미달/부분 일은 `REPORT_DAY_RANGE_REQUIRED`(422)다. 기존 C07 `max_query_days` 상한(기본 31일)은 유지한다. GUI는 KST 시작일과 포함 종료일을 [시작일 00:00, 종료일 다음 날 00:00)으로 전달한다. 기존 저장 결과·JC 재시도 입력과 RCA 기간은 바꾸지 않는다. 정기 일정은 기존 현지 달력 일/주/월 및 DST 규칙을 유지한다. O07 자원 이름·단위는 저장된 resource_catalog와 대조한다. O10 조치 전후 계산/단순 비교 판정은 Report Agent 입력으로 전달한다.

O08을 포함하고 group_by가 namespace 또는 cluster+namespace이면 즉시·정기 envelope는 `DSX_NAMESPACE_REPORT_PROFILE_REVISION`(기본 report-namespace-v1)을 사용한다. 그 외는 기존 DSX_EXECUTION_PROFILE_REVISION을 쓴다. JC 프로필이 criteria 1.2와 report 전용 제한을 소유한다. API 입력에 사용자 임의 criteria 필드를 추가하지 않는다. 원본 envelope에 프로필을 고정하므로 재전송·기존 job은 변경되지 않는다.

수동 접수는 `manual:<Idempotency-Key>`이고 원본 deadline·execution_profile_revision을 manual_report_intents에 먼저 고정한다. 타임스탬프 UTC, scope·topic 정렬 후 같은 입력을 JC `/internal/v1/jobs/report`에 재전송한다. Agent URL을 호출하지 않는다.

```json
{
  "frequency":"daily","local_time":"09:00","timezone":"Asia/Seoul",
  "period":"previous_complete_day","enabled":true,
  "report_spec":{
    "scope":{"clusters":[{"cluster_id":"cpc-1","namespaces":null}]},
    "topic_ids":["O11"],"group_by":["cluster"]
  }
}
```

주간 weekday=1~7(월~일), 월간 day=1~31. report_spec에는 고정 time_range/timezone/parent_job_id를 넣지 않는다. 기간과 시간대는 발생 시 확정한다.
월말 보정·완료된 현지 달력 기간·DST gap의 다음 유효 시각/fold의 첫 시각을 적용한다. 수정 잠금 시 효력 전 예정분을 기존 revision으로 먼저 저장한다. 발생과 outbox는 원자적이며 schedule+예정시각, canonical 보고기간이 중복되지 않는다. paused는 새 발생을 막고 기존 pending 전달을 유지한다.

## 실제 연결 범위

DB 저장 조회·일정·지식·설정은 독립 동작한다. JC/Incident 미설정 명령은 503, 정기 전달은 pending/backoff로 유지된다. 마감 후 receipt 조회가 불가능하면 확인 가능한 때까지 pending을 유지하며, receipt=404가 확인되어야 마감 실패로 확정한다. JC 접수는 Agent 실행 성공을 뜻하지 않는다.

실시간 Mimir/Loki 조회, Agent 집계/LLM, 외부 파일 저장소 전송은 이번 Backend 구현의 실환경 검증 범위 밖이다. 관측이 없으면 미확인/빈 목록이며 임의 수치를 생성하지 않는다.

### 최초 기동과 readiness

Backend는 기동 시 필수 `C07` 운영 한도를 자동 생성한다. 기존 행은 config/enabled/version을 보존한다. `DSX_SEED=false`에서도 동작하며 예제 클러스터는 등록하지 않는다. 등록 클러스터가 없어도 API 조회를 위한 readiness는 성공한다. 분석·보고서 실행에는 실제 cluster ID 등록이 필요하다. 화면의 연결·설정 → 데이터 연결에서 등록하거나 `POST /clusters`를 사용한다. 등록은 수집 성공을 의미하지 않으며 collection_status는 unknown으로 시작한다. 클러스터 등록과 감사 기록, 멱등 receipt는 한 트랜잭션으로 저장한다.

readiness 실패는 `DATABASE_UNAVAILABLE`(DB/스키마 조회 실패), `SCHEMA_NOT_READY`(version 2 미적용), `LIMITS_NOT_CONFIGURED`(C07 누락·비활성·유효하지 않은 한도)로 구분한다. 모든 경우 HTTP 503이며 liveness와는 별개다.

## 저장 기록 웹 추적 — 2026-10-01

- `GET /jobs/{id}/trace`: 작업의 input_snapshot·versions·원본 출처 키, 고정 incident_evidence_versions, 같은 source_module/source_key의 outbox, 즉시 보고서 원본, 정기 회차와 해당 revision, 공개된 후보의 메타데이터를 읽는다. 후보 본문은 이 경로에 포함하지 않는다. 각 연결은 `state: available | not_found | schema_unavailable`과 `record`로 반환한다. 현재 사건 revision이나 최신 일정으로 대체하지 않는다. 한 읽기 전용 repeatable-read 트랜잭션에서 조회한다.
- `alerts`는 같은 사건의 수신 이벤트와 receipt의 수신 시각·HTTP 상태·라벨·annotation을 최근 200건까지 제공한다. 초과하면 `truncated: true`. receipt 전체 payload는 반환하지 않는다. 사건의 모든 이벤트가 현재 작업을 생성했다는 의미는 아니다.
- `GET /jobs/{id}/evidence?attempt=1&limit=50&cursor=...`: 선택한 시도의 저장 근거 메타데이터. attempt 생략 시 현재 시도, 0 이상 정수. 기본 50/최대 200건, created_at/id 오름차순, cursor는 작업·시도에 고정된다. `order: stored_at_asc`; 일괄 저장 시각은 실행 순서/소요시간이 아니다. 공개 결과가 없는 작업도 저장 근거를 조회할 수 있으며 빈 목록은 수집 미실행을 증명하지 않는다.
- `GET /jobs/{id}/evidence/{evidence_id}?attempt=1`: 작업·시도·근거 ID가 모두 일치하는 행만 반환한다. 다른 작업/시도는 404. 기존 snapshot 외에 저장된 LogQL/PromQL·datasource UID·요청 시간·limit·target 등 허용된 input 인자를 제공한다. 일반 `/evidence/{id}`의 응답 계약은 유지한다.

기존 인증 없는 내부 GUI 계약을 따른다. 진단 응답도 기존 sanitize와 헤더·키·토큰 필드 제거를 적용하며 lease 자격증명, 내부 object_key, 임의 transport 설정, 미공개 후보 본문을 반환하지 않는다. 임의 SQL 실행이나 Grafana/Worker 직접 호출 API가 아니다. 새 migration은 없고, Incident/JC 테이블 미설치는 미제공 상태로 구분한다. Worker가 저장하지 않은 오류 원인·실행 시각은 추가하지 않는다.
