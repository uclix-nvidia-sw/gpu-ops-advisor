---
paths:
  - "rcca-agent/**"
  - "ops-agent/**"
  - "shared/python/**"
  - "agents/**"
  - "grafana-mcp/**"
---

# Product Agents and Shared Python

This file guides development of product workers; it does not define a Claude Code subagent. Root [AGENTS.md](../../AGENTS.md) is a separate coding-assistant entry point.

- `rcca-agent/` implements incident RCA; `ops-agent/` implements operational reports. `agents/` holds their shared configuration examples, setup, tests and execution documentation.
- `shared/python/src/agent_common/` is code imported by both workers: JC worker lifecycle, LLM calls, settings, result contracts, observations/calculations and storage. Reuse it for behavior shared by both workers. It is not another running Agent, a Python installation or coding-assistant memory.
- Shared Python, `agents/` or Grafana MCP changes require checking both workers. Share JC/DB contract impacts with the Backend/DB owner. Keep pinned official Grafana MCP packaging and existing query/evidence contracts.
- RCA changes must preserve incident snapshot/runbook/evidence references and missing-evidence behavior; Ops changes must preserve period/units/calculations and references to published RCA. RCA result changes also affect Ops, Backend and Frontend consumers.
- Workers register/claim with JC and submit result candidates for JC publication. Do not add another scheduler, queue or direct submission API. Calculate/validate deterministically; use the LLM to explain verified evidence, not manufacture completeness or performed actions.
- Read [execution and timeout guidance](../../agents/README.md), [Agent QA](../../agents/QA.md), the relevant worker README and current Agent/contract specifications in [docs/README.md](../../docs/README.md). Source configuration edits also require [deployment.md](deployment.md).

## Setup and Validation

Packages support Python 3.11–3.13; CI uses 3.12. Do not use Python 3.14 or later for the workers. Create `.venv` with `python3.12 -m venv .venv` on macOS/Linux or `py -3.12 -m venv .venv` on Windows. Activate with `source .venv/bin/activate` or `.\.venv\Scripts\Activate.ps1` respectively, and verify `python --version`.

From the repository root, in that environment:

```bash
python -m pip install -r agents/requirements.txt -e shared/python -e rcca-agent -e ops-agent ruff==0.14.0
ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci
ruff format --check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci
python -m pytest -c agents/pytest.ini agents/tests -q
```

Apply the [common completion criteria](workflow.md#completion-criteria). Run relevant lifecycle/integration/E2E cases, including both workers for shared changes. E2E requires `RUN_AGENT_E2E=1` plus the test DB, binaries and verified MCP setup in [.github/workflows/tests.yml](../../.github/workflows/tests.yml); setting the flag alone is insufficient.

A successful LLM response is not proof of a correct RCA/report or JC publication. Verify applicable evidence references, field semantics, insufficient-data outcomes, final job/result state and affected consumers. Separate real Grafana/LLM validation from fixture tests; agree task-specific quality criteria against actual evidence rather than inventing a universal accuracy percentage.
