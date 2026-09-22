# Claude Code Context

Project-wide team guidance. This English file and the English files in [.claude/rules/](.claude/rules/) are authoritative; Korean translations are in [docs/CLAUDE.ko.md](docs/CLAUDE.ko.md) and [docs/rules.ko.md](docs/rules.ko.md). Other coding agents enter through [AGENTS.md](AGENTS.md).

## Scope and Rule Routing

These instructions apply to the entire repository unless a deeper `CLAUDE.md` overrides them. Before analysis, edits, tests, or operational commands, read the applicable rules below if they are not already loaded. Apply all relevant rules for cross-module work, including affected consumers.

| When | Rules to read |
|---|---|
| Every task: scope, Git authorization, validation and completion | [workflow.md](.claude/rules/workflow.md) |
| Every task: secrets, databases and deployment safety | [safety.md](.claude/rules/safety.md) |
| Frontend work | [frontend.md](.claude/rules/frontend.md) |
| Backend, Incident, Job Controller, shared Go contracts or migrations | [go-services.md](.claude/rules/go-services.md) |
| RCA/Ops workers, shared Python, Agent tests/config or Grafana MCP | [agents.md](.claude/rules/agents.md) |
| Helm, CI, deployment or the Agent/JC/Incident source configuration examples | [deployment.md](.claude/rules/deployment.md) |

Claude Code loads unscoped rules at startup and `paths`-scoped rules when reading matching files. The routing above also covers tasks that do not read matching files. Other coding agents must explicitly follow these links; do not assume they automatically load `.claude/rules/`. Do not import every scoped rule into this file. Rules guide behavior; they are not permission enforcement. See [Claude Code memory](https://code.claude.com/docs/en/memory) and [Codex AGENTS.md guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## Product Intent and Boundaries

- GPU Ops Advisor v1.3 produces GPU/Node/Pod incident RCA and operational reports from stored observability evidence.
- Automatic RCA: `Grafana -> Incident -> Job Controller -> RCA Agent`. Reports: `GUI/Backend -> Job Controller -> Ops Agent`; Backend also creates scheduled report jobs.
- Agents are long-running workers that register and pull work from Job Controller. JC owns queueing, capacity, leases, attempts and result publication. Do not add direct GUI/Backend-to-Agent execution or a device-control path. Do not introduce another queue, scheduler, aggregator, user-facing Agent API or dependency without a demonstrated requirement.
- Preserve the database ownership in [shared/README.md](shared/README.md), immutable incident snapshots/config revisions/result hashes and idempotency keys.
- Deterministic calculation and validation belong in code. The LLM interprets verified evidence; it must not invent data, actions or successful completion. Unavailable or semantically unverified observations remain `unknown`, `partial` or `blocked`. Do not infer Fleet, metric, allocation, topology or health semantics absent a deployed contract.
- Hardware remediation remains a human action.

## Truth Hierarchy

- Stable intent and guardrails: this file, applicable rules and the root [README.md](README.md).
- Actual runtime behavior: implementation and tests in each module.
- Shared API and database contracts: `shared/contract/` and `shared/migrations/`; the latter is the single SQL source.
- Designed scope and acceptance criteria: current specifications listed in [docs/specs/README.md](docs/specs/README.md), organized into common contracts and module folders. RCA proposals in `docs/specs/rca-agent/drafts/` are review drafts, not current requirements; use them when the task explicitly targets the proposal, and do not treat them as replacing current contracts.
- Verified status and known limits: each module's `QA.md`, within its stated date, environment and scope.

If documents and code diverge, treat code and tests as current behavior and update the nearest relevant document in the same change. Design documents, fixtures and newly added tests are not proof of production validation.

## Repository and Reference Map

- `backend/`, `incident/`, `job-controller/`, `shared/`: four independent Go modules; no root Go workspace.
- `rcca-agent/` and `ops-agent/`: product worker implementations. `shared/python/`: common Python runtime. `agents/`: shared configuration examples, setup, tests and execution documentation, not coding-assistant instructions.
- `frontend/`: React/TypeScript/Vite/Vitest. `grafana-mcp/`: pinned official Grafana MCP packaging.
- `charts/gpu-ops-advisor/` and `tools/ci/`: deployment configuration and packaging/contract checks.
- [docs/README.md](docs/README.md): current requirements, API/data/Agent contracts, acceptance criteria, operations, module README/QA and architecture links. Start here instead of assuming a dated design path is still current.
- [docs/team-development.md](docs/team-development.md): ownership, human explanations, branch/PR examples and deployment handoffs. [docs/agent-prompts.md](docs/agent-prompts.md): four role-specific first-task prompts, not additional runtime agents.
- [.github/workflows/tests.yml](.github/workflows/tests.yml): authoritative full CI command/setup list; [docs/ci-release.md](docs/ci-release.md): release behavior.
