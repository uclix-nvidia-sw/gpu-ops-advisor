"""Typed sample handling. Preserve raw evidence; invalid points break continuity."""

import math


def sample_value(value, quality):
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value):
        return None
    rules = quality.get("invalid_values") or {}
    if value in rules.get("sentinels", []):
        return None
    if rules.get("minimum") is not None and value < rules["minimum"]:
        return None
    if rules.get("maximum") is not None and value > rules["maximum"]:
        return None
    if quality.get("sample_type") in {"enum", "bitmask"} and (
        value < 0 or not value.is_integer()
    ):
        return None
    return value


def counter_delta(samples, max_gap):
    """A decrease, conflict, invalid point or gap withholds the delta; no reset guess."""
    points = {}
    for at, value in samples:
        try:
            at, value = float(at), float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(at) or not math.isfinite(value) or value < 0:
            return None
        if at in points and points[at] != value:
            return None
        points[at] = value
    ordered = sorted(points.items())
    if len(ordered) < 2:
        return None
    if any(
        b - a > max_gap or right < left
        for (a, left), (b, right) in zip(ordered, ordered[1:])
    ):
        return None
    return ordered[-1][1] - ordered[0][1]
