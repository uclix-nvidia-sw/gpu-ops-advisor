# Go Job Controller v1.3

Backend와 같은 PostgreSQL을 사용하는 독립 프로세스입니다. 보고서는 Backend, RCA는 Incident만 접수합니다. Agent는 JC의 pull API로 작업을 인수합니다. 사용자·Agent 인증은 현재 범위에서 제외했습니다.

## Docker 없이 실행

저장소 루트에서 각각 별도 터미널로 실행합니다.

```powershell
./backend/scripts/dev-db.ps1
./job-controller/scripts/dev-server.ps1
./backend/scripts/dev-server.ps1
```

기본 주소: PostgreSQL `127.0.0.1:55432`, JC `127.0.0.1:8090`, Backend `127.0.0.1:8080`. Backend 개발 스크립트가 `DSX_JOB_CONTROLLER_URL=http://127.0.0.1:8090`을 설정합니다. Frontend는 Backend에만 연결합니다. `.env.example`은 예시이며 자동으로 읽지 않습니다.

`DATABASE_URL`은 두 서버가 같은 DB를 가리켜야 합니다. JC가 공통 001/002와 큐 003, Worker 계약 006 마이그레이션을 적용합니다. Backend가 registry/설정 초기화를 담당하므로 신규 개발 DB에는 Backend seed도 실행해야 합니다. 별도 Agent나 LLM을 가짜로 띄우지 않습니다. Worker 0개라도 보고서는 202로 영속 접수되고 `worker_unavailable` 상태로 대기합니다.

## 구성과 동작

- `controller/`: 접수, FIFO/종류 간 교대 배분, Worker/lease, 결과 발행, 취소·재시도, 격리 복구, 읽기 API.
- `cmd/server`: HTTP 서버와 2초 복구 루프. `cmd/admin`: 종료 근거를 기록하는 격리 해제 CLI.
- `../shared/contract`: 공통 DTO·정규화·hash. `../shared/migrations`: 유일한 SQL 원본.
- `../backend/tests/job_controller_test.go`: 실제 Backend + JC + PostgreSQL 통합 검사.

capacity → job → attempt 순서로 DB 트랜잭션을 잠그며, 인수·결과 발행·명령 receipt는 커밋 후 응답합니다. 동일 source 키/정규화 hash는 기존 job, 다른 입력은 409입니다. 저장된 candidate만으로 성공하지 않고 `published_result_id`가 지정되어야 공개됩니다. 발행된 candidate와 Incident evidence snapshot은 DB에서 수정·삭제를 금지합니다.

작업마다 입력, deadline, execution/query/parser/criteria/result schema/knowledge/model 참조를 고정합니다. 기존 작업의 프로필과 예산은 재시도나 설정 변경으로 초기화하지 않습니다. Worker 재등록에는 시작별 새 boot UUID를 사용합니다. 이전 boot는 retired이며 재사용하지 못합니다.

## 운영 설정

### RCA 입력 계약 전환 준비

RCA 접수는 1.3/1.4를 구분하고, 보고서는 1.3을 유지합니다. 새 job은 `versions.input_contract`를 고정하며 Worker가 등록한 `supported_contract_versions`에 맞게 배분합니다. 생략한 구 Worker는 1.3만 지원합니다. 호환 Worker 없는 1.4 job은 `queued/worker_unavailable`로 보존하며 다른 실행 가능한 작업을 막지 않습니다. 결과 공개 때도 job과 후보의 입력 계약 일치를 검사합니다. 상세 입력·오류는 [API](API.md)를 따릅니다.

**현재 제품 RCA Worker의 1.4 목적 선택·이력·의미 검증은 후속 작업입니다.** 이 변경은 JC-01/02와 JC-03의 JC 공개 경계이며, 1.4 생산자 전환이나 전체 실행 완료를 뜻하지 않습니다.

006은 `workers.supported_contract_versions`에 기본 `["1.3"]`인 열과 제약만 추가하고 `jc_migrations=2`를 기록합니다. 기존 job·snapshot·hash·예산은 변경하지 않습니다. JC `Prepare()`가 적용하며 readiness가 새 migration을 확인합니다. Incident 004/005 migration과 별개로 적용할 수 있습니다.

공유 DB 적용은 담당자가 승인된 배포에서 수행합니다. 모든 JC 복제본을 호환 버전으로 교체한 뒤 Worker·결과 소비자 검증을 완료하고 신규 생산자를 전환합니다. 롤백은 신규 1.4 접수를 먼저 멈추고 pending/queued/running을 지원 소비자로 처리하거나 보존합니다. 1.4 입력을 1.3으로 변환하거나 열·PVC를 삭제하지 않습니다. 구 JC가 1.4를 배분하지 않도록 1.4 작업이 남은 동안 호환 JC를 유지합니다.

### 실행 한도

`JC_CONFIG_FILE`에 `config.example.json` 형식의 파일 경로를 지정합니다. 기본 개발 프로필은 종류별 슬롯 1, 공유 슬롯 1, Worker 슬롯 1, lease 30초, heartbeat 5초, 최대 3회, 총 토큰 예산 3,000, attempt 예산 1,000입니다. 재시도는 지수 backoff(최대 300초) + 1초 미만 jitter를 적용합니다.

**예산은 보수적인 예약 방식**입니다. claim 때 attempt 예산 전체를 누적 차감하고 잔여분을 환급하지 않습니다. 실측 LLM 사용량을 뜻하지 않습니다. Agent는 반환된 `budget.attempt_limit` 안에서 모델 호출을 직렬 실행해야 합니다. JC만으로 외부 모델 서버의 실제 토큰 소비를 강제할 수는 없습니다.

query/parser/criteria의 개발 기본 revision은 `unconfigured`입니다. Agent와 연결할 때 실제 배포 revision을 설정해야 합니다. model snapshot은 Backend routing의 참조이고 미설정이면 null입니다. 설정 누락을 Agent가 실제 분석 성공으로 처리하면 안 됩니다.

`JC_APPLY_CONFIG`는 미지정 시 `true`이며, 시작할 때 전달한 설정을 DB에 적용합니다. DB config revision과 다른 구 프로세스는 readiness·claim·heartbeat·complete를 503으로 막으므로 모든 JC replica를 같은 설정으로 교체해야 합니다. 한도 감소는 기존 실행을 죽이지 않고 점유가 새 한도 아래로 내려갈 때까지 신규 인수만 중단합니다. 기본 실행 프로필은 `local-v1` 하나이며 시도당 32,768, 작업 전체 98,304의 예산을 사용합니다. 예산 변경은 새로 접수되는 작업에 적용하고, 기존 작업은 접수 시 저장한 실행 설정 스냅샷을 사용합니다. 자동 적용을 끄려면 `JC_APPLY_CONFIG=false`를 명시합니다.

## 추론 격리와 취소

lease 만료나 boot 교체 시 원격 추론 종료를 증명할 수 없으면 reservation을 quarantined로 유지합니다. 해당 job과 점유된 공유/종류/Worker 슬롯은 다시 사용하지 않습니다. HTTP timeout만으로 슬롯을 반환하지 않습니다. 현재 검증된 원격 최대 수명 설정은 없으므로 운영 확인 해제만 제공합니다.

```powershell
cd job-controller
$env:DATABASE_URL = 'postgres://dsx:local-development-only@127.0.0.1:55432/dsx?sslmode=disable'
go run ./cmd/admin -job <job-uuid> -attempt 1 -evidence "모델 서버 request ID ... 종료 확인, 확인 시각 ..."
```

실제로 모델 서버의 종료를 확인한 뒤 실행합니다. CLI는 근거와 audit event를 저장합니다. 운영 설정 파일을 쓰는 환경에서는 동일 `JC_CONFIG_FILE`도 지정해야 합니다. 실행 중 취소는 먼저 플래그를 기록하며, Agent의 종료 확인 또는 운영 확인 후 cancelled가 됩니다. 종료 불명인 취소는 running + cancellation_pending_remote_termination으로 남고 deadline이면 expired가 되더라도 슬롯은 격리를 유지합니다.

## 검사와 이미지

```powershell
./job-controller/scripts/format.ps1
./job-controller/scripts/test.ps1 -E2E
./backend/scripts/test.ps1 -E2E
```

통합 테스트는 실제 PostgreSQL의 고유 임시 schema를 만들고 그 schema만 정리합니다. Agent/LLM은 프로토콜 드라이버만 사용하며 실추론은 하지 않습니다. [검증 기록](QA.md), [API 예시](API.md)를 참고하세요.

Docker가 있는 환경에서는 저장소 루트에서 `docker build -f job-controller/Dockerfile .` 또는 `docker compose -f backend/compose.yaml up --build`를 사용합니다. compose의 JC는 내부 네트워크에만 두고 호스트 포트를 열지 않습니다. 이 개발 PC에는 Docker가 없어 이미지 빌드/컨테이너 구동은 검증하지 않았습니다.
