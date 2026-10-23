# GPU 노드 RCA 런북 근거자료 카탈로그

검토 기준일: 2026-10-22 (최초 2026-09-22)

용도: GPU 노드 RCA Agent용 런북을 작성할 때 사용할 출처 목록

상태: URL·문서 성격·문서 개정일 검토 완료, 개별 절차의 대상 환경 재현 검증은 미완료

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
| 대응 순서 | [GPU Node Triage](https://docs.nvidia.com/deploy/gpu-debug-guidelines/gpu-node-triage.html) | Last updated on Oct 04, 2026. 흐름도 3개, 표 1(XID 13·31·45·48·61·62·63·64·74·79·92·94·95·123), 표 2(리셋 가능 범위)를 원문 HTML로 대조 | 분류(애플리케이션·ECC 메모리·HW/시스템·기타) → 표 1 조치 → 해결 여부 → DCGM 진단 → 공급사 보고 순서, 공급사 전달 자료 9항목 |
| Xid | [NVIDIA Xid Errors](https://docs.nvidia.com/deploy/xid-errors/latest/index.html) | 공식 문서와 Xid catalog 진입점 확인 | Xid 의미·조사 방향. gpud action과 서로 다른 버전 근거로 보존 |
| Xid 카탈로그 | [Analyzing Xid Catalog](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html) | Last updated on Sep 09, 2026. 표 1(코드별 적용 제품·즉시/조사 조치·Xid 154 연계)과 표 3(Resolution Bucket) | 코드별 조치 분류. Xid 154 복구 수준(None·Drain P2P·Drain and Reset·GPU Reset Required·Node Reboot Required) |
| 자료 수집 | [Working with Xid Errors](https://docs.nvidia.com/deploy/xid-errors/working-with-xid-errors.html) | Last updated on Sep 09, 2026 | `nvidia-bug-report.sh`(root, 최대 1시간, 멈추면 `--safe-mode --extra-system-data`) |
| GPU 메모리 | [GPU Memory Error Management](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/index.html) | Last updated on Sep 09, 2026 | row remapping 적용(GPU 리셋 후), Pending·Failure 플래그, DRAM·SRAM RMA 기준 |
| nvidia-smi | [nvidia-smi](https://docs.nvidia.com/deploy/nvidia-smi/index.html) | 날짜 없음, 변경 기록 v610까지 | `-r` 전제와 리셋 후 확인, GPU Recovery Action 값, R580의 Fabric State·Status 폐기, `nvlink -s/-e`, PCI·온도·Clocks Event Reasons 항목 |
| GPU 진단 | [DCGM Diagnostics](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-diagnostics.html) | 공식 문서 확인 | 진단 level, plugin, 전제 조건, JSON 결과. 진단은 문제를 자동 수정하지 않는다는 범위 포함 |
| DCGM 건강 점검 | [DCGM Feature Overview](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html) | Last updated 2026-06-17 | 백그라운드 건강 점검의 PASS·WARN·FAIL 의미와 `dcgmi health -c` |
| DCGM 오류 코드 | [dcgm_errors.h](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_errors.h) | NVIDIA 공식 소스, commit 고정(DCGM v4.6.x) | `DCGM_FR_*` 코드별 메시지와 다음 단계(`_NEXT`). Fleet DCGM 컴포넌트 보고의 `dcgm_incidents.code` 해석 |
| SXid·Fabric Manager | [NVIDIA Fabric Manager User Guide](https://docs.nvidia.com/datacenter/tesla/fabric-manager-user-guide/index.html) | Document History v2.6(Sep 21, 2026) | SXid 표 22~25 분류, Bare Metal Mode의 비치명·치명(access/trunk) 복구 절차, 로그 위치와 수준 |
| DGX 관리 | [NVSM CLI](https://docs.nvidia.com/datacenter/nvsm/nvsm-user-guide/latest/using-nvsm-cli.html) | NVSM User Guide 25.03 | `nvsm show health`, `nvsm show storage`, 지원 티켓용 `nvsm dump health` |
| Fleet 알림 정의 | [Fleet Intelligence SDK components](https://github.com/dsx-ai-factory/fleet-intelligence-agent/tree/84f99beef3e633071ad0998b10629b01fb294eaf/third_party/fleet-intelligence-sdk/components) | commit 고정 소스 | 컴포넌트별 Unhealthy 사유 문자열·임계값·재부팅 이력 권고 규칙. 알림을 무엇이 냈는지의 근거이며 조치의 근거가 아님 |
| NCCL·IB/RoCE | [NCCL Troubleshooting](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting.html) | 공식 현행 문서 확인 | GPU·network·runtime·logging·RAS별 관측 분기 |
| NCCL network | [NCCL Networking Troubleshooting](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting/networking_troubleshooting.html) | ZIP의 잘린 URL을 정상 URL로 교체 | interface, IB/RoCE, bandwidth·latency, RDMA counter 조사 절차 |
| NCCL 환경변수 | [NCCL Environment Variables](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html) | 공식 문서 확인 | 설치된 NCCL 버전 기준 변수 의미. 디버그용 변수를 영구 설정하지 않는 주의 포함 |
| InfiniBand | [ibdiagnet v2.19](https://networking-docs.nvidia.com/ibdiagnetutilityum/219) | 공식 문서 확인 | fabric discovery, error·counter, switch·HCA·cable 증거 수집 |
| InfiniBand 링크 | [mlxlink](https://networking-docs.nvidia.com/mftswum/4.36.0/mlxlink-utility) | MFT 4.36.0 문서 | 링크 폭·속도·오류 상태, 물리 카운터·BER, 트랜시버 정보 |
| Node CPU·Memory RAS | [Linux Kernel RAS](https://docs.kernel.org/admin-guide/RAS/main.html) | 공식 문서 확인 | EDAC·memory controller 증거. 실제 kernel·vendor에 맞는 decoder 필요 |
| Node 디스크·OS·네트워크 | Linux 커널 문서 [ext4](https://docs.kernel.org/admin-guide/ext4.html)·[md](https://docs.kernel.org/admin-guide/md.html)·[sysctl fs](https://docs.kernel.org/admin-guide/sysctl/fs.html)·[sysctl kernel](https://docs.kernel.org/admin-guide/sysctl/kernel.html)·[operstates](https://docs.kernel.org/networking/operstates.html) | 커널 문서 7.3.0 | 읽기 전용 재마운트(`errors=remount-ro`), RAID 구성 장치 상태, `file-nr`·`pid_max`, 인터페이스 운영 상태 |
| GPU Operator | [GPU Operator Troubleshooting](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/troubleshooting.html) | ZIP에서 미검증으로 표시됐지만 canonical 문서 확인 | node의 driver·device injection·operator component 증거에 한정. Kubernetes 스케줄링 RCA로 확대하지 않음 |

`latest` URL은 탐색용이다. 실제 런북 revision을 발행할 때는 사용 제품의 문서 버전 또는 문서 revision을 함께 기록한다.

### 2.1 출처가 서로 다를 때의 적용 순서

1. 제품별 행이 일반 분류보다 앞선다. Xid 카탈로그는 XID 64·95의 즉시 조치를 RESET_GPU로 분류하지만 GPU Node Triage의 A100 행은 기록 실패(64)와 MIG 비활성 상태의 격리되지 않은 오류(95)에 노드 즉시 재부팅을 안내한다. A100 장비에는 Triage 행을 쓰고 카탈로그 분류를 함께 표시한다.
2. 최신 개정을 확인하되 차이는 지우지 않는다. 카탈로그(Sep 09, 2026)는 XID 61·123을 Unused로 두지만 Triage(Oct 04, 2026) 표 1은 공급사 보고와 GPU 리셋을 안내한다. 운영자 단계는 Triage를 따르고, 카탈로그의 Unused 표시는 원문·드라이버 버전을 확인할 근거로 남긴다.
3. Fabric Manager 가이드 표 22의 Guest VM 열은 공유 NVSwitch 가상화의 영향·복구다. bare metal은 같은 가이드의 Bare Metal Mode 절차를 먼저 적는다.
4. 문서가 폐기를 밝힌 필드는 확인 명령으로 쓰지 않는다. R580 nvidia-smi에서 `-q`의 Fabric State·Status는 폐기됐으므로 Hopper 이후 Fabric Health 항목과 Fabric Manager 서비스·로그를 쓴다.
5. 숫자 코드는 정의 출처와 함께 읽는다. DCGM Fabric Manager 상태(D47)의 0은 미지원이며 정상이나 실패가 아니다(`dcgm_structs.h`). DCGM 클록 제한 사유(D45)는 비트마스크다.

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

다음 구조는 작성용 worksheet 예시다. 그대로 API payload로 적재하지 않는다. 새 DB 테이블을 요구하지 않으며, 검토가 끝난 값만 현재 프로젝트의 versioned runbook content와 `source_refs` 계약에 맞춰 옮긴다. 현재 Backend의 최상위 `source_refs`는 DB evidence ID를 검증하므로 URL이나 문헌 revision 문자열을 넣지 않는다. 특히 common Knowledge는 사건 evidence를 연결하지 않는다. 문헌 URL·버전·확인일·원문 위치는 `content.sources`에 기록한다. 구현 예시는 [Runbook 개발 및 RCA 연계](../../../../rcca-agent/runbooks/README.md)를 따른다. 오류별 초안 3건의 DB 필드 대응·검토/발행·다른 PC의 재현 절차와 추가 GPUd 대조 commit은 [DB 등록 안내](../../../../rcca-agent/runbooks/DB-WORKFLOW.md)에 기록했다.

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
document_sources:
  - 버전 또는 revision을 확인할 수 있는 URL이나 pinned source 식별자
source_review:
  checked_at: 2026-09-22
  applies_to: 적용 제품과 버전
  location: 근거가 있는 section 또는 code 위치
```

## 6. 작성·재검토 우선순위

운영 RCA 기록(2026-09-28~10-22, 133건)에서 XID 79가 62건, SXID 11001이 46건으로 81%였고 대부분 주입 시험이었다. 코드 없는 알림은 disk(읽기 전용 재마운트)와 cpu가 각 1건이었다. cpc-1 노드는 DGX A100(A100-SXM4, NVSwitch, 드라이버 R580, MIG 비활성)이다. 이 분포와 장비를 기준으로 정한 순서다.

1. 운영 빈도 상위 코드(XID 79, SXID 11001)는 운영자 순서로 재작성한다: 즉시 확인·격리(실제 장애와 주입 시험 구분) → 자료 보존 → 판단 → 복구 → 복구 확인 → 공급사 전달.
2. GPU Node Triage 표 1의 코드는 Triage 개정과 카탈로그를 다시 대조하고, 장비 세대(A100·Hopper)와 운영 모드(bare metal·가상화)별 분기를 먼저 적는다.
3. Fleet 기본 등록 컴포넌트 중 Unhealthy 판정이 있는 컴포넌트는 Runbook 1.2 컴포넌트 목표로 작성하고, 기본 프로필 `health_contracts`에 컴포넌트를 함께 등록한다. 등록 없이 작성만 하면 보고서에 지침이 표시되지 않는다.
4. 남은 일: Fabric Manager 로그·NVSwitch 토폴로지·row remapping 상태·NVLink 오류 카운터 수집(D 등록과 binding), D45·D47 값 해석의 화면 표시, NCCL·IB 성능처럼 수치 계산 fact가 필요한 비코드 Runbook, 대상 장비에서의 명령 재현 검증.
