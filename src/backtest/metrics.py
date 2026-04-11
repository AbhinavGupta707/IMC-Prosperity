"""Aggregate metrics and per-trade records for a backtest run.

Phase 2B shipped the per-product aggregates (pnl, cash, position,
maker/taker decomposition, time near limit). Phase 4a adds:

- ``TradeRecord`` with decision-time **and** fill-time context, so we
  can compute entry edge from the fair value we believed at the
  moment we committed the order, and markouts from the execution
  price against future mids.
- Pure metric helpers (``compute_entry_edges``, ``compute_markouts``,
  ``weighted_mean``) that the simulator composes into the enriched
  ``ProductResult``/``SimulationResult``.

All helpers are deliberately pure: they do not touch state, do not
import matplotlib, and do not care how the series were collected.
They can be unit-tested in isolation without standing up a full
backtest run.

Sign convention:

- buy trade: ``edge = fair_value_at_decision - price``,
  ``markout_k = mid[fill_step + k] - price``
- sell trade: ``edge = price - fair_value_at_decision``,
  ``markout_k = price - mid[fill_step + k]``

Positive means the trade looks favourable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TradeSide = Literal["buy", "sell"]
TradeMode = Literal["taker", "maker"]
SeriesKey = tuple[int | None, int]


@dataclass(frozen=True)
class TradeRecord:
    """A single executed fill with its full decision and fill context."""

    product: str
    side: TradeSide
    price: float
    quantity: int
    mode: TradeMode
    decision_timestamp: int
    fill_timestamp: int
    fair_value_at_decision: float | None
    fair_value_method_at_decision: str | None
    mid_at_decision: float | None
    mid_at_fill: float | None
    decision_day: int | None = None
    fill_day: int | None = None

    def decision_key(self) -> SeriesKey:
        return (self.decision_day, self.decision_timestamp)

    def fill_key(self) -> SeriesKey:
        return (self.fill_day, self.fill_timestamp)


@dataclass(frozen=True)
class ProductResult:
    product: str
    pnl: float
    cash: float
    final_position: int
    mark_price: float | None
    order_count: int
    trade_count: int
    taker_trade_count: int
    maker_trade_count: int
    taker_trade_quantity: int
    maker_trade_quantity: int
    buy_trade_quantity: int
    sell_trade_quantity: int
    steps_near_limit: int
    avg_entry_edge: float | None = None
    entry_edge_count: int = 0
    avg_markout_1: float | None = None
    markout_1_count: int = 0
    avg_markout_5: float | None = None
    markout_5_count: int = 0
    avg_markout_20: float | None = None
    markout_20_count: int = 0


# Step-indexed time series: list of (timestamp, value) pairs in order.
TimeSeries = tuple[tuple[int, float], ...]


@dataclass(frozen=True)
class SimulationResult:
    steps: int
    total_pnl: float
    per_product: dict[str, ProductResult] = field(default_factory=dict)
    trade_records: tuple[TradeRecord, ...] = ()
    mid_series: dict[str, TimeSeries] = field(default_factory=dict)
    fair_value_series: dict[str, TimeSeries] = field(default_factory=dict)
    pnl_series: dict[str, TimeSeries] = field(default_factory=dict)
    mid_keys: dict[str, tuple[SeriesKey, ...]] = field(default_factory=dict)
    fair_value_keys: dict[str, tuple[SeriesKey, ...]] = field(default_factory=dict)
    pnl_keys: dict[str, tuple[SeriesKey, ...]] = field(default_factory=dict)

    def summary_table(self) -> str:
        header = (
            f"{'product':<10} {'pnl':>10} {'cash':>12} {'pos':>4} "
            f"{'mark':>9} {'trades':>7} {'tk_q':>6} {'mk_q':>6} "
            f"{'buy_q':>6} {'sell_q':>7} {'near_lim':>9}"
        )
        lines = [header, "-" * len(header)]
        for product in sorted(self.per_product):
            r = self.per_product[product]
            mark = f"{r.mark_price:.2f}" if r.mark_price is not None else "   n/a"
            lines.append(
                f"{product:<10} {r.pnl:>10.2f} {r.cash:>12.2f} {r.final_position:>4d} "
                f"{mark:>9} {r.trade_count:>7d} {r.taker_trade_quantity:>6d} "
                f"{r.maker_trade_quantity:>6d} {r.buy_trade_quantity:>6d} "
                f"{r.sell_trade_quantity:>7d} {r.steps_near_limit:>9d}"
            )
        lines.append("-" * len(header))
        lines.append(f"{'TOTAL':<10} {self.total_pnl:>10.2f}")

        # Second block: entry edge + markouts with sample counts.
        lines.append("")
        edge_header = (
            f"{'product':<10} {'edge':>8} {'edge_n':>7} "
            f"{'mk_1':>8} {'mk_1_n':>7} {'mk_5':>8} {'mk_5_n':>7} "
            f"{'mk_20':>8} {'mk_20_n':>7}"
        )
        lines.append(edge_header)
        lines.append("-" * len(edge_header))
        for product in sorted(self.per_product):
            r = self.per_product[product]
            lines.append(
                f"{product:<10} "
                f"{_fmt(r.avg_entry_edge):>8} {r.entry_edge_count:>7d} "
                f"{_fmt(r.avg_markout_1):>8} {r.markout_1_count:>7d} "
                f"{_fmt(r.avg_markout_5):>8} {r.markout_5_count:>7d} "
                f"{_fmt(r.avg_markout_20):>8} {r.markout_20_count:>7d}"
            )
        lines.append("-" * len(edge_header))
        return "\n".join(lines)


# ---------------------------------------------------------------- helpers


def weighted_mean(values: list[float], weights: list[float]) -> float | None:
    """Return the weight-weighted mean, or ``None`` if no weight accrued.

    Using a list-of-floats signature keeps the helper trivially pure;
    callers filter out ``None`` values themselves.
    """
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")
    total_weight = 0.0
    total = 0.0
    for value, weight in zip(values, weights, strict=True):
        if weight <= 0:
            continue
        total_weight += weight
        total += value * weight
    if total_weight <= 0:
        return None
    return total / total_weight


def compute_entry_edges(
    records: list[TradeRecord] | tuple[TradeRecord, ...],
) -> dict[str, tuple[float | None, int]]:
    """Compute quantity-weighted average entry edge per product.

    Returns ``{product: (avg_edge_or_None, record_count)}``. A record
    contributes only if ``fair_value_at_decision`` is not ``None``.
    The count is the number of records that contributed, not the
    quantity sum.
    """
    buckets: dict[str, list[tuple[float, float]]] = {}
    for record in records:
        fair = record.fair_value_at_decision
        if fair is None:
            continue
        sign = 1.0 if record.side == "buy" else -1.0
        edge = sign * (fair - record.price)
        buckets.setdefault(record.product, []).append((edge, float(record.quantity)))

    out: dict[str, tuple[float | None, int]] = {}
    for product, entries in buckets.items():
        values = [edge for edge, _ in entries]
        weights = [weight for _, weight in entries]
        out[product] = (weighted_mean(values, weights), len(entries))
    return out


def compute_markouts(
    records: list[TradeRecord] | tuple[TradeRecord, ...],
    mid_series: dict[str, TimeSeries],
    horizons: list[int] | tuple[int, ...],
    *,
    mid_keys: dict[str, tuple[SeriesKey, ...]] | None = None,
) -> dict[str, dict[int, tuple[float | None, int]]]:
    """Compute quantity-weighted average markouts per product per horizon.

    ``mid_series`` is the visible-mid series collected by the
    simulator (NOT the carry-forward PnL series). Markouts use only
    observable mids so we do not manufacture future prices.

    Returns ``{product: {horizon: (avg_markout_or_None, count)}}``.
    Missing horizons (run too short, or one-sided book at
    ``fill_step + k``) drop records out of that horizon's average.
    """
    # Pre-index mid_series by (product, day, timestamp) -> step_index for O(1) lookup.
    index_by_product: dict[str, dict[SeriesKey, int]] = {}
    for product, series in mid_series.items():
        keys = _series_keys_or_legacy(series, None if mid_keys is None else mid_keys.get(product))
        index_by_product[product] = {key: idx for idx, key in enumerate(keys)}

    buckets: dict[str, dict[int, list[tuple[float, float]]]] = {}
    counts: dict[str, dict[int, int]] = {}
    for horizon in horizons:
        # Ensure every product that has records gets a bucket per horizon later,
        # even if zero records contribute. Handled lazily below.
        _ = horizon

    for record in records:
        product = record.product
        product_series = mid_series.get(product)
        idx_map = index_by_product.get(product)
        if product_series is None or idx_map is None or not product_series:
            continue
        fill_index = idx_map.get(record.fill_key())
        if fill_index is None:
            continue
        sign = 1.0 if record.side == "buy" else -1.0
        product_buckets = buckets.setdefault(product, {})
        product_counts = counts.setdefault(product, {})
        for horizon in horizons:
            future_index = fill_index + horizon
            if future_index < 0 or future_index >= len(product_series):
                continue
            future_mid = product_series[future_index][1]
            markout = sign * (future_mid - record.price)
            product_buckets.setdefault(horizon, []).append((markout, float(record.quantity)))
            product_counts[horizon] = product_counts.get(horizon, 0) + 1

    out: dict[str, dict[int, tuple[float | None, int]]] = {}
    for product, horizon_map in buckets.items():
        out[product] = {}
        for horizon, entries in horizon_map.items():
            values = [markout for markout, _ in entries]
            weights = [weight for _, weight in entries]
            out[product][horizon] = (
                weighted_mean(values, weights),
                counts[product].get(horizon, 0),
            )
    return out


def _series_keys_or_legacy(
    series: TimeSeries,
    keys: tuple[SeriesKey, ...] | None,
) -> tuple[SeriesKey, ...]:
    if keys is None:
        return tuple((None, ts) for ts, _ in series)
    if len(keys) != len(series):
        raise ValueError(
            "series keys must have the same length as the corresponding series "
            f"(got {len(keys)} keys for {len(series)} points)"
        )
    return keys


def _fmt(value: float | None) -> str:
    return f"{value:+.3f}" if value is not None else "n/a"
