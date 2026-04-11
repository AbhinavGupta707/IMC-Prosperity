"""Parameter sweep utilities for replay-backed tuning.

Phase 6 asks for stable parameter regions rather than a single lucky
peak. This module runs a grid of candidate configs through the replay
simulator and records both the best rows and per-parameter averages so
we can look for robust settings.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any, cast

from src.backtest.fair_value_compare import filter_replay_to_product
from src.backtest.metrics import ProductResult
from src.backtest.replay_engine import ReplayEngine
from src.backtest.simulator import BacktestSimulator
from src.backtest.sweep import GridValue, parameter_grid
from src.core.config import EngineConfig, ProductConfig, default_engine_config
from src.trader import Trader

type SweepValue = GridValue
_DEFAULT_SWEEP_DIR = Path("outputs/sweeps")


@dataclass(frozen=True)
class SweepRow:
    params: dict[str, SweepValue]
    pnl: float
    trade_count: int
    maker_share: float | None
    final_position: int
    steps_near_limit: int


@dataclass(frozen=True)
class ParameterAggregate:
    parameter: str
    value: SweepValue
    mean_pnl: float
    mean_trade_count: float
    mean_steps_near_limit: float


@dataclass(frozen=True)
class ParameterSweepReport:
    run_label: str
    product: str
    generated_at: str
    fair_value_method: str
    baseline: SweepRow
    rows: tuple[SweepRow, ...]
    aggregates: tuple[ParameterAggregate, ...]

    def ranked_rows(self) -> list[SweepRow]:
        return sorted(
            self.rows,
            key=lambda row: (
                row.pnl,
                -row.steps_near_limit,
                -abs(row.final_position),
                -row.trade_count,
            ),
            reverse=True,
        )

    def summary_text(self, *, top_n: int = 10) -> str:
        header = (
            f"{'maker':>5} {'taker':>5} {'skew':>5} {'flat':>5} "
            f"{'pnl':>10} {'trades':>7} {'mk%':>6} {'near':>5} {'pos':>4}"
        )
        lines = [
            f"Parameter sweep: {self.product}",
            f"run_label: {self.run_label}",
            f"fair_value_method: {self.fair_value_method}",
            "",
            "Baseline",
            header,
            "-" * len(header),
            _row_line(self.baseline),
            "",
            f"Top {min(top_n, len(self.rows))} configs",
            header,
            "-" * len(header),
        ]
        for row in self.ranked_rows()[:top_n]:
            lines.append(_row_line(row))

        lines.extend(
            [
                "",
                "Average pnl by parameter value",
            ]
        )
        for aggregate in self.aggregates:
            lines.append(
                f"{aggregate.parameter}={aggregate.value}: "
                f"mean_pnl={aggregate.mean_pnl:.2f}, "
                f"mean_trades={aggregate.mean_trade_count:.1f}, "
                f"mean_near_limit={aggregate.mean_steps_near_limit:.1f}"
            )
        return "\n".join(lines)


def build_parameter_sweep_report(
    replay: ReplayEngine,
    *,
    product: str,
    grid: dict[str, list[SweepValue]],
    config: EngineConfig | None = None,
    run_label: str = "",
) -> ParameterSweepReport:
    engine_config = config or default_engine_config()
    product_config = engine_config.product_config(product)
    if product_config is None:
        raise ValueError(f"Unknown product {product!r}")

    product_replay = filter_replay_to_product(replay, product)
    if not product_replay.steps:
        raise ValueError(f"No replay steps found for product {product!r}")

    baseline = _simulate_row(
        product_replay=product_replay,
        product=product,
        product_config=product_config,
        engine_config=engine_config,
        params={key: getattr(product_config, key) for key in grid},
    )

    rows: list[SweepRow] = []
    for params in parameter_grid(grid):
        candidate = replace(product_config, **cast(dict[str, Any], params))
        rows.append(
            _simulate_row(
                product_replay=product_replay,
                product=product,
                product_config=candidate,
                engine_config=engine_config,
                params={key: value for key, value in params.items()},
            )
        )

    return ParameterSweepReport(
        run_label=run_label,
        product=product,
        generated_at=datetime.now(UTC).isoformat(),
        fair_value_method=product_config.fair_value_method,
        baseline=baseline,
        rows=tuple(rows),
        aggregates=tuple(_build_aggregates(rows, grid)),
    )


def write_parameter_sweep_report(
    report: ParameterSweepReport,
    *,
    base_dir: Path | str = _DEFAULT_SWEEP_DIR,
) -> Path:
    run_id = _run_id(report.run_label or report.product.lower())
    directory = Path(base_dir) / run_id
    directory.mkdir(parents=True, exist_ok=True)

    (directory / "summary.json").write_text(json.dumps(asdict(report), indent=2, sort_keys=True))
    (directory / "summary.txt").write_text(report.summary_text() + "\n")
    return directory


def _simulate_row(
    *,
    product_replay: ReplayEngine,
    product: str,
    product_config: ProductConfig,
    engine_config: EngineConfig,
    params: dict[str, SweepValue],
) -> SweepRow:
    run_config = EngineConfig(
        state_version=engine_config.state_version,
        max_trader_data_chars=engine_config.max_trader_data_chars,
        diagnostics_verbosity=engine_config.diagnostics_verbosity,
        products={product: product_config},
    )
    simulator = BacktestSimulator(trader=Trader(config=run_config))
    result = simulator.run(product_replay)
    product_result = result.per_product[product]
    return SweepRow(
        params=params,
        pnl=product_result.pnl,
        trade_count=product_result.trade_count,
        maker_share=_maker_share(product_result),
        final_position=product_result.final_position,
        steps_near_limit=product_result.steps_near_limit,
    )


def _maker_share(result: ProductResult) -> float | None:
    total_qty = result.taker_trade_quantity + result.maker_trade_quantity
    if total_qty <= 0:
        return None
    return result.maker_trade_quantity / total_qty


def _build_aggregates(
    rows: list[SweepRow], grid: dict[str, list[SweepValue]]
) -> list[ParameterAggregate]:
    aggregates: list[ParameterAggregate] = []
    for parameter, values in grid.items():
        for value in values:
            matching = [row for row in rows if row.params.get(parameter) == value]
            if not matching:
                continue
            aggregates.append(
                ParameterAggregate(
                    parameter=parameter,
                    value=value,
                    mean_pnl=mean(row.pnl for row in matching),
                    mean_trade_count=mean(row.trade_count for row in matching),
                    mean_steps_near_limit=mean(row.steps_near_limit for row in matching),
                )
            )
    return aggregates


def _row_line(row: SweepRow) -> str:
    maker = row.params.get("maker_edge", "n/a")
    taker = row.params.get("taker_edge", "n/a")
    skew = row.params.get("inventory_skew", "n/a")
    flatten = row.params.get("flatten_threshold", "n/a")
    maker_share = f"{row.maker_share * 100:.1f}" if row.maker_share is not None else "n/a"
    return (
        f"{maker:>5} {taker:>5} {skew:>5} {flatten:>5} "
        f"{row.pnl:>10.2f} {row.trade_count:>7d} {maker_share:>6} "
        f"{row.steps_near_limit:>5d} {row.final_position:>4d}"
    )


def _run_id(run_label: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    clean = "".join(char if char.isalnum() or char in "-_" else "_" for char in run_label)
    return f"{stamp}_{clean}" if clean else stamp
