# RCA·보고서 Worker v1.3

`11_RCA_Agent_모듈_설계서.md`, `12_보고서_Agent_모듈_설계서.md`와 두 문서가 참조하는 공통 계약 03/04/14를 기준으로 구현했습니다. 폴더 이름은 요청대로 **rcca-agent**, **ops-agent**이며 JC의 kind는 각각 `rca`, `report`입니다.

`runaiRCA`에서는 `agent/app/llm.py`의 연결 방식과 `agent/app/config.py`의 LLM 설정만 참고했습니다. 후속 요청에 따라 Dockerfile의 dependencies/build/runtime 구조도 맞췄습니다. 그 저장소의 조사·보고서·지식·업무 로직은 가져오지 않았습니다.

## 구성

| 경로 | 역할 |
| --- | --- |
| `rcca-agent` | Incident snapshot, 호환 Runbook, 네 등록 procedure, R01~R09 평가 |
| `ops-agent` | O01~O11 수집 계획·결정적 계산·공개 RCA 인용·보고서 |
| `shared/python` | JC Worker, LLM 전송, NAT MCP 연결, 정규화·공통 산식·결과 검사·저장·파일 |
| `grafana-mcp` | 공식 Grafana MCP v1.4.2, Prometheus/Mimir·Loki 읽기 도구 |
| `agents` | 공통 배포 프로필, Compose, 설치·테스트 스크립트, QA |

`agents/`는 제품의 두 Worker가 함께 사용하는 설정·테스트·실행 스크립트·문서를 담고, 실제 공통 실행 코드는 `shared/python/`에 있습니다. [.claude/rules/agents.md](../.claude/rules/agents.md)는 이 제품 코드를 수정하는 코딩 에이전트용 개발 지침입니다.

각 Worker는 독립 프로세스/이미지이고 공유 코드는 패키지입니다. 별도 업무 큐·접수 API·일정 루프·장비 조작·RCA 직접 요청은 없습니다. JC register → claim → heartbeat → candidate/evidence 저장 → complete로 실행합니다. 한 프로세스에서 한 작업씩 처리하며 JC가 전역 슬롯을 제어합니다.

## Grafana 시간 형식과 LLM 오류 진단

Grafana MCP 1.4.2의 Prometheus 시간 파서는 마이크로초 시각(예: `2026-09-21T02:34:41.713295Z`)을 거부할 수 있습니다. Worker는 Prometheus 탐색·조회 요청에서만 UTC 밀리초로 변환합니다. 탐색 시작은 올림, 종료는 내림하여 요청 범위를 넓히지 않으며, 원본 Incident snapshot·해시·증거 시각과 Loki 요청의 정밀도는 유지합니다.

LLM 통신 실패는 `LLM transport failed` 로그에서 `error_type`, `cause_type`, `stage`, 시도 번호, 경과 시간과 timeout을 확인합니다. HTTP 오류는 `LLM HTTP failed`와 상태 코드를 남깁니다. 이 진단 로그에는 API 키·프롬프트·응답 본문·원본 예외 메시지를 넣지 않습니다. 이후 연결 검사가 성공해도 기존 `inference_quarantined`는 자동 해제되지 않습니다. 원격 추론 종료를 확인한 뒤 [Job Controller 운영 해제 절차](../job-controller/README.md#추론-격리와-취소)를 따릅니다.

이 처리는 공유 Python 모듈에 있으므로 배포할 때 `rcca-agent`와 `ops-agent` 이미지를 함께 다시 빌드합니다.

## 모델 호출 timeout 조정

현재 저장소에서 출발점은 [chart values](../charts/gpu-ops-advisor/values.yaml)의 `llm.requestTimeoutSeconds`이며 기본값은 300초다. 이 값은 Worker의 `LLM_REQUEST_TIMEOUT_SECONDS`로 전달된다. 실제 요청 시간에는 작업의 남은 deadline도 적용되므로 이 값만 늘린다고 전체 작업 시간이 늘어나는 것은 아니다.

timeout은 모델에 보낸 요청의 통신 대기 제한, deadline은 분석 작업 전체의 마감 시간이다. Worker는 Agent 프로필의 `limits.deadline_seconds`와 JC가 준 `deadline_at` 중 먼저 끝나는 제한을 따른다. 모델 요청에 설정하는 timeout도 남은 시간보다 길게 잡지 않는다. 예를 들어 요청 timeout이 300초여도 전체 작업에 40초만 남았다면 그 요청 때문에 300초를 더 쓸 수 있는 것은 아니다.

1. [현재 협업 규칙](../docs/team-development.md)에 따라 변경 담당자를 지정하고 추가 리뷰가 필요하면 요청한다. 담당자는 두 Agent의 호출과 deadline·슬롯·격리 정책 영향을 검증하고, C-1/C-2·B에게 관련 내용을 공유한다.
2. 변경할 원본 설정, 실제 배포에 쓰는 override, 목표 시간, 적용·복구 순서를 작업 대화·Issue 또는 PR에 적는다. 외부 모델 서버·프록시·Ingress·LiteLLM 등을 사용하는 환경이라면 해당 설정을 소유한 별도 저장소·담당자도 기록한다. 이 저장소가 그 외부 설정까지 관리한다고 가정하지 않는다.
3. 사용자 요청·승인 범위에서 main 반영과 CI 발행을 마친 뒤 지정한 사람이 별도로 승인된 배포를 수행한다. 실제 Worker 설정값, RCA·보고서 작업의 ID·상태·소요 시간·결과 공개 여부와 슬롯 상태를 확인한다. HTTP 성공만으로 검증을 끝내지 않는다.
4. timeout 뒤 원격 추론의 종료가 불명확하면 슬롯이 격리될 수 있다. 이후 요청이 성공했다고 이전 격리가 해제된 것은 아니다. [추론 격리와 취소](../job-controller/README.md#추론-격리와-취소)에 따라 원격 종료를 확인한 뒤 처리한다.

연결이 끊겼다고 모델 서버의 계산까지 멈췄다고 단정할 수는 없다. 슬롯 격리는 “기존 계산이 끝났는지 모르니 이 자리를 바로 다른 작업에 내주지 말자”는 안전장치다. 설정을 바꾸거나 새 요청을 성공시키는 것과 기존 작업의 종료 확인은 별개다.

공유 기록 예시이며, 실제 적용 결과는 아니다:

```text
변경: 모델 요청 시간 상한 조정 (기존 값 → 합의한 값)
담당/리뷰(선택): 변경 담당자 / 요청한 경우 담당자, 미요청이면 표시
적용: 커밋·CI 실행·chart 버전, 대상 환경·namespace·release, values 위치
확인: 실제 설정값, RCA·보고서 작업 ID·상태·소요 시간, 결과·슬롯 상태
미확인: 실행하지 못한 검증, 후속 담당자와 기한
복구: 변경 전 버전·설정, DB 영향 여부, 복구 순서
```

## Windows 실행

저장소 루트의 PowerShell에서 실행합니다. Python 3.12와 NAT 1.5.0을 사용합니다.

```powershell
./agents/scripts/setup.ps1 -DownloadMcp
Copy-Item agents/.env.example agents/.env
```

`.env`에 기존 `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` 등을 설정합니다. `/chat/completions`를 호출하며 단계별 모델 설정, 300초 요청 상한, 기본 4096/설명 16384/insight 1024 토큰 설정을 지원합니다. 실제 호출은 JC attempt budget과 deadline으로 추가 제한합니다. 키는 코드·이미지에 넣지 않습니다. 모델/주소/키가 없으면 LLM 설명을 생략하고 유효한 결정적 결과는 유지합니다.

기본 실행은 포함된 `agents/config.example.json` 프로필을 그대로 사용하며 별도 파일 작성이 필요 없습니다. 기본 쿼리는 모두 `validated: true`이고 이 필드는 수집 차단 스위치로 사용하지 않습니다. Grafana MCP로 datasource 목록과 클러스터 label 값을 탐색해 UID/selector를 자동으로 결정합니다. 작업 시간 범위에서 `cluster_id`, `cluster`, `k8s_cluster_name`, `kubernetes_cluster`, `k8s_cluster` 순으로 첫 번째 값이 있는 라벨을 사용하고 작업 cluster ID와 정확히 일치시킵니다. 중복 후보·라벨 부재·조회 오류는 evidence와 Worker 로그에 원인을 남기며 전체 데이터로 범위를 넓히지 않습니다. 탐색은 작업별 캐시, 64회 기본 호출 한도, 응답 크기·타임아웃·작업 deadline 제한을 적용합니다.

Mimir tenant와 인증은 기존 Grafana 데이터소스 설정을 사용합니다. Worker에 Mimir/Loki 직접 주소·계정·UID를 주지 않습니다. Grafana 토큰에는 datasource 목록과 데이터 조회 권한이 필요합니다. `cpc-2`와 `cpc2` 같은 서로 다른 cluster ID는 자동으로 동일시하지 않습니다. 고급 환경의 명시적 매핑·생산자별 의미 계약이 필요하면 `AGENT_CONFIG_FILE`로 전체 프로필을 선택적으로 지정할 수 있습니다. C07 숫자는 예시이며 운영 확정값이 아닙니다.

```powershell
$env:GRAFANA_URL='https://your-grafana'
# GRAFANA_SERVICE_ACCOUNT_TOKEN은 로컬 환경에 설정
.local/mcp-grafana/mcp-grafana.exe -t streamable-http -address 127.0.0.1:8000 -enabled-tools datasource,prometheus,loki -disable-write -max-loki-log-limit 5000
```

별도 터미널에서 JC·DB를 먼저 준비하고 Worker를 실행합니다. `agents/.env`의 Docker 호스트명 대신 로컬 접속 주소를 사용합니다. `.env`는 CLI가 자동으로 읽지 않으므로 `uv run --env-file`을 사용합니다.

```powershell
$env:DATABASE_URL='postgresql://...@127.0.0.1:5432/dsx'
$env:JC_URL='http://127.0.0.1:8090/internal/v1'
$env:GRAFANA_MCP_URL='http://127.0.0.1:8000/mcp'
uv run --no-project --python .venv/Scripts/python.exe --env-file agents/.env -m rcca_agent.main
uv run --no-project --python .venv/Scripts/python.exe --env-file agents/.env -m ops_agent.main
```

위 두 Worker는 각각 별도 터미널에서 실행합니다. 한 건 처리 후 종료하려면 `--once`를 추가합니다. 운영 클러스터는 기존 Backend/JC의 `cluster_registry`에 등록되어 있어야 합니다. Agent는 등록·일정·사건 상태를 변경하지 않습니다.

## Docker 배포

루트 build context를 사용하고 `runaiRCA/agent/Dockerfile`과 같은 Python 3.12 다단계 빌드·가상환경 복사·UID 10001 실행 구조입니다.

```powershell
docker compose --env-file agents/.env -f agents/compose.yaml up --build -d
docker compose --env-file agents/.env -f agents/compose.yaml logs -f rcca-agent ops-agent grafana-mcp
```

Compose는 로컬 개발용 PostgreSQL·JC도 포함합니다. 기존 DB/JC 배포에 붙일 때는 두 Worker의 `DATABASE_URL`, `JC_URL` 및 volume을 맞춥니다. `GRAFANA_URL`은 기존 Grafana를 가리킵니다. 데이터소스 provisioning이나 운영 tenant를 임의로 변경하지 않습니다. 보고서 파일은 `agent-artifacts` volume에 저장됩니다.

이 환경에서는 사용자의 안내대로 Linux Docker 엔진 실행을 중단했습니다. **컨테이너 빌드/기동은 검증하지 않았고**, 실제 서버/Worker 연결은 Windows 프로세스 E2E로 검증했습니다.

## 결과·관측 계약

- 결과 본문 `result_schema_version=1.1`, 현재 JC의 candidate 봉투 `schema_version=1.3`을 구분합니다. Go `encoding/json`과 호환되는 SHA-256을 사용하며 실제 JC complete에서 재검증합니다.
- 지표는 instant range-vector query로 원본 표본 시각을 보존합니다. 기간을 chunk로 나누고 계산에서 경계 중복·공백·최대 유효시간을 처리합니다. Loki는 행 제한 도달 시 `partial`, 실패는 `unavailable`, 빈 결과는 `empty`입니다.
- scope/namespace/대상/기간은 코드가 조립·검사합니다. LLM에는 쿼리 ID만 전달하며 임의 PromQL/LogQL/SQL/쉘이나 저장·완료 함수는 노출하지 않습니다.
- 보고서는 REPEATABLE READ에서 data cutoff, Incident, 공개된 RCA ID/hash, 실제 조치 기록을 고정합니다. RCA 원인 수준은 인용한 결과 수준을 유지합니다.
- LLM 설명은 검증된 사실 ID 선택으로 제한하고 저장된 `value_refs`로 렌더링합니다. 자유 문장의 새 수치·인과 주장은 허용하지 않습니다.
- timeout/cancel 이후 추론 종료가 확인되지 않으면 `remote_call_state=unknown`으로 fail을 보내 JC의 격리 정책에 맡깁니다. 저장 실패는 succeeded가 아닙니다.
- Agent는 HTML·CSV 파일과 checksum을 저장합니다. Backend 다운로드 API는 발행된 결과에서 HTML 표와 항목별 CSV를 렌더링하며 새 조회·분석은 하지 않습니다. HTML escape와 CSV 수식 방어를 적용합니다. 화면 상단의 HTML·CSV 다운로드 버튼으로 받을 수 있습니다.

## 배포 입력이 필요한 부분

코드가 모든 R/O ID를 받아 주제별 결과와 부족 입력을 반환하지만, 실제 생산자 의미를 추정하지 않습니다. 다음 입력이 없으면 해당 판단은 `partial/blocked` 또는 null입니다.

- `D08`의 `gpu_ops_allocation_info`는 실제로 존재한다고 가정한 metric이 아니라 **배포 시 매핑할 정규화 계약 예시**입니다. `gpu_uuid`/`UUID`, namespace, pod, pod_uid 또는 동시 KSM uid, allocation_mode, allocation_episode_key, MIG instance_id를 검증해야 합니다. episode가 없으면 장시간 저활동 후보를 만들지 않습니다.
- O02·O08은 이 정규화 metric이 없어도 기존 DCGM 활용률(D01)과 `kube_pod_info`(D06)의 동시 구간을 연결해 관측 GPU 수, GPU–Pod 연결 관측 시간, Namespace별 연결 관측 시간을 산출합니다. 같은 이름의 Pod UID가 중첩되는 구간은 제외합니다. 이 수치는 독점 할당량·실제 연산 시간과 구분하며 공유 GPU의 Namespace별 시간을 합산해 전체 할당량으로 사용하지 않습니다.
- Prometheus 원본 표본 수 또는 응답 크기가 한도를 넘으면 시간 구간을 자동으로 줄여 다시 조회합니다. `max_queries`와 실행시간 한도는 재조회에도 적용되며, 끝내 수집하지 못한 구간·원본 경고는 부분 수집으로 남깁니다. 결과의 주제별 관측 품질에는 조회별 상태와 표본 수가 저장됩니다.
- `D07`의 `gpu_ops_effective_unbound_request` 역시 검증된 recording rule/원본으로 교체해야 합니다. scheduler 버전별 effective request 규칙, terminal/binding, resource 단위를 확인해야 합니다.
- Fleet 상태는 `health_contracts`에 producer별 `checks`/`health`/revision 매핑을 등록한 JSON에만 의미를 부여합니다. 원본 여러 incidents 항목을 각각 보존합니다. 미등록 상태는 unknown입니다.
- 토폴로지, 현재 조치 범위, 정책·정상 관측 기간, 실제 작업 중단/재개 증거가 없는 R04/R07/R08/R09를 확정하지 않습니다. reset 안전·업무 복구를 자동 판정하지 않습니다.
- 전체 기대 대상/관측 분모가 없는 전체 커버리지·발생률·순위, 검증된 scheduler 제약이 없는 GPU 부족량, 업무량 비교가 없는 조치 인과 효과는 보류합니다.

## 테스트

```powershell
./agents/scripts/test.ps1
./agents/scripts/test.ps1 -E2E -PgBin ./backend/.local/postgres/bin/bin
```

E2E는 Windows PostgreSQL 바이너리와 Go가 필요합니다. 스크립트는 JC와 Incident를 빌드합니다. `PG_BIN`, `JC_BINARY`, `INCIDENT_BINARY`, `GRAFANA_MCP_BINARY`로 경로를 변경할 수 있습니다. 실제 Incident 웹훅 → outbox → JC → RCA Worker → 결과 발행 경로를 포함하며, 이 테스트는 snapshot을 DB에 직접 삽입하지 않습니다. 별도 legacy snapshot/Runbook 사례도 유지합니다. 테스트마다 별도 PostgreSQL data directory/포트를 만들고, 생성한 서비스만 종료합니다. 로그·출력은 gitignore 대상 `.local/agent-e2e/`에 남깁니다. 자세한 검증 결과는 [QA.md](QA.md)입니다.

기술 확인 근거: [NAT MCP client](https://docs.nvidia.com/nemo/agent-toolkit/1.5/build-workflows/mcp-client.html), [NAT custom functions](https://docs.nvidia.com/nemo/agent-toolkit/1.5/extend/custom-components/custom-functions/functions.html), [공식 Grafana MCP](https://github.com/grafana/mcp-grafana/tree/v1.4.2).
