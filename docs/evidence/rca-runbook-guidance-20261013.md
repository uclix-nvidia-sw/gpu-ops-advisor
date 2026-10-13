# RCA Runbook guidance review / 조사 지침 검수

## Source check

On 2026-10-13, the NVIDIA [Xid catalog](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html)
was checked for Xid 79 and Xid 154. The Xid 79 row marks A100, H100,
B100 and GB200, RESTART_BM / CONTACT_SUPPORT, and linkage CUDA 12.7;
GPU driver R565. Xid 154 summarizes recovery actions for other Xids;
the linkage is not a guarantee that every Xid 79 produces a companion event.
Deployment version, event co-occurrence, target identity and action approval
are separate checks. Existing reviewed Runbook content and hashes are preserved.

## Local validation

- RCA/Fleet/catalog focused tests: 128 passed before final compatibility corrections.
- Final non-E2E Agent regression: 1067 passed, 38 deselected; the existing
  Windows-specific Report cleanup test file was excluded. No Report code changed.
- Real local PostgreSQL + workers + official MCP publication tests: 4 passed.
  Grafana and model responses are fixtures, not production inference validation.
- Frontend: 240 tests passed; production build passed (existing chunk-size warning).
- Actual RcaNarrative component rendered as a local fixture: Korean keep-all
  wrapping and separate guidance section verified in browser. Not a live deployment.
- Python lint, changed frontend formatting and local documentation links passed.

Investigation guidance remains documentary text citing the immutable Runbook
snapshot. It never enters eligible recommendations, promotes device identity,
changes partial status, or executes remediation. English prose checks preserve
known identifiers and technical vocabulary. Causal grounding instructions are
not a proof of model correctness; a fresh live RCA remains required after deployment.
