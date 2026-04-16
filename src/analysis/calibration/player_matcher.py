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
) -> list[Fill]:
    """Phase 2: bot takers walk the combined book; player passive may fill.

    Bots have time priority at every price level (they were resting
    before the player quoted). Player passive only fills the leftover
    after bot inventory at the takers's target price is exhausted.

    A bot taker on side ``buy`` consumes asks; ``sell`` consumes bids.
    The taker's price tells which level got hit. We walk only that
    exact level, on the assumption bot trades print at the level they
    consumed (consistent with the trade-sampler's joint-offset model).
    """
    # Group player passive by (side, price) for quick lookup.
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
            # Buyer takes from ask side. Bot ask at this price has time priority.
            bot_remaining = max(depleted_ask_inv.get(taker.price, 0), 0)
            consumed_by_bot = min(taker.quantity, bot_remaining)
            depleted_ask_inv[taker.price] = bot_remaining - consumed_by_bot
            leftover = taker.quantity - consumed_by_bot
            if leftover > 0:
                player_avail = passive_asks.get(taker.price, 0)
                player_fill = min(leftover, player_avail)
                if player_fill > 0:
                    # Player was offering at this ask price → player sells.
                    fills.append(Fill(
                        timestamp=taker.timestamp,
                        product=taker.product,
                        price=taker.price,
                        quantity=-player_fill,
                        counterparty="bot_taker_passive",
                    ))
                    passive_asks[taker.price] = player_avail - player_fill
        elif taker.side == "sell":
            bot_remaining = max(depleted_bid_inv.get(taker.price, 0), 0)
            consumed_by_bot = min(taker.quantity, bot_remaining)
            depleted_bid_inv[taker.price] = bot_remaining - consumed_by_bot
            leftover = taker.quantity - consumed_by_bot
            if leftover > 0:
                player_avail = passive_bids.get(taker.price, 0)
                player_fill = min(leftover, player_avail)
                if player_fill > 0:
                    # Player was bidding at this price → player buys.
                    fills.append(Fill(
                        timestamp=taker.timestamp,
                        product=taker.product,
                        price=taker.price,
                        quantity=+player_fill,
                        counterparty="bot_taker_passive",
                    ))
                    passive_bids[taker.price] = player_avail - player_fill
    return fills


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
