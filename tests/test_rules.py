from dealagent.rules import verdict

BASE = {"baseline_days": 14, "units_spike": 2.5, "incremental_profit": 5000, "roi": 1.2,
        "breakeven_platform_share_pct": 80.0}


def case(**over):
    return verdict(dict(BASE, **over))


def test_repeat():
    assert case()["action"] == "REPEAT"


def test_thin_baseline_wins_over_everything():
    assert case(baseline_days=3)["action"] == "TEST_AGAIN"


def test_flat_volume_is_stopped_even_if_cheap():
    assert case(units_spike=1.1)["action"] == "STOP"


def test_loss_making_but_fixable_is_renegotiated_with_a_target():
    v = case(incremental_profit=-800, roi=-0.2, breakeven_platform_share_pct=60.0)
    assert v["action"] == "RENEGOTIATE" and v["target_platform_share_pct"] == 48


def test_thin_roi_is_renegotiated():
    assert case(incremental_profit=100, roi=0.05)["action"] == "RENEGOTIATE"


def test_unfixable_loss_is_stopped():
    assert case(incremental_profit=-800, roi=-0.2, breakeven_platform_share_pct=0.0)["action"] == "STOP"
