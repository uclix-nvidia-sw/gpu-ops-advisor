"""Local authoring/retrieval checks; no DB, MCP or LLM calls."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from rcca_agent.retrieval import retrieve_runbooks
from rcca_agent.runbook_contract import (
    compatibility_status,
    schema_kind,
    validate_runbook,
)

ROOT = Path(__file__).resolve().parents[2]
QUERIES = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))[
    "queries"
]
ALLOWED = list(QUERIES)
ROWS = [
    json.loads(path.read_text("utf-8"))
    for path in sorted((ROOT / "rcca-agent/runbooks").rglob("RB-*.json"))
]
XID = next(row for row in ROWS if row["knowledge_key"] == "RB-XID-79")


class RunbookContractTests(unittest.TestCase):
    def test_content_retrieval_plan_and_unbound_runtime(self):
        self.assertEqual(len(ROWS), 267)
        for row in ROWS:
            with self.subTest(key=row["knowledge_key"]):
                self.assertEqual(row["source_refs"], [])
                plan = validate_runbook(row, QUERIES, ALLOWED, authoring=True)
                expected = ["D09", "D02"]
                if row["knowledge_key"] == "RB-XID-48-63-64":
                    expected.append("D03")
                    self.assertEqual(plan[-1]["fact_names"], ["observations"])
                    self.assertIn(
                        "normalized_health", row["content"]["required_evidence"]
                    )
                    self.assertTrue(row["content"]["investigation_only"])
                self.assertEqual([step["query_id"] for step in plan], expected)
                self.assertFalse(plan[-1]["required"])
                if row["knowledge_key"] == "RB-GENERAL-GPU-NODE":
                    self.assertEqual(row["content"]["applicability_conditions"], [])
                    with self.assertRaisesRegex(ValueError, "unbound draft"):
                        validate_runbook(row, QUERIES, ALLOWED)
                    continue
                code = row["content"]["search"]["codes"][0]
                ranked = retrieve_runbooks(ROWS, {"summary": code})
                self.assertEqual(
                    ranked[0]["runbook"]["knowledge_key"], row["knowledge_key"]
                )
                self.assertEqual(ranked[0]["exact_codes"], [code])
                with self.assertRaisesRegex(ValueError, "unbound draft"):
                    validate_runbook(row, QUERIES, ALLOWED)

    def test_bound_plan_is_ordered_and_detached(self):
        row = deepcopy(XID)
        row["compatibility"] = {"producer_contract": "fixture-only-v1"}
        row["content"]["observation_plan"].reverse()
        plan = validate_runbook(row, QUERIES, ALLOWED)
        self.assertEqual([step["query_id"] for step in plan], ["D09", "D02"])
        plan[0]["fact_names"].append("incident_history")
        self.assertNotIn(
            "incident_history", row["content"]["observation_plan"][-1]["fact_names"]
        )

    def test_schema_dispatch_never_silently_accepts_unknown(self):
        self.assertEqual(schema_kind({}), "legacy")
        for schema in (None, "", "gpu-rca-runbook/2.0", 1):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                schema_kind({"schema": schema})

    def test_invalid_content_is_rejected(self):
        cases = [
            (("schema",), "unknown"),
            (("unexpected",), True),
            (("investigation_only",), "yes"),
            (("required_evidence",), ["invented_fact"]),
            (("search", "codes"), ["79"]),
            (("search", "codes"), ["xid:079"]),
            (("applicability_conditions",), []),
            (
                ("applicability_conditions", 0),
                {"field": "error_code", "operator": "eq", "equals": "xid:79"},
            ),
            (("applicability_conditions", 0, "equals"), ["xid:79"]),
            (("required_queries",), ["D02"]),
            (("observation_plan",), None),
            (("observation_plan", 0, "query_id"), "D99"),
            (("observation_plan", 0, "priority"), True),
            (("observation_plan", 0, "required"), "yes"),
            (("observation_plan", 0, "binding"), "arbitrary-datasource"),
            (("observation_plan", 0, "fact_names"), ["invented_fact"]),
            (("recommendations", 0, "execution"), "performed"),
            (("sources", 0, "url"), "https://user:password@example.invalid/doc"),
            (("sources", 0, "checked_at"), "2026-99-99"),
        ]
        for path, value in cases:
            with self.subTest(path=path, value=value):
                row = deepcopy(XID)
                if path == ("applicability_conditions",):
                    row["content"]["investigation_only"] = False
                target = row["content"]
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(ValueError):
                    validate_runbook(row, QUERIES, ALLOWED, authoring=True)

    def test_duplicate_and_required_only_fallback(self):
        row = deepcopy(XID)
        row["content"]["observation_plan"].append(row["content"]["observation_plan"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_runbook(row, QUERIES, ALLOWED, authoring=True)
        del row["content"]["observation_plan"]
        plan = validate_runbook(row, QUERIES, ALLOWED, authoring=True)
        self.assertEqual([step["query_id"] for step in plan], ["D09"])
        self.assertEqual(plan[0]["fact_names"], [])

    def test_compatibility_unknown_and_mismatch(self):
        requirements = {"gpu_model": ["A100", "V100"], "mig_enabled": False}
        cases = [
            ({}, "pending"),
            ({"gpu_model": {"status": "known", "value": "A100"}}, "pending"),
            ({"gpu_model": {"status": "known", "value": "H100"}}, "incompatible"),
            ({"gpu_model": {"status": "unknown", "value": "H100"}}, "pending"),
            (
                {
                    "gpu_model": {"status": "known", "value": "V100"},
                    "mig_enabled": {"status": "known", "value": False},
                },
                "compatible",
            ),
            (
                {
                    "gpu_model": {"status": "known", "value": "V100"},
                    "mig_enabled": {"status": "known", "value": 0},
                },
                "pending",
            ),
        ]
        for facts, expected in cases:
            with self.subTest(facts=facts):
                self.assertEqual(compatibility_status(requirements, facts), expected)
        for requirements in (
            {},
            {"gpu_model": []},
            {"gpu_model": "A*"},
            {"mig_enabled": 0},
            {"unknown": "x"},
        ):
            with self.subTest(requirements=requirements), self.assertRaises(ValueError):
                compatibility_status(requirements, {})


if __name__ == "__main__":
    unittest.main()
