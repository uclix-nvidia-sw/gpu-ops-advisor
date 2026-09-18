# GPU Ops Advisor Frontend

React + TypeScript + Vite. [v1.3 명세](../output/deliverables-20260917-v1.3/07_프론트엔드_개발명세서.md)의 Backend 계약 변경에 맞춰 실제 Go API 연결을 갱신했습니다. 사용자/권한 DTO, Assistant, 직접 RCA 실행, GUI 용량 변경은 제외했습니다.

## 실행

저장소 루트에서 DB와 Backend를 각각 별도 터미널로 실행하고 Frontend를 실행합니다.

```powershell
./backend/scripts/dev-db.ps1
./backend/scripts/dev-server.ps1
cd frontend
npm ci
npm run dev
```

개발 주소는 http://127.0.0.1:5173/dashboard 입니다. Vite가 `/api`를 127.0.0.1:8080으로 전달합니다. Docker가 필요하지 않습니다.

## 연결

- 공통 범위: `/clusters`의 등록 CPC를 필터로 사용합니다. 로그인/권한은 없습니다.
- 최초 설치: 클러스터 0건이면 빈 상태와 등록 안내를 표시합니다. 연결·설정 → 데이터 연결에서 클러스터 ID를 등록하면 목록과 공통 관측 범위가 갱신됩니다. 등록 전에는 분석 화면의 조회/실행을 시작하지 않습니다.
- 대시보드: GET `/dashboard`, 작업·서비스 상태.
- 자산/Pod: 저장된 identity 및 관측·매핑 스냅샷. 실시간 소스가 없으면 미확인입니다.
- 사건/RCA: 저장 사건·분석 조회, Incident 메타데이터 PATCH. 새 RCA는 Incident에서 생성합니다.
- 보고서: JC 접수 응답 후 job 이동, 저장된 final의 주제별 수치·산출 불가 이유·수집 상태 표시, HTML/CSV 다운로드. GPU–Pod 연결 관측 시간과 독점 할당량을 구분합니다.
- 일정: Backend의 평탄한 calendar 입력·report_spec, revision 수정·일시 정지·occurrence 조회.
- 지식/모델: 불변 revision·검토/발행, rca/report 모델 라우팅, secret_ref만 저장.
- 변경 요청: 멱등 키를 생성하고 응답 유실 시 같은 본문/키/최초 버전을 재사용합니다.
- HTTP NodePort 접속: 요청 fingerprint는 브라우저 SHA-256 구현으로, UUID는 `crypto.getRandomValues`로 생성합니다. HTTPS 전용 `crypto.subtle`·`crypto.randomUUID`에 의존하지 않습니다. 기존 SHA-256 fingerprint와 재시도 키는 유지합니다.

분석 실행에는 배포 환경의 JC·Incident·Agent·관측/LLM 연결이 필요합니다. 의존 서비스 미연결로 요청이 실패하면 오류를 표시하고 가짜 완료·결과를 만들지 않습니다. JC가 접수했지만 Agent가 없으면 queued 상태를 유지합니다. 테스트 fixture는 앱에 연결하지 않습니다. 검증 환경과 실제 연결 범위는 아래 QA를 따릅니다.

```powershell
npm run test
npm run build
npm run format:check
```

[검증 기록](QA.md) · [Backend API](../backend/API.md)
