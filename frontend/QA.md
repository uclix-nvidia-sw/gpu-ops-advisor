# Frontend v1.3 Backend 연결 검증

2026-09-17: 사용자/권한 부트스트랩을 등록 CPC 조회로 바꾸고, 직접 RCA/Assistant/용량 변경 UI를 제거했습니다. 일정 입력과 revision 수정은 Backend v1.3 API에 연결했습니다.

- Vitest 최소 3개·TypeScript/Vite build: PASS.
- 실제 브라우저 일정 생성·다음 실행 시각·일시 정지·실행 시각 수정: PASS.
- 검증용 일정은 일시 정지 상태이며 revision 3, 매일 10:00 KST입니다.
- Go/PostgreSQL E2E: [Backend QA](../backend/QA.md).
- 실제 JC/Agent/LLM 실행·실시간 관측 통합은 NOT RUN입니다.

아래는 과거 버전의 검증 기록으로 현행 검수 결과에 합산하지 않습니다.

---

# 프론트엔드 API 연결 검증


> 과거 데모의 실행 기록입니다. 아래 직접 RCA·Assistant·역할 선택은 [v1.3](../docs/specs/frontend/07_프론트엔드_개발명세서.md)에서 제거할 대상이며 PASS를 현행 제품에 승계하지 않습니다. v1.3 통합 시험은 NOT RUN입니다.

검증일: 2026-09-17 · 기준: DSX FE/GUI v1.1 · 실행 환경: Windows, Node 24, Codex 내장 Chromium 브라우저.

이 기록은 **프론트엔드 데모 검증**입니다. 명세 05의 실환경 T01~T40, API/DB/LLM 통합 또는 인증 검수 PASS를 의미하지 않습니다.

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
# 2026-09-18 클러스터 등록 흐름 검증

프로덕션 빌드와 Vitest 3개, Prettier 검사 통과. Headless Edge에서 빈 목록 표시, 등록 화면 이동, 등록 요청의 멱등 키, 등록 후 목록·범위 갱신, 중복 등록 오류, 새로고침 및 모바일 화면을 확인했다. 클러스터가 없을 때 범위 없는 대시보드 조회가 실행되지 않음을 확인했다. 브라우저 API 응답은 격리된 fixture이며, 실제 PostgreSQL·Backend의 등록과 저장 동작은 Backend E2E에서 별도로 검증했다.
# 2026-09-18 HTTP NodePort 등록 오류 회귀 검사

일반 HTTP origin에서 `isSecureContext=false`, `crypto.subtle`/`crypto.randomUUID`가 undefined인 조건으로 기존 digest 오류를 재현했다. 기존 localhost 검증은 secure context 예외 때문에 이 실패를 찾지 못했다.

수정 후 동일 HTTP 조건에서 클러스터 등록, 응답 유실(503) 후 새로고침·동일 멱등 키 재전송, 중복 등록 오류, 백엔드 연결 화면 렌더링을 Headless Edge로 확인했다. 브라우저 API는 격리 fixture를 사용했다. Vitest 9개와 TypeScript·프로덕션 빌드·Prettier 검사 통과. SHA-256 결과와 저장소 키는 기존 Web Crypto 결과와 동일하며, UUID는 HTTP에서도 사용 가능한 getRandomValues로 생성한다. 운영 클러스터의 수정 이미지 배포 검증은 아직 수행하지 않았다.
