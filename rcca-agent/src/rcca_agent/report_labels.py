"""Labels loaded from the canonical packaged dictionary."""

import json
from importlib.resources import files
import re

from .incident_dossier import METRICS

LABELS = json.loads(
    files("rcca_agent").joinpath("report_labels.json").read_text(encoding="utf-8")
)


def label(group, code):
    return f"{LABELS[group].get(code, '의미 미확인')}({code})"


def query_label(code):
    return f"{code}({LABELS['queries'].get(code, '조회 의미 미확인')})"


# Report-facing names: section 3 metric names first, then the query dictionary.
NAMES = {"D09": "오류·상태 로그", "D13": "보조 원본 로그"}
QUERY_IDS = re.compile(
    r"(?<![A-Za-z0-9])(D\d{2}(?:[·/]D\d{2})*)(?![A-Za-z0-9])(으로|은|는|이|가|을|를|과|와|로)?"
)
PARTICLES = (("은", "는"), ("이", "가"), ("을", "를"), ("과", "와"), ("으로", "로"))


def query_name(code):
    return NAMES.get(code) or METRICS.get(code) or LABELS["queries"].get(code, code)


def particle(word, josa):
    """Pick the particle form that fits the last Hangul syllable of word."""
    last = word[-1]
    if not "가" <= last <= "힣":
        return josa
    batchim = (ord(last) - 0xAC00) % 28
    for after_consonant, after_vowel in PARTICLES:
        if josa in (after_consonant, after_vowel):
            # ㄹ batchim takes 로, not 으로.
            if after_consonant == "으로":
                return after_vowel if batchim in (0, 8) else after_consonant
            return after_consonant if batchim else after_vowel
    return josa


def plain_query_ids(text):
    """Report text never shows query IDs: drop '(D09)' asides and name the rest."""
    text = re.sub(r"\s?\(D\d{2}(?:[·/,] ?D\d{2})*\)", "", text)
    text = re.sub(r"(?<![A-Za-z0-9])D\d{2}\(([^()]+)\)", r"\1", text)

    def name(m):
        word = "·".join(query_name(c) for c in re.split(r"[·/]", m.group(1)))
        return word + (particle(word, m.group(2)) if m.group(2) else "")

    return QUERY_IDS.sub(name, text)
