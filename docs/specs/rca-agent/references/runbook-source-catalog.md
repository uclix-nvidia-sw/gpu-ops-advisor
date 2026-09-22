# GPU 노드 RCA 런북 근거자료 카탈로그

검토 기준일: 2026-09-22

용도: GPU 노드 RCA Agent용 런북을 작성할 때 사용할 출처 목록

상태: URL·문서 성격 검토 완료, 개별 절차의 대상 환경 재현 검증은 미완료

## 1. 이 자료의 사용 범위

이 문서는 첨부 ZIP의 `런북을 위한 자료 모음`을 검토해, 런북의 근거로 사용할 출처와 보조 참고자료를 구분한 것이다. 링크가 열리거나 검색된다는 사실은 해당 절차가 현재 장비에서 안전하고 유효하다는 뜻이 아니다.

각 출처에서는 다음 요소만 추출한다.

- 증상과 오류 코드의 의미
- 확인해야 할 증거와 식별자
- 진단 명령의 전제 조건과 예상 결과
- 권고 조치와 조치 전 확인사항
- 적용 제품·아키텍처·소프트웨어 버전

원문 전체를 복사하지 않고 URL, 문서 버전, 확인일, 발췌한 사실과 적용 조건을 기록한다. 명령 실행과 reset·reboot·power-cycle은 Agent 자동 실행 대상으로 만들지 않는다.

## 2. 1차 근거로 사용할 자료

| Domain·Category | 출처 | 검토 결과 | 런북에서 사용할 부분 |
|---|---|---|---|
| 공통 트리아지 | [NVIDIA GPU Debug Guidelines](https://docs.nvidia.com/deploy/gpu-debug-guidelines/index.html) | 공식 canonical 문서 확인 | 초기 증거 수집, GPU Node Triage, 벤더 전달 자료 체크리스트 |
| Xid | [NVIDIA Xid Errors](https://docs.nvidia.com/deploy/xid-errors/latest/index.html) | 공식 문서와 Xid catalog 진입점 확인 | Xid 의미·조사 방향. gpud action과 서로 다른 버전 근거로 보존 |
| GPU 진단 | [DCGM Diagnostics](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-diagnostics.html) | 공식 문서 확인 | 진단 level, plugin, 전제 조건, JSON 결과. 진단은 문제를 자동 수정하지 않는다는 범위 포함 |
| SXid·Fabric Manager | [NVIDIA Fabric Manager User Guide](https://docs.nvidia.com/datacenter/tesla/fabric-manager-user-guide/index.html) | 공식 문서 확인 | 설치된 FM 버전·플랫폼에 맞는 SXid 의미, fatality, fabric 상태와 로그 |
| NCCL·IB/RoCE | [NCCL Troubleshooting](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting.html) | 공식 현행 문서 확인 | GPU·network·runtime·logging·RAS별 관측 분기 |
| NCCL network | [NCCL Networking Troubleshooting](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting/networking_troubleshooting.html) | ZIP의 잘린 URL을 정상 URL로 교체 | interface, IB/RoCE, bandwidth·latency, RDMA counter 조사 절차 |
| NCCL 환경변수 | [NCCL Environment Variables](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html) | 공식 문서 확인 | 설치된 NCCL 버전 기준 변수 의미. 디버그용 변수를 영구 설정하지 않는 주의 포함 |
| InfiniBand | [ibdiagnet v2.19](https://networking-docs.nvidia.com/ibdiagnetutilityum/219) | 공식 문서 확인 | fabric discovery, error·counter, switch·HCA·cable 증거 수집 |
| Node CPU·Memory RAS | [Linux Kernel RAS](https://docs.kernel.org/admin-guide/RAS/main.html) | 공식 문서 확인 | EDAC·memory controller 증거. 실제 kernel·vendor에 맞는 decoder 필요 |
| GPU Operator | [GPU Operator Troubleshooting](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/troubleshooting.html) | ZIP에서 미검증으로 표시됐지만 canonical 문서 확인 | node의 driver·device injection·operator component 증거에 한정. Kubernetes 스케줄링 RCA로 확대하지 않음 |

`latest` URL은 탐색용이다. 실제 런북 revision을 발행할 때는 사용 제품의 문서 버전 또는 문서 revision을 함께 기록한다.

## 3. 조건부 또는 미래 장비용 자료

| 자료 | 판정 | 적용 조건 |
|---|---|---|
| [MNNVL Troubleshooting](https://docs.nvidia.com/multi-node-nvlink-systems/mnnvl-user-guide/troubleshooting.html) | 공식 자료지만 현재 장비 공통 런북으로 사용하지 않음 | MNNVL rack, switch tray, NMX-C·IMEX를 사용하는 장비에서만 활성화 |
| [NVOS Link Diagnostic Per Port](https://docs.nvidia.com/networking/display/NVIDIANVOSUserManualforInfiniBandSwitchesv25023000/Link%2BDiagnostic%2BPer%2BPort) | 공식 코드표 확인 | 해당 NVOS 버전의 switch를 사용하는 경우에만 code mapping 적용 |
| [nvbandwidth](https://github.com/NVIDIA/nvbandwidth) | NVIDIA 도구 확인 | 설치 버전·topology·예상 baseline이 확인된 뒤 사람이 실행하는 진단 단계로 사용 |
| [kubectl-nv](https://github.com/NVIDIA/kubectl-nv) | NVIDIA 참고 구현 확인 | 현재 Agent 범위와 겹치는 기능을 비교하는 설계 참고. 그대로 런북 action으로 넣지 않음 |

## 4. 보조 출처로만 사용할 자료

| 자료 | 사용 방법 | 제한 |
|---|---|---|
| [gpud SXid package](https://pkg.go.dev/github.com/leptonai/gpud/components/accelerator/nvidia/error/sxid) | 파싱 방식과 코드 카탈로그 구현 근거 | 반드시 commit 또는 tag를 고정하고 공식 FM 문서와 함께 사용 |
| [Modal GPU Health](https://modal.com/docs/guide/gpu-health) | 공식 표에 없는 코드의 조사 후보 | 제3자 해석을 fatality나 repair action의 단독 근거로 사용하지 않음 |
| [Google Cloud NCCL/gIB 로그 가이드](https://docs.cloud.google.com/ai-hypercomputer/docs/nccl/collect-and-understand) | NCCL 로그 수집 형식과 예시 | Google gIB·GKE 전용 설정을 온프레미스 공통 절차로 복사하지 않음 |
| [Lambda nvidia-bug-report 가이드](https://docs.lambda.ai/education/linux-usage/using-the-nvidia-bug-report.log-file-to-troubleshoot-your-system/) | bug report 해석 보조 | 벤더별 환경 차이를 확인하고 NVIDIA 공식 지침보다 우선하지 않음 |
| [USE Method](https://www.brendangregg.com/usemethod.html) | CPU·memory·disk·network 가설을 utilization·saturation·errors로 분해 | GPU 오류 코드나 조치의 직접 근거가 아님 |
| [Percona NVMe health 글](https://www.percona.com/blog/using-nvme-command-line-tools-to-check-nvme-flash-health/) | NVMe 관측 항목을 찾는 보조 자료 | 장비 제조사와 nvme-cli·smartmontools 공식 문서로 명령·threshold 재검증 |

Fleet와 GPUd의 component, XID·SXID 정적 정의와 기본 action을 찾을 때는 저장소 안의 [Fleet·GPUd component·오류 카탈로그](fleet-gpud-error-catalog.md)를 사용한다. 이 카탈로그의 action은 분석 commit의 정적 기본값이며 현재 상태 평가 결과나 즉시 실행 지시가 아니다.

## 5. 런북 한 건으로 변환할 때 필요한 정보

다음 구조는 작성용 worksheet 예시다. 그대로 API payload로 적재하지 않는다. 새 DB 테이블을 요구하지 않으며, 검토가 끝난 값만 현재 프로젝트의 versioned runbook content와 `source_refs` 계약에 맞춰 옮긴다. 현재 UI·API의 `source_refs`는 문자열 배열로 다루므로 고정된 URL 또는 revision 식별자를 문자열로 저장하고, 상세한 적용 버전·조회일·원문 위치는 검토 기록에 함께 남긴다.

```yaml
title: 사람이 이해할 수 있는 증상 이름
scope:
  gpu_architecture: []
  product: []
  driver_version: ""
  dcgm_version: ""
  fabric_manager_version: ""
trigger:
  facts: []
  log_patterns: []
observations:
  - query_id: 승인된 조회 ID
    lookback: 15m
    target_binding: uuid 또는 PCI BDF
    expected_evidence: 관측 사실
decision:
  conditions: []
  insufficient_evidence: unknown
recommendation:
  action: 사람이 검토할 권고
  prerequisites: []
  remediation_performed: false
source_refs:
  - 버전 또는 revision을 확인할 수 있는 URL이나 pinned source 식별자
source_review:
  checked_at: 2026-09-22
  applies_to: 적용 제품과 버전
  location: 근거가 있는 section 또는 code 위치
```

## 6. 우선 작성할 런북 순서

1. `GPU_ACCESS_LOST` / Xid 79: Fleet·gpud catalog, Loki 원문, PCI BDF, 장치 마지막 관측을 묶기 쉽다.
2. `ECC_DBE`: counter 증가, Xid, UUID binding과 human action 경계를 명확히 검증할 수 있다.
3. `SXID_ERROR` / `FABRIC_MANAGER_ERROR`: NVSwitch capability가 확인된 노드만 대상으로 작성한다.
4. `NCCL_NETWORK_ERROR`: 설치 NCCL·IB/RoCE 환경을 확인한 뒤 공식 networking troubleshooting의 관측 절차를 연결한다.
5. Node CPU·memory·disk: 사내 장비 vendor와 실제 수집 metric이 확인된 뒤 확장한다.
