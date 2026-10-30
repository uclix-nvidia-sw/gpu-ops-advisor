import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "change_plan", ROOT / "tools/ci/change_plan.py"
)
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)
COMPONENTS = json.loads((ROOT / "tools/ci/components.json").read_text())


class ChangePlanTests(unittest.TestCase):
    def test_frontend_pr_selects_its_tests_and_image(self):
        result = planner.plan(
            [
                "frontend/src/App.tsx",
                "frontend/package-lock.json",
                "docs/ci-release.md",
            ],
            "pull_request",
            COMPONENTS,
        )
        self.assertTrue(result["frontend"])
        self.assertFalse(result["backend"])
        self.assertEqual(
            [r["component"] for r in result["matrix"]["include"]], ["frontend"]
        )
        self.assertFalse(result["package"])

    def test_docs_skip_runtime_but_unknown_and_shared_changes_are_full(self):
        result = planner.plan(
            ["README.md", "docs/ci-release.md", "backend/QA.md"],
            "pull_request",
            COMPONENTS,
        )
        self.assertFalse(
            result["backend"]
            or result["frontend"]
            or result["images"]
            or result["package"]
        )
        for path in [
            "backend/a.go",
            "incident/a.go",
            "job-controller/a.go",
            "shared/contract/api.json",
            "shared/migrations/1.sql",
            "shared/python/a.py",
            "agents/config.example.json",
            "rcca-agent/a.py",
            "ops-agent/a.py",
            "grafana-mcp/Dockerfile",
            "charts/values.yaml",
            ".github/workflows/ci.yml",
            "tools/ci/change_plan.py",
            ".dockerignore",
            "docs/deployment-values.yaml",
            "new-module/file",
            "backend/fixtures/README.md",
        ]:
            with self.subTest(path=path):
                result = planner.plan(["frontend/a", path], "pull_request", COMPONENTS)
                self.assertTrue(
                    result["backend"] and result["frontend"] and result["package"]
                )
                self.assertEqual(result["matrix"]["include"], COMPONENTS)

    def test_missing_comparison_and_non_pr_runs_keep_every_gate(self):
        for paths, event in [
            (None, "pull_request"),
            ([], "pull_request"),
            (["frontend/a"], "push"),
            (["README.md"], "push"),
            (["README.md"], "workflow_dispatch"),
        ]:
            result = planner.plan(paths, event, COMPONENTS)
            self.assertTrue(
                result["backend"] and result["frontend"] and result["package"]
            )

    def test_git_comparison_includes_deletion_rename_and_entire_pr_range(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def git(*args):
                return subprocess.check_output(
                    ["git", *args], cwd=root, text=True
                ).strip()

            git("init", "-q")
            git("config", "user.email", "ci-test@example.invalid")
            git("config", "user.name", "CI test")
            (root / "backend").mkdir()
            (root / "backend/a.go").write_text("original")
            git("add", ".")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            (root / "frontend").mkdir()
            git("mv", "backend/a.go", "frontend/a.txt")
            git("commit", "-qm", "rename")
            (root / "frontend/b.ts").write_text("second commit")
            git("add", ".")
            git("commit", "-qm", "second")
            env = {
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_REF": "refs/pull/1/merge",
                "GITHUB_SHA": git("rev-parse", "HEAD"),
            }
            paths = planner.changed_paths(
                env, {"pull_request": {"base": {"sha": base}}}, root
            )
            self.assertEqual(
                set(paths), {"backend/a.go", "frontend/a.txt", "frontend/b.ts"}
            )
            self.assertTrue(planner.plan(paths, "pull_request", COMPONENTS)["backend"])
            self.assertIsNone(planner.changed_paths(env, {}, root))
            self.assertIsNone(
                planner.changed_paths(
                    env, {"pull_request": {"base": {"sha": "f" * 40}}}, root
                )
            )
            env["GITHUB_EVENT_NAME"] = "push"
            env["GITHUB_REF"] = "refs/tags/v1.3.0"
            self.assertIsNone(planner.changed_paths(env, {"before": base}, root))


if __name__ == "__main__":
    unittest.main()
