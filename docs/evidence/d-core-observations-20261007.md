# Shared core observation bindings — 2026-10-07

This review reuses the saved exporter/KSM samples, image/CSV inventory and
operator-supplied Alloy routes in [the environment ledger](d-binding-cpc-20261006.md).
It does not reintroduce per-cluster profiles or pinned datasource UIDs.

| D | Reviewed contract | Consumer limit |
|---|---|---|
| D03 | DCGM exporter framebuffer used, gauge MiB, UUID/node, direct Alloy 15s scrape | Usage is not memory error diagnosis or a capacity ratio; namespace/Pod ownership is not asserted |
| D06 | KSM kube_pod_info, gauge 1, node/namespace/pod/uid, direct Alloy 15s scrape | Pod placement is not GPU allocation or proof of workload impact |
| D10 | Alloy up, gauge 0/1, instance, direct path 15s scrape | Scrape status is not device health; missing samples do not establish downtime |

The reviewed exporter versions are 4.2.3-4.1.3 and 4.4.2-4.7.0; KSM versions
are v2.17.0/v2.18.0 and Alloy v1.19.2. Saved windows are bounded observations,
not whole-cluster totals or current availability. Both supplied Alloy routes
retain these metric names and add collection_path=alloy-direct without value
transformation. D03/D06 retain their producer job selectors. D10 intentionally
covers scrape targets on this direct route. New producers must satisfy this
contract; datasource discovery alone does not attest versions or semantics.

Thirty-second max_hold is a conservative analysis cap, not guaranteed continuity.
D03 rejects negative, nonfinite and values above the exact integer range (including
DCGM integer sentinel magnitudes); D06 accepts only 1; D10 accepts the 0..1 range.
The gauges never use counter deltas. Central retention limits and their caveats
remain those in [the discovery review](d-binding-discovery-20261007.md#availability-and-time).

The XID48/ECC investigation draft adds optional D03 context with explicit limits:
used MiB cannot establish ECC failure, health or an unverified capacity percentage.
Required D09 health/error facts remain unchanged. DB publication is separate.
Existing Ops consumers receive the same typed observation contract; the separate
Ops invalid-result incident is not addressed by this change.

## Remaining original queries

- D04/D11: Fleet temperature/power samples exist; producer invalid-value and time
  behavior still need review before selection. Uppercase exporter alternatives
  are not silently substituted for these Fleet bindings.
- D07: effective unbound request producer not observed in the inspected windows.
- D12: allocatable metrics are not in the supplied direct Alloy keep rule; raw
  container requests cannot replace allocatable capacity.
- D13: workload-log producer, selector and outcome semantics remain unverified.

These five and the remaining new bindings stay candidates. Neither this file nor
fixture tests prove new-profile live Worker acceptance. After deployment, inspect
actual query IDs, request cluster/target, UID, units, evidence and published results.
