"""Real PostgreSQL + JC + Worker processes + NAT + official Grafana MCP.

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
    logs_fail = False

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
                        {"fact_ids": [f["id"] for f in data.get("facts", [])][:2]}
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
            return self.send([])
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
            if self.logs_fail:
                return self.send({"error": "fixture query failure"}, 503)
            start = int(
                datetime.fromisoformat(
                    PERIOD["start"].replace("Z", "+00:00")
                ).timestamp()
                * 1e9
            )
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
            return self.send(
                {
                    "status": "success",
                    "data": {
                        "resultType": "streams",
                        "result": [
                            {
                                "stream": {"cluster": "cpc2", "namespace": "dev"},
                                "values": [[str(start), line]],
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
    assert mcp.is_file() and jc.is_file()
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
        upstream_url = f"http://127.0.0.1:{upstream.server_port}"
        mp = spawn(
            [
                str(mcp),
                "-t",
                "streamable-http",
                "-address",
                f"127.0.0.1:{mcp_port}",
                "-enabled-tools",
                "prometheus,loki",
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
        profile["clusters"]["cpc-2"].update(mimir_uid="mimir", loki_uid="loki")
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
        for q in profile["queries"].values():
            q.update(validated=True, revision="fixture-original-v1")
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
        yield dict(url=url, jc=jc_url, env=worker_env, spawn=spawn, profile=profile)
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
def test_real_workers_nat_grafana_mcp_and_publication(stack):
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
    assert rca["device_observations"] and rca["cause_candidates"]
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
    result, evidence = worker_result(stack, "rca", rid, "-runbook")
    assert result["termination_reason"] == "evidence_sufficient"
    assert result["cause_candidates"][0]["causal_status"] == "supported"
    assert not any(q.startswith("D") for q, s in evidence)
