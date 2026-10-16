# RCA Agent

Incident가 접수한 GPU·NVSwitch·노드 사건을 Job Controller에서 인수해 조사하는 Worker다. 현재 구현은 아래 코드와 계약을 기준으로 읽는다. 코드 병합과 운영 배포·Runbook 발행은 별개다.

## 현재 실행 흐름

1. JC claim의 사건 snapshot·대상·기간·예산·지식 revision을 고정한다. [workflow.py](src/rcca_agent/workflow.py)가 전체 흐름을 소유한다.
2. [retrieval.py](src/rcca_agent/retrieval.py)로 발행 Runbook을 검색하고 [runbook_contract.py](src/rcca_agent/runbook_contract.py)와 적용 조건을 검사한다. 검색 점수는 관련도이며 원인 확률이 아니다. 일반 조사 템플릿은 원인 확정 근거가 아니다.
3. 선택한 Runbook의 필수 관측을 [observation_agents.py](src/rcca_agent/observation_agents.py)에서 수집한다. 허용된 독립 조회는 공유 예산 안에서 병렬 실행한다.
4. 코드가 수집 상태와 형식·시각·식별자의 명확한 조건을 확인한다. 원문과 진단은 보존한다.
5. [통합 작성](src/rcca_agent/combined_synthesis.py)이 **증거 해석과 원인 분석을 한 번의 작성 LLM 요청**으로 처리한다. 출력은 보고서가 아닌 사실·추론·미확인·원인 후보·근거 참조를 담은 구조화된 RCA 자료다.
6. [독립 품질 검토](src/rcca_agent/analysis_review.py)가 전체 주장과 원본을 대조한다. 검토 실패가 같은 증거의 재작성이나 재검토 루프를 유발하지 않는다. 특정 가능한 부적절 주장을 코드로 보류하면 새 초안은 미검토로 기록하고 이전 검토 지적을 보존한다.
7. [Runbook 판단](src/rcca_agent/decision_policy.py)이 조사 목적의 필수 기준·차단 조건·같은 초안의 검토를 확인한다. 목적을 달성하면 선택 조회가 남아도 종료한다. 미달이면 허용된 필수 보완 조회 또는 한계 종료를 결정한다. 새 관측이 추가된 경우에만 다음 RCA 작성이 가능하다.
8. `rca_result_frozen`에 최종 RCA 근거 자료와 hash를 고정한다. [report.py](src/rcca_agent/report.py)는 이 자료를 최종 보고서로 구성한다. [report_editor.py](src/rcca_agent/report_editor.py)의 선택적 LLM은 이미 만든 문장 ID를 정렬하며 새로운 원인·근거를 생성하지 않는다. 실패하면 코드 보고서를 유지한다. `report_assembly`는 사용한 근거 자료 hash를 연결한다. 저장·공개는 기존 Worker/JC가 담당한다.

기본 작성 방식은 `combined`다. 비교·회귀용 profile의 `rca.generation_mode=separate`는 기존 해석·분석 호출을 유지하지만 같은 증거 재작성 제한은 동일하다. 한 attempt 안에서 원본 내용 hash를 비교하므로 UUID 변경·같은 응답 재수집·모델 입력 축약·검토 feedback은 새 증거가 아니다. 작성은 HTTP 오류·출력 잘림에도 재전송하지 않는다. 다른 명시적 작업/attempt의 재평가는 별도 실행이다. 핵심 분석 LLM 두 단계와 선택·보고서 정렬 호출을 합쳐 ‘전체 호출 두 번’이라고 표시하지 않는다. fast path, 기존 결과 읽기, 취소·원격 종료 불명 처리는 유지한다.

XID 79와 SXID 11001 작성 원본에 Runbook 1.1 `decision_policy`를 넣었다. 현재 목적은 **해당 대상·기간의 오류 보고 식별**이며 실제 고장 원인이나 회복 확인이 아니다. Python·Backend Go가 계약을 검증하고 GUI·Ops가 평가 schema 1/2를 읽는다. 운영 적용에는 새 Runbook revision 발행과 코드 배포가 필요하다. 실제 모델 비교·의미 품질은 아직 검증하지 않았다.

D09의 대상·기간·오류 보고, 필수 근거와 차단 조건, LLM의 한계 설명 및 같은 초안의 품질 검토가 모두 충족되면 `goal_achieved`로 종료한다. XID 79의 D44·D02·D11과 SXID 11001의 D02·D13은 이 목적에 선택 조회이므로 남아 있어도 실행하지 않는다. `evidence_evaluation`과 `investigation_decision`은 `decision_policy_status`(`applied`/`mixed`/`not_configured`)를 보존하며, 종료 결정에 `collected_queries`와 `deferred_queries`를 연결한다. GUI는 수집한 근거·목적 밖 선택 조회·미적용 사유를 구분한다. 구 발행 1.0에는 정책을 자동으로 덧씌우지 않는다. 운영 갱신은 [1.1 적용 절차](runbooks/DB-WORKFLOW.md#조사-완료-기준-11)를 따른다.

통합 프롬프트는 기존 분석·해석의 판단 규칙만 재사용하며, 출력 지시는 `interpretation`·`hypotheses`·`limitations`를 가진 JSON 객체 하나로 제공한다. 해석의 목록은 `interpretation` 내부에, Runbook 의미 기준이 있으면 `criterion_assessments`도 그 내부에 둔다. 분리 모드의 프롬프트와 기존 형식·참조·부분 성공 검증은 유지한다.

개발용 RCA의 **분석 요약·LLM 실행 기록**과 **워크플로우 단계 상세**는 요청 실패·호출 전 생략·응답 수신 후 검증 실패를 구분한다. `invalid_author_response`는 받은 통합 응답이 검증을 통과하지 못했다는 뜻이다. 그중 `author_shape`는 최상위 구조 오류이며, 해석·분석 내부의 형식·근거 오류는 각 세부 코드로 구분한다. 모두 연결 실패와는 다르다. HTTP 오류는 모델 서버 요청 실패로, `remote_call_state=unknown`은 통신 중단·원격 실행 상태 미확인으로 표시한다. 응답 횟수만으로 채택 여부를 판단하지 않으며, 거절된 응답 원문과 임의 추가 필드명은 저장하지 않는다. 통합 응답은 `diagnostics.validation_failures[].details`, 별도 증거 해석·품질 검토와 후속 조회 선택은 `validation_details[].details`에 검증 코드·규칙·실패한 필드와 목록 위치를 보존한다. 필수 필드 누락, 타입·길이 오류, 허용되지 않은 참조, Runbook 기준 key 불일치를 구분하며 JSON 파싱 실패와도 분리한다. 별도 해석·검토의 기존 1회 수정 요청에는 같은 세부 진단을 전달하고, 수정 성공 후에도 이전 실패 이력을 확인할 수 있다. `hypothesis_index`와 `limitation_index`는 0부터 시작하며 GUI는 1부터 표시한다. 각 영역의 첫 실패를 기록하고 거절된 원문·임의 필드명·예외 메시지는 저장하지 않는다. `analysis_invalid`·`interpretation_invalid`만 있는 과거 기록의 세부 원인은 추정하지 않는다. 작성 프롬프트는 검증기와 같은 조건을 명시한다. 근거 없는 `unknowns`에는 비어 있지 않은 `reason`이 필요하며, Runbook 판단은 `method=llm` 기준마다 revision을 포함한 전체 `key`로 한 번씩 답해야 한다. 근거 참조의 허용 범위와 채택 조건은 그대로 유지한다.

통합 응답은 **항목 단위로 채택**한다. 해석 목록의 한 항목, 원인 후보 하나, 한계 문장 하나가 검증에 실패하면 그 항목만 제외하고 `diagnostics.dropped_items[]`에 같은 코드·규칙·경로와 `action=dropped`를 남긴다. 제외된 항목에 의존하는 원인 후보(`finding_refs`)도 함께 제외된다. Runbook 의미 기준 답변이 잘못되거나, 결론을 제한하는 `unknowns`·`conflicts`·`limitations` 항목이 하나라도 제외되면 모든 기준을 `unknown`으로 두고 `criterion_withheld`를 기록하므로 목적 달성으로 이어지지 않는다. 제외된 항목이 `findings`뿐이면 기준 판단은 유지한다. 최상위 구조, 목록 타입, 해석 전체 형식 오류는 기존처럼 응답 전체를 거절한다. 재작성 호출은 추가하지 않는다. 작성 입력은 예산 계획과 같은 크기(`max_input_bytes`)를 사용하며, 형식 통과 검사 행보다 관측 행을, 같은 노드의 다른 GPU보다 보고된 GPU의 지표를 먼저 넣는다.

검토 완료와 검토 통과를 구분한다. 검토 지적을 반영해 코드가 주장을 제외하면 `review_claims_withheld` 사유와 이전 검토 ID를 가진 초안을 저장한다. 뒤의 `draft_changed_after_review`·`attempts=0` 기록은 **변경 초안 미검토** 상태이며 추가 LLM 호출이 아니다. GUI는 검토 판정·미실행·주장 제외를 구분하고, 상세 코드·식별값은 접어서 표시한다. 과거 초안은 같은 작업·시도·초안 식별값의 미실행 검토 기록이 연결되는 경우에만 변경 초안으로 표시한다.

회귀 검사는 [통합 프롬프트 계약](../agents/tests/test_rca_author_prompt.py)과 [GUI 실패 구분](../frontend/src/components/RcaModelFailure.test.tsx)을 포함한다. fixture 통과와 실제 운영 모델의 출력 개선은 별도 검증이다.

## 보완 조회 선택

선택 조건은 발행 Runbook의 `observation_plan`에 둔다. `selection.missing_any`는 부족 조건, `requires_all`은 필요한 scoped fact, `independent: true`는 독립 조회를 뜻한다. 조건을 만족한 항목을 priority와 query ID 순으로 선택한다. 명시적 `unexpected_evidence.additional_queries` 정책도 지원하되 단계의 selection 규칙을 우회하지 않는다.

규칙으로 배치를 선택하면 선택 LLM을 호출하거나 남는 자리를 LLM으로 채우지 않는다. `exploratory_llm: true`인 보조 단계만 JSON 방식의 탐색 선택에 참여한다. 이 표시는 필수 단계나 selection 규칙과 함께 사용할 수 없다. 설정되지 않은 단계는 `selection_conditions_missing`으로 남긴다.

탐색 LLM은 승인된 query ID만 최대 3개 반환할 수 있다. 잘못된 JSON 선택은 같은 예산·deadline 안에서 1회 수정한다. HTTP·deadline·예산 실패로 임의의 조회를 강제하지 않는다. 빈 선택은 조사 중단이며 근거 충분을 뜻하지 않는다.


모델 토큰 예산 부족(`llm_budget_exhausted`)은 조회 예산과 구분한다. 이 경우에도 발행 Runbook의 명시적 조건·예상 밖 근거 정책이 허용하는 독립 조회는 남은 query budget·deadline 안에서 수행한다. LLM 탐색은 추가 호출하지 않는다. 정책 없는 구 Runbook은 검토가 acceptable이어도 기존 명시적 보완 조회 조건을 유지한다. Runbook 1.1은 위의 목적 달성 조건을 먼저 확인한다. 최초 수집 → RCA 작성 → 독립 검토 → 필요한 보완 수집 순서와 최대 2라운드·보완 3개 한도는 유지하며, 마지막 검토 실패는 정상 판정으로 바꾸지 않는다.

XID 79 저작 계획은 D44·D02·D11(전력), SXID 11001은 D02·D13을 조건부 보완 대상으로 둔다. D02 작업 라벨과 D06 Pod UID의 유효 시각을 조인한다. 사건에 GPU UUID가 없으면 같은 클러스터·서버의 XID 보고 PCI와 인벤토리가 유일하게 일치할 때만 관측 연결 대상으로 사용하며 원문 근거 참조를 보존한다. SXID PCI를 GPU PCI로 대체하거나 노드의 모든 Pod를 영향 작업으로 간주하지 않는다. 실제 실패·중단은 별도 근거가 필요하다.

`quality.collection_checks`는 오류 로그·FM 원본·토폴로지의 조회 ID, 수집 상태, 원본 근거와 추가 연결 요건을 기록한다. 자동 수집 결과는 권고 조치/분석 한계에 표시하며 추가 확인 사항에는 원천·조회 계획·신원 연결이 필요한 항목만 남긴다. 실패·빈 응답·부분 응답·예산으로 미수집한 항목은 연결 누락과 구분해 분석 한계에 보존한다. RCA 범위는 GPU 노드이므로 GPU–Pod(쿠버네티스 작업) 연결은 요청하지 않으며, 이전 Worker가 저장한 `workload_identity` 항목도 보고서에 표시하지 않는다. 기존 `missing_inputs`와 적격 권고는 변경하지 않는다.

FM 전용 원천은 선택 사항인 실행 프로파일 `rca.evidence_roles.fabric_manager_logs`와 `fabric_topology`에 **이미 등록된 조회 ID**로 연결한다. 해당 조회는 발행 Runbook 계획에도 포함되고 검증된 binding·scope·기간 조건을 만족해야 한다. 이 역할 선언은 조회 권한이나 topology 파서를 생성하지 않는다. 현재 기본 프로파일에는 전용 역할이 없으며 D13 일반 로그를 FM 포트 연결 근거로 승격하지 않는다. 기본 D13 raw binding은 클러스터 범위만 지원하므로 서버·장비로 좁힌 요청의 `binding_scope_unavailable`은 추가 연결 요건으로 표시한다. 현재 범위를 넓히거나 GPU 필터를 제거해 우회하지 않는다. 실제 포트 매핑에는 서버·NVSwitch PCI·source port·상대 GPU/스위치·유효 시각을 보존한 원천과 계약이 추가로 필요하다.

## 관측과 판단의 경계

- 공통 [Observation](../shared/python/src/agent_common/observation.py)이 검증된 D binding과 Grafana MCP를 사용한다. 데이터소스 UID는 profile에 따라 발견하거나 고정하며, 요청 cluster_id와 허용 범위를 유지한다.
- [Fleet 이벤트](src/rcca_agent/fleet_events.py)는 보고된 오류와 장치 연결을 구조화한다. 로그 기록 시각·장비 발생 시각·현재 상태를 구분한다. PCI가 GPU 목록과 같아도 오류 장비 확정을 뜻하지 않으며, SXID의 스위치 주소를 GPU 목록으로 검증하지 않는다.
- 원본 관측은 evidence에 보존한다. 모델에는 크기를 제한한 뷰를 전달하며 `context_selection`과 입력 refs로 생략 범위를 기록한다. 수집 성공과 모델 입력 포함은 별개다.
- 현재 Synthesis는 구조·refs·한국어·숫자 표현·일부 원인 주장 패턴을 검사한다. 장치 신원 불확실성을 원인으로 제시하는 검사는 문장 표현 검사보다 먼저 적용한다. 수정 응답도 같은 기준을 통과해야 한다. 이 검사는 가설의 진실성이나 원인 분석 정확도 점수가 아니다.
- 수정은 예산·deadline 안에서 1회다. `validated_response`와 유효 부분만 남은 `validated_subset`을 구분한다. 진단에는 거절 사유·위치·hash를 남기고 거절 원문 전체는 저장하지 않는다.
- 원인 후보가 없을 때 보고된 증상 요약이 표시될 수 있다. 관측 요약, LLM 가설, Runbook 적용에 따른 판단을 같은 확정 원인으로 해석하지 않는다. 장비 조치는 수행하지 않는다.

## 보고서와 조회 호환

보고서는 발생 내용 → 영향과 심각도 → 원인 분석 → 권고 조치 → 추가 확인 사항 순서로 구성한다(`quality.report.presentation=incident-first/1`). 참고 지침과 분석 한계는 근거와 함께 보존하며 화면에서는 접힌 보충 자료로 제공한다. 사건 근거 요약이 본문을 작성한 결과는 `incident-first/2`로 표시하며, 이때 참고 지침은 **이 오류에 대한 참고 안내** 본문 섹션으로 보이고 발행본의 일반 확인 절차·조사 방향 문구는 사건별 문장으로 대체한다. 생산자 오류 이벤트가 있으면 발생 시각(KST)·서버·오류 장치·GPU 인벤토리 일치를 먼저 표시한다. 상태 보고만 있으면 동일 보고 안의 PCI–GPU 일치는 설명하되 사건 기준 시각을 오류 발생 시각으로 바꾸지 않는다. GPU–Pod 관측 연결과 업무 실패는 구분한다. 최종 LLM은 새 원인이나 수치를 작성하지 않고 문장 ID를 정렬한다. 모델 미설정·확정 실패에는 코드 기본 보고서를 사용하며, 원격 실행 종료 불명은 공통 Worker의 격리 규칙을 따른다.

단일 생산자 오류 이벤트에는 `quality.incident_findings`(`incident-findings/2`)를 코드로 계산해 보고서 본문에 사용한다. 이벤트 PCI 주소의 GPU UUID를 Fleet 인벤토리·Fleet 상태 보고 원문·수집 지표 라벨(`pci_bus_id`)과 대조해 `corroborated`(서로 다른 생산자 2개 이상 일치)·`single_source`·`conflicting`으로 표시하고, 충돌하면 오류 GPU와 복구 권고를 특정하지 않는다. 같은 근거에서 GPU 모델·드라이버, 이벤트 전후 Fleet 상태 보고 전이와 회복 보고 유무(Loki 기록 시각), 해당 GPU의 카운터 증가량·게이지 구간 값(같은 노드 GPU 비교 포함)을 요약한다. SXID는 이벤트의 NVSwitch PCI 주소를 Fleet 이벤트·상태 보고 원문으로 확인하고, 그 주소가 수집된 GPU PCI 주소와 겹치면 `conflicting`으로 처리한다. 스위치 포트·연결 GPU·파티션은 원천이 없어 미확인으로 남긴다. 선택된 발행 Runbook의 `NVIDIA 적용`·`NVIDIA 조치 분류`·`Fleet 고정 카탈로그`·`GPUd 고정 정의/기본 action`·`적용 조건(…에는 적용하지 않는다)` 문장을 읽어 모델·플랫폼 적용 여부, 조치, 심각도와 참고 안내를 작성한다. 조치는 NVIDIA 즉시 조치를 우선하고, 없거나 이번 제품군이 목록에 없으면 Fleet, 그다음 GPUd 기본 조치를 쓴다. 미정의 값(nil·미정의·미기재)은 조치로 쓰지 않는다. 발행본 의미 문장은 첫 문장만, 조건형 원인 메모(“…라면 … 등을 조사할 수 있습니다”)는 원인 후보만 사용한다.

원인 분석은 판단 → 확인한 근거 → 남은 원인 후보 순서다. 권고 조치는 조치 유형별로 한 문단에 둔다. 재시작류(RESTART_BM·RESTART_VM·RESET_GPU·REBOOT_SYSTEM)는 근거 보존(Grafana 수집분은 자동 완료, 재시작 전 호스트 진단 자료만 운영자) → 작업 확인·배출 → 복구(VM·시험 주입 예외 명시) → 조치 후 확인 → 재발 대응(CONTACT_SUPPORT 또는 HARDWARE_INSPECTION) 순서다. RESTART_APP은 애플리케이션 재시작, CONTACT_SUPPORT는 지원 요청, IGNORE는 즉시 조치 불필요, 그 밖의 NVIDIA 코드는 해당 절차 안내로 쓰며 작업 배출·재시작 문구를 붙이지 않는다. 제외 모델·플랫폼이면 조치를 권고하지 않는다. Fleet 원천 권고는 같은 조치일 때만 같다고 쓴다. 영향 문장의 "사용할 수 없는 상태"는 Runbook 분류가 GPU 접근 상실(`gpu_access_loss`)일 때만 쓴다. 추가 확인 사항에는 수집 지표로 판정할 수 없는 운영 모드·GPU 모델(라벨 미수집 시)·시험 주입 여부·커널 AER·스위치 포트 연결과 장치 연결이 교차 확인되지 않은 경우만 남긴다. 이 요약은 보고된 식별자 일치와 표본 기록이며 `fact_eligible`, `recommendations`, `result_status`를 바꾸지 않는다.

적격 권고가 비어 있어도 선택된 발행 조사 Runbook의 조건부 권고는 출처·조건과 함께 표시한다. 이 표시가 `recommendations`의 실행 적격성이나 조치 수행 상태를 변경하지 않는다. 저장소 XID 79·SXID 11001 작성 원본은 자동 보존 범위와 조치 전 호스트 진단 자료, 적용 조건의 재시작, 조치 후 확인·재발 대응을 명시한다([검토 기록](runbooks/incident-report-review-20261015.json)). 운영 반영에는 새 Runbook revision의 검토·발행이 필요하며 기존 발행본은 불변이다.

품질 검토용 예산은 원인 분석의 유효 원문 근거가 모두 제거되지 않는 범위에서 예약한다. 기존 외부 예약과 총예산은 유지하며 예약 축소·남은 예산·원문 포함 가능 여부를 Synthesis의 `budget_allocation`에 기록한다. 축소된 예약은 후속 검토 성공을 보장하지 않는다. 실제 부족·출력 잘림·변경된 초안의 미검토 상태는 그대로 보존한다.

예산 조정은 수집/분석 결함 수정과 별도로 수행한다. `attempt_budget=32768`은 한 시도의 작성·검토·선택·보고서 정렬이 공유하며 `token_budget=98304` 전체를 한 시도에서 사용할 수 있는 것은 아니다. 실제 재생 실험 후보는 RCA용 새 실행 프로파일의 `attempt_budget=65536`, `token_budget=196608`, `max_attempts=3`이다. 기본값과 운영 설정은 이 변경에서 올리지 않는다. 보완 수집 후 분석·최종 검토까지 완료되는지, 토큰 사용·지연·동시성 비용을 비교한 뒤 채택한다. 출력 잘림은 단계별 출력 상한 문제도 확인해야 하며 총예산 증액만으로 해결됐다고 보지 않는다.

`operator_guidance`의 공통 스키마는 의미, 원인 관련 주의, 다음 확인, 출처를 표현한다. 지침은 해당 Runbook revision에 속하며 관측 사실이나 조치 승인을 대신하지 않는다. [작성·발행 안내](runbooks/DB-WORKFLOW.md)를 따른다.

새 작업의 수집 평가 기록은 `evidence_evaluation`이다. 과거 `unexpected_evidence`·`sufficiency` 기록은 기존 결과 조회용으로 남아 있고, `analysis.sufficiency`도 호환 요약으로 제공한다. `job.status`, `result_status`, Synthesis 상태, `narrative_status`는 각각 실행·판단 가능 범위·모델 응답·보고서 구성 상태다.

증거 해석·품질 검토의 입력 크기 초과와 토큰 부족은 별도 사유와 `request_checks`로 기록한다. 두 조건이 함께 발생하면 모두 보존하며 검토 불가를 품질 통과로 표시하지 않는다. 모델 보고 토큰과 보수적 차감량도 구분한다. 상세 계약과 종료 처리는 [F0 설계](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md#모델-요청-제한-진단-f0)를 따른다. GUI의 개발측 RCA 결과에서 **워크플로우 디버깅**을 누르면 시도·단계별 사유, 입력·결과, 관련 근거를 확인할 수 있다.

검토 예약 때문에 분석에 관측을 하나도 담지 못하면, 규칙 기반 검토 초안·보존된 검토 뷰·기본 출력 상한을 보호하는 하한 안에서 예약을 줄인다. 두 요구를 함께 감당하지 못하면 기존 예약을 유지한다. 총예산과 호출 제한은 그대로이며 `synthesis.budget_allocation`에 전후 예약·하한·이유를 남긴다. 이후 모델이 추가하는 주장이나 재시도까지 검토 완료를 보장하는 정책은 아니다. 산식과 회귀 기준은 [11의 통합 개선안](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md)을 따른다.

Runbook 본문은 적용·호환 조건을 거쳐 조사에 사용할 지침이 정해지면 최초 수집 전에 한 번 보존한다. 검색 후보 전체를 저장하지 않는다. 조사 확장으로 새 지침을 선택하면 그 본문만 추가하며, 분석·권고·검토는 같은 근거 ID를 재사용한다. 선택 기록과의 연결은 원문 `quality.selection_evidence_id`, 최초 계획의 `selection_evidence_id/evidence_refs`, 확장 계획의 `evidence_refs`로 남긴다. 기존 결과의 저장 순서와 링크는 재작성하지 않는다.

## Runbook 관리

- [목록](runbooks/CATALOG.md) · [등록·검토·발행](runbooks/DB-WORKFLOW.md) · [구조 계약](src/rcca_agent/runbook_contract.py).
- 오프라인 계약 검사는 `python -m rcca_agent.runbook_audit --help`로 입력 형식을 확인한다. 운영 DB를 변경하거나 발행하지 않는다.
- `python -m rcca_agent.runbook_transition --snapshot published.json --profile profile.json --output new-review-directory`는 제공된 발행 snapshot으로 전환 검토안을 만든다. 입력 hash를 확인하고 새 출력 폴더만 사용한다. Backend 호출·승인·발행은 없다.
- [265개 전환 검토](runbooks/transition-review-20261014.json)는 196개 계약 통과 제안과 69개 보류(정의 미확정 64개·정보성 5개)를 기록한다. 의미 검토·운영 발행 완료를 뜻하지 않는다. 원인·필수 근거·출처를 보존하고 발행 전 최신 revision/hash와 다시 대조해야 한다.

## 오프라인 RCA 재생

[재생 도구](../agents/tests/rca_replay.py)는 기존 `workflow.run()` → `evaluate_analysis()` → 조립·검토·보완 조회·종료를 그대로 실행한다. 검토자만 시험할 때는 `review_analysis()`를 직접 사용한다. 모델 전송은 `httpx.MockTransport`, 조회는 **도구 이름과 전체 요청 인자가 일치하는 고정 응답**으로 대체한다. 실제 MCP·모델·DB·JC 발행에 연결하지 않으며 운영 실행 설정은 바꾸지 않는다.

공통 Agent 개발 환경을 설치한 뒤 저장소 루트에서 실행한다. 결과에는 입력 원문이 포함되므로 합성 또는 비식별화한 자료만 사용하고 출력은 `.local/`에 둔다. 새 출력 폴더만 허용하며 기존 결과를 덮어쓰지 않는다.

```bash
python agents/tests/rca_replay.py --case enough_budget --output .local/rca-replay/before
python agents/tests/rca_replay.py --input .local/rca-replay/before/input.json --baseline .local/rca-replay/before/result.json --output .local/rca-replay/after
python -m pytest -c agents/pytest.ini agents/tests/test_rca_replay.py -q
```

- `summary.md`: 라운드별 해석·분석·검토, 실패 이유, 추가 수집·종료를 한국어로 읽는 요약.
- `input.json`: 사건·대상·기간·profile·Runbook 내용/revision/hash·총예산·출력 cap·조회와 응답 fixture·사전 기대 판정을 고정한 입력. Runbook은 합성 revision이며 운영 발행본이 아니다.
- `result.json`: 입력 hash와 실행한 Worker/공통 Python 소스 hash, 실제 전송 입력·프롬프트·cap·완료 사유·응답 크기/hash·예산 차감, **검증 후 보존된** 해석·분석·검토·결정·최종 결과. 거절된 모델 원문은 실행 추적에 복사하지 않는다. 입력 fixture 자체는 별도로 남는다.
- `comparison.json`: 같은 입력 hash일 때만 호출·부분 성공·잘림·검토·다음 행동의 차이를 비교한다. 의미상 타당성은 원문과 함께 사람이 확인해야 한다. 소스가 바뀐 뒤 `--case`로 새 입력을 만들지 말고 저장한 `--input`을 재사용한다.

[기본 사례](../agents/tests/rca_replay_cases.py)는 충분 예산, 의도적 부족, 해석만 보존, 보완 후 검토 변경, 검토 수락 후 명시 규칙 조회를 포함한다. `review_limited/overclaim/typo/gap/conflict/unused`는 적절·과장 쌍과 오타·관측 공백·모순·증거 미사용의 검토자 단독 사례다. 실행 전 기대 판정은 도구용 제안이며 사람의 의미 평가 합의 완료로 간주하지 않는다.

누락·모호한 조회 fixture, 모델 응답 fixture 소진, 응답 참조 바인딩 실패는 `partial` 재생으로 표시한다. 모델 usage를 제공하지 않은 경우 실제 사용량을 0으로 해석하지 않고 미기록과 보수적 차감을 나눈다. fixture 토큰값·실행시간은 운영 비용이나 모델 지연의 실측이 아니다. 이 도구는 **현행 분리 경로의 최소 비교 기반**이며 통합 호출·새 Runbook 판단 정책·실제 모델 의미 평가가 구현됐다는 뜻이 아니다. 이후 변경은 같은 입력으로 다시 재생한다.

## 실행·검증·남은 과제

설치·환경 변수·timeout·Worker 실행은 [공통 Agent 안내](../agents/README.md), 검증 범위는 [Agent QA](../agents/QA.md), 상세 계약은 [RCA 명세](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md)를 따른다.

현재 미완료인 작업은 오류별 보완 조회·출처·지침의 의미 검토, 발행 profile 재검증, 실제 모델·장비 사건으로 원인 분석 품질 검증이다. 중간 언어 검사/최종 한국어 표현의 분리도 구현돼 있지 않다.

[수집·증거·분석 품질 분리 설계·개발](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md#평가-분리-설계개발)은 별도 증거 해석·분석 검토 LLM, 제한된 수정·보완 수집, 결과·추적 필드와 Backend·Frontend·Ops 소비 범위를 정의한다. 현재 코드에 구현했으며 실행별 결과는 `quality.rca_evaluation`에서 구분한다. 평가 척도는 근거 연결·대상/시각·상충·대안·한계·증거 활용의 6항목이며, 이유와 refs를 GUI에서 확인한다. 실제 모델의 의미 평가 정확도와 운영 배포는 별도 검증 대상이다. 원인 정확도 점수나 자유로운 Runbook 재선택 루프를 추가하는 설계가 아니다. 공통 결과·실행·화면·검수의 담당 문서는 설계서에서 연결한다.
