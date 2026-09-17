# Incident 검증 기록

검증일: 2026-09-17. Go 1.26.2 / Windows / PostgreSQL 16 개발 인스턴스. 사용자·Agent 인증 제외.

- Incident `go test ./...`, `go vet ./...`, 서버 바이너리 빌드 통과.
- 실제 PostgreSQL + 실제 JC HTTP + 별도 포트의 실제 Backend 바이너리 E2E 5개 시나리오 통과.
- Backend 기존 단위 테스트·vet·전체 E2E 회귀 검사 통과.
- 개발 Incident 서버 `127.0.0.1:8091` 실행, `/internal/v1/health/ready` 200 및 pending_outbox=0 확인.
- 이 작업에서 추가·수정한 소스/설정/문서의 CRLF 확인.

## E2E 범위

1. 혼합 배치에서 유효/잘못된 자식 각각 보존, 동일 배치 receipt 복구, 12개 동시 재전송 중복 방지.
2. JC가 RCA를 커밋한 뒤 응답을 잃어도 전달 마감 이후 receipt로 같은 job 복구. Worker가 없을 때 queued/worker_unavailable. 테스트 Worker가 실제 claim으로 완전한 RCA input과 snapshot을 수신하며 누락된 GPU UUID를 생성하지 않음.
3. 수치 heartbeat는 새 RCA를 만들지 않고 등록된 error_code 변경은 새 증거 revision·job 생성. snapshot DB 수정 차단. resolved와 늦은 firing은 회복/재분석으로 오인하지 않음.
4. 실제 Backend에서 사건·RCA 연결 조회, Incident로 PATCH 전달, 동일 명령/이전 If-Match 재전송, 변경된 명령 409. acknowledged/closed 처리와 메모 변경은 분석 실행을 만들지 않음.
5. JC 장애 중 webhook 영속 접수, receipt 조회 불가 시 pending 유지, 미접수 마감 건의 failed 처리. 미등록 정책·오래된 알람·잘못된 시각·NUL 포함 자식 보존, 정상 형제 알람 처리, 본문 한도 413.

테스트는 임시 schema와 임시 Backend 프로세스를 사용하고 종료 시 해당 자원만 정리합니다. 기존 개발 Backend/JC 프로세스는 재시작하지 않았습니다. 현재 실행 중인 Backend는 Incident URL이 아직 적용되지 않아 service-status에서 Incident 미연결로 표시됩니다. 갱신된 `backend/scripts/dev-server.ps1`로 다음 기동 시 8091을 연결합니다.

실제 Grafana Contact point 설정, Grafana 서버 발송, 운영망 연결, 실제 RCA Agent/LLM 추론은 검증 범위 밖입니다. 공식 기본 Webhook JSON을 HTTP로 전송해 검증했습니다. Docker가 없어 컨테이너 이미지 빌드와 compose 실행은 확인하지 않았습니다.
