# 프론트엔드 API 연결 검증

검증일: 2026-09-17. Windows · Node 24 · Go 1.26.2 · PostgreSQL 16.9 · 내장 Chromium 브라우저. UI는 Vite 5173 → Go 8080 → 실제 PostgreSQL 55432로 연결했습니다. 사용자·Agent 인증은 요청에 따라 제외했습니다.

## 자동 검사

- TypeScript strict / Vite production build: PASS.
- Vitest 최소 4개: PASS. KST 시간 구간·미확인 날짜, role/CPC/Namespace 조합, 재시도 해시, 실제 전송 헤더 및 오류 보존.
- Go 최소 단위 테스트·vet 및 실제 PostgreSQL 기반 E2E 11개 시나리오: PASS. 자세한 범위는 [Backend QA](../backend/QA.md).
- 데모 fixtures·localStorage 원장·DemoJobRunner·가짜 Assistant·브라우저 보고서 생성 코드 제거.

## 실제 브라우저 E2E

| 흐름 | 확인 |
|---|---|
| 대시보드 | DB 사건 개수와 관측 미연결 상태, 실제 작업 목록·모듈 상태 |
| 자산·Pod·관측 품질 | API 빈 목록과 저장 스냅샷 가용성 표시 |
| 사건·분석 목록 | Incident 503와 DB 분석 빈 목록을 구분 |
| RCA 요청 | 미등록 GPU 대상으로 422 표시, 입력 유지 |
| 보고서 요청 | Report 503 표시, 가짜 작업 미생성 |
| 일정 | Scheduler 503 표시와 재조회 버튼 |
| Assistant | 대화 목록·생성 503 표시, 질문 유지·가짜 답변 미생성 |
| 지식 | 생성 → 검토 요청 → 승인 → 발행 → 새로고침 → 발행 목록 조회 |
| 설정 | C07 실제 조회 및 같은 설정 저장, 성공 응답 확인 |
| 모바일 | 390px/320px 메뉴·지식·대시보드, 좁은 화면 스크롤 점검 |

남겨 둔 검증용 지식: `API 연동 E2E · 관측 누락 점검`, knowledge_id `9bcd382c-c3f5-4083-82f4-38966510cf27`, revision 1, published. 서버 저장·재조회 확인용이며 실제 운영 조치 지침은 아닙니다.

## 검증 한계

실제 RCA·Report·Chatbot·Incident·Scheduler 서비스는 미연결입니다. 브라우저에서 실제 분석 성공·생성 보고서 다운로드·일정 실행·대화 응답 완료를 검증한 것은 아닙니다. 해당 API의 중계·멱등·저장 결과 조회는 백엔드 E2E의 HTTP fixture로 검증했습니다. 실시간 Mimir/Loki·GPU 수집·모델 추론·전체 제품 검수 T01~T48·Docker 실행은 아직 검증하지 않았습니다.
