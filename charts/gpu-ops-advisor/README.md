# GPU Ops Advisor Helm chart

기본 설치는 **8개 Pod**입니다. 각 모듈은 1 replica이며 자동 확장은 포함하지 않습니다.

| Pod | Kubernetes workload | 역할 / 포트 |
| --- | --- | --- |
| frontend | Deployment | Nginx·React, 8080 |
| backend | Deployment | API·내부 일정 처리, 8080 |
| job-controller | Deployment | 큐·lease·결과 공개, 8090 |
| incident | Deployment | Grafana alert 접수·Incident 처리, 8091 |
| rcca-agent | Deployment | RCA Worker, HTTP 포트 없음 |
| ops-agent | Deployment | 보고서 Worker, HTTP 포트 없음 |
| grafana-mcp | Deployment | 공식 MCP의 Mimir·Loki 읽기 도구, 8000 |
| postgres | StatefulSet | PostgreSQL 16.9, 5432 |

**Grafana, Mimir, Loki, LLM 서버는 기존 외부 서비스를 사용합니다.** MCP는 `grafana.url`과 Grafana service account token으로 접속하고, Agent는 MCP를 통해 Grafana에 등록된 Mimir/Loki datasource UID를 조회합니다. PostgreSQL은 `postgres.enabled=false`로 제외하고 외부 DB를 사용할 수 있습니다.

## 패키지 받기

GitHub Actions의 `helm-chart-<version>` artifact 안에 `.tgz`, SHA256 파일, `rendered.yaml`, `release-manifest.json`이 들어 있습니다. `main` push/merge는 commit SHA 이미지와 CI 버전(`1.3.0-ci.<run>.<attempt>`)의 OCI chart를 함께 발행합니다. `v1.3.0` 같은 버전 태그는 정식 버전의 이미지와 OCI chart를 발행합니다. PR·수동 실행 패키지는 검토용이며 이미지가 발행되지 않습니다. 세부 흐름은 [CI 안내](../../docs/ci-release.md)를 참조하세요.

```sh
sha256sum -c gpu-ops-advisor-1.3.0.tgz.sha256
helm show values ./gpu-ops-advisor-1.3.0.tgz
# 또는 태그 릴리스의 OCI 패키지
helm pull oci://ghcr.io/<github-owner>/charts/gpu-ops-advisor --version 1.3.0
```

## 설치 준비

리소스 이름은 기본적으로 `<release>-<component>`입니다. 예: `gpu-ops-ops-agent`, `gpu-ops-postgres`. `fullnameOverride`로 접두사를 변경할 수 있습니다. 이전 `<release>-gpu-ops-advisor-<component>` 설치를 업그레이드할 때는 [기존 설치 업그레이드 안내](../../docs/helm-upgrade-existing.md)에 따라 DB/보고서 PVC 이름을 유지하고 앱 Deployment를 전환하세요.

내장 PostgreSQL을 사용하는 설치는 [설치용 values](../../docs/deployment-values.yaml)와 [Secret 준비·설치 명령 안내](../../docs/helm-install.md)를 사용할 수 있습니다.

릴리스 이름을 `gpu-ops`, namespace를 `gpu-ops`로 설치하면 DB 서비스명은 `gpu-ops-postgres`입니다. 다른 릴리스 이름을 쓰면 `helm template`으로 이름을 확인하고 DB URL도 맞춥니다. 모든 Secret은 같은 namespace에 미리 준비합니다. chart 자체는 Secret을 생성하지 않으며 값에 비밀을 넣지 않습니다.

| 기존 Secret 기본 이름 | 필수 key | 용도 |
| --- | --- | --- |
| gpu-ops-advisor-database | DATABASE_URL | 모든 Go 서비스·Worker가 사용할 PostgreSQL URI |
| gpu-ops-advisor-database | POSTGRES_PASSWORD | 내장 PostgreSQL을 사용할 때의 비밀번호 |
| gpu-ops-advisor-grafana | GRAFANA_SERVICE_ACCOUNT_TOKEN | 기존 Grafana의 읽기 권한 service account |
| 사용자가 `llm.existingSecret`으로 지정 | LLM_API_KEY | LLM API 인증; 인증 없는 서버이면 생략 가능 |

내장 DB URL 형식은 `postgresql://dsx:<URL-encoded-password>@gpu-ops-postgres:5432/dsx?sslmode=disable`이며 Secret의 `POSTGRES_PASSWORD`와 같은 비밀번호를 사용합니다. 외부 DB라면 해당 주소·사용자·TLS 설정으로 지정합니다. 스키마 초기화는 서비스가 advisory lock을 잡고 수행하며 DB 사용자는 해당 스키마에 DDL 권한이 필요합니다.

운영 Secret 관리 방식으로 주입하거나, 권한을 제한한 로컬 env 파일을 이용할 수 있습니다. 파일을 저장소에 추가하지 않습니다.

```sh
kubectl create namespace gpu-ops
kubectl -n gpu-ops create secret generic gpu-ops-advisor-database --from-env-file=/secure/database.env
kubectl -n gpu-ops create secret generic gpu-ops-advisor-grafana --from-env-file=/secure/grafana.env
kubectl -n gpu-ops create secret generic gpu-ops-advisor-llm --from-env-file=/secure/llm.env
```

`deployment-values.yaml` 예시:

```yaml
grafana:
  url: https://grafana.example.internal
llm:
  existingSecret: gpu-ops-advisor-llm
  baseUrl: https://inference.example.internal/v1
  model: your-model
postgres:
  enabled: true
  persistence:
    storageClass: your-storage-class
artifacts:
  persistence:
    storageClass: your-storage-class
```

LLM 모델·주소·토큰 한도는 [Agent 설정](../../agents/README.md)의 동일한 설정을 사용합니다. 단계별 모델은 `components.rcca-agent.env.LLM_MODEL_PLANNER` 등 `components.<name>.env`에 문자열로 설정할 수 있습니다. 비밀값은 위 Secret 참조를 사용합니다.

기본 실행 프로필은 `local-v1` 하나이며, 입력·출력을 포함해 시도당 32,768, 작업 전체 98,304의 예산을 사용합니다. `llm.synthesisMaxTokens`만 바꿔서는 실행 예산이 늘어나지 않습니다. 기존 설치는 [토큰 예산 업데이트](../../docs/helm-install.md#기존-설치의-llm-토큰-예산-업데이트)에 따라 업그레이드하고 새 보고서를 요청합니다.

`configuration.agents: {}`는 내장 수집 프로필을 사용합니다. 별도 `agents.json`을 만들거나 datasource UID, Mimir/Loki 접속 정보를 입력할 필요가 없습니다. Agent가 Grafana MCP의 `list_datasources`와 label 조회 도구로 작업 대상 클러스터에 해당하는 Prometheus 호환/Mimir 및 Loki datasource와 selector를 찾습니다. Grafana 토큰에는 datasource 목록과 데이터 조회 권한이 필요합니다. 기본 쿼리의 `validated`는 모두 `true`이며 수집 차단 스위치로 사용하지 않습니다. 데이터가 없거나 의미를 해석할 계약이 부족하면 해당 결과는 `empty/unavailable` 또는 `partial/blocked`로 남습니다.

탐색은 작업 시간 범위에서 `cluster_id`, `cluster`, `k8s_cluster_name`, `kubernetes_cluster`, `k8s_cluster` 라벨 순서로 수행합니다. 첫 번째로 값이 존재하는 라벨에서 작업의 cluster ID와 정확히 일치하는 대상을 찾습니다. 일치하는 datasource가 하나일 때만 조회하며, 후보가 여러 개거나 클러스터 라벨이 없거나 권한/통신 오류가 있으면 원인을 evidence와 Worker 로그에 남깁니다. `cpc-2`와 `cpc2` 같은 별칭을 임의로 동일시하거나 전체 클러스터로 조회 범위를 넓히지 않습니다. 표준 배포에서는 Grafana에 올바른 데이터소스와 클러스터 라벨이 준비되어 있어야 합니다.

고급 환경에서는 `configuration.agents`에 전체 프로필 객체를 지정해 기존의 명시적 UID/selector 매핑이나 생산자별 의미 계약을 유지할 수 있습니다. `configuration.jobController`, `configuration.incident`도 전체 객체로 대체할 수 있습니다. 내장 프로필과 chart 내부 복사본의 일치는 CI가 검사합니다. 이 기능은 두 Worker와 Grafana MCP의 새 이미지 및 새 chart를 함께 발행한 뒤 사용할 수 있습니다.

`configuration.applyJobController`와 `applyIncident`의 기본값은 모두 `true`입니다. 최초 설치와 업그레이드 시 JC·Incident 설정을 DB에 적용하며, 이미 접수된 작업의 입력·예산 스냅샷은 유지합니다. 기존 values에서 두 옵션을 `false`로 지정했다면 삭제하거나 `true`로 변경합니다. Incident 분석 정책의 내용을 바꿀 때는 정책 revision을 새로 지정합니다. `seedDemoData` 기본값은 `false`입니다. Backend는 필수 `C07` 운영 한도를 자동 초기화하고 기존 설정은 보존합니다. 클러스터가 0건이어도 Ready가 되며, 실제 분석을 실행하려면 cluster_registry에 대상 클러스터를 등록해야 합니다.

## 설치 및 확인

```sh
helm upgrade --install gpu-ops ./gpu-ops-advisor-1.3.0.tgz \
  --namespace gpu-ops --values deployment-values.yaml --wait --timeout 10m
kubectl -n gpu-ops get pods,pvc,svc
kubectl -n gpu-ops port-forward svc/gpu-ops-frontend 8080:8080
```

모든 Service는 ClusterIP이며 Ingress 기본값은 꺼져 있습니다. 현재 제품의 인증 제외 범위에 맞춰 신뢰하는 내부 네트워크에서 사용합니다. Incident webhook은 클러스터 내부의 `http://gpu-ops-incident:8091`에 별도로 연결합니다. 외부 Grafana에서 webhook을 전달해야 하면 운영 네트워크에 맞는 내부 라우팅을 구성합니다. frontend Ingress는 `ingress.enabled`, `className`, `host`, `tls`로 설정합니다.

GHCR 이미지가 비공개라면 `global.imagePullSecrets: [{name: ghcr-pull}]`과 동일 namespace의 registry Secret이 필요합니다. CI 패키지에 들어 있는 이미지 digest는 유지하고, 직접 소스로 설치할 때는 `global.imageNamespace`와 각 `components.<name>.image.tag`에 실제 발행된 이미지를 지정합니다.

PostgreSQL 데이터 PVC와 보고서 파일 PVC는 각각 기본 10Gi입니다. StorageClass 기본값은 클러스터 기본 StorageClass를 사용합니다. 보고서 PVC는 `artifacts.persistence.existingClaim`으로 기존 PVC를 지정할 수 있습니다. PostgreSQL StatefulSet의 PVC는 삭제 시 자동 정리되지 않지만 **chart가 만든 보고서 PVC는 Helm uninstall 시 삭제됩니다**. 보고서를 보존할 배포는 기존 PVC를 사용하고 DB·파일을 함께 백업하세요. `persistence.enabled=false`는 재시작 시 데이터를 잃는 임시 저장소입니다.

현재 chart는 서비스별 1 replica를 schema로 제한하고, 업그레이드는 Recreate 방식이라 잠깐의 중단이 있습니다. 수동 확장이 필요한 경우 JC capacity/worker profile과 공유 파일 저장 방식을 함께 설계한 뒤 replica 제한을 변경합니다. Kubernetes HTTP probe는 HTTP 서비스에만 있으며 Worker는 JC와 Grafana MCP readiness를 기다린 후 시작하고 JC heartbeat로 상태를 관리합니다.

Grafana MCP에는 내부 Service DNS와 포트가 포함된 `-allowed-hosts`를 전달하고 probe의 `Host` 헤더도 맞춥니다. Pod IP를 사용하는 기본 probe는 공식 MCP의 Host 검증에서 403으로 거부됩니다. HTTP 서비스의 startup/liveness는 생존 여부를, readiness는 의존성과 설정 준비 여부를 확인합니다. 새 이미지가 포함된 chart로 기존 긴 이름 설치를 업그레이드하는 절차는 [기존 설치 안내](../../docs/helm-upgrade-existing.md)를 참고하세요.

## 로컬 검증

```sh
pip install PyYAML==6.0.2 jsonschema==4.26.0
python tools/ci/check_chart.py
python -m unittest discover -s tools/ci/tests -v
```

Helm 3.17.3을 PATH에 설치하거나 `HELM_BINARY`를 지정합니다. 기본/외부 DB/임시 저장소/기존 PVC/Ingress/Secret/digest 설정의 실제 Helm 렌더링과 패키지 재렌더링을 검사합니다. Kubernetes에 실제 설치한 결과나 운영 Grafana·LLM 통합 검수를 뜻하지 않습니다.

## 설치 후 클러스터 등록

클러스터가 없는 최초 설치에서도 Backend가 Ready가 되고 화면에 “등록된 클러스터가 없습니다”가 표시된다. **클러스터 등록하기 → 연결·설정 → 데이터 연결 → 클러스터 등록**에서 실제 클러스터 ID를 입력한다. Grafana에서 조회하는 메트릭·로그의 클러스터 라벨 값과 일치해야 하며, Mimir/Loki URL이나 datasource UID는 입력하지 않는다. 등록 후 목록과 관측 범위가 갱신되며 서버 재시작은 필요 없다. 등록 전에는 분석 화면 대신 등록 안내를 표시한다.

이 흐름은 수정된 Backend와 Frontend 이미지가 모두 포함된 새 chart에 적용된다. 실제 클러스터에 데이터가 없거나 Grafana 권한이 부족한 경우 등록 자체는 가능하지만 수집 결과는 별도로 확인해야 한다.
