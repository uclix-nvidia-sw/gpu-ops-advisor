# Shared observation expansion — 2026-10-07

Base: main `566ec4a` (PR 81 merged). One RCA/Report profile, arbitrary request
`cluster_id`, MCP UID discovery and exact scope filtering remain mandatory.
No per-CPC profile, cluster registry or pinned datasource UID is introduced.

## Evidence and scope

The operator reconfirmed Fleet 1.5.0-rc.1, Alloy v1.19.2, KSM v2.17.0/v2.18.0,
and DCGM exporter 4.2.3-4.1.3/4.4.2-4.7.0. Both exporter variants use
`/etc/dcgm-exporter/dcp-metrics-included.csv`. Existing saved CSV, samples and
forwarding evidence are in the [earlier ledger](d-binding-cpc-20261006.md).

Live Grafana read-only instant inventory at 06:15:53.791Z returned 118 metric/cluster
rows. A bounded top-one-per-metric/cluster observation at 06:20:48.267Z returned
108 rows and confirmed Fleet `uuid`/`node`, CPU `node`/`load_duration`, and KSM
workload `uid`/`namespace`/`pod`/`node` dimensions. These are bounded presence
checks, not complete device coverage or historical continuity. Raw identifiers
and snapshots remain private. No operational setting changed during these reads.

The reviewed source is the deployed [Fleet tag](https://github.com/dsx-ai-factory/fleet-intelligence-agent/tree/1.5.0-rc.1):
`third_party/fleet-intelligence-sdk/components/accelerator/nvidia/dcgm/` metric
definitions and field assignments, CPU definitions, `pkg/metrics/scraper/prometheus.go`
and `internal/exporter/converter/otlp.go`. The scraper assigns gather time; the
OTLP converter preserves that timestamp and cumulative counter type. A failed
component check can leave the last exported value present. Accordingly Fleet
bindings have **zero forward hold**, carry `measurement_time_verified=false`,
and cannot establish current hardware health or uninterrupted measurement.

## Typed observations

39 of 45 logical queries now resolve to a reviewed shared observation binding.
There are 56 bindings because eleven explicit Fleet alternatives retain their
original exporter candidates. This does not enable every D in every RCA: the
Runbook/query plan still chooses relevant queries within its budget. Nor does it
complete all new report calculations or publish database Runbook revisions.

| Queries | Type and unit | Interpretation limit |
|---|---|---|
| D04, D23 | gauge, Celsius | No universal thermal threshold or causal conclusion |
| D11, D48 | gauge, W | Consumption and enforced limit are distinct; no forward-filled energy |
| D15 | gauge, MiB | Direct exporter free memory; no Pod allocation assertion |
| D16 | gauge, MiB | DCGM byte-to-MiB conversion verified; capacity ratios still need matching identity/time |
| D17 | gauge, ratio 0..1 | Used/(total-reserved), not percent 0..100 and not used/total |
| D18, D19 | gauge, percent / load | Preserve load_duration; load is not a percentage |
| D20 | gauge, 0/1 | Preserve condition/status; Node condition is not GPU health |
| D21 | gauge, resource_units | Preserve resource/unit/container/Pod UID; raw requests are not effective requests |
| D22 | gauge, seconds | Scrape duration, not application latency |
| D24, D25 | gauge, MHz | Clock observations, no throttling diagnosis from value alone |
| D26–D30 | gauge, ratio 0..1 | Activity observations, not workload throughput |
| D31–D34 | gauge, bytes/second | Already rates; never counter-differentiate or combine directions implicitly |
| D36–D44 | counter, count | Reject decreases; preserve ECC device/total and volatile/aggregate distinctions |
| D45, D47 | bitmask / enum | Preserve raw integer codes; no automatic health mapping |

The [NVIDIA profiling reference](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)
identifies PCIe/NVLink fields as rates. Native field semantics are cross-checked
against the [DCGM field reference](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-field-ids.html)
and deployed Fleet assignments. DCGM v4.2.3 and v4.4.2
`dcgmlib/src/DcgmCacheManager.cpp` divide NVML bytes by 1024*1024 for FB_TOTAL,
establishing D16 as MiB despite the Help string saying MB. An adjacent field's
ns wording is not accepted as D46's unit. Nonfinite/out-of-domain/sentinel magnitudes are
rejected; enum/bitmask observations require nonnegative integers.

## Fleet alternatives

D23–D32 and D44 add separate `fleet_intelligence` bindings. The deployed source
assigns each corresponding DCGM field to the named lower-case metric without a
value scale transformation. The live stored names and GPU target labels match.
Equivalence is limited to the typed GPU observation, **not** freshness, scrape
cadence, Pod attribution or an exporter health contract. The original uppercase
exporter candidates remain unselected, avoiding hidden source substitution.

## Remaining activation work

| Query | Concrete missing prerequisite |
|---|---|
| D07 | A verified effective-v1 producer; Run:ai workload-exporter presence does not prove this contract |
| D12 | Forward kube_node_status_allocatable through the direct Alloy keep rule and verify stored dimensions/values |
| D13 | Workload log producer, stream selector and outcome meaning; never substitute Fleet health logs |
| D35 | Forward the existing CSV XID field; it is a last-code observation, not an event counter |
| D46 | Resolve deployed board-limit violation counter unit; observed zeros cannot establish ns versus another unit |
| D49 | Forward the existing CSV energy field and verify mJ/counter continuity/reset handling |

The common [forwarding helper](../../tools/ci/extend_observation_forwarding.py) is documented below.
It adds only the three missing names to the exact reviewed Alloy metric-name keep
rule. It does not edit any cluster label, exporter CSV, Secret, deployment or PVC.

Run `python3 tools/ci/extend_observation_forwarding.py` to preview, then the same
command with `--apply` on a server whose kubectl context is the intended cluster.
The identical script works for every cluster. It fails on unfamiliar/ambiguous
rules, uses a compare-and-swap JSON patch, and stores private apply/rollback files.
Rollback uses `kubectl -n alloy patch configmap alloy --type=json --patch-file
<private_backup>/rollback.json`; it refuses to overwrite subsequent edits.
Confirm Alloy reload and new Mimir samples before selecting D12/D35/D49.

## Acceptance boundary

Local tests cover arbitrary cluster discovery, alternative source selection,
typed invalid values, preservation through RCA synthesis inputs, and absence of
health promotion. Both Worker fixture E2E and chart checks must pass before push.
Deployment, actual Worker results and the six prerequisites remain separately
unverified. All-D activation is **not complete**.
