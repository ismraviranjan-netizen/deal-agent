"""Deal economics in plain Python. The model never does this arithmetic."""
from __future__ import annotations

from .data import POST_DAYS

BASELINE_WINDOW = 14
MIN_BASELINE_DAYS = 7


class Store:
    """In-memory view of the three tables with the lookups the metrics need."""

    def __init__(self, dataset: dict):
        self.products = {p["sku"]: p for p in dataset["products"]}
        self.deals = {d["deal_id"]: d for d in dataset["deals"]}
        self.units = {(r["sku"], r["day"]): r["units"] for r in dataset["daily_sales"]}
        self.price = {(r["sku"], r["day"]): r["price"] for r in dataset["daily_sales"]}
        self.last_day = max(r["day"] for r in dataset["daily_sales"])
        self._busy = {}  # sku -> days touched by any deal or its after-effect
        for d in dataset["deals"]:
            days = range(d["start_day"], d["start_day"] + d["days"] + POST_DAYS)
            self._busy.setdefault(d["sku"], set()).update(days)

    def clean_days_before(self, sku: str, start: int) -> list[int]:
        busy = self._busy.get(sku, set())
        lo = max(1, start - BASELINE_WINDOW)
        return [d for d in range(lo, start) if d not in busy]


def deal_metrics(store: Store, deal_id: str) -> dict:
    """Everything known about one deal, as a flat dict of rounded numbers."""
    deal = store.deals[deal_id]
    prod = store.products[deal["sku"]]
    sku, start, days = deal["sku"], deal["start_day"], deal["days"]
    list_price, cost = prod["list_price"], prod["unit_cost"]
    disc, share, fee = deal["discount_pct"], deal["platform_funding_share"], deal["promo_fee"]

    base_days = store.clean_days_before(sku, start)
    baseline = sum(store.units[(sku, d)] for d in base_days) / len(base_days) if base_days else 0.0
    deal_range = range(start, start + days)
    deal_units = sum(store.units[(sku, d)] for d in deal_range)
    deal_gms = sum(store.units[(sku, d)] * store.price[(sku, d)] for d in deal_range)
    post_range = [d for d in range(start + days, start + days + POST_DAYS) if d <= store.last_day]
    post_avg = sum(store.units[(sku, d)] for d in post_range) / len(post_range) if post_range else baseline

    baseline_units = baseline * days
    baseline_gms = baseline_units * list_price
    units_spike = (deal_units / baseline_units) if baseline_units else 0.0
    gms_spike = (deal_gms / baseline_gms) if baseline_gms else 0.0
    incremental_units = deal_units - baseline_units
    pull_forward_units = max(0.0, (baseline - post_avg) * len(post_range))
    net_incremental_units = incremental_units - pull_forward_units

    unit_margin = list_price - cost
    discount_value = deal_units * list_price * disc          # total discount given to shoppers
    investment = discount_value * share + fee                # what the platform paid for the deal
    baseline_margin = baseline_units * unit_margin
    pull_forward_loss = pull_forward_units * unit_margin
    # profit if the brand funded the whole discount, then what the platform's share costs on top
    profit_if_fully_brand_funded = deal_units * unit_margin - fee - baseline_margin - pull_forward_loss
    incremental_profit = profit_if_fully_brand_funded - discount_value * share
    roi = incremental_profit / investment if investment else 0.0
    breakeven_share = profit_if_fully_brand_funded / discount_value if discount_value else 0.0
    breakeven_share = min(1.0, max(0.0, breakeven_share))

    return {
        "deal_id": deal_id,
        "sku": sku,
        "category": prod["category"],
        "deal_type": deal["deal_type"],
        "days": days,
        "discount_pct": round(disc * 100, 1),
        "platform_funding_share_pct": round(share * 100, 1),
        "promo_fee": fee,
        "baseline_days": len(base_days),
        "baseline_daily_units": round(baseline, 1),
        "deal_units": deal_units,
        "deal_gms": round(deal_gms),
        "units_spike": round(units_spike, 2),
        "gms_spike": round(gms_spike, 2),
        "incremental_units": round(incremental_units),
        "pull_forward_units": round(pull_forward_units),
        "net_incremental_units": round(net_incremental_units),
        "investment": round(investment),
        "investment_pct_of_gms": round(100 * investment / deal_gms, 1) if deal_gms else 0.0,
        "incremental_profit": round(incremental_profit),
        "roi": round(roi, 2),
        "breakeven_platform_share_pct": round(breakeven_share * 100, 1),
    }


def category_benchmark(store: Store, category: str) -> dict:
    """Median spike, ROI and investment share for every deal in a category."""
    rows = [deal_metrics(store, d) for d, deal in store.deals.items()
            if store.products[deal["sku"]]["category"] == category]
    rows = [r for r in rows if r["baseline_days"] >= MIN_BASELINE_DAYS]

    def median(key):
        vals = sorted(r[key] for r in rows)
        if not vals:
            return 0.0
        mid = len(vals) // 2
        return vals[mid] if len(vals) % 2 else round((vals[mid - 1] + vals[mid]) / 2, 2)

    return {
        "category": category,
        "deals_counted": len(rows),
        "median_units_spike": median("units_spike"),
        "median_roi": median("roi"),
        "median_investment_pct_of_gms": median("investment_pct_of_gms"),
    }
