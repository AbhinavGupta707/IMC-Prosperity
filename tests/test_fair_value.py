"""Unit tests for ``src.core.fair_value``."""

from __future__ import annotations

import pytest

from src.core.config import ProductConfig
from src.core.fair_value import (
    _DEFAULT_EWMA_ALPHA,
    AnchorEstimator,
    DepthMidEstimator,
    EwmaMidEstimator,
    FairValueEngine,
    FilteredWallMidEstimator,
    HybridWallMicroEstimator,
    LinearDriftEstimator,
    MicropriceEstimator,
    MidEstimator,
    RollingMidEstimator,
    WallMidEstimator,
    WeightedMidEstimator,
)
from src.core.types import BookLevel, NormalizedSnapshot, ProductMemory


def _anchor_config(price: float = 10_000.0) -> ProductConfig:
    return ProductConfig(
        position_limit=20,
        strategy_name="market_making",
        fair_value_method="anchor",
        fair_value_fallbacks=("microprice", "mid"),
        anchor_price=price,
    )


def _mid_config() -> ProductConfig:
    return ProductConfig(
        position_limit=20,
        strategy_name="market_making",
        fair_value_method="mid",
        fair_value_fallbacks=(),
    )


def _ewma_config(alpha: float | None = None) -> ProductConfig:
    return ProductConfig(
        position_limit=20,
        strategy_name="market_making",
        fair_value_method="ewma_mid",
        fair_value_fallbacks=("mid",),
        ewma_alpha=alpha,
    )


def _snapshot(
    *, bid: int = 9998, bid_vol: int = 5, ask: int = 10002, ask_vol: int = 5
) -> NormalizedSnapshot:
    return NormalizedSnapshot(
        product="P",
        timestamp=0,
        bids=(BookLevel(bid, bid_vol),),
        asks=(BookLevel(ask, ask_vol),),
        position=0,
    )


@pytest.mark.unit
def test_anchor_estimator_returns_anchor_price() -> None:
    result = AnchorEstimator().estimate(_snapshot(), ProductMemory(), _anchor_config())
    assert result is not None
    assert result.price == 10_000.0
    assert result.method == "anchor"
    assert result.components["anchor_price"] == 10_000.0


@pytest.mark.unit
def test_anchor_estimator_returns_none_without_anchor_price() -> None:
    config = _mid_config()  # no anchor_price set
    result = AnchorEstimator().estimate(_snapshot(), ProductMemory(), config)
    assert result is None


@pytest.mark.unit
def test_mid_microprice_estimators_return_expected_values() -> None:
    memory = ProductMemory()
    config = _mid_config()
    snap = _snapshot(bid=100, bid_vol=3, ask=102, ask_vol=1)
    mid = MidEstimator().estimate(snap, memory, config)
    micro = MicropriceEstimator().estimate(snap, memory, config)
    assert mid is not None
    assert mid.price == 101.0
    assert micro is not None
    # (100 * 1 + 102 * 3) / 4 = 101.5
    assert micro.price == pytest.approx(101.5)


@pytest.mark.unit
def test_rolling_mid_averages_history_and_current_mid() -> None:
    memory = ProductMemory(recent_mids=[99.0, 100.0, 101.0])
    snap = _snapshot(bid=100, bid_vol=1, ask=102, ask_vol=1)  # mid 101
    result = RollingMidEstimator().estimate(snap, memory, _mid_config())
    assert result is not None
    # Mean of [99, 100, 101, 101] = 100.25
    assert result.price == pytest.approx(100.25)


@pytest.mark.unit
def test_weighted_mid_puts_more_weight_on_recent_mids() -> None:
    memory = ProductMemory(recent_mids=[100.0, 100.0, 100.0, 100.0])
    snap = _snapshot(bid=110, bid_vol=1, ask=110, ask_vol=1)  # mid 110
    result = WeightedMidEstimator().estimate(snap, memory, _mid_config())
    assert result is not None
    # Weights 1..5; values [100, 100, 100, 100, 110]; total_w = 15
    # num = 100*1 + 100*2 + 100*3 + 100*4 + 110*5 = 1000 + 550 = 1550? no
    # = 100+200+300+400+550 = 1550 → 1550/15 = 103.333
    assert result.price == pytest.approx(103.3333, rel=1e-3)


@pytest.mark.unit
def test_depth_mid_uses_all_visible_levels() -> None:
    snap = NormalizedSnapshot(
        product="P",
        timestamp=0,
        bids=(BookLevel(100, 1), BookLevel(99, 3)),
        asks=(BookLevel(102, 1), BookLevel(103, 3)),
        position=0,
    )

    result = DepthMidEstimator().estimate(snap, ProductMemory(), _mid_config())

    assert result is not None
    # bid_vwap = (100*1 + 99*3) / 4 = 99.25
    # ask_vwap = (102*1 + 103*3) / 4 = 102.75
    assert result.price == pytest.approx(101.0)
    assert result.components["bid_vwap"] == pytest.approx(99.25)
    assert result.components["ask_vwap"] == pytest.approx(102.75)


@pytest.mark.unit
def test_ewma_formula_matches_expected_recurrence() -> None:
    """Hand-computed EWMA: alpha=0.5, history=[100, 102], mid=104.

    Seed with the first sample (100), then:
      step 1: 0.5*102 + 0.5*100 = 101
      step 2 (current mid 104): 0.5*104 + 0.5*101 = 102.5
    """
    memory = ProductMemory(recent_mids=[100.0, 102.0])
    snap = _snapshot(bid=103, bid_vol=1, ask=105, ask_vol=1)  # mid 104
    config = _ewma_config(alpha=0.5)
    result = EwmaMidEstimator().estimate(snap, memory, config)
    assert result is not None
    assert result.price == pytest.approx(102.5)
    assert result.method == "ewma_mid"
    assert result.components["alpha"] == pytest.approx(0.5)
    assert "bootstrap" not in result.components


@pytest.mark.unit
def test_ewma_alpha_one_equals_current_mid() -> None:
    """alpha=1 should discard history entirely and return the current mid."""
    memory = ProductMemory(recent_mids=[50.0, 60.0, 70.0])
    snap = _snapshot(bid=199, bid_vol=1, ask=201, ask_vol=1)  # mid 200
    result = EwmaMidEstimator().estimate(snap, memory, _ewma_config(alpha=1.0))
    assert result is not None
    assert result.price == pytest.approx(200.0)


@pytest.mark.unit
def test_ewma_empty_history_uses_current_mid_as_bootstrap() -> None:
    memory = ProductMemory()
    snap = _snapshot(bid=99, bid_vol=1, ask=101, ask_vol=1)  # mid 100
    result = EwmaMidEstimator().estimate(snap, memory, _ewma_config(alpha=0.3))
    assert result is not None
    assert result.price == pytest.approx(100.0)
    assert result.components["bootstrap"] == pytest.approx(1.0)


@pytest.mark.unit
def test_ewma_one_sample_history_blends_with_current_mid() -> None:
    memory = ProductMemory(recent_mids=[100.0])
    snap = _snapshot(bid=109, bid_vol=1, ask=111, ask_vol=1)  # mid 110
    result = EwmaMidEstimator().estimate(snap, memory, _ewma_config(alpha=0.4))
    assert result is not None
    # Seed 100 then blend current 110 at alpha 0.4 -> 0.4*110 + 0.6*100 = 104
    assert result.price == pytest.approx(104.0)


@pytest.mark.unit
def test_ewma_returns_none_when_no_mid_and_no_history() -> None:
    memory = ProductMemory()
    snap = NormalizedSnapshot(product="P", timestamp=0, bids=(), asks=())
    result = EwmaMidEstimator().estimate(snap, memory, _ewma_config(alpha=0.3))
    assert result is None


@pytest.mark.unit
def test_ewma_uses_config_alpha_when_present() -> None:
    memory = ProductMemory(recent_mids=[100.0, 100.0, 100.0])
    snap = _snapshot(bid=119, bid_vol=1, ask=121, ask_vol=1)  # mid 120
    low = EwmaMidEstimator().estimate(snap, memory, _ewma_config(alpha=0.1))
    high = EwmaMidEstimator().estimate(snap, memory, _ewma_config(alpha=0.9))
    assert low is not None
    assert high is not None
    # Larger alpha -> closer to current mid (120). Smaller alpha -> closer to 100.
    assert low.price < high.price
    assert abs(low.price - 100.0) < abs(low.price - 120.0)
    assert abs(high.price - 120.0) < abs(high.price - 100.0)


@pytest.mark.unit
def test_ewma_defaults_to_module_alpha_when_config_is_none() -> None:
    memory = ProductMemory(recent_mids=[100.0, 100.0, 100.0])
    snap = _snapshot(bid=119, bid_vol=1, ask=121, ask_vol=1)  # mid 120
    default = EwmaMidEstimator().estimate(snap, memory, _ewma_config(alpha=None))
    explicit = EwmaMidEstimator().estimate(
        snap, memory, _ewma_config(alpha=_DEFAULT_EWMA_ALPHA)
    )
    assert default is not None
    assert explicit is not None
    assert default.price == pytest.approx(explicit.price)


@pytest.mark.unit
def test_engine_falls_back_from_ewma_mid_when_none() -> None:
    """With empty memory and a one-sided book, ewma_mid returns None and the
    engine falls through to the configured fallback chain.
    """
    config = ProductConfig(
        position_limit=20,
        strategy_name="market_making",
        fair_value_method="ewma_mid",
        fair_value_fallbacks=("mid", "microprice"),
        anchor_price=10_000.0,
        ewma_alpha=0.3,
    )
    snap = NormalizedSnapshot(product="P", timestamp=0, bids=(), asks=())
    result = FairValueEngine().estimate("P", snap, ProductMemory(), config)
    # Both mid and microprice also decline on an empty book, so the engine
    # should land on the anchor_fallback terminal clause.
    assert result.method == "anchor_fallback"
    assert result.price == 10_000.0


@pytest.mark.unit
def test_engine_primary_falls_through_to_next_when_returning_none() -> None:
    """If weighted_mid has no mid and no history, fall through to anchor."""
    config = ProductConfig(
        position_limit=20,
        strategy_name="market_making",
        fair_value_method="weighted_mid",
        fair_value_fallbacks=("anchor",),
        anchor_price=10_000.0,
    )
    # Snapshot with no bids (so mid is None) and empty memory.
    snap = NormalizedSnapshot(product="P", timestamp=0, bids=(), asks=())
    engine = FairValueEngine()
    result = engine.estimate("P", snap, ProductMemory(), config)
    assert result.method == "anchor"
    assert result.price == 10_000.0


@pytest.mark.unit
def test_engine_returns_anchor_fallback_when_all_estimators_decline() -> None:
    """No primary, no fallback, no mid -> anchor_fallback."""
    config = ProductConfig(
        position_limit=20,
        strategy_name="market_making",
        fair_value_method="mid",
        fair_value_fallbacks=(),
        anchor_price=50.0,
    )
    snap = NormalizedSnapshot(product="P", timestamp=0, bids=(), asks=())
    result = FairValueEngine().estimate("P", snap, ProductMemory(), config)
    assert result.method == "anchor_fallback"
    assert result.price == 50.0


@pytest.mark.unit
def test_estimate_all_returns_every_non_none_estimator() -> None:
    engine = FairValueEngine()
    snap = _snapshot(bid=99, bid_vol=2, ask=101, ask_vol=2)
    results = engine.estimate_all(snap, ProductMemory(), _anchor_config())
    assert "anchor" in results
    assert "mid" in results
    assert "microprice" in results
    # rolling_mid and weighted_mid work too because snap has a mid
    assert "rolling_mid" in results
    assert "weighted_mid" in results
    assert "ewma_mid" in results
    assert "depth_mid" in results
    assert results["anchor"].price == 10_000.0
    assert results["mid"].price == 100.0


@pytest.mark.unit
def test_fair_value_estimate_components_is_immutable() -> None:
    """Regression guard: frozen + MappingProxyType should reject mutation."""
    result = AnchorEstimator().estimate(_snapshot(), ProductMemory(), _anchor_config())
    assert result is not None
    with pytest.raises(TypeError):
        result.components["x"] = 1  # type: ignore[index]


# ---- Phase 2: WallMidEstimator tests ----


@pytest.mark.unit
def test_wall_mid_symmetric_book() -> None:
    """Wall mid of symmetric book equals regular mid."""
    snap = _snapshot(bid=100, bid_vol=10, ask=102, ask_vol=10)
    result = WallMidEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is not None
    assert result.price == pytest.approx(101.0)
    assert result.method == "wall_mid"


@pytest.mark.unit
def test_wall_mid_asymmetric_book_picks_largest_levels() -> None:
    """Wall mid picks the biggest volume levels on each side."""
    snap = NormalizedSnapshot(
        product="P",
        timestamp=0,
        bids=(BookLevel(100, 5), BookLevel(98, 20)),  # wall at 98
        asks=(BookLevel(102, 5), BookLevel(104, 20)),  # wall at 104
    )
    result = WallMidEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is not None
    assert result.price == pytest.approx(101.0)  # (98 + 104) / 2
    assert result.components["wall_bid_price"] == 98
    assert result.components["wall_ask_price"] == 104


@pytest.mark.unit
def test_wall_mid_empty_side_returns_none() -> None:
    snap = NormalizedSnapshot(product="P", timestamp=0, bids=(), asks=(BookLevel(102, 5),))
    result = WallMidEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is None


@pytest.mark.unit
def test_wall_mid_single_level_per_side() -> None:
    snap = _snapshot(bid=100, bid_vol=5, ask=102, ask_vol=5)
    result = WallMidEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is not None
    assert result.price == pytest.approx(101.0)
    assert result.components["wall_bid_vol"] == 5


# ---- Phase 2: FilteredWallMidEstimator tests ----


@pytest.mark.unit
def test_filtered_wall_mid_filters_small_levels() -> None:
    """Levels with vol < 25% of max are filtered out."""
    snap = NormalizedSnapshot(
        product="P",
        timestamp=0,
        bids=(BookLevel(100, 20), BookLevel(99, 1)),  # 1 < 20*0.25=5 -> filtered
        asks=(BookLevel(102, 20), BookLevel(103, 1)),  # 1 < 20*0.25=5 -> filtered
    )
    result = FilteredWallMidEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is not None
    assert result.price == pytest.approx(101.0)  # (100 + 102) / 2
    assert result.components["filtered_out_count"] == 2


@pytest.mark.unit
def test_filtered_wall_mid_returns_none_on_empty_side() -> None:
    snap = NormalizedSnapshot(product="P", timestamp=0, bids=(), asks=(BookLevel(102, 5),))
    result = FilteredWallMidEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is None


@pytest.mark.unit
def test_filtered_wall_mid_tie_break_by_proximity_to_touch() -> None:
    """Equal volume: pick the level closest to touch (index 0)."""
    snap = NormalizedSnapshot(
        product="P",
        timestamp=0,
        bids=(BookLevel(100, 10), BookLevel(99, 10), BookLevel(98, 10)),
        asks=(BookLevel(102, 10), BookLevel(103, 10), BookLevel(104, 10)),
    )
    result = FilteredWallMidEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is not None
    assert result.components["wall_bid_price"] == 100
    assert result.components["wall_ask_price"] == 102


# ---- Phase 2: HybridWallMicroEstimator tests ----


@pytest.mark.unit
def test_hybrid_wall_micro_blends_correctly() -> None:
    snap = _snapshot(bid=100, bid_vol=3, ask=102, ask_vol=1)
    result = HybridWallMicroEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is not None
    # wall_mid = (100 + 102) / 2 = 101.0
    # microprice = (100*1 + 102*3) / 4 = 101.5
    # hybrid = 0.5 * 101.0 + 0.5 * 101.5 = 101.25
    assert result.price == pytest.approx(101.25)
    assert result.components["wall_weight"] == pytest.approx(0.5)


@pytest.mark.unit
def test_hybrid_wall_micro_symmetric_book() -> None:
    """When wall_mid == microprice, blend equals both."""
    snap = _snapshot(bid=100, bid_vol=5, ask=102, ask_vol=5)
    result = HybridWallMicroEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is not None
    assert result.price == pytest.approx(101.0)


@pytest.mark.unit
def test_hybrid_wall_micro_none_when_both_missing() -> None:
    snap = NormalizedSnapshot(product="P", timestamp=0, bids=(), asks=())
    result = HybridWallMicroEstimator().estimate(snap, ProductMemory(), _mid_config())
    assert result is None


# ---- Phase 2: Registration tests ----


@pytest.mark.unit
def test_weighted_mid_respects_history_length() -> None:
    """history_length controls the lookback window for weighted_mid.

    Regression guard: previously weighted_mid hardcoded LOOKBACK=4,
    making history_length sweeps a no-op.
    """
    # 8 mids: first 4 are 90, last 4 are 100
    memory = ProductMemory(recent_mids=[90.0, 90.0, 90.0, 90.0, 100.0, 100.0, 100.0, 100.0])
    snap = _snapshot(bid=100, bid_vol=1, ask=100, ask_vol=1)  # mid 100

    short_config = ProductConfig(
        position_limit=20,
        strategy_name="market_making",
        fair_value_method="weighted_mid",
        fair_value_fallbacks=(),
        history_length=4,
    )
    long_config = ProductConfig(
        position_limit=20,
        strategy_name="market_making",
        fair_value_method="weighted_mid",
        fair_value_fallbacks=(),
        history_length=8,
    )

    short_result = WeightedMidEstimator().estimate(snap, memory, short_config)
    long_result = WeightedMidEstimator().estimate(snap, memory, long_config)

    assert short_result is not None and long_result is not None
    # With history_length=4: uses [100,100,100,100] + mid 100 -> all 100
    assert short_result.price == pytest.approx(100.0)
    # With history_length=8: uses [90,90,90,90,100,100,100,100] + mid 100
    # The 90s pull the weighted average below 100
    assert long_result.price < short_result.price


@pytest.mark.unit
def test_new_estimators_in_estimate_all() -> None:
    """All three new estimators appear in estimate_all output."""
    engine = FairValueEngine()
    snap = _snapshot(bid=99, bid_vol=2, ask=101, ask_vol=2)
    results = engine.estimate_all(snap, ProductMemory(), _anchor_config())
    assert "wall_mid" in results
    assert "filtered_wall_mid" in results
    assert "hybrid_wall_micro" in results


def _linear_drift_config(history_length: int = 32) -> ProductConfig:
    return ProductConfig(
        position_limit=20,
        strategy_name="market_making",
        fair_value_method="linear_drift",
        fair_value_fallbacks=("mid",),
        history_length=history_length,
    )


@pytest.mark.unit
def test_linear_drift_returns_none_when_no_data() -> None:
    """With empty memory and a one-sided book, the estimator declines."""
    snap = NormalizedSnapshot(
        product="P",
        timestamp=0,
        bids=(BookLevel(99, 5),),
        asks=(),
    )
    result = LinearDriftEstimator().estimate(snap, ProductMemory(), _linear_drift_config())
    assert result is None


@pytest.mark.unit
def test_linear_drift_bootstrap_uses_current_mid() -> None:
    """With empty memory but a current mid, fall back to current mid."""
    snap = _snapshot(bid=100, ask=102)  # mid = 101
    result = LinearDriftEstimator().estimate(snap, ProductMemory(), _linear_drift_config())
    assert result is not None
    assert result.price == pytest.approx(101.0)
    assert result.components.get("bootstrap") == 1.0


@pytest.mark.unit
def test_linear_drift_projects_constant_slope() -> None:
    """On a perfectly linear history, slope is recovered and next step is projected."""
    # History: 100, 101, 102, 103 (slope +1 per step).  Current mid = 104.
    memory = ProductMemory(recent_mids=[100.0, 101.0, 102.0, 103.0])
    snap = _snapshot(bid=103, bid_vol=1, ask=105, ask_vol=1)  # mid = 104
    result = LinearDriftEstimator().estimate(snap, memory, _linear_drift_config())
    assert result is not None
    # 5 samples total (history + current); OLS fit slope ≈ 1.0.
    # Forecast at index n=5: slope * 5 + intercept = 105.0.
    assert result.price == pytest.approx(105.0)
    assert result.components["slope"] == pytest.approx(1.0)


@pytest.mark.unit
def test_linear_drift_flat_history_returns_intercept() -> None:
    """When mids are constant, slope is zero and the forecast equals the level."""
    memory = ProductMemory(recent_mids=[100.0, 100.0, 100.0, 100.0])
    snap = _snapshot(bid=99, bid_vol=1, ask=101, ask_vol=1)  # mid = 100
    result = LinearDriftEstimator().estimate(snap, memory, _linear_drift_config())
    assert result is not None
    assert result.price == pytest.approx(100.0)
    assert result.components["slope"] == pytest.approx(0.0)


@pytest.mark.unit
def test_linear_drift_respects_history_length() -> None:
    """A short history_length ignores the older samples."""
    # First four samples trend down, last four trend up.
    memory = ProductMemory(
        recent_mids=[120.0, 115.0, 110.0, 105.0, 100.0, 102.0, 104.0, 106.0]
    )
    snap = _snapshot(bid=107, bid_vol=1, ask=109, ask_vol=1)  # mid = 108

    short_config = _linear_drift_config(history_length=4)
    long_config = _linear_drift_config(history_length=8)

    short_result = LinearDriftEstimator().estimate(snap, memory, short_config)
    long_result = LinearDriftEstimator().estimate(snap, memory, long_config)

    assert short_result is not None and long_result is not None
    # Short window uses [100, 102, 104, 106, 108] (last 4 of history + current):
    # clean +2/step upward drift.
    assert short_result.components["slope"] == pytest.approx(2.0)
    # Long window blends the down-trend with the up-trend; slope is less
    # steep upward (and the forecast is below the short-window forecast).
    assert long_result.components["slope"] < short_result.components["slope"]


@pytest.mark.unit
def test_linear_drift_single_prior_falls_back_to_last_mid() -> None:
    """With only one mid in memory and no current mid, echo that sample."""
    memory = ProductMemory(recent_mids=[100.0])
    snap = NormalizedSnapshot(
        product="P", timestamp=0, bids=(BookLevel(99, 1),), asks=()
    )
    result = LinearDriftEstimator().estimate(snap, memory, _linear_drift_config())
    assert result is not None
    assert result.price == pytest.approx(100.0)
    assert result.components.get("bootstrap") == 1.0


@pytest.mark.unit
def test_linear_drift_in_estimate_all() -> None:
    """Linear drift is registered in the default engine."""
    engine = FairValueEngine()
    snap = _snapshot(bid=99, bid_vol=2, ask=101, ask_vol=2)
    memory = ProductMemory(recent_mids=[95.0, 97.0, 99.0])
    results = engine.estimate_all(snap, memory, _linear_drift_config())
    assert "linear_drift" in results
