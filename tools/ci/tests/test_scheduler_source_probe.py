import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "scheduler_source_probe.py"
SPEC = importlib.util.spec_from_file_location("probe", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProbeTests(unittest.TestCase):
    def test_only_allowed_settings_leave_process(self):
        pods = {
            "items": [
                {
                    "metadata": {"name": "scheduler"},
                    "spec": {
                        "nodeName": "control-plane",
                        "hostNetwork": True,
                        "containers": [
                            {
                                "image": "scheduler:test",
                                "command": ["scheduler", "--bind-address=127.0.0.1"],
                                "args": [
                                    "--secure-port",
                                    "10259",
                                    "--token=PRIVATE",
                                    "--kubeconfig=/private/path",
                                ],
                                "env": [{"name": "TOKEN", "value": "PRIVATE"}],
                            }
                        ],
                    },
                }
            ]
        }
        result = MODULE.selected_settings(pods)
        self.assertEqual(
            result[0]["explicit_settings"],
            {"bind-address": "127.0.0.1", "secure-port": "10259"},
        )
        self.assertNotIn("PRIVATE", str(result))
        self.assertNotIn("private/path", str(result))

    def test_absent_flags_are_not_claimed_as_effective_defaults(self):
        result = MODULE.selected_settings(
            {"items": [{"spec": {"containers": [{"image": "scheduler:test"}]}}]}
        )
        self.assertEqual(result[0]["explicit_settings"], {})

    def test_missing_value_does_not_expose_following_argument(self):
        result = MODULE.selected_settings(
            {
                "items": [
                    {
                        "spec": {
                            "containers": [
                                {"args": ["--secure-port", "--token=PRIVATE"]}
                            ]
                        }
                    }
                ]
            }
        )
        self.assertEqual(result[0]["explicit_settings"], {"secure-port": None})
        self.assertNotIn("PRIVATE", str(result))


if __name__ == "__main__":
    unittest.main()
