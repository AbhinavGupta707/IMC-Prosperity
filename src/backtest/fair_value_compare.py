"""Phase 3 fair-value comparison workflow.

Builds apples-to-apples comparisons across candidate fair-value
estimators on the tutorial or round replay data.

For each product we produce two complementary views:

1. Snapshot-fit metrics: how well each estimator tracks the current and
   future mid prices.
2. Replay metrics: how the same execution skeleton behaves when that
   estimator is promoted to the primary fair value in a live-style
   replay run.

This lets us separate "tracks price well" from "trades well on one
sample", which is the key discipline Phase 3 is supposed to enforce.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from src.backtest.metrics import ProductResult
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config import EngineConfig, ProductConfig, default_engine_config
from src.core.fair_value import ESTIMATORS
from src.core.market_data import MarketDataAdapter
from src.core.types import NormalizedSnapshot, ProductMemory
from src.core.utils import bounded_append
from src.trader import Trader

DEFAULT_COMPARISON_ESTIMATORS = (
    "anchor",
    "mid",
    "microprice",
    "rolling_mid",
    "weighted_mid",
    "depth_mid",
)
_DEFAULT_REPORT_DIR = Path("outputs/fair_value_comparison")


@dataclass(frozen=True)
class EstimatorComparison:
    estimator: str
    samples: int
    coverage: float
    current_mid_mae: float | None
    next_mid_mae: float | None
    horizon_5_mid_mae: float | None
    next_mid_delta_vs_mid: float | None
    pnl: float
    trade_count: int
    maker_share: float | None
    final_position: int
    steps_near_limit: int


@dataclass(frozen=True)
class ProductFairValueComparison:
    product: str
    live_method: str
    baseline_next_mid_mae: float | None
    comparisons: tuple[EstimatorComparison, ...]

    def summary_table(self) -> str:
        header = (
            f"{'estimator':<12} {'cov%':>6} {'mae_now':>8} {'mae_n1':>8} "
            f"{'d_n1':>8} {'mae_n5':>8} {'pnl':>10} {'trades':>7} "
            f"{'mk%':>6} {'near':>5}"
        )
        lines = [header, "-" * len(header)]
        for row in self.comparisons:
            maker_share = f"{row.maker_share * 100:.1f}" if row.maker_share is not None else "n/a"
            lines.append(
                f"{row.estimator:<12} {row.coverage * 100:>6.1f} "
                f"{_fmt(row.current_mid_mae):>8} {_fmt(row.next_mid_mae):>8} "
                f"{_fmt(row.next_mid_delta_vs_mid, signed=True):>8} "
                f"{_fmt(row.horizon_5_mid_mae):>8} {row.pnl:>10.2f} "
                f"{row.trade_count:>7d} {maker_share:>6} {row.steps_near_limit:>5d}"
            )
        lines.append("-" * len(header))
        lines.append(
            "delta_n1 compares estimator next-step MAE against the current-mid baseline "
            f"({ _fmt(self.baseline_next_mid_mae) })"
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class FairValueComparisonReport:
    run_label: str
    generated_at: str
    products: tuple[ProductFairValueComparison, ...]

    def summary_text(self) -> str:
        blocks = [
            f"Fair value comparison report: {self.run_label}",
            f"generated_at: {self.generated_at}",
        ]
        for product in self.products:
            blocks.append("")
            blocks.append(f"[{product.product}] live_method={product.live_method}")
            blocks.append(product.summary_table())
        return "\n".join(blocks)


@dataclass(frozen=True)
class _SnapshotRecord:
    timestamp: int
    mid: float | None
    estimates: dict[str, float | None]


def filter_replay_to_product(replay: ReplayEngine, product: str) -> ReplayEngine:
    steps: list[ReplayStep] = []
    for step in replay.steps:
        row = step.rows_by_product.get(product)
        if row is None:
            continue
        market_trades = (
            {product: list(step.market_trades.get(product, []))}
            if product in step.market_trades
            else {}
        )
        steps.append(
            ReplayStep(
                day=step.day,
                timestamp=step.timestamp,
                rows_by_product={product: dict(row)},
                market_trades=market_trades,
            )
        )
    return ReplayEngine(steps)


def build_fair_value_report(
    replay: ReplayEngine,
    *,
    config: EngineConfig | None = None,
    run_label: str = "tutorial_round_1",
    products: tuple[str, ...] | None = None,
    estimator_names: tuple[str, ...] = DEFAULT_COMPARISON_ESTIMATORS,
) -> FairValueComparisonReport:
    engine_config = config or default_engine_config()
    target_products = products or tuple(engine_config.products)

    product_reports: list[ProductFairValueComparison] = []
    for product in target_products:
        product_config = engine_config.product_config(product)
        if product_config is None:
            continue
        product_replay = filter_replay_to_product(replay, product)
        if not product_replay.steps:
            continue
        supported_estimators = _supported_estimator_names(
            product_config=product_config,
            estimator_names=estimator_names,
        )

        records = _build_snapshot_records(
            product_replay,
            product=product,
            product_config=product_config,
            estimator_names=supported_estimators,
        )
        baseline_next_mid_mae = _baseline_next_mid_mae(records)

        comparisons: list[EstimatorComparison] = []
        for estimator_name in supported_estimators:
            comparisons.append(
                _compare_estimator(
                    product_replay=product_replay,
                    product=product,
                    estimator_name=estimator_name,
                    product_config=product_config,
                    engine_config=engine_config,
                    records=records,
                    baseline_next_mid_mae=baseline_next_mid_mae,
                    estimator_names=supported_estimators,
                )
            )

        product_reports.append(
            ProductFairValueComparison(
                product=product,
                live_method=product_config.fair_value_method,
                baseline_next_mid_mae=baseline_next_mid_mae,
                comparisons=tuple(comparisons),
            )
        )

    return FairValueComparisonReport(
        run_label=run_label,
        generated_at=datetime.now(UTC).isoformat(),
        products=tuple(product_reports),
    )


def write_fair_value_report(
    report: FairValueComparisonReport,
    *,
    base_dir: Path | str = _DEFAULT_REPORT_DIR,
) -> Path:
    run_id = _run_id(report.run_label)
    directory = Path(base_dir) / run_id
    directory.mkdir(parents=True, exist_ok=True)

    (directory / "summary.json").write_text(json.dumps(asdict(report), indent=2, sort_keys=True))
    (directory / "summary.txt").write_text(report.summary_text() + "\n")
    return directory


def _build_snapshot_records(
    replay: ReplayEngine,
    *,
    product: str,
    product_config: ProductConfig,
    estimator_names: tuple[str, ...],
) -> list[_SnapshotRecord]:
    adapter = MarketDataAdapter()
    memory = ProductMemory()
    records: list[_SnapshotRecord] = []

    for step in replay.steps:
        state = ReplayEngine.build_trading_state(
            step,
            trader_data="",
            position={product: 0},
            own_trades={},
        )
        snapshot = adapter.normalize_state(state)[product]

        estimates: dict[str, float | None] = {}
        for estimator_name in estimator_names:
            estimator = ESTIMATORS.get(estimator_name)
            if estimator is None:
                continue
            result = estimator.estimate(snapshot, memory, product_config)
            estimates[estimator_name] = result.price if result is not None else None

        records.append(
            _SnapshotRecord(
                timestamp=step.timestamp,
                mid=snapshot.mid,
                estimates=estimates,
            )
        )
        _update_memory(memory, snapshot, product_config.history_length)

    return records


def _supported_estimator_names(
    *,
    product_config: ProductConfig,
    estimator_names: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        name
        for name in estimator_names
        if name in ESTIMATORS and _estimator_supported(product_config, name)
    )


def _estimator_supported(product_config: ProductConfig, estimator_name: str) -> bool:
    return not (estimator_name == "anchor" and product_config.anchor_price is None)


def _compare_estimator(
    *,
    product_replay: ReplayEngine,
    product: str,
    estimator_name: str,
    product_config: ProductConfig,
    engine_config: EngineConfig,
    records: list[_SnapshotRecord],
    baseline_next_mid_mae: float | None,
    estimator_names: tuple[str, ...],
) -> EstimatorComparison:
    current_mid_errors: list[float] = []
    next_mid_errors: list[float] = []
    horizon_5_errors: list[float] = []
    samples = 0

    for index, record in enumerate(records):
        estimate = record.estimates.get(estimator_name)
        if estimate is None:
            continue
        samples += 1

        if record.mid is not None:
            current_mid_errors.append(abs(estimate - record.mid))

        next_mid = _future_mid(records, index=index, horizon=1)
        if next_mid is not None:
            next_mid_errors.append(abs(estimate - next_mid))

        horizon_5_mid = _future_mid(records, index=index, horizon=5)
        if horizon_5_mid is not None:
            horizon_5_errors.append(abs(estimate - horizon_5_mid))

    replay_result = _run_estimator_replay(
        product_replay=product_replay,
        product=product,
        estimator_name=estimator_name,
        product_config=product_config,
        engine_config=engine_config,
        estimator_names=estimator_names,
    )

    total_trade_qty = replay_result.taker_trade_quantity + replay_result.maker_trade_quantity
    maker_share = (
        replay_result.maker_trade_quantity / total_trade_qty if total_trade_qty > 0 else None
    )

    next_mid_mae = _mean(next_mid_errors)
    return EstimatorComparison(
        estimator=estimator_name,
        samples=samples,
        coverage=samples / len(records) if records else 0.0,
        current_mid_mae=_mean(current_mid_errors),
        next_mid_mae=next_mid_mae,
        horizon_5_mid_mae=_mean(horizon_5_errors),
        next_mid_delta_vs_mid=(
            None
            if next_mid_mae is None or baseline_next_mid_mae is None
            else next_mid_mae - baseline_next_mid_mae
        ),
        pnl=replay_result.pnl,
        trade_count=replay_result.trade_count,
        maker_share=maker_share,
        final_position=replay_result.final_position,
        steps_near_limit=replay_result.steps_near_limit,
    )


def _run_estimator_replay(
    *,
    product_replay: ReplayEngine,
    product: str,
    estimator_name: str,
    product_config: ProductConfig,
    engine_config: EngineConfig,
    estimator_names: tuple[str, ...],
) -> ProductResult:
    comparison_config = _comparison_engine_config(
        product=product,
        product_config=product_config,
        engine_config=engine_config,
        estimator_name=estimator_name,
        estimator_names=estimator_names,
    )
    simulator = BacktestSimulator(trader=Trader(config=comparison_config))
    result = simulator.run(product_replay)
    return result.per_product[product]


def _comparison_engine_config(
    *,
    product: str,
    product_config: ProductConfig,
    engine_config: EngineConfig,
    estimator_name: str,
    estimator_names: tuple[str, ...],
) -> EngineConfig:
    safe_fallbacks = tuple(
        name
        for name in estimator_names
        if name != estimator_name
        and name in ESTIMATORS
        and (name != "anchor" or product_config.anchor_price is not None)
    )
    comparison_product_config = replace(
        product_config,
        fair_value_method=estimator_name,
        fair_value_fallbacks=safe_fallbacks,
    )
    return EngineConfig(
        state_version=engine_config.state_version,
        max_trader_data_chars=engine_config.max_trader_data_chars,
        diagnostics_verbosity=engine_config.diagnostics_verbosity,
        products={product: comparison_product_config},
    )


def _future_mid(records: list[_SnapshotRecord], *, index: int, horizon: int) -> float | None:
    future_index = index + horizon
    if future_index >= len(records):
        return None
    return records[future_index].mid


def _baseline_next_mid_mae(records: list[_SnapshotRecord]) -> float | None:
    errors: list[float] = []
    for index, record in enumerate(records):
        if record.mid is None:
            continue
        next_mid = _future_mid(records, index=index, horizon=1)
        if next_mid is None:
            continue
        errors.append(abs(record.mid - next_mid))
    return _mean(errors)


def _update_memory(
    memory: ProductMemory, snapshot: NormalizedSnapshot, history_length: int
) -> None:
    if history_length <= 0:
        return
    if snapshot.mid is not None:
        bounded_append(memory.recent_mids, float(snapshot.mid), history_length)
    if snapshot.spread is not None:
        bounded_append(memory.recent_spreads, float(snapshot.spread), history_length)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _fmt(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.3f}" if signed else f"{value:.3f}"


def _run_id(run_label: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    clean = "".join(char if char.isalnum() or char in "-_" else "_" for char in run_label)
    return f"{stamp}_{clean}" if clean else stamp
