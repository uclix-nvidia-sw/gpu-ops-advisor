# Job Controller 검증 기록

## 2026-10-02 저장과 heartbeat 잠금 경합

**통과:** `origin/main` 5ddfe21 기반 로컬 변경. JC/Backend/Incident 각각 Go vet/race/server build 및 격리 PostgreSQL Backend·Incident E2E. Agent 전체 315건에서 실제 JC와 Store로 2초 lease 중 2.6초 저장 지연·heartbeat 갱신·최종 공개·취소/만료/시도 교체 rollback·잠금 대기 후 만료된 heartbeat 409를 확인했다. non-key 잠금으로 FK KEY SHARE와 공존하며 JC 변경끼리의 배타성과 capacity 잠금은 보존한다. 상세 환경은 [Agent QA](../agents/QA.md)의 같은 날짜 대량 저장 기록을 따른다. **미수행:** 운영 반영·격리 해제·원격 CI. DB migration·lease 설정 변경 없음.

## 2026-09-30 보고서 전용 criteria 프로필

**통과:** JC/Backend/Incident Go vet/race/build, 격리 PostgreSQL Backend E2E와 두 Worker E2E. report-namespace-v1은 report만 허용하며 criteria 1.2를 새 작업에 고정한다. RCA 접수의 사용 거부·전역 unconfigured 유지·정기 보고서 재전송 멱등성을 확인했다. **미검증:** 운영 설정 반영·배포. 환경·명령·fixture 경계는 [Agent QA](../agents/QA.md)의 같은 날짜 실행·표시 개선 기록을 따른다.

## 2026-09-23 Incident·JC 통합 PR 최종 검사

Incident·JC 변경을 함께 포함한 별도 PR 작업 트리 `C:/Temp/gpu-ops-incident-jc-pr`에서 재검사했다. 아래 결과는 앞선 기록의 CGo/race 미검증 항목을 보완한다.

- **통과:** `shared`, `incident`, `job-controller`, `backend` 각각 `go vet ./...`, `go test -race ./...`, `go build ./...`. Go 1.26.2, `CGO_ENABLED=1`, 임시 폴더의 SHA256 검증된 w64devkit GCC를 사용했다.
- **통과:** Incident와 Backend 각각 `go test -tags=e2e ./tests -v -count=1 -timeout=5m`. 새 PostgreSQL 16.9의 `127.0.0.1:51009/incident_test`와 테스트별 임시 schema만 사용하고 종료했다. 이 작업 트리에는 검증 복사본 전용 `TestReviewIncident14`가 없으며 저장소에 포함된 검사만 실행했다.
- **통과:** 문서 링크 검사와 변경 diff 공백 검사.
- **미검증:** 실제 Grafana 발송·운영 시각 계약, 제품 RCA Worker의 1.4 실행·목적 선택·결과 의미 검증, 운영 배포. 에피소드 1.4 전달 검사는 계약 수신 fixture, JC 배분·공개 검사는 실제 JC와 Worker 프로토콜 드라이버를 사용한다.

## 2026-09-23 입력 계약 호환 구현

범위: JC-01/02 및 JC-03의 JC 공개 경계. Incident 소스·설정·004/005 migration은 이 작업에서 수정하지 않았다. RCA 목적 선택·공통 Python validator·조회 소비자 전환은 구현하지 않았으며 현재 제품 Worker는 1.3만 지원한다.

환경: Windows, Go 1.26.2, PostgreSQL 16.9. 저장소의 `[0]` 경로 때문에 Go embed가 실패해 Go/SQL 소스를 검증용 임시 경로에 복사했다. 샌드박스 restricted-token 및 한글 경로에서 PostgreSQL initdb가 실패한 뒤, 영문 경로의 격리 디렉터리에서 일반 실행 권한으로 새 PostgreSQL을 기동했다. 최종 DB는 `127.0.0.1:61743/jc_test`, 새 data directory와 테스트별 schema를 사용했고 검사 후 서버를 종료했다. 기존 개발·공유·운영 DB에는 적용하지 않았다.

| 검사·기준 | 결과와 범위 |
|---|---|
| shared/job-controller/backend/incident 각각 `go vet ./...`, `go test ./...`, `go build ./...` | **통과**. 검증 복사본의 각 모듈에서 실행 |
| Backend `go vet -tags=e2e ./tests` | **통과** |
| Backend `go test -tags=e2e ./tests -v -count=1 -timeout=5m` | **통과**. `TestRealJobController` 11개 하위 시험, Backend 회귀·빈 DB 기동 시험 포함 |
| Incident 동일 E2E 명령 | **통과**. 복사 당시 다른 세션의 개발 코드에 대한 소비자 회귀 검사만 수행, 원본 수정 없음 |
| JC-01 / T42·T48 일부 | **통과**. 1.3 필수 목적·revision, 1.4 제거 필드/최초 evidence/key/ref, 실제 snapshot 입력 불일치 거절, 동일 재전송·본문 충돌 |
| JC-02 / T55 | **통과**. capability 생략·정규화·동일 boot 변경 거절·빈/null/잘못된 버전·report 불일치·claim 덮어쓰기 거절. 구 Worker는 1.4 선두를 건너뛰어 1.3만 인수. 호환 Worker 없는 RCA가 report를 막지 않으며 호환 Worker 등록 후 교대 배분 |
| 기존 DB 업그레이드·반복 기동 / T48 일부 | **통과**. 006 적용 전 Worker 열과 job 버전 필드가 없는 상태를 구성, 두 번 Prepare 후 기존 Worker의 1.3 claim 확인. job input/hash/versions 불변, 응답에만 1.3 전달. 명시적 unknown/null/빈 버전은 구 Worker에 배분하지 않음 |
| JC-03 공개 경계 / T55 | **통과**. 1.4 후보의 버전 부재/1.3/unknown 거절, 일치하는 blocked 프로토콜 후보 공개와 동일 complete 재전송. 구 1.3 후보 필드 부재 허용. 기존 stale·취소·lease·동시 claim·예산·DB 장애 회귀 유지 |
| Worker capability 롤백·대기 마감 | **통과**. 새 boot가 1.3으로 등록되면 1.4 job은 worker_unavailable로 보존, 기존 boot 차단, 원래 deadline 적용 |
| `python tools/check_links.py`, 변경 파일 `git diff --check` | **통과** |
| `go test -race ./...` | **미실행/미검증**. JC에서 실행을 시도했으나 CGo 비활성화로 시작하지 못함. 일반 테스트 통과와 구분 |
| 실제 Python Worker/NAT/MCP E2E, 1.4 목적 선택 trace·assessments / T47 | **미실행/미검증**. 새 결과 의미 검증은 Worker 후속 개발 범위이며 이번 후보는 프로토콜 드라이버가 저장한 fixture |
| 실환경 Grafana·LLM 품질, 배포·CI | **미실행/미검증**. 로컬 변경·격리 DB 검사 단계, 커밋·push·배포 없음 |

최초 새 E2E는 테스트 드라이버가 한 attempt에 여러 후보를 삽입해 기존 UNIQUE 제약에서 실패했다. 미발행 후보 한 건의 body/hash를 바꾸어 버전 거절을 검사하도록 시험만 수정한 뒤 전체 Backend/Incident E2E가 통과했다. 로그는 로컬 `.local/jc-validation/e2e.log`에 보존했다. 공개된 후보를 수정하지 않는다.

운영 전환은 [README의 전환 순서](README.md#rca-입력-계약-전환-준비)를 따른다. T48의 전체 생산자 전환/롤백과 T47/JC-03의 Worker 의미 검증까지 완료된 것은 아니다.

## 2026-09-17

환경: Windows, Go 1.26.2, PostgreSQL 16.9(네이티브 55432), Node 24. Docker 없이 수행했습니다. 사용자·Agent 인증은 제외했습니다.

## 통과한 검사

- Backend `go test ./...`, `go vet ./...`, 서버 빌드.
- JC `go test ./...`(패키지 컴파일), `go vet ./...`, server/admin 빌드.
- Backend `go test -tags=e2e ./tests -count=1`: 기존 Backend 회귀 검사와 실제 JC 연동 검사 모두 통과.
- Frontend `npm run build`, `npm test`(기존 3개), 변경 TSX/TS Prettier 검사.
- `git diff --check`, 작업 파일 CRLF 확인.

실제 Backend + JC HTTP 서버와 PostgreSQL을 연결한 핵심 E2E 9개 시나리오:

1. Worker 없이 접수, JC 커밋 뒤 응답 유실 재전송, 입력 충돌, 취소 receipt 재전송.
2. 같은 Worker의 20개 동시 claim 중 소유자 1개, candidate hash 검사, 성공 재전송, Backend 결과 공개, 발행 결과 수정 차단.
3. 취소 우선 시 late complete 거절, heartbeat 취소 전달, 종료 확인 후 cancelled.
4. lease 만료 격리, 운영 근거 해제, 이전 attempt 결과 거절, boot 교체와 이전 boot 등록 차단, 3회 누적 예산 소진.
5. 종류별 FIFO, 상대 Worker 부재 시 진행, RCA/report 교대. RCA 고정 snapshot과 다른 분석 프로필 접수 거절.
6. Backend 일정 발생 → 실제 JC 커밋 → 응답 유실 → 전달 마감 후 receipt 조회로 accepted 복구, job 중복 없음.
7. 공유/종류/Worker 한도 2→1 감소 시 실행 작업 2개 유지, 신규 인수 제한, 구 config revision 거절.
8. 종료 불명 취소의 격리 유지 및 근거 확인 후 종료; 저장된 재시도 가능 실패의 수동 retry·receipt·예산/attempt 보존.
9. 닫힌 DB pool에서 claim·heartbeat·complete 모두 503으로 중단.

통합 테스트는 별도 임시 schema만 생성·정리합니다. Agent 부분은 결과 후보를 저장하고 Worker 프로토콜을 호출하는 테스트 드라이버이며 실제 LLM 분석은 수행하지 않았습니다. Docker 이미지 빌드·다중 호스트 배포·실제 원격 모델의 종료 확인은 이 PC에서 검증하지 않았습니다.

## 브라우저 검증

기존 5173 프론트엔드 → 8080 Backend → 8090 JC → 개발 PostgreSQL 연결에서 확인했습니다.

- 새 보고서 요청이 실제 job `f8276550-88b7-4ba6-94a4-415827b70c97`로 접수됨.
- 실행 대기 / 미발행 / Agent 연결 대기 사유 표시.
- 화면에서 사유를 입력해 취소 요청 후 취소 완료로 전환; 완료 후 처리 중 안내와 취소 버튼이 사라짐.
- 백엔드 연결 화면에 Go Backend 연결됨, PostgreSQL 준비 완료, Job Controller 연결됨 표시.
- 사건·알림(Incident)은 아직 미연결이며 Report/RCA Agent도 실행하지 않음. 테스트 작업은 취소 상태로 보존하고 기존 정기 일정의 일시 정지를 유지함.

브라우저는 `/settings/backend` 연결 확인 화면으로 남겨 두었습니다.
