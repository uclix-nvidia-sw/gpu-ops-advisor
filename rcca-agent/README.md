# RCA Agent

Incident가 접수한 GPU·NVSwitch·노드 사건을 Job Controller에서 인수해 조사하는 Worker다. 현재 구현은 아래 코드와 계약을 기준으로 읽는다. 코드 병합과 운영 배포·Runbook 발행은 별개다.

## 현재 실행 흐름

1. JC claim의 사건 snapshot·대상·기간·예산·지식 revision을 고정한다. [workflow.py](src/rcca_agent/workflow.py)가 전체 흐름을 소유한다.
2. [retrieval.py](src/rcca_agent/retrieval.py)로 발행 Runbook을 검색하고 [runbook_contract.py](src/rcca_agent/runbook_contract.py)와 적용 조건을 검사한다. 검색 점수는 관련도이며 원인 확률이 아니다. 일반 조사 템플릿은 원인 확정 근거가 아니다.
3. XID 79·SXID 11001의 새 계획은 아래 단일 수집 경로를 따른다. 다른 기존 발행본은 선택한 Runbook의 필수 관측을 [observation_agents.py](src/rcca_agent/observation_agents.py)에서 수집한다. 허용된 독립 조회는 공유 예산 안에서 병렬 실행한다.
4. 기존 발행본에서는 코드가 수집 상태와 형식·시각·식별자의 명확한 조건을 확인한다. 원문과 진단은 보존한다. 필수 D09가 실패·불완전하면 같은 라운드에서 한 번만 다시 조회하고, 이전 결과는 `superseded_by_retry`로 남긴다. 이어서 [fleet_events.match_alert](src/rcca_agent/fleet_events.py)가 알람(Fleet `Unhealthy` 상태 보고)과 D09의 같은 사유 상태 보고·kmsg 이벤트를 대조한다. XID는 오류 코드·PCI(function 제외)·알람 UUID와 재고 대응 UUID를, SXID는 오류 코드·스위치 PCI(function 포함)를 비교한다. 결과는 `quality.analysis.alert_match`에 남는다.
   - 아래 비교 수집 계획이 없는 기존 발행본은 `match`이고 해당 코드의 발행 Runbook이 적용되면 작성·검토 LLM을 호출하지 않는다. 보고서는 코드 자료와 Runbook `operator_guidance`로 만들고 종료 이유는 `alert_match`다.
   - `alert_report_not_found`·`report_reason_changed`·`event_not_found`·`pci_mismatch`·`multiple_devices`·`uuid_unresolved`·`uuid_mismatch`는 근거 공백(gap)으로 기록한다. 남은 Runbook 선택 조회 전체를 한 번의 보완 라운드에서 기존 예산·동시성 안에 모은 뒤 다음 라운드에서 D09와 추가 증거로 작성·검토를 수행한다. 작성 LLM 입력에는 대조 결과가 포함된다.
   - `error_code_unparsed`(알람 사유에 XID·SXID 코드 없음)와 `collection_failed`(재조회 후에도 D09 불완전)는 기존 Runbook 경로를 따른다.
   - 대조는 경로 선택에만 쓴다. 현재 장치 상태·실제 장애 여부·독립 장치 신원을 검증한 사실로 승격하지 않는다.
5. [통합 작성](src/rcca_agent/combined_synthesis.py)이 **증거 해석과 원인 분석을 한 번의 작성 LLM 요청**으로 처리한다. 출력은 보고서가 아닌 사실·추론·미확인·원인 후보·근거 참조를 담은 구조화된 RCA 자료다.
6. XID 79·SXID 11001의 단일 수집 경로는 `analysis_review` LLM 호출·평가용 토큰 예약·평가 피드백 재작성을 수행하지 않는다. 구조·근거 참조 검증을 통과한 작성 자료를 보고서로 전달한다. 결과 envelope의 `review`는 구 소비자 호환을 위해 `skipped/not_requested`, 판정 `null`, 참조 빈 목록으로만 남기며 평가 성공으로 취급하지 않는다. 다른 기존 경로의 [독립 품질 검토](src/rcca_agent/analysis_review.py)가 전체 주장과 원본을 대조한다. 통합 작성의 수정 요구에는 최대 1회 수정·독립 재검토를 허용한다. 요청 실패나 예산 부족은 무한 재시도로 이어지지 않는다. 재검토 후에도 부적절한 주장은 기존 보류 규칙으로 제외하고 원래 지적을 보존한다.
7. 단일 수집 경로에는 goal 달성 평가가 없다. 다른 기존 경로의 [Runbook 판단](src/rcca_agent/decision_policy.py)이 조사 목적의 필수 기준·차단 조건·같은 초안의 검토를 확인한다. 목적을 달성하면 선택 조회가 남아도 종료한다. 미달이면 허용된 필수 보완 조회 또는 한계 종료를 결정한다. 통합 작성에서는 독립 검토가 수정을 요구하면 같은 증거와 검토 지적으로 최대 1회 수정하고 새 초안을 다시 독립 검토한다. 이후 추가 작성은 새 관측이 있을 때만 가능하다.
8. `rca_result_frozen`에 RCA 자료와 hash를 고정한다. [report_writer.py](src/rcca_agent/report_writer.py)는 채택 자료만 투영해 **보고서 LLM 한 번**으로 완성된 문장을 작성한다. 원본 로그·Runbook을 다시 읽어 판단하지 않으며 문장 정렬 호출을 추가하지 않는다. 서술의 필수 섹션·출처 범위·전체 자료 참조·새 수치 여부를 코드로 검사하고, 실제 수집·작성 오류는 보존한다. 단일 수집 보고서에는 품질 검토 상태·목표 평가·평가 종료 이유를 붙이지 않는다. 작성 LLM의 `unknowns`·`conflicts`·`limitations` 자유 문장과 원인 후보의 비코드 `missing_inputs`는 진단·검토에만 남기고 보고서에는 넣지 않는다. 보고서의 불확실성은 코드가 정한 gap 라벨, 대조 결과, `non_blocking_unknowns`를 묶은 "이번 조사 범위 밖" 문장, 고정 한계 문구(`evaluation.FIXED_LIMITS`)로만 표시한다. 입력 초과·예산 부족·모델 미설정·출력 실패에는 동일 자료를 기본 표시한다. `report_assembly`에는 작성 호출의 시간·모델·usage·입력 hash·실패 위치와 결과 구성 상태를 따로 저장한다. 저장·공개는 기존 Worker/JC가 담당한다.

단일 수집 경로는 `combined`로 고정하며 구 profile의 `separate`로 증거 해석 호출을 추가하지 않는다. 수집 뒤 구형 보완 조회 선택·런북 확장·근거 충분성 평가를 실행하지 않고 작성·보고서로 이어진다. 다른 기존 경로의 기본 작성 방식은 `combined`다. 비교·회귀용 profile의 `rca.generation_mode=separate`는 기존 해석·분석 호출과 동일 증거 재작성 금지를 유지한다. 한 attempt 안에서 원본 내용 hash를 비교하므로 UUID 변경·같은 응답 재수집·모델 입력 축약·검토 feedback은 새 증거가 아니다. 작성은 HTTP 오류·출력 잘림에도 재전송하지 않는다. 다른 명시적 작업/attempt의 재평가는 별도 실행이다. 분석·검토 두 단계와 보고서 서술·선택 호출을 합쳐 ‘전체 호출 두 번’이라고 표시하지 않는다. fast path, 기존 결과 읽기, 취소·원격 종료 불명 처리는 유지한다.

XID 79·SXID 11001의 최신 작성 원본은 **오류 보고와 관련 관측을 함께 수집한 비교 자료**를 목표로 한다. Fleet가 장애를 판단했다는 전제에서 같은 알림을 재판정하지 않는다. 새 필수 계획(XID의 D44, SXID의 D47 포함)을 가진 발행 revision에서 [incident_dossier.py](src/rcca_agent/incident_dossier.py)가 동작하며, 기존 발행본은 기존 선택 조회·알림 일치 종료를 유지한다. 운영 적용에는 코드 배포와 새 Runbook revision 발행이 모두 필요하다.

- 첫 라운드: 고정 cutoff를 넘지 않는 조회 종료 시각까지 30분의 같은 노드 XID/SXID 로그(D09)와 관련 메트릭을 기존 Grafana MCP binding·공유 예산으로 함께 수집한다. XID 79는 PCIe replay(D44), 사용률(D02), 전력(D11); SXID 11001은 Fabric Manager 원시 상태 코드(D47), NVLink 수신/송신(D33/D34)이다. 알림 일치와 LLM 예산 부족도 이 수집을 생략시키지 않는다.
- 이력: RCA 전용 `RcaStore`가 기존 저장소 context를 읽은 뒤 별도 읽기 전용 트랜잭션에서 같은 host의 최근 14일 Incident를 가져온다. scope·cluster와 machine ID(없으면 node)를 고정하고 최대 500건을 저장한다. 사건 최초 snapshot의 코드·사유와 사건 ID를 사용한다. 현재 로그의 반복 전달 건수와 등록 사건 수를 합치지 않는다. 같은 cutoff로 기간을 제한하지만 두 DB 읽기가 하나의 트랜잭션은 아니다. 이력은 원본 evidence로 고정한다. 이전 기간 Loki/메트릭 재조회는 하지 않는다.
- 대상: XID는 각 원문의 `gpuInfo.gpus`와 PCI를 대조해 UUID가 유일하게 대응할 때만 GPU 이력·지표를 연결한다. 이는 보고된 재고의 연결이며 독립 실장비 검증이 아니다. SXID는 같은 machine/node·스위치 PCI(function 포함)를 비교하고 GPU 지표는 노드 참고값으로 표시한다. 다른 노드 조회는 추가하지 않는다.
- 고정 보고 자료: 이번 구간의 코드·메시지별 처음/마지막 보고와 원문 refs, 대상 GPU 관련 지표의 최소·최대·마지막 값·단위·표본 수를 코드로 만든다. 보고서 UI는 호스트 Incident 표를 최근 7일/14일과 코드로 필터링하고 사건 원문으로 연결한다. GPU UUID는 사건 target 또는 XID 원문에 유일하게 명시된 UUID를 표시한다. 메트릭은 클러스터·노드와 XID GPU 대응을 요구하고, machine_id 라벨이 있으면 충돌을 배제한다. 노드가 없는 경우 machine_id 일치를 요구한다. 반복은 호스트 전체 코드별 집계와 GPU UUID·오류 코드별 집계를 함께 제공한다. GPU UUID가 없는 사건만을 호스트 전체 건수로 표시하지 않는다. 보고 구간을 장애 지속 시간이나 재부팅·복구 증거로 바꾸지 않는다. 모델 실패에도 표와 공식 지침은 남는다.
- 단일 수집: 이 경로는 observation plan 전체를 한 라운드에서 실행한다. 여러 MCP 호출을 하나의 수집 단계로 묶는 것이며 단일 HTTP 요청을 뜻하지 않는다. D09 재시도·모델의 추가 조회 선택은 실행하지 않는다. `required_queries` 필드는 기존 발행 계약 호환과 새 계획 식별에만 남기며 이 경로의 필수/선택 수집 분기로 쓰지 않는다.
- NVIDIA Node Triage는 자동 복구 절차가 아닌 보고서 순서(사건·관련 관측·반복 이력·다음 대응)에 적용한다. Xid 79는 업무 배제와 진단 자료 확보/지원 전달, SXid는 Fabric Manager 메시지·스위치/포트·플랫폼별 지침을 연결한다. 새 계획의 작성 입력은 원본 출처별로 제한한 최대 24KB 뷰를 사용해 운영에서 관측된 32,768토큰 종료에 대비해 출력 여유를 확보한다. 이는 라우터의 설정 한도를 확정한 값이 아니다. 전체 원문은 evidence에 보존하며 이 상한 자체가 모델 성공을 보장하지는 않는다. Nemotron 작성은 확보한 자료 설명에 집중하고 수치·정렬·집계는 코드가 담당한다. 별도 모델 성능 우열이나 GPU 진단 전문성을 가정하지 않는다.

필수 메트릭의 빈 결과·실패도 자료에 남기지만 0/정상으로 채우지 않는다. 원인 미확정은 새 원인 생성의 이유가 아니다. 공통 결과 schema와 Ops 구현은 변경하지 않는다. Xid 79·SXid 11001의 단일 수집 경로는 goal 평가를 수행하지 않으며, 현재 작성 원본에서 `decision_policy`를 제거했다. 원인 확정 근거를 자동 누락 항목으로 추가하지 않는다. 모델 형식·근거 참조 검증과 실제 수집 실패 기록은 유지한다. 구 발행본의 목적 종료 및 규칙 기반 후속 조회 호환은 유지한다. `evidence_evaluation`과 `investigation_decision`은 `decision_policy_status`(`applied`/`mixed`/`not_configured`)를 보존하며, 종료 결정에 `collected_queries`와 `deferred_queries`를 연결한다. GUI는 수집한 근거·목적 밖 선택 조회·미적용 사유를 구분한다. `method=llm` 완료 기준(`bounded_conclusion`)은 작성 LLM의 자기평가가 아니라 독립 검토 루브릭으로 판정한다(`agent_common.rca_evaluation.review_scope_status`). 검토가 완료되어 `acceptable`/`acceptable_after_feedback`이고 `grounding`·`identity_time`·`limitations`가 `pass`/`not_applicable`이면 `satisfied`다. `needs_revision`은 모든 지적이 특정 주장을 가리켜 코드가 그 주장을 제외한 경우(`unattributed_issues=false`)에만 해소로 본다. 채택된 해석에 남은 finding이 없거나 형식 복구로 caveat이 빠진 경우(`criterion_withheld`)는 `unknown`이다. 작성 LLM의 답은 `author_status`로만 보존하고 검토 대상 주장으로 보내지 않는다. 결과 검증기도 같은 함수로 완료 기준과 검토 근거 ID의 일치를 확인한다. 목적을 달성한 실행은 모든 적용 정책이 `non_blocking_unknowns`로 둔 항목(예: `causal_confirmation_evidence`)을 필수 `missing_inputs`에서 제외한다. 알림 일치 경로도 원인 확정 근거를 요구하지 않는다. 검토를 통과해 목적을 달성한 불일치 조사는 대조 결과를 `alert_match`와 본문에 보존하고 처리 미완료로 집계하지 않는다. 제외한 항목은 `resolved_scope_gaps`로 추적하며 조회 실패·실제 필수 근거 누락은 계속 부분 산출/보류다. Fleet 계약이 의미를 정하지 않은 `Healthy` 기준 보고는 오류 코드가 있는 보고가 함께 있을 때 `unknown_value`를 만들지 않는다. 같은 호스트 GPU 재고에서 보고 PCI가 유일하게 대응하면 발생 내용에 그 GPU UUID를 재고 대응으로 표시한다. 구 발행 1.0에는 정책을 자동으로 덧씌우지 않는다. 운영 갱신은 [1.1 적용 절차](runbooks/DB-WORKFLOW.md#조사-완료-기준-11)를 따른다.

과거 2라운드 보조 조회의 입력 크기 검증: 2026-10-16 운영 작업(보조 조회를 2라운드에서 실행한 XID `f063d28e`·`a04c7939`, SXID `6182aac4`)으로 측정한 결과, 보조 조회를 포함하면 작성 원본 입력이 46~75KB에서 83~138KB로 늘었다. 그래도 `bounded_context`가 16,000바이트 상한 안에 맞췄고(15,887~15,929바이트), XID는 오류 GPU의 D02·D11·D44 시계열(각 8개 표본)과 오류 보고를 보존했다. 대신 D09 원문 발췌 2건과 다른 GPU 지표가 더 생략됐다. SXID의 D02는 NVSwitch와 무관한 GPU 지표만 남겨 판단에 도움이 되지 않았다. 이는 과거 작업의 입력 보존 범위이며, 현재 첫 라운드 자동 보조 조회 또는 실제 장비 상태 판정의 근거가 아니다.


통합 프롬프트는 기존 분석·해석의 판단 규칙만 재사용하며, 출력 지시는 `interpretation`·`hypotheses`·`limitations`를 가진 JSON 객체 하나로 제공한다. 해석의 목록은 `interpretation` 내부에, Runbook 의미 기준이 있으면 `criterion_assessments`도 그 내부에 둔다. 분리 모드의 프롬프트와 기존 형식·참조·부분 성공 검증은 유지한다.

개발용 RCA의 **분석 요약·LLM 실행 기록**과 **워크플로우 단계 상세**는 요청 실패·호출 전 생략·응답 수신 후 검증 실패를 구분한다. `invalid_author_response`는 받은 통합 응답이 검증을 통과하지 못했다는 뜻이다. 그중 `author_shape`는 최상위 구조 오류이며, 해석·분석 내부의 형식·근거 오류는 각 세부 코드로 구분한다. 모두 연결 실패와는 다르다. HTTP 오류는 모델 서버 요청 실패로, `remote_call_state=unknown`은 통신 중단·원격 실행 상태 미확인으로 표시한다. 응답 횟수만으로 채택 여부를 판단하지 않으며, 거절된 응답 원문과 임의 추가 필드명은 저장하지 않는다. 통합 응답은 `diagnostics.validation_failures[].details`, 별도 증거 해석·품질 검토와 후속 조회 선택은 `validation_details[].details`에 검증 코드·규칙·실패한 필드와 목록 위치를 보존한다. 필수 필드 누락, 타입·길이 오류, 허용되지 않은 참조, Runbook 기준 key 불일치를 구분하며 JSON 파싱 실패와도 분리한다. 별도 해석·검토의 기존 1회 수정 요청에는 같은 세부 진단을 전달하고, 수정 성공 후에도 이전 실패 이력을 확인할 수 있다. `hypothesis_index`와 `limitation_index`는 0부터 시작하며 GUI는 1부터 표시한다. 각 영역의 첫 실패를 기록하고 거절된 원문·임의 필드명·예외 메시지는 저장하지 않는다. `analysis_invalid`·`interpretation_invalid`만 있는 과거 기록의 세부 원인은 추정하지 않는다. 작성 프롬프트는 검증기와 같은 조건을 명시한다. 근거 없는 `unknowns`에는 비어 있지 않은 `reason`이 필요하며, Runbook 판단은 `method=llm` 기준마다 revision을 포함한 전체 `key`로 한 번씩 답해야 한다. 근거 참조의 허용 범위와 채택 조건은 그대로 유지한다.

통합 응답은 **항목 단위로 채택**한다. 해석 목록의 한 항목, 원인 후보 하나, 한계 문장 하나가 검증에 실패하면 그 항목만 제외하고 `diagnostics.dropped_items[]`에 같은 코드·규칙·경로와 `action=dropped`를 남긴다. 단, 허용 필드 외의 키만 추가된 항목(`unexpected_fields`)은 추가 키를 제거하고 항목을 유지하며 `action=stripped`로 기록한다. 문장·근거는 그대로이므로 기준 보류(`criterion_withheld`)로 이어지지 않는다. 제외된 항목에 의존하는 원인 후보(`finding_refs`)도 함께 제외된다. Runbook 의미 기준 답변이 잘못되거나, 결론을 제한하는 `unknowns`·`conflicts`·`limitations` 항목이 하나라도 제외되면 모든 기준을 `unknown`으로 두고 `criterion_withheld`를 기록하므로 목적 달성으로 이어지지 않는다. 제외된 항목이 `findings`뿐이면 기준 판단은 유지한다. 최상위 구조, 목록 타입, 해석 전체 형식 오류는 기존처럼 응답 전체를 거절한다. 형식 오류만을 이유로 재작성하지 않는다. 독립 검토가 요구한 의미 수정과 구분한다. 작성 입력은 예산 계획과 같은 크기(`max_input_bytes`)를 사용하며, 형식 통과 검사 행보다 관측 행을, 같은 노드의 다른 GPU보다 보고된 GPU의 지표를 먼저 넣는다.

검토 완료와 검토 통과를 구분한다. 검토 지적을 반영해 코드가 주장을 제외하면 `review_claims_withheld` 사유와 이전 검토 ID를 가진 초안을 저장한다. 남은 초안은 검토한 초안에서 지적된 주장만 뺀 것이므로 같은 검토의 판정·기준을 유지한 채 `verdict=acceptable_after_feedback`(검토 지적 주장 제외 후 통과)로 기록하며 추가 LLM 호출은 없다. 특정 주장을 가리키지 않는 전체 지적(`claim_id=null`)은 검토의 `grounding`·`identity_time`이 모두 `pass`이면 주장을 무효화하지 않는 피드백으로 남긴다. 둘 중 하나라도 통과하지 못한 전체 지적이 있으면 기존처럼 해석 전체를 제외하고 `draft_changed_after_review`·`attempts=0`(**변경 초안 미검토**)로 기록한다. GUI는 검토 판정·미실행·주장 제외를 구분하고, 상세 코드·식별값은 접어서 표시한다. 과거 초안은 같은 작업·시도·초안 식별값의 미실행 검토 기록이 연결되는 경우에만 변경 초안으로 표시한다.

회귀 검사는 [통합 프롬프트 계약](../agents/tests/test_rca_author_prompt.py)과 [GUI 실패 구분](../frontend/src/components/RcaModelFailure.test.tsx)을 포함한다. fixture 통과와 실제 운영 모델의 출력 개선은 별도 검증이다.

## 보완 조회 선택

선택 조건은 발행 Runbook의 `observation_plan`에 둔다. `selection.missing_any`는 부족 조건, `requires_all`은 필요한 scoped fact, `independent: true`는 독립 조회를 뜻한다. 조건을 만족한 항목을 priority와 query ID 순으로 선택한다. 명시적 `unexpected_evidence.additional_queries` 정책도 지원하되 단계의 selection 규칙을 우회하지 않는다.

규칙으로 배치를 선택하면 선택 LLM을 호출하거나 남는 자리를 LLM으로 채우지 않는다. `exploratory_llm: true`인 보조 단계만 JSON 방식의 탐색 선택에 참여한다. 이 표시는 필수 단계나 selection 규칙과 함께 사용할 수 없다. 설정되지 않은 단계는 `selection_conditions_missing`으로 남긴다.

탐색 LLM은 승인된 query ID만 최대 3개 반환할 수 있다. 잘못된 JSON 선택은 같은 예산·deadline 안에서 1회 수정한다. HTTP·deadline·예산 실패로 임의의 조회를 강제하지 않는다. 빈 선택은 조사 중단이며 근거 충분을 뜻하지 않는다.


모델 토큰 예산 부족(`llm_budget_exhausted`)은 조회 예산과 구분한다. 이 경우에도 발행 Runbook의 명시적 조건·예상 밖 근거 정책이 허용하는 독립 조회는 남은 query budget·deadline 안에서 수행한다. LLM 탐색은 추가 호출하지 않는다. 정책 없는 구 Runbook은 검토가 acceptable이어도 기존 명시적 보완 조회 조건을 유지한다. Runbook 1.1은 위의 목적 달성 조건을 먼저 확인한다. 일반 경로는 최초 수집 → RCA 작성 → 독립 검토 → 필요한 보완 수집 순서와 최대 2라운드·보완 3개 한도를 유지한다. 알림 대조 불일치 경로는 앞서 설명한 대로 남은 선택 조회 전체를 예산 안에서 먼저 수집한다. 마지막 검토 실패는 정상 판정으로 바꾸지 않는다.

XID 79 저작 계획은 D44·D02·D11(전력), SXID 11001은 D02·D13을 조건부 보완 대상으로 둔다. D02 작업 라벨과 D06 Pod UID의 유효 시각을 조인한다. 사건에 GPU UUID가 없으면 같은 클러스터·서버의 XID 보고 PCI와 인벤토리가 유일하게 일치할 때만 관측 연결 대상으로 사용하며 원문 근거 참조를 보존한다. SXID PCI를 GPU PCI로 대체하거나 노드의 모든 Pod를 영향 작업으로 간주하지 않는다. 실제 실패·중단은 별도 근거가 필요하다.

`quality.collection_checks`는 오류 로그·FM 원본·토폴로지의 조회 ID, 수집 상태, 원본 근거와 추가 연결 요건을 기록한다. 자동 수집 결과는 권고 조치/분석 한계에 표시하며 추가 확인 사항에는 원천·조회 계획·신원 연결이 필요한 항목만 남긴다. 실패·빈 응답·부분 응답·예산으로 미수집한 항목은 연결 누락과 구분해 분석 한계에 보존한다. RCA 범위는 GPU 노드이므로 GPU–Pod(쿠버네티스 작업) 연결은 요청하지 않으며, 이전 Worker가 저장한 `workload_identity` 항목도 보고서에 표시하지 않는다. 기존 `missing_inputs`와 적격 권고는 변경하지 않는다.

FM 전용 원천은 선택 사항인 실행 프로파일 `rca.evidence_roles.fabric_manager_logs`와 `fabric_topology`에 **이미 등록된 조회 ID**로 연결한다. 해당 조회는 발행 Runbook 계획에도 포함되고 검증된 binding·scope·기간 조건을 만족해야 한다. 이 역할 선언은 조회 권한이나 topology 파서를 생성하지 않는다. 현재 기본 프로파일에는 전용 역할이 없으며 D13 일반 로그를 FM 포트 연결 근거로 승격하지 않는다. 기본 D13 raw binding은 클러스터 범위만 지원하므로 서버·장비로 좁힌 요청의 `binding_scope_unavailable`은 추가 연결 요건으로 표시한다. 현재 범위를 넓히거나 GPU 필터를 제거해 우회하지 않는다. 실제 포트 매핑에는 서버·NVSwitch PCI·source port·상대 GPU/스위치·유효 시각을 보존한 원천과 계약이 추가로 필요하다.

## 확장성 원칙

오류별 분석·보고서 동작을 특정 XID/SXID 번호, PCI 주소 또는 한국어 문장의 일치·치환으로 구현하지 않는다. 오류별 의미·대응·적용 조건은 발행 Runbook과 검증된 생산자 계약에 두고, 공통 코드는 관측 종류·대상·시각·근거 참조·평가 상태를 처리한다. 동일한 원칙을 다른 Fleet 오류에 적용한다. 기존 결과 호환과 내부 상태 코드의 표시 번역은 사건별 분석 예외와 구분한다. 새 의미 규칙은 문장 패턴을 늘리기보다 구조화된 계약과 검증으로 추가한다.

## 관측과 판단의 경계

- 공통 [Observation](../shared/python/src/agent_common/observation.py)이 검증된 D binding과 Grafana MCP를 사용한다. 데이터소스 UID는 profile에 따라 발견하거나 고정하며, 요청 cluster_id와 허용 범위를 유지한다.
- [Fleet 이벤트](src/rcca_agent/fleet_events.py)는 보고된 오류와 장치 연결을 구조화한다. 로그 기록 시각·장비 발생 시각·현재 상태를 구분한다. PCI가 GPU 목록과 같아도 오류 장비 확정을 뜻하지 않으며, SXID의 스위치 주소를 GPU 목록으로 검증하지 않는다.
- 원본 관측은 evidence에 보존한다. 모델에는 크기를 제한한 뷰를 전달하며 `context_selection`과 입력 refs로 생략 범위를 기록한다. 수집 성공과 모델 입력 포함은 별개다.
- 현재 Synthesis는 구조·refs·한국어·숫자 표현·일부 원인 주장 패턴을 검사한다. 장치 신원 불확실성을 원인으로 제시하는 검사는 문장 표현 검사보다 먼저 적용한다. 수정 응답도 같은 기준을 통과해야 한다. 이 검사는 가설의 진실성이나 원인 분석 정확도 점수가 아니다.
- 수정은 예산·deadline 안에서 1회다. `validated_response`와 유효 부분만 남은 `validated_subset`을 구분한다. 진단에는 거절 사유·위치·hash를 남기고 거절 원문 전체는 저장하지 않는다.
- 원인 후보가 없을 때 보고된 증상 요약이 표시될 수 있다. 관측 요약, LLM 가설, Runbook 적용에 따른 판단을 같은 확정 원인으로 해석하지 않는다. 장비 조치는 수행하지 않는다.

## 보고서와 조회 호환

현재 Worker는 구조화된 RCA 작성 → 독립 품질 검토 → 목적 종료 → 자료 고정 → 보고서 서술 순서다. `quality.report.presentation=rca-material/1`, `method=llm_composed`는 보고서 LLM이 고정된 자료로 문장을 작성한 결과다. `deterministic_fallback`은 서술을 채택하지 못해 동일 자료를 기본 표시한 결과이며, 보고서 실패가 RCA 판정·자료를 변경하지 않는다. 보고서 작성은 기존 synthesis 전송 모델·출력 cap·예산 검사와 16,000바이트 입력 한도를 사용하며 전송·응답 복구·정렬 재호출을 하지 않는다. 원격 실행 종료 불명·취소는 기존 Worker fencing을 유지한다.

[report_sources()](src/rcca_agent/report_writer.py)는 발생 내용·분석 결과·권고 대응을 중심으로 자료를 투영한다. 자유 형식 `missing_inputs`와 unknowns는 조사 제한에 보존하며 운영자 조치로 변환하지 않는다. 원인 후보가 없다는 상투적 문구를 반복하지 않고, 선택한 발행 Runbook의 오류 설명과 조건부 대응을 원문으로 연결한다. 오류 설명은 보고서 LLM이 다시 쓰지 않으므로 처리 실패 문장이 오류 정의에 덧붙지 않는다. 관측된 비정상 상태만으로 일반적인 원인 후보를 자동 생성하지 않는다. 원본 로그나 카탈로그를 재분석해 회복·하드웨어 원인 문구를 추가하지 않는다. 권고는 보류/적격과 조건을 함께 표시한다. 검토 실패 후 남은 자료를 검토 통과로 승격하지 않는다. 서술 입력 크기를 초과하면 조용히 잘라 보내지 않고 원문 기본 표시와 사유를 남긴다.

`source_items`와 `material_hash`를 저장하고 GUI에서 서술 전 자료를 대조한다. 형식·참조·수치 검증은 의미 일치의 보장이 아니다. 단일 수집 보고서는 별도 의미 평가 상태를 생성하지 않는다. 실제 모델이 불확실성·반대 근거·조치 조건을 유지하는지는 배포 후 사람의 전후 비교 대상이다. 고정 한계는 LLM이 줄이거나 제거하지 않는다.

과거 `incident-first/1`, `incident-first/2`, `llm_prioritized` 결과 조회는 유지한다. 고정 자료 인자가 없는 구 호출자는 기존 [report.py](src/rcca_agent/report.py) 경로를 유지하지만 현재 Worker는 항상 고정 자료를 전달하므로 사건 재해석·정렬 경로를 실행하지 않는다. 최종 선택한 발행 Runbook의 `operator_guidance`와 출처·revision도 자료 hash에 포함한다. 수집된 보고가 정책의 `applies_when`(정책 없는 코드 지침은 명시한 코드)에 맞을 때만 본문에 반영한다. 나머지는 `reference_only` 참고 자료다. 오류 설명은 서술 입력에 포함하되 대응·모델/버전 조건·조치 후 확인은 `fixed` 원문으로 삽입해 LLM이 생략하거나 새 지시로 바꾸지 못하게 한다. GUI는 이 보고서에 일반 원인 문장을 덧붙이지 않으며 상세 제한은 펼침 영역에서 보존한다. 별도 Ops 운영보고서는 변경하지 않는다.

LLM 작성의 성공·실패와 관계없이, 기존 대상·출처 검증을 통과한 상태 보고와 오류 이벤트를 코드로 요약한 `reported_observations`를 같은 고정 자료에 저장하고 발생 내용에 표시한다. 클러스터·대상·보고된 코드/사유·보고 건수·시각 기준·원본 근거를 유지하며, 일반 Fleet 컴포넌트에도 같은 경로를 적용한다. 발생 내용은 보고서 LLM의 서술 대상에서 제외하고 원문으로 삽입하므로 보고서 작성마저 실패해도 남는다. 분석 처리 상태는 별도로 표시하며 보고 사실을 현재 상태·원인·회복이나 분석 성공으로 승격하지 않는다. 다른 대상·신원 충돌·유효하지 않은 시각/근거의 보고는 제외한다. 조회·LLM 요청·workflow 노드·scoring은 추가하지 않는다.

발생 내용은 대상 이름을 한 번 표시하고 오류 이벤트와 상태 보고의 건수를 구분한다. 오류 코드가 있는 보고는 코드·PCI·보고 상태로 압축하며 같은 클러스터·대상·컴포넌트의 유효한 오류 이벤트가 있을 때 다른 PCI 또는 장치를 지정하지 않은 상태 기록은 접힌 참고 상세로 구분한다. 다른 컴포넌트의 Fleet 보고에는 이 분류를 적용하지 않는다. 원본 사유·machine ID는 구조화된 근거에 보존한다. LLM 입력 크기 제한 전 같은 클러스터·대상·컴포넌트에서 사건 이벤트의 PCI와 일치하는 상태 보고를 우선 배치하며, 생략된 관측으로 신원 모순을 추론하지 않도록 검토한다. 처리 실패와 시각 대체 설명은 한계 상세로 이동하고 대응 항목마다 반복하던 접두어는 제거한다. 이 변경은 조회·호출·예산·종료 판정을 추가하거나 완화하지 않는다.

생산자 시각이 누락·초기값인 상태 보고는 이미 검증한 Loki 기록 시각으로 사건 구간에 연결한다. 보고서에 이 대체 기준과 사용 범위(보고 순서)를 한 번 설명하며, 발생·회복 시각이나 현재 상태로 승격하지 않는다. 원본 시각·내부 상태·근거는 그대로 유지한다.

### 비코드 Fleet 오류와 평가

Runbook `gpu-rca-runbook/1.2`는 기존 코드 목표 외에 `reported_producer_contract + reported_component + reported_normalized_health=unhealthy` 조합을 지원한다. 컴포넌트 이름은 정확히 일치해야 하며 설명문에 이름이 있다는 이유만으로 지침을 고르지 않는다. 등록된 Fleet `component_data` 원천, 대상·기간·생산자와 비정상 보고를 검사하고 동일한 `reported_error/scoped_source` 및 독립 의미 검토로 종료한다. 보고 사실은 조치 precondition이나 현재 상태 fact로 사용할 수 없다. 서로 다른 상태가 섞이면 기록 시각만으로 회복을 추정하지 않는다.

같은 컴포넌트 안에서 오류별 대응이 다르면 `applies_when.reported_reason`을 추가해 원본 사유의 정확한 일치까지 요구한다. 검색에서도 구조화된 `reason`을 대조하므로 설명문의 부분 일치로 다른 오류의 절차를 선택하지 않는다. 예를 들어 disk의 읽기 전용 전환과 이벤트 조회 실패를 같은 복구 절차로 취급하지 않는다. 안정된 사유 문자열이 없는 원천은 컴포넌트 공통 조사 범위의 지침을 사용하고, 구체적 이벤트 식별은 검증된 원천 계약을 추가한다.

신규 오류는 검증한 producer의 `health_contracts.components` 등록과 출처·적용 조건·대응 지침을 갖춘 새 Runbook revision으로 추가한다. 현재 기본 프로파일/카탈로그는 XID·SXID 범위이며 모든 Fleet 오류의 운영 지침이 이미 발행됐다는 뜻은 아니다. 이벤트 전용·새 payload 원천은 별도 검증된 parser/binding이 필요하다. 조회는 등록된 실행 프로파일과 Runbook 계획에서 선택하며 D09를 모든 원천의 보편 조회로 가정하지 않는다.

Scoring의 위치는 유지한다: 조회 전 BM25는 Runbook 관련도, 수집 후 코드는 근거의 대상·시각·의미·완전성, 기존 독립 검토는 grounding/identity_time/contradictions/alternatives/limitations/evidence_use를 평가한다. 이를 원인 확률 하나로 합치지 않는다. 일반 성공 경로는 작성·검토·보고서 각각 1회이며 별도 scoring/번역/런북 선택 LLM이나 workflow 단계를 추가하지 않는다. 대응의 필수 조건을 판단할 유효한 조회만 기존 계획·예산 안에서 수행하고, 기존 발행본에서는 목표를 충족한 D09 결과 뒤에 선택 조회를 강제하지 않는다. 새 XID 79·SXID 11001 계획의 필수 지표는 첫 라운드에 수집한다.

### 중복 처리와 검토 상태

분석 입력의 순서만 다른 동일 레코드를 포함한 `gpu_candidates` 배열은 `gpu_inventories`에 한 번 저장하고 각 관측에서 `gpu_inventory_ref`로 연결한다. 관측 자체의 시각·출처·값은 합치지 않으며 원본도 변경하지 않는다. 검토 입력은 통합·분리 모드 모두 `claims`와 제한·초안 hash를 전달하고 동일 후보·권고·해석 본문을 반복 전송하지 않는다. 원본 근거 뷰는 독립 검토용으로 유지한다. 원문 발췌에는 로그 기록 시각과 시각 기준을 함께 전달한다. `unknown` 평가 항목은 사실 주장 목록 대신 `unresolved_assessments`로 검토에 전달하며 원래 평가와 초안 hash는 보존한다. 작성자의 미응답 자체는 검토 통과나 목적 달성의 근거가 아니다. `method=llm` 완료 기준은 독립 검토의 판정·루브릭으로 평가한다. 실행 총예산은 유지한다. JC `attempt_budget`은 시도 전체, `token_budget`은 작업 전체의 사용 예산이고 `llm.synthesisMaxTokens`는 호출별 출력 요청 상한이다. 호출의 `charged_tokens`는 이 예산에서 차감한 사용량이며 모델 문맥 한도 설정값이 아니다. Helm의 `configuration.jobController`는 예제 객체를 대체하므로 실제 작업의 execution snapshot으로 적용값을 확인한다. 작성 근거 뷰는 남은 예산과 검토 예약을 반영해 기존 경로는 최대 64,000바이트, incident comparison 계획은 최대 24,000바이트로 제한하며, 검토·보고서는 고정 24KB·16KB 대신 현재 남은 예산으로 전송 가능 여부를 판단한다. 초과 자료를 몰래 제거하지 않으며, 검토 불가 상태와 보고서의 원문 기반 대체 표시를 남긴다.

Runbook `unknown`은 미확정 상태이며 참조가 비었다는 이유만으로 허위 사실 주장으로 판정하지 않도록 검토 지시를 구분한다. 개별 해석/기준 지적은 해당 항목과 의존 후보·기준만 보류하고 나머지 해석을 유지한다. 결론을 제한하는 항목이 제외되면 의미 기준은 unknown으로 둔다. 전역 지적은 해석 전체 보류를 유지하며 변경 초안은 미검토다. 기존 검토 통과를 새 초안에 승계하지 않는다.

## 보고서의 조사 설명과 장치 대조

보고서는 발생 내용 → 무엇을 조사했나요? → 자료를 비교한 결과 → 분석 결과 → 다음에 할 일 순서로 구성한다. 코드별 오류 설명과 대응 조건은 발행 Runbook을 따르며 공통 설명은 XID·SXID 전체에 적용한다. `investigation_summary.py`는 모델 입력 축약 전 전체 수집 자료로 같은 서버의 GPU 주소 목록을 비교한다. GPU 목록에 없는 주소는 실제 장치 부재의 확정이 아니라 **수집된 목록과의 불일치**로 본문에 표시한다. GPU 목록을 NVSwitch 존재 판단에 사용하지 않는다. 요약과 근거 ID는 작성·검토 입력 및 고정 자료에 보존한다. 정상 상태 로그는 비교한 시각 기준을 설명하며 사건 전 보고를 복구 근거로 사용하지 않는다.

보고서에는 내부 조회 번호 대신 자료 이름을 쓰고, 추가 조회를 한 이유와 다른 장치의 지표를 알림 대상에 연결할 수 없는 이유를 설명한다. 기존 발행본의 무조건적인 GPU 연결/독립 신원 검증 안내는 별도 현장 점검 참고 항목에 보존하고 사건별 대조를 본문에 우선한다. XID 79·SXID 11001 작성 원본의 새 표현은 별도 revision 검토·발행이 필요하다. 과거 저장 보고서와 hash는 재작성하지 않으며, 기존 부분 산출 상태를 화면에서 임의로 성공으로 바꾸지 않는다. 운영 데이터/모델로 새 실행을 검증하는 것은 배포 후 별도 단계다.

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
