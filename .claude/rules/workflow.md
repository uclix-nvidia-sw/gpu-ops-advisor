# Workflow and Completion

Applies to every task. Human explanations and examples: [team collaboration guide](../../docs/team-development.md).

## Working Scope

- Confirm the task goal, allowed scope and observable acceptance criteria before implementing. Analysis-only requests do not authorize implementation.
- Inspect the branch and worktree; preserve existing changes. Keep edits focused, reuse existing structure and avoid unrelated formatting, renames, abstractions or dependencies.
- Follow the ownership and contract-impact map in the team guide. Validate affected consumers, share cross-module impacts and clarify ambiguous contracts; optional peer review does not remove this coordination.
- Match existing naming and surrounding documentation language; keep identifiers and developer-facing code comments in English. Preserve UTF-8 CRLF text and use existing formatters.
- Update nearby documentation when behavior/interfaces change. Do not casually edit versioned/generated deliverables; change Archify JSON sources and regenerate HTML instead of manually editing generated HTML.

## Git and Review

- Branch naming applies to every contributor and coding assistant in this repository. Use `<type>/<short-english-description>` with `feat`, `fix`, `docs`, `test`, `refactor` or `chore`; use lowercase letters, digits and hyphens in the description. Do not use `codex/` or another tool-name prefix. This user-selected project convention replaces default tool prefixes. Honor an explicitly requested branch name. Creating a branch is not required when the task permits working on main.

- Current policy permits main work and direct push after change review, relevant checks and user authorization. A development request alone does not authorize commit, push, PR creation, merge or deployment. Stop after a local commit when only a commit is requested.
- Peer review/Approve is optional; the author remains responsible for verification, including AI-written changes. The future branch/PR workflow applies only after the team records its transition or explicitly chooses PRs for the task. Do not impose it on current main work.
- Use English and Korean together for commit messages, PR titles and core change descriptions. Explicitly select only intended files and inspect the staged diff before an authorized commit.
- Before an authorized push, check fresh remote state; never overwrite divergent history with force push or bypass repository protections. After push, report that commit's actual CI state, investigate failures and do not deploy failed artifacts. PR merges require the latest required CI to pass.
- Push/merge, artifact publication and deployment are separate outcomes; deployment needs its own authorization. Branch names and command examples are in the team guide.

## Completion Criteria

1. Define what success looks like for this task: expected input, observable output/state and relevant failure or missing-evidence behavior. Use current contracts and acceptance documents linked from [docs/README.md](../../docs/README.md); do not invent a blanket coverage or analysis-accuracy target.
2. Review the final diff for scope, secrets and unintended changes. Update affected contracts, consumers, configuration mirrors and documentation where applicable.
3. Run the smallest relevant checks in the applicable module rules, then the relevant DB, integration or E2E checks covering the changed behavior, even for a single-module change. The complete CI setup is in [.github/workflows/tests.yml](../../.github/workflows/tests.yml).
4. Report each required criterion as **passed**, **failed**, **not run/unverified**, or **not applicable with a reason**. A successful command is evidence only for what it actually checked. Report commands, working directories, results and real-system versus fixture boundaries. Never label skipped tests or pending CI as passed.
5. Verify the requested behavior, not only a build or HTTP response. Default Go tests omit `-tags=e2e`; Python E2E skips without `RUN_AGENT_E2E=1`. Fixture-backed E2E is not proof of production integration or RCA quality.
6. Do not mark the task fully verified or push/merge while required pre-push checks remain unresolved. If an external check must occur after an authorized deployment, agree its owner, conditions and failure response, and leave it explicitly unverified until run. Product changes need relevant acceptance evidence; documentation-only changes do not require live LLM/Grafana tests.
7. State the completed stage precisely: local files, local commit, remote push, CI, deployment or real-system validation. List remaining gaps and next actions without implying authorization to perform them.

## Documentation Checks

Run `python tools/check_links.py` from the repository root (or `python3` where that is the Python 3 command). It needs only the standard library. Check renamed section anchors and paths inside prompt code blocks separately; the checker does not validate those. For rule changes, review scope/routing, English–Korean consistency and preservation of existing policies. Loading a module rule does not itself require its entire runtime suite for a documentation-only change; choose checks by the actual impact, and verify any changed executable instructions. Static file checks do not prove a coding tool loaded the rules in a live session.
