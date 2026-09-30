import csv
import hashlib
import html
import io
import os
from pathlib import Path
from uuid import uuid4


def safe_cell(value):
    value = str(value if value is not None else "")
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
        else value
    )


def render(result):
    registry = result["measurements"] + [
        m for t in result.get("topics", []) for m in t["metrics"]
    ]
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(["id", "value", "unit", "method", "reason"])
    rows = []
    for m in registry:
        cells = [
            m["id"],
            m["value"],
            m["unit"],
            m["method"],
            m["quality"].get("reason", ""),
        ]
        writer.writerow([safe_cell(c) for c in cells])
        rows.append(
            "<tr>"
            + "".join(
                "<td>" + html.escape(str(c) if c is not None else "미확인") + "</td>"
                for c in cells
            )
            + "</tr>"
        )
    page = (
        '<!doctype html><html lang="ko"><meta charset="utf-8"><title>GPU 운영 보고서</title><body><h1>GPU 운영 보고서</h1><p>'
        + html.escape(result["result_status"])
        + "</p>"
        + "".join(
            "<section><h2>"
            + html.escape(s.get("title", "분석 설명"))
            + "</h2>"
            + "".join("<p>" + html.escape(p) + "</p>" for p in s["text"].split("\n\n"))
            + "</section>"
            for s in result.get("narrative", [])
        )
        + "<table><thead><tr><th>항목</th><th>값</th><th>단위</th><th>산식</th><th>제한</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )
    page += (
        "".join("<p>" + html.escape(x) + "</p>" for x in result["limitations"])
        + "</body></html>"
    )
    return {"html": page.encode(), "csv": buf.getvalue().encode("utf-8-sig")}


def save_artifacts(result, directory):
    folder = Path(directory).resolve() / result["job_id"]
    folder.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for extension, body in render(result).items():
        name = str(uuid4()) + "." + extension
        target = folder / name
        tmp = folder / (name + ".tmp")
        with open(tmp, "xb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
        artifacts.append(
            dict(
                format=extension,
                object_key=result["job_id"] + "/" + name,
                checksum=hashlib.sha256(body).hexdigest(),
                size_bytes=len(body),
            )
        )
    return artifacts
