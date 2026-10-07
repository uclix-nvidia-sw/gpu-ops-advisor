"""Extend the reviewed shared Alloy metric keep rule; never change cluster labels."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

BASE = (
    "kube_node_status_condition|kube_pod_info|kube_pod_container_resource_requests|"
    "DCGM_FI_DEV_GPU_UTIL|DCGM_FI_DEV_FB_USED|DCGM_FI_DEV_FB_FREE|up|scrape_duration_seconds"
)
ADDITIONS = (
    "kube_node_status_allocatable",
    "DCGM_FI_DEV_XID_ERRORS",
    "DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION",
)
POD_STATE = ("kube_pod_status_phase",)


def extend(config, *, include_pod_state=False):
    """Fail closed on an unfamiliar rule; only replace one exact regex value."""
    pattern = re.compile(
        r'(source_labels\s*=\s*\["__name__"\]\s+regex\s*=\s*")'
        r'([^"\n]+)("\s+action\s*=\s*"keep")'
    )
    standard = BASE + "|" + "|".join(ADDITIONS)
    with_state = standard + "|" + "|".join(POD_STATE)
    matches = [
        m for m in pattern.finditer(config) if m[2] in (BASE, standard, with_state)
    ]
    if len(matches) != 1:
        raise ValueError(
            "Expected exactly one reviewed metric-name keep rule; no changes made"
        )
    match = matches[0]
    # Running the old/default mode must never remove a reviewed state extension.
    expanded = with_state if include_pod_state or match[2] == with_state else standard
    return config[: match.start(2)] + expanded + config[match.end(2) :]


def kubectl(*args):
    result = subprocess.run(
        ["kubectl", *args], capture_output=True, text=True, check=True
    )
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="alloy")
    parser.add_argument("--configmap", default="alloy")
    parser.add_argument("--key", default="config.alloy")
    parser.add_argument(
        "--include-pod-state",
        action="store_true",
        help="Also forward KSM Pod phase for D07 source validation; no scheduler scrape or binding activation",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the selected reviewed metric extension",
    )
    args = parser.parse_args()
    cm = json.loads(
        kubectl("-n", args.namespace, "get", "configmap", args.configmap, "-o", "json")
    )
    before = cm["data"][args.key]
    after = extend(before, include_pod_state=args.include_pod_state)
    requested = ADDITIONS + (POD_STATE if args.include_pod_state else ())
    summary = {
        "metric_names_added": [
            name for name in requested if after.count(name) > before.count(name)
        ],
        "changed": before != after,
        "cluster_labels_modified": False,
        "applied": False,
    }
    if args.apply and before != after:
        directory = Path(
            tempfile.mkdtemp(prefix="gpu-ops-forwarding-", dir=Path.home())
        )
        os.chmod(directory, 0o700)
        escaped = args.key.replace("~", "~0").replace("/", "~1")
        field = "/data/" + escaped
        patches = {
            "apply.json": [
                {"op": "test", "path": field, "value": before},
                {"op": "replace", "path": field, "value": after},
            ],
            "rollback.json": [
                {"op": "test", "path": field, "value": after},
                {"op": "replace", "path": field, "value": before},
            ],
        }
        for name, patch in patches.items():
            path = directory / name
            path.write_text(json.dumps(patch), encoding="utf-8")
            os.chmod(path, 0o600)
        kubectl(
            "-n",
            args.namespace,
            "patch",
            "configmap",
            args.configmap,
            "--type=json",
            "--patch-file",
            str(directory / "apply.json"),
        )
        current = json.loads(
            kubectl(
                "-n", args.namespace, "get", "configmap", args.configmap, "-o", "json"
            )
        )
        if current["data"][args.key] != after:
            raise RuntimeError(
                "ConfigMap read-back mismatch; inspect private rollback file"
            )
        summary.update(
            applied=True,
            private_backup=str(directory),
            config_sha256=hashlib.sha256(after.encode()).hexdigest(),
        )
    summary["scope"] = (
        "ConfigMap only. Confirm Alloy reload and stored samples; no binding or Worker activation asserted."
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
