"""Guardrail: every number in the agent's rationale must come from the metrics."""
from __future__ import annotations

import re

ALLOWED_CONSTANTS = {7.0, 14.0, 20.0, 30.0, 100.0}   # windows and thresholds named in the rules
_ID = re.compile(r"\b(?:D|SKU|PRP)-\d+\b")
_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> list[float]:
    text = _ID.sub(" ", text)
    return [float(n.replace(",", "")) for n in _NUM.findall(text)]


def ungrounded_numbers(text: str, *sources: dict) -> list[float]:
    """Numbers in `text` that match no value in the source dicts (within rounding)."""
    known = set(ALLOWED_CONSTANTS)
    for src in sources:
        for v in src.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                known.add(abs(float(v)))
    bad = []
    for n in numbers_in(text):
        a = abs(n)
        if not any(abs(a - k) <= 0.051 + 0.006 * k for k in known):
            bad.append(n)
    return bad
