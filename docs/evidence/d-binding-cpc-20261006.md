# CPC-1/CPC-2 D binding 환경 조사 — 2026-10-06

## 기준과 완료 범위

최신 `origin/main`과 로컬 HEAD는 조사 시작 시 `2849de10205e001423d6b69e268357e975cd43e6`으로 같았다. [PR #71](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/pull/71)은 병합되었고, PR CI의 필수 gate는 성공했다. PR 준비 중 추가된 UI 변경 PR #72의 `a3dd8c4`를 로컬에 fast-forward로 반영했으며 조사·회귀 기준의 Worker/공통 설정은 동일하다. PR 이미지 발행용 `images` job은 skipped였으며 이를 실행 성공으로 세지 않는다.

[개발 계획 P1](../specs/common/d-contract-redesign-plan.md)의 환경 원장 단계다. [매핑 설계](../specs/common/d-query-mapping.md)의 45개 D를 두 클러스터에 대조하여 [90개 환경별 항목](d-binding-cpc-20261006.json)을 작성했다. 실제 Grafana 조직 2의 Mimir/Loki를 읽기 조회했다. Worker 배포·설정 활성화·DB Runbook 등록/발행·LLM 실행은 수행하지 않았다.

**이번 결과는 원본 데이터의 존재와 형태 확인이며, binding의 verified 승격이 아니다.** 후속 사용자 제공 preflight 출력으로 Fleet·DCGM HostEngine·Exporter·KSM의 image tag/digest를 확인했다. 실제 CSV 내용·전송 규칙, 타입/단위/무효값 규칙, 중앙 보존 정책과 최대 유지시간 검증은 아직 필요하다. [PDF 재검증](fleet-dcgm-pdf-audit-20261006.md)은 문서 내부 산술·생산 코드 정의와 과거 원본 미확인 범위를 구분한다. 공통 예제 JSON과 Helm 사본의 선택 상태는 변경하지 않았다.

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

## 후속 서버 preflight 대조

사용자가 제공한 2026-10-06 08:53:59~08:55:42 UTC의 세 출력에서 JSON을 파싱했다. 원본은 로컬에만 보관하고 첨부 파일의 SHA-256, 필요한 버전·설정 요약을 JSON 원장의 `preflight`와 `deployment_inventory`에 추가했다. 이번 확인은 메타데이터 대조이며 운영 조회 활성화나 Worker 재시작이 아니다.

| 항목 | CPC-1 | CPC-2 |
|---|---|---|
| KSM | v2.17.0, image digest 확인 | v2.18.0, image digest 확인 |
| Exporter | 4.2.3-4.1.3-ubuntu22.04, 2개 Pod digest 일치 | 4.4.2-4.7.0-distroless, 2개 Pod digest 일치 |
| Fleet | 1.5.0-rc.1, 2개 Pod digest 일치 | 1.5.0-rc.1, 2개 Pod digest 일치 |
| Alloy | v1.19.2, 설정에 15s scrape / 10s timeout 행 | 같은 버전·시간 행, 설정 해시는 다름 |
| monitoring Prometheus 보존 인수 | 7d | 10d |
| 수집 오류 | 0건 | rulefiles ConfigMap 4개 unreadable |

- KSM의 4개 D × 2개 환경에 버전 근거를 추가하여 생산자 버전이 있는 항목은 74개에서 82개가 됐다. 90개 항목 모두 `candidate`, `selected=false`를 유지한다. 버전 확인으로 의미 검증을 대신하지 않는다.
- CPC-1 KSM에는 `--metric-labels-allowlist`가 있고 CPC-2 출력에는 없다. 이는 **메트릭 이름 allowlist가 아니며**, D12가 중앙 조회에 안 보인 원인을 확정하지 않는다. 두 설정을 동일하다고 가정하지 않는다.
- Exporter 두 환경 모두 `DCGM_EXPORTER_COLLECTORS=/etc/dcgm-exporter/dcp-metrics-included.csv`를 보고했다. 이 경로의 파일 내용은 출력에 없으므로 upstream 기본 CSV와 같다고 확정할 수 없다.
- 중앙 `gpu-ops-config`의 `agents.json`은 45개 D, cluster override 없음, 선택된 binding 없음이다. SHA-256 `fd157a7de21c870e83619a56b925bb38bf246c6a6036e23e9859a07ab18d7b4b`, 114,026 bytes는 저장소 JSON의 CRLF를 LF로 변환한 결과와 정확히 같다. 기존 원본 해시 차이는 줄바꿈 때문이다. 이 확인은 ConfigMap 내용에 한정하며, 실행 중인 두 Worker의 실제 로드 상태나 이미지의 소스 commit을 증명하지 않는다.
- 중앙 Mimir 3.2.0·Loki 3.7.7과 두 Worker 이미지 digest를 기록했다. 중앙 보존 정책 필드가 출력되지 않았으므로 정책이 없거나 무제한이라고 해석하지 않는다. 원래 수집기의 단순 duration 정규식은 복합 duration을 누락할 수 있다. CPC Prometheus의 7d/10d나 CPC-1 Loki의 30d를 중앙 Mimir/Loki 보존으로 전용하지 않는다.
- CPC-2 오류는 monitoring/runai의 rulefiles-1/2 ConfigMap 네 건이다. 출력에는 실패 원인이 없어 미존재/RBAC/요청 실패 중 하나로 단정하지 않는다. 성공한 Pod 버전 관측과 분리하여 기록한다.

추가 수집은 Exporter에 지정된 CSV 파일의 읽기, Fleet의 명시적 수집 주기 환경변수, 중앙 ConfigMap의 선택된 보존·조회 기간 필드로 좁힌다. 읽기 도구가 없는 distroless 이미지에서는 실패를 기록하고 컨테이너 설치/변경을 시도하지 않는다. 이 결과 이후에도 Alloy/OTel 변환·전송 규칙의 의미 대조와 두 Worker 실환경 결과 검수는 남는다.

## 2026-10-07 수집 설정 후속 확인

PR #73은 main에 병합되었으며, 이번 후속 검토는 PR #74가 포함된 `c699573` 기준이다. `followup_details`에 CPC-1 첨부 원문 해시와 CPC-2/중앙 서버의 사용자 메시지에서 전사한 구조화 사실을 구분해 기록했다. 메시지 전사에 원문 파일 해시가 있는 것처럼 표시하지 않는다.

- **CPC-1:** Exporter 두 Pod의 CSV가 동일하다. SHA-256 `9728e45c9d733bd0d8807f9d82c005e07a180dbf10fba21df4ad451c9c8eb900`, 활성 정의 25개(gauge 19, counter 5, label 1). Exporter 후보 16개 중 14개가 있고 D26 `DCGM_FI_PROF_SM_ACTIVE`와 D27 `DCGM_FI_PROF_SM_OCCUPANCY`는 없다. CSV 존재는 장비 지원·표본 방출·중앙 전송의 증명이 아니다. PCIe RX/TX는 gauge 선언이며 이름의 BYTES만으로 누적 counter로 해석하지 않는다.
- **CPC-2:** root 재실행에서 메타데이터를 받았지만 Exporter 두 Pod의 CSV 읽기는 모두 실패했다. 원래 도구가 stderr를 감췄으므로 `cat` 부재나 RBAC로 확정하지 않는다. `errors: []`도 항목별 읽기 성공을 뜻하지 않았다.
- **Fleet:** 두 CPC 각각 두 Pod의 `FLEETINT_COLLECT_INTERVAL`과 `FLEETINT_CHECK_INTERVAL`은 모두 `1m`. 환경변수 설정값이며 실제 무누락 주기나 최대 유지시간 정책은 아니다.
- **Alloy:** 두 환경 설정 해시는 전날과 동일하다. 각각 15s scrape / 10s timeout 행이 있으나 전체 생산자 전송 규칙 검증은 아직이다.
- **중앙:** Mimir/Loki 설정 네 개를 읽었고 전날 해시와 같다. 추출된 보존 설정은 0개다. 설정 생략/다른 표현/기본값/tenant override를 구분할 실제 적용 설정 확인이 필요하며 무제한으로 판정하지 않는다.

### 후속 읽기 도구와 남은 검증

[binding_details.py](../../tools/ci/binding_details.py)는 이전 전달 도구의 전체 결과 유실과 오류 은폐를 보완한다. 특정 namespace의 Pod 읽기가 실패해도 다른 성공 결과를 보존하고, 단계·분류 코드만 출력한다. CSV 실패도 최상위 `errors`와 `collection_status=partial`에 포함한다. 원본 stderr·Secret·접속 URL은 출력하지 않으며 새 컨테이너 생성/설치/설정 변경은 없다. `kubectl exec`는 명시된 Exporter CSV의 `cat`만 시도한다. 설정명 발견 여부와 안전한 scalar 추출을 구분하지만 실제 적용된 보존 정책을 자동 판정하지 않는다.

서버에 해당 파일을 복사해 사용할 때는 파이프 실패를 보존한다. 필요한 환경에서만 실행하며 전체 목록을 반복 수집할 필요는 없다.

```bash
set -o pipefail
python3 ./binding_details.py --environment cpc-2 | tee binding-details-cpc-2-v2.json
python3 ./binding_details.py --environment advisor-central | tee binding-details-central-v2.json
```

이후 확인할 항목은 (1) CPC-2 CSV 또는 정확한 이미지·mount에 연결된 동등한 근거, (2) 중앙 Mimir/Loki의 실제 적용 보존/tenant 설정, (3) Alloy/OTel의 필터·신원·단위 변환, (4) D별 invalid/reset/max_hold 및 지원 소비자 계약이다. 해당 근거가 갖춰진 binding만 환경 revision에서 선택하고 두 Worker 실제 조회·계산·발행을 검수한다. 진단 도구는 운영 설정이나 배포 절차를 대신하지 않는다.

## 다음 확인 순서

1. 회신받은 Fleet·DCGM/Exporter·KSM의 이미지/digest와 ConfigMap 요약을 원장에 기록했다. 중앙 JSON의 LF 해시 일치도 확인했다. 실제 수집·전송 설정의 의미 검증은 남아 있다. PDF metrics 원본 두 묶음을 받아 수량·UUID별 비교를 재현했고 에너지 표기 오류 1건을 확인했다. 정정과 states의 시각 누락은 PDF 재검증 문서에 기록했다.
2. 해당 버전의 Fleet metric 생산 코드/OTel 변환, CPC-2 DCGM collectors CSV, KSM allowlist와 Alloy 전송 선별 규칙 확인. CPC-1 CSV 선언과 양쪽 Fleet 주기는 위 후속 기록에 추가했다. Secret/토큰은 수집하지 않는다.
3. 기본 D부터 타입·단위·신원·시각·invalid/reset·max_hold·보존 근거를 채우고, 검증을 충족하는 환경별 binding만 선택한 revision 작성. 실행 예제와 Helm 사본의 동기화 규칙을 지킨다.
4. 두 Worker와 O01의 실제 원본 재생/결과 검수 후, 남은 신규·조건부 분석과 개별 Runbook의 소비 계약을 구현한다. 배포와 DB 발행은 별도 단계다.
