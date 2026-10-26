"""Grafana alert rule definitions stay aligned with the runbook catalog and Incident policy."""

import json
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
BOOKS = ROOT / "rcca-agent/runbooks"
GRAFANA = ROOT / "incident/grafana"
MANIFEST = json.loads((BOOKS / "catalog-manifest.json").read_text("utf-8"))
RULES = {
    rule["uid"]: (group, rule)
    for group in yaml.safe_load((GRAFANA / "alert-rules.yaml").read_text("utf-8"))[
        "groups"
    ]
    for rule in group["rules"]
}
INCIDENT = json.loads((ROOT / "incident/config.example.json").read_text("utf-8"))

FM_PHRASE = {
    "22": "잠재적 비치명",
    "23": "잠재적 치명",
    "24": "항상 치명",
    "25": "기타 주요",
    None: "FM 가이드 미수록",
}


def entries(kind):
    return [e for e in MANIFEST["entries"] if e["code"].startswith(kind + ":")]


class AlertRuleCatalogTests(unittest.TestCase):
    def test_manifest_fleet_and_fm_fields_match_runbook_text(self):
        for entry in entries("xid") + entries("sxid"):
            content = json.loads((BOOKS / entry["file"]).read_text("utf-8"))["content"]
            line = next(
                (
                    a
                    for a in content["analysis_guidance"]
                    if a.startswith("Fleet 고정 카탈로그:")
                ),
                None,
            )
            text = line or json.dumps(content["operator_guidance"], ensure_ascii=False)
            found = re.search(r"event_type=(\w+)", text)
            self.assertEqual(
                entry["fleet_event_type"], found and found.group(1), entry["code"]
            )
            if entry["code"].startswith("sxid:"):
                meaning = content["operator_guidance"]["meaning"]
                self.assertIn(
                    f"Fabric Manager 가이드 분류는 {FM_PHRASE[entry['fm_sxid_table']]}",
                    meaning,
                    entry["code"],
                )

    def test_state_rule_raises_fatal_and_critical_from_repeating_state_lines(self):
        # Event lines are written once and can be lost (SetHealthy purges unexported
        # events), so codes that change the component state must alert from state lines.
        _, rule = RULES["gpuops-xid-sxid-state"]
        expr = rule["data"][0]["model"]["expr"]
        self.assertIn('log_type="component_data"', expr)
        # Fleet maps Fatal to Unhealthy and Critical to Degraded.
        self.assertIn('health=~"Unhealthy|Degraded"', expr)
        self.assertIn('component=~"accelerator-nvidia-error-(xid|sxid)"', expr)

    def test_event_rule_takes_every_code_the_state_rule_does_not(self):
        _, rule = RULES["gpuops-xid-sxid-rca"]
        expr = rule["data"][0]["model"]["expr"]
        # Fatal/Critical stay with the state rule; repeating them here would open a
        # second incident and RCA for the same error. Every other code has a Runbook.
        self.assertRegex(expr, r'\| event_type!~"Fatal\|Critical"\s*\[10m\]')
        self.assertNotIn("code=~", expr)
        self.assertIn('log_type="event"', expr)
        self.assertIn('event_name=~"error_(xid|sxid)"', expr)
        # Fleet exports events on an interval; a short window misses late lines.
        self.assertIn("[10m]", expr)
        self.assertEqual(rule["data"][0]["relativeTimeRange"]["from"], 600)

    def test_component_rule_leaves_xid_and_sxid_to_their_rules(self):
        _, rule = RULES["gpuops-component-rca"]
        expr = rule["data"][0]["model"]["expr"]
        # Components without their own Runbook fall back to RB-GENERAL-GPU-NODE.
        self.assertIn('component!~"accelerator-nvidia-error-(xid|sxid)"', expr)
        self.assertNotIn("component=~", expr)
        self.assertIn('health="Unhealthy"', expr)
        self.assertIn('log_type="component_data"', expr)

    def test_every_rule_raises_gpualert_for_the_incident_analysis_policy(self):
        policies = {p["alertname"] for p in INCIDENT["analysis_policies"]}
        self.assertIn("GPUAlert", policies)
        self.assertEqual(
            set(RULES),
            {"gpuops-xid-sxid-state", "gpuops-xid-sxid-rca", "gpuops-component-rca"},
        )
        for group, rule in RULES.values():
            self.assertEqual(rule["title"], "GPUAlert")
            # A failed Loki query keeps the last state instead of opening an incident.
            self.assertEqual(rule["execErrState"], "KeepLast")
            self.assertEqual(
                rule["notification_settings"]["receiver"], "${GPU_OPS_CONTACT_POINT}"
            )
            self.assertEqual(rule["data"][0]["datasourceUid"], "${LOKI_DATASOURCE_UID}")
            self.assertEqual(group["folder"], "${GRAFANA_FOLDER}")


if __name__ == "__main__":
    unittest.main()
