# 검증 기록 · 2026-09-17

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
