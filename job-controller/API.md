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

등록: `{worker_id,boot_id,kind,capacity_profile_id}`. boot_id는 새 시작마다 생성한 UUID, kind는 rca/report, 프로필 예시는 rca-v1/report-v1입니다. 임의 slots 입력은 거절합니다.

인수: `{worker_id,boot_id,kind}`. 반환은 `{job_id,kind,input,attempt_no,claim_token,lease_expires_at,deadline_at,versions,budget,heartbeat_seconds}`. `budget`에는 attempt_limit/total_limit/reserved_total이 있습니다. 인수 응답을 잃으면 같은 작업을 다시 배정받지 않으며 기존 lease 복구 정책을 따릅니다.

heartbeat: `{attempt_no,claim_token,stage,remote_call_state}`. remote_call_state는 `not_started | running | terminated | unknown`입니다. 추론이 시작된 뒤 not_started로 되돌릴 수 없습니다. 취소를 받으면 새 호출을 중단하고 실제 종료 확인 뒤 fail을 보냅니다.

fail: `{attempt_no,claim_token,code,retryable,remote_call_state}`. code는 transient_error/dependency_unavailable/timeout/invalid_input/invalid_result/insufficient_data/budget_exhausted/cancelled/internal_error입니다. 앞의 일시 오류 3종만 retryable=true일 때 자동 재시도합니다. not_started/terminated만 슬롯 반환 근거로 취급하고 running/unknown은 격리합니다. insufficient_data를 부분 결과로 발행하려면 실패 대신 유효한 partial/blocked candidate를 저장하고 complete합니다.

complete: `{attempt_no,claim_token,candidate_id,content_hash}`. Agent가 먼저 result_candidates에 같은 job/attempt/kind, schema_version=고정 profile schema, validation_status=valid인 결과를 저장합니다. content_hash는 공통 `contract.Hash(body)`의 Go JSON 직렬화 SHA-256입니다. JC는 저장 body의 hash까지 다시 확인합니다. 같은 candidate/hash 재전송은 최초 성공 응답, 다른 후보나 오래된 토큰은 409입니다. published_result_id 외 후보는 Backend가 공개하지 않습니다.

## 명령

헤더 `Idempotency-Key`, `If-Match: "<version>"`. body는 `{contract_version:"1.3",source_module:"backend",input:{reason:"..."}}`. Incident는 source_module=incident 및 input.incident_id가 자기 RCA와 일치해야 합니다. 같은 명령 재전송은 최초 If-Match를 그대로 사용하세요. receipt를 먼저 확인하므로 이후 version 증가 때문에 재전송을 거절하지 않습니다.

queue-status 형식은 `{kinds:{rca:{waiting,running,failed,expired,worker_unavailable,capacity_wait,inference_quarantined,capacity_limit,reserved_slots,worker_available},report:{...}},shared:{limit,reserved_slots,quarantined_slots},config_revision,observed_at}`입니다. Backend의 `/api/v1/service-status`가 이를 읽기 전용 `queue`로 반환합니다.
