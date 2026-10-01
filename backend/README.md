# Go Backend v1.3

## 보고서 일 단위 접수 — 2026-10-01

새 수동 보고서·비교 기간은 최소 24시간, 24시간의 정수 배수로 검증한다. 최대 기간은 기존 C07 한도를 유지한다. 일정 템플릿 검증용 임시 기간도 24시간으로 맞췄다. 정기 일정의 현지 달력·DST 계산, 기존 job/result, RCA/Agent/DB schema는 변경하지 않는다. GUI는 KST 날짜만 선택하며 연간은 지원하지 않는다.

## Ops 최종 보고서 내보내기 — 2026-09-30

기존 HTML 다운로드는 공개 결과의 `narrative` 제목·본문과 모델 편집/기본 보고서 상태를 함께 렌더링한다. HTML escape/CSP, Namespace 해석 제한, CSV 원시 값·단위를 유지한다. narrative 없는 과거 결과에는 새 설명을 만들어 넣지 않는다. DB/API 계약 변경 없음.

Backend가 GUI 조회·입력 검증·지식/모델/설정·정기 보고서 발생과 outbox를 소유합니다. 보고서 실행 접수와 명령은 Job Controller에 위임하고 RCA는 Incident가 생성합니다. 사용자·Agent 인증은 제외했습니다.

## Docker 없이 실행

서로 다른 터미널에서 저장소 루트 기준으로 실행합니다.

```powershell
./backend/scripts/dev-db.ps1
./job-controller/scripts/dev-server.ps1
./backend/scripts/dev-server.ps1
```

Go 1.26, PostgreSQL 16을 사용합니다. dev-db는 공식 Maven 배포의 embedded-postgres 16.9를 내려받아 `.local/postgres`에서 실행하며 이후 재사용합니다. 개발 DB는 127.0.0.1:55432, Backend는 127.0.0.1:8080, JC는 127.0.0.1:8090입니다. Frontend는 별도 `npm run dev`로 실행합니다. Docker/compose는 선택입니다.

`.env.example`은 설정 예시이며 서버가 자동으로 읽지 않습니다. PowerShell 환경 변수로 설정하거나 배포 환경에 주입합니다. 개발 스크립트는 migration/seed/내부 스케줄러를 켭니다. 운영에서는 `DSX_SEED=false`여도 필수 `C07` 운영 한도를 자동 생성하며, 기존 설정은 덮어쓰지 않습니다. 클러스터 0건은 정상 초기 상태로 취급합니다. 실제 분석에는 등록된 클러스터가 필요합니다.

- `DSX_JOB_CONTROLLER_URL`: JC base URL. `/internal/v1/jobs/report`, receipts, report 명령, queue-status 호출.
- `DSX_INCIDENT_URL`: Incident base URL. 메타데이터 PATCH만 위임.
- `DSX_SCHEDULER_ENABLED=true`: 독립 발생/전달 루프. 복제 간 schedule/outbox 행 잠금과 유일 키 적용.
- catch-up/마감/프로필: `DSX_CATCHUP_WINDOW`, `DSX_MAX_CATCHUP`, `DSX_DISPATCH_WINDOW`, `DSX_JOB_DEADLINE`, `DSX_EXECUTION_PROFILE_REVISION`.
- 기본 개발 예시: 7일 catch-up, 최대 10건, 전달 마감 24h, 잡 마감 48h. 운영 확정값이 아니므로 배포별 지정 필요.
- 모델: `DSX_MODEL_HOSTS` 정확한 host:port; 사설 DNS는 `DSX_MODEL_CIDRS`도 설정. redirect 차단, DNS 검증/고정. 비밀 원문 대신 secret_ref만 저장.

미연결 JC/Incident는 503으로 표시하며 테스트용 가짜 서비스를 개발 서버에 연결하지 않습니다. Agent가 없어도 JC가 영속 접수했다면 202 queued입니다.

## v1.2에서 변경

1. 직접 RCA/Report/Chatbot/Scheduler 실행 중계를 제거하고 JC report 계약 1.3 적용.
2. `/me`, 권한 DTO/편집, 대화, Grafana 중계, GUI 용량 설정 제거.
3. Backend 내부 정기 일정·불변 revision·occurrence/outbox·재전송/receipt 복구 추가.
4. published_result_id로 지정된 결과만 조회/안전한 HTML·CSV 내보내기.
5. 전체 변경 API 멱등 receipt, 지식 검토 해시 확인, 모델 불변 revision, 미인증 조치자 표시.
6. 프론트엔드 등록 CPC 필터·일정 DTO·rca/report 라우팅 연결 수정.

## 데이터 마이그레이션

새 DB는 인증/대화 테이블을 만들지 않습니다. 기존 DB는 추가 migration으로 보존하며 legacy access_grants/conversations/module_dispatches를 삭제하지 않습니다. 과거 외부 Scheduler 일정은 `legacy_schedules_v12`에 보존하고 자동 실행으로 이관하지 않습니다. 새 정책을 확인해 v1.3 일정으로 등록해야 합니다.

기존 jobs 입력을 input_snapshot으로 복사하지만 과거 job_results를 자동 발행하지 않습니다. 최종 결과는 JC의 published_result_id 확정이 필요합니다. 기존 reviewed 지식에 검토 hash가 없으면 다시 검토해야 발행됩니다. 실행 중 구버전 생산자/Agent를 먼저 중단하고 모듈 계약을 함께 갱신해야 합니다.

## 검사

```powershell
./backend/scripts/format.ps1
./backend/scripts/test.ps1 -E2E
cd backend
go build -o bin/dsx-backend.exe ./cmd/server
```

테스트는 실제 PostgreSQL의 고유 e2e schema에서 실행하고 해당 schema만 정리합니다. 기존 Backend 계약 검사는 HTTP fixture, `TestRealJobController`는 실제 JC와 Backend를 HTTP로 연결해 검사합니다. Agent만 테스트 프로토콜 드라이버이며 LLM은 호출하지 않습니다. Go 포맷 후 CRLF를 복구합니다.

[API](API.md) · [검증 기록](QA.md)

## 개발자 웹 추적

작업별 읽기 API로 사건 고정 증거 → 전달 기록 → 작업 입력, 시도별 근거와 저장 조회 인자를 제공한다. 기록 조회는 [웹 추적 API](API.md#저장-기록-웹-추적--2026-10-01)를 따른다. 새 DB migration이나 Worker 실행 변경은 없으며 실제 실행 시각과 미기록 오류 원인을 만들어내지 않는다.
