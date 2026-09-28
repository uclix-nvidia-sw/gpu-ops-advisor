# GPU Ops Advisor 개발 문서 안내

현재 기준은 **GPU Ops Advisor v1.3**입니다. Job Controller는 큐와 기존 자원 내 배분을 맡고, 정기 보고서 일정·요청 생성은 Backend, 보고서 실행은 보고서 Agent가 담당합니다. RCA 요청은 Incident에서만 시작합니다. 두 Agent 내부에는 NAT 워크플로를 적용합니다. RCA는 Runbook·사고 증거·Grafana MCP를, 보고서는 Incident·공개 RCA 결과 DB와 MCP 기간 관측을 사용합니다. 상세 연결·운영·검수 기준은 03/04/05/06/11/12/14에 있습니다.

[저장소 README](../README.md) · [전체 구조도](architecture/architecture-modules-20260917-v1.3/README.md) · [보존한 환경 근거](evidence/README.md)

## 팀 공통 개발 지침

- [팀 개발 역할과 협업 규칙](team-development.md): 담당 범위, 현재 main 작업·향후 PR 절차, DB 변경과 배포
- [CLAUDE.md: 공통 원칙과 규칙 안내](../CLAUDE.md) · [한국어 번역](CLAUDE.ko.md)
- [AGENTS.md: 코딩 에이전트 시작 지침](../AGENTS.md) · [한국어 번역](AGENTS.ko.md)
- [작업·완료 기준](../.claude/rules/workflow.md) · [안전수칙](../.claude/rules/safety.md)
- [Frontend](../.claude/rules/frontend.md) · [Go·DB](../.claude/rules/go-services.md) · [제품 Agent·공통 Python](../.claude/rules/agents.md) · [배포·설정·CI](../.claude/rules/deployment.md)
- [분리한 여섯 규칙의 한국어 번역](rules.ko.md) · [검증 성공 기준](rules.ko.md#공통-완료-기준)
- [처음 작업을 시작할 때 쓰는 담당별 프롬프트 4가지](agent-prompts.md)

`AGENTS.md`와 `.claude/rules/`는 코딩 도우미가 읽는 지침입니다. 제품의 `agents/`는 RCA·Ops Worker용 공통 설정·테스트·실행 안내이며, 두 Worker가 재사용하는 실제 Python 코드는 `shared/python/`에 있습니다. 이 규칙들은 지침이지 commit·push·배포 권한을 강제로 차단하는 설정은 아닙니다.

### 지침을 수정하고 확인하는 방법

공통 원칙은 루트 `CLAUDE.md`, 세부 규칙은 해당 영어 규칙 파일을 수정하고 한국어 번역도 함께 맞춥니다. 한국어 번역은 중복으로 자동 로딩되지 않도록 `docs/`에만 둡니다. 개인 설정이나 별도 hook은 이 구조에 포함하지 않습니다.

문서 변경의 성공 기준은 링크·프롬프트 경로가 유효하고, 규칙의 적용 범위가 맞으며, 기존 정책과 번역이 일치하는 것입니다. `python tools/check_links.py`로 로컬 링크를 확인하고, 절 제목 링크와 프롬프트 코드 블록의 경로는 따로 확인합니다. 문서 검사 성공과 실제 도구의 로딩 확인은 별개입니다.

Claude Code에서는 새 세션을 열어 `/context`에서 공통 규칙을 확인하고, 담당 모듈 파일을 읽은 뒤 해당 경로 규칙도 확인합니다. 경로 없는 규칙은 시작할 때, `paths`가 있는 규칙은 맞는 파일을 읽을 때 로딩되는 방식입니다. 다른 코딩 도구는 루트 `AGENTS.md`의 안내에 따라 같은 규칙을 읽게 합니다. 실제 세션에서 확인하기 전에는 자동 적용 검증을 완료했다고 적지 않습니다. [Claude Code 공식 안내](https://code.claude.com/docs/en/memory)

## 현행 개발 문서

현행 명세는 `specs/`, 구조도는 `architecture/`, 실제 환경 확인 자료는 `evidence/`에서 관리합니다. 명세의 위치는 고정하고 기준일·버전은 문서 안에 기록합니다. 공통 데이터·산식·실행 계약은 `specs/common/`을 참조하고, 담당 모듈 문서에서 중복 정의하지 않습니다. 실제 실행 방법과 검증 기록은 각 코드 모듈의 README·QA를 따릅니다.

- [개발 명세 안내·담당별 읽기 순서](specs/README.md)
- [01_요구사항_개발범위_정의서](specs/01_요구사항_개발범위_정의서.md)
- [02_백엔드_API_작업명세서](specs/backend/02_백엔드_API_작업명세서.md)
- [03_데이터_설계서](specs/common/03_데이터_설계서.md)
- [04_Agent_동작_판단_명세서](specs/common/04_Agent_동작_판단_명세서.md)
- [05_테스트_검수_기준서](specs/05_테스트_검수_기준서.md)
- [06_배포_운영_인계서](specs/06_배포_운영_인계서.md)
- [07_프론트엔드_개발명세서](specs/frontend/07_프론트엔드_개발명세서.md)
- [08_GUI_화면설계서](specs/frontend/08_GUI_화면설계서.md)
- [09_통합검토_반영내역](specs/09_통합검토_반영내역.md)
- [10_Job_Controller_모듈_설계서](specs/job-controller/10_Job_Controller_모듈_설계서.md)
- [11_RCA_Agent_모듈_설계서](specs/rca-agent/11_RCA_Agent_모듈_설계서.md)
- [12_보고서_Agent_모듈_설계서](specs/ops-agent/12_보고서_Agent_모듈_설계서.md)
- [13_Incident_모듈_설계서](specs/incident/13_Incident_모듈_설계서.md)
- [14_모듈간_호출과_공통실행_계약](specs/common/14_모듈간_호출과_공통실행_계약.md)

## 설계 검토 초안

아래 문서는 `specs/rca-agent/drafts/`에 모은 **팀 검토용 초안**입니다. 현행 명세를 자동으로 대체하지 않으며, 해당 제안을 구현 대상으로 지정한 작업에서 참고합니다. GPU 노드 RCA의 Knowledge DB·런북·조사 흐름을 제안하며 운영 DB에는 반영되지 않았습니다. Runbook-first 문서에는 일부 검색 코드의 구현·검증 기록도 있지만 전체 파이프라인의 통합·검수 완료를 뜻하지 않습니다. 합의한 내용만 현행 명세에 반영합니다.

- [GPU 노드 RCA Runbook 설계 초안](specs/rca-agent/drafts/gpu-node-rca-runbook-design.md)
- [Runbook-first 검색·조사 파이프라인 초안](specs/rca-agent/drafts/gpu-node-rca-runbook-first-pipeline.md)
- [GPU 노드 RCA Knowledge DB 참고 설계](specs/rca-agent/drafts/knowledge-db-reference.md)

보고서 Agent의 후속 개발 제안은 [워크플로우 검토안·도식](architecture/report-agent-workflow/README.md)에 별도로 보관합니다. 현재 통계·공개 RCA 소비 경로와 향후 개선 후보·LLM 조언·보완 조회를 구분한 설계 초안이며, 현행 12번 명세나 구현 완료 상태를 대체하지 않습니다.

## 구현 상태

2026-09-28 RCA·Runbook 후속 개발 상태는 [인수인계 문서](../rcca-agent/HANDOFF.md)에서 확인합니다. XID/SXID 초안의 기존 DB 필드 대응·등록/검토/발행·재현 명령은 [Runbook DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)를 따릅니다. 아래의 이전 제품 전체 기준과 구분하며, 로컬 구현·fixture 검증을 운영 배포 완료로 해석하지 않습니다.

현재 문서는 제품 코드 `775ab2f`의 Backend 초기화·클러스터 등록, 보고서 관측 집계·분할 조회·화면/다운로드, 운영 설정 변경을 반영했습니다. [산출물 안내](specs/README.md)에서 구현 범위와 QA를, [반영내역](specs/09_통합검토_반영내역.md)에서 변경·삭제 근거를 확인합니다.

Frontend는 실제 Go API를 호출합니다. Agent의 실제 프로세스 연동 시험 기록은 있으나 Grafana 데이터·LLM 응답은 fixture를 사용했으며, 운영 환경의 분석 품질 검수와 구분합니다. 각 모듈 QA의 날짜·환경·범위를 따르고 구버전 자료를 현행 검수 결과로 사용하지 않습니다.

## 실행·배포 안내

- [Frontend](../frontend/README.md) · [Backend](../backend/README.md)
- [Incident](../incident/README.md) · [Job Controller](../job-controller/README.md) · [두 Agent](../agents/README.md)
- [Helm 설치](helm-install.md) · [기존 배포 업그레이드](helm-upgrade-existing.md) · [CI·릴리스](ci-release.md)
