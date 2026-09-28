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

## Runbook 지식 검증과 검색

`kind=runbook`, `content.schema=gpu-rca-runbook/1.0`은 생성/PATCH에서 허용 필드·조건·출처·관측 계획·호환성 형식을 검사한다. 승인(approve)과 발행(publish)은 빈 `compatibility`를 422로 거부한다. schema 없는 legacy 콘텐츠의 기존 처리는 유지하며, 미지원 schema는 거부한다. query 등록·procedure 허용 여부는 관리 CLI와 RCA Worker의 실행 프로필로 검증한다. Backend 형식 검사가 실제 환경 검수를 대신하지 않는다.

`GET /knowledge?kind=runbook&code=xid%3A79`는 legacy `content.code` 또는 v1 `content.search.codes`의 정확한 값을 조회한다. `xid:79`와 `sxid:79`는 별개다. 기존 상태·scope·cursor 필터와 revision/hash·멱등 처리·발행본 불변 규칙을 유지한다.

기존 `knowledge_revisions`의 JSONB 필드를 사용하며 테이블·컬럼·migration을 추가하지 않았다. 오류별 Runbook은 서로 다른 knowledge_key이며 변경 이력은 같은 knowledge_id의 새 revision이다. CLI 명령·초안/발행 경계는 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)를 따른다.

## 보고서/일정

보고서 입력은 scope/time_range/timezone/topic_ids(O01~O11)/group_by와 선택 comparison_range/action_record_ids/resource_selectors/parent_job_id다. O07 자원 이름·단위는 저장된 resource_catalog와 대조한다. O10 조치 전후 계산/단순 비교 판정은 Report Agent 입력으로 전달한다.

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
