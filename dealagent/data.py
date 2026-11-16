"""Synthetic marketplace data. Nothing here comes from a real company.

Each deal is generated from one of four archetypes, and the archetype is kept as a
planted label so the evals can check the pipeline against a known truth.
"""
from __future__ import annotations

import csv
import os
import random

HORIZON_DAYS = 130
POST_DAYS = 7  # days after a deal in which pulled-forward demand shows up as a dip

CATEGORIES = [
    "Home & Kitchen", "Personal Care", "Grocery",
    "Electronics Accessories", "Toys", "Sports & Fitness",
]
DEAL_TYPES = ["Lightning Deal", "Deal of the Day", "Coupon", "Festival Event"]

# archetype -> the action a sound analyst should reach
EXPECTED_ACTION = {
    "winner": "REPEAT",
    "fixable": "RENEGOTIATE",
    "dud": "STOP",
    "thin_data": "TEST_AGAIN",
}
ARCHETYPE_CYCLE = ["winner", "fixable", "dud", "winner", "fixable", "dud", "thin_data", "winner"]


def _noisy(rng: random.Random, mean: float) -> int:
    return max(0, round(rng.gauss(mean, max(1.0, mean) ** 0.5)))


def generate(seed: int = 7, n_skus: int = 24) -> dict:
    """Return {'products': [...], 'deals': [...], 'daily_sales': [...]} as lists of dicts."""
    rng = random.Random(seed)
    products, deals, sales = [], [], []
    deal_no = 0
    for i in range(n_skus):
        list_price = rng.choice([199, 299, 399, 499, 699, 999, 1499])
        margin_pct = rng.uniform(0.24, 0.38)
        prod = {
            "sku": f"SKU-{i + 1:04d}",
            "category": CATEGORIES[i % len(CATEGORIES)],
            "list_price": list_price,
            "unit_cost": round(list_price * (1 - margin_pct), 2),
            "base_daily_units": rng.randint(30, 90),
        }
        products.append(prod)
        base = prod["base_daily_units"]

        plan = []  # (archetype, start_day)
        for slot in range(2):
            arch = ARCHETYPE_CYCLE[(2 * i + slot) % len(ARCHETYPE_CYCLE)]
            start = 4 if (arch == "thin_data" and slot == 0) else (30 if slot == 0 else 90)
            if arch == "thin_data" and slot == 1:
                arch = "winner"  # a late deal always has a full baseline
            plan.append((arch, start))

        mean = {d: float(base) for d in range(1, HORIZON_DAYS + 1)}
        price = {d: float(list_price) for d in range(1, HORIZON_DAYS + 1)}
        for arch, start in plan:
            deal_no += 1
            days = rng.randint(3, 7)
            if arch in ("winner", "thin_data"):
                disc, uplift = rng.uniform(0.10, 0.15), rng.uniform(2.2, 3.2)
                share, fee, pull = rng.uniform(0.30, 0.50), rng.randint(500, 1500), rng.uniform(0.05, 0.10)
            elif arch == "fixable":
                disc, uplift = rng.uniform(0.25, 0.30), rng.uniform(1.8, 2.4)
                share, fee, pull = rng.uniform(0.90, 1.00), rng.randint(500, 1500), rng.uniform(0.12, 0.18)
            else:  # dud
                disc, uplift = rng.uniform(0.05, 0.08), rng.uniform(0.98, 1.08)
                share, fee, pull = rng.uniform(0.50, 0.80), rng.randint(3000, 6000), 0.0
            disc, share = round(disc, 2), round(share, 2)
            for d in range(start, start + days):
                mean[d] = base * uplift
                price[d] = round(list_price * (1 - disc), 2)
            pulled = pull * base * (uplift - 1) * days
            for d in range(start + days, start + days + POST_DAYS):
                mean[d] = max(0.0, base - pulled / POST_DAYS)
            deals.append({
                "deal_id": f"D-{deal_no:04d}",
                "sku": prod["sku"],
                "deal_type": rng.choice(DEAL_TYPES),
                "start_day": start,
                "days": days,
                "discount_pct": disc,
                "platform_funding_share": share,
                "promo_fee": fee,
                "archetype": arch,
            })
        for d in range(1, HORIZON_DAYS + 1):
            sales.append({"day": d, "sku": prod["sku"], "units": _noisy(rng, mean[d]), "price": price[d]})
    return {"products": products, "deals": deals, "daily_sales": sales}


def write_csvs(dataset: dict, folder: str) -> None:
    os.makedirs(folder, exist_ok=True)
    for name, rows in dataset.items():
        with open(os.path.join(folder, f"{name}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


def read_csvs(folder: str) -> dict:
    out = {}
    num = {"list_price", "unit_cost", "discount_pct", "platform_funding_share", "price"}
    integer = {"base_daily_units", "start_day", "days", "promo_fee", "day", "units"}
    for name in ("products", "deals", "daily_sales"):
        with open(os.path.join(folder, f"{name}.csv"), newline="", encoding="utf-8") as f:
            rows = []
            for r in csv.DictReader(f):
                for k in r:
                    if k in num:
                        r[k] = float(r[k])
                    elif k in integer:
                        r[k] = int(r[k])
                rows.append(r)
            out[name] = rows
    return out
