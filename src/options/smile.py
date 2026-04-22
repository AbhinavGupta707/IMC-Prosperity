"""IV smile fitter with graceful degradation (fixes D2 for options).

F1 forensic showed chrispyroberts' quadratic smile BROKE on submission
day — a single quadratic overfits in-sample and fails OOS. His team
switched to rolling mid-IV mid-round and doubled P&L (80k → 200k/day).

Our fitter implements BOTH in a degradation chain:

- **Warmup mode** (obs per strike < 50): fit quadratic in moneyness.
  Returns a fitted IV per strike.
- **Rolling mode** (obs per strike ≥ 50): use the rolling-mean mid-IV
  per strike with an EWMA halflife. More robust to regime changes.

The degradation is AUTOMATIC — the caller always asks for `fair_iv(strike)`
and the fitter picks the right mode internally. No config flag needed
to switch between modes.

Moneyness is computed as `m = log(K/S) / sqrt(T)` per Gatheral-Jacquier.

Pure Python; no numpy or scipy. The polynomial fit uses normal
equations on 3x3 matrices.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SmileConfig:
    """Smile fitter configuration."""

    warmup_threshold: int = 50
    """Minimum observations per strike before switching off quadratic warmup."""

    rolling_window: int = 200
    """Lookback for the rolling-mid-IV mode."""

    ewma_halflife: float = 100.0
    """EWMA halflife for the rolling mode (ticks)."""

    max_sensible_iv: float = 2.0
    """Reject IV observations above this (likely solver failures)."""

    min_sensible_iv: float = 0.01
    """Reject IV observations below this."""

    def __post_init__(self) -> None:
        if self.warmup_threshold <= 0:
            raise ValueError("warmup_threshold must be > 0")
        if self.rolling_window <= 0:
            raise ValueError("rolling_window must be > 0")
        if self.ewma_halflife <= 0:
            raise ValueError("ewma_halflife must be > 0")


def moneyness(strike: float, spot: float, time_to_expiry: float) -> float:
    """Gatheral-Jacquier moneyness: m = log(K/S) / sqrt(T)."""
    if spot <= 0 or time_to_expiry <= 0:
        raise ValueError("spot and time_to_expiry must be > 0")
    return math.log(strike / spot) / math.sqrt(time_to_expiry)


# =============================================================== fitter


@dataclass
class SmileFitter:
    """Accumulates IV observations per strike and fits a smile.

    Holds one deque per strike and an EWMA state. Query ``fair_iv``
    with a strike (and current spot+T for moneyness) to get the
    fitted IV.

    State is mutable but self-contained; serialized via ``snapshot``
    for traderData persistence.
    """

    config: SmileConfig = field(default_factory=SmileConfig)
    # strike -> deque of recent IV observations
    _per_strike_iv: dict[float, deque[float]] = field(default_factory=dict)
    # strike -> EWMA rolling IV
    _ewma_iv: dict[float, float] = field(default_factory=dict)
    # total observations across all strikes (to decide warmup vs rolling)
    _total_obs: int = 0

    def observe(self, strike: float, iv: float) -> None:
        """Feed one IV observation for a strike. Ignores outliers."""
        cfg = self.config
        if iv < cfg.min_sensible_iv or iv > cfg.max_sensible_iv:
            return
        if strike not in self._per_strike_iv:
            self._per_strike_iv[strike] = deque(maxlen=cfg.rolling_window)
        self._per_strike_iv[strike].append(iv)
        # EWMA update.
        alpha = 1.0 - math.exp(math.log(0.5) / cfg.ewma_halflife)
        prev = self._ewma_iv.get(strike)
        self._ewma_iv[strike] = iv if prev is None else alpha * iv + (1 - alpha) * prev
        self._total_obs += 1

    def _in_warmup(self, strike: float) -> bool:
        return (
            strike not in self._per_strike_iv
            or len(self._per_strike_iv[strike]) < self.config.warmup_threshold
        )

    def fair_iv(
        self,
        *,
        strike: float,
        spot: float,
        time_to_expiry: float,
    ) -> float | None:
        """Return the fitted fair IV for this strike, given current S/T.

        Picks rolling mode if observations permit, else warmup mode
        (quadratic fit across strikes if ≥ 3 strikes, else return
        latest obs for this strike).
        """
        if self._in_warmup(strike):
            return self._warmup_iv(strike=strike, spot=spot, time_to_expiry=time_to_expiry)
        return self._ewma_iv.get(strike)

    def _warmup_iv(
        self,
        *,
        strike: float,
        spot: float,
        time_to_expiry: float,
    ) -> float | None:
        """Quadratic fit across strikes on moneyness. Needs ≥ 3 strikes."""
        # Gather (moneyness, mean_iv) pairs across strikes.
        points: list[tuple[float, float]] = []
        for k, samples in self._per_strike_iv.items():
            if not samples:
                continue
            m = moneyness(strike=k, spot=spot, time_to_expiry=time_to_expiry)
            avg_iv = sum(samples) / len(samples)
            points.append((m, avg_iv))
        if not points:
            return None
        if len(points) < 3:
            # Can't fit a quadratic — return last obs for this strike.
            if strike in self._per_strike_iv and self._per_strike_iv[strike]:
                return self._per_strike_iv[strike][-1]
            return None
        # Fit v = a*m^2 + b*m + c via normal equations.
        coeffs = _fit_quadratic(points)
        if coeffs is None:
            return None
        a, b, c = coeffs
        m_query = moneyness(strike=strike, spot=spot, time_to_expiry=time_to_expiry)
        return a * m_query * m_query + b * m_query + c

    def snapshot(self) -> dict:
        """Serializable snapshot for traderData persistence."""
        return {
            "per_strike_iv": {
                str(k): list(v) for k, v in self._per_strike_iv.items()
            },
            "ewma_iv": {str(k): v for k, v in self._ewma_iv.items()},
            "total_obs": self._total_obs,
        }

    @classmethod
    def restore(cls, payload: dict, config: SmileConfig | None = None) -> SmileFitter:
        cfg = config or SmileConfig()
        fitter = cls(config=cfg)
        raw = payload.get("per_strike_iv", {})
        if isinstance(raw, dict):
            for k, v in raw.items():
                try:
                    strike = float(k)
                    fitter._per_strike_iv[strike] = deque(
                        [float(x) for x in v], maxlen=cfg.rolling_window,
                    )
                except (ValueError, TypeError):
                    continue
        raw_ewma = payload.get("ewma_iv", {})
        if isinstance(raw_ewma, dict):
            for k, v in raw_ewma.items():
                try:
                    fitter._ewma_iv[float(k)] = float(v)
                except (ValueError, TypeError):
                    continue
        fitter._total_obs = int(payload.get("total_obs", 0))
        return fitter


def _fit_quadratic(points: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    """Least-squares quadratic fit v = a*x^2 + b*x + c via normal equations."""
    n = len(points)
    if n < 3:
        return None
    # Normal equations for y = a*x^2 + b*x + c:
    # [Σx^4  Σx^3  Σx^2] [a]   [Σx^2*y]
    # [Σx^3  Σx^2  Σx  ] [b] = [Σx*y  ]
    # [Σx^2  Σx    n   ] [c]   [Σy    ]
    sx = sx2 = sx3 = sx4 = sy = sxy = sx2y = 0.0
    for x, y in points:
        x2 = x * x
        sx += x; sx2 += x2; sx3 += x2 * x; sx4 += x2 * x2
        sy += y; sxy += x * y; sx2y += x2 * y
    matrix = [
        [sx4, sx3, sx2],
        [sx3, sx2, sx],
        [sx2, sx, float(n)],
    ]
    rhs = [sx2y, sxy, sy]
    return _solve_3x3(matrix, rhs)


def _solve_3x3(
    matrix: list[list[float]], rhs: list[float]
) -> tuple[float, float, float] | None:
    """Gaussian elimination for a 3x3 linear system. Returns None if singular."""
    m = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for i in range(3):
        pivot = m[i][i]
        # Partial pivoting.
        max_row = max(range(i, 3), key=lambda r: abs(m[r][i]))
        if max_row != i:
            m[i], m[max_row] = m[max_row], m[i]
            pivot = m[i][i]
        if abs(pivot) < 1e-12:
            return None
        for j in range(i + 1, 3):
            factor = m[j][i] / pivot
            for k in range(i, 4):
                m[j][k] -= factor * m[i][k]
    # Back-substitute.
    x = [0.0, 0.0, 0.0]
    for i in range(2, -1, -1):
        s = m[i][3]
        for j in range(i + 1, 3):
            s -= m[i][j] * x[j]
        x[i] = s / m[i][i]
    return (x[0], x[1], x[2])
