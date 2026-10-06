# D binding 공통 런타임 적용 기록

기준: 2026-10-06, `main`의 `05bb4f69aec024ed72da72e266d63fa267be8f9a`와 사용자 확인 JSON. [개발 계획](d-contract-redesign-plan.md)과 [매핑 설계](d-query-mapping.md)의 구현 진행 기록이다. 두 문서의 전체 완료 기준을 대체하지 않는다.

## 입력 파일 확인

사용자가 제공한 `config.example 3.json`과 보관본 `config.example.json`은 byte 단위로 같았다. SHA-256은 `85b348a142b7656a7e35058995131bbecd4a0d1b8cddf9c7bde03e28ed3bd932`이다. [공통 원본](../../../agents/config.example.json)과 [Helm 사본](../../../charts/gpu-ops-advisor/files/agents.json)에 그 파일을 그대로 적용했다.

`d-query-profile/3-draft`, `single-query-v3-draft`, `d-contract-restart-20261006-r1`은 전달 파일의 스키마·계약·revision 식별자다. MD가 정한 릴리스 번호가 아니다. 원본의 `delivery.runtime_ready=false`도 유지했다. 런타임 코드가 이 구조를 읽는 것과 환경별 binding이 준비되는 것은 별개다.

45개 논리 D와 45개 후보 binding, Fleet Intelligence·NVIDIA DCGM Exporter·KSM 생산자 목록을 유지한다. 기본 실행 registry에는 D01/D05/D08/D14가 없다. 등록 정보·과거 참조는 실행 정의로 사용하지 않는다. 모든 `selected_binding`은 아직 null이다. **이 예제를 환경 검증 없이 그대로 운영에 적용하면 관측 기반 결과는 미확인/불충분 상태가 된다.**

## 구현된 공통 계약

- RCA와 Report 모두 `Settings.profile()` → `validate_profile()`을 사용한다. `Observation`도 같은 검사를 거친다. 선택된 candidate, 등록되지 않은 producer/source, 여러 메트릭을 합친 표현식, 누락된 검증 규칙은 거부한다.
- `queries[D].selected_binding` 또는 `clusters[cluster_id].bindings[D]`로 하나를 선택한다. 클러스터의 명시적 null은 기본 선택을 해제한다. 첫 후보 외 대안은 의미·단위 등 동등성을 확인한 `equivalence_evidence_refs`가 있어야 선택할 수 있다. 자동 대체·서로 다른 producer 표본의 병합은 없다.
- verified binding에는 producer/version, revision, 정확한 datasource UID, cluster, selector, 대상 label mapping, 단위/타입, 시간 기준, 표본 간격, 최대 유지 시간, invalid/reset 규칙, 조사 기간·보존·근거 참조가 필요하다. 이 필드 검사는 실제 운영 증거의 진실성을 대신 검증하지 않는다.
- metric은 원본 Prometheus 표본 시간만 지원한다. log는 Loki 기록 시간을 명시한다. counter reset은 현재 `reject_decrease`만 지원한다. log에 적용되지 않는 표본/invalid/reset 규칙도 `not_applicable`과 사유를 명시한다. 기존 숫자 산식이 소비하는 기본 D는 그 산식의 단위·타입과 일치해야 한다.
- 미선택 binding은 datasource 탐색과 원격 조회를 모두 수행하지 않는다. 선택 환경과 요청 cluster가 다르거나, Namespace/target을 표현할 label이 없으면 불가 사유를 남긴다. Host/GPU 관측을 위해 요청 범위를 임의로 확대하지 않는다. 관계를 통한 Host 범위 투영은 아직 지원하지 않는다.
- evidence에 query/binding revision, producer/version, 단위·타입·시간·label·invalid/reset·freshness 규칙을 보존한다. 원본 snapshot은 그대로 두고 계산용 사본만 canonical label과 무효 표본 규칙을 적용한다. 무효 표본 시각을 건너뛰어 이전 값을 계속 유지하지 않는다.
- binding을 쓰지 않는 구 profile은 명시적으로 계속 지원한다. [v7 테스트 fixture](../../../agents/tests/fixtures/config-v7.json)는 이 호환성 검사용이며 새 기본 배포 설정이 아니다. 과거 evidence/result/hash나 DB 발행 revision은 재작성하지 않았다.

## 소비자 연결과 현재 한계

| 경로 | 이번 구현 | 남은 범위 |
|---|---|---|
| 기본 D 통합 | D02를 장비 관측·활동·관측 연결 입력으로 사용, D06 UID와 시간 중첩 확인. D09로 기존 상태 fact·freshness 처리 | 환경별 override의 실제 할당 원본 검토. D02 Pod label은 독점/공유/MIG 할당 증거가 아님 |
| Report O01~O11 | 매핑 §6의 기본 추가 입력을 선택하고 quality/evidence에 연결. 선택 실패·예산 초과는 기존 독립 수치를 지우지 않음. O08 양 기준 유지 | 조건부 조사와 추가 입력별 모든 신규 출력·판정은 미완료 |
| O01 첫 계산 사례 | D15 여유량, D03/D16 동일 GPU·Node·단위·시간 교집합의 용량 비율, D18 CPU 사용률, D19 window별 load. D20은 Node condition 관측으로 유지 | 실환경 이름/단위/label 검증, 다른 신규 D의 전체 산식 |
| 값 처리 | sentinel/범위/비정상 숫자 제외, counter 감소·누락·시간 gap 거부 함수 | counter 함수는 아직 D별 최종 보고서/RCA 출력에 연결되지 않음. bitmask/enum별 의미 해석도 미완료 |
| RCA 작성 원본 | 267개 원본의 D05 요구를 D09와 필수 fact로 병합, 일반 패키지 사본 동기화. 생성 불가능한 D→fact 요구 거부 | 코드별 추가 D·개별 의미 검토, 오류 코드 없는 6개 사례 Runbook, DB draft 등록·검토·발행 |
| 표시/내보내기 | 추가 O01 지표, binding 불가 사유, D04 실제 GPU 온도 및 신규 D 표시명 동기화 | 신규 분석 출력이 늘 때마다 해당 소비자 추가 검수 |

사용량 비율은 같은 장비의 사용량/총량이 유효한 시간에만 계산한다. 용량 0, 사용량>용량, 중복 시계열, 단위/신원 충돌은 계산하지 않는다. 신규 용량 근거가 없어도 기존 VRAM 수치는 유지한다. 기본 수집을 먼저 수행하고, 추가 입력은 남은 조회 예산과 남은 시간의 절반 이내에서 수집해 계산/보고 단계 시간을 남긴다. 새 메트릭의 null은 0으로 표시하지 않는다. D19는 window를 유지하며 평균을 Host 건강 판정으로 해석하지 않는다.

Runbook 공통 변경은 원본 267개와 패키지 사본만 대상으로 한다. `knowledge_key`, compatibility, 코드별 문헌·지침·조건·조사 전용 속성은 유지한다. 공통 변환 검사는 **267개 각각의 신규 분석 의미를 검수했다는 뜻이 아니다.** 이미 발행된 DB 원본을 덮어쓰거나 새 revision을 등록하지 않았다.

## 수정·적용 순서

1. 업로드 JSON과 기준 MD/원격 main을 확인한다. 공통 로더·binding 검증·원본 evidence 처리부터 수정한다.
2. 두 Worker의 D02/D09 소비, Runbook 원본/패키지, 추가 입력 선택과 첫 O01 산식을 함께 연결한다.
3. 표시·내보내기·Helm 사본·CI 검사를 맞추고, 구 profile 회귀와 새 profile의 미선택/선택 경로를 검수한다. **JSON만 먼저 push하거나 구 Worker에 먼저 적용하지 않는다.** 관련 소스와 테스트·문서를 하나의 검토 가능한 변경으로 관리한다.
4. 운영 적용 전 각 대상 환경의 증거 원장을 작성하고, 실행할 binding만 verified로 선택한 별도 환경 revision을 만든다. 두 Worker가 같은 환경 설정과 지원 코드를 읽는지 확인한다. chart의 `configuration.agents`는 전체 객체를 대체하므로 부분 override로 취급하지 않는다.
5. 기존 실행을 drain한 뒤 두 Worker와 설정을 함께 전환한다. 대상 DB의 구 Runbook revision은 보존하며, 새 D 요구는 기존 draft→검토→발행 절차를 거친 새 revision에서 적용한다. 구 profile/Worker/Runbook revision 조합을 회수 기준으로 보관한다. 이 문서는 배포·발행을 수행한 기록이 아니다.

## 검증 경계

2026-10-06 후속 [환경 조사 원장](../../evidence/d-binding-cpc-20261006.md)은 실환경 표본 확인과 아직 부족한 활성화 근거를 구분한다. D19의 `window`, D20의 `condition/status` 매핑은 verified binding의 필수 소비 차원이며, 대상 신원과 서로 다른 원본 label을 가리켜야 한다.

재현 명령과 결과는 [Agent QA](../../../agents/QA.md)에 기록한다. `test_binding_contract.py`는 계약·수집·소비 산식을 합성 입력으로 검증한다. `test_e2e.py`의 binding profile 사례는 실제 Worker·JC·공식 MCP·격리 PostgreSQL로 조회와 결과 발행을 검증하지만 Grafana/LLM 응답은 fixture다.

실환경 Grafana/LLM 검수, P1 환경 원장, 전체 P2 소비 계약, 전체 신규 계산·조건부 조사, Runbook 발행과 배포는 완료되지 않았다. DB 스키마·JC의 lease/publication 계약 변경은 이 단계에 필요하지 않아 수행하지 않았다.
