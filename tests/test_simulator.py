"""End-to-end tests for ``src.backtest.simulator.BacktestSimulator``.

These drive a real ``Trader`` against a tiny hand-built replay stream
so we can assert on PnL, position, and trade accounting.
"""

from __future__ import annotations

import pytest

from src.backtest.fill_model import FillModel
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config import EngineConfig, ProductConfig
from src.datamodel import Order, TradingState
from src.trader import Trader


class _ScriptedTrader:
    """Test double that returns a pre-baked sequence of orders."""

    def __init__(self, scripted: list[dict[str, list[Order]]]) -> None:
        self._scripted = scripted
        self._index = 0

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        orders = self._scripted[self._index] if self._index < len(self._scripted) else {}
        self._index += 1
        return orders, 0, ""


def _row(
    timestamp: int, product: str, bid: int, bid_vol: int, ask: int, ask_vol: int
) -> dict[str, str]:
    return {
        "day": "-1",
        "timestamp": str(timestamp),
        "product": product,
        "bid_price_1": str(bid),
        "bid_volume_1": str(bid_vol),
        "bid_price_2": "",
        "bid_volume_2": "",
        "bid_price_3": "",
        "bid_volume_3": "",
        "ask_price_1": str(ask),
        "ask_volume_1": str(ask_vol),
        "ask_price_2": "",
        "ask_volume_2": "",
        "ask_price_3": "",
        "ask_volume_3": "",
        "mid_price": str((bid + ask) / 2),
        "profit_and_loss": "0.0",
    }


@pytest.mark.integration
def test_simulator_produces_zero_pnl_on_empty_orders() -> None:
    replay = ReplayEngine(
        [ReplayStep(day=-1, timestamp=0, rows_by_product={"P": _row(0, "P", 99, 5, 101, 5)})]
    )
    simulator = BacktestSimulator(trader=_ScriptedTrader([{}]))  # type: ignore[arg-type]
    result = simulator.run(replay)
    assert result.steps == 1
    assert result.total_pnl == 0.0
    # The simulator records accounting for every product seen in the
    # replay book so zero-trade products still show up in the report.
    product = result.per_product["P"]
    assert product.trade_count == 0
    assert product.final_position == 0
    assert product.cash == 0.0
    assert product.pnl == 0.0


@pytest.mark.integration
def test_simulator_records_a_taker_buy_and_mtm_profit() -> None:
    steps = [
        ReplayStep(day=-1, timestamp=0, rows_by_product={"P": _row(0, "P", 99, 5, 101, 5)}),
        ReplayStep(day=-1, timestamp=1, rows_by_product={"P": _row(1, "P", 103, 5, 105, 5)}),
    ]
    replay = ReplayEngine(steps)

    scripted = [
        {"P": [Order("P", 101, 2)]},  # buy 2 @ 101
        {"P": []},
    ]
    simulator = BacktestSimulator(trader=_ScriptedTrader(scripted))  # type: ignore[arg-type]

    result = simulator.run(replay)
    product = result.per_product["P"]
    assert product.final_position == 2
    assert product.trade_count == 1
    assert product.buy_trade_quantity == 2
    assert product.sell_trade_quantity == 0
    assert product.cash == pytest.approx(-202.0)
    # mark-to-market at last mid 104, position 2 -> +208
    assert product.pnl == pytest.approx(6.0)
    assert result.total_pnl == pytest.approx(6.0)


@pytest.mark.integration
def test_simulator_records_a_taker_sell_and_round_trip() -> None:
    steps = [
        ReplayStep(day=-1, timestamp=0, rows_by_product={"P": _row(0, "P", 99, 5, 101, 5)}),
        ReplayStep(day=-1, timestamp=1, rows_by_product={"P": _row(1, "P", 103, 5, 105, 5)}),
        ReplayStep(day=-1, timestamp=2, rows_by_product={"P": _row(2, "P", 99, 5, 101, 5)}),
    ]
    replay = ReplayEngine(steps)
    scripted = [
        {"P": [Order("P", 101, 1)]},  # buy 1 @ 101
        {"P": [Order("P", 103, -1)]},  # sell 1 @ 103
        {"P": []},
    ]
    simulator = BacktestSimulator(trader=_ScriptedTrader(scripted))  # type: ignore[arg-type]

    result = simulator.run(replay)
    product = result.per_product["P"]
    assert product.final_position == 0
    assert product.trade_count == 2
    assert product.cash == pytest.approx(2.0)
    assert product.pnl == pytest.approx(2.0)
    assert result.total_pnl == pytest.approx(2.0)


@pytest.mark.integration
def test_simulator_never_exceeds_position_limit_for_real_trader() -> None:
    """Drive the real ``Trader`` against a book that would invite unlimited fills.

    The anchor strategy's taker logic will not be marketable here because
    the spread is wide, but the integration check is that the simulator
    runs cleanly and respects the position limit via risk clipping.
    """
    rows = [
        {"P": _row(timestamp=t, product="P", bid=9998, bid_vol=50, ask=10002, ask_vol=50)}
        for t in range(5)
    ]
    replay = ReplayEngine(
        [ReplayStep(day=-1, timestamp=t, rows_by_product=r) for t, r in enumerate(rows)]
    )

    config = EngineConfig(
        products={
            "P": ProductConfig(
                position_limit=20,
                strategy_name="stable_anchor",
                fair_value_method="anchor",
                anchor_price=10_000.0,
                maker_edge=2.0,
                taker_edge=1.0,
                quote_size=5,
                max_aggressive_size=10,
            )
        }
    )
    simulator = BacktestSimulator(trader=Trader(config=config), fill_model=FillModel())

    result = simulator.run(replay)
    assert abs(result.per_product["P"].final_position) <= 20
