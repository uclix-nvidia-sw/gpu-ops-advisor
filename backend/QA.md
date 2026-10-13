# 2026-10-13 Aggregate report intake / 집계 보고서 접수

Base: latest origin/main `74c93f9`. PASS: all four Go modules vet/race/build, Backend and Incident DB E2E on a fresh temporary loopback PostgreSQL, then stopped. Actual Backend→JC→Ops process tests cover new report submission/publication/read, daily/weekly schedule acceptance and monthly rejection. Additional Ops snapshot test proves start-inclusive/end-exclusive periods and Namespace isolation. Existing RCA/legacy report regression passed. No production DB or schema changes. [Full verification](../agents/QA.md) · [Contract](../docs/specs/ops-agent/aggregate-report-v1.md).

# 2026-10-12 종료된 보고서 삭제와 참조 경합

- **통과:** 새 임시 PostgreSQL 16.9에서 실제 Backend·JC를 연결해 `backend/`의 `go test -tags=e2e ./... -v -count=1 -timeout=10m`. 기존 전체 E2E와 상세 projection, `TestReportDeletion`을 함께 통과했다. 작업 종료 네 상태의 자체 결과·근거 정리, report 목록 제외·job 이력 유지, 발행 hash·입력·시도·receipt·감사 보존, RCA 보존, 활성/격리/미종료 시도 거부, 외부 정식 참조 거부와 rollback을 확인했다.
- **통과:** 실제 HTTP와 DB 잠금 대기로 두 순서를 재현했다. 지식 근거 참조 작성이 먼저면 201·삭제 409, 삭제가 먼저면 200·참조 작성 404다. Backend는 지식 생성/PATCH/검토/발행 및 검토 기록 INSERT와 같은 트랜잭션에서 근거 scope만 `FOR KEY SHARE`로 읽는다. 범위 검증을 유지하며 큰 snapshot을 해석하지 않는다. 사용 중인 근거는 2초 lock timeout 뒤 `report_busy`로 전체 rollback했다.
- **통과:** 기존 스키마에서 migration 008 업그레이드와 두 서비스 초기화 반복, 새 Backend의 삭제 테이블 누락 readiness 503. 마지막에 추가한 빈 보고서·사유·버전 경계 및 구 JC 정책 fence는 새 임시 DB에서 `go test -tags=e2e ./tests -run TestReportDeletion -v -count=1`로 별도 통과했다. 초기화 전/후 데이터 보존과 공개 candidate 불변 trigger 유지를 확인했다.
- **통과:** Backend vet/race/build와 문서 링크/diff 검사. 전체 실행 기록은 로컬 `.local/report-projection/backend-e2e.log`, 마지막 삭제 회귀는 `deletion-regression-final.log`다. 테스트 DB는 종료·제거했다.
- **검증 경계:** 위 Backend 검사는 DB 삭제·조회 계약을 검증한다. Ops 파일 정리·늦은 파일 저장 차단 검증은 [Agent QA](../agents/QA.md)를 따른다. 이력과 작은 삭제 기록은 남는다. PostgreSQL 행 삭제가 DB 파일 크기를 즉시 줄이지는 않으며 VACUUM FULL을 자동 실행하지 않는다. 운영 DB 삭제·배포·Kubernetes OOM 재발 여부는 **미수행/미검증**이다.

---

# 2026-10-12 큰 기본 보고서 상세 조회

- 기준: `origin/main`의 `029fbed`, 로컬 `fix/minimal-report-evidence`. 계산 기준 1.3 보고서 O01의 중복 `quality.node_condition_observations`만 SQL에서 제외하며 DB 원본과 hash는 보존한다. 계산 기준 1.2/미기록, RCA, 다른 주제는 유지한다.
- **통과:** Go 1.26.2의 Backend vet/race/build, 새 loopback PostgreSQL 16.9의 `TestPublishedReportProjection`와 기존 전체 `./tests` E2E. 중복 필드 외 모든 필드 동등성, 0/null·metrics·facts·참조·주제 순서, 원본 evidence 개별 조회, 저장 body/hash·불변 trigger, 공개 후보 연결과 미발행 후보 차단, malformed/missing 주제, 상세·추적·지표 및 metric-free HTML/CSV fallback을 확인했다. HTML/다운로드 헤더의 조회용 본문 안내와 원본 hash도 검사했다.
- 동일 fixture로 SQL 결과를 수신하고 `store.One`으로 JSON을 해석하는 실제 DB benchmark를 추가했다. 운영 데이터와 DSN은 사용하지 않았다. 로컬 임시 DB는 검사 후 종료·제거했다.

## 중복 구간 881,280개의 전후 측정

macOS arm64 / Apple M2 / PostgreSQL 16.9 / Go 1.26.2. 합성 153개 series 각각 5,760개의 15초 구간, 총 881,280개를 저장했다. 동일 candidate·DB·connection pool에서 기존 `SELECT to_jsonb(c)`와 새 projection SQL을 각 1회 수신/해석 준비 후 비교했다. 전→후와 후→전 순서를 각각 2회 실행하고, 표의 범위는 각 실행에서 3회 측정한 **평균값 4개**의 최소~최대다. p95나 HTTP·브라우저 전체 시간은 아니다.

| 항목 | 기존 전체 본문 읽기 | SQL projection |
|---|---:|---:|
| DB→Go 반환 JSON | 30,867,261 bytes | 638 bytes |
| SQL+전송+JSON 해석 | 607.7–764.4 ms/op | 108.9–120.9 ms/op |
| Go 누적 할당량 | 286,799,613–286,803,090 B/op | 6,208 B/op |
| Go 할당 횟수 | 8,378,448–8,378,450 /op | 122 /op |

638 bytes는 나머지 지표·facts·narrative·참조에 작은 sentinel 값을 둔 합성 본문이다. 구간의 개수와 배열 구조를 재현했으며 운영 보고서 전체 필드 분포·나머지 약 1MiB 본문을 복제하지 않았다. 따라서 운영의 응답 크기·전체 지연·절대 heap/RSS를 이 숫자로 예측하지 않는다. 할당량은 요청 중 누적 allocation이며 상주 메모리나 peak가 아니다. 측정 전 projection 결과와 원본에서 정확히 해당 필드만 제거한 결과를 비교하고 interval 개수도 실제 SQL로 확인했다.

격리 test DB에만 `E2E_DATABASE_URL`을 설정하고 `backend/`에서 재현한다:

```sh
go test -tags=e2e ./internal/api -run TestPublishedReportProjection -v -count=1
go test -tags=e2e ./internal/api -run '^$' -bench BenchmarkPublishedReportProjection -benchtime=3x -count=2 -timeout=10m
```

실행 보조와 로그는 로컬 `.local/report-projection/verify.py`, `projection-test.log`, `benchmark.log`, `backend-e2e.log`에 있다. 위 두 Go 검사와 합성 생성기는 저장소에 포함된다. **미검증:** 운영 배포·동시 부하·실제 요청 지연·Kubernetes OOM 재발. PostgreSQL 내부의 큰 JSON 읽기/압축 해제와 원본 evidence 크기는 남는다.

---

# 2026-10-12 작업·보고서 목록 조회 경량화

- 기준: 최신 원격 main `49193b0`; 로컬 브랜치 `fix/lightweight-job-lists`. Backend 목록 읽기 구현·회귀 검사·문서만 변경했다. API 응답/DB schema/Frontend/Agent/JC 실행 정책은 동일하다.
- **통과:** `backend/`에서 Go 1.26.2 `go vet ./...`, `go test -race ./...`, `go build ./...`. 로컬 테스트 HTTP 포트가 sandbox에서 차단된 최초 실행은 허용된 로컬 테스트 환경에서 다시 실행해 통과했다.
- **통과:** 새 loopback PostgreSQL 16.9의 격리 schema에서 `E2E_DATABASE_URL`과 재빌드한 `E2E_BACKEND_BINARY`를 명시하고 `go test -tags=e2e ./tests -v -count=1 -timeout=10m`. 기존 Backend/실제 JC/초기화/추적과 새 `TestJobListProjection` 전체 통과. Backend만 초기화한 DB와 JC 적용 DB, 세 목록·상세 DTO 동등성, 출처/재시도/취소 경계, 범위·필터·동률 cursor, 미공개/잘못된 참조/누락 필드, 큰 본문과 안전한 상세·HTML/CSV를 확인했다. 신규 fixture의 UUID/text 매개변수 오류를 수정한 후 최종 전체 재실행했다.
- **통과:** `frontend/`에서 `npm run format:check`, `npm test`(196 tests/17 files), `npm run build`. UI 검사는 기존 합성 응답 기반이며 실제 운영 브라우저 검사는 아니다. 기존 큰 JavaScript 청크 경고는 남아 있다.

## 로컬 전후 성능 측정

실제 Backend HTTP 프로세스와 PostgreSQL 16.9를 사용했다. 운영 데이터·DB는 사용하지 않았다. 동일 DB에 완료 report 31건, 완료 RCA 31건, 실패 report 31건을 넣었다. 각 완료 결과는 약 4 MiB의 압축 효과가 작은 결정적 합성 문자열을 포함하며, 각 작업 입력과 버전 스냅샷에도 각각 256 KiB를 넣었다. 운영 보고서의 실제 크기·내용 분포를 복제한 것은 아니다.

각 경로는 30건을 반환하며 reports/analyses는 완료 30건, jobs는 report/RCA 각 15건이다. 경로·버전별 새 Backend 프로세스에서 준비 조회 2회 후 20회 순차 요청했다. 지연은 응답 본문 수신 완료까지의 시간, p95는 20회 중 19번째 값이다. 메모리는 준비 조회를 포함해 100 ms마다 관측한 Backend RSS 최고치로, 절대 peak나 컨테이너 제한 검증이 아니다.

1차 측정 순서는 수정 전 → 수정 후였다.

| API | 수정 전 중앙값 / p95 | 수정 후 중앙값 / p95 | 중앙값 감소 | 관측 Backend RSS 전 → 후 |
|---|---|---|---|---|
| `/reports?limit=30` | 948.037 / 4019.523 ms | 89.218 / 123.434 ms | 90.6% | 128.98 → 20.06 MiB |
| `/jobs?limit=30` | 908.961 / 1040.411 ms | 70.944 / 104.695 ms | 92.2% | 146.44 → 20.12 MiB |
| `/analyses?limit=30` | 892.426 / 937.783 ms | 49.967 / 53.136 ms | 94.4% | 141.98 → 21.75 MiB |
| `/reports?limit=30&status=failed` | 71.847 / 85.907 ms | 4.235 / 5.104 ms | 94.1% | 52.77 → 22.30 MiB |

- **통과:** 모든 요청에서 `request_id`만 제외한 전체 응답 JSON이 수정 전후 동일했다. cursor·null·버튼 판정도 비교했다. 화면으로 전송되는 응답 크기를 줄인 변경이 아니라, DB에서 Backend로 가져와 해석하는 중간 데이터를 줄인 변경이다.
- PostgreSQL 로그 기준 완료 30건의 요청당 SQL은 C07·scope 포함 33회에서 4회로 줄었다. 목록 자체는 작업 1회+결과 30회에서 schema 호환성 검사 1회+요약 JOIN 1회가 된다. 실패 목록은 결과 조회가 없어 3회에서 4회로 늘지만 큰 작업 스냅샷의 전송·해석을 생략해 지연은 줄었다. 첫 reports 전 측정에 pool `-- ping` 1회가 추가돼 원시 기록은 33.05회/요청이며 기능 SQL과 구분했다.
- 로컬 측정 스크립트/원시 결과: `.local/list-read-perf/run.py`, `run-20261012T051744Z/summary.json` 및 해당 폴더의 로그. 로컬 산출물이며 제품 파일에 포함하지 않는다. 최초 reports 측정 초반의 긴 지연도 제외하지 않았다.

## 실행 순서를 뒤집은 추가 확인

동일한 중단된 테스트 DB를 재기동하고 두 바이너리 SHA가 동일함을 확인한 뒤, 수정 후 → 수정 전 순서로 각 경로 준비 2회/측정 20회를 반복했다. 1차 원본 응답과도 `request_id`를 제외하고 모두 동일했다. 캐시·실행 순서의 영향을 확인하기 위한 반복이며 초기 지연을 임의로 제외하지 않았다. 두 회차를 합친 버전별 40회 결과는 아래와 같다.

| API | 수정 전 중앙값 / p95 | 수정 후 중앙값 / p95 | 중앙값 감소 |
|---|---|---|---|
| reports | 924.600 / 3441.362 ms | 66.924 / 117.125 ms | 92.8% |
| jobs | 908.113 / 3109.297 ms | 61.657 / 104.695 ms | 93.2% |
| analyses | 883.302 / 937.783 ms | 49.395 / 54.482 ms | 94.4% |
| failed_reports | 71.594 / 87.294 ms | 4.197 / 5.059 ms | 94.1% |

역순 로그의 완료 목록 SQL은 정확히 33 → 4회/요청이고 연결 확인 ping은 별도 집계했다. 관측 RSS 최고치는 두 회차 중 큰 값으로 reports 144.38 → 21.62 MiB, jobs 146.44 → 20.12 MiB, analyses 150.03 → 22.17 MiB다. 원시 결과는 위 1차 폴더의 `reverse-20261012T052136Z/summary.json`, 합산은 `combined-summary.json`이다. 모든 테스트 Backend와 PostgreSQL 프로세스는 측정 후 종료했다.

**미수행/미검증:** 운영 배포·운영 DB 부하·동시 사용자·Kubernetes 메모리 제한하 OOM 재발 여부·원격 CI. PostgreSQL은 결과 상태 필드를 꺼낼 때 큰 JSON을 내부적으로 읽을 수 있다. 상세/다운로드는 기존 전체 본문 조회이며, 보고서 목록 첫 카드의 별도 요약 조회도 이 상세 경로를 사용하므로 그 지연까지 제거했다고 주장하지 않는다. 운영 검증 시 현재 Helm values를 유지하고 목록 응답·상세 응답·Pod 재시작을 구분해서 측정해야 한다.

---

# 2026-10-06 D binding 결과 표시 — 로컬 검수

## 2026-10-07 실패 슬롯 반환 소비와 시도 상태

**통과:** Backend·JC·Incident Go vet/race/build, 새 임시 PostgreSQL Backend·Incident 전체 E2E. 시도 DTO의 `remote_call_state`, `slot_state`, `slot_released_at`을 RCA/report 경로에서 확인했다. JC 테이블/예약이 없는 Backend 단독 실행은 슬롯 필드를 null로 보존하며 다른 시도의 예약을 연결하거나 claim token·boot/worker ID·반환 근거를 노출하지 않는다. 실패 슬롯 반환·늦은 결과 거부·기존 격리 전환 검증은 [JC QA](../job-controller/QA.md)를 따른다. **미검증:** 운영 배포·실제 모델 부하. API 추가 필드는 선택적이며 DB schema 변경은 없다.

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
