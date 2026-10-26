# RCA 보고서 점검 영역 애니메이션

**상태: 보고서 2장 연결 구현(GPU·NVSwitch·네트워크 포트 그림 5종), 나머지 9종은 보류.** 애니메이션은 확인할 부품군의 위치를 안내한다. 실제 고장 위치·장치 번호·정비 절차를 표현하지 않는다.

[14종 그림·매핑 함께 보기](index.html) · [전체 코드·Runbook·조건·자산 목록](manifest.json)

## 파일과 수정 방법

| 파일 | 용도 |
|---|---|
| [`frontend/public/inspection-figures/`](../../frontend/public/inspection-figures/) `S1.webp` ~ `S7.webp`, `P1.webp` ~ `P7.webp` | 900×600, 14초 반복 애니메이션 14종. 제품 화면이 정적 자산으로 그대로 제공한다 |
| 같은 폴더·같은 이름의 PNG | 750×500, 점검 영역이 표시된 정지 이미지 14종 |
| [manifest.json](manifest.json) | 그림 ID·제목·경로·SHA-256·조건부 매핑의 단일 원본 |
| [review-template.html](review-template.html) | 검토 화면 템플릿 |
| [build-review.py](build-review.py) | 자산 무결성 확인 및 검토 화면 생성; Python 표준 라이브러리만 사용 |
| [index.html](index.html) | 생성된 검토 화면. 브라우저에서 직접 열기 |

매핑은 manifest, 검토 UI는 템플릿을 수정하고 저장소 루트에서 `python docs/rca-animations/build-review.py`를 실행한다. index.html을 직접 수정하지 않는다. 원본 자산은 약 50 MiB이며 GIF·옛 C 코드·중복 HTML 애니메이션은 포함하지 않는다. 기하 모델 생성기는 이번 전달 범위에 포함하지 않는다. 이미지가 바뀌면 경로와 hash를 함께 갱신한다.

## 표시 정책

- 첫 구현에서는 **SXM/PCIe를 자동 판별하지 않는다.** 선택한 점검 주제의 S/P 예시를 둘 다 표시한다. 모델명·PCI BDF·UUID로 그림 위치를 바꾸지 않는다.
- SXID의 NVSwitch 점검은 **S2만** 표시한다. P2는 NVSwitch의 PCIe 대체 그림이 아니다.
- NVLink 점검에서 S2는 NVSwitch 구성, P2는 외부 브리지 장착 구성의 조건부 참고다. 두 구성이 해당 서버에 실제 존재한다고 표현하지 않는다. GPU 측 점검만 권고되면 S1/P1만 사용한다.
- 장착 형태 미확인 때문에 두 예시를 보여주는 것과, 물리 점검 필요성을 확인하지 못한 것은 구분한다. 후자는 그림을 넣지 않는다.
- 제목은 `SXM(예시) · GPU`, `PCIe(예시) · GPU`처럼 타입을 앞에 둔다. 그림 아래에는 “실제 장비의 구성에 맞는 예시를 참고하세요. 표시 영역은 실제 장치 위치를 특정하지 않습니다.”만 표시한다.
- 관련 부품군 전체를 강조한다. 개별 GPU·포트·팬을 선택하거나 PCI 번호에 맞춰 강조 영역을 바꾸지 않는다.
- NVL72·PDU는 제외한다. PSU는 서버 내부 전원 부품이다.

## 그림 선택

정확한 XID/SXID 목록과 컴포넌트 Runbook 이름은 [manifest.json](manifest.json)의 `xid`, `sxid`, `runbooks`, `conditions`를 따른다. 숫자 문자열은 범위를 포함한 **검토용 표기**이며 실행용 규칙 엔진이 아니다. 실제 선택 구현에서는 숫자 집합과 명시적인 조건으로 옮겨 검증해야 한다.

| 주제 | 그림 | 적용 범위 |
|---|---|---|
| GPU | S1 / P1 | GPU–호스트 PCIe, GPU 메모리, GPU 측 NVLink·전력 등의 물리 점검 |
| GPU 간 연결 | S2 / P2 | NVSwitch 또는 실제 외부 NVLink 브리지 점검. SXID는 S2만 |
| 네트워크 포트 | S3 / P3 | INFINIBAND·NETWORK-ETHERNET의 데이터 포트 점검. BMC 제외 |
| 전면 드라이브 | S4 / P4 | DISK에서 전면 장착 장치임이 확인되고 물리 점검이 필요한 경우 |
| 내부 M.2 | S5 / P5 | DISK에서 내부 M.2임이 확인되고 물리 점검이 필요한 경우 |
| PSU·전원 입력 | S6 / P6 | DCGM-POWER에서 노드 전원 계통의 추가 점검 근거가 있는 경우 |
| 팬·흡기 | S7 / P7 | DCGM-THERMAL에서 냉각 계통 점검을 권고한 경우 |

XID 28개, SXID 92개, 컴포넌트 Runbook 11개가 조건부 후보다. 하나의 코드가 여러 그림의 후보일 수 있으므로 카드별 수를 합산하지 않는다. 기존 분류 284개 중 나머지 153개는 기본 그림 대상에서 제외한다.

추가 선택 조건:

- XID 63·156·162의 복구/상태 기록만 있거나 수집 실패·설정 확인만 필요한 경우는 생략한다. XID 79·54·162–165만으로 PSU 그림을 선택하지 않는다.
- PERSISTENCE-MODE는 GPU lost/reset-required의 점검 분기만 대상이다. InfoROM은 손상 보고의 GPU 영역만 안내한다.
- SXID 20009는 보류다. 10005의 열 이벤트 종료나 22013의 인터럽트 등 상태 안내만 필요한 사건에는 S2를 자동 삽입하지 않는다. 코드가 해당 제품·생산자에서 지원되는지도 확인한다.
- 디스크 이름 `nvme0`나 루트 파일시스템만으로 전면 드라이브/M.2를 선택하지 않는다. 파일시스템·RAID 논리 문제만 있으면 생략한다.
- LIBRARY·NCCL·PEERMEM·CPU·MEMORY·OS와 일반 조사에는 기본 그림을 배정하지 않는다. 별도 물리 점검 근거 없이 라이브러리·자원 문제를 하드웨어 점검으로 바꾸지 않는다.

## 보고서 연결 구현

[RcaOperatorReport](../../frontend/src/components/RcaOperatorReport.tsx)의 2장 "대응 순서"에서, 물리 작업을 지시하는 런북 단계 바로 아래에 작은 미리보기(정지 PNG, 96×64)를 둔다. 미리보기를 누르면 큰 그림 창이 열리고 "구조 보기"를 누를 때만 WebP를 내려받아 재생한다. 모션 줄이기 설정에서는 재생 버튼을 숨긴다. 그림을 불러오지 못하면 미리보기 줄을 숨기고 단계 글은 그대로 둔다. 1장 요약·3장 관측·4장 분석에는 넣지 않는다.

그림 선택은 [inspectionFigures.ts](../../frontend/src/lib/inspectionFigures.ts)의 고정 대응표(알림 코드 또는 Fleet 컴포넌트 → 런북 단계 제목 → 그림)다. 코드가 manifest 후보라는 이유만으로 넣지 않고, 보고서에 저장된 런북 지침에 그 단계가 있을 때만 넣는다. 런북·Worker·결과 형식·Backend 검사는 바꾸지 않는다. [테스트](../../frontend/src/lib/inspectionFigures.test.ts)가 대응표의 단계 제목이 저장소 런북에 실제로 있는지 확인하므로, 단계 제목이 바뀌면 테스트가 실패한다.

| 코드·컴포넌트 | 단계 | 그림 | 단계가 지시하는 물리 작업 |
|---|---|---|---|
| XID 79 | 복구: 호스트 재시작 (RESTART_BM) | S1·P1 | 재시작 뒤에도 GPU가 없으면 GPU 재장착 |
| XID 54 | 복구 조치 | S1·P1 | CHECK_MECHANICALS: 장착 상태·보조 전원 커넥터 |
| XID 74 | 오류별 판단 기준 | S1·P1 | GPU 쪽 링크의 기계적 연결 점검·재장착 |
| SXID 11001 | 공급사 전달 (재발) | S2 | 스위치·포트 하드웨어 점검(HARDWARE_INSPECTION) |
| accelerator-nvidia-dcgm-pcie | 복구 | S1·P1 | GPU 재장착·연결 점검 |
| accelerator-nvidia-infiniband | 복구 | S3·P3 | 케이블·트랜시버 재장착·교체 |
| network-ethernet | 복구 | S3·P3 | 케이블·스위치 포트 점검 |

남은 작업:

- 보류 그림: P2(브리지 장착 여부), S4·P4·S5·P5(디스크 장착 형태), S6·P6·S7·P7(전원·냉각 보조 근거)은 보고서가 조건을 판단할 근거가 없어 넣지 않았다. manifest의 다른 후보 코드도 런북 단계가 물리 작업을 지시하지 않아 그림이 없다. 런북 문장에 물리 점검이 생기면 대응표에 한 줄을 더한다.
- HTML 저장: [readerExport](../../frontend/src/lib/readerExport.ts)는 버튼을 지우고 `img-src data:`만 허용하므로 저장된 HTML에는 그림이 빠지고 글만 남는다. 선택된 PNG를 data URI로 넣으려면 내보내기를 비동기로 바꿔야 한다.
- 실장비 배치 검수와 운영 보고서 화면 확인은 배포 뒤에 한다.

## 검수 기준

- XID 79에서 GPU 물리 점검 조건 충족 시 S1/P1, SXID 11001에서 스위치 점검 조건 충족 시 S2만 표시한다.
- NVLink의 GPU·스위치·브리지 조건을 구분한다. 전원·냉각 보조 근거가 없으면 6·7번을 추가하지 않는다.
- DISK 장착 형태 미확인, 단순 조회 실패, 상태 알림만 있는 사건, 매핑 밖 코드, 과거 결과의 필드 누락은 그림을 생략하고 텍스트를 보존한다.
- 여러 코드의 동일 그림은 중복되지 않는다. 식별자 값이 바뀌어도 강조 위치는 바뀌지 않는다.
- PC 두 열·모바일 한 열, 키보드 조작, 모션 감소, 정지·재생, 자산 오류, HTML 저장·인쇄의 정지 이미지와 캡션을 확인한다.
- 선택 함수 단위 검사와 RcaOperatorReport 렌더링 검사를 추가하고 Frontend의 기존 검사·빌드를 수행한다. 결과 계약을 바꾸면 관련 Worker·공유 계약·JC 소비자도 검사한다.

`build-review.py`는 14종 자산·hash·매핑 수·검토 화면을 확인한다. 실장비 배치 검수·운영 데이터 검증은 아직 완료되지 않았다.

## 구조 참고 출처

SXM은 DGX H100/H200 8U, PCIe는 Supermicro SYS-421GE-TNRT3 4U와 후단 GPU 4+4 배치의 단순화 예시다. 모든 SXM/PCIe 서버의 내부가 같다는 뜻은 아니다. S5의 상부 분리와 하부 트레이 연결은 구조 안내이며 실제 정비 순서를 재현하지 않는다. NIC 슬롯 위치는 대표 배치이며 BMC는 강조에서 제외한다.

- [DGX H100/H200 구성](https://docs.nvidia.com/dgx/dgxh100-user-guide/introduction-to-dgxh100.html), [M.2 어셈블리 접근](https://docs.nvidia.com/dgx/dgxh100-service-manual/m2-boot-assembly-replacement.html)
- [Supermicro 4U 제품](https://www.supermicro.com/en/products/system/gpu/4u/sys-421ge-tnrt3), [MNL-2593 공통 매뉴얼](https://www.supermicro.com/manuals/superserver/4U/MNL-2593.pdf): 10-GPU 사진을 8-GPU의 정확한 슬롯 배치로 해석하지 않는다. 전면 베이 외형은 실제 장착 드라이브 수를 뜻하지 않는다.
- [지원 NIC 구성](https://www.supermicro.com/datasheet/datasheet_SuperCluster_Omniverse_L40S.pdf), [ConnectX-7 포트 자료](https://networking-docs.nvidia.com/connectx7hw)
- [H100 PCIe 브리지 사양](https://www.nvidia.com/content/dam/en-zz/Solutions/gtcs22/data-center/h100/PB-11133-001_v01.pdf), [XID Catalog](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html), [Fabric Manager 가이드](https://docs.nvidia.com/hgx-platforms/fabric-manager-user-guide/index.html)

공식 자료는 구조·의미의 참고 출처이며 이미지의 실장비 정확성이나 모든 세대에서의 코드 지원을 보증하지 않는다. 제공 자산은 참고 자료를 바탕으로 제작한 단순화 그림이다.
