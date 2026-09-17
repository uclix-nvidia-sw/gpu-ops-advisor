# DSX Frontend


React + TypeScript + Vite 기반의 독립 프론트엔드입니다. 개발 기준은 [v1.3 FE 명세](../output/deliverables-20260917-v1.3/07_프론트엔드_개발명세서.md)와 [GUI 설계](../output/deliverables-20260917-v1.3/08_GUI_화면설계서.md)입니다.

**현재 코드는 이전 설계의 데모입니다.** Assistant·직접 RCA 요청·역할 선택 UI가 남아 있으며 v1.3 전환에서 제거합니다. 아래 실행/데모 설명은 현 코드 상태를 기록한 것이고 새 기능 기준이 아닙니다.

## Docker 없이 실행

저장소 루트에서 각각 별도 터미널을 사용합니다.

```powershell
./backend/scripts/dev-db.ps1
./backend/scripts/dev-server.ps1
cd frontend
npm ci
npm run dev
```

브라우저: http://127.0.0.1:5173/dashboard

Vite가 `/api`를 `http://127.0.0.1:8080`으로 전달합니다. PostgreSQL은 개발용 55432 포트를 사용합니다. 사용자·Agent 인증은 요청에 따라 제외되어 있으며 Backend의 고정 개발 사용자와 업무 범위를 사용합니다.

## 연결 범위

| 화면 | 실제 호출 |
|---|---|
| 공통 범위 | `/me`, `/clusters`; principal·grant 변경 시 조회 캐시와 대화 맥락 초기화 |
| 대시보드 | `/dashboard/query`, `/jobs`, `/service-status` |
| 장비·Pod·품질 | `/assets`, `/observations/query`, `/mappings/query`, `/evidence/{id}` |
| RCA·사건 | `/analyses`, `/incidents`; 실제 대상·기간 검증 및 사건 상태 변경 |
| 보고서 | `/reports`; O01~O11·비교 기간·조치·자원 조건, 서버 HTML/CSV 내보내기 |
| 작업 | `/jobs/{id}`, cancel/retry; 버전·멱등 키, 종료 상태 폴링 중단 |
| 일정 | `/schedules`, occurrences, dispatches; 등록·조건 변경·일시 정지, 서버 계산 다음 실행 |
| 지식 | `/knowledge`; 초안·revision·검토 요청/승인/수정 요청·발행·폐기 |
| 모델·설정 | `/models`, test-connection, `/model-routes`, `/settings/C07`, access-grants |
| Assistant | `/conversations`, messages; 서버 대화 목록·메시지 상태·응답·작업 참조 |

지식·모델·설정은 Backend가 PostgreSQL에 저장합니다. 작업·결과 목록과 관측은 현재 저장된 서버 기록을 읽습니다. RCA/Report/Chatbot/Incident/Scheduler는 각 소유 모듈로 중계합니다. **현재 해당 모듈과 실시간 관측 소스는 미연결 상태**이며 실제 추론·보고서 생성·예약 실행은 아직 실행할 수 없습니다. UI는 서버의 503/422 등을 표시하고 성공 기록을 만들지 않습니다.

`sessionStorage`에는 진행 중 요청의 해시·멱등 키·원래 버전과 선택한 대화 ID만 보관합니다. 업무 데이터는 PostgreSQL이 원본입니다. 변경 요청 실패 시 입력은 유지하며, 불확실한 응답은 같은 요청 키로 다시 시도할 수 있습니다. 서버가 보낸 `Retry-After`와 조회 실패 지연을 적용합니다.

## 구조

```text
frontend/
├── src/components/  # Shell, Assistant, 공통 조회/오류·근거·결과 표시
├── src/pages/       # 업무별 실제 API 화면
├── src/lib/         # API 전송, 조회/변경 훅, 범위·기간, 최소 테스트
├── Dockerfile
├── nginx.conf
└── vite.config.ts
```

`frontend/`, `backend/`, `output/`은 같은 루트 수준입니다. React Router, TanStack Query, Lucide, 로컬 Fontsource 폰트를 사용합니다. 파일 줄바꿈은 CRLF입니다.

## 검사

```powershell
npm run build
npm test
npm run format:check
```


[검증 기록](QA.md)을 참고하세요. 프론트엔드 최소 테스트는 4개입니다. 백엔드의 실제 DB·HTTP 계약 E2E는 `../backend/scripts/test.ps1 -E2E`로 실행합니다.

## 현재 구현 범위

7개 메뉴와 S01~S16/S07B의 경로를 구현했습니다. Node/GPU/Pod 조사, 전체 R01~R09와 O01~O11 선택, 비동기 작업 데모, 사건 상태 변경, 검토/실제 조치 기록, HTML/CSV 출력, 일·주·월 일정 조건, 지식 revision 관리, 모델 등록·라우팅, Assistant 예시 응답을 확인할 수 있습니다.

**현재 실행 모드는 프론트엔드 데모입니다.** `localStorage`의 `dsx-frontend-demo-v1`은 가상 데이터만 보존하며 실제 서버 업무 원장이 아닙니다. 개발 화면을 새로고침해도 데모 작업·지식·일정·대화가 유지됩니다. 실제 인증·권한/ETag·멱등성·소스 조회·Worker·스케줄러·LLM 호출·서버 출력 권한 검증은 아직 연결되지 않았습니다. 모델 연결 검사와 데이터 설정 저장은 이 제한을 명시합니다. 임의 서버 URL이나 모델 비밀 원문을 브라우저에서 호출/저장하지 마세요.

우측 상단 사용자 프로필에서 데모 역할을 바꾸면 조회자, 운영자, 지식 관리자, 서비스 관리자 화면을 확인할 수 있습니다. 이 선택은 인증 기능이 아닙니다.

사용 안내의 **데모 데이터 초기화**로 브라우저 내 예시 데이터를 복원할 수 있습니다. 미저장 모델·지식 폼은 앱 내부 확인창에서 계속 편집하거나 변경을 버리고 닫을 수 있습니다.

초기 대시보드는 2026-09-16 14:15 KST의 **합성 예시 데이터**입니다. 새 작업은 관측 데이터가 없으므로 `succeeded + blocked`, `narrative_status=omitted` 결과를 보여줍니다. UI가 실제 운영 수치나 원인을 만들어내지 않습니다.

## 백엔드 통합 지점

`src/lib/api.ts`에 `/api/v1` JSON 요청, 조건부 변경 헤더, 멱등 키, 구조화 오류·Retry-After 전달을 위한 전송 기반을 두었습니다. 현재 화면은 `demoRepository`를 사용합니다. **환경 변수 하나로 실서비스 연결이 완료되는 상태는 아닙니다.**

통합 시 화면별 DTO를 v1.3의 02/03에 연결합니다. 제품 인증·/me·권한 grant와 대화 API는 이번 범위에서 제외하며 CPC/Namespace는 분석 필터로 사용합니다. 데모 수명주기 `DemoJobRunner`는 제거하고 `/jobs` 조회의 backoff·Retry-After·terminal 중단으로 교체합니다. 모델/지식/일정의 서버 입력 검증, 사건 결과 조회·보고서 접수·다운로드는 별도 통합 시험 대상입니다. RCA 실행은 Incident만 접수하며 일정 발생은 Backend가 수행합니다.


## 컨테이너

```powershell
docker build -t dsx-frontend:dev ./frontend
```

nginx는 `/api/`를 같은 Docker 네트워크의 `backend:8080`으로 전달합니다. Backend의 컨테이너 실행 주소는 `0.0.0.0:8080`이어야 합니다. SPA 직접 링크를 지원합니다. 현재 PC에는 Docker가 없어 이미지 실행은 검증하지 않았습니다.
