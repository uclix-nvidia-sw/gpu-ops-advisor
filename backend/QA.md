# 2026-09-30 보고서 단위·한계 출력

## Ops 최종 보고서 HTML — 2026-09-30

main `40b68d3` 기반. 임시 소스 복사본의 Backend `go vet ./...`, `go test -race ./...`, `go build ./...` 및 새 격리 PostgreSQL의 `go test -tags=e2e ./tests -v -count=1 -timeout=5m` **통과**. 최종 narrative 제목/본문·fallback 상태의 HTML escape와 CSV 원래 수치 보존을 검사했다. 실제 Backend→JC→Ops→공개 HTML 검사는 [Agent QA](../agents/QA.md)에 기록했다. 운영 배포/실제 모델 품질은 **미검증**, DB migration/API 변경은 **해당 없음**.

- **통과:** Backend 디렉터리 기준 `go vet ./...`, `go test -race ./...`, `go build -o ../.local/backend-e2e ./cmd/server`. HTML 연결 GPU 고유 대수 이름·GPU·시간 설명·한계 우선 표시, HTML escape와 CSV 원시 단위·정밀도 보존을 검사했다.
- **통과:** `.local/report-usability/go_e2e.py`가 새 임시 PostgreSQL·loopback 포트·최신 Backend 바이너리로 `go test -tags=e2e ./tests -count=1 -timeout=10m` 실행 후 DB를 종료했다. 기존 운영 DB는 사용하지 않았다. Backend→JC→Ops namespace 공개·다운로드는 [Agent QA](../agents/QA.md)의 전체 검사에 포함됐다.
- **해당 없음:** API 접수·JC 계약·DB migration 변경. **미수행:** 운영 배포와 운영 다운로드 검수.

---

# Backend v1.3 검증 기록

## 2026-09-30 Namespace 보고서 실행·내보내기

**통과:** Backend Go vet/race/build, 격리 PostgreSQL의 전체 `-tags=e2e` 검사, 실제 Backend→JC→Ops 공개/HTML 다운로드. 즉시·정기 보고서 프로필 선택과 CSV 원래 수치/단위 유지·HTML 단위 변환을 확인했다. **미검증:** 운영 배포·실제 Grafana/LLM. 환경·명령·fixture 경계는 [Agent QA](../agents/QA.md)의 같은 날짜 실행·표시 개선 기록을 따른다.

## 2026-09-28 전체 Runbook 콘텐츠·일괄 등록

- **통과:** Backend에서 `go vet ./...`, `go test -race ./...`, `go build ./...`. 분리한 xid/sxid 폴더와 일반 Runbook을 합친 267건의 v1 구조·빈 호환성 발행 거부·잘못된 조건/계획/출처를 검사했다.
- **통과:** 새 격리 PostgreSQL에서 `go test -tags=e2e ./tests -v -count=1`. `TestFreshBackendWithoutDemoSeed`, `TestBackendE2E`, `TestRealJobController`와 기존 SXID 등록·검토·발행·회수 경로를 재검증했다.
- **통과:** [Agent E2E](../agents/QA.md)의 실제 일괄 등록 CLI로 신규 263건의 draft 저장·코드별 조회/hash·재실행 중복 등록 방지를 확인했다. Backend 기본 요청 한도를 유지하고 429의 Retry-After를 따랐다.
- **해당 없음:** Backend 실행 로직·DB 스키마 변경. 기존 Knowledge API를 그대로 사용하고 테스트 파일 검색 경로만 갱신했다.
- **미수행:** 운영 DB 등록·발행·배포. 실제 Grafana/Fleet/LLM 검증은 별도다.

Windows 대괄호 경로의 Go embed 문제 때문에 임시 소스 복사본에서 검사했으며 DB는 새 data directory와 localhost 포트로 시작한 뒤 종료했다. 등록 절차와 기존 ID의 새 revision 처리 방법은 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)에 기록했다.

## 2026-09-28 Runbook v1 DB 연계

- **통과:** Backend에서 `go vet ./...`, `go test -race ./...`, `go build ./...`. 실제 JSON 4건의 초안 형식·빈 호환성 발행 거부·잘못된 필드/조건/관측 계획/출처·legacy 호환을 검사했다.
- **통과:** 격리 PostgreSQL 16.9에서 `go test -tags=e2e ./tests -v -count=1`, `TestFreshBackendWithoutDemoSeed`, `TestBackendE2E`, `TestRealJobController`. 신규 Runbook 사례는 실제 SXID JSON의 등록·검토·빈 호환성 승인 거부·수정 후 재검토·발행·코드 namespace 검색·발행본 불변·회수·새 revision을 확인했다.
- **통과:** 별도 [Agent E2E](../agents/QA.md)에서 오류별 JSON 3건의 CLI/API 생명주기·멱등 재전송과 RCA 소비까지 검사했다. 기존 migration만 사용하며 DB 구조 변경은 없다.
- **미수행:** 운영 DB 적재·운영 Fleet/Grafana/LLM 검증·배포. fixture compatibility는 운영 적용 승인이 아니다.

Windows의 대괄호 포함 checkout 경로는 Go embed를 방해해 소스를 임시 경로로 복사해 빌드했다. 새 PostgreSQL data directory와 localhost 포트에서 검사하고 종료했다. 재현 설정은 [CI](../.github/workflows/tests.yml), 등록 절차는 [DB 등록 안내](../rcca-agent/runbooks/DB-WORKFLOW.md)를 따른다.

## 2026-09-18 운영 초기화 회귀 검사

실제 PostgreSQL의 빈 schema와 실제 Backend 실행 파일을 `DSX_MIGRATE=true`, `DSX_SEED=false`로 기동했다. 필수 C07 한도만 생성되고 예제 클러스터 없이 readiness 200이 되는 것을 확인했다. 미등록 클러스터 보고서 요청은 422로 거부하며, 이후 HTTP 등록 → 목록·범위 조회를 검증했다. 등록의 입력 검증, 멱등 재전송, 중복 충돌, 감사 기록 1건, 기존 비활성 클러스터 보존을 확인했다. 기존 C07 config/enabled/version은 재초기화해도 유지한다. 누락·비활성·유효하지 않은 한도와 미적용 스키마는 readiness 503을 유지한다.

Go 단위 테스트, vet, 서버 빌드 및 Backend E2E 전체(`TestFreshBackendWithoutDemoSeed`, `TestBackendE2E`, `TestRealJobController`) 통과. 운영 Kubernetes에 수정 이미지를 배포한 검증은 아직 수행하지 않았다.

## 2026-09-17 검증

2026-09-17 / Windows / Go 1.26.2 / native PostgreSQL 16.9 / Docker 미사용.

- Go 단위 테스트 2개: scope/시간 경계, 달력 DST gap/fold·23시간 완료일·월말·월요일 시작 주간: PASS.
- go vet 및 서버 빌드: PASS.
- 실제 HTTP + PostgreSQL E2E 1개, 아래 8개 subtest: PASS.

| 시나리오 | 확인 |
|---|---|
| v1.3 경계 | 인증 테이블 미생성·제거 API 404·등록 scope/중복/기간 422 |
| JC 접수/명령 | 커밋 후 응답 유실·동일 키/정규화 입력 복구·본문 충돌·queued·report 한정·receipt 우선·cursor |
| 최종 결과 | 후보 미노출·JC 발행 참조만 조회·Backend 재시작·HTML 이스케이프·CSV 수식 방어 |
| 지식 | 원자적 receipt·재전송·검토 hash 불일치 차단·발행본 불변 |
| 일정 복구 | 두 Backend 경합·단일 occurrence·outbox·마감 후 JC receipt로 accepted 복구·revision 보존 |
| 달력 backlog | catchup_window/max_catchup·중복 기간 missed/canonical 참조·일시 정지 후 pending 전달 |
| 모델/조치 | 불변 revision·라우팅 유지·사용 모델 비활성화 차단·secret_ref·용량 변경 거부·미인증 조치자 |
| 조회/장애 | dashboard/assets/workloads/quality/incident/procedure 조회·JC 미연결 503 |

실제 브라우저에서도 Frontend → Go → PostgreSQL 일정 생성 → 일시 정지 → 실행 시각 변경(revision 1→2→3)을 확인했습니다. 확인 중 등록 폼 시간대 누락을 수정했습니다. 검증용 일정 `16660c00-c133-4535-9804-91117afc3591`은 일시 정지 상태로 남겨 자동 실행을 막았습니다.

기존 로컬 DB에 보존 migration을 적용하고 새 Backend로 readiness 성공을 확인했습니다. frontend Vitest 3개·TypeScript/Vite build도 통과했습니다.

한계: JC/Incident/두 Agent는 실제 서비스가 연결되지 않았습니다. E2E의 JC는 PostgreSQL 커밋을 수행하는 계약 fixture이며 제품 JC 구현이나 실제 RCA/보고서 계산·LLM 실행 검수가 아닙니다. 실시간 관측, 운영 부하·배포·백업복원·원격 LLM 장애 시험은 NOT RUN입니다.
