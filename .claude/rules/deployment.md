---
paths:
  - "charts/**"
  - ".github/**"
  - "tools/ci/**"
  - "agents/config.example.json"
  - "job-controller/config.example.json"
  - "incident/config.example.json"
  - "docs/helm-*.md"
  - "docs/ci-release.md"
---

# Deployment, Configuration and CI

Read [safety.md](safety.md) before operational commands. Use the [chart README](../../charts/gpu-ops-advisor/README.md), [installation](../../docs/helm-install.md), [upgrade](../../docs/helm-upgrade-existing.md) and [CI/release](../../docs/ci-release.md) guides for the actual environment.

## Configuration Mirrors

Update both sides in the same change; `python tools/ci/check_chart.py` enforces equality:

| Source | Helm copy |
|---|---|
| `agents/config.example.json` | `charts/gpu-ops-advisor/files/agents.json` |
| `job-controller/config.example.json` | `charts/gpu-ops-advisor/files/job-controller.json` |
| `incident/config.example.json` | `charts/gpu-ops-advisor/files/incident.json` |

- `configuration.agents`, `configuration.jobController` and `configuration.incident` replace the complete embedded object; they are not deep-merged. Update environment examples and documentation for changed inputs.
- Keep `tools/ci/components.json`, the deployment-component inventory, aligned with chart components. Preserve immutable policy revisions when changing Incident policy content.
- CI publication does not deploy to Kubernetes. Use successful CI artifacts and record the exact chart version, image digests, target and recovery plan for an authorized deployment; preserve DB/report PVCs. PR build artifacts are not published deployment images.
- For Agent timeout changes, use [Agent execution guidance](../../agents/README.md); request timeout, job deadline and uncertain remote execution/quarantine are distinct concerns.

## Validation

Use an active Python 3.12 environment and Helm 3.17.3 on `PATH`. If needed, create/activate `.venv` as described in [Agent setup](agents.md#setup-and-validation); installing worker dependencies is not required for chart-only checks.

From the repository root:

```bash
python -m pip install PyYAML==6.0.2 jsonschema==4.26.0
python tools/ci/check_chart.py
python -m unittest discover -s tools/ci/tests -v
```

Also run the affected module checks when runtime settings/contracts change; follow [.github/workflows/tests.yml](../../.github/workflows/tests.yml) for full CI and workflow validation. Apply the [common completion criteria](workflow.md#completion-criteria). Static chart checks do not prove deployment success. After an authorized deployment, verify the affected intake-to-execution-to-publication/query flow, not just Pod readiness; common Agent settings require both workers. Record remaining real-environment checks as unverified until executed.
