"""Render real Helm templates and check deployment contracts without a cluster."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import hashlib
import shutil
import sys
from unittest.mock import patch

import jsonschema
import yaml
import package_chart

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared/python/src"))
from agent_common.query_contract import validate_profile  # noqa: E402

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
    services = {
        d["metadata"]["name"]: d["spec"] for d in docs if d["kind"] == "Service"
    }
    frontend = services["verify-frontend"]
    assert frontend["type"] == "NodePort"
    assert frontend["ports"] == [
        {"name": "http", "port": 8080, "targetPort": "http", "nodePort": 30006}
    ]
    assert all(
        s.get("type", "ClusterIP") == "ClusterIP"
        for name, s in services.items()
        if name != "verify-frontend"
    )
    internal = next(
        d["spec"]
        for d in render("--set", "frontendService.type=ClusterIP")
        if d["kind"] == "Service" and d["metadata"]["name"] == "verify-frontend"
    )
    assert internal["type"] == "ClusterIP" and "nodePort" not in internal["ports"][0]
    custom_port = next(
        d["spec"]
        for d in render("--set", "frontendService.nodePort=30007")
        if d["kind"] == "Service" and d["metadata"]["name"] == "verify-frontend"
    )
    assert custom_port["ports"][0]["nodePort"] == 30007
    deployments = {
        d["metadata"]["labels"]["app.kubernetes.io/component"]: d
        for d in docs
        if d["kind"] == "Deployment"
    }
    assert set(deployments) == names
    mcp = deployments["grafana-mcp"]["spec"]["template"]["spec"]["containers"][0]
    hosts = mcp["args"][mcp["args"].index("-allowed-hosts") + 1].split(",")
    assert "*" not in hosts
    assert "verify-grafana-mcp:8000" in hosts
    assert "verify-grafana-mcp.default.svc.cluster.local:8000" in hosts
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        assert mcp[probe]["httpGet"]["httpHeaders"] == [
            {"name": "Host", "value": "verify-grafana-mcp:8000"}
        ]
    for name in ("backend", "incident", "job-controller"):
        container = deployments[name]["spec"]["template"]["spec"]["containers"][0]
        assert container["startupProbe"]["httpGet"]["path"].endswith("/live")
        assert container["readinessProbe"]["httpGet"]["path"].endswith("/ready")
    config = next(d for d in docs if d["kind"] == "ConfigMap")["data"]
    execution_revision = values["configuration"]["executionProfileRevision"]
    profiles = json.loads(config["job-controller.json"])["execution_profiles"]
    namespace_revision = values["configuration"]["namespaceReportProfileRevision"]
    assert set(profiles) == {execution_revision, namespace_revision}
    assert profiles[namespace_revision]["kind"] == "report"
    assert profiles[namespace_revision]["criteria"] == "1.2"
    assert "criteria" not in profiles[execution_revision]
    backend_env = deployments["backend"]["spec"]["template"]["spec"]["containers"][0][
        "env"
    ]
    assert (
        next(
            e["value"]
            for e in backend_env
            if e["name"] == "DSX_NAMESPACE_REPORT_PROFILE_REVISION"
        )
        == namespace_revision
    )
    execution = profiles[execution_revision]
    assert execution["attempt_budget"] >= 8192 + values["llm"]["synthesisMaxTokens"]
    assert (
        execution["token_budget"]
        >= execution["max_attempts"] * execution["attempt_budget"]
    )
    assert (
        json.loads(config["incident.json"])["execution_profile_revision"]
        == execution_revision
    )
    for name, flag in [
        ("job-controller", "JC_APPLY_CONFIG"),
        ("incident", "INCIDENT_APPLY_CONFIG"),
    ]:
        env = deployments[name]["spec"]["template"]["spec"]["containers"][0]["env"]
        assert next(e["value"] for e in env if e["name"] == flag) == "true"
    agent_profile = json.loads(config["agents.json"])
    validate_profile(agent_profile)
    assert agent_profile["clusters"] == {}, (
        "Example has no verified environment selection"
    )
    assert all(q["selected_binding"] is None for q in agent_profile["queries"].values())
    assert "REPLACE_" not in config["agents.json"]
    assert "http://verify-backend:8080" in config["nginx.conf"]
    assert all(
        d["metadata"]["name"] == f"verify-{name}" for name, d in deployments.items()
    )
    for name in ("rcca-agent", "ops-agent"):
        pod = deployments[name]["spec"]["template"]["spec"]
        c = pod["containers"][0]
        env = {e["name"]: e for e in c["env"]}
        assert env["JC_URL"]["value"].endswith("-job-controller:8090/internal/v1")
        assert env["GRAFANA_MCP_URL"]["value"].endswith("-grafana-mcp:8000/mcp")
        assert "secretKeyRef" in env["DATABASE_URL"]["valueFrom"]
        assert "readinessProbe" not in c and pod["initContainers"]
        waits = {i["name"]: i for i in pod["initContainers"]}
        assert set(waits) == {"wait-for-job-controller", "wait-for-grafana-mcp"}
        assert (
            waits["wait-for-grafana-mcp"]["env"][0]["value"]
            == env["GRAFANA_MCP_URL"]["value"]
        )
        compile(waits["wait-for-grafana-mcp"]["args"][0], "mcp-init", "exec")
    renamed = render("--set", "fullnameOverride=gpu-ops")
    assert any(
        d["kind"] == "StatefulSet" and d["metadata"]["name"] == "gpu-ops-postgres"
        for d in renamed
    )
    assert any(
        d["kind"] == "PersistentVolumeClaim"
        and d["metadata"]["name"] == "gpu-ops-artifacts"
        for d in renamed
    )
    migrated = render(
        "--set",
        "fullnameOverride=gpu-ops,postgres.nameOverride=verify-gpu-ops-advisor-postgres,artifacts.persistence.nameOverride=verify-gpu-ops-advisor-artifacts",
    )
    existing = render(
        "--namespace",
        "gpu-ops-advisor",
        "--set",
        "fullnameOverride=gpu-ops-gpu-ops-advisor",
    )
    mcp = next(
        d
        for d in existing
        if d["kind"] == "Deployment" and d["metadata"]["name"].endswith("-grafana-mcp")
    )["spec"]["template"]["spec"]["containers"][0]
    existing_host = "gpu-ops-gpu-ops-advisor-grafana-mcp:8000"
    assert existing_host in mcp["args"][mcp["args"].index("-allowed-hosts") + 1].split(
        ","
    )
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        assert mcp[probe]["httpGet"]["httpHeaders"] == [
            {"name": "Host", "value": existing_host}
        ]
    pg = next(d for d in migrated if d["kind"] == "StatefulSet")
    assert (
        pg["metadata"]["name"]
        == pg["spec"]["serviceName"]
        == "verify-gpu-ops-advisor-postgres"
    )
    assert (
        next(d for d in migrated if d["kind"] == "PersistentVolumeClaim")["metadata"][
            "name"
        ]
        == "verify-gpu-ops-advisor-artifacts"
    )
    report_pod = next(
        d
        for d in migrated
        if d["kind"] == "Deployment" and d["metadata"]["name"] == "gpu-ops-ops-agent"
    )["spec"]["template"]["spec"]
    assert (
        next(v for v in report_pod["volumes"] if v["name"] == "artifacts")[
            "persistentVolumeClaim"
        ]["claimName"]
        == "verify-gpu-ops-advisor-artifacts"
    )
    customized = render(
        "--set", "components.ops-agent.env.GRAFANA_MCP_URL=http://custom-mcp:8000/mcp"
    )
    report_pod = next(
        d
        for d in customized
        if d["kind"] == "Deployment" and d["metadata"]["name"] == "verify-ops-agent"
    )["spec"]["template"]["spec"]
    assert (
        report_pod["initContainers"][1]["env"][0]["value"]
        == "http://custom-mcp:8000/mcp"
    )
    external = render(
        "--set",
        "postgres.enabled=false,artifacts.persistence.enabled=false,ingress.enabled=true,llm.existingSecret=test-llm,components.backend.env.DSX_MODEL_HOSTS=model.internal,components.backend.env.DSX_MODEL_CIDRS=10.20.30.40/32",
    )
    assert not any(
        d["kind"] in ("StatefulSet", "PersistentVolumeClaim") for d in external
    )
    assert any(d["kind"] == "Ingress" for d in external)
    for d in external:
        if d["kind"] == "Deployment" and d["metadata"]["labels"][
            "app.kubernetes.io/component"
        ] in ("backend", "rcca-agent", "ops-agent"):
            env = d["spec"]["template"]["spec"]["containers"][0]["env"]
            for name, value in (
                ("DSX_MODEL_HOSTS", "model.internal"),
                ("DSX_MODEL_CIDRS", "10.20.30.40/32"),
            ):
                assert next(e["value"] for e in env if e["name"] == name) == value
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
