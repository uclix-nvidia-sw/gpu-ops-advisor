# GPU Ops Advisor

GPU·Node·Pod 관측을 바탕으로 장애 원인 조사(RCA)와 운영보고서를 제공하는 서비스입니다. **현재 개발 기준은 v1.3**입니다. Frontend·Backend·Incident·Job Controller·두 Agent와 Grafana MCP 연결 코드가 있으며, 현재 구현과 시험 범위는 아래 안내 및 모듈별 QA에서 확인할 수 있습니다.

## [Architecture · Sequence 다이어그램 열기 →](output/archify/gpu-ops-advisor.html)

**전체 시스템 구성과 실제 요청 처리 순서를 한 화면에서 탐색하는 HTML 뷰어입니다.** 저장소 코드와 설계 문서를 바탕으로 Archify로 작성했으며, 상단 탭으로 구조도와 시퀀스를 전환할 수 있습니다.

- **Architecture:** CPC 수집 모듈, CSC 수신·저장 및 분석 모듈, Client를 구분하고 두 Agent·Job Controller·Grafana MCP·LLM·DB의 연결과 화살표 방향을 보여줍니다.
- **Sequence:** RCA 접수·실행, 즉시 보고서 요청·조회, 정기 보고서 접수, 보고서 실행의 다섯 시나리오에서 호출·응답과 데이터 저장·결과 공개 순서를 확인할 수 있습니다.

GitHub의 위 링크는 HTML 파일 페이지로 연결됩니다. **다이어그램을 보려면 저장소를 내려받고 `output/archify/gpu-ops-advisor.html`을 브라우저에서 여세요.** 같은 폴더의 다이어그램 HTML 파일들도 함께 유지해야 합니다. [뷰어 안내·검증 기록](output/archify/README.md) · [Sequence 코드 근거](output/archify/sequence-evidence.md)

[개발 문서 15종](output/deliverables-20260917-v1.3/00_산출물_안내.md) · [전체 구조도](output/architecture-modules-20260917-v1.3/README.md) · [문서 탐색](docs/README.md) · [변경·정리 내역](output/deliverables-20260917-v1.3/09_통합검토_반영내역.md)

[CI·릴리스 파이프라인](docs/ci-release.md) · [Helm 설치 안내 — 기본 8개 Pod](charts/gpu-ops-advisor/README.md) · [RCA·보고서 Agent](agents/README.md)

## 구조와 사용자 흐름

Agent는 **GPU Node RCA·운영보고서** 두 개의 독립 실행·배포 모듈이며 Job Controller에서 작업을 인수합니다.

| 목적 | 흐름 |
|---|---|
| RCA 자동 조사 | Grafana → Incident → Job Controller → RCA Agent |
| RCA 결과 조회 | GUI → Backend → 저장된 사건·분석 결과 |
| 즉시 보고서 | GUI → Backend → Job Controller → 보고서 Agent |
| 정기 보고서 | Backend 내부 스케줄러 → 같은 보고서 큐 → 보고서 Agent |
| 처리 용량 변경 | 운영자가 Agent 수·동시 처리 한도를 수동 조정 |

Job Controller는 큐 관리와 **기존 자원 한도 안에서 잡 배분**을 맡습니다. 처리 여유가 없으면 큐에서 대기합니다. Backend·Incident·Job Controller·RCA·보고서는 각각 독립 실행·배포합니다. 두 Agent는 **NVIDIA NeMo Agent Toolkit(NAT)** 워크플로를 내부에서 실행하며, 공통 정규화·계산 함수만 라이브러리로 재사용합니다.

- RCA: Runbook 검색·적용 조건 확인 → 필요한 사고 증거를 Grafana MCP로 조회 → 원인·권고 분석 → 결과·근거 저장.
- 보고서: Incident·공개 RCA 결과 DB + Grafana MCP의 기간 지표·로그 → 집계·계산 → 설명·보고서 저장.

Grafana MCP는 관측 조회 연결을 맡으며 최종 결과 공개는 Job Controller 완료 검증을 거칩니다. 실제 Incident·JC·Worker·공식 MCP 프로세스를 연결한 시험 기록이 있습니다. 해당 시험의 Grafana 데이터와 LLM 응답은 fixture이며 운영 환경의 데이터·모델 품질 검수와 구분합니다.

Chatbot/Assistant, GUI 직접 RCA 실행, 독립 Scheduler, HPA/자동 확장, 제품 인증·RBAC·사용자 tenant는 이번 범위에서 제외합니다. 기존 관측 저장소 접속 설정은 유지합니다.

## 현재 구현 상태

2026-09-18, 제품 코드 `775ab2f` 기준입니다. 설계 문서는 전체 기능의 구현 완료를 의미하지 않습니다.

| 범위 | 반영된 동작 | 상세·검증 |
|---|---|---|
| Backend·클러스터 등록 | 데모 seed 없이 필수 API 한도 초기화, 빈 클러스터 상태 기동, API/GUI 등록 | [Backend](backend/README.md) · [QA](backend/QA.md) |
| 사건·잡·Agent | Incident 기원의 RCA, JC 큐·claim·완료, NAT/MCP 조회 및 결과 저장 | [Incident](incident/README.md) · [JC](job-controller/README.md) · [Agent QA](agents/QA.md) |
| 보고서 수집·계산 | 대용량 응답 분할, GPU–Pod 연결 관측 수·시간과 독점 할당 구분, 부분 결과 보존 | [보고서 명세](output/deliverables-20260917-v1.3/12_보고서_Agent_모듈_설계서.md) |
| GUI·다운로드 | 서버 기반 일정·작업·결과 조회, 보고서 수치·부족 사유·수집 상태, HTML/CSV 출력 | [Frontend](frontend/README.md) · [QA](frontend/QA.md) |
| 배포 설정 | probe 분리, MCP Host 허용, 현재 실행/조회/LLM 예산 및 시작 시 설정 적용 | [운영 인계](output/deliverables-20260917-v1.3/06_배포_운영_인계서.md) · [설치](docs/helm-install.md) |

수집 데이터·할당 계약·조회 예산이 부족하면 결과는 partial/blocked가 될 수 있습니다. 잡의 succeeded와 분석 근거 충분함, LLM 설명 성공은 별개입니다. 시험 실행일·환경·범위는 각 QA를 따르며 문서 갱신이나 테스트 코드 추가를 새 시험 PASS로 간주하지 않습니다.

## 처음 읽는 순서

1. [요구사항·개발 범위](output/deliverables-20260917-v1.3/01_요구사항_개발범위_정의서.md)에서 기능과 단계별 종료 조건을 확인합니다.
2. [API](output/deliverables-20260917-v1.3/02_백엔드_API_작업명세서.md), [데이터](output/deliverables-20260917-v1.3/03_데이터_설계서.md), [모듈 간 계약](output/deliverables-20260917-v1.3/14_모듈간_호출과_공통실행_계약.md)을 맞춰 구현합니다.
3. [시험 기준](output/deliverables-20260917-v1.3/05_테스트_검수_기준서.md)과 [운영 인계](output/deliverables-20260917-v1.3/06_배포_운영_인계서.md)에 실행 증거를 남깁니다.

R01~R09/O01~O11의 업무와 기존 계산·품질 기준은 유지합니다. 수치는 코드로 계산하고 LLM은 근거 해석·설명을 맡습니다. 현재/과거 관계, 0/null, 작업 성공/분석 근거 부족/설명 실패를 구분합니다. 실제 장비 조치는 사람이 수행합니다.

## 로컬 개발 실행

PostgreSQL·JC·Backend는 저장소 루트에서 각각 별도 터미널로 실행합니다. 사전 도구와 환경 설정은 [Backend 안내](backend/README.md)를 따릅니다.

```powershell
./backend/scripts/dev-db.ps1
./job-controller/scripts/dev-server.ps1
./backend/scripts/dev-server.ps1
```

[Frontend](frontend/README.md)는 React 기반이며 `/api/v1`의 실제 Go API를 호출합니다. 별도 터미널에서 실행합니다.

```sh
cd frontend
npm ci
npm run dev
```

`/settings/backend`에서 연결 상태를 확인하고 `/settings/data`에서 실제 클러스터 라벨 ID를 등록합니다. 등록 성공이 데이터 수집 성공을 뜻하지는 않습니다. 개발 DB의 데모 seed와 운영 차트의 `seedDemoData=false` 초기화는 구분합니다.

위 명령만으로 Incident·두 Agent·Grafana MCP·LLM까지 실행되지는 않습니다. 분석 실행은 [Incident 실행 안내](incident/README.md)와 [Agent 실행 안내](agents/README.md)를 따릅니다. 전체 배포는 [Helm 설치 안내](docs/helm-install.md)를 사용합니다. 미연결 기능에 가짜 완료·결과를 생성하지 않습니다.

## 저장소와 검증

`output/deliverables-20260917-v1.3/`는 현행 개발 문서, `output/architecture-modules-20260917-v1.3/`는 확정 구조도, [docs/evidence](docs/evidence/README.md)는 수집 환경의 원문 근거입니다. 구버전 명세·중간 구조도·중복 시안·배포본은 정리했으며 Git 이력에서 확인할 수 있습니다.

```sh
python tools/check_links.py
```

이 명령은 로컬 문서·자산 경로를 검사합니다. 원격 URL 응답이나 실제 Backend·Agent 통합 검수를 대신하지 않습니다. 변경은 PR에서 목적·영향·검증·남은 작업을 확인합니다.
