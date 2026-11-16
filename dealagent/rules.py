"""The decision rule. Maths decides the action; the model only explains it."""
from __future__ import annotations

from .metrics import MIN_BASELINE_DAYS

MIN_UNITS_SPIKE = 1.25   # below this the deal barely moved volume
MIN_ROI = 0.30           # incremental profit per rupee the platform invested
SAFETY = 0.8             # ask for a funding share 20% inside break-even

ACTIONS = ("REPEAT", "RENEGOTIATE", "STOP", "TEST_AGAIN")


def verdict(m: dict) -> dict:
    """Return {'action', 'reason', 'target_platform_share_pct'} for one deal's metrics."""
    target = None
    if m["baseline_days"] < MIN_BASELINE_DAYS:
        action = "TEST_AGAIN"
        reason = "Too few clean days before the deal to trust the baseline."
    elif m["units_spike"] < MIN_UNITS_SPIKE:
        action = "STOP"
        reason = "The deal barely moved volume, so the spend bought almost nothing."
    elif m["incremental_profit"] > 0 and m["roi"] >= MIN_ROI:
        action = "REPEAT"
        reason = "Volume rose and the deal earned more than it cost."
    elif m["breakeven_platform_share_pct"] > 5:
        action = "RENEGOTIATE"
        target = round(m["breakeven_platform_share_pct"] * SAFETY)
        reason = "Volume rose but the platform funded too much of the discount."
    else:
        action = "STOP"
        reason = "The deal loses money even if the brand funds the whole discount."
    return {"action": action, "reason": reason, "target_platform_share_pct": target}
