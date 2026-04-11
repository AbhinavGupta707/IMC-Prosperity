"""Unit tests for pure metric helpers in ``src.backtest.metrics``."""

from __future__ import annotations

import pytest

from src.backtest.metrics import (
    ProductResult,
    SimulationResult,
    TradeRecord,
    compute_entry_edges,
    compute_markouts,
    weighted_mean,
)


def _record(
    *,
    product: str = "P",
    side: str = "buy",
    price: float = 100.0,
    quantity: int = 1,
    mode: str = "taker",
    decision_ts: int = 0,
    fill_ts: int | None = None,
    fair: float | None = None,
    method: str | None = None,
    mid_at_decision: float | None = None,
    mid_at_fill: float | None = None,
) -> TradeRecord:
    return TradeRecord(
        product=product,
        side=side,  # type: ignore[arg-type]
        price=price,
        quantity=quantity,
        mode=mode,  # type: ignore[arg-type]
        decision_timestamp=decision_ts,
        fill_timestamp=decision_ts if fill_ts is None else fill_ts,
        fair_value_at_decision=fair,
        fair_value_method_at_decision=method,
        mid_at_decision=mid_at_decision,
        mid_at_fill=mid_at_fill,
    )


# ------------------------------------------------------------ weighted_mean


@pytest.mark.unit
def test_weighted_mean_empty_returns_none() -> None:
    assert weighted_mean([], []) is None


@pytest.mark.unit
def test_weighted_mean_all_zero_weight_returns_none() -> None:
    assert weighted_mean([1.0, 2.0], [0.0, 0.0]) is None


@pytest.mark.unit
def test_weighted_mean_weights_bigger_trades_more() -> None:
    # 1 contributes weight 1, 3 contributes weight 10 -> heavy skew to 3.
    value = weighted_mean([1.0, 3.0], [1.0, 10.0])
    assert value is not None
    assert value == pytest.approx((1.0 * 1 + 3.0 * 10) / 11)


@pytest.mark.unit
def test_weighted_mean_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        weighted_mean([1.0], [1.0, 2.0])


# --------------------------------------------------------- compute_entry_edges


@pytest.mark.unit
def test_compute_entry_edges_buy_positive_when_fair_above_price() -> None:
    records = [_record(side="buy", price=99.0, fair=100.0, quantity=2)]
    out = compute_entry_edges(records)
    assert out["P"] == (pytest.approx(1.0), 1)


@pytest.mark.unit
def test_compute_entry_edges_sell_positive_when_fair_below_price() -> None:
    records = [_record(side="sell", price=101.0, fair=100.0, quantity=2)]
    out = compute_entry_edges(records)
    assert out["P"] == (pytest.approx(1.0), 1)


@pytest.mark.unit
def test_compute_entry_edges_drops_records_with_missing_fair() -> None:
    records = [
        _record(side="buy", price=99.0, fair=100.0, quantity=1),
        _record(side="buy", price=98.0, fair=None, quantity=10),
    ]
    out = compute_entry_edges(records)
    # Only the first record contributes; the big missing one is discarded.
    avg, count = out["P"]
    assert avg == pytest.approx(1.0)
    assert count == 1


@pytest.mark.unit
def test_compute_entry_edges_quantity_weighted() -> None:
    records = [
        _record(side="buy", price=99.0, fair=100.0, quantity=1),  # edge +1 w1
        _record(side="buy", price=95.0, fair=100.0, quantity=9),  # edge +5 w9
    ]
    avg, count = compute_entry_edges(records)["P"]
    assert avg == pytest.approx((1 * 1 + 5 * 9) / 10)
    assert count == 2


@pytest.mark.unit
def test_compute_entry_edges_per_product() -> None:
    records = [
        _record(product="A", side="buy", price=99.0, fair=100.0, quantity=1),
        _record(product="B", side="sell", price=101.0, fair=100.0, quantity=1),
    ]
    out = compute_entry_edges(records)
    assert out["A"] == (pytest.approx(1.0), 1)
    assert out["B"] == (pytest.approx(1.0), 1)


# ----------------------------------------------------------- compute_markouts


def _series(values: list[tuple[int, float]]) -> tuple[tuple[int, float], ...]:
    return tuple(values)


@pytest.mark.unit
def test_compute_markouts_buy_favorable_future_mid() -> None:
    # Fill at ts=10, price 100. Future mids: 100, 102, 104, 106, 108, 110.
    mid_series = {
        "P": _series([(10, 100.0), (11, 102.0), (12, 104.0), (13, 106.0), (14, 108.0), (15, 110.0)])
    }
    records = [_record(product="P", side="buy", price=100.0, fill_ts=10, quantity=1)]
    out = compute_markouts(records, mid_series, (1, 5))
    assert out["P"][1] == (pytest.approx(2.0), 1)
    assert out["P"][5] == (pytest.approx(10.0), 1)


@pytest.mark.unit
def test_compute_markouts_sell_sign_flip() -> None:
    mid_series = {"P": _series([(10, 100.0), (11, 98.0)])}
    records = [_record(product="P", side="sell", price=100.0, fill_ts=10, quantity=1)]
    out = compute_markouts(records, mid_series, (1,))
    # Sell at 100, mid drops to 98 -> favourable, markout +2.
    assert out["P"][1] == (pytest.approx(2.0), 1)


@pytest.mark.unit
def test_compute_markouts_missing_future_step_excludes_horizon() -> None:
    mid_series = {"P": _series([(10, 100.0), (11, 101.0)])}
    records = [_record(product="P", side="buy", price=100.0, fill_ts=10, quantity=1)]
    out = compute_markouts(records, mid_series, (1, 5, 20))
    assert out["P"][1] == (pytest.approx(1.0), 1)
    # Horizons 5 and 20 run past the end of the series -> not present.
    assert 5 not in out["P"]
    assert 20 not in out["P"]


@pytest.mark.unit
def test_compute_markouts_missing_fill_timestamp_skips_record() -> None:
    # fill_timestamp 12 is not in the series (one-sided book there).
    mid_series = {"P": _series([(10, 100.0), (11, 100.0), (13, 100.0)])}
    records = [_record(product="P", side="buy", price=100.0, fill_ts=12, quantity=1)]
    out = compute_markouts(records, mid_series, (1,))
    assert out == {}


@pytest.mark.unit
def test_compute_markouts_quantity_weighted_per_product() -> None:
    mid_series = {
        "P": _series([(0, 100.0), (1, 101.0)]),
    }
    records = [
        _record(product="P", side="buy", price=100.0, fill_ts=0, quantity=1),  # +1 w1
        _record(product="P", side="buy", price=100.0, fill_ts=0, quantity=9),  # +1 w9
    ]
    avg, count = compute_markouts(records, mid_series, (1,))["P"][1]
    assert avg == pytest.approx(1.0)
    assert count == 2


@pytest.mark.unit
def test_compute_markouts_handles_decision_vs_fill_timestamp_divergence() -> None:
    """Maker fill: decision at ts=0, actual clear at ts=2. Markout uses ts=2."""
    mid_series = {
        "P": _series([(0, 100.0), (1, 100.0), (2, 100.0), (3, 103.0)]),
    }
    records = [
        _record(
            product="P",
            side="buy",
            price=100.0,
            quantity=1,
            mode="maker",
            decision_ts=0,
            fill_ts=2,
            fair=101.0,
        )
    ]
    out = compute_markouts(records, mid_series, (1,))
    # 1 step after the fill (ts=3) the mid is 103 -> markout +3.
    assert out["P"][1] == (pytest.approx(3.0), 1)

    edges = compute_entry_edges(records)
    # Entry edge uses fair_value_at_decision = 101 - price 100 = +1.
    assert edges["P"] == (pytest.approx(1.0), 1)


@pytest.mark.unit
def test_compute_markouts_uses_day_aware_keys_when_timestamps_repeat() -> None:
    mid_series = {
        "P": _series([(100, 10.0), (101, 11.0), (100, 30.0), (101, 40.0)]),
    }
    mid_keys = {
        "P": ((-2, 100), (-2, 101), (-1, 100), (-1, 101)),
    }
    records = [
        TradeRecord(
            product="P",
            side="buy",
            price=30.0,
            quantity=1,
            mode="taker",
            decision_timestamp=100,
            fill_timestamp=100,
            fair_value_at_decision=31.0,
            fair_value_method_at_decision="anchor",
            mid_at_decision=30.0,
            mid_at_fill=30.0,
            decision_day=-1,
            fill_day=-1,
        )
    ]
    out = compute_markouts(records, mid_series, (1,), mid_keys=mid_keys)
    # Without day-aware lookup this would incorrectly hit day -2's next step (11.0).
    assert out["P"][1] == (pytest.approx(10.0), 1)


# ----------------------------------------------------- summary_table block


@pytest.mark.unit
def test_summary_table_prints_new_aggregate_block() -> None:
    result = SimulationResult(
        steps=5,
        total_pnl=0.0,
        per_product={
            "P": ProductResult(
                product="P",
                pnl=0.0,
                cash=0.0,
                final_position=0,
                mark_price=100.0,
                order_count=0,
                trade_count=1,
                taker_trade_count=1,
                maker_trade_count=0,
                taker_trade_quantity=1,
                maker_trade_quantity=0,
                buy_trade_quantity=1,
                sell_trade_quantity=0,
                steps_near_limit=0,
                avg_entry_edge=1.5,
                entry_edge_count=1,
                avg_markout_1=2.0,
                markout_1_count=1,
                avg_markout_5=None,
                markout_5_count=0,
                avg_markout_20=None,
                markout_20_count=0,
            )
        },
    )
    text = result.summary_table()
    assert "edge" in text
    assert "mk_1" in text
    assert "mk_20" in text
    # Missing mk_5 / mk_20 should render as n/a.
    assert "n/a" in text
