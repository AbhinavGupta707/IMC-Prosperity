"""Tests for player_matcher: aggressive crossing + passive fill priority."""
from __future__ import annotations

from src.analysis.calibration.player_matcher import (
    PlayerOrder, apply_fills_to_account,
    match_aggressive_orders, match_bot_taker_trades,
)
from src.analysis.calibration.trade_sampler import SyntheticTrade
from src.analysis.calibration.types import BookLevel


def _bid(price: int, vol: int) -> BookLevel:
    return BookLevel(price=price, volume=vol)


def _ask(price: int, vol: int) -> BookLevel:
    return BookLevel(price=price, volume=vol)


# ---------------------------------------------------------- aggressive matching


def test_aggressive_buy_crosses_lowest_ask_first():
    fills, unfilled, bid_inv, ask_inv = match_aggressive_orders(
        timestamp=100,
        player_orders=[PlayerOrder(product="P", price=5005, quantity=3)],
        bot_bids=(_bid(4995, 10),),
        bot_asks=(_ask(5002, 5), _ask(5004, 8)),
    )
    assert len(fills) == 1
    assert fills[0].price == 5002
    assert fills[0].quantity == 3
    assert ask_inv[5002] == 2  # 5 - 3 remaining
    assert not unfilled


def test_aggressive_buy_walks_multiple_levels():
    fills, unfilled, _, ask_inv = match_aggressive_orders(
        timestamp=100,
        player_orders=[PlayerOrder(product="P", price=5006, quantity=10)],
        bot_bids=(),
        bot_asks=(_ask(5002, 4), _ask(5004, 8)),
    )
    assert len(fills) == 2
    assert fills[0].price == 5002 and fills[0].quantity == 4
    assert fills[1].price == 5004 and fills[1].quantity == 6
    assert ask_inv[5002] == 0
    assert ask_inv[5004] == 2


def test_aggressive_buy_unfilled_at_too_low_price():
    fills, unfilled, _, ask_inv = match_aggressive_orders(
        timestamp=100,
        player_orders=[PlayerOrder(product="P", price=5001, quantity=5)],
        bot_bids=(),
        bot_asks=(_ask(5002, 10),),
    )
    assert fills == []
    assert len(unfilled) == 1
    assert unfilled[0].quantity == 5
    # Ask inventory not consumed.
    assert ask_inv[5002] == 10


def test_aggressive_sell_crosses_highest_bid_first():
    fills, unfilled, bid_inv, _ = match_aggressive_orders(
        timestamp=100,
        player_orders=[PlayerOrder(product="P", price=4995, quantity=-3)],
        bot_bids=(_bid(4998, 4), _bid(4995, 10)),
        bot_asks=(),
    )
    assert len(fills) == 1
    assert fills[0].price == 4998
    assert fills[0].quantity == -3
    assert bid_inv[4998] == 1  # 4 - 3
    assert bid_inv[4995] == 10  # untouched


def test_aggressive_partial_fill_remainder_unfilled():
    """Player buys 10 but only 6 available at his price → 6 fill, 4 unfilled."""
    fills, unfilled, _, _ = match_aggressive_orders(
        timestamp=100,
        player_orders=[PlayerOrder(product="P", price=5003, quantity=10)],
        bot_bids=(),
        bot_asks=(_ask(5002, 4), _ask(5005, 100)),  # 5005 above player price
    )
    assert len(fills) == 1
    assert fills[0].quantity == 4
    assert len(unfilled) == 1
    assert unfilled[0].quantity == 6


# ---------------------------------------------------------- bot-taker matching


def test_bot_taker_buy_consumes_bot_ask_first_then_player_passive():
    """Bot taker buys 5 at price 5002. Bot has 3 remaining; player has 4 passive."""
    fills = match_bot_taker_trades(
        bot_takers=[SyntheticTrade(
            timestamp=100, product="P", price=5002, quantity=5, side="buy",
        )],
        player_passive=[PlayerOrder(product="P", price=5002, quantity=-4)],
        depleted_bid_inv={},
        depleted_ask_inv={5002: 3},
    )
    assert len(fills) == 1  # one player fill (after bot priority)
    assert fills[0].price == 5002
    assert fills[0].quantity == -2  # 5 - 3 (bot) = 2 player ask filled


def test_bot_taker_buy_no_player_passive_at_price_no_fill():
    fills = match_bot_taker_trades(
        bot_takers=[SyntheticTrade(
            timestamp=100, product="P", price=5002, quantity=5, side="buy",
        )],
        player_passive=[],
        depleted_bid_inv={},
        depleted_ask_inv={5002: 100},  # plenty of bot inventory
    )
    assert fills == []


def test_bot_taker_sell_consumes_bot_bid_first_then_player_passive():
    fills = match_bot_taker_trades(
        bot_takers=[SyntheticTrade(
            timestamp=100, product="P", price=4998, quantity=8, side="sell",
        )],
        player_passive=[PlayerOrder(product="P", price=4998, quantity=+6)],
        depleted_bid_inv={4998: 4},
        depleted_ask_inv={},
    )
    assert len(fills) == 1
    assert fills[0].price == 4998
    assert fills[0].quantity == +4  # 8 - 4 = 4 to player bid


def test_bot_taker_buy_bot_inventory_exceeds_taker_size():
    fills = match_bot_taker_trades(
        bot_takers=[SyntheticTrade(
            timestamp=100, product="P", price=5002, quantity=5, side="buy",
        )],
        player_passive=[PlayerOrder(product="P", price=5002, quantity=-10)],
        depleted_bid_inv={},
        depleted_ask_inv={5002: 100},  # bots fill entire taker; player gets 0
    )
    assert fills == []


def test_bot_taker_player_priority_mode_fills_player_first():
    """priority_mode='player': player passive fills BEFORE bot inventory.

    Bot taker buys 5 at price 5002. Bot has 100 ask inventory; player
    has 3 passive. Under bot priority, bot would fill all 5 → player 0.
    Under player priority, player fills 3 first, then bot fills 2.
    """
    fills = match_bot_taker_trades(
        bot_takers=[SyntheticTrade(
            timestamp=100, product="P", price=5002, quantity=5, side="buy",
        )],
        player_passive=[PlayerOrder(product="P", price=5002, quantity=-3)],
        depleted_bid_inv={},
        depleted_ask_inv={5002: 100},
        priority_mode="player",
    )
    assert len(fills) == 1
    assert fills[0].quantity == -3  # player filled all 3 ahead of bot


def test_bot_taker_split_mode_distributes_proportionally():
    """priority_mode='split': fills distribute by standing volume share.

    Bot taker buys 10 at price 5002. Bot has 30 ask, player has 10
    passive. Player fills 10*10/(30+10) = 2; bot fills 10-2 = 8.
    """
    fills = match_bot_taker_trades(
        bot_takers=[SyntheticTrade(
            timestamp=100, product="P", price=5002, quantity=10, side="buy",
        )],
        player_passive=[PlayerOrder(product="P", price=5002, quantity=-10)],
        depleted_bid_inv={},
        depleted_ask_inv={5002: 30},
        priority_mode="split",
    )
    assert len(fills) == 1
    # Player gets 2 (from the proportional formula)
    assert fills[0].quantity == -2


def test_bot_taker_invalid_priority_mode_raises():
    with pytest.raises(ValueError, match="priority_mode must be"):
        match_bot_taker_trades(
            bot_takers=[],
            player_passive=[],
            depleted_bid_inv={},
            depleted_ask_inv={},
            priority_mode="invalid",
        )


def test_bot_taker_caps_player_fill_at_player_passive_size():
    """Bot inventory 0, taker size 10, player passive only 3 → player fills 3."""
    fills = match_bot_taker_trades(
        bot_takers=[SyntheticTrade(
            timestamp=100, product="P", price=5002, quantity=10, side="buy",
        )],
        player_passive=[PlayerOrder(product="P", price=5002, quantity=-3)],
        depleted_bid_inv={},
        depleted_ask_inv={5002: 0},
    )
    assert len(fills) == 1
    assert fills[0].quantity == -3


def test_bot_taker_unknown_side_skipped():
    fills = match_bot_taker_trades(
        bot_takers=[SyntheticTrade(
            timestamp=100, product="P", price=5002, quantity=5, side="unknown",
        )],
        player_passive=[PlayerOrder(product="P", price=5002, quantity=-10)],
        depleted_bid_inv={},
        depleted_ask_inv={5002: 0},
    )
    assert fills == []


# ---------------------------------------------------------- account aggregation


def test_apply_fills_buys_decrease_cash_increase_position():
    from src.analysis.calibration.player_matcher import Fill

    fills = [
        Fill(timestamp=100, product="P", price=5000, quantity=+3, counterparty="x"),
        Fill(timestamp=100, product="P", price=5005, quantity=-2, counterparty="x"),
    ]
    cash_delta, pos_delta = apply_fills_to_account(fills)
    # Buy 3 @ 5000 = -15000 cash, +3 position
    # Sell 2 @ 5005 = +10010 cash, -2 position
    # Net: cash = -15000 + 10010 = -4990; position = +1
    assert cash_delta == pytest.approx(-4990) if False else cash_delta == -4990
    assert pos_delta == 1


# small import workaround for pytest.approx-free assertion
import pytest  # noqa: E402
