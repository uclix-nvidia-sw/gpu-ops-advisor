# GPU Ops Advisor 문서 안내

현재 구현은 코드·테스트와 각 모듈 README를 기준으로 확인한다. 명세는 계약을, QA는 명시된 환경에서의 검증을 설명한다. Git 병합·로컬 검증·운영 배포를 서로 대신하는 증거로 사용하지 않는다.

## 공통 문서 관리

[AGENTS.md](../AGENTS.md) → [CLAUDE.md](../CLAUDE.md) → [공통 문서 관리 지침](../.claude/rules/workflow.md#shared-documentation)을 먼저 읽는다. 한국어 참고는 [팀 규칙](rules.ko.md#공통-문서-관리)이다.

같은 기능의 설명은 담당 문서 하나에서 갱신한다. 날짜별 작업 요약·인수인계 파일을 추가하지 않고 변경 과정은 PR에 남긴다. 대체된 설명은 제거하고 유효한 계약·검증 근거·참조는 담당 문서로 옮긴다.

## 현재 동작의 담당 문서

| 범위 | 구현·운영 안내 | 검증 근거 |
|---|---|---|
| 사건 접수 | [Incident](../incident/README.md) | [QA](../incident/QA.md) |
| 큐·claim·공개 | [Job Controller](../job-controller/README.md) | [QA](../job-controller/QA.md) |
| RCA·Runbook | [RCA Agent](../rcca-agent/README.md) | [Agent QA](../agents/QA.md) |
| 집계·기존 보고서 | [Ops Agent](../ops-agent/README.md) | [Agent QA](../agents/QA.md) |
| Worker·MCP·모델 설정 | [두 Agent 공통](../agents/README.md) | [Agent QA](../agents/QA.md) |
| API·일정·결과 조회 | [Backend](../backend/README.md) | [QA](../backend/QA.md) |
| 화면·표시 | [Frontend](../frontend/README.md) | [QA](../frontend/QA.md) |
| DB 소유권·공통 계약 | [Shared](../shared/README.md) | 모듈별 소비자 검사 |

## 상세 계약과 근거

- [네 탭 GUI 개편 계획](specs/frontend/07_프론트엔드_개발명세서.md) · [화면 설계](specs/frontend/08_GUI_화면설계서.md): 기존 세 화면 보존과 신규 탭의 화면·API·호환·검수 계약. 구현과 검증 상태는 모듈 README·QA에서 확인.
- [명세 목차](specs/README.md): 공통 데이터·판단·실행 계약과 모듈별 상세 규칙.
- 현재 RCA 실행은 [RCA Agent](../rcca-agent/README.md#현재-실행-흐름)를 따른다. 과거 결과 호환 참고: [RCA 평가 분리 설계·개발](specs/rca-agent/11_RCA_Agent_모듈_설계서.md#평가-분리-설계개발): 수집 상태·증거 해석·분석 품질의 분리, LLM 개입 위치, 함수별 변경과 검수 기준. 공통 결과·실행·화면 계약은 해당 문서로 연결한다.
- [공통 D binding](specs/common/d-binding-runtime.md) · [D 매핑](specs/common/d-query-mapping.md): RCA와 기존 O계열 보고서의 관측 계약.
- [집계 보고서 v1](specs/ops-agent/aggregate-report-v1.md): 신규 기본 보고서의 Ops 전용 쿼리·시간 집계·제한. 공통 D 경로와 구분한다.
- [Runbook 등록·발행](../rcca-agent/runbooks/DB-WORKFLOW.md) · [목록](../rcca-agent/runbooks/CATALOG.md): 저장소 원본과 발행 revision의 관계.
- [원천 근거](evidence/README.md): 수집원·단위·시각·신원 의미. 날짜가 오래됐다는 이유로 유일한 출처를 버리지 않는다.
- [아키텍처 뷰어](architecture/archify/README.md): 그림의 코드 기준일과 범위를 확인한다. 이후 실행 변경은 모듈 README를 따른다.

## 개발·배포

- [팀 담당과 협업](team-development.md) · [역할별 시작 프롬프트](agent-prompts.md).
- [작업·검증 규칙](../.claude/rules/workflow.md) · [안전 규칙](../.claude/rules/safety.md) · [한국어 번역](rules.ko.md).
- [설치](helm-install.md) · [기존 환경 업그레이드](helm-upgrade-existing.md) · [CI·릴리스](ci-release.md).
- 문서 변경 후 저장소 루트에서 `python tools/check_links.py`를 실행한다. 변경한 절의 anchor와 코드 블록의 명령은 별도로 확인한다.
