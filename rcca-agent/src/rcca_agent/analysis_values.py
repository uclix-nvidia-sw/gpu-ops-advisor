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


def code_label(code):
    family, _, number = str(code).partition(":")
    return f"{family.upper()} {number}" if number else str(code)


def period_text(first, last):
    if first == last:
        return korean_time(first)
    return f"{korean_time(first)} ~ {korean_time(last)}"


def report_text(row):
    """Counts and times the author may cite only through a value token."""
    kind = row.get("type")
    if kind == "log_report_group":
        times = row.get("event_times") or []
        shown = ", ".join(korean_time(t) for t in times[:3])
        if len(times) > 3:
            shown += f" 외 {len(times) - 3}개"
        return (
            f"{code_label(row['code'])} 보고 {row['reports']}건 ({row['device']}, 기록 {period_text(row['first'], row['last'])}"
            + (f", 커널 이벤트 시각 {shown}" if shown else "")
            + ", 보고 수이며 사건 수가 아님)"
        )
    if kind == "host_history":
        period = row["period"]
        text = f"같은 호스트 이력({period_text(period['start'], period['end'])}, 이번 사건 제외): {code_label(row['code'])} "
        if not row["previous_incidents"]:
            text += "이전 사건 없음"
        else:
            text += f"이전 사건 {row['previous_incidents']}건, 마지막 {korean_time(row['latest_previous'])}"
            counts = sorted(
                row["device_counts"].items(), key=lambda kv: (-kv[1], kv[0])
            )
            text += " · 장치별 " + ", ".join(
                f"{'장치 정보 없음' if d == 'node' else d} {n}건" for d, n in counts[:5]
            )
            if len(counts) > 5:
                text += f" 외 장치 {len(counts) - 5}개"
        return text + ("" if row["complete"] else " (이력 조회 일부 누락)")
    if kind == "prior_rca":
        codes = ", ".join(code_label(c) for c in row["codes"])
        return f"이전 RCA 보고 {korean_time(row['occurred_at'])} · {codes}" + (
            f" · {row['device']}" if row.get("device") else ""
        )
    return None


def register_values(rows):
    for index, row in enumerate(rows):
        if row.get("type") != "metric_comparison":
            text = report_text(row)
            if text:
                row["value_token"] = "{{observation-" + str(index + 1) + "}}"
                row["value_text"] = text
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
