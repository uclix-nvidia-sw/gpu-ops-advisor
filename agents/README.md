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

각 Worker는 독립 프로세스/이미지이고 공유 코드는 패키지입니다. 별도 업무 큐·접수 API·일정 루프·장비 조작·RCA 직접 요청은 없습니다. JC register → claim → heartbeat → candidate/evidence 저장 → complete로 실행합니다. 한 프로세스에서 한 작업씩 처리하며 JC가 전역 슬롯을 제어합니다.

## Windows 실행

저장소 루트의 PowerShell에서 실행합니다. Python 3.12와 NAT 1.5.0을 사용합니다.

```powershell
./agents/scripts/setup.ps1 -DownloadMcp
Copy-Item agents/.env.example agents/.env
```

`.env`에 기존 `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` 등을 설정합니다. `/chat/completions`를 호출하며 단계별 모델 설정, 300초 요청 상한, 기본 4096/설명 16384/insight 1024 토큰 설정을 지원합니다. 실제 호출은 JC attempt budget과 deadline으로 추가 제한합니다. 키는 코드·이미지에 넣지 않습니다. 모델/주소/키가 없으면 LLM 설명을 생략하고 유효한 결정적 결과는 유지합니다.

실행 전 `agents/config.example.json`을 배포 프로필로 복사해 `AGENT_CONFIG_FILE`로 지정합니다. 실제 datasource UID, CPC selector, 원본 주기·최대 유효시간·단위·query revision을 검수하고 해당 query의 `validated`를 `true`로 바꿉니다. 예시의 `false`는 미검증 출처가 계산에 섞이지 않도록 하는 차단값입니다. C07 숫자도 예시이며 운영 확정값이 아닙니다.

Mimir tenant는 Grafana 데이터소스 헤더에서 설정합니다. 예시 CPC-2 지표는 `cluster_id="cpc-2"`, Loki는 `cluster="cpc2"` selector를 사용하며 tenant/실제 UID는 운영 환경에서 확인해야 합니다. Worker에 Mimir/Loki 직접 주소를 주지 않습니다.

```powershell
$env:GRAFANA_URL='https://your-grafana'
# GRAFANA_SERVICE_ACCOUNT_TOKEN은 로컬 환경에 설정
.local/mcp-grafana/mcp-grafana.exe -t streamable-http -address 127.0.0.1:8000 -enabled-tools prometheus,loki -disable-write -max-loki-log-limit 5000
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
- HTML escape, CSV 수식 방어, 서버 생성 파일명, checksum을 적용합니다. 재다운로드에는 저장 파일을 사용하며 새 분석이 필요 없습니다.

## 배포 입력이 필요한 부분

코드가 모든 R/O ID를 받아 주제별 결과와 부족 입력을 반환하지만, 실제 생산자 의미를 추정하지 않습니다. 다음 입력이 없으면 해당 판단은 `partial/blocked` 또는 null입니다.

- `D08`의 `gpu_ops_allocation_info`는 실제로 존재한다고 가정한 metric이 아니라 **배포 시 매핑할 정규화 계약 예시**입니다. `gpu_uuid`/`UUID`, namespace, pod, pod_uid 또는 동시 KSM uid, allocation_mode, allocation_episode_key, MIG instance_id를 검증해야 합니다. episode가 없으면 장시간 저활동 후보를 만들지 않습니다.
- `D07`의 `gpu_ops_effective_unbound_request` 역시 검증된 recording rule/원본으로 교체해야 합니다. scheduler 버전별 effective request 규칙, terminal/binding, resource 단위를 확인해야 합니다.
- Fleet 상태는 `health_contracts`에 producer별 `checks`/`health`/revision 매핑을 등록한 JSON에만 의미를 부여합니다. 원본 여러 incidents 항목을 각각 보존합니다. 미등록 상태는 unknown입니다.
- 토폴로지, 현재 조치 범위, 정책·정상 관측 기간, 실제 작업 중단/재개 증거가 없는 R04/R07/R08/R09를 확정하지 않습니다. reset 안전·업무 복구를 자동 판정하지 않습니다.
- 전체 기대 대상/관측 분모가 없는 전체 커버리지·발생률·순위, 검증된 scheduler 제약이 없는 GPU 부족량, 업무량 비교가 없는 조치 인과 효과는 보류합니다.

## 테스트

```powershell
./agents/scripts/test.ps1
./agents/scripts/test.ps1 -E2E -PgBin ./backend/.local/postgres/bin/bin
```

E2E는 Windows PostgreSQL 바이너리와 Go가 필요합니다. `PG_BIN`, `JC_BINARY`, `GRAFANA_MCP_BINARY`로 경로를 변경할 수 있습니다. 테스트마다 별도 PostgreSQL data directory/포트를 만들고, 생성한 서비스만 종료합니다. 로그·출력은 gitignore 대상 `.local/agent-e2e/`에 남깁니다. 자세한 검증 결과는 [QA.md](QA.md)입니다.

기술 확인 근거: [NAT MCP client](https://docs.nvidia.com/nemo/agent-toolkit/1.5/build-workflows/mcp-client.html), [NAT custom functions](https://docs.nvidia.com/nemo/agent-toolkit/1.5/extend/custom-components/custom-functions/functions.html), [공식 Grafana MCP](https://github.com/grafana/mcp-grafana/tree/v1.4.2).
