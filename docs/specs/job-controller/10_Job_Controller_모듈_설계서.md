# 10. Job Controller 모듈 설계서

버전 1.3 · 모듈 job-controller · 독립 실행·배포 · F06/F07/F11

## 역할과 경계

영속 큐에 요청을 접수하고 **현재 배포된 Agent와 설정된 처리 한도 안에서만 잡을 배분**한다. jobs·attempts·queue receipt·실행 점유·용량 예약을 소유한다. Agent 배포·레플리카·노드·GPU 생성, 자동 확장, 달력 일정, RCA/보고서 계산·추론은 하지 않는다.

PostgreSQL의 종류별 논리 큐를 사용한다. 별도 브로커/분산 Scheduler는 추가하지 않는다. RCA는 Incident, 보고서는 Backend만 생성한다. 큐에는 `kind=rca|report`만 존재한다.

## 내부 API

접두사는 `/internal/v1`. 상세 필드·오류는 [14 계약](../common/14_모듈간_호출과_공통실행_계약.md)을 따른다.

| Method·경로 | 호출자·처리 |
|---|---|
| POST /jobs/rca | Incident: incident_id·evidence_version 필수, 커밋 후 202 |
| POST /jobs/report | Backend: 즉시/정기 입력, 커밋 후 202 |
| GET /receipts/{source_module}/{source_key} | 생산자: 같은 요청의 job 조회 |
| GET /jobs, /jobs/{id} | Backend/생산자: 상태·결과 참조 |
| POST /workers/register | 기존 배포 Agent: boot_id·kind·profile 등록 |
| POST /claims | 여유 있는 Agent: 자기 kind의 잡 1개 인수, 없음=204 |
| POST /jobs/{id}/heartbeat | 현 attempt·claim_token: lease 갱신·취소 지시 조회 |
| POST /jobs/{id}/complete | 현 attempt: 후보 결과 확인·원자적 final 참조 확정 |
| POST /jobs/{id}/fail | 현 attempt: 오류·추론 종료 여부에 따라 재시도/실패 |
| POST /jobs/{id}/cancel, /retry | Backend는 report만; Incident는 자기 사건 RCA만 |
| GET /queue-status | 유형별 대기·실행·오류·용량·대기 사유 |
| GET /health/live, /health/ready | 생존 / DB·큐 계약·설정 준비 |

제품 인증은 제외한다. source_module/worker_id는 업무 추적과 타입 검증용이며 신원 인증을 대신하지 않는다. GUI가 내부 API에 직접 연결되지 않게 배치한다.

## 잡 배분

Agent가 여유 슬롯이 있을 때 pull하고 Job Controller가 claim 응답으로 잡을 배분한다. Agent는 DB에서 jobs를 직접 점유하거나 다른 유형 잡을 실행하지 않는다.

1. DB 시간과 Worker 등록/배포 프로필을 확인한다. 시작마다 새 boot_id를 사용한다.
2. 현재 Worker 점유 < worker_slots, 유형별 점유 < kind_limit, 공유 점유 < shared_limit 조건을 검사한다. 값은 서버 운영 설정이며 Agent가 임의 상향하지 못한다.
3. 공통 capacity 행을 잠그고, 오래된 실행 가능 요청부터 jobs 행 잠금으로 선택한다. 동일 트랜잭션에서 attempt 증가·claim_token·lease·슬롯 예약을 확정한다.
4. 반환 전 커밋한다. 적격 잡이나 슬롯이 없으면 204이며 잡은 queued/retry_wait로 유지한다. Agent는 backoff+jitter로 다시 인수한다.

초기 배분 정책은 종류별 `(eligible_at,created_at,id)` FIFO다. 공유 슬롯 경합은 두 종류에 실행 가능한 잡과 최근 유효 Worker가 있으면 번갈아 기회를 주며, 상대 종류가 실행 불가하면 현재 종류를 막지 않는다. `last_granted_kind`와 Worker freshness를 같은 capacity 잠금에서 평가한다. 긴급 우선순위·선점·동적 용량 산정은 추가하지 않는다.

설정 한도를 낮추면 실행 중 잡을 강제 종료하지 않고 신규 claim을 멈춘다. 점유가 새 한도 아래로 내려가면 재개한다. Agent가 0개인 종류는 worker_unavailable, 슬롯 부족은 capacity_wait, 공유 추론 격리는 inference_quarantined로 조회한다.

## 상태와 복구

`queued → running → succeeded|retry_wait|failed`. retry_wait는 eligible_at 이후 running으로 전이한다. queued/retry_wait는 cancelled/expired로 종료할 수 있다. running 취소는 요청 플래그를 먼저 기록하고 종료 확인 후 cancelled, deadline 도달은 expired다. terminal 결과는 불변이다.

재시도는 같은 job의 새 attempt이며 original deadline·누적 예산·max_attempts를 초기화하지 않는다. 실패 소진은 failed이고 데이터 부족만으로 재시도하지 않는다. 수동 retry도 남은 예산과 재시도 가능한 오류가 있을 때만 허용한다. succeeded/cancelled/expired는 같은 job으로 재시도하지 않는다.

현재 attempt/claim_token/lease/deadline/취소 조건이 유효할 때만 complete를 받는다. 늦은 결과는 409 stale_attempt이며 새 attempt와 final을 덮어쓸 수 없다. 동일 완료 재전송은 같은 candidate/hash일 때 기존 응답을 반환한다.

DB 장애 시 신규 claim·lease 갱신·성공 확정을 중단한다. Agent는 lease를 유지하지 못하면 새 도구/추론 호출을 멈추고 재연결 뒤 유효성을 확인한다. 오래된 Worker가 실행 중일 수 있으면 공유 추론 점유를 자동 해제하지 않는다. 원격 종료 불명은 quarantine으로 남겨 운영 확인 또는 검증된 원격 최대 수명 이후 해제한다.

## 용량의 보수적 기준

초기에는 job 한 개가 실행되는 동안 공유 추론 슬롯 하나를 예약하고 한 job의 모델 호출을 직렬 실행한다. 관측 조회 중에도 슬롯을 잡으므로 처리량에 한계가 있지만 동시 추론 한도를 단순하게 보장한다. job 내부 병렬 LLM 호출이나 예약 없이 모델을 부르는 경로는 금지한다. 필요성이 측정되면 별도 변경에서 호출 단위 예약을 설계한다.

운영자가 배포 수·worker_slots·kind_limit·shared_limit을 정한다. Job Controller는 그 숫자 안에서 배분만 한다. 수동 변경 절차는 [06](../06_배포_운영_인계서.md), 경합 시험은 [05](../05_테스트_검수_기준서.md)다.
