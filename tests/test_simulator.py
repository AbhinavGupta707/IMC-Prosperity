"""End-to-end tests for ``src.backtest.simulator.BacktestSimulator``."""

from __future__ import annotations

import pytest

from src.backtest.fill_model import FillModel, FillModelConfig
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config import EngineConfig, ProductConfig
from src.datamodel import Order, Trade, TradingState
from src.trader import Trader


class _ScriptedTrader:
    """Test double that returns a pre-baked sequence of orders."""

    def __init__(self, scripted: list[dict[str, list[Order]]]) -> None:
        self._scripted = scripted
        self._index = 0
        self.config = EngineConfig(
            products={
                "P": ProductConfig(
                    position_limit=20,
                    strategy_name="stable_anchor",
                    fair_value_method="anchor",
                    anchor_price=100.0,
                )
            }
        )

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


def _step(
    timestamp: int,
    product: str,
    bid: int,
    bid_vol: int,
    ask: int,
    ask_vol: int,
    market_trades: dict[str, list[Trade]] | None = None,
) -> ReplayStep:
    return ReplayStep(
        day=-1,
        timestamp=timestamp,
        rows_by_product={product: _row(timestamp, product, bid, bid_vol, ask, ask_vol)},
        market_trades=market_trades or {},
    )


@pytest.mark.integration
def test_simulator_zero_trades_when_orders_are_empty() -> None:
    replay = ReplayEngine([_step(0, "P", 99, 5, 101, 5)])
    simulator = BacktestSimulator(trader=_ScriptedTrader([{}]))  # type: ignore[arg-type]
    result = simulator.run(replay)
    assert result.steps == 1
    assert result.total_pnl == 0.0
    product = result.per_product["P"]
    assert product.trade_count == 0
    assert product.final_position == 0


@pytest.mark.integration
def test_simulator_taker_buy_marks_to_market() -> None:
    replay = ReplayEngine(
        [
            _step(0, "P", 99, 5, 101, 5),
            _step(1, "P", 103, 5, 105, 5),
        ]
    )
    scripted = [{"P": [Order("P", 101, 2)]}, {"P": []}]
    simulator = BacktestSimulator(trader=_ScriptedTrader(scripted))  # type: ignore[arg-type]

    result = simulator.run(replay)
    product = result.per_product["P"]
    assert product.final_position == 2
    assert product.taker_trade_count == 1
    assert product.maker_trade_count == 0
    assert product.cash == pytest.approx(-202.0)
    # Last mid 104, position 2 -> +208, cash -202 -> pnl 6
    assert product.pnl == pytest.approx(6.0)


@pytest.mark.integration
def test_simulator_deferred_passive_fill_from_next_step_market_trades() -> None:
    """A non-marketable bid at step 0 should be filled by a matching
    market trade at step 1."""
    replay = ReplayEngine(
        [
            _step(0, "P", 99, 5, 101, 5),
            _step(
                1,
                "P",
                99,
                5,
                101,
                5,
                market_trades={"P": [Trade("P", 99, 6, timestamp=1)]},
            ),
            _step(2, "P", 99, 5, 101, 5),
        ]
    )
    # Step 0: trader places a passive bid at 99 size 4 -> becomes pending
    # Step 1: passive fill scored against market trade at 99 qty 6
    #         with allocation 0.5 -> floor(6 * 0.5) = 3 units filled
    # Step 2: no orders
    scripted = [
        {"P": [Order("P", 99, 4)]},
        {"P": []},
        {"P": []},
    ]
    simulator = BacktestSimulator(
        trader=_ScriptedTrader(scripted),  # type: ignore[arg-type]
        fill_model=FillModel(FillModelConfig(passive_allocation=0.5)),
    )
    result = simulator.run(replay)
    product = result.per_product["P"]
    assert product.maker_trade_count == 1
    assert product.final_position == 3
    assert product.cash == pytest.approx(-297.0)


@pytest.mark.integration
def test_simulator_respects_position_limit_for_real_trader() -> None:
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
    simulator = BacktestSimulator(trader=Trader(config=config))
    result = simulator.run(replay)
    assert abs(result.per_product["P"].final_position) <= 20


@pytest.mark.integration
def test_simulator_tracks_steps_near_position_limit() -> None:
    """When |position| >= 0.75 * limit we should count the step."""
    replay = ReplayEngine(
        [
            _step(0, "P", 99, 5, 101, 5),
            _step(1, "P", 99, 5, 101, 5),
            _step(2, "P", 99, 5, 101, 5),
        ]
    )
    # Force position above 75% of limit via taker buys, then hold.
    scripted = [
        {"P": [Order("P", 101, 5)]},  # buy 5 -> pos 5
        {"P": [Order("P", 101, 5)]},  # buy 5 -> pos 10
        {"P": [Order("P", 101, 5)]},  # buy 5 -> pos 15 >= 0.75*20=15
    ]
    simulator = BacktestSimulator(trader=_ScriptedTrader(scripted))  # type: ignore[arg-type]
    result = simulator.run(replay)
    # Step 0: pos 0 (before fill). After fill 5, step end count uses 5 < 15.
    # Step 1: pos 5 -> 10 < 15.
    # Step 2: pos 10 -> 15 == 15 -> counted as near-limit.
    assert result.per_product["P"].steps_near_limit == 1
