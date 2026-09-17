# 02. DSX Backend·프론트엔드 연결 API 명세서

문서 ID: DSX-BE-001 · 버전: 1.2 · 기준일: 2026-09-17 · 상태: 개발 기준

대응 요구사항: F01~F14, N01~N04. 이 문서의 경로와 DTO는 신규 구현 계약이며 배포된 API 목록이 아니다.

## 1. 실행 단위와 처리 책임

Backend는 프론트엔드의 단일 연결점이다. 입력·현재 범위를 검증하고 아래 소유 모듈의 내부 API를 호출한다. 대화 추론·Agent 작업 점유·사건 정규화·달력 실행 루프는 Backend에 포함하지 않는다.

| 외부 기능 | 처리 소유자·내부 경로 | Backend 책임 |
|---|---|---|
| conversations·messages | Chatbot /internal/v1/conversations 및 하위 경로 | 현재 맥락·키 보존 중계 |
| POST analyses·reports | RCA /internal/v1/analyses, Report /internal/v1/reports | 검증·접수 결과 반환 |
| incidents·webhooks/grafana | Incident /internal/v1의 동일 경로 | 원문·서명 관련 헤더 보존 중계 |
| schedules·occurrences | Scheduler /internal/v1의 동일 경로 | CRUD·이력 중계 |
| jobs cancel/retry | immutable jobs.kind의 RCA/Report /internal/v1/jobs/{id}/cancel 또는 retry | 현재 권한 확인·동일 명령 키 전달 |
| reports export | Report /internal/v1/reports/{id}/export | 파일 스트림·오류 중계 |
| dispatches 조회·취소 | source_module의 Chatbot/Incident/Scheduler /internal/v1/dispatches/{id} 및 cancel | 권한을 적용한 소유자 조회 후 중계 |
| jobs·analyses·reports 읽기, evidence·관측·대시보드 | 공통 읽기 어댑터 | 현재 범위를 적용한 통합 조회·응답 조합 |
| 권한·설정·모델·지식 관리·reviews | Backend의 공통 관리 핸들러 | 해당 데이터 변경·감사, 허용된 연결 검사 |
| service-status | 각 모듈 health·공통 읽기 상태 | 모듈별 available/degraded/unavailable 표시 |

통합 작업 목록은 PostgreSQL의 공통 읽기 어댑터로 단일 정렬·cursor를 적용한다. 별도 조회 서비스를 추가하지 않는다. Backend는 다른 모듈의 jobs/messages/incidents/schedules를 직접 변경하지 않는다. 라이브러리의 관측 snapshot·감사 저장은 03의 소유 규칙을 따른다. 내부 신원·멱등·전달 복구는 [15](15_모듈간_호출과_공통실행_계약.md)가 기준이다.

## 2. API 공통 계약

| 항목 | 계약 |
|---|---|
| 기본 경로·형식 | `/api/v1`, JSON UTF-8. 식별자는 불투명 문자열로 전달 |
| 인증 | C01에서 정한 사내 인증과 연계. 서버가 검증한 principal 사용. 브라우저 세션 쿠키 방식이면 HttpOnly/Secure·CSRF 보호 적용 |
| 시간 | RFC3339의 명시적 UTC offset 필수. 저장은 UTC, 기간은 `[start,end)`. `timezone`은 표시·달력 경계 계산용 IANA 이름 |
| 범위 | `scope.clusters`의 CPC별 `{cluster_id,namespaces}` 조합 필수. namespaces=null은 CPC 전체이며 전역 grant 필요, 배열은 그 Namespace만. 빈 배열·중복 CPC·종전 평면 scope는 422, 권한 밖 명시 조합은 403 |
| 자산 | GPU/Pod/Node 식별자의 소속·시점 검증. 배열의 다른 CPC 대상, 외부 결과·근거 참조도 개별 검증 |
| 페이지 | 목록은 `limit` 기본 50·최대 200, 불투명 cursor. 정렬 `(created_at DESC,id DESC)` 또는 API별 명시 정렬 |
| 생성 | 일반 리소스 201, 직접 전문 작업은 Agent 커밋 후 202와 `job_id`; 자동 전달 접수는 dispatch_ref와 nullable job_id. DB 저장 실패는 접수 성공으로 응답하지 않음 |
| 멱등성 | 작업 생성·수동 retry/cancel·메시지 제출에 Idempotency-Key, Webhook에 생산자 중복 키 적용. 권한 확인→기존 명령 기록→최초 요청만 If-Match 검사. 같은 키·다른 정규화 본문은 409 |
| 변경 경합 | version/ETag 반환. PATCH와 종결 상태 변경은 `If-Match` 필수. 누락 428, 오래된 버전 412 |
| 검증 | 열거값·날짜·범위·문자열 길이·본문 크기·정렬 필드를 서버 allowlist로 검사. query ID별 매개변수 스키마 적용 |
| 리소스 제한 | 최대 조회 기간·로그량·본문/대화 크기·작업 접수량은 C07 프로필에 양수 상한 필수. 미설정이면 해당 접수 비활성 |
| 보안 응답 | 비밀·내부 원문 스택·타 CPC 라벨을 오류에 포함하지 않음. 존재 자체를 숨겨야 하는 타 사용자 리소스는 404 |

정상 목록은 `{items:[], next_cursor:null}`. 상세 응답은 리소스 객체와 `request_id`를 포함한다. 오류는 다음 형식을 사용한다.

HTML 출력은 원문·모델·사용자 텍스트를 이스케이프하고 허용된 서식만 렌더링한다. CSV는 표준 quoting과 함께 `=`, `+`, `-`, `@` 등으로 수식 해석될 수 있는 문자열 셀을 안전한 텍스트로 출력한다. 실제 숫자 필드는 숫자로 유지한다. 파일명·콘텐츠 타입을 서버에서 정하고 비밀·권한 밖 데이터가 포함되지 않게 한다.

```json
{
  "error": {
    "code": "INVALID_TIME_RANGE",
    "message": "시작 시각은 종료 시각보다 빨라야 합니다.",
    "details": {"field": "time_range"}
  },
  "request_id": "example-request"
}
```

HTTP 400/422는 형식·의미 오류, 401 인증 필요, 403 권한 없음, 404 리소스 없음, 409 멱등/상태 충돌, 413 크기 초과, 429 접수·호출 한도, 503 저장·의존 서비스 불가다. 429는 `Retry-After`를 반환한다. 유효한 조회의 데이터 부재는 200과 결과 품질/도구 상태로 표현하며 서버 오류와 구분한다.

## 3. API 목록

표의 모든 읽기·변경은 범위 검증을 전제로 한다. 개별 ID 상세 조회·파일 출력·재분석에서도 검사한다.

| 구분 | Method·경로 | 입력·처리 | 출력 |
|---|---|---|---|
| 권한 | GET `/me` | 인증 principal | 역할·허용 scope·장비 관측 권한 |
| 권한 관리 | GET/PATCH `/settings/access-grants` | 별도 manage_access 권능, If-Match, grant 목록·변경 사유 | grants 원자적 변경·감사·권한 캐시 무효화 |
| 대상 | GET `/clusters` | 허용 CPC | CPC·수집 상태·기준 시각 |
| 대상 | GET `/assets` | cluster, kind=node/gpu/pod, namespace, cursor | 자산 키·표시명·신원 상태 |
| 대시보드 | POST `/dashboard/query` | scope, time_range | 관측 품질·사건·할당 요약·근거 |
| 매핑 | POST `/mappings/query` | scope, GPU 또는 Pod, at 또는 time_range 중 하나 | 03의 관계·신원·시간·품질 |
| 관측 | POST `/observations/query` | query_id, scope, target, time_range, parameters | 도구 상태·값·단위·품질·근거 |
| 근거 | GET `/evidence/{id}` | 근거 ID | 허용된 요약·스냅샷·원문 접근 가능 상태 |
| 사건 | GET `/incidents` / GET `/incidents/{id}` | scope, 상태·기간·자산, cursor | 사건·관측·관련 분석·version |
| 사건 | PATCH `/incidents/{id}` | If-Match, status, reason | 상태·변경 이력. close에는 종결 이유 필수 |
| 수신 | POST `/webhooks/grafana/{profile_id}` | 검증된 원문·전용 인증 | 사건·전달 커밋 후 수신 ID·사건/dispatch 참조·nullable job_id·중복 여부 |
| RCA | POST `/analyses` | 아래 RCA 요청, Idempotency-Key | 202, job_id=analysis_id, 상태 URL |
| RCA | GET `/analyses` / GET `/analyses/{id}` | scope·기간·대상·cursor 또는 ID | 작업·최종 결과·이전 실행 참조 |
| 보고서 | POST `/reports` | 아래 보고서 요청, Idempotency-Key | 202, job_id=report_id, 상태 URL |
| 보고서 | GET `/reports` / GET `/reports/{id}` | scope·기간·주제·cursor 또는 ID | 작업·주제별 결과·근거·버전 |
| 출력 | GET `/reports/{id}/export?format=html\|csv` | 저장된 보고서 ID | HTML 보고서 또는 집계 CSV. 원본 결과 재계산 없음 |
| 작업 목록 | GET `/jobs` | kind, status, from/to, scope, cursor, limit | 허용 범위의 안전한 작업 DTO 목록·안정 정렬 |
| 작업 | GET `/jobs/{id}` | 해당 분석/보고서 읽기 권한 | 상태·단계·시도·종료 이유·결과 참조·허용 행동 |
| 취소 | POST `/jobs/{id}/cancel` | If-Match, reason, Idempotency-Key | 종결 전이면 cancelled 또는 running의 cancel_requested; 완료 후 최초 취소면 409 |
| 전달 상태 | GET `/dispatches/{id}` | 현재 원본 업무/결과 권한 | 전달 상태·job_id·version·허용 취소 |
| 전달 취소 | POST `/dispatches/{id}/cancel` | If-Match·Idempotency-Key·reason | 접수 전 전달 취소 또는 Agent job 취소 결과 |
| 재시도 | POST `/jobs/{id}/retry` | If-Match, reason, Idempotency-Key | 서버가 판단한 재시도 가능 failed만 retry_wait. 임의 단계 건너뛰기 불가 |
| 일정 | GET/POST `/schedules` | 생성 시 보고서 조건·달력 일정 | 목록 또는 201 일정 ID·다음 발생 시각 |
| 일정 상세 | GET `/schedules/{id}` | 소유자 또는 관리 권한 | revision·조건·effective_at·다음 시각·blocked 사유 |
| 일정 이력 | GET `/schedules/{id}/occurrences` | revision/status/from/to/cursor/limit | 발생 시각·고정 기간·pending/accepted/missed/blocked/failed·dispatch_ref·nullable job_id·사유 |
| 일정 | PATCH `/schedules/{id}` | If-Match, 조건 변경·enabled | 새 revision·다음 시각. 소유자/관리자만 변경 |
| 대화 | GET/POST `/conversations` | 본인 대화 목록 / scope·제목 | 대화 ID·맥락 |
| 대화 | GET/POST `/conversations/{id}/messages` | 질문·허용 맥락·Idempotency-Key | 저장된 메시지 또는 설명·등록 조회 결과·전문 job 참조 |
| 메시지 복구 | GET `/conversations/{id}/messages/{message_id}` | 본인·현재 범위 권한 | 메시지 처리 상태·응답·고정 맥락/모델·전문 job 참조 |
| 기록 | GET/POST `/reviews` | 대상 종류·ID, 의견 또는 실제 조치 | 작성자·발생/입력 시각·근거·수정 전 기록 참조 |
| 지식 | GET `/knowledge` / GET `/knowledge/{id}/revisions/{rev}` | kind·코드·증상·호환 조건 | 발행 목록·상세. 관리자만 초안 조회 |
| 지식 | POST `/knowledge` / POST `/knowledge/{id}/revisions` | 초안 내용·근거·지원 범위 | 새 초안 ID/revision |
| 지식 | PATCH `/knowledge/{id}/revisions/{rev}` | If-Match, 초안 내용 | 초안만 수정. 검토 후 수정 시 재검토 필요 |
| 지식 | POST `/knowledge/{id}/revisions/{rev}/review` | If-Match, action=request/approve/request_changes, comment, evidence_refs? | draft→in_review→reviewed 또는 draft |
| 지식 | POST `/knowledge/{id}/revisions/{rev}/publish` | If-Match, 검토된 revision | 발행 기록·내용 hash. 관리 권한 필수 |
| 지식 | POST `/knowledge/{id}/revisions/{rev}/retire` | If-Match, 사유 | 신규 실행 선택 중단. 기존 실행 참조 유지 |
| 조사 절차 | GET `/knowledge/procedures` | 허용된 증상·procedure ID/version 필터 | 등록 코드 절차의 읽기 전용 메타데이터 |
| 모델 | GET/POST `/models` | 서비스 관리자, 모델 프로필 입력 | 목록 또는 모델 프로필 ID·revision |
| 모델 | GET/PATCH `/models/{id}` | 서비스 관리자, If-Match, 프로필 또는 enabled 변경 | 비밀 제외 모델 설정·revision |
| 연결 검사 | POST `/models/{id}/test-connection` | 관리자, 검사할 revision | transport/schema 각각 상태·검사 시각·오류. 품질 합격을 의미하지 않음 |
| 모델 지정 | GET/PATCH `/model-routes` | 관리자, If-Match, assistant/rca/report별 모델 참조 | 역할별 모델 ID·revision 및 라우팅 revision |
| 운영 | GET `/service-status` | 서비스 관리자 또는 제한된 상태 조회 | 경로별 신선도·큐·Worker·추론 상태 |
| 설정 | GET/PATCH `/settings/{profile_id}` | 관리자, If-Match, 허용 설정 | 비밀값 제외 설정·검증 결과·revision |
| 진단 | GET `/health/live` / GET `/health/ready` | 내부 접근 | 프로세스 생존 / API 핵심 처리 준비 상태 |

## 4. 요청·응답 상세

### 4.1 공통 분석 조건

`scope={clusters:[{cluster_id,namespaces:null|[name,...]}]}`; `target={kind,cluster_id,node_uid?,node?,gpu_uuid?,pod_uid?,namespace?,pod_name?}`. target 생략은 보고서의 명시 scope 전체다. RCA는 target 또는 권한 검증된 incident_id 중 하나 이상이 필요하다. 둘 다 있으면 사건 소속·대상과 일치해야 한다. Pod 조사에서 GPU·Node 미확정은 접수 거절 사유가 아니며 허용된 CPC·Namespace·Pod 식별과 기준 시각으로 시작한다.

`/me`는 `principal,grants:[{role,cluster_id,namespace,asset_observation}],capabilities,access_revision`을 반환한다. 각 행의 role과 scope를 함께 평가한다. namespace=null은 그 행의 CPC 전역 권한이다. “접근 가능한 전체”를 고르면 UI는 이 grants에서 해당 행동의 허용 조합을 명시 scope로 만든다. 여러 행의 역할과 범위를 교차 합성하지 않는다. 저장 결과·지식·근거·모델 입력과 Worker 실행 시에도 현재 권한을 검증한다.

GET 목록의 scope 매개변수는 위 객체를 JSON으로 직렬화한 뒤 URL 인코딩한 값이다. 생략 시 해당 조회 행동의 현재 허용 조합만 서버가 사용한다. from/to는 created_at의 반개구간 필터이며 정렬은 `(created_at DESC,id DESC)`. cursor는 필터·정렬 조건을 포함해 검증한다. schedule occurrences는 `(scheduled_for DESC,id DESC)`다.

`time_range={start,end}`, `timezone`, `parent_job_id?`, `conversation_id?`를 공통 사용한다. 부모·대화는 허용된 동일 목적/범위 맥락만 연결한다. 다른 범위의 결과를 새 scope로 재포장할 수 없다.

RCA는 `incident_id?`, `incident_time?`, `symptom`, `purpose_ids`(R01~R09)를 받는다. 사건이 있으면 사건 시각을 기본으로 사용하고 다른 시각 요청은 조사 범위로 명시한다. 사건 없는 사용자 조사는 Incident를 가짜로 만들지 않는다.

보고서는 `topic_ids`(O01~O11), `group_by`(cluster/model/node/namespace/pod/workload), `comparison_range?`, `action_record_ids?`, `resource_selectors?`를 받는다. action_record_ids는 O10의 실제 조치 review UUID 목록이다. time_range는 조치 후, comparison_range는 비교 전 기간으로 명시한다. 조치 기록이 없으면 기간 비교만 제공하고 인과적인 조치 효과는 보류한다. resource_selectors는 O07의 `{cluster_id,resource_name,unit}` 배열이며 등록된 `resource_catalog` query 결과에서 고른다. 미확인 resource 단위는 0으로 가정하지 않는다. Workload 이력이 없으면 Pod 수준 유효 결과와 집계 제한을 반환한다.

```json
{
  "scope": {"clusters": [{"cluster_id": "cpc-1", "namespaces": ["dev"]}, {"cluster_id": "cpc-2", "namespaces": ["prod"]}]},
  "time_range": {"start": "2026-09-07T00:00:00+09:00", "end": "2026-09-14T00:00:00+09:00"},
  "timezone": "Asia/Seoul",
  "topic_ids": ["O02", "O03", "O05", "O11"],
  "group_by": ["cluster", "namespace", "pod"]
}
```

```json
{
  "job_id": "7af117a4-c4bb-4b57-8f0b-d08fc88bfd1c",
  "report_id": "7af117a4-c4bb-4b57-8f0b-d08fc88bfd1c",
  "status": "queued",
  "status_url": "/api/v1/jobs/7af117a4-c4bb-4b57-8f0b-d08fc88bfd1c",
  "request_id": "example-request"
}
```

GET job는 `id,kind,status,stage,attempt_no,created_at,started_at,deadline_at,cancel_requested_at,termination_reason,result_ref,result_status,narrative_status,can_cancel,can_retry,version`을 반환한다. result가 없으면 result_status와 narrative_status는 null이다. 허용된 결과를 읽는 조회자에게도 안전한 job 상태는 제공하되 원본 요청·Worker 내부·민감 로그는 포함하지 않는다. 취소/retry는 소유 운영자 또는 해당 업무 관리가 허용된 서비스 관리자만 가능하다. can_cancel/can_retry는 UI 안내값이며 변경 시 권한·deadline·version을 다시 검증한다. poll_after_ms는 이번 응답에 넣지 않고 UI는 운영 설정의 간격·backoff를 사용한다. 최종 result_status 요약은 04에서 계산·저장하며 FE가 주제 상태를 추정하지 않는다.

`GET /jobs/{id}` 상세에는 `attempts`도 포함한다. 소유 운영자 또는 해당 업무 관리가 허용된 관리자에게만 `attempt_no,started_at,finished_at,stage,termination_reason,error_code`의 안전한 요약 배열을 시도 번호 오름차순으로 반환하고 그 외에는 null이다. finished_at과 stage는 job_attempts의 ended_at과 last_stage를 매핑한다. 원문 오류·Worker 주소·민감한 체크포인트를 노출하지 않으며 목록에는 이 배열을 싣지 않는다.

Knowledge 경로의 `{id}`는 revision별 ID가 아닌 불변 `knowledge_id`이며 `{rev}`는 해당 지식의 revision 번호다. 생성 응답에는 knowledge_id·revision·revision_id를 모두 반환한다. 조회자·일반 대화에서 전문 작업이 필요해도 운영자 권한이 없으면 작업을 생성하지 않고 권한 부족을 안내한다.

### 4.2 정기 일정

일정 CRUD와 달력 계산은 [14 Scheduler](14_Scheduler_모듈_설계서.md)가 소유한다. 발생 응답은 pending/accepted/missed/blocked/failed와 dispatch_ref·job_id를 구분한다. pending은 전달 의도 저장, accepted는 보고서 job 접수다. 일정 비활성화만으로 이미 저장된 전달·job을 취소하지 않는다.

### 4.3 실제 조치·검토

POST reviews는 `subject_type=incident|job|knowledge`, `subject_id`, `kind=comment|review|action`, `text`, `occurred_at?`, `evidence_refs?`, `supersedes_id?`를 받는다. action은 `target`, `occurred_at`, `performed_by`, `action_summary`가 필수다. 운영자가 이미 수행한 조치를 기록하며 Backend가 장비 조치를 실행하지 않는다. 수정은 새 기록으로 추가한다.

### 4.4 사내 모델과 라우팅

모델 프로필은 `name,endpoint_url,model_name,artifact_revision,engine_revision,precision,secret_ref?,enabled,capabilities,limits_profile_id`를 받는다. 문자열·URL·허용 모델 형태를 C06 계약으로 검증한다. API는 기존 service_profiles와 불변 revision 스냅샷을 재사용하며 모델 저장소를 추가하지 않는다. API 모델 ID는 profile ID다. GET에는 비밀값을 반환하지 않는다.

연결 검사는 서버에서 허용된 목적지만 제한된 시간·요청 크기로 검사한다. DNS 해석·리다이렉트 이후 목적지도 allowlist 정책을 적용한다. transport와 schema 상태는 ok/failed/not_checked로 나누고 각각 이유·검사 시각·설정 revision을 반환한다. 실제 GPU 용량·R/O 품질 평가는 C09/T40의 별도 결과다.

라우팅은 assistant/rca/report의 각 `{model_id,model_revision}`과 공통 default 참조를 보존한다. 기본·명시 라우팅에 쓰는 모델의 비활성화는 대체 라우팅을 같은 변경으로 지정하거나 409 사용 중으로 거절한다. API에서 모델을 물리 삭제하지 않는다. 이미 접수된 job·message는 고정 모델/설정 스냅샷을 계속 참조한다. 장애·폐기·보안 사유로 사용할 수 없으면 명시 실패 또는 연결된 새 요청으로 전환하고 조용한 모델 교체는 하지 않는다.

### 4.5 Assistant 메시지 복구

S16의 일반 대화와 복구는 [10 Chatbot](10_Chatbot_Agent_모듈_설계서.md)을 따른다. Backend는 대화 추론을 수행하지 않는다. message 상태·dispatch_ref·job_id를 그대로 반환하며 Backend 재시작을 메시지 실패로 취급하지 않는다.

## 5. 사건·알림 처리

원문 검증·정규화·episode·사건 상태 변경은 [13 Incident](13_Incident_모듈_설계서.md)가 수행한다. Backend는 Grafana 원문 bytes와 필요한 인증 헤더를 보존하여 전달한다. Incident가 사건·전달 의도를 커밋한 응답과 RCA의 job 접수를 구분한다. dispatch_id가 있어도 job_id는 접수 확인 전 null이다.

## 6. 영속 작업·동시 실행

jobs의 생성·점유·취소·재시도·최종 결과 확정은 kind별 RCA/Report 소유다. 공통 상태 전이·lease·예산·명령 receipt는 [15 §5](15_모듈간_호출과_공통실행_계약.md)를 따른다. Backend는 상태를 읽고 변경 명령을 소유 Agent API로 전달한다.

## 7. 공유 한도·실패 처리

내부 연결 실패·timeout을 접수 성공으로 바꾸지 않는다. 직접 요청은 원래 키로 재시도하고, 영속 전달은 source_module이 복구한다. 일부 모듈 장애는 해당 경로의 503 또는 안전한 저장 상태 조회로 표현한다. 공통 LLM 제한·취소·지연 응답은 [15 §6](15_모듈간_호출과_공통실행_계약.md)를 따른다.

## 8. 구현 완료 확인

각 API는 요청·성공·오류 예시와 인증·범위·멱등 검증을 제공한다. 각 모듈은 별도 시작·중지·배포·health 점검이 가능해야 하며 공통 DTO·저장 라이브러리를 공유한다. Backend가 소유 모듈 내부 API를 호출하는 계약 시험을 제공한다. 런타임/DB 버전·실제 Endpoint·수치 한도는 [06 인계서](<06_배포_운영_인계서.md>)의 C01~C12를 적용한다.

검증은 [05 테스트 기준서](<05_테스트_검수_기준서.md>)를 따른다. 결과·데이터 계약은 [03](<03_데이터_설계서.md>), 판단·출력은 [04](<04_Agent_동작_판단_명세서.md>)를 참조한다.
