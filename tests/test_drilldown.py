"""Tests for Phase 4b drilldowns.

Covers the pure selector/ranking helpers plus the integration path
that rebuilds local book snapshots from on-disk CSVs and writes per
case artifacts. A synthetic review pack is used throughout because
it keeps the tests deterministic and lets us force the near-limit
case that the tutorial baseline doesn't produce.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.backtest.drilldown import (
    BookSnapshot,
    DrilldownCase,
    DrilldownError,
    ReviewPack,
    build_case_window,
    load_review_pack,
    rank_trades,
    rebuild_books_for_window,
    reconstruct_position_series,
    select_best_trades,
    select_by_timestamp,
    select_by_trade_id,
    select_near_limit,
    select_worst_trades,
    trade_score,
)
from src.backtest.drilldown_writer import (
    update_drilldowns_index,
    write_case_artifacts,
)
from src.backtest.metrics import (
    ProductResult,
    SimulationResult,
    TradeRecord,
)
from src.backtest.reporting import write_review_pack
from src.core.config import EngineConfig, ProductConfig

# ---------------------------------------------------------- CSV fixtures

_PRICE_CSV_HEADER = (
    "day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;"
    "bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;"
    "ask_price_3;ask_volume_3;mid_price;profit_and_loss"
)


def _write_price_csv(
    path: Path,
    *,
    product: str = "P",
    day: int = -1,
    rows: list[tuple[int, int, int]] | None = None,
) -> None:
    """Write a minimal tutorial-shaped price CSV.

    ``rows`` is a sequence of ``(timestamp, bid, ask)`` tuples. Only
    the top level is populated; the other levels are blank, matching
    how Prosperity encodes missing book levels.
    """
    rows = rows or [(ts, 99 + ts // 100, 101 + ts // 100) for ts in (0, 100, 200, 300, 400)]
    lines = [_PRICE_CSV_HEADER]
    for ts, bid, ask in rows:
        lines.append(
            f"{day};{ts};{product};{bid};5;;;;;"
            f"{ask};5;;;;;"
            f"{(bid + ask) / 2.0};0.0"
        )
    path.write_text("\n".join(lines) + "\n")


# ------------------------------------------------------- pack fixtures


def _taker_result() -> SimulationResult:
    """Synthetic result with one taker fill on product 'P'."""
    records = (
        TradeRecord(
            product="P",
            side="buy",
            price=101.0,
            quantity=2,
            mode="taker",
            decision_timestamp=100,
            fill_timestamp=100,
            fair_value_at_decision=100.5,
            fair_value_method_at_decision="anchor",
            mid_at_decision=100.0,
            mid_at_fill=100.0,
        ),
        TradeRecord(
            product="P",
            side="sell",
            price=104.0,
            quantity=1,
            mode="taker",
            decision_timestamp=300,
            fill_timestamp=300,
            fair_value_at_decision=103.0,
            fair_value_method_at_decision="anchor",
            mid_at_decision=103.5,
            mid_at_fill=103.5,
        ),
    )
    # 5 steps: 0..400 at stride 100; mid climbs +0.5 per step.
    mid_series = {"P": tuple((ts, 100.0 + 0.5 * i) for i, ts in enumerate((0, 100, 200, 300, 400)))}
    fair_value_series = {"P": tuple((ts, 101.0) for ts in (0, 100, 200, 300, 400))}
    pnl_series = {"P": tuple((ts, float(i)) for i, ts in enumerate((0, 100, 200, 300, 400)))}
    return SimulationResult(
        steps=5,
        total_pnl=4.0,
        per_product={
            "P": ProductResult(
                product="P",
                pnl=4.0,
                cash=0.0,
                final_position=1,
                mark_price=102.0,
                order_count=2,
                trade_count=2,
                taker_trade_count=2,
                maker_trade_count=0,
                taker_trade_quantity=3,
                maker_trade_quantity=0,
                buy_trade_quantity=2,
                sell_trade_quantity=1,
                steps_near_limit=0,
            )
        },
        trade_records=records,
        mid_series=mid_series,
        fair_value_series=fair_value_series,
        pnl_series=pnl_series,
    )


def _maker_result() -> SimulationResult:
    """Synthetic result with one maker fill whose decision ts precedes fill ts."""
    record = TradeRecord(
        product="P",
        side="buy",
        price=99.0,
        quantity=3,
        mode="maker",
        decision_timestamp=0,
        fill_timestamp=100,
        fair_value_at_decision=100.0,
        fair_value_method_at_decision="anchor",
        mid_at_decision=100.0,
        mid_at_fill=100.5,
    )
    mid_series = {"P": tuple((ts, 100.0 + 0.2 * i) for i, ts in enumerate((0, 100, 200, 300, 400)))}
    fair_value_series = {"P": tuple((ts, 100.0) for ts in (0, 100, 200, 300, 400))}
    pnl_series = {"P": tuple((ts, float(i) * 0.1) for i, ts in enumerate((0, 100, 200, 300, 400)))}
    return SimulationResult(
        steps=5,
        total_pnl=0.0,
        per_product={
            "P": ProductResult(
                product="P",
                pnl=0.0,
                cash=-297.0,
                final_position=3,
                mark_price=100.8,
                order_count=1,
                trade_count=1,
                taker_trade_count=0,
                maker_trade_count=1,
                taker_trade_quantity=0,
                maker_trade_quantity=3,
                buy_trade_quantity=3,
                sell_trade_quantity=0,
                steps_near_limit=0,
            )
        },
        trade_records=(record,),
        mid_series=mid_series,
        fair_value_series=fair_value_series,
        pnl_series=pnl_series,
    )


def _near_limit_result() -> SimulationResult:
    """Synthetic result with position pinned >= 0.75*limit across the run."""
    # limit=20 in the engine config below; 15 buys on step 1 drive pos=15 at
    # step 1, then flat through 2/3, so three steps qualify as near-limit.
    records = (
        TradeRecord(
            product="P",
            side="buy",
            price=101.0,
            quantity=15,
            mode="taker",
            decision_timestamp=100,
            fill_timestamp=100,
            fair_value_at_decision=100.0,
            fair_value_method_at_decision="anchor",
            mid_at_decision=100.0,
            mid_at_fill=100.0,
        ),
    )
    mid_series = {"P": tuple((ts, 100.0) for ts in (0, 100, 200, 300))}
    fair_value_series = {"P": tuple((ts, 100.0) for ts in (0, 100, 200, 300))}
    pnl_series = {"P": tuple((ts, float(i)) for i, ts in enumerate((0, 100, 200, 300)))}
    return SimulationResult(
        steps=4,
        total_pnl=0.0,
        per_product={
            "P": ProductResult(
                product="P",
                pnl=0.0,
                cash=-1515.0,
                final_position=15,
                mark_price=100.0,
                order_count=1,
                trade_count=1,
                taker_trade_count=1,
                maker_trade_count=0,
                taker_trade_quantity=15,
                maker_trade_quantity=0,
                buy_trade_quantity=15,
                sell_trade_quantity=0,
                steps_near_limit=3,
            )
        },
        trade_records=records,
        mid_series=mid_series,
        fair_value_series=fair_value_series,
        pnl_series=pnl_series,
    )


def _engine_config() -> EngineConfig:
    return EngineConfig(
        products={
            "P": ProductConfig(
                position_limit=20,
                strategy_name="market_making",
                fair_value_method="anchor",
                anchor_price=100.0,
            )
        }
    )


def _write_pack(
    tmp_path: Path,
    result: SimulationResult,
    *,
    label: str,
    price_rows: list[tuple[int, int, int]] | None = None,
) -> tuple[Path, Path]:
    """Write a price CSV + review pack pair; return ``(pack_dir, csv_path)``."""
    csv_path = tmp_path / f"prices_{label}.csv"
    if price_rows is None:
        price_rows = [
            (ts, 99, 101) for ts in
            [ts for ts, _ in next(iter(result.mid_series.values()))]
        ]
    _write_price_csv(csv_path, rows=price_rows)
    pack_dir = write_review_pack(
        result,
        run_label=label,
        base_dir=tmp_path / "packs",
        render_charts=False,
        engine_config=_engine_config(),
        data_files=[csv_path],
        git_commit=None,
        git_dirty=None,
    )
    return pack_dir, csv_path


# -------------------------------------------------------------- unit tests


@pytest.mark.unit
def test_load_review_pack_parses_round_trip(tmp_path: Path) -> None:
    pack_dir, _ = _write_pack(tmp_path, _taker_result(), label="load_rt")
    pack = load_review_pack(pack_dir)

    assert pack.run_id.startswith("2") or pack.run_id.endswith("load_rt")
    assert len(pack.trades) == 2
    assert pack.trades[0].product == "P"
    assert pack.trades[0].side == "buy"
    assert pack.mid_series["P"][0] == (0, 100.0)
    assert pack.mid_index_by_product["P"][100] == 1
    assert pack.position_limit("P") == 20


@pytest.mark.unit
def test_trade_score_edge_sign_convention() -> None:
    result = _taker_result()
    pack = ReviewPack(
        pack_dir=Path("."),
        run_id="unit",
        manifest={},
        summary={},
        trades=result.trade_records,
        mid_series=result.mid_series,
        fair_value_series=result.fair_value_series,
        pnl_series=result.pnl_series,
        mid_index_by_product={
            p: {ts: i for i, (ts, _) in enumerate(series)}
            for p, series in result.mid_series.items()
        },
    )
    buy = pack.trades[0]
    sell = pack.trades[1]
    # buy at 101, fair 100.5 -> edge = 100.5 - 101 = -0.5
    assert trade_score(buy, pack.mid_series, pack.mid_index_by_product, "edge") == pytest.approx(-0.5)
    # sell at 104, fair 103 -> edge = 104 - 103 = 1.0
    assert trade_score(sell, pack.mid_series, pack.mid_index_by_product, "edge") == pytest.approx(1.0)


@pytest.mark.unit
def test_trade_score_markout_reaches_future_mid() -> None:
    result = _taker_result()
    pack = ReviewPack(
        pack_dir=Path("."),
        run_id="unit",
        manifest={},
        summary={},
        trades=result.trade_records,
        mid_series=result.mid_series,
        fair_value_series=result.fair_value_series,
        pnl_series=result.pnl_series,
        mid_index_by_product={
            p: {ts: i for i, (ts, _) in enumerate(series)}
            for p, series in result.mid_series.items()
        },
    )
    buy = pack.trades[0]
    # buy at 101 at ts=100 (idx 1). markout_1 -> mid at idx 2 = 101.0 -> +0.0
    assert trade_score(buy, pack.mid_series, pack.mid_index_by_product, "markout_1") == pytest.approx(0.0)
    # Horizon 20 reaches past the end of the 5-step series -> None.
    assert trade_score(buy, pack.mid_series, pack.mid_index_by_product, "markout_20") is None


@pytest.mark.unit
def test_rank_trades_by_edge_orders_descending() -> None:
    result = _taker_result()
    pack = ReviewPack(
        pack_dir=Path("."),
        run_id="unit",
        manifest={},
        summary={},
        trades=result.trade_records,
        mid_series=result.mid_series,
        fair_value_series=result.fair_value_series,
        pnl_series=result.pnl_series,
        mid_index_by_product={
            p: {ts: i for i, (ts, _) in enumerate(series)}
            for p, series in result.mid_series.items()
        },
    )
    ranked = rank_trades(pack, "edge")
    # Sell (+1.0) should come before buy (-0.5).
    assert [idx for _, idx, _ in ranked] == [1, 0]


@pytest.mark.unit
def test_select_best_and_worst_return_distinct_cases(tmp_path: Path) -> None:
    pack_dir, _ = _write_pack(tmp_path, _taker_result(), label="bw")
    pack = load_review_pack(pack_dir)
    best = select_best_trades(pack, 1, "edge")
    worst = select_worst_trades(pack, 1, "edge")
    assert len(best) == 1 and len(worst) == 1
    assert best[0].case_id != worst[0].case_id
    assert best[0].kind == "best"
    assert worst[0].kind == "worst"


@pytest.mark.unit
def test_select_by_trade_id_and_timestamp(tmp_path: Path) -> None:
    pack_dir, _ = _write_pack(tmp_path, _taker_result(), label="ids")
    pack = load_review_pack(pack_dir)

    by_id = select_by_trade_id(pack, 0)
    assert by_id.kind == "trade"
    assert by_id.trade_index == 0
    assert by_id.anchor_timestamp == 100

    by_ts = select_by_timestamp(pack, "P", 300)
    assert by_ts.kind == "timestamp"
    assert by_ts.product == "P"
    assert by_ts.anchor_timestamp == 300
    assert by_ts.extra["trade_indices"] == [1]

    with pytest.raises(IndexError):
        select_by_trade_id(pack, 99)
    with pytest.raises(KeyError):
        select_by_timestamp(pack, "MISSING", 100)


@pytest.mark.unit
def test_reconstruct_position_series_matches_cumulative_signed_qty() -> None:
    result = _taker_result()
    positions = reconstruct_position_series(result.trade_records, result.pnl_series, "P")
    assert positions == [(0, 0), (100, 2), (200, 2), (300, 1), (400, 1)]


@pytest.mark.unit
def test_build_case_window_clips_at_series_bounds(tmp_path: Path) -> None:
    pack_dir, _ = _write_pack(tmp_path, _taker_result(), label="clip")
    pack = load_review_pack(pack_dir)
    # First trade is at ts=100 (idx 1). Ask for a radius of 2 to force the
    # left bound to clip at idx 0.
    case = select_by_trade_id(pack, 0)
    window = build_case_window(case, pack, window_radius=2)
    assert window.start_timestamp == 0
    assert window.end_timestamp == 300
    assert window.mid_slice[0] == (0, 100.0)
    assert window.position_slice[0] == (0, 0)
    # At ts=100 the first trade has landed so position == 2.
    assert dict(window.position_slice)[100] == 2


@pytest.mark.unit
def test_rebuild_books_for_window_returns_correct_bid_ask(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    _write_price_csv(
        csv_path,
        product="P",
        rows=[
            (0, 99, 101),
            (100, 98, 102),
            (200, 97, 103),
            (300, 96, 104),
            (400, 95, 105),
        ],
    )
    snaps = rebuild_books_for_window(
        data_files=[csv_path], product="P", start_ts=100, end_ts=300
    )
    assert [s.timestamp for s in snaps] == [100, 200, 300]
    assert snaps[0].best_bid == 98
    assert snaps[0].best_ask == 102
    assert snaps[-1].best_bid == 96
    assert snaps[-1].mid == pytest.approx(100.0)


@pytest.mark.unit
def test_rebuild_books_for_window_filters_other_products(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(
        "\n".join(
            [
                _PRICE_CSV_HEADER,
                "-1;100;OTHER;10;5;;;;;20;5;;;;;15.0;0.0",
                "-1;100;P;99;5;;;;;101;5;;;;;100.0;0.0",
            ]
        )
        + "\n"
    )
    snaps = rebuild_books_for_window(
        data_files=[csv_path], product="P", start_ts=100, end_ts=100
    )
    assert len(snaps) == 1
    assert snaps[0].product == "P"
    assert snaps[0].best_bid == 99


# ------------------------------------------------------- integration tests


@pytest.mark.integration
def test_write_case_artifacts_taker_case_writes_all_files(tmp_path: Path) -> None:
    pack_dir, _ = _write_pack(tmp_path, _taker_result(), label="taker")
    pack = load_review_pack(pack_dir)
    case = select_by_trade_id(pack, 0)
    window = build_case_window(case, pack, window_radius=2)

    out_root = pack_dir / "drilldowns"
    case_dir = write_case_artifacts(
        case, window, out_dir=out_root, pack=pack, render_charts=True
    )

    assert case_dir.is_dir()
    assert (case_dir / "summary.json").is_file()
    assert (case_dir / "window_series.json").is_file()
    assert (case_dir / "notes.md").is_file()

    summary = json.loads((case_dir / "summary.json").read_text())
    assert summary["kind"] == "trade"
    assert summary["product"] == "P"
    assert summary["anchor_timestamp"] == 100
    assert summary["extra"]["side"] == "buy"
    assert summary["extra"]["mode"] == "taker"
    # For a taker fill, decision and fill timestamps are the same.
    assert summary["extra"]["decision_timestamp"] == summary["extra"]["fill_timestamp"]

    window_payload = json.loads((case_dir / "window_series.json").read_text())
    assert window_payload["product"] == "P"
    assert len(window_payload["mid_series"]) >= 1
    assert window_payload["book_snapshots"]

    charts_dir = case_dir / "charts"
    assert charts_dir.is_dir()
    charts = {p.name for p in charts_dir.iterdir()}
    assert "price_vs_fair_window.png" in charts
    assert "book_depth.png" in charts
    assert "pnl_position_window.png" in charts


@pytest.mark.integration
def test_write_case_artifacts_maker_case_preserves_decision_vs_fill_ts(
    tmp_path: Path,
) -> None:
    pack_dir, _ = _write_pack(tmp_path, _maker_result(), label="maker")
    pack = load_review_pack(pack_dir)
    case = select_by_trade_id(pack, 0)
    assert case.anchor_timestamp == 100  # anchored on the fill timestamp
    assert case.extra["decision_timestamp"] == 0
    assert case.extra["fill_timestamp"] == 100

    window = build_case_window(case, pack, window_radius=2)
    out_root = pack_dir / "drilldowns"
    case_dir = write_case_artifacts(
        case, window, out_dir=out_root, pack=pack, render_charts=True
    )

    summary = json.loads((case_dir / "summary.json").read_text())
    # Maker fills must preserve the gap between decision and fill.
    assert summary["extra"]["decision_timestamp"] == 0
    assert summary["extra"]["fill_timestamp"] == 100
    assert summary["extra"]["mode"] == "maker"
    # The anchor we drill on is the fill timestamp so the chart window is
    # centered on when the position actually changed.
    assert summary["anchor_timestamp"] == 100
    # And the trade ends up in the window slice.
    assert summary["trades_in_window"][0]["mode"] == "maker"


@pytest.mark.unit
def test_select_near_limit_picks_extreme_steps(tmp_path: Path) -> None:
    pack_dir, _ = _write_pack(tmp_path, _near_limit_result(), label="nl")
    pack = load_review_pack(pack_dir)
    cases = select_near_limit(pack, n=5)
    # pos=15 >= 0.75*20 at ts=100, 200, 300. Position 0 at ts=0 is below.
    assert [c.anchor_timestamp for c in cases] == [100, 200, 300]
    assert all(c.kind == "near_limit" for c in cases)
    assert cases[0].extra["position"] == 15
    assert cases[0].extra["position_limit"] == 20
    assert cases[0].extra["abs_ratio"] == pytest.approx(0.75)


@pytest.mark.integration
def test_near_limit_case_writes_artifacts(tmp_path: Path) -> None:
    pack_dir, _ = _write_pack(tmp_path, _near_limit_result(), label="nl_write")
    pack = load_review_pack(pack_dir)
    cases = select_near_limit(pack, n=1)
    assert cases, "fixture should trigger at least one near-limit case"
    case = cases[0]
    window = build_case_window(case, pack, window_radius=2)
    case_dir = write_case_artifacts(
        case, window, out_dir=pack_dir / "drilldowns", pack=pack, render_charts=True
    )
    summary = json.loads((case_dir / "summary.json").read_text())
    assert summary["kind"] == "near_limit"
    assert summary["extra"]["position"] == 15
    assert (case_dir / "notes.md").read_text().startswith("# Drilldown:")
    assert (case_dir / "charts" / "price_vs_fair_window.png").is_file()


@pytest.mark.unit
def test_book_snapshot_mid_handles_one_sided_book() -> None:
    full = BookSnapshot(timestamp=1, product="P", bids=((99, 5),), asks=((101, 5),))
    assert full.mid == pytest.approx(100.0)
    one_sided = BookSnapshot(timestamp=2, product="P", bids=((99, 5),), asks=())
    assert one_sided.mid is None
    assert one_sided.best_ask is None


@pytest.mark.unit
def test_drilldown_case_is_immutable() -> None:
    case = DrilldownCase(
        case_id="x",
        kind="trade",
        product="P",
        anchor_timestamp=100,
    )
    with pytest.raises(Exception):
        case.product = "Q"  # type: ignore[misc]


# --------------------------------------------------- hardening + index tests


@pytest.mark.unit
def test_rebuild_books_raises_on_empty_data_files() -> None:
    with pytest.raises(DrilldownError, match="no data_files"):
        rebuild_books_for_window(
            data_files=[], product="P", start_ts=0, end_ts=100
        )


@pytest.mark.unit
def test_rebuild_books_raises_on_missing_price_csv(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(DrilldownError, match="missing price CSVs"):
        rebuild_books_for_window(
            data_files=[missing], product="P", start_ts=0, end_ts=100
        )


@pytest.mark.unit
def test_rebuild_books_raises_on_malformed_price_csv(tmp_path: Path) -> None:
    broken = tmp_path / "prices.csv"
    broken.write_text("not;a;valid;header\n1;2;3;4\n")
    with pytest.raises(DrilldownError, match="missing required columns"):
        rebuild_books_for_window(
            data_files=[broken], product="P", start_ts=0, end_ts=100
        )


@pytest.mark.unit
def test_rebuild_books_ignores_only_trades_csv_and_errors(tmp_path: Path) -> None:
    trade_only = tmp_path / "trades_round_0_day_-1.csv"
    trade_only.write_text("symbol;timestamp\nP;100\n")
    with pytest.raises(DrilldownError, match="no price CSVs"):
        rebuild_books_for_window(
            data_files=[trade_only], product="P", start_ts=0, end_ts=100
        )


@pytest.mark.unit
def test_update_drilldowns_index_upserts_by_case_id(tmp_path: Path) -> None:
    pack_dir, _ = _write_pack(tmp_path, _taker_result(), label="idx")
    pack = load_review_pack(pack_dir)
    out_root = pack_dir / "drilldowns"
    out_root.mkdir(parents=True, exist_ok=True)

    case_a = select_by_trade_id(pack, 0)
    case_b = select_by_trade_id(pack, 1)
    update_drilldowns_index(out_root, pack=pack, cases=[case_a])
    update_drilldowns_index(out_root, pack=pack, cases=[case_b, case_a])

    payload = json.loads((out_root / "index.json").read_text())
    assert payload["parent_run_id"] == pack.run_id
    case_ids = [entry["case_id"] for entry in payload["cases"]]
    # Two distinct case ids, even though case_a was written twice.
    assert sorted(case_ids) == sorted({case_a.case_id, case_b.case_id})
    entry_a = next(c for c in payload["cases"] if c["case_id"] == case_a.case_id)
    assert entry_a["selector"] == "trade"
    assert entry_a["product"] == "P"
    assert entry_a["anchor_timestamp"] == case_a.anchor_timestamp
    assert entry_a["trade_index"] == 0
    assert entry_a["case_dir"].endswith(case_a.case_id)


@pytest.mark.unit
def test_update_drilldowns_index_recovers_from_corrupted_file(tmp_path: Path) -> None:
    pack_dir, _ = _write_pack(tmp_path, _taker_result(), label="corrupt_idx")
    pack = load_review_pack(pack_dir)
    out_root = pack_dir / "drilldowns"
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "index.json").write_text("{not valid json")

    case = select_by_trade_id(pack, 0)
    update_drilldowns_index(out_root, pack=pack, cases=[case])

    payload = json.loads((out_root / "index.json").read_text())
    assert len(payload["cases"]) == 1
    assert payload["cases"][0]["case_id"] == case.case_id


@pytest.mark.integration
def test_run_drilldown_cli_subprocess_writes_case_and_index(
    tmp_path: Path,
) -> None:
    """End-to-end subprocess check for ``python -m src.scripts.run_drilldown``.

    Uses a synthetic pack so the test is hermetic (no tutorial CSVs
    required) and verifies that (a) the CLI exits 0, (b) the case
    directory contains summary/window/notes, and (c) the rolling
    ``index.json`` picks up the new case.
    """
    pack_dir, _ = _write_pack(tmp_path, _taker_result(), label="cli")

    repo_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.scripts.run_drilldown",
            "--pack",
            str(pack_dir),
            "--best-trades",
            "1",
            "--rank-metric",
            "edge",
            "--window",
            "2",
            "--no-charts",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"CLI failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Wrote 1 drilldown case" in result.stdout

    out_root = pack_dir / "drilldowns"
    index_path = out_root / "index.json"
    assert index_path.is_file()
    payload = json.loads(index_path.read_text())
    assert payload["parent_run_id"] == load_review_pack(pack_dir).run_id
    assert len(payload["cases"]) == 1
    case_entry = payload["cases"][0]
    assert case_entry["selector"] == "best"
    assert case_entry["rank_metric"] == "edge"
    assert case_entry["product"] == "P"
    assert case_entry["trade_index"] is not None

    case_dir = out_root / case_entry["case_id"]
    assert (case_dir / "summary.json").is_file()
    assert (case_dir / "window_series.json").is_file()
    assert (case_dir / "notes.md").is_file()
    # --no-charts should suppress chart output.
    assert not (case_dir / "charts").exists()


@pytest.mark.integration
def test_run_drilldown_cli_exits_clean_on_missing_csv(tmp_path: Path) -> None:
    """Deleting the manifest's CSV should produce a readable error, not a traceback."""
    pack_dir, csv_path = _write_pack(
        tmp_path, _taker_result(), label="missing_csv"
    )
    csv_path.unlink()

    repo_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.scripts.run_drilldown",
            "--pack",
            str(pack_dir),
            "--trade-id",
            "0",
            "--no-charts",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 2
    assert "drilldown error" in result.stderr
    assert "missing price CSVs" in result.stderr
    # Should not leak a raw Python traceback on the hardened path.
    assert "Traceback" not in result.stderr
