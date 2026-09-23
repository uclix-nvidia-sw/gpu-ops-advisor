# 내부 API 계약 구현

접두사 `/internal/v1`, JSON body, 응답 `request_id`, 오류 `{error:{code,message,details,retryable}}`. 인증/토큰 검증은 추가하지 않았습니다. source_module/worker_id는 업무 타입 식별자입니다. 변경 요청 body는 알려진 필드만 허용합니다.

| 경로 | 용도 |
| --- | --- |
| GET /health/live, /health/ready | 생존 / DB·큐 migration·설정 revision |
| POST /jobs/report, /jobs/rca | 202 영속 접수 또는 기존 접수 확인 |
| GET /receipts/{source_module}/{source_key} | URL encode된 생산자 키로 job 조회 |
| GET /jobs | kind/status/limit(1~100)/cursor 조회 |
| GET /jobs/{id} | 상태·공개 결과 참조 (claim_token 미노출) |
| POST /workers/register | 운영 프로필로 Worker 등록 |
| POST /claims | 자기 kind 작업 1개 반환, 없음 204 |
| POST /jobs/{id}/heartbeat | lease 갱신, 취소 여부 확인 |
| POST /jobs/{id}/complete | 후보 검사 후 원자적 final 발행 |
| POST /jobs/{id}/fail | 실패·재시도 및 종료 확인 |
| POST /jobs/{id}/cancel, /retry | 생산자 소유 작업 명령 |
| GET /queue-status | kinds별 대기/실행/오류·슬롯, shared 점유·격리 |

## Backend 보고서 접수

Backend가 클라이언트 멱등 키와 원본 deadline을 저장한 뒤 보냅니다. 직접 실행을 테스트할 때만 아래 내부 입력을 사용합니다.

```json
{
  "contract_version": "1.3", "source_module": "backend", "source_key": "manual:unique-client-key", "kind": "report",
  "input": {
    "scope": {"clusters": [{"cluster_id": "cpc-1", "namespaces": null}]},
    "time_range": {"start": "2026-09-15T00:00:00Z", "end": "2026-09-16T00:00:00Z"},
    "timezone": "Asia/Seoul", "topic_ids": ["O01"], "group_by": ["cluster"]
  },
  "deadline_at": "2026-09-19T00:00:00Z", "execution_profile_revision": "local-v1"
}
```

실제 요청에서는 미래 deadline과 고유 키를 지정하세요. 자동 요청은 원본 `dispatch_deadline`과 `snapshot_ref`도 전달합니다. deadline·snapshot을 재전송마다 변경하면 멱등 충돌입니다. RCA input은 `scope,incident_id,evidence_version,analysis_profile_revision,incident_time,time_range,purpose_ids`와 선택적 `target`이며 실제 incident_evidence_versions 레코드가 있어야 합니다. Incident는 `snapshot={input:<같은 RCA 입력>,evidence:<증거 원본>}` 및 `content_hash=contract.Hash(snapshot)`를 저장합니다. JC는 정규화한 input 전체의 일치와 snapshot 해시를 확인합니다. 해당 immutable snapshot은 claim.input.incident_snapshot으로 전달합니다.

## Worker

등록: `{worker_id,boot_id,kind,capacity_profile_id,supported_contract_versions?}`. boot_id는 새 시작마다 생성한 UUID, kind는 rca/report, 프로필 예시는 rca-v1/report-v1입니다. 임의 slots 입력은 거절합니다. 지원 계약 생략은 `["1.3"]`이며 RCA는 1.3/1.4, report는 1.3만 등록할 수 있습니다. 빈 배열·null·알 수 없는 버전·kind 불일치는 422입니다. 배열 순서와 중복을 정규화하며 같은 worker/boot의 capability 변경은 409 `worker_conflict`입니다. 변경하려면 새 boot로 등록합니다.

인수: `{worker_id,boot_id,kind}`. 반환은 `{job_id,kind,input,attempt_no,claim_token,lease_expires_at,deadline_at,versions,budget,heartbeat_seconds}`. `budget`에는 attempt_limit/total_limit/reserved_total이 있습니다. 인수 응답을 잃으면 같은 작업을 다시 배정받지 않으며 기존 lease 복구 정책을 따릅니다.

JC가 등록 당시 저장한 지원 계약에 맞는 작업만 배분합니다. claim body에 capability를 넣으면 422입니다. `versions.input_contract`는 접수 버전이며, 이 필드가 없는 과거 job만 응답에서 1.3으로 해석합니다. DB의 기존 input/hash/versions는 재작성하지 않습니다. 명시적인 null·빈 문자열·알 수 없는 버전은 1.3으로 해석하지 않고 배분하지 않습니다. 호환 Worker가 없으면 `worker_unavailable`, 호환 Worker가 있지만 슬롯이 부족하면 `capacity_wait`입니다. 호환되지 않는 선두 작업은 뒤의 실행 가능한 작업이나 다른 종류의 교대 배분을 막지 않습니다.

heartbeat: `{attempt_no,claim_token,stage,remote_call_state}`. remote_call_state는 `not_started | running | terminated | unknown`입니다. 추론이 시작된 뒤 not_started로 되돌릴 수 없습니다. 취소를 받으면 새 호출을 중단하고 실제 종료 확인 뒤 fail을 보냅니다.

fail: `{attempt_no,claim_token,code,retryable,remote_call_state}`. code는 transient_error/dependency_unavailable/timeout/invalid_input/invalid_result/insufficient_data/budget_exhausted/cancelled/internal_error입니다. 앞의 일시 오류 3종만 retryable=true일 때 자동 재시도합니다. not_started/terminated만 슬롯 반환 근거로 취급하고 running/unknown은 격리합니다. insufficient_data를 부분 결과로 발행하려면 실패 대신 유효한 partial/blocked candidate를 저장하고 complete합니다.

complete: `{attempt_no,claim_token,candidate_id,content_hash}`. Agent가 먼저 result_candidates에 같은 job/attempt/kind, schema_version=고정 profile schema, validation_status=valid인 결과를 저장합니다. content_hash는 공통 `contract.Hash(body)`의 Go JSON 직렬화 SHA-256입니다. JC는 저장 body의 hash까지 다시 확인합니다. 같은 candidate/hash 재전송은 최초 성공 응답, 다른 후보나 오래된 토큰은 409입니다. published_result_id 외 후보는 Backend가 공개하지 않습니다.

후보 `body.versions.input_contract`도 job과 일치해야 합니다. 1.3 후보만 필드 부재를 허용하며, 1.4의 부재·다른 버전·알 수 없는 버전은 422 `invalid_candidate`입니다. 목적 선택 trace와 assessments의 의미 검증은 Worker 공통 validator의 책임이며 JC가 대신 판단하지 않습니다.

## RCA 1.4 접수

`POST /jobs/rca`는 기존 1.3과 신규 1.4를 별도로 검증합니다. 보고서 접수·cancel/retry 계약은 1.3을 유지합니다. 1.4의 `source_key`는 `incident:<incident_id>:first`, `snapshot_ref`는 `{incident_id,revision:1}`, input의 `evidence_version`은 1이어야 합니다. input은 `scope,incident_id,evidence_version,incident_time,time_range`와 선택적 `target,prior_incident_id`를 받습니다. `purpose_ids,analysis_profile_revision`은 null을 포함해 금지하며 JC가 기본 목적을 주입하지 않습니다.

1.3과 동일하게 실제 Incident snapshot의 hash·scope·정규화 입력 일치를 확인하고 동일 키/동일 요청은 기존 job, 다른 요청은 409로 처리합니다. 기존 outbox와 과거 job은 재작성하지 않습니다. 새 접수의 `jobs.versions.input_contract`를 envelope에서 고정하므로 호출자나 실행 설정이 덮어쓸 수 없습니다.

현재 제품 RCA Worker는 1.3만 지원합니다. JC 접수·배분 호환 구현만으로 1.4 실행 준비가 완료되는 것은 아니며, RCA 목적 선택·이력 확보·공통 validator 및 결과 소비자 검증 후 1.4 지원을 등록해야 합니다.

## 명령

헤더 `Idempotency-Key`, `If-Match: "<version>"`. body는 `{contract_version:"1.3",source_module:"backend",input:{reason:"..."}}`. Incident는 source_module=incident 및 input.incident_id가 자기 RCA와 일치해야 합니다. 같은 명령 재전송은 최초 If-Match를 그대로 사용하세요. receipt를 먼저 확인하므로 이후 version 증가 때문에 재전송을 거절하지 않습니다.

queue-status 형식은 `{kinds:{rca:{waiting,running,failed,expired,worker_unavailable,capacity_wait,inference_quarantined,capacity_limit,reserved_slots,worker_available},report:{...}},shared:{limit,reserved_slots,quarantined_slots},config_revision,observed_at}`입니다. Backend의 `/api/v1/service-status`가 이를 읽기 전용 `queue`로 반환합니다.
