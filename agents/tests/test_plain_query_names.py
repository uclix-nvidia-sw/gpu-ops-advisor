"""Operator-facing report text names metrics instead of query IDs."""

import json
from pathlib import Path
import re

import pytest

from rcca_agent.report_labels import plain_query_ids, query_name

ROOT = Path(__file__).resolve().parents[2]
QUERY_ID = re.compile(r"(?<![A-Za-z0-9])D\d{2}(?![A-Za-z0-9])")


@pytest.mark.parametrize(
    ("text", "plain"),
    [
        ("오류 원문(D09), 장치 식별 정보", "오류 원문, 장치 식별 정보"),
        ("D08(GPU–Pod 할당): 조회 실패", "GPU–Pod 할당: 조회 실패"),
        ("D02와 D09를 비교합니다", "GPU 사용률과 오류·상태 로그를 비교합니다"),
        ("D40·D36은 누적값", f"{query_name('D40')}·{query_name('D36')}은 누적값"),
        ("D47로 확인", "GPU별 Fabric Manager 상태 코드로 확인"),
        ("D44으로 확인", "PCIe replay 누적값으로 확인"),
        ("XID 79·SXID 11001", "XID 79·SXID 11001"),
    ],
)
def test_query_ids_become_metric_names_with_matching_particles(text, plain):
    assert plain_query_ids(text) == plain


def test_runbook_prose_shown_in_reports_has_no_query_ids():
    books = [
        json.loads(p.read_text("utf-8"))["content"]
        for p in (ROOT / "rcca-agent/runbooks").rglob("RB-*.json")
    ]
    books.append(
        json.loads(
            (ROOT / "rcca-agent/src/rcca_agent/general_runbook.json").read_text("utf-8")
        )
    )
    for content in books:
        prose = [
            *content.get("analysis_guidance", []),
            *content.get("limitations", []),
            json.dumps(content.get("operator_guidance", {}), ensure_ascii=False),
        ]
        for line in prose:
            assert not QUERY_ID.search(line), line[:120]
