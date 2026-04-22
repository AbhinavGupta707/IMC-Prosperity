"""Portfolio-level risk manager (fixes D3 + D5 at the risk layer).

Extends the existing per-product RiskManager to coordinate limits
across products. Needed when:

- Basket arb: basket position + constituent positions share capacity
  across a logical "arb book". Need aggregate exposure tracking.
- Options MM: per-strike positions aggregate to a net delta that must
  be hedged at the underlying. Aggregate delta limit applies.
- Stat-arb pairs: position in product A implies position in product B
  via hedge ratio; need joint capacity management.

This module wraps the existing RiskManager (unchanged) and adds a
cross-product coordinator on top. Per-product clipping still happens;
we just also surface cross-product aggregate metrics and allow
arb-tagged strategies to reserve capacity.

Also: residual allocator default=on for arb-tagged strategies (D5).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from src.core.risk import Capacity, RiskManager
from src.datamodel import Order

StrategyTag = Literal["mm", "arb", "directional", "hedger"]


@dataclass(frozen=True)
class ProductTag:
    """Metadata on how a product is being traded this tick."""

    product: str
    strategy_tag: StrategyTag = "mm"
    """How this product is being used: MM (symmetric quotes), ARB (hedge
    leg of a spread), DIRECTIONAL (signal-driven take), HEDGER (delta
    neutralizer for an options book)."""

    # For arb legs: the logical "group" this product belongs to. Used to
    # track aggregate exposure of a basket-arb or options-book setup.
    arb_group: str | None = None

    # For hedger legs: the target product whose risk this leg hedges.
    hedges_product: str | None = None


@dataclass(frozen=True)
class PortfolioCapacity:
    """Cross-product capacity summary for one tick."""

    per_product: Mapping[str, Capacity]
    gross_exposure: int
    """Sum of |position| across all products."""

    net_exposure_by_group: Mapping[str, int]
    """Signed net exposure per arb_group (baskets / options books)."""


@dataclass(frozen=True)
class PortfolioRiskConfig:
    """Portfolio-level risk gates."""

    # Caps on gross exposure (sum of |positions|). 0 = no cap.
    max_gross_exposure: int = 0

    # Per-arb-group caps on net exposure (signed sum of positions in the group).
    max_net_exposure_per_group: int = 0

    # If True, residual-allocator defaults ON for arb-tagged strategies
    # (fixes D5).
    residual_default_on_for_arb: bool = True


class PortfolioRiskManager:
    """Composes cross-product checks on top of per-product clipping.

    Usage:

        mgr = PortfolioRiskManager(base=RiskManager(), config=...)
        # Per-product clipping (unchanged from existing RiskManager)
        clipped = mgr.clip_orders(product, orders, position, limit)
        # Cross-product capacity (new)
        cap = mgr.portfolio_capacity(positions, limits, tags)
        # Group-level exposure (new)
        exposure = mgr.group_exposure("basket1_arb", positions, tags)
    """

    def __init__(
        self,
        *,
        base: RiskManager | None = None,
        config: PortfolioRiskConfig | None = None,
    ) -> None:
        self.base = base or RiskManager()
        self.config = config or PortfolioRiskConfig()

    # ---------------- per-product (delegated to base)

    def clip_orders(
        self,
        product: str,
        orders: list[Order],
        current_position: int,
        limit: int,
    ) -> list[Order]:
        return self.base.clip_orders(product, orders, current_position, limit)

    def capacity(self, position: int, limit: int) -> Capacity:
        return self.base.capacity(position, limit)

    # ---------------- cross-product (new)

    def portfolio_capacity(
        self,
        positions: Mapping[str, int],
        limits: Mapping[str, int],
        tags: Mapping[str, ProductTag] | None = None,
    ) -> PortfolioCapacity:
        per_product = {
            p: self.base.capacity(positions.get(p, 0), limits.get(p, 0))
            for p in set(positions) | set(limits)
        }
        gross = sum(abs(positions.get(p, 0)) for p in positions)
        net_by_group: dict[str, int] = {}
        if tags is not None:
            for product, tag in tags.items():
                if tag.arb_group is None:
                    continue
                net_by_group[tag.arb_group] = (
                    net_by_group.get(tag.arb_group, 0) + positions.get(product, 0)
                )
        return PortfolioCapacity(
            per_product=per_product,
            gross_exposure=gross,
            net_exposure_by_group=net_by_group,
        )

    def group_exposure(
        self,
        arb_group: str,
        positions: Mapping[str, int],
        tags: Mapping[str, ProductTag],
    ) -> int:
        return sum(
            positions.get(product, 0)
            for product, tag in tags.items()
            if tag.arb_group == arb_group
        )

    def residual_allowed(self, tag: ProductTag) -> bool:
        """Does the residual allocator run for this strategy?

        Replaces the global ``ResidualConfig.enabled=False`` default with
        a tag-aware decision. Arb strategies have slack by design; MM
        strategies already saturate the book.
        """
        if tag.strategy_tag == "arb" and self.config.residual_default_on_for_arb:
            return True
        if tag.strategy_tag == "directional":
            # Directional strategies take discrete positions; residual
            # would dilute the signal. Default off.
            return False
        if tag.strategy_tag == "hedger":
            # Hedgers fire only to neutralize delta. No residual.
            return False
        # MM default: off (their primary logic already uses full capacity).
        return False

    def exceeds_gross_cap(self, gross: int) -> bool:
        return self.config.max_gross_exposure > 0 and gross > self.config.max_gross_exposure

    def exceeds_group_cap(self, group_net: int) -> bool:
        cap = self.config.max_net_exposure_per_group
        return cap > 0 and abs(group_net) > cap
