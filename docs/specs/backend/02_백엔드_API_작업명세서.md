## 일정 실행 상태 읽기 보완 — 2026-10-02

## 소주제별 기준을 가진 보고서 — 2026-10-06

`POST /reports`와 일정 `report_spec`은 선택적 `topic_group_by` 객체를 받는다. 예: `{"topic_ids":["O01","O08","O09"],"group_by":["cluster"],"topic_group_by":{"O01":["cluster"],"O08":["namespace"],"O09":["cluster"]}}`. 선택된 모든 topic에 정확히 하나의 축 배열이 있어야 하며 누락·추가 key·null·빈 map은 422다. 현재 지원 프리셋은 O08=`[namespace]` 또는 `[cluster,namespace]`, 나머지=`[cluster]`뿐이다. 이는 현행 계산 기준 선택이며 임의 그룹별 재집계를 새로 구현한 계약이 아니다.

기존 필수 `group_by`는 유지한다. 새 map이 없으면 종전 입력·프로필·결과 처리 그대로다. map이 있으면 각 topic의 기준으로 사용하고, O08의 namespace 기준은 기존 `report-namespace-v1` 프로필(criteria 1.2)을 선택한다. Backend·JC·Ops가 모두 검증하고 Ops는 O08 기준 버전 불일치를 거부한다. RCA 입력에는 이 필드를 허용하지 않는다. DB 구조와 input schema_version 1.3은 유지하고 저장된 JSON snapshot/일정 revision/멱등 해시에 map을 포함한다. 종합·다중 선택도 하나의 job이다.

새 map 요청에서 O10 조치 ID 또는 비교 기간이 없으면 해당 주제 전용 수집을 하지 않고 기존 null/blocked와 부족 사유를 남긴다. 직접 요청은 조건을 선택 입력하며 신규 자동보고서는 임의 조치·비교 기간을 만들지 않는다. 다른 주제에 필요한 같은 D 조회는 유지한다. 구 요청/일정의 비교 동작은 변경하지 않는다.

결과 `quality.topic_group_by`, `topic.quality.requested_group_by/display_basis`, `metric.quality.display_basis`에 적용한 표시 기준을 보존한다. 새 결과 CSV에는 마지막 `display_basis` 열을 추가하고 HTML·UI에도 기준을 표시한다. 구 결과의 CSV 열은 유지한다.

배포는 새 입력을 만드는 Frontend/Backend 활성화 전에 JC·공통 계약·Ops 소비자를 함께 갱신하고 이전 Ops Worker를 drain/교체한다. 구 Worker가 새 map을 무시할 수 있으므로 혼합 버전 실행은 보장하지 않는다. 새 버전은 구 요청/일정을 처리하지만, 구 버전이 새 요청을 처리하는 호환성은 없다. 운영 배포는 별도 검수다.

`GET /schedules`는 최근 예정 회차 `latest_occurrence`와 서버 시각 기준 회차 기록 부재 `awaiting_occurrence`를 추가 제공한다. 최근 회차와 `GET /schedules/{id}/occurrences`의 `execution`은 실제 report 작업 및 최신 시도의 상태·시각·사유·공개 참조만 담는다. 접수는 실행 완료가 아니며 회차 기록 부재만으로 실패를 판정하지 않는다. 필드·null·정렬·호환 조건은 [Backend API](../../../backend/API.md)의 자동 보고서 실행 요약 계약을 따른다. 일정/outbox 쓰기와 JC 실행 소유권, DB schema는 유지한다.

# 02. Backend·GUI API 및 정기 보고서

버전 1.3 · 모듈 backend · 독립 실행·배포

## 0. 현재 구현 분석과 업그레이드 작업

2026-09-23 · 코드 대조 기준 `d391f3d`. 아래는 코드 정적 대조 결과이며 신규 동작의 실행 검증이 아니다. 본문의 API·일정 계약은 유지하고, 다음 차이를 후속 개발 대상으로 관리한다. 공통 입력·DB 정의는 03/14, Runbook 실행 가능 조건은 11이 원본이다.

| 작업 | 현재 구현·코드 근거 | 문제·영향 | 업그레이드 목표·완료 조건 |
|---|---|---|---|
| BE-01 사건 조회·소비 | [proxy.go](../../../backend/internal/api/proxy.go)의 목록은 `COALESCE(state,status)`로 필터링하고 DB 행을 반환한다. 상세는 RCA job 목록을 추가한다. PATCH는 `state`, `review_status`, `memo`를 Incident에 전달한다 | Frontend는 현재 `status`를 배지에 사용한다. 신규 Incident 행의 `state`와 legacy `status`가 달라 필터·표시가 어긋난다. 에피소드·분석 생략 사유의 전용 표시도 필요하다 | 사건의 기준 상태는 `state`로 소비하고 `alarm_status`·검토·분석 상태를 분리한다. legacy fallback과 13의 에피소드/이전 사건/생략 사유 응답을 Frontend와 확정한다. 종결 PATCH 후 재조회와 새 사건 연결을 확인한다 |
| BE-02 RCA 목적·결과 조회 | [read.go](../../../backend/internal/api/read.go)의 `jobDTO()`는 입력 `purpose_ids`를 복사하고, 공개 candidate 본문만 결과로 반환한다 | 1.4에는 입력 목적이 없으므로 기존 필드만 보면 목적이 사라진다. 미공개 결과를 추정해 채울 수도 없다 | 기존 1.3 목적 표시를 유지하고 1.4는 공개 assessments·선택 근거를 소비한다. 아직 선택/발행되지 않은 목적은 미확정으로 표시한다. 14의 input_contract 전달을 선행 구현하고 두 버전의 목록·상세를 검사한다 |
| BE-03 Runbook 작성·발행·검색 | [knowledge.go](../../../backend/internal/api/knowledge.go)는 content가 비어 있지 않은 객체인지, scope·근거 참조·검토 hash를 검사한다. code 필터는 `content.code`만 비교한다 | 검토 hash 일치만으로 query/fact/조건의 실행 가능성이 입증되지 않는다. 새 `search.codes`만 가진 Runbook은 기존 code 필터로 찾을 수 없다 | [11 §6.2](../rca-agent/11_RCA_Agent_모듈_설계서.md)의 신규/legacy content 검증 및 선언 코드 검색을 연결한다. 미지원 query·조건·미해석 참조는 실행 가능한 신규 발행을 막고, 기존 발행본은 수정하지 않는다. 관리 화면과 RCA가 같은 revision을 읽는지 확인한다 |

BE-01/02는 Incident·JC·Frontend와 접수 전환 전에 연결하고, BE-03은 RCA의 P1과 함께 진행한다. 새 Agent 실행 API·별도 스케줄러를 추가하지 않는다. 즉시 요청의 intent, 정기 occurrence/outbox, 공개 결과만 내보내는 기존 경로는 회귀 보존 대상이다.

BE-01의 1.4 사건 응답은 `state`, `alarm_status`, `review_status`, `episode_started_at`, `last_observed_at`, `observation_count`, `ended_at`, `ended_reason`, `closed_at`, `prior_incident_id`, `rca_eligibility_reason`을 구분해 제공한다. last_observed_at/count는 재시도를 포함한 수신 기준이다. legacy의 에피소드 전용 값은 null이며 추정하지 않는다. state가 있는 경우 status로 덮어쓰지 않고, legacy state 부재일 때만 기존 status를 표시한다. 신규 state는 open/acknowledged/closed이며 resolved는 알람 상태다. 1.4 job/결과의 입력 버전은 14의 input_contract로 전달한다.

검수 연결: [05](../05_테스트_검수_기준서.md)의 T28/T29(상태 표시), T30(지식), T48(구·신규 소비), T49~T52(에피소드). [기존 Backend E2E](../../../backend/tests/e2e_test.go)와 [실제 JC 연결 시험](../../../backend/tests/job_controller_test.go)은 기존 경로의 출발점이며 위 신규 조건 전체를 검증한 기록은 아니다. **이번 상태: 정적 대조 완료, 신규 구현·제품 테스트·실환경 검수 미실행.**

## 책임

Backend는 GUI 연결점이며 조회·입력 검증·내부 호출·결과 응답·설정과 정기 보고서 일정을 소유한다. RCA를 접수하거나 Agent를 직접 호출해 실행하지 않는다. Grafana Webhook은 Incident로 직접 연결한다. 보고서 집계와 LLM 실행은 보고서 Agent에 둔다.

2026-09-22 역할 변경 목표: Incident는 최초 알람 중복 제거·전달, RCA Agent는 파싱·목적·Runbook/일반 조사 선택을 맡는다. Backend는 새 R 매핑 API를 추가하지 않는다. 신규 결과의 목적은 Agent assessments/선택 evidence에서 읽으며 Incident 입력에 purpose_ids가 없다고 R01/R02를 기본 표시하지 않는다. 기존 1.3 결과 조회는 유지한다. 상세 입력 이행은 [14](../common/14_모듈간_호출과_공통실행_계약.md)을 따르며 아직 런타임 변경은 아니다.

## API 공통 계약

외부 접두사는 `/api/v1`. JSON UTF-8, UUID 문자열, UTC timestamp, `[start,end)` 기간을 사용한다. 제품 인증·`/me`·권한 DTO는 없다. `scope={clusters:[{cluster_id,namespaces:null|[name,...]}]}`는 분석 필터다. 빈 배열·중복 cluster·미등록 cluster·범위 밖 target·역전 기간은 422다. namespaces=null은 해당 CPC 전체를 뜻한다.

목록은 `items,next_cursor`, 기본 limit=50·최대 200, `(created_at DESC,id DESC)` 순서다. cursor는 필터·정렬을 함께 검증한다. 변경은 `Idempotency-Key`, 수정/명령은 `If-Match: version`을 사용한다. 같은 키·다른 본문은 409. 이미 적용된 같은 명령 재전송은 If-Match보다 receipt 확인이 먼저다.

오류는 `{error:{code,message,retryable,details},request_id}`. 404는 없음/제공하지 않는 API, 409는 충돌, 422는 입력 오류, 503은 의존 서비스 장애 또는 필수 스키마·설정 미준비다. 큐가 정상 접수했지만 실행 슬롯이 없는 경우는 202 queued이며 503이 아니다.

## API 목록

| Method·경로 | 입력/처리 | 응답·소유 |
|---|---|---|
| GET /clusters | 등록 클러스터 조회·scope | 분석 범위 선택용 목록 |
| POST /clusters | cluster_id·멱등 키 | 등록 201, 중복 409, 수집 상태 unknown |
| GET /dashboard | scope, 기간 | 관측·사건·잡 요약 |
| GET /assets, /workloads, /observation-quality | scope, 대상, at 또는 기간 | 식별·관계·품질 DTO |
| GET /incidents, /incidents/{id} | 사건 필터/ID | Incident 저장 사건·RCA job 연결 |
| PATCH /incidents/{id} | 메모·검토 상태·If-Match | Incident에 위임, RCA 실행 부수 효과 없음 |
| GET /analyses, /analyses/{id} | incident_id, scope / RCA job ID | 발행된 RCA 결과 또는 미발행 상태 |
| POST /reports | 보고서 조건·멱등 키 | JC 커밋 후 202, job_id=report_id |
| GET /reports, /reports/{id} | 필터/보고서 job ID | 저장 결과·주제 상태 |
| GET /reports/{id}/export?format=html 또는 csv | 저장된 final | Backend가 발행된 결과 값으로 HTML/CSV 렌더링 |
| GET /jobs, /jobs/{id} | kind/status/scope / ID | JC 상태·안전한 attempt 이력 |
| POST /jobs/{id}/cancel, /retry | report만, If-Match·멱등 키 | JC 명령 결과. RCA에는 409 kind_not_allowed |
| GET/POST /schedules | 목록/일정 조건 | Backend 일정, 생성 201 |
| GET/PATCH /schedules/{id} | 조회/수정·enabled·If-Match | revision·effective_at·next_run |
| GET /schedules/{id}/occurrences | 기간·상태·cursor | 예정 발생·전달 상태·job_id |
| GET /evidence/{id} | 저장 근거 ID | 안전한 근거·파일 참조 |
| GET/POST /reviews | subject_type/id, comment/review/action | 불변 검토/실제 조치 기록 |
| GET/POST /knowledge | 목록/초안 | 지식 ID·revision |
| GET/PATCH /knowledge/{id}/revisions/{rev} | 상세/초안 수정 | content_hash·상태 |
| POST /knowledge/{id}/revisions/{rev}/review | request/approve/request_changes | draft/in_review/reviewed |
| POST /knowledge/{id}/revisions/{rev}/publish, /retire | revision·If-Match | 발행/폐기 상태 |
| GET /procedures | 등록 조사 메타데이터 | 읽기 전용 목록, 임의 실행 API 없음 |
| GET/POST /models; GET/PATCH /models/{id} | 비밀 제외 프로필 | 불변 revision·enabled |
| POST /models/{id}/test-connection | 프로필 revision | transport/schema 검사 결과 |
| GET/PATCH /model-routes | rca/report의 모델 참조 | 라우팅 revision |
| GET/PATCH /settings/{id} | 등록된 관측·모델 설정만 | 검증된 설정 revision |
| GET /service-status | 없음 | 큐·Worker·의존성 상태, 용량은 읽기 전용 |
| GET /health/live, /health/ready | 없음 | 생존 / DB·필수 설정 준비 |

`POST /analyses`, RCA retry/new-analysis, 대화 API, GUI 레플리카 변경 API는 제공하지 않는다. `/settings`를 통한 임의 용량·배포 변경도 제공하지 않는다. Incident 상태 변경이 필요하면 Backend가 Incident의 메타데이터 PATCH를 위임하되 RCA 실행을 부수 효과로 만들지 않는다.

## 클러스터 등록과 준비 상태

`POST /clusters`는 `Idempotency-Key`와 `{"cluster_id":"production-gpu"}`를 받는다. ID는 비어 있지 않은 문자열이며 UTF-8 바이트 길이 200 이하, 앞뒤 공백·제어 문자 없는 값이어야 한다. 응답 본문은 `id,cluster_id,namespaces:null,collection_status:"unknown"`이다. 등록은 관측 데이터 수집 성공을 의미하지 않는다.

같은 멱등 키·동일 본문의 재전송은 기존 응답을 반환한다. 새 키로 기존 ID를 등록하면 `409 CLUSTER_ALREADY_REGISTERED`이며 비활성 행도 자동 활성화하지 않는다. 같은 키·다른 본문은 409, 잘못된 입력 또는 필수 키 누락은 422다. ID는 Grafana에서 조회하는 실제 클러스터 라벨 값과 일치시킨다.

`GET /health/live`는 프로세스의 HTTP 응답 여부를 확인한다. `GET /health/ready`는 DB 스키마 version 2와 활성 C07 API 한도의 7개 양수 값을 확인한다. 활성 클러스터 유무와 MCP·LLM 상태는 이 검사의 조건이 아니다. 클러스터가 없는 최초 설치도 Ready가 되며 미등록 범위의 보고서 요청은 입력 검증에서 거부한다.

| readiness 오류 | 의미 |
|---|---|
| `DATABASE_UNAVAILABLE` | DB 연결·스키마 또는 운영 한도 조회 실패 |
| `SCHEMA_NOT_READY` | 스키마 version 2 기록 없음 |
| `LIMITS_NOT_CONFIGURED` | C07 누락·비활성 또는 필수 한도가 양수가 아님 |

오류 응답은 모두 503이다. 기본 설정 초기화와 실제 기본값은 [06 배포·운영](../06_배포_운영_인계서.md)에 둔다. 구현: [클러스터 등록](../../../backend/internal/api/clusters.go), [readiness](../../../backend/internal/api/readiness.go).

## 보고서 접수와 응답

입력: `scope,time_range,timezone,topic_ids,group_by,topic_group_by?,comparison_range?,action_record_ids?,resource_selectors?,parent_job_id?`. topic은 O01~O11, group_by는 cluster/model/node/namespace/pod/workload다. 추가 개발의 주제별 지원 조합은 04 §5.5를 따른다. 잘못된 enum은 422, 유효하지만 미지원 조합은 접수 후 해당 topic의 blocked/unsupported_group_by로 표시한다. O10은 time_range=조치 후, comparison_range=비교 전이며 조치 기록이 없으면 단순 비교로 표시한다. O07의 resource_selectors는 등록된 이름·단위만 받는다.

```json
{
  "scope":{"clusters":[{"cluster_id":"cpc-2","namespaces":["dev"]}]},
  "time_range":{"start":"2026-09-16T00:00:00+09:00","end":"2026-09-17T00:00:00+09:00"},
  "timezone":"Asia/Seoul","topic_ids":["O02","O03","O11"],"group_by":["namespace","pod"]
}
```

Backend는 `source_module=backend,source_key=manual:<Idempotency-Key>`로 JC의 report 접수 API를 호출한다. 202는 JC의 job 커밋 이후에만 반환한다. 응답 유실 시 같은 키·동일 본문으로 재전송한다. 새 키로 자동 재전송하지 않는다. `parent_job_id`는 기존 보고서의 의도적 재생성에만 사용하며 새 요청의 별도 멱등 키가 필요하다.

응답: `{job_id,report_id,status,status_url,request_id}`. GET job는 `id,kind,status,stage,attempt_no,created_at,started_at,deadline_at,queue_reason,cancel_requested_at,termination_reason,result_ref,result_status,narrative_status,can_cancel,can_retry,version`을 반환한다. 상세에만 안전한 attempts 요약을 추가하며 claim_token·Worker 내부 주소는 노출하지 않는다.

## Backend 내부 정기 보고서 스케줄러

별도 서비스가 아니라 Backend 프로세스 내부의 발생/전달 루프다. Backend 복제 수가 늘어도 DB 잠금·유일 키로 한 발생만 저장한다. 보고서 Agent 장애는 일정 계산을 막지 않는다. JC 장애 중 발생은 Backend outbox에 남긴다.

입력은 `frequency=daily|weekly|monthly,local_time=HH:mm,timezone,weekday?,day?,period,enabled,report_spec`다. period는 frequency에 맞는 previous_complete_day/week/month. 월간 없는 날짜는 말일, 주간은 월요일 시작. 분석 기간은 현지 시간의 완료된 달력 기간을 UTC로 고정한다. DST 없는 시각은 다음 유효 시각, 중복 시각은 첫 번째를 택한다.

1. schedule 행을 잠그고 예정 시각의 불변 revision·완료 기간을 계산한다.
2. `(schedule_id,scheduled_for_utc)` 발생 유일 키와 `(schedule_id,period_start,period_end)` canonical 기간 유일 키를 검사한다.
3. occurrence=pending과 enqueue_outbox를 같은 Backend 트랜잭션에 저장한다. source_key는 `schedule:<occurrence_id>`다.
4. 전달 루프가 같은 키로 JC report API를 호출한다. JC 커밋 확인 후 occurrence=accepted·job_id를 저장한다.
5. 응답 유실/재시작 시 같은 occurrence를 복구한다. accepted는 분석 성공이 아니라 큐 접수 확인이다.

수정 시 schedule 잠금 아래 revision과 effective_at을 기록한다. 효력 전 예정분은 이전 revision, 이후 예정분은 새 revision을 적용한다. 이미 pending/accepted인 발생의 조건은 바꾸지 않는다. 같은 보고기간을 다시 가리키는 발생은 missed/already_reserved_period와 기존 참조를 남긴다. 일시중지는 이후 새 발생만 막고 이미 접수한 잡은 취소하지 않는다.

복구 시 운영 설정 catchup_window/max_catchup 내 누락만 발생시키고 나머지는 missed로 남긴다. 기존 pending 전달은 새 발생 생성과 별도로 재전송한다. occurrence 상태는 pending/accepted/missed/failed. 자동 전달은 유효성 오류에 failed, 일시 오류에는 상한 있는 backoff를 적용한다. 전송 마감 시 최종 실패 판정 전 JC의 멱등 receipt를 재확인한다.

## 조회·지식·모델·기록

결과 조회는 jobs의 published result_ref만 사용한다. 미완료 후보 파일을 정상 결과로 노출하지 않는다. 파일명은 서버 생성, HTML 이스케이프·CSV 수식 방어, URL/파일경로 입력 검증을 적용한다. 모델 연결은 등록된 내부 endpoint만 허용하고 secret_ref만 저장·표시한다. 라우팅에서 사용 중인 모델 비활성화는 대체 지정 또는 409이며 진행 중 job의 모델을 조용히 교체하지 않는다.

지식은 검토한 content_hash가 일치할 때 발행하며 발행본은 불변이다. 실제 조치 기록은 target·occurred_at·performed_by·action_summary를 받지만 장비 제어를 실행하지 않는다. performed_by는 미인증 입력임을 표시한다.

### 보고서 결과 소비 보완 목표

2026-09-30 소비 보완 목표: 보고서 내부 병렬 관측은 기존 `/reports`·일정·JC 접수 계약을 변경하지 않는다. [12](../ops-agent/12_보고서_Agent_모듈_설계서.md)의 OP-07에 따라 공개 결과의 facts/findings/recommendations·value_refs/evidence_refs·eligibility·preconditions·reason·execution을 기존 결과 본문으로 전달하고 HTML에서 권고/보류·근거·다음 확인을 읽을 수 있게 한다. Backend가 조언이나 eligibility를 다시 생성하지 않으며 미공개 candidate는 조회하지 않는다. 구 결과의 필드 부재·설명 실패·partial/blocked를 보존한다. CSV는 아래 기존 수치 열과 저장 값을 유지한다. 이는 개발 목표이며 현재 HTML/CSV 구현과 구분한다. 검수는 [05 T65](../05_테스트_검수_기준서.md)를 따른다.

### 보고서 다운로드의 현재 구현

Backend는 발행된 `result_candidates.body`의 `measurements`와 `topics[].metrics`를 읽어 출력하며 새 분석을 실행하지 않는다. 수치가 있으면 HTML은 항목·대상·값·단위·제한 사유 표를, CSV는 `id,target,value,unit,method,reason,evidence_refs` 열을 생성한다. null 값은 ‘산출 불가’로 표시한다. HTML은 원본 결과와 해석 제한을 포함하고 텍스트를 escape하며 CSV는 수식 문자를 방어한다. 수치 배열이 비어 있으면 기존 JSON 기반 HTML/필드별 CSV 출력을 사용한다. Agent의 저장 파일을 그대로 전송하는 경로와는 구분한다. 구현: [export](../../../backend/internal/api/export.go), [수치 출력](../../../backend/internal/api/report_export.go).

[DB](../common/03_데이터_설계서.md) · [큐](../job-controller/10_Job_Controller_모듈_설계서.md) · [공통 계약](../common/14_모듈간_호출과_공통실행_계약.md)
