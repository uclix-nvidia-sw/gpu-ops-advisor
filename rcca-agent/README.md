# RCA Agent

Incident가 접수한 GPU·NVSwitch·노드 사건을 Job Controller에서 인수해 조사하는 Worker다. 현재 구현은 아래 코드와 계약을 기준으로 읽는다. 코드 병합과 운영 배포·Runbook 발행은 별개다.

## 현재 실행 흐름

1. JC claim의 사건 snapshot·대상·기간·예산·지식 revision을 고정한다. [workflow.py](src/rcca_agent/workflow.py)가 전체 흐름을 소유한다.
2. [retrieval.py](src/rcca_agent/retrieval.py)로 발행 Runbook을 검색하고 [runbook_contract.py](src/rcca_agent/runbook_contract.py)와 적용 조건을 검사한다. 검색 점수는 관련도이며 원인 확률이 아니다. 일반 조사 템플릿은 원인 확정 근거가 아니다.
3. 선택한 Runbook의 필수 관측을 [observation_agents.py](src/rcca_agent/observation_agents.py)에서 수집한다. 허용된 독립 조회는 공유 예산 안에서 병렬 실행한다.
4. 코드가 수집 상태와 형식·시각·식별자 정확 비교를 기록한다. [evidence_interpretation.py](src/rcca_agent/evidence_interpretation.py)의 LLM ①이 제한된 원문·관측에서 보고된 사실과 추론·미확인을 구분한다. 추론은 verified facts에 합치지 않는다.
5. [synthesis.py](src/rcca_agent/synthesis.py)의 LLM ②가 후보·한계를 작성한다. 기존 수치·참조 검증과 Runbook 후보·권고를 결합해 초안을 고정한다.
6. [analysis_review.py](src/rcca_agent/analysis_review.py)의 LLM ③이 초안 전체를 6개 평가 척도로 검토한다. 항목마다 판정·이유·근거를 남기며 초안 hash가 바뀌면 이전 판정을 재사용하지 않는다.
7. [evaluation.py](src/rcca_agent/evaluation.py)에서 의미 수정은 attempt당 최대 1회다. 조건부 보완 수집은 최대 1라운드·3개 조회이며 해석부터 다시 수행한다. `evidence_evaluation`의 기존 요건 기록과 `investigation_decision`의 다음 행동·종료 이유를 구분한다. fast path는 기존 규칙 판단을 유지하고 해석·Synthesis·검토를 생략한다.
8. [report.py](src/rcca_agent/report.py)가 상태·한계를 포함한 보고서 문장을 구성하고 [report_editor.py](src/rcca_agent/report_editor.py)가 문장 ID의 우선순위만 선택한다. 결과·근거를 저장한 뒤 JC가 공개를 확정한다.

## 보완 조회 선택

선택 조건은 발행 Runbook의 `observation_plan`에 둔다. `selection.missing_any`는 부족 조건, `requires_all`은 필요한 scoped fact, `independent: true`는 독립 조회를 뜻한다. 조건을 만족한 항목을 priority와 query ID 순으로 선택한다. 명시적 `unexpected_evidence.additional_queries` 정책도 지원하되 단계의 selection 규칙을 우회하지 않는다.

규칙으로 배치를 선택하면 선택 LLM을 호출하거나 남는 자리를 LLM으로 채우지 않는다. `exploratory_llm: true`인 보조 단계만 JSON 방식의 탐색 선택에 참여한다. 이 표시는 필수 단계나 selection 규칙과 함께 사용할 수 없다. 설정되지 않은 단계는 `selection_conditions_missing`으로 남긴다.

탐색 LLM은 승인된 query ID만 최대 3개 반환할 수 있다. 잘못된 JSON 선택은 같은 예산·deadline 안에서 1회 수정한다. HTTP·deadline·예산 실패로 임의의 조회를 강제하지 않는다. 빈 선택은 조사 중단이며 근거 충분을 뜻하지 않는다.


모델 토큰 예산 부족(`llm_budget_exhausted`)은 조회 예산과 구분한다. 이 경우에도 발행 Runbook의 명시적 조건·예상 밖 근거 정책이 허용하는 독립 조회는 남은 query budget·deadline 안에서 수행한다. LLM 탐색은 추가 호출하지 않는다. 검토가 acceptable이어도 충족된 명시적 보완 조회 조건은 먼저 수행하며, 검토 통과만으로 해당 조회를 생략하지 않는다. 최초 수집 → 해석 → 분석 → 검토 → 보완 수집 순서와 최대 2라운드·보완 3개 한도는 유지하며, 마지막 검토 실패는 정상 판정으로 바꾸지 않는다.

XID 79 저작 계획은 D44·D02·D06, SXID 11001은 D02·D06·D13을 조건부 보완 대상으로 둔다. D02 작업 라벨과 D06 Pod UID의 유효 시각을 조인한다. 사건에 GPU UUID가 없으면 같은 클러스터·서버의 XID 보고 PCI와 인벤토리가 유일하게 일치할 때만 관측 연결 대상으로 사용하며 원문 근거 참조를 보존한다. SXID PCI를 GPU PCI로 대체하거나 노드의 모든 Pod를 영향 작업으로 간주하지 않는다. 실제 실패·중단은 별도 근거가 필요하다.

`quality.collection_checks`는 오류 로그·작업 연결·FM 원본·토폴로지의 조회 ID, 수집 상태, 원본 근거와 추가 연결 요건을 기록한다. 자동 수집 결과는 권고 조치/분석 한계에 표시하며 추가 확인 사항에는 원천·조회 계획·신원 연결이 필요한 항목만 남긴다. 실패·빈 응답·부분 응답·예산으로 미수집한 항목은 연결 누락과 구분해 분석 한계에 보존한다. 기존 `missing_inputs`와 적격 권고는 변경하지 않는다.

FM 전용 원천은 선택 사항인 실행 프로파일 `rca.evidence_roles.fabric_manager_logs`와 `fabric_topology`에 **이미 등록된 조회 ID**로 연결한다. 해당 조회는 발행 Runbook 계획에도 포함되고 검증된 binding·scope·기간 조건을 만족해야 한다. 이 역할 선언은 조회 권한이나 topology 파서를 생성하지 않는다. 현재 기본 프로파일에는 전용 역할이 없으며 D13 일반 로그를 FM 포트 연결 근거로 승격하지 않는다. 기본 D13 raw binding은 클러스터 범위만 지원하므로 서버·장비로 좁힌 요청의 `binding_scope_unavailable`은 추가 연결 요건으로 표시한다. 현재 범위를 넓히거나 GPU 필터를 제거해 우회하지 않는다. 실제 포트 매핑에는 서버·NVSwitch PCI·source port·상대 GPU/스위치·유효 시각을 보존한 원천과 계약이 추가로 필요하다.

## 관측과 판단의 경계

- 공통 [Observation](../shared/python/src/agent_common/observation.py)이 검증된 D binding과 Grafana MCP를 사용한다. 데이터소스 UID는 profile에 따라 발견하거나 고정하며, 요청 cluster_id와 허용 범위를 유지한다.
- [Fleet 이벤트](src/rcca_agent/fleet_events.py)는 보고된 오류와 장치 연결을 구조화한다. 로그 기록 시각·장비 발생 시각·현재 상태를 구분한다. PCI가 GPU 목록과 같아도 오류 장비 확정을 뜻하지 않으며, SXID의 스위치 주소를 GPU 목록으로 검증하지 않는다.
- 원본 관측은 evidence에 보존한다. 모델에는 크기를 제한한 뷰를 전달하며 `context_selection`과 입력 refs로 생략 범위를 기록한다. 수집 성공과 모델 입력 포함은 별개다.
- 현재 Synthesis는 구조·refs·한국어·숫자 표현·일부 원인 주장 패턴을 검사한다. 장치 신원 불확실성을 원인으로 제시하는 검사는 문장 표현 검사보다 먼저 적용한다. 수정 응답도 같은 기준을 통과해야 한다. 이 검사는 가설의 진실성이나 원인 분석 정확도 점수가 아니다.
- 수정은 예산·deadline 안에서 1회다. `validated_response`와 유효 부분만 남은 `validated_subset`을 구분한다. 진단에는 거절 사유·위치·hash를 남기고 거절 원문 전체는 저장하지 않는다.
- 원인 후보가 없을 때 보고된 증상 요약이 표시될 수 있다. 관측 요약, LLM 가설, Runbook 적용에 따른 판단을 같은 확정 원인으로 해석하지 않는다. 장비 조치는 수행하지 않는다.

## 보고서와 조회 호환

보고서는 발생 내용 → 영향과 심각도 → 원인 분석 → 권고 조치 → 추가 확인 사항 순서로 구성한다(`quality.report.presentation=incident-first/1`). 참고 지침과 분석 한계는 근거와 함께 보존하며 화면에서는 접힌 보충 자료로 제공한다. 생산자 오류 이벤트가 있으면 발생 시각(KST)·서버·오류 장치·GPU 인벤토리 일치를 먼저 표시한다. 상태 보고만 있으면 동일 보고 안의 PCI–GPU 일치는 설명하되 사건 기준 시각을 오류 발생 시각으로 바꾸지 않는다. GPU–Pod 관측 연결과 업무 실패는 구분한다. 최종 LLM은 새 원인이나 수치를 작성하지 않고 문장 ID를 정렬한다. 모델 미설정·확정 실패에는 코드 기본 보고서를 사용하며, 원격 실행 종료 불명은 공통 Worker의 격리 규칙을 따른다.

적격 권고가 비어 있어도 선택된 발행 조사 Runbook의 조건부 권고는 출처·조건과 함께 표시한다. 이 표시가 `recommendations`의 실행 적격성이나 조치 수행 상태를 변경하지 않는다. 저장소 XID 79 작성 원본은 적용 모델·bare-metal 조건의 호스트 재시작과 조치 후 확인·재발 지원 요청을 명시한다. 운영 반영에는 새 Runbook revision의 검토·발행이 필요하며 기존 발행본은 불변이다.

품질 검토용 예산은 원인 분석의 유효 원문 근거가 모두 제거되지 않는 범위에서 예약한다. 기존 외부 예약과 총예산은 유지하며 예약 축소·남은 예산·원문 포함 가능 여부를 Synthesis의 `budget_allocation`에 기록한다. 축소된 예약은 후속 검토 성공을 보장하지 않는다. 실제 부족·출력 잘림·변경된 초안의 미검토 상태는 그대로 보존한다.

예산 조정은 수집/분석 결함 수정과 별도로 수행한다. `attempt_budget=32768`은 한 시도의 해석·분석·수정·검토가 공유하며 `token_budget=98304` 전체를 한 시도에서 사용할 수 있는 것은 아니다. 실제 재생 실험 후보는 RCA용 새 실행 프로파일의 `attempt_budget=65536`, `token_budget=196608`, `max_attempts=3`이다. 기본값과 운영 설정은 이 변경에서 올리지 않는다. 보완 수집 후 분석·최종 검토까지 완료되는지, 토큰 사용·지연·동시성 비용을 비교한 뒤 채택한다. 출력 잘림은 단계별 출력 상한 문제도 확인해야 하며 총예산 증액만으로 해결됐다고 보지 않는다.

`operator_guidance`의 공통 스키마는 의미, 원인 관련 주의, 다음 확인, 출처를 표현한다. 지침은 해당 Runbook revision에 속하며 관측 사실이나 조치 승인을 대신하지 않는다. [작성·발행 안내](runbooks/DB-WORKFLOW.md)를 따른다.

새 작업의 수집 평가 기록은 `evidence_evaluation`이다. 과거 `unexpected_evidence`·`sufficiency` 기록은 기존 결과 조회용으로 남아 있고, `analysis.sufficiency`도 호환 요약으로 제공한다. `job.status`, `result_status`, Synthesis 상태, `narrative_status`는 각각 실행·판단 가능 범위·모델 응답·보고서 구성 상태다.

증거 해석·품질 검토의 입력 크기 초과와 토큰 부족은 별도 사유와 `request_checks`로 기록한다. 두 조건이 함께 발생하면 모두 보존하며 검토 불가를 품질 통과로 표시하지 않는다. 모델 보고 토큰과 보수적 차감량도 구분한다. 상세 계약과 종료 처리는 [F0 설계](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md#모델-요청-제한-진단-f0)를 따른다. GUI의 개발측 RCA 결과에서 **워크플로우 디버깅**을 누르면 시도·단계별 사유, 입력·결과, 관련 근거를 확인할 수 있다.

## Runbook 관리

- [목록](runbooks/CATALOG.md) · [등록·검토·발행](runbooks/DB-WORKFLOW.md) · [구조 계약](src/rcca_agent/runbook_contract.py).
- 오프라인 계약 검사는 `python -m rcca_agent.runbook_audit --help`로 입력 형식을 확인한다. 운영 DB를 변경하거나 발행하지 않는다.
- `python -m rcca_agent.runbook_transition --snapshot published.json --profile profile.json --output new-review-directory`는 제공된 발행 snapshot으로 전환 검토안을 만든다. 입력 hash를 확인하고 새 출력 폴더만 사용한다. Backend 호출·승인·발행은 없다.
- [265개 전환 검토](runbooks/transition-review-20261014.json)는 196개 계약 통과 제안과 69개 보류(정의 미확정 64개·정보성 5개)를 기록한다. 의미 검토·운영 발행 완료를 뜻하지 않는다. 원인·필수 근거·출처를 보존하고 발행 전 최신 revision/hash와 다시 대조해야 한다.

## 실행·검증·남은 과제

설치·환경 변수·timeout·Worker 실행은 [공통 Agent 안내](../agents/README.md), 검증 범위는 [Agent QA](../agents/QA.md), 상세 계약은 [RCA 명세](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md)를 따른다.

현재 미완료인 작업은 오류별 보완 조회·출처·지침의 의미 검토, 발행 profile 재검증, 실제 모델·장비 사건으로 원인 분석 품질 검증이다. 중간 언어 검사/최종 한국어 표현의 분리도 구현돼 있지 않다.

[수집·증거·분석 품질 분리 설계·개발](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md#평가-분리-설계개발)은 별도 증거 해석·분석 검토 LLM, 제한된 수정·보완 수집, 결과·추적 필드와 Backend·Frontend·Ops 소비 범위를 정의한다. 현재 코드에 구현했으며 실행별 결과는 `quality.rca_evaluation`에서 구분한다. 평가 척도는 근거 연결·대상/시각·상충·대안·한계·증거 활용의 6항목이며, 이유와 refs를 GUI에서 확인한다. 실제 모델의 의미 평가 정확도와 운영 배포는 별도 검증 대상이다. 원인 정확도 점수나 자유로운 Runbook 재선택 루프를 추가하는 설계가 아니다. 공통 결과·실행·화면·검수의 담당 문서는 설계서에서 연결한다.
