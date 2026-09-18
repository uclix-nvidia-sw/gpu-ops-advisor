# 내장 PostgreSQL을 사용하는 Helm 설치

[설치용 values](deployment-values.yaml)는 PostgreSQL Pod 1개와 DB PVC 10Gi를 사용한다. 외부 DB는 필요 없다. 기본 구성은 PostgreSQL을 포함한 8개 Pod다. 아래 명령은 저장소 루트에서 **Bash/Linux/WSL**로 실행하며, 릴리스 이름과 namespace는 모두 `gpu-ops`로 고정한다.

## 1. 환경 값 준비

```bash
mkdir -p .local/helm
chmod 700 .local/helm
cp docs/deployment-values.yaml .local/helm/values.yaml
```

`.local/helm/values.yaml`에서 아래 값을 수정한다. `.local/`은 Git 추적에서 제외된다.

| 설정 | 준비할 값 |
| --- | --- |
| `grafana.url` | `http://192.168.20.186:31891` 반영됨; MCP Pod에서도 접근 가능해야 함 |
| `llm.baseUrl`, `llm.model` | LLM API 주소와 모델명 |
| `llm.existingSecret` | 기본값은 `gpu-ops-advisor-llm`; 인증 없는 서버이면 빈 문자열 |
| `postgres.persistence.storageClass`, `artifacts.persistence.storageClass` | 빈 문자열은 클러스터 기본 StorageClass 사용 |
| `global.imagePullSecrets` | private GHCR용 `[{name: ghcr-pull}]` 반영됨; 아래 Secret 생성 필요 |
| `artifacts.persistence.existingClaim` | 보고서 보존용 기존 PVC가 있으면 이름 지정 |

**별도 `agents.json`은 만들지 않는다.** `configuration.agents: {}`를 유지하면 내장 프로필을 사용하며, Grafana MCP를 통해 Mimir/Prometheus 및 Loki datasource UID와 클러스터 라벨을 자동 탐색한다. 기본 쿼리는 활성화되어 있고 `validated`를 설정할 필요가 없다. 이 동작이 포함된 새 chart와 Worker/MCP 이미지를 사용해야 한다.

Grafana에는 해당 데이터소스가 이미 등록되어 있어야 하며 토큰에 datasource 목록·label·query 조회 권한이 필요하다. 데이터의 클러스터 라벨 값은 작업의 cluster ID와 정확히 일치해야 한다. 여러 datasource에 같은 클러스터가 존재하거나 라벨이 없으면 임의로 전체 데이터를 조회하지 않고 원인을 표시한다. 지원 라벨과 상세 동작은 [Chart 안내](../charts/gpu-ops-advisor/README.md)를 참고한다. 실제 메트릭이나 로그 의미 계약이 없는 항목은 데이터 부족으로 남으며 자동 탐색이 원본 데이터를 생성하지는 않는다.

`seedDemoData: false`이므로 실제 `cluster_registry`와 운영 설정도 별도로 등록해야 한다. 필요한 경우 `configuration.jobController`와 `configuration.incident`에 환경에 맞춘 전체 객체를 지정한다. Grafana alert를 받을 경우 Incident webhook 연결도 별도 구성한다. Pod가 Ready인 것과 실제 데이터 수집/분석 준비가 끝난 것은 다르다.

## 2. Secret 준비

Chart는 Secret을 생성하지 않는다. 아래 파일을 로컬 편집기로 만들고 `REPLACE_*`를 실제 값으로 바꾼다. env 파일 값에는 따옴표를 붙이지 않는다.

`.local/helm/database.env`:

```dotenv
POSTGRES_PASSWORD=REPLACE_DB_PASSWORD
DATABASE_URL=postgresql://dsx:REPLACE_URL_ENCODED_DB_PASSWORD@gpu-ops-gpu-ops-advisor-postgres:5432/dsx?sslmode=disable
```

두 값에는 **같은 비밀번호**를 사용한다. `POSTGRES_PASSWORD`에는 원문, URL에는 percent-encoding한 비밀번호를 넣는다. 릴리스 이름을 바꾸면 DB 호스트명도 바뀐다. 기존 DB PVC를 재사용하는 경우 기존 비밀번호를 사용해야 하며 Secret만 바꿔도 기존 PostgreSQL 사용자의 비밀번호가 바뀌지는 않는다.

`.local/helm/grafana.env`:

```dotenv
GRAFANA_SERVICE_ACCOUNT_TOKEN=REPLACE_GRAFANA_SERVICE_ACCOUNT_TOKEN
```

개인 로그인 ID/비밀번호 대신 대상 Mimir/Loki datasource를 조회할 수 있는 Grafana Service Account Token을 사용한다. Agent의 MCP 내부 URL은 Helm이 자동 설정한다.

`.local/helm/llm.env` (LLM 인증이 필요한 경우):

```dotenv
LLM_API_KEY=REPLACE_LLM_API_KEY
```

실제 값을 저장한 후 최초 설치 시 실행한다.

```bash
chmod 600 .local/helm/*.env
kubectl create namespace gpu-ops --dry-run=client -o yaml | kubectl apply -f -
kubectl -n gpu-ops create secret generic gpu-ops-advisor-database \
  --from-env-file=.local/helm/database.env
kubectl -n gpu-ops create secret generic gpu-ops-advisor-grafana \
  --from-env-file=.local/helm/grafana.env
# 인증 없는 LLM 서버이면 아래 명령 생략 + values의 llm.existingSecret을 ""로 설정
kubectl -n gpu-ops create secret generic gpu-ops-advisor-llm \
  --from-env-file=.local/helm/llm.env
```

업그레이드 시 이미 존재하는 Secret은 재생성하지 않는다.

### Private GHCR 인증

GitHub의 **Personal access token (classic)**에 `read:packages` 권한을 부여한다. 토큰 소유 계정이 chart와 각 애플리케이션 이미지 패키지에 읽기 권한을 가져야 한다. 조직이 SSO를 요구하면 토큰의 SSO 인증도 필요하다. [GitHub 공식 인증 안내](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)를 참고한다.

인증은 두 곳에 설정한다. `helm registry login`은 설치 PC의 chart 다운로드용이고, `ghcr-pull` Secret은 Kubernetes의 컨테이너 이미지 다운로드용이다. 같은 PAT를 사용할 수 있지만 Helm 로그인만으로 Kubernetes 인증까지 설정되지는 않는다. Grafana Service Account Token과는 별개다.

아래 명령은 namespace 생성 후 Bash에서 실행한다. `GHCR_USER`는 조직 이름이 아니라 PAT를 발급한 GitHub 사용자명이다.

```bash
read -rp 'GitHub username: ' GHCR_USER
read -rsp 'GitHub PAT (classic, read:packages): ' GHCR_TOKEN
printf '\n'

printf '%s' "$GHCR_TOKEN" | helm registry login ghcr.io \
  --username "$GHCR_USER" --password-stdin

kubectl -n gpu-ops create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username="$GHCR_USER" \
  --docker-password="$GHCR_TOKEN"

unset GHCR_TOKEN
```

이미 `ghcr-pull`이 존재하고 유효하면 Secret 생성은 생략한다. 토큰은 values 파일에 넣지 않는다.

## 3. 발행된 Chart 다운로드 및 설치

**이미지까지 발행된 main/tag CI 패키지**를 사용한다. PR/수동 실행의 검토용 패키지는 배포용 이미지가 없다. 실제 발행 버전은 [CI 릴리스 안내](ci-release.md)를 참고한다.

```bash
# 실제 GitHub owner(소문자)와 발행된 chart 버전으로 교체
CHART_OWNER=REPLACE_GITHUB_OWNER
CHART_VERSION=REPLACE_PUBLISHED_CHART_VERSION

helm pull "oci://ghcr.io/${CHART_OWNER}/charts/gpu-ops-advisor" \
  --version "$CHART_VERSION" --destination .local/helm

CHART_PACKAGE=".local/helm/gpu-ops-advisor-${CHART_VERSION}.tgz"

# 설치 전 문법/렌더링 확인
helm lint "$CHART_PACKAGE" --strict \
  --values .local/helm/values.yaml

helm template gpu-ops "$CHART_PACKAGE" --namespace gpu-ops \
  --values .local/helm/values.yaml \
  > .local/helm/rendered.yaml

# 실제 설치 (동일 명령으로 업그레이드 가능)
helm upgrade --install gpu-ops "$CHART_PACKAGE" \
  --namespace gpu-ops \
  --values .local/helm/values.yaml \
  --wait --timeout 10m
```

Actions에서 `.tgz`를 이미 받았다면 `helm pull`을 생략하고 `CHART_PACKAGE`에 해당 파일 경로를 넣는다. 패키지의 이미지 namespace/tag/digest를 이 values 파일은 덮어쓰지 않는다. 저장소의 `./charts/gpu-ops-advisor`를 직접 설치하려면 실제 발행된 이미지 namespace와 각 컴포넌트의 tag/digest를 별도로 설정해야 한다.

## 4. 설치 확인과 접속

```bash
helm status gpu-ops -n gpu-ops
kubectl -n gpu-ops get pods,pvc,svc
kubectl -n gpu-ops rollout status statefulset/gpu-ops-gpu-ops-advisor-postgres
kubectl -n gpu-ops logs deployment/gpu-ops-gpu-ops-advisor-grafana-mcp --tail=100
kubectl -n gpu-ops port-forward svc/gpu-ops-gpu-ops-advisor-frontend 8080:8080
```

포트 포워딩 실행 중 브라우저에서 `http://localhost:8080`으로 접속한다. 분석 작업을 실행해 Worker 로그와 evidence에서 datasource 자동 탐색 및 실제 query 성공을 확인한다. 기본 Ingress는 꺼져 있다.

업그레이드에서 기존 DB의 JC/Incident 설정은 보존된다. 설정 revision을 변경해 적용할 때만 `configuration.applyJobController` / `configuration.applyIncident`를 명시적으로 활성화한다. PostgreSQL PVC는 uninstall 후에도 남지만 chart가 생성한 보고서 PVC는 삭제되므로, 보고서를 보존할 배포는 기존 PVC를 지정한다.
