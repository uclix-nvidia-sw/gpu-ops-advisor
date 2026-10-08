# Fleet state and event evidence review — 2026-10-08

Base: merged PR #87 (`c54080c`). This is source/observation validation, not permission to publish Runbooks or proof that current physical GPU health is known.

## Confirmed observations

- Saved XID D09 sample: 30 component_data records (28 Healthy, 2 Unhealthy); all attributes.time values are the Go zero timestamp. A separate saved sample contains eight XID/SXID component records with the same zero timestamp. These are bounded samples, not an all-cluster inventory.
- Live read-only Grafana Explore query, 2026-10-08 09:10–09:25 KST: one XID event record was returned by the query below. Loki displayed 09:14:18 KST and extra_info.data.time was 00:14:18Z. This establishes agreement in one stored sample, not a general transport guarantee or comparison with host clock accuracy.
- The event contains event_name=error_xid, event_type=Fatal, data_source=kmsg, xid=79 and a PCI device identifier. Its PCI address was absent from the GPU inventory in the same record. Do not select an arbitrary GPU from the node inventory.
- GPU inventory is a JSON-encoded string in the inspected payloads. The current component parser accepts list-valued inventory only; merely decoding the string would still not prove that an event belongs to an inventory GPU.
- The user identified this run as fault injection. The inspected event itself does not establish synthetic versus physical origin, so production classification cannot rely on this operator context alone.

```logql
{job="fleet-intelligence-agent"}
  | json event_kind=`attributes["log_type"]`, component_name=`attributes["component"]`
  | __error__=""
  | event_kind="event"
  | component_name=~"accelerator-nvidia-error-(xid|sxid)"
```

This cross-cluster query is a bounded source investigation only. Runtime observations must keep the job's requested cluster_id filter. No CPC-specific branch or configuration is introduced.

## Source trace and limits

Inspected the previously acquired Fleet 1.5.0-rc.1 source snapshot, not a newly attested running binary:

| Path | Meaning |
|---|---|
| internal/exporter/collector/collector.go: collectComponentData | Copies LastHealthStates()[0].Time, Health, Reason and Incidents |
| SDK XID/SXID component.go: LastHealthStates and updateCurrentState | Returns currState assigned from evolveHealthyState |
| SDK XID/SXID health_state.go: evolveHealthyState | Computes summary health from event/action/reboot history; the returned state does not assign Time |
| internal/exporter/converter/otlp.go: convertToOTLPLogs | Component records use collection Timestamp; event records use event.Time |
| internal/exporter/collector/collector.go: collectEvents | Reads component events over EventsLookback and carries event time/extra_info |

The separate checkResult.HealthStates function assigns a check time but does not establish that LastHealthStates uses that value. Do not infer event time from that unrelated method.

## Runtime implications

### Injection versus actual kernel errors

Compared the cached 1.5.0-rc.1 source paths, not a newly attested deployed binary:

- `cmd/fleetint/inject.go:getKernelMessageForComponent` uses fixed example text: XID79 at `PCI:0000:01:00`, SXID11001 at `PCI:0000:00:00.0`. It does not discover an installed device. An unmatched PCI identifier in this injection is not evidence that real kernel events cannot map to devices.
- `kernel-message` sends priority/message only. `internal/server/handlers_inject_fault.go` writes through `pkg/kmsg/writer/kmsg.go`; this writer does not set a custom event timestamp. This differs from `component-error` and direct `event` injection.
- The injected kernel message and real kernel messages enter the same `pkg/kmsg/watcher.go` parser. Follow mode estimates boot time when the watcher starts using wall clock minus uptime; `parseLine` adds the kernel microsecond offset. XID/SXID component event records copy that parsed time. A later wall-clock adjustment is a possible shared source of differences, not an established explanation of the observed nine-second difference.
- XID/SXID `evolveHealthyState` omits top-level `HealthState.Time` for both error history and the healthy branch, without an injection-specific branch. Therefore zero-time component summaries are not explained solely by injection. Separate structured event times and nested incident times must not be confused with this summary field.
- SXID identifies an NVSwitch. Matching its PCI address against GPU inventory must not produce GPU identity.

Do not compensate timestamps by the observed offset or classify matching example messages as definitively synthetic. Preserve original event and Loki times, report unverified clock alignment, and validate real device association when evidence permits. Production normal-error samples have not yet been independently paired with host kernel records.

The local follow-up parser now separates structured error events from health facts and passes bounded event observations to RCA synthesis. Its candidate inventory association is not independent identity proof. Runtime publication and live verification remain pending.

Current parse_health intentionally handles component_data; a Fatal event is not a health snapshot. Current health_facts shares the fact_eligible time gate across normalized_health, component, severity, producer_contract and error_code. Setting loki_timestamp_is_observed_at=true to admit the summary would conflate collection time with device observation time.

Next implementation should parse structured error events separately, validate code namespace, event time and provenance, retain node identity, and attach GPU identity only after an unambiguous exact mapping. Re-exported events require deduplication by stable event provenance, with conflicts retained as uncertainty. Error occurrence does not prove present health or repair success. Missing/currently unsupported state evidence must remain an explicit gap.

Regression fixtures now preserve three boundaries: zero-time XID/SXID summaries with string inventory cannot produce device facts; event severity with a structured timestamp cannot masquerade as component health. Fixtures use invented identities and times; raw production records are not committed.

## What publication means

A reviewed investigation Runbook can be published even though some future incidents will lack evidence. Validation must establish correct query/fact contracts, applicable producer semantics, matching criteria, and tested incomplete-evidence behavior. It does not require every incident to yield a root cause.

Compatibility values describe validated applicability; they are not arbitrary nonempty strings used to bypass approval. Keep revisions immutable after publication. Existing nine drafts remain drafts until these conditions are reviewed. PR merge, image deployment, Knowledge publication and a new RCA run are separate events; old results are retained.
