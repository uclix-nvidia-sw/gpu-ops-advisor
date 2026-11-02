# RCA source contracts

This document owns the RCA-only source selection prepared by
[source_profile.py](../../rcca-agent/src/rcca_agent/source_profile.py).
The shared Agent configuration and Ops worker are unchanged. Preparing a file
does not deploy it or establish successful Worker publication.

## Fleet GPU utilization

On 2026-11-02, read-only Grafana queries for CPC-1/dgx02 at
2026-10-30 06:29:47 UTC found eight `dcgm_fi_dev_gpu_util` series from
`job="fleet-intelligence-agent"`. Each had 27 samples in the preceding 30 minutes.
The labels include `cluster_id`, `node`, lowercase `uuid`, `gpu`, and `pci_bus_id`.
The existing direct-exporter selection returned no GPU utilization at that time.
This is a source mismatch, not a measured zero or proof of missing Fleet data.

The reviewed Fleet commit `84f99beef3e633071ad0998b10629b01fb294eaf` SDK `dcgm/utilization/metrics.go` names the gauge;
`component.go` exports `DCGM_FI_DEV_GPU_UTIL` using `fieldValue.Int64()` without
scaling. NVIDIA's pinned [field definition](https://github.com/NVIDIA/DCGM/blob/9fae2867e6e5264fa0fca22a07dc898d591baa21/dcgmlib/dcgm_fields.h)
defines the legacy field as percent 0–100. Do not substitute a newer ratio field
without conversion and a separately reviewed contract.

The prepared RCA binding uses exact cluster/node/UUID scope, the Fleet job,
percent gauge validation, and zero forward hold. Sixty seconds is the reviewed
collection interval, not a promise of continuous samples. A failed producer check
may leave a previous gauge value exposed; Prometheus sample time is not guaranteed
hardware measurement time. Values outside 0–100 remain invalid. No health, recovery,
Pod ownership, useful work, or workload allocation is inferred from this gauge.
Equivalence with the original query is limited to recorded percent observations;
the original 15-second cadence/hold and Pod-label assumptions are not transferred.

Use the existing full deployed profile as input and a new revision. Select only
clusters whose Fleet source contract has been reviewed. The output is for the RCA
Worker's `AGENT_CONFIG_FILE`, not the shared ConfigMap or Ops worker. The command
refuses to overwrite an existing file. Global and other-cluster bindings remain
resolved to their original sources; there is no automatic fallback or source merge.

```powershell
python -m rcca_agent.source_profile --base deployed-profile.json --output rca-profile.json --revision rca-fleet-util-v1 --cluster-id cpc-1
```

## Empty metric status impact

On 2026-11-02, the 311 stored RCA jobs from October 29–30 KST were compared
against their 281 immutable published Runbook revisions, including the original
required/optional observation plans. Of 43 cases with empty GPU utilization,
all 43 treated it as supporting evidence; 42 were ready and one was already
partial for another reason. Holding the other observations and model outcomes
fixed, the empty-metric correction adds zero partial cases: 77/311 (24.7588%)
before and after. Treating every empty supporting metric as a report failure
would instead produce 119/311 (38.2637%); that is not the implemented rule.

The incremental probability is P(previously ready AND any required metric empty),
not P(any metric empty). Do not multiply individual query success probabilities:
queries share producers, nodes and overlapping time windows. For illustration
only, an independent-identically-distributed Bernoulli model gives the one-sided
95% zero-event upper bound `1 - 0.05**(1/311) = 0.9586%` for an arbitrary case,
or `1 - 0.05**(1/234) = 1.2721%` conditional on previously ready cases. These
incident campaigns contain synthetic events and correlated windows; neither
bound is a calibrated production forecast. The historical cohort counts are exact.

The authenticated Grafana response for the recorded SXID 23003 case was replayed
through the current production Observation collector, incident comparisons and
bounded synthesis-input code on main `41ccbb0` plus the local RCA changes.
Eight GPU series and 216 original samples survived, including recorded zeros.
The identical comparison rows compacted into one row explicitly listing all eight
GPUs: 26 samples before and one after the alert per GPU; maximum sample gap
120.01 seconds. The eight original series remained in the model input. This
verifies source-response processing, not live MCP transport, LLM interpretation,
Worker deployment or JC publication. No new production RCA job was created.

## Fabric Manager logs and topology

Grafana Loki-Operations, 2026-10-29 00:00 through 2026-10-31 00:00 UTC:
the job-label inventory contained only `fleet-intelligence-agent`. In CPC-1,
searching for Fabric Manager, source-port and topology text returned no records. The exact requested KST interval (2026-10-28 15:00 through 2026-10-30 15:00 UTC) also returned zero matching streams.
NVSwitch-related records were Fleet component health reports, not direct FM logs.
This bounded search does not establish absence on disk, other tenants or dates.
The read-only SSH inventory attempt to the cluster host failed authentication;
the deployed Fleet image and node-local FM log destination remain unverified.

At 2026-10-30 06:29:47 UTC, CPC-1 Mimir exposed seven relevant metric names:
GPU FM status, NVLink RX/TX bytes, bandwidth total, and CRC/recovery/replay errors.
No switch-port-to-GPU topology series was returned by the scoped name search.
GPU FM status and switch counts cannot reconstruct physical port connections.

Additional read-only checks found only `fleet-intelligence-agent` in the Loki
service-name inventory for that exact KST interval. The sampled NVSwitch reports
contained an empty `extra_info` object and a GPU UUID/PCI inventory, not switch
port edges. A case-insensitive Mimir name search for fabric/topology/NVSwitch/build
metadata returned only GPU FM status (16 series at the same timestamp), not a
Fleet build identity or topology. No local kubectl/Kubernetes credentials were
available for a separate authenticated Kubernetes inventory route. These checks
do not establish absence in unconnected sources or on node storage.

Therefore no FM/topology binding is marked verified or silently substituted.
The existing cluster-only D13 binding cannot query node RCA. A usable source must
retain exact node, recorded/event time, NVSwitch PCI identity, source port and
peer endpoint where available. First configure an explicit FM log source from
the deployed service's configured log destination and obtain versioned topology
inventory from supported vendor tooling. Validate these observations against the
same node and period before enabling a separate RCA binding. Do not widen the
query to the whole cluster or relabel Fleet health reports as FM originals.

NVIDIA's [GPU Node Triage](https://docs.nvidia.com/deploy/gpu-debug-guidelines/gpu-node-triage.html)
and [Fabric Manager guide](https://docs.nvidia.com/datacenter/tesla/fabric-manager-user-guide/index.html)
remain the incident evidence and device-specific recovery authorities.
