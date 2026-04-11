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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from src.backtest.metrics import TradeRecord
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
    mid_index_by_product: dict[str, dict[int, int]] = field(default_factory=dict)

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
    trade_index: int | None = None
    rank_metric: RankMetric | None = None
    rank_score: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseWindow:
    """Series slice plus rebuilt book snapshots for one drilldown case."""

    product: str
    anchor_timestamp: int
    window_radius: int
    start_timestamp: int
    end_timestamp: int
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

    mid_index_by_product = {
        product: {ts: idx for idx, (ts, _) in enumerate(series)}
        for product, series in mid_series.items()
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
        mid_index_by_product=mid_index_by_product,
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Review pack is missing {path.name}: {path}")
    return json.loads(path.read_text())


def _parse_series(
    raw: dict[str, Any],
) -> dict[str, tuple[tuple[int, float], ...]]:
    parsed: dict[str, tuple[tuple[int, float], ...]] = {}
    for product, points in raw.items():
        parsed[product] = tuple((int(ts), float(value)) for ts, value in points)
    return parsed


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
    )


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


# ------------------------------------------------------------------ scoring


def trade_score(
    record: TradeRecord,
    mid_series: dict[str, tuple[tuple[int, float], ...]],
    mid_index: dict[str, dict[int, int]],
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
    fill_idx = index_map.get(record.fill_timestamp)
    if fill_idx is None:
        return None
    future_idx = fill_idx + horizon
    if future_idx < 0 or future_idx >= len(series):
        return None
    future_mid = series[future_idx][1]
    return sign * (future_mid - record.price)


def rank_trades(
    pack: ReviewPack, metric: RankMetric
) -> list[tuple[float, int, TradeRecord]]:
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


def select_best_trades(
    pack: ReviewPack, n: int, metric: RankMetric
) -> list[DrilldownCase]:
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


def select_worst_trades(
    pack: ReviewPack, n: int, metric: RankMetric
) -> list[DrilldownCase]:
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
            f"trade_index {trade_index} out of range for pack with "
            f"{len(pack.trades)} trades"
        )
    record = pack.trades[trade_index]
    case_id = _case_id(
        "trade", str(trade_index), record.product, str(record.fill_timestamp)
    )
    return DrilldownCase(
        case_id=case_id,
        kind="trade",
        product=record.product,
        anchor_timestamp=record.fill_timestamp,
        trade_index=trade_index,
        extra=_trade_extras(record),
    )


def select_by_timestamp(
    pack: ReviewPack, product: str, timestamp: int
) -> DrilldownCase:
    if product not in pack.mid_series:
        raise KeyError(f"product {product!r} not present in review pack")
    case_id = _case_id("timestamp", product, str(timestamp))
    # Look up a nearby trade record for convenience; it's not required.
    matching = [
        i for i, t in enumerate(pack.trades)
        if t.product == product and t.fill_timestamp == timestamp
    ]
    extra: dict[str, Any] = {"trade_indices": matching}
    return DrilldownCase(
        case_id=case_id,
        kind="timestamp",
        product=product,
        anchor_timestamp=timestamp,
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
    candidates: list[tuple[float, int, str, int]] = []
    for product in pack.products():
        limit = pack.position_limit(product)
        if limit is None or limit <= 0:
            continue
        threshold = near_limit_fraction * limit
        positions = reconstruct_position_series(pack.trades, pack.pnl_series, product)
        for ts, pos in positions:
            abs_pos = abs(pos)
            if abs_pos < threshold:
                continue
            ratio = abs_pos / float(limit)
            candidates.append((ratio, pos, product, ts))

    # Descending by ratio, break ties by timestamp ascending for determinism.
    candidates.sort(key=lambda item: (-item[0], item[3]))
    cases: list[DrilldownCase] = []
    for rank, (ratio, pos, product, ts) in enumerate(candidates[:n], start=1):
        case_id = _case_id("near_limit", str(rank), product, str(ts))
        cases.append(
            DrilldownCase(
                case_id=case_id,
                kind="near_limit",
                product=product,
                anchor_timestamp=ts,
                extra={
                    "rank": rank,
                    "position": pos,
                    "position_limit": pack.position_limit(product),
                    "abs_ratio": ratio,
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

    pnl_grid = [ts for ts, _ in pnl_series]
    anchor_idx = _index_of_or_nearest(pnl_grid, case.anchor_timestamp)
    lo = max(0, anchor_idx - window_radius)
    hi = min(len(pnl_grid) - 1, anchor_idx + window_radius)
    start_ts = pnl_grid[lo]
    end_ts = pnl_grid[hi]

    mid_slice = _slice_series(mid_series, start_ts, end_ts)
    fair_slice = _slice_series(pack.fair_value_series.get(product, ()), start_ts, end_ts)
    pnl_slice = tuple(pnl_series[lo : hi + 1])

    positions = reconstruct_position_series(pack.trades, pack.pnl_series, product)
    position_slice = tuple(positions[lo : hi + 1])

    trades_in_window = tuple(
        record for record in pack.trades
        if record.product == product
        and start_ts <= record.fill_timestamp <= end_ts
    )

    book_snapshots = rebuild_books_for_window(
        data_files=pack.data_files(),
        product=product,
        start_ts=start_ts,
        end_ts=end_ts,
    )

    return CaseWindow(
        product=product,
        anchor_timestamp=case.anchor_timestamp,
        window_radius=window_radius,
        start_timestamp=start_ts,
        end_timestamp=end_ts,
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


# ------------------------------------------------------------- book rebuild


def rebuild_books_for_window(
    *,
    data_files: list[Path],
    product: str,
    start_ts: int,
    end_ts: int,
) -> tuple[BookSnapshot, ...]:
    """Re-parse price CSVs to reconstruct book snapshots for a window.

    Only rows for ``product`` with ``start_ts <= timestamp <= end_ts``
    are parsed. Trade CSVs are ignored — drilldowns don't need the
    trade tape, just the visible book shape. Days are read in order
    but we key the output by timestamp alone because tutorial days
    are already merged into the series view by Phase 4a.

    Raises ``DrilldownError`` when the manifest does not list any
    price CSVs, when a listed price CSV is missing from disk, or when
    a CSV is present but missing the required columns. This is
    deliberately stricter than "silently skip" so a broken manifest
    produces a readable error instead of an empty window.
    """
    price_paths = _classify_price_csvs(data_files)
    snapshots: list[BookSnapshot] = []
    for path in price_paths:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            _validate_price_csv_columns(path, reader.fieldnames)
            for row in reader:
                if row.get("product") != product:
                    continue
                try:
                    ts = int(row["timestamp"])
                except (KeyError, ValueError) as exc:
                    raise DrilldownError(
                        f"malformed price row in {path} "
                        f"(timestamp unparseable): {exc}"
                    ) from exc
                if ts < start_ts or ts > end_ts:
                    continue
                depth = _order_depth_from_row(row)
                snapshots.append(
                    BookSnapshot(
                        timestamp=ts,
                        product=product,
                        bids=_sorted_levels(depth, side="bid"),
                        asks=_sorted_levels(depth, side="ask"),
                    )
                )
    snapshots.sort(key=lambda s: s.timestamp)
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


def _validate_price_csv_columns(
    path: Path, fieldnames: list[str] | None
) -> None:
    if not fieldnames:
        raise DrilldownError(
            f"price CSV {path} is empty or has no header row"
        )
    missing = [col for col in _PRICE_CSV_REQUIRED_COLUMNS if col not in fieldnames]
    if missing:
        raise DrilldownError(
            f"price CSV {path} is missing required columns: {missing}"
        )


def _sorted_levels(
    depth: OrderDepth, *, side: Literal["bid", "ask"]
) -> tuple[tuple[int, int], ...]:
    if side == "bid":
        return tuple(
            (price, int(volume)) for price, volume in sorted(
                depth.buy_orders.items(), key=lambda item: -item[0]
            )
        )
    return tuple(
        (price, int(abs(volume))) for price, volume in sorted(
            depth.sell_orders.items(), key=lambda item: item[0]
        )
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
        kind, str(rank), metric, record.product, str(record.fill_timestamp)
    )
    return DrilldownCase(
        case_id=case_id,
        kind=kind,
        product=record.product,
        anchor_timestamp=record.fill_timestamp,
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
        "decision_timestamp": record.decision_timestamp,
        "fill_timestamp": record.fill_timestamp,
        "fair_value_at_decision": record.fair_value_at_decision,
        "mid_at_decision": record.mid_at_decision,
        "mid_at_fill": record.mid_at_fill,
    }


def _case_id(*parts: str) -> str:
    clean = [
        "".join(c if c.isalnum() or c in "-_" else "_" for c in part) for part in parts
    ]
    return "_".join(clean)


# Writer/serialization/notes helpers live in ``drilldown_writer`` so
# this module stays pure core. Re-exported there via the public
# ``write_case_artifacts`` entry point.
