# D07 source forwarding and candidate inventory — 2026-10-07

Base: main `2ca9c85`. No binding status, Worker profile, cluster labels or
datasource UID is changed by this source-preparation change.

## Stored source check

Read-only Grafana Mimir-Operations queries found KSM Pod identity and raw
container requests in both observed environments, including UID, namespace,
Pod, node, resource and unit labels on the reviewed samples. The route label
was alloy-direct. A one-hour existence check found no
`kube_pod_resource_request`, plural-name variant,
`gpu_ops_effective_unbound_request`, `kube_pod_status_phase`, init request or
Pod overhead series. Absence applies to the queried datasource/time interval,
not every possible source, tenant or historical period.

The operator's scheduler API-proxy requests failed: connection refused in one
installation and RKE2 proxy 502 in the other. These are reachability failures,
not evidence of metric absence. Upstream Kubernetes 1.32.9/1.34.3 resource
metrics expose effective requests but not Pod UID. RKE2's effective deployment
and actual metric endpoint remain unverified. Do not open control-plane ports
or replace request semantics merely to make D07 return data.

## Listed bindings versus actual observations

At 2026-10-07T07:37:39.933Z, a bounded name inventory returned 24 aggregated
metric/cluster rows: the following twelve lowercase Fleet names in both
observed clusters. None of the listed uppercase exporter names or the custom
D07 metric returned a row in that instant query. Counts describe visible
series, not complete GPU inventory, measurement freshness or device support.

| Query | Observed Fleet metric | Current common binding |
|---|---|---|
| D23 | dcgm_fi_dev_memory_temp | Fleet alternative verified; exporter candidate retained |
| D24 | dcgm_fi_dev_sm_clock | Fleet alternative verified; exporter candidate retained |
| D25 | dcgm_fi_dev_mem_clock | Fleet alternative verified; exporter candidate retained |
| D26 | dcgm_fi_prof_sm_active | Fleet alternative verified, including the user's X item |
| D27 | dcgm_fi_prof_sm_occupancy | Fleet alternative verified, including the user's X item |
| D28 | dcgm_fi_prof_pipe_tensor_active | Fleet alternative verified; exporter candidate retained |
| D29 | dcgm_fi_prof_dram_active | Fleet alternative verified; exporter candidate retained |
| D30 | dcgm_fi_prof_gr_engine_active | Fleet alternative verified; exporter candidate retained |
| D31 | dcgm_fi_prof_pcie_rx_bytes | Fleet alternative verified; already a rate gauge |
| D32 | dcgm_fi_prof_pcie_tx_bytes | Fleet alternative verified; already a rate gauge |
| D44 | dcgm_fi_dev_pcie_replay_counter | Fleet alternative verified; reset-aware counter |
| D46 | dcgm_fi_dev_board_limit_violation | Present but candidate: deployed unit evidence unresolved |

The [earlier expansion ledger](d-observation-expansion-20261007.md) records the
source semantics review for these alternatives. Upper/lowercase names are not
silently interchangeable; explicit reviewed bindings preserve producer identity.
D13 is a Loki query, not a Prometheus metric name. Its unresolved workload
producer candidate is separate from the raw-context alternative added in PR 83;
see [D07/D13 contract review](d07-d13-source-review-20261007.md).

At 2026-10-07T07:40:22.955Z, a separate Loki five-minute count by cluster and
job returned Fleet logs in both observed environments. No other job appeared
in that bounded query. This confirms stored raw context, not a verified
workload-log producer or complete historical log coverage.

## Common preparation, application and recovery

The existing [forwarding helper](../../tools/ci/extend_observation_forwarding.py)
now accepts `--include-pod-state`. This adds only kube_pod_status_phase to the
previously reviewed metric keep rule (and preserves the original three-name
extension). It creates no scheduler scrape job, recording rule or new service.
It accepts the original, previous extended and new extended rule forms; a later
default invocation cannot remove the state extension. Unknown/ambiguous rules
still fail closed. Cluster labels and all other configuration are preserved.

On each Kubernetes administration server, use the same script and its current
kubectl context. Preview, then apply the reviewed ConfigMap-only change:

```bash
python3 gpu-ops-extend-observation-forwarding.py --include-pod-state
python3 gpu-ops-extend-observation-forwarding.py --include-pod-state --apply
python3 gpu-ops-scheduler-source-probe.py
```

The [probe](../../tools/ci/scheduler_source_probe.py) reads server version and
scheduler image/bind-address/secure-port only, omitting credentials and unrelated
arguments. Its localhost TCP probe applies only to the executing machine and
does not establish endpoint authentication or metric availability. No writes,
exec into workloads, TLS changes, RBAC changes or token creation occur.

Application uses private backup and compare-and-swap patches. Rollback:
`kubectl -n alloy patch configmap alloy --type=json --patch-file <private_backup>/rollback.json`.
It refuses to overwrite subsequent edits. Confirm Alloy reload and new stored
phase samples before using them. Existing scheduler connectivity/authentication
must be reviewed before adding a common scrape route to the same remote_write.

Only after scheduler samples, UID/time/state joins and replica deduplication are
validated should the common D07 consumer/binding change proceed. Preserve raw
samples through MCP and calculate in code. A custom precomputed metric is not
mandatory. Neither this helper nor the source inventory completes D07 activation.

## Validation

Python 3.12 helper unit tests, Ruff and chart/contract checks passed locally.
Tests cover exact-rule-only replacement, both prior rule versions, idempotency,
preserving the state extension on default invocation, and filtered scheduler
settings without credential output. Runtime/DB/Worker code is unchanged, so
Worker execution tests are not applicable to this tooling-only change.
Actual helper application, Alloy reload, stored phase samples and authenticated
scheduler metric access remain operator-side acceptance steps.
