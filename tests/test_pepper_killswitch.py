"""Round-2 PEPPER kill-switch evaluator — isolated unit coverage.

Each of the four kill switches is tested in isolation (other three
disabled) so a firing can be attributed unambiguously. Plus cross-
cutting tests:

- default params → all four disabled, evaluator is a no-op
- day-rollover resets every counter and flag
- intraday-PnL halt is sticky for the rest of the day
- latch + release hysteresis on residual signal
- countdown behaviour on slope and step-move pauses

State layout in ProductMemory (``counters``, ``values``) is asserted
where it materially affects behaviour — these keys are a documented
contract, not an implementation detail (the day-rollover reset and
the Trader cross-product state store both depend on them).
"""

from __future__ import annotations

import pytest

from src.strategies.pepper_core_long import (
    CoreLongParams,
    KillSwitchDecision,
    evaluate_kill_switches,
)


# ---------- validation ----------


@pytest.mark.unit
def test_core_long_params_defaults_all_kills_disabled() -> None:
    p = CoreLongParams()
    assert p.kill_consecutive_neg_slope_n == 0
    assert p.kill_residual_threshold == 0.0
    assert p.kill_step_move_threshold == 0.0
    assert p.kill_intraday_pnl_threshold == 0.0


@pytest.mark.unit
def test_core_long_params_rejects_negative_kill_values() -> None:
    with pytest.raises(ValueError, match="kill_consecutive_neg_slope_n must be >= 0"):
        CoreLongParams(kill_consecutive_neg_slope_n=-1)
    with pytest.raises(ValueError, match="kill_residual_threshold must be >= 0"):
        CoreLongParams(kill_residual_threshold=-5.0)
    with pytest.raises(ValueError, match="kill_step_move_threshold must be >= 0"):
        CoreLongParams(kill_step_move_threshold=-5.0)
    with pytest.raises(ValueError, match="kill_intraday_pnl_threshold must be >= 0"):
        CoreLongParams(kill_intraday_pnl_threshold=-1.0)


@pytest.mark.unit
def test_core_long_params_residual_release_below_threshold() -> None:
    # release >= threshold would never release (flap).
    with pytest.raises(ValueError, match="kill_residual_release must be <"):
        CoreLongParams(kill_residual_threshold=35.0, kill_residual_release=35.0)
    with pytest.raises(ValueError, match="kill_residual_release must be <"):
        CoreLongParams(kill_residual_threshold=35.0, kill_residual_release=40.0)


@pytest.mark.unit
def test_core_long_params_slope_kill_requires_window_and_pause() -> None:
    with pytest.raises(ValueError, match="kill_slope_window must be >= 2"):
        CoreLongParams(
            kill_slope_window=1,
            kill_consecutive_neg_slope_n=5,
            kill_slope_pause_snaps=20,
        )
    with pytest.raises(ValueError, match="kill_slope_pause_snaps must be > 0"):
        CoreLongParams(
            kill_slope_window=50,
            kill_consecutive_neg_slope_n=5,
            kill_slope_pause_snaps=0,
        )


@pytest.mark.unit
def test_core_long_params_step_move_requires_pause() -> None:
    with pytest.raises(ValueError, match="kill_step_move_pause_snaps must be > 0"):
        CoreLongParams(
            kill_step_move_threshold=40.0,
            kill_step_move_pause_snaps=0,
        )


# ---------- helpers ----------


def _fire(params: CoreLongParams, **overrides):
    defaults = {
        "params": params,
        "snapshot_timestamp": 0,
        "current_mid": 12_000.0,
        "position": 0,
        "slope": 0.1,
        "residual": 0.0,
        "memory_counters": {},
        "memory_values": {},
    }
    defaults.update(overrides)
    return evaluate_kill_switches(**defaults)


# ---------- default: evaluator is a no-op ----------


@pytest.mark.unit
def test_default_params_evaluator_returns_no_firing() -> None:
    p = CoreLongParams()
    counters: dict[str, int] = {}
    values: dict[str, float] = {}
    d = _fire(p, memory_counters=counters, memory_values=values)
    assert d == KillSwitchDecision(False, False, tuple())


@pytest.mark.unit
def test_default_params_evaluator_still_tracks_day_open_mid_and_last_mid() -> None:
    # Even with every switch off we keep the invariants the latch/
    # Δmid checks need — so turning on a switch mid-day does not
    # reference an unset key.
    p = CoreLongParams()
    counters: dict[str, int] = {}
    values: dict[str, float] = {}
    _fire(p, memory_counters=counters, memory_values=values, current_mid=12_345.0)
    assert values["kill_day_open_mid"] == 12_345.0
    assert values["kill_last_mid"] == 12_345.0
    assert counters["kill_seen_ts_high"] == 0


# ---------- signal #1: rolling slope, consecutive negative ----------


@pytest.mark.unit
def test_slope_kill_fires_after_n_consecutive_negative_and_pauses_for_k_snaps() -> None:
    p = CoreLongParams(
        kill_slope_window=50,
        kill_consecutive_neg_slope_n=3,
        kill_slope_pause_snaps=5,
    )
    counters: dict[str, int] = {}
    values: dict[str, float] = {}

    # Three consecutive negative-slope snaps → fire on the 3rd.
    for i, slope in enumerate([-0.01, -0.01, -0.01]):
        d = _fire(
            p,
            snapshot_timestamp=100 * (i + 1),
            current_mid=12_000.0 - i,
            slope=slope,
            memory_counters=counters,
            memory_values=values,
        )
        if i < 2:
            assert not d.buy_paused, f"should not fire at step {i}"
        else:
            assert d.buy_paused, "should fire on 3rd consecutive"
            assert "slope_fire" in d.reasons

    # Next 4 snaps are inside the 5-snap pause (buy paused, no slope check).
    for i in range(4):
        d = _fire(
            p,
            snapshot_timestamp=500 + 100 * i,
            current_mid=12_000.0,
            slope=0.5,  # positive now — irrelevant, we're in pause
            memory_counters=counters,
            memory_values=values,
        )
        assert d.buy_paused, f"pause snap {i} should still be paused"
        assert "slope_pause" in d.reasons

    # Pause expires → 6th snap post-fire is free.
    d = _fire(
        p,
        snapshot_timestamp=900,
        current_mid=12_000.0,
        slope=0.2,
        memory_counters=counters,
        memory_values=values,
    )
    assert not d.buy_paused


@pytest.mark.unit
def test_slope_kill_resets_counter_on_non_negative_snap() -> None:
    p = CoreLongParams(
        kill_slope_window=50, kill_consecutive_neg_slope_n=3, kill_slope_pause_snaps=5
    )
    counters: dict[str, int] = {}
    values: dict[str, float] = {}
    # Two negative, then one positive, then two more negative → never fires
    for i, slope in enumerate([-0.1, -0.1, 0.05, -0.1, -0.1]):
        d = _fire(
            p,
            snapshot_timestamp=100 * (i + 1),
            current_mid=12_000.0,
            slope=slope,
            memory_counters=counters,
            memory_values=values,
        )
        assert not d.buy_paused


# ---------- signal #2: residual latch ----------


@pytest.mark.unit
def test_residual_kill_fires_then_releases_on_hysteresis() -> None:
    p = CoreLongParams(kill_residual_threshold=35.0, kill_residual_release=15.0)
    counters: dict[str, int] = {}
    values: dict[str, float] = {}

    # Above threshold (residual = -40) → fire
    d = _fire(p, residual=-40.0, memory_counters=counters, memory_values=values)
    assert d.buy_paused and "residual_fire" in d.reasons

    # Still below release (-20 < -15) → stay paused
    d = _fire(
        p, snapshot_timestamp=100, residual=-20.0, memory_counters=counters, memory_values=values
    )
    assert d.buy_paused and "residual_pause" in d.reasons

    # Residual climbs to -10 (above -release) → release
    d = _fire(
        p, snapshot_timestamp=200, residual=-10.0, memory_counters=counters, memory_values=values
    )
    assert not d.buy_paused


@pytest.mark.unit
def test_residual_kill_never_fires_below_threshold_magnitude() -> None:
    p = CoreLongParams(kill_residual_threshold=35.0, kill_residual_release=15.0)
    counters: dict[str, int] = {}
    values: dict[str, float] = {}
    # Worst empirical residual on PEPPER tape was -11 (batch-B spec)
    d = _fire(p, residual=-11.0, memory_counters=counters, memory_values=values)
    assert not d.buy_paused


# ---------- signal #3: single-step Δmid ----------


@pytest.mark.unit
def test_step_move_kill_fires_on_large_negative_delta() -> None:
    p = CoreLongParams(kill_step_move_threshold=40.0, kill_step_move_pause_snaps=3)
    counters: dict[str, int] = {}
    values: dict[str, float] = {}

    # First snap: set baseline mid, no reference yet → no firing
    d = _fire(p, current_mid=12_000.0, memory_counters=counters, memory_values=values)
    assert not d.buy_paused
    # Next snap: -50 move → fire
    d = _fire(
        p,
        snapshot_timestamp=100,
        current_mid=11_950.0,
        memory_counters=counters,
        memory_values=values,
    )
    assert d.buy_paused and "step_move_fire" in d.reasons
    # Next two snaps inside the 3-snap pause (even if mid stable)
    for i in range(2):
        d = _fire(
            p,
            snapshot_timestamp=200 + 100 * i,
            current_mid=11_950.0,
            memory_counters=counters,
            memory_values=values,
        )
        assert d.buy_paused
    # 4th snap post-fire: out of pause
    d = _fire(
        p,
        snapshot_timestamp=500,
        current_mid=11_950.0,
        memory_counters=counters,
        memory_values=values,
    )
    assert not d.buy_paused


@pytest.mark.unit
def test_step_move_kill_ignores_small_moves() -> None:
    p = CoreLongParams(kill_step_move_threshold=40.0, kill_step_move_pause_snaps=3)
    counters: dict[str, int] = {}
    values: dict[str, float] = {}
    _fire(p, current_mid=12_000.0, memory_counters=counters, memory_values=values)
    # -30 is below the 40 threshold magnitude
    d = _fire(
        p, snapshot_timestamp=100, current_mid=11_970.0, memory_counters=counters, memory_values=values
    )
    assert not d.buy_paused


# ---------- signal #4: intraday PnL halt ----------


@pytest.mark.unit
def test_intraday_pnl_halts_buys_only_and_is_sticky() -> None:
    """Intraday-PnL kill is BUY-SIDE ONLY per the batch-D2 design fix.

    Halting both sides would block the natural guard-driven sell-down
    of a losing long position (D2 adverse-tape sweep proved it *hurts*
    PnL on slope-flip and prolonged-down scenarios). The kill must
    pause new BUYS while leaving the strategy free to sell.
    """
    p = CoreLongParams(kill_intraday_pnl_threshold=2_500.0)
    counters: dict[str, int] = {}
    values: dict[str, float] = {}

    # Day open at 12_000, long 80 → price drops to 11_970
    # MTM loss = 80 * (11_970 - 12_000) = -2_400 (just under threshold)
    d = _fire(
        p, current_mid=12_000.0, position=80, memory_counters=counters, memory_values=values
    )
    assert not d.all_paused and not d.buy_paused
    d = _fire(
        p,
        snapshot_timestamp=100,
        current_mid=11_970.0,
        position=80,
        memory_counters=counters,
        memory_values=values,
    )
    assert not d.all_paused and not d.buy_paused

    # -50 off open → MTM = -4_000 ≤ -2_500 → BUY halt (not both sides)
    d = _fire(
        p,
        snapshot_timestamp=200,
        current_mid=11_950.0,
        position=80,
        memory_counters=counters,
        memory_values=values,
    )
    assert not d.all_paused, "intraday PnL kill must NOT halt both sides"
    assert d.buy_paused, "intraday PnL kill must halt buys"
    assert "intraday_pnl_halt" in d.reasons

    # Stickiness: even if price recovers, buy-halt persists for the rest of the day.
    # Sells remain permitted throughout so the guard can drain inventory.
    d = _fire(
        p,
        snapshot_timestamp=300,
        current_mid=12_050.0,
        position=80,
        memory_counters=counters,
        memory_values=values,
    )
    assert not d.all_paused
    assert d.buy_paused


@pytest.mark.unit
def test_intraday_pnl_halt_resets_on_day_rollover() -> None:
    p = CoreLongParams(kill_intraday_pnl_threshold=2_500.0)
    counters: dict[str, int] = {}
    values: dict[str, float] = {}

    # Day 1: trigger halt (buy-side only per batch-D2 design)
    _fire(p, current_mid=12_000.0, position=80, memory_counters=counters, memory_values=values)
    d = _fire(
        p,
        snapshot_timestamp=500,
        current_mid=11_900.0,
        position=80,
        memory_counters=counters,
        memory_values=values,
    )
    assert d.buy_paused
    assert not d.all_paused  # buy-side only per batch-D2 design

    # Day 2: timestamp resets to 0 → rollover detected → halt cleared
    d = _fire(
        p,
        snapshot_timestamp=0,
        current_mid=13_000.0,
        position=80,
        memory_counters=counters,
        memory_values=values,
    )
    assert not d.buy_paused
    assert counters.get("kill_intraday_halt", 0) == 0
    # New day_open_mid should anchor to day 2's first mid
    assert values["kill_day_open_mid"] == 13_000.0


# ---------- cross-cutting: day-rollover resets all day-scoped state ----------


@pytest.mark.unit
def test_day_rollover_resets_all_kill_state() -> None:
    p = CoreLongParams(
        kill_slope_window=50,
        kill_consecutive_neg_slope_n=3,
        kill_slope_pause_snaps=5,
        kill_residual_threshold=35.0,
        kill_residual_release=15.0,
        kill_step_move_threshold=40.0,
        kill_step_move_pause_snaps=3,
        kill_intraday_pnl_threshold=2_500.0,
    )
    counters: dict[str, int] = {}
    values: dict[str, float] = {}

    # Populate state mid-day
    _fire(p, current_mid=12_000.0, slope=-0.01, memory_counters=counters, memory_values=values)
    _fire(
        p,
        snapshot_timestamp=100,
        current_mid=11_950.0,  # -50 step → fire step_move
        slope=-0.01,
        residual=-40.0,  # fire residual
        memory_counters=counters,
        memory_values=values,
    )
    # Many kill keys should be populated now
    assert counters.get("kill_residual_active", 0) == 1
    assert counters.get("kill_step_pause_left", 0) > 0

    # Day rollover
    _fire(
        p,
        snapshot_timestamp=0,
        current_mid=13_000.0,
        memory_counters=counters,
        memory_values=values,
    )
    # All day-scoped counters should be reset
    assert counters.get("kill_consec_neg_slope", 0) == 0
    assert counters.get("kill_slope_pause_left", 0) == 0
    assert counters.get("kill_residual_active", 0) == 0
    assert counters.get("kill_step_pause_left", 0) == 0
    assert counters.get("kill_intraday_halt", 0) == 0
    assert values["kill_day_open_mid"] == 13_000.0
