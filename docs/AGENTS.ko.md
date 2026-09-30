# AI Agent 컨텍스트

이 저장소의 팀 공통 지침 원본은 [CLAUDE.md](../CLAUDE.md)와 [.claude/rules/](../.claude/rules/)의 영어 파일에서 관리합니다.

프로젝트 브랜치 명명 규칙: 모든 코딩 도우미는 `feat/`, `fix/`, `docs/`처럼 작업 목적에 따른 접두사를 사용하며 `codex/`는 사용하지 않습니다. 공통 [Git 규칙](../.claude/rules/workflow.md#git-and-review)을 따릅니다.

저장소를 살펴보거나 수정·테스트·문서 작성·운영 명령을 실행하기 전에 다음을 따릅니다.

1. [CLAUDE.md](../CLAUDE.md)를 읽고 따릅니다. 해당 문서의 적용 범위와 더 하위 디렉터리의 `CLAUDE.md` 재정의도 포함합니다.
2. 모든 작업에서 아직 읽지 않은 [workflow.md](../.claude/rules/workflow.md)와 [safety.md](../.claude/rules/safety.md)를 읽습니다.
3. `CLAUDE.md`의 규칙 선택 표를 따라 영향을 받는 사용 모듈을 포함해 모든 관련 경로별 규칙을 읽습니다. 사용 중인 도구가 `.claude/rules/`를 자동으로 찾는다고 가정하지 않습니다.

한국어 참고 문서는 [CLAUDE.ko.md](CLAUDE.ko.md)와 [rules.ko.md](rules.ko.md)이며, 영어 원본을 기준으로 합니다. 이 시작 지침 파일은 코딩 도우미를 팀 규칙에 연결합니다. `rcca-agent/`, `ops-agent/`, `agents/`의 제품 Worker와는 별개입니다.

이 문서는 [루트 AGENTS.md](../AGENTS.md)의 한국어 참고용 번역입니다. 시작 지침 파일은 루트의 영어 `AGENTS.md`를 사용합니다.
