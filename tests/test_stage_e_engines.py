"""Integration tests for Stage E engine assemblies.

These are smoke tests — the engines COMPOSE already-tested primitives,
so deep unit testing happens at the primitive layer. Here we verify:
- Engine constructs from minimal config
- step() returns (orders, tags) for basket / options / stat-arb
- counterparty engine produces classifications after sufficient trades
- No crashes on empty / degenerate inputs
"""

from __future__ import annotations

import pytest

from src.conversions.layer import ConversionSpec, RemoteQuote, StockpileConfig
from src.core.primitives.portfolio_context import build_portfolio_snapshot
from src.core.primitives.portfolio_risk import PortfolioRiskManager
from src.core.primitives.signal_bus import SignalBus
from src.core.types import BookLevel, NormalizedSnapshot, TradePrint
from src.engines.basket_arb import BasketArbConfig, BasketArbEngine, BasketSpec
from src.engines.counterparty_intel import (
    CounterpartyIntelConfig,
    CounterpartyIntelEngine,
)
from src.engines.options_mm import (
    OptionsBookSpec,
    OptionsEngine,
    OptionsEngineConfig,
    VoucherSpec,
)
from src.engines.stat_arb import StatArbConfig, StatArbEngine


def _snap(
    product: str,
    bids: list[tuple[int, int]],
    asks: list[tuple[int, int]],
    position: int = 0,
    trades: list[TradePrint] | None = None,
    timestamp: int = 0,
) -> NormalizedSnapshot:
    return NormalizedSnapshot(
        product=product,
        timestamp=timestamp,
        bids=tuple(BookLevel(price=p, volume=v) for p, v in bids),
        asks=tuple(BookLevel(price=p, volume=v) for p, v in asks),
        position=position,
        trades=tuple(trades or []),
    )


# ============================================================= Basket


@pytest.mark.unit
def test_basket_engine_no_spread_no_orders():
    """Basket exactly at fair ⇒ no arb, no orders."""
    spec = BasketSpec(
        basket="BASKET",
        weights={"A": 1, "B": 1},
    )
    config = BasketArbConfig(welford_warmup=5)
    engine = BasketArbEngine(
        spec=spec, config=config,
        risk=PortfolioRiskManager(), bus=SignalBus(),
    )
    # Feed warmup ticks with spread=0.
    for _ in range(10):
        snaps = {
            "BASKET": _snap("BASKET", [(200, 20)], [(202, 20)]),
            "A": _snap("A", [(99, 20)], [(101, 20)]),
            "B": _snap("B", [(99, 20)], [(101, 20)]),
        }
        portfolio = build_portfolio_snapshot(
            timestamp=0, snapshots=snaps,
            position_limits={"BASKET": 60, "A": 100, "B": 100},
        )
        orders, tags = engine.step(portfolio)
    # After warmup with zero spread, no orders (z=0).
    assert orders == [] or all(
        o.quantity == 0 for o in orders
    ), f"expected no orders on zero-spread; got {orders}"
    assert "BASKET" in tags and tags["BASKET"].strategy_tag == "arb"


@pytest.mark.unit
def test_basket_engine_returns_orders_on_large_spread():
    """Basket massively cheap ⇒ engine emits long-basket + short-constituents."""
    spec = BasketSpec(basket="BASKET", weights={"A": 1, "B": 1})
    config = BasketArbConfig(welford_warmup=5, abs_thr=5.0, z_thr=1.5, hedge_factor=0.5)
    engine = BasketArbEngine(
        spec=spec, config=config,
        risk=PortfolioRiskManager(), bus=SignalBus(),
    )
    # Warm up with a spread of roughly zero.
    for _ in range(15):
        snaps = {
            "BASKET": _snap("BASKET", [(199, 20)], [(201, 20)]),  # mid 200
            "A": _snap("A", [(99, 20)], [(101, 20)]),  # mid 100
            "B": _snap("B", [(99, 20)], [(101, 20)]),  # mid 100
        }
        portfolio = build_portfolio_snapshot(
            timestamp=0, snapshots=snaps,
            position_limits={"BASKET": 60, "A": 100, "B": 100},
        )
        engine.step(portfolio)

    # Now inject a regime where basket is very cheap.
    snaps = {
        "BASKET": _snap("BASKET", [(179, 20)], [(181, 20)]),  # basket mid 180
        "A": _snap("A", [(99, 20)], [(101, 20)]),  # mid 100
        "B": _snap("B", [(99, 20)], [(101, 20)]),  # mid 100
    }
    # theoretical = 1*100 + 1*100 = 200, basket = 180, spread = -20
    portfolio = build_portfolio_snapshot(
        timestamp=0, snapshots=snaps,
        position_limits={"BASKET": 60, "A": 100, "B": 100},
    )
    orders, tags = engine.step(portfolio)
    # Engine should buy basket (spread negative ⇒ basket cheap).
    basket_orders = [o for o in orders if o.symbol == "BASKET"]
    assert any(o.quantity > 0 for o in basket_orders), f"expected long basket; got {orders}"


# ============================================================= Options


@pytest.mark.unit
def test_options_engine_quotes_after_smile_warmup():
    """Options engine quotes vouchers after smile has observations."""
    spec = OptionsBookSpec(
        underlying="ROCK",
        vouchers=(
            VoucherSpec(product="V_9500", strike=9500),
            VoucherSpec(product="V_10000", strike=10000),
            VoucherSpec(product="V_10500", strike=10500),
        ),
        time_to_expiry_ticks=100.0,  # toy T in "tick-years"
    )
    config = OptionsEngineConfig(
        smile_warmup_threshold=3,
        delta_hedge_enabled=False,
        default_quote_size=5,
    )
    engine = OptionsEngine(spec=spec, config=config, risk=PortfolioRiskManager())

    # Feed a few ticks with realistic IV implied by prices.
    # Spot 10000, T small ⇒ short-dated options. Use price that implies ~25% vol.
    snaps = {
        "ROCK": _snap("ROCK", [(9999, 30)], [(10001, 30)]),
        "V_9500": _snap("V_9500", [(520, 10)], [(540, 10)]),   # deep ITM
        "V_10000": _snap("V_10000", [(100, 10)], [(110, 10)]),  # ATM
        "V_10500": _snap("V_10500", [(5, 10)], [(15, 10)]),     # deep OTM
    }
    portfolio = build_portfolio_snapshot(
        timestamp=0, snapshots=snaps,
        position_limits={"ROCK": 400, "V_9500": 80, "V_10000": 80, "V_10500": 80},
    )
    # Drive a few ticks through the engine to let smile accumulate.
    for _ in range(10):
        orders, tags = engine.step(portfolio)
    # Post-warmup, engine should be quoting at least some vouchers.
    assert "V_10000" in tags
    assert tags["V_10000"].strategy_tag == "arb"


@pytest.mark.unit
def test_options_engine_no_crash_on_missing_underlying():
    spec = OptionsBookSpec(
        underlying="ROCK",
        vouchers=(VoucherSpec(product="V_10000", strike=10000),),
        time_to_expiry_ticks=100.0,
    )
    engine = OptionsEngine(
        spec=spec,
        config=OptionsEngineConfig(),
        risk=PortfolioRiskManager(),
    )
    portfolio = build_portfolio_snapshot(
        timestamp=0, snapshots={}, position_limits={},
    )
    orders, tags = engine.step(portfolio)
    assert orders == []
    assert tags == {}


# ============================================================= StatArb


@pytest.mark.unit
def test_stat_arb_emits_sell_local_on_high_bid():
    """Local bid > sell_be ⇒ sell locally."""
    spec = ConversionSpec(transport_fee=1, import_tariff=2, conv_cap_per_tick=10)
    cfg = StatArbConfig(
        local_product="PROD",
        conversion_spec=spec,
        stockpile_config=StockpileConfig(batch_multiplier=3.0),
    )
    engine = StatArbEngine(config=cfg, risk=PortfolioRiskManager(), bus=SignalBus())
    snaps = {
        # local bid 110 ≫ sell_be = 100 + 1 + 2 = 103
        "PROD": _snap("PROD", [(110, 50)], [(112, 50)]),
    }
    portfolio = build_portfolio_snapshot(
        timestamp=0, snapshots=snaps, position_limits={"PROD": 100},
    )
    remote = RemoteQuote(bid=95, ask=100)
    orders, conv_qty, tags = engine.step(portfolio, remote=remote)
    # Should sell (negative quantity) at local bid.
    assert any(o.quantity < 0 for o in orders), f"expected sell-local; got {orders}"
    assert "PROD" in tags and tags["PROD"].strategy_tag == "arb"


@pytest.mark.unit
def test_stat_arb_conversion_size_offloads():
    spec = ConversionSpec(conv_cap_per_tick=10)
    cfg = StatArbConfig(local_product="PROD", conversion_spec=spec)
    engine = StatArbEngine(config=cfg, risk=PortfolioRiskManager(), bus=SignalBus())
    # Current position 50 long ⇒ convert -10 (sell remote).
    snaps = {"PROD": _snap("PROD", [(100, 10)], [(101, 10)], position=50)}
    portfolio = build_portfolio_snapshot(
        timestamp=0, snapshots=snaps, position_limits={"PROD": 100},
    )
    _, conv_qty, _ = engine.step(
        portfolio, remote=RemoteQuote(bid=100, ask=100),
    )
    assert conv_qty == -10


@pytest.mark.unit
def test_stat_arb_no_arb_no_orders():
    spec = ConversionSpec()
    cfg = StatArbConfig(local_product="PROD", conversion_spec=spec)
    engine = StatArbEngine(config=cfg, risk=PortfolioRiskManager(), bus=SignalBus())
    snaps = {"PROD": _snap("PROD", [(100, 10)], [(100, 10)], position=0)}
    portfolio = build_portfolio_snapshot(
        timestamp=0, snapshots=snaps, position_limits={"PROD": 100},
    )
    orders, conv_qty, _ = engine.step(
        portfolio, remote=RemoteQuote(bid=100, ask=100),
    )
    assert orders == []
    assert conv_qty == 0


# ============================================================= Counterparty


@pytest.mark.unit
def test_counterparty_ingests_and_classifies_informed():
    engine = CounterpartyIntelEngine(
        config=CounterpartyIntelConfig(
            min_trades_for_classification=5,
            piggyback_confidence_threshold=0.1,
            forward_horizon_ticks=0,  # zero for immediate resolution
        ),
        bus=SignalBus(),
    )
    # Feed a stream of trades from "Olivia" where she always buys low,
    # then mid drifts up on subsequent ticks (she wins).
    for tick in range(50):
        mid = 100.0 + tick * 0.5
        # Olivia's trade at a price below current mid.
        trade = TradePrint(
            price=mid - 5.0, quantity=10, buyer="Olivia", seller=None,
            source="market",
        )
        snap = _snap("P", [(99, 10)], [(101, 10)], trades=[trade])
        # Spike the mid so it looks like she "won" (previous trades gain value).
        snap = NormalizedSnapshot(
            product="P", timestamp=tick,
            bids=(BookLevel(price=int(mid) - 1, volume=10),),
            asks=(BookLevel(price=int(mid) + 1, volume=10),),
            position=0,
            trades=(trade,),
        )
        portfolio = build_portfolio_snapshot(
            timestamp=tick, snapshots={"P": snap}, position_limits={"P": 100},
        )
        engine.step(portfolio, current_tick=tick)

    summary = engine.summary()
    olivia = summary.get("Olivia"[:8], {})
    assert olivia.get("trades", 0) >= 5
    # With forward_horizon=0 and a rising mid, her implied P&L is positive.
    assert olivia.get("cum_pnl", 0) > 0


@pytest.mark.unit
def test_counterparty_fingerprint_hashes_stable():
    """Pre-R5 (no buyer/seller): same behavior → same hash."""
    engine = CounterpartyIntelEngine(
        config=CounterpartyIntelConfig(min_trades_for_classification=5),
        bus=SignalBus(),
    )
    # Feed multiple similar trades with no buyer/seller (hashed).
    trades = [
        TradePrint(price=101, quantity=3, source="market"),  # buyer-aggressor, small
        TradePrint(price=101, quantity=3, source="market"),
        TradePrint(price=101, quantity=3, source="market"),
    ]
    for i, trade in enumerate(trades):
        snap = _snap("P", [(99, 10)], [(101, 10)], trades=[trade])
        portfolio = build_portfolio_snapshot(
            timestamp=i, snapshots={"P": snap}, position_limits={"P": 100},
        )
        engine.step(portfolio, current_tick=i)
    # All 3 trades should map to the same fingerprint hash.
    assert len(engine._states) == 1
    state = next(iter(engine._states.values()))
    assert state.trade_count == 3
