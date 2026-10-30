"""The frontend incident labels are generated from the authored Runbooks."""

import json
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[3]
GENERATOR = runpy.run_path(str(ROOT / "tools/generate_incident_labels.py"))


class IncidentLabelsTest(unittest.TestCase):
    def test_sxid_nonfatal_exceptions_preserve_workload_impact(self):
        labels = GENERATOR["build"]()
        self.assertIn("자동 정정", labels["sxid:11021"]["action"])
        self.assertIn("작업 중단", labels["sxid:11004"]["action"])
        self.assertIn("성능 저하", labels["sxid:20001"]["action"])
        self.assertIn("별도 조치 불필요", labels["sxid:22013"]["action"])
        self.assertIn("오류 포트", labels["sxid:11019"]["action"])
        self.assertIn("전체 GPU 연결망", labels["sxid:23017"]["action"])

    def test_xid173_official_identity_and_c2c_checks_are_distinct_from_recovery(self):
        row = json.loads(
            (ROOT / "rcca-agent/runbooks/xid/RB-XID-173.json").read_text("utf-8")
        )
        content = row["content"]
        definition = GENERATOR["build"]()["xid:173"]["official"]
        self.assertIn(
            "/NVIDIA/open-gpu-kernel-modules/blob/ca2d03e6", definition["source"]
        )
        self.assertIn("치명적 오류", definition["meaning"])
        self.assertNotIn("소스에만", definition["meaning"])
        self.assertIn(
            "nvidia-smi c2c -i", content["operator_guidance"]["next_checks"][0]["text"]
        )
        self.assertIn(
            "카운터가 초기화", content["operator_guidance"]["next_checks"][4]["text"]
        )
        self.assertIn(
            "일괄 재부팅 명령으로 해석하지",
            content["operator_guidance"]["next_checks"][3]["text"],
        )
        self.assertEqual(content["search"]["aliases"], ["C2C Fatal Link Failure"])
        self.assertTrue(content["investigation_only"])

    def test_entire_official_unused_set_and_exceptions(self):
        # NVIDIA Xid catalog Table 1, checked 2026-10-30. Keep independent
        # of manifest classification so accidentally omitted codes fail here.
        codes = {
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            9,
            10,
            12,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            26,
            27,
            28,
            29,
            30,
            33,
            34,
            35,
            36,
            42,
            47,
            49,
            50,
            51,
            52,
            53,
            55,
            56,
            57,
            58,
            59,
            61,
            65,
            73,
            81,
            87,
            90,
            91,
            108,
            111,
            112,
            113,
            114,
            115,
            116,
            117,
            118,
            122,
            123,
            124,
            125,
            138,
        }
        labels = GENERATOR["build"]()
        self.assertEqual(len(codes), 63)
        for code in codes:
            definition = labels[f"xid:{code}"]["official"]
            self.assertIn("미사용(Unused)", definition["meaning"])
            self.assertNotIn("Unused", definition["name"])
        self.assertIn("시험용 오류", labels["xid:14"]["official"]["name"])
        self.assertIn("XID 137", labels["xid:108"]["official"]["meaning"])
        for code in codes - {14, 108}:
            self.assertIn(
                "적용하지 않는 코드", labels[f"xid:{code}"]["official"]["meaning"]
            )

    def test_actions_describe_checks_instead_of_internal_workflows(self):
        labels = GENERATOR["build"]()
        for label in labels.values():
            self.assertNotIn("런북 순서대로 확인", label["action"])
            self.assertNotIn("WORKFLOW_", label["action"])
        self.assertIn("DRAM", labels["xid:171"]["action"])
        self.assertIn("SRAM", labels["xid:172"]["action"])
        self.assertIn("세부 오류값", labels["xid:146"]["action"])

    def test_all_pinned_reserved_codes_have_official_operator_definitions(self):
        import re

        catalog = (
            ROOT / "docs/specs/rca-agent/references/fleet-gpud-error-catalog.md"
        ).read_text("utf-8")
        codes = set(re.findall(r"^\| (\d+) \| Reserved \|", catalog, re.M))
        labels = GENERATOR["build"]()
        self.assertEqual(len(codes), 17)
        for code in codes:
            definition = labels[f"xid:{code}"]["official"]
            self.assertNotIn("Reserved", definition["name"])
            self.assertNotIn("Reserved", definition["meaning"])
            self.assertIn("docs.nvidia.com", definition["source"])

    def test_collector_unused_names_do_not_hide_copy_engine_errors(self):
        import re

        catalog = (
            ROOT / "docs/specs/rca-agent/references/fleet-gpud-error-catalog.md"
        ).read_text("utf-8")
        codes = set(re.findall(r"^\| (\d+) \| Unused \|", catalog, re.M))
        labels = GENERATOR["build"]()
        self.assertEqual(len(codes), 15)
        for code in codes:
            self.assertIn("official", labels[f"xid:{code}"])
        for code in (39, 40, 41):
            definition = labels[f"xid:{code}"]["official"]
            self.assertIn(f"CE{code - 39}", definition["name"])
            self.assertNotIn("미사용", definition["meaning"])

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
        self.assertTrue(labels["sxid:11001"]["action"].startswith("치명 가능"))
        self.assertIn("component:disk", labels)
        for code, label in labels.items():
            with self.subTest(code=code):
                self.assertTrue(label["name"] and label["action"] and label["steps"])
                self.assertNotIn("런북 판단", label["action"])
                self.assertFalse(
                    any(s.startswith("알림이 가리키는") for s in label["steps"])
                )


if __name__ == "__main__":
    unittest.main()
