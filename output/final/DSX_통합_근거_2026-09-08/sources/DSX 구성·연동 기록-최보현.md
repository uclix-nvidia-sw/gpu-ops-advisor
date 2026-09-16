# DSX 구성·연동 기록

- **작성자:** 최보현 (Bohyun Choi)
- **대상 작업일 또는 기간:** 2026-08-29 ~ 2026-09-08
- **보조 참고 기간:** 2026-04-16 GPU/RDMA 주변 인프라 기록 일부
- **대상 환경**
  - DSX Exchange CSC/CPC 실험·검증 환경: **클러스터명 미확인**
  - Fleet Intelligence 검증 환경: `vessl-k8s-*` 노드명 사용 환경. 공식 Kubernetes cluster name은 **미확인**
- **주소 표기 규칙**
  - 내부 IP는 재사용 가능한 문서화를 위해 가명 처리함.
  - `[OTLP-GW-OLD]`: 2026-09-04 및 09-07 Fleet Agent 로그에서 사용된 기존 OTLP HTTP endpoint
  - CSC Agent Gateway 등의 Kubernetes ClusterIP는 서비스명으로 식별하고 실제 ClusterIP는 기록에서 생략함.
- **비밀정보**
  - enrollment token, JWT 원문, client secret, NKey seed, kubeconfig 인증정보 등은 기록하지 않음.

## 참고한 자료와 확인 한계

### 실제 참고한 자료

| 구분 | 자료 | 확인 가능한 내용 |
|---|---|---|
| 실행 결과 | 2026-08-31 Kubernetes Pod 목록 | CSC/CPC별 Agent Gateway, Event Bus, MCP backend, Envoy Gateway, IDP, OTel Collector의 실제 Running 상태 |
| 실행 결과 | 2026-09-04 Fleet Agent 로그 | Fleet health exporter 설정, DCGM 기반 수집, XID/SXID 처리, OTLP endpoint와 404 실패, inventory/nvattest 문제 |
| 실행 결과 | 2026-09-07 Fleet Agent 로그 | 480 metrics 수집, XID/SXID 상태, 8 GPU 확인, 기존 OTLP logs 404, inventory/attestation JWT 만료 |
| 실행 결과 | 2026-09-08 `enroll` container 로그 | Ampere/driver/DCGM/nvattest precheck 성공, enrollment backend redirect 실패 |
| 실행 결과 | Fleet Pod/노드 조회 대화 | GPU worker 2대에 Fleet Pod 배치, `nvidia.com/gpu.deploy.dcgm=true` 확인 |
| 실행 결과 | `kubectl debug node/...` | worker host에서 `nvidia-smi` binary가 host PATH에 없음을 확인 |
| 설정/명령 | Fleet Helm upgrade 명령 | Alloy OTLP endpoint, `otelGateway.enabled=false`, nodeGroup/computeZone, logLevel, listenAddress 설정안 |
| 산출물 | `fleet-intelligence-loki-dashboard*.json` | Loki에서 Fleet logs를 `service_name`, `dsx_cpc`, `pod` 기준으로 조회하는 대시보드 구성 |
| 산출물 | `fleet-intelligence-mimir-dashboard-v*.json` | Mimir/Prometheus에서 Fleet metrics와 inventory labels를 조회하는 대시보드 구성 |
| 공개 문서 | NVIDIA DSX Exchange repository / architecture / authentication / bridge docs | 제품에서 정의한 CSC/CPC, NATS federation, MCP bridge, auth 구조 |
| 공개 문서 | Fleet Intelligence Agent Helm docs | DCGM prerequisite, 기본 nodeSelector, enrollment 설정 |
| 공개 문서 | Grafana Alloy docs | Alloy의 정체와 OTLP HTTP 4318 수신 역할 |

2026-08-31 관측 시 `cpc-1`, `cpc-2`, `csc` 각각에 Agent Gateway 계열 Pod와 Event Bus 계열 Pod가 실제 Running이었다. 
### 이번 기록에서 확인하지 못한 범위

다음은 기록 부족 때문에 **미확인**이며, “없음” 또는 “사용하지 않음”을 의미하지 않는다.

- DSX Exchange 환경의 실제 Kubernetes cluster name 및 각 CPC/CSC의 물리적 cluster mapping
- Agent Gateway, Bridge, Controller, Rate Limit, Valkey의 실제 Helm release version/image digest
- 각 Pod의 Kubernetes workload kind를 `kubectl get deploy/sts/ds`로 직접 조회한 결과
- Agent Gateway의 전체 ConfigMap/Helm values
- Agent Gateway → MCP backend의 실제 route table
- Bridge → NATS 연결의 실제 connection status
- CPC → CSC NATS leaf-node connection의 runtime status
- 실제 JWT issuer/audience/tenant claim mapping
- IDP namespace 내부 각 테스트 issuer의 실제 사용 관계
- Grafana Alloy의 Deployment/DaemonSet, 버전, ConfigMap
- Alloy → Mimir / Loki exporter 설정
- Mimir, Loki, Grafana의 실제 Kubernetes 배치와 버전
- 작성된 dashboard JSON이 실제 Grafana에 import되었는지 여부
- `FLEETINT_COLLECTOR_ENDPOINT=...alloy...` Helm 명령이 실제 적용되었는지 여부
- 2026-09-08 시점 최종 Fleet Helm release values/image
- enrollment endpoint의 원래 설정값과 redirect가 발생한 정확한 인증 경로
- Fleet Agent의 ServiceAccount/RBAC/볼륨 전체 구성

### 확인 상태 표기

- **[문서]** 제품 공식 문서나 공개 저장소에서 확인
- **[설정]** 명령·JSON·Helm 값 등 설정 내용에서 확인
- **[실행]** 사용자가 제시한 명령 출력이나 로그에서 검증
- **[추정]** 여러 자료가 일치하지만 runtime 검증 부족
- **[계획/검토]** 구성 방향으로 논의되었으나 적용 증거 없음
- **[미확인]** 판단할 자료 부족

---

# 1. 이번에 다룬 범위와 목적

## 1.1 DSX Exchange 구조 이해

2026-08-29~09-01에는 DSX Exchange의 구조를 이해하기 위해 다음 영역을 조사했다.

- DSX Exchange 자체 구성
- CSC와 CPC의 역할
- Agent Gateway
- MCP backend
- NATS 기반 Event Bus
- Agent Gateway Bridge
- 인증/auth-callout
- tenant 개념
- 외부 접근 경로와 Gateway

여기서 중요한 정정 사항이 있다.

**현재 NVIDIA 공식 DSX Exchange 문서 기준:**

- **CSC = Common Services Cluster**
- **CPC = Control Plane Cluster**
- AI Factory는 하나의 CSC와 하나 이상의 CPC로 구성
- 각 cluster는 독립 NATS Event Bus를 가지고 CPC Event Bus가 CSC로 NATS leaf-node federation을 구성한다.

과거 대화 중 CSC/CPC 의미를 다른 뜻으로 설명한 기록이 있었으나, **통합 아키텍처에는 위 공식 정의를 사용해야 한다.**

DSX Exchange 자체는 NATS Event Bus, AsyncAPI schema, auth-callout, MCP/Agent Gateway 계층을 포함하는 integration layer이다. 현재 공개 repository는 Agentgateway와 `dsx-agentgateway-bridge`를 명시적으로 포함한다.

## 1.2 실제 배치 확인

2026-08-31에는 Kubernetes Pod 목록을 통해 다음이 이미 배치되어 Running임을 확인했다.

- `cpc-1-dsx-agentgateway`
- `cpc-2-dsx-agentgateway`
- `csc-dsx-agentgateway`
- 각 cluster layer별 Event Bus
- 각 cluster layer별 MCP backend
- Envoy Gateway
- `dsx-obs` OpenTelemetry Collector
- `idp` 관련 workload

따라서 이 구성들은 이번 조사에서 새로 만든 것으로 기록하지 않고, **“조사 시작 당시 이미 구성되어 있던 환경”​**으로 분류한다.

## 1.3 Fleet Intelligence 관측 파이프라인

2026-09-04 이후에는 DSX Fleet Intelligence Agent를 GPU 노드에 배치하여 다음을 확인하거나 구성 방향을 검토했다.

- GPU/DCGM 기반 telemetry 수집
- XID/SXID 처리
- health exporter
- OTLP metrics/log export
- inventory
- attestation / nvattest
- enrollment
- Grafana Alloy를 통한 OTLP 수집
- Mimir metrics
- Loki logs
- Grafana dashboard

Fleet 측은 단순 개념 조사가 아니라 **실제 Pod log와 Kubernetes node 배치를 통해 상당 부분 runtime 검증**이 이루어졌다.

다만 DSX Exchange의 CSC/CPC 환경과 Fleet 검증에 사용된 `vessl-k8s-*` 환경이 **동일 Kubernetes cluster라는 근거는 없다.** 통합 아키텍처 작성 시 두 환경을 물리적으로 하나로 합쳐 그리면 안 된다.

---

# 2. 구성 요소와 역할

## 2.1 DSX Exchange

**정식 명칭:** NVIDIA DSX Exchange  
**저장소:** NVIDIA/dsx-exchange 또는 dsx-ai-factory/dsx-exchange 공개 repository  
**분류:** DSX 자체 구성요소  
**확인 수준:** [문서] + [실행]

공개 repository 기준 DSX Exchange는 다음을 포함한다.

- NATS 기반 DSX Event Bus
- AsyncAPI schema
- auth-callout
- Agentgateway
- `dsx-agentgateway-bridge`
- Helm charts
- local evaluation 환경

Upstream Agentgateway는 authenticated MCP request를 local MCP server로 전달하고, DSX Bridge는 DSX Event Bus를 통해 remote MCP discovery/request routing을 추가한다.

현재 공개 changelog에서 Agent Gateway bridge는 아직 `Unreleased` 항목으로 기록되어 있다. 공개 v2.5.11은 2026-05-29 초기 공개 release다. 따라서 2026-08-31 환경에서 Agent Gateway가 실제 실행 중이었다는 사실만으로 공개 v2.5.11을 사용했다고 판단하면 안 된다.

---

## 2.2 DSX Agent Gateway

**관측 이름**

- `cpc-1-dsx-agentgateway`
- `cpc-2-dsx-agentgateway`
- `csc-dsx-agentgateway`

**일반 역할 [문서]**

MCP client request를 받고 인증·routing 후 MCP server로 전달하는 gateway 계층.

**실제 환경 [실행]**

CSC:

- gateway Pod 3개
- bridge Pod 2개
- controller Pod 1개
- rate-limit Pod 2개
- Valkey Pod 3개

가 Running 상태였다.

CPC-1도 gateway 3개, bridge 2개, controller, rate-limit, Valkey가 배치되어 있었다.

CPC-2도 동일 계열이 관측되었다.

**실제 Kubernetes workload kind:** 미확인.

Pod 이름 형태상 Deployment/StatefulSet 계열로 보이는 항목이 있으나 `kubectl get deployment,statefulset` 결과가 없으므로 확정하지 않는다.

### CSC에서 확인한 Service

사용자 실행 결과 기준:

| Service | Type | Port |
|---|---|---:|
| `csc-dsx-agentgateway` | NodePort | `80 → 30180/TCP` |
| `csc-dsx-agentgateway-bridge` | ClusterIP | `3001/TCP`, `9464/TCP` |
| `csc-dsx-agentgateway-controller` | ClusterIP | `9978/TCP`, `9093/TCP`, `9092/TCP` |
| `csc-dsx-agentgateway-ratelimit` | ClusterIP | `8080/TCP`, `8081...` |

ClusterIP 자체는 이 기록에서 가명화하여 생략한다.

Bridge 공식 문서에서도 leaf bridge가 local Agent Gateway를 `http://<release>.<namespace>.svc:80/mcp` 형태로 사용하고 NATS endpoint를 별도 설정하도록 정의되어 있다.

---

## 2.3 DSX Agentgateway Bridge

**정식 모듈:** `dsx-agentgateway-bridge`  
**분류:** DSX 자체 구성요소  
**확인 수준:** [문서] + Pod [실행], 실제 NATS session [미확인]

공개 DSX repository는 Bridge의 역할을 다음과 같이 정의한다.

> MCP discovery와 request routing을 DSX Event Bus를 통해 수행.

Bridge는 local Agent Gateway와 NATS를 연결하는 계층이다.

환경에서는 각 CSC/CPC Agent Gateway namespace에 `*-bridge-*` Pod가 Running이었다.

다만 다음은 runtime으로 확인하지 않았다.

- 실제 `NATS_URL`
- bridge auth mode
- active NATS connection
- remote MCP discovery 성공 여부
- 어느 backend가 어느 CPC/CSC에 export되는지

따라서 **Bridge ↔ NATS 연결은 제품 구조와 배치를 근거로 한 “구성 정의상 연결”이며 runtime 성공 검증은 미확인​**이다.

---

## 2.4 DSX Event Bus / NATS

**정식 제품:** NATS 기반 DSX Event Bus  
**분류:** DSX 자체 구성요소에 포함된 third-party messaging infrastructure  
**확인 수준:** [문서] + Pod [실행]

공식 DSX architecture에서 Event Bus는:

- NATS HA cluster
- MQTT 3.1.1
- JetStream persistence
- NATS leaf-node federation

을 제공한다.

### 실제 Pod

CPC-1:

- `nats-0`
- `nats-1`
- `nats-2`
- `nats-mtls-0`
- `nats-event-bus-cpc-1-surveyor-*`
- `auth-callout-*`
- `nack-*`

가 Running이었다.

CPC-2 역시 동일 계열이 배치되었다.

CSC에서도:

- NATS 3 replica
- NATS mTLS
- Surveyor
- auth-callout
- NACK

가 Running이었다.

### 제품상 포트

공식 architecture:

| Port | 용도 |
|---:|---|
| 1883 | MQTT |
| 4222 | NATS client |
| 7422 | NATS leaf node |
| 8883 | mTLS MQTT |

CPC → CSC federation은 NATS leaf node `7422`를 사용하도록 설계되어 있다.

**주의:** 실제 환경에서 이 포트들의 Service/Endpoint 및 established connection을 직접 조회한 기록은 없다.

---

## 2.5 auth-callout

**정식 모듈:** DSX Exchange NATS Auth Callout Service  
**분류:** DSX 자체 구성요소  
**확인 수준:** [문서] + Pod [실행]

환경에서 CSC/CPC 각각 `auth-callout-*` Pod가 Running이었다.

제품 문서에서 auth-callout은:

- OAuth2 JWT/JWKS
- mTLS
- NKey
- 개발용 noauth

를 지원하고, 인증 후 NATS account 및 publish/subscribe subject permission을 부여한다.

OAuth2의 경우 OIDC provider JWKS를 사용하여 JWT를 검증한다.

실제 환경에서:

- JWKS URL
- issuer
- `azp`
- subject
- tenant claim
- 실제 NATS permission

은 확인하지 않았다.

따라서 **“auth-callout Pod 존재”는 실행 사실이며, 어떤 auth profile이 현재 사용되는지는 미확인​**이다.

---

## 2.6 NACK / Surveyor

**NACK:** NATS JetStream declarative management controller  
**Surveyor:** NATS monitoring/Prometheus exporter  
**분류:** DSX Event Bus를 구성하는 주변 third-party component

공식 DSX architecture에서도 cluster당 기본적으로 NACK 1개, Surveyor 1개를 구성한다.

실제 CSC/CPC 모두 관련 Pod가 Running이었다.

현재 공개 DSX Helm dependency 기준 버전은:

- NATS `2.12.6`
- NACK `0.33.2`
- Surveyor `0.20.7`
- auth-callout `0.1.1`
- agentgateway `1.4.1`
- Valkey `0.9.4`

이다.

**이 버전들은 현재 repository dependency 값이며 2026-08-31 cluster에 설치된 실제 버전이라고 확정하면 안 된다.**

---

## 2.7 Valkey / Rate Limit

**관측 Pod**

- `*-ratelimit-*`
- `*-valkey-0/1/2`

가 각 Agent Gateway namespace에 존재.

**분류:** Agent Gateway 주변 인프라로 추정  
**실행 상태:** Running  
**실제 연결:** 미확인

Valkey가 rate limit state backend인지 여부는 chart 구조상 가능성이 높으나, 현재 확보한 ConfigMap/arguments/connection log가 없으므로 **같은 namespace에 있다는 이유만으로 연결을 확정하지 않는다.**

---

## 2.8 MCP backend

각 CSC/CPC에 다음 Pod가 관측되었다.

- `legacy-sse-*`
- `mcp-backend-a-*`
- `mcp-backend-b-*`

CPC-1 예:
CPC-2 예:
CSC 예:

제품상 Agentgateway가 local MCP server를 route하는 것은 확인되지만, 실제 환경에서 `backend-a`, `backend-b`, `legacy-sse` 각각이 어떤 route와 연결되었는지에 대한 설정은 미확인이다.

---

## 2.9 Envoy Gateway

`envoy-gateway-system` namespace에서 다음이 Running이었다.

- CPC-1 gateway Envoy
- CPC-2 gateway Envoy
- CSC gateway Envoy
- Envoy Gateway controller



공식 DSX reference architecture도 Envoy Gateway를 Gateway API controller 예시로 사용한다. 다만 다른 conformant controller도 가능하다고 명시한다.

따라서 이 환경에서는 **실제로 Envoy Gateway가 배치됨**까지는 확정할 수 있다.

하지만:

- 각 Listener
- TCPRoute/TLSRoute
- LoadBalancer IP
- CPC→CSC leaf-node route

의 실제 object 전체는 이번 기록에서 확보하지 못했다.

---

## 2.10 IDP 관련 workload

`idp` namespace에서 다음 Pod가 Running이었다.

- `event-bus-*`
- `human-oidc-*`
- `service-oidc-*`
- `svid-issuer-*`
- `svid-wrong-key-*`
- `unconfigured-issuer-*`



이 이름만으로 각 Pod의 정확한 제품·역할을 확정하지 않는다.

특히 `svid-wrong-key`, `unconfigured-issuer`는 test fixture일 가능성이 있지만 **실제 목적은 미확인**이다.

---

## 2.11 OpenTelemetry Collector (`dsx-obs`)

`dsx-obs` namespace에서:

`otel-collector-6754b6b7bc-vq6dt`

Pod가 Running이었다.

- 정확한 OpenTelemetry Collector distribution: 미확인
- receiver/exporter ConfigMap: 미확인
- Agent Gateway / Event Bus telemetry가 실제 이 Collector로 들어오는지: 미확인

따라서 현재는 **“DSX observability namespace에 OTel Collector가 배치돼 있었다”​**까지만 확정한다.

---

## 2.12 NVIDIA Fleet Intelligence Agent

**정식 모듈/프로젝트:** Fleet Intelligence Agent  
**사용 repository/chart 계열:** `dsx-ai-factory/fleet-intelligence-agent` / Fleet Intelligence Helm Chart  
**분류:** DSX GPU/host observability 계열로 사용된 agent  
**확인 수준:** [문서] + [설정] + [실행]

NVIDIA 문서 기준 Fleet Agent는 GPU Operator/DCGM HostEngine을 전제로 GPU와 시스템 health/telemetry를 수집한다. DCGM `4.2.3+`, driver 510+가 prerequisite이다.

### 2026-09-08 enroll precheck

직접 실행 로그:

```text
NVIDIA GPU detected
supported GPU architecture detected: ampere
NVIDIA driver detected: 580.173.02
nvattest detected
DCGM HostEngine version is supported: 4.2.3
```

따라서 이 Pod 관점에서:

- GPU 인식: 성공
- GPU architecture: Ampere
- NVIDIA driver: `580.173.02`
- nvattest binary: 존재
- DCGM HostEngine: `4.2.3`, supported

까지는 실행 검증됐다.

---

## 2.13 DCGM HostEngine / GPU Operator

Fleet Agent에서 GPU metrics 수집의 직접 backend 역할을 한다.

2026-09-04 Fleet runtime에서 다음 DCGM component를 실제 검사했다.

- CPU
- InfoROM
- NVLink
- NVSwitch
- PCIe
- profiling



2026-09-07에는:

- clock
- memory
- NVLink
- NVSwitch
- PCIe
- power
- profiling
- thermal
- utilization

등이 Healthy로 수집되었다.

NVSwitch는 6개가 발견되었고, 해당 상태가 Healthy였다.

8개의 GPU persistence mode도 모두 확인되었다.

### scheduling

Fleet 공식 Helm chart 기본값은:

```yaml
nodeSelector:
  nvidia.com/gpu.deploy.dcgm: "true"
```

이다.

실제 환경에서도:

- `vessl-k8s-worker-01`: `nvidia.com/gpu.deploy.dcgm=true`
- `vessl-k8s-worker-02`: `nvidia.com/gpu.deploy.dcgm=true`
- master node: 해당 값 없음

이 확인되었고 Fleet Pod도 worker-01/02에 각각 배치되었다.

따라서 **Fleet가 DCGM-enabled GPU worker만 대상으로 배치되는 구조는 공식 default와 실제 관측이 일치한다.**

Pod 출력에 각 node가 affinity target처럼 나타난 기록이 있었으나, 그것만으로 사용자가 수동으로 특정 node에 pinning했다고 판단하지 않는다.

---

## 2.14 nvattest

**분류:** Fleet attestation 주변 NVIDIA component

2026-09-08 enroll precheck에서는 `nvattest detected`가 성공했다.

하지만 2026-09-04 실제 attestation 실행에서는:

- result code `608`
- GPU device ID `0x20b2` unsupported
- `No inband GPU devices found`
- GPU evidence 수집 실패
- exit status `96`

가 발생했다.

따라서:

> `nvattest detected` ≠ 실제 attestation 성공

으로 기록해야 한다.

---

## 2.15 Grafana Alloy

사용자가 Fleet Agent OTLP destination으로 다음 이름을 설정하는 Helm 명령을 제시했다.

```text
http://alloy.alloy.svc.cluster.local:4318/otlp
```

`Alloy`라는 이름은 여기서 **Grafana Alloy로 조사되었다.**

Grafana 공식 문서에서 Alloy는 OpenTelemetry Collector distribution이며 `otelcol.receiver.otlp`를 통해 metrics/logs/traces를 수신한다. HTTP/protobuf OTLP의 일반적인 port는 `4318`이다.

그러나 실제 환경에서:

- `kubectl get pod -n alloy`
- Alloy image/version
- Alloy ConfigMap

을 확인한 기록은 없다.

따라서 정확한 표현은:

**“Fleet 설정에서 `alloy.alloy.svc.cluster.local:4318`을 목적지로 사용하는 방향이 제시되었고 Grafana Alloy의 표준 OTLP HTTP 구조와 일치한다. 실제 Alloy runtime 배치는 별도 미확인.”**

---

## 2.16 Mimir

Fleet metrics를 Prometheus-compatible query로 조회하기 위한 대상으로 사용되는 구성 산출물이 존재한다.

`fleet-intelligence-mimir-dashboard-v6-ngc-style.json`은 datasource를 명시적으로:

```text
Mimir / Prometheus
```

로 정의한다.

inventory 계열에서는:

```promql
count(count by (compute_zone) (
  target_info{job="fleet-intelligence-agent",compute_zone!=""}
))
```



Node Group은 `node_group`, Machine은 `host_name`을 사용한다. 
GPU memory metric 예:

```promql
avg(dcgm_fi_dev_fb_used_percent) * 100
```



**중요:** 이 JSON은 Mimir 조회를 위한 대시보드가 작성되어 있음을 보여줄 뿐, 해당 datasource에 실제 데이터가 정상 유입되는 것까지 증명하지 않는다.

---

## 2.17 Loki

Fleet log dashboard는 datasource로 Loki를 사용하고 다음 label을 중심으로 쿼리하도록 작성되어 있다.

- `service_name`
- `dsx_cpc`
- `pod`

Raw logs query:

```logql
{service_name=~"$service", dsx_cpc=~"$cpc", pod=~"$pod"}
```



CPC별 log rate query도 작성되어 있다.

Dashboard tag에도:

- `loki`
- `fleet-intelligence`
- `alloy`

가 포함되어 있다.

역시 **dashboard artifact 존재와 실제 Loki ingestion 성공은 구분해야 한다.**

---

# 3. 실제 배치 구조

## 3.1 DSX Exchange 계층

공식 DSX 구조는:

```text
Common Services Cluster (CSC)
        ↑
        │ NATS leaf-node federation
        │
Control Plane Cluster (CPC-1)
Control Plane Cluster (CPC-2)
...
```

이다.

실제 관측 namespace도 이 구조를 반영하고 있었다.

### CPC-1

```text
cpc-1-dsx-agentgateway
  ├─ cpc-1-dsx-agentgateway-*          x3
  ├─ ...-bridge-*                      x2
  ├─ ...-controller-*                  x1
  ├─ ...-ratelimit-*                   x2
  └─ ...-valkey-{0,1,2}

cpc-1-event-bus
  ├─ auth-callout-*
  ├─ nack-*
  ├─ nats-{0,1,2}
  ├─ nats-mtls-0
  └─ nats-event-bus-cpc-1-surveyor-*

cpc-1-mcp-backends
  ├─ legacy-sse-*
  ├─ mcp-backend-a-*                   x2
  └─ mcp-backend-b-*
```

모두 2026-08-31 관측에서 Running이었다.

### CPC-2

동일한 세 계층이 존재했다.

### CSC

```text
csc-dsx-agentgateway
csc-event-bus
csc-mcp-backends
```

구성이 존재하며 같은 유형의 gateway, bridge, NATS 및 MCP backend Pod가 Running이었다.

### 공통 인프라

```text
envoy-gateway-system
  ├─ envoy-cpc-1-...
  ├─ envoy-cpc-2-...
  ├─ envoy-csc-...
  └─ envoy-gateway-...

dsx-obs
  └─ otel-collector-...

idp
  ├─ event-bus-...
  ├─ human-oidc-...
  ├─ service-oidc-...
  ├─ svid-issuer-...
  ├─ svid-wrong-key-...
  └─ unconfigured-issuer-...
```



### Node 배치

DSX Exchange Pod가 실제 어느 Kubernetes node에 있었는지는 **미확인**이다.

---

## 3.2 Fleet Intelligence 환경

### Namespace

```text
fleet-intelligence
```

### 관측된 Pod 세대

이전 관측:

```text
fleet-intelligence-agent-6xsvp → vessl-k8s-worker-02
fleet-intelligence-agent-fw4mx → vessl-k8s-worker-01
```

2026-09-07 log 대상:

```text
fleet-intelligence-agent-279kg
```

실제 사용자가 실행한 log command도 파일에 남아 있다.

2026-09-08 enroll 확인 대상:

```text
fleet-intelligence-agent-kfstv
container: enroll
```

Pod suffix가 바뀐 것은 재배포/rolling update 등 여러 가능성이 있으므로 **정확한 변경 원인은 미확인**이다.

### 노드 특성

worker-01, worker-02는 DCGM deployment label이 `true`였고 Fleet Pod가 배치됐다.

Fleet 공식 chart default nodeSelector도 같은 label을 사용한다.

### Host debug 결과

worker-02에:

```bash
kubectl debug node/vessl-k8s-worker-02 \
  -it --image=ubuntu:24.04 --profile=sysadmin
```

형태로 접근하여 host `chroot /host`까지 수행했으나:

```text
nvidia-smi: not found
```

였다.

이 결과는 **host filesystem에 `nvidia-smi` 실행파일이 없었다**는 뜻이지, Fleet/DCGM에서 GPU가 보이지 않았다는 뜻은 아니다.

실제로 Fleet runtime에서는 CUDA/NVML library와 8 GPU를 정상 식별했다.

---

# 4. 구성 요소 간 연결 관계 — 핵심

## 4.1 확인 수준을 반영한 전체 구조

```text
[DSX Exchange domain — cluster identity 미확인]

External MCP client
        │
        │ HTTP / NodePort 30180 (CSC에서 Service 확인)
        ▼
┌───────────────────────────────┐
│ CSC DSX Agent Gateway         │
│ gateway / controller          │
│ rate-limit / Valkey           │
└───────────┬───────────────────┘
            │
            ├─ local MCP route ─────→ CSC MCP backends
            │                         [제품 정의, runtime route 미확인]
            │
            ▼
      Agentgateway Bridge
            │
            │ NATS
            ▼
      CSC Event Bus
        NATS x3
        auth-callout
        NACK
        Surveyor
            ▲
            │ NATS leaf :7422
            │ [제품 정의, runtime session 미확인]
        ┌───┴───────────┐
        │               │
   CPC-1 Event Bus  CPC-2 Event Bus
        ▲               ▲
        │               │
    Bridges          Bridges
        ▲               ▲
        │               │
   CPC-1 AgentGW    CPC-2 AgentGW
        │               │
    MCP backends     MCP backends


[Fleet Intelligence domain — vessl-k8s-*]

GPU worker
    │
    ├── NVIDIA driver / NVML
    ├── DCGM HostEngine
    ├── kernel messages (XID/SXID)
    └── nvattest
            │
            ▼
 Fleet Intelligence Agent
            │
            ├── inventory / attestation ─→ Fleet backend
            │
            ├── OTLP metrics/logs
            │
            └── /v1/metrics, /metrics
            │
            ├─ 09-04/09-07 observed:
            │       [OTLP-GW-OLD]/otlp
            │              └─ logs /v1/logs → HTTP 404
            │
            └─ proposed/target:
                    alloy.alloy.svc:4318/otlp
                             │
                           Alloy
                         ┌────┴────┐
                         ▼         ▼
                       Mimir      Loki
                       metrics    logs
                         │         │
                         └────┬────┘
                            Grafana

Alloy→Mimir/Loki 부분은 현재 artifact/config 방향이며
실제 Alloy config와 end-to-end ingestion 성공은 미확인.
```

---

## 4.2 External client → CSC Agent Gateway

- **출발:** 외부 MCP client
- **도착:** `csc-dsx-agentgateway`
- **목적:** MCP request 진입
- **요청 시작:** client
- **방향:** client → gateway
- **Service:** `csc-dsx-agentgateway`
- **Service type:** NodePort
- **Service port:** `80`
- **NodePort:** `30180`
- **MCP path:** 제품 문서상 `/mcp`; 환경 runtime request 성공 기록은 미확인
- **실제 검증:** Service 존재 및 port만 확인
- **상태:** **부분 검증**

Agentgateway가 MCP request를 local MCP server로 route하는 것은 DSX repository에서 확인된다.

AI가 과거 제안한 MCP Inspector/port-forward 테스트 명령은 **실행 증거가 없으므로 직접 수행 작업으로 기록하지 않는다.**

---

## 4.3 Agent Gateway → local MCP backend

- **목적:** MCP tool/resource request routing
- **요청 시작:** Agent Gateway
- **데이터:** MCP protocol request/response
- **예상 경로:** Agent Gateway service → local MCP server
- **실제 backend Pod:** `mcp-backend-a`, `mcp-backend-b`, `legacy-sse`
- **실제 route config:** 미확인
- **실제 MCP request 결과:** 미확인
- **상태:** **제품 구조 확인 + 양쪽 Pod 존재, 실제 연결 미검증**

---

## 4.4 Agentgateway Bridge → DSX Event Bus

- **출발:** `*-dsx-agentgateway-bridge`
- **도착:** NATS Event Bus
- **목적:** remote MCP discovery/request routing
- **요청 시작:** Bridge
- **데이터:** DSX Event Bus 상의 MCP discovery/request messaging
- **프로토콜:** NATS
- **설정:** `NATS_URL`, `SUBJECT_PREFIX`, auth mode 등이 공식 Bridge runtime setting
- **실제 NATS session:** 미확인

공식 Bridge 문서는 Bridge가 OAuth client credential로 token을 얻어 NATS에 연결하는 방식도 정의한다.

환경에는 Bridge와 NATS가 모두 실제 배치돼 있지만 **connection log를 확인하지 않았으므로 runtime 연결 성공으로 기록하지 않는다.**

---

## 4.5 CPC Event Bus → CSC Event Bus

- **출발:** CPC NATS
- **도착:** CSC Gateway/NATS
- **목적:** cluster 간 event federation
- **프로토콜:** NATS leaf node
- **port:** `7422`
- **방향:** CPC → CSC
- **제품 설정 예:** `global.eventBus.cscEndpoint`, cross-layer exports
- **실제 leaf connection:** 미확인

공식 문서에서 CPC는 `cscEndpoint`를 통해 CSC에 leaf connection을 구성한다.

Envoy Gateway와 양쪽 NATS Pod가 실제 존재한다는 것까지는 확인됐지만, `nats server report connections` 등에 해당하는 runtime 확인 결과는 없다.

---

## 4.6 NATS → auth-callout

- **출발:** NATS
- **도착:** auth-callout
- **목적:** client connection 인증 및 subject ACL 결정
- **데이터:** auth request / authorization response
- **auth method:** OAuth2/JWKS, mTLS, NKey 또는 noauth 가능
- **실제 Pod:** 각 CSC/CPC에 존재
- **실제 사용 auth profile:** 미확인

제품상 명확한 연결이다.

그러나 실제 runtime에서 OAuth인지 NKey인지 등을 확정하지 않는다.

---

## 4.7 OIDC Provider → auth-callout

제품 OAuth2 mode에서는 auth-callout이 OIDC provider의 JWKS를 사용한다.

- **연결 목적:** JWT signature/issuer 검증
- **방향:** auth-callout → JWKS endpoint
- **실제 `idp` Pod:** 존재
- **해당 Pod가 실제 auth-callout JWKS provider인지:** 미확인

`idp` namespace와 auth-callout의 공존만으로 연결을 확정하지 않는다.

---

## 4.8 Fleet Agent → DCGM HostEngine

이 연결은 **실제 검증됨**.

- **출발:** Fleet Intelligence Agent
- **도착:** DCGM HostEngine
- **목적:** GPU metrics/health 수집
- **수집 항목:** clock, memory, utilization, thermal, power, PCIe, NVLink, NVSwitch, profiling 등
- **요청 시작:** Fleet Agent
- **실제 상태:** 정상 수집
- **DCGM version:** `4.2.3`
- **근거:** Fleet runtime log

2026-09-07에는 480 metrics가 매 cycle 수집됐다.

---

## 4.9 Kernel → Fleet XID/SXID watcher

Fleet Agent는 kernel message를 검사해 XID/SXID 이벤트를 구분한다.

2026-09-04 debug log에서 일반 PCI/kernel message에:

```text
not xid event, skip
not sxid event, skip
```

동작이 확인됐다.

2026-09-07 당시 XID/SXID state는 모두 Healthy였고 collected events는 `0`이었다.

따라서 당시에는 **실제 XID 장애 이벤트를 검증하지 못했다.**

XID fault injection endpoint도 09-04 로그에서는 disabled였다.

---

## 4.10 Fleet Agent → 기존 OTLP Gateway

2026-09-04와 09-07에 **실제 HTTP request가 발생한 것이 검증됨**.

### 설정

2026-09-04 process가 읽은 collector:

```text
collector_endpoint = http://[OTLP-GW-OLD]/otlp
```

health exporter는:

- metrics
- events
- machine info
- component data

를 모두 include하도록 설정돼 있었다.

### 실제 logs 전송

Fleet Agent는 다음 endpoint로 OTLP log request를 만들었다.

```text
http://[OTLP-GW-OLD]/otlp/v1/logs
```

결과:

```text
HTTP 404
retry 3 attempts
Export failed
```



09-07에도 동일 endpoint로 계속 404가 발생했다.

따라서 **Fleet → 기존 OTLP gateway 네트워크 도달 자체는 있었지만 logs ingestion path는 정상 동작하지 않았다.**

Metrics의 “수집”은 확실히 성공했지만, 이 로그만으로 metrics가 downstream backend에 성공적으로 저장되었다고 확정하지 않는다.

---

## 4.11 Fleet Agent → Grafana Alloy

사용자 제공 Helm 설정안:

```bash
--set otelGateway.enabled=false
--set-string env.FLEETINT_COLLECTOR_ENDPOINT="http://alloy.alloy.svc.cluster.local:4318/otlp"
```

의 의도는:

```text
Fleet Agent
   │ OTLP HTTP
   ▼
Grafana Alloy :4318
```

으로 **chart 내부 OTel Gateway 대신 기존 Alloy를 직접 사용**하는 것이다.

Grafana Alloy는 공식적으로 OTLP HTTP receiver를 `4318`에서 구성할 수 있다.

그러나 이 Helm command가 실제 성공적으로 적용된 출력이 없고, 09-07 runtime log는 여전히 `[OTLP-GW-OLD]`를 향하고 있었다.

따라서 현재 기록상:

**Alloy 전환 = 계획/설정안, runtime 완료 미확인**

이다.

---

## 4.12 Alloy → Mimir / Loki

현재 산출물들의 설계 의도는 다음과 같다.

```text
Fleet OTLP
   ↓
Alloy
   ├─ metrics → Mimir
   └─ logs/events → Loki
                    ↓
                  Grafana
```

Mimir dashboard에서는 `target_info`, DCGM metric을 조회한다. 
Loki dashboard에서는 Fleet log label을 조회한다.

하지만 실제 Alloy exporter config가 없으므로 **Alloy → Mimir/Loki는 확정 연결이 아니라 현재 설계 방향**으로 남긴다.

---

## 4.13 Fleet Agent → inventory / attestation backend

### 2026-09-04 inventory

```text
initial inventory collection failed
node upsert response missing nodeGroup field
```

가 관측되었다.

즉 backend에 요청하고 response를 받을 정도의 통신은 있었지만 application-level validation에서 실패했다.

### 2026-09-07

inventory와 attestation 모두:

```text
401 Unauthorized
JWT assertion is expired
```

로 실패했다.

따라서 backend network connectivity 자체보다는 인증 상태가 실패한 것으로 관측된다.

### 2026-09-08 enroll

`enroll` container에서는 GPU/DCGM precheck 이후:

```text
failed to make backend request:
Post "https://ngc.nvidia.com/signout":
backend redirects are not allowed
```

로 실패했다.

여기서 중요한 점은:

**Fleet Agent가 처음부터 `/signout`을 endpoint로 설정했다고 확정할 수 없다.**

확인되는 것은 backend request 결과가 `ngc.nvidia.com/signout` 쪽 redirect를 받았고, enroll client가 redirect를 보안상 허용하지 않아 중단했다는 사실이다.

---

# 5. 직접 수행한 작업과 변경 사항

## 5.1 2026-08-29 ~ 09-01: DSX Exchange 구조 조사

### 수행 내용

- DSX Exchange repository 구조 조사
- Agent Gateway 추가 내용 조사
- CSC/CPC 구조 조사
- NATS/Event Bus 역할 조사
- Agent Gateway와 MCP backend 구조 조사
- auth 구조 조사
- tenant 개념 조사

### 클러스터 변경

**확인된 변경 없음.**

해당 기간 기록은 대부분 구조 확인 및 existing environment 관측이다.

---

## 5.2 2026-08-31: 실제 DSX 배치 확인

실제 Kubernetes 출력에서:

- CSC
- CPC-1
- CPC-2
- Agent Gateway
- Event Bus
- MCP backend
- Envoy
- IDP
- OTel Collector

Pod의 Running 상태를 확인했다.

또한 CSC Agent Gateway Service를 조회하여 NodePort/ClusterIP service와 port 구성을 확인했다.

### 변경 여부

**조회만 확인됨. 적용/수정은 확인되지 않음.**

---

## 5.3 2026-09-04: Fleet health exporter 및 OTLP 경로 확인

사용자가 Fleet Agent log를 직접 조회했다.

```bash
kubectl logs -n fleet-intelligence "$POD" \
  -c fleet-intelligence-agent --since=10m |
grep -Ei 'export|metrics|otlp|endpoint|failed|error'
```



이 실행으로:

- include metrics/events/machine/component = true
- interval 60 sec
- retry max 3
- `[OTLP-GW-OLD]/otlp`
- logs 404

를 확인했다.

### 변경 전 구조

```text
Fleet Agent
   ↓
[OTLP-GW-OLD]:8080/otlp
```

### 관측 결과

`/otlp/v1/logs` → 404.



### 최종 해결 여부

이 시점에는 미해결.

---

## 5.4 Fleet Agent의 nodeGroup / computeZone 설정 검토

Helm command에서 다음 값이 제시됐다.

```bash
--set-string enroll.nodeGroup="prod-a"
--set-string enroll.computeZone="us-east-1c"
```

Fleet 공식 Helm chart에도 같은 옵션이 존재한다.

2026-09-04 inventory failure가:

```text
node upsert response missing nodeGroup field
```

였기 때문에 metadata 설정 보완과 관련해 조사되었다.

다만 해당 Helm upgrade가 적용됐다는 명시적 command result가 없으므로:

- **설정 작성/검토:** 확인
- **cluster apply:** 미확인
- **backend response 개선:** 미확인

으로 기록한다.

---

## 5.5 Fleet internal OTel Gateway → external Alloy 전환안

제시된 Helm 변경:

```bash
--set otelGateway.enabled=false
--set-string env.FLEETINT_COLLECTOR_ENDPOINT="http://alloy.alloy.svc.cluster.local:4318/otlp"
```

### 의도

변경 전:

```text
Fleet Agent → 기존 OTLP endpoint
```

변경 후 목표:

```text
Fleet Agent → existing Grafana Alloy → observability backends
```

### 적용 수준

**설정안 확인, 실제 적용 미확인.**

특히 09-07 log가 계속 `[OTLP-GW-OLD]`를 사용하므로, 최소한 그 로그가 생성된 Fleet process에는 Alloy endpoint가 반영돼 있지 않았다.

가능성은:

- Helm upgrade 미실행
- 일부 Pod만 구 설정 사용
- upgrade 이전 log
- values override 실패

등 여러 가지이며 현재 자료만으로 특정할 수 없다.

---

## 5.6 log level 변경 검토

Fleet Helm command에서:

```bash
--set logLevel=debug
```

가 사용되었고, 실제 09-04/09-07 로그에는 debug-level XID/SXID 및 collector 정보가 출력됐다.

이후 debug 로그가 너무 많아 `warning` 수준을 검토했다.

단, `warning`으로 변경한 Helm command의 실제 실행 결과는 현재 확보하지 못했으므로 **변경 완료로 기록하지 않는다.**

---

## 5.7 `listenAddress=0.0.0.0:15133`

Helm command에:

```bash
--set listenAddress=0.0.0.0:15133
```

가 포함된 버전이 논의됐다.

Fleet process 자체에서는:

```text
GET /v1/metrics
GET /metrics
```

endpoint가 시작된 로그를 확인했다.

그러나 실제 `15133` listen socket 또는 Service exposure를 `ss`, `curl`, `kubectl get svc`로 검증한 결과는 없다.

따라서:

- setting 작성: 확인
- listener runtime binding: 미확인
- 외부 접근: 미확인

---

## 5.8 XID/SXID 검증

debug log를 이용해 XID/SXID watcher가 kernel message를 분류하는 것을 확인했다.

실제 XID 장애는 발생하지 않았고:

```text
Collected events: 0
error_xid: Healthy
error_sxid: Healthy
```

였다.

따라서 “Fleet가 XID failure를 실제 OTLP log로 전송하는 end-to-end test”는 아직 수행된 것으로 기록할 수 없다.

---

## 5.9 Grafana dashboard 구성

접근 가능한 파일에 다음 artifact가 존재한다.

- `fleet-intelligence-loki-dashboard.json`
- `fleet-intelligence-loki-dashboard-fixed.json`
- `fleet-intelligence-mimir-dashboard-v3.json`
- `fleet-intelligence-mimir-dashboard-v4.json`
- `fleet-intelligence-mimir-dashboard-v6-ngc-style.json`

Loki dashboard는 raw log/CPC log rate/error-like logs를 구성한다. 
Mimir dashboard는 compute zone/node group/machine count 및 GPU/DCGM metrics를 구성한다. 
### 적용 상태

- JSON artifact 작성/존재: 확인
- Grafana import: 미확인
- dashboard query 실제 데이터 반환: 일부 대화 맥락은 있으나 현재 보존된 실행 증거로는 충분하지 않음
- production 사용: 미확인

---

## 5.10 2026-09-07: Fleet backend 인증 실패 확인

직접 실행:

```bash
kubectl logs -n fleet-intelligence \
  fleet-intelligence-agent-279kg \
  -c fleet-intelligence-agent \
  --since=30m |
grep -Ei 'collector|gateway|export|inventory|attest|backend|error|failed'
```



결과:

```text
attestation → 401 JWT assertion is expired
inventory   → 401 JWT assertion is expired
```



따라서 이 시점의 inventory/attestation backend 연동은 **인증 실패 상태**였다.

---

## 5.11 2026-09-08: enroll version 설치 중 확인

현재 `enroll` container에서:

```text
GPU             PASS
architecture    Ampere
driver          580.173.02
nvattest        detected
DCGM            4.2.3 supported

Backend request
  → redirect to ngc.nvidia.com/signout
  → redirect rejected
  → enrollment FAIL
```

상태다.

즉 현재 설치 진행의 blocker는 GPU/DCGM prerequisite가 아니라 **enrollment/auth/backend HTTP flow** 쪽이다.

---

# 6. 검증 결과와 현재 이해

## 6.1 DSX Exchange

### 확실히 확인된 것

1. CSC/CPC별 독립 Agent Gateway namespace가 존재한다.
2. CSC/CPC별 독립 Event Bus namespace가 존재한다.
3. 각 Event Bus에 NATS 3 replica, auth-callout, NACK, Surveyor, NATS mTLS Pod가 존재한다.
4. CSC/CPC별 MCP backend가 존재한다.
5. Agent Gateway마다 gateway/bridge/controller/rate-limit/Valkey 계열 Pod가 존재한다.
6. Envoy Gateway가 CPC-1/CPC-2/CSC용으로 배치돼 있다.
7. `dsx-obs`에 OTel Collector가 배치돼 있다.
8. `idp` namespace에 여러 identity test/service Pod가 존재한다.

모두 2026-08-31 시점 Running이었다.

### 제품 구조와 실제 배치가 일치하는 부분

공식 문서의:

```text
CSC
├─ Gateway
├─ NATS x3
├─ auth-callout
├─ NACK
└─ Surveyor

CPC
├─ Gateway
├─ NATS x3
├─ auth-callout
└─ ...
```

구조는 실제 Pod topology와 상당히 일치한다.

### 아직 검증 안 된 핵심

- CPC NATS가 실제 CSC에 leaf-connected 상태인지
- Bridge가 NATS에 실제 연결되어 있는지
- Agent Gateway가 어떤 local MCP backend를 route하는지
- 실제 MCP request가 end-to-end 성공하는지
- auth-callout이 어떤 OIDC/JWKS profile을 사용하는지
- tenant ID가 어느 claim/config에 의해 결정되는지

---

## 6.2 Fleet Intelligence

### 로컬 수집

**정상 동작 확인.**

2026-09-07:

```text
Collected metrics = 480
Collected events = 0
Collected component data = 24
```



DCGM GPU metrics와 각종 host health state가 수집됐다.

### GPU visibility

8 GPU가 실제로 검사됐고 persistence mode에는 문제가 없었다.

따라서 host debug shell에서 `nvidia-smi` binary가 없었던 것과 Fleet GPU detection 성공은 모순되지 않는다.

### XID/SXID

watcher가 활성화돼 있으나 실제 XID/SXID event는 관측되지 않았다.

```text
XID Healthy
SXID Healthy
events 0
```

### telemetry export

기존 OTLP logs path는 실패 상태다.

```text
Fleet
 → [OTLP-GW-OLD]/otlp/v1/logs
 → HTTP 404
 → retry
 → fail
```



### inventory/attestation

09-04:
- inventory response에 `nodeGroup` 누락
- nvattest GPU evidence 실패

09-07:
- JWT expired → 401

09-08:
- enroll HTTP redirect → NGC signout → redirect rejected

즉 backend-facing control/auth path는 기간 중 계속 완전히 정상화되지 않았다.

### Alloy 전환

설계 방향은:

```text
Fleet → Alloy → Mimir/Loki
```

이지만, runtime 성공 증거는 아직 없다.

---

## 6.3 서로 맞지 않거나 주의해야 하는 내용

### CSC/CPC 명칭

과거 대화에서 다른 의미로 설명된 기록이 있었으나 공식 DSX 문서를 기준으로 다음이 맞다.

- CSC = Common Services Cluster
- CPC = Control Plane Cluster



### 공개 release vs 실제 배치

공개 changelog상 Agent Gateway bridge는 `Unreleased`인데 08-31 환경에는 이미 Bridge Pod가 존재한다.

따라서 실제 배치는:

- unreleased build
- internal build
- main branch-derived chart
- 이후 별도 package

중 하나일 가능성이 있으나 정확한 version은 미확인이다.

### Fleet Chart repository 표기

작업 중 사용된 command에서는:

```text
ghcr.io/dsx-ai-factory/charts/fleet-intelligence-agent
```

계열이 사용됐다.

현재 NVIDIA 공식 문서는 NVIDIA chart namespace를 보여주는 부분도 있으므로, **2026-09-08 현재 문서 경로와 사용 당시 deployment artifact를 동일하다고 자동 치환하지 않는다.**

### nvattest

09-08 precheck의 `nvattest detected`는 binary/기본 prerequisite 검증이다.

09-04 실제 evidence collection은 실패했으므로 attestation 성공으로 기록하면 안 된다.

### OTLP destination

09-04와 09-07 runtime은 `[OTLP-GW-OLD]`를 사용했다.

Alloy endpoint를 넣은 Helm command가 존재하지만 runtime 반영 증거가 없다.

따라서 최종 아키텍처에 지금 바로:

```text
Fleet → Alloy
```

를 “현재 동작 중”이라고 표시하면 안 된다.

---

## 6.4 다른 팀원에게 확인이 필요한 정보

아키텍처 통합 시 다음 정보를 추가 확보하면 현재의 점선을 실선으로 바꿀 수 있다.

| 필요 정보 | 이유 |
|---|---|
| 각 CSC/CPC의 실제 Kubernetes cluster/context 이름 | namespace가 물리적으로 어느 cluster에 속하는지 확인 |
| `helm list` / `helm get values` for DSX Exchange | 실제 chart/version/config 확인 |
| Agent Gateway ConfigMap/values | MCP route/auth/rate-limit 구조 확인 |
| Bridge env/config | NATS endpoint, auth mode, shard 역할 확인 |
| NATS leaf connection 상태 | CPC↔CSC 실제 federation 검증 |
| Gateway/TCPRoute/TLSRoute/HTTPRoute | 실제 외부/cluster 간 network path 확정 |
| auth-callout JWKS/issuer 설정 | identity flow 확정 |
| tenant mapping 설정 | tenant의 실제 isolation boundary 확인 |
| Alloy Pod/Service/ConfigMap | Fleet→Alloy 경로 확정 |
| Alloy exporters | Mimir/Loki destination 확정 |
| Mimir/Loki Service 및 datasource | observability backend 위치 확정 |
| Fleet `helm get values` | 현재 collector/enroll/nodeGroup/computeZone 확인 |
| Fleet current image/chart version | 09-04/07/08 로그 차이 원인 추적 |
| enrollment backend endpoint | `/signout` redirect 원인 확정 |
| Grafana dashboard import 상태 | dashboard artifact와 실제 운영 상태 분리 |

---

# 최종 요약

## 1. 전체 아키텍처에 확실히 반영할 수 있는 구성과 연결

### DSX Exchange

다음 **구성 요소의 존재**는 확정 가능하다.

```text
CSC
 ├─ DSX Agent Gateway
 │    ├─ gateway
 │    ├─ bridge
 │    ├─ controller
 │    ├─ rate-limit
 │    └─ Valkey
 ├─ DSX Event Bus
 │    ├─ NATS x3
 │    ├─ NATS mTLS
 │    ├─ auth-callout
 │    ├─ NACK
 │    └─ Surveyor
 └─ MCP backends

CPC-1
 ├─ DSX Agent Gateway
 ├─ DSX Event Bus
 └─ MCP backends

CPC-2
 ├─ DSX Agent Gateway
 ├─ DSX Event Bus
 └─ MCP backends

Shared / supporting
 ├─ Envoy Gateway
 ├─ IDP workloads
 └─ OpenTelemetry Collector
```

CSC/CPC의 NATS federation과 Agentgateway Bridge의 역할은 DSX 공식 architecture에 명시되어 있고 실제 양쪽 구성요소도 배치돼 있다. 다만 **runtime connection 확인 여부는 별도 표시해야 한다.**

### Fleet Intelligence

다음 연결은 실제 실행으로 확정 가능하다.

```text
GPU worker
   ↓
DCGM / NVML / kernel data
   ↓
Fleet Intelligence Agent
   ├─ GPU/DCGM health collection     정상
   ├─ XID/SXID monitoring            활성, 당시 event 0
   ├─ inventory                      backend 요청 발생
   ├─ attestation                    backend 요청 발생
   └─ OTLP export
          ↓
      [OTLP-GW-OLD]
          ↓
      /otlp/v1/logs
          ↓
      HTTP 404 실패
```

09-07에는 480 metrics와 24 component data가 실제 수집됐다. 
Fleet scheduling도 DCGM-enabled GPU worker를 대상으로 한다는 제품 default와 실제 배치가 일치한다.

---

## 2. 추가 확인 전에는 확정하면 안 되는 구성과 연결

다음은 통합 아키텍처에서 **점선 또는 `TBD`로 표시해야 한다.**

```text
Agent Gateway ─ ─ → 특정 MCP backend
Bridge        ─ ─ → 실제 NATS connection
CPC NATS      ─ ─ → CSC NATS active leaf connection
auth-callout  ─ ─ → 실제 OIDC/JWKS provider
tenant        ─ ─ → 특정 JWT claim / namespace / account
Valkey        ─ ─ → rate-limit state backend

Fleet         ─ ─ → Grafana Alloy
Alloy         ─ ─ → Mimir
Alloy         ─ ─ → Loki
Mimir/Loki    ─ ─ → 실제 Grafana datasource

Fleet enroll  ─ ─ → 정상 enrollment backend
```

특히 Fleet observability의 **목표 구조**는:

```text
Fleet Agent
    ↓ OTLP HTTP 4318
Grafana Alloy
    ├─ metrics → Mimir
    └─ logs/events → Loki
                    ↓
                  Grafana
```

으로 정리할 수 있으나, 현재 접근 가능한 자료만으로는 **“설계·설정 방향”이지 “검증 완료된 현재 동작 구조”는 아니다.**

2026-09-08 현재 Fleet 설치 진행의 가장 최신 상태는:

```text
GPU / driver / DCGM prerequisite       PASS
nvattest binary detection              PASS
Fleet local GPU/health collection      과거 실행에서 PASS
기존 OTLP logs export                  FAIL (404)
inventory/attestation backend auth     09-07 FAIL (expired JWT)
new enrollment                         FAIL
  └─ redirect → ngc.nvidia.com/signout
     → redirect not allowed
Alloy 경로                              적용/통신 미확인
```

따라서 다음 통합 단계에서 우선 확인해야 하는 것은 **(1) DSX Exchange의 실제 bridge/NATS/MCP runtime 연결**, **(2) Fleet의 현재 Helm values와 enrollment endpoint**, **(3) Alloy receiver/exporter 실제 config** 세 가지다.