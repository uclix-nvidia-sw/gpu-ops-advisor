"""Labels loaded from the canonical packaged dictionary."""

import json
from importlib.resources import files

LABELS = json.loads(
    files("rcca_agent").joinpath("report_labels.json").read_text(encoding="utf-8")
)


def label(group, code):
    return f"{LABELS[group].get(code, '의미 미확인')}({code})"


def query_label(code):
    return f"{code}({LABELS['queries'].get(code, '조회 의미 미확인')})"
