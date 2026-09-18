"""Resolve Grafana datasources and cluster selectors using read-only MCP tools."""

import json


class DiscoveryError(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class Discovery:
    # Prefer the explicit ID label. Never guess aliases or fall back to all clusters.
    CLUSTER_LABELS = (
        "cluster_id",
        "cluster",
        "k8s_cluster_name",
        "kubernetes_cluster",
        "k8s_cluster",
    )

    def __init__(self, call):
        self.call = call
        self.cache = {}

    async def _cached(self, name, args):
        key = (name, json.dumps(args, sort_keys=True))
        if key not in self.cache:
            try:
                self.cache[key] = await self.call(name, args)
            except DiscoveryError as exc:
                self.cache[key] = exc
        result = self.cache[key]
        if isinstance(result, DiscoveryError):
            raise result
        return result

    async def resolve(self, source, cluster_id, period):
        source_type = "loki" if source == "loki" else "prometheus"
        candidates = []
        offset = 0
        while True:
            page = await self._cached(
                "list_datasources",
                {"type": source_type, "limit": 100, "offset": offset},
            )
            if not isinstance(page, dict) or not isinstance(
                page.get("datasources"), list
            ):
                raise DiscoveryError("datasource_discovery_invalid_response")
            rows = page["datasources"]
            if any(
                not isinstance(row, dict)
                or not isinstance(row.get("uid"), str)
                or not row["uid"]
                or row.get("type") != source_type
                for row in rows
            ):
                raise DiscoveryError("datasource_discovery_invalid_response")
            candidates.extend(rows)
            if not page.get("hasMore", False):
                break
            if not rows:
                raise DiscoveryError("datasource_discovery_invalid_response")
            offset += len(rows)
        if not candidates:
            raise DiscoveryError("datasource_not_found")

        matches = []
        for uid in sorted({row["uid"] for row in candidates}):
            for label in self.CLUSTER_LABELS:
                args = dict(
                    datasourceUid=uid,
                    labelName=label,
                    startRfc3339=period["start"],
                    endRfc3339=period["end"],
                )
                if source_type == "prometheus":
                    args["limit"] = 5001
                values = await self._cached(f"list_{source_type}_label_values", args)
                if not isinstance(values, list) or any(
                    not isinstance(v, str) for v in values
                ):
                    raise DiscoveryError("datasource_discovery_invalid_response")
                if len(values) >= 5001:
                    raise DiscoveryError("cluster_discovery_limit_exceeded")
                if cluster_id in values:
                    matches.append((uid, {label: cluster_id}))
                    break
                if values:
                    # A stronger cluster label exists, but this cluster is absent.
                    break
        if not matches:
            raise DiscoveryError("cluster_not_found_in_datasources")
        if len(matches) != 1:
            raise DiscoveryError("datasource_ambiguous")
        return matches[0]
