# DSX 구성·연동 기록

- **작성자**: 오수경
- **대상 기간**: 2026-09-01 ~ 2026-09-04 (관측된 로그·Helm 배포 시각 기준)
- **대상 환경**: CSC `dell-l40s` 단일 노드 클러스터 / CPC `vessl-k8s-master-01` 클러스터
- **문서 상태**: 초안. 타 팀원 기록과 취합 필요.

---

## 0. 근거 자료와 확인 범위

### 0.1 실제로 참고한 자료

| 유형 | 내용 |
| --- | --- |
| 명령 실행 결과 | `kubectl get/describe/logs`, `helm list/get values/status`, `curl`(NATS monitoring API, Mimir API), `mqttx pub/sub`, `ss`, `docker ps` 출력 |
| 클러스터 설정 | Helm computed values(`dsx`, `fleet-intelligence-agent`, `my-grafana`), ConfigMap `auth-callout-permissions`, Prometheus rule 파일 |
| 공식 문서 | NVIDIA DSX Exchange(architecture, stateless async bus, 인증 모드), Fleet Intelligence Client(skills, SDK, overview), NVSentinel(data-flow, health-event-data-model, datastore-connection) |
| 저장소 | `github.com/dsx-ai-factory/fleet-intelligence-agent`, OCI 차트 `oci://ghcr.io/dsx-ai-factory/charts/fleet-intelligence-agent` |

### 0.2 확인하지 못한 범위

- **타 팀원의 다른 채팅·작업 기록에는 접근하지 못했다.** 본 문서는 단일 대화 세션에서 확인된 내용만 담는다.
- `dsx-ai-factory` 저장소는 비공개로 보이며, 차트 values 외 소스·문서 원문은 확인하지 못했다.
- NVSentinel은 **문서 조사만** 수행했다. 이번에 확인한 두 클러스터의 Pod 목록에서 `nvsentinel` 네임스페이스나 관련 Pod를 관측하지 못했다. 다른 클러스터에 설치되어 있을 수 있으므로 "미설치"로 단정하지 않는다.
- Omniverse(Kit / Isaac Sim / Nucleus) 본체의 실행 위치를 **특정하지 못했다.**
- CPC로 지목된 `192.168.20.171~174`와 실제 관측된 노드 IP가 일치하지 않는다(§3.1 참조).
- `192.168.20.181`(proxy)의 역할을 확인하지 못했다.

### 0.3 이전 구성과 이번 기간 작업 구분

| 구분 | 내용 |
| --- | --- |
| 이전부터 존재 | CPC의 Run:ai, GPU Operator, monitoring(Prometheus/Thanos/Loki/MinIO), Knative, Dynamo, `runai-rca`, `ns-aiq` 등 (AGE 40~296일) |
| 이번 기간 신규 | DSX Exchange(CSC/CPC 양쪽), Keycloak, Envoy Gateway, Robusta, Fleet Intelligence Agent, Mimir, Grafana, Trident(CSC) |

---

## 1. 이번에 다룬 범위와 목적

### 1.1 목적

1. DSX Exchange와 Fleet Intelligence Agent를 결합한 구조의 **동작 방식과 순서 파악**
2. 두 시스템이 **실제로 연결되어 있는지 검증**
3. GPU 텔레메트리의 **장기 저장 경로 확보**(Mimir + Grafana)
4. 향후 Omniverse 디지털 트윈 연동을 위한 선행 조건 정리

### 1.2 조사만 한 부분

- DSX Exchange 아키텍처, 무상태 비동기 버스 설계 원칙, 인증 모드
- NVSentinel HealthEvent 데이터 모델 및 MongoDB 조회 방법
- Fleet Intelligence Agent Skills(`node-rca-rcca`, `fleet-health-report`)
- Omniverse 연동 방식(설계 검토만, 미구현)

### 1.3 직접 구성·검증한 부분

- DSX 리프노드 페더레이션 상태 확인
- Keycloak OAuth2 기반 MQTT 인증 및 CPC→CSC 메시지 전달 검증
- Fleet Intelligence Agent enrollment 문제 해결
- Mimir 설치 및 데이터 수신 확인
- Grafana 설치

---

## 2. 구성 요소와 역할

### 2.1 DSX Exchange 본체

| 항목 | 내용 |
| --- | --- |
| 정식명 | NVIDIA DSX Exchange |
| Helm 릴리스 | `dsx` / chart `nats-event-bus-0.2.0` / app `0.2.0` |
| 배포 시각 | CSC 2026-09-01 15:50 (revision 4) |
| 분류 | **DSX 자체 구성 요소** |
| 확인 수준 | 문서 조사 + 설정 확인 + 실행 검증 |

구성 모듈(양 클러스터 동일):

| 모듈 | Pod | 역할(문서) | 이번 환경에서 확인된 역할 |
| --- | --- | --- | --- |
| Event Bus | `nats-0/1/2` (2/2) | MQTT 3.1.1 + HA + 리프노드 페더레이션 | 동일. 실제 메시지 전달 검증됨 |
| Auth Callout | `dsx-auth-callout` | OAuth2/mTLS/NKey 인증, 토픽 ACL | NKey·OAuth2 두 경로 모두 동작 확인 |
| NACK | `nack` | JetStream 스트림 선언적 관리 | `$MQTT_*` 내장 스트림 5개 생성 확인 |
| Surveyor | `dsx-surveyor` | Prometheus 메트릭 노출(:7777) | 기동 확인. 스크레이프 대상 등록 여부 미확인 |

> 문서 근거: MQTT 5가 아닌 3.1.1을 채택한 이유는 BMS·프로세스 제어 업계의 클라이언트 보급률 때문이라고 명시되어 있다.

### 2.2 Fleet Intelligence Agent

| 항목 | 내용 |
| --- | --- |
| 정식명 | Fleet Intelligence Agent (`fleetint`) |
| 저장소 | `github.com/dsx-ai-factory/fleet-intelligence-agent` |
| 차트 | `oci://ghcr.io/dsx-ai-factory/charts/fleet-intelligence-agent` |
| 버전 | `1.5.0-rc.1` (릴리스 후보) |
| 이미지 | `ghcr.io/dsx-ai-factory/fleet-intelligence-agent:1.5.0-rc.1`<br>digest `sha256:d9a61090116f1f9a2f183c6779fb1b76f4792f6e927b60c64f33a5137577d18b` |
| 기반 | leptonai/gpud |
| 분류 | **DSX 주변 인프라 / 데이터 생산자.** DSX Exchange의 필수 구성 요소는 아님 |
| 확인 수준 | 문서 + 설정 + 실행 |

수집 대상(문서): GPU 전력·온도·클럭·사용률·메모리, XID/SXID, NVLink/NVSwitch/PCIe, 드라이버·CUDA·InfiniBand, CPU/메모리/디스크/네트워크, Fabric Manager 로그, DCGM HostEngine 상태.

내보내기 방식(문서): ① HTTP REST/Prometheus 서버 ② 로컬 파일(CSV/JSON) ③ OTLP over HTTP. **MQTT 발행 기능은 없다.**

> 상태 저장: `/var/lib/fleetint/fleetint.state`. 문서상 이 디렉터리를 삭제·교체하면 동일 물리 노드가 새 아이덴티티로 중복 등록된다.

### 2.3 Grafana Mimir

| 항목 | 내용 |
| --- | --- |
| Helm 릴리스 | `mimir` / chart `mimir-distributed-6.2.0` / app `3.2.0` |
| 배포 시각 | 2026-09-04 15:20 |
| Helm 상태 | **`failed`** (§6.4) |
| 분류 | **주변 인프라(장기 메트릭 저장소).** DSX 구성 요소 아님 |
| 확인 수준 | 설치 + 데이터 수신 검증 |

분산 모드로 설치되어 있으며 ingester/store-gateway가 zone a/b/c로 3중화, Kafka(ingest storage) 포함.

### 2.4 Grafana

| 항목 | 내용 |
| --- | --- |
| Helm 릴리스 | `my-grafana` / chart `grafana-13.2.0` / app `13.2.1` |
| 이미지 | `docker.io/grafana/grafana:13.2.1-distroless` |
| 배포 시각 | 2026-09-04 16:31 |
| 확인 수준 | 설치까지. 데이터소스 연결은 §6.5 |

### 2.5 Keycloak

| 항목 | 내용 |
| --- | --- |
| Pod | `dsx-keycloak-0`, `keycloak-operator` (namespace `keycloak`) |
| Realm | `dsx` |
| 분류 | **DSX 인증 의존 구성 요소** |
| 확인 수준 | 실행 검증(토큰 발급 성공) |

### 2.6 NVSentinel — 문서 조사만

| 항목 | 내용 |
| --- | --- |
| 정식명 | NVIDIA NVSentinel |
| 저장소 | `github.com/NVIDIA/NVSentinel` |
| 문서 | `docs.nvidia.com/nvsentinel` (문서 기준 v1.21.0) |
| 확인 수준 | **문서 조사만.** 이번 관측 범위에서 배포 확인 못 함 |

핵심 구조: Health Monitor가 gRPC로 `HealthEvent` 발행 → Platform Connector가 MongoDB에 저장 + K8s 노드 컨디션 갱신 → MongoDB change stream으로 Fault Quarantine / Node Drainer / Fault Remediation / Health Analyzer가 반응.

저장 형식(문서 `health-event-data-model`):

```go
type HealthEventWithStatus struct {
    CreatedAt         time.Time                 `bson:"createdAt"`
    HealthEvent       *protos.HealthEvent       `bson:"healthevent,omitempty"`
    HealthEventStatus *protos.HealthEventStatus `bson:"healtheventstatus"`
}
```

- BSON 필드명은 소문자 한 단어(`healthevent`, `healtheventstatus`)
- `healthevent` 주요 필드: `agent`, `componentClass`, `checkName`, `isFatal`, `isHealthy`, `message`, `recommendedAction`, `errorCode[]`, `entitiesImpacted[]`, `metadata{}`, `generatedTimestamp`, `nodeName`(필수), `processingStrategy`
- `healtheventstatus`: `nodeQuarantined`, `userPodsEvictionStatus`, `faultRemediated`, `spanIds{}` 등
- MongoDB 대신 PostgreSQL 사용 가능(기능 동등, JSONB 저장), Event Exporter는 CloudEvents 출력

### 2.7 Omniverse 관련 — 위치 미확인

CSC 호스트(`dell-l40s`)의 `docker ps`에서 관측된 컨테이너:

| 포트 | 컨테이너 | 이미지 |
| --- | --- | --- |
| 9901 | `omni-ui-mcp` | `omni-ui-mcp:local` (command `omni-ui-aiq`) |
| 9902 | `kit-mcp` | `kit-mcp:local` |
| 9903 | `usd-code-mcp` | `usd-code-mcp:local` |
| 9904 | `isaacsim-mcp` | `isaacsim-mcp:local` |
| 8001 | `mcp-embedder` | `nvcr.io/nim/nvidia/nv-embedqa-e5-v5:latest` |
| 8002 | `mcp-reranker` | `nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:latest` |

> **이들은 Omniverse 본체가 아니라 MCP 서버다.** Kit/Isaac Sim 프로세스는 이 호스트의 `docker ps`에 없다. 실제 실행 위치는 미확인.

기타 관측 컨테이너: `kind-registry`(zot), `dsx-exchange-control-plane`(kind 노드, `127.0.0.1:16443`, `0.0.0.0:18180->30180`), `fingerpoint`(pytorch 25.01, 12개월 전 생성).

> ⚠️ `dell-l40s`에는 **kubeadm 클러스터와 kind 클러스터가 공존**한다. kubeconfig 컨텍스트 혼동 주의.

### 2.8 이번 대화에서 이름만 언급되고 확정하지 못한 것

- **Alloy**: Grafana Alloy(`grafana/alloy`)를 가정하고 논의했으나 **설치·사용하지 않았다.** OTel Collector 대안으로만 거론됨.
- **agentgateway**: CPC/CSC에 MCP를 묶는 게이트웨이로 계획에 등장했으나, 어떤 제품인지 확정하지 못했다. 관측된 Envoy Gateway 리소스와의 관계도 미확인.

---

## 3. 실제 배치 구조

### 3.1 클러스터·노드

| 역할 | 호스트 | IP | 비고 |
| --- | --- | --- | --- |
| CSC | `dell-l40s` | 192.168.20.186 | 단일 노드 kubeadm 클러스터 |
| CPC | `vessl-k8s-master-01` 클러스터 | — | 다중 노드 |
| CPC GPU 노드 | `dgx01` | 192.168.20.100 | A100-SXM4-**80GB** ×8 |
| CPC GPU 노드 | `dgx02` | 192.168.20.101 | A100-SXM4-**40GB** ×8 |
| CPC 기타 | `k8s-lb-01`, `k8s-lb-02`, masters | 192.168.20.172~176 | Prometheus targets 기준 |

> ⚠️ **불일치**: CPC를 `192.168.20.171~174`로 들었으나, 실제 관측된 노드 IP는 `100, 101, 172~176`이다. 이 클러스터가 CPC 중 하나인지 별개 클러스터인지 **팀 확인 필요**.

DNS: `dsxcsc.uclick.ai.kr`(→186), `dsxkeycloak.uclick.ai.kr`(→186). 둘 다 해석·접속 확인됨.

### 3.2 CSC 리소스

| Namespace | 리소스 | 이름 |
| --- | --- | --- |
| `dsx` | StatefulSet | `nats` (0/1/2) |
| `dsx` | Deployment | `dsx-auth-callout`, `dsx-surveyor`, `nack` |
| `dsx` | Service | `dsx-auth-callout`(8000), `dsx-auth-callout-metrics`(9090), `dsx-surveyor`(7777), `nats`(4222/7422/1883), `nats-headless` |
| `dsx` | ConfigMap | `auth-callout-permissions`, `dsx-auth-callout-config` |
| `dsx` | Secret | `auth-callout-keys` |
| `dsx` | TCPRoute | `nats-client`, `nats-leafnode`, `nats-mqtt` |
| `dsx` | ServiceMonitor | `dsx-auth-callout`, `dsx-surveyor` / PodMonitor `nack` |
| `keycloak` | StatefulSet | `dsx-keycloak-0` |
| `envoy-gateway-system` | Service(LB) | `envoy-csc-gateway-shared-gateway-e059d0eb` → **192.168.20.186**, `1883/4222/7422` |
| `envoy-gateway-system` | Service(LB) | `envoy-keycloak-keycloak-gateway-997ad362` → **192.168.20.186**, `443:31263` |
| `csc-gateway` | Gateway | `shared-gateway` (class `eg`, PROGRAMMED True) |
| `keycloak` | Gateway | `keycloak-gateway` (listener hostname `dsxkeycloak.uclick.ai.kr`, `allowedRoutes.namespaces.from: Same`) |
| `mimir-test` | 다수 | distributor, ingester zone a/b/c, querier×2, query-frontend, query-scheduler×2, store-gateway zone a/b/c, compactor, ruler, alertmanager, gateway, minio, kafka, overrides-exporter, rollout-operator |
| `mimir-test` | Service | `mimir-gateway` **ClusterIP** `10.36.172.150`, `80/TCP, 8080/TCP` |
| `monitoring` | Deployment | `my-grafana` → Service **NodePort** `80:31891` |
| `trident` | — | Trident CSI |
| — | StorageClass | `ontap-nas-economy-sc` (default, `csi.trident.netapp.io`) |

Mimir PVC(모두 `ontap-nas-economy-sc`): ingester/store-gateway 각 2Gi, compactor 2Gi, alertmanager 1Gi, kafka 5Gi, **minio 5Gi**.

> Grafana `persistence.enabled: false` → `storage` 볼륨이 **EmptyDir**. Pod 재시작 시 데이터소스·대시보드 유실.

### 3.3 CPC 리소스 (DSX·Fleet 관련만)

| Namespace | 리소스 | 이름 / 배치 |
| --- | --- | --- |
| `dsx` | StatefulSet/Deployment | `nats-0/1/2`, `dsx-auth-callout`, `dsx-surveyor`, `nack` |
| `dsx-envoy-gateway-system` | Pod | `envoy-cpc-1-gateway-shared-gateway-dd5d3866-*` (dgx01), `envoy-gateway-*` (dgx01) |
| `fleet-intelligence` | **DaemonSet** | `fleet-intelligence-agent`, desired 2 |
| `fleet-intelligence` | Pod | dgx01, dgx02 각 1개 |
| `fleet-intelligence` | ConfigMap | `kube-root-ca.crt`만 |
| `fleet-intelligence` | **Service** | **없음** |
| `fleet-intelligence` | Secret | `uclix-fleetint-token` (enrollment 토큰) |

**노드 고정 방식**: `nodeSelector: nvidia.com/gpu.deploy.dcgm=true`. GPU Operator가 DCGM 배포 노드에 자동으로 붙이는 라벨이며, 차트 기본값이다. 즉 dgx01/dgx02에 있는 것은 **스케줄 결과가 아니라 라벨 기반 고정**이다.

DaemonSet 주요 설정:

- `hostPID: true`, `securityContext.privileged: true`, `runAsUser/Group: 0`, `runtimeClassName: nvidia`
- hostPath 볼륨: `/dev`, `/sys`, `/etc/os-release`, `/etc/machine-id`, `/var/lib/systemd/pstore`, `/var/log/fabricmanager.log`, **`/var/lib/fleetint`(state, DirectoryOrCreate)**
- Init container `enroll` → 본 컨테이너 `fleet-intelligence-agent` (port 15133)
- `serviceAccount.automountToken: false`

CPC 기존 인프라(참고): `runai`, `runai-backend`, `runai-rca`(grafana-mcp/kubernetes-mcp/postgres-mcp/runai-mcp/typedb 포함), `gpu-operator`, `monitoring`(Prometheus/Thanos/Loki/MinIO), `knative-serving`, `dynamo-system`, `ns-aiq`, `nvidia-network-operator`, `robusta`, `vllm-semantic-router-system`.

---

## 4. 구성 요소 간 연결 관계

### 4.1 [검증됨] CPC NATS → CSC NATS (리프노드 페더레이션)

| 항목 | 내용 |
| --- | --- |
| 출발 | CPC `dsx/nats-0,1,2` |
| 도착 | CSC `dsx/nats` (Envoy LB 경유) |
| 목적 | 클러스터 간 토픽 페더레이션 |
| 요청 개시 | **CPC 측**(remote 설정 보유) |
| 데이터 방향 | 양방향(export 설정에 따름) |
| 경유 | `tls://dsxcsc.uclick.ai.kr:7422` → `envoy-csc-gateway-shared-gateway` → TCPRoute `nats-leafnode` → `nats` Service |
| 프로토콜/포트 | NATS leafnode / **7422** |
| 정의 위치 | CPC Helm values `crossLayer.cscEndpoint` |

**검증 내용**

- CPC `varz.leaf.remotes[0].urls = ["dsxcsc.uclick.ai.kr:7422"]`, `local_account: CSC`
- CSC `/leafz`에 CPC 세션 존재. 소스 IP는 `10.35.227.35`(Envoy Pod IP) — LB SNAT 결과이며 정상
- CPC `nats-2` 로그: `[INF] 192.168.20.186:7422 - lid:12 - Leafnode connection created for account: CSC`
- 3개 Pod 전부 연결됨. `/leafz`는 호출한 Pod 시야만 보여주므로 개별 확인 필요

**정정 기록**: 초기에 "리프노드 미연결" 및 "nats-2 누락"으로 판단했으나 둘 다 오판이었다.

### 4.2 [검증됨] MQTT 클라이언트 → CSC (OAuth2 인증)

| 항목 | 내용 |
| --- | --- |
| 경유 | `dsxcsc.uclick.ai.kr:1883` (mqtts, Envoy TLS 종단) → TCPRoute `nats-mqtt` |
| 프로토콜 | MQTT **3.1.1** over TLS |
| 인증 | Keycloak realm `dsx`, client_credentials, client `mqtt-client` → JWT를 MQTT username `oauthtoken` + password로 전달 |
| CA | 사설 루트 CA `/usr/local/share/ca-certificates/dsx-root-ca.crt` |
| 정의 위치 | ConfigMap `auth-callout-permissions` |

토큰 엔드포인트: `https://dsxkeycloak.uclick.ai.kr/realms/dsx/protocol/openid-connect/token`

**검증 결과**

- CSC 내부 pub/sub 왕복 성공 (`test/topic`, payload 21B 수신)
- 토큰 수명이 짧아(약 5분 추정) 만료 시 `Connection refused: Not authorized` 발생 — 재발급으로 해소

### 4.3 [검증됨] CPC 발행 → CSC 수신 (접두어 부착 확인)

가장 중요한 검증. 실제 관측 결과:

```
[CPC] mqttx pub -h 127.0.0.1 -p 1884 -t 'test/cpc2csc/ping' -m 'federation test'
      (kubectl -n dsx port-forward svc/nats 1884:1883 경유)

[CSC] mqttx sub -h dsxcsc.uclick.ai.kr -p 1883 -l mqtts -t 'cpc/1/test/cpc2csc/ping'
      → topic: cpc/1/test/cpc2csc/ping, qos: 0, size: 15B
        federation test
```

- CPC에서 `test/cpc2csc/ping`으로 발행 → CSC에서 **`cpc/1/`이 접두어로 붙어** 도착
- `cpc.{id}.` 접두어 부착이 문서 설명대로 동작함을 확인
- 이로써 NATS·Envoy·TLS·Keycloak·auth-callout·리프노드·`cpcExports` 라우팅 전 구간이 검증됨

### 4.4 [부분 검증 / 제약] 와일드카드 구독 거부

| 구독 토픽 | 결과 |
| --- | --- |
| `test/topic` (정확한 이름) | ✅ 성공 |
| `cpc/1/test/cpc2csc/ping` (정확한 이름) | ✅ 성공 |
| `test/#` | ❌ SUBACK 128 |
| `cpc/1/test/#` | ❌ SUBACK 128 |
| `cpc/+/test/#` | ❌ SUBACK 128 |

- `#`가 포함되면 거부. `+`는 단독 검증하지 못함
- `dsx-auth-callout` 로그에 거부 기록 **없음** → 거부 주체는 auth-callout이 아니라 NATS 서버로 추정
- `test.>`가 허용 목록에 있음에도 `test/#` 구독이 거부된 점은 **미해결**

> ⚠️ 운영 영향: 구독자가 토픽을 하나하나 나열해야 한다. 노드/GPU 증가 시 구독 재작성이 필요해지므로 소비자 설계 전에 해결해야 한다.

### 4.5 [검증됨] Fleet Agent → NVIDIA Fleet Intelligence (enrollment)

| 항목 | 내용 |
| --- | --- |
| 출발 | CPC `fleet-intelligence-agent` init container `enroll` |
| 도착 | `https://data.fleet-intelligence.nvidia.com` |
| 방향 | 아웃바운드 HTTPS (인터넷) |
| 인증 | Secret `uclix-fleetint-token` 의 `token` 키 |
| 정의 위치 | Helm values `enroll.endpoint` / `enroll.tokenSecretName` |

실행 커맨드(관측):

```
/usr/bin/fleetint enroll --endpoint "https://data.fleet-intelligence.nvidia.com" --token "${FLEETINT_TOKEN}"
```

**호스트 구분 (중요)**

| 호스트 | 용도 |
| --- | --- |
| `fleet-intelligence.ngc.nvidia.com` | 웹 UI(토큰 발급, 대시보드). API 아님 |
| `data.fleet-intelligence.nvidia.com` | **에이전트 데이터 수집 API** |
| `api.fleet-intelligence.nvidia.com` | `nvfleetint` CLI/SDK 조회 API (문서 기준) |

### 4.6 [사용자 진술] Fleet Agent → Mimir (OTLP)

| 항목 | 내용 |
| --- | --- |
| 설정 | `FLEETINT_COLLECTOR_ENDPOINT: http://192.168.20.186:8080/otlp` |
| 프로토콜 | OTLP over HTTP (평문) |
| 테넌트 | `cpc-1` |
| 검증 | Mimir 쿼리로 `fleetint_agent_up`, `dcgm_fi_dev_*` 수신 확인 |

> ⚠️ 이 환경변수는 사용자 진술로 확인했으며, `helm get values` 출력에는 나타나지 않았다(값 확인 시점 차이로 추정). **재확인 필요.**
>
> ⚠️ 평문 HTTP이며 인증이 없다. 임의 메트릭 주입 및 GPU 인벤토리 노출 위험.

### 4.7 [미연결] Fleet Agent 로컬 API

- 본 컨테이너 실행 인자: `run --log-level=warn --listen-address=127.0.0.1:15133 --retention-period=24h --components=all`
- `127.0.0.1` 바인딩 + `fleet-intelligence` 네임스페이스에 **Service 없음** → 클러스터 내 다른 Pod에서 접근 불가
- 로그의 모든 HTTP 요청이 `127.0.0.1` 출처
- `hostPID: true`는 PID만 공유하며 네트워크는 공유하지 않으므로 호스트에서도 접근 불가

엔드포인트(문서/로그 기준): `/healthz`, `/metrics`, `/v1/metrics`, `/v1/states`, `/v1/events`

### 4.8 [미연결 / 미확인] 나머지

| 구간 | 상태 |
| --- | --- |
| Fleet Agent → DSX MQTT | **미연결.** 에이전트에 MQTT 발행 기능 자체가 없음. 브리지 필요 |
| DSX ↔ NVSentinel | 미확인 |
| DSX ↔ Omniverse | 미연결. Omniverse 위치도 미확인 |
| CPC agentgateway ↔ CSC agentgateway | **계획 단계.** 구성 미확인 |
| Mimir ↔ Grafana | §6.5 |

---

## 5. 직접 수행한 작업과 변경 사항

### 5.1 Fleet Intelligence Agent enrollment 엔드포인트 수정

**문제**: init container `enroll`이 `Init:CrashLoopBackOff`, exit code 1, 재시작 7회.

로그:

```
✔ NVIDIA GPU detected
✔ supported GPU architecture detected: ampere
✔ NVIDIA driver detected: 580.173.02
✔ nvattest detected
✔ DCGM HostEngine version is supported: 4.2.3
✘ failed to make backend request: Post "https://ngc.nvidia.com/signout": backend redirects are not allowed
```

**원인 규명 과정**

1. 토큰 무결성 확인: 70바이트, 마지막 바이트 `0x6a` — 개행 없음, 정상
2. 헤더 없이 동일 URL 요청 → 동일하게 `307 → signout` 반환. 즉 **해당 URL은 인증과 무관하게 리다이렉트하는 웹 UI 진입점**
3. 에이전트는 보안상 리다이렉트를 따르지 않도록 되어 있어 실패

**변경**

| 항목 | 변경 전 | 변경 후 |
| --- | --- | --- |
| `enroll.endpoint` | `https://fleet-intelligence.ngc.nvidia.com/` | `https://data.fleet-intelligence.nvidia.com` |

**결과**: init container `Exit Code: 0`, `Completed`. 본 컨테이너 정상 기동.

**부수 변경**: `logLevel: warn` → `debug` (Helm revision 2, 2026-09-04 16:24). 전송 로그 확인 목적.

### 5.2 실패한 시도 기록

| 시도 | 결과 | 원인 |
| --- | --- | --- |
| `helm upgrade ... fleet-intelligence-agent-1.5.0-rc.1` | 실패 | 차트 이름을 경로로 사용. OCI 경로 필요 |
| `helm show values fleet-intelligence-agent` | 실패 | 릴리스 이름으로는 조회 불가 |
| `kubectl debug --target=enroll -- curl ...` | 실패 | `--target`이 `--` 뒤로 밀려 curl 인자로 전달됨 |
| `kubectl exec ... -c enroll -- cat/sh/bash` | 실패 | distroless 이미지, 셸·유틸리티 없음 |
| `kubectl exec ... wget /v1/metrics` | exit 137 | OOM 추정. 해당 엔드포인트는 응답에 4.7초 소요되는 무거운 경로 |

### 5.3 Mimir·Grafana 설치

| 릴리스 | Namespace | 시각 | 상태 |
| --- | --- | --- | --- |
| `mimir` | `mimir-test` | 2026-09-04 15:20 | **failed** |
| `my-grafana` | `monitoring` | 2026-09-04 16:31 | deployed |
| `trident` | `trident` | 2026-09-04 15:26 | deployed |

> 상세 values는 이번 대화에서 확인하지 못했다. 별도 보관 필요.

### 5.4 작성만 하고 적용하지 않은 것

다음은 **논의·작성 단계에서 멈춘 것**으로, 클러스터에 적용하지 않았다.

- OTel Collector values (노드 라벨 승격 + `gpuInfo.gpus` 제거)
- Grafana provisioning values (persistence + 데이터소스)
- Mimir 노출용 Gateway / HTTPRoute
- Fleet Agent `listenAddress: 0.0.0.0:15133` 변경 + Service + NetworkPolicy

---

## 6. 검증 결과와 현재 이해

### 6.1 DSX Exchange 설정 (설정 확인)

**CPC** `helm -n dsx get values dsx -a`:

```yaml
crossLayer:
  cpcExports:        [test.cpc2csc.>]
  cscExports:        [test.broadcast.>]
  cscPrefixedExports: [test.csc2cpc.>]
cscEndpoint: tls://dsxcsc.uclick.ai.kr:7422
```

**CSC**: `cscEndpoint: ""`, 세 리스트 모두 비어 있음. CSC는 리프를 받는 쪽이므로 정상.

> ⚠️ computed values 출력에는 서브차트에 상속된 **빈 crossLayer 블록이 다수 섞여** 있다. `cscEndpoint`가 채워진 블록이 실제 적용값이다.
>
> ⚠️ 문서 경고: 세 export 리스트에 동일 서브젝트 패턴이 중복되면 순환 NATS import가 발생해 NATS Pod가 CrashLoopBackOff에 빠지며, **설치 시점에는 아무 에러도 표시되지 않는다.**

**MQTT 스트림 설정**:

```yaml
mqttStreams:
  maxAge: 3h
  maxBytes: 67108864   # 64 MiB
  replicas: 3
  storage: memory
```

**보관 특성**: QoS 1/2 및 retained 메시지만 JetStream에 저장되며 3시간/64MiB 중 먼저 도달하는 조건에서 삭제. `storage: memory`이므로 **NATS Pod 전체 재시작 시 소멸**.

### 6.2 인증 설정 (설정 확인)

ConfigMap `auth-callout-permissions` → `permissions.json`:

```json
{
  "mtls": {},
  "noauth": null,
  "nkey": {
    "leaf-cpc-1":      {"account": "CSC", "public_key": "${NKEY_LEAF_CPC_1_PUBKEY}"},
    "nack-controller": {"account": "CSC", "public_key": "${NKEY_NACK_USER_PUBKEY}"},
    "surveyor":        {"account": "SYS", "public_key": "${NKEY_SURVEYOR_PUBKEY}"}
  },
  "oauth2": {
    "mqtt-client": {
      "account": "CSC", "azp": "mqtt-client",
      "permissions": {
        "pub": {"allow": ["test.>", "perf.>", "cpc.*.test.>"]},
        "sub": {"allow": ["test.>", "perf.>", "cpc.*.test.>"]}
      }
    }
  }
}
```

읽어낼 수 있는 사실:

- `leaf-cpc-1` — CPC를 여러 대 받도록 설계됨. 현재 **1개만 등록**. 확장 시 `leaf-cpc-2` 이상 추가 필요
- `noauth: null` — 익명 접속 차단
- 애플리케이션용 계정은 `mqtt-client` **하나뿐**이며, 허용 토픽이 `test.*`, `perf.*` 계열로 **테스트 범위에 한정**되어 있음

> ⚠️ 실제 텔레메트리 토픽(`telemetry.*` 등)으로 발행하면 인증은 통과하되 발행이 조용히 거부된다. permissions와 `cpcExports`를 **함께** 수정해야 한다.

`dsx-auth-callout` 로그에서 `nack-controller`의 NKey 인증이 20~30초 주기로 성공하는 것을 확인. 반복 출력되는 `dial tcp 127.0.0.1:4317: connect: connection refused`는 OTLP 트레이싱 수신처 부재로 인한 것이며 인증 기능과 무관.

### 6.3 JetStream 상태 (실행 확인)

`$MQTT_msgs`, `$MQTT_out`, `$MQTT_qos2in`, `$MQTT_rmsgs` 모두 0건. `$MQTT_sess`만 2건(2026-09-02 06:30:33 ~ 06:31:08, 약 35초). DSX 애플리케이션 스트림은 생성되지 않았고 `$MQTT_*` 내장 스트림 5개만 존재.

→ **테스트 이전에는 실데이터가 발행된 적이 없다.**

### 6.4 Mimir 상태

**Helm `failed` 원인 (확인)**

```
mimir-make-minio-buckets-5.4.0   Complete   1/1     ← 버킷 생성 성공
mimir-minio-post-job             Failed     0/1     ← 실패
```

버킷 `mimir-tsdb`, `mimir-ruler`는 정상 생성되었고 post-job만 실패. Mimir 동작 자체에는 영향 없어 보이나 **post-job 로그는 미확인**.

**데이터 수신 (검증됨)**

테넌트 `cpc-1`, `kubectl port-forward`로 `127.0.0.1:18080` 경유 조회.

```
GET /prometheus/api/v1/query?query=fleetint_agent_up
→ {"__name__":"fleetint_agent_up","job":"fleet-intelligence-agent"}, value "1"
```

수집 메트릭 계열(총 약 95개):

| 계열 | 개수 | 예시 |
| --- | --- | --- |
| GPU (DCGM) | 약 60 | `dcgm_fi_dev_gpu_temp`, `dcgm_fi_dev_power_usage`, `dcgm_fi_dev_ecc_dbe_agg_total`, `dcgm_fi_dev_nvlink_error_dl_crc`, `dcgm_fi_prof_*` |
| 노드 | 약 30 | `cpu_used_percent`, `memory_used_bytes`, `disk_*`, `network_ethernet_*`, `os_*` |
| 에이전트 | 4 | `fleetint_agent_up`, `fleetint_agent_uptime_seconds`, `fleetint_agent_collection_summary`, `fleetint_gpu_firmware_info`, `fleetint_node_software_info`, `fleetint_node_uptime_seconds` |
| 메타 | 1 | `target_info` |

**라벨 구조 (중요)**

`dcgm_fi_dev_gpu_temp` — **16 시계열** (GPU 8 × 노드 2). 정상.

```
labels: device, gpu, gpu_serial, job, model_name, pci_bus_id, uuid
```

노드 이름 라벨은 없으나 `uuid`가 고유하여 데이터는 섞이지 않는다. 또한 `model_name`이 노드별로 다르다(`A100-SXM4-80GB`=dgx01, `A100-SXM4-40GB`=dgx02).

`fleetint_agent_up` — **1 시계열**. 라벨이 `job` 하나뿐.

```
labels: job
```

→ dgx01/dgx02가 동일 시계열을 공유. **노드 단위 메트릭(약 30개)은 두 노드가 구분되지 않는다.**

`target_info` — **9 시계열** (노드 2대인데 9개)

```
labels: host_name, machine_id, node_group(prod-a), compute_zone(us-east-1c),
        gpuInfo_gpus, job
```

- 노드 식별 정보(`host_name` = dgx01/dgx02)는 **여기에만** 존재
- `gpuInfo_gpus`에 GPU 8장 정보 JSON 전체가 라벨 값으로 들어감. **배열 순서가 매 전송마다 달라** 새 시계열이 계속 생성됨 → 카디널리티 증가

**정정 기록**: 초기에 "두 노드 데이터가 섞여 손상 중"이라고 판단했으나, GPU 메트릭은 `uuid`로 구분되어 정상이다. 실제 영향 범위는 **노드 단위 메트릭 약 30개**로 한정된다.

**원인 (문서 확인)**: 차트 주석에 명시 — *"Agent identity flows through OTLP resource attributes (machine.id, GPU UUIDs)"*. 노드 식별자를 리소스 속성으로만 전송하므로 Mimir에서 `target_info`로 분리된다.

**해결 경로 검토 결과**

| 경로 | 판정 |
| --- | --- |
| 에이전트 차트 설정 | ❌ 불가. values에 라벨/속성 조작 항목 없음 |
| `otelGateway` 옵션 | ❌ 부적합. 주석상 백엔드 JWT 인증 전용(`enroll.endpoint`, `sakToken` 필요) |
| Mimir 리소스 속성 승격 | ❓ `mimir -help`에서 `promote` 미발견. `-help-all` 재확인 필요 |
| 별도 OTel Collector 삽입 | ✅ 유력. **미적용** |

### 6.5 Grafana 상태

- Service NodePort `31891` → `http://192.168.20.186:31891` 접근 가능
- `persistence.enabled: false`, `datasources: {}` → **데이터소스 미설정, 영속성 없음**
- UI에서 `prometheus-1` 데이터소스에 URL `http://mimir-gateway.mimir-test.svc.cluster.local/prom...` 입력한 화면까지 확인. `X-Scope-OrgID` 헤더 설정 및 저장 여부는 **미확인**

> ⚠️ Mimir 멀티테넌시 사용 시 `X-Scope-OrgID` 헤더가 없으면 에러 없이 빈 결과가 반환된다.

### 6.6 CPC Run:ai Prometheus (참고 — 별도 계통)

DSX와 직접 관련은 없으나 메트릭 소스 후보로 조사했다.

```yaml
retention: 2h
remoteWrite:
  - name: runai
    basicAuth: {...}
    tlsConfig: {ca: runai-ca.pem}
```

- 컨테이너: `prometheus`, `config-reloader` — **Thanos 사이드카 없음**
- 즉 **2시간 버퍼 + Run:ai 백엔드로 remoteWrite 중계** 구조. 장기 저장소가 아니다
- `__name__` 개수 2351 (원본 + recording rule 결과)
- `serviceMonitorSelector: {}`, `podMonitorSelector: {}` → 전체 선택
- **down 상태 타겟**: `kube-controller-manager`, `kube-scheduler`, `kube-etcd`, `kube-proxy`, `mpi-operator`, knative(`activator-service`, `autoscaler`, `controller`, `webhook`) → 관련 알림 규칙이 무효 상태

DSX 연동에 재사용 가능한 규칙(`monitoring-node-gpu-ib-health` rule 파일):

```yaml
- alert: NodeGPUDegraded          # runai_node_gpu_count != 8
  labels: {action: cordon, severity: critical}
- alert: NodeInfinibandLinkDown   # node_infiniband_state_id{port="1", device=~"mlx5_[0-3,6-9]"} != 4
  labels: {action: cordon, severity: critical}
```

`action: cordon` 라벨이 이미 정의되어 있으나 이를 실행할 소비자가 없다. **Alertmanager webhook → MQTT 발행**이 브리지 1차 대상으로 적합해 보인다(제안, 미구현).

### 6.7 설계 원칙 (문서 확인)

DSX 문서 "Stateless Async Bus"에서 확인한 내용으로, 향후 브리지·토픽 설계에 직접 적용된다.

- 버스는 **현재 상태 이벤트**를 나르며 애플리케이션 상태를 담는 데이터베이스가 아니다
- **버스를 쓰지 말아야 할 때**: 호출자가 알려진 소유자로부터 즉각적인 응답을 받아야 진행 가능한 경우 → 직접 API 사용. **MCP는 요청-응답이므로 버스에 태우면 안 된다** (agentgateway 직결 계획이 옳음)
- 자주 바뀌는 라이브 값은 **retain하지 말 것**. retained는 시작 시점에 필요한 느리게 변하는 메타데이터용
- 패턴: 상태 변화 시 발행 + 변화 없어도 감당 가능한 주기로 **현재값 재발행** + 소비자 멱등 처리
- 값은 **델타가 아니라 현재값**으로 전송

> **정정 기록**: 초기에 "헬스 상태를 retained로, XID를 QoS 1로"라고 권고했으나 위 원칙과 어긋난다. 주기적 재발행 방식이 문서 의도에 부합한다. 에이전트의 `FLEETINT_COLLECT_INTERVAL=1m`이 이 패턴과 자연스럽게 맞는다.

### 6.8 Fleet Agent 잔여 경고

본 컨테이너 로그에서 지속 관측:

```
outbound validation issue ... field: attestationData.sdkResponse.resultMessage
  message: "length 2505 exceeds max 2048"
outbound validation issue ... field: attestationData.sdkResponse.evidences
  message: "evidence is required when success=true"

inventory attempt failed ... error: "node upsert response missing nodeGroup field"  (5분마다 반복)
```

- attestation 페이로드가 백엔드 스키마 한계를 초과. `1.5.0-rc.1`이 릴리스 후보인 점과 관련 가능성
- 인벤토리 업서트가 계속 실패. **UI에서 node group 미생성**이 원인일 가능성(추정). 차트에 `enroll.nodeGroup`, `enroll.computeZone` 주석 항목이 존재
- 다만 `target_info`에 `node_group: prod-a`, `compute_zone: us-east-1c`가 나타나므로 값 자체는 설정되어 있다. **해석 불명확 — 확인 필요**

---

## 7. 요약

### 7.1 전체 아키텍처에 확실히 반영 가능한 구성·연결

| # | 항목 | 근거 |
| --- | --- | --- |
| 1 | CSC = `dell-l40s`(192.168.20.186). DSX 4개 모듈 + Keycloak + Envoy Gateway 배포 | `kubectl get pods/svc/gateway` |
| 2 | CPC 클러스터에도 동일한 DSX 4개 모듈 배포 | `kubectl get pods -A` |
| 3 | CPC→CSC 리프노드 페더레이션 3/3 연결. `tls://dsxcsc.uclick.ai.kr:7422` | `/leafz`, `/varz`, nats-2 로그 |
| 4 | CSC 외부 노출: `1883`(MQTT/TLS), `4222`(NATS), `7422`(leafnode). Envoy LB + TCPRoute 3종 | `kubectl get svc/tcproute` |
| 5 | Keycloak(realm `dsx`) OAuth2 → auth-callout → MQTT 인증 전 구간 동작 | 토큰 발급 + mqttx 성공 |
| 6 | CPC 발행 메시지가 `cpc/1/` 접두어와 함께 CSC에 도달 | mqttx pub/sub 왕복 |
| 7 | `cpcExports=[test.cpc2csc.>]` 등 crossLayer는 **테스트 범위로만** 설정됨 | Helm values |
| 8 | MQTT 스트림: 3h / 64MiB / **memory** — 이력 저장소 아님 | Helm values |
| 9 | Fleet Agent는 dgx01·dgx02에 DaemonSet, `nodeSelector: nvidia.com/gpu.deploy.dcgm=true`로 고정 | DaemonSet spec |
| 10 | Agent enrollment 엔드포인트는 `data.fleet-intelligence.nvidia.com`. UI 호스트와 다름 | init container args, exit 0 |
| 11 | Agent 로컬 API는 `127.0.0.1:15133`, Service 없음 → 외부 접근 불가 | Pod spec, 로그 출처 |
| 12 | Agent는 MQTT 발행 기능이 없다 (REST/Prometheus, 파일, OTLP만) | 저장소 문서 |
| 13 | Mimir가 테넌트 `cpc-1`로 GPU/노드 메트릭 약 95종 수신 중 | Mimir query API |
| 14 | GPU 메트릭(`dcgm_fi_dev_*`)은 16 시계열, `uuid`로 노드 구분 가능 | `/series` |
| 15 | 노드 단위 메트릭은 노드 구분 불가(`job` 라벨만) | `/series` |
| 16 | 노드 식별 정보는 `target_info`에만 존재(OTLP 리소스 속성 기인) | `/series` + 차트 주석 |
| 17 | Run:ai Prometheus는 `retention: 2h` + remoteWrite 중계기. Thanos 사이드카 없음 | Prometheus CR, 컨테이너 목록 |
| 18 | CSC StorageClass = `ontap-nas-economy-sc` (Trident, default) | `kubectl get sc` |

### 7.2 추가 확인 전에는 확정하면 안 되는 구성·연결

| # | 항목 | 필요한 확인 |
| --- | --- | --- |
| 1 | **CPC IP 대역 불일치** — 들은 값(171~174) vs 관측값(100,101,172~176) | 이 클러스터가 CPC 중 하나인지, 몇 번인지 |
| 2 | `192.168.20.181`(proxy)의 역할 | LB VIP인지 egress proxy인지 |
| 3 | `FLEETINT_COLLECTOR_ENDPOINT` 설정 위치와 값 | `helm get values`로 재확인 |
| 4 | `#` 와일드카드 구독 거부 원인 | NATS 권한 매칭 방식, `-help-all`, accountz |
| 5 | Mimir 리소스 속성 승격 지원 여부 | `mimir -help-all \| grep promote` |
| 6 | Mimir `mimir-minio-post-job` 실패 원인 | job 로그 |
| 7 | Grafana 데이터소스 실제 저장 여부 및 `X-Scope-OrgID` 설정 | UI 또는 API |
| 8 | agentgateway의 정체와 배포 상태 | 담당자 확인 |
| 9 | NVSentinel 배포 위치 및 datastore(MongoDB/PostgreSQL) 선택 | 담당자 확인 |
| 10 | Omniverse Kit/Isaac Sim 실행 호스트 | MCP 컨테이너 env 확인 |
| 11 | enrollment에 따른 **GPU 텔레메트리 외부 반출 정책 승인 여부** | 조직 확인 |
| 12 | 인벤토리 업서트 실패 원인 | UI node group 상태 |
| 13 | attestation 페이로드 초과 — 버그인지 설정 문제인지 | NVIDIA 확인 |
| 14 | `dell-l40s`의 kind 클러스터 `dsx-exchange-control-plane` 용도 | 담당자 확인 |
| 15 | CSC MinIO 5Gi / ingester 2Gi 용량 적정성 | 수집량 대비 산정 |

### 7.3 알려진 리스크

| 항목 | 내용 |
| --- | --- |
| `target_info` 카디널리티 | `gpuInfo_gpus` JSON 순서 변동으로 시계열 지속 증가. 노드 2대에 이미 9 시계열 |
| Grafana EmptyDir | Pod 재시작 시 데이터소스·대시보드 전량 유실 |
| OTLP 평문 + 무인증 | `http://192.168.20.186:8080/otlp` 임의 주입·정보 노출 가능 |
| MQTT 스트림 memory | NATS 전체 재시작 시 3시간치 소멸 |
| crossLayer 중복 | 세 export 리스트 패턴 중복 시 NATS CrashLoopBackOff, 설치 시점 무경고 |
| Mimir 스토리지 | ingester 2Gi / MinIO 5Gi, 보관 기간 미설정 상태로 추정 |
| CSC 443 포트 | Keycloak Gateway가 점유, `allowedRoutes.from: Same`. Mimir/Grafana 노출 시 별도 포트 또는 Gateway 필요 |

---

## 부록 A. 검증에 사용한 조회 방법

이 절은 재현을 위한 참고이며, 아래 명령이 모두 실행되었음을 뜻하지 않는다. 실제 실행하여 결과를 확보한 항목은 §6에 기재했다.

```bash
# NATS 모니터링 (:8222)
curl -s localhost:8222/leafz  | jq '.leafs[] | {account,name,ip,in_msgs,out_msgs}'
curl -s localhost:8222/varz   | jq '.leaf'
curl -s 'localhost:8222/connz?auth=1&subs=1'
curl -s 'localhost:8222/accountz?acc=CSC' | jq '.account_detail'
curl -s 'localhost:8222/jsz?accounts=1&streams=1'

# DSX 설정
kubectl -n dsx get cm auth-callout-permissions -o jsonpath='{.data}' | jq
helm -n dsx get values dsx -a

# MQTT 왕복
mqttx pub -h dsxcsc.uclick.ai.kr -p 1883 -l mqtts --ca <CA> \
  -t 'test/cpc2csc/ping' -m '<msg>' -u oauthtoken -P "$TOKEN" -V 3.1.1

# Fleet Agent
kubectl -n fleet-intelligence get ds fleet-intelligence-agent -o yaml
kubectl -n fleet-intelligence logs <pod> -c enroll

# Mimir (테넌트 헤더 필수)
curl -sS -H 'X-Scope-OrgID: cpc-1' '<mimir>/prometheus/api/v1/label/__name__/values'
curl -sS -G -H 'X-Scope-OrgID: cpc-1' '<mimir>/prometheus/api/v1/series' \
  --data-urlencode 'match[]=<metric>'
```

## 부록 B. 참고 문서

| 제목 | URL |
| --- | --- |
| DSX Exchange Architecture | `https://docs.nvidia.com/dsx-exchange/architecture` |
| DSX Exchange Stateless Async Bus | `https://docs.nvidia.com/dsx-exchange/stateless-async-bus` |
| Fleet Intelligence Agent | `https://github.com/dsx-ai-factory/fleet-intelligence-agent` |
| Fleet Intelligence Client — Skills | `https://docs.nvidia.com/fleet-intel/client/skills` |
| Fleet Intelligence Client — SDK | `https://docs.nvidia.com/fleet-intel/client/sdk` |
| NVSentinel — Data Flow | `https://docs.nvidia.com/nvsentinel/architecture/data-flow` |
| NVSentinel — HealthEvent Data Model | `https://docs.nvidia.com/nvsentinel/architecture/health-event-data-model` |
| NVSentinel — Datastore Connection | `https://docs.nvidia.com/nvsentinel/runbooks/datastore-connection` |

---

**보안 처리**: Keycloak client secret, Grafana admin 비밀번호, enrollment 토큰, NKey seed는 본 문서에서 제외했다. 내부 IP와 도메인은 팀 내 재현을 위해 실제 값을 유지했다.

> ⚠️ 별도 조치 필요: 작업 과정에서 `mqtt-client` client secret과 Grafana admin 비밀번호가 평문으로 노출된 이력이 있다. 재발급 권장.
