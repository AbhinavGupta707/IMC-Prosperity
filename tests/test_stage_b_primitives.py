"""Unit tests for Stage B primitives.

Covers:
- portfolio_context.PortfolioSnapshot
- volume_robust_mid.max_amount_mid / filtered_wall_mid / walls_and_mid
- hysteresis_sizer.target_position / clamp_by_capacity
- portfolio_risk.PortfolioRiskManager
"""

from __future__ import annotations

import pytest

from src.core.primitives.hysteresis_sizer import (
    HysteresisConfig,
    clamp_by_capacity,
    sizing_metadata,
    target_position,
)
from src.core.primitives.portfolio_context import (
    PortfolioSnapshot,
    build_portfolio_snapshot,
)
from src.core.primitives.portfolio_risk import (
    PortfolioRiskConfig,
    PortfolioRiskManager,
    ProductTag,
)
from src.core.primitives.volume_robust_mid import (
    WallMidConfig,
    filtered_wall_mid,
    max_amount_mid,
    walls_and_mid,
)
from src.core.types import BookLevel, NormalizedSnapshot


def _book(
    product: str,
    bids: list[tuple[int, int]],
    asks: list[tuple[int, int]],
    position: int = 0,
) -> NormalizedSnapshot:
    return NormalizedSnapshot(
        product=product,
        timestamp=0,
        bids=tuple(BookLevel(price=p, volume=v) for p, v in bids),
        asks=tuple(BookLevel(price=p, volume=v) for p, v in asks),
        position=position,
    )


# ========================================================== PortfolioSnapshot


@pytest.mark.unit
def test_portfolio_snapshot_builds_from_multiple_products():
    snaps = {
        "BASKET": _book("BASKET", [(99, 10)], [(101, 10)], position=5),
        "COCOA": _book("COCOA", [(9, 20)], [(11, 20)], position=-3),
    }
    limits = {"BASKET": 50, "COCOA": 100}
    portfolio = build_portfolio_snapshot(
        timestamp=1000, snapshots=snaps, position_limits=limits,
    )
    assert portfolio.for_product("BASKET") is not None
    assert portfolio.position_of("BASKET") == 5
    assert portfolio.position_of("COCOA") == -3
    assert portfolio.limit_of("BASKET") == 50
    assert set(portfolio.products()) == {"BASKET", "COCOA"}


@pytest.mark.unit
def test_portfolio_snapshot_missing_product_returns_none():
    p = build_portfolio_snapshot(timestamp=0, snapshots={}, position_limits={})
    assert p.for_product("ABSENT") is None
    assert p.position_of("ABSENT") == 0
    assert p.limit_of("ABSENT") == 0


@pytest.mark.unit
def test_portfolio_snapshot_is_immutable():
    p = build_portfolio_snapshot(timestamp=0, snapshots={}, position_limits={})
    with pytest.raises((TypeError, AttributeError)):
        p.snapshots["X"] = None  # type: ignore[index]


# ========================================================== wall-mid family


@pytest.mark.unit
def test_max_amount_mid_picks_largest_volume_level():
    snap = _book(
        "P",
        bids=[(9999, 5), (9998, 30), (9997, 3)],  # wall at 9998
        asks=[(10001, 5), (10002, 30), (10003, 3)],  # wall at 10002
    )
    mid = max_amount_mid(snap, WallMidConfig(min_volume=10, top_n_levels=3))
    assert mid == (9998 + 10002) / 2.0


@pytest.mark.unit
def test_max_amount_mid_falls_back_when_no_qualifier():
    snap = _book("P", bids=[(99, 1)], asks=[(101, 1)])
    # min_volume=10 filters both, but we fall back to best non-empty.
    mid = max_amount_mid(snap, WallMidConfig(min_volume=10))
    assert mid == 100.0


@pytest.mark.unit
def test_max_amount_mid_returns_none_on_empty_side():
    snap = _book("P", bids=[], asks=[(100, 5)])
    assert max_amount_mid(snap) is None


@pytest.mark.unit
def test_filtered_wall_mid_uses_ratio():
    snap = _book(
        "P",
        bids=[(99, 40), (98, 5), (97, 30)],  # ratio filter keeps 40 and 30
        asks=[(101, 10), (102, 20), (103, 5)],
    )
    # Default ratio 0.25: on bid side max=40, threshold=10, so 40 and 30 pass.
    mid = filtered_wall_mid(snap, WallMidConfig(volume_ratio_threshold=0.25))
    assert mid is not None and mid > 0


@pytest.mark.unit
def test_walls_and_mid_returns_levels():
    snap = _book(
        "P",
        bids=[(99, 5), (98, 30)],
        asks=[(101, 25), (102, 5)],
    )
    result = walls_and_mid(snap, WallMidConfig(min_volume=10))
    assert result is not None
    wall_bid, wall_ask, mid = result
    assert wall_bid.price == 98
    assert wall_ask.price == 101
    assert mid == (98 + 101) / 2.0


@pytest.mark.unit
def test_walls_and_mid_inside_placement():
    """The F2 pattern: quote inside the wall."""
    snap = _book("P", bids=[(98, 30)], asks=[(101, 25)])
    result = walls_and_mid(snap)
    assert result is not None
    wall_bid, wall_ask, _mid = result
    inside_bid = wall_bid.price + 1
    inside_ask = wall_ask.price - 1
    assert inside_bid == 99
    assert inside_ask == 100
    # Check they don't cross (would signal degenerate book).
    assert inside_bid < inside_ask


@pytest.mark.unit
def test_wallmid_config_validation():
    with pytest.raises(ValueError):
        WallMidConfig(min_volume=-1)
    with pytest.raises(ValueError):
        WallMidConfig(volume_ratio_threshold=2.0)
    with pytest.raises(ValueError):
        WallMidConfig(top_n_levels=0)


# ========================================================== hysteresis sizer


@pytest.mark.unit
def test_hysteresis_exits_inside_exit_z():
    cfg = HysteresisConfig(entry_z=2.0, exit_z=0.3, kill_z=4.0, max_position=60)
    assert target_position(z=0.2, current_position=30, config=cfg) == 0
    assert target_position(z=-0.1, current_position=-50, config=cfg) == 0


@pytest.mark.unit
def test_hysteresis_holds_between_exit_and_entry():
    cfg = HysteresisConfig(entry_z=2.0, exit_z=0.3, kill_z=4.0, max_position=60)
    # |z|=1.5 is in the hold zone; keep the existing position.
    assert target_position(z=1.5, current_position=25, config=cfg) == 25
    assert target_position(z=-1.0, current_position=-40, config=cfg) == -40


@pytest.mark.unit
def test_hysteresis_scales_in_active_zone():
    cfg = HysteresisConfig(
        entry_z=2.0, exit_z=0.3, kill_z=4.0, max_position=60, scale_exponent=1.0,
    )
    # At |z|=entry_z, position should be ~0 (just entered active zone).
    # Position grows monotonically as |z| increases toward kill_z.
    # At |z|=kill_z, kill zone freezes (returns current_position=0).
    t1 = target_position(z=2.0, current_position=0, config=cfg)
    t2 = target_position(z=3.0, current_position=0, config=cfg)
    t3 = target_position(z=3.9, current_position=0, config=cfg)  # just below kill
    assert 0 <= abs(t1) < abs(t2) < abs(t3) <= cfg.max_position
    # Kill zone should freeze, not size up.
    t_kill = target_position(z=5.0, current_position=0, config=cfg)
    assert t_kill == 0


@pytest.mark.unit
def test_hysteresis_kill_zone_freezes():
    cfg = HysteresisConfig(kill_z=4.0, max_position=60)
    # At kill_z, hold current (don't grow further).
    assert target_position(z=5.0, current_position=40, config=cfg) == 40
    assert target_position(z=-4.5, current_position=-20, config=cfg) == -20


@pytest.mark.unit
def test_hysteresis_sign_convention():
    """Positive z ⇒ long; negative z ⇒ short."""
    cfg = HysteresisConfig(entry_z=2.0, exit_z=0.3, kill_z=4.0, max_position=60)
    assert target_position(z=3.0, current_position=0, config=cfg) > 0
    assert target_position(z=-3.0, current_position=0, config=cfg) < 0


@pytest.mark.unit
def test_clamp_by_capacity():
    assert clamp_by_capacity(target=100, current=0, limit=50) == 50
    assert clamp_by_capacity(target=-100, current=0, limit=50) == -50
    assert clamp_by_capacity(target=20, current=0, limit=50) == 20


@pytest.mark.unit
def test_hysteresis_config_validation():
    with pytest.raises(ValueError):
        HysteresisConfig(exit_z=2.0, entry_z=1.0)  # violates ordering
    with pytest.raises(ValueError):
        HysteresisConfig(max_position=0)


@pytest.mark.unit
def test_sizing_metadata_regime_labels():
    cfg = HysteresisConfig(entry_z=2.0, exit_z=0.3, kill_z=4.0)
    meta = sizing_metadata(z=0.1, current_position=0, target=0, config=cfg)
    assert meta["regime"] == "exit"
    meta = sizing_metadata(z=1.0, current_position=10, target=10, config=cfg)
    assert meta["regime"] == "hold"
    meta = sizing_metadata(z=3.0, current_position=0, target=30, config=cfg)
    assert meta["regime"] == "active"
    meta = sizing_metadata(z=5.0, current_position=30, target=30, config=cfg)
    assert meta["regime"] == "kill"


# ========================================================== portfolio risk


@pytest.mark.unit
def test_portfolio_risk_manager_delegates_to_base():
    from src.datamodel import Order

    mgr = PortfolioRiskManager()
    orders = [Order("P", 100, 50)]
    clipped = mgr.clip_orders("P", orders, current_position=70, limit=80)
    # Only 10 remaining buy capacity.
    assert len(clipped) == 1 and clipped[0].quantity == 10


@pytest.mark.unit
def test_portfolio_capacity_aggregates_gross():
    mgr = PortfolioRiskManager()
    cap = mgr.portfolio_capacity(
        positions={"A": 20, "B": -30, "C": 0},
        limits={"A": 50, "B": 50, "C": 50},
    )
    assert cap.gross_exposure == 50  # |20| + |30| + |0|


@pytest.mark.unit
def test_portfolio_capacity_groups_by_arb():
    mgr = PortfolioRiskManager()
    tags = {
        "BASKET": ProductTag(product="BASKET", strategy_tag="arb", arb_group="B1"),
        "COCOA": ProductTag(product="COCOA", strategy_tag="arb", arb_group="B1"),
        "SUGAR": ProductTag(product="SUGAR", strategy_tag="mm"),
    }
    cap = mgr.portfolio_capacity(
        positions={"BASKET": 10, "COCOA": -20, "SUGAR": 5},
        limits={"BASKET": 50, "COCOA": 100, "SUGAR": 30},
        tags=tags,
    )
    assert cap.net_exposure_by_group["B1"] == -10  # 10 + (-20)
    assert "default" not in cap.net_exposure_by_group


@pytest.mark.unit
def test_residual_allowed_default_for_arb():
    mgr = PortfolioRiskManager(
        config=PortfolioRiskConfig(residual_default_on_for_arb=True),
    )
    assert mgr.residual_allowed(ProductTag(product="X", strategy_tag="arb"))
    assert not mgr.residual_allowed(ProductTag(product="X", strategy_tag="mm"))
    assert not mgr.residual_allowed(ProductTag(product="X", strategy_tag="hedger"))


@pytest.mark.unit
def test_residual_allowed_off_when_config_disables():
    mgr = PortfolioRiskManager(
        config=PortfolioRiskConfig(residual_default_on_for_arb=False),
    )
    assert not mgr.residual_allowed(ProductTag(product="X", strategy_tag="arb"))


@pytest.mark.unit
def test_gross_and_group_cap_checks():
    mgr = PortfolioRiskManager(
        config=PortfolioRiskConfig(
            max_gross_exposure=100, max_net_exposure_per_group=50,
        ),
    )
    assert mgr.exceeds_gross_cap(150)
    assert not mgr.exceeds_gross_cap(50)
    assert mgr.exceeds_group_cap(60)
    assert not mgr.exceeds_group_cap(30)
