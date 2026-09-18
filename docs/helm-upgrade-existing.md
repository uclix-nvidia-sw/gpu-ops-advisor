# 기존 설치의 Agent 기동 수정과 이름 변경

대상: release `gpu-ops`, namespace `gpu-ops-advisor`, 기존 접두사 `gpu-ops-gpu-ops-advisor`.

새 chart는 기본 접두사로 릴리스 이름만 사용한다. 앱 Deployment/Pod/Service는 `gpu-ops-ops-agent`, `gpu-ops-rcca-agent`, `gpu-ops-grafana-mcp` 등의 이름이 된다. `fullnameOverride`로 다른 접두사도 지정할 수 있다.

**기존 설치에는 [upgrade-existing-values.yaml](upgrade-existing-values.yaml)을 추가로 적용한다.** 이 파일은 PostgreSQL StatefulSet/Service와 보고서 PVC의 기존 이름을 유지한다. DB Secret의 `DATABASE_URL`도 기존 `gpu-ops-gpu-ops-advisor-postgres:5432`를 그대로 사용한다. DB Pod 이름은 데이터 보존을 위해 이번 업그레이드에서는 유지한다. 새 설치는 기본값으로 `gpu-ops-postgres-0`과 `gpu-ops-postgres:5432`를 사용한다.

보고서 PVC를 유지하려고 현재 chart가 관리하는 PVC를 `existingClaim`으로만 바꾸면 chart의 PVC 리소스가 사라져 삭제될 수 있다. 이 overlay는 `nameOverride`로 동일 PVC를 계속 관리한다. 원래부터 외부 `existingClaim`을 사용했다면 그 설정을 그대로 유지한다. 기존 DB/PVC는 삭제하지 않는다.

## 업그레이드

수정 사항을 `main`에 반영하면 CI가 MCP·RCA·Ops를 포함한 이미지를 새로 빌드·발행하고, 그 실행에서 발행된 이미지 digest를 고정한 새 chart를 발행한다. 테스트나 이미지 빌드가 실패하면 chart 발행도 진행하지 않는다. 수동 `kubectl patch` 없이 새 chart 업그레이드로 기동 수정이 적용된다. 아래 파일 경로에는 **현재 설치에 사용한 환경 values**와 **수정 버전의 `.tgz`**를 지정한다. 이 과정은 앱 Deployment 이름이 바뀌므로 서비스 중단이 있다.

```bash
CHART_PACKAGE=./gpu-ops-advisor-REPLACE_NEW_VERSION.tgz
VALUES_FILE=./values.yaml
UPGRADE_VALUES=./docs/upgrade-existing-values.yaml

kubectl -n gpu-ops-advisor get sts,pvc
helm template gpu-ops "$CHART_PACKAGE" --namespace gpu-ops-advisor \
  --values "$VALUES_FILE" --values "$UPGRADE_VALUES" > rendered-upgrade.yaml

# 이름이 다른 구/신 Deployment가 동시에 작업하지 않도록 기존 앱을 먼저 정지
kubectl -n gpu-ops-advisor scale deployment \
  -l app.kubernetes.io/instance=gpu-ops --replicas=0

# 기존 앱 Pod가 종료됐는지 확인. PostgreSQL은 실행 상태를 유지한다.
kubectl -n gpu-ops-advisor get pods
# 앱 Pod가 아직 Terminating이면 종료될 때까지 기다린 후 다음 명령을 실행한다.

helm upgrade gpu-ops "$CHART_PACKAGE" --namespace gpu-ops-advisor \
  --values "$VALUES_FILE" --values "$UPGRADE_VALUES" \
  --wait --timeout 10m

kubectl -n gpu-ops-advisor get pods,pvc,svc
```

이후 업그레이드에서도 저장소 이름 override를 계속 유지한다. 모든 기존 이름을 그대로 두고 기동 수정만 적용하려면 `fullnameOverride: gpu-ops-gpu-ops-advisor`를 사용한다. 이 경우 앱 이름 변경을 위한 scale-down 절차는 필요 없다.

## 새 이미지와 chart에 포함된 MCP 수정

확인된 이벤트는 `Startup probe failed: HTTP probe failed with statuscode: 403`이다. 공식 Grafana MCP 1.4.2는 `/healthz`에도 Host 검증을 적용한다. 기존 probe가 보내는 Pod IP와 Agent가 사용하는 Service DNS가 기본 허용 목록에 없었다. startup probe 60회 × 5초 실패로 MCP가 재시작되고, Ready endpoint가 없어서 Agent도 연결에 실패했다. Grafana 토큰 오류를 의미하는 403이 아니다. [공식 HTTP 보안 설명](https://github.com/grafana/mcp-grafana/blob/v1.4.2/README.md#cli-flags-reference)을 참고한다.

MCP 이미지는 Docker 서비스 이름을 허용하고, chart는 실제 Helm Service DNS와 **`:8000` 포트까지** 포함한 허용 목록을 전달한다. 모든 MCP HTTP probe도 같은 Host 헤더를 사용한다. 새 설치와 기존 접두사를 유지하는 설치 모두 실제 공식 MCP 바이너리로 health check와 MCP 초기화·도구 목록 조회를 검증한다.

## Backend readiness 확인

기존 Backend는 C07 한도와 활성 클러스터가 모두 있어야 Ready가 되었고, 데모 seed를 끄면 두 항목을 자동 생성하지 않았다. 따라서 새 DB에 설치할 때 readiness가 503으로 유지되었다. 수정된 Backend 이미지는 데모 seed와 별도로 C07을 자동 초기화하며 기존 설정은 보존한다. 클러스터 0건은 정상 초기 상태로 허용하고 실제 분석 요청에서는 등록 여부를 계속 검사한다. 새 이미지가 포함된 chart로 업그레이드하면 추가 SQL 없이 기동된다.

Backend가 계속 Ready가 아니면 다음으로 설정 상태를 확인한다.

```bash
# 운영 데이터는 수정하지 않고 readiness에 필요한 상태만 조회
kubectl -n gpu-ops-advisor exec -i gpu-ops-gpu-ops-advisor-postgres-0 -- \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version=2) AS schema_v2;
SELECT name, enabled, config FROM service_profiles WHERE kind='limits' AND name='C07';
SELECT id, enabled FROM cluster_registry;
SQL
```

실제 분석 대상 클러스터 ID는 환경에 맞게 등록한다. 기본 운영 한도는 자동 생성되며, 기존 C07이 비활성화되었거나 유효하지 않으면 운영 설정을 수정해야 한다. `seedDemoData: true`로 바꾸어 예제 클러스터를 운영 환경에 넣지 않는다.

## MCP 연결 확인

첨부 오류 `httpx.ConnectError: All connection attempts failed`는 Agent → MCP 연결 실패다. MCP의 비-loopback caller 인증 경고 뒤에 서버 시작 로그가 있다면 그 경고 자체가 TCP 연결 실패를 의미하지 않는다.

새 Worker Pod는 `wait-for-job-controller`와 `wait-for-grafana-mcp` init container에서 준비 상태를 기다린다. 앱 초기화 중 일시적 MCP 연결 오류도 2초부터 최대 30초 간격으로 재시도한다. 준비 전에는 JC 작업을 인수하지 않는다. 잘못된 설정이나 HTTP 401/403 같은 인증 오류는 무한 재시도로 숨기지 않는다.

```bash
kubectl -n gpu-ops-advisor logs deployment/gpu-ops-ops-agent -c wait-for-grafana-mcp
kubectl -n gpu-ops-advisor logs deployment/gpu-ops-ops-agent -c ops-agent --tail=100
kubectl -n gpu-ops-advisor logs deployment/gpu-ops-grafana-mcp --tail=100
kubectl -n gpu-ops-advisor get endpointslice \
  -l kubernetes.io/service-name=gpu-ops-grafana-mcp -o yaml
```

Endpoint가 Ready인데도 연결 실패가 계속되면 Pod 간 네트워크/NetworkPolicy/Service 라우팅을 확인한다. 준비 대기와 재시도는 네트워크 차단을 해제하지 않는다. 이름 변경 전 진단 명령은 리소스 접두사로 `gpu-ops-gpu-ops-advisor`를 사용한다.

## 설치 후 클러스터 등록

클러스터가 없는 최초 설치에서도 Backend가 Ready가 되고 화면에 “등록된 클러스터가 없습니다”가 표시된다. **클러스터 등록하기 → 연결·설정 → 데이터 연결 → 클러스터 등록**에서 실제 클러스터 ID를 입력한다. Grafana에서 조회하는 메트릭·로그의 클러스터 라벨 값과 일치해야 하며, Mimir/Loki URL이나 datasource UID는 입력하지 않는다. 등록 후 목록과 관측 범위가 갱신되며 서버 재시작은 필요 없다. 등록 전에는 분석 화면 대신 등록 안내를 표시한다.

이 흐름은 수정된 Backend와 Frontend 이미지가 모두 포함된 새 chart에 적용된다. 실제 클러스터에 데이터가 없거나 Grafana 권한이 부족한 경우 등록 자체는 가능하지만 수집 결과는 별도로 확인해야 한다.
