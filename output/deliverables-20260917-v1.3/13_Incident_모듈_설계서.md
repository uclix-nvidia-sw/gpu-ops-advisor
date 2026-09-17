# 13. Incident 모듈 설계서

버전 1.3 · 모듈 incident · 독립 실행·배포 · F02/F03

## 목적과 진입 경로

Grafana Webhook을 받아 사건·증거를 정리하고 Job Controller의 RCA 큐에 실행을 요청한다. **RCA 업무 요청을 생성하는 유일한 모듈**이다. GUI·Backend·보고서 Agent가 직접 RCA를 접수하지 않는다. Grafana는 Backend를 경유하지 않는다.

| Method·경로 | 처리 |
|---|---|
| POST /webhooks/grafana | 크기·배열·시각·라벨 검증, 알람·사건·outbox 커밋 후 202 |
| GET /internal/v1/incidents, /incidents/{id} | 사건·증거 revision·job 연결 조회 |
| PATCH /internal/v1/incidents/{id} | 메모·acknowledged/closed 등 검토 상태, RCA 실행 부수 효과 없음 |
| GET /internal/v1/health/live, /health/ready | 생존 / DB·입력 계약·전달 준비 |

## 중복·사건 정책

Webhook의 alerts 배열 전체를 처리한다. 식별 불가 자식은 원문 위치·오류로 보존하고 유효 자식의 사건을 소거하지 않는다. 동일 배치 재전송은 같은 접수 receipt로 처리한다.

알람 키는 `(grafana_source,cluster_id,fingerprint,startsAt)`다. 본문 해시는 정확히 같은 전송을 식별하고 firing/resolved 갱신은 동일 알람 생명주기에 반영한다. 수신 시각과 발생 시각을 구분한다. 잘못된/오래된 알람도 원문·이유를 보존하되 실행 적격 여부는 운영 정책으로 판정한다.

incident는 대상·알람 생명주기별로 연결한다. source_key=`incident:<incident_id>:evidence:<version>:profile:<revision>`로 RCA 요청을 생성한다. 동일 키에 한 job만 생긴다. 의미 있는 새 증거와 등록 정책이 있을 때만 evidence_version을 올려 새 요청을 만든다. heartbeat 수준 반복 알람이나 resolved 수신만으로 재분석하지 않는다.

## 영속 전달

알람·사건·불변 입력 snapshot·enqueue_outbox를 하나의 Incident 트랜잭션에 저장한다. 전달 루프가 `/internal/v1/jobs/rca`를 같은 source_key로 호출한다. JC 커밋 확인 후 job_id를 기록한다. JC 장애·응답 유실에도 새 키를 만들지 않고 동일 outbox를 재전송한다. RCA Worker가 없는 경우 JC 접수는 성공하며 queued로 남는다.

RCA input에는 incident_id·evidence_version·analysis_profile_revision·target 또는 식별 가능한 사건 범위·incident_time·scope·purpose_ids·절대 time_range가 필수다. 고정된 사건 snapshot과 다르면 거절한다. 원본에 없는 GPU UUID를 임의 생성하지 않는다.

## 회복·상태

사건 상태 `open|acknowledged|resolved|closed`와 알람 firing/resolved, RCA job.status는 별개다. Grafana resolved를 장비/업무 회복이나 사건 closed로 자동 승격하지 않는다. 장비 회복은 유효한 정상 검사와 등록 관측 조건, 업무 회복은 실제 작업 진행 근거가 필요하다. GUI 검토 기록으로 acknowledged/closed를 변경해도 기존 final과 실행 입력은 불변이다.

자동 재시도는 JC가 같은 RCA job으로 처리한다. 새 RCA 업무 요청은 Incident의 새 증거·분석 정책에서만 생성한다. GUI의 직접 RCA 재시도/재분석 버튼은 없다.

[RCA](11_RCA_Agent_모듈_설계서.md) · [DB](03_데이터_설계서.md) · [멱등 전달](14_모듈간_호출과_공통실행_계약.md)
