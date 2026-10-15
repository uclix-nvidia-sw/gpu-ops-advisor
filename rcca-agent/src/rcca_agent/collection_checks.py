"""Describe collection outcomes without promoting transport into device facts."""

from agent_common.query_contract import mapping_query
from .fleet_events import pci


def reported_gpu_identity(data, health):
    """Resolve one scoped XID PCI inventory match for an observed workload join."""
    target = data.get("target", {})
    if data.get("identity_conflicts") or len(data["scope"]["clusters"]) != 1:
        return {}, []
    explicit = {k: v for k, v in target.items() if k in {"gpu_uuid", "pod_uid"} and v}
    if explicit:
        return explicit, []
    cluster = data["scope"]["clusters"][0]["cluster_id"]
    node = target.get("node") or target.get("k8s_node_name")
    if not node:
        return {}, []
    matches = {}
    for row in health:
        if (
            row.get("cluster_id") != cluster
            or row.get("target", {}).get("node") != node
            or (
                target.get("machine_id")
                and row.get("target", {}).get("machine_id") != target["machine_id"]
            )
            or row.get("check_status") != "valid"
            or not str(row.get("error_code", "")).startswith("xid:")
            or row.get("pci_inventory_relation") != "inventory_candidate_only"
        ):
            continue
        for address in row.get("reported_pci_addresses", []):
            for gpu in row.get("gpu_candidates", []):
                if pci(address) and pci(address) == pci(gpu.get("bus_id")):
                    matches.setdefault(gpu["gpu_uuid"], []).extend(row["evidence_refs"])
    if len(matches) != 1:
        return {}, []
    gpu, refs = next(iter(matches.items()))
    return {"gpu_uuid": gpu}, list(dict.fromkeys(refs))


def collection_checks(profile, planned, collected, relations, error_codes):
    checks = []

    def add(key, title, queries, connection):
        entries = [entry for q in queries for entry in collected.get(q, [])]
        reasons = sorted(
            {
                str(e.get("quality", {}).get("reason"))
                for e in entries
                if e.get("quality", {}).get("reason")
            }
        )
        if not queries or any(q not in profile["queries"] for q in queries):
            status = "connection_required"
        elif any(q not in planned for q in queries):
            status = "plan_required"
        elif any(q not in collected for q in queries):
            status = "not_collected"
        elif any(e.get("tool_status") == "unavailable" for e in entries):
            status = (
                "connection_required"
                if any(
                    r
                    in {
                        "unsupported_source",
                        "binding_not_selected",
                        "no_verified_binding",
                        "binding_scope_unavailable",
                        "binding_unverified",
                    }
                    for r in reasons
                )
                else "failed"
            )
        elif not entries or any(e.get("tool_status") == "empty" for e in entries):
            status = "empty"
        elif any(
            e.get("tool_status") != "ok" or not e.get("quality", {}).get("complete")
            for e in entries
        ):
            status = "partial"
        else:
            status = "collected"
        checks.append(
            dict(
                key=key,
                title=title,
                query_ids=queries,
                status=status,
                evidence_refs=[e["id"] for e in entries],
                reasons=reasons,
                connection_required=connection,
            )
        )

    add(
        "error_logs",
        "오류·시스템 원본",
        ["D09"],
        "사건 서버·기간의 원본 로그 datasource와 검증된 D09 binding을 연결하세요.",
    )
    add(
        "workload_identity",
        "GPU–작업 연결",
        [mapping_query(profile), "D06"],
        "동일 서버·GPU UUID의 작업 라벨과 Pod UID 이력 원천을 연결하세요.",
    )
    checks[-1]["relation_count"] = len(relations)
    if checks[-1]["status"] == "collected" and not relations:
        checks[-1]["status"] = "identity_unresolved"
    if any(code.startswith("sxid:") for code in error_codes):
        # Optional roles name registered queries only. They do not bypass the
        # published plan, binding validation, scope or query budget.
        roles = profile.get("rca", {}).get("evidence_roles", {})
        for key, title, instruction in (
            (
                "fabric_manager_logs",
                "Fabric Manager 원본",
                "FM 로그의 사건 시각·서버·NVSwitch PCI·source port를 보존하는 원천과 조회 binding을 연결하세요.",
            ),
            (
                "fabric_topology",
                "NVSwitch 포트·연결 대상",
                "같은 서버의 NVSwitch PCI·포트·상대 GPU/스위치 식별자와 유효 시각이 있는 토폴로지 원천을 연결하세요.",
            ),
        ):
            query = roles.get(key)
            add(
                key,
                title,
                [query] if isinstance(query, str) and query else [],
                instruction,
            )
        if "D13" in planned:
            add(
                "raw_log_context",
                "보조 로그 문맥",
                ["D13"],
                "사건 서버의 보조 Loki 원천을 연결하세요. 일반 로그 수집을 FM 포트 매핑으로 간주하지 않습니다.",
            )
    return checks
