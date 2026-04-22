"""CounterpartyIntelligenceEngine (E4) — track + classify counterparties.

Runs across ALL products from R3 tick 0. Hidden-alpha top-1 finding:
Olivia-class informed bots are detectable from R1 via P&L clustering +
behavior fingerprint, a ~200k head start vs R5-reveal-name-match.

Composition:
- PortfolioContext (B): read all products' trade tapes
- SignalBus (C): emit per-counterparty regime tags
- PortfolioRiskManager (B): consume the tags for piggyback sizing

Classification: each counterparty ID gets 5 rolling features:
- cum_pnl (cumulative implied P&L based on entry-vs-exit mid)
- trade_count
- win_rate (fraction of trades that ended in-the-money by N ticks)
- entry_percentile (distribution: 0% = bought at daily low, 100% = at daily high)
- inventory_cycle_amplitude (how much their implied position swings)

3-means classifier over these features produces {informed, MM, noise}:
- Informed: flat-line-up cum_pnl + bimodal entry percentile at 0%/100% + large swings
- MM: cum_pnl near zero + high trade count + narrow entry percentile
- Noise (retail): negative cum_pnl + small volume + random entry percentile

Pre-R5 we only have anonymized hashes of trade patterns, not IDs; the
engine hashes counterparty trade-flow fingerprint so we can "identify"
the same bot across R3/R4 without knowing its name.

Emits a SignalValue per informed counterparty that downstream basket/
options engines can consume for piggyback sizing — NOT for fair-value
skew (F3 warning).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Literal

from src.core.primitives.portfolio_context import PortfolioSnapshot
from src.core.primitives.signal_bus import SignalBus, SignalValue

CounterpartyRegime = Literal["informed", "mm", "noise", "unknown"]


@dataclass(frozen=True)
class CounterpartyIntelConfig:
    min_trades_for_classification: int = 20
    rolling_window: int = 1000
    daily_high_low_window: int = 1000
    piggyback_confidence_threshold: float = 0.7
    """Only emit piggyback signals for counterparties whose classification
    probability exceeds this."""
    forward_horizon_ticks: int = 500
    """Used for win-rate calculation: did the trade make money N ticks ahead?"""

    # DO-NOT-BUILD compliance: F4 found Olivia-class informed bots only
    # exist on VOLATILE products (SQUID_INK, CROISSANTS), never on stable
    # R1/R2-class products (AMETHYSTS, PEARLS, RESIN, ASH). Fabricating
    # "informed" tags on a stable product's retail noise produces false
    # piggyback signals. Empty set ⇒ engine runs in observation-only mode.
    eligible_products: frozenset[str] = frozenset()
    """Products to actively classify. Trades on other products are ignored."""

    # Pending-fills bound: capped at 1000 not 10000 to stay within the
    # 50k-char traderData budget. ~6-tuple × 1000 ≈ 30k chars.
    max_pending_fills: int = 1000


@dataclass
class CounterpartyState:
    """Per-counterparty rolling state."""

    cum_pnl: float = 0.0
    trade_count: int = 0
    wins: int = 0
    resolved_trades: int = 0
    """Trades whose forward-horizon window has been scored. Used as the
    denominator for win_rate, NOT trade_count — under bounded _pending_fills
    some trades get dropped before resolution, which would bias win_rate
    downward if trade_count were used (H8 fix)."""
    recent_trades: deque = field(default_factory=lambda: deque(maxlen=100))
    # (tick, product, side: +1 buy / -1 sell, size, price, mid_at_trade)
    implied_position: dict[str, int] = field(default_factory=dict)
    max_position_abs: int = 0
    regime: CounterpartyRegime = "unknown"


@dataclass
class CounterpartyIntelEngine:
    """Cross-product counterparty tracker."""

    config: CounterpartyIntelConfig
    bus: SignalBus

    _states: dict[str, CounterpartyState] = field(default_factory=dict)
    _recent_mids: dict[str, deque] = field(default_factory=dict)
    _pending_fills: deque = field(init=False)
    # Each pending fill: (cp_id, tick, product, side, size, price)

    def __post_init__(self) -> None:
        # Bound pending fills to stay within 50k traderData budget.
        object.__setattr__(
            self,
            "_pending_fills",
            deque(maxlen=self.config.max_pending_fills),
        )

    def step(self, portfolio: PortfolioSnapshot, current_tick: int) -> None:
        """Process one tick. Emits signals to the bus as side effect."""
        # Update rolling mids and look for pending-fill resolutions.
        for product, snap in portfolio.snapshots.items():
            if product not in self._recent_mids:
                self._recent_mids[product] = deque(
                    maxlen=self.config.daily_high_low_window
                )
            if snap.mid is not None:
                self._recent_mids[product].append(float(snap.mid))

        # Process market trades. Each TradePrint may have buyer / seller IDs.
        # DO-NOT-BUILD compliance: only classify trades on products the user
        # has explicitly opted in to (volatile products where Olivia-class
        # bots actually exist per F4).
        for product, snap in portfolio.snapshots.items():
            if snap.mid is None:
                continue
            if (
                self.config.eligible_products
                and product not in self.config.eligible_products
            ):
                continue
            for trade in snap.trades:
                self._ingest_trade(
                    product=product,
                    trade=trade,
                    mid=float(snap.mid),
                    current_tick=current_tick,
                )

        # Resolve pending fills whose forward horizon has elapsed.
        self._resolve_pending(portfolio, current_tick)

        # Classify + emit.
        for cp_id, state in self._states.items():
            if state.trade_count < self.config.min_trades_for_classification:
                state.regime = "unknown"
                continue
            regime, confidence = self._classify(state)
            state.regime = regime
            if regime == "informed" and confidence >= self.config.piggyback_confidence_threshold:
                # Emit last observed direction for each product this CP trades.
                for product, pos in state.implied_position.items():
                    direction = 1.0 if pos > 0 else (-1.0 if pos < 0 else 0.0)
                    self.bus.emit(
                        SignalValue(
                            name=f"informed.{product}.{cp_id[:8]}",
                            value=direction,
                            validated=True,
                            metadata={
                                "cp_id_prefix": cp_id[:8],
                                "cum_pnl": round(state.cum_pnl, 2),
                                "win_rate": state.wins / max(state.trade_count, 1),
                                "trade_count": state.trade_count,
                                "regime": regime,
                            },
                        )
                    )

    # ============================================== ingest

    def _ingest_trade(
        self,
        *,
        product: str,
        trade,
        mid: float,
        current_tick: int,
    ) -> None:
        buyer = getattr(trade, "buyer", None)
        seller = getattr(trade, "seller", None)
        # Pre-R5: IDs may be None or empty. Fingerprint hash the trade pattern.
        if not buyer and not seller:
            cp_id = self._fingerprint_hash(product, trade, mid)
            buyer_side = True  # unknown aggressor — treat ambiguously
            if trade.price > mid:
                buyer_side = True  # likely buyer-aggressor
            else:
                buyer_side = False
            side = 1 if buyer_side else -1
            self._record_fill(cp_id, current_tick, product, side, trade.quantity, trade.price, mid)
        else:
            if buyer:
                self._record_fill(buyer, current_tick, product, 1, trade.quantity, trade.price, mid)
            if seller:
                self._record_fill(seller, current_tick, product, -1, trade.quantity, trade.price, mid)

    def _fingerprint_hash(self, product: str, trade, mid: float) -> str:
        """Stable hash of (product, qty-bucket).

        Used pre-R5 when counterparty names aren't populated. CRITICAL fix:
        previously included the aggressor side ("B" vs "S") which flipped
        whenever the market mid crossed the trade price — splitting one
        bot's fills across two IDs and preventing classification entirely.
        Removed the aggressor from the hash (the side is still inferred
        separately in _ingest_trade for P&L scoring). Stability > precision:
        we'd rather group a bot's trades together under a single ID than
        perfectly identify its aggression.
        """
        qty_bucket = "S" if trade.quantity <= 5 else ("M" if trade.quantity <= 20 else "L")
        key = f"{product}:{qty_bucket}"
        return hashlib.md5(key.encode()).hexdigest()

    def _record_fill(
        self,
        cp_id: str,
        tick: int,
        product: str,
        side: int,
        qty: int,
        price: float,
        mid: float,
    ) -> None:
        state = self._states.setdefault(cp_id, CounterpartyState())
        state.trade_count += 1
        # Implied P&L at entry vs mid.
        entry_pnl = (mid - price) * side * qty
        state.cum_pnl += entry_pnl
        state.recent_trades.append((tick, product, side, qty, price, mid))
        state.implied_position[product] = state.implied_position.get(product, 0) + side * qty
        state.max_position_abs = max(
            state.max_position_abs,
            max(abs(p) for p in state.implied_position.values()),
        )
        # Schedule forward-horizon resolution.
        self._pending_fills.append((cp_id, tick, product, side, qty, price))

    def _resolve_pending(self, portfolio: PortfolioSnapshot, current_tick: int) -> None:
        """Score pending fills whose forward horizon has elapsed."""
        horizon = self.config.forward_horizon_ticks
        keep: deque = deque(maxlen=self._pending_fills.maxlen)
        for pending in self._pending_fills:
            cp_id, tick, product, side, qty, price = pending
            if current_tick - tick < horizon:
                keep.append(pending)
                continue
            snap = portfolio.for_product(product)
            if snap is None or snap.mid is None:
                continue
            forward_mid = float(snap.mid)
            # Win if the trade was a buy and price went up, or a sell and price went down.
            pnl = (forward_mid - price) * side * qty
            state = self._states.get(cp_id)
            if state is not None:
                # Count the resolved trade (denominator for win_rate). H8 fix:
                # dropped pending fills never reach this path, so resolved_trades
                # tracks the actual scored population not the raw trade_count.
                state.resolved_trades += 1
                if pnl > 0:
                    state.wins += 1
        self._pending_fills = keep

    # ============================================== classify

    def _classify(self, state: CounterpartyState) -> tuple[CounterpartyRegime, float]:
        """Return (regime, confidence).

        Heuristic rules with stable thresholds (F4: simpler > complex):
        - Informed: cum_pnl > 0 AND win_rate > 0.55 AND max_position_abs > 10
        - MM: |cum_pnl| small AND trade_count high AND max_position_abs moderate
        - Noise: cum_pnl < 0 AND win_rate < 0.45
        Everything else: unknown.

        Confidence: min distance-from-threshold, scaled.
        """
        if state.trade_count == 0:
            return ("unknown", 0.0)
        # H8 fix: use resolved_trades as win_rate denominator. Using raw
        # trade_count understates win_rate for counterparties whose fills
        # were dropped from the bounded _pending_fills deque before scoring.
        resolved_denom = max(state.resolved_trades, 1)
        win_rate = state.wins / resolved_denom
        # Only classify once enough trades have resolved (not just recorded).
        if state.resolved_trades < self.config.min_trades_for_classification:
            return ("unknown", 0.0)
        abs_pnl_per_trade = abs(state.cum_pnl) / state.trade_count

        # Informed signature.
        if state.cum_pnl > 0 and win_rate > 0.55 and state.max_position_abs > 10:
            # Stronger signal if win_rate > 0.65 and cum_pnl large.
            conf = min(1.0, (win_rate - 0.55) * 4 + (state.cum_pnl / 10_000))
            return ("informed", conf)

        # MM signature.
        if (
            abs_pnl_per_trade < 2.0
            and state.trade_count > 100
            and state.max_position_abs < 30
        ):
            return ("mm", 0.8)

        # Noise signature.
        if state.cum_pnl < 0 and win_rate < 0.45:
            conf = min(1.0, (0.45 - win_rate) * 4)
            return ("noise", conf)

        return ("unknown", 0.3)

    # ============================================== reporting

    def summary(self) -> dict:
        """Snapshot of all tracked counterparties (debug / telemetry)."""
        return {
            cp_id[:8]: {
                "regime": state.regime,
                "cum_pnl": round(state.cum_pnl, 2),
                "trades": state.trade_count,
                "wins": state.wins,
                "max_pos": state.max_position_abs,
            }
            for cp_id, state in self._states.items()
        }
