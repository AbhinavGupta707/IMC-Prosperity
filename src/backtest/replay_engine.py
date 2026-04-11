"""Replay tutorial/round CSV data into the engine's ``TradingState`` format.

The IMC tutorial CSVs use one row per (day, timestamp, product) with up
to three bid and three ask levels. This module:

1. Parses those rows and optionally the matching trade tape.
2. Groups them by (day, timestamp) so one ``ReplayStep`` describes all
   products the exchange saw at that instant plus the market trades
   that were observed in the interval leading up to it.
3. Converts each ``ReplayStep`` into a ``TradingState`` on demand so the
   live ``Trader`` can be driven by the exact same interface it sees in
   production.

The backtest simulator consumes ``TradingState``s produced here and
tracks positions, cash, and fills itself; this module is pure parsing.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from src.datamodel import Observation, OrderDepth, Trade, TradingState

# Column name templates in the tutorial CSVs.
_BID_PRICE_COLS = [f"bid_price_{i}" for i in (1, 2, 3)]
_BID_VOLUME_COLS = [f"bid_volume_{i}" for i in (1, 2, 3)]
_ASK_PRICE_COLS = [f"ask_price_{i}" for i in (1, 2, 3)]
_ASK_VOLUME_COLS = [f"ask_volume_{i}" for i in (1, 2, 3)]

_DAY_FILENAME_RE = re.compile(r"day_(-?\d+)")


@dataclass(frozen=True)
class ReplayStep:
    day: int
    timestamp: int
    rows_by_product: dict[str, dict[str, str]]
    market_trades: dict[str, list[Trade]] = field(default_factory=dict)


class ReplayEngine:
    def __init__(self, steps: list[ReplayStep]) -> None:
        self.steps = steps

    @classmethod
    def from_price_files(cls, paths: Sequence[str | Path]) -> ReplayEngine:
        return cls.from_files(price_paths=paths, trade_paths=[])

    @classmethod
    def from_files(
        cls,
        price_paths: Sequence[str | Path],
        trade_paths: Sequence[str | Path] = (),
    ) -> ReplayEngine:
        grouped: dict[tuple[int, int], dict[str, dict[str, str]]] = defaultdict(dict)
        for path in price_paths:
            with Path(path).open(newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";")
                for row in reader:
                    day = int(row["day"])
                    timestamp = int(row["timestamp"])
                    grouped[(day, timestamp)][row["product"]] = row

        trades_by_key: dict[tuple[int, int], dict[str, list[Trade]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for path in trade_paths:
            day = _infer_day_from_filename(Path(path))
            with Path(path).open(newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";")
                for row in reader:
                    timestamp = int(row["timestamp"])
                    symbol = row["symbol"]
                    trades_by_key[(day, timestamp)][symbol].append(
                        Trade(
                            symbol=symbol,
                            price=int(float(row["price"])),
                            quantity=int(float(row["quantity"])),
                            buyer=row.get("buyer") or None,
                            seller=row.get("seller") or None,
                            timestamp=timestamp,
                        )
                    )

        steps = [
            ReplayStep(
                day=day,
                timestamp=timestamp,
                rows_by_product=rows,
                market_trades={
                    symbol: list(trades)
                    for symbol, trades in trades_by_key.get((day, timestamp), {}).items()
                },
            )
            for (day, timestamp), rows in sorted(grouped.items())
        ]
        return cls(steps)

    def iter_steps(self) -> Iterator[ReplayStep]:
        yield from self.steps

    # -------------------------------------------------------- row -> state

    @staticmethod
    def build_trading_state(
        step: ReplayStep,
        *,
        trader_data: str,
        position: dict[str, int],
        own_trades: dict[str, list[Trade]],
    ) -> TradingState:
        """Build a ``TradingState`` the ``Trader`` can consume.

        The trader's position, recent own trades, and ``traderData`` are
        threaded in from the simulator so this function stays pure.
        """
        order_depths: dict[str, OrderDepth] = {}
        for product, row in step.rows_by_product.items():
            order_depths[product] = _order_depth_from_row(row)

        return TradingState(
            traderData=trader_data,
            timestamp=step.timestamp,
            listings={},
            order_depths=order_depths,
            own_trades={product: own_trades.get(product, []) for product in order_depths},
            market_trades={
                product: list(step.market_trades.get(product, [])) for product in order_depths
            },
            position={product: position.get(product, 0) for product in order_depths},
            observations=Observation(),
        )


def _infer_day_from_filename(path: Path) -> int:
    match = _DAY_FILENAME_RE.search(path.name)
    if match is None:
        raise ValueError(
            f"Could not infer day from trade filename {path.name!r}; "
            "expected a pattern like 'trades_round_0_day_-1.csv'"
        )
    return int(match.group(1))


def _order_depth_from_row(row: dict[str, str]) -> OrderDepth:
    """Parse a single CSV row into an ``OrderDepth``.

    Uses Prosperity's native convention: sell volumes are stored as
    negative integers so ``core.market_data`` can normalize either way.
    """
    buy_orders: dict[int, int] = {}
    sell_orders: dict[int, int] = {}

    for price_col, volume_col in zip(_BID_PRICE_COLS, _BID_VOLUME_COLS, strict=True):
        price = row.get(price_col, "")
        volume = row.get(volume_col, "")
        if not price or not volume:
            continue
        buy_orders[int(float(price))] = int(float(volume))

    for price_col, volume_col in zip(_ASK_PRICE_COLS, _ASK_VOLUME_COLS, strict=True):
        price = row.get(price_col, "")
        volume = row.get(volume_col, "")
        if not price or not volume:
            continue
        sell_orders[int(float(price))] = -abs(int(float(volume)))

    return OrderDepth(buy_orders=buy_orders, sell_orders=sell_orders)
