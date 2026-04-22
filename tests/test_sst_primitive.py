"""Unit tests for the Take / Clear / Make SST primitive."""

from __future__ import annotations

import pytest

from src.core.primitives.sst import SSTParams, TradingDecision, take_clear_make
from src.core.types import BookLevel, NormalizedSnapshot, TradePrint


def _book(bids: list[tuple[int, int]], asks: list[tuple[int, int]]) -> NormalizedSnapshot:
    return NormalizedSnapshot(
        product="TEST",
        timestamp=0,
        bids=tuple(BookLevel(price=p, volume=v) for p, v in bids),
        asks=tuple(BookLevel(price=p, volume=v) for p, v in asks),
        position=0,
    )


@pytest.mark.unit
def test_sst_params_validates_negative_widths():
    with pytest.raises(ValueError, match="take_width"):
        SSTParams(take_width=-1.0)
    with pytest.raises(ValueError, match="default_edge"):
        SSTParams(default_edge=-0.5)


@pytest.mark.unit
def test_sst_params_validates_clear_threshold_range():
    with pytest.raises(ValueError, match="clear_threshold"):
        SSTParams(clear_threshold=1.5)
    with pytest.raises(ValueError, match="clear_threshold"):
        SSTParams(clear_threshold=-0.1)


@pytest.mark.unit
def test_sst_take_crosses_cheap_ask():
    """Ask at 9998 below buy_take_threshold (10000 - take_width=1.0 = 9999) ⇒ take."""
    snap = _book(bids=[(9990, 20)], asks=[(9998, 15)])
    dec = take_clear_make(
        product="TEST",
        fair_value=10000,
        snapshot=snap,
        position=0,
        position_limit=80,
        params=SSTParams(take_width=1.0, default_quote_size=20, max_taker_size=30),
    )
    buys = [o for o in dec.orders if o.quantity > 0]
    assert any(
        o.price == 9998 and o.quantity > 0 and o.quantity <= 15 for o in buys
    ), f"expected take_buy at 9998; got {dec.orders}"


@pytest.mark.unit
def test_sst_take_crosses_rich_bid():
    """Bid at 10002 above sell_take_threshold ⇒ take (sell to it)."""
    snap = _book(bids=[(10002, 25)], asks=[(10020, 10)])
    dec = take_clear_make(
        product="TEST",
        fair_value=10000,
        snapshot=snap,
        position=0,
        position_limit=80,
        params=SSTParams(take_width=1.0, default_quote_size=20, max_taker_size=30),
    )
    sells = [o for o in dec.orders if o.quantity < 0]
    assert any(
        o.price == 10002 and -o.quantity > 0 and -o.quantity <= 25 for o in sells
    ), f"expected take_sell at 10002; got {dec.orders}"


@pytest.mark.unit
def test_sst_no_take_when_opponent_inside_take_width():
    """Opponent ask at 9999.5 (inside take_width=1.0 of fair=10000) ⇒ don't take."""
    snap = _book(bids=[(9990, 20)], asks=[(9999, 15)])  # 9999 >= 10000 - 1
    dec = take_clear_make(
        product="TEST",
        fair_value=10000,
        snapshot=snap,
        position=0,
        position_limit=80,
        params=SSTParams(take_width=1.5, default_quote_size=20),
    )
    buys = [o for o in dec.orders if o.quantity > 0 and o.price == 9999]
    assert not buys, f"should not cross at 9999 with take_width 1.5; got {dec.orders}"


@pytest.mark.unit
def test_sst_make_places_symmetric_maker_quotes():
    """No crossing orders ⇒ emit bid at fair - default_edge, ask at fair + default_edge."""
    snap = _book(bids=[(9990, 20)], asks=[(10010, 15)])
    dec = take_clear_make(
        product="TEST",
        fair_value=10000,
        snapshot=snap,
        position=0,
        position_limit=80,
        params=SSTParams(
            take_width=1.0,
            default_edge=3.0,
            default_quote_size=20,
            disregard_edge=1.0,
            join_edge=2.0,
        ),
    )
    bids = [o for o in dec.orders if o.quantity > 0]
    asks = [o for o in dec.orders if o.quantity < 0]
    assert len(bids) == 1 and bids[0].price == 9997
    assert len(asks) == 1 and asks[0].price == 10003


@pytest.mark.unit
def test_sst_clear_mode_suppresses_long_bid():
    """Long inventory at / past clear_threshold ⇒ suppress bid."""
    snap = _book(bids=[(9990, 20)], asks=[(10010, 15)])
    dec = take_clear_make(
        product="TEST",
        fair_value=10000,
        snapshot=snap,
        position=60,  # 60/80 = 0.75 > 0.5 clear_threshold
        position_limit=80,
        params=SSTParams(clear_threshold=0.5, default_quote_size=20),
    )
    bids = [o for o in dec.orders if o.quantity > 0]
    assert not bids, f"should not place bid when long and flattening; got {dec.orders}"
    # Should have a sell-side order (either take or maker).
    sells = [o for o in dec.orders if o.quantity < 0]
    assert sells, "should still quote ask side in clear mode"
    assert dec.mode == "recovery"


@pytest.mark.unit
def test_sst_clear_mode_suppresses_short_ask():
    """Short inventory past threshold ⇒ suppress ask."""
    snap = _book(bids=[(9990, 20)], asks=[(10010, 15)])
    dec = take_clear_make(
        product="TEST",
        fair_value=10000,
        snapshot=snap,
        position=-60,
        position_limit=80,
        params=SSTParams(clear_threshold=0.5, default_quote_size=20),
    )
    asks = [o for o in dec.orders if o.quantity < 0]
    assert not asks, f"should not place ask when short and flattening; got {dec.orders}"
    assert dec.mode == "recovery"


@pytest.mark.unit
def test_sst_invalid_fair_returns_idle():
    snap = _book(bids=[(9990, 20)], asks=[(10010, 15)])
    dec = take_clear_make(
        product="TEST",
        fair_value=0.0,  # invalid
        snapshot=snap,
        position=0,
        position_limit=80,
        params=SSTParams(),
    )
    assert dec.mode == "idle"
    assert not dec.orders
    assert "invalid" in dec.rationale


@pytest.mark.unit
def test_sst_no_orders_when_position_limit_reached_both_sides():
    """Fully long + no buyer ⇒ emit ask only."""
    snap = _book(bids=[(9990, 20)], asks=[(10010, 15)])
    dec = take_clear_make(
        product="TEST",
        fair_value=10000,
        snapshot=snap,
        position=80,  # at max long
        position_limit=80,
        params=SSTParams(default_quote_size=20),
    )
    buys = [o for o in dec.orders if o.quantity > 0]
    sells = [o for o in dec.orders if o.quantity < 0]
    assert not buys
    assert sells


@pytest.mark.unit
def test_sst_toxic_size_widens_ask():
    """Small sell-side prints (toxic) ⇒ widen ask by 1 tick."""
    # Include a small market trade below mid (sell-side toxicity).
    snap = NormalizedSnapshot(
        product="TEST",
        timestamp=0,
        bids=(BookLevel(price=9990, volume=20),),
        asks=(BookLevel(price=10010, volume=15),),
        position=0,
        trades=(TradePrint(price=9995, quantity=1, source="market"),),
    )
    params = SSTParams(
        default_edge=3.0, prevent_adverse=True, toxic_size_threshold=2,
    )
    dec = take_clear_make(
        product="TEST",
        fair_value=10000,
        snapshot=snap,
        position=0,
        position_limit=80,
        params=params,
    )
    asks = [o for o in dec.orders if o.quantity < 0]
    assert len(asks) == 1
    # Normal ask would be 10003; toxic widens by +1 ⇒ 10004.
    assert asks[0].price == 10004, f"expected 10004 (widened); got {asks[0].price}"


@pytest.mark.unit
def test_sst_metadata_populated():
    snap = _book(bids=[(9990, 20)], asks=[(10010, 15)])
    dec = take_clear_make(
        product="TEST",
        fair_value=10000,
        snapshot=snap,
        position=40,
        position_limit=80,
        params=SSTParams(),
    )
    assert dec.metadata["fair_value"] == 10000
    assert dec.metadata["position_ratio"] == 0.5
    assert dec.metadata["flattening"] is True  # 0.5 >= default clear_threshold 0.5


@pytest.mark.unit
def test_sst_deterministic():
    """Same inputs → same outputs (pure function)."""
    snap = _book(bids=[(9990, 20)], asks=[(10010, 15)])
    params = SSTParams()
    d1 = take_clear_make(
        product="TEST", fair_value=10000, snapshot=snap,
        position=0, position_limit=80, params=params,
    )
    d2 = take_clear_make(
        product="TEST", fair_value=10000, snapshot=snap,
        position=0, position_limit=80, params=params,
    )
    assert [(o.symbol, o.price, o.quantity) for o in d1.orders] == \
           [(o.symbol, o.price, o.quantity) for o in d2.orders]


# ======================================================== quote-inside-wall


@pytest.mark.unit
def test_sst_inside_wall_pegs_quote_one_tick_inside_max_volume_level():
    """With ``quote_inside_wall=True``, maker quotes sit one tick toward
    mid from the largest-volume level on each side. F2 pattern.
    """
    # Wall bid at 9990 volume 50 (largest); best bid is 9998 volume 2.
    # Wall ask at 10010 volume 50; best ask is 10002 volume 2.
    snap = _book(
        bids=[(9998, 2), (9990, 50), (9985, 5)],
        asks=[(10002, 2), (10010, 50), (10015, 5)],
    )
    dec = take_clear_make(
        product="TEST", fair_value=10000, snapshot=snap,
        position=0, position_limit=80,
        params=SSTParams(
            quote_inside_wall=True,
            wall_min_volume=10,
            default_quote_size=20,
            take_width=10.0,  # don't trigger take
        ),
    )
    # Expected: bid at 9990 + 1 = 9991, ask at 10010 - 1 = 10009.
    bids = [o for o in dec.orders if o.quantity > 0]
    asks = [o for o in dec.orders if o.quantity < 0]
    assert any(o.price == 9991 for o in bids), (
        f"expected bid inside wall at 9991; got {[(o.price, o.quantity) for o in bids]}"
    )
    assert any(o.price == 10009 for o in asks), (
        f"expected ask inside wall at 10009; got {[(o.price, o.quantity) for o in asks]}"
    )


@pytest.mark.unit
def test_sst_inside_wall_falls_back_to_edge_when_no_wall():
    """If no level meets ``wall_min_volume`` on a side, fall back to the
    edge-from-fair maker pricing for that side.
    """
    # Every level volume below wall_min_volume=10.
    snap = _book(bids=[(9990, 5), (9985, 3)], asks=[(10010, 5), (10015, 3)])
    dec = take_clear_make(
        product="TEST", fair_value=10000, snapshot=snap,
        position=0, position_limit=80,
        params=SSTParams(
            quote_inside_wall=True,
            wall_min_volume=10,
            default_edge=2.0,
            default_quote_size=20,
            take_width=10.0,
        ),
    )
    # Fall back to fair±edge: bid=9998, ask=10002.
    bids = [o for o in dec.orders if o.quantity > 0]
    asks = [o for o in dec.orders if o.quantity < 0]
    assert any(o.price == 9998 for o in bids)
    assert any(o.price == 10002 for o in asks)


@pytest.mark.unit
def test_sst_inside_wall_disabled_by_default():
    """Default params preserve existing behaviour — no regression."""
    params = SSTParams()
    assert params.quote_inside_wall is False


@pytest.mark.unit
def test_sst_inside_wall_still_respects_do_not_cross_spread():
    """Inside-wall must not post a bid at or above the opposing touch."""
    # Best ask at 10005; wall bid at 10004 v 50 (pathological). The
    # inside-wall candidate is 10005 which equals the opposing touch —
    # engine must clamp to best_ask - 1 = 10004.
    snap = _book(bids=[(10004, 50)], asks=[(10005, 20)])
    dec = take_clear_make(
        product="TEST", fair_value=10000, snapshot=snap,
        position=0, position_limit=80,
        params=SSTParams(
            quote_inside_wall=True,
            wall_min_volume=10,
            default_quote_size=10,
            take_width=50.0,  # no take
        ),
    )
    bids = [o for o in dec.orders if o.quantity > 0]
    # No bid may be at or above best ask (10005).
    for o in bids:
        assert o.price < 10005
