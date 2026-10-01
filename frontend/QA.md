# 2026-10-01 Frontend 이미지 빌드 수정

- **원인:** PR #45의 단위 테스트는 통과했으나 이미지 빌드에서 테스트의 `rcca-agent` JSON import가 frontend 전용 Docker context 밖을 참조해 TS2307로 실패했다.
- **수정:** XID 99 Runbook 테스트 스냅샷을 frontend 내부 fixture로 고정했다. 테스트와 타입 검사는 유지한다.
- **통과:** frontend 포맷 검사, 69개 테스트, 타입/프로덕션 빌드. Docker 이미지 검증은 수정 커밋의 원격 CI에서 확인한다.

---

# 2026-10-01 최신 main 통합 검증

- **통과:** main `e22947f`의 보고서 요청·목록 복귀 및 RCA 단계 진단을 보존해 충돌을 해결했다. Frontend 포맷, 69개 테스트, 타입/프로덕션 빌드 및 문서 링크 검사를 통과했다.
- Backend 코드는 통합 중 변경되지 않았으며 아래 격리 PostgreSQL 검증 결과를 유지한다. 통합 후 운영 배포·실환경 검증은 미수행이다.

---

# 2026-10-01 저장 기록 웹 추적·Runbook content

- **통과:** frontend `npm test` 53건, 타입/프로덕션 build, format 검사. 원본 소수점 시각·null/필드 없음 차이, 고정 revision, 선택한 시도의 경로, 실제 XID 99 Runbook content와 legacy text, HTML escape를 검사했다.
- **통과:** Edge/Playwright 모의 API에서 고정 사건 revision, 전달 전후 비교, 두 작업 비교, 과거 시도, 실제 저장 조회 인자·응답 표시, 두 조회 비교, 페이지 추가, 503 재조회, 잘못된 작업 근거 차단, trace 실패 상태를 확인했다. 지식 상세와 작업의 고정 revision에서 Runbook 본문 표시, 1440px/390px 화면, 모바일 넘침 없음, pageerror 0건을 확인했다.
- **통과:** 새 API의 실제 HTTP/PostgreSQL 검증은 [Backend QA](../backend/QA.md)를 따른다. 브라우저는 모의 API로 검사했으며 운영 데이터와 연결하지 않았다.
- **미수행/미검증:** 운영 배포·실제 RCA/보고서 재실행·Grafana/LLM 연동. 미기록 synthesis 오류 상세와 실제 단계 실행 시각은 이번 변경으로 복구되지 않는다. Worker와 DB migration 변경 없음.

---

# 2026-10-01 작업 중심 개발자 디버깅

- **통과:** frontend에서 `npm test` 50건, `npm run format:check`, `npm run build`. 키 연결·복합 키·지식 content_hash 대조, 미공개 결과 차단, 상세 탭과 목록 복귀 경로 보존을 검사했다.
- **통과:** Edge/Playwright 격리 모의 API로 RCA/보고서의 단일 상세 진입, 사건·근거·지식 조회, 과거 시도 선택, 다른 작업의 근거 차단, 503 재조회·404·접수 대기·미공개 상태, 새로고침 후 목록 필터 복귀, 세 관점 전환과 중복 메뉴 제거를 확인했다. 1440px/390px 화면 확인, 모바일 가로 넘침 없음, pageerror 0건.
- **통과:** 문서 링크 및 diff 검사. 브라우저 검사는 모의 응답이며 운영 DB를 읽거나 수정하지 않았다.
- **미수행/미검증:** 실제 Backend·DB·Worker·Grafana·LLM 연결, 원격 CI·배포. 실행 당시 사건/모델 스냅샷과 원본 요청 키, 미공개 후보는 기존 API가 제공하지 않아 GUI 조회 불가로 표시한다.
- **해당 없음:** Backend/Agent/DB 테스트 — 해당 코드와 API 계약 변경 없음. 로컬 파일 수정 단계다.

---

# 2026-10-01 RCA 분석 검증 실패 사유 문구

- **통과:** `frontend/`에서 `npm run format:check`, `npm test` **59 tests**, `npm run build`.
- **통과:** 렌더 fixture로 `invalid_limitations`가 코드만이 아니라 한국어 설명과 함께 표시되는지 확인했다. 운영 작업 `ed730b4d` 화면은 배포 전 `사유 코드 invalid_limitations`로 표시됐다.
- **추가:** RCA 부족한 근거 중 문구가 없던 `error_code`·`observation_degraded`·`observation_conflicted`·`synthesis_failed`·`approved_runbook` 설명. 운영 작업 `ed730b4d` 화면에 `사유 코드 error_code` 등으로 표시되던 항목이다.
- **미검증:** 배포 후 실제 브라우저 표시.

---

# 2026-10-01 보고서 기간·수집 구간 검수

- **통과:** `npm run format:check`, `npm test` **57 tests**, `npm run build`.
- **통과:** 로컬 production build + 합성 API의 in-app browser에서 30일 입력→720시간 안내 갱신, 수집 전 검사 중단/조회 구간 완료/일부 미완료 표시, query별 데이터 응답·빈 응답·미완료 구간과 근거 링크 표시를 확인했다. 실제 요청 전 서버 예산 판정 API는 없으며 Worker가 관측 시작 전에 검사한다는 문구를 확인했다.
- **통과:** 390px 화면에서 수집 상세를 펼쳐도 문서 가로 넘침 없음(clientWidth=scrollWidth=375), 브라우저 오류/경고 없음. 뷰포트 원복.
- **미검증:** 운영 배포와 실시간 데이터소스. 화면 검수는 합성 데이터다. 조회 완료를 원본 표본 연속성·계산 가능성으로 표시하지 않는다.

---

# 2026-10-01 보고서 요청·이력·진단 UI 개선

기준: main `1de6f68`. Frontend와 관련 문서만 변경했다. Backend/API·Ops/RCA Worker·수집 예산·DB·다운로드 결과는 변경하지 않았다.

- **통과:** `frontend/`에서 `npm run format:check`, `npm test` **55 tests**, `npm run build`.
- **통과:** 렌더/단위 검사로 목록 필터·공개 결과 이동·짧은 제목·정기 일정 표현·기본 O08/namespace 요청·접힌 세부 설정·로컬 목록 복귀 경로를 확인했다. 진단은 수집 제한/빈 응답/조회 실패/기록 없음, 실제 0/null, 알 수 없는 표본 수, 계산·권고 보류를 구분한다.
- **통과:** 로컬 합성 API와 production build를 in-app browser에서 검수했다. 기존·운영측·개발측 관점, 제목 클릭 후 본문 이동, 실패 작업 이동, 목록 필터와 불러온 행 복귀, 단일 생성 버튼, 구조화 요약 우선 표시, 접힌 수집·계산 진단을 확인했다.
- **통과:** 브라우저에서 사용자 지정 조건 후 기본 목적 복원, 즉시 보고서·정기 일정 제출을 실행하고 합성 서버가 받은 `topic_ids=[O08]`, `group_by=[namespace]`를 확인했다. 일정 목록의 목적·대상·주기를 확인했다.
- **통과:** 390px 화면에서 진단을 펼쳐도 페이지 가로 넘침 없음(clientWidth=scrollWidth=375). 브라우저 오류 없음. 뷰포트와 기존 관점을 복원했다.
- **한계:** 저장된 기록만 표시하며 실시간 단계 trace를 추가하지 않는다. 로딩되지 않은 행이나 직접 URL 접근에는 이전 목록 위치를 복원하지 않는다. 브라우저 검수는 합성 데이터이며 운영 Backend·Grafana·LLM 연결과 배포 후 화면은 미검증이다. 원격 CI는 PR에서 별도로 확인한다.

---

# 2026-10-01 RCA 분석 요청 시도·응답 기록 분리 표시

- **통과:** `frontend/`에서 `npm run format:check`, `npm test` **47 tests**, `npm run build`.
- **통과:** 렌더 fixture로 synthesis 요청 0건·전체 LLM 응답 1건·`llm_context_budget_exhausted` 사유 표시와, 단계별 진단이 없는 구 결과의 `미확인` 표시를 확인했다.
- **확인:** 운영 GUI(배포 전)의 작업 `22c1f69f` 화면에서 `LLM 응답 사용 기록 1건`과 분석 상태 `failed`가 함께 표시되는 기존 혼동을 확인했다.
- **미검증:** 배포 후 실제 브라우저에서 새 항목 표시. 운영 API·배포는 이번 범위가 아니다.

---

# 2026-10-01 보고서 목록에서 본문 바로 열기

- **통과:** `frontend/`에서 `npm run format:check`, `npm test` **46 tests**, `npm run build`.
- **통과:** 목록 컴포넌트 렌더 fixture로 공개된 부분 분석 보고서의 제목·카드가 `/reports/{id}#final-report`를 가리키며 작업 상세를 거치지 않는지 확인했다. 실행 중·실패·성공 상태라도 공개 참조가 없으면 `/jobs/{id}`로 연결된다. 공통 표의 RCA 제목·최종 보고서 링크는 기존 경로를 유지한다.
- **미검증:** 실제 브라우저 클릭·스크롤, 운영 API·배포. 검사는 모의 API 데이터의 링크 출력에 한정한다.
- **해당 없음:** Backend·Worker·DB 로컬 통합 재실행 — UI 링크 외 제품 코드·계약 변경 없음.

---

# 2026-09-30 보고서 GPU·시간과 부분 산출 안내

Ops 목록 식별 정보 보강: Frontend `npm test` **43 passed**, `npm run format:check`와 `npm run build` **통과**. 표·운영 카드 렌더 fixture로 복수 분석 주제, CPC/Namespace 대상, 기간·요청 집계와 공개 보고서 링크를 확인했다. 공통 helper는 복수 CPC, 전체 Namespace(null), 범위 누락, 빈 Namespace 목록과 미지원 주제를 검사한다. 작업 UUID는 표의 접힌 상세로 이동했다. API/DB/LLM 변경 없음. 운영 API 및 실제 브라우저 검수는 **미수행**이다.

Ops 첫 화면 후속 개선: Frontend `npm test` **42 passed**, `npm run format:check`와 `npm run build` **통과**. 두 화면의 강조 버튼/탭, 완료 필터와 주제 보존, 공개 보고서 hash 바로가기를 렌더 fixture로 확인했다. API/LLM 변경 없음. 실제 브라우저 검수는 미수행이다.

## RCA 첫 화면·Ops 최종 보고서 — 2026-09-30

main `40b68d3` 기반. Frontend에서 `npm run format:check`, `npm test`(**38 passed**), `npm run build` **통과**. 공개 참조가 있는 RCA/Ops의 hash 바로가기, 미발행 링크 미노출, Ops 제목/본문/기본 보고서·HTML escape 및 기존 Namespace/수치 표시 회귀를 확인했다. 실제 브라우저 상호작용과 운영 API 화면은 **미검증**이며 컴포넌트 렌더 fixture다. 별도 실제 프로세스 8건은 [Agent QA](../agents/QA.md)에 기록했다.

- **통과:** `frontend/`에서 `npm run format:check`, `npm test` **36 tests**, `npm run build`. 기간과 누적 GPU·시간 구분, 연결 GPU 대수, partial 사유의 상세 밖 노출, 실제 0/null/구 결과, cluster 보고서의 namespace 전용 표 숨김, 혼합 보고서에서 다른 주제 설명 보존을 검사했다.
- **통과:** 로컬 합성 API·Vite build와 브라우저에서 기존/운영측/개발측의 동일 보고서 표시, 0%와 공유 구간 산출 불가, 기간·고유 GPU 대수·누적 시간 설명 확인. 390px viewport에서 문서 가로 넘침 없음(스크롤바 제외 clientWidth=scrollWidth=375), 브라우저 오류 없음. 검사 뒤 뷰포트·기존 관점을 복원했다.
- **통과:** Backend HTML의 GPU·시간 설명·한계 우선 표시와 CSV의 `7.9864155557420515,GPU-hours` 원시 정밀도 보존 검사. 실제 로컬 서비스 공개 경로는 [Agent QA](../agents/QA.md)를 따른다.
- **미수행:** 운영 배포. 합성 화면 검사는 운영 데이터·LLM 품질 검수가 아니다.

---

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

## 2026-10-01 RCA 한국어·중복 제거·부족 근거 분류

기준 `529df747173e76a908ff2d56b1ac3688c4a3e648`, 브랜치 `fix/rca-report-korean-labels`. 로컬 파일 변경 단계.

- **통과:** `frontend/`에서 `npm run format:check`, `npm test` **77 tests**, `npm run build`. esbuild subprocess의 샌드박스 EPERM은 권한 있는 검사 재실행으로 해소했다.
- **통과:** 렌더 fixture로 본문 분석 한계 1회 표시(접힌 원본 제외), 구 결과 한계 보존, 부족 항목 네 분류와 확인 방향, R01 이름·필수 근거, D05 이름, `non_korean_claim`·`invalid_limitations` 한국어 설명을 확인했다. 기존 공개/미공개·실패·빈 응답·partial·0/미확인 검사도 통과했다.
- **통과:** Python 검사에서 Frontend `rcaLabels.json` 전체와 Worker 사전이 일치함을 확인했다. 표기 재사용만 변경했으며 API·결과 구조와 근거 원본을 보존한다.
- **미검증:** 실제 브라우저 시각 검사, 운영 배포 후 화면, 실제 LLM/Grafana 신규 결과, 원격 CI. 저장된 본문의 영어 문장은 자동 번역하지 않는다. 운영 저장 결과 읽기 전용 재현은 [Agent QA](../agents/QA.md)에 기록했다.

- **문서 검사:** 전체 `python tools/check_links.py`는 기존 미추적 `_review_current/`·`_codex_dcgm_publish/` 안의 경로 7건으로 실패했다. 두 기존 검토용 폴더만 제외해 같은 `check()`를 실행하면 변경 문서를 포함한 링크 검사는 통과한다. 이 폴더들은 수정하지 않았다.

### PR 제출 전 최신 main 호환 검사 — 2026-10-01

- `origin/main` `212e2bc4d18270fd8b46212eeb67f3db6757aaf6`의 최신 보고서 강조 카드 변경과 충돌 없이 결합했다.
- **통과:** `frontend/`에서 `npm run format:check`, `npm test` **82 tests**, `npm run build`. 기존 77건에 최신 main의 ReportHistory 검사 5건이 추가됐다.
- Python 제품 코드는 최신 main에서 바뀌지 않아 위 Agent QA의 269 passed/17 skipped 검증 범위를 유지한다. PR 대상 밖의 기존 미추적 파일은 포함하지 않는다. 원격 CI·배포는 이 로컬 검사와 별도다.
