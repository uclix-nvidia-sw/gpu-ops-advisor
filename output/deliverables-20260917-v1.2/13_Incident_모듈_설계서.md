# 13. Incident 모듈 설계서

문서 버전: 1.2 · 모듈 ID: incident · 대응: F04, F05 연계 · 독립 실행·배포

## 1. 책임과 진입 경로

Grafana → 공개 Gateway/Backend Webhook 경로 → Incident 내부 API로 전달한다. Backend는 크기·기본 수신 자격과 라우팅을 확인하고 **검증에 필요한 원문 bytes와 서명 헤더를 변형하지 않는다.** Incident가 profile별 송신자 검증·원문 파싱·CPC 결정·정규화·중복·상관·재발·사건 상태를 소유한다.

브라우저의 사건 목록·상태 변경도 Backend를 통해 Incident를 호출한다. Incident는 원인 분석을 실행하지 않고 RCA Agent에 저장된 요청을 전달한다. 사건 처리 규칙은 Backend나 RCA에서 중복 구현하지 않는다.

## 2. 내부 API

접두사는 `/internal/v1`이다.

| Method·경로 | 역할 | 결과 |
|---|---|---|
| POST /webhooks/grafana/{profile_id} | profile 인증·정규화·중복 처리 | 커밋 후 receipt_id·incident_refs·dispatch_refs·duplicate |
| GET /incidents, /incidents/{id} | 허용 사건·관측·관련 결과 | 사건·version·전달 상태·접수된 job 참조 |
| PATCH /incidents/{id} | If-Match·상태·종결 사유 | 변경 사건·감사 이력 |
| GET /dispatches/{id} | 현재 해당 사건 범위 | 전달·실제 job 접수 상태 |
| POST /dispatches/{id}/cancel | If-Match·멱등 키 | 15의 취소 경합 계약 |
| GET /health/live, /health/ready | 내부 상태 | 수신·저장 준비 |

소유 데이터: incidents, incident_observations, source_module=incident 전달 행과 관련 감사. RCA jobs를 직접 INSERT/UPDATE하지 않는다. 사건에 연결된 RCA 결과는 공통 권한 조회 또는 RCA API로 읽는다.

## 3. 사건 처리 정책

1. profile별 인증·크기·스키마를 검증하고 허용 CPC를 서버 설정에서 확정한다. 원문 cluster 라벨로 권한을 확장하지 않는다.
2. 원문과 원본 시각·수신 시각·parser revision을 보존한다. production 계약에 없는 값은 unknown으로 보존한다.
3. 원본 관측 중복, 알림 재전송, Incident 상관, 분석 멱등을 별도 키로 처리한다.
4. 동일 source_event_key와 동일 의미 hash/원본 revision의 재전송만 receipt_count·last_received_at을 갱신한다. 같은 이벤트 키라도 firing→resolved 등 의미가 바뀌면 별도 관측 revision으로 보존한다.
5. 새로운 의미 있는 증거는 사건 evidence_version을 올리고 새 RCA 전달 의도를 저장한다. 단순 수신 시각 변경은 증거 변경이 아니다.
6. 사건·관측과 RCA 전달 의도를 같은 DB 트랜잭션에서 커밋한 뒤 응답한다. RCA job 접수는 별도 내부 API로 수행하고 15의 동일 키 복구를 적용한다. 처리 실패는 Webhook 재전송으로 복구 가능해야 한다.

알림 `firing/resolved`는 생산자 상태다. Incident는 `open→investigating→resolved→closed`를 사용한다. **같은 episode**의 정정·추가 근거는 기존 사건의 evidence_version을 올리고 새 분석으로 연결하며 필요 시 resolved/closed→open으로 재개한다. **새 episode**의 재발은 새 Incident와 recurrence_of로 기록한다. resolved 전환에는 운영 판단 또는 명시적인 검증 정책 근거가 필요하다. Grafana resolved·RCA succeeded만으로 자동 종결하지 않는다.

상관 키는 CPC·해결된 자산·증상·생산자 계약·발생 episode를 사용한다. episode의 시간창은 오류 종류별 C08 정책값이다. 알림 fingerprint만으로 시간상 다른 재발을 영구 합치지 않는다. 별도 재발 사건은 `recurrence_of`로 이전 사건과 연결한다.

episode 경계를 판단할 수 없으면 원본 관측을 correlation_status=unknown으로 보존하고 기존 확정 episode에 임의 합치지 않는다. 사건률 산정에는 확정 episode만 사용하고 미해결 관측 건수를 별도 표시한다. 여러 GPU 항목을 가진 원문은 자식 항목별 식별·의미 hash를 보존해 모두 처리한다.

새 알림 없는 사건의 재확인은 S07의 명시적인 ‘상태 다시 확인’으로 같은 incident_id의 새 RCA(R01/R09) job을 접수하는 방식을 채택한다. 그 시각의 근거와 운영자 판단을 기록한다. 별도 자동 재조회 모니터를 추가하지 않는다. 원문 조회 실패·유효하지 않은 Healthy는 회복 근거가 아니며 11 §3.4의 검사 유효성 표를 적용한다.

## 4. 사건 저장과 RCA 전달

v1.1의 사건+job 단일 커밋은 적용하지 않는다. **원문 수신·사건/증거 버전 변경·RCA 전달 의도**를 Incident 트랜잭션에 함께 저장한다. 같은 사건·evidence_version·analysis_profile_version은 같은 전달 키를 사용한다. RCA job의 커밋은 이후 RCA 모듈에서 수행한다.

전달 루프는 `POST RCA /internal/v1/analyses`를 호출한다. incident_id·입력 증거 버전·대상·시각·scope·purpose_ids와 dispatch_id를 전달한다. RCA는 호출 주체와 원본 사건 범위를 검증한 뒤 job을 저장한다. Incident가 응답을 잃어도 같은 ID로 재전송하여 같은 job을 받는다.

Webhook 성공은 원문과 필요한 전달 의도의 영속 저장을 뜻한다. 그 시점에 RCA job이 아직 없을 수 있다. `dispatch_refs[].job_id=null`이면 화면은 “조사 요청 전달 중”을 표시한다. RCA 불가 상태에서도 DB 수신 저장이 성공하면 Webhook은 202로 수신을 확인할 수 있다. Incident DB 커밋 실패는 성공 응답하지 않는다.

새 증거 버전은 새 분석 요청이며 단순 재전송은 새 분석 요청이 아니다. 정상 관측처럼 조사 조건이 없는 이벤트는 dispatch_refs가 빈 배열일 수 있다. source 식별·재발 정책과 자료 부족 처리는 원문 계약대로 유지한다.

## 5. 장애·완료

Incident 중단 시 Webhook은 503과 재전송 정책으로 복구한다. Backend가 메모리 큐에만 저장하고 성공을 반환하지 않는다. Grafana 재전송 정책과 원문 보존 한계는 C08에 명시한다. RCA 중단 시 사건 수신은 유지하고 전달 적체를 계측한다.

T07~T09, T44에서 사건 커밋 직후 종료, RCA 접수 응답 유실, 동일 알림 20회, 새 증거·재발을 시험한다. 원문·사건·전달이 보존되고 같은 입력의 job은 하나여야 한다. T48에서 전달 취소와 늦은 RCA 접수를 검증한다. 실제 NOT RUN.

[11 RCA](11_RCA_Agent_모듈_설계서.md) · [03 데이터](03_데이터_설계서.md) · [15 전달 계약](15_모듈간_호출과_공통실행_계약.md)
