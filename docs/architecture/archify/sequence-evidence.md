# Sequence 재검토 근거

기준 revision: `cd2273be1af3d1ab4056ed13284d36d9beac2b51` · 2026-10-02.
[통합 뷰어](gpu-ops-advisor.html#sequence)의 Sequence 탭에서 일곱 시나리오를 선택한다. Architecture는 기존 19개 모듈·48개 연결과 CPC·CSC 수집 경계를 보존했다.

## 시나리오와 시간 순서

| 화면 | 범위 | 주요 근거 |
|---|---|---|
| [RCA 접수](gpu-ops-advisor.sequence.html) | Grafana → Incident → DB 트랜잭션 → 202. 별도 outbox 루프 → JC 접수 | [ingest.go](../../../incident/service/ingest.go), [delivery.go](../../../incident/service/delivery.go) |
| [RCA 실행](gpu-ops-advisor.sequence-rca-execution.html) | RCA Worker claim → 입력·Runbook → MCP·LLM → 후보 저장 → complete → 공개 | [worker.py](../../../shared/python/src/agent_common/worker.py), [RCA workflow](../../../rcca-agent/src/rcca_agent/workflow.py) |
| [즉시 보고서 요청·조회](gpu-ops-advisor.sequence-report-request.html) | Client → Backend → 요청 의도 저장 → JC → 202. 실행 완료 후 별도 상태·결과·다운로드 요청 | [proxy.go](../../../backend/internal/api/proxy.go), [read.go](../../../backend/internal/api/read.go), [export.go](../../../backend/internal/api/export.go) |
| [정기 보고서 접수](gpu-ops-advisor.sequence-report-schedule.html) | Backend 내부 일정 루프 → occurrence·outbox → 별도 전달 루프 → JC | [schedules.go](../../../backend/internal/api/schedules.go) |
| [보고서 실행](gpu-ops-advisor.sequence-report-execution.html) | 보고서 Worker claim → 기간 입력 → MCP·LLM → 파일·후보 저장 → complete → 공개 | [Ops workflow](../../../ops-agent/src/ops_agent/workflow.py), [artifacts.py](../../../shared/python/src/agent_common/artifacts.py) |
| [보고서 수집 상세](gpu-ops-advisor.sequence-report-collection.html) | query+CPC 계획·의존성·예약 예산 → 독립 MCP 병렬 실행 → 배치 종료·취합 | [collection.py](../../../ops-agent/src/ops_agent/collection.py), [parallel.py](../../../shared/python/src/agent_common/parallel.py) |
| [웹 디버깅 추적](gpu-ops-advisor.sequence-debug.html) | job trace → attempt별 근거 목록·상세 → 고정 Runbook 본문 | [trace.go](../../../backend/internal/api/trace.go), [JobDebug](../../../frontend/src/components/JobDebug.tsx), [TraceView](../../../frontend/src/components/TraceView.tsx) |

각 화면의 숫자는 그 화면 안의 순서다. 실선은 호출·저장, 반대 방향 점선은 응답이다. SQL 묶음과 MCP 도구 탐색·조회는 관련 호출을 요약한다. 전체 화면을 하나의 동기 호출 스택으로 읽지 않는다.

RCA outbox 전달은 접수 트랜잭션의 COMMIT 이후 독립적으로 실행된다. Grafana에 202를 보내는 것과 outbox 루프 시작 사이의 엄격한 선후를 보장한다는 뜻은 아니다. 202는 분석 결과가 아니라 접수 결과다. JC가 작업을 저장하면 해당 kind의 Worker가 인수할 수 있으며 outbox accepted 갱신 완료가 claim의 선행 조건은 아니다.

JC 내부 경로의 공통 prefix는 `/internal/v1`이다. 짧은 화살표의 `/jobs/rca`, `/jobs/report`, `/claims`는 이 prefix를 생략했다. heartbeat·complete는 `/internal/v1/jobs/{job_id}/heartbeat`, `/internal/v1/jobs/{job_id}/complete`를 가리킨다. 보고서 export 전체 경로는 `/api/v1/reports/{report_id}/export`다.

## 접수와 영속성

- **RCA:** 신규이며 분석 적격인 알림의 정상 접수 경로를 그렸다. Incident는 사건·snapshot·outbox와 webhook receipt를 저장한다. 동일 source/body hash의 재전송은 receipt를 재사용하고, 충돌은 별도로 처리한다. outbox 전송 실패는 backoff와 receipt 조회로 조정한다.
- **즉시 보고서:** Backend의 `manual_report_intents`에 `manual:<Idempotency-Key>`의 고정 envelope와 deadline을 저장한 뒤 JC를 **직접 호출**한다. 같은 키·본문은 기존 의도를 재사용하며 본문 충돌은 409다. 정기 보고서용 outbox에 넣는 경로가 아니다.
- **정기 보고서:** Backend가 도래한 일정을 잠그고 발생 건·outbox·다음 실행 시각을 같은 트랜잭션으로 저장한다. 별도 pending 전달 루프가 JC에 제출한다. 전송 실패는 backoff, 마감·거절 시 receipt 확인으로 기존 접수 여부를 확인한다. 별도 Scheduler 서비스는 없다.

DB receipt와 intent는 멱등성·복구용 영속 기록이다. API 응답 캐시로 부르지 않는다.

## Worker, MCP, LLM, 공개 결과

등록된 Worker가 JC에 claim을 요청하는 pull 방식이다. JC는 job·attempt·lease·slot을 확보한 뒤 claim 정보를 반환한다. 등록 과정과 빈 큐 polling 반복은 도면의 시작 전제다. [claim.go](../../../job-controller/controller/claim.go), [submit.go](../../../job-controller/controller/submit.go).

[Store](../../../shared/python/src/agent_common/store.py)는 RCA의 사건 snapshot·호환 Runbook, 보고서의 고정 기준 시각에 따른 기간 사건·공개 RCA를 읽는다. 보고서가 새 RCA 분석을 실행하는 것은 아니다.

Agent는 [RCA NAT 설정](../../../rcca-agent/configs/workflow.yml)과 [Ops NAT 설정](../../../ops-agent/configs/workflow.yml)의 Grafana MCP `/mcp`를 통해 데이터소스 도구를 호출한다. Grafana·Mimir·Loki의 관측 인프라 연결은 Architecture에서 확인한다. 실행 시퀀스는 Agent의 도구 호출과 반환 경계를 표시한다.

[Observation](../../../shared/python/src/agent_common/observation.py)은 실행별 메모리 캐시를 가지며 `(query_id, period.start, period.end)`가 같으면 근거를 재사용한다. miss일 때 MCP를 조회한다. 실패한 관측 조회를 PostgreSQL로 대체하는 fallback은 없으며 unavailable/partial 품질 상태로 다룬다. DB 입력 조회는 별도 단계다.

RCA는 [Orchestrator](../../../rcca-agent/src/rcca_agent/workflow.py)의 승인 계획과 [병렬 관측](../../../rcca-agent/src/rcca_agent/observation_agents.py), 코드 충분성 판정, 최대 1회 재조사, 도구 없는 [Synthesis](../../../rcca-agent/src/rcca_agent/synthesis.py)와 최대 1회 교정을 사용한다. 적용 Runbook과 기존 증거가 충분하면 MCP·원인 Synthesis를 생략한다. 최종 보고서 구성·조건부 문장 편집은 별도 단계다.

보고서는 query+CPC+기간별 계획을 먼저 검사하고 준비된 task를 예약 예산·동시성 상한 안에서 배치 실행한다. 같은 metric의 완전한 동일 응답 재사용과 O08 단독 namespace의 D01/D08→D06 의존성을 유지한다. 완료된 캐시만 복사하며 실행 중 mutable Observation은 공유하지 않는다. 배치가 모두 끝난 후 미사용 예산을 재배분한다. 비교 기간은 별도 task다. RCA와 bounded runner만 공유하며 보고서 추가 관측 라운드는 구현하지 않았다.

보고서 수치는 코드로 계산한다. [report.py](../../../ops-agent/src/ops_agent/report.py)는 기본 다섯 섹션을 만들고 조건이 맞으면 LLM으로 검증된 문장 참조·순서를 선택한다. 확정 실패·미설정에도 기본 보고서를 보존한다. 원격 종료 불명은 공통 fail/격리 계약을 따른다. [LLM 클라이언트](../../../shared/python/src/agent_common/llm.py).

웹 디버깅 도면의 API에는 `/api/v1` prefix를 생략했다. trace는 고정 입력·발행 revision·출처·공개 참조를 연결하고, evidence는 job+attempt로 제한해 목록·상세를 조회한다. 저장된 요청 인자·응답·품질만 표시하며 실시간 trace나 미저장 모델 원문을 생성하지 않는다. 미공개 후보 본문·lease 자격 증명은 반환하지 않는다. Runbook은 실행 당시 revision과 현재 지식 상세를 구분한다.


Worker는 실행 중 별도 heartbeat task를 병행하고, 저장 직전 heartbeat로 lease·취소 상태를 재확인한다. Store는 유효 attempt·lease·취소·deadline 조건을 검사하며 후보·근거를 저장한다. complete의 전송 재시도는 동일 후보·hash를 사용한다. JC의 [완료 처리](../../../job-controller/controller/attempt.go)가 유효성·schema/hash 등을 검사한 뒤 `published_result_id`를 확정한다. 후보 저장과 공개 완료는 별개다.

## 보고서 파일과 최종 응답

보고서 Worker는 HTML/CSV를 파일 경로에 저장하고 경로·checksum을 결과에 반영한다. 이 저장은 DB와 별개다. 현재 Backend export는 Worker 파일을 직접 전달하지 않고 **DB에 공개된 결과 body로 HTML/CSV를 생성**한다.

Client의 POST는 202로 끝난다. 상태 조회, 공개 보고서 조회, 다운로드는 각각 별도 요청이다. B·C 구간은 보고서 실행·공개 후 성공 응답 예이며, 완료 callback이나 서버 push가 아니다. 실행 중에는 상태를 반복 조회할 수 있고, 공개 전 결과·다운로드에는 미완료 상태 처리가 있다. [Frontend API](../../../frontend/src/lib/api.ts), [Backend read](../../../backend/internal/api/read.go), [Backend export](../../../backend/internal/api/export.go).

## 범위와 검증

제품 로그인·인증은 개발 범위에서 제외한다. claim token과 lease 검사는 작업 소유권 검증이며 사용자 인증으로 그리지 않았다. 외부 서비스 자격 증명도 제품 인증과 별개다.

실제 비동기 경계인 DB outbox 전달과 Worker heartbeat를 표시했다. 코드에서 근거를 확인하지 못한 Kafka·외부 trace collector·완료 이벤트 broker는 추가하지 않았다. 재시도·조건 분기·캐시 hit는 카드에 설명하고 도면은 정상 완료의 주 경로를 유지한다.

일곱 Sequence는 각각 Archify showcase 9/9, 오류·경고 0으로 생성했다. 네 desktop 크기 브라우저 검사와 밝은/어두운 실제 캡처 검토 결과는 [검토 영수증](review-receipt.json)에 기록한다. 상단 탭·시나리오 선택은 [탭 검사](tabs-check.json)로 확인한다. 제품 코드 실행 시험이나 export 기능 시험을 의미하지 않는다.
