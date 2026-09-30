# ops-agent

`12_보고서_Agent_모듈_설계서.md`에 따른 운영 보고서 Worker입니다. JC kind는 `report`입니다.

`src/ops_agent/workflow.py`의 O01~O11 수집 계획을 순차 실행합니다. 집계는 공통 결정적 산식을 쓰고, LLM은 검증된 사실 선택만 수행합니다. 고정된 절대 기간·DB snapshot·공개 RCA 참조·주제별 partial/blocked 상태를 보존합니다. HTML/CSV는 저장한 수치 레지스트리에서 생성합니다.

후속 개발의 기준은 [12번 보고서 설계서](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md)의 OP-01~07·개발 순서입니다. 2026-09-30에 Orchestrator → query별 병렬 Observation Sub-agent → 통계·제한적 보완 조회 → 도구 없는 단일 Synthesis → 검증·공개 구조를 개발 목표로 반영했습니다. 같은 Worker/job/lease와 전체 예산을 사용하며 현재 구현된 기능은 아닙니다. [상세 Mermaid 흐름도](../docs/architecture/report-agent-workflow/detailed-workflow.md)는 이 기준을 설명하고, [05 T60~T65](../docs/specs/05_테스트_검수_기준서.md)는 추가 검수 기대값입니다. 제품 구현은 대기 중입니다.

설치·환경 설정·Docker·최소 테스트/E2E: [공통 실행 안내](../agents/README.md), [검증 기록](../agents/QA.md).

```powershell
.venv/Scripts/python.exe -m ops_agent.main
```

저장소 루트에서 실행합니다. 일정 계산, RCA 생성, 별도 접수 API는 제공하지 않습니다.
