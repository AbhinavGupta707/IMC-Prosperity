"""Cross-product portfolio context (fixes D3 in R3+ architecture).

Existing ``StrategyContext`` carries only one product's snapshot. A
basket-arb strategy fundamentally needs to read multiple products'
snapshots at once (basket + constituents). Rather than fork
``StrategyContext``, this module provides a ``PortfolioSnapshot`` that
sits alongside the single-product snapshot. The trader dispatch layer
builds it once per tick and passes it to strategies that opt in.

Existing single-product strategies ignore the new field (they never
read it), so this is a non-breaking extension.

Access patterns:

    # Single-product strategy (unchanged)
    def generate_intent(self, context: StrategyContext):
        snap = context.snapshot
        ...

    # Cross-product strategy (new)
    def generate_intent(self, context: StrategyContext):
        portfolio = context.portfolio  # PortfolioSnapshot | None
        if portfolio is None:
            # Degrade gracefully — portfolio not populated
            return self._single_product_fallback(context)
        basket_snap = portfolio.for_product("BASKET")
        coc_snap   = portfolio.for_product("COCOA")
        ...

The old-school single-product StrategyContext still works; R3+ engines
build on this extension.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from src.core.types import NormalizedSnapshot, Product, ProductMemory, Timestamp


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Read-only view of all products' books at one tick.

    Built by the trader dispatch layer from the full ``TradingState`` and
    shared across all strategies for the tick. Also carries cross-product
    signal values and counterparty state that were materialized before
    per-product strategy dispatch (so single-product strategies can still
    opt in to these signals without re-computing).
    """

    timestamp: Timestamp
    snapshots: Mapping[Product, NormalizedSnapshot] = field(
        default_factory=lambda: MappingProxyType({})
    )

    # Cross-product positions: same as per-product snapshots' .position, but
    # exposed at the portfolio level for convenience and for strategies that
    # aggregate positions (e.g., an options book that tracks aggregate delta).
    positions: Mapping[Product, int] = field(
        default_factory=lambda: MappingProxyType({})
    )

    # Per-product position limits. Trader-provided so strategies don't have
    # to re-fetch from config.
    position_limits: Mapping[Product, int] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def for_product(self, product: Product) -> NormalizedSnapshot | None:
        """Return the snapshot for a product, or None if absent this tick."""
        return self.snapshots.get(product)

    def position_of(self, product: Product) -> int:
        return int(self.positions.get(product, 0))

    def limit_of(self, product: Product) -> int:
        return int(self.position_limits.get(product, 0))

    def products(self) -> tuple[Product, ...]:
        return tuple(self.snapshots.keys())


def build_portfolio_snapshot(
    timestamp: Timestamp,
    snapshots: Mapping[Product, NormalizedSnapshot],
    position_limits: Mapping[Product, int],
) -> PortfolioSnapshot:
    """Factory used by the trader dispatch layer.

    Extracts positions from each snapshot (since ``NormalizedSnapshot``
    already carries ``.position``) and freezes the maps.
    """
    positions = {p: int(s.position) for p, s in snapshots.items()}
    return PortfolioSnapshot(
        timestamp=timestamp,
        snapshots=MappingProxyType(dict(snapshots)),
        positions=MappingProxyType(positions),
        position_limits=MappingProxyType(dict(position_limits)),
    )
