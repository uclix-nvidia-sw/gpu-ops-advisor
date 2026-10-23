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
ALLOWLIST = json.loads((GRAFANA / "rca-alert-allowlist.json").read_text("utf-8"))
RULES = {
    rule["uid"]: (group, rule)
    for group in yaml.safe_load((GRAFANA / "alert-rules.yaml").read_text("utf-8"))[
        "groups"
    ]
    for rule in group["rules"]
}
INCIDENT = json.loads((ROOT / "incident/config.example.json").read_text("utf-8"))

# NVIDIA Xid catalog resolution buckets that ask the operator to act on the device.
ACTION_BUCKETS = {
    "RESET_GPU",
    "RESTART_BM",
    "RESTART_VM",
    "WORKFLOW_XID_48",
    "WORKFLOW_NVLINK_ERR",
    "WORKFLOW_NVLINK5_ERR",
    "CHECK_MECHANICALS",
    "CHECK_UVM",
    "UPDATE_SWFW",
    "XID_154",
}
# GPU Node Triage table 1 (Oct 04, 2026).
TRIAGE_TABLE1 = {13, 31, 45, 48, 61, 62, 63, 64, 74, 79, 92, 94, 95, 123}
# FM User Guide v2.6 table 25: SXID 10003 is fatal to the fabric/system.
FM_TABLE25_FATAL = {10003}
FM_PHRASE = {
    "22": "잠재적 비치명",
    "23": "잠재적 치명",
    "24": "항상 치명",
    "25": "기타 주요",
    None: "FM 가이드 미수록",
}


def entries(kind):
    return [e for e in MANIFEST["entries"] if e["code"].startswith(kind + ":")]


def number(entry):
    return int(entry["code"].split(":")[1])


def raises_rca_alone(entry):
    return entry["fleet_event_type"] in ("Fatal", "Critical")


def code_regex():
    xid = "|".join(str(e["code"]) for e in ALLOWLIST["xid"])
    sxid = "|".join(str(e["code"]) for e in ALLOWLIST["sxid"])
    return f"^(xid:({xid})|sxid:({sxid}))$"


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

    def test_allowlist_is_derived_from_nvidia_guidance(self):
        opt_in = {o["code"] for o in ALLOWLIST["opt_in"]}
        xid = set()
        for entry in entries("xid"):
            if entry["fleet_event_type"] is None or raises_rca_alone(entry):
                continue
            used = "YES" in entry["nvidia_products"].values()
            if (entry["immediate_action"] in ACTION_BUCKETS and used) or number(
                entry
            ) in TRIAGE_TABLE1:
                xid.add(entry["code"])
        sxid = {
            e["code"]
            for e in entries("sxid")
            if not raises_rca_alone(e)
            and (e["fm_sxid_table"] in ("23", "24") or number(e) in FM_TABLE25_FATAL)
        }
        # Opt-in codes must be real candidates so an exclusion never hides a typo.
        self.assertLessEqual(opt_in, xid | sxid)
        listed = {f"xid:{e['code']}" for e in ALLOWLIST["xid"]} | {
            f"sxid:{e['code']}" for e in ALLOWLIST["sxid"]
        }
        self.assertEqual(listed, (xid | sxid) - opt_in)
        by_code = {e["code"]: e for e in MANIFEST["entries"]}
        for kind in ("xid", "sxid"):
            for item in ALLOWLIST[kind]:
                self.assertEqual(
                    item["fleet_event_type"],
                    by_code[f"{kind}:{item['code']}"]["fleet_event_type"],
                )
        self.assertEqual(
            {e["code"] for e in ALLOWLIST["not_emitted_by_fleet"]},
            {e["code"] for e in MANIFEST["entries"] if e["fleet_event_type"] is None},
        )

    def test_event_rules_split_rca_and_notice_by_the_same_allowlist(self):
        _, rca = RULES["gpuops-xid-sxid-rca"]
        _, notice = RULES["gpuops-xid-sxid-notice"]
        regex = code_regex()
        rca_expr = rca["data"][0]["model"]["expr"]
        notice_expr = notice["data"][0]["model"]["expr"]
        self.assertIn(f'event_type=~"Fatal|Critical" or code=~"{regex}"', rca_expr)
        self.assertIn(f'event_type!~"Fatal|Critical" and code!~"{regex}"', notice_expr)
        for expr in (rca_expr, notice_expr):
            self.assertIn('log_type="event"', expr)
            self.assertIn('event_name=~"error_(xid|sxid)"', expr)
        # An unanchored xid pattern would also match inside sxid codes (xid:150 in sxid:15001).
        self.assertTrue(regex.startswith("^(") and regex.endswith(")$"))

    def test_component_rule_covers_exactly_the_component_runbooks(self):
        _, rule = RULES["gpuops-component-rca"]
        expr = rule["data"][0]["model"]["expr"]
        found = re.search(r'component=~"\^\(([^)]*)\)\$"', expr)
        self.assertIsNotNone(found)
        self.assertEqual(
            found.group(1).split("|"),
            sorted(c["component"] for c in MANIFEST["component_entries"]),
        )
        self.assertIn('health="Unhealthy"', expr)
        self.assertIn('log_type="component_data"', expr)

    def test_alert_names_match_incident_analysis_policy(self):
        policies = {p["alertname"] for p in INCIDENT["analysis_policies"]}
        for uid, title in (
            ("gpuops-xid-sxid-rca", "GPUAlert"),
            ("gpuops-component-rca", "GPUAlert"),
            ("gpuops-xid-sxid-notice", "GPUErrorNotice"),
        ):
            group, rule = RULES[uid]
            self.assertEqual(rule["title"], title)
            self.assertEqual(title in policies, title == "GPUAlert")
            self.assertEqual(
                rule["notification_settings"]["receiver"], "${GPU_OPS_CONTACT_POINT}"
            )
            self.assertEqual(rule["data"][0]["datasourceUid"], "${LOKI_DATASOURCE_UID}")
            self.assertEqual(group["folder"], "${GRAFANA_FOLDER}")


if __name__ == "__main__":
    unittest.main()
