# RCA metric coverage observations — 2026-10-24

Base: main `2c87784` (PR 204 merged). Adds D50–D60 to the one shared RCA/Report
profile so incident Runbooks can collect metrics that bear on the alert itself.
No Ops plan references them; Ops behavior is unchanged.

## Evidence and scope

Read-only Grafana queries through the operator's signed-in browser session
against the `Mimir-Operations` Prometheus datasource, 2026-10-23 23:45Z
(`max_over_time`/`min_over_time` over 7 days, `count_over_time` over 10 minutes).
No dashboard, alert rule, exporter, Alloy or Secret changed. Raw identifiers and
snapshots remain private.

Types and help text come from the deployed Fleet source,
[`v1.5.0-rc.1`](https://github.com/dsx-ai-factory/fleet-intelligence-agent/tree/v1.5.0-rc.1)
`third_party/fleet-intelligence-sdk/components/accelerator/nvidia/dcgm/{mem,nvlink,inforom}/metrics.go`
and `components/disk/metrics.go`. Field meanings are cross-checked against the
[DCGM field reference](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-field-ids.html)
and NVIDIA [GPU memory error management](https://docs.nvidia.com/deploy/a100-gpu-mem-error-mgmt/user-visible-statistics.html).

## Typed observations

| Query | Fleet metric | Fleet type | Unit | Live (7 days) | Interpretation limit |
|---|---|---|---|---|---|
| D50 | `dcgm_fi_dev_row_remap_pending` | gauge 0/1 | enum | 16 GPU series, dgx01/dgx02, all 0 | 1 means a remap waits for a GPU reset; not a failure by itself |
| D51 | `dcgm_fi_dev_row_remap_failure` | gauge 0/1 | enum | 16 series, all 0 | 1 is the RMA-policy flag only once Field Diagnostics confirms it |
| D52 | `dcgm_fi_dev_uncorrectable_remapped_rows` | counter | count | 16 series, all 0 | InfoROM entries, not rows remapped in hardware; reject decreases |
| D53 | `dcgm_fi_dev_correctable_remapped_rows` | counter | count | 16 series, all 0 | Same as D52 for correctable errors |
| D54 | `dcgm_fi_dev_banks_remap_rows_avail_none` | gauge | count | 16 series, all 0 | Historical bucket of banks without spare rows; not current availability |
| D55–D57 | `dcgm_fi_dev_nvlink_error_dl_{crc,recovery,replay}` | counter | count | 16 series, all 0 | Sum over the GPU's links; no per-link attribution or BER |
| D58 | `dcgm_fi_dev_inforom_config_valid` | gauge 0/1 | enum | 18 series incl. two workers, all 1 | Checksum validity only; not InfoROM version or ECC health |
| D59, D60 | `disk_used_bytes`, `disk_free_bytes` | gauge | bytes | 4 node series, `mount_point="/"` only | Fleet reports the root mount; other mounts are absent, not empty |

All bindings use `job="fleet-intelligence-agent"`, GPU targets `uuid`/`node`
(D59/D60: `node`/`mount_point`), Fleet gather time and zero forward hold, as in
the [2026-10-07 expansion](d-observation-expansion-20261007.md).

## Availability and time

Samples arrived about every 150 seconds within the 10-minute window. Fleet gather
time is not hardware measurement time; observations stay
`measurement_time_verified=false` and cannot establish current health.

## Not added

| Metric | Reason |
|---|---|
| `dcgm_fi_dev_thermal_violation`, `dcgm_fi_dev_power_violation`, `dcgm_fi_dev_reliability_violation` | Cumulative violation time; the deployed unit is not confirmed (same open question as D46) |
| `dcgm_fi_dev_nvlink_count_*` | Present in Fleet source but not in this datasource's metric list |
