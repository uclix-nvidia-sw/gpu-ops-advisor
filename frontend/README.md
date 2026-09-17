# DSX Frontend

React 19 + TypeScript + Vite 기반 프론트엔드입니다. 모든 업무 화면은 `/api/v1`을 통해 Go Backend를 호출합니다. 브라우저의 데모 저장소와 가짜 작업 완료·Assistant 응답은 제거했습니다.

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

## 컨테이너

```powershell
docker build -t dsx-frontend:dev ./frontend
```

nginx는 `/api/`를 같은 Docker 네트워크의 `backend:8080`으로 전달합니다. Backend의 컨테이너 실행 주소는 `0.0.0.0:8080`이어야 합니다. SPA 직접 링크를 지원합니다. 현재 PC에는 Docker가 없어 이미지 실행은 검증하지 않았습니다.
