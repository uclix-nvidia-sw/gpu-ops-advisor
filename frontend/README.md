# GPU Ops Advisor Frontend

React + TypeScript + Vite. [v1.3 명세](../docs/specs/frontend/07_프론트엔드_개발명세서.md)의 Backend 계약 변경에 맞춰 실제 Go API 연결을 갱신했습니다. 사용자/권한 DTO, Assistant, 직접 RCA 실행, GUI 용량 변경은 제외했습니다.

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
- 대시보드: GET `/dashboard`, 작업·서비스 상태. 최근 작업 아래에 내부 서비스 준비 상태를 작은 요약으로 표시한다. `/service-status`의 available은 '응답 정상', unavailable은 '응답 확인 실패', 누락/알 수 없는 상태는 '미확인'이다. Backend의 readiness 확인이며 Agent·MCP·실제 작업 성공을 보장하지 않는다.
- 자산/Pod: 저장된 identity 및 관측·매핑 스냅샷. 실시간 소스가 없으면 미확인입니다.
- 사건/RCA: 저장 사건·분석 조회, Incident 메타데이터 PATCH. 새 RCA는 Incident에서 생성합니다.
- 보고서: JC 접수 응답 후 job 이동, 저장된 final의 주제별 수치·산출 불가 이유·수집 상태 표시, HTML/CSV 다운로드. GPU–Pod 연결 관측 시간과 독점 할당량을 구분합니다.
- 일정: Backend의 평탄한 calendar 입력·report_spec, revision 수정·일시 정지·occurrence 조회.
- 지식/모델: 불변 revision·검토/발행, rca/report 모델 라우팅, secret_ref만 저장.
- 모델 등록: 기본 화면에서 API 주소(`/chat/completions` 제외)·모델명·인증을 지정합니다. 인증은 배포된 API 키 사용 또는 인증 없음이며 키 원문은 저장하지 않습니다. revision·정밀도 등만 선택 설정입니다. 연결 검사는 선택한 인증으로 실제 추론을 요청합니다. 질의·Agent별 모델 지정 후 새 작업부터 해당 revision을 두 Worker가 사용합니다. [키 배포와 확인](../docs/model-connection.md).
- 변경 요청: 멱등 키를 생성하고 응답 유실 시 같은 본문/키/최초 버전을 재사용합니다.
- HTTP NodePort 접속: 요청 fingerprint는 브라우저 SHA-256 구현으로, UUID는 `crypto.getRandomValues`로 생성합니다. HTTPS 전용 `crypto.subtle`·`crypto.randomUUID`에 의존하지 않습니다. 기존 SHA-256 fingerprint와 재시도 키는 유지합니다.

분석 실행에는 배포 환경의 JC·Incident·Agent·관측/LLM 연결이 필요합니다. 의존 서비스 미연결로 요청이 실패하면 오류를 표시하고 가짜 완료·결과를 만들지 않습니다. JC가 접수했지만 Agent가 없으면 queued 상태를 유지합니다. 테스트 fixture는 앱에 연결하지 않습니다. 검증 환경과 실제 연결 범위는 아래 QA를 따릅니다.

```powershell
npm run test
npm run build
npm run format:check
```

[검증 기록](QA.md) · [Backend API](../backend/API.md)

## RCA 디버깅 화면

목록과 조사 상세는 저장된 target.alertname과 CPC·노드·Pod 등 발생 대상을 먼저 표시하고 사건/작업 ID를 보조 정보로 유지한다. 알람 이름이 없으면 제목·관측 증상을 사용하며 모두 없으면 미확인으로 표시한다. 이름에서 원인이나 심각도를 추정하지 않는다. 알람·사건·검토 상태는 별도 상자로 강조한다. 사건 원본 필드는 한국어 이름과 원래 키를 제공하며 항목 이름에 마우스를 올리거나 클릭/Enter로 설명을 확인할 수 있다. 제품 표기는 GPU Ops Advisor로 통일한다.

사건 목록/상세에서 alarm_status(발생/해제), state(열림/확인/종결), review_status를 분리한다. 상세의 연결된 RCA 작업에서 실행 상태·시도 이력 및 공개 결과로 이동한다. 새 RCA 실행·취소·재시도 기능은 추가하지 않는다.

RCA 결과는 공개 상태, 결과 품질, 종료 사유, 근거 충분성, 분석 경로, LLM 응답 사용 기록을 구분한다. llm_usage.calls는 원격 요청의 완전한 감사 기록이 아니므로 0건을 연결 실패나 미호출 확정으로 표시하지 않는다. 내부 evidence는 종료 후 일괄 저장되며 실행 중에는 서버 stage만 표시한다.

공개 결과의 evidence_refs를 기존 GET /evidence/{id}로 사용자가 8건씩 불러온다. 동일 job/attempt인지 검사하고 조회 실패는 별도 재조회로 제공한다. D-query별 구간·datasource UID·완전성·표본 수·안전한 오류 코드를 표시하며 구간 표본을 합산하지 않는다. 내부 조사 기록과 원본 결과는 펼쳐 볼 수 있다. 현재 API가 제외하는 input 쿼리 원문과 공개되지 않은 후보·webhook/outbox 기록은 제공하지 않는다. 화면은 운영 Grafana/LLM 검증을 대신하지 않는다.
