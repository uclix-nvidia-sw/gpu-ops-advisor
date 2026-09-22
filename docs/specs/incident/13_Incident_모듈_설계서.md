# 13. Incident 모듈 설계서

현행 구현 계약 1.3 · 변경 목표 RCA 접수 계약 1.4 · 모듈 incident · F02/F03

## 0. 변경 기준과 구현 상태

2026-09-22 설계 변경. **Incident는 알람 중복 제거와 최초 데이터의 영속 전달을 담당하고, RCA Agent가 파싱·조사 목적·Runbook/일반 로그 분석 경로를 결정한다.** 아래는 추가 개발 기준이며 이번 변경은 문서에만 적용한다.

현재 코드는 `alertname`에 `analysis_policies`를 매칭하고 기본 `GPUAlert`에 R01/R02를 지정한다. Xid/SXid 코드 의미를 분석하는 로직은 현재도 Incident에 없다. 정책 미등록 시 RCA 미생성, 의미 있는 증거/정책 revision 변경 시 새 RCA 생성 동작은 목표에서 제거한다. 실제 전환은 [14 실행 계약](../common/14_모듈간_호출과_공통실행_계약.md)을 따른다.

## 1. 역할과 진입 경로

Grafana Webhook의 유효한 알람을 생명주기로 구분하고, 최초 firing만 불변 snapshot과 outbox로 저장해 JC에 전달한다. GPU fault뿐 아니라 입력 계약을 만족하는 다른 fault도 이름별 분석 정책 없이 접수한다. 분석 지원 여부와 부족 근거는 Agent가 판단한다.

Incident는 오류 코드 추출·Runbook 검색·로그 원인 분석·R01~R09 배정·증거 변화의 의미 판정을 하지 않는다. 입력 형식/크기/시각/scope 검증, 영속성, 전달 재시도와 사건 조회·검토 메타데이터는 기반 기능으로 유지한다. **RCA 업무 요청의 유일한 생산자**이며 GUI·Backend·보고서 Agent는 RCA를 직접 요청하지 않는다.

| Method·경로 | 처리 |
|---|---|
| POST /webhooks/grafana | 입력 검증, 최초/중복/해제 구분, 영속 커밋 후 202 |
| GET /internal/v1/incidents, /incidents/{id} | 최초 snapshot·알람 상태·RCA job 연결 조회 |
| PATCH /internal/v1/incidents/{id} | 메모·acknowledged/closed 등 검토 상태, 중복 해제·RCA 실행 부수 효과 없음 |
| GET /internal/v1/health/live, /health/ready | 생존 / DB·입력 계약·전달 준비 |

## 2. 동일 알람과 최초 1회 규칙

중복 키는 `(grafana_source, cluster_id, fingerprint, startsAt)`다. source는 수신 설정, cluster는 등록 범위로 검증한다. fingerprint는 생산자의 알람 신원이고 startsAt은 해당 firing 생명주기의 시작 시각이다. 서로 다른 GPU·Node·Pod·규칙은 구별 가능한 fingerprint를 제공해야 한다. 이름이나 로그 문구가 비슷하다는 이유로 합치지 않는다.

반복 전송에서는 fingerprint와 startsAt이 유지되어야 한다. 변동 수치·severity 등을 라벨로 사용해 fingerprint가 달라지거나 매번 startsAt을 바꾸면 별도 사건으로 접수될 수 있다. Incident가 오류 의미 추론으로 이를 보정하지 않는다. 배포 전에 실제 payload의 신원 안정성을 검수한다.

**첫 알람은 Incident가 최초로 유효 접수한 firing 원문**이다. 뒤늦게 도착한 payload로 첫 snapshot을 교체하지 않으며 발생 시각과 수신 시각을 구분한다.

| 수신 조건 | 사건·전달 처리 |
|---|---|
| 처음 보는 키의 수신 조건을 만족한 firing | 사건·최초 snapshot·outbox 각 1개, RCA 요청 1개 |
| 같은 키의 firing 반복 | 중복 접수로 성공 응답; 새 사건·snapshot·outbox·job 없음 |
| 같은 키에서 summary/message/error_code/annotation/수치 변경 | 내용이 달라도 중복; 의미 비교나 재분석 없음. fingerprint 변경은 별도 키 |
| 같은 키의 resolved | 알람 상태만 해제로 갱신; snapshot 변경·RCA 생성 없음 |
| resolved가 먼저 도착한 키 | 해제된 생명주기만 보존; 뒤늦은 동일 키 firing도 실행하지 않음 |
| 동일 fingerprint지만 새 startsAt의 firing | 새 생명주기·사건으로 최초 1회 전달; 이전 resolved 유실과 무관 |
| 다른 source/cluster/fingerprint | 별도 사건으로 처리 |
| 잘못된 입력·허용 나이/미래 시각 범위 밖 입력 | 원문·거절/실행 제외 이유 보존; 실행하지 않음. 분석 목적의 적격성 판정과 구분 |

중복으로 “무시”한다는 것은 **후속 분석·새 사건 생성을 억제**한다는 뜻이다. 반복 알람을 분석 증거 revision으로 누적하지 않는다. 접수 receipt·최소 처리 결과·배치 원문은 전달 확인/감사 기록으로 보존할 수 있으나 반복 알람을 별도 업무 사건으로 세지 않는다.

메모·acknowledged/closed 변경, Agent 분석 완료/실패, 운영자 조치 기록, 설정 변경, 재시작은 같은 키의 중복 억제를 해제하지 않는다. 시간만 지나면 재전달하는 TTL은 두지 않는다. 해제 후 재발은 새 startsAt으로 구분하고, 끝난 생명주기도 허용 재전송 기간 동안 키를 보존해 늦은 firing을 막는다. resolved는 장비/업무 회복의 증명이 아니다.

alerts 배열은 자식별로 판정한다. 식별 불가 자식은 위치·원문·이유를 보존하고 정상 자식은 처리한다. 정확한 배치 재전송은 같은 receipt를 반환한다. 부분 재전송·배치 순서 변경에도 자식 중복 키를 사용한다.

## 3. 영속 전달과 입력

동시 수신·여러 복제본·재시작에도 DB 유일 제약과 트랜잭션으로 최초 접수 승자를 하나로 정한다. 메모리 캐시만으로 중복을 판정하지 않는다. 사건·최초 불변 snapshot·enqueue_outbox를 한 트랜잭션에 저장하고 커밋 실패 시 성공 응답하지 않는다.

신규 계약의 `source_key=incident:<incident_id>:first`는 사건당 하나다. 최초 snapshot의 `evidence_version=1`을 유지하고 반복 알람·정책 변경으로 증가시키지 않는다. 전달 루프는 `/internal/v1/jobs/rca`를 같은 키·같은 hash로 호출한다. 응답 유실은 JC receipt로 확인한다. 전달 재시도는 새 업무 요청이 아니며 Worker가 없으면 queued로 남는다.

RCA 입력은 `incident_id`, `evidence_version`, `scope`, `target` 또는 확인된 사건 범위, `incident_time`, 절대 `time_range`와 불변 원본 snapshot 연결이다. labels·annotations·status·startsAt 등은 원문으로 보존한다. 원본에 없는 GPU UUID/Pod 신원을 생성하지 않는다. 조회 시간창은 수신 운영 설정으로 정하고 최초 접수에 고정한다.

**신규 입력에는 Incident가 정한 `purpose_ids`와 `analysis_profile_revision`을 넣지 않는다.** 실행 한도·Agent 설정은 기존 envelope의 `execution_profile_revision` 및 claim versions로 고정한다. Agent가 파싱·목적·workflow 선택을 실행 근거에 기록한다. 기존 1.3 snapshot/hash/source_key는 변환하지 않는다.

## 4. 상태와 역할 경계

사건 상태 `open|acknowledged|resolved|closed`, 알람 firing/resolved, RCA job.status는 별개다. resolved 수신은 알람 상태만 바꾸며 사건 종결·장비 복구·업무 회복을 판단하지 않는다. 조치는 사람이 수행하며 Incident가 조치 완료 여부로 중복을 해제하지 않는다.

자동 기술 재시도는 JC가 같은 job의 새 attempt로 처리한다. 동일 생명주기에서 증거 추가·목적 변경·조치 후 확인을 위해 새 RCA를 생성하지 않는다. Agent는 최초 job의 scope·기간·예산 안에서 추가 로그/지표를 조회한다. 이후 시각의 복구·후속 조치가 범위 밖이면 미평가 사유를 남긴다. 지속 감시·자동 재분석·GUI 직접 재분석은 이번 범위에 포함하지 않는다.

## 5. 이행과 검수

기존 `analysis_policies`와 `GPUAlert → R01/R02`는 현행 1.3 실행에만 사용한다. 신규 경로는 alertname 등록 여부로 전달을 차단하지 않는다. 소스 설정과 Helm 미러 제거는 소비자 전환 후 같은 구현 변경에서 수행한다. 문서 수정만으로 배포 설정을 삭제하지 않는다.

기존 사건은 키별 snapshot/outbox/job 존재를 이행 시 확인한다. 이미 분석을 접수한 키는 다시 보내지 않고 기존 outbox는 기존 키로 완료한다. 과거 정책 미등록 사건도 자동 backfill하지 않는다. 과거 snapshot·결과·revision을 삭제하거나 덮어쓰지 않는다. DB 변경·검증·복구 순서는 03/14 및 06을 따른다.

검수는 [05](../05_테스트_검수_기준서.md)의 최초/반복/재발·동시 접수·장애 복구·계약 이행 사례를 따른다. 코드 미수정 상태에서는 새 동작을 PASS로 기록하지 않는다.

[RCA](../rca-agent/11_RCA_Agent_모듈_설계서.md) · [DB](../common/03_데이터_설계서.md) · [멱등 전달](../common/14_모듈간_호출과_공통실행_계약.md)
