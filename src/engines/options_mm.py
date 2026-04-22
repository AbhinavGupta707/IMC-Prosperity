"""OptionsEngine (E2) — residual-IV market-maker for short-dated options.

Composition of Stage A-D primitives:
- BSM pricer + IV solver + SmileFitter (D)
- PortfolioSnapshot (B): aggregate delta across strikes
- TakeClearMake (A): per-strike execution scaffold
- PortfolioRiskManager (B): cross-strike capacity
- CrashTelemetry (A): jump-detector + kill-switch

Design (per engine_options.md + F2/F4 convergence):

- **Fair IV = SmileFitter output** (warmup quadratic → rolling EWMA).
- **Quote each strike around BSM(S, K, T, fair_IV).**
- **AGGREGATE-BOOK delta hedge**, not per-strike. 3-5× hedge reduction.
- **Whalley-Wilmott band** gate: hedge only if |Δ| > band, else skip.
  Default OFF (F1: hedging costs ~$50k/day in 1-wide spread).
- **Kill-switch**: halt on jump (|r| / EWMA(|r|, 500) > 4).
- **Short-straddle overlay**: cap <10% of book, IV > RV triggered.

The engine is SMALL — product-specific logic is the smile fit +
strike→BSM price conversion. Everything else is shared primitives.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field

from src.core.primitives.portfolio_context import PortfolioSnapshot
from src.core.primitives.portfolio_risk import (
    PortfolioRiskManager,
    ProductTag,
)
from src.datamodel import Order
from src.options.bsm import BSMInputs, call_greeks, call_price, implied_vol
from src.options.smile import SmileConfig, SmileFitter


@dataclass(frozen=True)
class VoucherSpec:
    """One European-call voucher strike."""

    product: str  # e.g., "VOUCHER_10000"
    strike: float
    position_limit: int = 80


@dataclass(frozen=True)
class OptionsBookSpec:
    """Underlying + chain of strikes."""

    underlying: str
    """Product symbol of the underlying (e.g., 'VOLCANIC_ROCK')."""

    vouchers: tuple[VoucherSpec, ...]
    """All listed strikes for this underlying."""

    time_to_expiry_ticks: float
    """T in tick units (must match the per-tick vol in SmileConfig)."""


@dataclass(frozen=True)
class OptionsEngineConfig:
    """MM configuration."""

    # Quote edge (ticks) around BSM fair.
    default_edge: float = 2.0

    # Size per strike per tick.
    default_quote_size: int = 10

    # Hedge behavior.
    delta_hedge_enabled: bool = False
    """DEFAULT OFF. In 1-wide spread books, spread cost ≫ gamma P&L."""

    ww_band_factor: float = 3.0
    """Whalley-Wilmott band = ww_band_factor × (λ Γ² S² / γ σ²)^(1/3).
    If |aggregate_delta| > band → hedge."""

    ww_risk_aversion: float = 1.0
    """γ in the WW formula. Higher = tighter band = more hedging."""

    # Jump detection.
    jump_window: int = 500
    jump_threshold: float = 4.0

    # Smile config (forwarded to SmileFitter).
    smile_warmup_threshold: int = 50
    smile_rolling_window: int = 200
    smile_ewma_halflife: float = 100.0


@dataclass
class OptionsEngine:
    """Options MM for one underlying + chain."""

    spec: OptionsBookSpec
    config: OptionsEngineConfig
    risk: PortfolioRiskManager

    _smile: SmileFitter = field(init=False)
    _recent_abs_returns: deque = field(init=False)
    _last_underlying_mid: float | None = field(default=None, init=False)
    _in_kill_cooldown: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._smile = SmileFitter(
            config=SmileConfig(
                warmup_threshold=self.config.smile_warmup_threshold,
                rolling_window=self.config.smile_rolling_window,
                ewma_halflife=self.config.smile_ewma_halflife,
            )
        )
        self._recent_abs_returns = deque(maxlen=self.config.jump_window)

    # ====================================================== step

    def step(
        self,
        portfolio: PortfolioSnapshot,
    ) -> tuple[list[Order], dict[str, ProductTag]]:
        """Emit orders for this tick across all strikes + hedge."""
        underlying_snap = portfolio.for_product(self.spec.underlying)
        if underlying_snap is None or underlying_snap.mid is None:
            return [], {}

        spot = float(underlying_snap.mid)

        # Jump detection.
        if self._detect_jump(spot):
            return [], self._build_tags()

        # Observe IVs from live voucher prices to train the smile.
        self._train_smile(portfolio, spot)

        orders: list[Order] = []
        aggregate_delta = 0.0

        # Quote each voucher around BSM fair.
        for voucher in self.spec.vouchers:
            voucher_orders, voucher_delta_contribution = self._step_voucher(
                voucher=voucher,
                portfolio=portfolio,
                spot=spot,
            )
            orders.extend(voucher_orders)
            aggregate_delta += voucher_delta_contribution

        # Aggregate-book delta hedge — only if enabled AND band breached.
        if self.config.delta_hedge_enabled:
            hedge_order = self._compute_hedge(
                aggregate_delta=aggregate_delta,
                underlying_snap=underlying_snap,
                portfolio=portfolio,
            )
            if hedge_order is not None:
                orders.append(hedge_order)

        return orders, self._build_tags()

    # ====================================================== sub-steps

    def _train_smile(self, portfolio: PortfolioSnapshot, spot: float) -> None:
        for voucher in self.spec.vouchers:
            snap = portfolio.for_product(voucher.product)
            if snap is None or snap.mid is None:
                continue
            market_price = float(snap.mid)
            iv = implied_vol(
                market_price=market_price,
                spot=spot,
                strike=voucher.strike,
                time_to_expiry=self.spec.time_to_expiry_ticks,
            )
            if iv is not None:
                self._smile.observe(strike=voucher.strike, iv=iv)

    def _step_voucher(
        self,
        *,
        voucher: VoucherSpec,
        portfolio: PortfolioSnapshot,
        spot: float,
    ) -> tuple[list[Order], float]:
        snap = portfolio.for_product(voucher.product)
        if snap is None:
            return [], 0.0
        fair_iv = self._smile.fair_iv(
            strike=voucher.strike,
            spot=spot,
            time_to_expiry=self.spec.time_to_expiry_ticks,
        )
        if fair_iv is None:
            return [], 0.0
        try:
            bsm = BSMInputs(
                spot=spot,
                strike=voucher.strike,
                time_to_expiry=self.spec.time_to_expiry_ticks,
                volatility=fair_iv,
            )
        except ValueError:
            return [], 0.0

        fair_price = call_price(bsm)
        greeks = call_greeks(bsm)

        # Position contribution to aggregate delta.
        pos = portfolio.position_of(voucher.product)
        delta_contribution = pos * greeks.delta

        # Symmetric maker quotes around fair. (F2 convergent: no asymmetric
        # quoting on stable/MR products; on short-dated options the same
        # principle applies — signal-aware asymmetry has zero top-team
        # evidence outside of Olivia-driven directional takes on volatile
        # products.)
        bid_price = int(math.floor(fair_price - self.config.default_edge))
        ask_price = int(math.ceil(fair_price + self.config.default_edge))

        # Don't cross existing BBO.
        if snap.best_ask is not None:
            bid_price = min(bid_price, snap.best_ask.price - 1)
        if snap.best_bid is not None:
            ask_price = max(ask_price, snap.best_bid.price + 1)

        limit = portfolio.limit_of(voucher.product) or voucher.position_limit
        buy_cap = max(0, limit - pos)
        sell_cap = max(0, limit + pos)

        size = self.config.default_quote_size
        bid_size = min(size, buy_cap)
        ask_size = min(size, sell_cap)

        orders: list[Order] = []
        if bid_size > 0 and bid_price > 0:
            orders.append(Order(voucher.product, bid_price, bid_size))
        if ask_size > 0 and ask_price > 0:
            orders.append(Order(voucher.product, ask_price, -ask_size))

        return orders, delta_contribution

    def _compute_hedge(
        self,
        *,
        aggregate_delta: float,
        underlying_snap,
        portfolio: PortfolioSnapshot,
    ) -> Order | None:
        """Aggregate-book delta hedge if Whalley-Wilmott band is breached.

        Pulls Γ·S² and σ from the current smile to compute the band.
        If |aggregate_delta| < band, don't hedge.
        """
        if abs(aggregate_delta) < 1:
            return None

        # Estimate band using ATM (closest-to-spot) voucher's Γ and σ.
        spot = float(underlying_snap.mid) if underlying_snap.mid else 0.0
        if spot <= 0:
            return None
        closest_voucher = min(
            self.spec.vouchers,
            key=lambda v: abs(v.strike - spot),
        )
        fair_iv = self._smile.fair_iv(
            strike=closest_voucher.strike,
            spot=spot,
            time_to_expiry=self.spec.time_to_expiry_ticks,
        )
        if fair_iv is None:
            return None
        try:
            bsm = BSMInputs(
                spot=spot,
                strike=closest_voucher.strike,
                time_to_expiry=self.spec.time_to_expiry_ticks,
                volatility=fair_iv,
            )
        except ValueError:
            return None
        g = call_greeks(bsm)
        sigma = fair_iv

        half_spread = 0.5  # ticks; 1-wide spread assumption
        lam = half_spread
        gamma_risk = self.config.ww_risk_aversion
        # Whalley-Wilmott no-trade band (Whalley & Wilmott 1997):
        #   Δ_band ≈ factor × (λ · Γ² · S² / (γ · σ²))^(1/3)
        # CRITICAL fix: previously computed gamma_s2 = Γ·S² then squared
        # the whole thing ⇒ (Γ·S²)² = Γ²·S⁴, giving a band S² too wide.
        # For S ≈ 10,000, that was ~1e8× wider ⇒ hedge never fired.
        gamma_sq_s_sq = (g.gamma * g.gamma) * (spot * spot)
        band = self.config.ww_band_factor * (
            (lam * gamma_sq_s_sq / (gamma_risk * sigma * sigma)) ** (1 / 3)
        )

        if abs(aggregate_delta) < band:
            return None

        # Hedge size = round aggregate_delta (cross the spread).
        hedge_qty = -int(round(aggregate_delta))
        if hedge_qty > 0 and underlying_snap.best_ask is not None:
            size = min(hedge_qty, underlying_snap.best_ask.volume)
            if size > 0:
                return Order(
                    self.spec.underlying, underlying_snap.best_ask.price, size
                )
        if hedge_qty < 0 and underlying_snap.best_bid is not None:
            size = min(-hedge_qty, underlying_snap.best_bid.volume)
            if size > 0:
                return Order(
                    self.spec.underlying, underlying_snap.best_bid.price, -size
                )
        return None

    def _detect_jump(self, spot: float) -> bool:
        """True if we should halt trading this tick (jump regime).

        Uses a true EWMA of |r_t| (Brown 1956) with halflife derived from
        jump_window. Previous SMA implementation was misnamed; functionally
        similar but docs/tests expected EWMA. Also: when cooldown expires,
        re-anchor _last_underlying_mid to current spot so the huge jump
        doesn't instantly re-trigger on the next tick.
        """
        if self._in_kill_cooldown > 0:
            self._in_kill_cooldown -= 1
            # H9 fix: re-anchor on cooldown expiry so post-jump spot becomes
            # the new baseline, preventing immediate re-trigger.
            if self._in_kill_cooldown == 0:
                self._last_underlying_mid = spot
                self._recent_abs_returns.clear()
            return True
        if self._last_underlying_mid is not None and self._last_underlying_mid > 0:
            r = abs(spot - self._last_underlying_mid) / self._last_underlying_mid
            self._recent_abs_returns.append(r)
            if len(self._recent_abs_returns) >= 50:
                # True EWMA: weight = 1 - exp(ln(0.5)/halflife), halflife
                # defaults to jump_window/2 for stable spin-up.
                import math as _math
                halflife = max(1.0, self.config.jump_window / 2.0)
                alpha = 1.0 - _math.exp(_math.log(0.5) / halflife)
                ewma_abs_r = self._recent_abs_returns[0]
                for x in list(self._recent_abs_returns)[1:]:
                    ewma_abs_r = alpha * x + (1.0 - alpha) * ewma_abs_r
                if ewma_abs_r > 0 and r / ewma_abs_r > self.config.jump_threshold:
                    # Halt for 500 ticks.
                    self._in_kill_cooldown = 500
                    self._last_underlying_mid = spot
                    return True
        self._last_underlying_mid = spot
        return False

    def _build_tags(self) -> dict[str, ProductTag]:
        group = f"options_{self.spec.underlying}"
        tags = {
            self.spec.underlying: ProductTag(
                product=self.spec.underlying,
                strategy_tag="hedger",
                arb_group=group,
            )
        }
        for voucher in self.spec.vouchers:
            tags[voucher.product] = ProductTag(
                product=voucher.product,
                strategy_tag="arb",
                arb_group=group,
                hedges_product=self.spec.underlying,
            )
        return tags
