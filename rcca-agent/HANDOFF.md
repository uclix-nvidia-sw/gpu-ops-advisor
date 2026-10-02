# RCA·Runbook 개발 인수인계

## 2026-09-30 후속 반영

시간 정밀도 partial의 개별 관측 사용, degraded 후속 query, Fleet JSON adapter, Incident target 투영/중복 호환, R02/R03 D08/D06 계획을 함께 반영했다. 구현 계약과 남은 운영 검수는 [RCA README](README.md#2026-09-30-fleet-rca-수집분석-보완), 검증 결과는 [Agent QA](../agents/QA.md)를 따른다. 기본 Fleet 설정은 로그 보고만 해석하며 현재 장비 상태/조치 조건을 확정하지 않는다. 기존 결과 재작성과 운영 배포는 포함하지 않는다.

## 2026-09-30 추가 인수인계: 최종 보고서

`report.py`와 workflow 마지막 단계에 다섯 섹션의 최종 보고서를 추가했다. 원인 Synthesis와 별개로 모델 편집을 시도하며, 기존 `explain()`의 문장 ID 선택을 사용한다. 모델 미설정/확정 실패에도 기본 보고서를 남기고 원격 종료 불명은 격리한다. `narrative`/`narrative_status`와 `quality.report`로 표시하며 assessment·원인 수준·권고 적격성은 그대로다. RCA 화면도 이 보고서를 표시한다.

아래 2026-09-28 검증 수치는 당시 기록이다. 이번 변경의 명령·검증 범위·미검증 항목은 [Agent QA](../agents/QA.md)와 [Frontend QA](../frontend/QA.md)를 따른다. 운영 배포·실제 Fleet/LLM 품질 검수·기존 작업 재분석은 별도이며 이 변경으로 완료됐다고 해석하지 않는다.

기록일: 2026-09-28. 이 문서는 다른 PC의 개발자·Codex·Claude가 대화 기록 없이 작업을 이어가기 위한 진입점이다. 저장소 루트의 [AGENTS.md](../AGENTS.md), [CLAUDE.md](../CLAUDE.md)와 해당 scoped rule을 먼저 따른다.

## 현재 단계

**로컬 구현·검증 완료, 원격 반영·CI·CSC 배포·운영 검증 미완료** 상태에서 작성했다. 읽는 시점의 실제 상태는 `git status --short`, `git log -5 --oneline`과 원격 CI로 다시 확인한다. 이 문서의 작성이 commit/push/배포를 뜻하지 않는다. 새 파일도 함께 커밋·push되어야 다른 PC에서 받을 수 있다.

이번 범위는 기존 **입력 1.3** RCA 실행부와 Runbook 작성 초안이다. 결과 본문 스키마 1.1과 기존 Worker/JC 저장·공개 계약을 유지한다. 운영 DB migration·자동 Runbook seed·하드웨어 조치 기능은 추가하지 않았다.

후속 XID/SXID 작업: 오류별 3건의 지침·출처, Backend v1 구조 검증/코드 검색, 등록 CLI를 추가했다. 기존 `knowledge_revisions` 구조로 격리 DB 등록·검토·발행·RCA 소비를 검증했다. [DB 등록 안내](runbooks/DB-WORKFLOW.md)에 필드 대응·명령·검토 책임을 기록했다. 이전 RCA PR과 별개로 이 후속 작업은 로컬 변경 단계이며 운영 DB에는 적재하지 않았다. 다른 세션과의 조율은 사용자 지시로 중단했다.

최신 콘텐츠 확장: 기존 대표 3건에서 **XID 173건·SXID 93건 + 일반 1건 = 267건**으로 늘렸다. 자료 범위의 코드별 작성은 완료했으며 미정의/Unused·정의 충돌·소스만 있는 항목은 명시적으로 구분했다. [전체 목록](runbooks/CATALOG.md)과 manifest를 먼저 확인한다. 실제 환경 query/parser·compatibility 및 운영 DB 발행은 남아 있다.

최신 파일 정리: XID/SXID JSON을 각각 runbooks/xid, runbooks/sxid로 이동했다. knowledge_key와 DB 계약은 유지한다. [일괄 등록 CLI](src/rcca_agent/runbook_import.py)가 전체 사전 검사·API draft 등록·응답 저장·중단 후 재개·429 대기를 제공한다. 공통 개발 설명은 JSON에서 문서로 옮겼다.

## 먼저 읽을 문서

| 순서 | 문서 | 확인할 내용 |
|---|---|---|
| 1 | [보완 계획·결정 기록](../docs/specs/rca-agent/implementation-plan-20260928.md) | 첨부 제안 중 채택·보류한 항목, 예산·재조사·DB 결정 |
| 2 | [RCA 설계서](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md) §2.4·§2.5 | 현재 동작·한계와 workflow. §0의 과거 gap 표를 최신 상태로 오인하지 않음 |
| 3 | [Runbook 계약과 콘텐츠](runbooks/README.md) | JSON 형식, 초안·검토·발행 경계, 필요한 parser/binding |
| 4 | [Agent QA](../agents/QA.md), [Incident QA](../incident/QA.md) | 실제 실행한 검사, fixture 경계, 미검증 범위 |
| 5 | [두 Worker 실행 안내](../agents/README.md) | 설치·환경변수·MCP·LLM·timeout/격리 |

사용자가 제공한 로컬 첨부 3건의 채택 결정은 보완 계획에 옮겼다. Downloads나 이전 채팅 첨부에 접근하지 않아도 이번 결정과 남은 일을 확인할 수 있다. 기술 출처는 Runbook JSON의 `content.sources`와 설계서의 `references/`에 있으며 실제 환경의 producer 의미는 별도 검증 대상이다.

## 구현한 내용과 코드 위치

| 내용 | 코드·검사 |
|---|---|
| Runbook 검색·조건·계획·충분성·종료 | [workflow.py](src/rcca_agent/workflow.py), [retrieval.py](src/rcca_agent/retrieval.py) |
| query별 독립 관측 task, 사전 예산 배정, 실패 격리·취소 회수 | [observation_agents.py](src/rcca_agent/observation_agents.py), [병렬 테스트](../agents/tests/test_rca_parallel.py) |
| 최종 LLM 해석·참조 검증, 계획 지침 전달 | [synthesis.py](src/rcca_agent/synthesis.py), [prompts.py](src/rcca_agent/prompts.py), [분석 테스트](../agents/tests/test_rca_analysis.py) |
| reason/component·Xid/SXid·suggested_actions 단서 | [incident.py](src/rcca_agent/incident.py). 원문 보존, 검색 단서와 검증된 사실 분리, 권고 미수행 |
| Runbook v1 검증·호환성 | [runbook_contract.py](src/rcca_agent/runbook_contract.py), [계약 테스트](../agents/tests/test_runbook_contract.py) |
| DB 등록·검토·발행 및 검색 | [관리 CLI](src/rcca_agent/runbook_admin.py), [Backend 검증기](../backend/internal/api/runbook.go), [Knowledge API](../backend/internal/api/knowledge.go) |
| 실제 Worker/NAT/MCP·DB·JC·보고서 연결 | [E2E 테스트](../agents/tests/test_e2e.py) |
| Loki/Prometheus 요청 시각 변환 | [grafana_time.py](../shared/python/src/agent_common/grafana_time.py), 공통 discovery/observation. 두 Worker에 영향. 원문 시각 보존·조회 범위 확장 금지·Loki 정밀도 손실은 partial |
| Incident 1.4 node 라벨/annotation 수신·충돌 거부 | [episodes.go](../incident/service/episodes.go), service/tests의 회귀 검사. RCA Worker의 1.4 지원을 의미하지 않음 |
| 설정 | [원본 프로필](../agents/config.example.json), [Helm 미러](../charts/gpu-ops-advisor/files/agents.json). `rca.general_runbook_key`, `limits.max_concurrency` |

실행은 **JC claim → Runbook 조회·코드 검사 → 기존 근거 충분 시 수집·원인 Synthesis 생략 / 부족 시 승인 계획의 병렬 수집 → 코드 충분성·최대 1회 재조사 → 도구 없는 Synthesis → 코드 검증 → DB evidence/candidate → JC 공개**다.

멀티 에이전트는 하나의 NAT workflow·프로세스·JC lease 안의 역할 분리다. Observation은 query별 수집 작업이다. GPU·네트워크·워크로드별 독립 LLM 전문 에이전트나 분산 서비스는 아직 없다. Synthesis의 모델 후보는 candidate이며 참조 검증이 문장 의미의 진실성을 보장하지 않는다.

## Runbook 현재 상태

[일반 조사](runbooks/RB-GENERAL-GPU-NODE.json), [Xid 79](runbooks/xid/RB-XID-79.json), [Xid 48 및 동반 코드](runbooks/xid/RB-XID-48-63-64.json), [SXid 11001](runbooks/sxid/RB-SXID-11001.json) 등 기존 4건에 코드별 263건을 추가해 총 267건이다. **모두 compatibility가 빈 작성 초안이며 운영 실행·발행 완료 상태가 아니다.**

- 현재 모든 초안은 `investigation_only: true`다. 원인 supported/조기 완료의 근거로 쓰지 않고 콘텐츠 recommendations를 최종 eligible 조치로 발행하지 않는다. 승인된 전용·일반 Runbook이 모두 없으면 `approved_runbook` 부족을 기록하고 조회하지 않는다.
- 위 보류는 RCA 작업 접수·시작을 막는다는 뜻이 아니다. JC claim과 사건/Runbook 검토는 수행하며, 승인 계획이 없을 때 MCP 수집·LLM 분석을 생략하고 blocked 결과를 저장·공개한다. 전용 Runbook 미일치는 승인된 일반 계획으로 조사한다.
- Worker는 파일 디렉터리를 자동 읽지 않고 DB의 scope·고정 revision/hash·검토 상태를 검사한다. Helm upgrade는 이 JSON을 DB에 발행하지 않는다.
- 현재 조건식은 등록 문자열 fact의 `field/equals`다. D09/D05는 로그·상태, D02는 보조 사용률 계획이며 `fact_names` 자체가 fact 생성기를 제공하지 않는다.
- Fleet adapter는 Xid/SXid를 관측에 추출한다. 기본 time 계약과 freshness 미등록 상태에서는 error_code fact로 승격하지 않는다. alert reason의 코드는 계속 검색 단서다. 빈 compatibility를 임의 값으로 채우거나 parser 없이 verified_facts로 승격해서 실행을 통과시키지 않는다.
- 선택된 계획의 지침·한계는 pending/applicable 상태와 함께 Synthesis에 전달한다. 일반 조사 또는 조건 미확인의 지침을 원인 근거로 간주하지 않는다.

## 다음 개발 순서와 필요한 입력

1. 실제 Fleet image/source revision과 비밀을 제거한 원본 로그 표본, 대상 식별자·시각·상태 의미를 확보한다. `Fleet 1.5.0-rc.1` 언급만으로 upstream commit이나 로그 계약을 확정하지 않는다.
2. 등록 D-query가 필요한 로그를 수집하는지 확인하고 producer별 parser·대상 binding·freshness를 구현/검증한다. 다른 대상·오래된 시각·미등록 producer·상충·partial/빈 결과의 부정 사례도 검사한다.
3. 환경별 compatibility와 필요한 query를 채워 일반 조사 및 Xid/SXid를 통합 검수한다. Backend 구조 검증·빈 호환성 승인/발행 차단은 구현했다. CLI와 Worker가 실행 프로필의 query를 검사하며 실제 환경 적합성은 운영 검토로 확인한다. 기존 draft → in_review → reviewed → published 절차를 따른다.
4. 사용자가 나중에 제공하기로 한 로컬 LLM endpoint를 연결하고 실제 Grafana 관측으로 분석 품질을 검수한다. endpoint 미구성은 유효 근거를 보존하면서 `synthesis_unconfigured`로 남는다.
5. 입력 1.4의 목적 자동 선택·선택 전 bounded DB 이력·purpose trace·소비자 계약을 구현/검증한다. 그 전에는 RCA Worker가 1.4 지원을 광고하거나 Incident 운영 설정을 전환하지 않는다.

InfiniBand·NVML·NCCL·peermem 콘텐츠와 도메인별 전문 분석 에이전트는 이후 확장이다. 모든 R01~R09 목적이나 복구·영향·토폴로지 판단이 완성된 것은 아니다.

## 다른 PC에서 검사하기

저장소 루트에서 Python 3.12 가상환경을 만들고 활성화한다. [설치 안내](../agents/README.md)와 [.github/workflows/tests.yml](../.github/workflows/tests.yml)의 고정 버전·빌드 명령을 사용한다.

```sh
python -m pip install -r agents/requirements.txt -e shared/python -e rcca-agent -e ops-agent ruff==0.14.0
ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci
ruff format --check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci
python -m pytest -c agents/pytest.ini agents/tests -m "not e2e" -q
python tools/check_links.py
```

E2E는 위 단위 명령에 포함되지 않는다. 별도 테스트 전용 PostgreSQL, Go 1.26.2로 빌드한 Backend/JC/Incident, 공식 Grafana MCP 1.4.2와 Helm 3.17.3을 준비하고 `RUN_AGENT_E2E=1`로 전체 검사를 실행한다. Windows는 [test.ps1](../agents/scripts/test.ps1)의 `-E2E -PgBin` 경로를 사용할 수 있다. `AGENT_E2E_DATABASE_URL`이 설정됐다면 운영/공유 DB가 아닌 격리 테스트 대상인지 먼저 확인한다. Linux의 재현 가능한 구성은 CI workflow를 따른다.

이 PC의 Windows 검증에서는 경로의 대괄호가 Go embed를, 한글이 PostgreSQL initdb를 방해해 임시 소스 복사본·ASCII 테스트 scratch 경로를 사용했다. 다른 PC에서는 ASCII·대괄호 없는 checkout 경로를 권장한다. `.local`의 venv·바이너리·로그·임시 runner와 개인 환경변수는 Git으로 전달되지 않는다. 기존 로컬 경로를 복사하는 대신 고정 의존성을 새로 준비한다.

2026-09-28 당시 검증은 **전체 106건(일반 97 + E2E 9) 통과**다. 신규 263건을 실제 일괄 CLI로 격리 DB에 등록하고, 재실행 시 중복 쓰기 없이 재개되는지 확인했다. 기존 대표 3건의 검토·발행·RCA 소비도 통과했다. Backend vet/race test/build와 DB E2E도 통과했다. 실제 DB/JC/Worker/NAT/MCP를 사용했지만 Grafana 데이터·LLM 응답은 fixture다. 원격 CI·운영 품질 검수 완료를 의미하지 않는다. 자세한 실행 범위는 [Agent QA](../agents/QA.md)를 따른다.

## 원격 반영과 CSC 적용

변경 파일과 새 파일을 함께 검토한 뒤 사용자가 요청한 범위에서 commit/push한다. 이 작업과 무관한 개인 설정·다른 작업 산출물을 섞지 않는다. 원격 main 반영 → 해당 커밋 `CI required` 성공 및 이미지/chart 발행 → CSC의 해당 chart 버전으로 upgrade → 실제 RCA와 보고서 경로 확인 순서다. [CI 안내](../docs/ci-release.md), [기존 설치 업그레이드](../docs/helm-upgrade-existing.md)를 따른다.

CSC의 기존 values·Secret·DB/보고서 PVC 이름을 보존한다. `configuration.agents` override는 객체 전체를 대체하므로 기존 override에 새 설정이 반영됐는지 확인한다. 실제 CSC release/namespace/values/chart 버전은 이 작업에서 확인하지 않았다. 위 Runbook 발행·parser·LLM 조건을 갖추지 않은 코드 업그레이드는 운영 RCA 준비 완료가 아니다.
