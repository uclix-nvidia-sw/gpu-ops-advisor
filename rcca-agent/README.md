# RCA Agent

Incident가 접수한 GPU·NVSwitch·노드 사건을 Job Controller에서 인수해 조사하는 Worker다. 현재 구현은 아래 코드와 계약을 기준으로 읽는다. 코드 병합과 운영 배포·Runbook 발행은 별개다.

## 현재 실행 흐름

1. JC claim의 사건 snapshot·대상·기간·예산·지식 revision을 고정한다. [workflow.py](src/rcca_agent/workflow.py)가 전체 흐름을 소유한다.
2. [retrieval.py](src/rcca_agent/retrieval.py)로 발행 Runbook을 검색하고 [runbook_contract.py](src/rcca_agent/runbook_contract.py)와 적용 조건을 검사한다. 검색 점수는 관련도이며 원인 확률이 아니다. 일반 조사 템플릿은 원인 확정 근거가 아니다.
3. 선택한 Runbook의 필수 관측을 [observation_agents.py](src/rcca_agent/observation_agents.py)에서 수집한다. 허용된 독립 조회는 공유 예산 안에서 병렬 실행한다.
4. 매 라운드 코드가 `evidence_evaluation`에 가용 사실·부족 조건·상충·선택 이유·종료 이유를 기록한다. 최초 수집과 보완 수집 1회, 최대 2라운드이며 보완 배치는 최대 3개 조회다.
5. 수집 종료 후 [synthesis_context.py](src/rcca_agent/synthesis_context.py)가 제한된 모델 입력을 만들고 [synthesis.py](src/rcca_agent/synthesis.py)가 원인 후보·한계를 생성하고 검증한다. 기존 근거로 판단하는 fast path에서는 원인 Synthesis를 생략한다.
6. [report.py](src/rcca_agent/report.py)가 근거가 연결된 보고서 문장을 구성하고 [report_editor.py](src/rcca_agent/report_editor.py)가 문장 ID의 우선순위를 선택한다. 선택되지 않은 원문도 보존한다. 결과·근거를 저장한 뒤 JC가 공개를 확정한다.

## 보완 조회 선택

선택 조건은 발행 Runbook의 `observation_plan`에 둔다. `selection.missing_any`는 부족 조건, `requires_all`은 필요한 scoped fact, `independent: true`는 독립 조회를 뜻한다. 조건을 만족한 항목을 priority와 query ID 순으로 선택한다. 명시적 `unexpected_evidence.additional_queries` 정책도 지원하되 단계의 selection 규칙을 우회하지 않는다.

규칙으로 배치를 선택하면 선택 LLM을 호출하거나 남는 자리를 LLM으로 채우지 않는다. `exploratory_llm: true`인 보조 단계만 JSON 방식의 탐색 선택에 참여한다. 이 표시는 필수 단계나 selection 규칙과 함께 사용할 수 없다. 설정되지 않은 단계는 `selection_conditions_missing`으로 남긴다.

탐색 LLM은 승인된 query ID만 최대 3개 반환할 수 있다. 잘못된 JSON 선택은 같은 예산·deadline 안에서 1회 수정한다. HTTP·deadline·예산 실패로 임의의 조회를 강제하지 않는다. 빈 선택은 조사 중단이며 근거 충분을 뜻하지 않는다.

## 관측과 판단의 경계

- 공통 [Observation](../shared/python/src/agent_common/observation.py)이 검증된 D binding과 Grafana MCP를 사용한다. 데이터소스 UID는 profile에 따라 발견하거나 고정하며, 요청 cluster_id와 허용 범위를 유지한다.
- [Fleet 이벤트](src/rcca_agent/fleet_events.py)는 보고된 오류와 장치 연결을 구조화한다. 로그 기록 시각·장비 발생 시각·현재 상태를 구분한다. PCI가 GPU 목록과 같아도 오류 장비 확정을 뜻하지 않으며, SXID의 스위치 주소를 GPU 목록으로 검증하지 않는다.
- 원본 관측은 evidence에 보존한다. 모델에는 크기를 제한한 뷰를 전달하며 `context_selection`과 입력 refs로 생략 범위를 기록한다. 수집 성공과 모델 입력 포함은 별개다.
- 현재 Synthesis는 구조·refs·한국어·숫자 표현·일부 원인 주장 패턴을 검사한다. 장치 신원 불확실성을 원인으로 제시하는 검사는 문장 표현 검사보다 먼저 적용한다. 수정 응답도 같은 기준을 통과해야 한다. 이 검사는 가설의 진실성이나 원인 분석 정확도 점수가 아니다.
- 수정은 예산·deadline 안에서 1회다. `validated_response`와 유효 부분만 남은 `validated_subset`을 구분한다. 진단에는 거절 사유·위치·hash를 남기고 거절 원문 전체는 저장하지 않는다.
- 원인 후보가 없을 때 보고된 증상 요약이 표시될 수 있다. 관측 요약, LLM 가설, Runbook 적용에 따른 판단을 같은 확정 원인으로 해석하지 않는다. 장비 조치는 수행하지 않는다.

## 보고서와 조회 호환

보고서는 사건·관측·원인 후보·권고·Runbook 지침·부족 근거를 연결한다. 최종 LLM은 새 원인이나 수치를 작성하지 않고 문장 ID를 정렬한다. 모델 미설정·확정 실패에는 코드 기본 보고서를 사용하며, 원격 실행 종료 불명은 공통 Worker의 격리 규칙을 따른다.

`operator_guidance`의 공통 스키마는 의미, 원인 관련 주의, 다음 확인, 출처를 표현한다. 지침은 해당 Runbook revision에 속하며 관측 사실이나 조치 승인을 대신하지 않는다. [작성·발행 안내](runbooks/DB-WORKFLOW.md)를 따른다.

새 작업의 수집 평가 기록은 `evidence_evaluation`이다. 과거 `unexpected_evidence`·`sufficiency` 기록은 기존 결과 조회용으로 남아 있고, `analysis.sufficiency`도 호환 요약으로 제공한다. `job.status`, `result_status`, Synthesis 상태, `narrative_status`는 각각 실행·판단 가능 범위·모델 응답·보고서 구성 상태다.

## Runbook 관리

- [목록](runbooks/CATALOG.md) · [등록·검토·발행](runbooks/DB-WORKFLOW.md) · [구조 계약](src/rcca_agent/runbook_contract.py).
- 오프라인 계약 검사는 `python -m rcca_agent.runbook_audit --help`로 입력 형식을 확인한다. 운영 DB를 변경하거나 발행하지 않는다.
- `python -m rcca_agent.runbook_transition --snapshot published.json --profile profile.json --output new-review-directory`는 제공된 발행 snapshot으로 전환 검토안을 만든다. 입력 hash를 확인하고 새 출력 폴더만 사용한다. Backend 호출·승인·발행은 없다.
- [265개 전환 검토](runbooks/transition-review-20261014.json)는 196개 계약 통과 제안과 69개 보류(정의 미확정 64개·정보성 5개)를 기록한다. 의미 검토·운영 발행 완료를 뜻하지 않는다. 원인·필수 근거·출처를 보존하고 발행 전 최신 revision/hash와 다시 대조해야 한다.

## 실행·검증·남은 과제

설치·환경 변수·timeout·Worker 실행은 [공통 Agent 안내](../agents/README.md), 검증 범위는 [Agent QA](../agents/QA.md), 상세 계약은 [RCA 명세](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md)를 따른다.

현재 미완료인 작업은 오류별 보완 조회·출처·지침의 의미 검토, 발행 profile 재검증, 실제 모델·장비 사건으로 원인 분석 품질 검증이다. Synthesis 후 적절성 점수로 다른 Runbook을 재선택하는 루프와 중간 언어 검사/최종 한국어 표현의 분리는 구현돼 있지 않다. 이를 변경할 때 RCA 결과를 읽는 Backend·Frontend·Ops와 검수 사례를 함께 정의해야 한다.
