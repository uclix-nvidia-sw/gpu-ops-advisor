# DSX 문서 3종 통합 원고 — 검토본 v0.1

- 기준일: 2026-08-21
- 수정 반영: PhysicsNeMo·Surrogate Model을 발열 예측과 반복 레이아웃 검증을 위한 권장 핵심 구성으로 재정의
- 목적: 최종 PPT/PDF 제작 전에 논리 흐름, 설명 깊이, 용어와 컴포넌트 범위를 함께 검토하기 위한 원고
- 적용 문서:
  1. 초보자용 `DSX Understanding` 슬라이드
  2. 기술 참조용 `DSX Component Guide` PDF
  3. 고객·SI용 `DSX & Omniverse Adoption Guide` 슬라이드

> 이 검토본은 디자인 시안이 아니다. 각 장에서 독자가 무엇을 이해해야 하는지, 어떤 도식과 컴포넌트를 포함할지를 먼저 확정하기 위한 문서다.

---

## 0. 세 문서가 공유할 핵심 관점

### 0.1 DSX의 한 문장 정의

NVIDIA DSX는 AI Factory를 **설계하고, 시뮬레이션하고, 구축하고, 운영하기 위한 참조 설계·소프트웨어·API·라이브러리·통합 규격의 집합**이다.

DSX를 하나의 설치 패키지나 단일 운영 제품으로 설명하지 않는다. 공개 문서와 오픈소스 구성요소, NVIDIA 제품, 제한적으로 제공되는 기술, 시설·전력·냉각 파트너 솔루션, 고객 또는 SI가 개발해야 하는 통합 애플리케이션이 함께 하나의 체계를 이룬다.

### 0.2 최상위 구조

최상위 설명은 다음 구조를 기준으로 통일한다.

1. **DSX Sim** — 논리·물리 인프라와 AI Factory Digital Twin을 설계하고 검증하는 영역
2. **DSX OS** — AI Factory의 인프라 및 AI 워크로드를 구축·운영하는 모듈형 소프트웨어 영역
3. **DSX MaxLPS** — 제한된 전력 범위에서 성능/와트를 높이기 위한 칩·열·시스템·소프트웨어 기술 체계
4. **DSX Exchange** — 전력·냉각·BMS와 컴퓨트·네트워크·스케줄러 사이의 IT/OT 통신 허브
5. **DSX Flex** — 전력망, 현장 발전, 재생에너지, 저장장치 신호에 맞춰 AI 부하를 조정하기 위한 전력 오케스트레이션 규격
6. **DSX Hardware / Facilities Infrastructure / Reference Designs** — 컴퓨트·네트워크·스토리지 및 토지·건물·냉각·전력의 세대별 기준 설계

### 0.3 DSX Sim의 두 역할

DSX Sim은 독자가 이해하기 쉽도록 두 시점으로 설명한다.

#### 구축 전: 설계·검증

- CAD/BIM/PLM 데이터를 OpenUSD로 전환
- 전력, 열·냉각, 연결점 등의 메타데이터를 추가해 SimReady 자산 구축
- CFD, 전기, 전력망, 부지 등 물리 시뮬레이션 수행
- DSX Air를 이용해 네트워크 및 논리 인프라 구성 검증
- 고정밀 Solver 결과로 PhysicsNeMo 기반 Surrogate Model을 학습해 발열·온도·유동을 빠르게 예측하고 레이아웃을 반복 검증
- 설계안 비교, 장애 시나리오, 용량·레이아웃 검토

#### 구축 후: 운영 Digital Twin의 기반

- 구축 당시의 자산·공간·연결 관계를 운영 자산 ID 및 텔레메트리 태그와 연결
- NVIDIA Mission Control/BCM, DCGM, NMX/UFM/NetQ, Run:ai, BMS/EPMS/DCIM 등의 데이터를 통합
- Omniverse 기반 3D 공간 화면과 2D 지표·알람·추세 화면을 함께 제공
- 전력, 열, 네트워크, GPU, 워크로드 상태를 한 문맥에서 분석
- 최적화 결과를 스케줄러·전력 제어·시설 제어로 전달할 수 있는 폐루프 기반 마련

단, **구축 후 운영 기능 전체를 DSX Sim 단독 기능으로 표현하지 않는다.** 운영 Digital Twin은 Omniverse AIF-DT, DSX OS, DSX Exchange, MaxLPS/Flex 및 외부 운영 시스템의 결합으로 설명한다.

### 0.4 Omniverse의 위치

Omniverse는 DSX 전체의 운영 제어 플랫폼이라기보다 다음을 담당하는 핵심 기술 기반이다.

- OpenUSD 기반 자산·공간·연결 관계 표현
- SimReady 자산 파이프라인
- Kit 기반 실시간 3D 애플리케이션
- WebRTC/App Streaming을 통한 원격 Viewer 제공
- Solver 결과, 운영 텔레메트리, AI Agent를 하나의 Digital Twin 애플리케이션에 연결

따라서 “Omniverse를 설치하면 DSX 운영 화면이 완성된다”라고 설명하지 않는다. NVIDIA Blueprint는 개발 출발점이며, 실제 운영에는 데이터 어댑터, 자산 매핑, 시계열 저장소, 알람·권한·업무 흐름, 2D 화면과 시스템 연계가 필요하다.

### 0.5 PhysicsNeMo와 Surrogate Model

- 사전 레이아웃 검증에는 열·유동·전력 등 **물리 현상을 예측하는 시뮬레이션 능력이 필수**다.
- 고정밀 CFD Solver는 학습·검증용 데이터를 만들고 기준 정확도를 제공하며, Surrogate Model은 랙 배치와 발열 조건이 바뀔 때 온도·속도·압력 분포를 빠르게 예측한다.
- PhysicsNeMo는 이러한 Physics AI Surrogate Model을 구축·학습·추론하기 위한 NVIDIA의 **권장 핵심 구현 경로**로 설명한다.
- DSX Blueprint의 목표 구조에서는 `고정밀 Solver → 학습 데이터 → PhysicsNeMo 기반 Surrogate Model → API 기반 빠른 예측 → Omniverse 시각화`가 핵심 흐름이다.
- 다른 Solver나 AI Framework로 구현할 수 있다는 것은 구현 제품을 대체할 수 있다는 의미이지, 사전 시뮬레이션과 빠른 예측 능력 자체가 부가 기능이라는 의미는 아니다.

### 0.6 운영 화면의 원칙

- 3D: 공간 위치, 영향 범위, 자산 관계, 열 분포, 장애 전파와 현장 문맥
- 2D: 알람 목록, 시계열, KPI, 작업 이력, 용량·비용·SLA 분석
- 운영 애플리케이션은 3D가 2D를 대체하는 구조가 아니라 **3D와 2D를 결합하는 구조**로 설명한다.

### 0.7 관측과 제어의 구분

1. **관측** — 상태를 수집·정규화·저장·시각화한다.
2. **분석/권고** — 상관관계, 예측, 최적화 결과를 생성한다.
3. **제어** — 승인 정책과 안전 조건에 따라 스케줄러, 전력 소프트웨어, BMS/시설 제어기에 명령을 전달한다.

Digital Twin이 데이터를 보여주는 것과, 실제 설비·워크로드를 자동 제어하는 것은 별도의 수준으로 구분한다.

### 0.8 공개·제품·개발 범위 표기

모든 컴포넌트는 다음 중 하나로 표시한다.

| 구분 | 의미 |
|---|---|
| DSX Capability | DSX의 공식 상위 기능 또는 체계 |
| NVIDIA Product | 별도 설치·구독·라이선스 또는 제품 지원 범위가 있는 NVIDIA 소프트웨어 |
| NVIDIA Open Source / Blueprint | 공개 저장소나 참조 구현으로 제공되는 구성요소 |
| Interface / Standard | OpenUSD, AsyncAPI, OTel처럼 통합을 가능하게 하는 규격 |
| External System | BMS, EPMS, DCIM, CAD/BIM, Solver 등 타사 또는 고객 시스템 |
| Project Development | 운영 화면, 어댑터, 데이터 모델, 승인 로직처럼 고객/SI가 구현할 영역 |
| Restricted / Early Preview | NVOnline, 승인된 초기 검증 등 공개 범위가 제한된 자료·기능 |

### 0.9 자체 구축 관점의 공식 자료 우선순위

이 문서 3종은 고객이 AI 데이터센터를 직접 구축하고 자체 서비스를 운영하는 시나리오를 기준으로 한다.

1. DSX 최상위 문서: DSX Sim/OS/MaxLPS/Exchange/Flex의 기능 체계
2. DGX SuperPOD Reference Architecture: 온프레미스 AI Factory의 하드웨어·소프트웨어 운영 구조
3. NVIDIA Mission Control 문서와 SBOM: Blackwell/Rubin 계열의 통합 운영 Stack과 실제 포함 컴포넌트
4. BCM, DCGM, NMX, UFM, Run:ai 등 개별 제품 문서: 각 구성요소의 기능과 배치
5. Omniverse DSX Blueprint/PhysicsNeMo 문서: Digital Twin과 시뮬레이션 구조

NVIDIA Cloud Partner(NCP) 문서는 외부 고객에게 멀티테넌트 Bare Metal/Cloud 서비스를 제공하는 사업자용 참조다. 자체 구축 아키텍처의 주 근거로 사용하지 않으며, Cloud Provider형 멀티테넌시를 별도로 비교할 때만 보조 자료로 사용한다. NICo 자체는 공식 DSX OS 페이지에 명시되어 있으므로 공식 DSX 구성표에는 유지하되, NICo 중심 NCP 구축 구조는 자체 구축 핵심 흐름에서 제외한다.

공식 DSX Architecture와 자체 구축 구현안을 같은 그림에 섞지 않는다. Mission Control, BCM, DCGM은 자체 구축 AI Factory의 공식 NVIDIA 제품이지만, 현재 공개 DSX 최상위 문서가 이들을 DSX OS 구성요소로 직접 명시하지 않는다. 따라서 이들은 `DSX 공식 구성요소`가 아니라 `자체 구축 시 연계 가능한 NVIDIA 운영 제품`으로 별도 Lane에 표시한다.

---

# 1. 초보자용 DSX 슬라이드 원고

## 문서 정의

- 가제: `DSX Understanding 2026.08`
- 예상 분량: 26장
- 독자: DSX를 처음 접하는 기술·사업·시설 담당자
- 목표: 제품 이름을 외우게 하는 것이 아니라, DSX가 왜 필요하고 각 영역이 어떤 역할을 하며 전체 생애주기가 어떻게 이어지는지 이해시킨다.
- 설명 깊이: 컴포넌트는 “어느 영역에서 무슨 역할을 하는가”까지만 설명한다.

## 전체 논리

`AI Factory가 어려운 이유 → DSX의 정의 → 전체 모듈 → 설계/시뮬레이션 → 구축/운영 → 통합/최적화 → 실제 도입 시 필요한 일`

## 슬라이드별 원고

### 1. 표지 — NVIDIA DSX에 대한 이해

- 부제: AI Factory의 설계, 시뮬레이션, 구축, 운영을 하나의 생애주기로 이해하기
- 핵심 문장: DSX는 하나의 제품이 아니라 AI Factory 전 생애주기를 연결하는 체계다.

### 2. AI Factory는 일반 데이터센터와 무엇이 다른가

- GPU 랙의 전력 밀도와 열 밀도가 매우 높다.
- 컴퓨트 성능이 네트워크, 냉각, 전력 가용량과 직접 연결된다.
- 하드웨어·시설·워크로드를 따로 최적화하면 전체 효율을 보장하기 어렵다.
- 도식: `GPU 성능 ↔ 네트워크 ↔ 전력 ↔ 냉각 ↔ 워크로드`

### 3. 기존 방식의 한계

- CAD/BIM, 네트워크 설계, 시설 제어, GPU 모니터링, 워크로드 관리가 서로 다른 도구에 흩어져 있다.
- 설계 단계의 모델과 운영 단계의 자산·데이터가 끊어지는 경우가 많다.
- 장애나 전력 제약이 발생했을 때 IT와 OT가 같은 자산·시간·상태를 기준으로 판단하기 어렵다.

### 4. DSX의 한 문장 정의

- DSX는 AI Factory를 설계·시뮬레이션·구축·운영하는 데 필요한 참조 설계와 소프트웨어, API, 라이브러리, 통합 규격을 묶은 NVIDIA의 플랫폼 체계다.
- 강조: `단일 패키지 ≠ DSX`

### 5. DSX 전체 지도

- DSX Sim
- DSX OS
- DSX MaxLPS
- DSX Exchange
- DSX Flex
- Hardware / Facilities / Reference Designs
- 도식: 상단은 설계·시뮬레이션, 중앙은 운영 SW와 통합, 하단은 물리 인프라와 전력망.

### 6. DSX를 생애주기로 보면

1. 설계 기준선
2. 사전 시뮬레이션
3. 시공·시운전
4. 운영 데이터 통합
5. Digital Twin 운영 화면
6. 최적화·제어와 설계 피드백

### 7. DSX Sim — 구축 전과 구축 후를 연결

- 구축 전: 설계안과 물리·논리 인프라를 검증
- 구축 후: 같은 Digital Twin에 실제 자산과 운영 데이터를 연결
- 주의: 운영 기능은 DSX Sim만이 아니라 DSX OS·Exchange·외부 시스템과 함께 완성된다.

### 8. 설계 기준선 — CAD/BIM/PLM에서 OpenUSD로

- 건물, 랙, 서버, 냉각장비, 전력장비, 배관·케이블 정보를 하나의 장면으로 조립
- OpenUSD를 공통 3D·데이터 표현 기반으로 사용
- PLM/자산 시스템이 설계 정보의 원본 관리 역할을 담당할 수 있음

### 9. SimReady — 보기 좋은 3D를 계산 가능한 자산으로

- 형상만 변환하는 것으로는 시뮬레이션과 운영 연계가 어렵다.
- 전력, 열·냉각, 연결점, 자산 식별 정보를 메타데이터로 부여
- 예: 랙의 전력 입력, CDU의 냉각 연결점, 장비의 내부/외부 형상 구분

### 10. 물리 시뮬레이션 — 배치 전에 검증

- 열/CFD, 전기, 전력망, 부지 시뮬레이션
- 랙 배치, 냉각 경로, 전력 부하, 장애 조건을 비교
- Omniverse는 장면과 결과를 연결하며, 실제 계산은 도메인 Solver가 수행할 수 있음

### 11. 논리 시뮬레이션 — DSX Air

- GPU, DPU, SuperNIC, 스위치와 연계 솔루션의 논리 구성을 가상 환경에서 검증
- 네트워크 토폴로지, 설정, 배포 절차를 실제 구축 전에 시험
- 물리 CFD와 다른 종류의 시뮬레이션임을 구분

### 12. PhysicsNeMo와 Surrogate Model — 발열 예측과 반복 검증의 핵심

- 고정밀 CFD Solver로 다양한 랙 배치와 발열 조건의 학습·검증 데이터를 생성한다.
- PhysicsNeMo 기반 Surrogate Model은 형상, 랙 수, 열 부하 등의 조건이 바뀔 때 온도·유속·압력 분포를 빠르게 예측한다.
- DSX Blueprint는 이 예측 결과를 API로 호출해 Omniverse 장면에 표시함으로써 반복적인 레이아웃 검토와 Hot Spot 분석을 지원한다.
- 따라서 사전 설계에서는 물리 Solver가 정확도 기준을 만들고, PhysicsNeMo·Surrogate Model이 반복 분석 속도를 높이는 권장 핵심 구조로 설명한다.

### 13. Omniverse AIF-DT — Digital Twin 애플리케이션의 기반

- OpenUSD 장면
- Omniverse Kit 기반 3D 렌더링
- Solver/Surrogate 결과 표시
- WebRTC/App Streaming Viewer
- AI Agent 및 데이터 저장소 연계

### 14. 구축 후에는 무엇을 연결하는가

- 컴퓨트·클러스터: NVIDIA Mission Control/BCM — 자체 구축 시 연계하는 NVIDIA 운영 제품
- GPU: DCGM
- NVLink·InfiniBand·Ethernet: NMX/UFM/NetQ/NVUE
- 워크로드: Run:ai, Kubernetes, Slurm
- 시설: BMS/EPMS/DCIM
- 핵심: 모든 데이터가 동일한 Asset ID와 시간 기준을 공유해야 한다.

### 15. DSX OS — AI Factory 소프트웨어 계층

- Platform Software: 스케줄링, 워크로드, 서비스 오케스트레이션, 추론
- Infrastructure Software: 클러스터 런타임, 프로비저닝, 관측, 복구, 네트워크·인벤토리 관리
- 오픈소스·제품·파트너 기술을 목적에 맞게 조합하는 모듈형 구조

### 16. 워크로드와 AI 서비스

- KAI Scheduler: Kubernetes 기반 AI 작업 배치
- Run:ai: GPU 자원·프로젝트·쿼터·워크로드 관리
- NVCF: AI/시뮬레이션 워크로드를 API 서비스로 오케스트레이션
- Grove/Dynamo: 분산 추론 워크로드 정의·실행
- 설명 수준: 역할 차이만 제시하고 설치 구조는 상세 PDF로 이동

### 17. DSX OS와 실제 구축 제품을 구분

- 공식 DSX OS: KAI Scheduler, Run:ai, NVCF, Grove, Dynamo, GPU/Network Operator, AICR, NVSentinel, Fleet Intelligence, NICo, DPF, Switch Infrastructure Config Manager 등 현재 DSX 페이지에 명시된 구성
- 자체 구축 NVIDIA 운영 Stack: Mission Control, BCM, DCGM, NMX/UFM/NetQ, Slurm/Kubernetes 등 별도 제품·참조 아키텍처
- 두 영역은 기능적으로 연결될 수 있지만 NVIDIA가 공개 DSX Architecture에서 직접 포함 관계로 정의하지 않았으므로 같은 Box 안에 넣지 않음
- Mission Control/BCM/DCGM은 `DSX 구성요소`가 아니라 `DSX 기반 자체 구축 시 연계하는 운영 제품 예시`로 표시
- DSX OS 컴포넌트가 BCM을 대체하도록 공식 지시된 것이 아님. DGX/Enterprise 자체 구축에서는 Mission Control과 BCM을 계속 사용하는 경로가 존재함
- NICo·AICR·Operator·KAI·NVSentinel 등은 Cloud Provider/Partner가 모듈형 멀티테넌트 Platform을 구성할 때 선택하는 별도 경로이며, BCM의 후속 제품 목록으로 해석하지 않음
- 필요에 따라 BCM으로 구축한 Cluster 위에 AICR, GPU Operator, Run:ai, NVSentinel 등 DSX OS 기술을 보완적으로 사용할 수 있음
- 현재 공개 DSX OS에는 Mission Control과 같은 단일 통합 Control Plane 또는 완성형 운영 Portal이 명시되어 있지 않음

### 18. 상태를 수집하고 장애를 복구하는 계층

- DCGM: GPU 상태·진단·텔레메트리
- NVSentinel: Kubernetes 기반 GPU 모니터링·결함 복구
- Fleet Intelligence: GPU Fleet 수준의 상태 가시성
- OTel/Prometheus 등으로 애플리케이션·인프라·네트워크 신호를 통합 가능

### 19. 세 종류의 고속 네트워크를 따로 이해

- Ethernet: NVUE/Cumulus, NetQ
- InfiniBand: UFM
- NVLink/NVSwitch: NMX-C, NMX-T, NMX-M, NMX Oasis
- NMX는 NVLink Scale-up Network 전용 관리 계층이며 일반 네트워크 관리도구와 구분

### 20. DSX Exchange — IT와 OT를 연결하는 통신 허브

- NATS 기반 Event Bus
- BMS 친화적인 MQTT 3.1.1 연결
- AsyncAPI 기반 Topic/Payload 계약
- 인증·권한 및 클러스터 간 연계
- “모든 시스템을 대체하는 통합 DB”가 아니라 실시간 신호 교환과 데이터 계약 계층

### 21. MaxLPS — 제한된 전력에서 더 많은 AI 처리

- 45°C Cooling
- Dynamic Power Software
- 고급 성능/와트 기법
- 목표: 고정된 전력 한도 안에서 AI Factory 처리량과 효율을 극대화
- 공개 범위가 제한된 기능은 별도 표기

### 22. DSX Flex — 전력 상황에 맞춰 AI 부하를 조정

- 전력망 부하 감축, 수요반응, 가격 이벤트, 재생에너지·저장장치 상태 수신
- DSX Exchange Schema를 통해 전력 목표와 위반·집행 결과 전달
- 실제 동작에는 Scheduler, 전력 소프트웨어, 시설 제어와 정책 연계 필요

### 23. 운영 Digital Twin은 3D와 2D의 결합

- 3D: 자산 위치, 열 분포, 장애 영향 범위
- 2D: GPU 사용률, 알람, 시계열, KPI, 작업 이력
- 예: 3D 랙 선택 → DCGM GPU 지표, NMX 링크 상태, Run:ai 워크로드, BMS 전력·냉각 패널 표시

### 24. 관측에서 제어까지는 단계가 있다

1. 데이터 수집·가시화
2. 상관분석·예측
3. 최적화 권고
4. 승인된 자동 제어
- 안전·책임·Fallback이 정의되지 않으면 자동제어로 넘어가지 않는다.

### 25. 누가 무엇을 준비해야 하는가

- NVIDIA: 참조 설계, Blueprint, 소프트웨어·라이브러리·인터페이스
- 고객: 목적, 운영정책, Asset ID, 시스템 원본, 보안·승인 기준
- SI/개발사: OpenUSD 파이프라인, 어댑터, 데이터 플랫폼, 운영 UI와 업무 흐름
- 시설·장비사: BMS/EPMS/DCIM 포인트, 프로토콜, 제어 가능 범위

### 26. 핵심 정리

- DSX는 단일 제품이 아니라 AI Factory 전 생애주기 체계다.
- 설계 단계의 Digital Twin을 운영 단계까지 이어가려면 ID·데이터 계약이 먼저 준비되어야 한다.
- NVIDIA의 구성요소를 조합하되 실제 운영 애플리케이션과 외부 설비 연계는 프로젝트로 완성한다.

---

# 2. 세부 컴포넌트 가이드 PDF 원고

## 문서 정의

- 가제: `DSX Component Guide 2026.08`
- 예상 분량: 36~40페이지
- 독자: 아키텍트, 인프라·네트워크·시설 엔지니어, SI, 기술 검토자
- 목표: 각 컴포넌트의 정확한 위치, 역할, 실행 위치, 연결 대상, 테넌시 조건과 오해하기 쉬운 경계를 빠르게 찾을 수 있게 한다.

## 컴포넌트 설명 카드 형식

각 구성요소는 가능한 범위에서 다음 항목을 동일하게 적용한다.

1. 무엇인가
2. 어느 계층에 속하는가
3. 어디에서 실행되는가
4. 무엇을 관측하거나 제어하는가
5. 주요 입력/출력 또는 API
6. 앞뒤로 연결되는 구성요소
7. 단일/멀티테넌시 적용 관점
8. 혼동하면 안 되는 구성요소
9. 설치·라이선스·공개 범위
10. 공식 근거

## 페이지별 구성

### 1. 표지

### 2. 문서 사용법과 정보 등급

- 공식 DSX 상위 기능, NVIDIA 제품, 오픈소스, 표준, 외부 시스템, 프로젝트 개발 영역 구분
- 현재 공개 문서에 없는 기능을 확정 제품처럼 표현하지 않는 원칙

### 3. DSX 전체 구조

- Sim / OS / MaxLPS / Exchange / Flex / Hardware / Facilities / Reference Designs
- “제품 BOM”과 “기능 체계”를 구분

### 4. AI Factory 생애주기와 데이터 흐름

- 설계 → 시뮬레이션 → 시공·시운전 → 운영 → 최적화
- 설계 자산과 운영 자산을 Asset ID로 연결

### 5. DSX Sim 개요

- Logical Infrastructure Simulation
- AI Factory Digital Twin
- SimReady Assets
- 구축 전/구축 후 사용 범위

### 6. OpenUSD와 SimReady Asset Pipeline

- CAD/BIM/PLM → Geometry Creation/Validation → Metadata Enrichment/Validation → SimReady OpenUSD Asset
- 전기, 열·냉각, 연결점, 형상 규격
- PLM/자산 저장소를 권위 원본으로 두는 관점

### 7. AI Factory Digital Twin Pipeline Samples

- 샘플 스크립트·Preset의 역할
- CAD ingestion, optimization, validation, metadata workflow
- 샘플과 실제 기업용 자산 파이프라인의 차이

### 8. DSX Air

- 논리 인프라 시뮬레이션
- GPU/SuperNIC/DPU/Switch 및 파트너 연계 검증
- 물리 CFD/전기 Solver와의 차이

### 9. 물리 Solver 연계

- Thermal/CFD, Electrical, Grid, Site
- Omniverse가 장면·결과 문맥을 제공하고 Solver가 계산을 수행하는 구조
- 도메인별 결과를 동일한 자산 ID에 연결

### 10. Surrogate Model과 PhysicsNeMo

- 사전 레이아웃 시뮬레이션에서 물리 예측 능력은 필수
- 고정밀 CFD Solver → 학습/검증 Dataset → PhysicsNeMo 기반 Surrogate Model → Inference API → Omniverse의 흐름
- 랙 배치, 형상, 열 부하 변화에 따른 온도·유속·압력 분포 예측
- PhysicsNeMo는 DSX의 빠른 Physics AI 예측을 구현하는 NVIDIA 권장 경로
- 모델 정확도, 적용 가능한 설계 범위, Solver 대비 오차, 재학습 기준 필요

### 11. Omniverse AIF-DT Runtime

- AIF-DT Application Logic
- Kit
- App Streaming API/WebRTC
- Simulation Data Delegate
- AI Agent
- Data Lake Database
- USD Storage API

### 12. DSX Blueprint의 공개 범위와 프로젝트화 조건

- 공개 Blueprint: 개발자용 참조 프레임워크·예제 장면·샘플 UI
- 실제 운영: 실데이터 Adapter, 인증/RBAC, 시계열 저장, 알람, 업무 흐름, 운영 KPI 개발 필요
- 샘플 KPI 또는 화면을 실제 제품 기능으로 오인하지 않도록 명시

### 13. DSX OS 전체 계층

- 공식 DSX Platform Software: KAI Scheduler, Run:ai, NVCF, Grove, Dynamo
- 공식 DSX Infrastructure Software: GPU Operator, Network Operator, AICR, NVSentinel, Fleet Intelligence, NICo, DPF, Switch Infrastructure Config Manager
- 현재 DSX 최상위 공개 문서에 이름이 명시된 구성만 Official DSX OS Component로 표시
- Mission Control, BCM, DCGM은 이 그림 안에 넣지 않고 다음 장의 자체 구축 연계 제품으로 분리
- DSX OS의 `OS`는 단일 설치형 운영체제나 통합 관리 제품이 아니라, AI Factory 운영 기능을 조합하는 모듈형 Software Portfolio를 의미한다고 설명
- DSX OS 모듈형 경로를 선택한 경우에만 Portal, Inventory/CMDB, Observability Backend, Break-Fix, IT/OT 제어 연계를 조합해야 함
- DGX/Enterprise 경로에서는 Mission Control/BCM이 통합 운영 기반을 제공하며 DSX OS 모듈은 필요에 따라 보완적으로 결합

### 14. KAI Scheduler

- Kubernetes-native AI Scheduler
- Topology-aware Placement, Resource Allocation
- Run:ai 및 Kubernetes 기본 Scheduler와의 관계는 배치 구조에 따라 결정

### 15. Run:ai

- Kubernetes 위의 GPU/AI Workload Orchestration
- Project/Department, Quota, Queue, Scheduling, GPU Sharing
- GPU Health 원천은 DCGM 계열과 구분
- 운영 Twin에는 “누가 어떤 작업에 GPU를 사용 중인가”라는 업무 문맥 제공

### 16. NVCF, Grove, Dynamo

- NVCF: Kubernetes Backend에 AI/Simulation 서비스를 API로 배포·확장
- Grove: 다중 컴포넌트 추론 워크로드를 Kubernetes API로 정의·확장
- Dynamo: 다중 노드 분산 추론 Serving Framework
- 세 구성요소의 서비스 오케스트레이션/실행 역할 구분

### 17. Slurm, NIM, NeMo

- Slurm: 장시간·대규모 학습에 사용되는 HPC Workload Manager
- NIM: 모델 추론 Microservice
- NeMo Microservices: 모델 커스터마이징 Workflow
- DSX를 구성할 때 선택되는 AI Platform 계층의 예

### 18. GPU Operator와 Container Toolkit

- GPU Driver, Device Plugin, Container Toolkit, Node Label, DCGM 기반 모니터링 배포 자동화
- Kubernetes에 GPU 사용 기반을 제공
- GPU Operator 자체가 워크로드 관리 플랫폼은 아님

### 19. Network Operator, DPU Operator, DPF/DOCA/HBN

- Network Operator: RDMA, SR-IOV, Driver 등 Kubernetes 네트워크 자원 구성
- DPU Operator/DPF: BlueField DPU 수명주기 및 인프라 서비스 오케스트레이션
- DOCA/HBN: DPU에서 Tenant Network 격리와 Overlay Offload

### 20. AI Cluster Runtime과 Switch Infrastructure Config Manager

- AICR: NVIDIA 가속 Kubernetes Runtime의 검증된 정의
- Switch Config Manager: 대규모 데이터센터 스위치 구성 자동화·인벤토리 관리
- 제품 설치물과 검증 Recipe/정의의 구분

### 21. DCGM과 DCGM Exporter

- DCGM: GPU Monitoring, Diagnostics, Health, Telemetry
- DCGM Exporter: Prometheus 형식의 GPU Metric 노출
- GPU 사용률, 온도, 전력, 오류, NVLink 관련 지표
- Run:ai의 업무/스케줄링 문맥과 구분

### 22. NVSentinel과 Fleet Intelligence

- NVSentinel: Kubernetes-native GPU Fault Detection/Remediation
- Fleet Intelligence: Agent 기반 GPU Fleet Health/Integrity 가시성
- DCGM 데이터 수집, 결함 판단, 복구 Workflow의 계층 차이

### 23. DSX 외부의 자체 구축 NVIDIA 운영 Stack

> 아래 구성은 NVIDIA의 공식 DGX/Mission Control/BCM 제품 구조이지만, 현재 공개 DSX Architecture가 이들을 DSX OS 구성요소로 직접 명시한 것은 아니다. DSX 공식도와 구분된 `구축 예시`로만 사용한다.

| 항목 | 주 적용 위치 | 핵심 역할 |
|---|---|---|
| NVIDIA Mission Control | DGX B200/B300 및 NVIDIA/DGX GB200/GB300 NVL72 | AI Factory 통합 운영, Provisioning, Workload, Telemetry, Recovery, Power/Cooling/BMS 연계 |
| BCM | Mission Control의 핵심 Cluster Management 또는 독립 AI/HPC Cluster | PXE/OS Provisioning, Slurm·K8s 배포, Workload/Infrastructure Monitoring |
| DCGM | GPU가 설치된 각 Compute Node와 중앙 Observability 연계 | GPU Inventory, Telemetry, Health, Diagnostics, Profiling, Workload Accounting |

- Mission Control은 자체 제품 구조 안에서 BCM 기술을 기반으로 Run:ai, DCGM/DCGM Exporter, NMX/UFM/NetQ, Prometheus/Grafana, Autonomous Recovery 등을 통합
- BCM은 Mission Control에 포함되는 핵심 구성인 동시에, 별도 AI/HPC Cluster Manager로도 제공됨
- DSX와 연결할 때에는 Digital Twin의 운영 데이터 Source/API로 연계되는 관계만 표현하고 DSX 내부 포함 관계로 그리지 않음
- NICo는 공식 DSX OS에 명시되어 있으나, 자체 구축안에서 실제 채택할지는 운영·테넌시 요구에 따라 별도 판단

### 24. Virtualization과 vGPU

- Hypervisor는 생태계 구성요소
- NVIDIA vGPU Manager와 Guest Driver
- VM 기반 멀티테넌시에서 GPU 공유·격리
- BCM의 VM 직접 Provisioning 한계와 관리 Domain 연결 방식

### 25. Ethernet 관리 — Cumulus Linux, NVUE, NetQ

- Cumulus Linux: Spectrum Switch OS
- NVUE: Switch별 Schema/API/CLI 기반 구성
- NetQ: Fabric Telemetry, Validation, Troubleshooting, Snapshot/Compare

### 26. InfiniBand 관리 — UFM

- 중앙 Fabric Monitoring/Management
- Health, Congestion, Tenant Isolation, Telemetry
- Ethernet/NetQ 및 NVLink/NMX와 구분

### 27. NVLink 관리 — NMX

| 구성 | 실행 위치 | 역할 |
|---|---|---|
| NMX-C | 각 NVLink Switch Tray | 개별 NVSwitch Program/Control |
| NMX-T | 각 NVLink Switch Tray | NVLink Switch Telemetry 수집 |
| NMX-M | 중앙 Control Plane | 다수 Rack의 NVLink Domain 통합 관리·Partition 연계 |
| NMX Oasis | 중앙 | API Gateway, ETL, Dashboard |

- IMEX, Mission Control/BCM과 NMX-M의 연계
- NVLink Scale-up Network 전용 관리라는 점 강조

### 28. Storage 경로 — GDS와 GDR

- GPUDirect Storage: Storage와 GPU Memory 간 Direct Data Path
- GPUDirect RDMA: Network Device와 GPU Memory 간 Direct Data Path
- Storage Management Product가 아니라 데이터 경로 기술이라는 점 구분

### 29. Telemetry와 Observability Architecture

- Source: Application, System/GPU, Network, Facility
- Collector: OTel Agent/Gateway, DCGM Exporter, gNMI/OpenConfig, Facility Adapter
- Hot Store: Prometheus/Loki/Tempo 등
- Cold Store: Telemetry Data Lake/Object Storage
- Correlation Key: Timestamp, Resource ID, Trace ID, Tenant/Service ID

### 30. Break-Fix Architecture

- Health Check → Detection → Cordon/Drain → Diagnostics/Repair → Validation → Return to Service
- DCGM, Mission Control/BCM, Autonomous Recovery, Scheduler의 역할 분리
- 자동 복구는 관측 화면과 별도의 제어 Workflow

### 31. DSX Exchange

- Event Bus: NATS, MQTT 3.1.1, JetStream, HA/Federation
- AsyncAPI Schema: Topic/Payload Contract
- Auth-Callout: OAuth2/mTLS/NKey, Topic ACL
- Agent Gateway: Operator/Tenant Agent의 DSX MCP 진입점
- Common Services Cluster와 Control Plane Cluster의 연계 개념

### 32. BMS/EPMS/DCIM Integration

- BMS 내부 포인트 이름을 그대로 표준이라고 가정하지 않음
- Adapter에서 DSX Exchange Topic/Payload 계약으로 변환
- Protocol 예: MQTT, BACnet, Modbus, OPC UA 등은 현장 설비와 Gateway에 따라 결정
- 제어 Command는 안전 인터록, 권한, 승인, 감사 로그를 별도로 설계

### 33. MaxLPS와 Dynamic Power Software

- 칩·열·시스템·소프트웨어를 포함한 성능/와트 기술 체계
- 고정된 Site/Rack Power Envelope 안에서 부하 배분
- 45°C Cooling, Dynamic Power Software, Advanced Perf/Watt
- 일부 문서·파일럿은 승인된 초기 참여 또는 NVOnline 범위임을 표기

### 34. DSX Flex

- Grid/On-site Generation/Renewables/Storage Signal
- Load Target, Power State, Breach Alert, Enforcement Outcome Schema
- DSX Exchange → Scheduler/Power Software/Facility Controller 연계
- Flex Schema 자체와 실제 제어 엔진을 구분

### 35. 운영 Digital Twin 데이터 아키텍처

- Geometry/Relationship: OpenUSD, USD Storage
- Operational State: Time-series/Telemetry Store
- Business/Workload Context: Run:ai, Scheduler, CMDB/ITSM
- Facility State: BMS/EPMS/DCIM
- Event/Command: DSX Exchange
- Visualization: Omniverse Kit + 2D Web UI

### 36. System of Record와 Asset ID

- 설계 형상 원본, 운영 자산 원본, 시계열 원본, Work Order 원본을 구분
- Digital Twin은 모든 원본을 복제하는 시스템이 아니라 ID와 관계를 연결하는 소비·통합 계층
- Asset ID, Telemetry Tag, Protocol, Unit, Timestamp, Quality, Ownership 정의

### 37. 보안·테넌시·책임 경계

- Operator / Tenant / Facility Operator / SI
- IT/OT Network Boundary
- RBAC, Topic ACL, Certificate, Secret, Audit
- 자체 구축 Cluster 운영과 Cloud Provider형 NCP Bare Metal 구조를 같은 그림으로 일반화하지 않음

### 38. 컴포넌트 선택표

- 요구사항별 필수·선택·외부·개발 영역을 표로 정리
- 예: `GPU 관측 → DCGM`, `NVLink 관리 → NMX`, `InfiniBand → UFM`, `AI 업무 자원 → Run:ai`, `시설 데이터 → BMS Adapter + Exchange`

### 39. 오해하기 쉬운 표현 정리

- DSX = 단일 설치 패키지: 아님
- Omniverse = 모든 운영 제어 시스템: 아님
- PhysicsNeMo/Surrogate Model = 단순 부가 시각화: 아님. 발열 예측과 반복 레이아웃 검증을 위한 권장 핵심 구성
- Run:ai = GPU Hardware Telemetry 원천: 아님
- DCGM = Workload/Quota Manager: 아님
- NMX = 일반 Ethernet/InfiniBand Manager: 아님
- Exchange = Data Lake/DCIM 대체: 아님
- Blueprint Demo 화면 = 완성된 상용 운영 UI: 아님

### 40. 공식 자료와 용어집

- 공식 URL, 자료 기준일, 공개 범위
- Official DSX: DSX OS, AIF-DT, OpenUSD, SimReady, MaxLPS, Flex, Exchange 등
- Adjacent NVIDIA Products: Mission Control, BCM, DCGM, NMX, UFM, NetQ 등

---

# 3. DSX·Omniverse 도입 가이드 슬라이드 원고

## 문서 정의

- 가제: `DSX & Omniverse Adoption Guide 2026.08`
- 예상 분량: 32장
- 독자: DSX/Omniverse 도입을 검토하는 고객, SI, 설계·시공·운영 파트너, 기술 의사결정자
- 목표: 무엇을 사거나 설치하는지보다, **무엇을 준비하고 누가 어떤 결과물을 만들어야 실제 도입이 가능한지** 설명한다.

## 전체 논리

`목표 정의 → 설계 기준선 → 사전 시뮬레이션 → 운영 통합 설계 → 시공·시운전 → 운영 애플리케이션 → 최적화·제어 → 책임과 단계적 도입`

## 슬라이드별 원고

### 1. 표지 — DSX & Omniverse Adoption Guide

- 부제: AI Factory Digital Twin을 설계에서 운영까지 연결하는 구축 방법

### 2. 이 문서가 답할 질문

- NVIDIA가 제공하는 것은 무엇인가
- 고객과 SI가 준비·개발해야 하는 것은 무엇인가
- 언제 어떤 데이터를 정의해야 하는가
- PoC와 운영 시스템의 경계는 어디인가

### 3. 목표 시스템의 모습

- 설계 모델과 운영 자산이 같은 ID로 연결됨
- 물리·논리 시뮬레이션 결과와 실측값 비교 가능
- GPU·네트워크·시설·워크로드 상태를 한 문맥에서 분석
- 필요 시 전력·워크로드 최적화 제어로 연결

### 4. DSX는 구매 가능한 단일 패키지가 아니다

- Reference Design + Product + Open Source + Interface + External System + Project Development
- 도입 계약과 Work Package를 이 구분에 맞춰 정의해야 함
- `NVIDIA 공식 DSX Architecture`와 `자체 구축 Reference Implementation`을 별도 그림으로 제시
- 공식 DSX 그림에는 NVIDIA가 DSX 페이지에 직접 명시한 항목만 포함하고, Mission Control/BCM/DCGM은 연계 제품 Lane에 배치
- 구축 경로 A — DGX/Enterprise 자체 구축: Mission Control + BCM을 운영 기반으로 사용하고 필요한 DSX 기술을 연계
- 구축 경로 B — Cloud Provider/Partner형 멀티테넌트 Platform: NICo, AICR, Operator, KAI/Run:ai, NVSentinel 등 DSX OS 모듈을 조합
- 두 경로는 후속/대체 관계가 아니라 대상 고객과 운영 모델이 다른 병렬 경로

### 5. 전체 권장 구축 흐름

```text
설계 기준선
CAD/BIM/PLM → SimReady OpenUSD → AI Factory Digital Twin
                         │
                  사전 시뮬레이션
     DSX Air + CFD/전기 Solver + PhysicsNeMo 기반 Surrogate Model
                         │
             운영 통합 설계 및 시공·시운전
Asset ID · telemetry tag · protocol · data contract 검증
                         │
       운영 데이터 Source — DSX 외부/연계 제품 포함
Mission Control/BCM · DCGM · NMX/UFM/NetQ · Run:ai · BMS/EPMS/DCIM
                         │
                       통합
DSX Exchange · OTel · Adapter · Time-series/Data Lake · USD Storage
                         │
                 운영 애플리케이션
      Omniverse AIF-DT 3D + 2D Dashboard/Alert/Workflow
                         │
                    최적화·제어
       MaxLPS · Flex · Scheduler · Facility Controller
                         │
         운영 결과를 설계·모델·정책에 Feedback
```

### 6. 다섯 개 Workstream을 병렬로 관리

1. Asset/Digital Twin
2. Simulation
3. IT/OT Data Integration
4. Operations Application
5. Optimization/Control & Governance

### 7. Phase 0 — 목표와 운영 시나리오 정의

- 해결할 운영 문제를 먼저 선택
- 예: 열 이상 조기 탐지, 전력 한도 내 GPU 처리량, 장애 영향 분석, 배치안 검증
- “전체 데이터센터 관제”처럼 범위가 무한한 목표를 피하고 성공 지표를 정의

### 8. Phase 0 — 이해관계자와 권위 원본 정의

- 설계: BIM/PLM
- 운영 자산: CMDB/EAM/DCIM
- 시설 상태: BMS/EPMS
- GPU/Cluster: NVIDIA Mission Control/BCM, DCGM
- Workload: Run:ai/Kubernetes/Slurm
- 각 데이터의 Owner, 갱신 책임, 보존기간 정의

### 9. Phase 1 — 설계 기준선 수집

- Site, Building, Hall, Row, Rack, Server, Network, Power, Cooling 자산 범위
- LOD, 좌표계, 단위, Naming, Version Rule
- 벤더 CAD 반입과 보안·IP 조건

### 10. Phase 1 — CAD/BIM을 OpenUSD로 변환

- Geometry 최적화
- Assembly/Variant/Payload 구조
- 내부 형상과 외부 형상의 선택적 로딩
- Validation 및 Version 관리

### 11. Phase 1 — SimReady Metadata

- Power/Electrical
- Thermal/Cooling
- Connection Point
- Asset Identity와 Operating Limit
- 도식: `형상 + 의미 + 연결점 = SimReady Asset`

### 12. Phase 1 — Asset ID를 운영까지 가져가기

- 설계 ID와 설치 후 Serial/Location/Tag를 Mapping
- 교체·이동·증설 시 관계 갱신 Rule
- Telemetry와 Work Order가 동일 자산을 가리키도록 정의

### 13. Phase 2 — 시뮬레이션 계획

- 질문, 입력, Solver, 결과, 검증 기준을 Domain별로 정의
- Network / Thermal / Electrical / Grid / Site
- 시뮬레이션 자체가 목적이 아니라 설계 의사결정 기준을 만드는 것이 목적

### 14. Phase 2 — DSX Air 논리 인프라 검증

- 네트워크 Topology, Configuration, Deployment Procedure
- GPU/DPU/SuperNIC/Switch와 파트너 솔루션 연계
- 산출물: 검증된 구성, 자동화 Script, Test Case, 예외 목록

### 15. Phase 2 — 물리 Solver 연계

- Thermal/CFD: 공기·액체 냉각, Hot Spot, Failure Scenario
- Electrical: Load Flow, Failure, Protection/Capacity
- Grid/Site: Site Constraint와 전력 공급 조건
- 결과를 OpenUSD 자산·공간과 연결

### 16. Phase 2 — PhysicsNeMo 기반 빠른 발열 예측

- 고정밀 CFD 결과를 학습·검증 데이터로 사용해 PhysicsNeMo 기반 Surrogate Model 구성
- 랙 배치, 형상, 열 부하 변화에 따른 온도·유속·압력 분포를 빠르게 예측
- AIF-DT가 Inference API를 호출하고 Omniverse 3D 장면에 결과를 Overlay
- 반복 설계와 운영 what-if를 목표로 하는 DSX Digital Twin의 권장 핵심 경로
- 학습 데이터 범위, Solver 대비 오차, 적용 가능 조건과 재학습 기준을 인수 항목으로 정의

### 17. Phase 2 — 설계 기준선 승인

- Simulation 결과와 설계 변경사항을 Versioned Baseline으로 승인
- 운영 단계에서 실측값과 비교할 기준값을 보존
- Acceptance Criteria와 책임자 지정

### 18. Phase 3 — 운영 통합 설계를 시공 전에 시작

- Asset ID
- Telemetry Tag/Unit/Quality
- Protocol/Network Zone
- Topic/Payload/Data Contract
- Sampling/Retention/Latency
- 이 항목을 시운전 시점에 처음 정의하면 비용과 재작업이 커짐

### 19. Phase 3 — 운영 데이터 Source Map

| 영역 | 대표 Source | 제공 문맥 |
|---|---|---|
| GPU | DCGM/DCGM Exporter | Health, Temp, Power, Utilization, Error |
| Cluster | Mission Control/BCM | Inventory, Provisioning, Lifecycle, Rack/System State, Recovery |
| NVLink | NMX | NVSwitch/NVLink Health, Telemetry, Partition |
| InfiniBand | UFM | Fabric Health, Congestion, Isolation |
| Ethernet | NVUE/NetQ | Configuration, Telemetry, Validation |
| Workload | Run:ai/K8s/Slurm | Job, Project, Quota, Placement, Allocation |
| Facility | BMS/EPMS/DCIM | Power, Cooling, Environment, Asset/Capacity |

### 20. Phase 3 — DSX Exchange와 Adapter

- BMS/OT의 현장 Protocol·Tag를 표준 Topic/Payload로 변환
- NATS/MQTT Event Bus와 AsyncAPI Data Contract
- OTel은 Logs/Metrics/Traces 통합에 사용
- Event Streaming과 장기 Data Lake의 역할을 구분

### 21. Phase 3 — 데이터 저장 구조

- USD Storage: 형상·관계·장면 Version
- Time-series/Observability Store: 실시간 Metric, Log, Trace
- Data Lake: 장기 분석, Simulation 결과, 학습 데이터
- CMDB/EAM/ITSM: 운영 자산과 작업 원본
- 같은 데이터를 무조건 복제하지 않고 Link/Cache/Derived Data 정책 수립

### 22. Phase 3 — 보안과 IT/OT 경계

- OT-to-IT Gateway, Network Segmentation
- Certificate/mTLS, OAuth2/NKey, Topic ACL
- Operator/Tenant/Facility 역할별 RBAC
- Command와 Telemetry Channel 분리
- 감사 로그와 비상 수동 운전 경로

### 23. Phase 4 — 시공·시운전 검증

- 설치 자산과 Digital Twin 자산 Mapping
- Sensor/Tag/Unit/Timestamp/Quality 검증
- Network Path와 API Endpoint 검증
- 실측값과 Simulation Baseline 비교
- 운영 인수 기준에 데이터 연계 항목 포함

### 24. Phase 5 — 운영 애플리케이션 구조

- Omniverse Kit/AIF-DT 3D
- 2D Dashboard, Trend, Alarm, Work Order
- API/Simulation Data Delegate
- Data Lake/Time-series/USD Storage
- App Streaming/WebRTC Viewer

### 25. Phase 5 — 3D와 2D의 역할 분담

- 3D: 위치·영향·관계·분포
- 2D: 숫자·시간·우선순위·업무 처리
- 사용자별 View: NOC, Facility, AI Infra, Management

### 26. Phase 5 — 대표 운영 시나리오

예: 랙 온도 이상

1. BMS 온도·유량 이상 수신
2. 3D에서 영향 Rack/CDU/배관 표시
3. DCGM GPU 온도·전력과 Workload 확인
4. NMX/Network 상태와 장애 상관 분석
5. 조치 권고 또는 Scheduler/Facility Controller에 승인된 명령

### 27. Phase 6 — 관측 → 권고 → 제어 성숙도

- Level 1: 통합 가시화
- Level 2: 상관분석·알람
- Level 3: 예측·최적화 권고
- Level 4: Human-in-the-loop 제어
- Level 5: 정책 기반 자동제어

### 28. Phase 6 — MaxLPS/Flex 제어 Loop

- Grid/BMS Power Signal
- DSX Exchange
- Dynamic Power Software / Scheduler / Facility Controller
- Workload 조정 또는 Power/Cooling Setpoint 조정
- DCGM/BMS 실측으로 결과 확인
- 실패 시 Safe State와 Rollback

### 29. 책임 분담

| 작업 | NVIDIA | 고객 | SI/개발사 | 시설·장비사 |
|---|---|---|---|---|
| Reference Design/Blueprint | 제공 | 검토 | 적용·확장 | 사양 제공 |
| Asset/ID 기준 | 지침·Sample | 승인·Owner | 모델·Mapping 구현 | 장비 데이터 제공 |
| Solver | 연계 기반 | 기준 승인 | Workflow 통합 | 도메인 모델 제공 |
| NVIDIA SW | 제품·문서 | 라이선스·운영정책 | 설치·통합 | - |
| BMS/EPMS/DCIM | Schema/Exchange | 시스템·권한 제공 | Adapter 개발 | Tag/Protocol/Control 제공 |
| 운영 UI | Blueprint | 요구사항·인수 | 3D/2D 앱 개발 | 운영 Workflow 협의 |
| 자동제어 | 일부 기술 | 최종 책임·승인 | 정책·연계 개발 | Safety/Interlock 책임 |

### 30. 권장 PoC 범위

- Hall/Row 일부와 대표 Rack/CDU/Power Asset
- GPU·전력·냉각 각 1개 이상의 실제 데이터 Source
- 1개의 사전 Simulation Scenario
- 1개의 운영 장애/최적화 Scenario
- 3D + 2D 화면, Asset ID Mapping, 데이터 지연·정확도 검증
- 자동제어는 초기에는 Simulation 또는 Human Approval 수준 권장

### 31. 단계적 Rollout

1. Offline Design Twin
2. Read-only Operational Twin
3. Alert/Correlation
4. Recommendation
5. Controlled Automation
6. Multi-site Optimization

### 32. 착수 전 확인할 핵심 질문

- 해결할 운영 문제와 성공 지표는 무엇인가
- 어느 시스템이 자산·상태·작업의 권위 원본인가
- 필요한 NVIDIA 제품과 공개/제한 자료는 무엇인가
- 시설 Vendor가 제공할 Tag, Protocol, 제어 범위는 무엇인가
- 누가 운영 애플리케이션과 Adapter를 소유·유지보수하는가
- 자동제어의 승인, 안전, 책임 경계는 어디인가

---

# 4. 공통 컴포넌트 목록 및 문서별 설명 깊이

| 컴포넌트/영역 | 분류 | 초보자 슬라이드 | 상세 PDF | 도입 슬라이드 |
|---|---|---|---|---|
| DSX Sim | DSX Capability | 정의·두 역할 | 하위 구조·연결 | 설계/시뮬레이션 Workstream |
| DSX Air | NVIDIA/DSX Capability | 논리 시뮬레이션 | 대상·산출물·경계 | 검증 절차와 산출물 |
| Omniverse DSX Blueprint/AIF-DT | NVIDIA Blueprint | 3D DT 기반 | Runtime 구성·공개 한계 | 운영 앱 개발 범위 |
| OpenUSD | Interface/Standard | 공통 3D 기반 | Layer/Assembly/Version 관점 | 설계 기준선과 System of Record |
| SimReady | NVIDIA Specification/Pipeline | 계산 가능한 자산 | Geometry·Metadata·Validation | Asset 공급·검수 Workflow |
| CFD/Electrical/Grid/Site Solver | External System | 물리 계산 | Domain 연결·I/O | Simulation Work Package |
| Surrogate Model | Architecture Pattern | 발열 예측·빠른 반복 검증 | API·오차·재학습·Solver 연계 | 사전 설계·운영 what-if 핵심 Work Package |
| PhysicsNeMo | NVIDIA Open Source Framework | 권장 Physics AI 구현 | 열·유동 Surrogate 학습·추론 | DSX Blueprint 권장 구현 경로 |
| DSX OS | DSX Capability | 플랫폼/인프라 SW | 계층·테넌시·컴포넌트 | 배치·운영 책임 |
| KAI Scheduler | NVIDIA Open Source | AI Scheduler | Topology-aware Scheduling | K8s 배치 선택 |
| Run:ai | NVIDIA Product | GPU/Workload 관리 | Quota/Queue/Sharing/Metric 경계 | Workload 문맥·API 연계 |
| NVCF | NVIDIA Product/Service | API 서비스화 | Cluster Agent/Backend | Simulation/AI Service 배포 선택 |
| Grove/Dynamo | NVIDIA Open Source | 분산 추론 | 정의/Serving 역할 | 추론 플랫폼 범위일 때 적용 |
| Slurm | Open Source/Ecosystem | 학습 Job Scheduler | 전용 Cluster 적용 | BCM/운영 정책과 연계 |
| NIM/NeMo | NVIDIA Product | AI 서비스 | Inference/Customization | AI Agent/서비스 범위 시 적용 |
| GPU Operator | NVIDIA Open Source/Product Terms | K8s GPU 기반 | Driver/Toolkit/DCGM 구성 | Cluster Runtime 구축 |
| Network/DPU Operator | NVIDIA Software | K8s 네트워크/DPU | RDMA/SR-IOV/DPU Lifecycle | 격리·네트워크 구축 |
| AICR | NVIDIA Open Source/Reference | 검증 런타임 | 구성·범위 | Production Platform 기준 |
| DCGM/DCGM Exporter | NVIDIA Product / DSX Adjacent | GPU 상태 수집 | Health/Diag/Metric/Prometheus | DSX 외부 운영 Source로 Metric·Asset Mapping |
| NVSentinel | NVIDIA Open Source | GPU 결함 복구 | Detection/Remediation | Break-Fix Workflow |
| Fleet Intelligence | NVIDIA Managed/Product | Fleet 상태 | Agent/가시성 경계 | 운영 서비스 선택 |
| Mission Control | NVIDIA Product / DSX Adjacent | 자체 구축 AI Factory 통합 운영 | BCM·DCGM·Workload·Network·Recovery·Power/Cooling 연계 | 공식 DSX 내부가 아닌 별도 구축 제품 Lane |
| BCM | NVIDIA Product / DSX Adjacent | Cluster 관리 핵심 | PXE/OS/Slurm/K8s/Infrastructure Monitoring | Mission Control 포함 또는 독립 Cluster Manager; 공식 DSX 내부로 표기하지 않음 |
| NICo | NVIDIA Open Source / Official DSX OS | 멀티테넌트 Bare Metal | DPU 격리/API/Lifecycle | 공식 DSX OS 구성이나 자체 구축 채택 여부는 별도 판단 |
| UFM | NVIDIA Product | InfiniBand 관리 | Health/Congestion/Isolation | Fabric 연계 |
| NVUE/Cumulus | NVIDIA Product | Ethernet 구성 | Switch API/CLI/OS | 구성 자동화 |
| NetQ | NVIDIA Product | Ethernet 가시성 | Telemetry/Validation | NOC 연계 |
| NMX-C/T/M/Oasis | NVIDIA Product | NVLink 관리 | 실행 위치·API·Telemetry | NVLink 연계·Asset Mapping |
| DPF/DOCA/HBN | NVIDIA Software | DPU 기반 격리 | Overlay/Offload/서비스 | 멀티테넌시 설계 |
| GDS/GDR | NVIDIA Technology | 고속 데이터 경로 | Storage/Network Direct Path | 성능 요구 시 적용 |
| DSX Exchange | NVIDIA Open Source/DSX Capability | IT/OT 허브 | NATS/MQTT/AsyncAPI/Auth | Integration Workstream |
| Agent Gateway | NVIDIA Open Source | AI Agent 진입점 | Operator/Tenant Agent·MCP | Agent 범위 시 보안 설계 |
| MaxLPS/Dynamic Power Software | DSX Capability/Restricted | 전력 내 성능 | 기능·공개 범위 | Pilot/제어 Loop |
| DSX Flex | DSX Capability/Schema | 전력 오케스트레이션 | 메시지·연계 경계 | Grid/Scheduler Workstream |
| BMS/EPMS/DCIM | External System | 시설 데이터 | 역할·프로토콜·Adapter | Vendor 책임·인수 기준 |
| OTel/Prometheus/Grafana | Standard/Open Source | 통합 관측 | Pipeline/Store/시각화 | 운영 데이터 플랫폼 |
| Time-series/Data Lake | External/Project | 저장 기반 | Hot/Cold Data | 용량·보존·책임 |
| CMDB/EAM/ITSM | External System | 운영 원본 | ID/Work Order | System of Record |
| 3D+2D 운영 UI/Adapter | Project Development | 추가 개발 필요 | 상세 구조·경계 | 핵심 개발 산출물 |
| Scheduler/Facility Controller | External/Project | 제어 대상 | Command/Safety 경계 | 최적화·제어 Loop |

---

# 5. 세 문서 간 중복 관리 원칙

같은 컴포넌트를 세 문서에서 동일한 깊이로 반복하지 않는다.

예를 들어 DCGM은 다음처럼 나눈다.

- 초보자 슬라이드: “GPU의 상태와 전력·온도·사용률을 수집하는 기반”
- 상세 PDF: DCGM, DCGM Exporter, 지표, 배치 위치, Prometheus/OTel 연계, Run:ai와의 차이
- 도입 슬라이드: 어떤 지표를 수집하고 Rack/Server/GPU Asset ID와 어떻게 매핑하며 운영 화면에서 어떻게 소비할지

BCM도 같은 방식으로 나눈다.

- 초보자 슬라이드: 전용 Cluster의 Provisioning과 Workload/Infrastructure 관리 선택지
- 상세 PDF: Mission Control 안의 BCM 역할, 독립 BCM 구성, PXE/OS, Slurm/K8s, DCGM·NMX 연계
- 도입 슬라이드: 대상 NVIDIA 시스템과 운영 모델에 따라 Mission Control/BCM 구성을 정하고 Inventory/State API를 통합하는 방법

---

# 6. 1차 검토 시 중점 확인 항목

1. 초보자 슬라이드 26장의 흐름이 너무 길거나 기술적으로 깊지 않은가
2. DSX Sim의 구축 후 역할을 어느 수준까지 강조할 것인가
3. 공식 DSX Architecture와 Mission Control·BCM·DCGM 기반 자체 구축 운영 Stack의 경계를 오해 없이 분리했는가
4. NMX를 초보자 문서에 어느 수준까지 보여줄 것인가
5. 상세 PDF에서 NVCF/Grove/Dynamo/NIM/NeMo의 비중을 줄이거나 늘릴 필요가 있는가
6. 운영 Digital Twin의 대표 시나리오를 열 이상 외에 전력 최적화 또는 GPU 장애로 바꿀 것인가
7. 도입 가이드의 PoC 범위를 고객 제안서 수준으로 더 구체화할 것인가
8. 최종 자료의 언어를 한글 중심으로 하되 제품명·기술명만 영문으로 유지할 것인가

---

# 7. 주요 공식 기준 자료

- [NVIDIA DSX Documentation](https://docs.nvidia.com/dsx)
- [Omniverse DSX Blueprint Overview](https://docs.omniverse.nvidia.com/dsx/latest/)
- [Omniverse DSX Blueprint System Architecture](https://docs.omniverse.nvidia.com/dsx/latest/system-architecture.html)
- [SimReady Assets for DSX Digital Twins](https://docs.omniverse.nvidia.com/dsx/latest/simready-assets.html)
- [NVIDIA DGX SuperPOD GB200 Reference Architecture — Key Components](https://docs.nvidia.com/dgx-superpod/reference-architecture-scalable-infrastructure-gb200/latest/dgx-superpod-components.html)
- [NVIDIA DGX SuperPOD GB200 Reference Architecture — Software Stack](https://docs.nvidia.com/dgx-superpod/reference-architecture-scalable-infrastructure-gb200/latest/dgx-software.html)
- [NVIDIA Mission Control Documentation](https://docs.nvidia.com/nvidia-mission-control/)
- [NVIDIA Mission Control 2.3.1 Software Bill of Materials](https://docs.nvidia.com/pdf/sbom-2-3-1.pdf)
- [NVIDIA Base Command Manager Documentation](https://docs.nvidia.com/base-command-manager/)
- [NVIDIA DCGM Documentation](https://docs.nvidia.com/datacenter/dcgm/latest/)
- [DSX Exchange Architecture](https://docs.nvidia.com/dsx-exchange/architecture)
- [DSX Exchange BMS Integration](https://docs.nvidia.com/dsx-exchange/bms-integration)
