"""Black-Scholes-Merton option pricing (fixes D7 for options).

Pure Python implementation with inline Abramowitz-Stegun (1964) approximation
for the standard normal CDF — scipy is NOT available in the Prosperity
submission container.

Only call options are implemented (Prosperity vouchers are calls in P3;
extend to puts when/if needed).

All functions are pure. No state, no I/O.

Reference: `engine_options.md` §2 for design decisions. The A&S 7.1.26
approximation is accurate to ~7.5e-8 — more than enough for voucher
pricing where the tick-grid rounds to 1 anyway.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ============================================================= norm CDF


# Abramowitz & Stegun 7.1.26 coefficients.
_A1 = 0.254829592
_A2 = -0.284496736
_A3 = 1.421413741
_A4 = -1.453152027
_A5 = 1.061405429
_P = 0.3275911


def norm_cdf(x: float) -> float:
    """Standard normal CDF, Abramowitz-Stegun 7.1.26 approximation.

    Accurate to ~7.5e-8. Symmetric: uses identity Φ(-x) = 1 - Φ(x).
    """
    sign = 1 if x >= 0 else -1
    abs_x = abs(x) / math.sqrt(2.0)
    t = 1.0 / (1.0 + _P * abs_x)
    y = 1.0 - (((((_A5 * t + _A4) * t) + _A3) * t + _A2) * t + _A1) * t * math.exp(
        -abs_x * abs_x
    )
    return 0.5 * (1.0 + sign * y)


def norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# ============================================================= BSM call


@dataclass(frozen=True)
class BSMInputs:
    """Inputs to the Black-Scholes-Merton formula.

    Time-to-expiry is in YEARS (or whatever unit matches the vol
    annualization). Prosperity vouchers: if expiry is in 'ticks' and
    vol is per-tick, T stays in ticks. If vol is daily, T in days. The
    caller must be consistent.
    """

    spot: float
    """Underlying price S."""

    strike: float
    """Strike price K."""

    time_to_expiry: float
    """T — time until expiration, in units matching volatility."""

    volatility: float
    """σ — standard deviation per unit time (same unit as T)."""

    risk_free_rate: float = 0.0
    """r — assumed 0 in Prosperity (no cash leg accrues interest)."""

    def __post_init__(self) -> None:
        if self.spot <= 0:
            raise ValueError("spot must be > 0")
        if self.strike <= 0:
            raise ValueError("strike must be > 0")
        if self.time_to_expiry <= 0:
            raise ValueError("time_to_expiry must be > 0")
        if self.volatility <= 0:
            raise ValueError("volatility must be > 0")


def _d1_d2(inputs: BSMInputs) -> tuple[float, float]:
    sigma_sqrt_t = inputs.volatility * math.sqrt(inputs.time_to_expiry)
    d1 = (
        math.log(inputs.spot / inputs.strike)
        + (inputs.risk_free_rate + 0.5 * inputs.volatility ** 2) * inputs.time_to_expiry
    ) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    return d1, d2


def call_price(inputs: BSMInputs) -> float:
    """Black-Scholes call price."""
    d1, d2 = _d1_d2(inputs)
    return (
        inputs.spot * norm_cdf(d1)
        - inputs.strike
        * math.exp(-inputs.risk_free_rate * inputs.time_to_expiry)
        * norm_cdf(d2)
    )


# ============================================================= Greeks


@dataclass(frozen=True)
class Greeks:
    """Option Greeks for a call."""

    delta: float  # ∂C/∂S
    gamma: float  # ∂²C/∂S²
    vega: float   # ∂C/∂σ (per 1.00 absolute change in vol, not per %)
    theta: float  # ∂C/∂T (per unit of T)


def call_greeks(inputs: BSMInputs) -> Greeks:
    """Compute delta/gamma/vega/theta for a call.

    Theta is returned per UNIT of time-to-expiry (negative, since
    extrinsic value decays). If T is in days, theta is per-day.
    """
    d1, d2 = _d1_d2(inputs)
    sqrt_t = math.sqrt(inputs.time_to_expiry)
    pdf_d1 = norm_pdf(d1)

    delta = norm_cdf(d1)
    gamma = pdf_d1 / (inputs.spot * inputs.volatility * sqrt_t)
    vega = inputs.spot * pdf_d1 * sqrt_t
    theta = (
        -inputs.spot * pdf_d1 * inputs.volatility / (2.0 * sqrt_t)
        - inputs.risk_free_rate
        * inputs.strike
        * math.exp(-inputs.risk_free_rate * inputs.time_to_expiry)
        * norm_cdf(d2)
    )
    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta)


# ============================================================= IV solver


def implied_vol(
    market_price: float,
    *,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    lo: float = 0.001,
    hi: float = 5.0,
    tol: float = 1e-6,
    max_iter: int = 60,
) -> float | None:
    """Bisection-based IV solver.

    Returns None if no IV in [lo, hi] produces a call price matching
    market_price (e.g., market_price below intrinsic or above cap).
    """
    if market_price <= 0:
        return None
    intrinsic = max(0.0, spot - strike * math.exp(-risk_free_rate * time_to_expiry))
    if market_price < intrinsic - tol:
        return None  # arbitrage or misquote
    if spot <= 0 or strike <= 0 or time_to_expiry <= 0:
        return None

    def f(sigma: float) -> float:
        inputs = BSMInputs(
            spot=spot, strike=strike, time_to_expiry=time_to_expiry,
            volatility=sigma, risk_free_rate=risk_free_rate,
        )
        return call_price(inputs) - market_price

    f_lo = f(lo)
    f_hi = f(hi)

    # Monotonic in sigma; need sign change to bracket root.
    if f_lo * f_hi > 0:
        # Root is outside [lo, hi]. Try widening hi up to 10 once.
        if f_hi < 0 and hi < 10.0:
            wider = 10.0
            f_wider = f(wider)
            if f_wider > 0:
                hi = wider
                f_hi = f_wider
            else:
                return None
        else:
            return None

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = f(mid)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return 0.5 * (lo + hi)
