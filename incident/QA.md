# Incident 검증 기록

## 2026-09-30 Fleet target 투영

**통과:** Go 1.26.2에서 `go vet ./...`, `go test -race ./...`, `go build ./...`. 최신 로컬 소스의 격리 임시 복사본으로 실행했다. 별도 로컬 PostgreSQL에서 `go test -tags=e2e ./tests -v -count=1 -timeout=5m` 전체 통과: 투영만 추가된 반복 알림에서 기존 incident/outbox/snapshot/hash 유지, 새 incident에 machine/component/node 투영, 기존 episode·migration 충돌 회귀 포함. Agent 실제 프로세스 E2E의 webhook→outbox→JC→RCA 공개도 통과했다. 상위 Grafana·LLM은 fixture이며 운영 배포는 미수행이다. DB migration 변경 없음.

## 2026-09-28 node 라벨 전달 보완

1.4 `k8s_node_name`을 labels에서 우선 읽고 annotations를 fallback으로 사용한다. 서로 다른 두 값은 `conflicting_node_name`으로 거부한다. DB 구조나 에피소드 정책 설정은 변경하지 않았다.

- **통과:** 라벨만/annotation만/같은 값/충돌 값의 단위 검사, 원문 hash 불변 확인. Incident `go vet ./...`, `go test -race ./...`, `go build ./...`.
- **통과:** `go test -tags=e2e ./tests -v -count=1 -timeout=5m`의 3개 최상위 테스트 및 하위 사례. 실제 PostgreSQL에서 node label이 incidents.target과 JC outbox input에 함께 저장됨을 추가 검증했다. 기존 에피소드·snapshot·중복 억제·migration 충돌 검사를 유지한다.
- **환경:** Windows, Go 1.26.2, CGO/GCC, 격리 PostgreSQL 16.9. 저장소 경로의 대괄호에 따른 Go embed 오류를 피하려고 동일 소스의 임시 검증 복사본에서 실행했다. 실제 Backend 바이너리와 JC를 사용하고 테스트별 schema 및 DB를 종료했다. 로그는 로컬 `.local/rca-incident-e2e.log`.
- **미검증:** 제품 RCA Worker의 입력 1.4 의미 처리·목적 선택, 실제 Grafana 발송·운영 parser·배포. 1.4 전달 수신기는 기존 계약 fixture이며, 제품 Worker의 1.3 실행은 [Agent QA](../agents/QA.md)에 별도로 기록했다.

## 2026-09-23 Incident·JC 통합 PR 최종 검사

Incident·JC 변경을 함께 포함한 별도 PR 작업 트리 `C:/Temp/gpu-ops-incident-jc-pr`에서 재검사했다. 아래 결과는 앞선 기록의 CGo/race 미검증 항목을 보완한다.

- **통과:** `shared`, `incident`, `job-controller`, `backend` 각각 `go vet ./...`, `go test -race ./...`, `go build ./...`. Go 1.26.2, `CGO_ENABLED=1`, 임시 폴더의 SHA256 검증된 w64devkit GCC를 사용했다.
- **통과:** Incident와 Backend 각각 `go test -tags=e2e ./tests -v -count=1 -timeout=5m`. 새 PostgreSQL 16.9의 `127.0.0.1:51009/incident_test`와 테스트별 임시 schema만 사용하고 종료했다. 이 작업 트리에는 검증 복사본 전용 `TestReviewIncident14`가 없으며 저장소에 포함된 검사만 실행했다.
- **통과:** 문서 링크 검사와 변경 diff 공백 검사.
- **미검증:** 실제 Grafana 발송·운영 시각 계약, 제품 RCA Worker의 1.4 실행·목적 선택·결과 의미 검증, 운영 배포. 에피소드 1.4 전달 검사는 계약 수신 fixture, JC 배분·공개 검사는 실제 JC와 Worker 프로토콜 드라이버를 사용한다.

## 2026-09-23 종결 후 resolved 반영 수정

종결한 에피소드를 알람 집계 갱신에서 제외하던 조건을 제거했다. `closed_by_operator`와 `observation_gap` 각각에 대해 일부 생명주기만 해제되면 firing 유지, 모두 해제되면 resolved 반영, 기존 state/closed_at/ended_at/ended_reason/관측 횟수·시각/snapshot/outbox 보존, 이후 늦은 firing의 재활성화 방지를 확인했다.

- **통과:** 검증 복사본의 Incident에서 `go vet ./...`, `go test ./...`, `go build ./...`.
- **통과:** 새 격리 PostgreSQL 16.9에서 `go test -tags=e2e ./tests -v -run='TestReviewIncident14|TestIncidentEpisodes' -count=1 -timeout=5m`. 저장소의 에피소드 회귀 검사와 검증 복사본에만 둔 직전 실패 재현 검사 모두 성공했다. 실제 Incident → 실제 JC의 1.4 접수도 다시 확인했다. 검사 후 DB를 종료했다.
- 실제 Agent 실행·운영 Grafana·`-race`는 이번 수정에서 미검증이다. DB 구조·설정 변경은 없다.

## 2026-09-23 에피소드 생산자 업그레이드

로컬 파일 구현·검증 단계다. 커밋/push/배포 및 운영 Grafana 검수는 수행하지 않았다. Windows / Go 1.26.2 / 새 PostgreSQL 16.9 프로세스의 임시 DB·schema를 사용하고 종료했다. 사용자 경로의 한글과 저장소 경로의 대괄호가 PostgreSQL 초기화/Go embed를 방해해 `C:/Temp/gpu-ops-incident-01a0cbd5`의 검증용 소스 복사본에서 실행했다. 운영 DB 환경변수는 재사용하지 않았다.

| 항목 | 결과와 범위 |
| --- | --- |
| `shared`, `incident`, `job-controller`, `backend` 각각 `go vet ./...`, `go test ./...`, `go build ./...` | 통과. Incident 경계 판정 단위 검사 포함 |
| `incident`: `go test -tags=e2e ./tests -v -count=1 -timeout=5m` | 통과. 기존 실제 JC/Backend 연동과 신규 에피소드·이행 충돌 검사 |
| `backend`: 같은 E2E 명령 | 통과. 기존 Backend/실제 JC 회귀 검사 |
| DB 새 스키마·기존 1.3 행에서 전환·반복 Prepare | 통과. snapshot/hash 보존, 기존 pending의 실제 JC 전달, 다중 사건 귀속 거절, 신규 에피소드 이후 1.3 생산자 재시작 차단 |
| `go test -race ./...` | 실행 시도 차단·미검증: `-race requires cgo`; 이 환경에는 C 컴파일러가 없음. CI/Linux에서 확인 필요 |
| 문서 링크 검사 | 저장소 루트의 `python tools/check_links.py` 통과 |
| 설정/Helm 기본 전환 | 해당 없음: 기존 1.3 기본값·설정 미러를 유지함 |
| 실제 1.4 JC/Worker 전체 실행·결과 공개, 운영 Grafana·K·시각 계약, DB 백업 복원 | 미검증. 통합 배포 전 별도 검수 필요 |

추가한 검사는 `service/episodes_test.go`의 결정 경계 검사와 `tests/episodes_test.go`의 DB/HTTP 시나리오에 집중했다. [05 검수 기준](../docs/specs/05_테스트_검수_기준서.md)의 아래 **해당 입력 사례**를 확인했으며 전체 T 항목이나 운영 적합성의 통과를 뜻하지 않는다.

- T41/T42/T49/T52: 같은 bytes 4회 → 관측 count=4, 원문·최초 snapshot 중복 없음. 두 Incident 인스턴스의 동시 최초 8회 → 사건/outbox 각 1개·count=8. reason storm·부분/순서 변경·annotation 변경도 최초 snapshot/revision 유지. 순수 함수에서 gap=K 유지, gap=K+1 종료 확인.
- T43/T53: 일부 resolved는 그룹 firing 유지, 전체 resolved도 검토 state=open 유지. late firing은 카운트 증가 없음. resolved 선접수는 사건 없음. 수집 장애는 excluded 사건·outbox 없음. 신원 누락은 생명주기별 분리, 신원 변경은 identity_conflict, NUL 자식과 정상 형제 격리, 잘못된 truncatedAlerts는 422 receipt.
- T50/T51/T54: gap 후 새 startsAt은 새 사건/prior 연결·prior_analysis_open. closed 후 과거 원문·문구 변경은 재발 보류. 동일 미해제 생명주기의 새 검수된 occurred_at은 새 사건/outbox. 늦은 closed는 기존 관측 종료 시각·사유 보존.
- T45/T59: 이름 정책 없는 입력·목적 필드 없는 1.4 envelope, 원문과 절대 창 고정. 발생 시각 계약 미검수 시 startsAt, 검수 후 occurred_at 선택·미래 오류 거절. Agent의 실제 목적/Runbook 선택은 미검증.
- T42/T48: 1.4 전달의 응답 유실은 계약 검사용 HTTP 수신기의 receipt로 같은 키를 복구한다. 이 수신기는 실제 JC/Worker가 아니다. 실제 JC 검사는 기존 1.3 pending 전달·회귀 경로이며, 신규 Worker 배분(T55) 검증으로 승계하지 않는다.

에피소드 설정 revision 재사용 시 내용 변경도 시작 단계에서 거절한다. 작업 중 별도로 들어온 JC/Worker 계약 변경은 보존했으며 이 기록을 그 개발의 완료 판정으로 사용하지 않는다. 1.4 운영 활성화 조건은 [README](README.md)의 적용 순서에 있다.

## 2026-09-17 기존 1.3 검증

검증일: 2026-09-17. Go 1.26.2 / Windows / PostgreSQL 16 개발 인스턴스. 사용자·Agent 인증 제외.

- Incident `go test ./...`, `go vet ./...`, 서버 바이너리 빌드 통과.
- 실제 PostgreSQL + 실제 JC HTTP + 별도 포트의 실제 Backend 바이너리 E2E 5개 시나리오 통과.
- Backend 기존 단위 테스트·vet·전체 E2E 회귀 검사 통과.
- 개발 Incident 서버 `127.0.0.1:8091` 실행, `/internal/v1/health/ready` 200 및 pending_outbox=0 확인.
- 이 작업에서 추가·수정한 소스/설정/문서의 CRLF 확인.

## E2E 범위

1. 혼합 배치에서 유효/잘못된 자식 각각 보존, 동일 배치 receipt 복구, 12개 동시 재전송 중복 방지.
2. JC가 RCA를 커밋한 뒤 응답을 잃어도 전달 마감 이후 receipt로 같은 job 복구. Worker가 없을 때 queued/worker_unavailable. 테스트 Worker가 실제 claim으로 완전한 RCA input과 snapshot을 수신하며 누락된 GPU UUID를 생성하지 않음.
3. 수치 heartbeat는 새 RCA를 만들지 않고 등록된 error_code 변경은 새 증거 revision·job 생성. snapshot DB 수정 차단. resolved와 늦은 firing은 회복/재분석으로 오인하지 않음.
4. 실제 Backend에서 사건·RCA 연결 조회, Incident로 PATCH 전달, 동일 명령/이전 If-Match 재전송, 변경된 명령 409. acknowledged/closed 처리와 메모 변경은 분석 실행을 만들지 않음.
5. JC 장애 중 webhook 영속 접수, receipt 조회 불가 시 pending 유지, 미접수 마감 건의 failed 처리. 미등록 정책·오래된 알람·잘못된 시각·NUL 포함 자식 보존, 정상 형제 알람 처리, 본문 한도 413.

테스트는 임시 schema와 임시 Backend 프로세스를 사용하고 종료 시 해당 자원만 정리합니다. 기존 개발 Backend/JC 프로세스는 재시작하지 않았습니다. 현재 실행 중인 Backend는 Incident URL이 아직 적용되지 않아 service-status에서 Incident 미연결로 표시됩니다. 갱신된 `backend/scripts/dev-server.ps1`로 다음 기동 시 8091을 연결합니다.

실제 Grafana Contact point 설정, Grafana 서버 발송, 운영망 연결, 실제 RCA Agent/LLM 추론은 검증 범위 밖입니다. 공식 기본 Webhook JSON을 HTTP로 전송해 검증했습니다. Docker가 없어 컨테이너 이미지 빌드와 compose 실행은 확인하지 않았습니다.
