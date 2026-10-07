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

42 of 45 logical queries now resolve to a reviewed shared observation binding.
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
| D12 | gauge, resource_units | Node allocatable, preserving resource/unit; no placement feasibility assertion |
| D21 | gauge, resource_units | Preserve resource/unit/container/Pod UID; raw requests are not effective requests |
| D22 | gauge, seconds | Scrape duration, not application latency |
| D24, D25 | gauge, MHz | Clock observations, no throttling diagnosis from value alone |
| D26–D30 | gauge, ratio 0..1 | Activity observations, not workload throughput |
| D31–D34 | gauge, bytes/second | Already rates; never counter-differentiate or combine directions implicitly |
| D36–D44 | counter, count | Reject decreases; preserve ECC device/total and volatile/aggregate distinctions |
| D45, D47 | bitmask / enum | Preserve raw integer codes; no automatic health mapping |
| D35 | enum, error_code | Last XID code, not event count or recovery; empty is unknown |
| D49 | counter, mJ | Reject decreases/gaps; no Pod attribution or double counting with power integration |

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
| D13 | Workload log producer, stream selector and outcome meaning; never substitute Fleet health logs |
| D46 | Resolve deployed board-limit violation counter unit; observed zeros cannot establish ns versus another unit |

The common [forwarding helper](../../tools/ci/extend_observation_forwarding.py) is documented below.
It adds only the three missing names to the exact reviewed Alloy metric-name keep
rule. It does not edit any cluster label, exporter CSV, Secret, deployment or PVC.

Run `python3 tools/ci/extend_observation_forwarding.py` to preview, then the same
command with `--apply` on a server whose kubectl context is the intended cluster.
The identical script works for every cluster. It fails on unfamiliar/ambiguous
rules, uses a compare-and-swap JSON patch, and stores private apply/rollback files.
Rollback uses `kubectl -n alloy patch configmap alloy --type=json --patch-file
<private_backup>/rollback.json`; it refuses to overwrite subsequent edits.
For new installations, confirm Alloy reload and new Mimir samples; forwarding
alone cannot establish that every device supports every field.

## Forwarding acceptance

The operator applied the same helper to both supplied environments, with
`cluster_labels_modified=false`. ConfigMap read-back succeeded. Subsequent
Grafana queries confirm new stored samples on `collection_path=alloy-direct`:

| Query | Bounded live evidence on 2026-10-07 UTC |
|---|---|
| D12 | 90 resource series, 720 samples, 06:32:49.280–06:34:36.113; both environments; node/resource/unit preserved |
| D35 | 16 GPU series, 120 samples, 06:32:44.335–06:34:29.335; only one environment, all observed values zero |
| D49 | 18 GPU series, 135 samples, 06:32:44.335–06:34:37.099; both environments; all sampled transitions nondecreasing |

Observed adjacent samples were 15 seconds apart. D49's mJ/counter definition is
declared in both reviewed exporter CSVs; future decreases still withhold deltas.
D35's absence in the other environment is **not** zero or healthy. Both versions
declare a last-XID-code field, so the shared query is enabled with zero hold and
unknown/empty behavior when no series exists. No cluster-specific exception was
added. D12 preserves KSM resource/unit dimensions and is not a scheduling verdict.
This advances source routing and shared query configuration, not post-deployment
Worker acceptance.

## Acceptance boundary

Local tests cover arbitrary cluster discovery, alternative source selection,
typed invalid values, preservation through RCA synthesis inputs, and absence of
health promotion. Both Worker fixture E2E and chart checks must pass before push.
Deployment, actual Worker results and the three prerequisites remain separately
unverified. All-D activation is **not complete**.

## Remaining source implementation order

The operator does not know of a separate effective-request or workload-log
producer. Treat their existence as unverified; do not enable placeholder bindings.
The next work is a common source contract, not a per-cluster profile:

1. D07: establish a versioned producer from authoritative Pod resource semantics,
   including ordinary/restartable init containers, overhead, UID, binding and
   terminal state. Reject unsupported resource semantics. Export the existing
   effective-v1 identity and validity contract; raw D21 sums are insufficient.
2. D13: define an explicit workload opt-in selection and collect its Pod logs
   with cluster, namespace, Pod UID, container and source timestamp. Reuse the
   existing Alloy/Loki route. Keep log observations separate from verified
   workload interruption/recovery facts; Fleet logs do not supply this source.
3. D46: resolve field 243's unit for the deployed versions before enabling it.
   Their Python field comments say microseconds, whereas adjacent fields and
   other NVML APIs mention nanoseconds. Neither adjacency nor a zero sample
   resolves that conflict.
4. Validate new source samples through MCP using an arbitrary request cluster_id,
   then update both shared config copies and test both workers. Deployment and
   real result acceptance remain required after the PR and release build.

No cluster-name condition, cluster registry or fixed datasource UID is needed
for these steps. Source rollout still occurs in each Kubernetes installation,
using the same contract and deployment template.
