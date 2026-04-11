"""Per-case chart rendering for Phase 4b drilldowns.

Matches the style of ``src.backtest.charts``: lazy matplotlib imports
so importing this module does not pull in a plotting backend, and the
``Agg`` backend is pinned on first use so headless runs work without
a display.

The drilldown charts are intentionally simple — they are meant to
support the structured ``notes.md`` that sits next to them. A
reviewer opens the window chart, sees the mid / fair / anchor marker,
glances at the book depth at the anchor step, and then jots the
diagnosis.
"""

from __future__ import annotations

from pathlib import Path

from src.backtest.drilldown import BookSnapshot, CaseWindow, DrilldownCase

CHART_DPI = 150
PRICE_FAIR_FIGSIZE = (9.0, 4.0)
BOOK_DEPTH_FIGSIZE = (6.0, 4.0)
PNL_POS_FIGSIZE = (9.0, 5.0)


def render_case_charts(
    case: DrilldownCase,
    window: CaseWindow,
    *,
    out_dir: Path | str,
) -> list[Path]:
    """Render the full per-case chart suite under ``out_dir``.

    Returns the list of chart files successfully written. Missing
    series (e.g. no fair value on a timestamp drill for a product
    with no fair-value log) simply skip that sub-chart.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    price_fair_path = out_path / "price_vs_fair_window.png"
    if render_case_price_fair(case, window, price_fair_path):
        written.append(price_fair_path)

    book_path = out_path / "book_depth.png"
    if render_case_book_depth(case, window, book_path):
        written.append(book_path)

    pnl_path = out_path / "pnl_position_window.png"
    if render_case_pnl_position(case, window, pnl_path):
        written.append(pnl_path)

    return written


# ------------------------------------------------------------ individual plots


def render_case_price_fair(
    case: DrilldownCase, window: CaseWindow, out: Path
) -> bool:
    if not window.mid_slice and not window.fair_value_slice:
        return False
    plt = _plt()
    fig, ax = plt.subplots(figsize=PRICE_FAIR_FIGSIZE)

    if window.mid_slice:
        xs = [ts for ts, _ in window.mid_slice]
        ys = [v for _, v in window.mid_slice]
        ax.plot(xs, ys, label="mid", color="#1f77b4", linewidth=1.3)
    if window.fair_value_slice:
        xs = [ts for ts, _ in window.fair_value_slice]
        ys = [v for _, v in window.fair_value_slice]
        ax.plot(xs, ys, label="fair value", color="#ff7f0e", linewidth=1.1, alpha=0.9)

    # Mark every fill in the window, and highlight the anchor explicitly.
    anchor_ts = case.anchor_timestamp
    for record in window.trades_in_window:
        marker = "^" if record.side == "buy" else "v"
        color = "#2ca02c" if record.side == "buy" else "#d62728"
        alpha = 1.0 if record.mode == "taker" else 0.45
        size = max(40, 12 * record.quantity)
        is_anchor = record.fill_timestamp == anchor_ts
        ax.scatter(
            [record.fill_timestamp],
            [record.price],
            marker=marker,
            color=color,
            s=size * (1.8 if is_anchor else 1.0),
            alpha=alpha,
            edgecolors="black" if is_anchor else "none",
            linewidths=1.2 if is_anchor else 0.0,
        )

    ax.axvline(anchor_ts, color="#7f7f7f", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.set_title(f"{window.product} — {case.case_id}")
    ax.set_xlabel("timestamp")
    ax.set_ylabel("price")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.2)
    _save(fig, out)
    return True


def render_case_book_depth(
    case: DrilldownCase, window: CaseWindow, out: Path
) -> bool:
    snapshot = _snapshot_at_or_near(window.book_snapshots, case.anchor_timestamp)
    if snapshot is None or (not snapshot.bids and not snapshot.asks):
        return False
    plt = _plt()
    fig, ax = plt.subplots(figsize=BOOK_DEPTH_FIGSIZE)

    bid_prices = [price for price, _ in snapshot.bids]
    bid_volumes = [vol for _, vol in snapshot.bids]
    ask_prices = [price for price, _ in snapshot.asks]
    ask_volumes = [vol for _, vol in snapshot.asks]

    if bid_prices:
        ax.barh(bid_prices, bid_volumes, color="#2ca02c", alpha=0.8, label="bids")
    if ask_prices:
        ax.barh(ask_prices, [-v for v in ask_volumes], color="#d62728", alpha=0.8, label="asks")

    ax.axvline(0, color="#888", linewidth=0.7)
    ax.set_title(
        f"{window.product} book @ ts={snapshot.timestamp}"
        f" (anchor={case.anchor_timestamp})"
    )
    ax.set_xlabel("volume  (asks left / bids right)")
    ax.set_ylabel("price")
    ax.legend(loc="best", fontsize=8)
    ax.grid(axis="x", alpha=0.2)
    _save(fig, out)
    return True


def render_case_pnl_position(
    case: DrilldownCase, window: CaseWindow, out: Path
) -> bool:
    if not window.pnl_slice and not window.position_slice:
        return False
    plt = _plt()
    fig, (ax_pnl, ax_pos) = plt.subplots(
        2, 1, figsize=PNL_POS_FIGSIZE, sharex=True
    )

    if window.pnl_slice:
        xs = [ts for ts, _ in window.pnl_slice]
        ys = [v for _, v in window.pnl_slice]
        ax_pnl.plot(xs, ys, color="#1f77b4", linewidth=1.3)
        ax_pnl.axhline(0, color="#888", linewidth=0.7, linestyle="--")
    ax_pnl.set_title(f"{window.product} — PnL (window)")
    ax_pnl.set_ylabel("pnl")
    ax_pnl.grid(alpha=0.2)
    ax_pnl.axvline(
        case.anchor_timestamp, color="#7f7f7f", linestyle="--", linewidth=0.8, alpha=0.7
    )

    if window.position_slice:
        xs = [ts for ts, _ in window.position_slice]
        ys = [p for _, p in window.position_slice]
        ax_pos.plot(xs, ys, color="#9467bd", linewidth=1.3)
        ax_pos.axhline(0, color="#888", linewidth=0.7, linestyle="--")
    ax_pos.set_title(f"{window.product} — position (window)")
    ax_pos.set_xlabel("timestamp")
    ax_pos.set_ylabel("position")
    ax_pos.grid(alpha=0.2)
    ax_pos.axvline(
        case.anchor_timestamp, color="#7f7f7f", linestyle="--", linewidth=0.8, alpha=0.7
    )

    _save(fig, out, bbox_inches="tight")
    return True


# ------------------------------------------------------------ helpers


def _snapshot_at_or_near(
    snapshots: tuple[BookSnapshot, ...], target_ts: int
) -> BookSnapshot | None:
    if not snapshots:
        return None
    for snapshot in snapshots:
        if snapshot.timestamp == target_ts:
            return snapshot
    # Fall back to the closest snapshot in the window so drilldowns
    # anchored on one-sided or missing steps still render.
    return min(snapshots, key=lambda s: abs(s.timestamp - target_ts))


def _plt():  # type: ignore[no-untyped-def]
    import matplotlib

    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    return plt


def _save(fig, out: Path, **savefig_kwargs) -> None:  # type: ignore[no-untyped-def]
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=CHART_DPI, **savefig_kwargs)
    _plt().close(fig)
