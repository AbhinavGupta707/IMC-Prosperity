"""Unit tests for ``src.backtest.replay_engine``."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.datamodel import OrderDepth, TradingState

_CSV_HEADER = (
    "day;timestamp;product;"
    "bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;"
    "ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;"
    "mid_price;profit_and_loss"
)


def _write_csv(tmp_path: Path, name: str, lines: list[str]) -> Path:
    path = tmp_path / name
    path.write_text(_CSV_HEADER + "\n" + "\n".join(lines) + "\n")
    return path


@pytest.mark.unit
def test_from_price_files_groups_by_day_and_timestamp(tmp_path: Path) -> None:
    file_a = _write_csv(
        tmp_path,
        "prices_a.csv",
        [
            "-1;0;EMERALDS;9992;14;9990;29;;;10008;14;10010;29;;;10000.0;0.0",
            "-1;0;TOMATOES;4999;5;4998;15;;;5013;5;5014;15;;;5006.0;0.0",
            "-1;100;EMERALDS;9993;10;;;;;10005;10;;;;;9999.0;0.0",
        ],
    )
    engine = ReplayEngine.from_price_files([file_a])

    assert [s.timestamp for s in engine.steps] == [0, 100]
    assert set(engine.steps[0].rows_by_product) == {"EMERALDS", "TOMATOES"}
    assert set(engine.steps[1].rows_by_product) == {"EMERALDS"}


@pytest.mark.unit
def test_build_trading_state_parses_order_depth_with_negative_ask_volumes(
    tmp_path: Path,
) -> None:
    file_a = _write_csv(
        tmp_path,
        "prices_a.csv",
        ["-1;0;EMERALDS;9992;14;9990;29;;;10008;14;10010;29;;;10000.0;0.0"],
    )
    engine = ReplayEngine.from_price_files([file_a])
    step = engine.steps[0]

    state = ReplayEngine.build_trading_state(
        step, trader_data="", position={"EMERALDS": 3}, own_trades={}
    )
    assert isinstance(state, TradingState)
    assert state.timestamp == 0
    assert state.position == {"EMERALDS": 3}
    depth = state.order_depths["EMERALDS"]
    assert isinstance(depth, OrderDepth)
    assert depth.buy_orders == {9992: 14, 9990: 29}
    assert depth.sell_orders == {10008: -14, 10010: -29}


@pytest.mark.unit
def test_build_trading_state_handles_missing_levels(tmp_path: Path) -> None:
    file_a = _write_csv(
        tmp_path,
        "prices_a.csv",
        ["-1;0;P;100;5;;;;;101;5;;;;;100.5;0.0"],
    )
    engine = ReplayEngine.from_price_files([file_a])
    state = ReplayEngine.build_trading_state(
        engine.steps[0], trader_data="", position={}, own_trades={}
    )
    depth = state.order_depths["P"]
    assert depth.buy_orders == {100: 5}
    assert depth.sell_orders == {101: -5}


@pytest.mark.unit
def test_replay_step_is_immutable() -> None:
    step = ReplayStep(day=-1, timestamp=0, rows_by_product={})
    with pytest.raises((AttributeError, TypeError)):
        step.day = 5  # type: ignore[misc]


@pytest.mark.unit
def test_from_files_joins_prices_and_trades_by_day_and_timestamp(tmp_path: Path) -> None:
    price_file = _write_csv(
        tmp_path,
        "prices_round_0_day_-1.csv",
        [
            "-1;0;EMERALDS;9992;14;;;;;10008;14;;;;;10000.0;0.0",
            "-1;100;EMERALDS;9993;10;;;;;10005;10;;;;;9999.0;0.0",
        ],
    )
    trade_file = tmp_path / "trades_round_0_day_-1.csv"
    trade_file.write_text(
        "timestamp;buyer;seller;symbol;currency;price;quantity\n" "100;;;EMERALDS;XIRECS;9993.0;5\n"
    )

    engine = ReplayEngine.from_files(price_paths=[price_file], trade_paths=[trade_file])

    assert engine.steps[0].market_trades == {}
    trades = engine.steps[1].market_trades["EMERALDS"]
    assert len(trades) == 1
    assert trades[0].price == 9993
    assert trades[0].quantity == 5
    assert trades[0].timestamp == 100


@pytest.mark.unit
def test_from_files_rejects_trade_file_without_day_in_name(tmp_path: Path) -> None:
    bad = tmp_path / "trades.csv"
    bad.write_text("timestamp;buyer;seller;symbol;currency;price;quantity\n")
    with pytest.raises(ValueError, match="infer day"):
        ReplayEngine.from_files(price_paths=[], trade_paths=[bad])


@pytest.mark.unit
def test_build_trading_state_includes_market_trades_from_step(tmp_path: Path) -> None:
    price_file = _write_csv(
        tmp_path,
        "prices_round_0_day_-1.csv",
        ["-1;100;EMERALDS;9993;10;;;;;10005;10;;;;;9999.0;0.0"],
    )
    trade_file = tmp_path / "trades_round_0_day_-1.csv"
    trade_file.write_text(
        "timestamp;buyer;seller;symbol;currency;price;quantity\n" "100;;;EMERALDS;XIRECS;9993.0;5\n"
    )
    engine = ReplayEngine.from_files(price_paths=[price_file], trade_paths=[trade_file])

    state = ReplayEngine.build_trading_state(
        engine.steps[0], trader_data="", position={}, own_trades={}
    )
    assert state.market_trades["EMERALDS"][0].price == 9993
