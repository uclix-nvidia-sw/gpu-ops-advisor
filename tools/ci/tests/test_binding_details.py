"""Read-only diagnostic regressions; no Kubernetes or network access."""

import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "binding_details", Path(__file__).resolve().parents[1] / "binding_details.py"
)
details = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(details)


def pod(image, env):
    return {
        "metadata": {"name": "fixture"},
        "status": {"phase": "Running"},
        "spec": {"containers": [{"name": "fixture", "image": image, "env": env}]},
    }


class BindingDetailsTests(unittest.TestCase):
    def test_partial_pod_failure_retains_other_results(self):
        def run(args):
            if args[1] == "configmap":
                return json.dumps({"data": {"config.alloy": 'scrape_interval = "15s"'}})
            if "gpu-operator" in args:
                raise details.ReadFailure("forbidden")
            return json.dumps(
                {
                    "items": [
                        pod(
                            "example/fleet-intelligence-agent:1",
                            [
                                {"name": "FLEETINT_COLLECT_INTERVAL", "value": "1m"},
                                {"name": "PASSWORD", "value": "DO_NOT_EMIT"},
                            ],
                        )
                    ]
                }
            )

        with patch.object(details, "run", side_effect=run):
            result = details.main("cpc-2")
        self.assertEqual(result["collection_status"], "partial")
        self.assertEqual(
            result["errors"][0], {"stage": "pods:gpu-operator", "status": "forbidden"}
        )
        self.assertEqual(
            result["fleet_intervals"][0]["explicit_interval_env"],
            {"FLEETINT_COLLECT_INTERVAL": "1m"},
        )
        self.assertEqual(
            result["configmaps"][0]["selected_settings"][0]["value"], "15s"
        )
        self.assertNotIn("DO_NOT_EMIT", json.dumps(result))

    def test_distroless_read_failure_has_no_mutating_fallback(self):
        calls = []

        def run(args):
            calls.append(args)
            if args[0] == "exec":
                self.assertEqual(
                    args[-3:],
                    ["--", "cat", "/etc/dcgm-exporter/dcp-metrics-included.csv"],
                )
                raise details.ReadFailure("executable_not_found")
            if args[1] == "configmap":
                return json.dumps({"data": {}})
            rows = (
                [
                    pod(
                        "example/dcgm-exporter:distroless",
                        [
                            {
                                "name": "DCGM_EXPORTER_COLLECTORS",
                                "value": "/etc/dcgm-exporter/dcp-metrics-included.csv",
                            }
                        ],
                    )
                ]
                if "gpu-operator" in args
                else []
            )
            return json.dumps({"items": rows})

        with patch.object(details, "run", side_effect=run):
            result = details.main("cpc-2")
        self.assertEqual(
            result["exporter_csv"][0]["read_error"], "executable_not_found"
        )
        self.assertEqual(sum(a[0] == "exec" for a in calls), 1)
        self.assertTrue(all(a[0] in ("get", "exec") for a in calls))
        self.assertTrue(
            any(e["stage"] == "exporter_csv:replica-1" for e in result["errors"])
        )

    def test_settings_do_not_export_secrets_or_infer_absent_values(self):
        text = 'retention_period: 720h0m0s\nmax_query_lookback: "30d"\npassword: DO_NOT_EMIT\nretention_enabled: true\n'
        self.assertEqual(
            [r["value"] for r in details.settings(text)], ["720h0m0s", "30d", "true"]
        )
        self.assertEqual(
            details.settings("retention_period: ${ENV}\npassword: DO_NOT_EMIT"), []
        )

    def test_csv_uses_declared_types(self):
        result = details.csv_summary(
            "DCGM_FI_PROF_PCIE_RX_BYTES, gauge, bytes/sec\nDCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION, counter, mJ\n"
        )
        self.assertEqual(
            [f["type"] for f in result["active_fields"]], ["gauge", "counter"]
        )
        self.assertEqual(
            details.csv_summary("# only comments")["status"], "no_fields_parsed"
        )

    def test_kubectl_diagnostics_are_classified_without_echo(self):
        for stderr, code in [
            ("Forbidden PRIVATE", "forbidden"),
            ("Unauthorized PRIVATE", "authentication_required"),
            ("connection refused PRIVATE", "connection_refused"),
            ("executable file not found PRIVATE", "executable_not_found"),
            ("PRIVATE", "read_failed"),
        ]:
            with (
                self.subTest(code=code),
                patch.object(
                    details.subprocess,
                    "run",
                    return_value=CompletedProcess([], 1, "", stderr),
                ),
            ):
                with self.assertRaises(details.ReadFailure) as caught:
                    details.run(["get", "pods"])
                self.assertEqual(str(caught.exception), code)
        for error, code in [
            (FileNotFoundError(), "kubectl_not_found"),
            (TimeoutExpired("kubectl", 30), "timeout"),
        ]:
            with patch.object(details.subprocess, "run", side_effect=error):
                with self.assertRaises(details.ReadFailure) as caught:
                    details.run(["get", "pods"])
                self.assertEqual(str(caught.exception), code)

    def test_malformed_response_remains_unverified(self):
        for payload in ["PRIVATE", "[]", "{}"]:
            errors = []
            with patch.object(details, "run", return_value=payload):
                self.assertIsNone(
                    details.read_json(["get", "pods"], errors, "pods:fixture")
                )
            self.assertEqual(
                errors, [{"stage": "pods:fixture", "status": "invalid_json"}]
            )

    def test_central_empty_settings_do_not_mean_unlimited_retention(self):
        with patch.object(
            details,
            "run",
            return_value=json.dumps({"data": {"config.yaml": "auth_enabled: true"}}),
        ):
            result = details.main("advisor-central")
        self.assertEqual(result["collection_status"], "completed")
        self.assertEqual(len(result["configmaps"]), 4)
        self.assertTrue(all(c["selected_settings"] == [] for c in result["configmaps"]))
        self.assertTrue(all("unverified" in c["scope"] for c in result["configmaps"]))


class EffectiveConfigTests(unittest.TestCase):
    def test_excerpt_redacts_credentials_and_tenant_names(self):
        raw = "limits:\n  compactor_blocks_retention_period: 720h\noverrides:\n  private-tenant:\n    retention_period: 48h\n    password: secret-value\n"
        out = details.config_excerpt(raw)
        self.assertEqual(
            [x["value"] for x in out["selected_settings"]], ["720h", "48h"]
        )
        self.assertEqual(out["selected_settings"][1]["parents"][0], "overrides")
        self.assertNotIn("private-tenant", json.dumps(out))
        self.assertNotIn("secret-value", json.dumps(out))
        self.assertFalse(out["empty_overrides_mapping_present"])

    def test_empty_overrides_and_unsupported_inline_are_distinct(self):
        self.assertTrue(
            details.config_excerpt("overrides: {}\n")["empty_overrides_mapping_present"]
        )
        out = details.config_excerpt("limits: {retention_period: 24h}\n")
        self.assertEqual(out["selected_settings"], [])
        self.assertIn("Lexical", out["scope"])

    def test_runtime_failure_preserves_live_base_config(self):
        def run(args):
            if args[1] == "pods":
                product = "mimir" if "mimir-test" in args else "loki"
                item = pod("grafana/" + product + ":1", [])
                item["spec"]["containers"][0]["ports"] = [
                    {"name": "http-metrics", "containerPort": 8080}
                ]
                return json.dumps({"items": [item]})
            self.assertEqual(args[:2], ["get", "--raw"])
            if args[-1].endswith("/runtime_config"):
                raise details.ReadFailure("forbidden")
            return "limits_config:\n  retention_period: 720h\n"

        with patch.object(details, "run", side_effect=run):
            out = details.effective_config()
        self.assertEqual(out["collection_status"], "partial")
        self.assertEqual(len(out["errors"]), 2)
        self.assertEqual(sum(x["status"] == "read" for x in out["endpoints"]), 2)

    def test_ambiguous_port_does_not_probe(self):
        item = pod("grafana/loki:1", [])
        with patch.object(
            details, "run", return_value=json.dumps({"items": [item]})
        ) as run:
            out = details.effective_config()
        self.assertEqual(len(out["endpoints"]), 0)
        self.assertTrue(out["errors"])
        self.assertTrue(all(call.args[0][1] == "pods" for call in run.call_args_list))


if __name__ == "__main__":
    unittest.main()
