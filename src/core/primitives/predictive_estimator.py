"""Predictive fair-value estimator (fixes D2).

Our existing 12 FairValueEngine estimators are all reactive — they
compute statistics of the current book / recent mids. None of them
conditions the price on a signal.

This module provides a composable wrapper:

    PredictiveEstimator(base: Estimator, signal_name: str, bus: SignalBus,
                        coefficient: float)

It reads the current value of a signal from the SignalBus, multiplies
by a coefficient, and adds the correction to the base estimator's
output. If the signal is absent or un-validated, the wrapper returns
the base estimator unchanged (graceful degradation).

The SIGNAL must have passed the validation harness before being used
here — the SignalBus already enforces ``trusted_only=True`` filtering
in its ``get()`` method, so unvalidated signals won't appear.

This is how R3+ engines inject signal information into fair value:
- basket spread z-score → predictive correction to basket mid
- IV residual → predictive correction to option fair
- regime flag → switch between estimators (via RegimeEstimator, next)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from src.core.config_core import ProductConfig
from src.core.fair_value import Estimator
from src.core.primitives.signal_bus import SignalBus
from src.core.types import FairValueEstimate, NormalizedSnapshot, ProductMemory, Scalar


@dataclass(frozen=True)
class PredictiveEstimatorConfig:
    """Wiring for one predictive estimator.

    The coefficient translates the signal value (z-score, imbalance,
    residual) into a price adjustment. For a z-score signal on a
    spread, coefficient ≈ expected_reversion_per_z_unit (ticks).
    """

    signal_name: str
    coefficient: float
    """Units: price per signal-unit. Positive = signal increases fair."""

    max_adjustment: float = 5.0
    """Cap on |coefficient × signal| — safety against runaway signal."""

    # NOTE: previously exposed a ``require_validated`` toggle. It has been
    # removed — PredictiveEstimator now UNCONDITIONALLY requires a signal
    # with ``validated=True`` before adjusting prices (D9 principle: no
    # unvalidated research signal may enter the fair-value path).
    # Research-quality signals should still be published on the bus, but
    # with ``validated=False``, and PredictiveEstimator will correctly
    # ignore them.


class PredictiveEstimator:
    """Composes a reactive base estimator with a validated signal.

    Implements the same ``Estimator`` protocol as the existing 12
    estimators (name, estimate) so it can be registered into
    FairValueEngine as a drop-in primary.
    """

    def __init__(
        self,
        *,
        base: Estimator,
        config: PredictiveEstimatorConfig,
        bus: SignalBus,
        name: str | None = None,
    ) -> None:
        self._base = base
        self._config = config
        self._bus = bus
        self.name = name or f"predictive_{base.name}_{config.signal_name}"

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        base_estimate = self._base.estimate(snapshot, memory, config)
        if base_estimate is None:
            return None

        signal = self._bus.get(
            self._config.signal_name,
            trusted_only=True,
        )
        if signal is None:
            # Graceful degradation: return base unchanged.
            return FairValueEstimate(
                price=base_estimate.price,
                method=self.name,
                confidence=base_estimate.confidence,
                components=base_estimate.components,
            )

        raw_adjustment = self._config.coefficient * signal.value
        adjustment = max(
            -self._config.max_adjustment,
            min(self._config.max_adjustment, raw_adjustment),
        )
        adjusted_price = base_estimate.price + adjustment

        components: Mapping[str, Scalar] = MappingProxyType(
            {
                "base_price": float(base_estimate.price),
                "signal_name": self._config.signal_name,
                "signal_value": float(signal.value),
                "signal_ic": float(signal.ic) if signal.ic is not None else 0.0,
                "adjustment": float(adjustment),
            }
        )
        return FairValueEstimate(
            price=adjusted_price,
            method=self.name,
            confidence=base_estimate.confidence,
            components=components,
        )
