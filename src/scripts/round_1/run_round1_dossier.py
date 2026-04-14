"""Round 1 product-dossier EDA.

For each Round-1 product, produces:

1.  Per-day price / spread / volume summary statistics (min, max, mean,
    median, std, percentiles).
2.  Spread histogram (as a frequency table).
3.  Visible depth and volume distribution by book level.
4.  One-sided / missing-side prevalence.
5.  Residual analysis against a shortlist of fair-value candidates
    (mean, std, skewness, short-horizon mean reversion, next-mid
    correlation). Both "anchor-style" and "trend-style" priors are
    evaluated.
6.  Simple microstructure flags: persistent walls, frequent-size
    clusters, one-tick undercutting frequency, trade-price offset from
    the mid at the nearest snapshot.

All outputs are written as JSON + Markdown tables into
``outputs/round_1/eda/<run_label>/`` so the dossier markdown files can
pull figures into their narrative.

This script is strictly observational: it never runs ``Trader`` and
never issues orders. Fair-value estimator tracking is done by calling
each estimator on each snapshot (same pathway as
``fair_value_compare._build_snapshot_records``).

Usage::

    PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.run_round1_dossier \
        --label round1_dossier_phase1
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.backtest.replay_engine import ReplayEngine
from src.core.config import ProductConfig
from src.core.fair_value import ESTIMATORS
from src.core.market_data import MarketDataAdapter
from src.core.types import NormalizedSnapshot, ProductMemory
from src.core.utils import bounded_append
from src.scripts.round_1.run_round1_fv_compare import (
    _PHASE1_PRODUCT_CONFIGS,
    _estimators_for,
)

_ROUND1_DATA_DIR = Path("data/raw/round_1")
_ROUND1_EDA_DIR = Path("outputs/round_1/eda")

# Residual horizon (steps). One step = 100 timestamp units in IMC data.
_RESIDUAL_HORIZONS: tuple[int, ...] = (1, 5, 20, 50)


# ---------------------------------------------------------------- helpers


def _pct(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    i = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * p))))
    return ordered[i]


def _mean(values: Iterable[float]) -> float | None:
    vals = list(values)
    return sum(vals) / len(vals) if vals else None


def _std(values: Iterable[float]) -> float | None:
    vals = list(values)
    return statistics.pstdev(vals) if len(vals) > 1 else None


def _safe_skew(values: Sequence[float]) -> float | None:
    if len(values) < 3:
        return None
    mu = statistics.mean(values)
    sigma = statistics.pstdev(values)
    if sigma == 0:
        return None
    return sum(((x - mu) / sigma) ** 3 for x in values) / len(values)


# ---------------------------------------------------------------- records


@dataclass(frozen=True)
class DossierRecord:
    day: int
    timestamp: int
    mid: float | None
    spread: float | None
    bid_price_1: int | None
    bid_volume_1: int | None
    ask_price_1: int | None
    ask_volume_1: int | None
    bid_levels: int
    ask_levels: int
    total_bid_volume: int
    total_ask_volume: int
    top_bid_volume: int
    top_ask_volume: int
    estimates: dict[str, float | None]
    trade_prices: tuple[float, ...]
    trade_quantities: tuple[int, ...]


def _collect_records(
    replay: ReplayEngine,
    *,
    product: str,
    product_config: ProductConfig,
    estimator_names: tuple[str, ...],
) -> list[DossierRecord]:
    adapter = MarketDataAdapter()
    memory = ProductMemory()
    records: list[DossierRecord] = []
    for step in replay.steps:
        if product not in step.rows_by_product:
            continue
        state = ReplayEngine.build_trading_state(
            step,
            trader_data="",
            position={product: 0},
            own_trades={},
        )
        snapshot = adapter.normalize_state(state).get(product)
        if snapshot is None:
            continue

        bids = list(snapshot.bids)
        asks = list(snapshot.asks)

        estimates: dict[str, float | None] = {}
        for est_name in estimator_names:
            estimator = ESTIMATORS.get(est_name)
            if estimator is None:
                estimates[est_name] = None
                continue
            fv = estimator.estimate(snapshot, memory, product_config)
            estimates[est_name] = fv.price if fv is not None else None

        trade_prices = tuple(t.price for t in snapshot.trades)
        trade_quantities = tuple(t.quantity for t in snapshot.trades)

        records.append(
            DossierRecord(
                day=step.day,
                timestamp=step.timestamp,
                mid=snapshot.mid,
                spread=snapshot.spread,
                bid_price_1=bids[0].price if bids else None,
                bid_volume_1=bids[0].volume if bids else None,
                ask_price_1=asks[0].price if asks else None,
                ask_volume_1=asks[0].volume if asks else None,
                bid_levels=len(bids),
                ask_levels=len(asks),
                total_bid_volume=snapshot.total_bid_volume(),
                total_ask_volume=snapshot.total_ask_volume(),
                top_bid_volume=bids[0].volume if bids else 0,
                top_ask_volume=asks[0].volume if asks else 0,
                estimates=estimates,
                trade_prices=trade_prices,
                trade_quantities=trade_quantities,
            )
        )

        # Update rolling memory so trend/EWMA/rolling estimators see history.
        if snapshot.mid is not None:
            bounded_append(memory.recent_mids, float(snapshot.mid), product_config.history_length)
        if snapshot.spread is not None:
            bounded_append(
                memory.recent_spreads, float(snapshot.spread), product_config.history_length
            )

    return records


# ---------------------------------------------------------------- stats


def _price_spread_stats(records: list[DossierRecord]) -> dict:
    """Per-day + combined stats on mid, spread, top-of-book volume."""
    by_day: dict[int, list[DossierRecord]] = defaultdict(list)
    for record in records:
        by_day[record.day].append(record)

    blocks: dict[str, dict] = {}
    for day, day_records in sorted(by_day.items()):
        two_sided = [r for r in day_records if r.mid is not None and r.spread is not None]
        mids = [r.mid for r in two_sided if r.mid is not None]
        spreads = [r.spread for r in two_sided if r.spread is not None]
        top_bid_vol = [r.top_bid_volume for r in two_sided]
        top_ask_vol = [r.top_ask_volume for r in two_sided]
        tot_bid_vol = [r.total_bid_volume for r in two_sided]
        tot_ask_vol = [r.total_ask_volume for r in two_sided]
        no_bid = sum(1 for r in day_records if r.bid_price_1 is None)
        no_ask = sum(1 for r in day_records if r.ask_price_1 is None)

        blocks[f"day_{day}"] = {
            "samples_total": len(day_records),
            "samples_two_sided": len(two_sided),
            "one_sided_no_bid": no_bid,
            "one_sided_no_ask": no_ask,
            "mid": {
                "min": min(mids) if mids else None,
                "max": max(mids) if mids else None,
                "mean": _mean(mids),
                "median": statistics.median(mids) if mids else None,
                "std": _std(mids),
                "p05": _pct(mids, 0.05),
                "p25": _pct(mids, 0.25),
                "p75": _pct(mids, 0.75),
                "p95": _pct(mids, 0.95),
            },
            "spread": {
                "min": min(spreads) if spreads else None,
                "max": max(spreads) if spreads else None,
                "mean": _mean(spreads),
                "median": statistics.median(spreads) if spreads else None,
                "std": _std(spreads),
                "p25": _pct(spreads, 0.25),
                "p50": _pct(spreads, 0.50),
                "p75": _pct(spreads, 0.75),
                "p95": _pct(spreads, 0.95),
                "histogram": dict(sorted(Counter(int(s) for s in spreads).items())),
            },
            "top_bid_volume": {
                "mean": _mean(top_bid_vol),
                "median": statistics.median(top_bid_vol) if top_bid_vol else None,
                "p95": _pct(top_bid_vol, 0.95),
                "max": max(top_bid_vol) if top_bid_vol else None,
            },
            "top_ask_volume": {
                "mean": _mean(top_ask_vol),
                "median": statistics.median(top_ask_vol) if top_ask_vol else None,
                "p95": _pct(top_ask_vol, 0.95),
                "max": max(top_ask_vol) if top_ask_vol else None,
            },
            "total_bid_volume": {
                "mean": _mean(tot_bid_vol),
                "median": statistics.median(tot_bid_vol) if tot_bid_vol else None,
            },
            "total_ask_volume": {
                "mean": _mean(tot_ask_vol),
                "median": statistics.median(tot_ask_vol) if tot_ask_vol else None,
            },
            "book_levels_bid_mean": _mean(r.bid_levels for r in day_records),
            "book_levels_ask_mean": _mean(r.ask_levels for r in day_records),
        }

    # Time-slice stats: split each day into 4 quartiles of timestamp and
    # compute mean mid + mean spread to flag intraday drift.
    slices: dict[str, dict] = {}
    for day, day_records in sorted(by_day.items()):
        two_sided = [r for r in day_records if r.mid is not None and r.spread is not None]
        if len(two_sided) < 4:
            continue
        two_sided.sort(key=lambda r: r.timestamp)
        bucket_size = len(two_sided) // 4
        for q in range(4):
            bucket = two_sided[q * bucket_size : (q + 1) * bucket_size]
            if not bucket:
                continue
            mids = [r.mid for r in bucket if r.mid is not None]
            spreads = [r.spread for r in bucket if r.spread is not None]
            slices[f"day_{day}_q{q + 1}"] = {
                "t_range": [bucket[0].timestamp, bucket[-1].timestamp],
                "samples": len(bucket),
                "mid_mean": _mean(mids),
                "mid_std": _std(mids),
                "spread_mean": _mean(spreads),
            }

    return {"per_day": blocks, "quartile_slices": slices}


def _estimator_residuals(
    records: list[DossierRecord], estimator_names: tuple[str, ...]
) -> dict:
    """For each estimator, compute residual = mid - estimate statistics
    and a short-horizon mean-reversion proxy (corr between residual and
    future price change)."""

    residual_blocks: dict[str, dict] = {}
    n_records = len(records)

    for est in estimator_names:
        residuals: list[float] = []
        future_returns_by_h: dict[int, list[tuple[float, float]]] = {h: [] for h in _RESIDUAL_HORIZONS}

        for i, record in enumerate(records):
            est_val = record.estimates.get(est)
            if est_val is None or record.mid is None:
                continue
            resid = record.mid - est_val
            residuals.append(resid)
            for h in _RESIDUAL_HORIZONS:
                j = i + h
                if j >= n_records:
                    continue
                future_mid = records[j].mid
                if future_mid is None:
                    continue
                future_returns_by_h[h].append((resid, future_mid - record.mid))

        if not residuals:
            residual_blocks[est] = {"samples": 0}
            continue

        block: dict = {
            "samples": len(residuals),
            "residual_mean": _mean(residuals),
            "residual_std": _std(residuals),
            "residual_median": statistics.median(residuals),
            "residual_skew": _safe_skew(residuals),
            "residual_abs_mean": _mean(abs(r) for r in residuals),
            "residual_p05": _pct(residuals, 0.05),
            "residual_p25": _pct(residuals, 0.25),
            "residual_p75": _pct(residuals, 0.75),
            "residual_p95": _pct(residuals, 0.95),
            "positive_fraction": sum(1 for r in residuals if r > 0) / len(residuals),
        }

        # Short-horizon mean-reversion proxy: Pearson correlation between
        # residual and future return. Negative correlation = residual
        # predicts a snap-back.
        reversion: dict[int, dict[str, float | None]] = {}
        for h, pairs in future_returns_by_h.items():
            if len(pairs) < 10:
                reversion[h] = {"samples": len(pairs), "correlation": None, "mean_return": None}
                continue
            r_vals = [p[0] for p in pairs]
            f_vals = [p[1] for p in pairs]
            r_mu = statistics.mean(r_vals)
            f_mu = statistics.mean(f_vals)
            r_sd = statistics.pstdev(r_vals)
            f_sd = statistics.pstdev(f_vals)
            if r_sd == 0 or f_sd == 0:
                corr: float | None = None
            else:
                cov = sum((r - r_mu) * (f - f_mu) for r, f in pairs) / len(pairs)
                corr = cov / (r_sd * f_sd)
            # Signed-return conditional on positive residual:
            pos_bucket = [f for r, f in pairs if r > 0]
            neg_bucket = [f for r, f in pairs if r < 0]
            reversion[h] = {
                "samples": len(pairs),
                "correlation_resid_vs_fwd_return": corr,
                "mean_fwd_return_pos_resid": _mean(pos_bucket),
                "mean_fwd_return_neg_resid": _mean(neg_bucket),
                "count_pos_resid": len(pos_bucket),
                "count_neg_resid": len(neg_bucket),
            }
        block["reversion_by_horizon"] = reversion
        residual_blocks[est] = block

    return residual_blocks


def _trend_fit(records: list[DossierRecord]) -> dict:
    """Day-level simple linear fit of mid vs timestamp, plus inter-day
    shift. Useful for flagging trend-fair products."""
    by_day: dict[int, list[DossierRecord]] = defaultdict(list)
    for record in records:
        if record.mid is not None:
            by_day[record.day].append(record)

    per_day: dict[str, dict] = {}
    for day, day_records in sorted(by_day.items()):
        xs = [float(r.timestamp) for r in day_records]
        ys = [float(r.mid) for r in day_records if r.mid is not None]
        if len(xs) < 2:
            continue
        mean_x = statistics.mean(xs)
        mean_y = statistics.mean(ys)
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
        den = sum((x - mean_x) ** 2 for x in xs)
        slope = num / den if den != 0 else None
        intercept = mean_y - slope * mean_x if slope is not None else None
        # Residuals around the fitted line
        residuals: list[float] = []
        if slope is not None and intercept is not None:
            residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys, strict=True)]
        per_day[f"day_{day}"] = {
            "slope_per_timestamp": slope,
            "slope_per_step": slope * 100.0 if slope is not None else None,
            "intercept": intercept,
            "residual_std": _std(residuals),
            "residual_abs_mean": _mean(abs(r) for r in residuals) if residuals else None,
        }

    # Inter-day level shift: compare day means
    day_means = {day: statistics.mean(r.mid for r in recs if r.mid is not None) for day, recs in by_day.items() if recs}
    days_sorted = sorted(day_means.items())
    inter_day_shifts = [
        {"from_day": a, "to_day": b, "delta_mean": day_means[b] - day_means[a]}
        for (a, _), (b, _) in zip(days_sorted, days_sorted[1:], strict=False)
    ]
    return {"per_day_fit": per_day, "inter_day_shifts": inter_day_shifts}


def _microstructure_flags(records: list[DossierRecord]) -> dict:
    """Simple bot / microstructure heuristics.

    - repeated top-of-book volumes (quote sizes that show up >N times)
    - one-sided book fraction
    - spread-spike fraction (spread >= median + 2*std)
    - trade-vs-mid offset histogram (how far from mid are printed trades)
    """
    bid_vols_top = [r.top_bid_volume for r in records if r.bid_volume_1 is not None]
    ask_vols_top = [r.top_ask_volume for r in records if r.ask_volume_1 is not None]
    bid_common = Counter(bid_vols_top).most_common(10)
    ask_common = Counter(ask_vols_top).most_common(10)

    one_sided = sum(1 for r in records if r.bid_price_1 is None or r.ask_price_1 is None)
    total = len(records)

    two_sided = [r for r in records if r.spread is not None]
    spreads = [r.spread for r in two_sided]
    spread_median = statistics.median(spreads) if spreads else 0.0
    spread_std = statistics.pstdev(spreads) if len(spreads) > 1 else 0.0
    spread_spike_threshold = spread_median + 2 * spread_std if spread_std > 0 else None
    spread_spike_fraction = (
        sum(1 for s in spreads if s >= spread_spike_threshold) / len(spreads)
        if spread_spike_threshold is not None and spreads
        else None
    )

    # Trade-offset: compare reported trade prices with the simultaneous snapshot mid.
    trade_offsets: list[float] = []
    for r in records:
        if r.mid is None:
            continue
        for tp in r.trade_prices:
            trade_offsets.append(tp - r.mid)

    offset_hist = Counter(round(o) for o in trade_offsets)

    return {
        "top_bid_volume_frequent_sizes": [
            {"volume": v, "count": c} for v, c in bid_common
        ],
        "top_ask_volume_frequent_sizes": [
            {"volume": v, "count": c} for v, c in ask_common
        ],
        "one_sided_fraction": one_sided / total if total else None,
        "spread_median": spread_median,
        "spread_std": spread_std,
        "spread_spike_threshold": spread_spike_threshold,
        "spread_spike_fraction": spread_spike_fraction,
        "trade_count": len(trade_offsets),
        "trade_offset_stats": {
            "mean": _mean(trade_offsets),
            "std": _std(trade_offsets),
            "median": statistics.median(trade_offsets) if trade_offsets else None,
            "min": min(trade_offsets) if trade_offsets else None,
            "max": max(trade_offsets) if trade_offsets else None,
            "p05": _pct(trade_offsets, 0.05),
            "p95": _pct(trade_offsets, 0.95),
        },
        "trade_offset_histogram": dict(sorted(offset_hist.items())),
    }


# ---------------------------------------------------------------- writers


def _write_product_report(out_dir: Path, product: str, report: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{product.lower()}_eda.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default))
    return path


def _json_default(value: object) -> object:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "__dict__"):
        return value.__dict__
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _run_id(label: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    clean = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
    return f"{stamp}_{clean}" if clean else stamp


# ---------------------------------------------------------------- entrypoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="round1_dossier_phase1")
    parser.add_argument("--data-dir", type=Path, default=_ROUND1_DATA_DIR)
    parser.add_argument(
        "--products", nargs="+", default=sorted(_PHASE1_PRODUCT_CONFIGS)
    )
    args = parser.parse_args()

    price_files = sorted(args.data_dir.glob("prices_round_1_day_*.csv"))
    trade_files = sorted(args.data_dir.glob("trades_round_1_day_*.csv"))
    if not price_files:
        raise SystemExit(f"No price files in {args.data_dir}")

    replay = ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)

    run_dir = _ROUND1_EDA_DIR / _run_id(args.label)
    run_dir.mkdir(parents=True, exist_ok=True)

    index_entries: list[dict] = []
    for product in args.products:
        product_config = _PHASE1_PRODUCT_CONFIGS.get(product)
        if product_config is None:
            print(f"[skip] {product}: no ProductConfig")
            continue
        estimator_names = _estimators_for(product_config)

        print(f"[{product}] collecting records …", flush=True)
        records = _collect_records(
            replay,
            product=product,
            product_config=product_config,
            estimator_names=estimator_names,
        )
        if not records:
            print(f"[{product}] no records found, skipping")
            continue

        report = {
            "product": product,
            "product_config": {
                "position_limit": product_config.position_limit,
                "fair_value_method": product_config.fair_value_method,
                "anchor_price": product_config.anchor_price,
                "taker_edge": product_config.taker_edge,
                "maker_edge": product_config.maker_edge,
                "history_length": product_config.history_length,
            },
            "estimators_evaluated": list(estimator_names),
            "samples_total": len(records),
            "price_spread_stats": _price_spread_stats(records),
            "trend_fit": _trend_fit(records),
            "estimator_residuals": _estimator_residuals(records, estimator_names),
            "microstructure_flags": _microstructure_flags(records),
        }
        path = _write_product_report(run_dir, product, report)
        size = path.stat().st_size
        index_entries.append({"product": product, "path": str(path), "bytes": size})
        print(f"[{product}] wrote {path} ({size:,} bytes)")

    (run_dir / "index.json").write_text(
        json.dumps(
            {
                "label": args.label,
                "generated_at": datetime.now(UTC).isoformat(),
                "data_dir": str(args.data_dir),
                "products": index_entries,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"\nIndex written to {run_dir / 'index.json'}")


if __name__ == "__main__":
    main()
