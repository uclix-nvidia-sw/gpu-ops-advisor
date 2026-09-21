# GPU Ops Advisor 개발 문서 안내

현재 기준은 **GPU Ops Advisor v1.3**입니다. Job Controller는 큐와 기존 자원 내 배분을 맡고, 정기 보고서 일정·요청 생성은 Backend, 보고서 실행은 보고서 Agent가 담당합니다. RCA 요청은 Incident에서만 시작합니다. 두 Agent 내부에는 NAT 워크플로를 적용합니다. RCA는 Runbook·사고 증거·Grafana MCP를, 보고서는 Incident·공개 RCA 결과 DB와 MCP 기간 관측을 사용합니다. 상세 연결·운영·검수 기준은 03/04/05/06/11/12/14에 있습니다.

[저장소 README](../README.md) · [전체 구조도](../output/architecture-modules-20260917-v1.3/README.md) · [보존한 환경 근거](evidence/README.md)

## 팀 공통 개발 지침

- [팀 개발 역할과 협업 규칙](team-development.md): 담당 범위, 현재 main 작업·향후 PR 절차, DB 변경과 배포
- [CLAUDE.md: 영어 공통 지침](../CLAUDE.md) · [한국어 번역](CLAUDE.ko.md)
- [AGENTS.md: Agent 시작 지침](../AGENTS.md) · [한국어 번역](AGENTS.ko.md)

## 현행 개발 문서

- [00_산출물_안내](../output/deliverables-20260917-v1.3/00_산출물_안내.md)
- [01_요구사항_개발범위_정의서](../output/deliverables-20260917-v1.3/01_요구사항_개발범위_정의서.md)
- [02_백엔드_API_작업명세서](../output/deliverables-20260917-v1.3/02_백엔드_API_작업명세서.md)
- [03_데이터_설계서](../output/deliverables-20260917-v1.3/03_데이터_설계서.md)
- [04_Agent_동작_판단_명세서](../output/deliverables-20260917-v1.3/04_Agent_동작_판단_명세서.md)
- [05_테스트_검수_기준서](../output/deliverables-20260917-v1.3/05_테스트_검수_기준서.md)
- [06_배포_운영_인계서](../output/deliverables-20260917-v1.3/06_배포_운영_인계서.md)
- [07_프론트엔드_개발명세서](../output/deliverables-20260917-v1.3/07_프론트엔드_개발명세서.md)
- [08_GUI_화면설계서](../output/deliverables-20260917-v1.3/08_GUI_화면설계서.md)
- [09_통합검토_반영내역](../output/deliverables-20260917-v1.3/09_통합검토_반영내역.md)
- [10_Job_Controller_모듈_설계서](../output/deliverables-20260917-v1.3/10_Job_Controller_모듈_설계서.md)
- [11_RCA_Agent_모듈_설계서](../output/deliverables-20260917-v1.3/11_RCA_Agent_모듈_설계서.md)
- [12_보고서_Agent_모듈_설계서](../output/deliverables-20260917-v1.3/12_보고서_Agent_모듈_설계서.md)
- [13_Incident_모듈_설계서](../output/deliverables-20260917-v1.3/13_Incident_모듈_설계서.md)
- [14_모듈간_호출과_공통실행_계약](../output/deliverables-20260917-v1.3/14_모듈간_호출과_공통실행_계약.md)

## 구현 상태

현재 문서는 제품 코드 `775ab2f`의 Backend 초기화·클러스터 등록, 보고서 관측 집계·분할 조회·화면/다운로드, 운영 설정 변경을 반영했습니다. [산출물 안내](../output/deliverables-20260917-v1.3/00_산출물_안내.md)에서 구현 범위와 QA를, [반영내역](../output/deliverables-20260917-v1.3/09_통합검토_반영내역.md)에서 변경·삭제 근거를 확인합니다.

Frontend는 실제 Go API를 호출합니다. Agent의 실제 프로세스 연동 시험 기록은 있으나 Grafana 데이터·LLM 응답은 fixture를 사용했으며, 운영 환경의 분석 품질 검수와 구분합니다. 각 모듈 QA의 날짜·환경·범위를 따르고 구버전 자료를 현행 검수 결과로 사용하지 않습니다.

## 실행·배포 안내

- [Frontend](../frontend/README.md) · [Backend](../backend/README.md)
- [Incident](../incident/README.md) · [Job Controller](../job-controller/README.md) · [두 Agent](../agents/README.md)
- [Helm 설치](helm-install.md) · [기존 배포 업그레이드](helm-upgrade-existing.md) · [CI·릴리스](ci-release.md)
