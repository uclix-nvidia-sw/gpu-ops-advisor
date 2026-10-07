#!/usr/bin/env python3
"""Read-only follow-up: selected configuration facts, never Secret objects.

Uses kubectl get pods/configmap. In source clusters only, also attempts
kubectl exec cat on the exporter CSV explicitly configured in the Pod.
No shell, writes, deployments, containers or debug pods are created.
Raw configuration, URLs, credentials, device identities and logs are not printed.
Missing output is unverified, never an inferred default.
"""

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
from datetime import datetime, timezone

KEYS = {
    "scrape_interval",
    "scrape_timeout",
    "collection_interval",
    "compactor_blocks_retention_period",
    "retention_period",
    "retention_enabled",
    "max_query_lookback",
    "query_ingesters_within",
    "max_query_length",
}
DURATION = re.compile(
    r"(?:[0-9]+(?:\.[0-9]+)?(?:ns|us|µs|ms|s|m|h|d|w|y))+|[0-9]+|true|false"
)
FLEET_ENV = {"FLEETINT_COLLECT_INTERVAL", "FLEETINT_CHECK_INTERVAL"}


class ReadFailure(Exception):
    """Expose only a bounded diagnostic code, never server diagnostics."""


def run(args):
    try:
        p = subprocess.run(
            ["kubectl", "--request-timeout=20s", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise ReadFailure("kubectl_not_found") from None
    except subprocess.TimeoutExpired:
        raise ReadFailure("timeout") from None
    if p.returncode:
        # These classify a reported error; they do not establish its root cause.
        diagnostic = p.stderr.lower()
        if "forbidden" in diagnostic:
            reason = "forbidden"
        elif "unauthorized" in diagnostic or "must be logged in" in diagnostic:
            reason = "authentication_required"
        elif "connection refused" in diagnostic:
            reason = "connection_refused"
        elif "executable file not found" in diagnostic:
            reason = "executable_not_found"
        else:
            reason = "read_failed"
        raise ReadFailure(reason)
    return p.stdout


def read_json(args, errors, stage):
    try:
        result = json.loads(run(args))
        if not isinstance(result, dict) or (
            args[1] == "pods" and not isinstance(result.get("items"), list)
        ):
            raise ValueError("invalid shape")
        return result
    except (ReadFailure, ValueError) as exc:
        errors.append(
            {
                "stage": stage,
                "status": str(exc) if isinstance(exc, ReadFailure) else "invalid_json",
            }
        )
        return None


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def settings(text):
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        m = re.fullmatch(
            r'\s*([a-z_]+)\s*[:=]\s*["\x27]?([^"\x27#]+?)["\x27]?\s*,?\s*(?:#.*)?', line
        )
        if m and m[1] in KEYS and DURATION.fullmatch(m[2].strip()):
            out.append({"line": number, "setting": m[1], "value": m[2].strip()})
    return out


def csv_summary(text):
    fields = []
    for row in csv.reader(io.StringIO(text)):
        if (
            len(row) >= 2
            and re.fullmatch(r"DCGM_[A-Z0-9_]+", row[0].strip())
            and row[1].strip() in {"gauge", "counter", "label"}
        ):
            fields.append({"field": row[0].strip(), "type": row[1].strip()})
    return {
        "sha256": digest(text),
        "active_fields": fields,
        "status": "parsed" if fields else "no_fields_parsed",
    }


def main(environment):
    out = {
        "schema_version": "binding-details/2",
        "environment": environment,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Selected configured facts; not proof of effective runtime settings or activation",
        "configmaps": [],
        "exporter_csv": [],
        "fleet_intervals": [],
        "errors": [],
    }
    refs = (
        [("alloy", "alloy")]
        if environment != "advisor-central"
        else [
            ("loki", "loki"),
            ("loki", "loki-runtime"),
            ("mimir-test", "mimir-config"),
            ("mimir-test", "mimir-runtime"),
        ]
    )
    for ns, name in refs:
        cm = read_json(
            ["get", "configmap", name, "-n", ns, "-o", "json"],
            out["errors"],
            f"configmap:{ns}/{name}",
        )
        if cm is not None:
            for key, text in cm.get("data", {}).items():
                out["configmaps"].append(
                    {
                        "namespace": ns,
                        "name": name,
                        "key": key,
                        "sha256": digest(text),
                        "selected_settings": settings(text),
                        "setting_names_present": sorted(
                            k
                            for k in KEYS
                            if re.search(r"\b" + re.escape(k) + r"\b", text)
                        ),
                        "scope": "Matching scalar lines only; tenant precedence and effective config unverified",
                    }
                )
    if environment != "advisor-central":
        response = read_json(
            ["get", "pods", "-n", "gpu-operator", "-o", "json"],
            out["errors"],
            "pods:gpu-operator",
        )
        pods = response.get("items", []) if isinstance(response, dict) else []
        index = 0
        for pod in pods:
            for c in pod["spec"].get("containers", []):
                if (
                    "/dcgm-exporter:" not in c["image"]
                    or pod.get("status", {}).get("phase") != "Running"
                ):
                    continue
                index += 1
                record = {"replica": index, "image": c["image"]}
                env = {e["name"]: e.get("value") for e in c.get("env", [])}
                path = env.get("DCGM_EXPORTER_COLLECTORS")
                # Fixed path from the supplied preflight; do not read arbitrary files.
                if path != "/etc/dcgm-exporter/dcp-metrics-included.csv":
                    record["status"] = "path_unverified"
                elif any(
                    a == "-f" or a.startswith("-f=") or a.startswith("--collectors")
                    for a in c.get("command", []) + c.get("args", [])
                ):
                    record["status"] = "command_override_requires_review"
                else:
                    try:
                        text = run(
                            [
                                "exec",
                                "-n",
                                "gpu-operator",
                                pod["metadata"]["name"],
                                "-c",
                                c["name"],
                                "--",
                                "cat",
                                path,
                            ]
                        )
                        record.update(csv_summary(text))
                    except ReadFailure as exc:
                        record["status"] = (
                            "unreadable_or_cat_unavailable_no_fallback_executed"
                        )
                        record["read_error"] = str(exc)
                out["exporter_csv"].append(record)
                if record["status"] != "parsed":
                    out["errors"].append(
                        {
                            "stage": f"exporter_csv:replica-{index}",
                            "status": record.get("read_error", record["status"]),
                        }
                    )
        response = read_json(
            ["get", "pods", "-n", "fleet-intelligence", "-o", "json"],
            out["errors"],
            "pods:fleet-intelligence",
        )
        pods = response.get("items", []) if isinstance(response, dict) else []
        for pod in pods:
            for c in pod["spec"].get("containers", []):
                if "/fleet-intelligence-agent:" not in c["image"]:
                    continue
                values = {}
                for e in c.get("env", []):
                    if e["name"] in FLEET_ENV:
                        value = e.get("value", "")
                        values[e["name"]] = (
                            value
                            if DURATION.fullmatch(value)
                            else "reference_or_unparsed"
                        )
                out["fleet_intervals"].append(
                    {
                        "replica": len(out["fleet_intervals"]) + 1,
                        "explicit_interval_env": values,
                        "env_from_present": bool(c.get("envFrom")),
                        "scope": "No default or effective cadence inferred when absent",
                    }
                )
        for section in ("exporter_csv", "fleet_intervals"):
            if not out[section]:
                out["errors"].append(
                    {"stage": section, "status": "no_matching_containers"}
                )
    out["collection_status"] = "partial" if out["errors"] else "completed"
    return out


def effective_config():
    """Read live service config through the existing Kubernetes API credentials.

    Output is a lexical allowlist, not a YAML evaluator or tenant resolver.
    Unknown parent keys are hashed; raw config and error text never leave memory.
    """
    out = {
        "schema_version": "binding-effective-config/1",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Live endpoint excerpts; tenant precedence requires review",
        "endpoints": [],
        "errors": [],
    }
    for namespace, product in (("mimir-test", "mimir"), ("loki", "loki")):
        response = read_json(
            ["get", "pods", "-n", namespace, "-o", "json"],
            out["errors"],
            f"pods:{namespace}",
        )
        pods = response.get("items", []) if response else []
        targets = []
        for pod in pods:
            if pod.get("status", {}).get("phase") != "Running":
                continue
            for container in pod.get("spec", {}).get("containers", []):
                if not re.search(
                    r"/" + product + r"(?::|@)", container.get("image", "")
                ):
                    continue
                ports = {
                    port["containerPort"]
                    for port in container.get("ports", [])
                    if port.get("name") in {"http", "http-metrics"}
                    and isinstance(port.get("containerPort"), int)
                    and 0 < port["containerPort"] < 65536
                }
                if len(ports) != 1:
                    out["errors"].append(
                        {"stage": product, "status": "ambiguous_http_port"}
                    )
                    continue
                targets.append((pod["metadata"]["name"], ports.pop()))
        if not targets:
            out["errors"].append({"stage": product, "status": "no_http_targets"})
        if len(targets) > 32:
            out["errors"].append({"stage": product, "status": "target_limit_exceeded"})
            continue
        for replica, (name, port) in enumerate(sorted(targets), 1):
            for endpoint in ("config", "runtime_config"):
                record = {"product": product, "replica": replica, "endpoint": endpoint}
                path = f"/api/v1/namespaces/{namespace}/pods/{name}:{port}/proxy/{endpoint}"
                try:
                    raw = run(["get", "--raw", path])
                    record.update(config_excerpt(raw))
                    record["status"] = "read"
                except ReadFailure as exc:
                    record["status"] = str(exc)
                    out["errors"].append(
                        {"stage": f"{product}:{replica}/{endpoint}", "status": str(exc)}
                    )
                out["endpoints"].append(record)
    out["collection_status"] = "partial" if out["errors"] else "completed"
    return out


def config_excerpt(raw):
    """Keep duration/boolean scalars and hashed parent paths; never infer defaults."""
    parents = []
    values = []
    safe_parents = {
        "limits",
        "limits_config",
        "compactor",
        "overrides",
        "runtime_config",
    }
    names = set()
    for number, line in enumerate(raw.splitlines(), 1):
        match = re.fullmatch(r"( *)([^:#]+):(?:\s*(.*))?", line)
        if not match:
            continue
        indent, key, value = len(match[1]), match[2].strip(), (match[3] or "").strip()
        while parents and parents[-1][0] >= indent:
            parents.pop()
        if key in KEYS:
            names.add(key)
            scalar = value.split("#", 1)[0].strip().strip("\"'")
            if DURATION.fullmatch(scalar):
                values.append(
                    {
                        "line": number,
                        "parents": [p[1] for p in parents],
                        "setting": key,
                        "value": scalar,
                    }
                )
        if not value or value.startswith("#"):
            safe_key = key if key in safe_parents else "sha256:" + digest(key)
            parents.append((indent, safe_key))
    return {
        "sha256": digest(raw),
        "selected_settings": values,
        "setting_names_present": sorted(names),
        "empty_overrides_mapping_present": bool(
            re.search(r"(?m)^overrides:\s*\{\}\s*$", raw)
        ),
        "scope": "Lexical excerpts only; aliases, lists and inline mappings require separate review",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--environment", required=True, choices=["cpc-1", "cpc-2", "advisor-central"]
    )
    parser.add_argument("--effective-config", action="store_true")
    args = parser.parse_args()
    if args.effective_config and args.environment != "advisor-central":
        parser.error("--effective-config requires advisor-central")
    try:
        result = effective_config() if args.effective_config else main(args.environment)
    except (ReadFailure, OSError, ValueError, KeyError, TypeError):
        print(
            json.dumps({"environment": args.environment, "status": "collection_failed"})
        )
        raise SystemExit(1)
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["errors"] else 0)
