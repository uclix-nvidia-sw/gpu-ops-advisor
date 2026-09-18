"""Exercise deployment Host headers against the actual official MCP server."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("deployment", ["compose", "helm", "helm-existing"])
async def test_deployment_hosts_allow_probes_and_mcp_without_disabling_protection(
    deployment, tmp_path
):
    if os.getenv("RUN_AGENT_E2E") != "1":
        pytest.skip("set RUN_AGENT_E2E=1; requires official MCP and Helm binaries")
    binary = os.getenv(
        "GRAFANA_MCP_BINARY",
        str(
            ROOT
            / (
                ".local/mcp-grafana/mcp-grafana"
                + (".exe" if sys.platform == "win32" else "")
            )
        ),
    )
    if deployment == "compose":
        cmd = (ROOT / "grafana-mcp/Dockerfile").read_text().split("CMD ")[1]
        args = json.loads(cmd)
        host = "grafana-mcp"
        probe_headers = {"Host": "127.0.0.1:8000"}
    else:
        options = (
            ["--set", "fullnameOverride=gpu-ops-gpu-ops-advisor"]
            if deployment == "helm-existing"
            else []
        )
        rendered = subprocess.check_output(
            [
                os.getenv("HELM_BINARY", "helm"),
                "template",
                "gpu-ops",
                str(ROOT / "charts/gpu-ops-advisor"),
                "--namespace",
                "gpu-ops-advisor",
                *options,
            ],
            text=True,
            encoding="utf-8",
        )
        obj = next(
            d
            for d in yaml.safe_load_all(rendered)
            if d
            and d["kind"] == "Deployment"
            and d["metadata"]["name"].endswith("-grafana-mcp")
        )
        container = obj["spec"]["template"]["spec"]["containers"][0]
        args = container["args"]
        host = obj["metadata"]["name"]
        probe_headers = {
            h["name"]: h["value"]
            for h in container["startupProbe"]["httpGet"]["httpHeaders"]
        }
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    args[args.index("-address") + 1] = f"127.0.0.1:{port}"
    url = f"http://127.0.0.1:{port}"
    # A kubelet probe normally sends the Pod IP as Host; this reproduces its 403.
    with (tmp_path / "mcp.log").open("w") as log:
        process = subprocess.Popen(
            [binary, *args],
            stdout=log,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                "GRAFANA_URL": "http://127.0.0.1:1",
                "GRAFANA_SERVICE_ACCOUNT_TOKEN": "fixture-only",
            },
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            for _ in range(100):
                assert process.poll() is None, "MCP exited before listening"
                try:
                    if (
                        httpx.get(
                            url + "/healthz", headers=probe_headers, timeout=1
                        ).status_code
                        == 200
                    ):
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("MCP failed to start")
            assert (
                httpx.get(
                    url + "/healthz", headers={"Host": "10.35.227.42:8000"}
                ).status_code
                == 403
            )
            assert httpx.get(url + "/healthz", headers=probe_headers).status_code == 200
            assert (
                httpx.get(
                    url + "/healthz", headers={"Host": host + ":8000"}
                ).status_code
                == 200
            )
            async with streamablehttp_client(
                url + "/mcp", headers={"Host": host + ":8000"}
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    assert "list_datasources" in {t.name for t in result.tools}
            assert (
                httpx.post(
                    url + "/mcp", headers={"Host": "untrusted.example"}
                ).status_code
                == 403
            )
        finally:
            process.terminate()
            process.wait(timeout=10)
