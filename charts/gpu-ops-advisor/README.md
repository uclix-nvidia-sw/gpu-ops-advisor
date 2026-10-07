# D binding 설정 사본 — 2026-10-06

내장 `files/agents.json`은 공통 원본과 동일한 `d-contract-restart-20261006-r1` 후보 registry다. 두 Worker의 새 런타임과 함께 적용해야 하며, **기본 binding은 미선택이라 관측을 실행하지 않는다.** 기존 운영 설정을 이 후보 예제로 단독 교체하지 않는다. [환경별 선택·전환·회수 순서](../../docs/specs/common/d-binding-runtime.md)를 따른다. 아래 v3 절은 이전 전환 기록이다.

# GPU Ops Advisor Helm chart

## Fleet RCA profile v3 (2026-09-30)

당시 내장 Agent 프로필은 `builtin-grafana-v3`이며 D05/D09 `builtin-v3`의 JSON 필터·`health_contract`와 `health_contracts.fleet-component-log-v1`을 포함한다. `configuration.agents` 전체 override를 쓰는 설치는 새 설정을 직접 병합해야 한다. 기본 계약은 로그 기록 관측만 제공하며 실제 장비 시각/freshness fact 승격은 비활성이다. [RCA 설정 계약](../../rcca-agent/README.md#2026-09-30-fleet-rca-수집분석-보완)을 확인한다.

공통 Python 변경으로 RCA/Ops 이미지를 모두 재빌드하고 target 투영에는 Incident, 최종 보고서 표시에는 Frontend의 새 이미지가 필요하다. DB migration·기존 snapshot 재작성은 없다. 배포 승인 후 새 작업의 수집·분석·보고서 공개를 검수하고 기존 PVC를 보존한다. 로컬 검사는 운영 배포 검증이 아니다.

Namespace 보고서의 `configuration.namespaceReportProfileRevision` 기본값은 `report-namespace-v1`이다. 새 Ops Worker → JC(보고서 전용 criteria 1.2 프로필) → Backend/Frontend 순서로 반영한다. `configuration.jobController`를 직접 지정했다면 전체 객체에 새 프로필을 포함해야 한다. 전역 criteria와 RCA 프로필은 유지한다. 이전 버전으로 복구할 때는 신규 요청 생산자인 Backend/Frontend부터 되돌리고 실행 중 작업의 고정 설정과 기존 DB·PVC를 보존한다. 실제 업그레이드는 [기존 환경 업그레이드](../../docs/helm-upgrade-existing.md)를 따른다.

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

`llm.existingSecret`의 키는 Backend 연결 검사와 두 Worker에 함께 전달됩니다. GUI에서 모델을 지정한 작업은 고정된 프로필의 주소·모델명·인증을 사용합니다. 위 `llm.baseUrl`·`llm.model`과 단계별 환경변수는 GUI 모델 지정이 없는 작업의 대체 설정입니다. `components.backend.env.DSX_MODEL_HOSTS`·`DSX_MODEL_CIDRS`는 두 Worker에도 기본 전달됩니다. [모델 인증 연결 절차](../../docs/model-connection.md)와 [Agent 설정](../../agents/README.md)을 따릅니다.

기본 실행 프로필은 `local-v1` 하나이며, 입력·출력을 포함해 시도당 32,768, 작업 전체 98,304의 예산을 사용합니다. `llm.synthesisMaxTokens`만 바꿔서는 실행 예산이 늘어나지 않습니다. 기존 설치는 [토큰 예산 업데이트](../../docs/helm-install.md#기존-설치의-llm-토큰-예산-업데이트)에 따라 업그레이드하고 새 보고서를 요청합니다.

`configuration.agents: {}`는 내장 후보 프로필을 사용하므로 기본 관측은 실행하지 않습니다. 실행하려면 환경별로 검증된 전체 설정을 `configuration.agents`에 지정합니다. 새 binding은 Grafana datasource UID, 고정 selector, `scope_labels`의 cluster_id 라벨 매핑, producer/version, 단위·시간·대상 규칙과 검증 근거를 명시해야 합니다. CPC 이름은 작업 입력에서 받으며 CPC별 전체 JSON을 만들지 않습니다. 공통 binding 선택에는 검증 계약의 적용 범위인 `verification.applicability`가 필요합니다. 구 profile에서만 기존 datasource/label 자동 탐색을 사용합니다. Mimir/Loki 접속과 인증은 Grafana datasource가 담당합니다. 데이터가 없거나 의미를 해석할 계약이 부족하면 해당 결과는 `empty/unavailable` 또는 `partial/blocked`로 남습니다.

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

Frontend Service는 기본적으로 NodePort `30006`을 사용하며 `http://<노드 IP>:30006`으로 접속합니다. Service·컨테이너 포트는 `8080`입니다. `frontendService.type`과 `frontendService.nodePort`로 변경할 수 있고, `ClusterIP`를 선택하면 NodePort를 할당하지 않습니다. 다른 Service는 ClusterIP이며 Ingress 기본값은 꺼져 있습니다. 현재 제품의 인증 제외 범위에 맞춰 신뢰하는 내부 네트워크에서 사용합니다. Incident webhook은 클러스터 내부의 `http://gpu-ops-incident:8091`에 별도로 연결합니다. 외부 Grafana에서 webhook을 전달해야 하면 운영 네트워크에 맞는 내부 라우팅을 구성합니다. frontend Ingress는 `ingress.enabled`, `className`, `host`, `tls`로 설정합니다.

GHCR 이미지가 비공개라면 `global.imagePullSecrets: [{name: ghcr-pull}]`과 동일 namespace의 registry Secret이 필요합니다. CI 패키지에 들어 있는 이미지 digest는 유지하고, 직접 소스로 설치할 때는 `global.imageNamespace`와 각 `components.<name>.image.tag`에 실제 발행된 이미지를 지정합니다.

PostgreSQL 데이터 PVC와 보고서 파일 PVC는 각각 기본 10Gi입니다. StorageClass 기본값은 클러스터 기본 StorageClass를 사용합니다. 보고서 PVC는 `artifacts.persistence.existingClaim`으로 기존 PVC를 지정할 수 있습니다. PostgreSQL StatefulSet의 PVC는 삭제 시 자동 정리되지 않지만 **chart가 만든 보고서 PVC는 기본적으로 Helm uninstall 시 삭제됩니다**. `artifacts.persistence.retainOnDelete: true`를 적용하면 해당 PVC에 `helm.sh/resource-policy: keep`을 기록해 Helm의 삭제를 건너뛰도록 합니다. 외부 PVC로 전환하기 전에 기존 PVC를 그대로 관리하는 중간 업그레이드에서 먼저 적용·확인하세요. 전환 후 보존된 PVC는 Helm 관리에서 벗어나므로 정리는 별도 작업입니다. 이 옵션은 PV의 reclaim policy를 바꾸거나 백업을 만들지 않습니다. DB·파일을 함께 백업하세요. `persistence.enabled=false`는 재시작 시 데이터를 잃는 임시 저장소입니다.

기본값은 서비스별 1 replica이며, Backend·Frontend·JC·Incident·MCP는 schema로 1개를 유지합니다. RCA/Ops Worker만 아래 조건에 따라 수동 확장할 수 있습니다. 업그레이드는 Recreate 방식이라 잠깐의 중단이 있습니다. Kubernetes HTTP probe는 HTTP 서비스에만 있으며 Worker는 JC와 Grafana MCP readiness를 기다린 후 시작하고 JC heartbeat로 상태를 관리합니다.

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


## RCA·Ops 각각 3개 실행 — 선택 배포 구성

[values-independent-agents.yaml](values-independent-agents.yaml)은 RCA Pod 3개와 Ops Pod 3개, Pod당 실행 슬롯 1개의 선택 구성입니다. JC는 `kind_limits.rca=3`, `kind_limits.report=3`, `shared_limit=6`으로 각각 최대 3개 작업을 실행합니다. 한 종류가 다른 종류의 몫을 빌려 4개 이상 실행하지 않습니다. 이 구성을 지원하는 JC 버전은 공유 한도가 종류별 한도 합계 이상이면 종류 간 교대 대기를 적용하지 않습니다. 모델 서버·MCP·DB 자원은 계속 공유하며, 6개 동시 작업의 실제 성능을 보장하는 값은 아닙니다.

기존 1개씩 설치와 RWO PVC 기본값은 바꾸지 않습니다. 이 예제의 `existingClaim`은 비어 있어 그대로 렌더링하면 실패합니다. Ops 3개가 여러 노드에서 파일을 보존하려면 실제로 사용 가능한 기존 RWX PVC 이름을 지정하고 `existingClaimAccessMode: ReadWriteMany`로 선언해야 합니다. 이 값은 운영자의 선언이며 Helm이 서버의 PVC 상태를 확인했다는 뜻은 아닙니다. 실제 accessModes·StorageClass 지원·UID/GID 10001 쓰기 권한·용량을 배포 전에 확인하세요. chart는 새 RWX PVC를 만들거나 기존 PVC의 accessModes·이름·내용을 변경하지 않습니다.

**기존 설치에 예제의 전체 `configuration.jobController`를 그대로 덮어쓰지 마세요.** 현재 환경의 전체 객체와 실행 프로필·revision·예산·기타 값을 유지하고 `shared_limit`, 두 `kind_limits`, 사용 중인 Worker profile의 `slots=1`만 옮겨 적용하세요. `configuration.agents`의 검증된 binding도 그대로 유지합니다. `applyJobController=false`를 쓰는 환경은 같은 capacity 설정이 JC에 먼저 적용되어 있어야 하며, Helm 렌더링만으로 DB 적용 여부를 보증하지 않습니다.

복제 수가 2개 이상인 Worker가 하나라도 있으면 chart는 두 종류의 설정된 replicas와 kind_limits 일치, shared_limit이 종류별 한도 합계 이상인지, 활성 Worker의 선택한 capacity profile이 같은 kind·slots=1인지 검사합니다. 복제 Worker에 같은 `WORKER_ID` 환경변수를 지정하면 거절합니다. 기본 Worker ID와 boot ID는 프로세스마다 생성되어 서로의 등록을 교체하지 않습니다. `CAPACITY_PROFILE_ID`를 바꿨다면 해당 프로필도 위 조건을 만족해야 합니다.

기존 chart 관리 보고서 PVC를 단순히 `existingClaim`으로 옮기면 Helm에서 원래 PVC가 삭제될 수 있습니다. `retainOnDelete`를 먼저 적용하는 보존 단계·파일 백업·필요한 복사·복구 계획을 준비하고 [기존 설치 업그레이드](../../docs/helm-upgrade-existing.md)를 따르세요. 기존 DB PVC도 유지합니다. `persistence.enabled=false`로 저장소 조건을 우회하지 않습니다. 기본 리소스 기준으로 Worker 4개 추가는 CPU 요청 1core, 메모리 요청 2Gi·한도 8Gi 증가이며 총 Pod 수는 기본 8개에서 12개가 됩니다.

렌더링·검사 후 배포는 별도 승인으로 진행합니다. 실제 검수는 Worker 6개 고유 등록, 종류별 동시 3개·4번째 대기, 같은 Pod 중복 실행 차단, Ops 3개의 저장소 쓰기와 보고서 발행·다운로드, RCA 실행, 실패 시 슬롯 반환·늦은 결과 차단을 확인해야 합니다. 축소할 때 진행 작업을 강제로 성공/취소 처리하지 않으며 저장소를 삭제하지 않습니다.
