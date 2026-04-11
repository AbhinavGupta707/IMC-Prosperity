"""Timestamp-level drilldowns for Phase 4a review packs.

Phase 4b builds on top of the enriched review packs that Phase 4a
persists under ``outputs/review_packs/<run_id>/``. A reviewer spots a
trade or a near-limit stretch in the aggregate charts, asks the
drilldown tool to zoom in, and gets a per-case directory with a
window slice of the series, a rebuilt snapshot of the local book,
per-case charts, and a structured notes template.

Design rules, echoing Phase 4a:

- Pure module. No matplotlib imports here — chart rendering lives in
  ``drilldown_charts``. That keeps this module cheap to unit test and
  safe to run on headless CI.
- Read-only against the review pack. The drilldown tool never
  rewrites the source pack's artifacts.
- Book snapshots are rebuilt on demand by re-replaying the manifest's
  CSVs. Phase 4a intentionally does not persist books at run time;
  replaying a small timestamp slice is cheap and keeps the simulator
  surface unchanged.
- Sign conventions mirror ``src.backtest.metrics``: buys score
  ``fair - price`` / ``future_mid - price``, sells flip.

See ``docs/phase_4_review_discipline_note.md`` for the human-facing
workflow and ``src/scripts/run_drilldown.py`` for the CLI entry point.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from src.backtest.metrics import SeriesKey, TradeRecord
from src.backtest.replay_engine import _order_depth_from_row
from src.datamodel import OrderDepth

_NEAR_LIMIT_FRACTION = 0.75
DEFAULT_WINDOW_RADIUS = 30
DEFAULT_RANK_METRIC: RankMetric = "markout_5"
_PRICE_CSV_REQUIRED_COLUMNS = ("day", "timestamp", "product", "bid_price_1")


class DrilldownError(RuntimeError):
    """Raised when a drilldown cannot be produced for a structural reason.

    Used for missing/unreadable manifest CSVs, malformed price rows,
    and other preconditions that the user should see explicitly
    instead of getting an empty window back.
    """


RankMetric = Literal["edge", "markout_1", "markout_5", "markout_20"]
_MARKOUT_METRICS: dict[str, int] = {
    "markout_1": 1,
    "markout_5": 5,
    "markout_20": 20,
}

CaseKind = Literal["trade", "best", "worst", "timestamp", "near_limit"]


# -------------------------------------------------------------- dataclasses


@dataclass(frozen=True)
class BookSnapshot:
    """Visible book at a single timestamp rebuilt from the manifest CSVs."""

    timestamp: int
    product: str
    bids: tuple[tuple[int, int], ...]  # (price, volume), volumes positive
    asks: tuple[tuple[int, int], ...]  # (price, volume), volumes positive
    day: int | None = None

    @property
    def best_bid(self) -> int | None:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> int | None:
        return self.asks[0][0] if self.asks else None

    @property
    def mid(self) -> float | None:
        if not self.bids or not self.asks:
            return None
        return (self.bids[0][0] + self.asks[0][0]) / 2.0


@dataclass(frozen=True)
class ReviewPack:
    """Parsed, in-memory view of a Phase 4a review pack.

    Carries the manifest, trades, and step-indexed series together
    with pre-indexed lookup tables so selectors can find a step by
    timestamp in O(1). Treat instances as immutable.
    """

    pack_dir: Path
    run_id: str
    manifest: dict[str, Any]
    summary: dict[str, Any]
    trades: tuple[TradeRecord, ...]
    mid_series: dict[str, tuple[tuple[int, float], ...]]
    fair_value_series: dict[str, tuple[tuple[int, float], ...]]
    pnl_series: dict[str, tuple[tuple[int, float], ...]]
    mid_keys: dict[str, tuple[SeriesKey, ...]] = field(default_factory=dict)
    fair_value_keys: dict[str, tuple[SeriesKey, ...]] = field(default_factory=dict)
    pnl_keys: dict[str, tuple[SeriesKey, ...]] = field(default_factory=dict)
    mid_index_by_product: dict[str, dict[object, int]] = field(default_factory=dict)
    pnl_index_by_product: dict[str, dict[SeriesKey, int]] = field(default_factory=dict)

    def products(self) -> list[str]:
        return sorted(self.mid_series)

    def position_limit(self, product: str) -> int | None:
        products = (self.manifest.get("engine_config") or {}).get("products") or {}
        entry = products.get(product)
        if entry is None:
            return None
        limit = entry.get("position_limit")
        return int(limit) if isinstance(limit, (int, float)) else None

    def data_files(self) -> list[Path]:
        return [Path(p) for p in self.manifest.get("data_files", [])]


@dataclass(frozen=True)
class DrilldownCase:
    """One drilldown request, bound to a product and an anchor timestamp.

    ``kind`` tags the selection mode so downstream artifacts can show
    the caller which flag generated this case. ``rank_metric`` /
    ``rank_score`` are populated for best/worst cases. ``extra``
    carries free-form metadata (e.g. near-limit position, |pos|/limit
    ratio, trade fields for --trade-id).
    """

    case_id: str
    kind: CaseKind
    product: str
    anchor_timestamp: int
    anchor_day: int | None = None
    trade_index: int | None = None
    rank_metric: RankMetric | None = None
    rank_score: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseWindow:
    """Series slice plus rebuilt book snapshots for one drilldown case."""

    product: str
    anchor_timestamp: int
    anchor_day: int | None
    window_radius: int
    start_timestamp: int
    start_day: int | None
    end_timestamp: int
    end_day: int | None
    mid_slice: tuple[tuple[int, float], ...]
    fair_value_slice: tuple[tuple[int, float], ...]
    pnl_slice: tuple[tuple[int, float], ...]
    position_slice: tuple[tuple[int, int], ...]
    trades_in_window: tuple[TradeRecord, ...]
    book_snapshots: tuple[BookSnapshot, ...]


# ------------------------------------------------------------------ loader


def load_review_pack(pack_dir: Path | str) -> ReviewPack:
    """Read a Phase 4a review pack directory into a ``ReviewPack``.

    The loader is strict about required files (manifest, trades, series,
    summary). It is tolerant of missing optional keys — e.g. a pack
    generated without charts still has a valid manifest.
    """
    directory = Path(pack_dir)
    manifest = _read_json(directory / "manifest.json")
    summary = _read_json(directory / "summary.json")
    trades_payload = _read_json(directory / "trades.json")
    series_payload = _read_json(directory / "series.json")

    trades = tuple(_trade_from_dict(t) for t in trades_payload.get("trades", []))
    mid_series = _parse_series(series_payload.get("mid_series", {}))
    fair_value_series = _parse_series(series_payload.get("fair_value_series", {}))
    pnl_series = _parse_series(series_payload.get("pnl_series", {}))
    mid_keys = _parse_series_keys(series_payload.get("mid_keys", {}), mid_series)
    fair_value_keys = _parse_series_keys(
        series_payload.get("fair_value_keys", {}),
        fair_value_series,
    )
    pnl_keys = _parse_series_keys(series_payload.get("pnl_keys", {}), pnl_series)

    mid_index_by_product = {
        product: _build_series_index(keys) for product, keys in mid_keys.items()
    }
    pnl_index_by_product = {
        product: {key: idx for idx, key in enumerate(keys)} for product, keys in pnl_keys.items()
    }

    run_id = manifest.get("run_id") or directory.name

    return ReviewPack(
        pack_dir=directory,
        run_id=str(run_id),
        manifest=manifest,
        summary=summary,
        trades=trades,
        mid_series=mid_series,
        fair_value_series=fair_value_series,
        pnl_series=pnl_series,
        mid_keys=mid_keys,
        fair_value_keys=fair_value_keys,
        pnl_keys=pnl_keys,
        mid_index_by_product=mid_index_by_product,
        pnl_index_by_product=pnl_index_by_product,
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Review pack is missing {path.name}: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"Review pack file {path} must contain a JSON object")
    return payload


def _parse_series(
    raw: dict[str, Any],
) -> dict[str, tuple[tuple[int, float], ...]]:
    parsed: dict[str, tuple[tuple[int, float], ...]] = {}
    for product, points in raw.items():
        parsed[product] = tuple((int(ts), float(value)) for ts, value in points)
    return parsed


def _parse_series_keys(
    raw: dict[str, Any],
    series: dict[str, tuple[tuple[int, float], ...]],
) -> dict[str, tuple[SeriesKey, ...]]:
    parsed: dict[str, tuple[SeriesKey, ...]] = {}
    for product, points in series.items():
        raw_points = raw.get(product)
        if raw_points is None:
            parsed[product] = tuple((None, ts) for ts, _ in points)
            continue
        keys = tuple(
            (
                None if day is None else int(day),
                int(timestamp),
            )
            for day, timestamp in raw_points
        )
        if len(keys) != len(points):
            raise ValueError(
                "series key length mismatch for product "
                f"{product!r}: {len(keys)} keys vs {len(points)} values"
            )
        parsed[product] = keys
    return parsed


def _build_series_index(keys: tuple[SeriesKey, ...]) -> dict[object, int]:
    index: dict[object, int] = {}
    timestamp_counts: dict[int, int] = {}
    for _, timestamp in keys:
        timestamp_counts[timestamp] = timestamp_counts.get(timestamp, 0) + 1
    for idx, key in enumerate(keys):
        index[key] = idx
        if timestamp_counts[key[1]] == 1:
            index[key[1]] = idx
    return index


def _trade_from_dict(payload: dict[str, Any]) -> TradeRecord:
    return TradeRecord(
        product=str(payload["product"]),
        side=payload["side"],
        price=float(payload["price"]),
        quantity=int(payload["quantity"]),
        mode=payload["mode"],
        decision_timestamp=int(payload["decision_timestamp"]),
        fill_timestamp=int(payload["fill_timestamp"]),
        fair_value_at_decision=_opt_float(payload.get("fair_value_at_decision")),
        fair_value_method_at_decision=payload.get("fair_value_method_at_decision"),
        mid_at_decision=_opt_float(payload.get("mid_at_decision")),
        mid_at_fill=_opt_float(payload.get("mid_at_fill")),
        decision_day=_opt_int(payload.get("decision_day")),
        fill_day=_opt_int(payload.get("fill_day")),
    )


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


# ------------------------------------------------------------------ scoring


def trade_score(
    record: TradeRecord,
    mid_series: dict[str, tuple[tuple[int, float], ...]],
    mid_index: dict[str, dict[object, int]],
    metric: RankMetric,
) -> float | None:
    """Per-unit score for one trade, matching the Phase 4a sign convention.

    Returns ``None`` when the metric cannot be computed for this record
    (missing decision-time fair value for ``edge``, or the fill step is
    too close to the end of the replay for markouts).
    """
    sign = 1.0 if record.side == "buy" else -1.0
    if metric == "edge":
        fair = record.fair_value_at_decision
        if fair is None:
            return None
        return sign * (fair - record.price)

    horizon = _MARKOUT_METRICS.get(metric)
    if horizon is None:
        raise ValueError(f"Unknown rank metric: {metric}")
    series = mid_series.get(record.product, ())
    index_map = mid_index.get(record.product, {})
    fill_idx = index_map.get(record.fill_key())
    if fill_idx is None:
        fill_idx = index_map.get(record.fill_timestamp)
    if fill_idx is None:
        return None
    future_idx = fill_idx + horizon
    if future_idx < 0 or future_idx >= len(series):
        return None
    future_mid = series[future_idx][1]
    return sign * (future_mid - record.price)


def rank_trades(pack: ReviewPack, metric: RankMetric) -> list[tuple[float, int, TradeRecord]]:
    """Return (score, trade_index, record) descending, dropping None scores."""
    scored: list[tuple[float, int, TradeRecord]] = []
    for idx, record in enumerate(pack.trades):
        score = trade_score(record, pack.mid_series, pack.mid_index_by_product, metric)
        if score is None:
            continue
        scored.append((score, idx, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


# ------------------------------------------------------------------ selectors


def select_best_trades(pack: ReviewPack, n: int, metric: RankMetric) -> list[DrilldownCase]:
    ranked = rank_trades(pack, metric)
    return [
        _trade_case(
            kind="best",
            pack=pack,
            rank=rank,
            idx=idx,
            record=record,
            metric=metric,
            score=score,
        )
        for rank, (score, idx, record) in enumerate(ranked[:n], start=1)
    ]


def select_worst_trades(pack: ReviewPack, n: int, metric: RankMetric) -> list[DrilldownCase]:
    ranked = rank_trades(pack, metric)
    worst = list(reversed(ranked))[:n]
    return [
        _trade_case(
            kind="worst",
            pack=pack,
            rank=rank,
            idx=idx,
            record=record,
            metric=metric,
            score=score,
        )
        for rank, (score, idx, record) in enumerate(worst, start=1)
    ]


def select_by_trade_id(pack: ReviewPack, trade_index: int) -> DrilldownCase:
    if trade_index < 0 or trade_index >= len(pack.trades):
        raise IndexError(
            f"trade_index {trade_index} out of range for pack with " f"{len(pack.trades)} trades"
        )
    record = pack.trades[trade_index]
    case_id = _case_id(
        "trade",
        str(trade_index),
        record.product,
        _day_slug(record.fill_day),
        str(record.fill_timestamp),
    )
    return DrilldownCase(
        case_id=case_id,
        kind="trade",
        product=record.product,
        anchor_timestamp=record.fill_timestamp,
        anchor_day=record.fill_day,
        trade_index=trade_index,
        extra=_trade_extras(record),
    )


def select_by_timestamp(
    pack: ReviewPack, product: str, timestamp: int, day: int | None = None
) -> DrilldownCase:
    if product not in pack.mid_series:
        raise KeyError(f"product {product!r} not present in review pack")
    anchor_day = _resolve_anchor_day(pack, product, timestamp, day)
    case_id = _case_id("timestamp", product, _day_slug(anchor_day), str(timestamp))
    # Look up a nearby trade record for convenience; it's not required.
    matching = [
        i
        for i, t in enumerate(pack.trades)
        if t.product == product and t.fill_timestamp == timestamp and t.fill_day == anchor_day
    ]
    extra: dict[str, Any] = {"trade_indices": matching, "day": anchor_day}
    return DrilldownCase(
        case_id=case_id,
        kind="timestamp",
        product=product,
        anchor_timestamp=timestamp,
        anchor_day=anchor_day,
        extra=extra,
    )


def select_near_limit(
    pack: ReviewPack,
    n: int,
    *,
    near_limit_fraction: float = _NEAR_LIMIT_FRACTION,
) -> list[DrilldownCase]:
    """Pick the N steps where ``|position| / limit`` is largest.

    Walks the reconstructed position series for every product that has
    a configured ``position_limit`` in the manifest, filters to steps
    above ``near_limit_fraction``, and returns the highest-ratio
    examples. Ties are broken by earliest timestamp so the output is
    deterministic.
    """
    candidates: list[tuple[float, int, str, int | None, int]] = []
    for product in pack.products():
        limit = pack.position_limit(product)
        if limit is None or limit <= 0:
            continue
        threshold = near_limit_fraction * limit
        positions = _reconstruct_position_path(pack, product)
        for key, pos in positions:
            abs_pos = abs(pos)
            if abs_pos < threshold:
                continue
            ratio = abs_pos / float(limit)
            candidates.append((ratio, pos, product, key[0], key[1]))

    # Descending by ratio, break ties by timestamp ascending for determinism.
    candidates.sort(
        key=lambda item: (
            -item[0],
            item[3] if item[3] is not None else 0,
            item[4],
        )
    )
    cases: list[DrilldownCase] = []
    for rank, (ratio, pos, product, day, ts) in enumerate(candidates[:n], start=1):
        case_id = _case_id("near_limit", str(rank), product, _day_slug(day), str(ts))
        cases.append(
            DrilldownCase(
                case_id=case_id,
                kind="near_limit",
                product=product,
                anchor_timestamp=ts,
                anchor_day=day,
                extra={
                    "rank": rank,
                    "position": pos,
                    "position_limit": pack.position_limit(product),
                    "abs_ratio": ratio,
                    "day": day,
                },
            )
        )
    return cases


# ---------------------------------------------------- position reconstruction


def reconstruct_position_series(
    trades: tuple[TradeRecord, ...] | list[TradeRecord],
    pnl_series: dict[str, tuple[tuple[int, float], ...]],
    product: str,
) -> list[tuple[int, int]]:
    """Rebuild the per-step position path for one product.

    Uses the pnl series as the step grid (it is gap-free even on
    one-sided books, unlike ``mid_series``) and walks the trade
    records to accumulate signed-quantity deltas at each fill step.
    The result is a sequence of ``(timestamp, position)`` tuples of
    the same length as ``pnl_series[product]``.
    """
    series = pnl_series.get(product, ())
    if not series:
        return []

    deltas: dict[int, int] = {}
    for record in trades:
        if record.product != product:
            continue
        delta = record.quantity if record.side == "buy" else -record.quantity
        deltas[record.fill_timestamp] = deltas.get(record.fill_timestamp, 0) + delta

    path: list[tuple[int, int]] = []
    position = 0
    for ts, _ in series:
        position += deltas.get(ts, 0)
        path.append((ts, position))
    return path


def _reconstruct_position_path(
    pack: ReviewPack,
    product: str,
) -> list[tuple[SeriesKey, int]]:
    series = pack.pnl_keys.get(product, ())
    if not series:
        return []

    deltas: dict[SeriesKey, int] = {}
    for record in pack.trades:
        if record.product != product:
            continue
        delta = record.quantity if record.side == "buy" else -record.quantity
        key = record.fill_key()
        deltas[key] = deltas.get(key, 0) + delta

    position = 0
    path: list[tuple[SeriesKey, int]] = []
    for key in series:
        position += deltas.get(key, 0)
        path.append((key, position))
    return path


# ------------------------------------------------------------ window slicing


def build_case_window(
    case: DrilldownCase,
    pack: ReviewPack,
    *,
    window_radius: int = DEFAULT_WINDOW_RADIUS,
) -> CaseWindow:
    """Slice ``pack`` around ``case.anchor_timestamp`` into a window.

    The radius is measured in **steps** along the mid series (not
    timestamps) so windows are stable regardless of the step cadence.
    When the anchor timestamp is missing from the mid series (e.g.
    one-sided book), the function falls back to the closest step in
    the pnl series.
    """
    product = case.product
    mid_series = pack.mid_series.get(product, ())
    pnl_series = pack.pnl_series.get(product, ())
    if not pnl_series:
        raise ValueError(
            f"Review pack has no pnl series for product {product!r}; "
            "cannot build a drilldown window"
        )

    pnl_keys = pack.pnl_keys.get(product, ())
    if not pnl_keys:
        raise ValueError(
            f"Review pack has no pnl keys for product {product!r}; "
            "cannot build a drilldown window"
        )

    anchor_key = (case.anchor_day, case.anchor_timestamp)
    anchor_idx = _index_of_or_nearest_key(pnl_keys, anchor_key)
    lo = max(0, anchor_idx - window_radius)
    hi = min(len(pnl_keys) - 1, anchor_idx + window_radius)
    start_key = pnl_keys[lo]
    end_key = pnl_keys[hi]

    pnl_index = pack.pnl_index_by_product.get(product, {})
    mid_slice = _slice_series_by_keys(
        mid_series,
        pack.mid_keys.get(product, ()),
        pnl_index,
        lo,
        hi,
    )
    fair_slice = _slice_series_by_keys(
        pack.fair_value_series.get(product, ()),
        pack.fair_value_keys.get(product, ()),
        pnl_index,
        lo,
        hi,
    )
    pnl_slice = tuple(pnl_series[lo : hi + 1])

    positions = _reconstruct_position_path(pack, product)
    position_slice = tuple((key[1], position) for key, position in positions[lo : hi + 1])

    trades_in_window = tuple(
        record
        for record in pack.trades
        if record.product == product
        and (idx := pnl_index.get(record.fill_key())) is not None
        and lo <= idx <= hi
    )

    book_snapshots = rebuild_books_for_window(
        data_files=pack.data_files(),
        product=product,
        window_keys=tuple(pnl_keys[lo : hi + 1]),
    )

    return CaseWindow(
        product=product,
        anchor_timestamp=case.anchor_timestamp,
        anchor_day=case.anchor_day,
        window_radius=window_radius,
        start_timestamp=start_key[1],
        start_day=start_key[0],
        end_timestamp=end_key[1],
        end_day=end_key[0],
        mid_slice=mid_slice,
        fair_value_slice=fair_slice,
        pnl_slice=pnl_slice,
        position_slice=position_slice,
        trades_in_window=trades_in_window,
        book_snapshots=book_snapshots,
    )


def _slice_series(
    series: tuple[tuple[int, float], ...], start_ts: int, end_ts: int
) -> tuple[tuple[int, float], ...]:
    return tuple((ts, v) for ts, v in series if start_ts <= ts <= end_ts)


def _slice_series_by_keys(
    series: tuple[tuple[int, float], ...],
    keys: tuple[SeriesKey, ...],
    pnl_index: dict[SeriesKey, int],
    lo: int,
    hi: int,
) -> tuple[tuple[int, float], ...]:
    if not series:
        return ()
    if not keys:
        return tuple(series[lo : hi + 1])
    sliced: list[tuple[int, float]] = []
    for point, key in zip(series, keys, strict=True):
        idx = pnl_index.get(key)
        if idx is None or idx < lo or idx > hi:
            continue
        sliced.append(point)
    return tuple(sliced)


def _index_of_or_nearest(timestamps: list[int], target: int) -> int:
    """Return the index of ``target`` in ``timestamps``, else the nearest.

    Used as a safety net when the caller asks for a timestamp that
    doesn't exist in the grid (e.g. a near-limit step recorded on a
    one-sided book, which is present in the pnl series but not the
    mid series).
    """
    if not timestamps:
        raise ValueError("cannot anchor a window against an empty timestamp grid")
    # Fast path: exact hit.
    lo, hi = 0, len(timestamps) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        ts = timestamps[mid]
        if ts == target:
            return mid
        if ts < target:
            lo = mid + 1
        else:
            hi = mid - 1
    # lo now points at the first timestamp > target (or len), hi at <= target.
    if lo >= len(timestamps):
        return len(timestamps) - 1
    if hi < 0:
        return 0
    before = timestamps[hi]
    after = timestamps[lo]
    return hi if (target - before) <= (after - target) else lo


def _index_of_or_nearest_key(keys: tuple[SeriesKey, ...], target: SeriesKey) -> int:
    if not keys:
        raise ValueError("cannot anchor a window against an empty key grid")
    for idx, key in enumerate(keys):
        if key == target:
            return idx

    target_day, target_ts = target
    if target_day is not None:
        same_day = [idx for idx, key in enumerate(keys) if key[0] == target_day]
        if same_day:
            return min(same_day, key=lambda idx: abs(keys[idx][1] - target_ts))

    return min(
        range(len(keys)),
        key=lambda idx: _key_distance(keys[idx], target),
    )


def _key_distance(a: SeriesKey, b: SeriesKey) -> tuple[int, int]:
    a_day, a_ts = a
    b_day, b_ts = b
    day_penalty = 0 if a_day == b_day else 1
    return (day_penalty, abs(a_ts - b_ts))


# ------------------------------------------------------------- book rebuild


def rebuild_books_for_window(
    *,
    data_files: list[Path],
    product: str,
    window_keys: tuple[SeriesKey, ...] | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> tuple[BookSnapshot, ...]:
    """Re-parse price CSVs to reconstruct book snapshots for a window.

    Rows are selected in one of two ways:

    - preferred: exact ``window_keys`` matching ``(day, timestamp)``
    - legacy compatibility: plain ``start_ts`` / ``end_ts`` filtering

    Trade CSVs are ignored — drilldowns don't need the trade tape,
    just the visible book shape.

    Raises ``DrilldownError`` when the manifest does not list any
    price CSVs, when a listed price CSV is missing from disk, or when
    a CSV is present but missing the required columns. This is
    deliberately stricter than "silently skip" so a broken manifest
    produces a readable error instead of an empty window.
    """
    price_paths = _classify_price_csvs(data_files)
    wanted = set(window_keys or ())
    snapshots: list[BookSnapshot] = []
    for path in price_paths:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            _validate_price_csv_columns(path, reader.fieldnames)
            for row in reader:
                if row.get("product") != product:
                    continue
                try:
                    day = int(row["day"])
                    ts = int(row["timestamp"])
                except (KeyError, ValueError) as exc:
                    raise DrilldownError(
                        f"malformed price row in {path} " f"(day/timestamp unparseable): {exc}"
                    ) from exc
                if wanted:
                    if (day, ts) not in wanted and (None, ts) not in wanted:
                        continue
                else:
                    if start_ts is None or end_ts is None:
                        raise TypeError(
                            "rebuild_books_for_window requires either window_keys or "
                            "both start_ts and end_ts"
                        )
                    if ts < start_ts or ts > end_ts:
                        continue
                depth = _order_depth_from_row(row)
                snapshots.append(
                    BookSnapshot(
                        timestamp=ts,
                        product=product,
                        bids=_sorted_levels(depth, side="bid"),
                        asks=_sorted_levels(depth, side="ask"),
                        day=day,
                    )
                )
    snapshots.sort(key=lambda s: ((s.day if s.day is not None else 0), s.timestamp))
    return tuple(snapshots)


def _classify_price_csvs(data_files: list[Path]) -> list[Path]:
    """Filter ``data_files`` to readable price CSVs, erroring otherwise.

    Files whose basename starts with ``trades_`` are skipped silently
    because the Phase 4a manifest lists the trade tape alongside the
    price tape. Anything else that doesn't exist is a hard error —
    the drilldown can't produce a book window without it.
    """
    if not data_files:
        raise DrilldownError(
            "review pack manifest lists no data_files; cannot rebuild book "
            "context for a drilldown"
        )

    missing: list[Path] = []
    price_paths: list[Path] = []
    for path in data_files:
        if path.name.startswith("trades_"):
            continue
        if not path.is_file():
            missing.append(path)
            continue
        price_paths.append(path)

    if missing:
        raise DrilldownError(
            "review pack manifest references missing price CSVs:\n  - "
            + "\n  - ".join(str(p) for p in missing)
        )
    if not price_paths:
        raise DrilldownError(
            "review pack manifest contains no price CSVs "
            "(only trade CSVs or unknown filenames); cannot rebuild books"
        )
    return price_paths


def _validate_price_csv_columns(path: Path, fieldnames: Sequence[str] | None) -> None:
    if not fieldnames:
        raise DrilldownError(f"price CSV {path} is empty or has no header row")
    missing = [col for col in _PRICE_CSV_REQUIRED_COLUMNS if col not in fieldnames]
    if missing:
        raise DrilldownError(f"price CSV {path} is missing required columns: {missing}")


def _sorted_levels(
    depth: OrderDepth, *, side: Literal["bid", "ask"]
) -> tuple[tuple[int, int], ...]:
    if side == "bid":
        return tuple(
            (price, int(volume))
            for price, volume in sorted(depth.buy_orders.items(), key=lambda item: -item[0])
        )
    return tuple(
        (price, int(abs(volume)))
        for price, volume in sorted(depth.sell_orders.items(), key=lambda item: item[0])
    )


# ------------------------------------------------------------- case helpers


def _trade_case(
    *,
    kind: CaseKind,
    pack: ReviewPack,
    rank: int,
    idx: int,
    record: TradeRecord,
    metric: RankMetric,
    score: float,
) -> DrilldownCase:
    del pack  # reserved for future extensions (e.g. include summary fields)
    case_id = _case_id(
        kind,
        str(rank),
        metric,
        record.product,
        _day_slug(record.fill_day),
        str(record.fill_timestamp),
    )
    return DrilldownCase(
        case_id=case_id,
        kind=kind,
        product=record.product,
        anchor_timestamp=record.fill_timestamp,
        anchor_day=record.fill_day,
        trade_index=idx,
        rank_metric=metric,
        rank_score=score,
        extra=_trade_extras(record) | {"rank": rank},
    )


def _trade_extras(record: TradeRecord) -> dict[str, Any]:
    return {
        "side": record.side,
        "price": record.price,
        "quantity": record.quantity,
        "mode": record.mode,
        "decision_day": record.decision_day,
        "decision_timestamp": record.decision_timestamp,
        "fill_day": record.fill_day,
        "fill_timestamp": record.fill_timestamp,
        "fair_value_at_decision": record.fair_value_at_decision,
        "mid_at_decision": record.mid_at_decision,
        "mid_at_fill": record.mid_at_fill,
    }


def _case_id(*parts: str) -> str:
    clean = ["".join(c if c.isalnum() or c in "-_" else "_" for c in part) for part in parts]
    return "_".join(clean)


def _day_slug(day: int | None) -> str:
    return "day_unknown" if day is None else f"day_{day}"


def _resolve_anchor_day(
    pack: ReviewPack,
    product: str,
    timestamp: int,
    requested_day: int | None,
) -> int | None:
    keys = pack.pnl_keys.get(product, ())
    matching_days = sorted(
        {day for day, ts in keys if ts == timestamp},
        key=lambda day: -1 if day is None else day,
    )
    if requested_day is not None:
        if requested_day not in matching_days:
            raise KeyError(
                f"timestamp {timestamp} for product {product!r} does not exist on day "
                f"{requested_day}; available days: {matching_days}"
            )
        return requested_day
    if not matching_days:
        raise KeyError(f"timestamp {timestamp} not present for product {product!r}")
    if len(matching_days) > 1:
        raise KeyError(
            f"timestamp {timestamp} is ambiguous for product {product!r}; "
            f"available days: {matching_days}. Pass an explicit day."
        )
    return matching_days[0]


# Writer/serialization/notes helpers live in ``drilldown_writer`` so
# this module stays pure core. Re-exported there via the public
# ``write_case_artifacts`` entry point.
