"""Render real Helm templates and check deployment contracts without a cluster."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import hashlib
import shutil
from unittest.mock import patch

import jsonschema
import yaml
import package_chart

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/gpu-ops-advisor"
HELM = os.getenv("HELM_BINARY", "helm")


def render(*args):
    output = subprocess.check_output(
        [HELM, "template", "verify", str(CHART), *args], text=True, encoding="utf-8"
    )
    documents = [d for d in yaml.safe_load_all(output) if d]
    keys = [(d["kind"], d["metadata"]["name"]) for d in documents]
    assert len(keys) == len(set(keys)), "Duplicate Kubernetes resource"
    services = {d["metadata"]["name"]: d for d in documents if d["kind"] == "Service"}
    workloads = [d for d in documents if d["kind"] in ("Deployment", "StatefulSet")]
    for service in services.values():
        selector = service["spec"]["selector"]
        assert any(
            selector.items() <= w["spec"]["template"]["metadata"]["labels"].items()
            for w in workloads
        ), service
    for workload in workloads:
        pod = workload["spec"]["template"]["spec"]
        volumes = {v["name"] for v in pod.get("volumes", [])}
        volumes.update(
            v["metadata"]["name"]
            for v in workload["spec"].get("volumeClaimTemplates", [])
        )
        for c in pod["containers"]:
            env = c.get("env", [])
            assert len({e["name"] for e in env}) == len(env), (
                "Duplicate environment variable"
            )
            assert all(m["name"] in volumes for m in c.get("volumeMounts", []))
    return documents


def main():
    manifest = json.loads((ROOT / "tools/ci/components.json").read_text())
    values = yaml.safe_load((CHART / "values.yaml").read_text())
    schema = json.loads((CHART / "values.schema.json").read_text())
    jsonschema.validate(values, schema)
    names = {row["component"] for row in manifest}
    assert names == set(values["components"])
    for row in manifest:
        assert (ROOT / row["dockerfile"]).is_file()
        assert (ROOT / row["context"]).is_dir()
    assert (
        next(row for row in manifest if row["component"] == "frontend")["context"]
        == "frontend"
    )
    for name, source in [
        ("agents", "agents"),
        ("job-controller", "job-controller"),
        ("incident", "incident"),
    ]:
        assert json.loads((CHART / f"files/{name}.json").read_text()) == json.loads(
            (ROOT / source / "config.example.json").read_text()
        ), f"Stale chart config: {name}"
    subprocess.run([HELM, "lint", "--strict", str(CHART)], check=True)
    docs = render()
    deployments = {
        d["metadata"]["labels"]["app.kubernetes.io/component"]: d
        for d in docs
        if d["kind"] == "Deployment"
    }
    assert set(deployments) == names
    config = next(d for d in docs if d["kind"] == "ConfigMap")["data"]
    agent_profile = json.loads(config["agents.json"])
    assert agent_profile["clusters"] == {}, "Default installs must discover sources"
    assert all(q["validated"] is True for q in agent_profile["queries"].values())
    assert "REPLACE_" not in config["agents.json"]
    assert "http://verify-gpu-ops-advisor-backend:8080" in config["nginx.conf"]
    for name in ("rcca-agent", "ops-agent"):
        pod = deployments[name]["spec"]["template"]["spec"]
        c = pod["containers"][0]
        env = {e["name"]: e for e in c["env"]}
        assert env["JC_URL"]["value"].endswith("-job-controller:8090/internal/v1")
        assert env["GRAFANA_MCP_URL"]["value"].endswith("-grafana-mcp:8000/mcp")
        assert "secretKeyRef" in env["DATABASE_URL"]["valueFrom"]
        assert "readinessProbe" not in c and pod["initContainers"]
    external = render(
        "--set",
        "postgres.enabled=false,artifacts.persistence.enabled=false,ingress.enabled=true,llm.existingSecret=test-llm",
    )
    assert not any(
        d["kind"] in ("StatefulSet", "PersistentVolumeClaim") for d in external
    )
    assert any(d["kind"] == "Ingress" for d in external)
    for d in external:
        if d["kind"] == "Deployment" and d["metadata"]["labels"][
            "app.kubernetes.io/component"
        ] in ("rcca-agent", "ops-agent"):
            env = d["spec"]["template"]["spec"]["containers"][0]["env"]
            assert (
                next(e for e in env if e["name"] == "LLM_API_KEY")["valueFrom"][
                    "secretKeyRef"
                ]["name"]
                == "test-llm"
            )
    digest = "sha256:" + "a" * 64
    pinned = render(
        "--set",
        f"components.backend.image.digest={digest},artifacts.persistence.existingClaim=existing-artifacts",
    )
    backend = next(
        d
        for d in pinned
        if d["kind"] == "Deployment"
        and d["metadata"]["labels"]["app.kubernetes.io/component"] == "backend"
    )
    assert backend["spec"]["template"]["spec"]["containers"][0]["image"].endswith(
        "@" + digest
    )
    assert not any(d["kind"] == "PersistentVolumeClaim" for d in pinned)
    with tempfile.TemporaryDirectory() as temp:
        subprocess.run([HELM, "package", str(CHART), "-d", temp], check=True)
        package = next(Path(temp).glob("*.tgz"))
        subprocess.run(
            [HELM, "template", "verify", str(package)],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        # Run the production packager on isolated fixture image records.
        stage = Path(temp) / "fixture-repository"
        shutil.copytree(CHART, stage / "charts/gpu-ops-advisor")
        records = stage / "dist/images"
        records.mkdir(parents=True)
        for name in names:
            (records / f"{name}.json").write_text(
                json.dumps(
                    {
                        "component": name,
                        "image": f"ghcr.io/fixture/gpu-ops-advisor-{name}:v1.3.0",
                        "digest": digest,
                        "published": "true",
                    }
                )
            )
        with patch.dict(
            os.environ,
            IMAGE_NAMESPACE="fixture",
            IMAGE_TAG="v1.3.0",
            CHART_VERSION="1.3.0-ci.99.1",
            HELM_BINARY=HELM,
        ):
            package_chart.main(stage)
        result = json.loads((stage / "dist/release-manifest.json").read_text())
        archive = stage / "dist" / result["chart"]
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == result["sha256"]
        packed = yaml.safe_load(
            subprocess.check_output(
                [HELM, "show", "values", str(archive)], text=True, encoding="utf-8"
            )
        )
        assert all(
            c["image"]["digest"] == digest for c in packed["components"].values()
        )
        assert (stage / "charts/gpu-ops-advisor/values.yaml").read_bytes() == (
            CHART / "values.yaml"
        ).read_bytes()
    print(
        "Chart contracts passed: 7 deployments + PostgreSQL, storage/external DB, secrets, digests, package/checksum"
    )


if __name__ == "__main__":
    main()
