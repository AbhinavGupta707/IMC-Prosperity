"""SignalBus — first-class pub/sub for trading signals (fixes D4).

Before this primitive, FlowAnalyzer was observational-only (its own
docstring: "never alters strategy behaviour"). Signals had no way to
influence decisions. This module introduces a pub/sub bus where:

- **Emitters** (flow analyzer, basket-spread calculator, IV-residual
  computer, counterparty-state model, lead-lag predictor) publish
  signal values per tick.

- **Consumers** (strategies, fair-value estimators, sizers, hedgers)
  subscribe to signals and read their current value.

- **Every signal carries validation metadata** (rolling IC, shuffle
  baseline, sample count, last-validated tick). No untrusted signal
  reaches a consumer without passing validation (fixes D9).

- **Snapshot is per-tick** — the bus is rebuilt each tick from the
  latest emitter outputs. There is no cross-tick pub/sub state; all
  that lives on the emitter/consumer side. Keeps the bus dumb.

Usage:

    bus = SignalBus()
    bus.emit(SignalValue(name="basket_spread_z", value=2.4,
        validated=True, ic=0.18, metadata={"window": 500}))
    val = bus.get("basket_spread_z")
    if val and val.validated and abs(val.ic) > 0.03:
        # act on the signal
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class SignalValue:
    """One signal reading at one tick.

    Immutable so consumers can't mutate emitter state.
    """

    name: str
    """Unique signal identifier (e.g., 'basket_b1_spread_z', 'ash_obi')."""

    value: float
    """The numeric signal value at this tick."""

    validated: bool = False
    """True iff the signal has passed its validation harness.
    Unvalidated signals can be emitted (for logging/research) but
    consumers should ignore them for trading decisions."""

    ic: float | None = None
    """Rolling information coefficient (Pearson correlation with forward
    returns). None if not yet measured."""

    sample_count: int = 0
    """Number of ticks contributing to the rolling IC estimate."""

    last_validated_tick: int = -1
    """Most recent tick at which full validation was run."""

    metadata: Mapping[str, float | int | str | bool] = field(
        default_factory=lambda: MappingProxyType({})
    )
    """Extra context (window size, regime flag, etc.)."""


class SignalBus:
    """Per-tick signal registry. Rebuilt each tick by the trader layer.

    Design decisions:
    - No cross-tick state on the bus itself. Emitters hold their own
      rolling history; the bus just mirrors the current-tick snapshot.
    - Last emit wins (no multi-value per name). Emitters can subscribe
      to each other if they want to chain.
    - Name-space is flat; use prefixes ('basket.b1.spread_z',
      'options.10000.iv_residual') for organization.
    - Consumers may ask for ``trusted_only=True`` to filter out any
      value whose ``validated`` is False. This is the enforcement
      point for D9.
    """

    def __init__(self) -> None:
        self._values: dict[str, SignalValue] = {}

    def emit(self, value: SignalValue) -> None:
        """Publish a signal value for the current tick."""
        self._values[value.name] = value

    def get(self, name: str, *, trusted_only: bool = True) -> SignalValue | None:
        """Return the current-tick value, or None.

        ``trusted_only=True`` (default) filters out un-validated signals;
        pass ``trusted_only=False`` to access research signals.
        """
        v = self._values.get(name)
        if v is None:
            return None
        if trusted_only and not v.validated:
            return None
        return v

    def all(self, *, trusted_only: bool = True) -> Mapping[str, SignalValue]:
        """Current-tick snapshot of all signals."""
        if trusted_only:
            return MappingProxyType(
                {name: v for name, v in self._values.items() if v.validated}
            )
        return MappingProxyType(dict(self._values))

    def names(self) -> tuple[str, ...]:
        return tuple(self._values.keys())

    def clear(self) -> None:
        """Drop all values. Called at tick start by the trader layer."""
        self._values.clear()


def empty_signal_bus() -> SignalBus:
    """Factory for a fresh bus (used by test harnesses and initial state)."""
    return SignalBus()
