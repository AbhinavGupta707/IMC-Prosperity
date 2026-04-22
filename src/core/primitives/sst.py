"""Shared Take / Clear / Make execution primitive.

Ported from the convergent pattern observed across P2/P3 top-team repos
(Linear Utility round_1_v6.py:14-310, Sylvain-Topeza, pe049395). Every
R3+ strategy builds on this scaffold instead of re-implementing quote
placement from scratch.

The primitive is a pure function: given a fair value, an order-book
snapshot, current position, and config, it returns a trading decision
(taker orders + maker quotes). No side effects. No mutable state. All
state lives on the caller side.

Three phases executed in order:

1. **Take.** Cross the spread when the opponent's best-opposite quote is
   more favorable than ``fair ± take_width``. Size is bounded by the
   opponent's displayed volume and our remaining capacity.

2. **Clear.** When inventory is ≥ ``clear_threshold`` of the position
   limit, actively seek to flatten: tighten the unwinding-side quote
   to ``fair`` (zero-edge); widen the building-side quote or suppress it.

3. **Make.** Place passive quotes at ``fair ∓ default_edge``, optionally
   joining the opponent if they're within ``join_edge``. Skews quotes
   away from the adverse-selection side when toxic prints are detected.

The primitive knows nothing about fair-value computation, signals, or
cross-product state — those are the caller's responsibility. It only
knows how to translate "fair + inventory + book" into "orders".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from src.core.types import BookLevel, ExecutionMode, NormalizedSnapshot
from src.datamodel import Order

TradingSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class SSTParams:
    """Take / Clear / Make parameters.

    All widths / edges are in *ticks* (integer price units). They must
    all be non-negative. ``disregard_edge`` and ``join_edge`` are
    sub-widths applied to the maker-quote placement decision.
    """

    # Take phase
    take_width: float = 1.0
    """Cross the spread if opponent best is beyond fair ± take_width."""

    # Clear phase
    clear_threshold: float = 0.5
    """|position| / limit >= this ⇒ active unwind mode."""

    clear_width: float = 1.0
    """In clear mode, accept fills within this edge to reduce inventory."""

    # Make phase
    default_edge: float = 2.0
    """Base maker quote offset from fair when no opponent to join."""

    disregard_edge: float = 1.0
    """Ignore opponent quotes within this edge (likely us or penny-jumpers)."""

    join_edge: float = 2.0
    """Join the opponent quote if they're within this edge of fair."""

    # Size controls
    default_quote_size: int = 20
    """Base quote size per side when not adjusted by inventory / toxicity."""

    max_taker_size: int = 30
    """Maximum size taken per cross-spread action."""

    # Adverse-selection filter (D9 in R3+ architecture)
    prevent_adverse: bool = True
    """Skew quotes away from side where recent prints are toxic (size ≤ 2)."""

    toxic_size_threshold: int = 2
    """Prints at or below this size count as toxic."""

    def __post_init__(self) -> None:
        for name, value in [
            ("take_width", self.take_width),
            ("clear_width", self.clear_width),
            ("default_edge", self.default_edge),
            ("disregard_edge", self.disregard_edge),
            ("join_edge", self.join_edge),
        ]:
            if value < 0:
                raise ValueError(f"SSTParams.{name} must be >= 0 (got {value})")
        if not 0.0 <= self.clear_threshold <= 1.0:
            raise ValueError("SSTParams.clear_threshold must be in [0, 1]")
        if self.default_quote_size <= 0:
            raise ValueError("SSTParams.default_quote_size must be > 0")
        if self.max_taker_size <= 0:
            raise ValueError("SSTParams.max_taker_size must be > 0")


@dataclass(frozen=True)
class TradingDecision:
    """Output of the SST primitive.

    Caller wraps this into a ``SignalIntent`` or emits orders directly.
    """

    product: str
    orders: list[Order] = field(default_factory=list)
    mode: ExecutionMode = "idle"
    bid_quote: tuple[int, int] | None = None  # (price, size) — for metadata
    ask_quote: tuple[int, int] | None = None
    rationale: str = ""
    metadata: dict[str, float | int | str | bool] = field(default_factory=dict)


# ============================================================= helpers


def _capacity(position: int, limit: int) -> tuple[int, int]:
    """Return (remaining_buy, remaining_sell) capacity."""
    return (max(0, limit - position), max(0, limit + position))


def _is_toxic(snapshot: NormalizedSnapshot, threshold: int) -> tuple[bool, bool]:
    """Check whether recent prints indicate adverse selection on each side.

    Returns ``(buy_side_toxic, sell_side_toxic)``. A side is toxic if
    recent market trades on that side had sizes ≤ ``threshold`` (small
    probing prints). Conservative: returns ``(False, False)`` if no
    trade tape exists.
    """
    if not snapshot.trades:
        return False, False
    # Snapshot.trades may include our own fills; we only care about market.
    market_trades = tuple(t for t in snapshot.trades if t.source == "market")
    if not market_trades:
        return False, False
    # Mid-of-best as reference for side classification.
    if snapshot.best_bid is None or snapshot.best_ask is None:
        return False, False
    mid = (snapshot.best_bid.price + snapshot.best_ask.price) / 2.0
    buy_toxic = any(
        t.quantity <= threshold and t.price > mid for t in market_trades
    )
    sell_toxic = any(
        t.quantity <= threshold and t.price < mid for t in market_trades
    )
    return buy_toxic, sell_toxic


def _pick_join_level(
    side_levels: tuple[BookLevel, ...],
    fair: float,
    disregard: float,
    join: float,
    side: TradingSide,
) -> BookLevel | None:
    """Pick an opponent level to join, or None if there's no good candidate.

    Walks the side's levels from best inward. Skips levels within
    ``disregard`` of fair (likely us or penny-jumpers). Joins the first
    level within ``join`` of fair.
    """
    for level in side_levels:
        distance = abs(level.price - fair)
        if distance <= disregard:
            continue
        if distance <= join:
            return level
        return None  # levels beyond join-edge won't be nearer on next iter
    return None


# ========================================================== primary API


def take_clear_make(
    *,
    product: str,
    fair_value: float,
    snapshot: NormalizedSnapshot,
    position: int,
    position_limit: int,
    params: SSTParams,
) -> TradingDecision:
    """Compute orders for one tick under the SST protocol.

    Pure function. No side effects. Deterministic given inputs.
    """
    if position_limit <= 0:
        raise ValueError("position_limit must be > 0")
    if fair_value <= 0:
        # Protect against zero_fallback FV. Caller should surface this
        # as a crash condition, but here we just abstain from trading.
        return TradingDecision(product=product, mode="idle", rationale="invalid_fair")

    buy_cap, sell_cap = _capacity(position, position_limit)
    pos_ratio = position / position_limit
    flattening = abs(pos_ratio) >= params.clear_threshold

    orders: list[Order] = []
    rationale_parts: list[str] = []
    meta: dict[str, float | int | str | bool] = {
        "fair_value": round(fair_value, 2),
        "position_ratio": round(pos_ratio, 4),
        "flattening": flattening,
    }

    # -------------------------------- Phase 1: TAKE
    buy_take_threshold = fair_value - params.take_width
    sell_take_threshold = fair_value + params.take_width

    # Take buy: opponent ask below buy_take_threshold.
    if snapshot.best_ask is not None and buy_cap > 0:
        if snapshot.best_ask.price <= buy_take_threshold:
            size = min(snapshot.best_ask.volume, buy_cap, params.max_taker_size)
            if size > 0:
                orders.append(Order(product, snapshot.best_ask.price, size))
                buy_cap -= size
                rationale_parts.append(f"take_buy@{snapshot.best_ask.price}x{size}")

    # Take sell: opponent bid above sell_take_threshold.
    if snapshot.best_bid is not None and sell_cap > 0:
        if snapshot.best_bid.price >= sell_take_threshold:
            size = min(snapshot.best_bid.volume, sell_cap, params.max_taker_size)
            if size > 0:
                orders.append(Order(product, snapshot.best_bid.price, -size))
                sell_cap -= size
                rationale_parts.append(f"take_sell@{snapshot.best_bid.price}x{size}")

    # -------------------------------- Phase 2: CLEAR
    if flattening:
        if position > 0 and sell_cap > 0:
            # Long inventory — actively unwind at fair.
            clear_price = int(math.ceil(fair_value - params.clear_width))
            # Only clear if the price is reachable by matching opponent bid.
            if snapshot.best_bid is not None and clear_price <= snapshot.best_bid.price:
                size = min(position, sell_cap, params.max_taker_size)
                if size > 0:
                    orders.append(Order(product, snapshot.best_bid.price, -size))
                    sell_cap -= size
                    rationale_parts.append(f"clear_sell@{snapshot.best_bid.price}x{size}")
        elif position < 0 and buy_cap > 0:
            # Short inventory — actively cover at fair.
            clear_price = int(math.floor(fair_value + params.clear_width))
            if snapshot.best_ask is not None and clear_price >= snapshot.best_ask.price:
                size = min(-position, buy_cap, params.max_taker_size)
                if size > 0:
                    orders.append(Order(product, snapshot.best_ask.price, size))
                    buy_cap -= size
                    rationale_parts.append(f"clear_buy@{snapshot.best_ask.price}x{size}")

    # -------------------------------- Phase 3: MAKE
    # Detect toxic flow.
    buy_toxic, sell_toxic = (False, False)
    if params.prevent_adverse:
        buy_toxic, sell_toxic = _is_toxic(snapshot, params.toxic_size_threshold)
        meta["buy_toxic"] = buy_toxic
        meta["sell_toxic"] = sell_toxic

    bid_quote: tuple[int, int] | None = None
    ask_quote: tuple[int, int] | None = None

    # Decide maker bid price.
    if buy_cap > 0 and not (flattening and position > 0):
        bid_price = int(math.floor(fair_value - params.default_edge))
        join = _pick_join_level(
            snapshot.bids, fair_value, params.disregard_edge, params.join_edge, "buy",
        )
        if join is not None:
            # Join by placing at the same price (or inside if allowed).
            bid_price = max(bid_price, join.price)
        # Widen if buy side is toxic.
        if buy_toxic:
            bid_price -= 1
        # Don't cross the spread.
        if snapshot.best_ask is not None:
            bid_price = min(bid_price, snapshot.best_ask.price - 1)
        bid_size = min(params.default_quote_size, buy_cap)
        # In clear mode with long position, suppress bid entirely.
        if flattening and position > 0:
            bid_size = 0
        if bid_size > 0 and bid_price > 0:
            orders.append(Order(product, bid_price, bid_size))
            bid_quote = (bid_price, bid_size)
            rationale_parts.append(f"make_bid@{bid_price}x{bid_size}")

    # Decide maker ask price.
    if sell_cap > 0 and not (flattening and position < 0):
        ask_price = int(math.ceil(fair_value + params.default_edge))
        join = _pick_join_level(
            snapshot.asks, fair_value, params.disregard_edge, params.join_edge, "sell",
        )
        if join is not None:
            ask_price = min(ask_price, join.price)
        if sell_toxic:
            ask_price += 1
        if snapshot.best_bid is not None:
            ask_price = max(ask_price, snapshot.best_bid.price + 1)
        ask_size = min(params.default_quote_size, sell_cap)
        if flattening and position < 0:
            ask_size = 0
        if ask_size > 0 and ask_price > 0:
            orders.append(Order(product, ask_price, -ask_size))
            ask_quote = (ask_price, ask_size)
            rationale_parts.append(f"make_ask@{ask_price}x{ask_size}")

    # -------------------------------- Assemble decision
    if not orders:
        mode: ExecutionMode = "idle"
    elif flattening:
        mode = "recovery"
    elif any("take" in r for r in rationale_parts):
        mode = "hybrid"
    else:
        mode = "maker"

    return TradingDecision(
        product=product,
        orders=orders,
        mode=mode,
        bid_quote=bid_quote,
        ask_quote=ask_quote,
        rationale=";".join(rationale_parts) if rationale_parts else "idle",
        metadata=meta,
    )
