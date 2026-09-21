# 팀 규칙 한국어 번역

이 문서는 [.claude/rules/](../.claude/rules/)의 영어 규칙 여섯 개를 한곳에 모은 참고용 번역입니다. [루트 CLAUDE.md](../CLAUDE.md)와 영어 규칙 파일이 원본입니다. 아래 `paths` 코드 블록은 원본의 적용 범위를 보여 주며, 이 번역 문서를 자동으로 불러오는 설정이 아닙니다.

## 작업 흐름과 완료

원본: [workflow.md](../.claude/rules/workflow.md)

모든 작업에 적용합니다. 사람을 위한 설명과 예시는 [팀 협업 가이드](team-development.md)를 참고합니다.

### 작업 범위

- 구현 전에 작업 목표, 허용 범위, 확인 가능한 검수 기준을 확정합니다. 분석만 요청한 경우 구현 권한까지 주어진 것은 아닙니다.
- 브랜치와 작업 트리를 확인하고 기존 변경을 보존합니다. 변경 범위를 집중시키고 기존 구조를 재사용하며, 관련 없는 포맷 변경·이름 변경·추상화·의존성 추가를 피합니다.
- 팀 가이드의 담당 범위와 계약 영향 표를 따릅니다. 영향을 받는 사용 모듈을 검증하고, 모듈 간 영향을 공유하며, 모호한 계약을 확인합니다. 동료 리뷰가 선택 사항이어도 이 조율은 필요합니다.
- 기존 이름 규칙과 주변 문서의 언어를 따릅니다. 코드 식별자와 개발자용 주석은 영어로 작성합니다. UTF-8 CRLF 텍스트를 유지하고 기존 포맷 도구를 사용합니다.
- 동작이나 인터페이스가 바뀌면 가까운 문서를 갱신합니다. 버전이 고정되었거나 생성된 산출물을 함부로 수정하지 않습니다. 생성된 HTML을 직접 편집하지 말고 Archify JSON 원본을 수정한 뒤 HTML을 다시 생성합니다.

### Git과 리뷰

- 현행 정책은 변경 검토, 관련 검사, 사용자 승인 후 main 작업과 직접 push를 허용합니다. 개발 요청만으로 commit, push, PR 생성, merge, 배포가 허용되지는 않습니다. commit만 요청받았다면 로컬 commit 후 멈춥니다.
- 동료 리뷰/Approve는 선택 사항입니다. AI가 작성한 변경을 포함해 작성자가 검증 책임을 집니다. 향후 브랜치·PR 방식은 팀이 전환을 기록하거나 해당 작업에서 PR을 명시적으로 선택한 뒤에만 적용합니다. 현재의 main 작업에 강제하지 않습니다.
- commit 메시지, PR 제목, 핵심 변경 설명에는 영어와 한국어를 함께 사용합니다. 승인된 commit 전에 의도한 파일만 명시적으로 선택하고 staged diff를 검토합니다.
- 승인된 push 전에 최신 원격 상태를 확인합니다. 갈라진 이력을 force push로 덮어쓰거나 저장소 보호 규칙을 우회하지 않습니다. push 후 해당 commit의 실제 CI 상태를 보고하고, 실패를 조사하며, 실패한 산출물을 배포하지 않습니다. PR merge에는 최신 필수 CI 통과가 필요합니다.
- push/merge, 산출물 게시, 배포는 서로 다른 결과입니다. 배포에는 별도 승인이 필요합니다. 브랜치 이름과 명령 예시는 팀 가이드에 있습니다.

## 공통 완료 기준

1. 이 작업의 성공 조건을 정의합니다. 예상 입력, 확인 가능한 출력·상태, 관련 실패 또는 근거 부족 시의 동작을 포함합니다. [docs/README.md](README.md)가 연결하는 현행 계약과 검수 문서를 사용하며, 일률적인 coverage나 분석 정확도 목표를 만들어내지 않습니다.
2. 최종 diff의 범위, 비밀값, 의도하지 않은 변경을 검토합니다. 해당하는 계약, 사용 모듈, 설정 복사본, 문서를 함께 갱신합니다.
3. 관련 모듈 규칙에서 가장 작은 관련 검사부터 실행한 뒤, 변경한 동작을 검증하는 DB·통합·E2E 검사를 실행합니다. 한 모듈만 변경해도 적용됩니다. 전체 CI 환경 준비 절차는 [.github/workflows/tests.yml](../.github/workflows/tests.yml)에 있습니다.
4. 각 필수 기준을 **통과**, **실패**, **미실행/미검증**, **해당 없음과 그 이유** 중 하나로 보고합니다. 명령이 성공했다는 사실은 실제로 검사한 내용에 대한 근거일 뿐입니다. 명령, 작업 디렉터리, 결과, 실제 시스템과 fixture의 경계를 보고합니다. 건너뛴 테스트나 대기 중인 CI를 통과로 표시하지 않습니다.
5. 빌드나 HTTP 응답뿐 아니라 요청한 동작을 검증합니다. 기본 Go 테스트는 `-tags=e2e`를 제외하며, Python E2E는 `RUN_AGENT_E2E=1`이 없으면 건너뜁니다. fixture 기반 E2E는 운영 통합이나 RCA 품질의 증거가 아닙니다.
6. push 전 필수 검사가 해결되지 않은 상태에서 작업이 완전히 검증되었다고 표시하거나 push/merge하지 않습니다. 승인된 배포 후에만 외부 검사가 가능하다면 담당자, 조건, 실패 대응을 합의하고 실행 전까지 미검증으로 명시합니다. 제품 변경에는 관련 검수 근거가 필요합니다. 문서만 변경한 경우 실제 LLM/Grafana 테스트는 필요하지 않습니다.
7. 완료한 단계를 로컬 파일, 로컬 commit, 원격 push, CI, 배포, 실제 시스템 검증 중에서 정확히 밝힙니다. 남은 공백과 다음 조치를 정리하되, 이를 수행할 권한이 주어졌다고 암시하지 않습니다.

### 문서 검사

저장소 루트에서 `python tools/check_links.py`를 실행합니다. Python 3 명령이 `python3`인 환경에서는 이를 사용합니다. 표준 라이브러리만 필요합니다. 이름이 바뀐 절의 anchor와 프롬프트 코드 블록 안의 경로는 별도로 확인합니다. 링크 검사기는 이를 검증하지 않습니다. 규칙을 변경할 때는 적용 범위와 규칙 선택, 영어·한국어 일치, 기존 정책 보존을 검토합니다. 모듈 규칙을 읽었다는 이유만으로 문서만 변경한 작업에 해당 모듈의 전체 런타임 테스트를 요구하지 않습니다. 실제 영향에 따라 검사를 선택하고, 실행 가능한 지침이 바뀌었다면 해당 지침을 검증합니다. 정적 파일 검사만으로 코딩 도구가 실제 세션에서 규칙을 읽었다고 입증할 수는 없습니다.

## 운영 안전

원본: [safety.md](../.claude/rules/safety.md)

파일을 수정하지 않는 분석과 운영 명령을 포함해 모든 작업에 적용합니다.

- 비밀값, 토큰, 로컬 `.env` 파일, 운영 데이터를 커밋하지 않습니다. 근거를 공유하기 전에 민감한 내용을 가립니다. 자격 증명이 포함된 전체 연결 문자열, 민감한 원본 로그, chart values/manifest의 비밀값을 노출하지 않습니다.
- 일반 개발과 테스트에는 개인 로컬 또는 격리된 테스트 데이터베이스를 사용합니다. 테스트는 데이터를 쓰거나 삭제할 수 있습니다. 실행 전에 실제 대상을 확인하고 테스트를 운영 환경에 연결하지 않습니다. 공유 통합 환경의 변경과 시점은 담당자와 조율합니다.
- `backend/scripts/dev-server.ps1`을 공유·스테이징·운영 데이터베이스에 실행하지 않습니다. migration과 데모 seed를 활성화하며 기존 `DATABASE_URL`을 재사용할 수 있습니다.
- Job Controller와 Incident는 시작할 때 파일/Helm 설정을 적용합니다. 데이터베이스를 직접 수정한 내용은 재시작 시 덮어쓸 수 있으므로 지속적인 설정 관리 수단이 아닙니다.
- 업그레이드 중 기존 PostgreSQL과 보고서 PVC를 보존합니다. [기존 배포 업그레이드](helm-upgrade-existing.md)를 따르고 영속 스토리지를 함부로 삭제하거나 다시 만들지 않습니다.
- DB·배포 변경을 적용하기 전에 대상, 기존 데이터 영향, 적용 순서, 복구 계획을 확인합니다. 애플리케이션이나 chart를 되돌려도 데이터베이스 변경이 자동으로 취소되지는 않습니다. 공유 DB 적용은 조율하며, 로컬 파일 수정 권한을 실제 시스템 변경 권한으로 간주하지 않습니다.
- 실제 장비 조치는 사람이 수행합니다. 검증되지 않은 관측과 불확실한 원격 실행은 명시적으로 미해결 상태를 유지합니다. 나중에 요청 하나가 성공했다는 사실만으로 복구를 주장하지 않습니다. Agent timeout·quarantine 운영은 [agents/README.md](../agents/README.md)와 [Job Controller](../job-controller/README.md#추론-격리와-취소)에 설명되어 있습니다.

## Frontend

원본: [frontend.md](../.claude/rules/frontend.md)

원본의 적용 경로:

```yaml
---
paths:
  - "frontend/**"
---
```

- 기존 React, TypeScript, Vite, Vitest 패턴을 재사용합니다. CI는 Node 24와 커밋된 lockfile을 사용합니다. 필요하면 `frontend/`에서 CI와 같이 `npm ci --ignore-scripts`로 설치합니다.
- [Frontend README](../frontend/README.md), [Frontend QA](../frontend/QA.md), [docs/README.md](README.md)의 현행 UI/API 명세부터 확인합니다. 필드나 상태를 만들어내지 말고 실제 Backend 응답을 확인합니다.
- 변경한 흐름에서 정상, 실패, 빈 상태·근거 부족 표시를 검증합니다. 알 수 없는 근거를 정상 측정값으로 표시하거나, 공개되지 않은 결과를 최종 결과로 표시하지 않습니다.
- API·결과 형식이 바뀌면 Frontend 테스트뿐 아니라 해당 Backend/Agent 사용 모듈과 그 규칙도 확인해야 합니다.

### Frontend 검증

`frontend/`에서 실행합니다.

```bash
npm run format:check
npm test
npm run build
```

[공통 완료 기준](#공통-완료-기준)을 적용합니다. 집중된 테스트나 UI 검사를 통해 변경한 화면·상호작용과 해당 응답 상태를 입증합니다. 빌드 통과만으로 상호작용이 검증되지는 않습니다. API가 실제였는지 mock이었는지 밝힙니다.

## Go 서비스와 데이터베이스 계약

원본: [go-services.md](../.claude/rules/go-services.md)

원본의 적용 경로:

```yaml
---
paths:
  - "backend/**"
  - "incident/**"
  - "job-controller/**"
  - "shared/contract/**"
  - "shared/migrations/**"
  - "shared/**/*.go"
  - "shared/go.mod"
  - "shared/go.sum"
  - "shared/README.md"
---
```

- `shared`, `backend`, `job-controller`, `incident`는 Go 1.26.2와 상대 `replace` 지시어를 사용하는 독립 Go 모듈입니다. 루트 Go workspace는 없습니다. 공통 계약을 재사용하고 여러 사례를 검사하는 로직에는 테이블 기반 테스트를 선호합니다.
- 수정하는 모듈의 README/API/QA와 [shared 소유권](../shared/README.md)부터 확인합니다. Incident의 RCA 접수, Backend의 보고서 예약, JC의 수명 주기·결과 공개 소유권, 변경 불가능한 근거·결과를 보존합니다.
- RCA 결과 변경은 Backend, RCA, Ops, Frontend 사용 모듈에 영향을 줍니다. 보고서 변경은 Backend, Ops, Frontend에 영향을 줍니다. 실제로 영향을 받는 경로를 검증하고 해당 규칙을 따릅니다.
- SQL은 `shared/migrations/`에서 관리합니다. SQL 파일을 추가하는 것만으로 충분하지 않습니다. embed 등록과 각 서비스의 적용 경로를 확인합니다. 이미 적용된 SQL을 수정하면 기존 DB도 갱신된다고 가정하지 않습니다.
- DB 변경은 Backend/DB 담당자와 조율합니다. 데이터 영향, 적용 순서, 복구 방법을 기록하고, 새 DB 초기화·기존 DB 업그레이드·반복 시작을 검증합니다. 격리된 테스트 DB를 사용하고 [운영 안전](#운영-안전)을 따릅니다.
- Incident의 `analysis_policies` 내용이 바뀌면 새 revision을 사용합니다. 기존 revision에 다른 내용을 덮어쓰지 않습니다. 원본/Helm 설정 복사본은 [배포 규칙](#배포-설정과-ci)을 따릅니다.

### Go 검증

변경한 각 모듈과 영향을 받는 사용 모듈에서 실행합니다.

```bash
go vet ./...
go test -race ./...
go build ./...
```

- 공통 Go 계약·migration을 변경하면 Go 모듈 네 개를 모두 검사해야 합니다. 다른 모듈이 재사용하는 Job Controller 코드를 변경하면 Backend와 Incident도 검사해야 합니다. 독립 모듈은 서로의 테스트를 실행하지 않습니다. 공통 계약 테스트는 `backend/internal/contract/`에도 있습니다.
- 변경한 동작과 관련된 DB·통합·E2E 사례를 실행합니다. 위의 일반 테스트는 `-tags=e2e` 테스트를 제외합니다. [.github/workflows/tests.yml](../.github/workflows/tests.yml)의 테스트 DB와 바이너리 준비 절차를 사용합니다.
- 계약 호환성과 관련 오류·멱등성 동작을 포함해 [공통 완료 기준](#공통-완료-기준)을 적용합니다. 실행하지 않은 DB/E2E 사례를 명시적으로 보고합니다.

## 제품 Agent와 공통 Python

원본: [agents.md](../.claude/rules/agents.md)

원본의 적용 경로:

```yaml
---
paths:
  - "rcca-agent/**"
  - "ops-agent/**"
  - "shared/python/**"
  - "agents/**"
  - "grafana-mcp/**"
---
```

이 규칙은 제품 Worker 개발을 안내하며 Claude Code subagent를 정의하지 않습니다. 루트 [AGENTS.md](../AGENTS.md)는 별도의 코딩 도우미 시작 지침입니다.

- `rcca-agent/`는 장애 RCA를, `ops-agent/`는 운영 보고서를 구현합니다. `agents/`에는 공통 설정 예시, 환경 준비, 테스트, 실행 문서가 있습니다.
- `shared/python/src/agent_common/`은 두 Worker가 import하는 코드입니다. JC Worker 수명 주기, LLM 호출, 설정, 결과 계약, 관측·계산, 저장소 기능을 포함합니다. 두 Worker가 공유하는 동작에는 이 코드를 재사용합니다. 별도로 실행되는 Agent, Python 설치본, 코딩 도우미 메모리가 아닙니다.
- 공통 Python, `agents/`, Grafana MCP를 변경하면 두 Worker를 모두 확인해야 합니다. JC/DB 계약 영향은 Backend/DB 담당자와 공유합니다. 버전이 고정된 공식 Grafana MCP 패키징과 기존 질의·근거 계약을 유지합니다.
- RCA 변경은 Incident snapshot·runbook·근거 참조와 근거 부족 시 동작을 보존해야 합니다. Ops 변경은 기간·단위·계산과 공개된 RCA 참조를 보존해야 합니다. RCA 결과 변경은 Ops, Backend, Frontend 사용 모듈에도 영향을 줍니다.
- Worker는 JC에 등록하고 작업을 claim하며, JC가 공개할 결과 후보를 제출합니다. 별도 스케줄러, 큐, 직접 제출 API를 추가하지 않습니다. 계산과 검증은 같은 입력에 같은 결과가 나오는 결정적 방식으로 수행합니다. LLM은 검증된 근거를 설명하는 데 사용하며, 완전성이나 수행한 조치를 만들어내는 데 사용하지 않습니다.
- [실행과 timeout 지침](../agents/README.md), [Agent QA](../agents/QA.md), 관련 Worker README, [docs/README.md](README.md)의 현행 Agent·계약 명세를 읽습니다. 원본 설정을 수정할 때는 [배포 규칙](#배포-설정과-ci)도 필요합니다.

### Agent 환경 준비와 검증

패키지는 Python 3.11–3.13을 지원하며 CI는 3.12를 사용합니다. Worker에 Python 3.14 이상을 사용하지 않습니다. macOS/Linux에서는 `python3.12 -m venv .venv`, Windows에서는 `py -3.12 -m venv .venv`로 `.venv`를 만듭니다. 각각 `source .venv/bin/activate` 또는 `.\.venv\Scripts\Activate.ps1`로 활성화하고 `python --version`을 확인합니다.

해당 환경을 활성화한 상태에서 저장소 루트에서 실행합니다.

```bash
python -m pip install -r agents/requirements.txt -e shared/python -e rcca-agent -e ops-agent ruff==0.14.0
ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci
ruff format --check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci
python -m pytest -c agents/pytest.ini agents/tests -q
```

[공통 완료 기준](#공통-완료-기준)을 적용합니다. 관련 수명 주기·통합·E2E 사례를 실행하고, 공통 변경이면 두 Worker를 모두 포함합니다. E2E에는 `RUN_AGENT_E2E=1`뿐 아니라 [.github/workflows/tests.yml](../.github/workflows/tests.yml)의 테스트 DB·바이너리·검증된 MCP 환경도 필요합니다. 플래그만 설정해서는 충분하지 않습니다.

LLM 응답 성공은 정확한 RCA·보고서나 JC 결과 공개의 증거가 아닙니다. 해당하는 근거 참조, 필드 의미, 데이터 부족 시 결과, 최종 job·결과 상태, 영향을 받는 사용 모듈을 검증합니다. 실제 Grafana/LLM 검증과 fixture 테스트를 구분합니다. 일률적인 정확도 백분율을 만들지 말고 실제 근거에 따라 작업별 품질 기준을 합의합니다.

## 배포, 설정과 CI

원본: [deployment.md](../.claude/rules/deployment.md)

원본의 적용 경로:

```yaml
---
paths:
  - "charts/**"
  - ".github/**"
  - "tools/ci/**"
  - "agents/config.example.json"
  - "job-controller/config.example.json"
  - "incident/config.example.json"
  - "docs/helm-*.md"
  - "docs/ci-release.md"
---
```

운영 명령을 실행하기 전에 [운영 안전](#운영-안전)을 읽습니다. 실제 환경에 맞춰 [chart README](../charts/gpu-ops-advisor/README.md), [설치](helm-install.md), [업그레이드](helm-upgrade-existing.md), [CI·릴리스](ci-release.md) 가이드를 사용합니다.

### 설정 복사본

같은 변경에서 양쪽을 모두 갱신합니다. `python tools/ci/check_chart.py`가 일치를 검사합니다.

| 원본 | Helm 복사본 |
|---|---|
| `agents/config.example.json` | `charts/gpu-ops-advisor/files/agents.json` |
| `job-controller/config.example.json` | `charts/gpu-ops-advisor/files/job-controller.json` |
| `incident/config.example.json` | `charts/gpu-ops-advisor/files/incident.json` |

- `configuration.agents`, `configuration.jobController`, `configuration.incident`는 내장 객체 전체를 대체하며 deep merge되지 않습니다. 입력이 바뀌면 환경 예시와 문서를 갱신합니다.
- 배포 컴포넌트 목록인 `tools/ci/components.json`을 chart 컴포넌트와 일치시킵니다. Incident 정책 내용을 바꿀 때 변경 불가능한 policy revision을 보존합니다.
- CI 산출물 게시는 Kubernetes 배포를 수행하지 않습니다. 승인된 배포에는 성공한 CI 산출물을 사용하고 정확한 chart 버전, 이미지 digest, 대상, 복구 계획을 기록합니다. DB·보고서 PVC를 보존합니다. PR 빌드 산출물은 게시된 배포 이미지가 아닙니다.
- Agent timeout을 바꿀 때는 [Agent 실행 지침](../agents/README.md)을 사용합니다. 요청 timeout, job deadline, 불확실한 원격 실행·quarantine은 서로 다른 문제입니다.

### 배포 검증

활성화된 Python 3.12 환경과 `PATH`에 있는 Helm 3.17.3을 사용합니다. 필요하면 [Agent 환경 준비](#agent-환경-준비와-검증)에 따라 `.venv`를 만들고 활성화합니다. chart만 검사할 때 Worker 의존성은 설치하지 않아도 됩니다.

저장소 루트에서 실행합니다.

```bash
python -m pip install PyYAML==6.0.2 jsonschema==4.26.0
python tools/ci/check_chart.py
python -m unittest discover -s tools/ci/tests -v
```

런타임 설정·계약이 바뀌면 영향을 받는 모듈 검사도 실행합니다. 전체 CI와 workflow 검증은 [.github/workflows/tests.yml](../.github/workflows/tests.yml)을 따릅니다. [공통 완료 기준](#공통-완료-기준)을 적용합니다. 정적 chart 검사만으로 배포 성공이 입증되지는 않습니다. 승인된 배포 후에는 Pod 준비 상태뿐 아니라 영향을 받는 접수→실행→결과 공개·조회 흐름을 검증합니다. 공통 Agent 설정은 두 Worker를 모두 검증해야 합니다. 남은 실제 환경 검사는 실행 전까지 미검증으로 기록합니다.
