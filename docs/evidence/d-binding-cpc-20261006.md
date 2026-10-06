# CPC-1/CPC-2 D binding 환경 조사 — 2026-10-06

## 기준과 완료 범위

최신 `origin/main`과 로컬 HEAD는 조사 시작 시 `2849de10205e001423d6b69e268357e975cd43e6`으로 같았다. [PR #71](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/pull/71)은 병합되었고, PR CI의 필수 gate는 성공했다. PR 준비 중 추가된 UI 변경 PR #72의 `a3dd8c4`를 로컬에 fast-forward로 반영했으며 조사·회귀 기준의 Worker/공통 설정은 동일하다. PR 이미지 발행용 `images` job은 skipped였으며 이를 실행 성공으로 세지 않는다.

[개발 계획 P1](../specs/common/d-contract-redesign-plan.md)의 환경 원장 단계다. [매핑 설계](../specs/common/d-query-mapping.md)의 45개 D를 두 클러스터에 대조하여 [90개 환경별 항목](d-binding-cpc-20261006.json)을 작성했다. 실제 Grafana 조직 2의 Mimir/Loki를 읽기 조회했다. Worker 배포·설정 활성화·DB Runbook 등록/발행·LLM 실행은 수행하지 않았다.

**이번 결과는 원본 데이터의 존재와 형태 확인이며, binding의 verified 승격이 아니다.** 사용자 제공 출력으로 Fleet image tag/digest와 DCGM/Exporter tag를 추가 확인했다. KSM 버전, Exporter digest, 현재 수집 설정, 타입/단위/무효값 규칙, 보존 정책과 최대 유지시간 승인은 아직 필요하다. [PDF 재검증](fleet-dcgm-pdf-audit-20261006.md)은 문서 내부 산술·생산 코드 정의와 과거 원본 미확인 범위를 구분한다. 공통 예제 JSON과 Helm 사본의 선택 상태는 변경하지 않았다.

## 직접 확인한 결과

| 구분 | CPC별 결과 | 의미와 한계 |
|---|---|---|
| 정확한 후보 이름의 메트릭 표본 | 각 28개 D, 합계 56개 환경 항목 | 짧은 원본 range-vector 결과. 값의 단위·의미 검증과 별개 |
| 정확한 후보 이름이 관측되지 않음 | 각 15개 D, 합계 30개 환경 항목 | 조회한 시점/기간 한정. 전체 기간 미수집이나 장비 미지원으로 확정하지 않음 |
| D09 Fleet 로그 | 두 CPC에서 표본 확인 | 전체 100건 한도에 도달. 기간 전체·오류 부재·현재 건강 상태의 근거가 아님 |
| D13 workload 로그 | 실행 원본 미확정으로 조회 보류 | Fleet component 로그를 workload 로그로 대체하지 않음 |

- 표본 확인: D02/D03/D04/D06/D10/D11/D15/D16/D17/D18/D19/D20/D21/D22/D33/D34/D36~D43/D45~D48.
- 정확한 후보 이름 미관측: D07/D12/D23~D32/D35/D44/D49. Fleet에서 보이는 유사 소문자 이름은 다른 생산자 후보이며 동등성을 자동 승인하지 않는다.
- D07 유효 요청은 원본이 확인되지 않았다. D21의 `kube_pod_container_resource_requests`에는 CPU·메모리 등 여러 resource가 있으므로 GPU resource selector가 필요하다. 원시 요청을 유효 요청으로 대체하지 않는다.
- D12 `kube_node_status_allocatable` 역시 조회 창에서 확인되지 않았다. Node condition이나 `up`으로 GPU 용량을 대신하지 않는다.

## 실행 계약에 영향을 주는 관측

| 항목 | 직접 관측 | 필요한 처리 |
|---|---|---|
| 환경 필터 | Mimir의 cluster 구분은 `cluster_id` | 실제 selector에 이 이름을 사용. 빈 `cluster` 집계를 환경 검증 근거로 쓰지 않음 |
| Exporter GPU 신원 | `UUID`, `uuid`, `node` 및 exporter 메타데이터 | 승인된 하나의 신원 매핑 사용. 일부 표본의 Pod 라벨 부재는 미할당/독점 할당의 증명이 아님 |
| Fleet GPU 신원 | `uuid`, `node`, `job=fleet-intelligence-agent` | Exporter와 조인할 때 같은 장비·시간·단위 검증 필요 |
| D19 CPU load | `load_duration`에 기간 구분 | binding의 `target_labels.window=load_duration`. 1/5/15분 관측을 합치거나 percent로 해석하지 않음 |
| D20 Node condition | `condition`, `status`, `node` | 세 차원을 보존. 상태값을 GPU health로 승격하지 않음 |
| D17 메모리 비율 | `_percent` 이름이지만 조사 표본이 0~1 범위 | Fleet v1.5.0-rc.1 소스 정의는 Used/(Total−Reserved), 0~1. D03/D16의 Used/Total과 대체 금지. 배포 변환 설정은 미확인 |
| 표본 간격 | Exporter/KSM 계열 약 15초, Fleet는 약 60초와 120~300초 공백 | 관측 간격과 max_hold 정책을 구분. 공백을 0이나 이전 값으로 메우지 않음 |
| D09 로그 | attributes에 component/health/time/log_type, resources에 k8s.node.name 등 | 사건 시각과 Loki 기록 시각·producer/freshness의 의미 검증이 별도로 필요 |

D19와 D20의 소비 차원 라벨이 빠졌거나 Node 신원 라벨과 같은 원본 필드를 가리키는 verified binding은 공통 validator가 거부하도록 보완했다. 두 Worker에 같은 검사가 적용된다. `load_duration`을 `window`로 매핑한 합성 입력이 O01의 기간별 독립 출력에 도달하며 원본 snapshot을 보존하는 회귀검사를 추가했다. 이 검사는 실환경 binding 승격을 뜻하지 않는다.

## 조사 방법과 근거 보관

Grafana Explore의 instant 조회에 원본 range vector를 사용했다. 기본 메트릭은 3분, KSM은 1분, Fleet는 20분의 표본을 확보했다. 최초 가용 목록은 1시간 화면에서 15초 평가 간격으로 조회했으며 이 집계 결과는 원본 표본 주기의 증거로 사용하지 않았다. 추가 instant 목록은 `__name__,cluster_id`로 구분했다. 실제 반환 시각 범위와 실행식·파일 SHA-256은 JSON 원장의 `evidence_exports`에 있다.

원본 데이터는 로컬 `.local/p1-binding/`에만 보관한다. 커밋 대상 원장은 label 이름·조회 방법·검증 상태와 한계만 남기며 UUID·Pod/Node 이름·IP·로그 원문을 포함하지 않는다. 원장의 로컬 파일명/해시는 비공개 원본을 대조하는 참조이며 다른 checkout에 해당 파일이 있다고 가정하지 않는다.

초기 다중 metric `count_over_time` 조사식은 이름 제거에 따른 label 충돌 오류로 폐기했다. 브라우저의 대용량 복사 오류와 한글 입력이 섞인 조회 오류 역시 제외했다. 원장에 열거한 정상 JSON export만 사용했다. 인증 없는 Grafana API는 HTTP 401이므로 현재 브라우저의 승인된 세션에서만 조사했다. 응답 개수나 단일 HTTP 성공을 의미 검증으로 취급하지 않는다.

## 다음 확인 순서

1. 회신받은 Fleet tag/digest·DCGM/Exporter tag는 원장의 `deployment_inventory`에 기록했다. KSM 이미지, Exporter imageID, 참조 ConfigMap과 실제 설정은 추가 확인이 필요하다. PDF metrics 원본 두 묶음을 받아 수량·UUID별 비교를 재현했고 에너지 표기 오류 1건을 확인했다. 정정과 states의 시각 누락은 PDF 재검증 문서에 기록했다.
2. 해당 버전의 Fleet metric 생산 코드/OTel 변환, DCGM collectors CSV, KSM allowlist와 Alloy 전송 선별 규칙 확인. Secret/토큰은 수집하지 않는다.
3. 기본 D부터 타입·단위·신원·시각·invalid/reset·max_hold·보존 근거를 채우고, 검증을 충족하는 환경별 binding만 선택한 revision 작성. 실행 예제와 Helm 사본의 동기화 규칙을 지킨다.
4. 두 Worker와 O01의 실제 원본 재생/결과 검수 후, 남은 신규·조건부 분석과 개별 Runbook의 소비 계약을 구현한다. 배포와 DB 발행은 별도 단계다.
