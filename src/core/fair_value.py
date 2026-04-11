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
    name = "weighted_mid"
    LOOKBACK = 4

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        history = memory.recent_mids[-self.LOOKBACK :]
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


ESTIMATORS: Mapping[str, Estimator] = MappingProxyType(
    {
        "anchor": AnchorEstimator(),
        "mid": MidEstimator(),
        "microprice": MicropriceEstimator(),
        "rolling_mid": RollingMidEstimator(),
        "weighted_mid": WeightedMidEstimator(),
        "ewma_mid": EwmaMidEstimator(),
        "depth_mid": DepthMidEstimator(),
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
