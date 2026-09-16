# DSX CPC-1·CPC-2 공통 수집 환경과 두 Agent 업무

> **후속 조건 반영:** 사용자가 Pod↔GPU UUID 매핑 활용 가능을 확인했다. 본문의 중앙 매핑 미완료에 따른 업무 제한은 최신 [운영보고서 Agent v1.1](<DSX_GPU_운영보고서_Agent_역할과_데이터설계_v1.1.md>)과 [RCA Agent v1.0](<DSX_GPU_RCA_Agent_역할과_데이터설계_v1.0.md>)의 기능 범위로 대체한다. 본문은 이전 수집 근거 기록으로 보존하며, 과거 이력·UID·활동률·전력의 검증은 별도 조건으로 유지한다.

| 항목 | 내용 |
|---|---|
| 기준일 | 2026-09-15 |
| 근거 | 사용자 최신 완료·미완료 설명, DCGM Exporter 설정·Prometheus 조회 원문, Fleet 실제 메트릭 라벨 목록 |
| 범위 | CPC-1·CPC-2. 두 CPC는 동일한 수집·연동 환경을 사용하며 CSC에서 양쪽 데이터를 조회할 환경이 구축됐다는 사용자 확인을 기준으로 함 |
| 수행 | 첨부 자료 분석과 문서 수정만 수행. 추가 설정·실환경 조회·배포 없음 |
| 문서 지위 | 두 CPC의 공통 수집 환경을 기준으로 업무를 정의함. 첨부 표본의 출처와 개별 데이터 검증 범위는 별도로 보존 |

## 1. 결론

**CPC-1·CPC-2의 데이터는 CSC에서 조회할 환경이 구축된 것으로 본다. 두 Agent는 공통 조회 경로에서 클러스터와 노드를 구분해 양쪽 데이터를 분석하도록 설계한다. GPU↔Pod 연결은 원본 검증 근거가 있으나 중앙 분석 경로는 미완료인 상태다.**

이 문서의 ‘동일 환경’은 수집·연동 구성과 CSC 조회 환경에 대한 전제다. GPU 모델·기능 지원까지 동일하다는 뜻은 아니므로 장비별 적용 조건은 유지한다. 원문에 있는 CPC-2의 라벨·조회값은 실제 표본으로 보존하며 CPC-1에서 동일한 값을 실측했다고 바꾸지 않는다.

그렇지만 이번 첨부로 저활동 분석, GPU 요청량 기반 통계, GPU 전력 분석이 모두 검증된 것은 아니다. 특히 다음 구분이 중요하다.

- Fleet 메트릭 라벨 목록은 이름·식별 라벨을 보여준다. 실제 숫자·단위·신선도·장기 이력을 보여주지는 않는다.
- `kube_pod_container_resource_requests`가 수집된다는 것과 그 안에 GPU 요청 시계열이 존재한다는 것은 다르다.
- DCGM Exporter의 GPU↔Pod 원본 매핑 성공과 그 메트릭의 Prometheus·Mimir 수신 성공은 다르다.
- GPU 활동률과 소비전력은 이번 Fleet 목록에 보이지 않는다. 목록에 없다는 이유로 실제 미수집을 확정하지도 않는다.

따라서 두 CPC에 대한 Agent 지원은 **노드·GPU 식별, VRAM 관련 관측, Node 상태·Pod 배치, Fleet 상태 로그를 중심으로 설계**한다. 실제 정량 분석은 필요한 값·기간을 확인한 범위로 제한한다.

## 2. 근거의 출처와 강도

| ID | 근거 | 직접 확인한 내용 | 범위·한계 |
|---|---|---|---|
| N00 | 사용자 후속 확인 | CPC-1도 동일 환경이며 CPC-1·CPC-2 데이터를 CSC에서 확인할 환경이 구축됐다고 보고 문서를 수정하도록 요청 | 두 CPC의 공통 환경 기준. 개별 값·기간 및 중앙 장치 매핑의 미완료 사항까지 완료로 바꾸는 것은 아님 |
| N01 | 사용자 최신 설명 | CPC-2 Fleet→Alloy→CSC Mimir/Loki 전송·조회 완료, 정상 상태 로그 수신, KSM 세 종류 중앙 수집, 테스트 Pod UUID 일치 검증 | 사용자가 전달한 최신 검증 결과로 수용. 첨부 두 파일에 모든 검증 원문이 포함된 것은 아님 |
| N02 | `dcgm exporter 설치 설정 prometheus 조회 결과.txt` | 두 워커의 Exporter Running, 이미지·환경 변수·마운트, Prometheus 조회 결과 | 원문 명령을 이번에 재실행하지 않음. 조회 시점과 테스트 Pod 생성·매핑 검증의 선후 관계는 미확인 |
| N03 | `fleet 실제 메트릭 라벨 목록.txt` | 라벨 표본 20행, 고유 메트릭 이름 18개. worker-01의 공통 라벨과 GPU UUID | 전체 메트릭 목록이라고 확정하지 않음. 숫자·HELP/TYPE·샘플 시각은 없음. worker-02의 동일 필드 표본은 이 파일에 없음 |

9월 초의 노드 라벨 부재와 구 OTLP logs 전송 실패를 현재 수집 환경의 기준으로 사용하지 않는다. 사용자 후속 확인(N00)에 따라 CPC-1·CPC-2의 CSC 조회 환경 구축을 공통 전제로 삼으며, 첨부 표본의 출처는 N01~N03으로 구분한다.

## 3. 확인된 수집 경로와 중앙 식별

| 데이터 | 현재 경로·상태 | 중앙 조회 시 구분 |
|---|---|---|
| 두 CPC의 Fleet 메트릭 | Fleet→Alloy→CSC Mimir 조회 환경 구축(N00). CPC-2 상세 검증 기록 N01 | 공통 Mimir tenant `cpc-1`, 대상 CPC의 `cluster_id`와 node로 구분 |
| 두 CPC의 Fleet 로그 | Fleet→Alloy→CSC Loki 조회 환경 구축(N00). CPC-2 정상 로그 확인 N01 | 각 CPC에 설정된 tenant·라벨 매핑 사용. CPC-2 표본은 tenant `cpc2`, `cluster="cpc2"` |
| 두 CPC의 KSM | KSM→Prometheus→Alloy→CSC Mimir 공통 환경. 확인된 세 종류를 기본 범위로 사용(N00·N01) | 공통 tenant 안에서 대상 CPC·Node·Pod를 구분 |
| DCGM Exporter 매핑 | Exporter 원본에서 테스트 Pod 연결·UUID 일치 확인(N01) | Prometheus scrape·Mimir 전달·중앙 join은 미완료 |

Mimir tenant 이름 `cpc-1`은 CPC-1 클러스터만의 데이터라는 뜻이 아니다. 현재는 공통 tenant 안에서 `cluster_id`로 클러스터를 구분한다. Loki의 tenant·라벨을 Mimir와 같다고 가정하면 안 된다.

공통 조회 도구는 내부 대상 CPC를 저장소별 tenant·라벨로 해석한다. 다음은 전달받은 **CPC-2 표본**이다. CPC-1에도 같은 조회 계약을 적용하되 대상별 설정값을 사용한다.

```text
내부 대상: CPC-2
  Mimir → tenant cpc-1 + cluster_id=cpc-2 + node
  Loki  → tenant cpc2  + cluster=cpc2    + 확인된 노드 필드
```

이는 논리 조회 계약이다. 현재 설정을 변경하라는 지시가 아니다. Loki 노드 필드의 실제 저장 위치·형식은 표본에 맞춰 사용하며, 모든 로그가 동일한 라벨 구조라는 가정은 하지 않는다.

## 4. Fleet 메트릭의 실제 매핑

N03의 표본은 `vessl-k8s-worker-01`에 해당한다. 다음 공통 라벨을 확인했다.

```text
cluster_id = cpc-2
node = vessl-k8s-worker-01
node_group = prod-b
compute_zone = us-east-1c
host_name, machine_id, job

GPU 메트릭 추가 라벨:
uuid, gpu, device, gpu_serial, model_name, pci_bus_id
```

따라서 해당 표본의 **GPU↔Node 연결은 명시적인 라벨로 확보**됐다. 과거처럼 GPU 모델 이름으로 노드를 추측할 필요가 없다. `node_group=prod-b`는 확인된 그룹 라벨이지만 프로젝트 소유·전용성을 증명하지는 않는다.

| 데이터 | 실제 이름 | 지금 확인한 수준 | 가능한 활용과 남은 조건 |
|---|---|---|---|
| CPU 부하 | `cpu_load_average` | 1m/5m/15m 라벨 표본 | 노드 부하 관측. 코어 수 없이 포화율로 표현하지 않음 |
| CPU 사용 | `cpu_used_percent` | 이름·노드 라벨 확인 | GPU·상태 사건과 동반 변화 비교. 숫자·단위·기간 필요 |
| VRAM | `dcgm_fi_dev_fb_free`, `dcgm_fi_dev_fb_total`, `dcgm_fi_dev_fb_used`, `dcgm_fi_dev_fb_used_percent` | 이름·GPU UUID·노드 라벨 확인 | 장치별 점유 현황·추세 입력. 값 유효성·단위 확인 후 계산 |
| ECC | `dcgm_fi_dev_ecc_dbe_agg_dev`, `dcgm_fi_dev_ecc_dbe_agg_total`, `dcgm_fi_dev_ecc_dbe_vol_dev`, `dcgm_fi_dev_ecc_dbe_vol_total`, `dcgm_fi_dev_ecc_sbe_agg_dev`, `dcgm_fi_dev_ecc_sbe_agg_total`, `dcgm_fi_dev_ecc_sbe_vol_dev`, `dcgm_fi_dev_ecc_sbe_vol_total` | 8종 이름·식별 라벨 확인 | 오류 관측의 근거 후보. 값·누적/휘발 의미·리셋 처리·중복 집계 여부 확인 |
| 클럭 제한 사유 | `dcgm_fi_dev_clocks_event_reasons` | 이름·식별 라벨 확인 | 원인 코드의 의미와 유효 값을 확인한 뒤 설명 |
| 보드 제한 위반 | `dcgm_fi_dev_board_limit_violation` | 이름·식별 라벨 확인 | 시간/비율 등 실제 정의를 확인하고 사용. 메트릭 존재만으로 위반 발생을 단정하지 않음 |
| 전력 제한 | `dcgm_fi_dev_enforced_power_limit` | 이름·식별 라벨 확인 | 설정된 제한 관련 관측. 소비전력이나 에너지 적산 입력으로 대체하지 않음 |
| Fabric Manager 상태 | `dcgm_fi_dev_fabric_manager_status` | V100 표본에도 이름 존재 | 기능 적용 여부·미지원 값 확인 전 장애 지표로 사용하지 않음 |

이번 목록에서 **GPU utilization, SM 활동, 온도, 실제 소비전력 이름·값은 확인되지 않았다.** 이는 해당 필드가 실제로 없다는 결론이 아니라 첨부 목록의 증거 범위다.

특히 VRAM 점유만으로 “GPU가 놀고 있다”라고 판정할 수 없다. 메모리 점유와 연산 활동을 결합한 분석에는 활동률의 실제 필드가 추가로 필요하다.

## 5. KSM 세 종류와 Prometheus 결과의 의미

중앙 수집이 확인됐다는 최신 설명은 다음 세 종류에 한정한다.

| 메트릭 | 설계에 반영할 활용 | 확대하면 안 되는 해석 |
|---|---|---|
| `kube_node_status_condition` | 실제 condition/status 라벨에 따른 Node 상태 연결 | allocatable·taint·스케줄링 금지·상세 배치 실패 사유까지 확보됐다는 뜻은 아님 |
| `kube_pod_info` | Pod·Namespace·Node 등의 실제 제공 필드를 통한 배치 관계 | 모든 상위 Workload owner·재시작·Pending 이력이 확보됐다는 뜻은 아님 |
| `kube_pod_container_resource_requests` | 실제 관측되는 resource별 요청량 | GPU 요청이 존재한다는 뜻은 아님 |

N02에는 다음 조회 결과가 있다.

```text
count by (resource) (kube_pod_container_resource_requests)
  cpu                → 100
  memory             → 99
  ephemeral_storage  → 2

kube_pod_container_resource_requests{resource=~"nvidia_com_.*"} > 0
  → success, totalSeries=0

DCGM_FI_DEV_GPU_UTIL
  → success, totalSeries=0
```

첫 번째의 100·99·2는 **시계열 개수**다. CPU 코어 수·메모리 용량·요청 자원량이 아니다.

두 번째는 그 조회 시점에 조건에 맞는 GPU 요청 시계열이 관측되지 않았다는 뜻이다. 테스트 Pod 생성 전이었는지, 짧게 실행됐는지, 요청 노출 문제가 있었는지 등은 이 자료만으로 구분할 수 없다. 요청 메트릭 수집 성공과 GPU 요청 관측 미확인은 동시에 성립한다.

세 번째는 해당 Prometheus에서 **대문자 이름의 DCGM Exporter 메트릭**을 조회한 결과다. 이것만으로 소문자 계열 Fleet 메트릭의 Mimir 수집 실패를 의미하지 않는다. 두 생산자·두 경로를 구분한다.

따라서 현재는 **Node 상태·Pod 배치 관계는 활용 근거가 확보됐고, GPU 요청량·요청 GPU·시간 통계는 여전히 보류**한다. KSM 세 종류만으로 앞 문서의 모든 Kubernetes 분석 주제를 활성화하지 않는다.

## 6. GPU↔Pod 매핑의 현재 상태

### 확인된 사실

- 두 워커에 DCGM Exporter Pod가 Running인 설정 출력이 있다.
- 이미지: `nvcr.io/nvidia/k8s/dcgm-exporter:4.4.2-4.7.0-distroless`.
- `DCGM_EXPORTER_KUBERNETES=true`.
- `/var/lib/kubelet/pod-resources`를 읽기 전용으로 마운트한다.
- `DCGM_REMOTE_HOSTENGINE_INFO=nvidia-dcgm:5555`가 설정돼 있다.
- 최신 설명에 따르면 테스트 Pod UUID, Exporter의 작업 Pod 매핑 UUID, Fleet UUID가 일치했다.

설정 존재뿐 아니라 테스트 매핑까지 확인됐으므로, 이전의 “GPU↔Pod 연결 근거 없음”은 수정한다. 다만 이 검증을 모든 노드·GPU·시간대·공유 방식으로 일반화하지 않는다.

### 남은 경계

```text
테스트 Pod ↔ GPU UUID         확인
Exporter 원본 매핑 ↔ Fleet UUID 확인
Exporter → Prometheus         미완료
Prometheus → Mimir             미완료
중앙 Fleet ↔ 장치 매핑 join     미완료
pod_uid                       원본에서 빈 값
과거 사건 시점의 연결 이력      미검증
```

`pod_uid`가 비어 있어도 동일 시점에 `(cluster, namespace, pod, node)`의 유일한 Pod를 KSM에서 찾아 UID를 보완하는 설계는 검토할 수 있다. 그러나 Pod 이름 재사용·재생성, 관측 지연, 짧은 Pod, 중복 행을 검사해야 한다. 현재 KSM UID 필드의 실제 표본도 이 첨부에 없으므로 보완 완료로 처리하지 않는다.

중앙에 매핑을 적재한 뒤에는 Fleet의 `uuid`와 Exporter의 실제 UUID 라벨명·노드 키를 정규화하고, 동일 시점의 유일한 연결인지 확인해야 한다. mapping 행 때문에 GPU 지표가 복제·이중 집계되지 않도록 한다. 구체적인 PromQL은 중앙 스키마가 결정되기 전 확정하지 않는다.

결론은 **“매핑 불가능”이 아니라 “원천 매핑 검증 완료, 중앙 활용 미완료”**다. Agent가 현재 중앙에서 오류 GPU의 Pod를 특정하는 기능은 아직 활성화하지 않는다.

## 7. RCA Agent의 업무 재판정

아래의 ‘데이터 기반 확보’는 해당 Agent 구현이 끝났다는 뜻이 아니다. 현재 설계에서 쓸 수 있는 입력 근거가 생겼다는 뜻이다.

| 업무 | 재판정 | 제공할 결과와 한계 |
|---|---|---|
| CPC-1·CPC-2 노드·GPU를 식별한 조사 | 공통 조회 환경 확보 | cluster_id·node·uuid로 대상 선택. 장비별 지원 필드와 유효 값은 구분 |
| Fleet 상태 로그 조회·설명 | 경로·정상 로그 수신 확인 | 정상 상태도 확인할 수 있음. Healthy 로그가 남는다고 연속 수집·복구 완료가 보장되지는 않음 |
| Node 상태와 사건의 동시점 비교 | KSM 입력 종류 확보 | actual condition/status·시각을 확인한 범위에서 연결 |
| VRAM·CPU·ECC·클럭 관련 증거 수집 | 필드·식별 기반 확보 | 실제 숫자·의미·해당 기간을 확보한 만큼 조사에 사용 |
| 당시 같은 노드의 Pod 후보 제시 | 현재 배치 입력 기반 확보, 과거 이력 조건부 | kube_pod_info의 보존 기간·필드를 확인해야 과거 목록 산출. GPU 요청 Pod로 한정하려면 GPU 요청 증거 필요 |
| 알려진 Xid/SXid Runbook 적용 | 사건 표본·계약 조건부 | 로그 경로 완료와 별개로 해당 코드·시간·장비·권고 필드 검증 필요. 현재 V100에 SXid 지원을 일괄 적용하지 않음 |
| 오류 GPU의 실제 Pod 연결 | 중앙 기능 보류 | 원본 테스트 성공은 반영. 중앙 매핑·UID·시간 이력이 완성되면 지원 확대 |
| 원인 불명·반복·회복 조사 | 증거·기간별 조건부 | 확보된 지표·로그로 후보를 좁힘. Incident·조치 이력은 서비스에 실제 축적된 범위만 사용 |

현 단계 RCA의 구체적인 목표 결과는 “이 노드의 이 GPU에 관측된 상태와 관련 수치, 같은 시간대 노드 상태·Pod 배치, 다음 점검”이다. 특정 Pod의 원인 책임·업무 피해까지 확정하지 않는다.

## 8. 운영보고서 Agent의 업무 재판정

| 업무·기존 주제 | 최신 판정 | 이유 |
|---|---|---|
| GPU별 VRAM 점유 현황·추세 | 입력 필드 기반 확보, 값·기간 조건부 | fb_used/free/total/used_percent와 uuid·node 존재 |
| CPC-1·CPC-2 노드 상태·Pod 배치 현황 | 공통 중앙 수집 환경 확보 | 확인된 KSM 두 종류 활용. 실제 제공 라벨 범위에 한정 |
| CPU 부하·사용과 GPU 관측 비교 | 입력 필드 기반 확보, 값·기간 조건부 | load_average·cpu_used_percent에 node 존재 |
| T01 저활동, T07 연산 활동 편차 | 아직 확정 보류 | 이번 목록에 GPU 활동률 표본이 없음. VRAM만으로 대체 불가 |
| T02 GPU 요청과 활동 차이 | 보류 | GPU 요청 시계열 0건 표본 + 활동률 표본 부족 |
| T06 GPU 요청량 기준 GPU·시간 | 보류 | CPU·메모리 요청 수집을 GPU 요청 수집으로 확대할 수 없음 |
| T03 정밀 배치 제약 | 부분 범위만 가능 | Node 상태는 있음. allocatable·taint·스케줄링 금지·실패 사유는 확인 범위 밖 |
| T08 높은 활동과 GPU 배치 대기 | 보류 | 활동률·GPU 요청·미배치 상태의 필요한 증거가 부족 |
| T09 GPU 에너지 분석 | 보류 | power_limit만 확인. 실제 power_usage 또는 에너지 필드와 기간 필요 |
| T04 기간 비교 | 실제 확보된 필드·기간만 조건부 | 현재 연결 완료를 주간·월간 이력 확보로 확대하지 않음 |
| T05 반복 사건·정비 우선순위 | 로그·사건 이력 조건부 | 정상 로그 수신과 정규화 Incident 축적은 별도 |
| T10 관측 품질 | 필수 업무로 설계 | 기대 대상·수집 주기·원본 샘플 시각·기간을 기준으로 평가 |
| 프로젝트별 실제 활동·전력 귀속 | 보류 | 중앙 GPU↔Pod와 프로젝트 매핑 미완료. 전용성도 미확인 |

따라서 공통 환경에서 운영보고서가 제공할 첫 결과는 **CPC-1·CPC-2의 노드 상태·Pod 배치·VRAM 점유·CPU 상황을 연결한 현황과 변화 설명**이다. 서로 다른 GPU 모델은 구분해 집계한다. GPU 저활동·자원 규모 검토는 활동률·GPU 요청·기간 증거가 추가 확인돼야 한다.

## 9. 기존 판단의 수정 내역과 미완료 범위

| 기존 표현 | 수정 표현 |
|---|---|
| 노드 라벨이 없어 join 가능 여부 미확인 | CPC-2 표본에서 node·cluster_id·uuid 확인. 사용자 확인에 따라 두 CPC 모두 공통 수집·식별 환경으로 설계 |
| KSM 중앙 수집 미확인 | 지정된 세 종류의 중앙 수집 확인. 나머지 KSM 항목은 미확인 유지 |
| Loki 로그 도달 미확인 | 두 CPC의 CSC 조회 환경 구축을 전제로 반영. CPC-2 정상 로그 검증 기록은 보존하며 개별 오류 스키마·장기 보존은 별도 |
| GPU↔Pod 매핑 근거 없음 | 테스트에서 원본 연결·UUID 일치 확인. 중앙 적재·join·UID 보완은 미완료 |
| 요청량 기반 GPU·시간은 조건부 가능 | 계산 방식은 유지하되, 이번 환경의 GPU 요청 관측 근거가 아직 없어 현재 기능은 보류 |
| 전력 메트릭 계열이 있으므로 전력 분석 후보 | 이번 표본의 전력 제한과 실제 소비전력을 분리. 에너지 분석 근거는 아직 부족 |

중지된 추가 작업을 재개하거나 설정을 변경하지 않았다. 미완료 목록은 향후 설계·검증의 입력으로 남긴다.

- DCGM Exporter 메트릭의 Prometheus 수집·Mimir 전송·중앙 join.
- 빈 pod_uid 보완과 Pod 재생성·과거 연결 처리.
- GPU 요청 시계열이 실제 생성되는 상황의 관측과 현재 0건 결과의 시점 해석.
- GPU 활동률·실제 소비전력의 Fleet 중앙 필드·단위·값·기간 확인.
- KSM 실제 라벨·owner 연결·필요한 추가 종류의 범위 확인.
- CPC-1 수집·정규화를 이유로 전체 업무 범위를 CPC-2에 제한하지 않는다. 두 CPC의 CSC 조회 환경 구축이 최신 기준이다.
- Loki 보관기간 변경과 실제 장기 이력 검증은 별도 사항으로 유지한다.

## 10. 자료 전달 시 함께 유지할 결론

**CPC-1·CPC-2 데이터를 CSC에서 조회할 공통 환경은 구축됐다. 두 Agent는 이 환경을 사용하며, 개별 업무의 활성화 범위는 메트릭 의미·유효 값·장치 매핑·기간 이력에 따라 정한다. 장치 매핑 원본 검증은 반영하되 중앙 join과 UID 보완은 미완료로 유지한다.**

이번 문서의 메트릭 이름·쿼리 결과는 첨부 원문에서 가져왔다. 정상 로그·세 종류 KSM의 중앙 도착·테스트 UUID 일치는 사용자가 전달한 최신 검증 설명을 근거로 명시했다. 원문에 없는 수치·실환경 검증 완료는 추가하지 않았다.
