# rcca-agent

`11_RCA_Agent_모듈_설계서.md`에 따른 Incident 전용 RCA Worker입니다. JC kind는 `rca`입니다.

`src/rcca_agent/workflow.py`에 snapshot 검사·호환 Runbook·조건 검사·등록 조사·근거/원인 후보/권고가 있고, `procedures.py`에 GPU 접근 이상·GPU와 Pod·작업 진행 이상·다중 장치 사건 네 절차를 등록했습니다. 저장/발행은 LLM 도구가 아니며 Worker가 처리합니다. NAT 설정과 프롬프트를 보고서 Agent와 분리했습니다.

설치·환경 설정·Docker·최소 테스트/E2E: [공통 실행 안내](../agents/README.md), [검증 기록](../agents/QA.md).

```powershell
.venv/Scripts/python.exe -m rcca_agent.main
```

저장소 루트에서 실행합니다. `incident_id`가 없는 임의 증상 요청은 받지 않습니다.
