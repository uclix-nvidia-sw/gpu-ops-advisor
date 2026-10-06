# Fleet/DCGM 비교 PDF 재검증 — 2026-10-06

## 대상과 결론

사용자 제공 `fleet_dcgm_181_183_rca_coverage_20261006.pdf` 19쪽을 검토했다. SHA-256은 `d7253680c0179212a40933e511e7844297f73954710067ac1efc701a33aee458`이다. PDF와 원본 운영 데이터는 저장소에 포함하지 않는다. PDF의 제안은 참고 자료이며 [D 계약 계획](../specs/common/d-contract-redesign-plan.md)과 [D 매핑](../specs/common/d-query-mapping.md)을 대체하지 않는다.

**추가 제공한 두 metrics 원본으로 수량과 UUID별 비교를 재현했다. PDF 표 420칸 중 419칸은 표기 정밀도에서 일치했으며, 에너지 1칸은 오류다. 운영 binding 승인은 미완료다.** PDF는 각 환경에서 한 Pod씩의 표본이다. 181/183은 확인 환경 주소이며 GPU 노드 식별자가 아니다. 표본의 GPU 수 8/1을 클러스터 전체 inventory, 가용 GPU 수 또는 사용 가능 용량으로 사용하지 않는다.

PDF의 저장소 기준은 `fc9ae22915020aefdc31f22ac4703a641108a520`이다. 이번 재검증 기준은 PR #71 병합 후 `2849de10205e001423d6b69e268357e975cd43e6`이다. 이후 UI 변경 PR #72의 `a3dd8c4`까지 로컬에 반영했으며 여기서 대조한 런북·계약·Worker는 동일하다. PDF의 과거 완료 선언을 현재 코드나 현재 배포의 검증 결과로 복사하지 않았다.

## 검증표

| PDF 항목 | 판정 | 근거와 적용 한계 |
|---|---|---|
| 1쪽 메트릭 수·공통/전용 수 | 원본 재현 통과 | 첫 환경 Fleet 99(DCGM 57+기타 42)/Exporter 24, 공통 19/Fleet 전용 80/Exporter 전용 5. 두 번째는 83(41+42)/20, 15/68/5. 별도 제공한 첫 환경 names 파일도 파싱한 sample 이름과 일치 |
| 4~11쪽 통합 표 105행 | 번호 검증 통과, 표현 구체화 필요 | 번호 1~105가 각각 한 번 존재하며 원본 이름 누락 없음. 두 환경의 원시 이름 합집합은 **124개**, 대소문자 대응 이름을 묶으면 **105행**. 같은 행은 의미 동등성 승인이 아님 |
| 1~2쪽 값 비교 | UUID별 Decimal 재현 통과 | 첫 환경 8 UUID, 152쌍 중 133 일치/19 차이; 두 번째 1 UUID, 15쌍 중 14 일치/1 차이. 첫 환경 차이는 메모리 온도 1/전력 4/DRAM 8/PCIe RX 3/TX 3으로 일치. 표기된 전력 최대 차이도 일치 |
| 3쪽 FB used ratio | 소스 정의 확인 | Fleet 해당 tag는 DCGM field를 gauge로 내보내며 Used/(Total−Reserved), 0~1을 명시. Used/Total인 용량 비율과 대체하거나 두 값을 일치한다고 판정하지 않음 |
| 3쪽 FB 정수와 비율 | 산술 확인, 원인 미확정 | 239+3+16140=16382이며 표기 total 16384와 2 차이. 3/(16384−239)≈0.00018582는 표기 0.0002400과 다름. 반올림·센서 시각·계산 경로 중 원인 확정 불가 |
| 3쪽 NVLink gauge/counter 차이 | tag 소스 선언 확인 | Fleet는 gauge, 두 Exporter tag의 기본 CSV는 counter. 동일한 0만으로 rate 계산이나 producer 대체를 승인하지 않음 |
| 3쪽 FB MB/MiB, Tensor HELP 차이 | 문구 차이 확인 | Fleet 코드와 두 Exporter tag 기본 CSV에서 차이 확인. 문구만으로 환산하거나 모델별 tensor 의미를 확정하지 않음 |
| 3쪽 PCIe bytes/bytes-per-second | 정의 보완 | 공식 DCGM profiling 정의와 두 Exporter tag의 활성 CSV 행은 bytes/s gauge. CSV의 과거 counter 예시는 주석이다. Fleet HELP의 bytes만 보고 누적 counter로 분류하지 않음. 배포 CSV/전송 변환은 미확인 |
| 3쪽 OS/disk HELP | 소스에서 차이 확인 | disk used는 HELP에 free라고 쓰지만 실제 UsedBytes를 설정. OS used는 Usage가 양수이면 이를 쓰고 아니면 RunningPIDs를 사용하므로 HELP의 RunningPIDs/limit가 항상 성립하지 않음 |
| 3쪽 음수 power violation·빈 Xid UUID | 원본 값 확인, 원인 미확정 | 음수 누적 시간과 Xid counter의 빈 UUID를 재확인. 음수를 유효값이나 0으로 사용하지 않고 overflow/특정 sentinel로 단정하지 않음. 빈 UUID counter를 특정 GPU의 새 사건으로 귀속하지 않음 |
| 3·5쪽 작은 energy 값 | **PDF 오류 — 정정 필요** | 5쪽 23행 첫 환경 Exporter는 5,542~6,095가 아니라 **554,205,031,106~609,520,495,469 mJ**. 3쪽의 비정상적으로 작다는 의심은 이 잘못된 표기에 기반하므로 철회. 원본 counter의 실제 reset/부팅 의미 검증은 별도 |
| 12쪽 states/events | 두 번째 환경 내용 추가 검증 | 새 첨부에서 states 24개 모두 Healthy 표기이나 Xid/SXid/NCCL 3개는 time 없음. NVML 시각은 다른 주 표본보다 224초 이전. events는 24키 중 null 18/빈 배열 6. 현재 무장애·전체 기간 사건 부재로 확대하지 않음. 첫 환경의 이전 states/events 원본은 아직 미제공 |
| 13~16쪽 9개 Domain/31개 Category/267개 Runbook | 현재 저장소 재계수 통과 | 참고 분류 9/31, Xid 173+SXid 93+general 1=267, 모두 content.investigation_only=true. 이름 일치가 원인 판정 정확도나 모든 분석 구현을 뜻하지 않음 |
| 16쪽 evidence group | manifest 대조 통과 | app 56, firmware 10, info 5, memory 12, pcie 3, power 5, nvlink 16, virtual 2, fabric 93, reserved 64. 합계 266은 코드 런북 수이며 general 1은 별도 |
| 17~19쪽 Fleet 중심 제안·중앙 수집 미검증 | 제안/시간 범위 구분 | 단일 수집원 제안은 이번 구현 지시가 아님. 이후 수행한 [중앙 Mimir/Loki 조사](d-binding-cpc-20261006.md)는 별도 시점의 제한 표본이며 PDF 시점의 수신이나 전체 이력을 입증하지 않음 |

## 버전 근거

사용자가 제공한 두 환경의 Pod 출력은 Fleet `1.5.0-rc.1`과 동일 imageID `sha256:d9a61090116f1f9a2f183c6779fb1b76f4792f6e927b60c64f33a5137577d18b`를 보여준다. 각 환경에서 Fleet Pod 두 개의 정보가 제공되었다. Exporter/HostEngine은 다음과 같으며 imageID는 아직 제공되지 않았다. KSM Pod 존재는 확인되지만 버전은 미확인이다.

| 환경 | HostEngine image tag | Exporter image tag |
|---|---|---|
| CPC-1 | 4.2.3-1-ubuntu22.04 | 4.2.3-4.1.3-ubuntu22.04 |
| CPC-2 | 4.4.2-1-ubuntu22.04 | 4.4.2-4.7.0-distroless |

Fleet 공식 tag `v1.5.0-rc.1`을 읽기 전용으로 확인했으며 commit은 `8dd8826b7604386ad667125298156ddb1d1a7865`이다. **동일 tag의 소스 확인은 실행 image digest와의 빌드 provenance 검증이 아니다.** 기본 CSV도 실제 mounted collectors CSV를 입증하지 않는다.

- [Fleet memory 정의](https://github.com/dsx-ai-factory/fleet-intelligence-agent/blob/8dd8826b7604386ad667125298156ddb1d1a7865/third_party/fleet-intelligence-sdk/components/accelerator/nvidia/dcgm/mem/metrics.go), [값 전달 코드](https://github.com/dsx-ai-factory/fleet-intelligence-agent/blob/8dd8826b7604386ad667125298156ddb1d1a7865/third_party/fleet-intelligence-sdk/components/accelerator/nvidia/dcgm/mem/component.go)
- [Fleet NVLink 정의](https://github.com/dsx-ai-factory/fleet-intelligence-agent/blob/8dd8826b7604386ad667125298156ddb1d1a7865/third_party/fleet-intelligence-sdk/components/accelerator/nvidia/dcgm/nvlink/metrics.go), [profiling 정의](https://github.com/dsx-ai-factory/fleet-intelligence-agent/blob/8dd8826b7604386ad667125298156ddb1d1a7865/third_party/fleet-intelligence-sdk/components/accelerator/nvidia/dcgm/prof/metrics.go)
- [Fleet OS 계산](https://github.com/dsx-ai-factory/fleet-intelligence-agent/blob/8dd8826b7604386ad667125298156ddb1d1a7865/third_party/fleet-intelligence-sdk/components/os/component.go), [disk HELP](https://github.com/dsx-ai-factory/fleet-intelligence-agent/blob/8dd8826b7604386ad667125298156ddb1d1a7865/third_party/fleet-intelligence-sdk/components/disk/metrics.go), [disk 값 전달](https://github.com/dsx-ai-factory/fleet-intelligence-agent/blob/8dd8826b7604386ad667125298156ddb1d1a7865/third_party/fleet-intelligence-sdk/components/disk/component.go)
- Exporter 기본 CSV: [4.2.3-4.1.3](https://github.com/NVIDIA/dcgm-exporter/blob/4.2.3-4.1.3/etc/default-counters.csv), [4.4.2-4.7.0](https://github.com/NVIDIA/dcgm-exporter/blob/4.4.2-4.7.0/etc/default-counters.csv)
- [NVIDIA DCGM profiling 정의](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html): 일반 정의의 보조 근거이며 배포 버전 검증과 구별
- 현행 [분류 참고 자료](../specs/rca-agent/references/domain-category-metric-mapping.md), [Runbook manifest](../../rcca-agent/runbooks/catalog-manifest.json)

## 원본 재현 방법과 남은 단계

사용자가 두 `/tmp/gpu-observe.*` 디렉터리의 터미널 출력을 추가 제공했다. 명령 경계로 metrics/names/states/events를 분리하고 원시 숫자를 Decimal로 읽었다. GPU 비교는 동일 UUID끼리 수행하며 중복·신원 불일치를 검사했다. PDF 105행의 네 칸(환경 2 × 생산자 2), 총 420칸을 존재 여부와 min/max로 대조했다. 반올림 허용 오차는 각 표기 숫자의 마지막 자리 절반이며 실제 센서 오차 허용치가 아니다. 419칸 일치, 에너지 1칸 불일치를 확인했고 PDF 5쪽 렌더링으로 추출 오류가 아님도 확인했다.

- 첫 첨부 SHA-256: `3eca7a20c257d73237b7d4bd9012798e11b3913158d55ccd230e2f837e99c1a5`
- 두 번째 첨부 SHA-256: `3b40f2b41ec5eefecfa98eef35824cd0508ad615fb6ea6afa1f63a4eeeb9dea8`

파싱한 metrics에는 명시적인 개별 sample timestamp가 없었다. 파일 목록·states 시각은 센서 동시성의 증거가 아니다. 새로 제공된 두 번째 환경의 states/events 내용은 PDF 작성 시점의 검토 범위를 확장하는 근거로 별도 기록했다. 첫 환경의 이전 states/events 원본 및 오류 재현/전체 이력 검증은 남아 있다. PDF 원본은 수정하지 않고 이 문서에 정정 내용을 남겼다.

운영 활성화 전에는 KSM 이미지, Exporter imageID와 실제 collectors CSV, Fleet/Alloy 전송 변환·필터, 보존/수집 주기·max_hold, 원천 시각 의미가 필요하다. 기본 D별 근거를 충족한 binding부터 선택한 뒤 두 Worker 결과를 검수한다. 현재 공통 예제 JSON/Helm 사본은 변경 없이 미선택 상태를 유지한다.

이번 변경의 PR 범위는 환경 원장·PDF 감사 기록과 D19/D20 소비 차원 검증이다. 전체 신규/조건부 분석 완료나 운영 활성화 PR로 표시하지 않는다. 로컬 회귀 결과는 [Agent QA](../../agents/QA.md)에 기록한다.
