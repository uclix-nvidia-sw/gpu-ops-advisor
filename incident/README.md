# Incident 모듈 · Go · 계약 1.3

[13번 설계서](../output/deliverables-20260917-v1.3/13_Incident_모듈_설계서.md)를 구현한 독립 프로세스입니다.

**Grafana → Incident → PostgreSQL outbox → Job Controller → RCA Agent** 흐름을 사용합니다. Backend는 같은 DB에서 사건과 연결된 RCA job을 읽고, 메모·검토·사건 상태 변경만 Incident로 전달합니다. 인증은 현재 범위에서 제외했습니다.

## 실행

Go 1.26와 PostgreSQL을 사용합니다. Docker가 없어도 저장소 루트에서 각각 별도 터미널로 실행할 수 있습니다.

```powershell
./backend/scripts/dev-db.ps1
./job-controller/scripts/dev-server.ps1
./incident/scripts/dev-server.ps1
./backend/scripts/dev-server.ps1
```

기본 Incident 주소는 `http://127.0.0.1:8091`입니다. Backend 개발 스크립트에 `DSX_INCIDENT_URL=http://127.0.0.1:8091`을 추가했습니다. 이미 실행 중인 Backend에는 다음 재시작 때 반영됩니다. 이 모듈 구현 과정에서 기존 Backend/JC 프로세스는 강제로 재시작하지 않습니다.

세 모듈의 `DATABASE_URL`은 같은 DB를 가리켜야 합니다. 공통 스키마에 `004_incident.sql`을 추가했으며 Incident가 자신의 마이그레이션과 운영 정책 등록을 수행합니다. JC의 queue 테이블은 변경하지 않습니다. cluster_registry는 Backend 초기화/운영 등록을 사용합니다.

`.env.example`은 환경 변수 예시이며 자동으로 읽지 않습니다. 기본값은 개발용 정책입니다. 운영 설정은 `INCIDENT_CONFIG_FILE`에 `config.example.json` 형식의 파일 경로를 지정합니다. 동일 Grafana source에 설정을 변경할 때는 `INCIDENT_APPLY_CONFIG=true`를 한 번 명시하고 모든 Incident 복제본의 설정을 맞춥니다. 이전 설정의 프로세스는 503으로 차단됩니다. 적용 후 해당 환경 변수는 false로 되돌립니다.

정책 revision의 내용은 불변입니다. 조사 목적·증거 필드 등을 바꿀 때 새 revision ID를 사용합니다. JC 주소만 바꿀 때는 `INCIDENT_JOB_CONTROLLER_URL`을 사용할 수 있지만 이것도 운영 설정 revision 변경에 해당합니다.

## Grafana 연결

Grafana Contact point에서 Webhook, HTTP POST, URL을 **Incident의 `/webhooks/grafana`**로 설정합니다. 로컬 테스트 URL은 `http://127.0.0.1:8091/webhooks/grafana`입니다. Grafana가 다른 서버/컨테이너라면 그 환경에서 도달 가능한 Incident 주소를 사용해야 합니다. Backend 주소로 보내지 않습니다.

[Grafana 공식 Webhook payload](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/webhook-notifier/)의 기본 JSON을 받습니다. 커스텀 payload를 쓰면 alerts 배열과 각 alert의 필수 필드를 유지해야 합니다. 본문에 있는 externalURL 등 외부 링크를 서버가 방문하지는 않습니다.

필수 자식 필드: `fingerprint`, `status=firing|resolved`, timezone이 있는 `startsAt`, `labels.alertname`, `labels.cluster_id`. resolved는 유효한 `endsAt`도 필요합니다. namespace 라벨이 있으면 해당 Namespace 범위, 없으면 해당 cluster 전체 범위입니다. `cluster_id`는 활성 cluster_registry 항목이어야 합니다. cluster 라벨명은 설정으로 변경할 수 있습니다.

개발 기본 분석 정책은 **alertname=GPUAlert**만 처리하며, 목적은 R01/R02입니다. 실제 Grafana 규칙의 alertname에 맞춰 analysis_policies를 등록하세요. 등록 정책이 없는 알람도 사건으로 저장하지만 `analysis_policy_unconfigured` 사유로 RCA는 만들지 않습니다. Grafana의 일반 Test notification도 필수 라벨이 없으면 invalid로 보존되며 실제 사건을 만들지 않습니다.

GPU UUID는 입력 라벨에 있을 때만 보존합니다. node/pod/namespace 등 확인된 대상만 사용하며 누락된 식별자를 생성하지 않습니다.

## 수신·증거·전달 정책

- alerts 배열 전체를 한 DB 트랜잭션으로 처리합니다. 잘못된 자식은 위치·이유·원문으로 보존하고 다른 정상 자식은 접수합니다. 정상 JSON인데 alerts 배열 자체가 잘못된 요청은 receipt와 함께 422, JSON 문법/인코딩 오류는 400, 본문·배열 한도 초과는 413입니다.
- 같은 source/원본 body SHA-256은 같은 receipt를 반환합니다. alert별 원장도 source/cluster/fingerprint/startsAt/payload hash로 중복을 막습니다. 정확한 webhook 바이트는 raw_body, 조회용 원문은 raw_payload에 보존합니다. PostgreSQL JSON이 표현하지 못하는 NUL이 포함된 자식은 encoded JSON으로 보존합니다.
- truncatedAlerts가 있으면 `grafana_truncated_alerts` 경고를 반환합니다. 받지 못한 알람을 정상/해제로 추정하지 않습니다.
- 사건 키는 알람 생명주기와 실제 대상에 연결됩니다. heartbeat 수준의 반복 수치·summary 변경으로 evidence revision이나 RCA를 늘리지 않습니다.
- 등록 정책의 evidence_labels/evidence_annotations 또는 policy revision이 달라진 적격 firing만 새 증거 revision과 RCA outbox를 만듭니다. 기본 의미 있는 필드는 severity/error_code이며 실제 운영 정책에 맞춰 지정합니다.
- 24시간보다 오래된 알람, 아직 미래인 알람, resolved 또는 closed 사건은 보존만 합니다. 허용된 시계 오차보다 미래인 timestamp는 invalid입니다. 기간·한도는 설정할 수 있습니다.
- 사건 state와 alarm_status는 분리됩니다. Grafana resolved는 alarm_status만 바꾸고 사건을 resolved/closed나 장비·업무 회복으로 자동 판정하지 않습니다. 같은 생명주기의 늦은 firing은 resolved를 되돌리지 않습니다.
- snapshot에는 완전한 RCA input과 원본 alert·정책을 고정하고 hash를 저장합니다. JC는 input·snapshot·hash를 실제 검증합니다. source_key는 `incident:<id>:evidence:<version>:profile:<revision>`입니다.
- RCA는 snapshot의 `alert`를 원본 증거로 읽으며 이미 저장된 snapshot을 변환하거나 hash를 다시 쓰지 않습니다. 실제 RCA 실행까지의 회귀 검증은 [Agent 통합 테스트](../agents/tests/test_e2e.py)의 Grafana webhook 경로에 포함됩니다.
- 5초 전달 루프는 자기 outbox 행만 잠그고 같은 envelope로 재전송합니다. JC 응답 유실·기한 경과 시 receipt를 먼저 확인합니다. JC가 내려가 있어도 Webhook은 로컬 영속 저장 후 202를 반환합니다. 마감 뒤 JC receipt 조회마저 실패하면 pending을 유지합니다.
- RCA Agent가 없으면 JC 접수는 queued입니다. 실제 GPU 조사·LLM 추론을 Incident가 수행하지 않습니다.

## API

| API | 설명 |
| --- | --- |
| POST /webhooks/grafana | 202 영속 접수, receipt_id/items/invalid_alerts/warnings |
| GET /internal/v1/incidents | scope(JSON), state, limit(1~100), cursor |
| GET /internal/v1/incidents/{id} | 사건·불변 evidence_versions·outbox/job 연결 |
| PATCH /internal/v1/incidents/{id} | Backend 계약 envelope를 통한 메타데이터 변경 |
| GET /internal/v1/health/live | 프로세스 생존 |
| GET /internal/v1/health/ready | DB·마이그레이션·운영 설정·전달 구성 준비 |

Backend의 PATCH `/api/v1/incidents/{id}`는 `memo`, `review_status=unreviewed|reviewing|reviewed`, `state=open|acknowledged|closed`를 받습니다. `If-Match`와 `Idempotency-Key`가 필요하며 같은 재전송은 최초 버전으로 처리합니다. 내부 envelope는 `{contract_version:"1.3",source_module:"backend",input:{...}}`입니다. resolved는 정상 관측에 따른 별도 회복 판정이 필요하므로 수동 PATCH로 허용하지 않습니다. 메모·검토 변경은 RCA 실행 부수 효과가 없습니다.

ready는 JC의 일시 장애 때문에 수신을 중단하지 않습니다. 전달 장애는 outbox 상태와 last_error로 확인하며, GUI의 분석 결과 완료 여부와 구분합니다.

## 검증·배포

```powershell
./incident/scripts/format.ps1
./incident/scripts/test.ps1 -E2E
```

E2E는 실제 PostgreSQL의 고유 임시 schema, 실제 JC HTTP 서버, 별도 포트의 실제 Backend 바이너리를 사용합니다. 실행 중인 개발 Backend/JC와 데이터·포트를 격리합니다. Grafana 서버 자체와 실제 RCA/LLM은 실행하지 않고 기본 Webhook payload 및 Worker 프로토콜로 연동을 검증합니다.

Docker가 있는 환경에서는 저장소 루트에서 다음 명령을 사용할 수 있습니다.

```powershell
docker build -f incident/Dockerfile .
docker compose -f backend/compose.yaml -f incident/compose.yaml up --build
```

이 PC에는 Docker가 없어 이미지 빌드/컨테이너 실행은 검증하지 않았습니다. [검증 기록](QA.md)을 참고하세요.
