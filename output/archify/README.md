# GPU Ops Advisor · Architecture / Sequence

[상단 탭 통합 뷰어](gpu-ops-advisor.html) · [Architecture 단독](gpu-ops-advisor.architecture.html) · [Sequence 단독](gpu-ops-advisor.sequence.html) · [Sequence 코드 근거](sequence-evidence.md)

2026-09-21 재구성. 기준 revision: `5f59ac6ba4afe8fa982f2d03d7d18113acdd44ac`.

## Architecture: 두 Agent와 공통 의존성

GPU RCA Agent와 GPU Ops 보고서 Agent를 **독립 실행 모듈**로 분리했다. Incident → Job Controller의 RCA 접수와 Backend → Job Controller의 보고서 접수를 각각 표시했다. 두 Agent 각각의 Job Controller·Grafana MCP·LLM endpoint·PostgreSQL 연결을 모두 선으로 표현했다. PostgreSQL은 보고서 파일과 분리된 명시적 DB 노드다.

기존 도면은 두 Agent를 하나로 묶고 핵심 의존 관계까지 카드 설명으로 옮겨, 전체 실행 구조를 읽기 어려웠다. 이번 도면은 19개 구성요소와 48개 방향선을 사용한다. CPC 수집 모듈과 CSC 수신·저장 모듈을 각각 분리했다. 핵심 연결을 보존하는 상세 구조도이므로 Archify `standard` 배치를 사용한다.

### 실제 호출 방향

Job Controller가 Agent의 HTTP endpoint를 직접 호출하는 구조가 아니다. 각 Worker가 자신의 kind로 `POST /claims`를 요청하고, Job Controller가 큐·용량·lease 조건을 확인한 뒤 작업을 반환한다. 그림의 Agent → JC 선은 claim과 complete 요청을 요약한다. claim 응답도 반대 방향 점선으로 표시했다. 반복 heartbeat·취소·상태 API는 해당 제어 연결에 포함되며 각각 별도 선으로 늘리지 않았다.

녹색 ①~④는 Grafana 알림 → Incident 접수 → RCA Worker 인수 → 후보 저장의 주요 처리 단계를 가리킨다. 숫자는 별도 서비스나 모든 API의 시간 순서가 아니다. 후보 저장 뒤 Worker가 complete를 요청하면 JC가 유효 attempt·token·lease·deadline·취소·schema/hash를 검증하고 공개 참조를 확정한다. Backend는 공개된 결과를 조회한다.

### 연결별 코드 근거

| 연결 | 동작과 근거 |
|---|---|
| CPC → 관측 수신·저장 | [hall architecture](../architecture-modules-20260917-v1.3/hall%20architecture.svg), [CPC-2 수집 검증](../../docs/evidence/CPC-2_수집검증_20260915.md). 현장 GPU/Fleet/Exporter/KSM → Alloy → CSC 전송 |
| Grafana → 관측 저장소 | [전체 환경 설명](../architecture-modules-20260917-v1.3/README.md). 등록 Mimir/Loki 데이터소스 조회 방향 |
| Grafana → Incident → JC | [Webhook ingest](../../incident/service/ingest.go), [outbox 전달](../../incident/service/delivery.go). 사건·snapshot 저장 후 RCA 접수 |
| Frontend → Backend → JC | [Frontend API](../../frontend/src/lib/api.ts), [즉시 보고서 접수](../../backend/internal/api/proxy.go), [정기 일정/outbox](../../backend/internal/api/schedules.go). Backend에서 /jobs/report 호출 |
| 각 Agent → JC | [공통 Worker](../../shared/python/src/agent_common/worker.py), [claim](../../job-controller/controller/claim.go), [complete](../../job-controller/controller/attempt.go). 두 Worker가 각각 pull하며 완료를 요청 |
| 각 Agent → Grafana MCP → Grafana | [RCA NAT 설정](../../rcca-agent/configs/workflow.yml), [보고서 NAT 설정](../../ops-agent/configs/workflow.yml), [MCP 배포 설명](../../grafana-mcp/README.md). streamable HTTP /mcp와 읽기 전용 데이터소스 도구 |
| 각 Agent → LLM endpoint | [RCA workflow](../../rcca-agent/src/rcca_agent/workflow.py), [보고서 workflow](../../ops-agent/src/ops_agent/workflow.py), [공통 LLM 클라이언트](../../shared/python/src/agent_common/llm.py). OpenAI 호환 /chat/completions |
| Incident → PostgreSQL | [ingest](../../incident/service/ingest.go), [delivery](../../incident/service/delivery.go). 사건·receipt·snapshot·outbox |
| Backend → PostgreSQL | [Backend 서버](../../backend/internal/api/server.go), [일정](../../backend/internal/api/schedules.go). 공개 결과 조회, 설정·일정 저장 |
| JC → PostgreSQL | [작업 접수](../../job-controller/controller/submit.go), [claim](../../job-controller/controller/claim.go), [완료](../../job-controller/controller/attempt.go). 작업·attempt·lease·공개 참조 |
| 두 Agent → PostgreSQL | [read_context / save](../../shared/python/src/agent_common/store.py). 입력 읽기와 후보·근거 저장 |

LLM 연결은 구성된 endpoint를 사용하는 의존성이다. 매 실행에서 반드시 추론을 호출한다는 의미는 아니다. LLM 설정과 가용 근거·예산에 따라 호출을 생략할 수 있다. RCA는 등록된 추가 조사 선택과 근거 해석에 사용하고, 보고서는 코드로 계산한 사실의 설명에 사용한다.

RCA는 호환 발행 Runbook과 사건 snapshot을 읽는다. 보고서는 기간 사건·공개 RCA 결과를 읽으며 새 RCA를 실행하지 않는다. 두 Agent의 공통 코드는 각 Worker 내부에서 재사용된다.

### 경계와 보조 저장

- **CPC-1 … CPC-N:** 기존 현장 수집. 이번 개발 범위 밖이지만 전체 데이터 출처로 표시했다. CPC-2 직접 scrape 근거를 CPC-1/N의 동일 배포 증거로 확대 해석하지 않는다.
- **CSC:** 기존 관측·추론 기반과 이 레포의 Backend·Incident·JC·두 Agent·MCP·PostgreSQL을 포함한다. 역할 경계이며 단일 Kubernetes 클러스터나 조직 소유권·보안 격리를 확정하지 않는다.
- **Client:** 브라우저에서 실행되는 Frontend. 정적 파일 제공과 API 중계는 [CSC의 Frontend 배포](../../frontend/nginx.conf)가 담당한다.
- **보고서 HTML/CSV:** [Worker](../../shared/python/src/agent_common/worker.py)가 [별도 파일 경로](../../shared/python/src/agent_common/artifacts.py)에 저장한다. PostgreSQL과 별개이며 카드에 명시했다.
- **관측 Object Storage:** 업무 PostgreSQL과 별개의 관측 장기 저장 계층이다. 실제 연결·보존 정책은 배포 확인 대상이다.
- 제품 로그인·인증은 개발 범위에서 제외한다. 외부 서비스의 API 자격 증명과 제품 사용자 인증을 혼동하지 않는다.
- 관측 tenant와 CPC 필터는 별개다. hall 문서의 Mimir tenant `cpc-1` + `cluster_id`, CPC-2 Loki tenant `cpc2` + `cluster=cpc2` 기록은 실제 배포에서 재확인해야 한다.

업무 요청·응답은 양방향으로 표시하고, heartbeat와 상태·취소·설정 CRUD 등 반복 보조 API는 해당 연결에 포함했다. 업무 요청·작업 배분·두 Agent의 분석 의존성과 DB 연결을 중심으로 한 구성도다. 교차선은 서로 연결되지 않는다.

## CPC 수집과 CSC 수신·저장 상세

CPC 수집을 한 상자로 묶지 않고 **Fleet Intelligence Agent, DCGM Exporter, Host Exporter, kube-state-metrics, Grafana Alloy**로 분리했다. CSC에서도 **Envoy Ingest Gateway, Grafana Mimir, Grafana Loki, Object Storage, Grafana**를 각각 표시했다. 기존 Incident·Backend·JC·두 Agent·MCP·LLM·PostgreSQL·Client의 역할과 기능 연결은 유지한다.

CPC 경계는 사이트마다 반복되는 수집 모듈 구성이다. 모든 CPC의 실제 설치가 같다는 뜻이 아니다. [hall architecture](../architecture-modules-20260917-v1.3/hall%20architecture.svg)를 구성 기준으로 사용하고, [CPC-2 검증 기록](../../docs/evidence/CPC-2_수집검증_20260915.md)으로 확인 수준을 구분했다.

| 시작 → 도착 | 화살표 의미 |
|---|---|
| Fleet → Alloy | OTLP HTTP로 GPU·호스트 메트릭 및 상태·이벤트 로그 전송 |
| Alloy → DCGM Exporter / KSM | HTTP GET /metrics 수집 요청 |
| DCGM Exporter / KSM → Alloy | GPU 메트릭 / Node·Pod 상태·요청량·UID 메트릭 응답 |
| Alloy ↔ Host Exporter | hall의 Host Exporter 수집 관계. 실제 설치·scrape 구성은 미확인으로 표시 |
| Alloy → CSC Envoy Gateway | remote_write, OTLP, Loki push로 CPC 관측 데이터 전송 |
| Gateway → Mimir | /api/v1/push 및 /otlp/v1/metrics의 지표 전달 |
| Gateway → Loki | /loki/api/v1/push의 로그 전달 |
| Grafana → Mimir / Loki | PromQL / LogQL 조회 요청 |
| Mimir / Loki → Grafana | 메트릭 / 로그 조회 결과 반환 |
| Mimir / Loki → Object Storage | hall의 메트릭 블록 / 로그 청크·인덱스 저장 관계. 실제 bucket·연결·보존 정책은 미확인 |

CPC-2에는 Alloy의 DCGM·KSM 직접 scrape 기록이 있다. 기존 Prometheus는 운영 환경에 남아 있지만 GPU Ops 중앙 전송 경로에서 제외됐으므로 그 전송 중계 노드로 추가하지 않았다. Kubernetes API를 이용한 대상 발견·메타데이터 보완은 관리 관계이며 관측 데이터 전송선과 구분한다. Fleet 로그는 마지막 Alloy 재배포 이후 최신 Loki 도착 여부를 별도로 확인해야 한다.

**실선 화살표는 요청·데이터 전송·저장 방향**, **반대 점선 화살표는 데이터 또는 처리 결과 응답 방향**이다. 양방향인 관계에는 반대 방향 화살표를 모두 그렸다. 업무 API 응답의 반복 라벨은 공통 범례로 설명하고 선 자체는 생략하지 않았다. 데이터 push·관측 저장의 단방향 화살표는 표시한 데이터의 이동 방향이며, 전송 계층의 ACK까지 없는 단방향 네트워크라는 뜻이 아니다.

JC → Agent 점선은 Worker의 claim에 대한 작업 응답이다. JC가 Agent 실행 endpoint를 직접 호출한다는 뜻이 아니다. DB → 각 모듈 점선은 조회 데이터·SQL 처리 결과의 반환이며 DB의 자율 push가 아니다. MCP와 LLM도 호출 요청과 반환 결과를 구분했다.

전체는 **19개 모듈과 48개 방향선**이다. 화살표가 교차하는 곳은 연결점이 아니다. 상세 모듈과 왕복 관계를 보존하기 위해 Archify standard를 사용한다.

## Sequence 재검토

Sequence 탭 안의 선택 메뉴에서 아래 다섯 화면을 전환한다. 요청과 반환 방향, DB 저장, 두 Agent 각각의 MCP·LLM 호출을 표시했다. 단계별 분할이며 새 서비스가 추가된 것이 아니다.

| 화면 | 내용 | 생성 영수증 |
|---|---|---|
| [RCA 접수](gpu-ops-advisor.html#sequence) | Grafana → Incident → DB·outbox → JC | [receipt](sequence-delivery-receipt.json) |
| [RCA 실행](gpu-ops-advisor.html#sequence-rca-execution) | Worker claim, Runbook·MCP·LLM, 후보 저장과 공개 | [receipt](sequence-rca-execution-delivery-receipt.json) |
| [즉시 보고서 요청·조회](gpu-ops-advisor.html#sequence-report-request) | Client → Backend → JC, 완료 후 상태·결과·다운로드 | [receipt](sequence-report-request-delivery-receipt.json) |
| [정기 보고서 접수](gpu-ops-advisor.html#sequence-report-schedule) | Backend 내부 일정·outbox 전달 | [receipt](sequence-report-schedule-delivery-receipt.json) |
| [보고서 실행](gpu-ops-advisor.html#sequence-report-execution) | 보고서 Worker, MCP·LLM, 파일·후보 저장과 공개 | [receipt](sequence-report-execution-delivery-receipt.json) |

즉시 보고서는 요청 의도를 DB에 저장한 뒤 JC를 직접 호출하고, 정기 보고서는 outbox로 전달한다. API 응답 캐시와 별개로 Agent에는 실행별 관측 캐시가 있다. hit는 근거 재사용, miss는 MCP 조회이며 관측 실패 시 DB fallback은 없다. 제품 인증은 범위 제외로 유지한다.

실행 도면은 필요한 조회의 cache miss와 조건부 LLM 사용 예다. 조건·재시도·heartbeat 병행은 카드에 기록했다. 보고서 Worker의 파일 저장과 Backend가 DB 공개 결과로 생성하는 다운로드 응답도 구분했다. 세부 코드와 비동기 순서의 한계는 [Sequence 근거](sequence-evidence.md)를 참조한다.

## 검증

- [Architecture 생성 영수증](delivery-receipt.json): **9/9 standard 통과, 오류 0, 교차 경고 10건**, 소스 참조 35개 확인. 경고는 양방향 선을 관계별로 집계한 교차 진단이다. 노드 관통·모호한 선 중첩·레이블 간격·가독성 진단은 0건이다. showcase 무경고 통과로 표기하지 않는다.
- [Architecture 브라우저 기록](gpu-ops-advisor.architecture.visual-check.json): 1440×900, 1600×1000, 1920×1080, 2048×1320에서 화면 넘침 없음.
- [Architecture 캡처](gpu-ops-advisor.architecture.visual-check.html), [이미지 검토 기록](review-receipt.json): 1440×900과 2048×1320의 밝은/어두운 테마 4개를 육안 확인했다. 노드·카드 가림 없음.
- 다섯 Sequence 생성 영수증: 각각 **9/9 showcase, 오류·경고 0**. 각 HTML과 같은 이름의 `.visual-check.json`에 브라우저 검사를 기록했다. 네 화면 크기에서 넘침 없음. 최종 1440×900 밝은 테마와 2048×1320 어두운 테마 캡처 10개를 직접 검토했다.
- [탭 검증](tabs-check.json): 네 화면 크기에서 Architecture와 다섯 Sequence 선택·전환, 직접 링크, 파일 직접 열기와 내부/외부 넘침 확인.
- 제품 코드 변경이나 새로운 서비스 통합 시험은 수행하지 않았다. Viewer 내보내기는 별도 시험하지 않았다.
- 본문은 한국어다. Archify 고정 Viewer UI와 생성 HTML의 `lang`은 영어 기본값이다.

## 파일과 재검증

공유 시 `gpu-ops-advisor.html`, `gpu-ops-advisor.architecture.html`, `gpu-ops-advisor.sequence.html` 및 `gpu-ops-advisor.sequence-*.html`의 시나리오 4개를 같은 폴더에 둔다. 총 7개 HTML이며 `visual-check` 파일은 공유에 필수가 아니다. 각 단독 다이어그램은 자체 포함 HTML이다.

[Architecture 원본](gpu-ops-advisor.architecture.json) · [Sequence 원본](gpu-ops-advisor.sequence.json)

Architecture는 Archify `validate architecture`와 `deliver architecture`에 `--quality standard --repo-root <repo>`를 지정한다. Sequence는 `--quality showcase`를 사용한다. 생성 HTML에 `visual-check --json`을 실행한다. 생성 HTML 자체는 수정하지 않는다.

탭 재검증: `node output/archify/check-tabs.mjs`. 설치된 Archify의 Chrome 도구를 재사용하며 필요 시 `ARCHIFY_SKILL_DIR`과 `CHROME_PATH`로 경로를 지정한다. 검사용 루프백 서버는 실행 중에만 열린다.
