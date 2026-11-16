import pytest

from dealagent.metrics import Store, category_benchmark, deal_metrics


def tiny(units_deal=30, units_post=10, share=0.5, fee=0, disc=0.10, start=15):
    """One SKU, list 100, cost 60, steady 10 units a day, one 5-day deal."""
    sales = []
    for day in range(1, 41):
        in_deal = start <= day < start + 5
        in_post = start + 5 <= day < start + 12
        units = units_deal if in_deal else (units_post if in_post else 10)
        sales.append({"day": day, "sku": "SKU-0001", "units": units, "price": 100 * (1 - disc) if in_deal else 100.0})
    return Store({
        "products": [{"sku": "SKU-0001", "category": "Toys", "list_price": 100, "unit_cost": 60.0, "base_daily_units": 10}],
        "deals": [{"deal_id": "D-0001", "sku": "SKU-0001", "deal_type": "Coupon", "start_day": start, "days": 5,
                   "discount_pct": disc, "platform_funding_share": share, "promo_fee": fee, "archetype": "winner"}],
        "daily_sales": sales,
    })


def test_spikes_and_incrementals():
    m = deal_metrics(tiny(), "D-0001")
    assert m["baseline_daily_units"] == 10 and m["baseline_days"] == 14
    assert m["deal_units"] == 150
    assert m["units_spike"] == 3.0
    assert m["gms_spike"] == 2.7           # 150 units at 90 against 50 units at 100
    assert m["incremental_units"] == 100 and m["pull_forward_units"] == 0


def test_investment_and_profit_by_hand():
    m = deal_metrics(tiny(fee=200), "D-0001")
    # discount given = 150 * 100 * 10% = 1500; platform pays half = 750, plus the 200 fee
    assert m["investment"] == 950
    assert m["investment_pct_of_gms"] == pytest.approx(100 * 950 / 13500, abs=0.05)
    # margin 40 a unit: 150*40 - 200 fee - baseline 50*40 - platform discount 750 = 3050
    assert m["incremental_profit"] == 3050
    assert m["roi"] == pytest.approx(3050 / 950, abs=0.005)


def test_pull_forward_reduces_profit():
    clean = deal_metrics(tiny(), "D-0001")
    dipped = deal_metrics(tiny(units_post=6), "D-0001")
    assert dipped["pull_forward_units"] == 28          # (10 - 6) * 7 days
    assert dipped["net_incremental_units"] == 72
    assert dipped["incremental_profit"] == clean["incremental_profit"] - 28 * 40


def test_breakeven_share():
    m = deal_metrics(tiny(share=1.0, disc=0.30), "D-0001")
    # fully brand funded profit = 150*40 - 50*40 = 4000; discount given = 150*100*30% = 4500
    assert m["breakeven_platform_share_pct"] == pytest.approx(100 * 4000 / 4500, abs=0.05)
    assert m["incremental_profit"] == -500


def test_short_baseline_is_reported():
    m = deal_metrics(tiny(start=4), "D-0001")
    assert m["baseline_days"] == 3


def test_category_benchmark_counts_only_full_baselines():
    b = category_benchmark(tiny(), "Toys")
    assert b["deals_counted"] == 1 and b["median_units_spike"] == 3.0
    assert category_benchmark(tiny(start=4), "Toys")["deals_counted"] == 0
