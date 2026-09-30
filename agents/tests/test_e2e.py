"""Real PostgreSQL + Incident + JC + Worker processes + NAT + official Grafana MCP.

Only upstream Grafana datasource responses and the inference endpoint are fixtures.
No production metrics or model-quality claims are made by this suite.
"""

import contextlib
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import psycopg
from psycopg.types.json import Jsonb
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import pytest

from agent_common.contracts import content_hash
from rcca_agent.runbook_admin import draft, transition
from test_rca_analysis import general_runbook, analysis_reply

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local" / "agent-e2e"
SCOPE = {"clusters": [{"cluster_id": "cpc-2", "namespaces": ["dev"]}]}
PERIOD = {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T01:00:00Z"}


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Upstream(BaseHTTPRequestHandler):
    requests = []
    llm_fail = False
    api_key = "fixture-only"
    logs_fail = False
    logs_max_limit = None
    logs_json_target = None
    logs_max_seconds = None
    fleet_reports = False

    def log_message(self, *args):
        pass

    def send(self, body, status=200):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path.endswith("/api/v1/query"):
            self.path += "?" + raw.decode()
            return self.do_GET()
        body = json.loads(raw or "{}")
        self.requests.append((self.path, body))
        if self.path == "/v1/chat/completions":
            if self.headers.get("Authorization") != "Bearer " + self.api_key:
                return self.send({"error": "unauthorized"}, 401)
            if len(body.get("messages", [])) == 1:
                return self.send({"choices": [{"message": {"content": "OK"}}]})
            if self.llm_fail:
                return self.send({"error": "fixture unavailable"}, 503)
            if body.get("tools"):
                allowed = body["tools"][0]["function"]["parameters"]["properties"][
                    "query_id"
                ]["enum"]
                query = "D02" if "D02" in allowed else "stop"
                message = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "fixture-call",
                            "type": "function",
                            "function": {
                                "name": "investigate",
                                "arguments": json.dumps({"query_id": query}),
                            },
                        }
                    ],
                }
            else:
                data = json.loads(body["messages"][1]["content"])
                message = {
                    "role": "assistant",
                    "content": json.dumps(
                        analysis_reply(data["observation_refs"])
                        if "observation_refs" in data
                        else {"fact_ids": [f["id"] for f in data.get("facts", [])][:2]}
                    ),
                }
            return self.send(
                {
                    "choices": [{"message": message, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 10,
                        "total_tokens": 30,
                    },
                }
            )
        return self.send({"error": "unexpected POST"}, 404)

    def do_GET(self):
        u = urlparse(self.path)
        query = parse_qs(u.query)
        self.requests.append((u.path, query))
        if u.path == "/api/datasources":
            return self.send(
                [
                    {"id": 1, "uid": "mimir", "name": "Metrics", "type": "prometheus"},
                    {"id": 2, "uid": "loki", "name": "Logs", "type": "loki"},
                ]
            )
        if "/label/" in u.path and u.path.endswith("/values"):
            label = u.path.split("/label/", 1)[1].split("/", 1)[0]
            expected = "cluster" if "/loki/" in u.path else "cluster_id"
            return self.send(
                {"status": "success", "data": ["cpc-2"] if label == expected else []}
            )
        if (
            "/api/datasources/uid/" in u.path
            and "/proxy/" not in u.path
            and "/resources/" not in u.path
        ):
            uid = u.path.rsplit("/", 1)[-1]
            return self.send(
                {
                    "id": 1 if uid == "mimir" else 2,
                    "uid": uid,
                    "name": uid,
                    "type": "prometheus" if uid == "mimir" else "loki",
                    "url": "http://127.0.0.1:" + str(self.server.server_port),
                    "access": "proxy",
                    "jsonData": {},
                }
            )
        if u.path.endswith("/api/v1/query"):
            expr = query.get("query", [""])[0]
            start = datetime.fromisoformat(
                PERIOD["start"].replace("Z", "+00:00")
            ).timestamp()
            labels = {
                "cluster_id": "cpc-2",
                "UUID": "GPU-1",
                "namespace": "dev",
                "pod": "training",
                "node": "node-1",
                "pod_uid": "pod-uid-1",
                "allocation_mode": "exclusive",
                "allocation_episode_key": "episode-1",
            }
            value = 250 if "POWER" in expr else (2 if "GPU_UTIL" in expr else 1)
            values = [[start + i * 30, str(value)] for i in range(121)]
            return self.send(
                {
                    "status": "success",
                    "data": {
                        "resultType": "matrix",
                        "result": [{"metric": labels, "values": values}],
                    },
                }
            )
        if u.path.endswith("/loki/api/v1/query_range"):
            requested_limit = int(query.get("limit", ["0"])[0])
            if (
                self.logs_max_limit is not None
                and requested_limit > self.logs_max_limit
            ):
                return self.send({"error": "max entries limit per query exceeded"}, 400)
            if self.logs_fail:
                return self.send({"error": "fixture query failure"}, 503)
            start = int(
                datetime.fromisoformat(
                    PERIOD["start"].replace("Z", "+00:00")
                ).timestamp()
                * 1e9
            )
            if self.logs_json_target is not None:
                expr = query["query"][0]
                selector = expr.split("}", 1)[0]
                drop = (
                    " | drop dsx_json_0, dsx_json_0_extracted, "
                    "dsx_json_1, dsx_json_1_extracted | json "
                )
                for index, (field, path) in enumerate(
                    sorted(
                        {
                            "node": 'resources["k8s.node.name"]',
                            "component": 'attributes["component"]',
                        }.items()
                    )
                ):
                    alias = f"dsx_json_{index}"
                    value = json.dumps(self.logs_json_target[field])
                    if (
                        not expr.split("}", 1)[1].startswith(drop)
                        or f"{alias}={json.dumps(path)}" not in expr
                        or '| __error__="" | (' not in expr
                        or f"| ({alias}={value} or {alias}_extracted={value})"
                        not in expr
                        or f"{field}=" in selector
                    ):
                        return self.send({"error": "Fleet JSON filter required"}, 400)
                start = int(query["start"][0])
                seconds = (int(query["end"][0]) - start) / 1e9
                padding = (
                    "fixture " * 2048
                    if self.logs_max_seconds is not None
                    and seconds > self.logs_max_seconds
                    else "fixture"
                )
                line = json.dumps(
                    {
                        "resources": {"k8s.node.name": self.logs_json_target["node"]},
                        "attributes": {
                            "component": self.logs_json_target["component"],
                            "health": "healthy",
                            "check_status": "valid",
                        },
                        "body": padding,
                    }
                )
            else:
                line = json.dumps(
                    {
                        "health": "Degraded",
                        "check_status": "valid",
                        "component": "gpu",
                        "producer_contract": "fixture-v1",
                        "target": {"gpu_uuid": "GPU-1"},
                        "observed_at": PERIOD["start"],
                    }
                )
            if self.fleet_reports:
                start = int(query["start"][0]) + 1_000_000_000
                line = json.dumps(
                    {
                        "attributes": {
                            "component": "accelerator-nvidia-error-sxid",
                            "health": "Unhealthy",
                            "log_type": "component_data",
                            "reason": "SXID 11001(ingress invalid command)",
                        },
                        "resources": {
                            "machine.id": "fixture-machine",
                            "k8s.node.name": "node-1",
                        },
                    }
                )
            return self.send(
                {
                    "status": "success",
                    "data": {
                        "resultType": "streams",
                        "result": [
                            {
                                "stream": {"cluster": "cpc-2", "namespace": "dev"},
                                "values": [
                                    [str(start + i), line]
                                    for i in range(31 if self.fleet_reports else 1)
                                ],
                            }
                        ],
                    },
                }
            )
        if u.path.endswith("/api/health"):
            return self.send({"database": "ok"})
        return self.send({"error": "unexpected GET", "path": self.path}, 404)


def wait_http(url, process=None):
    for _ in range(150):
        if process and process.poll() is not None:
            raise RuntimeError("service exited: " + str(process.returncode))
        try:
            if httpx.get(url, timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError("service not ready: " + url)


@pytest.fixture(scope="module")
def stack():
    if os.getenv("RUN_AGENT_E2E") != "1":
        pytest.skip(
            "set RUN_AGENT_E2E=1; requires official MCP and native PostgreSQL/JC binaries"
        )
    LOCAL.mkdir(parents=True, exist_ok=True)
    external_url = os.getenv("AGENT_E2E_DATABASE_URL", "")
    extension = ".exe" if sys.platform == "win32" else ""
    pg_bin = Path(os.getenv("PG_BIN", str(ROOT / "backend/.local/postgres/bin/bin")))
    mcp = Path(
        os.getenv(
            "GRAFANA_MCP_BINARY",
            str(ROOT / (".local/mcp-grafana/mcp-grafana" + extension)),
        )
    )
    jc = Path(os.getenv("JC_BINARY", str(ROOT / (".local/job-controller" + extension))))
    incident = Path(
        os.getenv("INCIDENT_BINARY", str(ROOT / (".local/incident" + extension)))
    )
    assert mcp.is_file() and jc.is_file() and incident.is_file()
    initdb, pg_ctl = pg_bin / ("initdb" + extension), pg_bin / ("pg_ctl" + extension)
    schema = "agent_e2e_" + uuid4().hex
    data = LOCAL / ("pg-" + uuid4().hex)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    if not external_url:
        assert initdb.is_file()
        subprocess.run(
            [
                str(initdb),
                "-D",
                str(data),
                "-U",
                "postgres",
                "-A",
                "trust",
                "--encoding=UTF8",
                "--no-locale",
            ],
            check=True,
            capture_output=True,
            creationflags=flags,
        )
    pg_port, jc_port, mcp_port = port(), port(), port()
    url = external_url or f"postgresql://postgres@127.0.0.1:{pg_port}/postgres"
    processes = []
    files = []
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()

    def spawn(args, env, name):
        log = open(LOCAL / (name + ".log"), "w", encoding="utf-8")
        files.append(log)
        p = subprocess.Popen(
            args,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        processes.append(p)
        return p

    try:
        # pg_ctl drops elevated Windows privileges before launching postgres.
        if not external_url:
            subprocess.run(
                [
                    str(pg_ctl),
                    "-D",
                    str(data),
                    "-l",
                    str(data / "server.log"),
                    "-o",
                    f"-h 127.0.0.1 -p {pg_port}",
                    "-w",
                    "start",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                timeout=30,
            )
        for _ in range(10):
            try:
                with psycopg.connect(url, connect_timeout=1):
                    break
            except psycopg.OperationalError:
                time.sleep(0.1)
        else:
            raise RuntimeError("PostgreSQL connection failed")
        if external_url:
            with psycopg.connect(external_url, autocommit=True) as conn:
                conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            # Both libpq/psycopg and Go pgx accept startup options in a URI.
            from urllib.parse import urlencode, quote

            parts = conninfo_to_dict(external_url)
            options = parts.pop("options", "") + f" -c search_path={schema}"
            # Keep the URI form because JC's database adapter parses URL DSNs.
            parsed = urlparse(external_url)
            query = parse_qs(parsed.query)
            query["options"] = [options.strip()]
            url = parsed._replace(
                query=urlencode(query, doseq=True, quote_via=quote)
            ).geturl()
        config = json.loads((ROOT / "job-controller/config.example.json").read_text())
        config["execution_profiles"]["local-v1"].update(
            attempt_budget=100000, token_budget=300000
        )
        cfg = LOCAL / "jc.json"
        cfg.write_text(json.dumps(config))
        env = {
            **os.environ,
            "DATABASE_URL": url,
            "JC_CONFIG_FILE": str(cfg),
            "JC_ADDRESS": f"127.0.0.1:{jc_port}",
        }
        jp = spawn([str(jc)], env, "jc")
        jc_url = f"http://127.0.0.1:{jc_port}/internal/v1"
        wait_http(jc_url + "/health/ready", jp)
        with psycopg.connect(url) as conn:
            conn.execute(
                "INSERT INTO cluster_registry(id) VALUES('cpc-2') ON CONFLICT DO NOTHING"
            )
            book = general_runbook("cpc-2")
            conn.execute(
                "INSERT INTO knowledge_revisions(id,knowledge_id,knowledge_key,revision,kind,state,visibility,content,content_hash,reviewed_content_hash,compatibility) VALUES(%s,%s,%s,1,'runbook','published','common',%s,%s,%s,%s)",
                (
                    book["id"],
                    book["knowledge_id"],
                    book["knowledge_key"],
                    Jsonb(book["content"]),
                    book["content_hash"],
                    book["reviewed_content_hash"],
                    Jsonb(book["compatibility"]),
                ),
            )
        incident_url = f"http://127.0.0.1:{port()}"
        ip = spawn(
            [str(incident)],
            {
                **os.environ,
                "DATABASE_URL": url,
                "INCIDENT_CONFIG_FILE": str(ROOT / "incident/config.example.json"),
                "INCIDENT_JOB_CONTROLLER_URL": f"http://127.0.0.1:{jc_port}",
                "INCIDENT_ADDRESS": incident_url.removeprefix("http://"),
                "INCIDENT_APPLY_CONFIG": "false",
            },
            "incident",
        )
        wait_http(incident_url + "/internal/v1/health/ready", ip)
        upstream_url = f"http://127.0.0.1:{upstream.server_port}"
        mp = spawn(
            [
                str(mcp),
                "-t",
                "streamable-http",
                "-address",
                f"127.0.0.1:{mcp_port}",
                "-enabled-tools",
                "datasource,prometheus,loki",
                "-disable-write",
                "-max-loki-log-limit",
                "5000",
            ],
            {
                **os.environ,
                "GRAFANA_URL": upstream_url,
                "GRAFANA_SERVICE_ACCOUNT_TOKEN": "fixture-only",
            },
            "mcp",
        )
        wait_http(f"http://127.0.0.1:{mcp_port}/healthz", mp)
        profile = json.loads((ROOT / "agents/config.example.json").read_text())
        profile["health_contracts"] = {
            "fixture-v1": {
                "producer_contract": "fixture-v1",
                "revision": "health-fixture-v1",
                "checks": {"valid": "valid", "unavailable": "unavailable"},
                "health": {
                    "Degraded": {"normalized_health": "degraded", "severity": "warning"}
                },
            }
        }
        profile_path = LOCAL / "profile.json"
        profile_path.write_text(json.dumps(profile))
        worker_env = {
            **os.environ,
            "DATABASE_URL": url,
            "JC_URL": jc_url,
            "AGENT_CONFIG_FILE": str(profile_path),
            "GRAFANA_MCP_URL": f"http://127.0.0.1:{mcp_port}/mcp",
            "LLM_BASE_URL": upstream_url + "/v1",
            "LLM_MODEL": "fixture-model",
            "LLM_API_KEY": "fixture-only",
            "ARTIFACT_DIR": str(LOCAL / "artifacts"),
        }
        yield dict(
            url=url,
            jc=jc_url,
            incident=incident_url,
            env=worker_env,
            spawn=spawn,
            profile=profile,
        )
    finally:
        upstream.shutdown()
        upstream.server_close()
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    p.wait(5)
        for f in files:
            f.close()
        if external_url:
            with psycopg.connect(external_url, autocommit=True) as conn:
                conn.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )
        else:
            subprocess.run(
                [str(pg_ctl), "-D", str(data), "stop", "-m", "immediate"],
                capture_output=True,
                creationflags=flags,
            )


def submit(stack, kind, data):
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    body = dict(
        contract_version="1.3",
        source_module="incident" if kind == "rca" else "backend",
        source_key=str(uuid4()),
        kind=kind,
        input=data,
        deadline_at=deadline,
        execution_profile_revision="local-v1",
    )
    if kind == "rca":
        body.update(
            dispatch_deadline=deadline,
            snapshot_ref={"incident_id": data["incident_id"], "evidence_version": 1},
        )
    response = httpx.post(stack["jc"] + "/jobs/" + kind, json=body, timeout=10)
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


def worker_result(stack, kind, jid, suffix=""):
    module = "rcca_agent.main" if kind == "rca" else "ops_agent.main"
    process = stack["spawn"](
        [sys.executable, "-m", module, "--once"], stack["env"], kind + suffix
    )
    assert process.wait(90) == 0, (LOCAL / (kind + suffix + ".log")).read_text()
    job = httpx.get(stack["jc"] + "/jobs/" + jid).json()
    assert job["status"] == "succeeded", job
    with psycopg.connect(stack["url"]) as conn:
        body, digest = conn.execute(
            "SELECT body,content_hash FROM result_candidates WHERE id=%s",
            (job["published_result_id"],),
        ).fetchone()
        evidence = conn.execute(
            "SELECT query_id,tool_status FROM evidence WHERE job_id=%s", (jid,)
        ).fetchall()
    assert content_hash(body) == digest
    assert body["result_schema_version"] == "1.1"
    return body, evidence


@pytest.mark.e2e
async def test_loki_limit_through_nat_and_official_mcp(stack, monkeypatch):
    from nat.plugins.mcp.client.client_base import MCPStreamableHTTPClient

    from agent_common.observation import Observation, unwrap

    monkeypatch.setattr(Upstream, "logs_max_limit", 5000)
    args = dict(
        datasourceUid="loki",
        logql='{cluster="cpc-2",namespace="dev"}',
        startRfc3339=PERIOD["start"],
        endRfc3339=PERIOD["end"],
        direction="forward",
        limit=5000,
    )
    async with MCPStreamableHTTPClient(
        stack["env"]["GRAFANA_MCP_URL"], reconnect_enabled=False
    ) as client:
        tool = await client.get_tool("query_loki_logs")
        raw = await tool.acall(args)
        assert raw.startswith("MCPToolClient tool call failed:")
        assert "max entries limit per query exceeded" in raw
        query_requests = [
            request
            for path, request in Upstream.requests
            if path.endswith("/loki/api/v1/query_range")
        ]
        assert query_requests[-1]["limit"] == ["5001"]
        raw = await tool.acall({**args, "limit": 4999})
        assert unwrap(raw)["data"]

        tools = {}
        for name in ("query_loki_logs", "list_datasources", "list_loki_label_values"):
            tools[name] = (await client.get_tool(name)).acall
        observation = Observation(
            tools,
            stack["profile"],
            {"scope": SCOPE, "time_range": PERIOD},
            time.monotonic() + 30,
        )
        request_start = len(Upstream.requests)
        for query_id in ("D05", "D09"):
            evidence = await observation.collect(query_id)
            assert evidence and all(row["tool_status"] == "ok" for row in evidence), (
                evidence
            )
        assert all(
            int(request["limit"][0]) <= 5000
            for path, request in Upstream.requests[request_start:]
            if path.endswith("/loki/api/v1/query_range")
        )


@pytest.mark.e2e
async def test_fleet_json_logs_split_through_nat_and_official_mcp(stack, monkeypatch):
    from nat.plugins.mcp.client.client_base import MCPStreamableHTTPClient

    from agent_common.observation import Observation
    from agent_common.parsers import log_lines, parse_health

    target = {"node": 'node-"fixture\\1', "component": "accelerator-nvidia-error-xid"}
    monkeypatch.setattr(Upstream, "logs_json_target", target)
    monkeypatch.setattr(Upstream, "logs_max_seconds", 900)
    profile = json.loads(json.dumps(stack["profile"]))
    profile["limits"].update(max_bytes=4096, max_queries=40)
    for query_id in ("D05", "D09"):
        profile["queries"][query_id]["target_labels"] = {
            "node": "node",
            "component": "component",
        }
    data = {
        "scope": SCOPE,
        "time_range": PERIOD,
        "target": {"node": target["node"]},
        "log_query_target": target,
    }
    request_start = len(Upstream.requests)
    async with MCPStreamableHTTPClient(
        stack["env"]["GRAFANA_MCP_URL"], reconnect_enabled=False
    ) as client:
        tools = {}
        for name in ("query_loki_logs", "list_datasources", "list_loki_label_values"):
            tools[name] = (await client.get_tool(name)).acall
        observation = Observation(tools, profile, data, time.monotonic() + 60)
        for query_id in ("D05", "D09"):
            evidence = await observation.collect(query_id)
            assert len(evidence) > 1 and all(
                row["tool_status"] == "ok" and row["snapshot"] for row in evidence
            ), evidence
            assert evidence[0]["time_range"]["start"] == PERIOD["start"]
            assert evidence[-1]["time_range"]["end"] == PERIOD["end"]
            assert all(
                left["time_range"]["end"] == right["time_range"]["start"]
                for left, right in zip(evidence, evidence[1:])
            )
            logs = [
                json.loads(line) for e in evidence for line in log_lines(e["snapshot"])
            ]
            assert logs and all(
                row["resources"]["k8s.node.name"] == target["node"]
                and row["attributes"]["component"] == target["component"]
                and row["attributes"]["health"] == "healthy"
                for row in logs
            )
            health = parse_health(evidence, profile["health_contracts"])
            assert health and all(
                row["check_status"] == row["normalized_health"] == "unknown"
                for row in health
            )
    requests = [
        args
        for path, args in Upstream.requests[request_start:]
        if path.endswith("/loki/api/v1/query_range")
    ]
    durations = [(int(q["end"][0]) - int(q["start"][0])) / 1e9 for q in requests]
    assert max(durations) > 900 and min(durations) <= 900
    assert all(
        'cluster="cpc-2"' in q["query"][0] and 'namespace=~"dev"' in q["query"][0]
        for q in requests
    )


@pytest.mark.e2e
def test_namespace_report_through_backend_with_report_only_criteria(stack):
    # Real Backend selects the report-only profile; global criteria stay unchanged.
    extension = ".exe" if sys.platform == "win32" else ""
    binary = Path(
        os.getenv("BACKEND_BINARY", str(ROOT / (".local/backend-e2e" + extension)))
    )
    backend = f"http://127.0.0.1:{port()}/api/v1"
    process = stack["spawn"](
        [str(binary)],
        {
            **os.environ,
            "DATABASE_URL": stack["url"],
            "DSX_ADDRESS": backend.removeprefix("http://").removesuffix("/api/v1"),
            "DSX_MIGRATE": "false",
            "DSX_SEED": "false",
            "DSX_SCHEDULER_ENABLED": "false",
            "DSX_JOB_CONTROLLER_URL": stack["jc"].removesuffix("/internal/v1"),
            "DSX_NAMESPACE_REPORT_PROFILE_REVISION": "report-namespace-v1",
        },
        "namespace-backend",
    )
    wait_http(backend + "/health/ready", process)
    data = dict(
        scope=SCOPE,
        time_range=PERIOD,
        timezone="UTC",
        topic_ids=["O08"],
        group_by=["namespace"],
    )
    response = httpx.post(
        backend + "/reports", json=data, headers={"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 202, response.text
    jid = response.json()["job_id"]
    result, evidence = worker_result(stack, "report", jid, "-namespace")
    assert result["versions"]["execution_profile_revision"] == "report-namespace-v1"
    assert result["quality"]["requested_group_by"] == ["namespace"]
    html = httpx.get(backend + f"/reports/{jid}/export?format=html")
    assert html.status_code == 200
    assert "연결 GPU 평균 활동률" in html.text
    assert "Namespace의 실제 소비량" in html.text
    with psycopg.connect(stack["url"]) as conn:
        assert conn.execute(
            "SELECT versions->>'criteria' FROM jobs WHERE kind='rca' LIMIT 1"
        ).fetchone() in (None, ("unconfigured",))
    assert result["versions"]["criteria"] == "1.2"
    topic = result["topics"][0]
    metrics = {m["id"].split(".")[1]: m for m in topic["metrics"]}
    assert metrics["namespace_connected_gpu_count"]["value"] == 1
    assert "GPU·시간" in html.text
    assert metrics["observed_namespace_hours"]["value"] == 1
    assert metrics["namespace_activity_valid_hours"]["value"] == 1
    assert metrics["namespace_connected_gpu_util"]["value"] == 2
    assert metrics["namespace_connected_gpu_util"]["target"] == {
        "cluster_id": "cpc-2",
        "namespace": "dev",
    }
    assert topic["status"] == "partial"
    assert not topic["recommendations"]
    assert any(q == "D02" and status == "ok" for q, status in evidence)
    for artifact in result["artifacts"]:
        body = (LOCAL / "artifacts" / artifact["object_key"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == artifact["checksum"]
        assert b"O08.namespace_connected_gpu_util.0" in body


@pytest.mark.e2e
def test_real_workers_nat_grafana_mcp_and_publication(stack, monkeypatch):
    monkeypatch.setattr(Upstream, "logs_max_limit", 5000)
    iid = str(uuid4())
    data = dict(
        scope=SCOPE,
        incident_id=iid,
        evidence_version=1,
        analysis_profile_revision="fixture-v1",
        incident_time="2026-09-15T00:15:00Z",
        time_range=PERIOD,
        purpose_ids=["R05"],
    )
    snapshot = {"input": data, "evidence": {"symptom": "gpu_access"}}
    with psycopg.connect(stack["url"]) as conn:
        conn.execute(
            "INSERT INTO incidents(id,cluster_id,scope,occurred_at,state,evidence_version) VALUES(%s,'cpc-2',%s,%s,'open',1)",
            (iid, Jsonb(SCOPE), data["incident_time"]),
        )
        conn.execute(
            "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES(%s,1,%s,%s)",
            (iid, Jsonb(snapshot), content_hash(snapshot)),
        )
    jid = submit(stack, "rca", data)
    rca, evidence = worker_result(stack, "rca", jid)
    assert any(q == "D09" and s == "ok" for q, s in evidence), evidence
    assert any(q == "D02" and s == "ok" for q, s in evidence), evidence
    assert rca["incident_id"] == iid
    assert rca["narrative_status"] == "complete"
    assert len(rca["narrative"]) == 5
    assert rca["device_observations"] and rca["cause_candidates"]
    assert rca["quality"]["analysis"]["status"] == "complete"
    assert rca["quality"]["analysis"]["followups"] == 1
    assert any(q == "rca_synthesis" for q, s in evidence)
    synthesis_requests = [
        json.loads(body["messages"][1]["content"])
        for path, body in Upstream.requests
        if path == "/v1/chat/completions"
        and "tools" not in body
        and len(body.get("messages", [])) > 1
    ]
    plans = next(
        p["runbook_plans"] for p in synthesis_requests if "observation_refs" in p
    )
    assert plans[0]["investigation_only"] and plans[0]["analysis_guidance"]
    assert all(c["causal_status"] == "candidate" for c in rca["cause_candidates"])
    report_input = dict(
        scope=SCOPE,
        time_range=PERIOD,
        timezone="Asia/Seoul",
        topic_ids=["O05", "O09", "O11"],
        group_by=["cluster"],
    )
    rid = submit(stack, "report", report_input)
    report, _ = worker_result(stack, "report", rid)
    energy = next(t for t in report["topics"] if t["topic_id"] == "O09")["metrics"][0]
    assert energy["value"] == 0.25, report
    assert report["narrative_status"] == "complete"
    assert next(t for t in report["topics"] if t["topic_id"] == "O05")[
        "rca_references"
    ][0]["result_id"]
    for artifact in report["artifacts"]:
        path = LOCAL / "artifacts" / artifact["object_key"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["checksum"]
    assert any("/api/v1/query" in p for p, _ in Upstream.requests)
    assert any("/loki/api/v1/query_range" in p for p, _ in Upstream.requests)
    assert any(p == "/v1/chat/completions" for p, _ in Upstream.requests)


@pytest.mark.e2e
@pytest.mark.parametrize("fleet_reports", [False, True])
def test_grafana_webhook_through_incident_jc_and_real_rca_worker(
    stack, monkeypatch, fleet_reports
):
    alert = {
        "status": "firing",
        "fingerprint": uuid4().hex,
        "startsAt": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "labels": {
            "alertname": "GPUAlert",
            "cluster_id": "cpc-2",
            "namespace": "dev",
            "node": "node-1",
            "gpu_uuid": "GPU-1",
            "severity": "warning",
            "k8s_node_name": "node-1",
            "component": "accelerator-nvidia-error-xid",
            "reason": "XID 79 on fixture device",
            "suggested_actions": json.dumps(
                {"description": "Fixture only", "repair_actions": ["inspect"]}
            ),
        },
        "annotations": {
            "summary": "GPU alert from real Incident path",
            "error_code": "Xid 79",
        },
    }
    if fleet_reports:
        alert["labels"].update(
            component="accelerator-nvidia-error-sxid",
            reason="SXID 11001",
            machine_id="fixture-machine",
        )
        alert["labels"].pop("gpu_uuid")
        alert["annotations"]["error_code"] = "SXID 11001"
        profile = json.loads((ROOT / "agents/config.example.json").read_text())
        path = LOCAL / "fleet-profile.json"
        path.write_text(json.dumps(profile))
        stack = {**stack, "env": {**stack["env"], "AGENT_CONFIG_FILE": str(path)}}
        monkeypatch.setattr(Upstream, "fleet_reports", True)
    response = httpx.post(
        stack["incident"] + "/webhooks/grafana", json={"alerts": [alert]}, timeout=10
    )
    assert response.status_code == 202, response.text
    item = response.json()["items"][0]
    assert item["outbox_id"], item
    # Read what Incident persisted and delivered; never manufacture an RCA snapshot/job.
    with psycopg.connect(stack["url"], autocommit=True) as conn:
        snapshot, digest = conn.execute(
            "SELECT snapshot,content_hash FROM incident_evidence_versions WHERE incident_id=%s AND revision=%s",
            (item["incident_id"], item["evidence_version"]),
        ).fetchone()
        assert snapshot["alert"] == alert and "evidence" not in snapshot
        assert content_hash(snapshot) == digest
        for _ in range(100):
            jid, status = conn.execute(
                "SELECT job_id,status FROM enqueue_outbox WHERE id=%s",
                (item["outbox_id"],),
            ).fetchone()
            if jid and status == "accepted":
                break
            time.sleep(0.1)
        else:
            pytest.fail("Incident did not dispatch RCA through its outbox")
    monkeypatch.setattr(
        Upstream,
        "logs_json_target",
        {"node": "node-1", "component": alert["labels"]["component"]},
    )
    request_start = len(Upstream.requests)
    result, evidence = worker_result(stack, "rca", str(jid), "-incident-webhook")
    assert snapshot["input"]["target"]["component"] == alert["labels"]["component"]
    log_requests = [
        args
        for path, args in Upstream.requests[request_start:]
        if path.endswith("/loki/api/v1/query_range")
    ]
    assert log_requests and all(
        f'| (dsx_json_0="{alert["labels"]["component"]}" or '
        f'dsx_json_0_extracted="{alert["labels"]["component"]}")' in args["query"][0]
        for args in log_requests
    )
    if fleet_reports:
        assert len(result["device_observations"]) == 62
        assert all(
            h["error_code"] == "sxid:11001" and not h["fact_eligible"]
            for h in result["device_observations"]
        )
        assert result["quality"]["analysis"]["status"] == "complete"
        assert {"D05", "D09", "D02", "D08", "D06"} <= {q for q, _ in evidence}
        assert "mapping_target_unverified" in result["missing_inputs"]
        assert result["narrative_status"] == "complete"
    else:
        assert all(
            row["check_status"] == row["normalized_health"] == "unknown"
            for row in result["device_observations"]
        )
    assert result["incident_id"] == item["incident_id"]
    assert {a["purpose_id"] for a in result["assessments"]} == {"R01", "R02"}
    assert ("incident_snapshot", "ok") in evidence
    assert any(query.startswith("D") for query, _ in evidence)
    # A published blocked result must not hide MCP rejecting fractional times.
    assert all(
        status in {"ok", "empty", "partial"}
        for query, status in evidence
        if query.startswith("D")
    ), evidence
    with psycopg.connect(stack["url"]) as conn:
        partial = conn.execute(
            "SELECT quality FROM evidence WHERE job_id=%s AND tool_status='partial'",
            (jid,),
        ).fetchall()
        assert partial and all(
            q[0]["reason"] == "time_precision_reduced" for q in partial
        )
        clues = conn.execute(
            "SELECT snapshot FROM evidence WHERE job_id=%s AND query_id='alert_clues'",
            (jid,),
        ).fetchone()[0]
        assert clues["error_codes"] == (["sxid:11001"] if fleet_reports else ["xid:79"])
        assert clues["provider_actions"]["execution"] == "not_performed"
        saved_snapshot, checksum = conn.execute(
            "SELECT snapshot,checksum FROM evidence WHERE job_id=%s AND query_id='incident_snapshot'",
            (jid,),
        ).fetchone()
        assert saved_snapshot == snapshot and checksum == digest
        unchanged = conn.execute(
            "SELECT snapshot,content_hash FROM incident_evidence_versions WHERE incident_id=%s AND revision=%s",
            (item["incident_id"], item["evidence_version"]),
        ).fetchone()
        assert unchanged == (snapshot, digest)


@pytest.mark.e2e
def test_builtin_profile_without_datasource_configuration(stack):
    builtin_stack = {
        **stack,
        "env": {
            **stack["env"],
            "AGENT_CONFIG_FILE": str(ROOT / "agents/config.example.json"),
        },
    }
    request_start = len(Upstream.requests)
    data = dict(
        scope=SCOPE,
        time_range=PERIOD,
        timezone="UTC",
        topic_ids=["O09", "O10"],
        group_by=["cluster"],
    )
    jid = submit(builtin_stack, "report", data)
    report, evidence = worker_result(builtin_stack, "report", jid, "-builtin")
    energy = next(t for t in report["topics"] if t["topic_id"] == "O09")["metrics"][0]
    assert energy["value"] == 0.25
    assert any(q == "D11" and s == "ok" for q, s in evidence)
    assert any(q == "D09" and s == "ok" for q, s in evidence)
    requests = Upstream.requests[request_start:]
    assert any(p == "/api/datasources" for p, _ in requests)
    assert any("/label/cluster_id/values" in p for p, _ in requests)
    assert any("/label/cluster/values" in p for p, _ in requests)
    for path, args in requests:
        if path.endswith("/api/v1/query"):
            assert 'cluster_id="cpc-2"' in args["query"][0]
        if path.endswith("/loki/api/v1/query_range"):
            assert 'cluster="cpc-2"' in args["query"][0]


@pytest.mark.e2e
@pytest.mark.parametrize("llm_failed", [False, True])
def test_rca_without_observations_publishes_final_report(
    stack, monkeypatch, llm_failed
):
    monkeypatch.setattr(Upstream, "llm_fail", llm_failed)
    iid = str(uuid4())
    data = dict(
        scope=SCOPE,
        incident_id=iid,
        evidence_version=1,
        analysis_profile_revision="fixture-v1",
        incident_time=PERIOD["start"],
        time_range=PERIOD,
        purpose_ids=["R05"],
    )
    snapshot = {
        "input": data,
        "alert": {
            "labels": {
                "reason": "XID 79",
                "k8s_node_name": "fixture-node",
                "suggested_actions": json.dumps(
                    {"description": "", "repair_actions": ["REBOOT_SYSTEM"]}
                ),
            }
        },
    }
    with psycopg.connect(stack["url"]) as conn:
        conn.execute(
            "INSERT INTO incidents(id,cluster_id,scope,occurred_at,state,evidence_version) VALUES(%s,'cpc-2',%s,%s,'open',1)",
            (iid, Jsonb(SCOPE), data["incident_time"]),
        )
        conn.execute(
            "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES(%s,1,%s,%s)",
            (iid, Jsonb(snapshot), content_hash(snapshot)),
        )
    profile = {
        **stack["profile"],
        "rca": {"general_runbook_key": "UNPUBLISHED-FIXTURE"},
    }
    path = LOCAL / "no-runbook-profile.json"
    path.write_text(json.dumps(profile))
    isolated = {**stack, "env": {**stack["env"], "AGENT_CONFIG_FILE": str(path)}}
    start = len(Upstream.requests)
    jid = submit(stack, "rca", data)
    result, evidence = worker_result(isolated, "rca", jid, "-final-report")
    assert result["result_status"] == "blocked"
    assert result["quality"]["analysis"]["status"] == "no_usable_evidence"
    assert result["narrative_status"] == ("failed" if llm_failed else "complete")
    assert len(result["narrative"]) == 5
    assert not any(q.startswith("D") for q, _ in evidence)
    assert any(path == "/v1/chat/completions" for path, _ in Upstream.requests[start:])
    text = "\n".join(section["text"] for section in result["narrative"])
    assert "XID 79" in text and "원인은 미확정" in text
    assert "실행 적격성 미검증" in text and "REBOOT_SYSTEM" in text
    with psycopg.connect(stack["url"]) as conn:
        saved = conn.execute(
            "SELECT snapshot,content_hash FROM incident_evidence_versions WHERE incident_id=%s",
            (iid,),
        ).fetchone()
        assert saved == (snapshot, content_hash(snapshot))


@pytest.mark.e2e
def test_llm_failure_preserves_metrics_and_independent_topics(stack):
    Upstream.llm_fail = True
    Upstream.logs_fail = True
    try:
        data = dict(
            scope=SCOPE,
            time_range=PERIOD,
            timezone="UTC",
            topic_ids=["O09", "O10", "O11"],
            group_by=["cluster"],
        )
        jid = submit(stack, "report", data)
        result, evidence = worker_result(stack, "report", jid, "-failure")
        assert result["narrative_status"] == "failed"
        assert result["quality"]["narrative_reason"] == "llm_http_error"
        assert result["llm_usage"]["request_attempts"] == 3
        assert result["llm_usage"]["calls"] == 0
        assert (
            next(t for t in result["topics"] if t["topic_id"] == "O09")["metrics"][0][
                "value"
            ]
            == 0.25
        )
        assert (
            next(t for t in result["topics"] if t["topic_id"] == "O10")["status"]
            == "blocked"
        )
        assert any(q == "D09" and s == "unavailable" for q, s in evidence)
    finally:
        Upstream.llm_fail = False
        Upstream.logs_fail = False


@pytest.mark.e2e
def test_all_report_topics_and_runbook_sufficient_skips_mcp(stack):
    data = dict(
        scope=SCOPE,
        time_range=PERIOD,
        timezone="UTC",
        topic_ids=[f"O{i:02}" for i in range(1, 12)],
        group_by=["cluster"],
    )
    jid = submit(stack, "report", data)
    report, _ = worker_result(stack, "report", jid, "-all-topics")
    assert len(report["topics"]) == 11
    assert all(
        t["status"] in {"ready", "partial", "blocked", "not_applicable"}
        for t in report["topics"]
    )
    iid = str(uuid4())
    data = dict(
        scope=SCOPE,
        incident_id=iid,
        evidence_version=1,
        analysis_profile_revision="fixture-v1",
        incident_time="2026-09-15T00:15:00Z",
        time_range=PERIOD,
        purpose_ids=["R01"],
    )
    snapshot = {
        "input": data,
        "evidence": {
            "producer_contract": "fixture-known-v1",
            "verified_facts": {
                "error_code": "registered_error",
                "producer_contract": "fixture-known-v1",
            },
        },
    }
    book = {
        "required_evidence": ["error_code"],
        "applicability_conditions": [
            {"field": "error_code", "equals": "registered_error"}
        ],
        "claim": "등록 오류 조건이 충족됐습니다.",
        "recommendations": [
            {
                "text": "장비의 연결 상태를 확인하세요.",
                "preconditions": [
                    {"field": "error_code", "equals": "registered_error"}
                ],
            }
        ],
    }
    with psycopg.connect(stack["url"]) as conn:
        conn.execute(
            "INSERT INTO knowledge_revisions(id,knowledge_id,knowledge_key,revision,kind,state,visibility,content,content_hash,reviewed_content_hash,compatibility) VALUES(%s,%s,%s,1,'runbook','published','common',%s,%s,%s,%s)",
            (
                str(uuid4()),
                str(uuid4()),
                "fixture-" + uuid4().hex,
                Jsonb(book),
                content_hash(book),
                content_hash(book),
                Jsonb({"producer_contract": "fixture-known-v1"}),
            ),
        )
        conn.execute(
            "INSERT INTO incidents(id,cluster_id,scope,occurred_at,state,evidence_version) VALUES(%s,'cpc-2',%s,%s,'open',1)",
            (iid, Jsonb(SCOPE), data["incident_time"]),
        )
        conn.execute(
            "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES(%s,1,%s,%s)",
            (iid, Jsonb(snapshot), content_hash(snapshot)),
        )
    rid = submit(stack, "rca", data)
    request_start = len(Upstream.requests)
    result, evidence = worker_result(stack, "rca", rid, "-runbook")
    assert result["termination_reason"] == "evidence_sufficient"
    assert result["cause_candidates"][0]["causal_status"] == "supported"
    assert not any(q.startswith("D") for q, s in evidence)
    model_requests = [
        json.loads(body["messages"][1]["content"])
        for path, body in Upstream.requests[request_start:]
        if path == "/v1/chat/completions"
    ]
    assert len(model_requests) == 1 and "facts" in model_requests[0]
    assert result["narrative_status"] == "complete"


@pytest.mark.e2e
@pytest.mark.parametrize("kind", ["rca", "report"])
def test_gui_model_auth_and_pinned_revision_reach_real_worker(stack, kind, monkeypatch):
    key = "model-authentication-secret-fixture"
    monkeypatch.setattr(Upstream, "api_key", key)
    extension = ".exe" if sys.platform == "win32" else ""
    binary = Path(
        os.getenv("BACKEND_BINARY", str(ROOT / (".local/backend-e2e" + extension)))
    )
    assert binary.is_file(), "Build Backend for model authentication E2E"
    backend = f"http://127.0.0.1:{port()}/api/v1"
    endpoint = stack["env"]["LLM_BASE_URL"]
    host = urlparse(endpoint).netloc
    process = stack["spawn"](
        [str(binary)],
        {
            **os.environ,
            "DATABASE_URL": stack["url"],
            "DSX_ADDRESS": backend.removeprefix("http://").removesuffix("/api/v1"),
            "DSX_MIGRATE": "true",
            "DSX_SEED": "false",
            "DSX_SCHEDULER_ENABLED": "false",
            "DSX_MODEL_HOSTS": host,
            "LLM_API_KEY": key,
        },
        "model-backend-" + kind,
    )
    wait_http(backend + "/health/ready", process)
    with httpx.Client(base_url=backend, timeout=40) as client:

        def command(path, body, version=None, method="POST"):
            headers = {"Idempotency-Key": uuid4().hex}
            if version is not None:
                headers["If-Match"] = str(version)
            response = client.request(method, path, json=body, headers=headers)
            assert response.is_success, response.status_code
            assert key not in response.text
            return response.json()

        model = command(
            "/models",
            {
                "endpoint_url": endpoint,
                "model_name": "saved-model-" + kind,
                "secret_ref": "env:LLM_API_KEY",
            },
        )
        path = "/models/" + model["id"]
        checked = command(path + "/test-connection", {"revision": 1}, 1)
        assert checked["transport"]["http_status"] == 200
        assert checked["schema"]["status"] == "ok"
        # This is a real 401 from the authenticated upstream fixture, not bad JSON.
        anonymous = command(
            "/models", {"endpoint_url": endpoint, "model_name": "anonymous-" + kind}
        )
        failed = command(
            "/models/" + anonymous["id"] + "/test-connection", {"revision": 1}, 1
        )
        assert failed["schema"]["reason"] == "authentication_failed"
        routes = client.get("/model-routes").json()
        command(
            "/model-routes",
            {kind: {"model_id": model["id"], "model_revision": 1}},
            routes["version"],
            "PATCH",
        )
        try:
            data = dict(
                scope=SCOPE,
                time_range=PERIOD,
                timezone="UTC",
                topic_ids=["O09"],
                group_by=["cluster"],
            )
            if kind == "rca":
                iid = str(uuid4())
                data = dict(
                    scope=SCOPE,
                    incident_id=iid,
                    evidence_version=1,
                    analysis_profile_revision="fixture-v1",
                    incident_time="2026-09-15T00:15:00Z",
                    time_range=PERIOD,
                    purpose_ids=["R05"],
                )
                snapshot = {"input": data, "evidence": {"symptom": "gpu_access"}}
                with psycopg.connect(stack["url"]) as conn:
                    conn.execute(
                        "INSERT INTO incidents(id,cluster_id,scope,occurred_at,state,evidence_version) VALUES(%s,'cpc-2',%s,%s,'open',1)",
                        (iid, Jsonb(SCOPE), data["incident_time"]),
                    )
                    conn.execute(
                        "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES(%s,1,%s,%s)",
                        (iid, Jsonb(snapshot), content_hash(snapshot)),
                    )
            routed = {
                **stack,
                "env": {
                    **stack["env"],
                    "LLM_BASE_URL": "http://must-not-be-used.invalid/v1",
                    "LLM_MODEL": "must-not-be-used",
                    "LLM_API_KEY": key,
                    "DSX_MODEL_HOSTS": host,
                },
            }
            jid = submit(routed, kind, data)
            command(path, {"model_name": "later-revision"}, 1, "PATCH")
            start = len(Upstream.requests)
            result, _ = worker_result(routed, kind, jid, "-routed")
            calls = [
                body
                for path, body in Upstream.requests[start:]
                if path == "/v1/chat/completions"
            ]
            assert calls and all(
                body["model"] == "saved-model-" + kind for body in calls
            )
            if kind == "report":
                assert result["narrative_status"] == "complete"
            else:
                assert result["quality"]["analysis"]["status"] == "complete"
            with psycopg.connect(stack["url"]) as conn:
                for table in [
                    "service_profiles",
                    "profile_revisions",
                    "jobs",
                    "audit_events",
                ]:
                    rows = conn.execute(
                        sql.SQL("SELECT to_jsonb(t)::text FROM {} t").format(
                            sql.Identifier(table)
                        )
                    ).fetchall()
                    assert all(key not in row[0] for row in rows)
        finally:
            routes = client.get("/model-routes").json()
            command("/model-routes", {kind: None}, routes["version"], "PATCH")


@pytest.mark.e2e
def test_runbook_api_lifecycle_and_real_rca_consumption(stack):
    extension = ".exe" if sys.platform == "win32" else ""
    binary = Path(
        os.getenv("BACKEND_BINARY", str(ROOT / (".local/backend-e2e" + extension)))
    )
    assert binary.is_file(), "Build Backend for Runbook API E2E"
    backend = f"http://127.0.0.1:{port()}/api/v1"
    process = stack["spawn"](
        [str(binary)],
        {
            **os.environ,
            "DATABASE_URL": stack["url"],
            "DSX_ADDRESS": backend.removeprefix("http://").removesuffix("/api/v1"),
            "DSX_MIGRATE": "true",
            "DSX_SEED": "false",
            "DSX_SCHEDULER_ENABLED": "false",
        },
        "runbook-backend",
    )
    wait_http(backend + "/health/ready", process)
    with httpx.Client(base_url=backend, timeout=30) as client:
        # The complete corpus must fit the existing API and schema without publication.
        pilots = {"RB-XID-79", "RB-XID-48-63-64", "RB-SXID-11001"}
        bulk = LOCAL / ("catalog-" + uuid4().hex)
        folder, receipts = bulk / "input", bulk / "receipts"
        rows = []
        for path in sorted((ROOT / "rcca-agent/runbooks").rglob("RB-*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            if (
                row["knowledge_key"] in pilots
                or row["knowledge_key"] == "RB-GENERAL-GPU-NODE"
            ):
                continue
            code = row["content"]["search"]["codes"][0]
            target = folder / code.split(":")[0] / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(row), encoding="utf-8")
            rows.append(row)
        command = [
            sys.executable,
            "-m",
            "rcca_agent.runbook_import",
            str(folder),
            "--profile",
            stack["env"]["AGENT_CONFIG_FILE"],
            "--backend",
            backend,
            "--batch-key",
            "catalog-fixture",
            "--receipts",
            str(receipts),
        ]
        for expected in (263, 0):
            imported = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=240,
                env={**os.environ, "PYTHONUTF8": "1"},
                creationflags=subprocess.CREATE_NO_WINDOW
                if sys.platform == "win32"
                else 0,
            )
            assert imported.returncode == 0, imported.stderr
            assert json.loads(imported.stdout) == {
                "total": 263,
                "registered": expected,
                "resumed": 263 - expected,
            }
        imported_codes = set()
        for row in rows:
            code = row["content"]["search"]["codes"][0]
            found = client.get(
                "/knowledge", params={"kind": "runbook", "state": "draft", "code": code}
            ).json()["items"]
            assert len(found) == 1 and found[0]["knowledge_key"] == row["knowledge_key"]
            assert found[0]["content_hash"] == content_hash(row["content"])
            imported_codes.add(code)
        assert len(imported_codes) == 263
        assert "xid:133" in imported_codes and "sxid:22012" in imported_codes
        for key, code in [
            ("RB-XID-79", "xid:79"),
            ("RB-XID-48-63-64", "xid:48"),
            ("RB-SXID-11001", "sxid:11001"),
        ]:
            row = json.loads(
                (
                    ROOT / f"rcca-agent/runbooks/{code.split(':')[0]}/{key}.json"
                ).read_text(encoding="utf-8")
            )
            imported = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "rcca_agent.runbook_admin",
                    "draft",
                    str(ROOT / f"rcca-agent/runbooks/{code.split(':')[0]}/{key}.json"),
                    "--profile",
                    stack["env"]["AGENT_CONFIG_FILE"],
                    "--backend",
                    backend,
                    "--request-key",
                    key + "-draft",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                env={**os.environ, "PYTHONUTF8": "1"},
                creationflags=subprocess.CREATE_NO_WINDOW
                if sys.platform == "win32"
                else 0,
            )
            assert imported.returncode == 0, imported.stderr
            first = json.loads(imported.stdout)
            assert first == draft(client, row, stack["profile"], key + "-draft")
            requested = transition(
                client,
                first,
                stack["profile"],
                "request",
                key + "-request",
                "fixture draft",
            )
            with pytest.raises(ValueError, match="unbound"):
                transition(
                    client,
                    requested,
                    stack["profile"],
                    "approve",
                    key + "-bad-approve",
                    "unbound must fail",
                )
            # Binding is ONLY for the isolated fixture cluster, never a shipped default.
            row["compatibility"] = {"cluster_id": "cpc-2"}
            bound = draft(
                client, row, stack["profile"], key + "-bound", first["knowledge_id"]
            )
            assert bound["revision"] == 2
            for action in ("request", "approve", "publish"):
                prior = bound
                bound = transition(
                    client,
                    prior,
                    stack["profile"],
                    action,
                    key + "-" + action + "-bound",
                    "fixture-only validation",
                )
                assert bound == transition(
                    client,
                    prior,
                    stack["profile"],
                    action,
                    key + "-" + action + "-bound",
                    "fixture-only validation",
                )
            assert bound["state"] == "published"
            found = client.get(
                "/knowledge", params={"kind": "runbook", "code": code}
            ).json()["items"]
            assert len(found) == 1 and found[0]["content_hash"] == content_hash(
                row["content"]
            )
            iid = str(uuid4())
            data = dict(
                scope=SCOPE,
                incident_id=iid,
                evidence_version=1,
                analysis_profile_revision="fixture-v1",
                incident_time="2026-09-15T00:15:00Z",
                time_range=PERIOD,
                purpose_ids=["R01"],
                target={"gpu_uuid": "GPU-1"},
            )
            snapshot = {
                "input": data,
                "alert": {"labels": {"reason": code.replace(":", " ")}},
            }
            with psycopg.connect(stack["url"]) as conn:
                conn.execute(
                    "INSERT INTO incidents(id,cluster_id,scope,occurred_at,state,evidence_version) VALUES(%s,'cpc-2',%s,%s,'open',1)",
                    (iid, Jsonb(SCOPE), data["incident_time"]),
                )
                conn.execute(
                    "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES(%s,1,%s,%s)",
                    (iid, Jsonb(snapshot), content_hash(snapshot)),
                )
            jid = submit(stack, "rca", data)
            before = len(Upstream.requests)
            result, evidence = worker_result(stack, "rca", jid, "-" + key)
            assert any(q.startswith("D") for q, _ in evidence)
            assert all(
                c["causal_status"] == "candidate" for c in result["cause_candidates"]
            )
            payloads = [
                json.loads(b["messages"][1]["content"])
                for path, b in Upstream.requests[before:]
                if path == "/v1/chat/completions" and not b.get("tools")
            ]
            plans = [
                plan
                for payload in payloads
                for plan in payload.get("runbook_plans", [])
            ]
            assert any(
                plan["id"] == bound["revision_id"]
                and plan["revision"] == 2
                and plan["analysis_guidance"] == row["content"]["analysis_guidance"]
                for plan in plans
            )
            retired = transition(
                client,
                bound,
                stack["profile"],
                "retire",
                key + "-retire",
                "fixture complete",
            )
            assert retired["state"] == "retired"
            assert (
                client.get(
                    "/knowledge", params={"kind": "runbook", "code": code}
                ).json()["items"]
                == []
            )
