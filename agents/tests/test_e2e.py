"""Real PostgreSQL + Incident + JC + Worker processes + NAT + official Grafana MCP.

Only upstream Grafana datasource responses and the inference endpoint are fixtures.
No production metrics or model-quality claims are made by this suite.
"""

from rca_report_fixture import report_reply

from evaluation_fixtures import (
    interpretation_reply as rca_interpretation_reply,
    review_reply,
)

import contextlib
import csv
import io
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

from agent_common.contracts import content_hash, timestamp
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


def interpretation_reply(data):
    from test_report_interpretation import reply_for
    from test_namespace_advice import section

    if "summary_repair" in data or "section_repair" in data:
        return {
            **(
                {
                    "advice": [
                        section([item])["advice"][0] for item in data["summary_repair"]
                    ]
                }
                if data.get("summary_repair")
                else {}
            ),
            **(
                reply_for(
                    {"topics": [item["topic"] for item in data["section_repair"]]}
                )
                if data.get("section_repair")
                else {}
            ),
        }
    return reply_for(data)


def policy_interpretation_reply(data):
    response = rca_interpretation_reply()
    policies = data.get("decision_assessment", {}).get("policies", [])
    if not policies:
        return response
    refs = data.get("observation_refs", [])
    if refs:
        response["findings"] = [
            {
                "id": "reported",
                "kind": "observed",
                "statement": "오류 보고를 확인했습니다. 근본 원인과 현재 상태는 미확정입니다.",
                "evidence_refs": refs,
            }
        ]
    response["criterion_assessments"] = [
        {
            "criterion_id": row["key"],
            "status": "satisfied" if refs else "unknown",
            "finding_refs": ["reported"] if refs else [],
            "evidence_refs": refs,
        }
        for policy in policies
        for row in policy["criteria"]
        if row["method"] == "llm"
    ]
    return response


def combined_reply(data):
    return {
        "interpretation": policy_interpretation_reply(data),
        "hypotheses": [],
        "limitations": ["원인과 현재 상태는 미확정입니다."],
    }


def combined_candidate_reply(data):
    response = analysis_reply(data["observation_refs"])
    response["interpretation"] = {
        "findings": [
            {
                "id": "observed",
                "statement": "대상 노드의 오류 보고가 기록됐습니다.",
                "kind": "observed",
                "evidence_refs": data["observation_refs"],
            }
        ],
        "unknowns": [],
        "conflicts": [],
        "limitations": [],
    }
    for hypothesis in response["hypotheses"]:
        hypothesis["finding_refs"] = ["observed"]
    return response


class Upstream(BaseHTTPRequestHandler):
    requests = []
    llm_fail = False
    author_http_fail = False
    reject_tool_requests = False
    api_key = "fixture-only"
    logs_fail = False
    logs_max_limit = None
    logs_json_target = None
    logs_max_seconds = None
    logs_padding_bytes = 16384
    prometheus_max_seconds = None
    prometheus_rows = {}
    fleet_reports = False
    fleet_component = "accelerator-nvidia-error-sxid"
    fleet_reason = "SXID 11001(ingress invalid command)"
    cluster_id = "cpc-2"

    def log_message(self, *args):
        pass

    def send(self, body, status=200):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        # A size-limited MCP client may close an oversized fixture response early.
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(data)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path.endswith(("/api/v1/query", "/api/v1/query_range")):
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
            if body.get("tools") and self.reject_tool_requests:
                return self.send({"error": "fixture tool protocol failure"}, 500)
            data = json.loads(body["messages"][1]["content"])
            if self.author_http_fail and data.get("generation_mode") == "combined":
                return self.send({"error": "fixture author failure"}, 400)
            message = {
                "role": "assistant",
                "content": json.dumps(
                    report_reply(data)
                    if "source_items" in data and "material_hash" in data
                    else review_reply(data)
                    if "rubric_version" in data
                    else combined_reply(data)
                    if data.get("generation_mode") == "combined"
                    else policy_interpretation_reply(data)
                    if "Interpret incident evidence" in body["messages"][0]["content"]
                    else analysis_reply(data["observation_refs"])
                    if "observation_refs" in data
                    else {"query_ids": data["available_queries"][:3]}
                    if "available_queries" in data
                    else interpretation_reply(data)
                    if data.get("interpretation_version")
                    in {
                        "ops-interpretation-v2",
                        "ops-interpretation-memory-v1",
                        "ops-interpretation-workload-v1",
                        "ops-interpretation-workload-v2",
                    }
                    or "summary_repair" in data
                    or "section_repair" in data
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
                {
                    "status": "success",
                    "data": [self.cluster_id] if label == expected else [],
                }
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
        if u.path.endswith("/api/v1/query_range") and "/loki/" not in u.path:
            from test_aggregate_report import fixture
            from ops_agent.report_contract import iso

            start = float(query["start"][0])
            end = float(query["end"][0])
            period = {"start": iso(start - 3600), "end": iso(end)}
            expr = query["query"][0]
            assert float(query["step"][0]) == 3600
            assert "offset 1ms" in expr
            if "kube_pod_labels" in expr:
                from test_workload_context import source

                rows = source(cluster_id="cpc-2", namespace="dev")["snapshot"]["series"]
                for row in rows:
                    value = row["values"][0][1]
                    row["values"] = [
                        [at, value] for at in range(int(start), int(end) + 1, 3600)
                    ]
                return self.send(
                    {
                        "status": "success",
                        "data": {"resultType": "matrix", "result": rows},
                    }
                )
            if '"pending_peak"' in expr or '"created_min"' in expr:
                from test_workload_summary import states, jobs

                sample = states() if '"pending_peak"' in expr else jobs()
                rows = sample["snapshot"]["series"]
                original = rows[0]["values"][0][0]
                for row in rows:
                    row["metric"].update(cluster_id="cpc-2", namespace="dev")
                    for point in row["values"]:
                        point[0] = start
                        if '"created_min"' in expr:
                            point[1] = str(float(point[1]) + start - original)
                return self.send(
                    {
                        "status": "success",
                        "data": {"resultType": "matrix", "result": rows},
                    }
                )
            name = (
                "hourly_gpu_memory"
                if "DCGM_FI_DEV_FB_USED" in expr
                else "hourly_gpu_activity"
                if "label_replace" in expr
                else "hourly_pod_identity"
                if "kube_pod_info" in expr
                else "hourly_gpu_identity_count"
            )
            evidence = fixture(period, cluster="cpc-2", namespace="dev")
            if name == "hourly_gpu_memory":
                from test_gpu_memory import memory_fixture

                evidence.append(memory_fixture(evidence))
            rows = next(
                e["snapshot"]["series"] for e in evidence if e["query_id"] == name
            )
            if name == "hourly_gpu_activity" and 'namespace=~"dev"' in expr:
                rows = [r for r in rows if r["metric"].get("namespace") == "dev"]
            return self.send(
                {"status": "success", "data": {"resultType": "matrix", "result": rows}}
            )
        if u.path.endswith("/api/v1/query"):
            expr = query.get("query", [""])[0]
            if getattr(self, "transition_fixture", None) and "[1h] offset 1ms" in expr:
                from test_identity_transitions import transition_fixture
                from ops_agent.report_contract import iso

                at = float(query["time"][0])
                _, gpu, pods, _ = transition_fixture(
                    {"start": iso(at - 3600), "end": iso(at)},
                    cluster="cpc-2",
                    namespace="dev",
                )
                if self.transition_fixture == "overlap":
                    gpu[1]["values"][0][0] = gpu[0]["values"][-1][0]
                return self.send(
                    {
                        "status": "success",
                        "data": {
                            "resultType": "matrix",
                            "result": pods if "kube_pod_info" in expr else gpu,
                        },
                    }
                )
            metric = expr.split("{", 1)[0]
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
            fleet_values = {"dcgm_fi_dev_gpu_temp": 40, "dcgm_fi_dev_power_usage": 250}
            if metric in fleet_values:
                labels = {"cluster_id": "cpc-2", "uuid": "GPU-1", "node": "node-1"}
            value = fleet_values.get(
                metric, 2 if metric == "DCGM_FI_DEV_GPU_UTIL" else 1
            )
            values = [[start + i * 30, str(value)] for i in range(121)]
            if self.prometheus_max_seconds is not None:
                length = int(expr.rsplit("[", 1)[1][:-2])
                stop = float(query["time"][0])
                values = [row for row in values if stop - length < row[0] <= stop]
                if length - 1 > self.prometheus_max_seconds:
                    labels["padding"] = "x" * (11 * 1024 * 1024)
            rows = self.prometheus_rows.get(
                metric, [{"metric": labels, "values": values}]
            )
            if metric in {"DCGM_FI_DEV_GPU_TEMP", "DCGM_FI_DEV_POWER_USAGE"} or (
                metric in fleet_values and "namespace=" in expr.split("}", 1)[0]
            ):
                rows = []
            return self.send(
                {
                    "status": "success",
                    "data": {
                        "resultType": "matrix",
                        "result": rows,
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
                    "x" * self.logs_padding_bytes
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
                            "component": self.fleet_component,
                            "health": "Unhealthy",
                            "log_type": "component_data",
                            "reason": self.fleet_reason,
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
                                "stream": {
                                    "cluster": self.cluster_id,
                                    "namespace": "dev",
                                },
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
        profile = json.loads(
            (ROOT / "agents/tests/fixtures/config-v7.json").read_text()
        )
        # Current Runbook drafts include auxiliary queries absent from v7.
        # These synthetic definitions test lifecycle/consumption, not live bindings.
        for query_id, unit in (
            ("D23", "celsius"),
            ("D33", "bytes/s"),
            ("D34", "bytes/s"),
            ("D36", "count"),
            ("D38", "count"),
            ("D40", "count"),
            ("D42", "count"),
            ("D44", "count"),
            ("D45", "bitmask"),
            ("D48", "W"),
        ):
            profile["queries"][query_id] = dict(
                source="mimir",
                metric="fixture_" + query_id.lower(),
                unit=unit,
                max_hold_seconds=30,
                revision="fixture-v1",
                validated=True,
            )
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


def submit(stack, kind, data, *, execution_profile="local-v1"):
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    body = dict(
        contract_version="1.3",
        source_module="incident" if kind == "rca" else "backend",
        source_key=str(uuid4()),
        kind=kind,
        input=data,
        deadline_at=deadline,
        execution_profile_revision=execution_profile,
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
@pytest.mark.parametrize("activate", [False, True])
@pytest.mark.parametrize("parameter_scope", [False, True, "discover"])
def test_binding_profile_through_both_real_workers(
    stack, activate, parameter_scope, monkeypatch
):
    from test_binding_contract import profile, verified

    config = profile()
    config["health_contracts"] = stack["profile"]["health_contracts"]
    if activate:
        for query, unit in (
            ("D02", "percent"),
            ("D03", "MiB"),
            ("D04", "celsius"),
            ("D06", "info"),
            ("D10", "boolean"),
            ("D11", "W"),
            ("D15", "MiB"),
            ("D16", "MiB"),
            ("D18", "percent"),
            ("D19", "load"),
            ("D20", "boolean"),
        ):
            b = verified(config, query, unit=unit, cluster="cpc-2")
            b["environment"].update(
                datasource_uid="mimir", selector={"cluster_id": "cpc-2"}
            )
            b["target_labels"].update(uid="pod_uid", window="load_duration")
            if query in {"D04", "D11"}:
                b["target_labels"] = {"gpu_uuid": "uuid", "node": "node"}
            elif query == "D20":
                b["target_labels"] = {
                    key: key for key in ("node", "condition", "status")
                }
                b["invalid_values"]["maximum"] = 1
        # Multi-device synthetic observations must survive candidate validation/publication.
        start = datetime.fromisoformat(
            PERIOD["start"].replace("Z", "+00:00")
        ).timestamp()
        rows = {}
        for query, value in (
            ("D03", 4),
            ("D15", 12),
            ("D16", 16),
            ("D18", 25),
            ("D19", 2),
        ):
            binding = config["bindings"][config["queries"][query]["selected_binding"]]
            rows[binding["metric"]] = [
                {
                    "metric": {
                        "cluster_id": "cpc-2",
                        "UUID": f"GPU-{device}",
                        "node": f"node-{device}",
                        "load_duration": window,
                    },
                    "values": [[start + i * 30, str(value)] for i in range(121)],
                }
                for device in (1, 2)
                for window in (("1m", "5m", "15m") if query == "D19" else ("",))
            ]
        binding = config["bindings"][config["queries"]["D20"]["selected_binding"]]
        rows[binding["metric"]] = [
            {
                "metric": {
                    "cluster_id": "cpc-2",
                    "node": f"node-{device}",
                    "condition": "Ready",
                    "status": status,
                },
                "values": [[start + i * 30, str(value)] for i in range(121)],
            }
            for device in (1, 2)
            for status, value in (("true", 1), ("false", 0))
        ]
        monkeypatch.setattr(Upstream, "prometheus_rows", rows)
        b = verified(config, "D09", unit="log", cluster="cpc-2", sample_type="log")
        b.update(
            timestamp_basis="loki_recorded_at",
            event_timestamp_rule="loki_recorded_at",
            json_target_fields={},
        )
        b["environment"].update(datasource_uid="loki", selector={"cluster": "cpc-2"})
        for rule in ("sample_interval", "invalid_values", "counter_reset"):
            b[rule] = {"mode": "not_applicable", "reason": "fixture log stream"}
        if parameter_scope:
            for b in config["bindings"].values():
                if b["verification"]["status"] != "verified":
                    continue
                label = "cluster" if b["source"] == "loki" else "cluster_id"
                b["environment"].pop("cluster_id")
                b["environment"]["selector"] = {}
                b["environment"]["scope_labels"] = {"cluster_id": label}
                if parameter_scope == "discover":
                    b["environment"].update(
                        datasource_mode="discover",
                        datasource_uid=None,
                        scope_labels={"cluster_id": ["cluster_id", "cluster"]},
                    )
                b["verification"]["applicability"] = "Shared synthetic source contract"
            config["auto_select_verified_bindings"] = True
            for query in config["queries"].values():
                query["selected_binding"] = None
    path = LOCAL / f"binding-profile-{activate}-{parameter_scope}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    isolated = {**stack, "env": {**stack["env"], "AGENT_CONFIG_FILE": str(path)}}
    request_start = len(Upstream.requests)
    data = dict(
        scope={"clusters": [{"cluster_id": "cpc-2", "namespaces": None}]},
        time_range=PERIOD,
        timezone="UTC",
        topic_ids=["O01", "O09"],
        group_by=["cluster"],
    )
    jid = submit(stack, "report", data)
    report, evidence = worker_result(isolated, "report", jid, f"-binding-{activate}")
    assert not {"D01", "D05", "D08"} & {q for q, _ in evidence}
    assert {"D02", "D15", "D16"} <= {q for q, _ in evidence}
    metrics = [m for topic in report["topics"] for m in topic["metrics"]]
    energy = next(m for m in metrics if m["id"].endswith("gpu_energy"))
    assert (energy["value"] is not None) == activate
    assert len({m["id"] for m in metrics}) == len(metrics)
    for name, count, value in (
        ("gpu_memory_free_mean", 2, 12),
        ("node_cpu_used_mean", 2, 25),
        ("node_load_by_window", 6, 2),
        ("gpu_memory_used_ratio", 2, 0.25),
    ):
        optional = [m for m in metrics if m["id"].split(".")[1] == name]
        assert len(optional) == (count if activate else 1)
        assert all(m["quality"]["optional"] for m in optional)
        assert all(m["value"] == (value if activate else None) for m in optional)
        assert {m["id"] for m in optional} == {
            f"O01.{name}.{i}" for i in range(len(optional))
        }
        if activate:
            assert all(m["target"]["cluster_id"] == "cpc-2" for m in optional)
            assert all(m["evidence_refs"] for m in optional)
    with psycopg.connect(stack["url"]) as conn:
        qualities = conn.execute(
            "SELECT quality FROM evidence WHERE job_id=%s AND query_id='D02'", (jid,)
        ).fetchall()
        condition_refs = {
            row[0]
            for row in conn.execute(
                "SELECT id::text FROM evidence WHERE job_id=%s AND query_id='D20'",
                (jid,),
            ).fetchall()
        }
    conditions = next(t for t in report["topics"] if t["topic_id"] == "O01")["quality"][
        "node_condition_observations"
    ]
    if activate:
        assert len(conditions) == 4
        assert {
            (c["labels"]["node"], c["labels"]["condition"], c["labels"]["status"])
            for c in conditions
        } == {
            (f"node-{device}", "Ready", status)
            for device in (1, 2)
            for status in ("true", "false")
        }
        assert condition_refs
        for condition in conditions:
            assert (
                condition["cluster_id"] == condition["labels"]["cluster_id"] == "cpc-2"
            )
            assert condition["intervals"] == [
                [
                    start + i * 30,
                    start + (i + 1) * 30,
                    float(condition["labels"]["status"] == "true"),
                ]
                for i in range(120)
            ]
            assert set(condition["evidence_refs"]) == condition_refs
    else:
        assert conditions == []
    assert qualities
    if activate:
        assert all(
            q[0]["binding_id"] == "nvidia_dcgm_exporter.D02"
            and q[0]["binding_revision"] == "fixture-binding-1"
            for q in qualities
        )
        if parameter_scope:
            assert all(
                q[0]["selection_method"] == "automatic_verified" for q in qualities
            )
        if parameter_scope == "discover":
            assert all(
                q[0]["datasource_resolution"] == "discover"
                and q[0]["datasource_uid"] == "mimir"
                for q in qualities
            )
    else:
        assert all(q[0]["reason"] == "binding_unselected" for q in qualities)
    if activate and parameter_scope == "discover":
        minimal_data = {
            **data,
            "topic_ids": ["O01", "O05", "O08", "O11"],
            "topic_group_by": {
                "O01": ["cluster"],
                "O05": ["cluster"],
                "O08": ["namespace"],
                "O11": ["cluster"],
            },
        }
        minimal_id = submit(
            stack, "report", minimal_data, execution_profile="report-namespace-v2"
        )
        minimal, minimal_evidence = worker_result(
            isolated, "report", minimal_id, "-binding-minimal"
        )
        assert minimal["versions"]["criteria"] == "1.3"
        assert minimal["quality"]["report"]["presentation"] == "operator_checks_v1"
        assert any(
            f.get("next_check") for t in minimal["topics"] for f in t["findings"]
        )
        assert "먼저 확인할 운영 사항" in str(minimal["narrative"])
        incident_topic = next(t for t in minimal["topics"] if t["topic_id"] == "O05")
        with psycopg.connect(stack["url"]) as conn:
            snapshot = conn.execute(
                "SELECT snapshot FROM evidence WHERE job_id=%s AND query_id='report_db_snapshot'",
                (minimal_id,),
            ).fetchone()[0]
        expected_incidents = {i["id"] for i in snapshot["incidents"]}
        assert {
            f["incident_id"]
            for f in incident_topic["findings"]
            if f["category"] == "incident_followup"
        } == expected_incidents
        assert any(
            f["category"] == "no_incidents" for f in incident_topic["findings"]
        ) == (not expected_incidents)
        assert not {"D15", "D18", "D19"} & {q for q, _ in minimal_evidence}
        equipment = next(t for t in minimal["topics"] if t["topic_id"] == "O01")
        assert "node_condition_observations" not in equipment["quality"]
        conditions = [
            m for m in equipment["metrics"] if ".node_condition_seconds." in m["id"]
        ]
        assert len(conditions) == 4
        assert {m["value"] for m in conditions} == {0, 3600}
        assert all(m["evidence_refs"] for m in conditions)
        with psycopg.connect(stack["url"]) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM evidence WHERE job_id=%s AND query_id='D20' AND snapshot IS NOT NULL",
                    (minimal_id,),
                ).fetchone()[0]
                > 0
            )
    iid = str(uuid4())
    rca = dict(
        scope=SCOPE,
        incident_id=iid,
        evidence_version=1,
        analysis_profile_revision="fixture-v1",
        incident_time=PERIOD["start"],
        time_range=PERIOD,
        purpose_ids=["R05"],
    )
    snapshot = {"input": rca, "alert": {"labels": {"reason": "fixture observation"}}}
    with psycopg.connect(stack["url"]) as conn:
        conn.execute(
            "INSERT INTO incidents(id,cluster_id,scope,occurred_at,state,evidence_version) VALUES(%s,'cpc-2',%s,%s,'open',1)",
            (iid, Jsonb(SCOPE), rca["incident_time"]),
        )
        conn.execute(
            "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES(%s,1,%s,%s)",
            (iid, Jsonb(snapshot), content_hash(snapshot)),
        )
    rid = submit(stack, "rca", rca)
    result, evidence = worker_result(isolated, "rca", rid, f"-binding-{activate}")
    assert not {"D01", "D05", "D08"} & {q for q, _ in evidence}
    assert "D09" in {q for q, _ in evidence}
    assert result["incident_id"] == iid
    assert result["result_status"] != "resolved"
    if activate and parameter_scope == "discover":
        with psycopg.connect(stack["url"]) as conn:
            logs = conn.execute(
                "SELECT quality FROM evidence WHERE job_id=%s AND query_id='D09'",
                (rid,),
            ).fetchall()
        assert logs and all(
            q[0]["datasource_resolution"] == "discover"
            and q[0]["datasource_uid"] == "loki"
            and q[0]["selection_method"] == "automatic_verified"
            for q in logs
        )
    if not activate:
        assert not any(
            "/api/v1/query" in p for p, _ in Upstream.requests[request_start:]
        )


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
@pytest.mark.parametrize("padding_bytes", [16384, 11 * 1024 * 1024])
async def test_fleet_json_logs_split_through_nat_and_official_mcp(
    stack, monkeypatch, padding_bytes
):
    from nat.plugins.mcp.client.client_base import MCPStreamableHTTPClient

    from agent_common.observation import MCPResponseError, Observation, unwrap
    from agent_common.parsers import log_lines, parse_health

    target = {"node": 'node-"fixture\\1', "component": "accelerator-nvidia-error-xid"}
    monkeypatch.setattr(Upstream, "logs_json_target", target)
    monkeypatch.setattr(Upstream, "logs_max_seconds", 900)
    monkeypatch.setattr(Upstream, "logs_padding_bytes", padding_bytes)
    profile = json.loads(json.dumps(stack["profile"]))
    profile["limits"].update(max_bytes=4096, max_queries=40)
    profile["queries"]["D13"]["json_target_fields"] = dict(
        profile["queries"]["D09"]["json_target_fields"]
    )
    for query_id in ("D05", "D09", "D13"):
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
        raw_responses = []
        query_logs = tools["query_loki_logs"]

        async def logs_with_response(args):
            raw = await query_logs(args)
            raw_responses.append(raw)
            return raw

        tools["query_loki_logs"] = logs_with_response
        observation = Observation(tools, profile, data, time.monotonic() + 60)
        for query_id in ("D05", "D09", "D13"):
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
                and row["body"] == "fixture"
                for row in logs
            )
            health = parse_health(evidence, profile["health_contracts"])
            if query_id == "D13":
                assert health == []  # Event logs are not health observations.
            else:
                assert health and all(
                    row["check_status"] == row["normalized_health"] == "unknown"
                    for row in health
                )
        errors = [
            raw
            for raw in raw_responses
            if raw.startswith("MCPToolClient tool call failed:")
        ]
        if padding_bytes > 10 * 1024 * 1024:
            # Exercise the real MCP upstream HTTP ceiling, before our JSON byte check.
            assert errors
            for raw in errors:
                with pytest.raises(MCPResponseError, match="^response_byte_limit$"):
                    unwrap(raw)
        else:
            assert not errors
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
async def test_large_prometheus_response_splits_through_official_mcp(
    stack, monkeypatch
):
    from agent_common.contracts import timestamp
    from agent_common.grafana_mcp import GrafanaMCPClient
    from agent_common.observation import Observation, series, unwrap

    monkeypatch.setattr(Upstream, "prometheus_max_seconds", 1800)
    request_start = len(Upstream.requests)
    async with GrafanaMCPClient(stack["env"]["GRAFANA_MCP_URL"]) as client:
        tools = {}
        for name in (
            "query_prometheus",
            "list_datasources",
            "list_prometheus_label_values",
        ):
            tools[name] = (await client.get_tool(name)).acall
        raw_responses = []
        query_prometheus = tools["query_prometheus"]

        async def query_with_response(args):
            raw = await query_prometheus(args)
            raw_responses.append(raw)
            return raw

        tools["query_prometheus"] = query_with_response
        observation = Observation(
            tools,
            stack["profile"],
            {"scope": SCOPE, "time_range": PERIOD},
            time.monotonic() + 60,
        )
        evidence = await observation.collect("D06")
        assert observation.calls == len(raw_responses) > 1
        # Official MCP returns the large Prometheus payload; Observation splits it.
        assert len(raw_responses[0].encode()) > 10 * 1024 * 1024
        assert unwrap(raw_responses[0])["data"]
        assert len(evidence) > 1 and all(
            e["tool_status"] == "ok" and e["quality"]["complete"] for e in evidence
        ), evidence
        assert evidence[0]["time_range"]["start"] == PERIOD["start"]
        assert all(
            previous["time_range"]["end"] == following["time_range"]["start"]
            for previous, following in zip(evidence, evidence[1:])
        )
        assert evidence[-1]["time_range"]["end"] == PERIOD["end"]
        rows = series(evidence)
        assert len(rows) == 1 and "padding" not in rows[0]["labels"]
        assert rows[0]["samples"] == [
            [timestamp(PERIOD["start"]) + i * 30, "1"] for i in range(121)
        ]
    requests = [
        args
        for path, args in Upstream.requests[request_start:]
        if path.endswith("/api/v1/query")
    ]
    expressions = [args["query"][0] for args in requests]
    durations = [int(expr.rsplit("[", 1)[1][:-2]) - 1 for expr in expressions]
    assert len(requests) == observation.calls
    assert durations[0] == 3600 and all(
        0 < seconds <= 1800 for seconds in durations[1:]
    )
    assert len({expr.rsplit("[", 1)[0] for expr in expressions}) == 1
    assert all(
        'cluster_id="cpc-2"' in expr and 'namespace=~"dev"' in expr
        for expr in expressions
    )


@pytest.mark.e2e
@pytest.mark.parametrize("multi", [False, True])
def test_namespace_report_through_backend_with_report_only_criteria(stack, multi):
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
        time_range={"start": PERIOD["start"], "end": "2026-09-16T00:00:00Z"},
        timezone="UTC",
        topic_ids=["O08"],
        group_by=["namespace"],
    )
    if multi:
        data["topic_ids"] = [f"O{i:02}" for i in range(1, 12)]
        data["group_by"] = ["cluster"]
        data["topic_group_by"] = {
            t: ["namespace" if t == "O08" else "cluster"] for t in data["topic_ids"]
        }
    response = httpx.post(
        backend + "/reports", json=data, headers={"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 202, response.text
    jid = response.json()["job_id"]
    result, evidence = worker_result(stack, "report", jid, "-namespace")
    assert result["versions"]["execution_profile_revision"] == "report-namespace-v1"
    assert result["quality"]["requested_group_by"] == data["group_by"]
    collection = result["quality"]["collection"]
    assert collection["plan_status"] == "accepted"
    assert collection["query_limit"] == 2048
    assert collection["complete"]
    if multi:
        assert result["quality"]["topic_group_by"] == data["topic_group_by"]
        assert {t["topic_id"] for t in result["topics"]} == set(data["topic_ids"])
        comparison = next(t for t in result["topics"] if t["topic_id"] == "O10")
        assert comparison["status"] == "blocked"
        assert (
            "performed_action_and_comparison_required" in comparison["missing_inputs"]
        )
        assert all(t["quality"]["display_basis"] for t in result["topics"])
        assert "D09" not in {t["query_id"] for t in collection["tasks"]}
    else:
        assert {t["query_id"] for t in collection["tasks"]} == {
            "D01",
            "D02",
            "D06",
            "D08",
        }
    assert all(t["incomplete_seconds"] == 0 for t in collection["tasks"])
    html = httpx.get(backend + f"/reports/{jid}/export?format=html")
    assert html.status_code == 200
    assert "분석 범위와 결과" in html.text and "권고와 실행 조건" in html.text
    assert "연결 GPU 평균 활동률" in html.text
    if multi:
        assert "표시 기준" in html.text and "소주제별 기준 적용" in html.text
        csv_response = httpx.get(backend + f"/reports/{jid}/export?format=csv")
        assert csv_response.status_code == 200 and "display_basis" in csv_response.text
    assert "Namespace의 실제 소비량" in html.text
    with psycopg.connect(stack["url"]) as conn:
        assert conn.execute(
            "SELECT versions->>'criteria' FROM jobs WHERE kind='rca' LIMIT 1"
        ).fetchone() in (None, ("unconfigured",))
    assert result["versions"]["criteria"] == "1.2"
    topic = next(t for t in result["topics"] if t["topic_id"] == "O08")
    metrics = {m["id"].split(".")[1]: m for m in topic["metrics"]}
    assert metrics["namespace_connected_gpu_count"]["value"] == 1
    assert metrics["cluster_observed_gpu_count"]["value"] == 1
    assert metrics["cluster_connected_gpu_count"]["value"] == 1
    assert metrics["cluster_connected_gpu_count"]["target"] == {"cluster_id": "cpc-2"}
    assert "클러스터 관측 GPU" in html.text
    assert "GPU·시간" in html.text
    # The fixture has 121 samples held for 30 seconds, not a full day of data.
    observed_hours = 121 * 30 / 3600
    assert metrics["observed_namespace_hours"]["value"] == observed_hours
    assert metrics["namespace_activity_valid_hours"]["value"] == observed_hours
    assert metrics["namespace_connected_gpu_util"]["value"] == 2

    assert metrics["namespace_connected_gpu_util"]["target"] == {
        "cluster_id": "cpc-2",
        "namespace": "dev",
    }
    assert (
        topic["status"] == "ready"
    )  # Complete observed metrics, not exclusive ownership.
    assert not topic["recommendations"]
    assert any(q == "D02" and status == "ok" for q, status in evidence)
    for artifact in result["artifacts"]:
        body = (LOCAL / "artifacts" / artifact["object_key"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == artifact["checksum"]
        assert b"O08.namespace_connected_gpu_util.0" in body


@pytest.mark.e2e
def test_basic_report_v2_intake_publication_and_exports(stack, monkeypatch):
    """Real Backend/JC/Worker with synthetic upstreams and an isolated database."""
    start = timestamp(PERIOD["start"])
    monkeypatch.setattr(
        Upstream,
        "prometheus_rows",
        {
            "DCGM_FI_DEV_GPU_UTIL": [
                {
                    "metric": {
                        "cluster_id": "cpc-2",
                        "UUID": "GPU-1",
                        "namespace": "dev",
                        "pod": "training",
                        "node": "node-1",
                        "pod_uid": "pod-uid-1",
                        "modelName": "fixture-model",
                    },
                    "values": [[start + i * 30, "2"] for i in range(121)],
                }
            ]
        },
    )
    backend = f"http://127.0.0.1:{port()}/api/v1"
    extension = ".exe" if sys.platform == "win32" else ""
    binary = os.getenv("BACKEND_BINARY", str(ROOT / (".local/backend-e2e" + extension)))
    process = stack["spawn"](
        [binary],
        {
            **os.environ,
            "DATABASE_URL": stack["url"],
            "DSX_ADDRESS": backend.removeprefix("http://").removesuffix("/api/v1"),
            "DSX_MIGRATE": "false",
            "DSX_SEED": "false",
            "DSX_SCHEDULER_ENABLED": "false",
            "DSX_JOB_CONTROLLER_URL": stack["jc"].removesuffix("/internal/v1"),
            "DSX_NAMESPACE_REPORT_PROFILE_REVISION": "report-namespace-v2",
        },
        "basic-backend",
    )
    wait_http(backend + "/health/ready", process)
    data = dict(
        scope=SCOPE,
        time_range={"start": PERIOD["start"], "end": "2026-09-16T00:00:00Z"},
        timezone="UTC",
        topic_ids=["O01", "O08", "O11"],
        group_by=["cluster"],
        topic_group_by={"O01": ["cluster"], "O08": ["namespace"], "O11": ["cluster"]},
    )
    headers = {"Idempotency-Key": str(uuid4())}
    response = httpx.post(backend + "/reports", json=data, headers=headers)
    assert response.status_code == 202, response.text
    jid = response.json()["job_id"]
    result, evidence = worker_result(stack, "report", jid, "-basic-v2")
    assert result["versions"]["criteria"] == "1.3"
    assert result["versions"]["execution_profile_revision"] == "report-namespace-v2"
    assert {t["topic_id"] for t in result["topics"]} == set(data["topic_ids"])
    assert not {"D07", "D09", "D11", "D12", "D13"} & {q for q, _ in evidence}
    topic = next(t for t in result["topics"] if t["topic_id"] == "O08")
    hours = [m for m in topic["metrics"] if ".hourly_gpu_activity." in m["id"]]
    assert hours and any(m["value"] == 2 for m in hours)
    assert any(m["value"] is None for m in hours)
    assert any("observed_low_activity_seconds" in m["id"] for m in topic["metrics"])
    again = httpx.post(backend + "/reports", json=data, headers=headers)
    assert again.json()["job_id"] == jid
    html = httpx.get(backend + f"/reports/{jid}/export?format=html")
    assert html.status_code == 200 and "시간대 연결 GPU 평균 활동률" in html.text
    assert "기록/분석 시각 (UTC)" in html.text
    exported = httpx.get(backend + f"/reports/{jid}/export?format=csv")
    assert exported.status_code == 200
    header = next(csv.reader(io.StringIO(exported.text.lstrip("\ufeff"))))
    assert "period" in header and "target" in header

    # Delete a real published report through Backend -> JC, then let Ops clean its files.
    detail = httpx.get(backend + f"/reports/{jid}").json()
    assert detail["can_delete"]
    folder = LOCAL / "artifacts" / jid
    assert folder.is_dir() and list(folder.iterdir())
    with psycopg.connect(stack["url"]) as conn:
        preserved = conn.execute(
            "SELECT count(*),sum(octet_length(content_hash)) FROM result_candidates WHERE job_id<>%s",
            (jid,),
        ).fetchone()
        own_evidence = conn.execute(
            "SELECT count(*) FROM evidence WHERE job_id=%s", (jid,)
        ).fetchone()[0]
    assert own_evidence > 0
    delete_headers = {
        "Idempotency-Key": str(uuid4()),
        "If-Match": str(detail["version"]),
    }
    deletion = httpx.post(
        backend + f"/jobs/{jid}/delete",
        json={"reason": "isolated deletion regression"},
        headers=delete_headers,
        timeout=15,
    )
    assert deletion.is_success, deletion.text
    repeated = httpx.post(
        backend + f"/jobs/{jid}/delete",
        json={"reason": "isolated deletion regression"},
        headers=delete_headers,
        timeout=15,
    )
    assert repeated.status_code == deletion.status_code
    assert {k: v for k, v in repeated.json().items() if k != "request_id"} == {
        k: v for k, v in deletion.json().items() if k != "request_id"
    }
    deleted = httpx.get(backend + f"/reports/{jid}").json()
    assert deleted["result_status"] == "deleted" and deleted["result_ref"] is None
    assert deleted["status"] == "succeeded" and deleted["attempts"]
    assert deleted["deletion"]["evidence_count"] == own_evidence
    assert not deleted["can_delete"]
    assert httpx.get(backend + f"/reports/{jid}/export?format=html").status_code == 410
    history = httpx.get(backend + f"/jobs/{jid}").json()
    assert history["result_status"] == "deleted"
    reports = httpx.get(backend + "/reports").json()["items"]
    jobs = httpx.get(backend + "/jobs").json()["items"]
    assert jid not in {row["id"] for row in reports}
    assert next(row for row in jobs if row["id"] == jid)["result_status"] == "deleted"
    process = stack["spawn"](
        [sys.executable, "-m", "ops_agent.main", "--once"],
        stack["env"],
        "report-deletion-cleanup",
    )
    assert process.wait(30) == 0
    assert folder.is_file() and folder.stat().st_size == 0
    with psycopg.connect(stack["url"]) as conn:
        assert conn.execute(
            "SELECT artifact_cleanup_state FROM report_deletions WHERE job_id=%s",
            (jid,),
        ).fetchone() == ("complete",)
        assert conn.execute(
            "SELECT count(*) FROM evidence WHERE job_id=%s", (jid,)
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT count(*) FROM result_candidates WHERE job_id=%s", (jid,)
        ).fetchone() == (0,)
        assert (
            conn.execute(
                "SELECT count(*),sum(octet_length(content_hash)) FROM result_candidates WHERE job_id<>%s",
                (jid,),
            ).fetchone()
            == preserved
        )


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
    evaluation = rca["quality"]["rca_evaluation"]
    assert evaluation["schema_version"] == "2"
    assert evaluation["evidence"]["execution_status"] == "complete"
    assert evaluation["review"]["execution_status"] == "skipped"
    assert evaluation["review"]["verdict"] is None
    assert evaluation["review"]["analysis_id"] == evaluation["analysis_id"]
    assert evaluation["review"]["criteria"] == {}
    assert rca["narrative_status"] == "complete"
    assert {s["id"] for s in rca["narrative"]} >= {
        "problem",
        "cause",
        "action",
        "limits",
    }
    assert rca["device_observations"]
    assert rca["quality"]["analysis"]["status"] == "complete"
    assert rca["quality"]["analysis"]["followups"] == 0
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
        scope={"clusters": [{"cluster_id": "cpc-2", "namespaces": None}]},
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
    assert len(report["narrative"]) == 5
    assert report["quality"]["report"]["status"] == "complete"
    assert next(t for t in report["topics"] if t["topic_id"] == "O05")[
        "rca_references"
    ][0]["result_id"]
    if any(t["topic_id"] == "O05" for t in report["topics"]):
        refs = next(t for t in report["topics"] if t["topic_id"] == "O05").get(
            "rca_references", []
        )
        if refs:
            assert all("rca_evaluation" in ref for ref in refs)
    for artifact in report["artifacts"]:
        path = LOCAL / "artifacts" / artifact["object_key"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["checksum"]
        if artifact["format"] == "html":
            assert "권고와 실행 조건" in path.read_text(encoding="utf-8")
    assert any("/api/v1/query" in p for p, _ in Upstream.requests)
    assert any("/loki/api/v1/query_range" in p for p, _ in Upstream.requests)
    assert any(p == "/v1/chat/completions" for p, _ in Upstream.requests)


# Tests monkeypatch this to change the webhook alert labels the helper posts.
alert_label_overrides = {}
# An alert reason without an XID/SXID code is `error_code_unparsed`: it keeps the
# analysis-first path with rule/model follow-up selection instead of the
# alert/D09 mismatch batch. Tests covering that path post this reason.
UNCODED_ALERT_REASON = "Fleet component report without an error code (fixture)"


@pytest.mark.e2e
@pytest.mark.parametrize("fleet_reports", [False, True, "discovery"])
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
        profile = json.loads(
            (ROOT / "agents/tests/fixtures/config-v7.json").read_text()
        )
        path = LOCAL / "fleet-profile.json"
        path.write_text(json.dumps(profile))
        stack = {**stack, "env": {**stack["env"], "AGENT_CONFIG_FILE": str(path)}}
        monkeypatch.setattr(Upstream, "fleet_reports", True)
    alert["labels"].update(alert_label_overrides)
    if fleet_reports == "discovery":
        cluster_id = "new-site-" + uuid4().hex
        alert["labels"]["cluster_id"] = cluster_id
        alert["labels"].pop("namespace")
        monkeypatch.setattr(Upstream, "cluster_id", cluster_id)
        with psycopg.connect(stack["url"], autocommit=True) as conn:
            conn.execute("INSERT INTO cluster_registry(id) VALUES(%s)", (cluster_id,))
        stack = {
            **stack,
            "env": {
                **stack["env"],
                "AGENT_CONFIG_FILE": str(ROOT / "agents/config.example.json"),
            },
        }
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
    if fleet_reports == "discovery":
        # The shared profile also filters machine/node aliases; inspect those
        # expressions below instead of applying the legacy two-field fixture.
        monkeypatch.setattr(Upstream, "logs_json_target", None)
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
        assert len(result["device_observations"]) == 31
        assert all(
            h["error_code"] == "sxid:11001" and not h["fact_eligible"]
            for h in result["device_observations"]
        )
        assert result["quality"]["analysis"]["status"] == "complete"
        assert {"D09", "D02"} <= {q for q, _ in evidence}
        assert "purpose_plan" not in {q for q, _ in evidence}
        assert result["narrative_status"] == "complete"
    else:
        assert all(
            row["check_status"] == row["normalized_health"] == "unknown"
            for row in result["device_observations"]
        )
    if fleet_reports == "discovery":
        assert snapshot["input"]["scope"]["clusters"][0]["cluster_id"] == cluster_id
        assert all(
            f'cluster="{cluster_id}"' in args["query"][0] for args in log_requests
        )
        assert all(
            'resources[\\"machine.id\\"]' in args["query"][0] for args in log_requests
        )
        with psycopg.connect(stack["url"]) as conn:
            resolved = conn.execute(
                "SELECT query_id,quality FROM evidence WHERE job_id=%s AND query_id IN ('D02','D09')",
                (jid,),
            ).fetchall()
        assert {q for q, _ in resolved} == {"D02", "D09"}
        for query, quality in resolved:
            label = "cluster" if query == "D09" else "cluster_id"
            assert quality["resolved_cluster_selector"] == {label: cluster_id}
            assert quality["datasource_resolution"] == "discover"
            assert quality["selection_method"] == "automatic_verified"
    assert result["incident_id"] == item["incident_id"]
    assert result["assessments"] and all(
        "purpose_id" not in a for a in result["assessments"]
    )
    assert "purpose_ids" not in snapshot["input"]
    assert result["versions"]["input_contract"] == "1.5"
    assert ("incident_snapshot", "ok") in evidence
    assert any(query.startswith("D") for query, _ in evidence)
    # A published blocked result must not hide MCP rejecting fractional times.
    assert all(
        status in {"ok", "empty", "partial"}
        for query, status in evidence
        if query.startswith("D")
    ), evidence
    with psycopg.connect(stack["url"]) as conn:
        # startsAt and receipt time carry microseconds; Incident stores a whole
        # millisecond window so Loki requests keep the exact period (no partial).
        window = conn.execute(
            "SELECT input_snapshot->'time_range' FROM jobs WHERE id=%s", (jid,)
        ).fetchone()[0]
        assert all(
            datetime.fromisoformat(window[k].replace("Z", "+00:00")).microsecond % 1000
            == 0
            for k in ("start", "end")
        ), window
        partial = conn.execute(
            "SELECT query_id, quality FROM evidence WHERE job_id=%s AND tool_status='partial'",
            (jid,),
        ).fetchall()
        assert not [
            q
            for q, quality in partial
            if quality.get("reason") == "time_precision_reduced"
        ], partial
        clues = conn.execute(
            "SELECT snapshot FROM evidence WHERE job_id=%s AND query_id='alert_clues'",
            (jid,),
        ).fetchone()[0]
        expected_codes = ["sxid:11001"] if fleet_reports else ["xid:79"]
        if alert["labels"]["reason"] == UNCODED_ALERT_REASON:
            expected_codes = []
        assert clues["error_codes"] == expected_codes
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
@pytest.mark.parametrize("namespaces", [None, ["dev"]])
def test_builtin_profile_without_datasource_configuration(stack, namespaces):
    builtin_stack = {
        **stack,
        "env": {
            **stack["env"],
            "AGENT_CONFIG_FILE": str(ROOT / "agents/tests/fixtures/config-v7.json"),
        },
    }
    request_start = len(Upstream.requests)
    data = dict(
        scope={"clusters": [{"cluster_id": "cpc-2", "namespaces": namespaces}]},
        time_range=PERIOD,
        timezone="UTC",
        topic_ids=["O01", "O09", "O10"],
        group_by=["cluster"],
    )
    jid = submit(builtin_stack, "report", data)
    report, evidence = worker_result(builtin_stack, "report", jid, "-builtin")
    energy = next(t for t in report["topics"] if t["topic_id"] == "O09")["metrics"][0]
    temperature = [
        m
        for t in report["topics"]
        if t["topic_id"] == "O01"
        for m in t["metrics"]
        if m["id"].startswith("O01.temperature.")
    ]
    if namespaces is None:
        assert energy["value"] == 0.25 and energy["unit"] == "kWh"
        assert len(temperature) == 1
        assert temperature[0]["value"] == 40 and temperature[0]["unit"] == "celsius"
        assert temperature[0]["target"] == {"cluster_id": "cpc-2", "gpu_uuid": "GPU-1"}
        assert all((q, "ok") in evidence for q in ("D04", "D11"))
    else:
        assert energy["value"] is None
        assert energy["quality"]["reason"] == "actual_power_original_samples_missing"
        assert not temperature
        assert all((q, "empty") in evidence for q in ("D04", "D11"))
    assert not {"D09", "D13"} & {q for q, _ in evidence}
    requests = Upstream.requests[request_start:]
    assert any(p == "/api/datasources" for p, _ in requests)
    assert any("/label/cluster_id/values" in p for p, _ in requests)
    assert not any("/loki/" in p for p, _ in requests)
    metric_queries = [
        args["query"][0] for path, args in requests if path.endswith("/api/v1/query")
    ]
    for metric in ("dcgm_fi_dev_gpu_temp", "dcgm_fi_dev_power_usage"):
        assert any(expr.startswith(metric + "{") for expr in metric_queries)
    assert not any(
        expr.startswith(("DCGM_FI_DEV_GPU_TEMP{", "DCGM_FI_DEV_POWER_USAGE{"))
        for expr in metric_queries
    )
    for path, args in requests:
        if path.endswith("/api/v1/query"):
            assert 'cluster_id="cpc-2"' in args["query"][0]
            assert ('namespace=~"dev"' in args["query"][0]) == (namespaces is not None)


@pytest.mark.e2e
@pytest.mark.parametrize("llm_failed", [False, True])
def test_rca_without_published_runbook_collects_and_publishes_final_report(
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
    assert result["result_status"] == ("partial" if llm_failed else "ready")
    assert "causal_confirmation_evidence" not in result["missing_inputs"]
    assert any(r["origin"] == "builtin" for r in result["runbook_revisions"])
    assert result["narrative_status"] == ("failed" if llm_failed else "complete")
    assert [section["id"] for section in result["narrative"]] == [
        "problem",
        "investigation",
        "comparison",
        "cause",
        "action",
        "limits",
    ]
    report = result["quality"]["report"]
    assert report["presentation"] == "rca-material/1"
    assert report["method"] == (
        "deterministic_fallback" if llm_failed else "llm_composed"
    )
    assert report["writer"]["stage"] == "report_writing"
    # A 503 gateway reply is retried once and its status is recorded.
    assert report["writer"]["usage"]["request_attempts"] == (2 if llm_failed else 1)
    if llm_failed:
        assert report["writer"]["http_status"] == 503
        assert report["writer"]["transient_retry_status"] == 503
    assert {"D09", "investigation_plan"} <= {q for q, _ in evidence}
    assert any(path == "/v1/chat/completions" for path, _ in Upstream.requests[start:])
    text = "\n".join(section["text"] for section in result["narrative"])
    # Unhealthy observations alone must not create a generic causal candidate.
    assert result["cause_candidates"] == []
    cause = next(section for section in result["narrative"] if section["id"] == "cause")
    assert "별도의 원인 후보는 채택하지 않았습니다" in cause["text"]
    # An alert's proposed action is preserved as input, not promoted by the writer.
    assert "REBOOT_SYSTEM" not in text
    if llm_failed:
        assert "채택된 증거 해석이 없습니다" in text
    with psycopg.connect(stack["url"]) as conn:
        frozen = conn.execute(
            "SELECT snapshot FROM evidence WHERE job_id=%s AND query_id='rca_result_frozen'",
            (jid,),
        ).fetchone()[0]
        assert report["material_hash"] == content_hash(frozen["material"])
        assert frozen["material"]["evaluation"] == result["quality"]["rca_evaluation"]
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
            scope={"clusters": [{"cluster_id": "cpc-2", "namespaces": None}]},
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
        assert not {"D09", "D13"} & {q for q, _ in evidence}
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
    assert result["cause_candidates"][0]["causal_status"] == "supported"
    assert not any(q == "analysis_review" for q, s in evidence)
    model_requests = [
        json.loads(body["messages"][1]["content"])
        for path, body in Upstream.requests[request_start:]
        if path == "/v1/chat/completions"
    ]
    assert 1 <= len(model_requests) <= 2
    request = model_requests[-1]
    assert request["material_hash"] == result["quality"]["report"]["material_hash"]
    assert "facts" not in request and "raw_excerpts" not in request
    assert any(
        "등록 오류 조건이 충족됐습니다." in row["text"]
        for row in request["source_items"]
        if row["section"] == "cause"
    )
    assert any(
        "장비의 연결 상태를 확인하세요." in row["text"]
        and "registered_error" in row["text"]
        for row in request["source_items"]
        if row["section"] == "action"
    )
    assert result["narrative_status"] == "complete"
    assert result["quality"]["report"]["method"] == "llm_composed"


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
            # JC prepared the schema before its background work started.
            "DSX_MIGRATE": "false",
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


@contextlib.contextmanager
def runbook_limits(stack):
    # Only this test's isolated database gets a larger bulk-import allowance.
    with psycopg.connect(stack["url"]) as conn:
        original = conn.execute(
            "SELECT config FROM service_profiles WHERE kind='limits' AND name='C07'"
        ).fetchone()[0]
        conn.execute(
            "UPDATE service_profiles SET config=jsonb_set(config,"
            "'{max_requests_per_minute}', '1000') WHERE kind='limits' AND name='C07'"
        )
    try:
        yield
    finally:
        with psycopg.connect(stack["url"]) as conn:
            conn.execute(
                "UPDATE service_profiles SET config=%s WHERE kind='limits' AND name='C07'",
                (Jsonb(original),),
            )


@contextlib.contextmanager
def runbook_publications(stack):
    """Do not let a failed RCA catalog test alter subsequent fixture routing."""
    with psycopg.connect(stack["url"]) as conn:
        original = [
            str(row[0])
            for row in conn.execute(
                "SELECT id FROM knowledge_revisions WHERE state='published'"
            ).fetchall()
        ]
    try:
        yield
    finally:
        with psycopg.connect(stack["url"]) as conn:
            conn.execute(
                "UPDATE knowledge_revisions SET state='retired' "
                "WHERE state='published' AND id <> ALL(%s::uuid[])",
                (original,),
            )


@pytest.mark.e2e
def test_runbook_api_lifecycle_and_real_rca_consumption(stack, monkeypatch):
    # This lifecycle test publishes the current catalog, including the SXid plan.
    profile = json.loads(json.dumps(stack["profile"]))
    profile["queries"]["D47"] = dict(
        source="mimir",
        metric="fixture_d47",
        unit="state",
        max_hold_seconds=30,
        revision="fixture-v1",
        validated=True,
    )
    config = LOCAL / "runbook-lifecycle-profile.json"
    config.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setitem(stack, "profile", profile)
    monkeypatch.setitem(stack["env"], "AGENT_CONFIG_FILE", str(config))
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
            # JC prepared the schema before its background work started.
            "DSX_MIGRATE": "false",
            "DSX_SEED": "false",
            "DSX_SCHEDULER_ENABLED": "false",
        },
        "runbook-backend",
    )
    wait_http(backend + "/health/ready", process)
    with (
        runbook_limits(stack),
        runbook_publications(stack),
        httpx.Client(base_url=backend, timeout=30) as client,
    ):
        # The complete corpus must fit the existing API and schema without publication.
        pilots = {"RB-XID-79", "RB-XID-48-63-64", "RB-SXID-11001"}
        bulk = LOCAL / ("catalog-" + uuid4().hex)
        folder, receipts = bulk / "input", bulk / "receipts"
        rows = []
        for path in sorted((ROOT / "rcca-agent/runbooks").rglob("RB-*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            # The code-keyed bulk import covers XID/SXID; component runbooks have no code.
            if (
                row["knowledge_key"] in pilots
                or row["knowledge_key"] == "RB-GENERAL-GPU-NODE"
                or not row["content"]["search"].get("codes")
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
                target={"node": "node-1", "gpu_uuid": "GPU-1"},
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
            if "operator_guidance" in row["content"]:
                projected = result["quality"]["runbook_guidance"]
                assert any(
                    item["guidance"] == row["content"]["operator_guidance"]
                    and str(item["revision"]) == "2"
                    for item in projected
                )
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

        # Check the real limiter without sleeping through two production windows.
        # Retry-After handling and idempotent retry are covered in test_runbook_import.
        with psycopg.connect(stack["url"]) as conn:
            conn.execute(
                "UPDATE service_profiles SET config=jsonb_set(config,"
                "'{max_requests_per_minute}', '1') WHERE kind='limits' AND name='C07'"
            )
        client.post("/knowledge", json={})  # Fill a fresh window if it just reset.
        limited = client.post("/knowledge", json={})
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert limited.headers["Retry-After"] == "60"


@pytest.mark.e2e
def test_rca_numeric_rejection_does_not_rewrite_same_evidence_before_publication(
    stack, monkeypatch
):
    original_reply = analysis_reply
    original_worker = worker_result
    captured = {}
    calls = 0

    def rejection_then_repair(refs):
        nonlocal calls
        calls += 1
        response = original_reply(refs)
        if calls == 1:
            response["hypotheses"][0]["claim"] = "온도는 999도입니다."
        return response

    def capture_result(stack, kind, jid, suffix=""):
        result, evidence = original_worker(stack, kind, jid, suffix)
        captured.update(result=result, evidence=evidence, job_id=jid)
        return result, evidence

    monkeypatch.setattr(sys.modules[__name__], "analysis_reply", rejection_then_repair)
    monkeypatch.setattr(
        sys.modules[__name__], "combined_reply", combined_candidate_reply
    )
    monkeypatch.setattr(sys.modules[__name__], "worker_result", capture_result)
    # A second analysis needs a second round. The alert/D09 mismatch batch
    # analyzes once after collecting; the uncoded alert keeps two rounds.
    monkeypatch.setattr(
        sys.modules[__name__],
        "alert_label_overrides",
        {"reason": UNCODED_ALERT_REASON},
    )
    test_grafana_webhook_through_incident_jc_and_real_rca_worker(
        stack, monkeypatch, True
    )
    with psycopg.connect(stack["url"]) as conn:
        rounds = [
            row[0]
            for row in conn.execute(
                "SELECT snapshot FROM evidence WHERE job_id=%s "
                "AND query_id='rca_synthesis' ORDER BY (snapshot->>'round')::integer",
                (captured["job_id"],),
            ).fetchall()
        ]
    assert [row["round"] for row in rounds] == [0]
    assert calls == 1
    diagnostic = rounds[0]["diagnostics"]
    assert captured["result"]["quality"]["analysis"]["synthesis"] == diagnostic
    assert diagnostic["request_attempts"] == 1
    assert any(
        row["code"] == "unregistered_numeric_claim"
        for row in diagnostic["dropped_items"]
    )
    assert not captured["result"]["cause_candidates"]
    assert ("rca_synthesis", "ok") in captured["evidence"]


@pytest.mark.e2e
def test_rca_review_above_legacy_input_limit_is_reviewed_before_publication(
    stack, monkeypatch
):
    original_reply, original_worker = analysis_reply, worker_result
    captured = {}

    def large_draft(refs):
        reply = original_reply(refs)
        reply["limitations"] = [
            prefix + "관측 공백에 대한 추가 확인이 필요합니다. " * 50
            for prefix in "가나다라마바사아자차카타"
        ]
        return reply

    def capture(stack, kind, jid, suffix=""):
        result, evidence = original_worker(stack, kind, jid, suffix)
        captured.update(result=result, job_id=jid)
        return result, evidence

    monkeypatch.setattr(sys.modules[__name__], "analysis_reply", large_draft)
    monkeypatch.setattr(
        sys.modules[__name__], "combined_reply", combined_candidate_reply
    )
    monkeypatch.setattr(sys.modules[__name__], "worker_result", capture)
    test_grafana_webhook_through_incident_jc_and_real_rca_worker(
        stack, monkeypatch, False
    )
    evaluation = captured["result"]["quality"]["rca_evaluation"]
    assert evaluation["review"]["execution_status"] == "skipped"
    assert evaluation["review"]["verdict"] is None
    with psycopg.connect(stack["url"]) as conn:
        records = conn.execute(
            "SELECT snapshot,quality FROM evidence WHERE job_id=%s AND query_id='analysis_review'",
            (captured["job_id"],),
        ).fetchall()
    assert not records


@pytest.mark.e2e
@pytest.mark.parametrize("activity", [60, 90])
def test_aggregate_report_publishes_without_d_registry(stack, monkeypatch, activity):
    import test_aggregate_report
    from test_aggregate_report import DATA

    original_fixture = test_aggregate_report.fixture
    monkeypatch.setattr(
        test_aggregate_report,
        "fixture",
        lambda *a, **kw: original_fixture(*a, **{**kw, "value": activity}),
    )
    from ops_agent.report_contract import VERSION

    data = {**DATA, "scope": SCOPE}
    monkeypatch.setitem(
        stack["env"], "AGENT_CONFIG_FILE", str(LOCAL / "missing-d-registry.json")
    )
    before = len(Upstream.requests)
    jid = submit(stack, "report", data, execution_profile=VERSION)
    body, evidence = worker_result(stack, "report", jid, "-aggregate")
    assert body["result_status"] == "ready", body
    assert body["quality"]["report_format"] == VERSION
    assert body["quality"]["report"]["method"] == "llm_interpreted"
    assert body["narrative_status"] == "complete"
    assert {n["topic_id"] for n in body["narrative"]} == {
        "namespace_usage",
        "incident_summary",
    }
    assert all(n["source_fact_ids"] and n["evidence_refs"] for n in body["narrative"])
    usage = next(t for t in body["topics"] if t["topic_id"] == "namespace_usage")
    incident = next(t for t in body["topics"] if t["topic_id"] == "incident_summary")
    assert usage["rows"][0]["gpu_memory"]["used_gib_per_gpu"] == 4
    assert ("hourly_gpu_memory", "ok") in evidence
    assert ("hourly_gpu_workload", "ok") in evidence
    assert ("hourly_gpu_jobs", "ok") in evidence
    assert ("hourly_gpu_workload_context", "ok") in evidence
    assert usage["workload_context"]["records"][0]["type_status"] == "declared_test"
    advice = next(n for n in body["narrative"] if n["topic_id"] == "namespace_usage")[
        "advice"
    ]
    assert advice[0]["kind"] == "queue_review"
    assert usage["workloads"][0]["completed_jobs"][0]["elapsed_seconds"] == 300
    assert advice[0]["evidence_refs"]
    stored_hours = {(h["start"], h["end"]): h for h in usage["workloads"][0]["hours"]}
    for hour in advice[0]["source_hours"]:
        source = stored_hours[(hour["start"], hour["end"])]
        assert hour["unscheduled"] == source["unscheduled_peak"]
        assert hour["unscheduled_samples"] == source["unscheduled_samples"]
    assert "대기 Pod" in advice[0]["observation"]
    assert usage["rows"][0]["activity_percent"] == activity
    assert usage["rows"][0]["change_percentage_points"] == 0
    assert incident["summary"]["count"] == 0
    assert len(evidence) == 11
    assert usage["workloads"][0]["pending_peak"] == 2
    assert usage["workloads"][0]["completed_observed"] == 1
    assert not any(query.startswith("D") for query, _ in evidence)
    queries = [
        args
        for path, args in Upstream.requests[before:]
        if path.endswith("/api/v1/query_range")
    ]
    assert len(queries) == 10
    assert not any("/loki/" in path for path, _ in Upstream.requests[before:])


@pytest.mark.e2e
def test_aggregate_report_backend_intake_schedule_and_read(stack):
    from test_aggregate_report import DATA
    from ops_agent.report_contract import VERSION

    extension = ".exe" if sys.platform == "win32" else ""
    binary = Path(
        os.getenv("BACKEND_BINARY", str(ROOT / (".local/backend-e2e" + extension)))
    )
    assert binary.is_file(), "Build Backend for aggregate report API E2E"
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
        },
        "aggregate-backend",
    )
    wait_http(backend + "/health/ready", process)
    with httpx.Client(base_url=backend, timeout=30) as client:
        data = {**DATA, "scope": SCOPE}
        response = client.post(
            "/reports", json=data, headers={"Idempotency-Key": uuid4().hex}
        )
        assert response.status_code == 202, response.text
        jid = response.json()["job_id"]
        body, _ = worker_result(stack, "report", jid, "-backend-aggregate")
        assert body["versions"]["criteria"] == VERSION
        result = client.get("/reports/" + jid)
        assert result.status_code == 200 and VERSION in result.text
        exported = client.get("/reports/" + jid + "/export", params={"format": "html"})
        assert exported.status_code == 200, exported.text
        assert "눈에 띄는 변화" in exported.text and "확인할 점" in exported.text
        spec = {k: v for k, v in data.items() if k not in ("time_range", "timezone")}
        for frequency, period, extras in (
            ("daily", "previous_complete_day", {}),
            ("weekly", "previous_complete_week", {"weekday": 1}),
            ("monthly", "previous_complete_month", {"day": 1}),
        ):
            response = client.post(
                "/schedules",
                json={
                    "enabled": True,
                    "frequency": frequency,
                    "period": period,
                    "timezone": "Asia/Seoul",
                    "local_time": "09:00",
                    "report_spec": spec,
                    **extras,
                },
                headers={"Idempotency-Key": uuid4().hex},
            )
            assert response.status_code == (422 if frequency == "monthly" else 201), (
                response.text
            )


@pytest.mark.e2e
def test_aggregate_incident_snapshot_respects_scope_and_period_edges(stack):
    import asyncio
    from test_aggregate_report import DATA
    from ops_agent.report_contract import VERSION, previous_period
    from ops_agent.report_store import ReportStore

    data = {**DATA, "scope": SCOPE}
    previous = previous_period(data)
    cases = [
        (SCOPE, data["time_range"]["start"]),
        (SCOPE, data["time_range"]["end"]),
        (SCOPE, previous["start"]),
        (
            {"clusters": [{"cluster_id": "cpc-2", "namespaces": ["private"]}]},
            data["time_range"]["start"],
        ),
    ]
    ids = [str(uuid4()) for _ in cases]
    with psycopg.connect(stack["url"]) as conn:
        for iid, (scope, at) in zip(ids, cases):
            conn.execute(
                "INSERT INTO incidents(id,cluster_id,scope,occurred_at,state,evidence_version,symptom,target) VALUES(%s,'cpc-2',%s,%s,'open',1,'XID fixture',%s)",
                (iid, Jsonb(scope), at, Jsonb({"gpu_uuid": "GPU-fixture"})),
            )
    context = asyncio.run(
        ReportStore(stack["url"]).read_context({"input": data, "versions": {}})
    )
    assert [row["id"] for row in context["incidents"]] == [ids[0]]
    assert [row["id"] for row in context["previous_incidents"]] == [ids[2]]
    assert context["incidents"][0]["target"] == {"gpu_uuid": "GPU-fixture"}
    assert not context["incident_limit_exceeded"]

    with psycopg.connect(stack["url"]) as conn:
        conn.execute(
            "UPDATE incidents SET symptom=NULL,alarm_status='firing',target=%s WHERE id=%s",
            (
                Jsonb(
                    {
                        "title": "XID 79 " + "x" * 600,
                        "node": None,
                        "k8s_node_name": "dgx01",
                        "component": "accelerator-nvidia-error-xid",
                        "test_alarm": True,
                        "private_raw_payload": "must not be read",
                    }
                ),
                ids[0],
            ),
        )
    context = asyncio.run(
        ReportStore(stack["url"]).read_context({"input": data, "versions": {}})
    )
    record = context["incidents"][0]

    assert record["symptom"] == ("XID 79 " + "x" * 600)[:512]
    assert (
        record["symptom_key"]
        == hashlib.md5(("XID 79 " + "x" * 600).encode()).hexdigest()
    )
    assert record["target"] == {
        "node": "dgx01",
        "component": "accelerator-nvidia-error-xid",
        "test_alarm": True,
    }
    assert context["previous_incidents"][0]["symptom"] == "XID fixture"

    jid = submit(stack, "report", data, execution_profile=VERSION)
    body, evidence = worker_result(stack, "report", jid, "-incident-details")
    usage = next(t for t in body["topics"] if t["topic_id"] == "namespace_usage")
    incident = next(t for t in body["topics"] if t["topic_id"] == "incident_summary")
    assert usage["rows"][0]["nodes"] == ["test-node"]
    assert usage["rows"][0]["gpu_memory"]["used_gib_per_gpu"] == 4
    assert ("hourly_gpu_memory", "ok") in evidence
    assert ("hourly_gpu_workload", "ok") in evidence
    assert ("hourly_gpu_jobs", "ok") in evidence
    advice = next(n for n in body["narrative"] if n["topic_id"] == "namespace_usage")[
        "advice"
    ]
    assert advice[0]["kind"] == "queue_review"
    assert usage["workloads"][0]["completed_jobs"][0]["elapsed_seconds"] == 300
    assert advice[0]["evidence_refs"]
    stored_hours = {(h["start"], h["end"]): h for h in usage["workloads"][0]["hours"]}
    for hour in advice[0]["source_hours"]:
        source = stored_hours[(hour["start"], hour["end"])]
        assert hour["unscheduled"] == source["unscheduled_peak"]
        assert hour["unscheduled_samples"] == source["unscheduled_samples"]
    assert "대기 Pod" in advice[0]["observation"]
    assert usage["rows"][0]["activity_percent"] == 60
    assert usage["rows"][0]["change_percentage_points"] == 0
    summary = incident["summary"]
    category = next(c for c in summary["categories"] if c["name"] == "XID 79")
    assert category["nodes"] == ["dgx01"]
    assert category["count"] == category["firing_count"] == category["test_count"] == 1
    assert category["incident_ids"] == [ids[0]]
    assert summary["status_as_of"]
    assert summary["unclassified_count"] == 1
    assert [(g["count"], g["previous_count"]) for g in summary["groups"]] == [(0, 1)]
    assert "cpc-2의 XID 79 1건(dgx01, 이전 0건)" in incident["findings"][0]["text"]
    assert "private_raw_payload" not in json.dumps(body)


@pytest.mark.e2e
@pytest.mark.parametrize("rule_selection", [False, True])
def test_rca_json_selection_and_safe_subset_survive_publication(
    stack, monkeypatch, rule_selection
):
    original_worker = worker_result
    captured = {}

    def unsafe_reply(refs):
        response = analysis_reply_original(refs)
        response["hypotheses"][0]["claim"] = (
            "보고된 PCI 주소가 인벤토리에 없는 GPU와 관련되어 오류가 발생했을 가능성이 있다"
        )
        response["limitations"] = [
            "unexpected English 상태입니다.",
            "오류 장치와 실제 장치의 연결을 확인해야 합니다.",
        ]
        return response

    analysis_reply_original = analysis_reply

    def capture_result(*args, **kwargs):
        result, evidence = original_worker(*args, **kwargs)
        captured.update(result=result, evidence=evidence)
        return result, evidence

    monkeypatch.setattr(Upstream, "reject_tool_requests", True)
    monkeypatch.setattr(sys.modules[__name__], "analysis_reply", unsafe_reply)
    monkeypatch.setattr(
        sys.modules[__name__], "combined_reply", combined_candidate_reply
    )
    monkeypatch.setattr(sys.modules[__name__], "worker_result", capture_result)
    # Rule/model follow-up selection runs only outside the alert/D09 mismatch
    # batch; an uncoded alert reason keeps that path.
    monkeypatch.setattr(
        sys.modules[__name__],
        "alert_label_overrides",
        {"reason": UNCODED_ALERT_REASON},
    )
    # The isolated fixture normally forces D02 by policy; remove only that force
    # to exercise the actual model selection/repair path (D02 remains approved).
    with psycopg.connect(stack["url"], autocommit=True) as conn:
        book_id, content, digest, reviewed = conn.execute(
            "SELECT id,content,content_hash,reviewed_content_hash FROM knowledge_revisions WHERE knowledge_key='RB-GENERAL-GPU-NODE' AND state='published'"
        ).fetchone()
        original_content = json.loads(json.dumps(content))
        content["unexpected_evidence"]["additional_queries"] = []
        content["unexpected_evidence"]["fallback"] = "general_runbook"
        if rule_selection:
            for step in content["observation_plan"]:
                if not step["required"]:
                    step["selection"] = {
                        "missing_any": ["causal_confirmation_evidence"],
                        "requires_all": ["observations"],
                        "independent": True,
                    }
        if not rule_selection:
            for step in content["observation_plan"]:
                if not step["required"]:
                    step["exploratory_llm"] = True
        conn.execute(
            "UPDATE knowledge_revisions SET content=%s,content_hash=%s,reviewed_content_hash=%s WHERE id=%s",
            (Jsonb(content), content_hash(content), content_hash(content), book_id),
        )
        try:
            test_grafana_webhook_through_incident_jc_and_real_rca_worker(
                stack, monkeypatch, True
            )
        finally:
            conn.execute(
                "UPDATE knowledge_revisions SET content=%s,content_hash=%s,reviewed_content_hash=%s WHERE id=%s",
                (Jsonb(original_content), digest, reviewed, book_id),
            )
    result = captured["result"]
    diagnostic = result["quality"]["analysis"]["synthesis"]
    assert diagnostic["adoption"] == "validated_response"
    assert diagnostic["dropped_items"]
    assert diagnostic["request_attempts"] == 1
    assert "인벤토리에 없는 GPU와 관련되어" not in json.dumps(
        result, ensure_ascii=False
    )
    assert "unexpected English" not in json.dumps(result, ensure_ascii=False)
    with psycopg.connect(stack["url"]) as conn:
        evaluations = conn.execute(
            "SELECT snapshot FROM evidence WHERE job_id=%s AND query_id='evidence_evaluation'",
            (result["job_id"],),
        ).fetchall()
    assert evaluations == []
    assert not any(q == "analysis_review" for q, _ in captured["evidence"])


@pytest.mark.e2e
@pytest.mark.parametrize("overlap", [False, True])
def test_aggregate_report_transition_verification_is_published(
    stack, monkeypatch, overlap
):
    import test_aggregate_report
    from test_identity_transitions import transition_fixture
    from ops_agent.report_contract import VERSION

    monkeypatch.setattr(
        test_aggregate_report,
        "fixture",
        lambda *a, **kw: transition_fixture(*a, **kw)[0],
    )
    monkeypatch.setattr(
        Upstream,
        "transition_fixture",
        "overlap" if overlap else "normal",
        raising=False,
    )
    data = {**test_aggregate_report.DATA, "scope": SCOPE}
    before = len(Upstream.requests)
    jid = submit(stack, "report", data, execution_profile=VERSION)
    body, evidence = worker_result(stack, "report", jid, "-aggregate-transition")
    usage = next(t for t in body["topics"] if t["topic_id"] == "namespace_usage")
    row = next(r for r in usage["rows"] if r["namespace"] == "dev")
    assert row["valid_hours"] == (23 if overlap else 24)
    assert row["verified_transition_hours"] == (0 if overlap else 1)
    assert row["hours"][0]["activity_percent"] == (None if overlap else 60)
    assert row["activity_percent"] == 60
    assert row["change_percentage_points"] == (None if overlap else 0)
    assert ("gpu_identity_transitions", "ok") in evidence
    assert (
        any("연결 변경이 확인된" in f["text"] for f in usage["findings"]) is not overlap
    )
    raw = [
        args
        for path, args in Upstream.requests[before:]
        if path.endswith("/api/v1/query")
        and "[1h] offset 1ms" in args.get("query", [""])[0]
    ]
    assert len(raw) == 4  # Two bounded checks for each comparison period.


@pytest.mark.e2e
@pytest.mark.parametrize(
    "failure,pattern",
    [
        ("json", None),
        ("mixed_topics", None),
        ("namespace_refs", None),
        ("json", "repeated_activity"),
        ("json", "relative_activity"),
        ("schedule_condition", "schedule_candidate"),
    ],
)
def test_scheduled_and_manual_reports_repair_same_data(
    stack, monkeypatch, failure, pattern
):
    from agent_common.artifacts import render
    from test_aggregate_report import DATA

    backend = f"http://127.0.0.1:{port()}/api/v1"
    extension = ".exe" if sys.platform == "win32" else ""
    binary = os.getenv("BACKEND_BINARY", str(ROOT / (".local/backend-e2e" + extension)))
    process = stack["spawn"](
        [binary],
        {
            **os.environ,
            "DATABASE_URL": stack["url"],
            "DSX_ADDRESS": backend.removeprefix("http://").removesuffix("/api/v1"),
            "DSX_MIGRATE": "false",
            "DSX_SEED": "false",
            "DSX_SCHEDULER_ENABLED": "true",
            "DSX_JOB_CONTROLLER_URL": stack["jc"].removesuffix("/internal/v1"),
        },
        "scheduled-interpretation-backend",
    )
    wait_http(backend + "/health/ready", process)
    send = Upstream.send
    corrupted = []
    before = len(Upstream.requests)
    if failure == "schedule_condition":
        monkeypatch.setitem(stack["env"], "OPS_LLM_MEDIUM_EFFORT", "true")

    def send_with_one_malformed_reply(self, body, status=200):
        if pattern and urlparse(self.path).path.endswith("/api/v1/query_range"):
            query = parse_qs(urlparse(self.path).query)
            start, end = float(query["start"][0]), float(query["end"][0])
            if '"created_min"' in query["query"][0]:
                body["data"]["result"] = []
            for row in body.get("data", {}).get("result", []):
                measure = row["metric"].get("measure", "")
                if measure in ("activity_sum", "minimum", "maximum"):
                    for point in row["values"]:
                        hour = int((point[0] - start) / 3600)
                        activity = (
                            1
                            if pattern == "schedule_candidate"
                            else (85 if hour in (1, 3) else 20)
                            if pattern == "repeated_activity"
                            else (80 if hour < 2 else 20)
                        )
                        point[1] = str(
                            activity * (240 if measure == "activity_sum" else 1)
                        )
                elif measure.startswith(("pending_", "unscheduled_", "running_")):
                    value = (
                        240
                        if measure.endswith("samples")
                        else (2 if pattern == "repeated_activity" else 0)
                    )
                    row["values"] = [
                        [at, str(value)] for at in range(int(start), int(end) + 1, 3600)
                    ]
        if (
            self.path == "/v1/chat/completions"
            and body.get("choices")
            and not corrupted
        ):
            corrupted.append(True)
            if failure == "json":
                content = '{"sections":'
            else:
                reply = json.loads(body["choices"][0]["message"]["content"])
                for item in reply["sections"]:
                    if item["topic_id"] == "namespace_usage":
                        item["advice"][0]["summary"] = item["advice"][0][
                            "summary"
                        ].replace(
                            "확인한 뒤"
                            if failure == "schedule_condition"
                            else "{{period}}",
                            "확인하고" if failure == "schedule_condition" else "",
                        )
                    elif failure == "mixed_topics":
                        item["observation"] = "알림은 3건입니다."
                content = json.dumps(reply)
            body = {
                **body,
                "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            }
        return send(self, body, status)

    monkeypatch.setattr(Upstream, "send", send_with_one_malformed_reply)
    spec = {k: v for k, v in DATA.items() if k not in ("time_range", "timezone")}
    spec["scope"] = SCOPE
    with httpx.Client(base_url=backend, timeout=30) as client:
        response = client.post(
            "/schedules",
            json={
                "enabled": True,
                "frequency": "daily",
                "period": "previous_complete_day",
                "timezone": "Asia/Seoul",
                "local_time": "09:00",
                "report_spec": spec,
            },
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert response.status_code == 201, response.text
        schedule_id = response.json()["id"]
        # Advance only this isolated fixture schedule; no production clock or data is touched.
        with psycopg.connect(stack["url"]) as conn:
            conn.execute(
                "UPDATE schedules SET next_run_at=clock_timestamp()-interval '1 second' WHERE id=%s",
                (schedule_id,),
            )
        jid = None
        for _ in range(100):
            with psycopg.connect(stack["url"]) as conn:
                row = conn.execute(
                    "SELECT job_id::text FROM schedule_occurrences WHERE schedule_id=%s AND status='accepted'",
                    (schedule_id,),
                ).fetchone()
            if row:
                jid = row[0]
                break
            time.sleep(0.1)
        assert jid, "scheduler did not deliver the fixture occurrence"
        scheduled, _ = worker_result(stack, "report", jid, "-scheduled-json-repair")
        assert (
            scheduled["versions"]["source_snapshot_ref"]["schedule_id"] == schedule_id
        )
        corrupted.clear()
        response = client.post(
            "/reports",
            json={
                **spec,
                "time_range": scheduled["time_range"],
                "timezone": "Asia/Seoul",
            },
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert response.status_code == 202, response.text
        manual, _ = worker_result(
            stack, "report", response.json()["job_id"], "-manual-json-repair"
        )
        for result in (scheduled, manual):
            fetched = client.get(f"/reports/{result['job_id']}")
            assert fetched.status_code == 200, fetched.text
            if pattern:
                assert pattern in fetched.text, (
                    result["quality"]["report"],
                    [n.get("selection") for n in result["narrative"]],
                )
    for result in (scheduled, manual):
        assert result["narrative_status"] == "complete"
        assert result["quality"]["report"]["reason"] == "repaired"
        failures = result["quality"]["report"]["failures"]
        assert len(failures) == 1 and failures[0]["attempt"] == 1
        assert failures[0]["reason"] in (
            {"llm_invalid_output"}
            if failure == "json"
            else {"conditional_scheduling_review_required"}
            if failure == "schedule_condition"
            else {"namespace_summary_tokens_required", "unsupported_prose"}
        )
        if failure == "namespace_refs":
            assert failures[0]["reference_errors"] == {
                "missing": ["period"],
                "duplicate": [],
                "unavailable_count": 0,
            }
        assert {n["topic_id"] for n in result["narrative"]} == {
            "namespace_usage",
            "incident_summary",
        }
        namespace = next(
            n for n in result["narrative"] if n["topic_id"] == "namespace_usage"
        )
        assert namespace["advice"]
        if pattern:
            item = next(a for a in namespace["advice"] if a["kind"] == pattern)
            assert item["source_hours"] and item["evidence_refs"]
            if pattern != "schedule_candidate":
                assert item["observed_periods"]
            if pattern == "relative_activity":
                assert item["reference_period"] != item["period"]
                assert item["reference_hours"]
            html = render(result)["html"].decode()
            if pattern == "schedule_candidate":
                assert item["summary"] in html
            else:
                assert item["summary_parts"]["evidence"] in html
        assert all(
            a["decision"]["option"] and a["decision"]["needed"]
            for a in namespace["advice"]
        )
        assert {d["fact_id"] for d in namespace["selection"]["decisions"]} == set(
            namespace["source_fact_ids"]
        )
    assert scheduled["time_range"] == manual["time_range"]
    assert render(scheduled)["csv"] == render(manual)["csv"]
    if failure == "schedule_condition":
        calls = [
            b
            for path, b in Upstream.requests[before:]
            if path == "/v1/chat/completions"
        ]
        assert len(calls) == 4  # Initial and repair for each report origin.
        for call in calls:
            assert call["chat_template_kwargs"] == {
                "enable_thinking": True,
                "medium_effort": True,
            }
        for call in calls[1::2]:
            item = json.loads(call["messages"][1]["content"])["summary_repair"][0]
            assert "'확인한 뒤'" in item["validation_error"]
            assert item["required_prose_terms"] == ["확인", "뒤", "검토"]


@pytest.mark.e2e
@pytest.mark.parametrize("failure", ["structure", "http"])
def test_aggregate_invalid_interpretation_keeps_published_calculations(
    stack, monkeypatch, failure
):
    from test_aggregate_report import DATA
    from ops_agent.report_contract import VERSION

    monkeypatch.setattr(
        sys.modules[__name__], "interpretation_reply", lambda data: {"sections": []}
    )
    if failure == "http":
        send = Upstream.send

        def unavailable(self, body, status=200):
            if self.path == "/v1/chat/completions":
                return send(self, {"error": "private-upstream-response"}, 503)
            return send(self, body, status)

        monkeypatch.setattr(Upstream, "send", unavailable)
    jid = submit(stack, "report", {**DATA, "scope": SCOPE}, execution_profile=VERSION)
    body, evidence = worker_result(stack, "report", jid, "-invalid-interpretation")
    assert body["result_status"] == "ready"
    assert body["narrative_status"] == "failed"
    assert body["quality"]["report"]["method"] == "deterministic_fallback"
    assert body["quality"]["report"]["attempts"] == (1 if failure == "http" else 2)
    if failure == "http":
        assert body["quality"]["report"]["failures"] == [
            {"attempt": 1, "reason": "llm_http_error", "http_status": 503}
        ]
        assert body["llm_usage"]["request_attempts"] == 3
        assert "private-upstream-response" not in json.dumps(body)
    assert (
        next(t for t in body["topics"] if t["topic_id"] == "namespace_usage")["rows"][
            0
        ]["activity_percent"]
        == 60
    )
    assert len(evidence) == 11


@pytest.mark.e2e
@pytest.mark.parametrize("invalid_interpretation", [False, True, "http", "revision"])
@pytest.mark.parametrize("component", ["sxid", "disk"])
def test_combined_runbook_goal_freezes_rca_material_before_report_and_publication(
    stack, monkeypatch, invalid_interpretation, component
):
    from copy import deepcopy

    monkeypatch.setattr(Upstream, "fleet_reports", True)
    review_calls = []

    def critic(data):
        review_calls.append(data["draft"]["analysis_id"])
        revise = invalid_interpretation == "revision" and len(review_calls) == 1
        return __import__("evaluation_fixtures").review_reply(
            data,
            "revision_required" if revise else "acceptable",
            [
                {
                    "claim_id": data["draft"]["claims"][0]["id"],
                    "reason": "보고된 사실로 결론을 한정하세요.",
                    "evidence_refs": data["input_evidence_refs"][:1],
                    "suggested_resolution": "현재 상태 단정을 피하세요.",
                }
            ]
            if revise
            else None,
        )

    monkeypatch.setattr(sys.modules[__name__], "review_reply", critic)
    if invalid_interpretation == "http":
        monkeypatch.setattr(Upstream, "author_http_fail", True)
    elif invalid_interpretation is True:
        original_reply = combined_reply

        def malformed_reply(data):
            response = original_reply(data)
            response["interpretation"]["unknowns"] = [
                {"statement": "Current health unknown", "evidence_refs": []}
            ]
            return response

        monkeypatch.setattr(sys.modules[__name__], "combined_reply", malformed_reply)
    profile = deepcopy(stack["profile"])
    profile["rca"]["generation_mode"] = "combined"
    profile["health_contracts"] = json.loads(
        (ROOT / "agents/tests/fixtures/config-v7.json").read_text()
    )["health_contracts"]
    if component == "disk":
        profile["health_contracts"]["fleet-component-log-v1"]["components"]["disk"] = (
            "component"
        )
        monkeypatch.setattr(Upstream, "fleet_component", "disk")
        monkeypatch.setattr(Upstream, "fleet_reason", "filesystem is read-only")
    config = LOCAL / "combined-profile.json"
    config.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setitem(stack["env"], "AGENT_CONFIG_FILE", str(config))
    book = json.loads(
        (ROOT / "agents/tests/fixtures/RB-SXID-11001-published-legacy.json").read_text(
            encoding="utf-8"
        )
    )
    # Parameter variants share the same published revision, not duplicate policies.
    if component == "disk":
        from test_rca_component_guidance import component_case

        book = deepcopy(component_case()["attempt"]["context"]["runbooks"][0])
    book_id = stack.setdefault("combined_goal_book_id_" + component, str(uuid4()))
    book["knowledge_key"] += "-goal-fixture-" + book_id
    with psycopg.connect(stack["url"]) as conn:
        conn.execute(
            "INSERT INTO knowledge_revisions(id,knowledge_id,knowledge_key,revision,kind,state,visibility,content,content_hash,reviewed_content_hash,compatibility) VALUES(%s,%s,%s,1,'runbook','published','common',%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (
                book_id,
                str(uuid4()),
                book["knowledge_key"],
                Jsonb(book["content"]),
                content_hash(book["content"]),
                content_hash(book["content"]),
                Jsonb({"cluster_id": "cpc-2"}),
            ),
        )
        iid = str(uuid4())
        data = dict(
            scope=SCOPE,
            incident_id=iid,
            evidence_version=1,
            analysis_profile_revision="fixture-v1",
            incident_time=PERIOD["start"],
            time_range=PERIOD,
            purpose_ids=["R01"],
            target={"node": "node-1"},
        )
        snapshot = {"input": data, "alert": {"labels": {"reason": "SXID 11001"}}}
        if component == "disk":
            data["target"]["component"] = "disk"
            snapshot["alert"]["labels"] = {
                "component": "disk",
                "reason": "filesystem is read-only",
            }
        conn.execute(
            "INSERT INTO incidents(id,cluster_id,scope,occurred_at,state,evidence_version) VALUES(%s,'cpc-2',%s,%s,'open',1)",
            (iid, Jsonb(SCOPE), data["incident_time"]),
        )
        conn.execute(
            "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES(%s,1,%s,%s)",
            (iid, Jsonb(snapshot), content_hash(snapshot)),
        )
    jid = submit(stack, "rca", data)
    result, evidence = worker_result(stack, "rca", jid, "-combined-goal")
    evaluation = result["quality"]["rca_evaluation"]
    assert evaluation["schema_version"] == "2"
    assert evaluation["generation_mode"] == "combined"
    assert evaluation["investigation"]["stop_reason"] == "no_available_followup"
    assert evaluation["review"]["reason"] == "not_requested"
    assert not any(q == "analysis_review" for q, _ in evidence)
    assert result["quality"]["report"]["status"] == "complete"
    assert result["narrative"]
    assert not any(q == "evidence_interpretation" for q, _ in evidence)
    assert any(q == "D09" for q, _ in evidence)
    with psycopg.connect(stack["url"]) as conn:
        stored = dict(
            conn.execute(
                "SELECT query_id,snapshot FROM evidence WHERE job_id=%s AND query_id IN ('rca_synthesis','rca_result_frozen','report_assembly')",
                (jid,),
            ).fetchall()
        )
    diagnostics = stored["rca_synthesis"]["diagnostics"]
    if invalid_interpretation == "http":
        # A gateway 400 gets exactly one more call with the lower output cap.
        assert diagnostics["request_attempts"] == 2
        assert diagnostics["reduced_output_retry"]["after_status"] == 400
        assert diagnostics["reduced_output_retry"]["succeeded"] is False
    else:
        assert diagnostics["request_attempts"] == 1
    assert (
        stored["rca_result_frozen"]["material_hash"]
        == stored["report_assembly"]["material_hash"]
    )
    assert stored["rca_result_frozen"]["material"]["evaluation"] == evaluation
    assert (
        stored["rca_result_frozen"]["material"]["runbook_guidance"]
        == result["quality"]["runbook_guidance"]
    )
    if component == "disk":
        assert "유지보수 승인" in str(result["narrative"])
        assert "RESTART_BM" not in str(result["narrative"])
    assert result["quality"]["report"]["method"] == "llm_composed"
    assert stored["report_assembly"]["attempts"] == 1
    assert stored["report_assembly"]["stage"] == "report_writing"
    assert (
        stored["report_assembly"]["input_material_hash"]
        == stored["rca_result_frozen"]["material_hash"]
    )

    diagnostics = stored["rca_synthesis"]["diagnostics"]
    if invalid_interpretation == "http":
        assert evaluation["evidence"]["reason"] == "llm_http_error"
        problem = next(row for row in result["narrative"] if row["id"] == "problem")
        assert "node-1" in problem["text"]
        assert "로그 기록 시각" in problem["text"]
        assert problem["evidence_refs"]
        assert stored["rca_result_frozen"]["material"]["reported_observations"]
    elif invalid_interpretation is True:
        # The malformed caveat is dropped and the rest adopted, but semantic criteria
        # are withheld so the objective above stays unmet.
        assert diagnostics["adoption"] == "validated_response"
        assert diagnostics["validation_failures"] == []
        assert diagnostics["dropped_items"] == [
            {
                "code": "interpretation_missing_support",
                "path": "$.interpretation.unknowns[0].reason",
                "rule": "missing_support",
                "action": "dropped",
            },
        ]
    else:
        assert diagnostics["adoption"] == "validated_response"
        assert diagnostics["validation_failures"] == []

    assert review_calls == []
    assert sum(q == "rca_synthesis" for q, _ in evidence) == 1


@pytest.mark.e2e
@pytest.mark.parametrize("kind,code", [("xid", "79"), ("sxid", "11001")])
def test_planned_incident_report_publishes_without_review_or_decision(
    stack, monkeypatch, kind, code
):
    from copy import deepcopy

    monkeypatch.setattr(Upstream, "fleet_reports", True)
    monkeypatch.setattr(Upstream, "fleet_component", "accelerator-nvidia-error-" + kind)
    monkeypatch.setattr(Upstream, "fleet_reason", f"{kind.upper()} {code}")
    review_calls = []

    def unexpected_review(data):
        review_calls.append(data)
        return {}

    def author(data):
        return {
            "interpretation": {
                "findings": [
                    {
                        "id": "report",
                        "kind": "observed",
                        "statement": "노드의 오류 보고를 수집 자료와 대조했습니다.",
                        "evidence_refs": data["observation_refs"][:1],
                    }
                ],
                "unknowns": [],
                "conflicts": [],
                "limitations": [],
            },
            "hypotheses": [],
            "limitations": [],
        }

    monkeypatch.setattr(sys.modules[__name__], "review_reply", unexpected_review)
    monkeypatch.setattr(sys.modules[__name__], "combined_reply", author)
    profile = deepcopy(stack["profile"])
    profile["health_contracts"] = json.loads(
        (ROOT / "agents/tests/fixtures/config-v7.json").read_text()
    )["health_contracts"]
    profile["queries"]["D47"] = dict(
        source="mimir",
        metric="fixture_fm",
        unit="enum",
        max_hold_seconds=30,
        revision="fixture-v1",
        validated=True,
    )
    config = LOCAL / f"planned-{kind}-profile.json"
    config.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setitem(stack["env"], "AGENT_CONFIG_FILE", str(config))
    book = json.loads(
        (ROOT / f"rcca-agent/runbooks/{kind}/RB-{kind.upper()}-{code}.json").read_text(
            encoding="utf-8"
        )
    )
    book_id, iid = str(uuid4()), str(uuid4())
    data = dict(
        scope=SCOPE,
        incident_id=iid,
        evidence_version=1,
        analysis_profile_revision="fixture-v1",
        incident_time=PERIOD["start"],
        time_range=PERIOD,
        purpose_ids=["R01"],
        target={"node": "node-1"},
    )
    snapshot = {
        "input": data,
        "alert": {
            "labels": {
                "component": "accelerator-nvidia-error-" + kind,
                "reason": f"{kind.upper()} {code}",
            }
        },
    }
    with psycopg.connect(stack["url"]) as conn:
        revision = conn.execute(
            "SELECT coalesce(max(revision),0)+1 FROM knowledge_revisions WHERE knowledge_key=%s",
            (book["knowledge_key"],),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO knowledge_revisions(id,knowledge_id,knowledge_key,revision,kind,state,visibility,content,content_hash,reviewed_content_hash,compatibility) VALUES(%s,%s,%s,%s,'runbook','published','common',%s,%s,%s,%s)",
            (
                book_id,
                str(uuid4()),
                book["knowledge_key"],
                revision,
                Jsonb(book["content"]),
                content_hash(book["content"]),
                content_hash(book["content"]),
                Jsonb({"cluster_id": "cpc-2"}),
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
    jid = submit(stack, "rca", data)
    result, evidence = worker_result(stack, "rca", jid, "-planned-" + kind)
    assert result["quality"]["analysis"]["workflow"] == "single_collection"
    assert any(
        r["id"] == book_id and r["revision"] == revision
        for r in result["runbook_revisions"]
    )
    assert result["quality"]["rca_evaluation"]["review"]["reason"] == "not_requested"
    assert not review_calls
    kinds = [q for q, _ in evidence]
    assert "analysis_review" not in kinds and "investigation_decision" not in kinds
    assert set(book["content"]["required_queries"]) <= set(kinds)
    assert kinds.count("D09") == 1
    assert kinds.count("rca_synthesis") == 1
    assert result["quality"]["report"]["status"] == "complete"
    assert any(
        "수집 자료와 대조" in row["text"]
        for row in result["narrative"]
        if row["id"] == "cause"
    )
