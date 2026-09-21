---
paths:
  - "backend/**"
  - "incident/**"
  - "job-controller/**"
  - "shared/contract/**"
  - "shared/migrations/**"
  - "shared/**/*.go"
  - "shared/go.mod"
  - "shared/go.sum"
  - "shared/README.md"
---

# Go Services and Database Contracts

- `shared`, `backend`, `job-controller` and `incident` are independent Go modules using Go 1.26.2 and relative `replace` directives. There is no root Go workspace. Reuse shared contracts and prefer table-driven tests for multi-case logic.
- Start with the touched module's README/API/QA and [shared ownership](../../shared/README.md). Preserve Incident RCA intake, Backend report scheduling, JC lifecycle/publication ownership and immutable evidence/results.
- RCA result changes affect Backend, RCA, Ops and Frontend consumers; report changes affect Backend, Ops and Frontend. Validate the actual affected paths and follow their rules.
- Keep SQL in `shared/migrations/`. Adding a SQL file is insufficient: check embed registration and each service's application path. Do not assume editing already-applied SQL updates an existing DB.
- Coordinate DB changes with the Backend/DB owner. Document data impact, application order and recovery; verify fresh initialization, existing-DB upgrade and repeated startup. Use an isolated test DB and follow [safety.md](safety.md).
- When Incident `analysis_policies` content changes, use a new revision; do not overwrite different content under an existing revision. Follow [deployment.md](deployment.md) for source/Helm configuration mirrors.

## Validation

From each changed module and its affected consumers:

```bash
go vet ./...
go test -race ./...
go build ./...
```

- Shared Go contract/migration changes require checks in all four Go modules. Reused Job Controller code changes also require Backend and Incident checks. Independent modules do not run each other's tests; shared-contract tests also live in `backend/internal/contract/`.
- Run relevant DB/integration/E2E cases for the changed behavior. Ordinary tests above omit `-tags=e2e` suites; use the test DB and binary setup in [.github/workflows/tests.yml](../../.github/workflows/tests.yml).
- Apply the [common completion criteria](workflow.md#completion-criteria), including contract compatibility and relevant error/idempotency behavior. Report unrun DB/E2E cases explicitly.
