# Operational Safety

Applies to every task, including analysis and operational commands that do not edit files.

- Never commit secrets, tokens, local `.env` files or production data. Redact evidence before sharing; do not expose full credential-bearing connection strings, raw sensitive logs or secrets in chart values/manifests.
- Use a personal local or isolated test database for ordinary development/tests. Tests can write or delete data. Confirm the actual target before running them; never connect tests to production. Coordinate shared integration changes and their timing with the responsible owner.
- Never run `backend/scripts/dev-server.ps1` against a shared, staging or production database; it enables migrations and demo seeding and can reuse an existing `DATABASE_URL`.
- Job Controller and Incident apply file/Helm configuration at startup. Direct database edits may be overwritten on restart and are not durable configuration management.
- Preserve existing PostgreSQL and report PVCs during upgrades. Follow [existing deployment upgrades](../../docs/helm-upgrade-existing.md); do not casually delete or recreate persistent storage.
- For DB/deployment changes, identify the target, existing-data impact, application order and recovery plan before applying. Rolling back an application/chart does not automatically reverse a database change. Coordinate shared DB application; do not treat a local file edit as authority to change a live system.
- Hardware remediation remains a human action. Keep unverified observations and uncertain remote execution explicitly unresolved; do not claim recovery from a later successful request alone. Agent timeout/quarantine operations are documented in [agents/README.md](../../agents/README.md) and [Job Controller](../../job-controller/README.md#추론-격리와-취소).
