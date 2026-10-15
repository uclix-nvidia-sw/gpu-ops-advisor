# 11. RCA Agent 실행 계약과 평가 분리 설계·개발

현재 실행 설명은 [RCA README](../../../rcca-agent/README.md)가 소유한다. 이 문서는 현재 코드가 사용하는 계약과 판단 경계, RCA 평가 분리의 설계·개발 범위를 정리한다. **평가 분리의 코드·GUI 경로를 구현했다. 고정 응답 검증과 실제 모델의 평가 정확도·운영 배포는 구분하며, 실행 근거는 Agent QA에서 관리한다.** 입력/실행은 [실행 계약](../common/14_모듈간_호출과_공통실행_계약.md), 결과 필드는 [공통 판단·결과 계약](../common/04_Agent_동작_판단_명세서.md), DB 소유권은 [Shared](../../../shared/README.md)를 따른다.

## 문서 관계와 읽는 순서

전체 방향을 함께 검토할 때는 [개선 목적](#평가-분리-설계개발) → 단계와 LLM 개입 → 사건 예시 → 함수별 변경 → 검수 기준 순으로 읽는다. 별도의 협의 항목이나 승인 절차를 만들지 않는다. 현재 동작과 목표를 비교할 때는 앞의 현행 계약 절과 RCA README를 함께 확인한다.

| 담당 문서 | 이 변경에서 소유하는 내용 |
|---|---|
| 이 문서 | RCA 조사 순서, LLM 역할, 반복·실패 처리, 함수별 개발 내용과 보존할 기능 |
| [04 공통 판단](../common/04_Agent_동작_판단_명세서.md#81-rca-평가-분리-결과-확장) | 새 결과 필드·상태·참조와 기존 결과 호환 계약 |
| [14 공통 실행](../common/14_모듈간_호출과_공통실행_계약.md#rca-평가-분리의-실행-호환) | 같은 attempt의 직렬 호출·예산·취소·공개 경계와 소비자 적용 순서 |
| [07 Frontend](../frontend/07_프론트엔드_개발명세서.md#rca-평가-분리-표시) | 최종 결과와 디버깅 화면의 표시·구형 결과 처리 |
| [05 검수](../05_테스트_검수_기준서.md#rca-평가-분리-검수) | 입력 사례별 기대 결과와 검증 범위 |
| RCA README / Agent QA | 실제 구현 상태 / 실행한 시험의 증거. 미구현 설계를 검증 완료로 옮기지 않음 |

같은 필드·상태를 여러 문서에서 재정의하지 않는다. 기존 문서를 갱신하며 별도의 날짜별 설계 요약이나 개발 일지를 만들지 않는다.

## 입력과 실행 소유권

Grafana 알림은 Incident가 사건 snapshot으로 저장하고 JC에 RCA 작업을 접수한다. Worker는 JC claim의 입력·scope·기간·예산·지식 revision을 사용한다. Backend/GUI가 Worker를 직접 호출하지 않는다. lease·heartbeat·취소·원격 실행 종료 불명·공개는 공통 Worker와 JC의 계약이다.

RCA는 GPU·NVSwitch·노드 하드웨어 사건을 조사한다. 알람의 검색 단서, 보고된 상태, 검증된 현재 상태, 원인 판단은 별개다. 기존 입력·결과와 legacy Runbook 호환은 유지한다. 새 계약을 도입할 때 기존 snapshot을 조용히 재해석하지 않는다.

## Runbook 검색과 적용

[검색](../../../rcca-agent/src/rcca_agent/retrieval.py)은 오류 코드 namespace를 구분하는 결정적 순위 검색이다. 양수 점수의 후보를 제한된 수로 반환하며 점수는 관련도이지 진단 확률이 아니다. 코퍼스·tokenizer가 바뀌면 검색 품질도 다시 확인해야 한다.

[발행 계약 검증](../../../rcca-agent/src/rcca_agent/runbook_contract.py)은 scope·revision·reviewed content hash·내용 구조·등록 query를 확인한다. 구조 통과와 실제 적용 조건 충족은 별개다. `compatibility_status`는 입력 attribute의 known/unknown과 일치 여부를 확인하고, workflow가 scoped facts로 적용 가능 후보를 판단한다.

일반 조사 Runbook은 원인 확정을 위한 지식과 구분한다. 등록 일반 Runbook을 사용할 수 없으면 패키지의 조사 전용 템플릿이 fallback이며 `origin=builtin`으로 표시한다. 조사 지침은 관측 근거가 아니다.

Runbook 작성 필드·등록·검토·발행 명령은 [작성 안내](../../../rcca-agent/runbooks/README.md)와 [DB workflow](../../../rcca-agent/runbooks/DB-WORKFLOW.md)를 따른다. 발행 revision을 덮어쓰지 않는다.

## 관측 계획과 보완 선택

`observation_plan`은 query ID·우선순위·필수 여부·목적·산출 fact·독립성을 정의한다. query는 profile에 등록되고 허용된 것이어야 하며 선언된 fact를 생산할 수 있는지 검증한다. 실제 대상·기간·데이터소스는 [공통 D binding](../common/d-binding-runtime.md)의 범위를 따른다.

| 선택 방식 | 현재 조건 |
|---|---|
| 필수 수집 | 선택된 Runbook이 요구하는 허용 조회 |
| 규칙 기반 보완 | `selection.missing_any`의 부족 조건이 있고 `requires_all` fact를 충족한 독립 보조 단계 |
| 명시적 정책 | `unexpected_evidence.additional_queries`; 단계의 selection 조건을 우회하지 않음 |
| 탐색 LLM | `exploratory_llm: true`인 독립 보조 단계만 JSON 선택 허용 |
| 선택 조건 없음 | `selection_conditions_missing`, `unconfigured_queries`로 기록. 암묵적 LLM fallback 없음 |

동일 query를 중복 선택하지 않고 priority/query ID 순서와 공유 예산을 적용한다. 최초 수집과 보완 수집 1회, 최대 2라운드다. 보완 배치는 최대 3개이며 이미 수집된 조회를 무조건 반복하지 않는다. 규칙으로 선택한 배치를 LLM으로 채우지 않는다.

매 라운드 `evidence_evaluation`은 가용 사실·부족 조건·상충/실패·정책과 규칙 판단·다음 조회·종료 이유를 저장한다. `sufficient`, `insufficient_actionable`, `insufficient_blocked`, `degraded`, `conflicted`를 구분한다. 다음 조회 없음, 예산/시간/라운드 소진은 근거 충분과 다르다.

## 관측의 판단 가능 범위

- 조회 성공은 응답 확보만 뜻한다. 값·단위·producer·대상·발생 시각·freshness가 해당 판단에 유효한지 별도 확인한다.
- Fleet 로그의 기록 시각은 장비 발생 시각이나 현재 상태를 자동으로 보증하지 않는다. `reported_error_code`와 현재 상태 fact를 분리한다. producer 시각 0은 유효한 사건 시각으로 승격하지 않는다.
- PCI 주소는 정규화한 후 제공된 인벤토리와 비교한다. 일치해도 후보 연결이며, 불일치는 제공된 목록에서 연결을 확인하지 못했다는 뜻이다. NVSwitch 주소는 GPU 인벤토리로 검증하지 않는다.
- GPU·Pod·Namespace 관계를 사용하는 기존 경로는 동일 대상·기간·UID 조건을 만족한 관측만 연결한다. 노드에 같은 시각 존재했다는 이유로 특정 GPU의 사용자나 업무 피해로 단정하지 않는다.
- 생산자가 같은 DCGM Field ID를 읽어도 표본을 합산하거나 독립된 장애 근거로 중복 가산하지 않는다. [생산자별 메트릭 의미](references/metric-meaning.md)와 [원천 검토 자료](references/README.md)를 따른다.

## 모델 입력과 원인 후보 검증

각 수집 라운드에서 증거 해석 후 Synthesis를 호출하고, Runbook 후보·권고를 결합한 초안을 별도로 검토한다. fast path와 유효 근거 없음·모델 미설정은 별도 상태로 남긴다. [입력 구성](../../../rcca-agent/src/rcca_agent/synthesis_context.py)은 원본을 수정하지 않고 제한된 모델 뷰를 만든다. 입력 refs·원본/전달 크기·생략 수를 기록하고 수정 요청에서도 실제 입력 범위를 남긴다.

모델은 `hypotheses`와 `limitations`를 반환한다. 후보에는 주장·지지 refs·반박 refs·부족 입력이 필요하다. [검증기](../../../rcca-agent/src/rcca_agent/synthesis.py)는 구조, 허용된 관측 참조, 상충 참조, 숫자·한국어 표현과 특정 원인 주장 패턴을 검사한다. 신원 불확실성을 원인으로 제시하는 검사와 미확정 장치의 기전 주장은 표현 검사보다 먼저 확인한다.

수정은 같은 예산·deadline 안에서 최대 1회다. 수정 응답은 전체 규칙을 다시 통과해야 한다. 유효한 부분만 남긴 `validated_subset`과 응답 전체를 채택한 `validated_response`를 구분한다. 거절 사유·위치·문장 hash를 진단에 저장하며 거절 원문 전체를 보관하지 않는다.

현재 검증은 원인 정확도나 확률을 산출하지 않는다. LLM 후보는 인과 확정으로 승격되지 않으며, 적용 가능한 Runbook에서 나온 후보와 관측 요약도 출처를 구분한다. 원인 후보가 없어도 보고된 증상과 부족한 근거를 보고할 수 있다.

## 결과·보고서·공개

코드는 사건·관측·Runbook·원인 후보·권고·한계를 근거 참조가 있는 문장으로 만든다. 마지막 LLM은 문장 ID의 우선순위만 선택하고 새 사실·수치·원인을 작성하지 않는다. 선택하지 않은 문장도 보존한다. 모델 미설정·확정 실패에는 기본 보고서를 사용한다.

Runbook의 `operator_guidance`는 의미·주의·다음 확인·출처를 공통 형식으로 표시한다. 발행된 지침을 관측 사실로 간주하지 않고 다른 오류의 지침을 대신 붙이지 않는다. 권고는 전제 조건 충족 여부를 표시하며 실제 장비 조치를 수행하지 않는다.

| 결과 축 | 의미 |
|---|---|
| job 상태 | Worker 실행과 JC 공개 수명주기 |
| result_status / assessment | 근거에 따른 판단 가능 범위와 부족 입력 |
| analysis / synthesis 진단 | 모델 호출·응답 검사·수정·채택 상태 |
| narrative_status / quality.report | 보고서 구성·문장 편집 상태 |

evidence와 candidate를 저장한 뒤 JC가 실행권·계약·hash 등을 확인해 공개한다. 과거 결과의 `analysis.sufficiency`와 이전 평가 기록은 조회 호환용으로 유지한다. 원본 snapshot·결과 hash·발행 revision은 변경하지 않는다.

## 평가 분리 설계·개발

### 개선 목적과 현재의 차이

RCA는 장애 관련 로그·지표를 모아 원인을 조사하는 과정이다. 데이터를 받았는지, 데이터가 무엇을 뜻하는지, 결론이 근거에 맞는지는 서로 다른 질문이다. 모든 자료가 확보돼야만 조사를 완료하는 구조를 피하고, 확보한 증거가 허용하는 범위에서 결론과 한계를 남긴다. 자료 부족만 반복해서 설명하고 확보한 중요한 증거를 검토하지 않는 분석도 적절하다고 보지 않는다.

| 구분 | 질문 | 판단 주체 | 예시 |
|---|---|---|---|
| 수집 상태 | 데이터를 제대로 받아왔는가? | 코드 | 성공·빈 결과·부분 수집·실패 |
| 증거 상태 | 이 데이터로 무엇을 알 수 있는가? | 명확한 검사: 코드 / 의미 해석: LLM | 오류 보고 확인, 오류 대상 GPU 미확인 |
| 분석 품질 | 이 근거로 이 결론을 내려도 되는가? | 구조·참조 검사: 코드 / 의미·논리 검토: 별도 LLM 호출 | 타당·수정 필요·판단 불가·미검토 |

`evaluate_requirements()`는 수집·Runbook 요건을, `analyze_round()`/`evaluate_analysis()`는 해석·초안·검토를, `select_followup()`는 허용된 다음 조회와 종료를 담당한다. 기존 `sufficient`는 분석 품질 판정으로 재사용하지 않는다. 요건 기록을 유지하면서 같은 attempt 안에서 제한적으로 수정·보완한다.

| 이전 흐름 | 현재 흐름 |
|---|---|
| 정규화 관측을 중심으로 Synthesis 입력 구성 | 관측과 별도로 검증 진단·제한된 원문 발췌·증거 해석 제공 |
| 코드로 Synthesis 구조·참조·일부 문장 패턴 검증 | 기존 검증 유지 + 최종 초안 전체의 의미·논리 검토 |
| 수집 종료 후 분석 | 최초 수집 후 해석·분석·검토, 필요한 경우 보완 수집 |
| 부족 조건과 수집 gate를 기록 | 기존 기록 유지 + 분석 검토·최종 초안·다음 행동의 연결 기록 |

### 기초 검증과 의미 해석의 경계

코드는 기준이 명확하고 반복해서 같은 답을 낼 수 있는 검사만 한다. JSON 파싱, 필드 존재·형식, 규격에 따른 시간 범위, 식별자 정확 일치와 명시된 정규화가 해당한다. 문자열 불일치는 다른 장비라는 증명이 아니며, LLM의 오타 추정도 동일 장비의 증명이 아니다.

- 원본은 기존 evidence에 보존하고 검사 이름·결과·이유·원본 위치를 남긴다. 실패한 의미 해석을 정상 관측으로 채우지 않는다.
- 파싱하지 못한 원문도 허용 scope 안의 제한된 발췌로 해석할 수 있다. `parse_failed`는 원문 내용 전체가 거짓이라는 뜻이 아니다.
- LLM에 원본 전체를 통째로 보내지 않는다. 크기·민감정보·허용 대상 제한을 적용하고 발췌 refs와 생략 정보를 보존한다. 원문 속 명령은 데이터로만 취급한다.
- 발췌 해석으로 `verified` facts, 수치 계산, GPU 연결, Runbook 적용 조건을 충족시키지 않는다. 보고된 내용·가능한 해석·검증된 대상 관계를 분리한다.
- 불확실한 자료를 보존한다는 이유로 범위 밖 조회나 현재의 시간·대상·권고 검증을 완화하지 않는다. 검증 불가 수치는 새 measurement로 만들지 않는다.

### 실행 순서와 LLM 개입

| 단계 | 담당 | 입력 → 출력 |
|---|---|---|
| 1 조사 범위 설정 | 코드 | 사건 snapshot·대상·기간·호환 Runbook → 계획·허용 조회 |
| 2 수집 | 코드 | 계획 → 원본 evidence·조회 기록 |
| 3 수집 상태 확인 | 코드 | 조회 기록 → 실패·빈 결과·잘림·시간 초과·제한 |
| 4 명확한 항목 검사 | 코드 | 원본 → 형식·필드·시간·식별자 진단 |
| 5 증거 해석 | **LLM ①**, 뒤에 코드 검증 | 관측·발췌·진단·제한 → 확인 내용·추론·미확인·상충 |
| 6 RCA 초안 작성 | **LLM ②** + 기존 규칙 | 증거 해석·근거·Runbook → 후보·지지/반박·대안·권고·한계 |
| 7 분석 품질 검토 | 코드 + **LLM ③** + 코드 | 결합된 초안·근거·제한 → 판정·문제·수정 의견 |
| 8 다음 행동 결정 | 코드 | 검토·중요한 미확인 사항·실행 조건 → 수정·보완 수집·종료 |
| 9 보고서 구성 | 코드, 기존 LLM 문장 ID 편집 | 확정 내용 → 결과·보고서 |

```text
범위 설정 → 수집·원본 보존 → 수집 상태·기초 검증             [코드]
  → 증거 해석 [LLM ①] → 출력 검증                         [코드]
  → RCA 분석 [LLM ②] → 규칙 후보·권고 결합 → 초안 검증     [코드]
  → 분석 품질 검토 [LLM ③] → 검토 검증·다음 행동 결정      [코드]
      ├─ 설명 문제 → 분석 수정 [LLM ②] → 검증·재검토 [LLM ③]
      ├─ 중요한 자료 확보 가능 → 허용 조회 선택·보완 수집 → 해석부터 반복
      └─ 종료 → 한계·검토 상태를 포함한 결과 → 문장 ID 편집 → 기존 저장·JC 공개
```

**LLM ①**은 `observed`(원문에서 확인한 보고)와 `inferred`(가능한 해석), unknowns/conflicts/limitations를 분리한다. 원문에 오류가 보고됐다는 내용은 실제 고장의 원인 확정과 다르다. **LLM ②**는 확인된 내용과 제한 안에서 원인 후보·반대 근거·중요한 대안·추가 확인을 작성한다. **LLM ③**은 초안뿐 아니라 원본 발췌, 수집·해석 제한과 입력 생략 정보를 보고 과장·모순·대안 누락·중요한 증거 미활용을 검토한다.

검토는 `synthesize()` 직후가 아니라 **Runbook 기반 후보·권고를 결합한 후** 수행한다. 대상은 근거를 가진 전체 주장·권고·한계다. 보고서 편집은 검토 뒤에 문장 ID 순서만 정하며 의미·확신 수준을 바꾸지 않는다. 필수 한계·미검토·보류 상태는 편집 결과와 무관하게 표시한다.

별도 검토는 별도 호출이지 다른 모델·서비스 도입 요구가 아니다. 같은 모델을 사용할 수 있고 기존 job 모델 라우팅을 따른다. 추가 조회 선택, 의미 수정, 형식 복구, 최종 문장 편집에도 LLM이 호출될 수 있어 총 호출을 항상 3회로 표시하지 않는다. 선택 LLM은 기존 `exploratory_llm: true` 후보만 사용하며 규칙 배치의 빈자리를 채우지 않는다. 해석·분석·검토에는 조회·저장·장비 제어 도구를 주지 않는다.

### 분석 품질 평가 척도 — rubric 1

평가 대상은 **최종 초안이 전달된 증거 범위에 맞는가**이다. 원인 정답률·수집량·문장 유창성의 점수가 아니다. 규칙은 출력의 구조·참조·판정 일관성을 검사하며, 아래 의미 판단은 별도 LLM 호출이 수행한다. 모델이 판단한 이유를 사람이 원본과 대조할 수 있어야 한다.

| 항목 / 코드 | 충족으로 볼 조건 | 수정 필요 사례 | 판단 불가 사례 |
|---|---|---|---|
| 근거와 결론의 연결 / `grounding` | 주요 주장·원인 배제·권고가 인용 증거의 범위를 지킴 | PCIe 일부 0값만으로 PCIe 원인 배제; 로그에 없는 고장 단정 | 판단에 필수인 인용 원문이 입력에서 빠져 확인 불가 |
| 대상·시각 구분 / `identity_time` | 보고 대상·실제 장치·사건/기록/현재 시각을 구분 | 이름의 마침표 차이를 같은 GPU로 확정; 기록 시각을 장애 발생 시각으로 확정 | 초안의 대상 연결을 검토할 식별 근거 자체가 전달되지 않음 |
| 반대 근거·모순 / `contradictions` | 서로 다른 관측을 함께 설명하거나 미해결로 표시 | 건강/이상 보고가 함께 있는데 한쪽만 채택 | 중요한 상충 자료의 세부 내용을 확인할 수 없음 |
| 중요한 대안 / `alternatives` | 현재 증거로 남는 주요 대안과 배제 범위를 설명 | 하드웨어 고장만 단정하고 설명 가능한 연결·관측 문제 누락 | 주요 대안을 비교할 근거의 의미가 불명확 |
| 수집·해석 한계 / `limitations` | 빈 결과·부분 수집·시간 공백·입력 생략이 결론을 어떻게 제한하는지 명시 | empty를 정상으로 처리; 검토하지 못한 기간까지 정상이라고 서술 | 제한이 결론에 미치는 영향을 판단할 문맥이 없음 |
| 중요한 증거 활용 / `evidence_use` | 확보한 핵심 보고를 사용하면서 미확인을 구분 | 유효한 오류 보고가 있는데 ‘자료 부족’만 반복 | 핵심 자료가 해석 불가능하거나 검토 입력에서 생략됨 |

항목마다 `pass/needs_revision/undetermined/not_applicable`, 이유, 실제 전달된 증거 ID를 기록한다. `not_applicable`에도 해당하지 않는 구체적 이유가 필요하다. 예컨대 반대 근거가 실제 제공되지 않은 경우와 반대 근거를 읽지 못한 경우를 혼동하지 않는다. 자료가 부족해도 ‘GPU 연결 미확인으로 해당 원인을 배제할 수 없다’는 설명은 충족일 수 있다.

종합 판정은 코드로 일관성을 확인한다. 하나라도 `needs_revision`이면 `revision_required`, 그것이 없고 `undetermined`가 있으면 `undetermined`, 나머지는 `acceptable`이다. 항목을 생략하거나 종합 판정과 모순되면 형식 복구를 한 번 요청하고, 다시 실패하면 **미검토**로 남긴다. 점수 평균이나 임의 가중치로 중요한 문제를 상쇄하지 않는다.

척도 자체를 검증할 기준 사례는 같은 자료에 대한 제한적 설명/과장된 설명 쌍, 식별자 오타, 관측 공백, 상충 보고, 핵심 증거 미사용이다. 기대 판정과 근거를 사람이 먼저 정하고 실제 모델 출력의 문제 누락·잘못된 지적·항목별 차이·호출 시간·토큰을 대조한다. 고정 응답 테스트는 이 평가의 저장·분기·참조 계약만 검증한다. 실제 모델의 의미 평가 정확도는 T79에서 별도로 검증한다.

### 다음 행동과 반복 제한

요건 미충족은 조사 제약이며 그 자체로 잘못된 분석이라는 뜻이 아니다. 반대로 기존 요건이 충족돼도 검토자가 중요한 보완 질문을 남겼다면 허용된 조회와 실행 조건을 다시 확인한다. `evaluate_requirements()`는 부족 조건과 정책 제안을 기록하고, `select_followup()`는 기존 Runbook 규칙·명시적 정책·허용 범위로 후보를 제한한다. `select_followup()`와 `evaluate_analysis()`의 결정이 `investigation_decision`에 실제 행동과 이유를 기록한다. LLM 제안은 등록 query ID와 목적·기대 효과만 포함하며 임의 조회식이나 새 Runbook 발행을 허용하지 않는다.

| 조건 | 행동 |
|---|---|
| 현재 자료를 과장했고 추가 자료 없이 고칠 수 있음 | 의미 수정 후 같은 검증과 재검토 |
| 중요한 결론을 바꿀 미확인 사항 + 허용된 미수행 조회 + 예산·범위 충족 | 보완 수집 후 해석·분석·검토 반복 |
| 근거 범위에서 타당하고 필요한 추가 조사가 없음 | 한계를 포함해 종료 |
| 원천 자료 부재·접근 불가·실행 가능한 조회 없음 | 판단할 수 없는 내용과 종료 사유를 남김 |
| 모델 미설정·확정된 호출 실패·유효 해석 자료 없음 | 가능한 코드 결과 보존, 단계 실패·생략 표시 |
| 예산 또는 라운드 소진 | 현재 검토 상태와 한계 기록. 미해결 초안을 정상 결론으로 승격하지 않음 |

추가 자료는 중요한 판단을 바꿀 수 있는지, 실제 확보 가능한지, 남은 예산 안에서 가치가 있는지 확인한다. 알려지지 않은 가용성을 ‘확보 가능’으로 단정하지 않으며 실패 이유를 기록한다. 같은 query/scope/기간/revision의 업무 재조회는 반복하지 않는다. 수집기의 기존 제한된 전송·분할 처리는 별도이며 전체 예산을 공유한다.

- 수집은 기존처럼 최초와 보완 1회, 최대 2라운드이며 보완 배치는 최대 3개다. 단순히 `causal_confirmation_evidence`가 없다는 이유로 모든 조회를 수행하지 않는다.
- 의미 수정은 attempt 전체에서 최대 1회다. 보완 수집 후 새 초안을 만드는 것은 수집 라운드에 속하며 수정 한도를 초기화하지 않는다.
- 형식·참조 복구와 의미 수정은 별도 사유로 기록한다. 새 해석·검토 단계의 무효 출력 복구는 각 논리 호출당 최대 1회, 기존 Synthesis 복구도 최대 1회를 유지한다. 전송 재시도는 공통 LLM 한도를 재사용하고 바깥에 추가 재시도 루프를 두지 않는다.
- 모든 LLM 호출은 같은 attempt에서 직렬로 실행하고 같은 token budget·deadline을 사용한다. 수집 예산·원격 실행 상태·취소 처리를 재설정하지 않는다.
- 초안 생성·수정 전에 bounded 입력과 기존 출력 cap으로 다음 검토에 필요한 토큰 여유를 계산해 남긴다. 남은 예산이 검토 입력·출력을 수용하지 못하면 새 초안을 시작하지 않고 제한된 결과로 종료한다. 시간은 호출마다 남은 deadline을 확인하며 추정 시간만으로 검토 완료를 보장하지 않는다.

### 실패와 최종 초안 처리

| 실패·생략 | 처리 |
|---|---|
| 증거 해석 실패 | 실패 기록과 기존 정규화 관측으로 분석 가능 범위를 판단. 원문 추정을 검증 사실로 대체하지 않음 |
| RCA 생성 실패·사용 가능한 자료 없음 | 코드로 확인 가능한 내용과 한계 제공. 무근거 후보를 생성하지 않음 |
| 검토 실패·생략 | 미검토. 검토 실행 성공과 타당 판정을 구분 |
| 검토 완료지만 판단 어려움 | `undetermined`, 확정 원인으로 승격하지 않음 |
| 수정 필요를 해결하지 못함 | 문제가 지적된 주장·연관 권고를 정식 결과에서 제외/보류. 의존성을 안전하게 분리하지 못하면 코드 기반 관측·한계만으로 대체 |
| fast path | 기존 규칙 경로 유지, 새 해석·분석·검토 생략 사유 기록. 최종 편집 호출과 구분 |
| 원격 종료 불명·취소·lease 상실·실행 deadline 초과 | [14 실행 계약](../common/14_모듈간_호출과_공통실행_계약.md) 우선. 부분 결과 공개로 우회하지 않음 |

검토한 초안은 정규화한 claims/recommendations/limitations와 입력 뷰 hash를 묶은 `analysis_id`로 고정한다. 기존 `content_hash()`를 재사용하며 job 전체 content_hash와 구분한다. LLM·Runbook 출처는 유지하고 권고에도 초안 내 local claim ID를 연결한다. 원인 후보·권고·한계를 변경하면 새 ID를 만들고 재검토해야 한다.

제외·보류로 최종 초안이 달라졌는데 재검토 예산이 없으면 **최종 초안의 review는 skipped/verdict=null**, 사유는 `draft_changed_after_review`로 남긴다. 이전 검토는 이전 ID의 evidence 이력에만 연결하고 최종 초안의 통과로 표시하지 않는다. 검토 완료·타당 판정을 단순히 문장 삭제 후 승계하지 않는다. 기존 assessment/result_status는 최종 유효 근거와 기존 규칙으로 다시 계산하며 검토 통과로 상향하지 않는다.

형식 검증을 통과한 초안·구조화 검토는 기존 evidence에 저장하되, 거절된 원시 모델 응답 전체를 새로 저장하지 않는다. 기존 사유·위치·hash 진단 및 민감정보 제한을 유지한다. 보류된 내용은 일반 보고서·Ops의 정상 후보로 인용하지 않는다.

### 사건 예시와 결과 추적

예시 입력은 XID 오류 보고 로그, 정확히 연결되지 않은 GPU 식별자, 일부 값이 0이지만 시간 공백이 있는 PCIe 지표다. 실제 환경의 검증 결과가 아닌 설계 설명용 사례다.

| 단계 | 처리 예시 |
|---|---|
| 코드 검사 | 조회 성공·지표 공백·식별자 불일치 기록. 다른 장비라고 확정하지 않음 |
| LLM ① | 오류 보고 확인, GPU 연결과 공백 시간 상태는 미확인 |
| LLM ② 초안 | 만약 ‘PCIe 지표가 0이므로 PCIe 원인은 아니다’라고 서술하면 검토 대상 |
| LLM ③ | 대상 연결과 관측 공백 때문에 원인 배제가 과도하다고 지적 |
| 수정 | ‘오류 보고는 확인했으나 GPU 연결·시간대 관측이 부족하여 PCIe 원인을 배제할 수 없다’ |
| 코드 결정 | 신뢰할 연결 자료가 조회 가능하고 중요하면 보완, 없으면 한계를 남기고 종료 |

가능한 최종 조합은 **부분 수집 / 오류 보고 확인·GPU 미확인 / 제한된 근거 안에서 타당 / 원인 미확정 / 조사 종료 / 추가 자료 확보 불가**다. 검토 LLM이 실패한 같은 사건은 ‘타당’ 대신 ‘미검토’다. 모든 조회에 성공했어도 근거 없는 단정이면 ‘수정 필요’다.

기록은 `D09 → 해석 → 초안 → 검토 → 추가 확인 필요 → D44`처럼 인과 연결을 제공한다. D 번호는 조회 식별자이지 실행 순서가 아니다. 실제 선택 이유·입력 refs·라운드·초안 ID·결정 기록으로 순서를 설명하며 생성 시각만으로 시작 순서·소요시간을 추정하지 않는다. 표시 기준은 [07](../frontend/07_프론트엔드_개발명세서.md#rca-평가-분리-표시)을 따른다.

### 함수별 개발 내용과 유지 범위

아래 함수와 파일이 현재 구현 위치다. 새 서비스·큐·DB 테이블 없이 기존 Worker·LLM·evidence/result 저장 경로를 재사용한다.

| 파일·함수 | 변경 내용 | 유지할 내용 |
|---|---|---|
| [workflow.py](../../../rcca-agent/src/rcca_agent/workflow.py) `run` | 요건 dict를 반환하는 `evaluate_requirements`, 라운드 분석 `analyze_round`, 선택·종료 `select_followup`로 분리. [evaluation.py](../../../rcca-agent/src/rcca_agent/evaluation.py)가 의미 수정·보류를 처리. 13개 위치 반환값 제거 | Runbook policy/extension provenance, scope·예산·종료 제한, 기존 수집 평가 기록 |
| 같은 파일 `normalized_state` | 정규화 결과와 별도로 검사 diagnostics 전달 | verified facts·대상/시간·관계 조건 |
| [공통 parsers.py](../../../shared/python/src/agent_common/parsers.py), [fleet_events.py](../../../rcca-agent/src/rcca_agent/fleet_events.py) | 필요한 파서에 선택적 diagnostics 인자를 추가해 실패 이유·위치 기록. 기존 파서를 중복 구현하지 않음 | 기존 반환 형식과 RCA/Ops 호출자, producer 시각·신원·단위 의미 |
| [observation_agents.py](../../../rcca-agent/src/rcca_agent/observation_agents.py) `collect_round`, [공통 Observation](../../../shared/python/src/agent_common/observation.py) | 기존 query 상태·제한을 새 평가에 연결. 수집기 전면 재작성 없음 | 병렬 task·예산 분배·정산·alias·원본 기록 |
| [evidence_interpretation.py](../../../rcca-agent/src/rcca_agent/evidence_interpretation.py) | `interpret_evidence`로 LLM ① 호출, `validate_interpretation`으로 구조·입력 refs·kind 검사 | 추론을 verified facts에 병합하지 않음 |
| [synthesis.py](../../../rcca-agent/src/rcca_agent/synthesis.py) `synthesis_input/synthesize/validate_synthesis` | 해석·제한된 발췌·검토 피드백 입력 추가. 기존 반환 tuple 유지. 정규화 관측 없음과 해석 가능한 발췌도 없음의 생략 조건 분리 | 참조·수치·언어·인과 제한과 기존 복구 검증 |
| [synthesis_context.py](../../../rcca-agent/src/rcca_agent/synthesis_context.py) `bounded_context` | 진단·발췌·해석도 같은 입력 크기 한도 안에 포함. 실제 전달 refs와 생략·view hash 기록 | 원본 불변, 표본 제한·context_selection |
| `workflow.py` 후보·권고 조립 부분 | `assemble_rca_draft`로 추출하여 규칙 후보까지 모은 후 초안 hash·검토 생성 | 기존 causal_status·confirmation rule·권고 eligibility/미수행 의미 |
| [analysis_review.py](../../../rcca-agent/src/rcca_agent/analysis_review.py) | `review_analysis`로 LLM ③ 호출, `validate_review`로 초안 ID·claim ID·전달 증거 참조·판정 검사 | 검토는 진실성 증명이나 규칙 우회 수단이 아님 |
| [prompts.py](../../../rcca-agent/src/rcca_agent/prompts.py) | 해석·검토 지침은 해당 모듈의 prompt에 정의. 기존 ‘수집 종료’ 전제를 제한된 후속 제안 계약으로 변경 | 로그 속 지시 무시, 도구 없는 분석·검토 |
| [공통 LLM](../../../shared/python/src/agent_common/llm.py), [settings.py](../../../shared/python/src/agent_common/settings.py) | 기존 `complete(stage=...)`에 `evidence_interpretation`, `analysis_review` stage 사용. stage별 usage delta·상태 기록, 검토 예산 확보 | 기존 모델 라우팅·기본 cap·직렬 호출·전송 재시도·원격 종료 불명 처리. 단계별 별도 모델 설정을 필수로 추가하지 않음 |
| [contracts.py](../../../shared/python/src/agent_common/contracts.py) `validate_result` | [04 확장](../common/04_Agent_동작_판단_명세서.md#81-rca-평가-분리-결과-확장)이 있으면 필드·상태·refs·최종 초안 ID 검사 | 구 결과 허용, result_status 산식·원인 확정 규칙 |
| [report.py](../../../rcca-agent/src/rcca_agent/report.py), [report_editor.py](../../../rcca-agent/src/rcca_agent/report_editor.py) | 상태·한계·미검토/보류를 코드 문장에 반영. 필수 제한을 편집 결과 밖에서도 유지 | 문장 ID 편집만 허용, 결정적 fallback |

### 소비자와 개발 단위

| 개발 단위 | 함께 반영할 곳 | 확인할 결과 |
|---|---|---|
| 결과·trace 계약 | 공통 validator·저장, Backend JSON 조회·trace 처리, Frontend의 새 필드 부재 처리 | 구 결과·미공개 결과·알 수 없는 버전 의미를 보존 |
| 진단·해석 | 파서 호출자, context builder, 새 해석 함수와 fixture | 불명확한 원문 유지, 의미 추정의 fact 승격 없음 |
| 초안·검토 | synthesis 호출자·repair tests, 후보/권고 조립, 새 review 함수 | 실제 최종 초안을 검토, 실패·변경 후 통과 승계 없음 |
| 반복 제어 | rule/batch selection·parallel tests, prompt, 공통 LLM 예산 | 정책 우회 없음, 한도 내 종료, 취소·원격 종료 불명 우선 |
| 보고서·Ops·화면 | [RcaDebug](../../../frontend/src/components/RcaDebug.tsx), [live](../../../frontend/src/components/live.tsx), [workflow 안내](../../../frontend/src/lib/workflow.ts), [Ops workflow](../../../ops-agent/src/ops_agent/workflow.py), [operator_insights](../../../ops-agent/src/ops_agent/operator_insights.py) | 검토 상태·미확인·원인 수준 유지, 보류 주장을 정상 인용하지 않음 |

기존 공개 ID/hash·과거 snapshot·입력 계약·DB 소유권을 바꾸지 않는다. Backend/JC는 RCA 의미를 재평가하지 않으며 공개 계약 검증을 계속 맡는다. 정책·설정 revision 변경이 필요한 구현에서는 해당 revision과 fixture를 함께 갱신하되 이 설계 작성으로 배포 설정을 변경하지 않는다.

개발 순서는 결과/trace 호환 → 기초 검증 진단·해석 → 초안 전체 검토 → 제한된 반복 → 보고서·Ops·UI 통합이다. 이는 코드 의존 순서이며 별도의 협의·승인 단계를 추가하는 것이 아니다. 실제 적용 순서와 롤백 경계는 14를 따른다.

### 검증과 완료 경계

[05의 T66~T79](../05_테스트_검수_기준서.md#rca-평가-분리-검수)를 구현 검수 기준으로 사용한다. 현재 [test_rca_analysis](../../../agents/tests/test_rca_analysis.py), [test_rca_repairs](../../../agents/tests/test_rca_repairs.py), [test_synthesis_context](../../../agents/tests/test_synthesis_context.py), [test_rca_rule_selection](../../../agents/tests/test_rca_rule_selection.py), [test_rca_batch_selection](../../../agents/tests/test_rca_batch_selection.py), [test_rca_parallel](../../../agents/tests/test_rca_parallel.py), [test_e2e](../../../agents/tests/test_e2e.py)를 회귀 대상으로 유지한다. 신규 해석·검토 단위 테스트와 Frontend 표시 테스트를 추가한다.

공통 Python 변경은 RCA/Ops 양쪽, 결과 변경은 Backend·Frontend·Ops와 Worker→JC 공개 경로를 함께 검사한다. 고정 LLM 응답으로 분기·참조·예산을 검증한 결과와 실제 모델이 과장·누락을 찾아낸 결과는 구분한다. 실제 사례는 같은 증거의 적절한 설명과 과장된 설명, 상충·대상 미확인·관측 공백을 포함하고 사람이 원본 근거와 비교한다. 호출 시간·토큰·검토 누락/오검출을 기록하며 보편적인 정확도 목표나 검토 점수를 임의로 만들지 않는다. 실행 증거가 생기기 전에는 Agent QA를 통과 기록으로 갱신하지 않는다.

## 남은 과제와 검수 조건

| 남은 과제 | 완료를 판단할 근거·소비자 |
|---|---|
| 오류별 보완 조회·지침 전환 | [265개 검토](../../../rcca-agent/runbooks/transition-review-20261014.json)의 미확정 정의·정보성 이벤트·병합 대상 검토, 최신 발행 hash/profile 대조, Backend/RCA 발행·소비 검증 |
| 평가 척도의 실제 모델 검증 | 구현된 6항목 rubric을 같은 증거의 적절한 설명/과장된 설명 쌍에 적용해 누락·오검출을 사람이 원본과 대조. 고정 응답 테스트를 의미 정확도로 대체하지 않음 |
| 중간 분석과 최종 언어 표현 분리 | refs·수치·불확실성 보존, 의미 검사의 언어 의존 제거/대체, 최종 한국어 가독성 검수. 현재는 중간 한국어 검사가 실행됨 |
| 실제 품질·부하 | 원천 대상/시각/상태와 실제 원인을 대조한 사례, 원본/모델 입력 생략 영향, 동시 실행·큰 evidence·조회 지연/RSS 측정 |

미구현 목표는 현행 기능으로 설명하지 않는다. 검증 revision·환경·범위는 [Agent QA](../../../agents/QA.md)를 따른다. 코드와 문서 변경만으로 운영 배포·실제 원인 확인을 주장하지 않는다.
