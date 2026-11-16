from dealagent.data import HORIZON_DAYS, generate, read_csvs, write_csvs


def test_generation_is_deterministic():
    assert generate(seed=3) == generate(seed=3)
    assert generate(seed=3) != generate(seed=4)


def test_shape_and_ids():
    ds = generate(seed=7)
    assert len(ds["products"]) == 24 and len(ds["deals"]) == 48
    assert len(ds["daily_sales"]) == 24 * HORIZON_DAYS
    assert all(p["sku"].startswith("SKU-") for p in ds["products"])
    assert all(p["unit_cost"] < p["list_price"] for p in ds["products"])


def test_deals_on_one_sku_do_not_overlap():
    ds = generate(seed=7)
    by_sku = {}
    for d in ds["deals"]:
        by_sku.setdefault(d["sku"], []).append((d["start_day"], d["start_day"] + d["days"]))
    for spans in by_sku.values():
        spans.sort()
        assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))


def test_csv_round_trip(tmp_path):
    ds = generate(seed=7)
    write_csvs(ds, tmp_path)
    back = read_csvs(tmp_path)
    assert back["deals"] == ds["deals"]
    assert back["daily_sales"][:50] == ds["daily_sales"][:50]
