"""Review pack generation and persistence.

Every non-trivial backtest run produces a review pack: a structured
``outputs/review_packs/<run_id>/`` directory containing the metric
summary, per-trade records, step-indexed series, optional chart
artifacts, a provenance manifest, and a human-writable notes
template. This lets every strategy change be reviewed against the
same artifact shape.

Phase 4a scope:

- ``build_review_pack`` carries the new markout / entry-edge
  aggregates and counts.
- ``write_review_pack`` is the one-call-does-everything writer. It
  always writes ``manifest.json``, ``summary.json``, ``summary.txt``,
  ``trades.json`` and ``series.json``. When ``render_charts=True``
  it also calls into ``src.backtest.charts`` and writes a
  ``notes.md`` template.

The writer stays matplotlib-free: ``charts.py`` imports matplotlib
lazily inside its render functions, and ``reporting`` only imports
``charts`` inside ``write_review_pack`` when ``render_charts=True``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.backtest import provenance
from src.backtest.metrics import ProductResult, SimulationResult, TradeRecord
from src.core.config import EngineConfig

_DEFAULT_REVIEW_DIR = Path("outputs/review_packs")
_MARKOUT_HORIZONS: tuple[int, ...] = (1, 5, 20)

_NOTES_TEMPLATE = """# Review: {run_label}

- **Run ID:** {run_id}
- **Generated:** {generated_at}
- **Commit:** {commit}

## Decision
_keep / modify / discard — fill in after inspecting charts_

## What looked good
-

## What looked bad
-

## Most important chart to inspect
_e.g. charts/price_vs_fair_TOMATOES.png - look at steps 300-400_

## Next change to test
-
"""


class _Sentinel:
    """Marker for "no value provided" so ``None`` can opt out."""

    _INSTANCE: _Sentinel | None = None

    def __new__(cls) -> _Sentinel:
        if cls._INSTANCE is None:
            cls._INSTANCE = super().__new__(cls)
        return cls._INSTANCE


_UNSET = _Sentinel()


def build_review_pack(result: SimulationResult, *, run_label: str = "") -> dict[str, Any]:
    return {
        "run_label": run_label,
        "generated_at": datetime.now(UTC).isoformat(),
        "steps": result.steps,
        "total_pnl": result.total_pnl,
        "per_product": {product: _product_to_dict(r) for product, r in result.per_product.items()},
    }


def write_review_pack(
    result: SimulationResult,
    *,
    run_label: str = "",
    base_dir: Path | str = _DEFAULT_REVIEW_DIR,
    render_charts: bool = False,
    engine_config: EngineConfig | None = None,
    data_files: Sequence[str | Path] = (),
    git_commit: str | None | _Sentinel = _UNSET,
    git_dirty: bool | None | _Sentinel = _UNSET,
) -> Path:
    """Persist a review pack to disk and return the directory.

    Provenance fields default to auto-detection: pass a concrete
    value (including ``None``) to opt out. Tests pass ``None``
    explicitly so they never shell out to git.
    """
    run_id = _run_id(run_label)
    directory = Path(base_dir) / run_id
    directory.mkdir(parents=True, exist_ok=True)

    pack = build_review_pack(result, run_label=run_label)
    (directory / "summary.json").write_text(json.dumps(pack, indent=2, sort_keys=True))
    (directory / "summary.txt").write_text(result.summary_table() + "\n")
    (directory / "trades.json").write_text(
        json.dumps(
            {"trades": [_trade_to_dict(t) for t in result.trade_records]},
            indent=2,
            sort_keys=True,
        )
    )
    (directory / "series.json").write_text(
        json.dumps(
            {
                "mid_series": _series_dict(result.mid_series),
                "fair_value_series": _series_dict(result.fair_value_series),
                "pnl_series": _series_dict(result.pnl_series),
                "mid_keys": _series_keys_dict(result.mid_series, result.mid_keys),
                "fair_value_keys": _series_keys_dict(
                    result.fair_value_series, result.fair_value_keys
                ),
                "pnl_keys": _series_keys_dict(result.pnl_series, result.pnl_keys),
            },
            indent=2,
            sort_keys=True,
        )
    )

    # Provenance manifest — always written so every pack is traceable.
    commit = _resolve_commit(git_commit)
    dirty = _resolve_dirty(git_dirty)
    manifest = provenance.build_manifest(
        run_id=run_id,
        run_label=run_label,
        engine_config=engine_config,
        data_files=data_files,
        markout_horizons=_MARKOUT_HORIZONS,
        charts_rendered=render_charts,
        artifacts={
            "summary_json": "summary.json",
            "summary_text": "summary.txt",
            "trades_json": "trades.json",
            "series_json": "series.json",
            "charts_dir": "charts",
            "notes_md": "notes.md",
        },
        commit=commit,
        dirty=dirty,
    )
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))

    if render_charts:
        # Local import keeps the Prosperity submission runtime
        # matplotlib-free. ``charts.py`` itself also imports
        # matplotlib lazily for the same reason.
        from src.backtest import charts as _charts

        _charts.render_review_charts(
            result, out_dir=directory / "charts", markout_horizons=_MARKOUT_HORIZONS
        )
        (directory / "notes.md").write_text(
            _NOTES_TEMPLATE.format(
                run_label=run_label or run_id,
                run_id=run_id,
                generated_at=manifest["generated_at"],
                commit=commit if commit is not None else "unknown",
            )
        )

    return directory


def _product_to_dict(r: ProductResult) -> dict[str, Any]:
    return {
        "pnl": r.pnl,
        "cash": r.cash,
        "final_position": r.final_position,
        "mark_price": r.mark_price,
        "order_count": r.order_count,
        "trade_count": r.trade_count,
        "taker_trade_count": r.taker_trade_count,
        "maker_trade_count": r.maker_trade_count,
        "taker_trade_quantity": r.taker_trade_quantity,
        "maker_trade_quantity": r.maker_trade_quantity,
        "buy_trade_quantity": r.buy_trade_quantity,
        "sell_trade_quantity": r.sell_trade_quantity,
        "steps_near_limit": r.steps_near_limit,
        "avg_entry_edge": r.avg_entry_edge,
        "entry_edge_count": r.entry_edge_count,
        "avg_markout_1": r.avg_markout_1,
        "markout_1_count": r.markout_1_count,
        "avg_markout_5": r.avg_markout_5,
        "markout_5_count": r.markout_5_count,
        "avg_markout_20": r.avg_markout_20,
        "markout_20_count": r.markout_20_count,
    }


def _trade_to_dict(record: TradeRecord) -> dict[str, Any]:
    return asdict(record)


def _series_dict(
    series: dict[str, tuple[tuple[int, float], ...]],
) -> dict[str, list[list[float]]]:
    # Use nested lists so json.dumps produces arrays rather than tuple
    # strings. Preserves int/float types.
    return {
        product: [[int(ts), float(value)] for ts, value in points]
        for product, points in series.items()
    }


def _series_keys_dict(
    series: dict[str, tuple[tuple[int, float], ...]],
    keys: dict[str, tuple[tuple[int | None, int], ...]],
) -> dict[str, list[list[int | None]]]:
    payload: dict[str, list[list[int | None]]] = {}
    for product, points in series.items():
        point_keys = keys.get(product)
        if point_keys is None:
            payload[product] = [[None, int(ts)] for ts, _ in points]
            continue
        if len(point_keys) != len(points):
            raise ValueError(
                "series keys must align with the persisted series length "
                f"for product {product!r}"
            )
        payload[product] = [
            [None if day is None else int(day), int(timestamp)] for day, timestamp in point_keys
        ]
    return payload


def _run_id(run_label: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if run_label:
        clean = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_label)
        return f"{stamp}_{clean}"
    return stamp


def _resolve_commit(value: str | None | _Sentinel) -> str | None:
    if isinstance(value, _Sentinel):
        return provenance.git_commit()
    return value


def _resolve_dirty(value: bool | None | _Sentinel) -> bool | None:
    if isinstance(value, _Sentinel):
        return provenance.git_dirty()
    return value
