"""Match player orders against bot quotes + bot taker trades.

Two phases per tick:

  Phase 1 - Player aggressive orders cross the bot book.
    For each player order whose price crosses the visible bot book,
    fill against bot inventory in price priority. Update player cash
    and position. Unfilled remainder becomes a passive resting order.

  Phase 2 - Bot takers walk the combined book.
    For each synthetic trade emitted by the trade_sampler, walk the
    combined (bot + player passive) book. Bots have time priority
    at the same price (they were resting before player orders arrived
    this tick), so player passive only fills the leftover after bot
    inventory at that price level is exhausted.

Player passive orders DO NOT persist across ticks. Every tick the
player must re-quote — same as IMC Prosperity semantics.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.analysis.calibration.trade_sampler import SyntheticTrade
from src.analysis.calibration.types import BookLevel


@dataclass(frozen=True)
class PlayerOrder:
    """A player order to match this tick.

    ``quantity`` is signed: positive = buy, negative = sell. The book
    is interpreted with this convention throughout matching.
    """

    product: str
    price: int
    quantity: int  # +ve = buy, -ve = sell


@dataclass(frozen=True)
class Fill:
    """One executed fill (player perspective)."""

    timestamp: int
    product: str
    price: int
    quantity: int  # signed: +ve = player bought, -ve = player sold
    counterparty: str  # "bot_aggressive", "bot_taker_passive"


@dataclass(frozen=True)
class TickMatchResult:
    """Outcome of matching one tick's player orders + bot takers."""

    fills: tuple[Fill, ...]
    cash_delta: float  # player cash change this tick (signed)
    position_delta: int  # player position change this tick (signed)
    unfilled_passive: tuple[PlayerOrder, ...]  # informational; cleared at tick end


def match_aggressive_orders(
    *,
    timestamp: int,
    player_orders: Iterable[PlayerOrder],
    bot_bids: tuple[BookLevel, ...],
    bot_asks: tuple[BookLevel, ...],
) -> tuple[list[Fill], list[PlayerOrder], dict[int, int], dict[int, int]]:
    """Phase 1: cross player orders against bot book.

    Returns:
        - fills: list[Fill] for filled portions
        - unfilled_orders: player orders (or remainders) that didn't cross
        - depleted_bid_levels: dict[price -> remaining volume after consumption]
        - depleted_ask_levels: dict[price -> remaining volume]
    """
    # Mutable copies of book inventory (bot side).
    bid_inv = {lvl.price: lvl.volume for lvl in bot_bids}
    ask_inv = {lvl.price: lvl.volume for lvl in bot_asks}

    fills: list[Fill] = []
    unfilled: list[PlayerOrder] = []

    for order in player_orders:
        if order.quantity == 0:
            continue
        if order.quantity > 0:
            # Player buying: walk asks at <= order.price, ascending.
            remaining = order.quantity
            for ask_price in sorted(p for p in ask_inv if p <= order.price):
                available = ask_inv[ask_price]
                if available <= 0:
                    continue
                take = min(remaining, available)
                fills.append(Fill(
                    timestamp=timestamp, product=order.product,
                    price=ask_price, quantity=take,
                    counterparty="bot_aggressive",
                ))
                ask_inv[ask_price] = available - take
                remaining -= take
                if remaining <= 0:
                    break
            if remaining > 0:
                unfilled.append(PlayerOrder(
                    product=order.product, price=order.price,
                    quantity=remaining,
                ))
        else:
            # Player selling: walk bids at >= order.price, descending.
            remaining = -order.quantity  # positive size
            for bid_price in sorted((p for p in bid_inv if p >= order.price), reverse=True):
                available = bid_inv[bid_price]
                if available <= 0:
                    continue
                take = min(remaining, available)
                fills.append(Fill(
                    timestamp=timestamp, product=order.product,
                    price=bid_price, quantity=-take,
                    counterparty="bot_aggressive",
                ))
                bid_inv[bid_price] = available - take
                remaining -= take
                if remaining <= 0:
                    break
            if remaining > 0:
                unfilled.append(PlayerOrder(
                    product=order.product, price=order.price,
                    quantity=-remaining,
                ))
    return fills, unfilled, bid_inv, ask_inv


def match_bot_taker_trades(
    *,
    bot_takers: Iterable[SyntheticTrade],
    player_passive: Iterable[PlayerOrder],
    depleted_bid_inv: dict[int, int],
    depleted_ask_inv: dict[int, int],
    priority_mode: str = "bot",
) -> list[Fill]:
    """Phase 2: bot takers walk the combined book; player passive may fill.

    ``priority_mode`` controls the queue priority at each price level:

      "bot" (default): bots have time priority. They were resting
        before the player quoted, so they fill first at any price
        level. Player passive only fills the leftover after bot
        inventory at that price is exhausted. This is the conservative
        model and is the one used for the headline F3a / cohort
        verdicts.

      "player": the alternative. Player passive at a price level fills
        FIRST, before any bot inventory at the same price. Models the
        case where the player can preempt bot quotes (e.g., because
        IMC's matching engine batches order arrival within a tick and
        gives the LATEST order priority). This is generally
        unrealistic but useful as a stress test: if a strategy's MC
        verdict reverses sign under "player" priority, the bot-
        priority result is matching-model-sensitive and should not be
        treated as definitive. Used to test whether the wall_mid kill
        verdict is bot-priority-biased.

      "split": each side fills proportionally to its standing volume
        at the price level. Compromise; not currently used but
        available for completeness.
    """
    if priority_mode not in ("bot", "player", "split"):
        raise ValueError(
            f"priority_mode must be 'bot' / 'player' / 'split'; got {priority_mode!r}"
        )

    passive_bids: dict[int, int] = {}
    passive_asks: dict[int, int] = {}
    for order in player_passive:
        if order.quantity > 0:
            passive_bids[order.price] = passive_bids.get(order.price, 0) + order.quantity
        elif order.quantity < 0:
            passive_asks[order.price] = passive_asks.get(order.price, 0) + (-order.quantity)

    fills: list[Fill] = []
    for taker in bot_takers:
        if taker.side == "buy":
            bot_avail = max(depleted_ask_inv.get(taker.price, 0), 0)
            player_avail = passive_asks.get(taker.price, 0)
            player_fill, bot_consumed = _split_taker_fill(
                taker_qty=taker.quantity,
                bot_avail=bot_avail, player_avail=player_avail,
                priority_mode=priority_mode,
            )
            depleted_ask_inv[taker.price] = bot_avail - bot_consumed
            if player_fill > 0:
                fills.append(Fill(
                    timestamp=taker.timestamp, product=taker.product,
                    price=taker.price, quantity=-player_fill,
                    counterparty="bot_taker_passive",
                ))
                passive_asks[taker.price] = player_avail - player_fill
        elif taker.side == "sell":
            bot_avail = max(depleted_bid_inv.get(taker.price, 0), 0)
            player_avail = passive_bids.get(taker.price, 0)
            player_fill, bot_consumed = _split_taker_fill(
                taker_qty=taker.quantity,
                bot_avail=bot_avail, player_avail=player_avail,
                priority_mode=priority_mode,
            )
            depleted_bid_inv[taker.price] = bot_avail - bot_consumed
            if player_fill > 0:
                fills.append(Fill(
                    timestamp=taker.timestamp, product=taker.product,
                    price=taker.price, quantity=+player_fill,
                    counterparty="bot_taker_passive",
                ))
                passive_bids[taker.price] = player_avail - player_fill
    return fills


def _split_taker_fill(
    *, taker_qty: int, bot_avail: int, player_avail: int,
    priority_mode: str,
) -> tuple[int, int]:
    """Compute (player_fill, bot_consumed) for one taker hitting a level.

    Returns a tuple where:
      - player_fill: quantity that fills against player passive
      - bot_consumed: quantity consumed from bot inventory at this level

    Both are non-negative; their sum is bounded by min(taker_qty,
    bot_avail + player_avail).
    """
    if taker_qty <= 0:
        return (0, 0)
    if priority_mode == "bot":
        bot_consumed = min(taker_qty, bot_avail)
        leftover = taker_qty - bot_consumed
        player_fill = min(leftover, player_avail)
        return (player_fill, bot_consumed)
    if priority_mode == "player":
        player_fill = min(taker_qty, player_avail)
        leftover = taker_qty - player_fill
        bot_consumed = min(leftover, bot_avail)
        return (player_fill, bot_consumed)
    # priority_mode == "split"
    total_avail = bot_avail + player_avail
    if total_avail == 0:
        return (0, 0)
    fillable = min(taker_qty, total_avail)
    # Proportional split by standing volume.
    player_fill = (fillable * player_avail) // total_avail
    bot_consumed = fillable - player_fill
    return (player_fill, bot_consumed)


def apply_fills_to_account(
    fills: Iterable[Fill],
) -> tuple[float, int]:
    """Aggregate signed fills into (cash_delta, position_delta).

    Buying: cash decreases by price * size, position increases by size.
    Selling: cash increases by price * size, position decreases.
    """
    cash_delta = 0.0
    position_delta = 0
    for f in fills:
        # f.quantity signed; +ve buy (cash out), -ve sell (cash in)
        cash_delta -= f.price * f.quantity
        position_delta += f.quantity
    return cash_delta, position_delta
