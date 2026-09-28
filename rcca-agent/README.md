# rcca-agent

다른 PC나 새 세션에서 이어받을 때는 [RCA·Runbook 개발 인수인계](HANDOFF.md)를 먼저 읽습니다. 구현 파일, 검증 범위, 미완료 항목과 다음 작업을 연결했습니다.

`11_RCA_Agent_모듈_설계서.md`에 따른 Incident 전용 RCA Worker입니다. JC kind는 `rca`입니다.

`src/rcca_agent/workflow.py`에 snapshot 검사·호환 Runbook·조건 검사·등록 조사·근거/원인 후보/권고가 있고, `procedures.py`에 GPU 접근 이상·GPU와 Pod·작업 진행 이상·다중 장치 사건 네 절차를 등록했습니다. 저장/발행은 LLM 도구가 아니며 Worker가 처리합니다. NAT 설정과 프롬프트를 보고서 Agent와 분리했습니다.

2026-09-28 구현은 하나의 NAT workflow 안에서 **Orchestrator → 병렬 Observation Sub-agent → 코드 충분성 판정 → 최대 1회 재조사 → 도구 없는 Synthesis → 결과 검증·저장 → JC 공개**로 동작합니다. `observation_agents.py`는 query별 독립 상태·예약 예산으로 수집하고 형제 실패를 격리하며 취소 시 task를 회수합니다. `synthesis.py`는 실제 수집 근거를 해석하되 모델 원인은 항상 candidate로 유지합니다. 충분한 기존 증거와 적용 Runbook이 있으면 MCP·LLM을 모두 생략합니다.

Runbook 조회·검색·조건 검사는 코드로 수행합니다. 전용 Runbook이 없으면 `rca.general_runbook_key`의 승인·고정 일반 Runbook을 사용합니다. 일반 Runbook까지 없으면 `approved_runbook` 부족을 저장하고 조사하지 않습니다. 기본 key `RB-GENERAL-GPU-NODE`는 콘텐츠를 자동 생성·발행하지 않으며, [Runbook 초안](runbooks/README.md)도 운영 발행본이 아닙니다. `limits.max_concurrency` 기본값은 3이며 전체 query/discovery 예산을 공유합니다.

실제 로컬 LLM endpoint는 추후 연결합니다. 미구성이면 유효 근거를 보존하고 `synthesis_unconfigured`를 기록합니다. 기본 health parser는 error_code fact를 만들지 않으며 운영 producer/binding/freshness 계약이 필요합니다. 현재 Worker 입력은 **1.3**입니다. 1.4 목적 자동 선택·이력 고정·선택 trace와 운영 분석 품질 검수는 [보완 계획](../docs/specs/rca-agent/implementation-plan-20260928.md)의 후속 단계입니다.

설치·환경 설정·Docker·최소 테스트/E2E: [공통 실행 안내](../agents/README.md), [검증 기록](../agents/QA.md).

```powershell
.venv/Scripts/python.exe -m rcca_agent.main
```

저장소 루트에서 실행합니다. `incident_id`가 없는 임의 증상 요청은 받지 않습니다.

Incident가 생성한 `incident_snapshot.alert`를 원본 알람 증거로 읽습니다. 기존 `incident_snapshot.evidence` 형식도 지원합니다. 원본 snapshot과 hash는 변경하지 않으며, 알람의 필드를 `verified_facts`로 승격하지 않습니다. `alert` 형식은 등록된 purpose에 따라 조사 절차를 선택하고 실제 수집 증거로 판단합니다. 두 증거 필드가 모두 없거나 `alert`가 객체가 아니면 Worker 입력 검증 단계에서 거부합니다.
