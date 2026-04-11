"""Persistence layer for Phase 4b drilldown cases.

Split out from ``src.backtest.drilldown`` so that module can stay
focused on the pure core (loading, ranking, window slicing, book
rebuild). This module owns:

- ``write_case_artifacts`` — the one-call-does-everything writer.
- ``update_drilldowns_index`` — maintains a rolling ``index.json``
  under ``drilldowns/`` that lists every case produced against the
  parent pack. Entries are keyed by case id so repeat runs overwrite
  rather than duplicate.
- The per-case notes template.
- Payload builders that serialize cases and windows into stable
  JSON shapes.

The chart import is kept inside ``write_case_artifacts`` so this
module stays matplotlib-free at import time, matching
``src.backtest.reporting`` / ``src.backtest.charts``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.backtest.drilldown import (
    _NEAR_LIMIT_FRACTION,
    CaseWindow,
    DrilldownCase,
    ReviewPack,
)
from src.backtest.metrics import TradeRecord

_CASE_NOTES_TEMPLATE = """# Drilldown: {case_id}

- **Pack:** {run_id}
- **Kind:** {kind}
- **Product:** {product}
- **Anchor timestamp:** {anchor_timestamp}
- **Window:** [{window_start}, {window_end}] (radius {window_radius})
- **Generated:** {generated_at}

## What we're looking at
{headline}

## Decision
_keep / modify / discard — fill in after inspecting the window charts_

## What looked good
-

## What looked bad
-

## Root cause hypothesis
-

## Next change to test
-
"""


def write_case_artifacts(
    case: DrilldownCase,
    window: CaseWindow,
    *,
    out_dir: Path,
    pack: ReviewPack,
    render_charts: bool = True,
) -> Path:
    """Persist one drilldown case under ``out_dir / case.case_id``.

    Always writes ``summary.json``, ``window_series.json``, and
    ``notes.md``. When ``render_charts=True``, also writes per-case
    PNGs under ``charts/``. Returns the case directory.
    """
    directory = Path(out_dir) / case.case_id
    directory.mkdir(parents=True, exist_ok=True)

    summary_payload = _build_summary_payload(case, window, pack)
    (directory / "summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True)
    )
    (directory / "window_series.json").write_text(
        json.dumps(_build_window_payload(window), indent=2, sort_keys=True)
    )
    (directory / "notes.md").write_text(_render_notes(case, window, pack))

    if render_charts:
        # Local import keeps this module matplotlib-free at import time.
        from src.backtest import drilldown_charts as _charts

        _charts.render_case_charts(case, window, out_dir=directory / "charts")

    return directory


def update_drilldowns_index(
    out_dir: Path,
    *,
    pack: ReviewPack,
    cases: list[DrilldownCase],
) -> Path:
    """Merge ``cases`` into ``out_dir/index.json`` and return its path.

    The index is a rolling table of contents for the ``drilldowns/``
    directory under a Phase 4a pack. Entries are keyed by ``case_id``
    so re-running ``run_drilldown`` against the same pack upserts
    rather than duplicates rows. Fields are chosen to answer "which
    selector produced this case, against which parent run, for which
    product, with what source trade, when" without opening any of the
    per-case files.
    """
    index_path = Path(out_dir) / "index.json"
    existing = _load_index(index_path)
    generated_at = datetime.now(UTC).isoformat()

    by_case_id: dict[str, dict[str, Any]] = {
        entry.get("case_id", ""): entry
        for entry in existing.get("cases", [])
        if isinstance(entry, dict)
    }
    for case in cases:
        by_case_id[case.case_id] = _index_entry(case, generated_at)

    payload = {
        "parent_run_id": pack.run_id,
        "parent_pack_dir": str(pack.pack_dir),
        "generated_at": generated_at,
        "cases": sorted(by_case_id.values(), key=lambda entry: entry["case_id"]),
    }
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return index_path


def _load_index(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"cases": []}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        # Corrupted index: start fresh rather than crashing. The new
        # writer will overwrite it atomically below.
        return {"cases": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        return {"cases": []}
    return payload


def _index_entry(case: DrilldownCase, generated_at: str) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "selector": case.kind,
        "product": case.product,
        "anchor_timestamp": case.anchor_timestamp,
        "trade_index": case.trade_index,
        "rank_metric": case.rank_metric,
        "rank_score": case.rank_score,
        "case_dir": f"drilldowns/{case.case_id}",
        "generated_at": generated_at,
    }


def _build_summary_payload(
    case: DrilldownCase, window: CaseWindow, pack: ReviewPack
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "kind": case.kind,
        "product": case.product,
        "anchor_timestamp": case.anchor_timestamp,
        "window_start": window.start_timestamp,
        "window_end": window.end_timestamp,
        "window_radius": window.window_radius,
        "rank_metric": case.rank_metric,
        "rank_score": case.rank_score,
        "trade_index": case.trade_index,
        "pack_run_id": pack.run_id,
        "pack_dir": str(pack.pack_dir),
        "near_limit_fraction": _NEAR_LIMIT_FRACTION,
        "extra": case.extra,
        "trades_in_window": [_trade_to_dict(t) for t in window.trades_in_window],
        "book_snapshot_count": len(window.book_snapshots),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _build_window_payload(window: CaseWindow) -> dict[str, Any]:
    return {
        "product": window.product,
        "anchor_timestamp": window.anchor_timestamp,
        "window_start": window.start_timestamp,
        "window_end": window.end_timestamp,
        "mid_series": [[ts, v] for ts, v in window.mid_slice],
        "fair_value_series": [[ts, v] for ts, v in window.fair_value_slice],
        "pnl_series": [[ts, v] for ts, v in window.pnl_slice],
        "position_series": [[ts, p] for ts, p in window.position_slice],
        "book_snapshots": [
            {
                "timestamp": snap.timestamp,
                "bids": [[price, volume] for price, volume in snap.bids],
                "asks": [[price, volume] for price, volume in snap.asks],
            }
            for snap in window.book_snapshots
        ],
    }


def _trade_to_dict(record: TradeRecord) -> dict[str, Any]:
    return {
        "product": record.product,
        "side": record.side,
        "price": record.price,
        "quantity": record.quantity,
        "mode": record.mode,
        "decision_timestamp": record.decision_timestamp,
        "fill_timestamp": record.fill_timestamp,
        "fair_value_at_decision": record.fair_value_at_decision,
        "fair_value_method_at_decision": record.fair_value_method_at_decision,
        "mid_at_decision": record.mid_at_decision,
        "mid_at_fill": record.mid_at_fill,
    }


def _render_notes(
    case: DrilldownCase, window: CaseWindow, pack: ReviewPack
) -> str:
    headline = _headline_for(case)
    return _CASE_NOTES_TEMPLATE.format(
        case_id=case.case_id,
        run_id=pack.run_id,
        kind=case.kind,
        product=case.product,
        anchor_timestamp=case.anchor_timestamp,
        window_start=window.start_timestamp,
        window_end=window.end_timestamp,
        window_radius=window.window_radius,
        generated_at=datetime.now(UTC).isoformat(),
        headline=headline,
    )


def _headline_for(case: DrilldownCase) -> str:
    if case.kind in ("best", "worst"):
        score = case.rank_score
        metric = case.rank_metric
        side = case.extra.get("side")
        price = case.extra.get("price")
        qty = case.extra.get("quantity")
        mode = case.extra.get("mode")
        score_str = f"{score:+.3f}" if score is not None else "n/a"
        return (
            f"{case.kind} by {metric} = {score_str}: "
            f"{mode} {side} {qty}@{price} on {case.product} "
            f"at ts={case.anchor_timestamp}"
        )
    if case.kind == "trade":
        side = case.extra.get("side")
        price = case.extra.get("price")
        qty = case.extra.get("quantity")
        mode = case.extra.get("mode")
        return (
            f"trade #{case.trade_index}: "
            f"{mode} {side} {qty}@{price} on {case.product} "
            f"at ts={case.anchor_timestamp}"
        )
    if case.kind == "timestamp":
        return f"{case.product} at ts={case.anchor_timestamp}"
    if case.kind == "near_limit":
        pos = case.extra.get("position")
        limit = case.extra.get("position_limit")
        return (
            f"near-limit on {case.product} at ts={case.anchor_timestamp}: "
            f"position {pos} / limit {limit}"
        )
    return f"{case.product} at ts={case.anchor_timestamp}"
