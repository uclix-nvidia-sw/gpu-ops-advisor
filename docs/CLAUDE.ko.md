# Claude Code 컨텍스트

이 저장소에서 Claude Code로 함께 개발할 때 적용하는 팀 공통 지침입니다. 다른 코딩 Agent도 [AGENTS.md](../AGENTS.md)를 통해 같은 규칙을 읽습니다. 이 문서는 [CLAUDE.md](../CLAUDE.md)의 한국어 번역본이며, 번역 내용이 다르면 영어 원본을 기준으로 합니다.

본문에 표시한 저장소 경로는 저장소 루트 기준입니다. 명령은 별도 작업 디렉터리가 명시되지 않은 한 저장소 루트에서 실행합니다.

## 적용 범위

더 하위 디렉터리의 `CLAUDE.md`가 재정의하지 않는 한, 이 지침은 저장소 전체에 적용됩니다.

## 제품 의도(안정적)

- GPU Ops Advisor v1.3은 저장된 GPU/Node/Pod 관측 근거를 바탕으로 장애 원인 분석(RCA)과 운영 보고서를 만듭니다.
- 자동 RCA는 Grafana에서 Incident, Job Controller, RCA Agent 순서로 진행됩니다. 보고서는 GUI/Backend에서 Job Controller와 Report Agent로 전달되며, Backend는 정기 보고서 작업도 생성합니다.
- Agent는 장기 실행 Worker로서 Job Controller에서 작업을 가져옵니다. 별도의 큐, 스케줄러, 사용자용 접수 API, 장비 제어 경로를 소유하지 않습니다.
- 결정적인 계산과 검증은 코드가 담당합니다. LLM은 검증된 근거를 해석하고 설명할 뿐, 데이터·조치·성공 결과를 만들어내면 안 됩니다.

## 진실의 우선순위

- 안정적인 의도와 가드레일: 루트 `CLAUDE.md`와 루트 `README.md`
- 실제 런타임 동작: 각 모듈의 구현과 테스트
- 공통 API 및 데이터베이스 계약: `shared/contract/`와 `shared/migrations/`; 후자가 SQL의 단일 원본입니다.
- 설계 범위와 검수 기준: `output/deliverables-20260917-v1.3/`
- 검증된 상태와 알려진 한계: 각 모듈의 `QA.md`

문서와 코드가 다르면 코드와 테스트를 현재 동작으로 간주하고, 같은 변경에서 가장 가까운 관련 문서를 갱신합니다. 설계 문서, fixture, 새로 추가한 테스트만으로 운영 환경 검증을 완료했다고 판단하지 않습니다.

## 참조 지도

- 시스템 개요와 흐름: `README.md`
- 요구사항과 범위: `output/deliverables-20260917-v1.3/01_요구사항_개발범위_정의서.md`
- API, 데이터, 모듈 간 계약: 같은 디렉터리의 `02_백엔드_API_작업명세서.md`, `03_데이터_설계서.md`, `14_모듈간_호출과_공통실행_계약.md`
- 테스트 검수와 운영: 같은 디렉터리의 `05_테스트_검수_기준서.md`, `06_배포_운영_인계서.md`
- Agent 동작과 한계: `agents/README.md`, `agents/QA.md`
- 배포: `charts/gpu-ops-advisor/README.md`, `docs/helm-install.md`
- CI와 릴리스 동작: `docs/ci-release.md`, `.github/workflows/tests.yml`

## 프로젝트 구조

- `backend/`, `incident/`, `job-controller/`, `shared/`: 서로 독립된 Go 모듈이며 루트 Go workspace는 없습니다.
- `rcca-agent/`, `ops-agent/`, `shared/python/`, `agents/`: Python Worker, 공통 런타임, 프로필, 테스트입니다.
- `frontend/`: React, TypeScript, Vite, Vitest 애플리케이션입니다.
- `grafana-mcp/`: 버전이 고정된 공식 Grafana MCP 패키징입니다.
- `charts/gpu-ops-advisor/`: Helm chart와 내장 애플리케이션 설정입니다.
- `tools/ci/`: chart, 컴포넌트, 패키징, 릴리스 계약 검사입니다.
- `docs/`, `output/`: 운영 근거, 현행 산출물, 아키텍처 자료입니다.

## 아키텍처 경계

- 자동 RCA 진입 경로를 `Grafana -> Incident -> Job Controller -> RCA Agent`로 유지하고, GUI/Backend에서 Agent를 직접 실행하는 경로를 추가하지 않습니다.
- Job Controller가 큐, 처리 용량, lease, attempt, 결과 공개를 소유합니다. Agent는 등록한 뒤 작업을 claim합니다.
- `shared/README.md`에 정의된 데이터베이스 소유권, 변경 불가능한 Incident snapshot·설정 revision·결과 hash, 멱등 키를 보존합니다.
- 사용할 수 없거나 의미가 검증되지 않은 관측값은 `unknown`, `partial`, `blocked`로 유지하며 완전한 결과를 만들어내지 않습니다.
- 실제 장비 조치는 사람이 수행합니다.

## 작업 방식

- 변경 범위를 집중시키고, 새 추상화·도구·의존성을 추가하기 전에 기존 구조를 재사용합니다.
- 작고 정확한 수정을 선호하며, 관련 없는 파일의 포맷이나 이름을 바꾸지 않습니다.
- 기존 이름 규칙과 주변 문서의 언어를 따릅니다. 코드 식별자와 개발자용 주석은 영어로 작성합니다.
- 동작이나 인터페이스가 바뀌면 가장 가까운 관련 문서를 함께 갱신합니다.
- UTF-8 CRLF 텍스트 형식을 유지하고, 제공되는 포맷 스크립트가 있으면 사용합니다.
- 비밀값, 토큰, 로컬 `.env` 파일, 운영 데이터를 커밋하지 않습니다.

## 설정 복사본

원본 설정을 변경할 때 같은 변경에서 Helm 복사본도 갱신합니다.

- `agents/config.example.json`과 `charts/gpu-ops-advisor/files/agents.json`
- `job-controller/config.example.json`과 `charts/gpu-ops-advisor/files/job-controller.json`
- `incident/config.example.json`과 `charts/gpu-ops-advisor/files/incident.json`

이 쌍은 `python tools/ci/check_chart.py`가 검사합니다.

- `configuration.agents`, `configuration.jobController`, `configuration.incident`는 내장 객체와 deep merge되지 않고 객체 전체를 대체합니다.
- `tools/ci/components.json`은 배포 컴포넌트 목록의 원본이며 chart의 컴포넌트와 일치해야 합니다.

## 운영 안전

- `backend/scripts/dev-server.ps1`은 migration과 데모 seed를 활성화하므로 공유·스테이징·운영 데이터베이스를 대상으로 실행하지 않습니다.
- Job Controller와 Incident는 시작할 때 파일/Helm 설정을 적용합니다. 재시작 시 덮어쓸 수 있는 데이터베이스 직접 수정에 의존하지 않습니다.
- Helm 업그레이드 중 기존 PostgreSQL과 보고서 PVC를 보존합니다. `docs/helm-upgrade-existing.md`를 따르고 함부로 삭제하거나 다시 만들지 않습니다.

## 검증 환경 준비

Python 검사는 CI와 같은 Python 3.12 가상환경을 활성화한 상태를 전제로 합니다. 최초 설정 시 macOS/Linux에서는 `python3.12 -m venv .venv`, Windows에서는 `py -3.12 -m venv .venv`로 `.venv`를 만듭니다. macOS/Linux에서는 `source .venv/bin/activate`, PowerShell에서는 `.\.venv\Scripts\Activate.ps1`로 활성화합니다. 의존성을 설치하기 전에 `python --version`을 확인합니다. Agent는 Python 3.14 이상을 지원하지 않습니다.

저장소 루트에서 필요한 검사에 맞는 의존성을 설치합니다.

- Agent 검사: `python -m pip install -r agents/requirements.txt -e shared/python -e rcca-agent -e ops-agent ruff==0.14.0`
- Helm과 CI 검사: `python -m pip install PyYAML==6.0.2 jsonschema==4.26.0`. Helm 3.17.3도 `PATH`에 있어야 합니다.
- 문서 링크 검사에는 Python 표준 라이브러리만 필요합니다.

## 검증(가장 작은 관련 검사부터)

- Go: 변경한 모듈(`shared`, `backend`, `job-controller`, `incident`)과 그 변경의 영향을 받는 사용 모듈 디렉터리에서 실행합니다.
  `go vet ./...`, `go test -race ./...`, `go build ./...`
  `shared/`의 Go 계약이나 migration을 변경하면 Go 모듈 네 개를 모두 검사합니다. 다른 모듈이 재사용하는 `job-controller/` 코드를 변경하면 `backend/`와 `incident/`도 검사합니다. 독립 모듈의 테스트는 다른 모듈의 테스트를 실행하지 않으며, 공통 계약 테스트 일부는 `backend/internal/contract/`에 있습니다.
- Python Agent: 저장소 루트에서 실행합니다.
  `ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`
  `ruff format --check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`
  `python -m pytest -c agents/pytest.ini agents/tests -q`
- Frontend: `frontend/`에서 실행합니다.
  `npm run format:check`, `npm test`, `npm run build`
- Helm과 CI 계약:
  `python tools/ci/check_chart.py`
  `python -m unittest discover -s tools/ci/tests -v`
- 문서 링크:
  `python tools/check_links.py`

수정한 동작을 검증하는 DB·통합·E2E 테스트가 있으면 해당 테스트를 실행합니다. 시작 시 기본값 초기화, migration, 서비스 간 계약이 여기에 포함되며 한 모듈만 변경해도 적용됩니다. 일반 Go 테스트에서는 `-tags=e2e` 테스트가 제외되고, Python E2E 테스트는 `RUN_AGENT_E2E=1`이 없으면 건너뜁니다. 따라서 기본 테스트 명령이 통과해도 E2E 검증을 완료한 것은 아닙니다. 전체 CI 명령의 기준인 `.github/workflows/tests.yml`의 테스트 DB·바이너리 준비 절차를 따르고, 어떤 외부 시스템이 실제였고 무엇이 fixture였는지 정확히 기록합니다.

## 언어와 도구 버전

- Go 모듈은 Go 1.26.2와 상대 `replace` 지시어를 사용합니다. `shared/`를 재사용하고 여러 사례를 검사하는 로직에는 테이블 기반 테스트를 선호합니다.
- Python 패키지는 3.11 이상 3.14 미만을 지원하며 CI는 3.12를 사용합니다. 두 Agent가 공유하는 동작은 `shared/python/`을 재사용합니다.
- Frontend CI는 Node 24와 커밋된 lockfile을 사용합니다. 필요 없이 기존 React/Vite/Vitest 패턴을 바꾸지 않습니다.
- Helm 검증 기준은 Helm 3.17.3입니다. chart values나 manifest에 비밀값을 넣지 않습니다.

## 피해야 할 것

- 명확한 요구 없이 새 큐, 스케줄러, aggregator, Agent 직접 API, 의존성을 도입하지 않습니다.
- 생성되었거나 버전이 고정된 산출물을 함부로 편집하지 않습니다. 특히 생성된 HTML을 직접 고치지 말고 Archify JSON 원본을 수정한 뒤 다시 생성합니다.
- 배포 계약으로 정의되지 않은 Fleet, metric, allocation, topology, health 의미를 추정하지 않습니다.
- 실제로 실행하지 않은 테스트를 통과했다고 쓰거나, fixture 기반 테스트를 운영 통합 검증이라고 표현하지 않습니다.
