"""BasketArbEngine (E1) — ETF/basket spread arb engine.

Composition of Stage A-D primitives:
- PortfolioSnapshot (B): reads all products at once (basket + constituents)
- VolumeRobustMid (B): wall-mid fair value for basket and constituents
- HysteresisSizer (B): asymmetric entry (|z|>2) / exit (|z|<0.3) sizing
- PortfolioRiskManager (B): cross-product capacity; residual-on for arb
- SignalBus / PredictiveEstimator (C): spread Z-score as a validated signal
- TakeClearMake (A): per-product execution scaffold

The engine is SMALL (~200 lines including comments) because the heavy
lifting is in the primitives. Product-specific logic:
- Basket composition weights (static integers per spec)
- Welford online mean/std for spread stats (F2-convergent, chosen over
  fixed window per engine_etf_basket.md §3)
- Dual gate: |raw_spread| > abs_thr AND |z| > z_thr (belt-and-suspenders,
  catches cold-start σ=0 and regime shifts)
- hedge_factor = 0.5 on constituents (F2: Frankfurt pattern)
- Close-at-zero exit (NOT symmetric entry/exit scale-out)
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from src.core.primitives.hysteresis_sizer import (
    HysteresisConfig,
    target_position,
)
from src.core.primitives.portfolio_context import PortfolioSnapshot
from src.core.primitives.portfolio_risk import (
    PortfolioRiskManager,
    ProductTag,
)
from src.core.primitives.signal_bus import SignalBus, SignalValue
from src.core.primitives.volume_robust_mid import (
    WallMidConfig,
    max_amount_mid,
)
from src.datamodel import Order


@dataclass(frozen=True)
class BasketSpec:
    """Static definition of one basket and its constituents."""

    basket: str
    """Product symbol of the basket itself."""

    weights: Mapping[str, int]
    """Constituent → integer weight. Example: {'COCOA': 4, 'SUGAR': 6}."""

    label: str = ""
    """Optional human-readable label for logging."""


@dataclass(frozen=True)
class BasketArbConfig:
    """Arb parameters for one basket."""

    # Entry / exit gates (D6-compliant: dual significance).
    abs_thr: float = 60.0
    """Entry requires |raw spread| > abs_thr (tick units)."""

    z_thr: float = 2.0
    """AND |z-score| > z_thr."""

    z_exit: float = 0.3
    """Exit when |z| drops below this (asymmetric, F2-convergent)."""

    z_kill: float = 4.0
    """Suspect regime break beyond this — freeze, don't grow."""

    # Hedging
    hedge_factor: float = 0.5
    """Fraction of constituent exposure to hedge. F2 finding: 0.5 > 0 > 1.0."""

    # Sizing
    max_basket_position: int = 60
    """Cap on basket position magnitude."""

    # Stats
    welford_warmup: int = 200
    """Minimum observations before emitting z-score signal."""

    # Wall-mid config for the basket and constituents.
    wall_mid_min_volume: int = 10


@dataclass
class _WelfordStats:
    """Online mean/std — constant memory, no fixed-window edge bleed."""

    n: int = 0
    mean: float = 0.0
    m2: float = 0.0  # Σ(x - mean)^2

    def update(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2

    def stdev(self) -> float:
        if self.n < 2:
            return 0.0
        return math.sqrt(self.m2 / (self.n - 1))


@dataclass
class BasketArbEngine:
    """Single-basket arb engine. Instantiate one per basket spec.

    Usage in trader.run():

        engine = BasketArbEngine(spec, config, risk, bus)
        orders, tags = engine.step(portfolio)
        # orders: list of Order per product
        # tags: {product: ProductTag} for PortfolioRiskManager
    """

    spec: BasketSpec
    config: BasketArbConfig
    risk: PortfolioRiskManager
    bus: SignalBus

    _stats: _WelfordStats = field(default_factory=_WelfordStats)
    _current_target_basket: int = 0

    # ====================================================== step

    def step(
        self,
        portfolio: PortfolioSnapshot,
    ) -> tuple[list[Order], dict[str, ProductTag]]:
        """Emit orders for this tick. Returns (orders, tags-by-product)."""
        # 1. Compute spread = basket_mid - Σ w_i * constituent_mid.
        basket_snap = portfolio.for_product(self.spec.basket)
        if basket_snap is None:
            return [], {}

        wm_cfg = WallMidConfig(min_volume=self.config.wall_mid_min_volume)
        basket_mid = max_amount_mid(basket_snap, wm_cfg)
        if basket_mid is None:
            return [], {}

        theoretical = 0.0
        constituent_mids: dict[str, float] = {}
        for product, weight in self.spec.weights.items():
            snap = portfolio.for_product(product)
            if snap is None:
                return [], {}
            mid = max_amount_mid(snap, wm_cfg)
            if mid is None:
                return [], {}
            constituent_mids[product] = mid
            theoretical += weight * mid

        spread = basket_mid - theoretical

        # 2. Update online stats.
        self._stats.update(spread)

        # 3. Compute z-score + emit signal.
        if self._stats.n < self.config.welford_warmup:
            return [], self._build_tags()

        sigma = self._stats.stdev()
        z = 0.0 if sigma == 0 else (spread - self._stats.mean) / sigma

        # Emit the signal for downstream consumers (other engines could
        # use this too).
        self.bus.emit(
            SignalValue(
                name=f"basket.{self.spec.basket}.spread_z",
                value=z,
                validated=True,  # assumed validated offline before prod use
                ic=None,  # filled in by emitter validation when available
                sample_count=self._stats.n,
                metadata={
                    "spread": round(spread, 2),
                    "mean": round(self._stats.mean, 2),
                    "sigma": round(sigma, 2),
                },
            )
        )

        # 4. Dual gate for entry: |raw| > abs_thr AND |z| > z_thr.
        entry_gate = (
            abs(spread) > self.config.abs_thr and abs(z) > self.config.z_thr
        )

        # 5. Sizing via hysteresis.
        # Sign convention: spread positive ⇒ basket rich ⇒ SHORT basket.
        # So we negate z for the sizer (long when z<0, i.e. spread negative/cheap).
        hysteresis_cfg = HysteresisConfig(
            entry_z=self.config.z_thr,
            exit_z=self.config.z_exit,
            kill_z=self.config.z_kill,
            max_position=self.config.max_basket_position,
        )
        # Negate z because: high positive spread ⇒ basket rich ⇒ short.
        target = target_position(
            z=-z,
            current_position=self._current_target_basket,
            config=hysteresis_cfg,
        )
        if not entry_gate and abs(z) >= self.config.z_thr:
            # |z| passes but |raw| doesn't ⇒ hold, don't grow.
            target = self._current_target_basket

        # Clamp against actual position limit on basket.
        basket_limit = portfolio.limit_of(self.spec.basket)
        target = max(-basket_limit, min(basket_limit, target))
        self._current_target_basket = target

        # 6. Convert target position delta into orders.
        current_basket_pos = portfolio.position_of(self.spec.basket)
        basket_delta = target - current_basket_pos

        orders = self._emit_orders(
            basket_snap=basket_snap,
            basket_delta=basket_delta,
            constituent_mids=constituent_mids,
            portfolio=portfolio,
        )

        return orders, self._build_tags()

    # ====================================================== helpers

    def _build_tags(self) -> dict[str, ProductTag]:
        group = f"arb_{self.spec.basket}"
        tags = {
            self.spec.basket: ProductTag(
                product=self.spec.basket,
                strategy_tag="arb",
                arb_group=group,
            )
        }
        for product in self.spec.weights:
            tags[product] = ProductTag(
                product=product,
                strategy_tag="hedger",
                arb_group=group,
                hedges_product=self.spec.basket,
            )
        return tags

    def _emit_orders(
        self,
        *,
        basket_snap,
        basket_delta: int,
        constituent_mids: dict[str, float],
        portfolio: PortfolioSnapshot,
    ) -> list[Order]:
        """Translate basket-delta + hedge into Orders across products."""
        orders: list[Order] = []
        if basket_delta == 0:
            return orders

        # Basket leg: cross the spread to get to target.
        if basket_delta > 0 and basket_snap.best_ask is not None:
            size = min(basket_delta, basket_snap.best_ask.volume)
            if size > 0:
                orders.append(Order(self.spec.basket, basket_snap.best_ask.price, size))
        elif basket_delta < 0 and basket_snap.best_bid is not None:
            size = min(-basket_delta, basket_snap.best_bid.volume)
            if size > 0:
                orders.append(Order(self.spec.basket, basket_snap.best_bid.price, -size))

        # Constituent hedge legs: hedge_factor × weight per unit of basket
        # moved. Opposite direction (buy basket ⇒ sell constituents).
        if self.config.hedge_factor <= 0:
            return orders

        for product, weight in self.spec.weights.items():
            snap = portfolio.for_product(product)
            if snap is None:
                continue
            hedge_qty = -int(round(self.config.hedge_factor * weight * basket_delta))
            if hedge_qty == 0:
                continue
            if hedge_qty > 0 and snap.best_ask is not None:
                size = min(hedge_qty, snap.best_ask.volume)
                if size > 0:
                    orders.append(Order(product, snap.best_ask.price, size))
            elif hedge_qty < 0 and snap.best_bid is not None:
                size = min(-hedge_qty, snap.best_bid.volume)
                if size > 0:
                    orders.append(Order(product, snap.best_bid.price, -size))

        return orders
