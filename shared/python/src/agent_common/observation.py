import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from .contracts import timestamp, now
from .discovery import Discovery, DiscoveryError
from .grafana_time import prometheus_time

log = logging.getLogger(__name__)


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def unwrap(response):
    if hasattr(response, "model_dump"):
        response = response.model_dump()
    if isinstance(response, str):
        response = json.loads(response)
    if isinstance(response, dict) and response.get("isError"):
        raise ValueError("MCP tool error")
    if isinstance(response, dict) and response.get("structuredContent"):
        return response["structuredContent"]
    if isinstance(response, dict) and "content" in response:
        texts = [x["text"] for x in response["content"] if x.get("type") == "text"]
        return json.loads("".join(texts))
    return response


class Observation:
    def __init__(self, tools, profile, data, deadline):
        self.tools, self.profile, self.data, self.deadline = (
            tools,
            profile,
            data,
            deadline,
        )
        self.evidence = []
        self.calls = 0
        self.cache = {}
        self.discovery_calls = 0
        self.discovery = Discovery(self._discover)

    async def _discover(self, name, args):
        limits = self.profile["limits"]
        if self.discovery_calls >= limits.get("max_discovery_calls", 64):
            raise DiscoveryError("discovery_budget_exhausted")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise DiscoveryError("discovery_deadline_exhausted")
        self.discovery_calls += 1
        try:
            async with asyncio.timeout(
                min(limits.get("query_timeout_seconds", 30), remaining)
            ):
                result = unwrap(await self.tools[name](args))
            if len(json.dumps(result).encode()) > limits["max_bytes"]:
                raise DiscoveryError("discovery_response_byte_limit")
            return result
        except DiscoveryError:
            raise
        except Exception as exc:
            # Never put upstream error bodies or credentials into evidence/logs.
            raise DiscoveryError("datasource_discovery_failed") from exc

    async def collect(self, query_id, period=None):
        period = period or self.data["time_range"]
        key = (query_id, period["start"], period["end"])
        if key in self.cache:
            return self.cache[key]
        definition = self.profile["queries"].get(query_id)
        if not definition:
            return []
        start, end = timestamp(period["start"]), timestamp(period["end"])
        allowed = self.data["time_range"]
        permitted = [allowed, self.data.get("comparison_range", allowed)]
        if not any(
            timestamp(p["start"]) <= start < end <= timestamp(p["end"])
            for p in permitted
        ):
            raise ValueError("query outside authorized period")
        limits = self.profile["limits"]
        if end - start > limits["max_range_seconds"]:
            return [
                self._evidence(
                    query_id,
                    None,
                    period,
                    {},
                    "unavailable",
                    {"reason": "range_budget_exhausted"},
                )
            ]
        out = []
        for scope in self.data["scope"]["clusters"]:
            source = definition["source"]
            cluster = self.profile.get("clusters", {}).get(scope["cluster_id"], {})
            uid_key = "loki_uid" if source == "loki" else "mimir_uid"
            selector_key = "loki_selector" if source == "loki" else "metric_selector"
            try:
                if cluster.get(uid_key) and selector_key in cluster:
                    # Optional legacy/expert overrides; normal deployments discover both.
                    uid, selector = cluster[uid_key], dict(cluster[selector_key])
                else:
                    uid, selector = await self.discovery.resolve(
                        source, scope["cluster_id"], period
                    )
            except DiscoveryError as exc:
                log.warning(
                    "Grafana discovery unavailable source=%s cluster=%s reason=%s",
                    source,
                    scope["cluster_id"],
                    exc.reason,
                )
                out.append(
                    self._evidence(
                        query_id,
                        scope["cluster_id"],
                        period,
                        {},
                        "unavailable",
                        {"reason": exc.reason, "source": source},
                    )
                )
                continue
            selector = dict(selector)
            target = (
                self.data.get("target") or self.data.get("resource_selectors") or {}
            )
            if isinstance(target, dict):
                for field, label in definition.get("target_labels", {}).items():
                    if target.get(field):
                        selector[label] = str(target[field])
            filters = [
                f"{k}={json.dumps(v)}"
                for k, v in sorted(selector.items())
                if re.fullmatch("[a-zA-Z_][a-zA-Z0-9_]*", k)
            ]
            if scope["namespaces"] is not None:
                filters.append(
                    "namespace=~"
                    + json.dumps("|".join(re.escape(x) for x in scope["namespaces"]))
                )
            # Query strings come only from reviewed configuration and escaped scope labels.
            base = "{" + ",".join(filters) + "}"
            cursor = start
            chunk_seconds = limits.get("chunk_seconds", 3600)
            while cursor < end:
                stop = min(end, cursor + chunk_seconds)
                window = {"start": iso(cursor), "end": iso(stop)}
                if (
                    self.calls >= limits["max_queries"]
                    or time.monotonic() >= self.deadline
                ):
                    out.append(
                        self._evidence(
                            query_id,
                            scope["cluster_id"],
                            window,
                            {},
                            "unavailable",
                            {"reason": "budget_exhausted"},
                        )
                    )
                    break
                if source == "loki":
                    name = "query_loki_logs"
                    args = dict(
                        datasourceUid=uid,
                        logql=base,
                        startRfc3339=window["start"],
                        endRfc3339=window["end"],
                        limit=limits["max_rows"],
                        direction="forward",
                    )
                else:
                    name = "query_prometheus"
                    metric = definition["metric"]
                    if not re.fullmatch("[a-zA-Z_:][a-zA-Z0-9_:]*", metric):
                        raise ValueError("unregistered metric expression")
                    # Instant range-vector retains original sample timestamps, unlike query_range.
                    expr = metric + base + f"[{int(stop - cursor) + 1}s]"
                    args = dict(
                        datasourceUid=uid,
                        expr=expr,
                        queryType="instant",
                        endTime=prometheus_time(window["end"]),
                    )
                self.calls += 1
                quality = {
                    "complete": True,
                    "original_samples": source != "loki",
                    "max_hold_seconds": definition.get("max_hold_seconds"),
                    "unit": definition.get("unit"),
                    "datasource_uid": uid,
                    "query_revision": definition["revision"],
                    "metric": definition.get("metric"),
                }
                try:
                    async with asyncio.timeout(
                        min(
                            limits.get("query_timeout_seconds", 30),
                            max(0.01, self.deadline - time.monotonic()),
                        )
                    ):
                        response = unwrap(await self.tools[name](args))
                    size = len(json.dumps(response, ensure_ascii=False).encode())
                    payload = (
                        response.get("data", response)
                        if isinstance(response, dict)
                        else response
                    )
                    rows = (
                        payload.get("result", payload)
                        if isinstance(payload, dict)
                        else payload
                    )
                    count = (
                        sum(len(r.get("values", [])) or 1 for r in rows)
                        if isinstance(rows, list)
                        else 0
                    )
                    quality.update(
                        sample_count=count,
                        series_count=len(rows) if isinstance(rows, list) else 0,
                    )
                    # Range vectors contain many samples per series. Re-query a smaller
                    # time window instead of throwing away a successfully fetched hour.
                    # Every retry still consumes the same query/deadline budget.
                    if (
                        source != "loki"
                        and (size > limits["max_bytes"] or count > limits["max_rows"])
                        and stop - cursor > 1
                    ):
                        ratio = min(
                            limits["max_bytes"] / max(size, 1),
                            limits["max_rows"] / max(count, 1),
                        )
                        chunk_seconds = max(
                            1, int((stop - cursor) * min(0.5, ratio * 0.8))
                        )
                        continue
                    if size > limits["max_bytes"]:
                        response = {}
                        quality.update(complete=False, reason="response_byte_limit")
                        status = "partial"
                    else:
                        warning = (
                            bool(response.get("warnings"))
                            if isinstance(response, dict)
                            else False
                        )
                        limited = (
                            count >= limits["max_rows"]
                            if source == "loki"
                            else count > limits["max_rows"]
                        )
                        if limited or warning:
                            quality.update(
                                complete=False,
                                reason="source_warning"
                                if warning
                                else "sample_limit_exceeded",
                            )
                        status = (
                            "partial"
                            if not quality["complete"]
                            else ("ok" if rows else "empty")
                        )
                    out.append(
                        self._evidence(
                            query_id,
                            scope["cluster_id"],
                            window,
                            response,
                            status,
                            quality,
                            args,
                        )
                    )
                except (Exception,) as exc:
                    out.append(
                        self._evidence(
                            query_id,
                            scope["cluster_id"],
                            window,
                            {},
                            "unavailable",
                            {
                                **quality,
                                "complete": False,
                                "reason": "query_failed",
                                "error_type": type(exc).__name__,
                            },
                            args,
                        )
                    )
                cursor = stop
        self.cache[key] = out
        return out

    def _evidence(self, query, cluster, period, snapshot, status, quality, args=None):
        e = dict(
            id=str(uuid4()),
            query_id=query,
            cluster_id=cluster,
            scope=self.data["scope"],
            time_range=period,
            query_version=self.profile["queries"]
            .get(query, {})
            .get("revision", "unconfigured"),
            tool_status=status,
            quality=quality,
            snapshot=snapshot,
            input=args or {},
            collected_at=now(),
        )
        self.evidence.append(e)
        return e


def series(evidence):
    """Return only complete original samples; preserve unknowns instead of zero-filling."""
    combined = {}
    for e in evidence:
        if e["tool_status"] != "ok" or not e["quality"].get("original_samples"):
            continue
        raw = e["snapshot"]
        raw = raw.get("data", raw) if isinstance(raw, dict) else raw
        raw = raw.get("result", []) if isinstance(raw, dict) else raw
        if not isinstance(raw, list):
            continue
        for row in raw:
            labels = row.get("metric", {})
            key = (e["cluster_id"], json.dumps(labels, sort_keys=True))
            entry = combined.setdefault(
                key,
                dict(
                    cluster_id=e["cluster_id"],
                    labels=labels,
                    samples=[],
                    evidence_refs=[],
                    max_hold_seconds=e["quality"].get("max_hold_seconds", 0),
                ),
            )
            entry["samples"].extend(row.get("values", []))
            entry["evidence_refs"].append(e["id"])
    return list(combined.values())
