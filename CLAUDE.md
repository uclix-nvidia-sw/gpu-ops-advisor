# Claude Code Context

Project-wide team guidance for Claude Code. Other coding agents load the same rules through [AGENTS.md](AGENTS.md). See [docs/CLAUDE.ko.md](docs/CLAUDE.ko.md) for the Korean translation. If the translations diverge, this English file is authoritative.

## Scope

These instructions apply to the entire repository unless a deeper `CLAUDE.md` overrides them.

## Product Intent (Stable)

- GPU Ops Advisor v1.3 produces GPU/Node/Pod incident RCA and operational reports from stored observability evidence.
- Automatic RCA flows from Grafana to Incident, Job Controller, and the RCA Agent. Reports flow from the GUI/Backend to Job Controller and the Report Agent; Backend also creates scheduled report jobs.
- Agents are long-running workers that pull jobs from Job Controller. They do not own another queue, scheduler, user-facing submission API, or device-control path.
- Deterministic calculations and validation belong in code. The LLM interprets and explains verified evidence; it must not invent data, actions, or successful completion.

## Truth Hierarchy

- Stable intent and guardrails: this `CLAUDE.md` and the root `README.md`.
- Actual runtime behavior: implementation and tests in each module.
- Shared API and database contracts: `shared/contract/` and `shared/migrations/`; the latter is the single SQL source.
- Designed scope and acceptance criteria: `output/deliverables-20260917-v1.3/`.
- Verified status and known limits: each module's `QA.md`.

If documents and code diverge, treat code and tests as current behavior and update the nearest relevant document in the same change. Design documents, fixtures, and newly added tests are not proof of production validation.

## Reference Map

- System overview and flows: `README.md`
- Requirements and scope: `output/deliverables-20260917-v1.3/01_요구사항_개발범위_정의서.md`
- API, data, and inter-module contracts: `02_백엔드_API_작업명세서.md`, `03_데이터_설계서.md`, and `14_모듈간_호출과_공통실행_계약.md` in the same directory
- Test acceptance and operations: `05_테스트_검수_기준서.md` and `06_배포_운영_인계서.md` in the same directory
- Agent behavior and limits: `agents/README.md` and `agents/QA.md`
- Deployment: `charts/gpu-ops-advisor/README.md` and `docs/helm-install.md`
- CI and release behavior: `docs/ci-release.md` and `.github/workflows/tests.yml`

## Project Layout

- `backend/`, `incident/`, `job-controller/`, `shared/`: independent Go modules; there is no root Go workspace.
- `rcca-agent/`, `ops-agent/`, `shared/python/`, `agents/`: Python workers, shared runtime, profiles, and tests.
- `frontend/`: React, TypeScript, Vite, and Vitest application.
- `grafana-mcp/`: packaging for the pinned official Grafana MCP.
- `charts/gpu-ops-advisor/`: Helm chart and embedded application configuration.
- `tools/ci/`: chart, component, packaging, and release contract checks.
- `docs/` and `output/`: operational evidence, current deliverables, and architecture material.

## Architectural Boundaries

- Keep automatic RCA entry at `Grafana -> Incident -> Job Controller -> RCA Agent`; do not add direct GUI/Backend-to-Agent execution.
- Job Controller owns queueing, capacity, leases, attempts, and result publication. Agents register and claim work from it.
- Preserve database ownership described in `shared/README.md`, immutable incident snapshots/config revisions/result hashes, and idempotency keys.
- Keep unavailable or semantically unverified observations as `unknown`, `partial`, or `blocked`; do not fabricate a complete result.
- Hardware remediation remains a human action.

## Working Style

- Keep changes focused and reuse existing structure before adding abstractions, tools, or dependencies.
- Prefer small, surgical edits; do not reformat or rename unrelated files.
- Match existing naming and the language of the surrounding documentation. Keep code identifiers and developer-facing comments in English.
- Update the nearest relevant documentation when behavior or an interface changes.
- Preserve UTF-8 CRLF text files and use existing formatting scripts where available.
- Never commit secrets, tokens, local `.env` files, or production data.

## Configuration Mirrors

When changing a source configuration, update its Helm copy in the same change:

- `agents/config.example.json` and `charts/gpu-ops-advisor/files/agents.json`
- `job-controller/config.example.json` and `charts/gpu-ops-advisor/files/job-controller.json`
- `incident/config.example.json` and `charts/gpu-ops-advisor/files/incident.json`

`python tools/ci/check_chart.py` enforces these pairs.

- `configuration.agents`, `configuration.jobController`, and `configuration.incident` replace the complete embedded object; they are not deep-merged.
- `tools/ci/components.json` is the deployment-component inventory and must remain aligned with chart components.

## Operational Safety

- Never run `backend/scripts/dev-server.ps1` against a shared, staging, or production database; it enables migrations and demo seeding.
- Job Controller and Incident apply file/Helm configuration at startup. Do not rely on direct database edits that a restart can overwrite.
- Preserve existing PostgreSQL and report PVCs during Helm upgrades. Follow `docs/helm-upgrade-existing.md`; do not delete or recreate them casually.

## Validation Setup

Python checks assume an active Python 3.12 virtual environment, matching CI. For initial setup, create `.venv` with `python3.12 -m venv .venv` on macOS/Linux or `py -3.12 -m venv .venv` on Windows. Activate it with `source .venv/bin/activate` on macOS/Linux or `.\.venv\Scripts\Activate.ps1` in PowerShell. Verify `python --version` before installing dependencies; the agents do not support Python 3.14 or later.

From the repository root, install the dependencies for the checks you need:

- Agent checks: `python -m pip install -r agents/requirements.txt -e shared/python -e rcca-agent -e ops-agent ruff==0.14.0`
- Helm and CI checks: `python -m pip install PyYAML==6.0.2 jsonschema==4.26.0`; Helm 3.17.3 must also be on `PATH`.
- The documentation link checker needs only Python's standard library.

## Validation (Smallest Relevant First)

- Go, from each changed module (`shared`, `backend`, `job-controller`, or `incident`) and its affected consumers:
  `go vet ./...`, `go test -race ./...`, `go build ./...`
  Changes to Go contracts or migrations in `shared/` require checks in all four Go modules. Changes to reused `job-controller/` code also require checks in `backend/` and `incident/`. Independent modules do not run each other's tests; some shared-contract tests live in `backend/internal/contract/`.
- Python agents, from the repository root:
  `ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`
  `ruff format --check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`
  `python -m pytest -c agents/pytest.ini agents/tests -q`
- Frontend, from `frontend/`:
  `npm run format:check`, `npm test`, `npm run build`
- Helm and CI contracts:
  `python tools/ci/check_chart.py`
  `python -m unittest discover -s tools/ci/tests -v`
- Documentation links:
  `python tools/check_links.py`

Run the relevant DB, integration, or E2E tests whenever they cover the changed behavior, including startup defaults, migrations, and cross-service contracts, even when only one module changes. Ordinary Go tests omit `-tags=e2e` suites, and Python E2E tests skip unless `RUN_AGENT_E2E=1`; a passing default test run does not establish E2E coverage. Use the test database and binary setup in `.github/workflows/tests.yml`, the authoritative full CI command list, and report exactly which external systems were real versus fixtures.

## Language and Toolchains

- Go modules use Go 1.26.2 and relative `replace` directives. Reuse `shared/` and prefer table-driven tests for multi-case logic.
- Python packages support 3.11 through 3.13; CI uses 3.12. Reuse `shared/python/` for behavior shared by both agents.
- Frontend CI uses Node 24 and the committed lockfile. Do not replace established React/Vite/Vitest patterns without need.
- Helm validation targets Helm 3.17.3. Do not put secrets in chart values or manifests.

## Avoid

- Do not introduce a new queue, scheduler, aggregator, direct Agent API, or dependency without a demonstrated requirement.
- Do not edit generated or versioned deliverables casually. In particular, change the Archify JSON source and regenerate its HTML rather than editing generated HTML.
- Do not infer Fleet, metric, allocation, topology, or health semantics that are not defined by a deployed contract.
- Do not describe a test as passed unless it was run, or a fixture-backed test as production integration.
