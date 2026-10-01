import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "tools/ci" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metadata = load("release_metadata").metadata
bind_images = load("package_chart").bind_images


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.env = dict(
            GITHUB_SHA="a" * 40,
            GITHUB_EVENT_NAME="pull_request",
            GITHUB_REF="refs/pull/5/merge",
            GITHUB_RUN_NUMBER="12",
            GITHUB_RUN_ATTEMPT="2",
            GITHUB_REPOSITORY_OWNER="Example",
        )

    def test_pr_and_manual_runs_never_publish(self):
        for event in ("pull_request", "workflow_dispatch"):
            self.env.update(GITHUB_EVENT_NAME=event, GITHUB_REF="refs/heads/main")
            result = metadata(self.env, "1.3.0")
            self.assertEqual(result["publish_images"], "false")
            self.assertEqual(result["publish_chart"], "false")
            self.assertEqual(result["chart_version"], "1.3.0-ci.12.2")

    def test_main_and_tag_publish_images_and_chart(self):
        self.env.update(GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/main")
        result = metadata(self.env, "1.3.0")
        self.assertEqual(
            (result["publish_images"], result["publish_chart"]), ("true", "true")
        )
        self.assertEqual(result["chart_version"], "1.3.0-ci.12.2")
        self.env["GITHUB_REF"] = "refs/tags/v1.3.0"
        result = metadata(self.env, "1.3.0")
        self.assertEqual(
            (result["image_tag"], result["publish_chart"]), ("v1.3.0", "true")
        )
        self.env["GITHUB_REF"] = "refs/tags/v9.0.0"
        with self.assertRaises(ValueError):
            metadata(self.env, "1.3.0")

    def test_parallel_pr_build_and_required_gate(self):
        jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
        self.assertEqual(jobs["pr-images"]["needs"], ["metadata"])
        self.assertEqual(jobs["pr-images"]["if"], "github.event_name == 'pull_request'")
        self.assertIs(jobs["pr-images"]["with"]["publish"], False)
        self.assertEqual(jobs["images"]["needs"], ["metadata", "tests"])
        self.assertEqual(jobs["images"]["if"], "github.event_name != 'pull_request'")
        self.assertEqual(
            set(jobs["chart"]["needs"]), {"metadata", "tests", "images", "pr-images"}
        )
        gate = jobs["required"]
        self.assertEqual(gate["if"], "always()")
        self.assertEqual(set(gate["needs"]), set(jobs) - {"required"})
        script = (
            gate["steps"][0]["run"].split("python - <<'PY'\n", 1)[1].rsplit("PY", 1)[0]
        )
        for event in ("pull_request", "push", "workflow_dispatch"):
            inactive = "images" if event == "pull_request" else "pr-images"
            results = {
                name: {"result": "skipped" if name == inactive else "success"}
                for name in gate["needs"]
            }
            variants = [("all required jobs passed", results, 0)]
            for name in results:
                for status in ("success", "failure", "cancelled", "skipped"):
                    if status == results[name]["result"]:
                        continue
                    changed = copy.deepcopy(results)
                    changed[name]["result"] = status
                    variants.append((f"{name}: {status}", changed, 1))
            for label, candidate, expected in variants:
                with self.subTest(event=event, result=label):
                    result = subprocess.run(
                        [sys.executable, "-c", script],
                        env={
                            **os.environ,
                            "EVENT": event,
                            "RESULTS": json.dumps(candidate),
                        },
                        capture_output=True,
                    )
                    self.assertEqual(result.returncode, expected, result.stderr)

    def test_agent_preparation_overlaps_and_preserves_failures(self):
        steps = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())[
            "jobs"
        ]["agents"]["steps"]
        prepare = next(step for step in steps if step.get("id") == "prepare-agents")
        self.assertEqual(prepare["shell"], "bash")
        # pip cannot finish until Go starts, so sequential preparation would time out.
        stubs = """
        pip() {
          for attempt in {1..500}; do
            if [ -f go-started ]; then return "${PIP_RESULT:-0}"; fi
            sleep 0.01
          done
          return 99
        }
        go() {
          touch go-started
          return "${GO_RESULT:-0}"
        }
        curl() {
          printf 'fixture mcp-grafana_Linux_x86_64.tar.gz\\n' > checksums.txt
          return "${CURL_RESULT:-0}"
        }
        sha256sum() { cat >/dev/null; return "${CHECKSUM_RESULT:-0}"; }
        tar() { return "${TAR_RESULT:-0}"; }
        """
        for failure in (None, "PIP", "GO", "CURL", "CHECKSUM", "TAR"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                env = dict(os.environ)
                for name in ("PIP", "GO", "CURL", "CHECKSUM", "TAR"):
                    env[name + "_RESULT"] = "17" if name == failure else "0"
                result = subprocess.run(
                    [
                        "bash",
                        "--noprofile",
                        "--norc",
                        "-eo",
                        "pipefail",
                        "-c",
                        stubs + prepare["run"],
                    ],
                    cwd=folder,
                    env=env,
                    capture_output=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 17 if failure else 0, result.stderr)

    def test_package_rejects_missing_wrong_or_unpublished_digests(self):
        values = {
            "global": {"imageRegistry": "ghcr.io"},
            "components": {
                "backend": {"image": {"repository": "gpu-ops-advisor-backend"}}
            },
        }
        record = {
            "component": "backend",
            "image": "ghcr.io/example/gpu-ops-advisor-backend:v1.3.0",
            "digest": "sha256:" + "b" * 64,
            "published": "true",
        }
        result = bind_images(
            copy.deepcopy(values), {"backend": record}, "example", "v1.3.0"
        )
        self.assertEqual(
            result["components"]["backend"]["image"]["digest"], record["digest"]
        )
        record["published"] = "false"
        result = bind_images(
            copy.deepcopy(values), {"backend": record}, "example", "v1.3.0"
        )
        self.assertEqual(result["components"]["backend"]["image"]["digest"], "")
        with self.assertRaises(ValueError):
            bind_images(copy.deepcopy(values), {}, "example", "v1.3.0")
        with self.assertRaises(ValueError):
            bind_images(
                copy.deepcopy(values), {"backend": record}, "other-owner", "v1.3.0"
            )
        record["digest"] = ""
        with self.assertRaises(ValueError):
            bind_images(copy.deepcopy(values), {"backend": record}, "example", "v1.3.0")


if __name__ == "__main__":
    unittest.main()
