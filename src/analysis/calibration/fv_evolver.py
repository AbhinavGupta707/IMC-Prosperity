"""Generate synthetic fair-value paths from a fitted FV process.

Model: discrete-time Gaussian random walk with optional drift and
optional quantization to a fixed grid.

    FV(t+1) = FV(t) + drift + sigma * Z_t,   Z_t ~ N(0, 1) i.i.d.
    FV(t)   = round(FV(t) / grid) * grid      if grid is set

Per-product paths are spawned independently. A cross-product correlation
of +0.64 was measured on round-1 ASH/PEPPER increment series, but the
rolling-window median correlation is +0.03 (near zero) and the +0.64 is
driven by a handful of synchronous common-shock windows (~5% of the day).
Since our present audit workflow evaluates a strategy on one product at
a time (F3a on ASH, buy_hold_80 on PEPPER) and F3a's FV estimator does
not reference PEPPER, modeling this as a common factor would add model
risk without changing the verdict. Gate 2 in simulator_validation will
flag this if the independence assumption fails a marginal match; bivariate
FV via empirical covariance is a v2 extension.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.analysis.calibration.types import FairValueFit


@dataclass(frozen=True)
class FVProcess:
    """Per-product FV process parameters for the generative simulator.

    Build one per product via ``FVProcess.from_fit()``.
    """

    sigma: float
    drift: float
    start_value: float
    quantization_grid: float | None  # None == continuous FV

    @classmethod
    def from_fit(
        cls, fit: FairValueFit, *, start_value: float | None = None
    ) -> FVProcess:
        """Construct an FVProcess from a calibrated FairValueFit.

        ``start_value`` defaults to the midpoint of the fit's observed
        FV range. Callers can override (e.g., to seed a Monte Carlo
        session at a specific starting level).
        """
        if start_value is None:
            start_value = 0.5 * (fit.fv_min + fit.fv_max)
        return cls(
            sigma=fit.sigma,
            drift=fit.mean_return,
            start_value=start_value,
            quantization_grid=fit.quantization_grid,
        )


def spawn_fv_path(
    process: FVProcess,
    *,
    n_ticks: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Spawn a single FV path of length ``n_ticks``.

    Sample (n_ticks - 1) Gaussian innovations with mean = drift and
    std = sigma, cumulatively sum from ``start_value``, then quantize
    to the grid if set. The first tick always equals ``start_value``
    (no randomness at t=0).

    Deterministic given the ``rng`` state.
    """
    if n_ticks < 1:
        raise ValueError(f"n_ticks must be >= 1, got {n_ticks}")
    path = np.empty(n_ticks, dtype=float)
    path[0] = process.start_value
    if n_ticks == 1:
        return _quantize(path, process.quantization_grid)
    innovations = rng.normal(
        loc=process.drift,
        scale=process.sigma,
        size=n_ticks - 1,
    )
    # cumulative sum of innovations added to start
    path[1:] = process.start_value + np.cumsum(innovations)
    return _quantize(path, process.quantization_grid)


def _quantize(path: np.ndarray, grid: float | None) -> np.ndarray:
    if grid is None or grid <= 0:
        return path
    return np.round(path / grid) * grid
