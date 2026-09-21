---
paths:
  - "frontend/**"
---

# Frontend

- Reuse the existing React, TypeScript, Vite and Vitest patterns. CI uses Node 24 and the committed lockfile; install as CI does with `npm ci --ignore-scripts` in `frontend/` when needed.
- Start with [Frontend README](../../frontend/README.md), [Frontend QA](../../frontend/QA.md) and the current UI/API specifications in [docs/README.md](../../docs/README.md). Verify actual Backend responses rather than inventing fields or statuses.
- Validate normal, failed and empty/missing-evidence displays for the changed flow. Do not display unknown evidence as a healthy measurement or an unpublished result as final.
- API/result format changes require checks of the corresponding Backend/Agent consumers and their rules, not only frontend tests.

## Validation

From `frontend/`:

```bash
npm run format:check
npm test
npm run build
```

Apply the [common completion criteria](workflow.md#completion-criteria): demonstrate the changed screen/interaction and applicable response states, using focused tests or UI checks. Passing a build alone does not verify the interaction. State whether the API was real or mocked.
