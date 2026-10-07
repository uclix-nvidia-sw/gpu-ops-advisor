# D07 and D13 source contracts — 2026-10-07

Base: main `8bd727e`, after PR 82, before operational deployment acceptance.
One common profile, request cluster_id and MCP discovery remain mandatory.

## D07 intent and existing implementation

The background dictionary in [the data design](../specs/common/03_데이터_설계서.md)
describes KSM container requests plus required object state. Its section 3.3
delegates executable transitions to [the D mapping](../specs/common/d-query-mapping.md).
That mapping preserves effective-v1 and explicitly forbids replacing D07 with
D21 raw requests. The original `def2aff` config named
`gpu_ops_effective_unbound_request` with
`effective-request-recording-rule-required` and `validated=false`.

`effective_request_producer` is a logical producer role, not an installed service
or an implementation. The shared validator checks its source registration. O07
consumes verified request intervals with UID, empty node, terminal=false and
request_contract=effective-v1. This repository does not implement the source
calculation or a recording rule that creates those series.

Prefer existing authoritative source data before adding a service. Kubernetes
[system metrics](https://kubernetes.io/docs/concepts/cluster-administration/system-metrics/)
and [KSM guidance](https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/workload/pod-metrics.md)
identify kube-scheduler's `kube_pod_resource_request` at `/metrics/resources` as
an effective Pod request source. This is a candidate, not proof of the deployed
version, enabled endpoint, stored samples or Pod UID continuity.

Required checks before registration:

- Actual scheduler version and metric schema, resource names/units and init,
  restartable init, overhead and any Pod-level resource semantics.
- Exact cluster and namespace/Pod identity. A name-only metric requires a
  time-valid, unique UID join; never join historical data to a current Pod.
- Nonterminal and unbound state, valid observation intervals, replicas and
  duplicate/conflicting sources. Pending alone does not prove unbound.
- Existing scrape/recording capability and retained samples. Do not label a raw
  request as effective-v1 merely to pass O07's gate.

D07 remains unavailable pending these checks. The same checks and implementation
apply to every cluster; no cluster-name branches or new mandatory service.

The operator supplied a KSM v2.17.0 Pod manifest with `pods` included in
`--resources` and Pod label export allowed. This confirms configured collection
scope, not the actual exported/stored series or effective request calculation.
The manifest's own container resource requests describe KSM, not workload demand.
Kubernetes/scheduler version and endpoint evidence are still required.

## D13 raw context versus workload outcome

The D mapping requires preserving the existing Loki query and evidence while
withholding workload-impact conclusions. A new workload collector is therefore
not a prerequisite for *all* D13 observations. The previous blanket candidate
gate conflated the ability to read existing logs with their workload semantics.

The shared profile now adds a distinct `loki_recorded_streams.D13` alternative:
recorded raw cluster log context, exact request cluster and MCP UID discovery.
It reuses the verified Loki transport/timestamp evidence in
[discovery acceptance](d-binding-discovery-20261007.md), not a workload producer
assertion. It has no Fleet job filter, health parser, workload parser or inferred
event timestamp. D09 remains independent. Existing candidate workload bindings
are retained for future concrete stream/target contracts.

The raw context has no verified target-label mapping. Namespace, node, Pod/GPU
targets, JSON log clues and projected namespace scopes therefore fail closed
instead of silently widening to the whole cluster. Limits, exact period,
truncation and missing/empty behavior remain in the shared collector.

Quality preserves evidence_role=raw_log_context, health_fact_eligible=false and
workload_fact_eligible=false. Only observations are supported. O06 continues to
withhold workload disruption and O10 continues to withhold comparable workload
and causal evidence. A successful log query is not proof of interruption,
recovery, throughput or business impact.

## Acceptance

Follow-up source preparation and live name inventory are recorded in
[D07 forwarding preflight](d07-forwarding-preflight-20261007.md). This adds an
optional common KSM phase forwarding step without activating D07.

Local regression tests cover arbitrary cluster discovery, exact LogQL, candidate
preservation, unsupported target rejection and prohibited fact promotion. Both
workers and their existing fixture E2E remain required before push. Live Worker
acceptance follows deployment; this document is not that acceptance.
