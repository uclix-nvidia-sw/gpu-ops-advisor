# DSX Frontend

React + TypeScript + Vite 기반의 독립 프론트엔드입니다. 개발 기준은 `output/deliverables-20260916-v1.1/07_프론트엔드_개발명세서.md`와 08 GUI 설계입니다.

## 실행

Node.js 22.12+ 또는 24 LTS 환경을 사용합니다.

```sh
cd frontend
npm ci
npm run dev
```

기본 주소: http://127.0.0.1:5173

```sh
npm run build
npm test
npm run preview
```

## 구성

```text
gpu-ops-advisor/
├── output/                  # 기존 개발 명세·설계 자료
└── frontend/                # 독립 npm 프로젝트·이미지 빌드 컨텍스트
    ├── src/
    │   ├── components/      # Shell, 범위 선택, Assistant, 공통 UI
    │   ├── pages/           # 관측, RCA, 보고서, 작업, 일정, 지식, 설정
    │   ├── data/            # 타입이 정의된 고정 데모 데이터
    │   ├── lib/             # 도메인 규칙, API 전송, 데모 저장소, 테스트
    │   ├── main.tsx         # 실제 리소스 경로 기반 라우터
    │   └── styles.css       # 공통 스타일·반응형·포커스
    ├── Dockerfile
    └── nginx.conf
```

후속 backend/와 agents/는 output/, frontend/와 같은 루트 수준에 독립 빌드 컨텍스트로 추가할 수 있습니다. 이번 작업은 해당 서비스를 만들지 않습니다.

## 사용 라이브러리

- React 19 / TypeScript: 화면과 데이터 타입
- Vite: 개발 서버·정적 산출물 빌드
- React Router: 직접 링크·새로고침·뒤로 가기
- TanStack Query: 공유 조회 캐시
- Recharts: GPU 추이 시각화
- Lucide React: 일관된 인터페이스 아이콘
- Vitest: 기간·scope·작업 수명주기·안전한 출력 검사
- Fontsource: Inter / Noto Sans KR를 로컬 번들에 포함. 런타임 외부 폰트 요청 없음

## 현재 구현 범위

7개 메뉴와 S01~S16/S07B의 경로를 구현했습니다. Node/GPU/Pod 조사, 전체 R01~R09와 O01~O11 선택, 비동기 작업 데모, 사건 상태 변경, 검토/실제 조치 기록, HTML/CSV 출력, 일·주·월 일정 조건, 지식 revision 관리, 모델 등록·라우팅, Assistant 예시 응답을 확인할 수 있습니다.

**현재 실행 모드는 프론트엔드 데모입니다.** `localStorage`의 `dsx-frontend-demo-v1`은 가상 데이터만 보존하며 실제 서버 업무 원장이 아닙니다. 개발 화면을 새로고침해도 데모 작업·지식·일정·대화가 유지됩니다. 실제 인증·권한/ETag·멱등성·소스 조회·Worker·스케줄러·LLM 호출·서버 출력 권한 검증은 아직 연결되지 않았습니다. 모델 연결 검사와 데이터 설정 저장은 이 제한을 명시합니다. 임의 서버 URL이나 모델 비밀 원문을 브라우저에서 호출/저장하지 마세요.

우측 상단 사용자 프로필에서 데모 역할을 바꾸면 조회자, 운영자, 지식 관리자, 서비스 관리자 화면을 확인할 수 있습니다. 이 선택은 인증 기능이 아닙니다.

사용 안내의 **데모 데이터 초기화**로 브라우저 내 예시 데이터를 복원할 수 있습니다. 미저장 모델·지식 폼은 앱 내부 확인창에서 계속 편집하거나 변경을 버리고 닫을 수 있습니다.

초기 대시보드는 2026-09-16 14:15 KST의 **합성 예시 데이터**입니다. 새 작업은 관측 데이터가 없으므로 `succeeded + blocked`, `narrative_status=omitted` 결과를 보여줍니다. UI가 실제 운영 수치나 원인을 만들어내지 않습니다.

## 백엔드 통합 지점

`src/lib/api.ts`에 `/api/v1` JSON 요청, 조건부 변경 헤더, 멱등 키, 구조화 오류·Retry-After 전달을 위한 전송 기반을 두었습니다. 현재 화면은 `demoRepository`를 사용합니다. **환경 변수 하나로 실서비스 연결이 완료되는 상태는 아닙니다.**

통합 시 화면별 DTO를 02/03의 응답과 연결하고, `/me`에서 principal·access_revision·grant를 받아 캐시 키와 허용 범위를 검증해야 합니다. 데모 수명주기 `DemoJobRunner`는 제거하고 `/jobs` 조회의 backoff·Retry-After·terminal 중단으로 교체합니다. 모델/지식/일정의 서버 검증, 메시지 복구, 증거 조회·다운로드의 접근 검사도 별도 통합 시험 대상입니다.

## 컨테이너

저장소 루트에서:

```sh
docker build -t dsx-frontend:dev ./frontend
docker run --rm -p 8080:8080 dsx-frontend:dev
```

nginx는 SPA 직접 링크를 index.html로 처리합니다. `/api/`는 백엔드를 연결하기 전 503을 반환합니다. 개발 서버와 이미지 배포는 별개이며 컨테이너 실행 검증 여부는 QA.md를 참고하세요.
