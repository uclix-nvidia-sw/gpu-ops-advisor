# Claude Code 컨텍스트

저장소 전체에 적용되는 팀 공통 지침입니다. [루트 CLAUDE.md](../CLAUDE.md)와 [.claude/rules/](../.claude/rules/)의 영어 파일이 원본이며, 한국어 번역은 이 문서와 [rules.ko.md](rules.ko.md)에 있습니다. 다른 코딩 Agent는 [AGENTS.md](../AGENTS.md)를 시작 지침으로 사용합니다.

## 적용 범위와 규칙 선택

더 하위 디렉터리의 `CLAUDE.md`가 재정의하지 않는 한, 이 지침은 저장소 전체에 적용됩니다. 분석, 수정, 테스트 또는 운영 명령을 실행하기 전에 아직 읽지 않은 관련 규칙을 아래에서 확인합니다. 여러 모듈에 걸친 작업에는 영향을 받는 사용 모듈을 포함해 모든 관련 규칙을 적용합니다.

| 적용 시점 | 읽어야 할 규칙 |
|---|---|
| 모든 작업: 범위, Git 권한, 검증과 완료 | [workflow.md](../.claude/rules/workflow.md) |
| 모든 작업: 비밀값, 데이터베이스와 배포 안전 | [safety.md](../.claude/rules/safety.md) |
| Frontend 작업 | [frontend.md](../.claude/rules/frontend.md) |
| Backend, Incident, Job Controller, 공통 Go 계약 또는 migration | [go-services.md](../.claude/rules/go-services.md) |
| RCA/Ops Worker, 공통 Python, Agent 테스트·설정 또는 Grafana MCP | [agents.md](../.claude/rules/agents.md) |
| Helm, CI, 배포 또는 Agent/JC/Incident 원본 설정 예시 | [deployment.md](../.claude/rules/deployment.md) |

Claude Code는 범위가 지정되지 않은 규칙을 시작할 때 읽고, `paths`로 범위가 지정된 규칙은 해당 파일을 읽을 때 불러옵니다. 위의 규칙 선택 기준은 해당 경로의 파일을 읽지 않는 작업에도 적용됩니다. 다른 코딩 Agent는 이 링크를 명시적으로 따라야 하며, `.claude/rules/`를 자동으로 읽는다고 가정하지 않습니다. 경로별 규칙을 모두 이 파일로 가져오지 않습니다. 규칙은 행동을 안내하며 권한을 강제하는 수단은 아닙니다. [Claude Code 메모리](https://code.claude.com/docs/en/memory)와 [Codex AGENTS.md 지침](https://learn.chatgpt.com/docs/agent-configuration/agents-md)을 참고합니다.

## 제품 의도와 경계

- GPU Ops Advisor v1.3은 저장된 관측 근거를 바탕으로 GPU/Node/Pod 장애 원인 분석(RCA)과 운영 보고서를 만듭니다.
- 자동 RCA: `Grafana -> Incident -> Job Controller -> RCA Agent`. 보고서: `GUI/Backend -> Job Controller -> Ops Agent`; Backend는 정기 보고서 작업도 생성합니다.
- Agent는 Job Controller에 등록하고 작업을 가져오는 장기 실행 Worker입니다. JC가 큐, 처리 용량, lease, attempt, 결과 공개를 소유합니다. GUI/Backend에서 Agent를 직접 실행하는 경로나 장비 제어 경로를 추가하지 않습니다. 입증된 요구 없이 별도의 큐·스케줄러·aggregator, 사용자용 Agent API 또는 의존성을 도입하지 않습니다.
- [shared/README.md](../shared/README.md)의 데이터베이스 소유권, 변경 불가능한 Incident snapshot·설정 revision·결과 hash, 멱등 키를 보존합니다.
- 같은 입력에 같은 결과가 나오는 계산(결정적 계산)과 검증은 코드가 담당합니다. LLM은 검증된 근거를 해석하며, 데이터·조치·성공 결과를 만들어내면 안 됩니다. 사용할 수 없거나 의미가 검증되지 않은 관측값은 `unknown`, `partial`, `blocked`로 유지합니다. 배포된 계약에 없는 Fleet, metric, allocation, topology, health의 의미를 추정하지 않습니다.
- 실제 장비 조치는 사람이 수행합니다.

## 진실의 우선순위

- 안정적인 의도와 가드레일: 이 문서의 영어 원본, 관련 규칙, 루트 [README.md](../README.md)
- 실제 런타임 동작: 각 모듈의 구현과 테스트
- 공통 API 및 데이터베이스 계약: `shared/contract/`와 `shared/migrations/`; 후자가 SQL의 단일 원본입니다.
- 설계 범위와 검수 기준: [docs/README.md](README.md)가 연결하는 현행 산출물. 현재는 `output/deliverables-20260917-v1.3/`입니다.
- 검증된 상태와 알려진 한계: 각 모듈의 `QA.md`에 명시된 날짜, 환경, 범위 내의 내용

문서와 코드가 다르면 코드와 테스트를 현재 동작으로 간주하고, 같은 변경에서 가장 가까운 관련 문서를 갱신합니다. 설계 문서, fixture, 새로 추가한 테스트만으로 운영 환경 검증을 완료했다고 판단하지 않습니다.

## 저장소와 참조 지도

- `backend/`, `incident/`, `job-controller/`, `shared/`: 서로 독립된 Go 모듈 네 개이며 루트 Go workspace는 없습니다.
- `rcca-agent/`와 `ops-agent/`: 제품 Worker 구현입니다. `shared/python/`: 공통 Python 런타임입니다. `agents/`: 공통 설정 예시, 환경 준비, 테스트, 실행 문서이며 코딩 도우미 지침이 아닙니다.
- `frontend/`: React/TypeScript/Vite/Vitest. `grafana-mcp/`: 버전이 고정된 공식 Grafana MCP 패키징입니다.
- `charts/gpu-ops-advisor/`와 `tools/ci/`: 배포 설정과 패키징·계약 검사입니다.
- [docs/README.md](README.md): 현행 요구사항, API·데이터·Agent 계약, 검수 기준, 운영, 모듈 README/QA, 아키텍처 링크입니다. 날짜가 붙은 설계 경로가 여전히 현행이라고 가정하지 말고 여기서 시작합니다.
- [docs/team-development.md](team-development.md): 담당 범위, 사람을 위한 설명, 브랜치·PR 예시, 배포 인계입니다. [docs/agent-prompts.md](agent-prompts.md): 역할별 첫 작업 프롬프트 네 개이며, 추가 런타임 Agent를 뜻하지 않습니다.
- [.github/workflows/tests.yml](../.github/workflows/tests.yml): 전체 CI 명령과 환경 준비 절차의 기준입니다. [docs/ci-release.md](ci-release.md): 릴리스 동작입니다.
