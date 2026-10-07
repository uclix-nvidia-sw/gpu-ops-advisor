# Shared binding discovery review — 2026-10-07

## Scope

This record supports `shared-grafana-discovery-20261007-r1`. It combines the
[earlier exporter investigation](d-binding-cpc-20261006.md), operator-supplied
pod/image and Alloy routing output, and a bounded authenticated Grafana review.
Raw logs, machine identities, private datasource UIDs and credentials are not
committed. Local fixtures validate implementation, not production acceptance.

Only D02 utilization and D09 recorded Fleet observations are enabled. The other
43 bindings remain candidates. Cluster names/counts and datasource UIDs are not
embedded. Both workers read the same source and Helm mirror. Discovery does not
attest producer versions or automatically verify newly onboarded producers.
New sources must satisfy these reviewed source contracts before onboarding.

## D02 direct exporter observations

Reviewed exporter variants: `4.2.3-4.1.3-ubuntu22.04` and
`4.4.2-4.7.0-distroless`. The common contract is
`DCGM_FI_DEV_GPU_UTIL`, percent gauge in [0,100], GPU `UUID` and node identity,
Prometheus sample time, direct Alloy route with `job=nvidia-dcgm-exporter` and
`collection_path=alloy-direct`. Supplied routing uses 15s scrape / 10s timeout
and does not transform values. The 30s hold is an analysis cap, not measured
continuity. No namespace/pod ownership or fleet-wide GPU total is inferred.
The earlier PDF sampled one exporter pod per environment; its sample counts
are not cluster GPU counts. The version string records reviewed variants, not
per-sample version attestation. Out-of-range utilization is invalid, not clamped.

## D09 recorded Fleet observations

Operator output identifies Fleet `1.5.0-rc.1` on the reviewed replicas. Alloy
routes OTLP resource cluster/node labels into Loki; the query preserves
`job=fleet-intelligence-agent`. Fleet JSON carries component, health, reason,
machine and Kubernetes node identity. JSON filters restrict requested targets;
these JSON fields must not be assumed to be indexed stream labels.

Authenticated Grafana inspection of the requested 2026-10-07 03:58:10–04:28:10 UTC
window returned bounded XID component records including Unhealthy and later
Healthy observations. The displayed records were capped; neither full coverage
nor recovery is proven. The observed producer `attributes.time` was year 0001,
so it is not a usable observation timestamp. Loki time is **recorded_at only**.
`loki_timestamp_is_observed_at=false` and zero hold remain in force: observations
cannot become current-health/error-code facts or satisfy a Runbook requirement
for independently verified normalized health merely because retrieval succeeds.

## Availability and time

D02 uses the earlier saved query window 2026-10-06 08:12:52.099–08:15:41.467 UTC;
D09 uses the bounded Grafana review above. These prove availability of returned
records only. Central configured retention values and selected scalar output do
not prove effective tenant retention or complete historical storage. Empty,
truncated and outside-coverage results remain missing/partial evidence. No
unlimited retention or absence-of-fault claim is authorized by this record.

## Routing and acceptance

The existing Incident path persists the alert cluster_id into the immutable job
scope. The common collector discovers datasource UIDs and approved cluster-label
names via MCP, then uses exact request values. A populated stronger label without
the requested value blocks fallback. Zero/ambiguous matches block retrieval.
Producer selectors and target filters remain intact; evidence records binding
revision, selection method, actual UID and resolved cluster selector.

The Grafana alert expression is unchanged in this PR. Expanding its cluster
selection is a follow-up. Backend/JC registry onboarding remains required;
there is no new cluster registration or per-cluster configuration generator.

An existing published XID79 Runbook still referred to D05. Its D09-compatible
revision 2 was separately published using the official draft/review/publish API
and matched against the saved incident snapshot. Its investigation-only policy
and required normalized-health fact remain. No prior result was rewritten.

After merging and deploying successful CI artifacts, verify both workers load
the shared discovery profile (old full Helm overrides can mask it), trigger an
authorized new incident, and inspect actual selectors/evidence/runbook/result.
Production acceptance of the new discovery code remains pending. Do not apply
the earlier pinned-UID ZIP as part of this common discovery rollout. Report
invalid-result diagnosis and hardware remediation are outside this change.
