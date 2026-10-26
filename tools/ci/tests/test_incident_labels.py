"""The frontend incident labels are generated from the authored Runbooks."""

import json
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[3]
GENERATOR = runpy.run_path(str(ROOT / "tools/generate_incident_labels.py"))


class IncidentLabelsTest(unittest.TestCase):
    def test_generated_file_is_current(self):
        committed = json.loads(
            (ROOT / "frontend/src/lib/incidentLabels.json").read_text("utf-8")
        )
        self.assertEqual(
            committed,
            GENERATOR["build"](),
            "run python tools/generate_incident_labels.py",
        )

    def test_operator_facing_fields(self):
        labels = GENERATOR["build"]()
        self.assertEqual(labels["xid:79"]["action"], "호스트 재시작 (RESTART_BM)")
        self.assertTrue(labels["sxid:11001"]["action"].startswith("치명 가능 SXID"))
        self.assertIn("component:disk", labels)
        for code, label in labels.items():
            with self.subTest(code=code):
                self.assertTrue(label["name"] and label["action"] and label["steps"])
                self.assertFalse(
                    any(s.startswith("알림이 가리키는") for s in label["steps"])
                )


if __name__ == "__main__":
    unittest.main()
