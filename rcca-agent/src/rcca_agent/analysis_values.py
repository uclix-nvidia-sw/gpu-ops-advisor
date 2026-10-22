"""Code-owned value phrases: the author explains them without rewriting their meaning."""

import re
from datetime import datetime, timedelta, timezone

TOKEN = re.compile(r"\{\{observation-(\d+)\}\}")


def compact_brief(rows):
    """Group identical node GPU comparisons without losing device IDs or periods."""
    result, groups = [], {}
    for original in rows:
        row = dict(original)
        if (
            row.get("type") == "metric_comparison"
            and row.get("scope") == "node_gpu_context"
        ):
            key = repr(
                {k: v for k, v in row.items() if k not in {"gpu_uuid", "evidence_refs"}}
            )
            if key in groups:
                grouped = groups[key]
                grouped["gpu_uuids"].append(row["gpu_uuid"])
                grouped["evidence_refs"] = sorted(
                    set(grouped["evidence_refs"] + row["evidence_refs"])
                )
                continue
            row["gpu_uuids"] = [row.pop("gpu_uuid")]
            groups[key] = row
        result.append(row)
    return result


def register_values(rows):
    for index, row in enumerate(rows):
        if row.get("type") != "metric_comparison":
            continue
        unit = {
            "bytes_per_second": "B/s",
            "percent": "%",
            "watts": "W",
            "enum": "상태 코드",
            "state": "상태 코드",
            "count": "회",
        }.get(row.get("unit"), row.get("unit") or "")
        device = (
            row.get("gpu_uuid")
            or "같은 노드 GPU " + str(len(row.get("gpu_uuids", []))) + "개"
        )
        value = (
            number(row["min"])
            if row["min"] == row["max"]
            else number(row["min"]) + " ~ " + number(row["max"])
        )
        row["value_token"] = "{{observation-" + str(index + 1) + "}}"
        row["value_text"] = (
            f"{device} · {row['name']}: {value} {unit} ({korean_time(row['first'])} ~ {korean_time(row['last'])}, 측정 기록 {row['samples']}개)"
        )
    return rows


def resolve_values(text, refs, view):
    registry = {
        r["value_token"]: r
        for r in view.get("incident_brief", [])
        if "value_token" in r
    }

    def replace(match):
        row = registry.get(match[0])
        if not row or not set(row["evidence_refs"]) <= set(refs):
            raise ValueError("invalid_value_reference")
        return row["value_text"]

    expanded = TOKEN.sub(replace, text)
    return TOKEN.sub("관측값", text), expanded


def number(value):
    return str(int(value)) if float(value).is_integer() else str(value)


def korean_time(value):
    at = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone(timedelta(hours=9))
    )
    text = at.strftime("%Y-%m-%d %H:%M:%S")
    if at.microsecond:
        text += f".{at.microsecond:06d}".rstrip("0")
    return text + " KST"
