# DSX GPU Operations

GPU·Node·Pod 관측을 바탕으로 장애 원인 조사(RCA)와 운영보고서를 제공하는 서비스입니다. **현재 개발 기준은 v1.3**이며, 문서가 준비된 상태입니다. Backend·Agent·DB·실환경 통합이 완료된 것은 아닙니다.

[개발 문서 15종](output/deliverables-20260917-v1.3/00_산출물_안내.md) · [전체 구조도](output/architecture-modules-20260917-v1.3/README.md) · [문서 탐색](docs/README.md) · [변경·정리 내역](output/deliverables-20260917-v1.3/09_통합검토_반영내역.md)

## 구조와 사용자 흐름

## 처음 읽는 순서

React 기반 프론트엔드는 루트의 [`frontend/`](frontend/README.md)에 있습니다. `cd frontend`, `npm ci`, `npm run dev`로 실행합니다. 7개 메뉴와 조사·보고서·일정·지식·모델 설정을 실제 Go API에 연결했습니다. 데모 저장소·가짜 완료 처리는 제거했습니다. 지식·모델·설정은 PostgreSQL에 저장하며, Agent·실시간 관측·LLM·예약 실행은 소유 모듈 연결이 필요합니다. [프론트엔드 검증 기록](frontend/QA.md)에 실행 결과와 미검증 범위를 분리했습니다.

Go Backend는 [`backend/`](backend/README.md)에 있습니다. Docker 없이 `./backend/scripts/dev-db.ps1`, `./backend/scripts/dev-server.ps1`을 별도 터미널에서 실행합니다. 모든 업무 화면이 `/api/v1`을 호출하며 `/settings/backend`에서 서비스 연결 상태를 확인합니다. 사용자·Agent 인증은 이번 단계에서 제외했습니다. [Backend API](backend/API.md) · [최소 테스트/E2E 결과](backend/QA.md).

1. 이 README에서 서비스 목적·구조·현재 상태를 확인합니다.
2. [요구사항·개발 범위](<output/deliverables-20260917-v1.2/01_요구사항_개발범위_정의서.md>)에서 담당 기능과 완료 조건을 확인합니다.
3. 개발 역할에 따라 API·데이터·Agent·프론트엔드 명세를 읽습니다.
4. [테스트 기준](<output/deliverables-20260917-v1.2/05_테스트_검수_기준서.md>)과 [운영 인계서](<output/deliverables-20260917-v1.2/06_배포_운영_인계서.md>)에 구현 결과와 실환경 증거를 연결합니다.

## 제공할 기능

Agent는 **Chatbot·GPU Node RCA·운영보고서** 세 개의 독립 실행·배포 모듈입니다. Chatbot은 일반 대화·조회·요청 해석·결과 설명을 맡으며, 긴 전문 분석을 해당 Agent의 작업으로 접수합니다.

| 목적 | 흐름 |
|---|---|
| RCA 자동 조사 | Grafana → Incident → Job Controller → RCA Agent |
| RCA 결과 조회 | GUI → Backend → 저장된 사건·분석 결과 |
| 즉시 보고서 | GUI → Backend → Job Controller → 보고서 Agent |
| 정기 보고서 | Backend 내부 스케줄러 → 같은 보고서 큐 → 보고서 Agent |
| 처리 용량 변경 | 운영자가 Agent 수·동시 처리 한도를 수동 조정 |

Job Controller는 큐 관리와 **기존 자원 한도 안에서 잡 배분**을 맡습니다. 처리 여유가 없으면 큐에서 대기합니다. Backend·Incident·Job Controller·RCA·보고서는 각각 독립 실행·배포하며 공통 조회·계산 코드는 라이브러리로 공유합니다.

Chatbot/Assistant, GUI 직접 RCA 실행, 독립 Scheduler, HPA/자동 확장, 제품 인증·RBAC·사용자 tenant는 이번 범위에서 제외합니다. 기존 관측 저장소 접속 설정은 유지합니다.

## 개발 기준

1. [요구사항·개발 범위](output/deliverables-20260917-v1.3/01_요구사항_개발범위_정의서.md)에서 기능과 단계별 종료 조건을 확인합니다.
2. [API](output/deliverables-20260917-v1.3/02_백엔드_API_작업명세서.md), [데이터](output/deliverables-20260917-v1.3/03_데이터_설계서.md), [모듈 간 계약](output/deliverables-20260917-v1.3/14_모듈간_호출과_공통실행_계약.md)을 맞춰 구현합니다.
3. [시험 기준](output/deliverables-20260917-v1.3/05_테스트_검수_기준서.md)과 [운영 인계](output/deliverables-20260917-v1.3/06_배포_운영_인계서.md)에 실행 증거를 남깁니다.

R01~R09/O01~O11의 업무와 기존 계산·품질 기준은 유지합니다. 수치는 코드로 계산하고 LLM은 근거 해석·설명을 맡습니다. 현재/과거 관계, 0/null, 작업 성공/분석 근거 부족/설명 실패를 구분합니다. 실제 장비 조치는 사람이 수행합니다.

## 프론트엔드 실행과 현재 차이

[frontend](frontend/README.md)는 React 기반 데모입니다.

```sh
cd frontend
npm ci
npm run dev
```

코드에는 이전 Assistant·수동 RCA·역할 선택 데모가 남아 있습니다. 이번 문서 개정에서 제품 코드는 바꾸지 않았으며 [FE 전환 명세](output/deliverables-20260917-v1.3/07_프론트엔드_개발명세서.md)에 제거·연동 작업을 기록했습니다. [기존 검증 기록](frontend/QA.md)은 v1.3 제품 검수 결과가 아닙니다.

## 저장소와 검증

`output/deliverables-20260917-v1.3/`는 현행 개발 문서, `output/architecture-modules-20260917-v1.3/`는 확정 구조도, [docs/evidence](docs/evidence/README.md)는 수집 환경의 원문 근거입니다. 구버전 명세·중간 구조도·중복 시안·배포본은 정리했으며 Git 이력에서 확인할 수 있습니다.

```sh
python tools/check_links.py
```

이 명령은 로컬 문서·자산 경로를 검사합니다. 원격 URL 응답이나 실제 Backend·Agent 통합 검수를 대신하지 않습니다. 변경은 PR에서 목적·영향·검증·남은 작업을 확인합니다.
