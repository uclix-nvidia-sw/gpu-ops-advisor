# RCA 보고서 점검 영역 애니메이션

**상태: 검토 자산 준비, 보고서 연결 미구현.** 기준 코드는 main `705f2bf`다. 애니메이션은 확인할 부품군의 위치를 안내한다. 실제 고장 위치·장치 번호·정비 절차를 표현하지 않는다.

[14종 그림·매핑 함께 보기](index.html) · [전체 코드·Runbook·조건·자산 목록](manifest.json)

## 파일과 수정 방법

| 파일 | 용도 |
|---|---|
| `assets/S1.webp` ~ `S7.webp`, `P1.webp` ~ `P7.webp` | 900×600, 14초 반복 애니메이션 14종 |
| 같은 이름의 PNG | 750×500, 점검 영역이 표시된 정지 이미지 14종 |
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

### 위치와 재생

현재 보고서의 [RcaOperatorReport](../../frontend/src/components/RcaOperatorReport.tsx) 안 `rca-response-reference`(2. 대응 순서), 물리 점검을 설명하는 항목 바로 아래에 배치한다. PC는 S/P 두 열, 모바일은 한 열이다. `대상 장치 확정`이나 PCI/UUID 표시 옆에 붙이지 않는다. 1장 요약·3장 관측·4장 분석에는 중복 삽입하지 않는다.

같은 그림은 한 보고서에서 한 번만 표시한다. 첫 화면은 PNG로 두고 `구조 보기`를 누르면 WebP를 재생한다. 정지/다시 보기 조작을 제공하며 모션 감소 설정과 인쇄에서는 PNG를 사용한다. 현재 WebP는 무한 반복 파일이므로 자동 1회 재생은 구현되어 있지 않다. 1회 후 정지가 필요하면 별도 재생 제어를 구현·검증한다.

검토 페이지의 코드 목록·적용 조건·S/P 식별 코드는 운영 보고서에 반복해서 표시하지 않는다. 기존 보고서가 이유와 조치를 설명하고 그림은 영역만 안내한다. 두 예시를 보여주더라도 사용자에게 두 장비를 모두 점검하라고 지시하지 않는다.

### 선택과 데이터 경계

1. 사건에 저장된 코드, 선택된 `runbook_revisions`, 적용 가능한 `quality.runbook_guidance`, 점검 권고의 근거를 읽는다. 최신 작성 Runbook으로 과거 보고서 판단을 다시 만들지 않는다. `reference_only` 지침은 자동 선택 근거로 쓰지 않는다.
2. 코드·Runbook으로 후보를 좁힌 뒤 물리 점검 필요성과 주제별 조건을 확인한다. 코드 일치만으로 삽입하지 않는다. 자유 서술의 단어 검색이나 LLM의 임의 파일명으로 선택하지 않는다.
3. 기존 구조화 결과만으로 조건 또는 대응 항목과의 연결을 확인할 수 없으면 자동 삽입을 보류한다. 추가 구조화 필드가 필요하면 Worker·공유 결과 계약·JC 검증·Frontend 소비자를 함께 변경하고 과거 결과의 필드 부재를 허용한다. 이 패키지는 새 결과 필드를 정의하거나 배포하지 않는다.
4. 검증된 선택 결과를 허용 목록의 그림 ID에 연결하고 같은 ID를 중복 제거한다. 자산 경로는 고정 manifest에서 가져온다. 사건/LLM 입력의 URL·HTML·스크립트를 실행하지 않는다.
5. 모델에 그림을 새로 생성시키지 않는다. 기존 보고서 작성·발행 흐름과 텍스트를 유지하고 준비된 자산을 렌더링한다. 로그·UUID·노드 이름을 그림 파일에 넣지 않는다.

처음 연결할 때는 새 표시 컴포넌트와 선택 함수를 추가하고, 기존 보고서에는 호출 지점만 넣는 것이 좋다. 현재 [RcaNarrative](../../frontend/src/components/RcaNarrative.tsx)의 최신 보고서 경로는 RcaOperatorReport를 재사용한다. 구 보고서 경로에 타입·선택 근거가 없으면 기존 텍스트를 유지한다. Ops 보고서·Worker 실행 횟수·DB 발행·장비 제어는 이번 UI 연결 범위가 아니다.

### 자산 제공·내보내기

구현 시 assets를 프런트엔드 정적 자산 경로로 제공하고 기본 URL/subpath를 반영한다. 현재 docs 경로는 제품 빌드에 자동 포함되지 않는다. 모든 애니메이션을 선로딩하지 말고 선택된 PNG만 지연 로드하며 WebP는 재생 요청 때 가져온다. 자산 로드 실패 시 기존 점검 텍스트를 유지한다.

HTML 저장·인쇄에서는 PNG를 사용한다. 오프라인 HTML은 선택된 PNG를 내장해야 로컬/상대 URL이 끊기지 않는다. 기존 내보내기 CSP·정화 정책을 완화하지 않고, 저장된 그림이 실제 사건 장치 사진인 것처럼 제목을 바꾸지 않는다. 서버 측 HTML 등 별도 출력 경로가 있다면 화면과 따로 검수한다.

## 검수 기준

- XID 79에서 GPU 물리 점검 조건 충족 시 S1/P1, SXID 11001에서 스위치 점검 조건 충족 시 S2만 표시한다.
- NVLink의 GPU·스위치·브리지 조건을 구분한다. 전원·냉각 보조 근거가 없으면 6·7번을 추가하지 않는다.
- DISK 장착 형태 미확인, 단순 조회 실패, 상태 알림만 있는 사건, 매핑 밖 코드, 과거 결과의 필드 누락은 그림을 생략하고 텍스트를 보존한다.
- 여러 코드의 동일 그림은 중복되지 않는다. 식별자 값이 바뀌어도 강조 위치는 바뀌지 않는다.
- PC 두 열·모바일 한 열, 키보드 조작, 모션 감소, 정지·재생, 자산 오류, HTML 저장·인쇄의 정지 이미지와 캡션을 확인한다.
- 선택 함수 단위 검사와 RcaOperatorReport 렌더링 검사를 추가하고 Frontend의 기존 검사·빌드를 수행한다. 결과 계약을 바꾸면 관련 Worker·공유 계약·JC 소비자도 검사한다.

이 패키지에서 확인하는 것은 14종 자산·hash·매핑 수·검토 화면뿐이다. 제품 보고서 연결·실장비 배치 검수·운영 데이터 검증은 아직 완료되지 않았다.

## 구조 참고 출처

SXM은 DGX H100/H200 8U, PCIe는 Supermicro SYS-421GE-TNRT3 4U와 후단 GPU 4+4 배치의 단순화 예시다. 모든 SXM/PCIe 서버의 내부가 같다는 뜻은 아니다. S5의 상부 분리와 하부 트레이 연결은 구조 안내이며 실제 정비 순서를 재현하지 않는다. NIC 슬롯 위치는 대표 배치이며 BMC는 강조에서 제외한다.

- [DGX H100/H200 구성](https://docs.nvidia.com/dgx/dgxh100-user-guide/introduction-to-dgxh100.html), [M.2 어셈블리 접근](https://docs.nvidia.com/dgx/dgxh100-service-manual/m2-boot-assembly-replacement.html)
- [Supermicro 4U 제품](https://www.supermicro.com/en/products/system/gpu/4u/sys-421ge-tnrt3), [MNL-2593 공통 매뉴얼](https://www.supermicro.com/manuals/superserver/4U/MNL-2593.pdf): 10-GPU 사진을 8-GPU의 정확한 슬롯 배치로 해석하지 않는다. 전면 베이 외형은 실제 장착 드라이브 수를 뜻하지 않는다.
- [지원 NIC 구성](https://www.supermicro.com/datasheet/datasheet_SuperCluster_Omniverse_L40S.pdf), [ConnectX-7 포트 자료](https://networking-docs.nvidia.com/connectx7hw)
- [H100 PCIe 브리지 사양](https://www.nvidia.com/content/dam/en-zz/Solutions/gtcs22/data-center/h100/PB-11133-001_v01.pdf), [XID Catalog](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html), [Fabric Manager 가이드](https://docs.nvidia.com/hgx-platforms/fabric-manager-user-guide/index.html)

공식 자료는 구조·의미의 참고 출처이며 이미지의 실장비 정확성이나 모든 세대에서의 코드 지원을 보증하지 않는다. 제공 자산은 참고 자료를 바탕으로 제작한 단순화 그림이다.
