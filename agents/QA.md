# Agent 검증 기록

## 2026-09-30 Fleet RCA 파이프라인 후속 검증

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
