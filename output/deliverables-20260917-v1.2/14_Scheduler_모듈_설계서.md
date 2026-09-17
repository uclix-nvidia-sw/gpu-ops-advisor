# 14. Scheduler 모듈 설계서

문서 버전: 1.2 · 모듈 ID: scheduler · 대응: F07 · 독립 실행·배포

## 1. 책임

Scheduler는 일정 생성·수정·일시중지, 시간대·달력·분석 기간 계산, 발생 이력·누락·복구, 보고서 요청 전달을 맡는다. Backend에 스케줄 실행 루프를 두지 않는다. 보고서 집계와 LLM 호출은 보고서 Agent의 책임이다.

Scheduler는 내부 관리 API와 주기적인 발생/전달 루프를 가진다. 복제본이 여러 개여도 공유 DB 잠금과 유일 키로 한 발생을 한 번만 예약한다. cron 제품·별도 메시지 브로커는 필수로 추가하지 않는다.

## 2. 내부 API

접두사는 `/internal/v1`이다.

| Method·경로 | 책임 | 응답 |
|---|---|---|
| GET/POST /schedules | 허용 일정 조회·생성 | 목록 / 201 schedule_id |
| GET/PATCH /schedules/{id} | 현재 권한·If-Match·revision 변경 | 일정·effective_at·다음 시각 |
| GET /schedules/{id}/occurrences | revision/status/from/to/cursor | 발생·고정 기간·dispatch_id·job_id·사유 |
| GET /dispatches/{id} | 소유자·현재 권한 | 전달 상태 |
| POST /dispatches/{id}/cancel | If-Match·멱등 키 | 전달 또는 이미 생성된 job의 취소 |
| GET /health/live, /health/ready | 내부 상태 | DB·달력 계약 준비 |

소유 데이터는 schedules, schedule_occurrences, source_module=scheduler 전달 행, 설정 revision 감사다. 보고서 jobs와 결과는 직접 변경하지 않는다.

## 3. 달력과 revision

입력은 `frequency=daily|weekly|monthly`, `local_time=HH:mm`, `timezone`, 주간이면 `weekday=1..7`, 월간이면 `day=1..31`, `period=previous_complete_day|week|month`, `enabled`, 보고서 조건이다. frequency와 period는 각각 대응하는 값을 사용한다. 월간 실행일이 없는 달은 말일을 사용한다. 주간 기간은 월요일 00:00부터 다음 월요일 00:00까지다.

기간은 일정 시간대의 완료된 달력 구간을 UTC로 변환한다. 서머타임으로 없는 실행 시각은 다음 유효 시각, 중복 시각은 첫 번째 발생을 선택하고 UTC 발생 ID를 저장한다. 중단 복구는 C08의 catch-up 기간·최대 건수 안에서 누락 발생을 접수하고 나머지는 missed 기록으로 남긴다. 자동으로 모든 과거 보고서를 무제한 생성하지 않는다.

일정 소유자의 권한은 생성·수정·실행 시 재확인한다. 권한 상실 시 일정은 차단 상태와 사유를 기록하며, scope를 조용히 바꿔 보고서를 생성하지 않는다.

일정 수정은 schedule 행을 잠그고 커밋 시각 `effective_at`을 기록한다. 그 시각 미만의 예정 발생분은 이전 revision, 해당 시각 이상은 새 revision을 적용한다. pending부터 occurrence의 조건·범위·기간은 불변이고 accepted 이후 job 참조도 고정한다. 아직 occurrence와 전달 의도가 저장되지 않은 이전 발생분은 이전 불변 설정 스냅샷과 현재 권한으로 catch-up 또는 missed/blocked를 판정한다. revision 변경이 과거 조건을 소급 변경하지 않는다.

스케줄러와 수정은 같은 schedule 잠금을 사용한다. 동일 `schedule_id + period_start + period_end`의 자동 보고서 접수는 revision·시각 변경과 무관하게 한 번이다. 새 revision이 이미 pending 또는 accepted로 예약된 같은 기간을 다시 가리키면 기존 dispatch와 확인된 job을 참조하는 missed(reason=already_reserved_period) 발생 기록을 남긴다. 다른 시간대 때문에 실제 UTC 기간이 달라지는 경우에는 별도 기간으로 표시한다. 같은 기간을 의도적으로 다시 만들려면 POST reports의 parent_job_id로 새 사용자 작업을 접수한다. 비활성화 기간에는 새 발생을 접수하지 않고 missed를 남기며, 다시 켜도 그 기간을 자동 재생성하지 않는다.

일정 비활성화는 그 효력 시각 이후의 새 발생을 막는다. 이미 저장한 pending/accepted 발생은 자동 취소하지 않는다. 취소하려면 발생별 dispatch 또는 job에 명시적인 취소를 요청한다. 설정 수정도 저장된 발생의 조건을 소급 변경하지 않는다.

## 4. 발생 예약과 보고서 접수

1. 해당 schedule 행을 잠그고 예정 시각의 유효 revision·소유자 권한·분석 기간을 계산한다.
2. 같은 schedule_id와 정확한 UTC period_start/period_end에 canonical 발생 예약이 있는지 확인한다.
3. 없으면 occurrence(status=pending, canonical=true)와 보고서 요청 module_dispatches를 **한 Scheduler 트랜잭션**에 저장한다.
4. 전달 루프가 고정 scope·절대 기간·주제·revision으로 `POST Report /internal/v1/reports`를 호출한다.
5. 보고서 Agent의 job 커밋 응답 후 occurrence를 accepted로 바꾸고 job_id를 연결한다.
6. 응답 유실·재시작은 동일 dispatch_id로 복구한다. pending 전달과 accepted 실행을 모두 중복 예약 검사에 포함한다.

동일 기간의 새 revision 발생은 기존 canonical 전달/작업을 참조하며 missed(reason=already_reserved_period)로 기록한다. pending 상태를 무시하고 새 revision으로 두 번째 job을 만들지 않는다. 의도적인 재생성은 사용자가 parent_job_id로 직접 보고서를 요청한다.

발생 상태는 pending/accepted/missed/blocked/failed다. pending은 Agent 접수 미확인, accepted는 job 참조 확정이며 분석 성공을 뜻하지 않는다. 현재 권한 상실은 blocked, 전달 deadline·재시도 소진은 failed로 사유를 기록하되 15 §4.1의 잠금·접수 확인을 먼저 수행한다. 명시 취소로 전달이 cancelled가 되면 occurrence는 missed(reason=cancelled_before_acceptance)로 남긴다. 이미 accepted인 발생은 job 취소 후에도 accepted와 job 참조를 보존한다.

## 5. 복구·계측·완료

발생 루프 중단은 C08 catch-up 범위에서 누락을 계산한다. **이미 생성된 pending 전달의 재전송은 새 발생 생성이 아니므로** catch-up과 별도로 복구한다. 다만 전달 deadline·권한·취소를 지킨다. 보고서 Agent 장애 중에는 Scheduler의 일정 관리와 발생 보존이 가능해야 한다.

next_run 지연, pending 전달 수·최고 대기시간, missed/blocked/failed 사유, 실제 job 연결을 계측한다. T22·T45에서 복제본 경합·응답 유실·월말·DST·revision 변경·같은 기간 pending을 검증한다. T47은 Scheduler만 재시작하고 사용자 직접 보고서가 유지되는지 확인한다. 전체 NOT RUN.

[12 보고서](12_보고서_Agent_모듈_설계서.md) · [03 데이터](03_데이터_설계서.md) · [15 공통 호출](15_모듈간_호출과_공통실행_계약.md)
