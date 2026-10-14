# 11. RCA Agent 실행·판단 계약

현재 실행 설명은 [RCA README](../../../rcca-agent/README.md)가 소유한다. 이 문서는 현재 코드가 사용하는 계약과 판단 경계, 남은 검수 조건을 정리한다. 입력/결과의 상세 공통 필드는 [실행 계약](../common/14_모듈간_호출과_공통실행_계약.md), DB 소유권은 [Shared](../../../shared/README.md)를 따른다.

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

Synthesis는 관측 라운드 종료 후 호출한다. fast path와 유효 근거 없음·모델 미설정은 별도 상태로 남긴다. [입력 구성](../../../rcca-agent/src/rcca_agent/synthesis_context.py)은 원본을 수정하지 않고 제한된 모델 뷰를 만든다. 입력 refs·원본/전달 크기·생략 수를 기록하고 수정 요청에서도 실제 입력 범위를 남긴다.

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

## 남은 과제와 검수 조건

| 남은 과제 | 완료를 판단할 근거·소비자 |
|---|---|
| 오류별 보완 조회·지침 전환 | [265개 검토](../../../rcca-agent/runbooks/transition-review-20261014.json)의 미확정 정의·정보성 이벤트·병합 대상 검토, 최신 발행 hash/profile 대조, Backend/RCA 발행·소비 검증 |
| 분석 적절성 평가와 재조사 | 실제 사건 기준 지지/반박/부족 근거 평가, 자료 부족과 틀린 추론 구분, 재조회 예산·중복 방지, Backend/Frontend/Ops 결과 소비 확인. 현재 Synthesis 후 Runbook 재선택 루프는 없음 |
| 중간 분석과 최종 언어 표현 분리 | refs·수치·불확실성 보존, 의미 검사의 언어 의존 제거/대체, 최종 한국어 가독성 검수. 현재는 중간 한국어 검사가 실행됨 |
| 실제 품질·부하 | 원천 대상/시각/상태와 실제 원인을 대조한 사례, 원본/모델 입력 생략 영향, 동시 실행·큰 evidence·조회 지연/RSS 측정 |

미구현 목표는 현행 기능으로 설명하지 않는다. 검증 revision·환경·범위는 [Agent QA](../../../agents/QA.md)를 따른다. 코드와 문서 변경만으로 운영 배포·실제 원인 확인을 주장하지 않는다.
