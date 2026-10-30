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

    def test_parallel_build_and_required_gate(self):
        jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
        self.assertEqual(jobs["images"]["needs"], "metadata")
        self.assertEqual(jobs["tests"]["needs"], "metadata")
        self.assertEqual(jobs["publish"]["needs"], ["metadata", "tests", "images"])
        self.assertIn("github.event_name == 'push'", jobs["publish"]["if"])
        self.assertNotIn("always()", jobs["publish"]["if"])
        self.assertEqual(
            set(jobs["chart"]["needs"]), {"metadata", "tests", "images", "publish"}
        )
        gate = jobs["required"]
        self.assertEqual(gate["if"], "always()")
        self.assertEqual(set(gate["needs"]), set(jobs) - {"required"})
        script = (
            gate["steps"][0]["run"].split("python - <<'PY'\n", 1)[1].rsplit("PY", 1)[0]
        )
        for images, publish, package in [
            (False, False, False),
            (True, False, False),
            (True, False, True),
            (True, True, True),
        ]:
            results = {name: {"result": "success"} for name in gate["needs"]}
            results["metadata"]["outputs"] = {
                "backend": "true",
                "frontend": "true",
                "images": str(images).lower(),
                "publish-images": str(publish).lower(),
                "package": str(package).lower(),
            }
            for name, run in [
                ("images", images),
                ("publish", publish),
                ("chart", package),
            ]:
                results[name]["result"] = "success" if run else "skipped"
            self.assert_gate(script, results, {})
            broken = copy.deepcopy(results)
            del broken["metadata"]["outputs"]["images"]
            self.assertNotEqual(self.run_gate(script, broken, {}).returncode, 0)

    def run_gate(self, script, results, env):
        return subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, **env, "RESULTS": json.dumps(results)},
            capture_output=True,
        )

    def assert_gate(self, script, results, env):
        self.assertEqual(self.run_gate(script, results, env).returncode, 0)
        for name in results:
            for status in ("success", "failure", "cancelled", "skipped"):
                if status == results[name]["result"]:
                    continue
                changed = copy.deepcopy(results)
                changed[name]["result"] = status
                with self.subTest(job=name, status=status, env=env):
                    self.assertNotEqual(
                        self.run_gate(script, changed, env).returncode, 0
                    )

    def test_planned_test_gate_rejects_unexpected_skips_and_failures(self):
        jobs = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())[
            "jobs"
        ]
        self.assertEqual(jobs["go"]["if"], "inputs.backend")
        self.assertEqual(jobs["agents"]["if"], "inputs.backend")
        self.assertEqual(jobs["frontend"]["if"], "inputs.frontend")
        self.assertNotIn("if", jobs["chart"])
        gate = jobs["required"]
        self.assertEqual(gate["if"], "always()")
        self.assertEqual(set(gate["needs"]), set(jobs) - {"required"})
        script = (
            gate["steps"][0]["run"].split("python - <<'PY'\n", 1)[1].rsplit("PY", 1)[0]
        )
        for backend, frontend in [(True, True), (False, True), (False, False)]:
            env = {"BACKEND": str(backend).lower(), "FRONTEND": str(frontend).lower()}
            results = {
                name: {"result": "success" if run else "skipped"}
                for name, run in [
                    ("go", backend),
                    ("agents", backend),
                    ("frontend", frontend),
                    ("chart", True),
                ]
            }
            self.assert_gate(script, results, env)

    def test_build_has_no_registry_write_and_publication_never_rebuilds(self):
        build = yaml.safe_load(
            (ROOT / ".github/workflows/container-images.yml").read_text()
        )
        self.assertEqual(build["permissions"], {"contents": "read"})
        steps = build["jobs"]["build"]["steps"]
        self.assertFalse(
            any(s.get("uses", "").startswith("docker/login") for s in steps)
        )
        image = next(s for s in steps if s.get("id") == "image")
        self.assertIs(image["with"]["push"], False)
        self.assertIn("type=docker", image["with"]["outputs"])
        publish = yaml.safe_load(
            (ROOT / ".github/workflows/publish-images.yml").read_text()
        )
        steps = publish["jobs"]["publish"]["steps"]
        self.assertFalse(any("build-push" in s.get("uses", "") for s in steps))
        verify = next(
            s for s in steps if s.get("name") == "Load and verify current-run image"
        )["run"]
        self.assertIn('test "$revision" = "$GITHUB_SHA"', verify)
        self.assertIn("docker load", verify)
        self.assertLess(
            next(
                i
                for i, s in enumerate(steps)
                if s.get("name") == "Load and verify current-run image"
            ),
            next(
                i
                for i, s in enumerate(steps)
                if s.get("uses", "").startswith("docker/login")
            ),
        )

    def test_export_and_import_reject_wrong_commit_or_load_failure(self):
        build = yaml.safe_load(
            (ROOT / ".github/workflows/container-images.yml").read_text()
        )["jobs"]["build"]["steps"]
        publish = yaml.safe_load(
            (ROOT / ".github/workflows/publish-images.yml").read_text()
        )["jobs"]["publish"]["steps"]
        for steps, name in [
            (build, "Verify exported image can be loaded"),
            (publish, "Load and verify current-run image"),
        ]:
            script = next(s for s in steps if s.get("name") == name)["run"]
            for bad in ("", "load", "revision"):
                stub = 'docker() { if [ "$1" = load ]; then return "${LOAD_STATUS:-0}"; else printf "%s\\n" "$REVISION"; fi; }\n'
                result = subprocess.run(
                    [
                        "bash",
                        "--noprofile",
                        "--norc",
                        "-eo",
                        "pipefail",
                        "-c",
                        stub + script,
                    ],
                    env={
                        **os.environ,
                        "IMAGE": "example:tag",
                        "GITHUB_SHA": "a" * 40,
                        "REVISION": "b" * 40 if bad == "revision" else "a" * 40,
                        "LOAD_STATUS": "17" if bad == "load" else "0",
                    },
                    capture_output=True,
                )
                self.assertEqual(result.returncode == 0, not bad, result.stderr)

    def test_publication_script_preserves_push_failure_and_requires_registry_digest(
        self,
    ):
        steps = yaml.safe_load(
            (ROOT / ".github/workflows/publish-images.yml").read_text()
        )["jobs"]["publish"]["steps"]
        script = next(
            s
            for s in steps
            if s.get("name") == "Publish without rebuilding and record registry digest"
        )["run"]
        image = "ghcr.io/example/frontend:sha-test"
        valid = "ghcr.io/example/frontend@sha256:" + "b" * 64
        for bad, digests in [
            ("", [valid]),
            ("push", [valid]),
            ("missing", []),
            ("other", ["ghcr.io/other/frontend@sha256:" + "b" * 64]),
            ("ambiguous", [valid, "ghcr.io/example/frontend@sha256:" + "c" * 64]),
        ]:
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as folder:
                stub = """docker() {
                  if [ "$1" = push ]; then return "$PUSH_STATUS"; fi
                  printf '%s\\n' "$INSPECT_JSON"
                }
                python() { "$PYTHON_EXE" "$@"; }
                """
                result = subprocess.run(
                    [
                        "bash",
                        "--noprofile",
                        "--norc",
                        "-eo",
                        "pipefail",
                        "-c",
                        stub + script,
                    ],
                    cwd=folder,
                    env={
                        **os.environ,
                        "IMAGE": image,
                        "COMPONENT": "frontend",
                        "PYTHON_EXE": sys.executable.replace("\\", "/"),
                        "PUSH_STATUS": "17" if bad == "push" else "0",
                        "INSPECT_JSON": json.dumps([{"RepoDigests": digests}]),
                    },
                    capture_output=True,
                )
                self.assertEqual(result.returncode == 0, not bad, result.stderr)
                record = Path(folder) / "dist/images/frontend.json"
                if not bad:
                    self.assertEqual(
                        json.loads(record.read_text())["digest"], "sha256:" + "b" * 64
                    )
                else:
                    self.assertFalse(record.exists())

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
