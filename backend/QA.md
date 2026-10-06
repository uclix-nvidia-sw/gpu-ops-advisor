# 2026-10-06 D binding 결과 표시 — 로컬 검수

[공통 검수 기록](../agents/QA.md)과 [구현 범위](../docs/specs/common/d-binding-runtime.md)를 따른다. 새 O01 메모리 여유/용량 비율·CPU/load 표시명과 binding/추가 입력 불가 사유를 추가했다. null은 0으로 바꾸지 않는다. Frontend 146건·포맷·빌드, Backend vet/race/build와 HTML/CSV 회귀, 두 Worker/서비스의 격리 DB E2E를 통과했다. Grafana/LLM/화면 데이터는 fixture이며 운영 적용·브라우저 실환경·원격 CI는 미검증이다.

---

# 2026-10-06 종합·다중 선택 보고서 — 로컬 검수

[통합 검수 기록](../agents/QA.md)을 따른다. 소주제별 기준 map, 한 job의 종합·다중 선택, 조건 없는 O10 안내와 전용 조회 생략, 새 결과 내보내기 기준 표시, 기존 요청/일정/결과 보존을 검수했다. Frontend 145건·빌드/포맷, 네 Go 모듈 vet/race/build, Backend·Incident 임시 DB E2E, 두 Worker 420건 통과. 브라우저는 5191 모의 API, 실제 서비스 프로세스 E2E의 Grafana/LLM은 fixture다. 운영 배포·성능·원격 CI는 미검증이다.

---

# 2026-10-02 O08 클러스터 요약 내보내기 — 로컬 검수

- **통과:** `backend/`의 Go vet·전체 race 검사·서버 빌드. HTML의 새 지표 한글명·사유, 연결 0·산출 불가 구분, CSV의 원본 ID·값·사유 보존을 검사했다.
- **통과:** 전체 Agent 검사 **335 passed**에 포함된 실제 Backend·Ops Worker·격리 DB 경로에서 새 클러스터 metric 발행과 HTML 내보내기 이름을 확인했다. Grafana/LLM은 HTTP fixture이며 운영 서비스가 아니다.
- **해당 없음:** API/DB schema·JC·RCA 수정. **미수행/미검증:** 운영 배포·실제 데이터·커밋·푸시·PR·원격 CI.

---

# 2026-10-02 일정 실행 요약 로컬 검수

- **통과:** `backend/`에서 `go vet ./...`, `go test -race ./...`, 서버 바이너리 빌드.
- **통과:** `.local/report-usability/save-go-e2e.py`에서 새 임시 PostgreSQL·재빌드 Backend로 `go test -tags=e2e ./tests -count=1 -timeout=10m` (Backend/Incident). 일정 E2E는 첫 회차 없음, 예정 경과·기록 부재, 회차 생성 후 경고 해제, 접수와 실행 상태 분리, retry_wait/timeout/격리·시작/종료, 늦게 삽입된 과거 회차와 최신 예정 회차 구분, 토큰 미노출·미공개 결과 null, 일시 정지를 확인했다. 일정 전달의 JC는 기존 영속 접수 fixture이며 실제 운영 Worker가 아니다. 테스트 DB는 종료했다.
- **미수행/미검증:** 운영 DB·배포·운영 부하·실제 자동보고서 복구·원격 CI. **해당 없음:** 이번 조회 변경의 DB migration·스케줄러/JC 정책·Agent 분석 수정. 기존 heartbeat 로컬 수정은 유지했다. 커밋·푸시·PR 없음.

---

# 2026-10-01 보고서 생성 방식 읽기 API

- **통과:** Backend `go vet ./...`, `go test -race ./...`, 서버 바이너리 빌드. manual/schedule/누락/잘못된 접두어/다른 source_module/RCA DTO 및 원본 키 미노출을 검사했다.
- **통과:** `.local/report-usability/go_e2e.py`의 새 임시 PostgreSQL·loopback Backend로 전체 `go test -tags=e2e ./tests -count=1 -timeout=10m`. 직접 접수 응답과 정기 생성 작업의 상세·목록 origin을 확인했다. 테스트 DB는 종료했다.
- **해당 없음:** DB migration·Agent·JC 변경. **미수행:** 커밋·푸시·원격 CI·배포·운영 데이터 검증.

---

# 2026-10-01 보고서 24시간 단위 접수 로컬 검수

- **통과:** `backend/`에서 `go vet ./...`, `go test -race ./...`, 서버 바이너리 빌드. 보고서 기간의 1·23·25시간 거부, 24시간·7일·31일 허용, 기존 최대 기간 보존을 검사했다.
- **통과:** `.local/report-usability/go_e2e.py`에서 새 임시 PostgreSQL data directory와 loopback 포트, 새 Backend 바이너리로 `go test -tags=e2e ./tests -count=1 -timeout=10m` 전체 실행. 새 `report_full_day_input_and_comparison`은 본문·비교 기간의 시간 단위 입력 422와 하루/7일 접수 202를 확인한다. 기존 정기 일정·JC 연계도 통과했으며 DB는 종료했다.
- **변경 범위:** 보고서 신규 접수와 비교 기간에 최소 24시간·24시간 배수 검증을 추가했다. 정기 일정 템플릿 검증의 임시 기간을 24시간으로 맞췄다. 기존 일정의 달력/DST 계산, RCA 접수, 조회 한도·Worker·DB 스키마는 변경하지 않았다.
- **미수행/미검증:** 운영 배포·운영 DB·실제 Grafana/LLM·원격 CI. Frontend 브라우저는 별도의 모의 API 검증이다. 로컬 파일 수정 단계다.

---

# 2026-10-01 저장 기록 웹 추적 API

- **통과:** Backend `go vet ./...`, `go test -race ./...`, `go build ./...`. 진단 응답의 중첩 헤더·비밀·claim token·object_key 제거와 조회 인자 보존을 검사했다.
- **통과:** 새 localhost PostgreSQL data directory의 격리 schema에서 `go test -tags=e2e ./tests -v -count=1 -timeout=5m`. 기존 Backend/실제 JC/부트스트랩과 새 `TestStoredWebTrace`를 검사했다. 고정 사건 revision(현재 99/작업 2), outbox/알람 연결, 미공개 후보 본문 제외, 공개 후보 메타데이터, 과거 시도 근거·페이지 이동, 다른 작업/시도 404, 잘못된 cursor/인자 422, 비밀 제거와 원본 시간 정밀도, 즉시 요청과 정기 회차 revision, 빈 목록을 포함한다.
- **통과:** 문서 링크·diff 검사. Windows Go embed의 대괄호 경로와 PostgreSQL의 한글 경로 제약 때문에 소스 복사본/별도 ASCII data directory를 사용했다. 테스트 DB는 종료했다.
- **미수행/미검증:** 운영 DB·배포·실제 Grafana/LLM·Worker 재실행. Frontend 브라우저는 별도의 모의 API 검증이다. DB migration/Worker/API 기존 응답 계약 변경 없음; 읽기 경로를 추가했다.

---

# 2026-09-30 보고서 단위·한계 출력

## Ops 최종 보고서 HTML — 2026-09-30

main `40b68d3` 기반. 임시 소스 복사본의 Backend `go vet ./...`, `go test -race ./...`, `go build ./...` 및 새 격리 PostgreSQL의 `go test -tags=e2e ./tests -v -count=1 -timeout=5m` **통과**. 최종 narrative 제목/본문·fallback 상태의 HTML escape와 CSV 원래 수치 보존을 검사했다. 실제 Backend→JC→Ops→공개 HTML 검사는 [Agent QA](../agents/QA.md)에 기록했다. 운영 배포/실제 모델 품질은 **미검증**, DB migration/API 변경은 **해당 없음**.

- **통과:** Backend 디렉터리 기준 `go vet ./...`, `go test -race ./...`, `go build -o ../.local/backend-e2e ./cmd/server`. HTML 연결 GPU 고유 대수 이름·GPU·시간 설명·한계 우선 표시, HTML escape와 CSV 원시 단위·정밀도 보존을 검사했다.
- **통과:** `.local/report-usability/go_e2e.py`가 새 임시 PostgreSQL·loopback 포트·최신 Backend 바이너리로 `go test -tags=e2e ./tests -count=1 -timeout=10m` 실행 후 DB를 종료했다. 기존 운영 DB는 사용하지 않았다. Backend→JC→Ops namespace 공개·다운로드는 [Agent QA](../agents/QA.md)의 전체 검사에 포함됐다.
- **해당 없음:** API 접수·JC 계약·DB migration 변경. **미수행:** 운영 배포와 운영 다운로드 검수.

---

# Backend v1.3 검증 기록

## 2026-09-30 Namespace 보고서 실행·내보내기

**통과:** Backend Go vet/race/build, 격리 PostgreSQL의 전체 `-tags=e2e` 검사, 실제 Backend→JC→Ops 공개/HTML 다운로드. 즉시·정기 보고서 프로필 선택과 CSV 원래 수치/단위 유지·HTML 단위 변환을 확인했다. **미검증:** 운영 배포·실제 Grafana/LLM. 환경·명령·fixture 경계는 [Agent QA](../agents/QA.md)의 같은 날짜 실행·표시 개선 기록을 따른다.

## 2026-09-28 전체 Runbook 콘텐츠·일괄 등록

- **통과:** Backend에서 `go vet ./...`, `go test -race ./...`, `go build ./...`. 분리한 xid/sxid 폴더와 일반 Runbook을 합친 267건의 v1 구조·빈 호환성 발행 거부·잘못된 조건/계획/출처를 검사했다.
- **통과:** 새 격리 PostgreSQL에서 `go test -tags=e2e ./tests -v -count=1`. `TestFreshBackendWithoutDemoSeed`, `TestBackendE2E`, `TestRealJobController`와 기존 SXID 등록·검토·발행·회수 경로를 재검증했다.
- **통과:** [Agent E2E](../agents/QA.md)의 실제 일괄 등록 CLI로 신규 263건의 draft 저장·코드별 조회/hash·재실행 중복 등록 방지를 확인했다. Backend 기본 요청 한도를 유지하고 429의 Retry-After를 따랐다.
- **해당 없음:** Backend 실행 로직·DB 스키마 변경. 기존 Knowledge API를 그대로 사용하고 테스트 파일 검색 경로만 갱신했다.
- **미수행:** 운영 DB 등록·발행·배포. 실제 Grafana/Fleet/LLM 검증은 별도다.

Windows 대괄호 경로의 Go embed 문제 때문에 임시 소스 복사본에서 검사했으며 DB는 새 data directory와 localhost 포트로 시작한 뒤 종료했다. 등록 절차와 기존 ID의 새 revision 처리 방법은 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)에 기록했다.

## 2026-09-28 Runbook v1 DB 연계

- **통과:** Backend에서 `go vet ./...`, `go test -race ./...`, `go build ./...`. 실제 JSON 4건의 초안 형식·빈 호환성 발행 거부·잘못된 필드/조건/관측 계획/출처·legacy 호환을 검사했다.
- **통과:** 격리 PostgreSQL 16.9에서 `go test -tags=e2e ./tests -v -count=1`, `TestFreshBackendWithoutDemoSeed`, `TestBackendE2E`, `TestRealJobController`. 신규 Runbook 사례는 실제 SXID JSON의 등록·검토·빈 호환성 승인 거부·수정 후 재검토·발행·코드 namespace 검색·발행본 불변·회수·새 revision을 확인했다.
- **통과:** 별도 [Agent E2E](../agents/QA.md)에서 오류별 JSON 3건의 CLI/API 생명주기·멱등 재전송과 RCA 소비까지 검사했다. 기존 migration만 사용하며 DB 구조 변경은 없다.
- **미수행:** 운영 DB 적재·운영 Fleet/Grafana/LLM 검증·배포. fixture compatibility는 운영 적용 승인이 아니다.

Windows의 대괄호 포함 checkout 경로는 Go embed를 방해해 소스를 임시 경로로 복사해 빌드했다. 새 PostgreSQL data directory와 localhost 포트에서 검사하고 종료했다. 재현 설정은 [CI](../.github/workflows/tests.yml), 등록 절차는 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)를 따른다.

## 2026-09-18 운영 초기화 회귀 검사

실제 PostgreSQL의 빈 schema와 실제 Backend 실행 파일을 `DSX_MIGRATE=true`, `DSX_SEED=false`로 기동했다. 필수 C07 한도만 생성되고 예제 클러스터 없이 readiness 200이 되는 것을 확인했다. 미등록 클러스터 보고서 요청은 422로 거부하며, 이후 HTTP 등록 → 목록·범위 조회를 검증했다. 등록의 입력 검증, 멱등 재전송, 중복 충돌, 감사 기록 1건, 기존 비활성 클러스터 보존을 확인했다. 기존 C07 config/enabled/version은 재초기화해도 유지한다. 누락·비활성·유효하지 않은 한도와 미적용 스키마는 readiness 503을 유지한다.

Go 단위 테스트, vet, 서버 빌드 및 Backend E2E 전체(`TestFreshBackendWithoutDemoSeed`, `TestBackendE2E`, `TestRealJobController`) 통과. 운영 Kubernetes에 수정 이미지를 배포한 검증은 아직 수행하지 않았다.

## 2026-09-17 검증

2026-09-17 / Windows / Go 1.26.2 / native PostgreSQL 16.9 / Docker 미사용.

- Go 단위 테스트 2개: scope/시간 경계, 달력 DST gap/fold·23시간 완료일·월말·월요일 시작 주간: PASS.
- go vet 및 서버 빌드: PASS.
- 실제 HTTP + PostgreSQL E2E 1개, 아래 8개 subtest: PASS.

| 시나리오 | 확인 |
|---|---|
| v1.3 경계 | 인증 테이블 미생성·제거 API 404·등록 scope/중복/기간 422 |
| JC 접수/명령 | 커밋 후 응답 유실·동일 키/정규화 입력 복구·본문 충돌·queued·report 한정·receipt 우선·cursor |
| 최종 결과 | 후보 미노출·JC 발행 참조만 조회·Backend 재시작·HTML 이스케이프·CSV 수식 방어 |
| 지식 | 원자적 receipt·재전송·검토 hash 불일치 차단·발행본 불변 |
| 일정 복구 | 두 Backend 경합·단일 occurrence·outbox·마감 후 JC receipt로 accepted 복구·revision 보존 |
| 달력 backlog | catchup_window/max_catchup·중복 기간 missed/canonical 참조·일시 정지 후 pending 전달 |
| 모델/조치 | 불변 revision·라우팅 유지·사용 모델 비활성화 차단·secret_ref·용량 변경 거부·미인증 조치자 |
| 조회/장애 | dashboard/assets/workloads/quality/incident/procedure 조회·JC 미연결 503 |

실제 브라우저에서도 Frontend → Go → PostgreSQL 일정 생성 → 일시 정지 → 실행 시각 변경(revision 1→2→3)을 확인했습니다. 확인 중 등록 폼 시간대 누락을 수정했습니다. 검증용 일정 `16660c00-c133-4535-9804-91117afc3591`은 일시 정지 상태로 남겨 자동 실행을 막았습니다.

기존 로컬 DB에 보존 migration을 적용하고 새 Backend로 readiness 성공을 확인했습니다. frontend Vitest 3개·TypeScript/Vite build도 통과했습니다.

한계: JC/Incident/두 Agent는 실제 서비스가 연결되지 않았습니다. E2E의 JC는 PostgreSQL 커밋을 수행하는 계약 fixture이며 제품 JC 구현이나 실제 RCA/보고서 계산·LLM 실행 검수가 아닙니다. 실시간 관측, 운영 부하·배포·백업복원·원격 LLM 장애 시험은 NOT RUN입니다.
