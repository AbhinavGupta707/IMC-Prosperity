"""Unit tests for the statistically-significant sweep selector."""

from __future__ import annotations

import pytest

from src.core.primitives.sweep_selector import (
    SweepConfig,
    bootstrap_ci,
    select_winner,
)


@pytest.mark.unit
def test_bootstrap_ci_reasonable_bounds():
    values = [100.0, 110.0, 90.0, 105.0, 95.0]
    ci = bootstrap_ci(values, n_bootstrap=500, confidence=0.95, seed=1)
    assert ci.mean == pytest.approx(100.0, abs=0.1)
    assert ci.lower < ci.mean < ci.upper
    assert ci.n_samples == 5


@pytest.mark.unit
def test_bootstrap_ci_single_sample():
    ci = bootstrap_ci([42.0])
    assert ci.mean == ci.lower == ci.upper == 42.0
    assert ci.n_samples == 1


@pytest.mark.unit
def test_bootstrap_ci_empty():
    ci = bootstrap_ci([])
    assert ci.n_samples == 0


@pytest.mark.unit
def test_selector_rejects_when_no_significant_winner():
    """If all candidates overlap baseline's CI upper, winner is None."""
    baseline = SweepConfig(
        label="baseline",
        params={},
        per_day_pnl=[100, 105, 95, 110, 90],
    )
    close_candidate = SweepConfig(
        label="close",
        params={},
        per_day_pnl=[102, 108, 98, 112, 92],  # overlaps baseline
    )
    result = select_winner(
        [baseline, close_candidate],
        baseline_label="baseline",
        n_bootstrap=500,
    )
    assert result.winner is None
    assert "No candidate exceeds" in result.rationale


@pytest.mark.unit
def test_selector_picks_clear_winner():
    """Candidate with CI-lower clearly above baseline's CI-upper wins."""
    baseline = SweepConfig(
        label="baseline", params={}, per_day_pnl=[100, 105, 95, 110, 90],
    )
    clear_winner = SweepConfig(
        label="winner", params={}, per_day_pnl=[200, 210, 195, 205, 200],
    )
    result = select_winner(
        [baseline, clear_winner],
        baseline_label="baseline",
        n_bootstrap=500,
    )
    assert result.winner is not None
    assert result.winner.label == "winner"


@pytest.mark.unit
def test_selector_warns_on_insufficient_samples():
    """Configs with fewer than min_samples per-day P&L get a warning."""
    baseline = SweepConfig(label="baseline", params={}, per_day_pnl=[100, 105])
    cand = SweepConfig(label="cand", params={}, per_day_pnl=[200, 210])
    result = select_winner(
        [baseline, cand],
        baseline_label="baseline",
        min_samples=5,
        n_bootstrap=200,
    )
    assert "WARNING" in result.rationale
    assert "per-day samples" in result.rationale


@pytest.mark.unit
def test_selector_baseline_missing_raises():
    c = SweepConfig(label="c", params={}, per_day_pnl=[1, 2, 3])
    with pytest.raises(ValueError, match="baseline_label"):
        select_winner([c], baseline_label="absent")


@pytest.mark.unit
def test_selector_tie_breaker_picks_narrow_ci():
    """Among candidates tied within 1%, pick the narrowest CI."""
    baseline = SweepConfig(label="baseline", params={}, per_day_pnl=[100] * 10)
    # Both candidates have same mean but different spreads.
    tight = SweepConfig(
        label="tight",
        params={},
        per_day_pnl=[199, 200, 201, 200, 199, 200, 201, 200, 199, 201],
    )
    wide = SweepConfig(
        label="wide",
        params={},
        per_day_pnl=[150, 250, 150, 250, 150, 250, 150, 250, 150, 250],
    )
    result = select_winner(
        [baseline, tight, wide],
        baseline_label="baseline",
        n_bootstrap=500,
    )
    assert result.winner is not None
    assert result.winner.label == "tight"


@pytest.mark.unit
def test_all_candidates_equal_baseline_rejects_all():
    baseline = SweepConfig(label="baseline", params={}, per_day_pnl=[100] * 8)
    identical = SweepConfig(label="identical", params={}, per_day_pnl=[100] * 8)
    result = select_winner(
        [baseline, identical],
        baseline_label="baseline",
        n_bootstrap=500,
    )
    assert result.winner is None


@pytest.mark.unit
def test_v5_vs_promoted_noise_rejected():
    """Regression test: the R2 v5 vs Promoted case (both ~7,900, 4 samples each,
    +75 mean delta) must NOT produce a significant winner. This is the exact
    case our old plateau-chart selector got wrong and F1 forensically exposed.
    """
    promoted = SweepConfig(
        label="Promoted", params={}, per_day_pnl=[8013, 7385, 7923, 7295],
    )
    v5 = SweepConfig(label="v5", params={}, per_day_pnl=[7399, 8281, 7851, 8356])
    result = select_winner(
        [promoted, v5],
        baseline_label="Promoted",
        min_samples=4,
        n_bootstrap=2000,
    )
    assert result.winner is None, (
        f"v5 vs Promoted is statistical noise and must not produce a winner; "
        f"got {result.winner.label if result.winner else None}"
    )
