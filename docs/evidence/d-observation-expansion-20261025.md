# RCA host metric observations — 2026-10-25

Base: main `b78c018` (PR 208 merged). Adds D63–D72 to the one shared RCA/Report
profile so the memory, ethernet and OS component Runbooks can collect metrics
that bear on their own alerts. CPU Runbooks reuse the verified D18/D19. No Ops
plan references the new queries; Ops behavior is unchanged.

## Evidence and scope

Read-only Grafana queries through the operator's signed-in browser session
against the `Mimir-Operations` Prometheus datasource, 2026-10-24 20:33Z
(`max_over_time`/`min_over_time`/`resets` over 7 days, `count_over_time` over 10 minutes).
No dashboard, alert rule, exporter, Alloy or Secret changed. Raw identifiers and
snapshots remain private.

Types, labels and help text come from the deployed Fleet source,
[`v1.5.0-rc.1`](https://github.com/dsx-ai-factory/fleet-intelligence-agent/tree/v1.5.0-rc.1)
`third_party/fleet-intelligence-sdk/components/{memory,os,network/ethernet}/metrics.go`
and the matching `component.go`. Meanings are cross-checked against the Linux kernel
[`/proc/meminfo`](https://docs.kernel.org/filesystems/proc.html) (MemAvailable),
[interface statistics](https://docs.kernel.org/networking/statistics.html) and
[sysctl fs](https://docs.kernel.org/admin-guide/sysctl/fs.html) (`file-nr`, `file-max`).

## Typed observations

| Query | Fleet metric | Fleet type | Unit | Live (7 days) | Interpretation limit |
|---|---|---|---|---|---|
| D63 | `memory_used_percent` | gauge | percent | 4 node series, 2.1–5.7% | Host memory only; GPU memory is D03 |
| D64 | `memory_available_bytes` | gauge | bytes | 4 series, 98 GB–2.1 TB | Kernel estimate of memory for new programs without swapping; not free memory |
| D65 | `network_ethernet_link_up` | gauge 0/1 | enum | 14 series, 9 interfaces; some interfaces 0 | Physical interfaces only. While every link is down, Fleet may not deliver samples; a gap is not 0 |
| D66–D69 | `network_ethernet_{rx,tx}_{errors,dropped}` | gauge set from the kernel's cumulative counters | packets | 8 series, 4 interfaces; errors 0, rx_dropped up to 403,095; `resets` 0 | Kernel totals that survive link down/up; only the before/after increase is read. Fleet reports these only for interfaces that are up |
| D70 | `os_zombie_processes` | gauge | processes | 4 series, 0–6 | Fleet thresholds are 20% (Degraded) and 80% (Unhealthy) of the system file handle limit on Linux; 1,000 and 2,000 only when that limit cannot be read |
| D71 | `os_threshold_running_pids_percent` | gauge | percent | 4 series, 0.04–0.77% | Running PIDs over Fleet's limit (default 900,000), not over `pid_max`; the value Fleet judges at 80/95% |
| D72 | `os_threshold_allocated_file_handles_percent` | gauge | percent | 4 series, 0.03–27.5% | Allocated file handles over the smaller of `file-max` and Fleet's 10,000,000; the value Fleet judges at 80/95% |

D66–D69 are bound as `counter` with `reject_decrease` because Fleet sets them from
the kernel's monotonic interface statistics; a decrease (driver reload, reboot)
is shown as a reset, never as an increase.

All bindings use `job="fleet-intelligence-agent"`, node targets `node`
(D65–D69: `node`/`interface`), Fleet gather time and zero forward hold, as in
the [2026-10-07 expansion](d-observation-expansion-20261007.md).

## Availability and time

Each node series had 4–8 samples within the 10-minute window (about every 75–150
seconds); per-interface ethernet series had 2–8. Fleet gather time is not
hardware measurement time; observations stay `measurement_time_verified=false`
and cannot establish current health.

## Not added

| Metric | Reason |
|---|---|
| `os_allocated_file_handles_percent`, `os_used_percent` | Divided by `file-max`; one node reports an effectively unlimited `file-max`, so the value is near 0 and differs from what Fleet judges (D72) |
| `memory_used_bytes`, `memory_free_bytes`, `memory_total_bytes` | D63 and D64 already cover the alert; free memory excludes reclaimable cache and misreads as shortage |
| InfiniBand, NCCL, peermem, library | No Fleet metric for these components in this datasource |
