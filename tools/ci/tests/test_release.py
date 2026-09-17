import copy
import importlib.util
from pathlib import Path
import unittest

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
