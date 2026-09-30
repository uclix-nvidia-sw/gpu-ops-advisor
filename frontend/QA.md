# 2026-09-30 PR #28과 GUI 관점 전환 병합 검증

2026-09-30 RCA 변경을 최신 main `77fbfcf` GUI 관점 전환과 통합한 뒤 **33 tests**, `npm run format:check`, `npm run build` 통과. 공개 RCA 최종 보고서는 공통 RcaResult를 통해 기존·운영·개발 화면에 표시된다. 아래 24건 기록은 통합 전 검사다. API/LLM fixture 범위를 유지하며 운영 화면 검수는 미수행이다.

main `b27ed57`의 기존·운영·개발 GUI를 Namespace 보고서 개선과 함께 유지했다. ReportContent·report 지표/사유·Results의 충돌을 해결하고 운영측 목차 선택 시 접힌 주제 상세를 펼치도록 연결했다.

- **통과:** frontend `npm test` 30건, `npm run build`, `npm run format:check`. 기존/새 결과·0/null·분모·권고 보류·근거·실패 표시 회귀를 포함한다.
- **통과:** 로컬 합성 API와 in-app browser에서 세 모드 전환 후 같은 namespace 수치·운영측 목차 이동/펼침·개발측 workflow/evidence 안내, 390px 개발측 페이지 가로 넘침 없음·브라우저 오류 없음 확인.
- **통과:** 문서 링크와 diff 검사. Backend·JC·Worker 제품 코드는 이전 PR 커밋과 동일하므로 로컬 서비스 E2E는 재실행하지 않았다. 이전 커밋의 원격 Go/Python/Frontend/Helm 검사 통과를 확인했다.
- **미검증:** 이 병합 커밋의 원격 CI·운영 배포·실제 Grafana/LLM. 운영 화면과 DB는 변경하지 않았다.

---

# 2026-09-30 Namespace 운영 보고서 개선

- **통과:** `npm test` 26건, `npm run format:check`, `npm run build`. 0%·산출 불가·기존 결과의 미계산, 공유 제외 사유, 실행 제한/조회 실패 구분, 메모리 단위, 검토 기록 없음 문구를 검사했다.
- **통과:** Codex in-app browser에서 로컬 Vite build와 합성 API로 보고서 목록 → Namespace GPU 현황 → O08/namespace 기본값 → 제출 → 저장 결과를 확인했다. namespace 요약·보류 권고·접힌 상세 근거·MiB, 390px 페이지 가로 넘침 없음과 브라우저 오류 없음 확인. 실제 운영 데이터는 UI fixture에 포함하지 않았다.
- **통과:** 실제 Backend/JC/Worker 연동은 별도의 [Agent QA](../agents/QA.md) 통합 검사에서 확인했다.
- **미수행/미검증:** 운영 화면 배포, 실제 Grafana/LLM. 기존 보고서의 수치는 변경하지 않으며 새 보고서를 실행해야 criteria 1.2가 적용된다.

---

# 2026-09-30 RCA 가독성 개선 로컬 검증

## 2026-09-30 RCA 최종 보고서 표시

- **통과:** `frontend/`에서 `npm.cmd test` — 5 files, 24 tests. complete/failed/omitted의 narrative 표시, 기본 보고서 안내, 원인 미확정/권고 보류 유지, HTML escape, 미발행 결과 숨김 및 기존 결과 표시 회귀.
- **통과:** 같은 디렉터리의 `npm.cmd run build`, `npm.cmd run format:check`.
- 화면 검사는 mocked result를 React 서버 렌더링한 검사다. 실제 브라우저·운영 Backend 응답을 통한 시각 검수는 **미검증**이다. esbuild의 상위 디렉터리 sandbox 읽기 제한은 동일 명령의 허용된 실행으로 재검사해 통과했다.
- 로컬 수정이며 배포하지 않았다. 실제 Worker/JC 결과 저장·공개 fixture 연동 범위는 [Agent QA](../agents/QA.md)를 따른다.

후속 목록 정리: 상태 상자를 알람/사건/검토 개별 컬럼의 배지로 변경했다. `npm test` 21건, 포맷·빌드·문서 링크·diff 검사를 통과했다. Edge/Playwright 모의 API로 다섯 컬럼, 상태 값만 표시, 누락 상태 미확인, 390px 페이지 가로 넘침 없음을 확인했다. 운영 검증은 미수행이다.

기준: main `54a7ea5`에서 분리한 `fix/rca-alarm-readability`. 기존 읽기 API의 target 필드를 사용하며 API·DB 계약 변경 없음.

- **통과:** frontend의 `npm test` (21 tests), `npm run build`, `npm run format:check`.
- **통과:** Edge/Playwright에서 모든 API를 fixture로 대체하여 알람 이름·대상·ID, 이름 없는 사건, 세 상태 상자, 제품명/탭 제목, 원본 필드 설명의 Enter 펼치기, 390px 상세 화면 가로 넘침 없음, pageerror 0건을 확인했다.
- **통과:** 대시보드 내부 서비스 요약의 응답 정상·응답 확인 실패·누락 시 미확인, 상세 링크, 1440px에서 높이 220px 미만, 390px에서 가로 넘침 없음, pageerror 0건을 Edge/Playwright 모의 API로 확인했다. 변경 후 위 테스트·빌드·포맷 검사를 다시 통과했다.
- **미수행/미검증:** 운영 알람·실제 Backend/DB·Grafana/LLM 연동, CI·배포.
- **해당 없음:** Go/Worker/DB 검증 — 변경 없음.

---

# 2026-09-30 RCA 디버깅 GUI 로컬 검증

기준: main `185ea2b`에서 분리한 `fix/rca-debugging-ui`의 로컬 변경. 기존 Backend 읽기 API만 사용하며 DB·Worker·RCA 실행 계약은 변경하지 않았다.

- **통과:** frontend에서 `npm test` (19 tests), `npm run build`, `npm run format:check`.
- **통과:** Edge/Playwright 브라우저에서 모든 `/api/**`를 fixture로 대체하여 사건 상태·필터 → 사건 연결 작업 → 공개된 blocked 결과 → 근거 8건씩 조회 → 일시적 조회 실패 재조회 → 다른 job 근거 차단 → 근거 dialog 열기/닫기를 검증했다. 브라우저 pageerror 0건, 390px 화면의 페이지 가로 넘침 없음. 근거 표는 자체 가로 스크롤을 사용한다.
- **통과:** 저장소 루트 문서 링크 검사 (95 documents, 1123 local links/assets), `git diff --check`.
- **미수행/미검증:** 실제 Backend/DB 연동, 운영 Grafana·LLM, 실제 알람 재시험, 원격 CI·배포. fixture의 성공·실패는 운영 관측 품질의 검증이 아니다.
- **해당 없음:** Go/Worker/DB migration 검사 — 해당 코드와 API 계약을 수정하지 않았다.

---

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

# 2026-09-30 Three GUI perspectives / 세 관점 GUI

변경 범위는 Frontend다. 기존/운영측/개발측 전환, 운영 홈·사건 목록·보고서 서재 및 읽기 화면, RCA·보고서 개발 가이드, 현재 API 요청 메타데이터를 추가했다. 보고서 표시를 현재 Ops Agent의 criteria 1.2 계약에 맞췄다. Backend·Agent 실행 코드는 변경하지 않았다.

- **Passed — static and unit checks**: frontend에서 npm run format:check, npm test(25 tests), npm run build를 통과했다.
- **Passed — UI/contract checks (mocked)**: Headless Edge, 1440px 및 390/320px. 같은 보고서의 세 관점 전환, 목록 탭·필터와 요청 폼 값 유지, 관점의 새로고침 유지, 보고서 criteria/산출 불가/권고 보류, 개발 단계 선택과 데이터 표시, 사건 PATCH의 If-Match·멱등 키, 보고서 POST의 멱등 키·202 이후 queued 작업 이동을 확인했다. 모바일 홈 가로 넘침 없음, 메뉴 열기·Escape 닫기를 확인했다.
- **Passed — failure/missing states (mocked)**: 빈 보고서 목록, 503와 요청 ID, failed 작업, 미공개 후보 비노출, 설명 생성 실패와 부분 산출을 확인했다. 추가 단위 검사는 0과 null, 분모와 제외 사유, 공개 참조, API 메타데이터의 최대 50건 및 본문·쿼리 값 제외를 검사한다.
- **Not run / unverified**: 실제 Backend·PostgreSQL·Grafana·LLM·Worker 연결, 실환경 Agent 완료와 보고서 다운로드 내용. 브라우저 응답은 격리된 모의 API이며 운영 데이터는 수정하지 않았다. 서버가 제공하지 않는 실시간 단계 trace와 내부 호출 원문은 구현 범위 밖이다.
- **Not applicable**: Backend/Agent 로컬 테스트는 해당 코드·계약 변경이 없어 실행하지 않았다. 이 기록은 로컬 검증 결과이며 원격 CI 결과는 PR에서 별도로 확인한다. 배포는 수행하지 않았다.
