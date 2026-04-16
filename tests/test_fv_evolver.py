"""Tests for fv_evolver: synthetic FV path generation."""
from __future__ import annotations

import numpy as np
import pytest

from src.analysis.calibration.fv_evolver import FVProcess, spawn_fv_path
from src.analysis.calibration.types import FairValueFit


def _make_process(
    *,
    sigma: float = 0.5,
    drift: float = 0.0,
    start_value: float = 5000.0,
    quantization_grid: float | None = None,
) -> FVProcess:
    return FVProcess(
        sigma=sigma,
        drift=drift,
        start_value=start_value,
        quantization_grid=quantization_grid,
    )


def test_spawn_length_matches_n_ticks():
    path = spawn_fv_path(
        _make_process(), n_ticks=1000, rng=np.random.default_rng(42),
    )
    assert path.shape == (1000,)


def test_spawn_deterministic_given_seed():
    p = _make_process()
    a = spawn_fv_path(p, n_ticks=500, rng=np.random.default_rng(7))
    b = spawn_fv_path(p, n_ticks=500, rng=np.random.default_rng(7))
    np.testing.assert_array_equal(a, b)


def test_first_tick_equals_start_value():
    p = _make_process(start_value=9999.5)
    path = spawn_fv_path(p, n_ticks=100, rng=np.random.default_rng(0))
    assert path[0] == 9999.5


def test_increment_sigma_recovered_within_tolerance():
    # N=100000 → SE on sigma ≈ sigma/sqrt(2N) ≈ 0.001 at sigma=0.5
    p = _make_process(sigma=0.5, drift=0.0)
    path = spawn_fv_path(p, n_ticks=100_000, rng=np.random.default_rng(1))
    returns = np.diff(path)
    assert abs(returns.std(ddof=1) - 0.5) < 0.01, (
        f"sigma off: got {returns.std(ddof=1):.4f}, expected 0.5"
    )


def test_drift_recovered_within_tolerance():
    # N=100000, drift=0.1, sigma=0.5 → SE on mean ≈ 0.5/sqrt(100000) ≈ 0.0016
    p = _make_process(sigma=0.5, drift=0.1)
    path = spawn_fv_path(p, n_ticks=100_000, rng=np.random.default_rng(2))
    returns = np.diff(path)
    assert abs(returns.mean() - 0.1) < 0.005, (
        f"drift off: got {returns.mean():.4f}, expected 0.1"
    )


def test_quantization_snaps_to_grid():
    p = _make_process(sigma=0.5, quantization_grid=0.25)
    path = spawn_fv_path(p, n_ticks=1000, rng=np.random.default_rng(3))
    residuals = np.mod(path / 0.25, 1.0)
    # After rounding to 0.25 grid, path/0.25 should be integer (mod 1 = 0)
    # Allow tiny float-precision noise.
    assert np.all(np.abs(residuals - np.round(residuals)) < 1e-9)


def test_quantization_none_leaves_continuous():
    p = _make_process(sigma=0.5, quantization_grid=None)
    path = spawn_fv_path(p, n_ticks=1000, rng=np.random.default_rng(4))
    # At least one value should not lie on any obvious grid.
    residuals = np.mod(path, 1.0)
    assert not np.all(residuals < 1e-9)


def test_from_fit_pulls_params_from_fairvaluefit():
    fit = FairValueFit(
        sigma=0.4074,
        mean_return=-0.0083,
        n_returns=999,
        ar1_phi=0.024,
        ar1_phi_se=0.032,
        vr_horizons=(2, 5),
        variance_ratio=(1.0, 1.0),
        quantization_grid=0.000977,
        fv_min=9993.76,
        fv_max=10011.00,
    )
    process = FVProcess.from_fit(fit)
    assert process.sigma == 0.4074
    assert process.drift == -0.0083
    assert process.quantization_grid == 0.000977
    # Default start_value is midpoint of fv_min and fv_max.
    assert process.start_value == pytest.approx(0.5 * (9993.76 + 10011.00))


def test_from_fit_respects_explicit_start_value():
    fit = FairValueFit(
        sigma=1.0, mean_return=0.0, n_returns=100,
        ar1_phi=0.0, ar1_phi_se=0.1,
        vr_horizons=(2,), variance_ratio=(1.0,),
        quantization_grid=None, fv_min=0.0, fv_max=10.0,
    )
    p = FVProcess.from_fit(fit, start_value=42.0)
    assert p.start_value == 42.0


def test_raises_on_zero_n_ticks():
    with pytest.raises(ValueError):
        spawn_fv_path(
            _make_process(), n_ticks=0, rng=np.random.default_rng(0),
        )


def test_n_ticks_one_returns_single_element():
    path = spawn_fv_path(
        _make_process(start_value=5.0), n_ticks=1,
        rng=np.random.default_rng(0),
    )
    assert path.shape == (1,)
    assert path[0] == 5.0
