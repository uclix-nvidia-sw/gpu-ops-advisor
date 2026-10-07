import asyncio
import json
import logging
import re
import time
from itertools import count
from datetime import datetime, timezone
from uuid import uuid4

from .contracts import timestamp, now
from .discovery import Discovery, DiscoveryError
from .grafana_time import mcp_time
from .runtime import attempt_context
from .query_contract import (
    consolidated,
    query_definition,
    scope_label_names,
    validate_profile,
)
from .binding_samples import sample_value

log = logging.getLogger(__name__)
_record_sequence = count()


def evidence_stamp():
    # Shared by concurrent collectors in this process; assigned before persistence.
    return dict(collected_at=now(), record_sequence=next(_record_sequence))


class MCPResponseError(ValueError):
    """A safe error code; never retain upstream response bodies."""


def _tool_failure(message):
    if re.search(
        r"response body exceeds maximum size of [0-9]+ bytes", message.lower()
    ):
        return MCPResponseError("response_byte_limit")
    code = (
        "loki_entry_limit_exceeded"
        if "max entries limit per query exceeded" in message.lower()
        else "mcp_tool_error"
    )
    return MCPResponseError(code)


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def unwrap(response):
    if hasattr(response, "model_dump"):
        response = response.model_dump()
    if isinstance(response, str):
        # NAT 1.5 returns MCP failures as text, not a JSON tool result.
        if response.startswith("MCPToolClient tool call failed:"):
            raise _tool_failure(response)
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            raise MCPResponseError("invalid_mcp_response") from None
    if isinstance(response, dict) and response.get("isError"):
        raise _tool_failure(
            "\n".join(
                x["text"]
                for x in response.get("content", [])
                if x.get("type") == "text"
            )
        )
    if isinstance(response, dict) and response.get("structuredContent") is not None:
        return response["structuredContent"]
    if isinstance(response, dict) and "content" in response:
        texts = [x["text"] for x in response["content"] if x.get("type") == "text"]
        return unwrap("".join(texts))
    return response


class Observation:
    def __init__(self, tools, profile, data, deadline, *, reuse_queries=False):
        validate_profile(profile)
        if consolidated(profile):
            scopes = data.get("scope", {}).get("clusters")
            if (
                not isinstance(scopes, list)
                or not scopes
                or any(
                    not isinstance(scope, dict)
                    or not isinstance(scope.get("cluster_id"), str)
                    or not scope["cluster_id"].strip()
                    for scope in scopes
                )
            ):
                raise ValueError("explicit cluster_id required for every scope")
        self.tools, self.profile, self.data, self.deadline = (
            tools,
            profile,
            data,
            deadline,
        )
        self.evidence = []
        self.calls = 0
        self.cache = {}
        self.reuse_queries = reuse_queries
        self.responses = {}
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

    def derive(self, query_id, sources):
        return [
            self._evidence(
                query_id,
                e["cluster_id"],
                e["time_range"],
                e["snapshot"],
                e["tool_status"],
                {
                    **e["quality"],
                    "derived_from": e["id"],
                    "derived_query": e["query_id"],
                },
                {"derived_from": e["id"]},
            )
            for e in sources
        ]

    async def collect(self, query_id, period=None, *, namespace_scope=None):
        period = period or self.data["time_range"]
        key = (
            query_id,
            period["start"],
            period["end"],
            json.dumps(namespace_scope, sort_keys=True),
        )
        if key in self.cache:
            return self.cache[key]
        definition = self.profile["queries"].get(query_id)
        if not definition:
            if consolidated(self.profile):
                raise ValueError("unregistered query in execution profile: " + query_id)
            return []
        source_query = definition.get("derived_from")
        if source_query:
            if source_query == query_id or self.profile["queries"].get(
                source_query, {}
            ).get("derived_from"):
                raise ValueError("derived query must reference a concrete source")
            sources = await self.collect(
                source_query, period, namespace_scope=namespace_scope
            )
            self.cache[key] = self.derive(query_id, sources)
            return self.cache[key]
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
            definition = query_definition(self.profile, query_id, scope["cluster_id"])
            if consolidated(self.profile):
                reason = definition.get("reason")
                target = (
                    self.data.get("target") or self.data.get("resource_selectors") or {}
                )
                labels = definition.get("target_labels") or {}
                if (
                    not reason
                    and scope["namespaces"] is not None
                    and "namespace" not in labels
                ):
                    reason = "binding_scope_unavailable"
                if not reason and any(
                    target.get(key) and key not in labels
                    for key in ("gpu_uuid", "node", "pod_uid", "pod", "namespace")
                ):
                    reason = "binding_scope_unavailable"
                if reason:
                    out.append(
                        self._evidence(
                            query_id,
                            scope["cluster_id"],
                            period,
                            {},
                            "unavailable",
                            {"reason": reason, "complete": False},
                        )
                    )
                    continue
            source = definition["source"]
            cluster = self.profile.get("clusters", {}).get(scope["cluster_id"], {})
            uid_key = "loki_uid" if source == "loki" else "mimir_uid"
            selector_key = "loki_selector" if source == "loki" else "metric_selector"
            try:
                if consolidated(self.profile):
                    environment = definition["environment"]
                    selector = dict(environment["selector"])
                    if environment.get("datasource_mode", "pinned") == "discover":
                        uid, discovered_scope = await self.discovery.resolve(
                            source,
                            scope["cluster_id"],
                            period,
                            cluster_labels=scope_label_names(environment),
                        )
                        selector.update(discovered_scope)
                    else:
                        uid = environment["datasource_uid"]
                elif cluster.get(uid_key) and selector_key in cluster:
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
            # Collection clues are not device identity or verified health facts.
            log_target = self.data.get("log_query_target") or {}
            json_filters = {
                field: (path, log_target[field])
                for field, path in (definition.get("json_target_fields") or {}).items()
                if source == "loki"
                and re.fullmatch("[a-zA-Z_][a-zA-Z0-9_]*", field)
                and isinstance(log_target.get(field), str)
                and log_target[field]
            }
            if isinstance(target, dict):
                for field, label in definition.get("target_labels", {}).items():
                    if target.get(field) and field not in json_filters:
                        if label in selector and selector[label] != str(target[field]):
                            raise ValueError("target conflicts with binding selector")
                        selector[label] = str(target[field])
            filters = [
                f"{k}={json.dumps(v)}"
                for k, v in sorted(selector.items())
                if re.fullmatch("[a-zA-Z_][a-zA-Z0-9_]*", k)
            ]
            namespaces = scope["namespaces"]
            narrowed = (namespace_scope or {}).get(scope["cluster_id"])
            if narrowed is not None:
                if not narrowed or (
                    namespaces is not None and not set(narrowed) <= set(namespaces)
                ):
                    raise ValueError("query outside authorized namespace scope")
                namespaces = narrowed
            if namespaces is not None:
                namespace_label = definition.get("target_labels", {}).get(
                    "namespace", "namespace"
                )
                if (
                    namespace_label in selector
                    and selector[namespace_label] not in namespaces
                ):
                    raise ValueError("namespace conflicts with binding selector")
                filters.append(
                    namespace_label
                    + "=~"
                    + json.dumps("|".join(re.escape(x) for x in sorted(namespaces)))
                )
            # Query strings come only from reviewed configuration and escaped scope labels.
            base = "{" + ",".join(filters) + "}"
            if json_filters:
                # Loki suffixes extracted names that collide with original labels.
                # Clear both names first so only the JSON value can satisfy a filter.
                fields = list(sorted(json_filters.items()))
                aliases = [f"dsx_json_{i}" for i in range(len(fields))]
                base += " | drop " + ", ".join(
                    name for alias in aliases for name in (alias, alias + "_extracted")
                )
                base += " | json " + ", ".join(
                    f"{alias}={json.dumps(path)}"
                    for alias, (_, (path, _)) in zip(aliases, fields)
                )
                base += ' | __error__=""'
                for alias, (_, (_, value)) in zip(aliases, fields):
                    value = json.dumps(value)
                    base += f" | ({alias}={value} or {alias}_extracted={value})"
            cursor = start
            chunk_seconds = limits.get("chunk_seconds", 3600)
            while cursor < end:
                stop = min(end, cursor + chunk_seconds)
                window = {"start": iso(cursor), "end": iso(stop)}
                if source == "loki":
                    name = "query_loki_logs"
                    args = dict(
                        datasourceUid=uid,
                        logql=base,
                        startRfc3339=mcp_time(window["start"], ceiling=True),
                        endRfc3339=mcp_time(window["end"]),
                        # MCP 1.4.2 fetches limit + 1 to detect truncation.
                        # Stay below the packaged MCP cap and Loki's default 5000 cap.
                        limit=min(4999, max(1, limits["max_rows"] - 1)),
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
                        endTime=mcp_time(window["end"]),
                    )
                if source == "loki" and timestamp(args["startRfc3339"]) > timestamp(
                    args["endRfc3339"]
                ):
                    out.append(
                        self._evidence(
                            query_id,
                            scope["cluster_id"],
                            window,
                            {},
                            "unavailable",
                            {"reason": "time_range_below_millisecond_resolution"},
                        )
                    )
                    cursor = stop
                    continue
                response_key = (
                    name,
                    scope["cluster_id"],
                    window["start"],
                    json.dumps(args, sort_keys=True),
                )
                cached = (
                    self.responses.get(response_key) if self.reuse_queries else None
                )
                if (
                    cached is None and self.calls >= limits["max_queries"]
                ) or time.monotonic() >= self.deadline:
                    out.append(
                        self._evidence(
                            query_id,
                            scope["cluster_id"],
                            {"start": iso(cursor), "end": iso(end)},
                            {},
                            "unavailable",
                            {"complete": False, "reason": "budget_exhausted"},
                        )
                    )
                    break
                quality = {
                    "complete": True,
                    "original_samples": source != "loki",
                    "max_hold_seconds": definition.get("max_hold_seconds"),
                    "allocation_semantics": definition.get("allocation_semantics"),
                    "unit": definition.get("unit"),
                    "datasource_uid": uid,
                    "datasource_resolution": (
                        definition["environment"].get("datasource_mode", "pinned")
                        if consolidated(self.profile)
                        else "legacy"
                    ),
                    "resolved_cluster_selector": (
                        {
                            label: selector[label]
                            for label in scope_label_names(definition["environment"])
                            if label in selector
                        }
                        if consolidated(self.profile)
                        and "scope_labels" in definition["environment"]
                        else None
                    ),
                    "query_revision": definition["revision"],
                    "metric": definition.get("metric"),
                }
                if narrowed is not None:
                    quality["queried_namespaces"] = namespaces
                if cached is not None:
                    quality["reused_from_evidence"] = cached[1]
                if source == "loki" and (
                    timestamp(args["startRfc3339"]) != cursor
                    or timestamp(args["endRfc3339"]) != stop
                ):
                    quality.update(
                        complete=False,
                        reason="time_precision_reduced",
                        request_time_range={
                            "start": args["startRfc3339"],
                            "end": args["endRfc3339"],
                        },
                        observation_usable=False,
                    )
                started = time.monotonic()
                outcome, reason = "cancelled", "cancelled"
                response_bytes = next_chunk_seconds = None
                try:
                    if cached is not None:
                        response = cached[0]
                    else:
                        self.calls += 1
                        async with asyncio.timeout(
                            min(
                                limits.get("query_timeout_seconds", 30),
                                max(0.01, self.deadline - time.monotonic()),
                            )
                        ):
                            response = unwrap(await self.tools[name](args))
                    size = len(json.dumps(response, ensure_ascii=False).encode())
                    response_bytes = size
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
                    metadata = (
                        response.get("metadata", {})
                        if isinstance(response, dict)
                        else {}
                    )
                    limited = (
                        count >= args["limit"] or bool(metadata.get("resultsTruncated"))
                        if source == "loki"
                        else count > limits["max_rows"]
                    )
                    # Re-query a smaller window before retaining oversized/truncated data.
                    # Every retry still consumes the same query/deadline budget.
                    if (size > limits["max_bytes"] or limited) and stop - cursor > 1:
                        ratio = min(
                            limits["max_bytes"] / max(size, 1),
                            limits["max_rows"] / max(count, 1),
                        )
                        chunk_seconds = max(
                            1, int((stop - cursor) * min(0.5, ratio * 0.8))
                        )
                        outcome = "split"
                        reason = (
                            "response_byte_limit"
                            if size > limits["max_bytes"]
                            else "sample_limit_exceeded"
                        )
                        next_chunk_seconds = chunk_seconds
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
                        if limited or warning:
                            quality.update(
                                complete=False,
                                reason="source_warning"
                                if warning
                                else "sample_limit_exceeded",
                            )
                        elif quality.get("reason") == "time_precision_reduced":
                            # Complete only within the actual request. Keep the original
                            # period incomplete for absence, continuity and aggregation.
                            quality["observation_usable"] = True
                        status = (
                            "partial"
                            if not quality["complete"]
                            else ("ok" if rows else "empty")
                        )
                    outcome, reason = status, quality.get("reason")
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
                    # Opted-in report attempts reuse only complete, bounded Prometheus responses.
                    if self.reuse_queries and source != "loki" and quality["complete"]:
                        self.responses[response_key] = (response, out[-1]["id"])
                except (Exception,) as exc:
                    error = {"error_type": type(exc).__name__}
                    if isinstance(exc, MCPResponseError):
                        error["error_code"] = str(exc)
                    oversized = error.get("error_code") == "response_byte_limit"
                    outcome = "unavailable"
                    reason = "response_byte_limit" if oversized else "query_failed"
                    if oversized and stop - cursor > 1:
                        chunk_seconds = max(1, int((stop - cursor) / 2))
                        outcome = "split"
                        next_chunk_seconds = chunk_seconds
                        continue
                    log.warning(
                        "Grafana query unavailable query=%s source=%s error_type=%s error_code=%s",
                        query_id,
                        source,
                        type(exc).__name__,
                        error.get("error_code", "query_failed"),
                    )
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
                                "reason": "response_byte_limit"
                                if oversized
                                else "query_failed",
                                **error,
                            },
                            args,
                        )
                    )
                finally:
                    claim = attempt_context.get({}).get("claim", {})
                    log.info(
                        "Grafana query window job=%s attempt=%s query=%s source=%s "
                        "cluster=%r namespace_count=%s start=%s end=%s "
                        "elapsed_seconds=%.3f outcome=%s reason=%s "
                        "sample_count=%s response_bytes=%s next_chunk_seconds=%s cached=%s",
                        claim.get("job_id"),
                        claim.get("attempt_no"),
                        query_id,
                        source,
                        scope["cluster_id"],
                        len(namespaces) if namespaces is not None else "all",
                        window["start"],
                        window["end"],
                        time.monotonic() - started,
                        outcome,
                        reason,
                        quality.get("sample_count"),
                        response_bytes,
                        next_chunk_seconds,
                        cached is not None,
                    )
                cursor = stop
        self.cache[key] = out
        return out

    def _evidence(self, query, cluster, period, snapshot, status, quality, args=None):
        if consolidated(self.profile):
            definition = query_definition(self.profile, query, cluster)
            metadata = {
                key: definition.get(key)
                for key in (
                    "binding_id",
                    "binding_revision",
                    "selection_method",
                    "selection_reason",
                    "producer",
                    "producer_version",
                    "source",
                    "unit",
                    "sample_type",
                    "timestamp_basis",
                    "target_labels",
                    "invalid_values",
                    "counter_reset",
                    "max_hold_seconds",
                    "health_contract",
                    "allocation_semantics",
                    "observation_semantics",
                )
            }
            quality = {**metadata, **quality}
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
            **evidence_stamp(),
        )
        self.evidence.append(e)
        return e


def usable_observation(evidence):
    quality = evidence["quality"]
    return (evidence["tool_status"] == "ok" and quality.get("complete", False)) or (
        evidence["tool_status"] == "partial"
        and quality.get("reason") == "time_precision_reduced"
        and quality.get("observation_usable") is True
        and bool(quality.get("request_time_range"))
    )


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
            labels = dict(row.get("metric", {}))
            quality = e["quality"]
            bound = bool(quality.get("binding_id"))
            if bound:
                label_map = quality.get("target_labels") or {}
                if any(
                    key in labels and label in labels and labels[key] != labels[label]
                    for key, label in label_map.items()
                ):
                    continue
                labels.update(
                    {
                        key: labels[label]
                        for key, label in label_map.items()
                        if label in labels
                    }
                )
            key = (
                e["cluster_id"],
                json.dumps(labels, sort_keys=True),
                quality.get("binding_id"),
                quality.get("binding_revision"),
            )
            entry = combined.setdefault(
                key,
                dict(
                    cluster_id=e["cluster_id"],
                    labels=labels,
                    samples=[],
                    evidence_refs=[],
                    max_hold_seconds=e["quality"].get("max_hold_seconds", 0),
                    sample_type=quality.get("sample_type"),
                    unit=quality.get("unit"),
                    binding_id=quality.get("binding_id"),
                    binding_revision=quality.get("binding_revision"),
                    observation_semantics=quality.get("observation_semantics"),
                ),
            )
            entry["samples"].extend(
                [
                    [at, sample_value(value, quality)]
                    for at, value in row.get("values", [])
                ]
                if bound
                else row.get("values", [])
            )
            entry["evidence_refs"].append(e["id"])
    return list(combined.values())
