import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "extend_observation_forwarding.py"
SPEC = importlib.util.spec_from_file_location("forwarding", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ForwardingTests(unittest.TestCase):
    def test_only_metric_keep_changes_and_retry_is_idempotent(self):
        config = (
            'prometheus.relabel "gpuops_direct" {\n  rule {\n'
            '    source_labels = ["__name__"]\n'
            f'    regex = "{MODULE.BASE}"\n    action = "keep"\n  }}\n'
            '  rule { target_label = "cluster_id" replacement = "arbitrary-site" }\n}\n'
        )
        expanded = MODULE.extend(config)
        self.assertEqual(
            expanded.replace(
                MODULE.BASE + "|" + "|".join(MODULE.ADDITIONS), MODULE.BASE
            ),
            config,
        )
        self.assertEqual(MODULE.extend(expanded), expanded)

    def test_ambiguous_or_modified_rules_are_not_overwritten(self):
        rule = f'source_labels = ["__name__"]\nregex = "{MODULE.BASE}"\naction = "keep"'
        for config in (
            "",
            rule + "\n" + rule,
            rule.replace('"keep"', '"drop"'),
            rule.replace(MODULE.BASE, "up"),
        ):
            with self.assertRaises(ValueError):
                MODULE.extend(config)
