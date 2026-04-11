"""End-to-end tests for ``src.backtest.simulator.BacktestSimulator``."""

from __future__ import annotations

import pytest

from src.backtest.fill_model import FillModel, FillModelConfig
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config import EngineConfig, ProductConfig
from src.datamodel import Order, Trade, TradingState
from src.trader import Trader


class _ScriptedLogger:
    """Minimal stand-in for ``DecisionLogger`` so the scripted trader
    can publish decision-time fair values into the simulator's
    log-reading path without pulling in the full trader stack."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record(self, event: dict[str, object]) -> None:
        self.events.append(event)


class _ScriptedTrader:
    """Test double that returns a pre-baked sequence of orders.

    When given a ``fair_values`` sequence the trader also publishes
    decision-log events so the simulator can harvest decision-time
    fair values from the same hook the real trader uses.
    """

    def __init__(
        self,
        scripted: list[dict[str, list[Order]]],
        fair_values: list[dict[str, float]] | None = None,
    ) -> None:
        self._scripted = scripted
        self._fair_values = fair_values or []
        self._index = 0
        self.logger = _ScriptedLogger()
        self.config = EngineConfig(
            products={
                "P": ProductConfig(
                    position_limit=20,
                    strategy_name="market_making",
                    fair_value_method="anchor",
                    anchor_price=100.0,
                )
            }
        )

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        orders = self._scripted[self._index] if self._index < len(self._scripted) else {}
        if self._index < len(self._fair_values):
            for product, fair in self._fair_values[self._index].items():
                self.logger.record(
                    {
                        "timestamp": state.timestamp,
                        "product": product,
                        "fair_value": float(fair),
                        "method": "scripted",
                    }
                )
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
    fair_values = [{"P": 100.0}, {"P": 104.0}]
    simulator = BacktestSimulator(
        trader=_ScriptedTrader(scripted, fair_values=fair_values)  # type: ignore[arg-type]
    )

    result = simulator.run(replay)
    product = result.per_product["P"]
    assert product.final_position == 2
    assert product.taker_trade_count == 1
    assert product.maker_trade_count == 0
    assert product.cash == pytest.approx(-202.0)
    # Last mid 104, position 2 -> +208, cash -202 -> pnl 6
    assert product.pnl == pytest.approx(6.0)

    # Phase 4a: trade record + series are populated, taker's decision
    # and fill timestamps coincide, and mids/pnl are gap-free.
    assert len(result.trade_records) == 1
    record = result.trade_records[0]
    assert record.product == "P"
    assert record.side == "buy"
    assert record.mode == "taker"
    assert record.decision_timestamp == 0
    assert record.fill_timestamp == 0
    assert record.fair_value_at_decision == pytest.approx(100.0)
    assert record.mid_at_decision == pytest.approx(100.0)
    assert record.mid_at_fill == pytest.approx(100.0)
    assert result.mid_series["P"] == ((0, 100.0), (1, 104.0))
    assert len(result.pnl_series["P"]) == 2
    # At step 0 PnL uses the step mid (100) -> -202 + 2*100 = -2.
    assert result.pnl_series["P"][0] == (0, pytest.approx(-2.0))
    # Entry edge: buy at 101 vs fair 100 -> -1 per unit, quantity-weighted.
    assert product.avg_entry_edge == pytest.approx(-1.0)
    assert product.entry_edge_count == 1
    # Markout 1: buy at 101 vs future mid 104 -> +3.
    assert product.avg_markout_1 == pytest.approx(3.0)
    assert product.markout_1_count == 1
    # Horizons 5 and 20 can't reach past a 2-step replay.
    assert product.markout_5_count == 0
    assert product.markout_20_count == 0


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
                strategy_name="market_making",
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


@pytest.mark.integration
def test_simulator_records_decision_context_for_maker_fills() -> None:
    """Passive fills should carry the quoting step's fair value, not the
    step that cleared them."""
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
                market_trades={"P": [Trade("P", 99, 10, timestamp=1)]},
            ),
            _step(2, "P", 99, 5, 101, 5),
        ]
    )
    scripted = [
        {"P": [Order("P", 99, 4)]},  # quote at 99, fair=100 at step 0
        {"P": []},
        {"P": []},
    ]
    fair_values = [{"P": 100.0}, {"P": 95.0}, {"P": 100.0}]
    simulator = BacktestSimulator(
        trader=_ScriptedTrader(scripted, fair_values=fair_values),  # type: ignore[arg-type]
        fill_model=FillModel(FillModelConfig(passive_allocation=0.5)),
    )
    result = simulator.run(replay)
    # Expect one passive fill at step 1 from the pending quote created at step 0.
    maker_records = [r for r in result.trade_records if r.mode == "maker"]
    assert len(maker_records) == 1
    record = maker_records[0]
    assert record.decision_day == -1
    assert record.fill_day == -1
    assert record.decision_timestamp == 0
    assert record.fill_timestamp == 1
    assert record.decision_timestamp < record.fill_timestamp
    # Decision fair value was 100 (step 0), NOT 95 (step 1 when it cleared).
    assert record.fair_value_at_decision == pytest.approx(100.0)
    # Entry edge uses the decision-time fair value: buy at 99 vs fair 100 -> +1.
    assert result.per_product["P"].avg_entry_edge == pytest.approx(1.0)
    assert result.per_product["P"].entry_edge_count == 1


@pytest.mark.integration
def test_simulator_pnl_series_gap_free_with_carry_forward_mid() -> None:
    """PnL series must have an entry every step, even when the book is
    one-sided and no new mid is observable."""

    # Build a replay where step 1 has empty ask (one-sided book).
    def _row_no_ask(timestamp: int) -> dict[str, str]:
        return {
            "day": "-1",
            "timestamp": str(timestamp),
            "product": "P",
            "bid_price_1": "99",
            "bid_volume_1": "5",
            "bid_price_2": "",
            "bid_volume_2": "",
            "bid_price_3": "",
            "bid_volume_3": "",
            "ask_price_1": "",
            "ask_volume_1": "",
            "ask_price_2": "",
            "ask_volume_2": "",
            "ask_price_3": "",
            "ask_volume_3": "",
            "mid_price": "99",
            "profit_and_loss": "0.0",
        }

    replay = ReplayEngine(
        [
            _step(0, "P", 99, 5, 101, 5),
            ReplayStep(day=-1, timestamp=1, rows_by_product={"P": _row_no_ask(1)}),
            _step(2, "P", 99, 5, 101, 5),
        ]
    )
    scripted = [{"P": []}, {"P": []}, {"P": []}]
    simulator = BacktestSimulator(trader=_ScriptedTrader(scripted))  # type: ignore[arg-type]
    result = simulator.run(replay)

    # mid_series only records steps with a two-sided book (two of three).
    assert len(result.mid_series["P"]) == 2
    # pnl_series records every step (three of three).
    assert len(result.pnl_series["P"]) == 3
    # Step 1 (one-sided) carried forward step 0's mid of 100.
    assert result.pnl_series["P"][1][0] == 1  # timestamp
    assert result.pnl_series["P"][1][1] == pytest.approx(0.0)  # position 0 -> pnl=cash=0
