# 2026-10-06 대용량 수집·MCP 통신 복구 — 로컬 검수

- 기준: 새로 fetch한 `origin/main` **b4ca5c7**, `fix/report-collection-resilience`. 공통 MCP 전송과 크기 초과 복구, Ops D06 초기 조회 구간을 보완했다. 기본 프로필 `builtin-grafana-v7`과 Helm 미러에 `report.query_chunk_seconds={"D06":7200}`을 추가하고 계획·실행에 같은 상한을 적용한다. 다른 query는 기존 Ops 기본 24시간, RCA는 기존 1시간을 유지한다.
- **통과 — 전체 회귀:** 저장소 루트, Python **3.11.16**, NAT 1.5.0에서 `RUN_AGENT_E2E=1`과 로컬 `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`, `HELM_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/collection-resilience-results.xml` 실행: **388 passed, 0 skipped, 66.61초**. 외부 DB 환경변수 두 개를 제거하고 매번 새 임시 loopback PostgreSQL을 사용했다. 현재 소스로 다시 빌드한 Go 서비스·별도 두 Worker·공식 Grafana MCP 1.4.2는 실제 프로세스이며 Grafana/LLM 응답은 fixture다. 기존 MCP deprecation warning 3건이 남는다.
- **통과 — 통신 회귀:** 실제 localhost HTTP 소켓에서 5.2초 지연 응답 성공, 연결 단절 뒤 두 Worker의 heartbeat·실패 보고·다음 실행 성공, 세션 종료 404 뒤 다음 호출 재연결을 확인했다. 실패한 조회를 자동 재전송하지 않는다. 도구 deadline·외부 취소·동시 호출 중 한 호출 취소·일반 도구 오류·종료 후 태스크 회수도 검사했다. 세션 종료 처리는 `get_tools`/`call_tool`의 공통 경로에 둔다.
- **통과 — 큰 응답과 의미 보존:** 공식 MCP로 보낸 Prometheus 인공 응답 **11,536,878바이트**는 전송된 뒤 Agent의 2MiB 제한에서 분할됐다. 별도 단일 실행에서는 3600초 요청을 버린 뒤 523초 구간 6개와 마지막 462초, 총 8회로 수집했고 원본 121개 표본·전체 기간·대상 필터가 보존됐다. **MCP의 10MiB 제한을 모든 출처에 적용되는 것으로 해석하지 않는다.** 원격 10MiB 제한은 기존 Loki E2E에서 확인했으며, Prometheus 원격 크기 오류 분기는 오류 주입 fixture로만 검사했다.
- **통과 — 수집 계획:** 1/7/31일 원본 표본, 2개 클러스터·11주제 초기 계획 46/322/1426회와 작은 사용자 예산의 사전 거절, Pod 이름 재사용·UID 충돌·표본 공백, 분할 중 호출/deadline 소진의 미확인 구간 보존을 검사했다. D06의 2시간은 확인한 하루 약 32MiB 응답을 줄이는 초기 상한이며 최적 구간이나 월간 완료 보장이 아니다. 구간별 소요시간·크기·표본 수·분할 사유를 새 진단 로그에 남긴다.
- **통과 — 정적·설정 검수:** Ruff check/format, Helm lint/template/package와 설정 미러, CI 도구 unittest 5건, 문서 링크·diff·CRLF 검사. 독립 검토에서 찾은 만료 세션 재사용 문제를 수정하고 최종 전체 회귀를 다시 실행했다. 새 수집 진단은 원본 payload·조회식·인증 값을 출력하지 않지만 NAT의 기존 원문 오류 로그까지 정리한 변경은 아니다.
- **미수행/미검증:** 운영 배포·수정본으로 같은 24시간/주간/월간 실제 보고서 재실행·운영 부하와 처리시간·원격 CI. 이번 운영 실패가 Mimir 과부하나 Prometheus 원격 10MiB 제한 때문이었다고 확정하지 않는다. 완료 단계는 로컬 파일이며 커밋·푸시·PR은 하지 않았다.
- **해당 없음/후속:** DB migration·API/result schema·JC lease/슬롯 정책·RCA 계산/판정·UI 변경은 없다. 공통 전송 변경은 두 Worker 이미지에 적용해야 하며 사용자 정의 전체 Agent 프로필은 D06 맵과 revision을 별도로 반영해야 한다. 기존 격리 해제와 11개 주제 축소·중복 evidence 저장/보존 정책은 이번 변경에 포함하지 않았다.

---

# 2026-10-06 PR 최종 재검수 — Fleet 지표와 실행시간 표시

- **통과:** 새로 fetch한 `origin/main`과 작업 시작 커밋은 모두 **2d9ee8f**이며 양쪽 단독 커밋은 0개였다. 기존 로컬 Fleet 설정과 Frontend 실행시간 표시를 함께 검토했다. 아래 10월 2일 기록은 당시 기능별 검수 범위를 뜻한다.
- **통과:** 저장소 루트의 격리 로컬 DB·실제 두 Worker·공식 MCP E2E를 포함해 **364 passed, 0 skipped, 61.85초**. Python 3.11.16, 앞선 검사와 같은 로컬 도구/외부 DB 환경 제거 조건이며 결과는 `.local/report-usability/pr-fleet-execution-results.xml`이다. Grafana/LLM 상위 응답은 fixture, 기존 MCP deprecation warning 3건이다.
- **통과:** Ruff check/format, Helm 계약·설정 미러, CI 도구 unittest 5건, 문서 링크·diff와 독립 검토. Frontend **136 passed**·format/build와 상세 표시 검수는 [Frontend QA](../frontend/QA.md)를 따른다.
- **범위/미검증:** RCA 판단 코드·Ops 산식은 바꾸지 않지만 D04/D11 공통 설정은 두 Worker에 적용된다. 특정 Namespace의 온도/전력 귀속, D07/D12 원본 확보, 운영 배포/수정본 실제 재실행은 미검증·미구현이며 이번 PR 범위에 포함하지 않는다. 원격 CI 상태는 PR에서 확인한다. 기존 운영 데이터·DB schema 변경은 없다.

---

# 2026-10-02 Fleet 온도·전력 조회명/대상 라벨 — 로컬 검수

- 기준: 최신 `origin/main` **2d9ee8f**, `fix/fleet-metric-bindings`. 기본 profile `builtin-grafana-v6`의 D04/D11을 실제 소문자 Fleet 이름과 `uuid`/`node` 필터에 연결하고 query revision을 `builtin-v6`로 변경했다. Helm 미러도 동기화했다. 공통 설정이 두 Worker에 적용되며 RCA 판단·Ops 산식·수집 코드·UI·DB/API/result schema는 변경하지 않았다.
- **통과 — 실환경 읽기 확인:** 로그인된 Grafana Mimir-Operations에서 2026-10-01 00:00~10-02 00:00(Asia/Seoul), CPC-1/CPC-2를 조회했다. 소문자 온도/전력의 원본 존재·`uuid`/`node`·Namespace 라벨 부재, 기존 대문자 GPU_UTIL/FB_USED·Pod/up 지표의 존재를 확인했다. 대문자 GPU_UTIL에는 `UUID`와 `uuid`가 모두 있어 D02/D08 필터를 유지한다. D07/D12 및 확인한 이름 변형은 이 기간에서 없었고 원시 Container 요청은 다른 계약이므로 대체하지 않았다. 이는 해당 기간/클러스터의 확인이며 전역 가용성 보장이 아니다.
- **통과 — 표본 공백:** 기간 끝 15분의 일부 전력 원본에는 60/120/180초 간격이 있었다. 기존 max_hold 30초를 유지하고 유효 관측 구간만 계산한다. 표본 공백을 채우거나 24시간 전체 에너지가 확보됐다고 판단하지 않는다. 단위 동등성은 [Fleet/Exporter 소스 대조](../docs/specs/rca-agent/references/domain-category-metric-mapping.md)에 근거하며 배포된 전체 producer 설정/지원 sentinel은 재검증하지 않았다.
- **통과 — 로컬 전체:** 저장소 루트, Python 3.11.16, `RUN_AGENT_E2E=1`과 `.local/namespace-tools`의 PostgreSQL/MCP/Helm, 로컬 JC/Backend/Incident를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/fleet-bindings-results.xml` 실행: **364 passed, 0 skipped, 63.38초**, 기존 MCP deprecation warning 3건. 외부 DB 환경 변수를 제거하고 임시 loopback PostgreSQL을 사용했다. 두 Worker·공식 MCP 1.4.2는 실제 프로세스이며 Grafana/LLM 상위 응답은 fixture다.
- **통과 — 회귀:** fixture는 잘못된 대문자 온도/전력 이름에 빈 결과를 반환한다. 전체 Namespace에서 40°C·250W×1시간=0.25kWh·GPU 신원, 특정 Namespace에서 필터 유지·빈 근거/null을 확인했다. RCA D04의 정확한 조회명·uuid/node 필터·원본 라벨, 60/120초 간격과 실제 0 표본의 총 유효 90초/0.0025kWh 계산을 검사했다. Ruff check/format, Helm 계약/미러, CI 도구 unittest 5건, 문서 링크·diff 검사도 통과했다.
- **미수행/미검증:** 운영 설정 변경·배포·수정본으로 실제 보고서/RCA 재실행·원격 CI·커밋/푸시/PR. 특정 Namespace의 GPU 온도·전력 귀속은 미지원이며 기존 제한을 유지한다. 수집 주기 보완/유지시간 확대·D07 유효 요청 producer·D12 용량 전송·D 통합/신규 D 구현은 포함하지 않았다. DB migration·과거 결과 재작성은 해당 없음.

---

# 2026-10-02 Loki 응답 용량·잘림 복구 — 로컬 검수

- 기준: 새로 fetch한 `origin/main` **a1d73e2**, `fix/loki-response-size-recovery`. 공통 Observation에서 MCP 본문 크기 초과와 Loki 행 잘림을 기존 기간 분할로 복구한다. 두 Worker의 수집 동작에 적용하며 RCA 판단·Ops 산식·D 정의·프로필/한도·DB/API/result schema는 유지한다.
- **통과:** 저장소 루트, Python 3.11.16 전체 Agent 검사 **362 passed, 0 skipped, 61.71초**. `RUN_AGENT_E2E=1`과 로컬 `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`, `HELM_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/loki-size-results.xml`을 실행했다. 외부 DB 환경 변수를 제거하고 새 임시 loopback PostgreSQL·최신 소스 JC/Backend/Incident·두 Worker·공식 Grafana MCP 1.4.2를 사용했다. Grafana/LLM 응답은 fixture이며 기존 MCP deprecation warning 3건이 남는다.
- **통과:** 공식 MCP/NAT E2E에서 상위 HTTP fixture의 11MiB 응답으로 실제 `response body exceeds maximum size of 10485760 bytes` 오류를 발생시킨 뒤 D09/D13·파생 D05의 연속 구간 복구·요청 기간 끝까지 수집·대상 필터와 정상 응답 필드 보존을 확인했다. D13 로그는 건강 관측으로 승격하지 않는다. 이 fixture는 조회 구간에 따라 응답을 생성하므로 동일 사건 집합 보존은 별도 고정 사건 단위 검사로 확인한다.
- **통과:** `test_discovery.py` **67 passed**. NAT 문자열/isError envelope·행 잘림/행 수 도달, 원본 고정 로그 집합·범위·query revision·파생 참조, 성공한 앞 구간과 예산/deadline 소진 나머지, 최소 구간 초과·원본 오류 비노출·취소 전파·일반 오류/Prometheus 미재시도·기존 시각 정밀도 회귀를 확인했다. 수정 전에는 새 복구/사유 검사 16건이 실패했다.
- **통과:** Ruff check/format 72개 파일, 문서 링크·diff 검사. 기존 `response_byte_limit` 사유를 재사용하므로 RCA/Frontend/Backend 이름 맵·UI 변경은 없다. 독립 코드 검토에서 차단할 문제는 발견하지 않았다.
- **미검증:** 원격 CI, 운영 배포 후 동일 기간의 실제 Grafana 재조회·보고서 공개·운영 부하/메모리. 로컬 fixture 성공은 실제 운영의 전체 기간 수집 보장이 아니다. 기존 예산/마감 안에 복구하지 못한 구간은 계속 미확인으로 남는다.
- **반영:** 병합·CI 성공 후 두 Worker 이미지를 함께 갱신하고 새 보고서로 확인한다. MCP 이미지·설정·DB migration·기존 결과 재작성은 필요 없다. 배포와 운영 변경은 이번 PR 생성에 포함하지 않는다.

---

# 2026-10-02 Ops 계산 중 heartbeat 유지 — 로컬 검수

- 기준: 최신 `origin/main` **03105a4**, `fix/report-calculation-heartbeat`. Ops 주제 계산만 요청 순서대로 별도 스레드에서 실행하고, 해당 주제에 필요한 할당·활동 입력만 정규화한다. 취소 시 현재 계산을 회수하며 다음 주제·문장 구성·저장으로 진행하지 않는다. RCA·공통 Worker/Store·JC·조회 한도·lease·스키마는 변경하지 않았다.
- **통과:** Python 3.11.16 전체 Agent 검사 **344 passed, 0 skipped, 54.93초**. 저장소 루트에서 `RUN_AGENT_E2E=1`과 준비된 로컬 `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`, `HELM_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/calculation-results.xml`을 실행했다. 외부 DB 환경 변수를 제거하고 임시 loopback PostgreSQL·최신 소스 JC/Backend/Incident·두 Worker·공식 Grafana MCP를 사용했다. Grafana/LLM 응답은 fixture이며 기존 MCP deprecation warning 3건이 남는다.
- **통과:** 새 Worker 검사 7건은 lease보다 긴 CPU 계산 중 heartbeat, criteria 1.1/1.2의 11개 주제 순서·산출물, 취소·반복 취소·409·deadline·계산 오류를 확인한다. 취소 후 계산 오류가 발생해도 원래 취소를 보존하며 Worker 반환 전에 계산을 회수한다. 수정 전 `run()`만 메모리에서 복원하면 성공 사례 2건이 계산 중 heartbeat 0회·lease 만료로 실패한다.
- **통과:** 실제 JC/DB E2E는 시험 job에만 2초 lease를 적용하고 2.6초 CPU 계산 중 heartbeat 200 유지, 11개 주제·기본 보고서 저장, checksum 일치와 `succeeded` 공개를 확인했다. 운영 설정은 변경하지 않았다.
- **통과:** main과 수정 코드의 11개 주제 × 기준 버전 2개 × 정상/빈 fixture 결과 44건이 동일했다. 별도 286 Pod·8 GPU·1시간 합성 자료에서 계산 0.506→0.258초, 10ms 주기 확인의 최대 공백 0.516→0.024초였고 수치·입력은 동일했다. 단일 로컬 측정이며 운영 처리시간이나 속도 개선율의 보장이 아니다.
- **통과:** Ruff check/format, 문서 링크 검사, diff 검사. 수집·주제 계산·문장 구성 시작/완료 로그로 후속 지연 구간을 구분한다.
- **미검증:** 운영 배포·실제 Grafana/LLM 보고서 재실행·운영 메모리/성능. 운영 로그의 약 75초 heartbeat 공백 전체가 계산에 쓰였는지는 당시 계측 부재로 확정하지 않는다. 기존 격리는 자동 해제하지 않으며 원격 종료 확인 뒤 별도 운영 절차를 따른다. DB migration·기존 결과 재작성은 해당 없음.

---

# 2026-10-02 O08 클러스터별 관측 요약 — 로컬 검수

- 기준: `b79758a`, 로컬 `fix/report-cluster-observation`. Ops O08 criteria 1.2에 요청 클러스터별 관측 GPU·연결 GPU·연결 시간·라벨 부재·신원 미확인 지표를 추가했다. RCA·공통 정규화·DB/API/result schema는 변경하지 않았다.
- **통과:** Python 3.11.16 전체 Agent 검사 **335 passed, 0 skipped, 43.00초**, 기존 MCP deprecation warning 3건. `RUN_AGENT_E2E=1`과 로컬 도구 경로를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/cluster-results.xml`을 실행했다. 임시 loopback PostgreSQL·실제 JC/Incident/Backend·두 Worker·공식 Grafana MCP를 사용했고 Grafana/LLM 응답은 HTTP fixture다.
- **통과:** 빈 작업 라벨은 유휴로 단정하지 않음, 클러스터별 evidence 참조, UUID 중복 제거, 공유 연결 시간 합집합, 선택 Namespace 범위, 부분 시간 조인, 유효 표본 없음·MIG·조회 실패·부분/미수집과 확인된 0 구분, 정상 빈 응답, 기존 Namespace 활동률·RCA 회귀. Ruff check/format 통과.
- **미수행/미검증:** 운영 조회·배포·기존 결과 재계산·실제 클러스터의 유휴 여부·커밋·푸시·PR·원격 CI. 브라우저 예시는 합성 D01/D02를 실제 계산 함수와 결과 검증기로 처리했다.

---

# 2026-10-02 Runbook-first RCA / R 실행 의존 제거

- **PR 준비 재검증 통과:** 최신 `main` **5f52fe5**를 반영하고 문서 2곳의 양쪽 변경을 보존했다. Python **324 passed, 0 skipped**(123.49초), Frontend **118 passed**·format/build, 4개 Go 모듈 vet/race/build, Backend·Incident DB/E2E, Ruff·문서 링크·diff 검사 통과. Windows 로컬 pytest 실행에는 실제 Worker와 같은 `WindowsSelectorEventLoopPolicy`를 적용했다. 아래 315/101건은 main 반영 전 최초 검증 기록이다.
- **통과:** Python 3.12.14 전체 Agent 검사 **315 passed, 0 skipped**(121.74초). 저장소 루트에서 `RUN_AGENT_E2E=1`과 현재 소스 JC/Incident/Backend 바이너리, 격리 로컬 PostgreSQL, 공식 Grafana MCP, Helm을 지정해 `python -m pytest -c agents/pytest.ini agents/tests -q --tb=short`를 실행했다. Grafana·LLM 응답은 HTTP fixture이며 운영 DB는 사용하지 않았다.
- **통과:** R 없는 신규 1.5 입력 → Incident outbox → JC → RCA Worker → 결과 발행, 기존 1.3 입력·불변 snapshot 호환, 1.4/1.5 입력 검증, Runbook 계획의 D04 선택, 미등록 값·실패·stop·일반 조사 전환, 미일치·비호환 Runbook의 패키지 fallback, 원인 미확정·추가 근거 유지. 기존 R 목적에 따라 강제하던 GPU–Pod 조회는 이제 해당 Runbook의 필수 계획으로 검증한다.
- **통과:** `shared`, `backend`, `job-controller`, `incident` 각각 `go vet ./...`, `go test -race ./...`, `go build ./...`. Windows 경로의 대괄호와 Go embed 제약 때문에 동일 소스를 임시 경로에 복사해 검사했다. Backend·Incident에서 격리 DB와 실제 Backend 바이너리를 지정한 `go test -tags=e2e ./tests -v -count=1 -timeout=10m`도 통과했다. 006의 기존 Worker 행/제약 → 007 업그레이드, 반복 시작, 1.5 허용·미지원 버전 거부를 포함한다.
- **통과:** `frontend`에서 `npm test` **101 passed**, `npm run build`. 신규 조사 질문 표시와 과거 purpose_id 결과 표시를 함께 검사했다. 루트 Ruff check/format, 문서 링크, `python tools/ci/check_chart.py`, `python -m unittest discover -s tools/ci/tests -v` **5 passed**도 통과했다. 처음의 도구 경로 오류는 설치된 Git Bash·Helm 경로를 명시해 해결했다.
- **미검증:** 원격 CI·운영 배포·실제 Grafana/LLM의 분석 품질. 완료 단계는 로컬 파일이며 commit/push/배포·Runbook DB 발행은 수행하지 않았다. 적용 순서는 JC → RCA Worker → Incident/화면이다. D 구조 확대는 이번 범위에서 제외했다.

---

# 2026-10-02 대량 저장 중 heartbeat·lease 보호 — 로컬 검수

- 기준: 새로 fetch한 `origin/main` **5ddfe21**, 로컬 브랜치 `fix/worker-save-heartbeat`. 공통 Store/Worker와 JC 행 잠금만 수정하며 Worker별 분석·관측 계획·해시 규칙·스키마·lease/슬롯 설정은 유지한다.
- **통과:** Python 3.11.16, 루트 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --tb=short --junitxml=.local/report-usability/save-results.xml` — **315 passed, 0 skipped, 43.36초**, 기존 MCP API deprecation warning 3건. `RUN_AGENT_E2E=1`, `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`, `HELM_BINARY`를 준비된 로컬 도구로 지정했다. 새 임시 loopback PostgreSQL·실제 JC/Incident/Backend·두 Worker·공식 Grafana MCP를 사용하며 데이터소스/모델 응답은 HTTP fixture다. 테스트 DB는 종료했다.
- **통과:** `test_store.py`의 실제 JC/DB 검사: 합성 evidence 217건, 2초 시험 lease보다 긴 2.6초 저장 지연 중 heartbeat 갱신과 최종 공개·동일 완료 재전송·원본 JSON/checksum 보존. 저장 중 취소·lease 만료·attempt 교체·deadline 만료는 evidence/candidate를 모두 롤백한다. JC의 실제 행 잠금 대기를 확인한 뒤 lease를 만료시키면 heartbeat 409로 갱신을 거부한다. 실제 운영 41 MiB snapshot의 성능 재현은 아니다.
- **통과:** Worker 저장 도중 취소/409 lease 상실 시 저장 task를 회수하고 complete를 보내지 않는 검사. JSON 큰 정수·소수·한국어·특수문자 보존, 기존 RCA/Ops 회귀 포함.
- **통과:** Ruff check/format 70개 파일. JC·Backend·Incident 각각 Go vet/race/server build, 별도 임시 PostgreSQL의 Backend·Incident 전체 `-tags=e2e` 검사. 관련 JC 배분·취소·완료·재시도 경로 포함. 문서 링크와 diff 검사 통과.
- **미수행/미검증:** 커밋·푸시·PR·원격 CI·배포·운영 보고서 재실행·기존 격리 해제·실제 Grafana/LLM·운영 메모리/저장 성능. 기존 운영 실패의 CPU와 DB 대기 시간 비율은 당시 계측 부재로 확정하지 않는다.
- **해당 없음:** DB migration, API/result schema, Frontend 변경. 배포 시 JC → 두 Worker 순서로 함께 반영하며 기존 격리는 모델 서버 종료 확인 후 별도 운영 절차로 해제한다.

---

# 2026-10-02 보고서 계획 기반 병렬 MCP 수집

- **통과:** Python 3.12.14 전체 Agent 검사 **306 passed, 0 skipped** (94.70초). `RUN_AGENT_E2E=1`, 격리 로컬 PostgreSQL, 최신 소스 Backend/JC/Incident, 공식 Grafana MCP 1.4.2와 Helm으로 실행했다. 데이터소스·모델은 HTTP fixture이며 운영 DB는 사용하지 않았다.
- **통과:** `test_report_parallel.py`는 동시성 1/3의 수치 동일성, 상한, 중복 query 제거, 의존 순서와 Namespace 범위 축소, 완료 응답 재사용, 발견 예산 상한, 취소 후 task 회수, 독립 실패와 비교 기간 분리를 검사한다. 기존 기간 수집·RCA 병렬 회귀도 통과했다.
- **통과:** Ruff check/format, 문서 링크 검사, 실제 Helm lint/template/package 및 설정 미러 검사. Linux Bash 실행을 포함하는 배포 파이프라인 단위 검사는 Windows에 Bash 실행 파일이 없어 로컬에서 실패했으며 PR CI에서 확인한다.
- **시간 비교:** 독립 MCP 6회에 각 40ms 지연을 주는 고정 검사에서 순차 0.281초, 동시성 3에서 0.094초였다. 실제 Grafana 성능 측정이 아니다.
- **미검증:** 운영 배포·실제 일간/주간/월간 자료의 처리시간·부하·메모리·관측 의미·모델 품질. 추가 보완 라운드·자유 생성형 조언은 이번 구현 범위가 아니다.
- 실행: `.local/rca-dev-venv/Scripts/python.exe -m pytest -c agents/pytest.ini agents/tests --tb=short` (위 E2E 환경과 현재 서비스 바이너리 지정). 로컬 준비 스크립트는 검증 도구 경로만 지정하며 제품 코드에 포함하지 않는다.

---

# 2026-10-01 일 단위 보고서 Backend 접수 회귀

- **통과:** 최신 main `e9ed87e` 기반 Python 3.11.16 전체 **286 passed, 0 skipped**, Ruff check/format 66개 파일. `RUN_AGENT_E2E=1`과 격리 로컬 PostgreSQL, 최신 Backend/JC/Incident 바이너리, 공식 Grafana MCP 1.4.2, Helm으로 두 Worker의 실제 프로세스·발행 경로를 실행했다. 데이터소스와 모델 응답은 HTTP fixture다.
- **변경:** Backend를 통한 Namespace 보고서 E2E만 1시간 요청에서 24시간 요청으로 바꿨다. fixture의 121개 표본 × 30초 hold를 기대 관측시간으로 명시해, 하루 요청을 하루 전체 관측으로 오해하지 않도록 검사한다. Worker 구현·공통 PERIOD·RCA 요청·수집 한도는 변경하지 않았다.
- 첫 검증은 오래된 Incident 실행 파일·잘못된 Helm 경로와 시간 기대값으로 실패했다. 최신 소스 빌드와 올바른 도구 경로·기대값으로 다시 실행해 전체 통과했다.
- **미검증:** 운영 배포·실제 Grafana/LLM 실행. 운영 DB는 사용하지 않았다.

---

## 2026-10-01 RCA synthesis 식별자 인용 허용

기준 main `7abc8d2`(#39·#40 포함), `fix/rca-synthesis-identifier-prose`. #39 배포 후 운영 작업 `ed730b4d`(Loki 합성 SXID 11001)에서 입력 536,621→15,570바이트 제한, `request_attempts=1`·`response_calls=1`을 확인했으나 응답이 `invalid_limitations`로 탈락했다. 같은 view를 읽기 전용으로 재구성하면 `D05`·`R01`·`cpc-2`·`vessl-k8s-worker-01` 등 숫자가 포함된 식별자가 47종이었고, 기존 `\d` 전면 금지가 이를 거부한다. 모델 원문은 저장하지 않으므로 실제 문장은 추정이다.

- **통과:** Windows/Python 3.12.14 agent tests **199 passed, 17 skipped**(E2E). 식별자 허용·대소문자·부분 일치(`D050`, `worker-02`) 거부, 숫자만/개수/기간/측정값·생산자 문장 속 `95C` 거부 회귀 추가. Ruff check/format 통과(무관한 로컬 미추적 파일 제외).
- **통과:** 운영 작업 `ed730b4d` view에서 추출한 식별자 47종에 공백 포함 문장·시각·숫자+단위 값이 없음을 확인했다.
- **미검증:** `RUN_AGENT_E2E=1` 전체 검사는 PR CI로 확인한다. 배포 후 새 RCA 실행에서 모델 응답이 검증을 통과하는지는 별도 확인이 필요하다.
- **해당 없음:** DB migration·결과 스키마·기존 결과 재작성.

# 2026-10-01 Ops 기간 수집·예산 분리

- **통과:** Python 3.11.16, Ruff check/format. 일반 검사 208 passed, 17 E2E skipped. 로컬 전용 PostgreSQL + 현재 소스의 Backend/JC/Incident + 두 Worker + 공식 Grafana MCP 1.4.2 전체 실행은 **225 passed, 0 skipped** (36.58초). 운영 DB는 사용하지 않았다.
- **통과:** 새 10개 고정 검사로 1일/7일/31일/73시간 원본 표본과 전체 요청 구간 보존, 큰 응답 자동 분할, 기존 1시간 수집과 동일한 Namespace 수치·0%, 첫 dense 조회가 다른 query/CPC를 고갈시키지 않는 예산 배분, 초과 계획의 외부 조회 0회, 비교 기간 분리, 오류/시간 만료/취소 전파, RCA profile 불변과 구 설정 fallback을 확인했다.
- **통과:** 기존 실제 프로세스 Namespace E2E에서 Backend 접수→Ops→JC 발행→HTML/CSV를 재검사하고 적용 한도 2048·계획 accepted·필수 D01/D02/D06/D08 전체 조회 구간 완료를 확인했다. RCA E2E도 통과했다. 데이터소스 응답은 HTTP fixture다.
- **통과:** Helm 3.17.3 chart 계약/패키징 및 workflow 계약 5개, 소스 설정과 Helm 미러 일치.
- **미검증:** 운영 배포, 실제 클러스터의 일간/주간/월간 데이터 밀도·표본 보존·부하/지연/최대 메모리. 기간 고정 검사는 운영 규모 성능 검증이 아니다. 보고서 전용 예산은 초기 예시이며 모든 범위의 성공을 보장하지 않는다. 재분할/에러/시간 소진 시 미완료를 명시한다. 원격 CI는 PR에 기록한다.

---

## 2026-10-01 RCA synthesis 입력 크기 제한·단계별 진단

기준 main `406f9fa`(#38 포함), `fix/rca-synthesis-context-budget`. 운영 작업 `22c1f69f`의 저장 evidence를 읽기 전용(`default_transaction_read_only=on`)으로 조회해 synthesis 입력 하한 530,150바이트가 작업 예산 32,768을 넘어 `LLM.complete()` 요청 전에 탈락함을 재현했다. 같은 GUI 결과의 `LLM 응답 사용 기록 1건`은 최종 보고서 편집 호출이었다.

- **통과:** Windows/Python 3.12.14 `python -m pytest -c agents/pytest.ini agents/tests -q`: **198 passed, 17 skipped**(E2E). 관계없는 로컬 미추적 `test_gpu_node_scope.py`는 제외했다. Ruff check/format 통과.
- **통과:** 같은 저장 evidence에 새 `bounded_context`를 적용하면 모델 입력 15,680바이트, 장비 관측 2건 전부 유지, metric 계열 138개 중 7개 선택·131개 생략이 `context_selection`에 기록된다. 원본 evidence는 변경하지 않는다.
- **통과:** README의 `rca_synthesis` 진단 SQL을 같은 DB에서 읽기 전용 실행. 구 결과의 `diagnostics`는 NULL이다.
- **미검증:** 로컬 Docker·Go가 없어 `RUN_AGENT_E2E=1` 전체 검사는 PR CI(Linux/Python 3.12, PostgreSQL 16)로 확인한다. 운영 배포와 새 RCA 실행에서의 실제 모델 응답 품질은 별도 검수 대상이다.
- **해당 없음:** DB migration·결과 스키마 버전·기존 결과 재작성·운영 설정 변경.

## 2026-10-01 Agent E2E Backend 중복 migration 교착 수정

기준 main `af9294e`(#34·#35 포함). [실패 CI 36793523231](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/actions/runs/36793523231)의 PostgreSQL 로그에서 Backend `ALTER TABLE jobs`와 JC의 만료 작업 `UPDATE jobs` 사이 `SQLSTATE 40P01` 교착을 확인했다. stack의 JC가 공통 schema를 준비한 뒤 모델 인증·런북 테스트의 Backend가 migration을 재실행하던 두 곳을 `DSX_MIGRATE=false`로 바꿨다. 기존 Namespace 테스트와 같은 설정이다.

- **통과:** macOS arm64/Python 3.11.16, Go 1.26.2의 현재 소스와 동일한 Backend/JC/Incident 바이너리, 실제 새 loopback PostgreSQL·Worker/NAT/공식 MCP로 전체 **206 passed**, 33.80초. 기존 MCP deprecation warning 3건. `DATABASE_URL`·`AGENT_E2E_DATABASE_URL`을 제거하고 `RUN_AGENT_E2E=1`로 실행했다. JUnit: `.local/e2e-migration-fix/results.xml`. Grafana/LLM 응답은 fixture다.
- **통과:** 모델 인증 두 Worker·고정 revision·런북 263개 등록/조회/hash/중복 방지 및 실제 RCA 소비·Namespace 보고서 검사. Ruff check/format·문서 링크·diff 검사.
- **유지:** Backend 자체 migration 및 재실행 검증은 별도 Backend DB E2E에 남아 있다. 테스트 재시도나 timeout 증가로 실패를 숨기지 않는다.
- **미검증:** 수정 커밋의 Linux/Python 3.12 전체 CI는 PR 생성 후 확인하고 PR 설명에 기록한다. 운영 migration 동시 실행 조정이나 배포 검증은 이번 변경 범위가 아니다.
- **해당 없음:** 제품 코드·SQL·운영 DB/설정·UI·API·배포 변경.

## 2026-09-30 보고서 단위 설명·수집 범위 개선

## RCA 접근·Ops 최종 보고서 — 2026-09-30

기준 main `40b68d3`(#31), `feat/final-report-access` 로컬 작업. 기존 GPU 시간·수집 재사용/범위 축소를 유지했다.

- **통과:** 루트 Python 3.12.14 `python -m pytest -c agents/pytest.ini agents/tests -q --basetemp=.local/pytest-final-access-2`: 189 passed, 17 skipped. Ops 수치 없음/실제 0, 모델 선택/무효 응답/미설정에서 다섯 섹션·부족 사유·원래 품질 보존, HTML escape 검사 포함. Ruff check/format 통과.
- **통과:** `.local/verify-final-report-access.py`, `RUN_AGENT_E2E=1`의 실제 Worker/NAT/공식 MCP·최신 로컬 Go 바이너리·격리 PostgreSQL: 관련 8 passed, 6 deselected. RCA native/Fleet webhook, 근거 없음 보고서 2건, 두 Worker 공개/참조·Worker HTML checksum/본문, fast path, Backend Namespace 보고서 HTML, Ops HTTP 실패 후 기존 수치 보존. 선택 외 6건은 이번에 미실행이다.
- **통과:** Backend/JC/Incident vet·race·build, `.local/verify-final-report-backend.py`의 격리 DB 전체 Backend E2E. Frontend 38 tests·format·build. 문서 링크/diff 검사.
- **미검증:** 운영 배포·실제 Grafana/LLM 의미와 품질, 실제 브라우저 클릭/화면 검수. Frontend는 컴포넌트 렌더 fixture이며 상위 Grafana/LLM도 fixture다. 운영 DB는 사용하지 않았고 새 임시 DB 종료를 확인했다. 새 schema/migration/API는 **해당 없음**. 커밋/push/PR/배포는 이번 작업에 포함하지 않았다.

기준: 원격 main `b80b8f7`(RCA PR #30 포함). 운영 보고서를 읽어 문제를 확인했으나 운영 데이터·설정은 변경하지 않았다. 과거 결과를 재계산하지 않는다.

- **통과:** 위 환경과 동일한 macOS/Python 3.11.16에서 `RUN_AGENT_E2E=1` 전체 검사 **199 passed**, 기존 MCP deprecation warning 3건. `DATABASE_URL`·`AGENT_E2E_DATABASE_URL`을 제거하고 `.local/namespace-tools`의 PostgreSQL/MCP/Helm, 최신 소스로 빌드한 Backend/JC/Incident를 사용했다. 명령은 아래 Namespace 전체 검사와 같고 JUnit은 `.local/agent-e2e/report-clarity-results.xml`이다. 실제 격리 DB·Worker·NAT·공식 MCP를 사용하며 Grafana/LLM 응답은 fixture다.
- **통과:** 이후 추가한 큰 Pod 집합 비교를 포함한 `agents/tests/test_report_observation.py` **12 passed**. GPU 8대/Pod 286개 고정 입력에서 기존/개선 namespace 수치와 품질이 같고 개선 조회는 3회였다. 운영 환경 호출 감소율·속도 검증은 아니다.
- **통과:** 8대×(1시간−6.113초) GPU-hours, 기간 중 고유 연결 대수, 기존 0/null·중복·공유/MIG·Pod UID·모델 충돌 회귀. 재사용 opt-in/기본 비활성, 기간/범위 격리, 불완전 응답 미재사용, namespace 단독 범위 축소와 혼합 보고서 전체 범위 보존을 확인했다.
- **통과:** Backend `go vet ./...`, `go test -race ./...`, 서버 build 및 새 loopback PostgreSQL의 `go test -tags=e2e ./tests -count=1 -timeout=10m`. 별도 schema와 임시 DB만 사용했다. Frontend 36 tests·format·build 및 로컬 브라우저 검수는 [Frontend QA](../frontend/QA.md)에 기록했다. Ruff·문서 링크·diff 검사 통과.
- **해당 없음:** RCA 제품 소스·설정 변경, JC 설정·DB migration·새 API·새 의존성. 공통 Observation에는 report opt-in 기능을 추가했으므로 두 Worker 회귀를 실행했다. 기존 Fleet 정밀도·usable_observation 처리는 보존했다.
- **미수행/미검증:** 운영 배포, 변경 코드의 실제 Grafana 조회 성능·LLM 품질, D08 할당 계약 확보. 원격 최신 커밋 CI 상태는 PR에서 확인한다.

# Agent 검증 기록

## 2026-09-30 Fleet RCA 파이프라인 후속 검증

최신 main `77fbfcf` 통합 후 **추가 통과**: 일반 175 passed/17 skipped, 관련 실제 프로세스 E2E 7 passed/7 deselected(webhook 2·근거 없음 2·두 Worker 공개·fast path·Backend namespace 보고서), Incident DB E2E 전체, Backend/JC/Incident vet·race·build, Frontend 33 tests·format·build, Ruff·Helm·문서 링크. 전체 263개 Runbook API import E2E는 병합 전 통과했고 병합 후에는 관련 7개만 재실행했다.

- **통과:** Python 3.12.14, 루트 `python -m pytest -c agents/pytest.ini agents/tests -q`: 175 passed, 17 skipped. skip은 E2E 별도 실행 대상이다. Ruff check/format, 문서 링크 검사, Helm chart 계약 및 CI unittest 3건 통과.
- **통과:** 최신 로컬 소스로 빌드한 Go 서비스와 새 격리 PostgreSQL, 실제 Worker/NAT/공식 MCP 1.4.2를 사용했다. 전체 실행 최초 187 passed/4 failed 중 Fleet timestamp 전달 결함, fast-path의 구형 LLM 0회 기대, Helm 경로 누락을 수정했다. 실패 관련 webhook(native/Fleet)·fast-path 3건 및 MCP Host 3건 재검사 통과. 나머지 전체 실행의 E2E는 통과했다. 전체 통과 단일 실행으로 표현하지 않는다.
- **통과:** 실제 공식 MCP의 `data[].timestamp/line`와 원시 Loki `values` 모두 ns 시각 보존. Fleet D05/D09 각 31건 → 62개 관측 → Synthesis 호출 → JC 공개. 원본 기간 partial 유지, degraded D02 실행, R02 D08/D06 계획, 대상 미확인 시 mapping 부족 유지, 5개 보고서 섹션, 기존 snapshot/hash 유지.
- **통과:** Incident DB E2E 전체, 공유/Backend/JC/Incident `go vet`, `go test -race`, `go build`. Go 임시 소스 복사본과 새 바이너리를 사용했다. Frontend 24 tests·format·build 통과.
- **미검증:** 운영 배포, 실제 Fleet producer 시각 의미/freshness/GPU binding, 실제 Grafana·LLM 분석 품질. 상위 Grafana와 LLM은 fixture다. DB migration은 **해당 없음**. 로컬 pytest 임시 디렉터리 정리 권한 경고와 기존 MCP deprecation 경고는 테스트 실패가 아니다.

로컬 실행 기록: `.local/verify-rca-pipeline-e2e.py`, `.local/verify-rca-pipeline-selected.py`, `.local/run-rca-pipeline-incident-e2e.py`. `AGENT_E2E_DATABASE_URL`을 제거하고 새 `C:/Users/Public/rca-pipeline-<uuid>` DB를 만들었으며 종료 후 프로세스를 정리했다. 아래 최종 보고서 단독 변경 기록은 이번 후속 수정 이전 시점이다.

## 2026-09-30 RCA 최종 보고서

로컬 파일 구현·검증 단계. 근거 없음·승인 Runbook 없음·결정적 fast path에서도 다섯 섹션을 만들고 모델 문장 ID 편집을 시도한다. 미설정/확정 실패/무효 응답은 코드 기본 보고서로 대체하며, 원인 분석 상태·권고 적격성·snapshot/hash는 유지한다. 원격 종료 불명은 기존 Worker fail/격리를 유지한다. DB migration·배포·과거 작업 재분석은 하지 않았다.

| 기준 | 결과와 범위 |
|---|---|
| 두 Worker 일반 회귀 | **통과**: 저장소 루트에서 `.local/rca-dev-venv/Scripts/python.exe -m pytest -c agents/pytest.ini agents/tests -q --basetemp=.local/pytest-rca-final`: 164 passed, 16 skipped. skip은 별도 E2E/환경 조건이며 통과로 계산하지 않음 |
| 실제 프로세스 연동 | **통과**: `RUN_AGENT_E2E=1`, `test_e2e.py -k 'rca_without_observations or real_workers_nat_grafana_mcp_and_publication'`: 3 passed, 10 deselected. 근거 없음+편집 성공/HTTP 503, RCA→JC 공개, 기존 관측 Synthesis와 Ops 공개 RCA 인용 검증 |
| 내용·경계 | **통과**: 다섯 섹션 비어 있지 않음, 원천 REBOOT_SYSTEM 미검증/미수행 보존, 무효 문장 ID·응답 오류·모델 미설정 기본 보고서, RemoteUncertain 전파, 결과 상태 불변 |
| 정적 검사 | **통과**: `ruff check`와 `ruff format --check`를 `shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`에 실행. 문서 링크·diff 공백 검사 |
| 화면 | **통과**: Frontend 24 tests, build, format:check. 공개/미공개·기본 보고서·HTML escape. [Frontend QA](../frontend/QA.md) 참고 |
| 운영 | **미검증**: 실제 Fleet/Grafana 데이터·실제 LLM 품질/연결, 운영 배포, 전체 E2E 재실행(이번에는 관련 3건 실행). 운영 로그 파서 불일치나 datasource 문제를 해결한 변경이 아님 |

환경: Windows / Python 3.12.14 / 실제 격리 PostgreSQL 16.9, 기존 로컬 JC·Incident 바이너리, 실제 Worker/NAT/공식 MCP 1.4.2. Grafana 응답·LLM은 fixture다. `AGENT_E2E_DATABASE_URL`을 제거해 운영 DB를 사용하지 않았다. PostgreSQL 실행 파일은 기존 검증된 영문 경로, DB·로그는 새 `C:/Users/Public/rca-final-report-<uuid>` 아래에 두고 종료 후 서버를 정리했다. Python `mkdtemp()`의 Windows 제한 ACL은 권한을 낮춘 initdb를 막아 일반 mkdir 방식으로 교체했다. 검증 wrapper는 `.local/verify-rca-final-report.py`, 결과는 `.local/rca-final-report-e2e.xml`에 보존했다.

기존 결과 스키마 1.1·입력 1.3 유지. Backend/JC/Incident/Ops 제품 코드와 SQL은 변경하지 않아 해당 Go 전체 빌드/DB migration 검사는 **해당 없음**이며, 실제 JC 저장·공개와 Ops 인용은 위 연동 검사로 확인했다. 운영 반영에는 새 RCA Worker·Frontend 배포와 새 incident 실행 검수가 필요하다.

## 2026-09-30 Namespace 보고서 실행·표시 개선

기준: main `434006a` 이후 `feat/report-namespace-usability`. [설계서 §0.3](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md)의 후속 개선이다. 운영 배포는 하지 않았다.

- **통과:** macOS arm64/Python 3.11.16/Go 1.26.2/PostgreSQL 16.9/NAT 1.5.0/Grafana MCP 1.4.2/Helm 3.17.3에서 전체 Python **173 passed**, 기존 MCP deprecation warning 3건. 아래 이전 기록의 전체 명령을 동일하게 실행하되 JUnit 경로는 `.local/agent-e2e/report-usability-results.xml`이다.
- **통과:** 실제 Backend POST → JC의 보고서 전용 criteria 1.2 고정 → 실제 Ops Worker/NAT/MCP → 공개 결과·저장 HTML/CSV checksum·Backend HTML 다운로드. 전역 criteria를 바꾸는 테스트 override를 제거했다. 두 Worker·참조·실패 격리 회귀를 함께 확인했다.
- **통과:** LLM 실패 시 성공 응답 0건과 HTTP 시도 3건 구분, 토큰 부족 시 미요청 사유, 기존 수치 보존. 설명 입력의 중복 evidence 참조만 생략하며 저장된 사실/근거는 보존한다.
- **통과:** Backend·JC·Incident에서 `go vet ./...`, `go test -race ./...`, `go build ./...`. Backend의 `go test -tags=e2e ./tests -count=1 -timeout=10m`을 새 임시 PostgreSQL/loopback/테스트 schema에서 실행했다. 정기 보고서의 criteria 1.2·멱등 재전송, RCA의 전용 프로필 거부와 기존 criteria 보존을 확인했다.
- **통과:** Frontend 26 tests·포맷·빌드, Ruff lint/format, chart 계약·배포 도구 검사, 문서 링크·CRLF·diff 검사. 화면 검증 범위는 [Frontend QA](../frontend/QA.md)에 기록했다.
- **해당 없음:** DB migration·새 API·새 의존성·자동 운영 조치·RCA 계산 변경. 공통 LLM 진단 필드 추가는 두 Worker에 적용된다.
- **미수행/미검증:** 이 변경의 운영 배포·실제 Grafana/LLM·정책 조언 품질. E2E 상위 Grafana/LLM은 fixture다. 수집 제한 자체를 없애거나 D08 할당 계약을 확보한 변경이 아니며, 기존 결과는 재계산하지 않는다. 원격 CI 결과는 해당 PR에서 별도 확인한다.

## 2026-09-30 Namespace 관측 보고서 초안

사용자 검토용 초안을 로컬에서 구현·검증했으며 운영 배포는 수행하지 않았다. [Ops README](../ops-agent/README.md)의 criteria 1.2 O08 namespace 초안 범위다. RCA·공통 Python·Backend·Frontend·JC/Helm 제품 코드/설정은 변경하지 않았다.

- **통과:** macOS arm64, Python 3.11.16(지원 범위), Go 1.26.2, PostgreSQL 16.9, NAT 1.5.0, 공식 Grafana MCP 1.4.2, Helm 3.17.3에서 전체 **173 passed**, 기존 MCP client deprecation warning 3건. PostgreSQL/Go/MCP/Helm은 `.local/namespace-tools`에 준비했으며 다운로드 SHA-256을 확인했다.
- **통과:** 고정 입력에서 시간 가중 평균(80%×1시간 + 20%×0.5시간 → 60%), 실제 활동 0%, 같은 GPU의 순차 namespace 사용, 동시 공유, 다른 표본 시각의 유효구간 충돌, 중복 container 관측, Pod UID 재사용/모호성, 활동 부재·부분 관측·단위/범위 오류, MIG instance UUID, 혼합 모델, 다중 클러스터·빈 namespace·미지원 그룹을 검사했다. 연결 시간과 평균에 사용한 GPU-seconds 분모를 구분한다.
- **통과:** 새 테스트 전용 criteria 1.2 JC → 실제 Ops Worker/NAT/MCP → candidate 저장·JC 공개·HTML/CSV checksum 검증. 새 테스트는 독립 DB/schema를 사용하며 기존 RCA·Ops 검사의 전역 criteria를 변경하지 않는다. 최초 검사에서 같은 DB를 쓰던 두 테스트용 JC의 configuration_mismatch를 발견해 fixture를 분리한 뒤 전체 재검사했다.
- **통과:** 기존 criteria 1.1/unconfigured의 조회·O08 계산 유지, 기존 두 Worker·Runbook·실패 격리 회귀, Ruff lint/format, 문서 링크, CRLF 및 `git diff --check`.
- **해당 없음:** 새 API·DB migration·런타임 의존성·제품 설정 변경. 기존 공유 `gpu_intervals()`는 변경하지 않았으며 namespace 계산은 Ops 안에서 기존 구간/신원 함수를 재사용한다.
- **미수행/미검증:** 실제 Grafana/할당 의미·운영 LLM·실제 화면/Backend 다운로드 확인, 보고서 전용 criteria 활성화, 운영 배포·원격 CI. 상위 Grafana 응답과 LLM 응답은 fixture이며 정책 조언·회수량·실제 namespace 소비량은 검증/산출하지 않는다. 기본 전역 criteria는 unconfigured이므로 이 초안이 자동 활성화되지 않는다.

저장소 루트에서 `.venv/bin/ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`, `.venv/bin/ruff format --check`에 같은 경로, `.venv/bin/python tools/check_links.py`, `git diff --check`를 실행했다. 전체 검사 명령은 다음과 같다. 새 임시 DB/data directory·무작위 localhost 포트만 사용하고 종료 후 테스트가 만든 서비스를 정리했다.

```bash
env -u DATABASE_URL -u AGENT_E2E_DATABASE_URL \
  RUN_AGENT_E2E=1 \
  PG_BIN="$PWD/.local/namespace-tools/postgres/bin" \
  JC_BINARY="$PWD/.local/job-controller" \
  INCIDENT_BINARY="$PWD/.local/incident" \
  BACKEND_BINARY="$PWD/.local/backend-e2e" \
  GRAFANA_MCP_BINARY="$PWD/.local/namespace-tools/mcp/mcp-grafana" \
  HELM_BINARY="$PWD/.local/namespace-tools/helm/darwin-arm64/helm" \
  .venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q \
  --junitxml=.local/agent-e2e/namespace-results.xml
```

## 2026-09-29 Fleet JSON 조회 범위·Loki 응답 분할

- **통과:** Python 전체 **149 passed**, 기존 MCP client deprecation warning 3건. 실제 격리 PostgreSQL 16.9·Backend/JC/Incident·RCA/Ops Worker·NAT 1.5.0·공식 Grafana MCP 1.4.2 프로세스로 수집부터 결과 저장·공개까지 검사했다. 이 E2E의 Grafana/Loki HTTP와 LLM 응답은 fixture다.
- **통과:** D05/D09가 Fleet JSON의 노드·컴포넌트를 필터링하며 cluster/namespace·값 escaping을 유지한다. 알림 component를 장비 식별이나 검증된 사실에 넣지 않고, 원본 claim·Incident snapshot을 보존한다. 기존 native label 조회·Prometheus·Ops 경로도 검사했다.
- **통과:** 큰 Loki 응답을 동일 조건의 짧은 시간 구간으로 재조회하여 로그와 연속된 기간을 보존했다. 재조회는 예산을 소모하며 최소 구간 초과 응답은 partial, 예산 소진 뒤 남은 전체 기간은 unavailable로 남긴다.
- **통과:** 별도 수동 검증에서 체크섬을 확인한 공식 Loki **3.7.8**(revision `09e6ce2f`, macOS arm64)을 임시 로컬 저장소·loopback에 실행했다. 실제 수집기가 만든 D05/D09 쿼리는 기존 stream label·structured metadata의 임시 별칭 및 `_extracted` 이름이 충돌해도 JSON 값이 맞는 로그만 반환했다. 잘못된 노드·누락 필드는 제외되고 JSON 조건 없는 native D09는 원래 9건을 유지했다. 이 검증도 입력 로그는 합성 자료이며 운영 로그가 아니다. 종료 후 Loki 프로세스를 정리했다.
- **통과:** Ruff lint/format, Helm chart 계약 검사, 배포 도구 단위 검사, 설정 원본·Helm 미러 일치, 문서 링크, CRLF 및 `git diff --check`.
- **해당 없음:** 새 런타임 의존성, DB migration, 건강 상태 의미 규칙 변경. 기본 프로필은 `builtin-grafana-v2`, D05/D09는 `builtin-v2`이며 명시적 프로필 override는 별도 반영이 필요하다.
- **미수행/미검증:** 운영 배포·실제 Grafana/Fleet 관측과 RCA 품질·이 커밋의 원격 CI. 운영 반영은 main CI 발행 이후 담당자가 새 차트로 업그레이드하고 새 알림의 query/evidence를 확인해야 한다. producer/binding/freshness 계약 부족과 잘못된 시각을 이번 변경이 해결했다고 간주하지 않는다.

전체 Python 검사는 저장소 루트에서 `DATABASE_URL`·`AGENT_E2E_DATABASE_URL`을 제거한 뒤 `RUN_AGENT_E2E=1`, 로컬 `PG_BIN`·`JC_BINARY`·`INCIDENT_BINARY`·`BACKEND_BINARY`·`GRAFANA_MCP_BINARY`를 지정해 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --junitxml=.local/agent-e2e/fleet-results.xml`로 실행했다. 별도 Loki 수동 검증 명령은 같은 루트에서 `.venv/bin/python /tmp/gpu-loki-query-validation/validate.py`였으며, 해당 임시 검수 스크립트는 저장소나 CI 의존성에 추가하지 않았다.

## 2026-09-29 Loki 조회 한도·MCP 오류 보존

- **통과:** macOS arm64, Python 3.12.14, PostgreSQL 16.9, Go 1.26.2, 공식 Grafana MCP 1.4.2, NAT 1.5.0에서 전체 **134 passed**, 기존 MCP client deprecation warning 3건. RCA·Ops 공통 수집기와 두 Worker의 결과 저장·JC 공개 회귀를 포함한다.
- **수정 전 재현:** 실제 NAT와 공식 MCP에 `limit=5000`을 보내면 fixture Loki HTTP 서버에는 5001건 요청이 전달됐다. 서버가 기본 한도 5000건을 적용해 HTTP 400을 반환하면 NAT가 오류 문자열로 변환하고 기존 수집기에서 `JSONDecodeError`가 발생했다. 새 통합 테스트가 수정 전에 실패하는 것을 확인했다.
- **수정 후 통과:** MCP 요청을 최대 4999건으로 제한하여 추가 확인 한 건까지 5000건 이내로 유지한다. D05/D09 조회 및 기존 RCA·보고서 Worker 통합 경로가 통과했다. 더 큰 Agent 행 예산, 최소 요청, D13, Prometheus 오류 격리도 단위 검사했다.
- **통과:** 행 수 제한 또는 `metadata.resultsTruncated`가 있으면 `partial / complete=false`를 보존한다. MCP 오류·비JSON 응답은 `query_failed`와 고정된 안전 오류 코드로 기록하며, 수집기 증거·진단 로그에 원문 오류와 시험용 비밀 문자열이 남지 않는지 확인했다.
- **통과:** Ruff lint/format, 문서 링크 검사, `git diff --check`.
- **해당 없음:** 새 의존성, DB migration, 배포 설정 변경. 공통 Python 코드가 포함된 RCA·Ops 이미지 갱신이 필요하다.
- **미수행/미검증:** 운영 서버 재현·배포·실제 Grafana/Loki 쿼리·LLM 분석 품질·원격 CI. 운영 서버 SSH 연결은 시간 초과됐다. 이번 검증의 Grafana/Loki HTTP 응답과 LLM 응답은 fixture이며 운영 장애의 상위 원인이 동일하다는 확정 근거는 아니다.

저장소 루트에서 `DATABASE_URL`과 `AGENT_E2E_DATABASE_URL`을 제거하고 `RUN_AGENT_E2E=1`, 작업 폴더에 설치한 `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `BACKEND_BINARY`, `GRAFANA_MCP_BINARY`를 지정하여 `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests -q --junitxml=.local/agent-e2e/results.xml`을 실행했다. fixture가 새 로컬 PostgreSQL 데이터 디렉터리·무작위 포트를 만들고 종료 후 정리했다. 운영 DB에는 접근하지 않았다.

## 2026-09-28 전체 XID/SXID 콘텐츠·폴더 분리·일괄 등록

- **통과:** 전체 **106 passed(일반 97 + E2E 9)**, 기존 MCP client deprecation warning 3건. 아래 103건 이후 전체 코드 콘텐츠와 일괄 등록 검사를 추가했다.
- **통과:** XID 173건·SXID 93건·일반 1건의 구조/등록 쿼리 검증, 기존 Fleet 카탈로그 264개 코드 포함 여부, manifest/파일 일치, 코드별 정확한 검색, 문헌 충돌·미정의 코드 보존.
- **통과:** 격리 PostgreSQL과 실제 Backend에 신규 263건을 `python -m rcca_agent.runbook_import`로 draft 등록하고 코드별 조회/hash를 확인했다. 같은 입력·batch key·receipts로 재실행하면 263건 모두 건너뛰며 새로 등록하지 않는다. 기본 변경 요청 한도의 429 대기·재시도도 실제 실행했다.
- **통과:** 기존 대표 3건의 검토·발행·RCA 소비와 두 Worker의 회귀 E2E. 별도 일반 검사에서 변경된 입력/receipt 불일치, 잘못된 형식·revision ID와 HTTP 재시도 시 동일 요청 키 보존을 검사했다.
- **통과:** Ruff lint/format, 문서 링크, diff 공백 검사. 전체 사전 검사 명령은 `python -m rcca_agent.runbook_import rcca-agent/runbooks --profile agents/config.example.json --dry-run`이며 결과는 267건 유효·쓰기 0건이다.
- **해당 없음:** DB migration·배포 설정 변경. 기존 Knowledge API/DB 계약을 사용한다.
- **미수행/미검증:** 운영 DB 등록·발행·배포, 실제 Fleet parser/버전·Grafana 쿼리·LLM 분석 품질. 266개 오류의 운영 RCA 정확도를 검증한 결과가 아니다. 모든 JSON은 빈 compatibility의 조사용 초안이다.

저장소 루트의 Python 3.12 환경에서 `RUN_AGENT_E2E=1`과 실제 Backend/JC/Incident/MCP/Helm 바이너리를 지정해 `python -m pytest -c agents/pytest.ini agents/tests -q`를 실행했다. 새로운 격리 PostgreSQL과 Windows ASCII scratch 경로를 사용하고 종료했다. Grafana 데이터와 모델 응답은 fixture다. 다른 PC의 설치·실행 절차는 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md), 전체 파일은 [CATALOG](../rcca-agent/runbooks/CATALOG.md)를 따른다.

## 2026-09-28 XID/SXID DB 등록·발행·RCA 소비

최신 전체 결과는 **103 passed(일반 94 + E2E 9)**, 기존 MCP client deprecation warning 3건이다. 아래 102건 검증 이후 등록 생명주기 E2E를 추가했다.

- **통과:** 실제 Backend API로 오류별 JSON 3건의 draft 등록, 같은 키 재전송, 빈 compatibility 승인 거부, fixture cluster 조건을 부여한 새 revision, 명시적 검토·발행, XID/SXID namespace 검색, 실제 RCA Worker/NAT/MCP·Synthesis 소비, 원인 supported 승격 방지, retire 후 신규 검색 제외.
- **통과:** 기존 Incident webhook·일반 조사·보고서 소비·실패 격리 회귀를 포함한 전체 검사. 위 신규 사례의 사건 입력은 fixture이고 실제 webhook 검사는 별도 사례다.
- **통과:** Ruff lint/format, 문서 링크(93개 문서·831개 링크/자산), diff 공백 검사, Helm chart 계약 및 CI 계약 unit test 3건. Windows chart 검사는 HELM_BINARY에 helm.exe 절대 경로를 지정했다.
- **미검증:** 실제 Fleet parser·대상/버전/freshness·토폴로지, 운영 Grafana 쿼리·LLM 품질, 운영 DB 발행·배포. 저장소 JSON은 빈 compatibility의 조사용 초안이며 원인 판정용이 아니다.

실행은 저장소 루트의 Python 3.12 환경에서 `RUN_AGENT_E2E=1`과 실제 Backend/JC/Incident/MCP 바이너리로 `python -m pytest -c agents/pytest.ini agents/tests -q`를 수행했다. 격리 PostgreSQL과 Windows ASCII scratch 경로를 사용했다. Grafana 데이터·모델 응답은 fixture다. Backend 바이너리 빌드를 CI와 Windows test.ps1에 추가했으며 별도 Backend 검사 결과는 [Backend QA](../backend/QA.md), 다른 PC의 등록 명령은 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)를 따른다.

## 2026-09-28 Runbook 콘텐츠 연계 후속 검증 (DB 연계 이전)

일반 조사 `RB-GENERAL-GPU-NODE`와 `RB-SXID-11001`을 추가해 작성 초안이 4건이다. `investigation_only` 일반 계획을 원인 판정·fast path 근거에서 제외하고, 선택된 Runbook의 revision·적용 상태·analysis_guidance·limitations를 Synthesis에 전달했다.

PR 준비 최종 재검증: **전체 102 passed(일반 94 + E2E 8)**, 기존 MCP client deprecation warning 3건. 아래 101건 및 94건 분리 실행 이후 같은 격리 환경에서 전체를 다시 실행했다. 원격 CI 성공을 의미하지 않는다.

- **통과:** 전체 실행 101건(일반 검사 93 + 실제 프로세스 E2E 8). 일반 JSON에 격리 테스트 cluster 호환성만 부여해 DB에 발행한 뒤 실제 JC/Worker/NAT/MCP 수집·Synthesis 요청·저장·보고서 인용을 검증했다. Grafana 데이터와 LLM 응답은 fixture다.
- **통과:** 추가한 일반 Runbook 표시 누락 방어를 포함한 RCA 분석 검사 13건, 최종 일반 검사 재실행 94건. Xid/SXid JSON의 검색·수집 계획 소비 및 오류 코드 fact 미확인 시 candidate 유지, 잘못된 일반 판정 콘텐츠 거부를 확인했다. 운영 producer/parser 검증은 아니다.
- **통과:** Ruff lint/format, 문서 링크, diff 공백 검사. 실행 명령과 격리 환경은 아래 실행부 검증과 같으며 단위 검사에는 `--basetemp=.local/pytest-runbooks`를 사용했다.
- **미검증/미수행:** 실제 Fleet 로그 parser·대상/버전/freshness 계약, 당시 Backend 발행 단계의 v1 validator 연결(위 후속 검사에서 완료), 운영 발행·LLM 연결·배포. 네 초안의 빈 compatibility는 운영 실행을 차단한다. GPU reset·재부팅·진단 도구 실행은 하지 않았다.

세부 작성·실행 계약은 [Runbook README](../rcca-agent/runbooks/README.md)에 기록했다. 새 DB 구조나 운영 설정 변경은 없다.

## 2026-09-28 RCA 병렬 조사·Synthesis 구현 검증

로컬 파일 개발 단계다. [보완 계획](../docs/specs/rca-agent/implementation-plan-20260928.md)의 입력 1.3 실행부를 구현했다. 실제 LLM endpoint 연결, 운영 Runbook 발행, 배포는 수행하지 않았다.

| 검사 | 결과·검증 범위 |
|---|---|
| 단위/Worker + 실제 프로세스 E2E | **99 passed**: 일반 검사 91개 + E2E 8개. Python 3.12.14 / NAT 1.5.0 / 공식 Grafana MCP 1.4.2 / PostgreSQL 16.9 |
| 수집·분석 | 기존 근거 충분 시 MCP·LLM 0회, 승인 일반 Runbook 대체, 발행본 없음→조회 0회, 병렬 수집·예산 예약·실패 격리·취소 회수, 최대 1회 재조사, 도구 없는 최종 Synthesis |
| 모델 경계 | 없는 근거 참조·추가 query·인과 수준 필드·숫자 claim 거부. 잘못된 계획/분석 응답의 근거 보존, endpoint 미구성 표시, 원격 종료 불명의 Worker 격리 경로 |
| 입력·저장·보고서 | 실제 Incident webhook→JC→RCA Worker→NAT/MCP→DB candidate→JC 공개. 원문/hash와 provider action 미수행 보존. 공개 RCA ID/hash의 보고서 인용 및 기존 에너지 계산·실패 격리 회귀 |
| MCP 시간 정밀도 | 실제 webhook 마이크로초 시각으로 Loki parser 실패를 재현한 뒤 공통 시간 변환으로 해결. 조회창 확장 없이 밀리초 경계 사용, 줄어든 구간은 `time_precision_reduced`/partial 기록. 두 Worker 공통 경로 검사 |
| 정적/배포 검사 | Ruff lint·format, 문서 링크, `tools/ci/check_chart.py`(Helm 3.17.3), CI 계약 unit test 3개 통과 |
| 미검증 | 운영 Grafana/Mimir/Loki 쿼리 평가·인증·producer 의미, 실제 모델 품질, Fleet 오류 fact parser·binding·freshness, 입력 1.4 목적 자동 선택·이력 고정, 운영 배포 |

저장소 루트의 Python 3.12 venv에서 `python -m pytest -c agents/pytest.ini agents/tests -q`를 실행했다. `RUN_AGENT_E2E=1`, 실제 JC/Incident/MCP 바이너리, 검증한 Helm 3.17.3을 지정했다. Windows 한글 경로의 PostgreSQL 초기화 문제 때문에 테스트의 `LOCAL` scratch 경로만 ASCII 임시 폴더로 바꾼 로컬 runner를 사용했다. 매 실행 새로운 data directory와 무작위 localhost 포트를 사용하고 종료했다. 운영 DB 환경변수는 재사용하지 않았다.

Grafana datasource HTTP 응답과 모델 응답은 fixture다. 일반 Runbook은 격리 DB에만 넣은 계약 fixture이며 운영 콘텐츠가 아니다. MCP Host 보호 회귀 3건도 실제 바이너리로 통과했다. 기존 MCP Python client의 deprecation warning 3건은 남아 있으며 실행 실패는 아니다. Incident Go 검증은 [Incident QA](../incident/QA.md)를 따른다.

Ruff 명령은 `ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`, `ruff format --check`에 같은 경로를 사용했다. 문서/차트/CI 검사 명령은 `python tools/check_links.py`, `python tools/ci/check_chart.py`, `python -m unittest discover -s tools/ci/tests -v`다. 최종 전체 실행 로그/XML은 로컬 `.local/rca-e2e-results.xml`에 보관한다.

## 2026-09-18 Incident → RCA 계약 회귀 검증

실제 Incident는 `snapshot.alert`를 저장하지만 RCA가 `snapshot.evidence`만 읽어 실패하던 문제를 수정했습니다. 새 회귀 테스트를 먼저 추가해 수정 전 실제 웹훅 경로의 RCA 작업이 `failed`가 되는 것을 재현했습니다. 수정 후에는 snapshot을 변경하지 않고 `alert`를 읽으며 legacy `evidence`도 지원합니다. 원본 알람 필드를 검증된 사실로 승격하지 않습니다.

- 단위/Worker 테스트 29개와 실제 프로세스 E2E 5개, 총 **34 passed**.
- 새 경로: Grafana 형식 HTTP webhook → 실제 Incident 저장/outbox → 실제 JC → 실제 RCA Worker/NAT/공식 Grafana MCP → 결과 저장/JC `succeeded`.
- 이 회귀 테스트는 Incident snapshot이나 RCA job을 DB에 직접 삽입하지 않습니다. Incident가 생성한 R01/R02 목적, 원본 alert, evidence snapshot과 hash 보존을 확인합니다.
- 별도 프로필 없이 datasource 자동 탐색, 기존 legacy snapshot·Runbook·보고서·실패 격리 경로도 통과했습니다.
- Ruff lint/format, actionlint, 문서 링크 검사를 통과했습니다. CI와 Windows 테스트 스크립트에 실제 Incident 바이너리 빌드를 추가했습니다.

Windows 로컬 PostgreSQL 초기화는 샌드박스의 restricted-token 오류 때문에 일반 사용자 권한에서 격리된 테스트 DB로 실행했습니다. Grafana/Mimir/Loki와 LLM 응답은 fixture이며 운영 연결이나 실제 모델 품질을 검증한 것은 아닙니다. 아래 2026-09-17 기록의 RCA snapshot 테스트는 DB에 직접 넣은 fixture였으며 실제 Incident 생산 형식을 검사하지 못했습니다.

## 이전 검증 기록

검증일: 2026-09-17, Windows, Python 3.12.14, NAT 1.5.0, 공식 Grafana MCP 1.4.2, PostgreSQL 16.9, 저장소의 실제 Go Job Controller.

## 실행 결과

| 검사 | 결과 |
| --- | --- |
| 최소 단위/Worker 테스트 | 8 passed |
| 실제 프로세스 E2E | 3 passed |
| Ruff 정적 검사 | 통과 |
| Python compile/모듈 import | 통과 |
| Docker Compose 구성 구문 검사 | 통과 (`config --no-env-resolution -q`) |
| 공식 MCP Windows 릴리스 SHA-256 | 검증 |
| 공식 Docker 이미지 `grafana/mcp-grafana:1.4.2` 태그 | 존재 확인 |
| Linux Docker build/up | NOT RUN — 사용자 안내에 따라 Windows 프로세스로 대체 |
| 운영 Grafana/Mimir/Loki·실제 LLM endpoint | NOT RUN — 해당 연결 정보/키가 제공되지 않음 |

## 최소 테스트

- 전용 할당 합집합 중복 제거, 공동 유효 구간 교집합.
- 58분 공동 관측/54분 저활동 고정 사례, 5분 할당·30분 Pod 교체 후보 보류.
- 시간 가중 평균/P95, 좌측 유지 전력 적분, 공백·중복 충돌 처리.
- 검사 불가+Healthy → unknown, Go JSON 호환 hash, reasoning tag 제거.
- 호환성 제한 후 최신 Runbook 선택.
- 주제별 ready/partial/blocked 집계, HTML escape·CSV 수식 방어.
- 실제 LLM 요청 형식 및 timeout 시 원격 종료 unknown.
- scope escaping·등록 query ID·조회 예산·기간 범위 제한.
- 비동기 heartbeat 중 취소, 미종료 LLM unknown 보고, 저장 실패 시 complete 미호출.

## E2E 경로와 단언

실제 구성: 테스트 전용 PostgreSQL → **실제 JC HTTP API** → **별도 Worker 프로세스** → **NAT workflow/MCP client** → **공식 Grafana MCP Windows 서버**.

Grafana datasource HTTP 응답과 OpenAI 호환 LLM endpoint만 고정 데이터 서버로 대체했습니다. 따라서 실제 Mimir/Loki 엔진의 쿼리 평가·운영 인증·실제 모델의 진단 품질을 검증했다는 의미는 아닙니다.

1. Incident snapshot → RCA claim → Loki 로그 조회 → LLM의 등록 D02 선택 → Mimir 호환 원본 표본 조회 → 상태 정규화·후보 저장 → JC complete. 이어 보고서가 공개된 RCA ID/hash를 인용하고 GPU 전력 250W×1시간=0.25kWh를 산출합니다. DB 저장 본문 hash, HTML/CSV 파일 checksum을 확인합니다.
2. LLM 503 + Loki 실패 시에도 O09 에너지 0.25kWh를 보존합니다. O10은 blocked, 설명은 failed이며 독립 주제를 지우지 않고 JC가 결과를 발행합니다.
3. O01~O11 전체 결과가 주제별 상태를 유지합니다. 호환 발행 Runbook의 필수 증거가 이미 충분한 R01은 추가 MCP 조회 없이 조건·권고를 평가하고 supported 후보를 발행합니다.

실행 명령: `./agents/scripts/test.ps1 -E2E -PgBin ./backend/.local/postgres/bin/bin`

테스트는 임시 포트와 새로운 DB data directory를 사용하며 기존 DB 데이터에 접근하지 않습니다. 이번 테스트의 로그와 보고서 파일은 `.local/agent-e2e/`에 있습니다. 초기 Windows PostgreSQL 관리자 직접 실행/파이프 상속 오류는 `pg_ctl`의 권한 처리와 DEVNULL 출력으로 수정했습니다. 실제 Grafana MCP가 Prometheus query를 form POST로 전송하는 동작도 fixture에 반영했습니다.

## 남은 운영 검수

배포 C02~C07의 실제 datasource UID/CPC 필터/metric 의미/원본 주기/조회 한도, Fleet parser 계약, 할당/작업 신원·완전성, 기대 대상 분모를 설정해야 합니다. 설정이 없는 판단은 null/partial/blocked입니다. 실제 도구 호출 모델 호환성, 실제 GPU 부하·공백·장기 이력과 C08 회복 정책은 운영 표본으로 별도 검수해야 합니다.

## 2026-10-01 Korean RCA prose / 한국어 문장·조회 표기 검증

기준 `origin/main` `529df747173e76a908ff2d56b1ac3688c4a3e648`, 브랜치 `fix/rca-report-korean-labels`. 로컬 파일 변경 단계이며 commit·push·PR·배포 없음.

- **통과:** Python 3.12.14 격리 환경에서 `python -m pytest -c agents/pytest.ini agents/tests -q -rs --ignore=agents/tests/test_gpu_node_scope.py -p no:cacheprovider --basetemp=.local/rca-korean/pytest-final`: **269 passed, 17 skipped**. 두 Worker의 추적 대상 단위·모의 lifecycle 검사와 새 한국어/숫자 단어/일반 단어 오탐/입력 식별자/정밀도 조건/단정/전체 D-query/사전 일치 회귀를 포함한다. `synthesize()`에 실제 전달되는 query_quality도 모의 모델로 검사했다.
- **실패(기존 사용자 파일):** 전체 `agents/tests` 실행에서 작업 시작 전부터 존재한 미추적 `test_gpu_node_scope.py`의 2건이 실패한다. `gpu-node-rca-v1` 및 `gpu_node`를 기대하지만 현재 기준 코드 값은 `gpu-alert-v1`·`gpu_access`다. 해당 파일과 정책·procedure를 수정하지 않았다. 전체 검사를 통과로 표시하지 않는다.
- **통과:** CI 범위 `ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci` (ruff 0.14.0). **실패:** 같은 범위 `ruff format --check`는 기존 미추적 `test_gpu_node_scope.py` 1파일 때문에 실패. 이 파일을 제외한 66파일은 통과했다.
- **통과:** 운영 작업 `ed730b4d`, `1e48ed0f`, `e24b3f20`의 해당 발행 시도 evidence와 result body를 `default_transaction_read_only=on`, `SHOW transaction_read_only=on`으로 읽고 로컬 보고서를 재생성했다. D02/D05/D06/D08/D09를 모두 표시하고 D06은 5개 구간으로 묶으며 표본 합산이 없다. 구 작업의 D05/D09는 정밀도 partial, 새 두 작업은 ok, D08은 모두 empty다. DB 변경·모델 재호출은 없다.
- **통과:** 저장된 문장 재검증에서 `1e48ed0f`의 영어 후보 2개는 `non_korean_claim`, 영어 한계 6개는 `invalid_limitations`; `e24b3f20` 후보 2개는 숫자 단어 제한, 영어 한계 4개는 `invalid_limitations`로 거부했다. 원래 모델 응답/view는 저장되지 않아 저장 문자열 재현 범위이며 당시 모델 품질 전체 검증이 아니다. 운영 원문 비교표는 Git 제외 로컬 `.local/rca-korean/production-comparison.md`에만 보존한다.
- **미수행/미검증:** Go 실행 파일이 없으며 공식 MCP·격리 PostgreSQL/JC·Helm 준비가 없어 17개 실프로세스 E2E가 건너뛰어졌다. 실제 LLM/Grafana 새 실행, 운영 배포 후 표시·언어 품질, 원격 CI는 미검증이다. Docker는 사용하지 않았다. mock lifecycle와 읽기 전용 저장 결과 재현을 실환경 새 실행으로 해석하지 않는다.
- **해당 없음:** Go 코드·DB migration·Fleet 시각 계약·충분성 gate·R01/R02 `REQUIRED`·결과 스키마 변경. 기존 결과는 재작성하지 않는다.

- **문서 검사:** 전체 `python tools/check_links.py`는 기존 미추적 `_review_current/`·`_codex_dcgm_publish/` 안의 경로 7건으로 실패했다. 두 기존 검토용 폴더만 제외해 같은 `check()`를 실행하면 변경 문서를 포함한 링크 검사는 통과한다. 이 폴더들은 수정하지 않았다.

## 2026-10-01 ci.110 후속 수정 — 로컬 검증

- `ruff check` / `ruff format --check`: 통과. 일반 pytest 284 passed, 17 skipped. 이후 격리 PostgreSQL 16.9(127.0.0.1:55432) + 실제 Incident/JC/두 worker + 공식 Grafana MCP 1.4.2 프로세스로 전체 실행: 299 passed, Helm 경로 누락 2 failed. `HELM_BINARY` 설정 후 실패한 두 사례만 재실행: 2 passed. 서로 다른 301개 사례 모두 통과, 남은 skip 없음. Grafana·LLM 응답은 fixture이며 운영 모델 품질 검증이 아니다.
- `python tools/ci/check_chart.py`: 실제 Helm 3.17.3 lint/template/package 계약 통과. `python -m unittest discover -s tools/ci/tests -v`: Git Bash 경로 설정 후 5 passed.
- 저장된 9684a61e 증거의 로컬 재생: 62개 장비 관측 → 고유 31개, Loki 호출 1회, gpu_pod → gpu_access. 고정 모델 응답 fixture에서 synthesis complete; 실제 실패 원문은 미보관이라 원인 문장 재현/운영 모델 성공을 입증하지 않는다. `partial/missing_data`와 R01/R02 partial 유지.
- 실제 사건 구간 D02에는 GPU UUID/node는 있지만 Pod·namespace 라벨이 없다. D08을 DCGM으로 바꾸어도 해당 사건의 Pod를 확정할 수 없다. inventory 로그도 장비 사건 시각·freshness 계약이 없어 신원 후보로만 보존한다.
- `DCGM_FI_DEV_XID_ERRORS`의 해당 구간 가용성은 미검증. 기본 D05는 D09 파생 보기를 사용한다. 전역 metric 부재나 모든 GPUAlert의 R01/R02 충족 불가를 주장하지 않는다.
- 운영 배포·동일 incident의 운영 재실행·실제 모델 품질 검증은 미실행. 과거 evidence/result와 hash는 변경하지 않았다.
