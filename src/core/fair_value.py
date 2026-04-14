"""Fair value estimators and the engine that resolves them.

Doctrine:

- Every trading decision must flow through a fair-value abstraction.
- Estimators are pluggable objects implementing the ``Estimator``
  protocol. New estimators register into ``ESTIMATORS``.
- Per-product resolution uses a primary estimator plus an ordered
  fallback chain (``ProductConfig.fair_value_fallbacks``). The first
  estimator in the chain that returns a non-``None`` result wins.
- ``estimate_all`` runs every registered estimator on the same snapshot
  so Phase 3 experiments can compare proxies side-by-side without
  rewriting production code.

Each estimator is stateless with respect to the request: it reads the
frozen snapshot and the product's rolling memory, and returns a
``FairValueEstimate`` or ``None`` to indicate that it cannot score this
step.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Protocol

from src.core.config import ProductConfig
from src.core.types import FairValueEstimate, NormalizedSnapshot, ProductMemory, Scalar
from src.core.utils import weighted_average

_DEFAULT_EWMA_ALPHA = 0.3


class Estimator(Protocol):
    name: str

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None: ...


class AnchorEstimator:
    name = "anchor"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        if config.anchor_price is None:
            return None
        return FairValueEstimate(
            price=float(config.anchor_price),
            method=self.name,
            confidence=1.0,
            components=MappingProxyType({"anchor_price": float(config.anchor_price)}),
        )


class MidEstimator:
    name = "mid"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        if snapshot.mid is None:
            return None
        return FairValueEstimate(price=float(snapshot.mid), method=self.name, confidence=0.7)


class MicropriceEstimator:
    name = "microprice"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        if snapshot.microprice is None:
            return None
        components: Mapping[str, Scalar] = MappingProxyType(
            {"imbalance": float(snapshot.book_imbalance or 0.0)}
        )
        return FairValueEstimate(
            price=float(snapshot.microprice),
            method=self.name,
            confidence=0.8,
            components=components,
        )


class RollingMidEstimator:
    name = "rolling_mid"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        history = list(memory.recent_mids)
        if snapshot.mid is not None:
            history.append(float(snapshot.mid))
        if not history:
            return None
        return FairValueEstimate(
            price=sum(history) / len(history),
            method=self.name,
            confidence=0.65,
        )


class WeightedMidEstimator:
    """Linearly-weighted average of recent mids.

    Uses ``config.history_length`` as the lookback window so that
    parameter sweeps of ``history_length`` are meaningful.  Previously
    this was hardcoded at 4 (``LOOKBACK``), which made sweeps of
    ``history_length`` a no-op for any value >= 4.
    """

    name = "weighted_mid"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        lookback = config.history_length if config.history_length > 0 else 0
        history = memory.recent_mids[-lookback:] if lookback > 0 else []
        if snapshot.mid is None:
            # Fall back to pure history if the book is one-sided.
            if not history:
                return None
            weights = list(range(1, len(history) + 1))
            return FairValueEstimate(
                price=weighted_average(history, weights),
                method=self.name,
                confidence=0.55,
            )
        values = [*history, float(snapshot.mid)]
        weights = list(range(1, len(values) + 1))
        return FairValueEstimate(
            price=weighted_average(values, weights),
            method=self.name,
            confidence=0.7,
        )


class EwmaMidEstimator:
    """Exponentially weighted moving average of recent mids.

    Applies the recurrence ``ewma = alpha * m + (1 - alpha) * ewma`` over
    ``memory.recent_mids`` oldest-to-newest, seeding with the first
    available sample, and finally blends in ``snapshot.mid`` if the
    current book has one. Reads alpha from ``ProductConfig.ewma_alpha``
    and falls back to ``_DEFAULT_EWMA_ALPHA`` when unset.

    Cold-start behaviour:
    - empty history AND no current mid -> return ``None`` (let the
      fallback chain handle it).
    - empty history, current mid present -> return the current mid and
      mark ``components["bootstrap"] = 1.0`` so the review pack can see
      that the estimate was a cold-start.
    - one-sample history, no current mid -> return that sample,
      bootstrap flagged.
    - ``alpha == 1.0`` -> collapses to the current mid (verified in
      tests).
    """

    name = "ewma_mid"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        alpha = config.ewma_alpha if config.ewma_alpha is not None else _DEFAULT_EWMA_ALPHA
        history = memory.recent_mids
        current = snapshot.mid

        if not history and current is None:
            return None

        bootstrap = False
        if not history:
            # Cold start: no prior samples, use the current mid as seed.
            ewma = float(current)  # type: ignore[arg-type]
            bootstrap = True
        else:
            ewma = float(history[0])
            for prior_mid in history[1:]:
                ewma = alpha * float(prior_mid) + (1.0 - alpha) * ewma
            if current is None:
                # No current mid to blend in: still valid, but mark it.
                bootstrap = len(history) == 1
            else:
                ewma = alpha * float(current) + (1.0 - alpha) * ewma

        components: dict[str, Scalar] = {"alpha": float(alpha)}
        if bootstrap:
            components["bootstrap"] = 1.0
        return FairValueEstimate(
            price=ewma,
            method=self.name,
            confidence=0.72,
            components=MappingProxyType(components),
        )


class LinearDriftEstimator:
    """Online linear-drift estimator: fair = slope * index + intercept.

    Fits a simple ordinary-least-squares line over the most recent
    ``config.history_length`` mids held in ``memory.recent_mids`` (or
    all of them if ``history_length`` is 0) and projects one step
    ahead to forecast the next mid. Assumes the observations are
    evenly spaced in time (true for IMC Prosperity replay data, which
    ticks at a constant 100-timestamp cadence).

    Designed for Round 1 INTARIAN_PEPPER_ROOT, which exhibits an
    almost-deterministic +0.1 per timestamp-step drift. The estimator
    does NOT hardcode the slope; it is recovered from recent data so
    the estimator remains useful if the slope drifts.

    Cold-start behaviour:
    - 0 prior mids and no current mid -> return ``None``.
    - 0 prior mids, current mid present -> return the current mid
      marked as ``bootstrap``.
    - 1 prior mid: fall back to the most recent mid.
    - 2+ prior mids: OLS fit with index as the independent variable;
      project one index step ahead to get the next-step forecast.
    """

    name = "linear_drift"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        lookback = config.history_length if config.history_length > 0 else None
        history = list(memory.recent_mids)
        if lookback is not None:
            history = history[-lookback:]
        current = snapshot.mid

        if not history and current is None:
            return None

        # Cold-start
        if not history:
            return FairValueEstimate(
                price=float(current),  # type: ignore[arg-type]
                method=self.name,
                confidence=0.3,
                components=MappingProxyType({"bootstrap": 1.0}),
            )

        # Build (index, mid) sample set. Use history, then append the
        # current mid if we have one.
        ys: list[float] = [float(y) for y in history]
        if current is not None:
            ys.append(float(current))

        n = len(ys)
        if n < 2:
            # Not enough points for a slope: return most recent observation.
            return FairValueEstimate(
                price=ys[-1],
                method=self.name,
                confidence=0.4,
                components=MappingProxyType({"bootstrap": 1.0, "samples": float(n)}),
            )

        xs = list(range(n))
        mean_x = (n - 1) / 2.0
        mean_y = sum(ys) / n
        var_x = sum((x - mean_x) ** 2 for x in xs)
        if var_x <= 0:
            return FairValueEstimate(
                price=ys[-1],
                method=self.name,
                confidence=0.4,
                components=MappingProxyType({"samples": float(n)}),
            )
        cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
        slope = cov_xy / var_x
        intercept = mean_y - slope * mean_x
        # Project one index step ahead (= the next observation).
        forecast = slope * n + intercept

        components: dict[str, Scalar] = {
            "slope": float(slope),
            "intercept": float(intercept),
            "samples": float(n),
        }
        return FairValueEstimate(
            price=forecast,
            method=self.name,
            confidence=0.7,
            components=MappingProxyType(components),
        )


class DepthMidEstimator:
    name = "depth_mid"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        del memory, config
        if not snapshot.bids or not snapshot.asks:
            return None

        bid_volume = sum(level.volume for level in snapshot.bids)
        ask_volume = sum(level.volume for level in snapshot.asks)
        if bid_volume <= 0 or ask_volume <= 0:
            return None

        bid_vwap = sum(level.price * level.volume for level in snapshot.bids) / bid_volume
        ask_vwap = sum(level.price * level.volume for level in snapshot.asks) / ask_volume

        return FairValueEstimate(
            price=(bid_vwap + ask_vwap) / 2.0,
            method=self.name,
            confidence=0.75,
            components=MappingProxyType(
                {
                    "bid_vwap": bid_vwap,
                    "ask_vwap": ask_vwap,
                }
            ),
        )


class WallMidEstimator:
    """Fair value as midpoint of the largest bid and ask levels."""

    name = "wall_mid"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        del memory, config
        if not snapshot.bids or not snapshot.asks:
            return None

        wall_bid = max(snapshot.bids, key=lambda l: l.volume)
        wall_ask = max(snapshot.asks, key=lambda l: l.volume)

        return FairValueEstimate(
            price=(wall_bid.price + wall_ask.price) / 2.0,
            method=self.name,
            confidence=0.75,
            components=MappingProxyType(
                {
                    "wall_bid_price": wall_bid.price,
                    "wall_ask_price": wall_ask.price,
                    "wall_bid_vol": wall_bid.volume,
                    "wall_ask_vol": wall_ask.volume,
                }
            ),
        )


class FilteredWallMidEstimator:
    """Wall mid after filtering out small levels.

    Considers only the top N visible levels per side. Filters out levels
    with volume < 25% of the side's max volume. Among survivors, picks
    the largest volume; ties broken by closeness to touch.
    """

    name = "filtered_wall_mid"
    _TOP_N = 3
    _MIN_VOLUME_RATIO = 0.25

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        del memory, config
        if not snapshot.bids or not snapshot.asks:
            return None

        top_bids = snapshot.bids[: self._TOP_N]
        top_asks = snapshot.asks[: self._TOP_N]

        wall_bid, bid_filtered = self._pick_wall(top_bids)
        wall_ask, ask_filtered = self._pick_wall(top_asks)

        if wall_bid is None or wall_ask is None:
            return None

        return FairValueEstimate(
            price=(wall_bid.price + wall_ask.price) / 2.0,
            method=self.name,
            confidence=0.75,
            components=MappingProxyType(
                {
                    "wall_bid_price": wall_bid.price,
                    "wall_ask_price": wall_ask.price,
                    "filtered_out_count": bid_filtered + ask_filtered,
                }
            ),
        )

    @staticmethod
    def _pick_wall(levels: tuple[BookLevel, ...]) -> tuple[BookLevel | None, int]:
        """Select the wall level after filtering.

        Returns (selected_level, count_filtered_out).
        """
        if not levels:
            return None, 0
        max_vol = max(l.volume for l in levels)
        threshold = max_vol * FilteredWallMidEstimator._MIN_VOLUME_RATIO
        indexed = [(i, l) for i, l in enumerate(levels) if l.volume >= threshold]
        filtered_count = len(levels) - len(indexed)
        if not indexed:
            return None, filtered_count
        # Largest volume first, then closest to touch (smallest index)
        indexed.sort(key=lambda x: (-x[1].volume, x[0]))
        return indexed[0][1], filtered_count


class HybridWallMicroEstimator:
    """Blends wall_mid and microprice estimates."""

    name = "hybrid_wall_micro"
    wall_weight: float = 0.5

    def __init__(self) -> None:
        self._wall = WallMidEstimator()
        self._micro = MicropriceEstimator()

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        wall_est = self._wall.estimate(snapshot, memory, config)
        micro_est = self._micro.estimate(snapshot, memory, config)

        if wall_est is not None and micro_est is not None:
            price = self.wall_weight * wall_est.price + (1 - self.wall_weight) * micro_est.price
            return FairValueEstimate(
                price=price,
                method=self.name,
                confidence=0.75,
                components=MappingProxyType(
                    {
                        "wall_mid_price": wall_est.price,
                        "microprice": micro_est.price,
                        "wall_weight": self.wall_weight,
                    }
                ),
            )

        if wall_est is not None:
            return FairValueEstimate(
                price=wall_est.price,
                method=self.name,
                confidence=0.75,
                components=MappingProxyType(
                    {"wall_mid_price": wall_est.price, "wall_weight": 1.0}
                ),
            )

        if micro_est is not None:
            return FairValueEstimate(
                price=micro_est.price,
                method=self.name,
                confidence=0.75,
                components=MappingProxyType(
                    {"microprice": micro_est.price, "wall_weight": 0.0}
                ),
            )

        return None


ESTIMATORS: Mapping[str, Estimator] = MappingProxyType(
    {
        "anchor": AnchorEstimator(),
        "mid": MidEstimator(),
        "microprice": MicropriceEstimator(),
        "rolling_mid": RollingMidEstimator(),
        "weighted_mid": WeightedMidEstimator(),
        "ewma_mid": EwmaMidEstimator(),
        "linear_drift": LinearDriftEstimator(),
        "depth_mid": DepthMidEstimator(),
        "wall_mid": WallMidEstimator(),
        "filtered_wall_mid": FilteredWallMidEstimator(),
        "hybrid_wall_micro": HybridWallMicroEstimator(),
    }
)


class FairValueEngine:
    """Resolves fair-value estimates with a per-product fallback chain."""

    def __init__(self, estimators: Mapping[str, Estimator] | None = None) -> None:
        self._estimators: dict[str, Estimator] = dict(estimators or ESTIMATORS)

    def register(self, estimator: Estimator) -> None:
        self._estimators[estimator.name] = estimator

    def known_estimators(self) -> tuple[str, ...]:
        return tuple(sorted(self._estimators))

    def estimate(
        self,
        product: str,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate:
        """Resolve the primary + fallback chain; never returns ``None``.

        If every configured estimator declines, drop to an anchor-price
        fallback, and finally a zero-confidence zero-price marker so the
        caller can still proceed. The doctrine Invariant 5: a fallback
        path always exists.

        **Warning — ``zero_fallback`` is a trap for products without an
        ``anchor_price``.** The ``price=0.0`` marker exists so the
        trader never crashes when the book is empty, but if any
        strategy uses that value as a real fair value it will place
        catastrophically mispriced orders. Round-1 sweeps caught this:
        ``depth_mid`` / ``hybrid_wall_micro`` / ``mid`` primaries on
        INTARIAN_PEPPER_ROOT (no anchor_price) all hit ``zero_fallback``
        on one-sided books and posted ~-128k PnL. The fix for any
        production-ready ``ProductConfig`` without an anchor is to put
        at least one estimator that **always returns a value** (e.g.
        ``linear_drift`` after warm-up, or any estimator with a
        non-``None`` bootstrap branch) at the end of the fallback
        chain. See ``outputs/round_1/notes/phase4_sweep_shortlist.md``
        for the full diagnosis.
        """
        del product  # reserved for future per-product registries
        chain: list[str] = [config.fair_value_method, *config.fair_value_fallbacks]
        for name in chain:
            estimator = self._estimators.get(name)
            if estimator is None:
                continue
            result = estimator.estimate(snapshot, memory, config)
            if result is not None:
                return result
        if config.anchor_price is not None:
            return FairValueEstimate(
                price=float(config.anchor_price),
                method="anchor_fallback",
                confidence=0.1,
            )
        return FairValueEstimate(price=0.0, method="zero_fallback", confidence=0.0)

    def estimate_all(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> dict[str, FairValueEstimate]:
        """Run every registered estimator on the same snapshot.

        Skips estimators that return ``None``. Useful for Phase 3
        side-by-side fair-value inference experiments.
        """
        results: dict[str, FairValueEstimate] = {}
        for name, estimator in self._estimators.items():
            result = estimator.estimate(snapshot, memory, config)
            if result is not None:
                results[name] = result
        return results
