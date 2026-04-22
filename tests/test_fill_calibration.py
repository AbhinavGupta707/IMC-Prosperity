"""Unit tests for the fill-model calibration harness."""

from __future__ import annotations

import pytest

from src.core.primitives.fill_calibration import (
    CalibrationPoint,
    consensus_fill_rate,
    sweep_fill_rate,
)


@pytest.mark.unit
def test_sweep_records_all_fill_rates():
    point = CalibrationPoint(
        label="ref", truth_pnl=7500, truth_n_samples=4,
        truth_stdev=300, scale_to_truth=30.0,
    )

    def sim(cfg):
        # Simulated P&L is linear in fill_rate (unrealistic but deterministic).
        return cfg.passive_allocation * 100_000

    sweep = sweep_fill_rate(
        point=point,
        run_simulation_fn=sim,
        fill_rates=[0.1, 0.2, 0.3],
    )
    assert len(sweep.results) == 3
    assert [r.fill_rate for r in sweep.results] == [0.1, 0.2, 0.3]


@pytest.mark.unit
def test_best_fill_rate_picked():
    """Sim returns passive_allocation * 225,000. Truth 7,500, scale 30.
    So scaled = passive_allocation * 7,500. Best match: fill_rate = 1.0.
    Within [0.05..0.5], closest is 0.5.
    """
    point = CalibrationPoint(
        label="ref", truth_pnl=7500, truth_n_samples=4,
        truth_stdev=300, scale_to_truth=30.0,
    )

    def sim(cfg):
        return cfg.passive_allocation * 225_000

    sweep = sweep_fill_rate(
        point=point,
        run_simulation_fn=sim,
        fill_rates=[0.1, 0.2, 0.3, 0.4, 0.5],
    )
    assert sweep.best_fill_rate() == 0.5


@pytest.mark.unit
def test_within_tolerance_filter():
    point = CalibrationPoint(
        label="ref", truth_pnl=100, truth_n_samples=1,
        truth_stdev=5, scale_to_truth=1.0,
    )

    def sim(cfg):
        return {0.1: 80, 0.2: 95, 0.3: 101, 0.4: 110, 0.5: 200}[cfg.passive_allocation]

    sweep = sweep_fill_rate(
        point=point,
        run_simulation_fn=sim,
        fill_rates=[0.1, 0.2, 0.3, 0.4, 0.5],
    )
    within = sweep.within_tolerance(tolerance_pct=5.0)
    # fill_rate=0.2 (sim=95, err=5%) and 0.3 (sim=101, err=1%) both within ±5%.
    assert [r.fill_rate for r in within] == [0.2, 0.3]


@pytest.mark.unit
def test_consensus_across_multiple_points():
    """If two points both best-match at fill_rate=0.2, consensus is 0.2."""
    p1 = CalibrationPoint("p1", 100, 4, 5, 1.0)
    p2 = CalibrationPoint("p2", 200, 4, 10, 1.0)

    def sim1(cfg):
        # Best at 0.2.
        return {0.1: 50, 0.2: 100, 0.3: 150}[cfg.passive_allocation]

    def sim2(cfg):
        # Best at 0.2.
        return {0.1: 100, 0.2: 200, 0.3: 300}[cfg.passive_allocation]

    s1 = sweep_fill_rate(point=p1, run_simulation_fn=sim1, fill_rates=[0.1, 0.2, 0.3])
    s2 = sweep_fill_rate(point=p2, run_simulation_fn=sim2, fill_rates=[0.1, 0.2, 0.3])
    assert consensus_fill_rate([s1, s2]) == 0.2


@pytest.mark.unit
def test_consensus_returns_none_on_empty():
    assert consensus_fill_rate([]) is None
