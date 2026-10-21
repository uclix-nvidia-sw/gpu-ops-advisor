# RCA Agent 모듈 설계서

현재 실행의 담당 문서는 [RCA README](../../../rcca-agent/README.md)다. 이 문서는 입력·수집·작성·공개 경계와 구 결과 호환 계약을 정의한다. 독립 평가·목표 달성·평가 예약 예산·후속 조회 선택 설계는 현행 실행에서 제거했다.

## 문서 관계와 읽는 순서

- [실행 계약](../common/14_모듈간_호출과_공통실행_계약.md): claim·lease·attempt·공개 소유권.
- [공통 결과 계약](../common/04_Agent_동작_판단_명세서.md): 저장 결과와 기존 소비자 호환.
- [Shared](../../../shared/README.md): DB 소유권과 immutable snapshot.
- [Runbook 발행](../../../rcca-agent/runbooks/DB-WORKFLOW.md): 실제 발행 revision의 적용 절차.
- [Agent QA](../../../agents/QA.md): 검증 revision·환경·fixture/운영 구분.

## 입력과 실행 소유권

Incident → JC → RCA Worker의 기존 경로를 사용한다. Backend나 GUI가 Worker를 직접 호출하지 않는다. JC가 작업·예산·시도·공개를 소유한다. RCA는 고정 사건 snapshot·scope·대상·기간·data cutoff와 발행 Runbook revision을 사용하고 원본 evidence를 보존한다. 별도 큐나 장비 조치 API를 만들지 않는다.

## Runbook 검색과 적용

선택 전 발행 상태·content hash·검토 hash·호환 조건·query ID 계약을 검사한다. 검색 관련도는 원인 확률이 아니다. 적용 조건과 권고의 조건은 유지하며, 관측된 증상을 물리적 원인이나 조치 완료로 승격하지 않는다. 발행본이 없을 때의 일반 조사 계획도 동일 실행 경로를 따른다.

## 관측 계획과 보완 선택

선택한 observation plan 전체를 한 수집 단계에서 실행한다. 과거 `required_queries`는 observation plan이 없는 발행본의 입력 호환용이다. 별도의 필수 조회 충분성 판정·평가 후 보완 조회·예상 밖 근거에 따른 런북 확장은 없다. 기존 binding·cluster/node/GPU 범위·조회 예산·deadline·동시성 제한은 유지한다.

Xid 79/D44와 SXid 11001/D47의 최신 계획에서는 같은 노드 30분 로그와 관련 메트릭을 함께 수집해 코드·메시지별 구간과 장치별 값을 정리한다. 다른 발행본의 내용을 자동으로 해당 계획으로 바꾸지 않는다. host 이력은 식별된 대상에 대해 기존 저장소 context의 Incident 자료를 연결한다. DB 읽기와 여러 MCP 요청은 단일 트랜잭션이나 단일 HTTP 호출이 아니다.

## 관측의 판단 가능 범위

- 조회 성공은 응답 확보만 뜻한다. 값·단위·producer·대상·발생 시각·freshness가 해당 판단에 유효한지 별도 확인한다.
- Fleet 로그의 기록 시각은 장비 발생 시각이나 현재 상태를 자동으로 보증하지 않는다. `reported_error_code`와 현재 상태 fact를 분리한다. producer 시각 0은 유효한 사건 시각으로 승격하지 않는다.
- PCI 주소는 정규화한 후 제공된 인벤토리와 비교한다. 일치해도 후보 연결이며, 불일치는 제공된 목록에서 연결을 확인하지 못했다는 뜻이다. NVSwitch 주소는 GPU 인벤토리로 검증하지 않는다.
- GPU·Pod·Namespace 관계를 사용하는 기존 경로는 동일 대상·기간·UID 조건을 만족한 관측만 연결한다. 노드에 같은 시각 존재했다는 이유로 특정 GPU의 사용자나 업무 피해로 단정하지 않는다.
- 생산자가 같은 DCGM Field ID를 읽어도 표본을 합산하거나 독립된 장애 근거로 중복 가산하지 않는다. [생산자별 메트릭 의미](references/metric-meaning.md)와 [원천 검토 자료](references/README.md)를 따른다.

## 모델 입력과 원인 후보 검증

계획 수집 후 해석·원인 분석을 한 번에 작성한다. [입력 구성](../../../rcca-agent/src/rcca_agent/synthesis_context.py)은 원본을 수정하지 않고 제한된 모델 뷰를 만들며 실제 입력 refs·크기·생략 수를 기록한다.

응답에는 interpretation·hypotheses·limitations가 있으며 가설은 관측 근거와 유효한 finding을 참조해야 한다. 구조·참조·장치 신원·수치·표현을 검사한다. 잘못된 개별 항목은 제외하고 의존 가설도 제외하되 유효한 부분은 유지한다. 최상위 구조 실패는 전체 응답을 거절한다. 같은 자료 재작성이나 독립 검토는 없다. 진단에는 실패 위치·코드·문장 hash를 남기고 거절 원문 전체를 복사하지 않는다.

현재 검증은 원인 정확도나 확률을 산출하지 않는다. LLM 후보는 인과 확정으로 승격되지 않으며, 적용 가능한 Runbook에서 나온 후보와 관측 요약도 출처를 구분한다. 원인 후보가 없어도 보고된 증상과 부족한 근거를 보고할 수 있다.

## 결과·보고서·공개

통합 작성 LLM 한 번 → 코드 구조·원문 참조 검증 → 자료 hash 고정 → 보고서 작성 LLM 한 번 → JC 완료 검증·공개 순서다. 과거 `generation_mode=separate`도 현행 Worker에서 별도 해석 호출을 추가하지 않는다. 모델의 평가 피드백·같은 증거 재작성·출력 잘림 재요청은 없다. 무효 항목과 의존 가설을 제외하되 유효한 관측·조건부 지침은 보존한다.

보고서는 사건 요약, 분석·권고, 로그·메트릭, host 이력, 원문 상세를 제공한다. 목표 달성·근거 충분성·독립 평가 척도·평가 예약 예산을 화면에 붙이지 않는다. 실제 조회/작성 실패, 잘림, 모델 사용량과 요청 참조는 실행 기록에 남긴다. 보고서가 고정 자료를 변경하면 공개하지 않는다.

## 평가 분리 설계·개발

과거 평가 실행 설계는 폐기했다. Worker의 `analysis_review`, 평가 예산 예약, goal 판정, 보완 조회 선택 함수는 제거했다. 현재 [evaluation.py](../../../rcca-agent/src/rcca_agent/evaluation.py)는 한 번의 작성 결과와 실행 진단을 조립하고 [analysis_material.py](../../../rcca-agent/src/rcca_agent/analysis_material.py)는 주장·근거 hash를 만든다.

기존 JC·Backend·Ops 결과 소비 계약을 바꾸지 않기 위해 `quality.rca_evaluation` envelope만 유지한다. 신규 `review`는 `execution_status=skipped`, `reason=not_requested`, `verdict=null`, 빈 `evidence_refs`다. `investigation.stop_reason=no_available_followup`은 기존 enum 호환값이며 goal 판정이나 실제 후속 조회를 뜻하지 않는다. 과거 결과와 원문은 덮어쓰지 않는다.

### 분석 품질 평가 척도 — rubric 1

구 결과의 rubric·판정 구조는 저장 자료 호환 검증 대상으로만 남는다. [테스트 전용 fixture](../../../agents/tests/legacy_review_fixtures.py)는 Worker 패키지에 포함되지 않는다. 새 보고서에서 이 척도를 실행하거나 평가 패널을 표시하지 않는다. 실제 보고서 품질은 운영자가 원문·수치·시각·대상·권고 조건과 대조해 검수한다.

### Runbook 판단 기준과 품질 검토·종료 설계

발행 JSON의 `decision_policy`는 과거 내용/hash를 읽기 위한 구조 검증만 유지한다. `assess_policies`, `finish_assessment`, `model_assessment`는 제거했다. 새로운 계획은 goal이나 causal confirmation을 충족시키기 위한 평가 정책을 요구하지 않는다. 계획 수집 후 작성으로 이어지며 대상 범위와 권고 적용 조건 검증을 생략하지 않는다.

## 검증과 완료 경계

- [평가 없는 실행 행렬](../../../agents/tests/test_rca_no_evaluation.py): 구 발행본·비코드 Fleet 오류·combined/separate 설정·정상/HTTP 실패/잘림/예산 부족에서도 평가나 추가 조회 선택을 재활성화하지 않는다.
- [관측 비교](../../../agents/tests/test_rca_incident_dossier.py): Xid·SXid 원문, 대상 충돌, 메트릭, 반복 보고·원인 경계.
- [원문 보존](../../../agents/tests/test_rca_runbook_evidence.py): 선택 revision과 원문 hash·참조 보존.
- [실제 프로세스 E2E](../../../agents/tests/test_e2e.py)와 [dossier 공개](../../../agents/tests/test_rca_dossier_e2e.py): 격리 DB·JC·Worker·공식 MCP·고정 모델 응답을 통한 저장·공개.
- [RCA UI](../../../frontend/src/components/RcaNarrative.test.tsx): 원문 보존, 평가 표시 제거, 빈 결과와 실패 표시.

fixture 검사·빌드는 운영 Grafana/Nemotron 품질이나 배포 완료를 뜻하지 않는다. 실제 환경 검수는 배포 후 오류 주입 시각·대상·로그·메트릭·host 이력·권고 조건을 대조한다. Ops 실행·보고서와 공유 결과 검증기는 변경하지 않는다.

## 남은 과제와 검수 조건

오류별 수집 계획·출처·지침을 실제 원천과 대조하고 검수된 revision을 발행한다. 실제 모델의 장문 출력·관측 누락·잘림·호출 지연과 사용자 조사 시간 절감은 운영 자료로 검증한다. 평가 척도 재도입이나 토큰 예산 일괄 증가는 이 작업의 목표가 아니다.
