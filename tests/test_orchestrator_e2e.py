"""End-to-end smoke test: real engine + orchestrator + Trader + replay data.

Fills a gap left by ``test_engine_orchestrator.py``, which stubs engines
behind ``_FakeEngine``. Here we drive the full chain:

    tutorial CSV
        → ReplayEngine.build_trading_state
            → Trader.run (with EngineOrchestrator containing a real engine)
                → PortfolioSnapshot / SignalBus / engine.step
                    → Order list + trader_data round-trip

Two engines are exercised:

- ``BasketArbEngine`` on a synthetic basket-of-tutorial-products
  (EMERALDS + TOMATOES) — verifies PortfolioSnapshot plumbing and the
  engine_state persistence round-trip across ticks.
- ``StatArbEngine`` on a single tutorial product with a synthetic
  ``ConversionObservation`` injected into the state — verifies the
  RemoteQuote adapter and conversions aggregation.

These tests are deliberately integration-level (marked as such). They
read CSVs and execute ~50 ticks, which is slow compared to unit tests
but fast enough to keep in the default suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.backtest.replay_engine import ReplayEngine
from src.conversions.layer import ConversionSpec, StockpileConfig
from src.core.primitives.engine_orchestrator import EngineOrchestrator
from src.core.primitives.portfolio_risk import PortfolioRiskManager
from src.core.primitives.signal_bus import SignalBus
from src.datamodel import ConversionObservation, Observation, TradingState
from src.engines.basket_arb import BasketArbConfig, BasketArbEngine, BasketSpec
from src.engines.stat_arb import StatArbConfig, StatArbEngine
from src.trader import Trader

REPO_ROOT = Path(__file__).resolve().parents[1]
_TUTORIAL_DIR = REPO_ROOT / "data" / "raw" / "tutorial_round_1"


def _tutorial_replay(limit_ticks: int = 50) -> list[TradingState]:
    """Load a short slice of tutorial ticks into TradingState objects."""
    price_files = sorted(_TUTORIAL_DIR.glob("prices_round_0_day_-*.csv"))
    if not price_files:
        pytest.skip("Tutorial CSVs not available in this checkout")
    engine = ReplayEngine.from_files(price_paths=price_files[:1])
    states: list[TradingState] = []
    for step in list(engine.iter_steps())[:limit_ticks]:
        states.append(
            ReplayEngine.build_trading_state(
                step, trader_data="", position={}, own_trades={},
            )
        )
    return states


# ============================================================= basket engine


@pytest.mark.integration
def test_basket_engine_runs_through_trader_on_replay_ticks():
    """Drive BasketArbEngine through a real Trader on replay ticks.

    The tutorial data has no real basket; we treat EMERALDS as a
    "basket" of 1× TOMATOES (pure nonsense economically, but it
    exercises the plumbing). The engine should:
      - accumulate Welford stats across ticks
      - emit validated spread-z signals after warmup
      - survive the persistence round-trip
    """
    states = _tutorial_replay(limit_ticks=30)
    if not states:
        pytest.skip("No replay states")

    # Find products actually present in the first state.
    first_products = set(states[0].order_depths.keys())
    if not {"EMERALDS", "TOMATOES"}.issubset(first_products):
        pytest.skip(
            "Tutorial ticks missing expected products; got "
            f"{sorted(first_products)}"
        )

    # Canonical wiring: construct the SignalBus first so both the
    # orchestrator and the engine share one instance. Without this
    # the engine emits to its own private bus that the orchestrator
    # never clears, and signals never reach other engines.
    bus = SignalBus()
    spec = BasketSpec(basket="EMERALDS", weights={"TOMATOES": 1})
    config = BasketArbConfig(welford_warmup=5, abs_thr=10.0, z_thr=1.5)
    engine = BasketArbEngine(
        spec=spec, config=config,
        risk=PortfolioRiskManager(), bus=bus,
    )
    orch = EngineOrchestrator(engines=[engine], signal_bus=bus)
    trader = Trader(orchestrator=orch)

    trader_data = ""
    last_signal_count = 0
    for i, state in enumerate(states):
        # Thread trader_data forward so engine state persists tick-to-tick.
        state = TradingState(
            traderData=trader_data,
            timestamp=state.timestamp,
            listings=state.listings,
            order_depths=state.order_depths,
            own_trades=state.own_trades,
            market_trades=state.market_trades,
            position=state.position,
            observations=state.observations,
        )
        orders, conversions, trader_data = trader.run(state)
        assert isinstance(orders, dict)
        assert isinstance(conversions, int)
        assert isinstance(trader_data, str)

        # After the Welford warmup, the engine should have emitted a
        # validated spread-z signal onto the bus.
        if i >= config.welford_warmup + 1:
            bus = orch.signal_bus
            sig = bus.get(f"basket.{spec.basket}.spread_z", trusted_only=True)
            if sig is not None:
                last_signal_count += 1

    assert last_signal_count > 0, (
        "basket engine never emitted a validated spread-z signal across replay"
    )

    # Persistence: engine state must survive a full trader_data → engine
    # round-trip. Build a new trader instance with a fresh engine and
    # verify the Welford state was restored from trader_data.
    fresh_engine = BasketArbEngine(
        spec=spec, config=config,
        risk=PortfolioRiskManager(), bus=SignalBus(),
    )
    fresh_orch = EngineOrchestrator(engines=[fresh_engine])
    fresh_orch.restore(trader.state_store.load(trader_data))
    assert fresh_engine._stats.n > 0, (
        "engine state was not persisted through trader_data"
    )
    assert fresh_engine._stats.n >= config.welford_warmup


# ============================================================= stat-arb engine


def _state_with_conversion_obs(
    base: TradingState, *, product: str, bid: float, ask: float,
) -> TradingState:
    """Rebuild a TradingState with an injected ConversionObservation."""
    conv = ConversionObservation(
        bidPrice=bid, askPrice=ask, transportFees=1.0,
        exportTariff=0.5, importTariff=0.5,
        sunlight=0.0, humidity=0.0,
    )
    return TradingState(
        traderData=base.traderData,
        timestamp=base.timestamp,
        listings=base.listings,
        order_depths=base.order_depths,
        own_trades=base.own_trades,
        market_trades=base.market_trades,
        position=base.position,
        observations=Observation(
            conversionObservations={product: conv},
        ),
    )


@pytest.mark.integration
def test_stat_arb_engine_reads_remote_quote_through_adapter():
    """Orchestrator + RemoteQuote adapter path works end-to-end.

    Inject a synthetic ConversionObservation on EMERALDS. The stat-arb
    engine should see the remote quote via ``portfolio.remote_for()``,
    detect the (synthetic) edge, and emit at least one order or a
    non-zero conversion across the replay slice.
    """
    states = _tutorial_replay(limit_ticks=15)
    if not states or "EMERALDS" not in states[0].order_depths:
        pytest.skip("Tutorial ticks missing EMERALDS")

    # Set remote quote WELL below local so the arb triggers repeatedly.
    # Local EMERALDS bids around 9990; remote at 8000 ⇒ strong sell-local.
    spec = ConversionSpec(
        transport_fee=1.0, import_tariff=0.5, export_tariff=0.5,
        conv_cap_per_tick=10,
    )
    cfg = StatArbConfig(
        local_product="EMERALDS",
        conversion_spec=spec,
        stockpile_config=StockpileConfig(batch_multiplier=3.0),
    )
    engine = StatArbEngine(config=cfg, risk=PortfolioRiskManager(), bus=SignalBus())
    orch = EngineOrchestrator(engines=[engine])
    trader = Trader(orchestrator=orch)

    total_orders = 0
    trader_data = ""
    for state in states:
        state = _state_with_conversion_obs(
            TradingState(
                traderData=trader_data,
                timestamp=state.timestamp,
                listings=state.listings,
                order_depths=state.order_depths,
                own_trades=state.own_trades,
                market_trades=state.market_trades,
                position=state.position,
                observations=state.observations,
            ),
            product="EMERALDS", bid=8000.0, ask=8005.0,
        )
        orders, _conversions, trader_data = trader.run(state)
        total_orders += len(orders.get("EMERALDS", []))

    assert total_orders > 0, (
        "stat-arb engine never emitted an order despite a 2000-tick edge"
    )


@pytest.mark.integration
def test_orchestrator_state_persists_across_trader_reinstantiation():
    """Engine state survives Trader being rebuilt from traderData.

    Mirrors the live container lifecycle: Prosperity re-creates the
    Trader each tick, so the orchestrator must restore from trader_data
    on every call. Here we prove that running N ticks with one Trader
    then M ticks with a brand-new Trader + new engine instance behaves
    identically to running N+M ticks with a single Trader.
    """
    states = _tutorial_replay(limit_ticks=20)
    if not states:
        pytest.skip("No replay states")

    def _run_once(trader_data: str, tick_states: list[TradingState]) -> str:
        spec = BasketSpec(basket="EMERALDS", weights={"TOMATOES": 1})
        config = BasketArbConfig(welford_warmup=3)
        engine = BasketArbEngine(
            spec=spec, config=config,
            risk=PortfolioRiskManager(), bus=SignalBus(),
        )
        orch = EngineOrchestrator(engines=[engine])
        trader = Trader(orchestrator=orch)
        td = trader_data
        for s in tick_states:
            s2 = TradingState(
                traderData=td,
                timestamp=s.timestamp, listings=s.listings,
                order_depths=s.order_depths, own_trades=s.own_trades,
                market_trades=s.market_trades, position=s.position,
                observations=s.observations,
            )
            _, _, td = trader.run(s2)
        return td

    # Path A: one trader, all 20 ticks.
    td_single = _run_once("", states)

    # Path B: first trader 10 ticks, second trader next 10.
    td_split = _run_once("", states[:10])
    td_split = _run_once(td_split, states[10:])

    # The two final trader_data strings must be identical: same engine
    # state, same product memory, same everything.
    assert td_single == td_split, (
        "engine state did not cleanly round-trip across Trader "
        "reinstantiation — persistence is broken."
    )
