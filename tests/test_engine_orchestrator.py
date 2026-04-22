"""Integration tests for the EngineOrchestrator + Trader wiring.

Covers:

- Orchestrator conformance: all shipped engines satisfy the
  ``PersistableEngine`` protocol.
- Persistence round-trip: ``to_state`` / ``from_state`` restores engine
  state across a fresh orchestrator + EngineState.
- Handled-product dispatch: the orchestrator claims its owned products
  and the Trader skips per-product dispatch on them.
- Crash telemetry: an engine whose ``step`` raises does not crash the
  tick; the other engines still run and the Trader still returns.
- Conversions aggregation: ``total_conversions`` flows back to the
  Prosperity container.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.conversions.layer import ConversionSpec, RemoteQuote
from src.core.primitives.engine_orchestrator import (
    EngineOrchestrator,
    EngineStepResult,
    PersistableEngine,
)
from src.core.primitives.portfolio_context import (
    PortfolioSnapshot,
    build_portfolio_snapshot,
)
from src.core.primitives.portfolio_risk import PortfolioRiskManager, ProductTag
from src.core.primitives.signal_bus import SignalBus
from src.core.state_store import StateStore
from src.core.types import BookLevel, EngineState, NormalizedSnapshot
from src.datamodel import (
    ConversionObservation,
    Observation,
    Order,
    TradingState,
)
from src.engines.basket_arb import BasketArbConfig, BasketArbEngine, BasketSpec
from src.engines.stat_arb import StatArbConfig, StatArbEngine
from src.trader import Trader


# ============================================================= helpers


def _snap(
    product: str,
    bids: list[tuple[int, int]],
    asks: list[tuple[int, int]],
    position: int = 0,
) -> NormalizedSnapshot:
    return NormalizedSnapshot(
        product=product,
        timestamp=0,
        bids=tuple(BookLevel(price=p, volume=v) for p, v in bids),
        asks=tuple(BookLevel(price=p, volume=v) for p, v in asks),
        position=position,
    )


@dataclass
class _FakeEngine:
    """Minimal PersistableEngine for orchestrator tests."""

    engine_id: str
    owned: frozenset[str] = field(default_factory=frozenset)
    step_calls: int = 0
    raise_on_step: bool = False
    orders_to_emit: tuple[Order, ...] = ()
    conversions_to_emit: int = 0
    persisted_counter: int = 0

    @property
    def owned_products(self) -> frozenset[str]:
        return self.owned

    def step(
        self, portfolio: PortfolioSnapshot, *, current_tick: int,
    ) -> EngineStepResult:
        self.step_calls += 1
        if self.raise_on_step:
            raise RuntimeError(f"{self.engine_id} blew up")
        tags: dict[str, ProductTag] = {}
        for p in self.owned:
            tags[p] = ProductTag(product=p, strategy_tag="arb")
        return EngineStepResult(
            orders=list(self.orders_to_emit),
            conversions=self.conversions_to_emit,
            tags=tags,
        )

    def to_state(self) -> dict:
        self.persisted_counter += 1
        return {"step_calls": self.step_calls, "persisted": self.persisted_counter}

    def from_state(self, blob: dict) -> None:
        self.step_calls = int(blob.get("step_calls", 0))
        self.persisted_counter = int(blob.get("persisted", 0))


# ============================================================= Protocol


@pytest.mark.unit
def test_all_shipped_engines_satisfy_protocol():
    """Each engine class exposes the PersistableEngine attributes."""
    from src.engines.basket_arb import BasketArbEngine
    from src.engines.counterparty_intel import CounterpartyIntelEngine
    from src.engines.options_mm import OptionsEngine
    from src.engines.stat_arb import StatArbEngine

    for cls in (
        BasketArbEngine, CounterpartyIntelEngine, OptionsEngine, StatArbEngine,
    ):
        for attr in ("engine_id", "owned_products", "step", "to_state", "from_state"):
            assert hasattr(cls, attr), f"{cls.__name__} missing {attr}"


@pytest.mark.unit
def test_orchestrator_rejects_duplicate_engine_ids():
    """Two engines cannot share an engine_id — state would collide."""
    engines = [_FakeEngine(engine_id="same"), _FakeEngine(engine_id="same")]
    with pytest.raises(ValueError, match="Duplicate engine_id"):
        EngineOrchestrator(engines=engines)


@pytest.mark.unit
def test_orchestrator_rejects_empty_engine_id():
    with pytest.raises(ValueError, match="empty engine_id"):
        EngineOrchestrator(engines=[_FakeEngine(engine_id="")])


@pytest.mark.unit
def test_orchestrator_accepts_pre_built_signal_bus():
    """Canonical wiring: a shared SignalBus is passed to both the
    orchestrator and each engine's ``bus=`` constructor arg. This
    test locks that contract in so signals emitted by one engine
    reach another engine (and the per-tick clear() hits the right
    instance).
    """
    shared = SignalBus()
    orch = EngineOrchestrator(engines=[], signal_bus=shared)
    assert orch.signal_bus is shared, (
        "orchestrator must use the injected bus, not a fresh one"
    )


@pytest.mark.unit
def test_orchestrator_creates_default_bus_when_none_provided():
    """Legacy callers that did not pass a bus still get a usable one."""
    orch = EngineOrchestrator(engines=[])
    assert orch.signal_bus is not None


# ============================================================= step


@pytest.mark.unit
def test_orchestrator_aggregates_orders_and_conversions():
    o1 = Order("A", 100, 5)
    o2 = Order("B", 50, -3)
    engines = [
        _FakeEngine(
            engine_id="e1", owned=frozenset({"A"}),
            orders_to_emit=(o1,), conversions_to_emit=4,
        ),
        _FakeEngine(
            engine_id="e2", owned=frozenset({"B"}),
            orders_to_emit=(o2,), conversions_to_emit=-2,
        ),
    ]
    orch = EngineOrchestrator(engines=engines)
    portfolio = build_portfolio_snapshot(
        timestamp=0, snapshots={}, position_limits={},
    )
    summary = orch.step(portfolio, current_tick=0)
    assert summary.total_conversions == 2  # 4 + -2
    assert summary.orders_by_product["A"] == [o1]
    assert summary.orders_by_product["B"] == [o2]
    assert summary.handled_products == {"A", "B"}
    assert not summary.errored_engines


@pytest.mark.unit
def test_orchestrator_isolates_engine_crash_from_tick():
    """One engine raising does not prevent others from running."""
    crashy = _FakeEngine(engine_id="crashy", raise_on_step=True)
    healthy = _FakeEngine(
        engine_id="healthy", owned=frozenset({"C"}),
        orders_to_emit=(Order("C", 10, 1),), conversions_to_emit=0,
    )
    orch = EngineOrchestrator(engines=[crashy, healthy])
    portfolio = build_portfolio_snapshot(
        timestamp=0, snapshots={}, position_limits={},
    )
    summary = orch.step(portfolio, current_tick=0)
    assert "crashy" in summary.errored_engines
    assert summary.orders_by_product["C"] == [Order("C", 10, 1)]


# ============================================================= persistence


@pytest.mark.unit
def test_orchestrator_persist_restore_round_trip():
    """to_state → set_engine_state → from_state restores engine state."""
    e = _FakeEngine(engine_id="e1", owned=frozenset({"A"}))
    e.step_calls = 7
    e.persisted_counter = 3
    orch = EngineOrchestrator(engines=[e])
    es = EngineState(version=1)
    orch.persist(es)
    # Fresh orchestrator, fresh engine instance, same EngineState.
    e2 = _FakeEngine(engine_id="e1", owned=frozenset({"A"}))
    orch2 = EngineOrchestrator(engines=[e2])
    orch2.restore(es)
    assert e2.step_calls == 7  # restored from persisted blob


@pytest.mark.unit
def test_persistence_survives_state_store_round_trip():
    """to_state blob travels through StateStore.save / load."""
    e = _FakeEngine(engine_id="e1")
    e.step_calls = 42
    orch = EngineOrchestrator(engines=[e])
    es_out = EngineState(version=1)
    orch.persist(es_out)
    store = StateStore(version=1, max_chars=50_000)
    trader_data = store.save(es_out)
    es_in = store.load(trader_data)
    e2 = _FakeEngine(engine_id="e1")
    orch2 = EngineOrchestrator(engines=[e2])
    orch2.restore(es_in)
    assert e2.step_calls == 42


@pytest.mark.unit
def test_real_stat_arb_engine_state_survives_round_trip():
    """Concrete StatArbEngine regime history persists through the store."""
    cfg = StatArbConfig(
        local_product="MAC",
        conversion_spec=ConversionSpec(conv_cap_per_tick=10),
        regime_lookback=50,
    )
    engine = StatArbEngine(
        config=cfg, risk=PortfolioRiskManager(), bus=SignalBus(),
    )
    # Feed some observations so regime history is populated.
    for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
        engine._regime.observe(v)
    assert len(engine._regime._history) == 5

    orch = EngineOrchestrator(engines=[engine])
    es = EngineState(version=1)
    orch.persist(es)
    store = StateStore(version=1, max_chars=50_000)
    trader_data = store.save(es)
    es_loaded = store.load(trader_data)

    engine2 = StatArbEngine(
        config=cfg, risk=PortfolioRiskManager(), bus=SignalBus(),
    )
    orch2 = EngineOrchestrator(engines=[engine2])
    orch2.restore(es_loaded)
    assert list(engine2._regime._history) == [1.0, 2.0, 3.0, 4.0, 5.0]


# ============================================================= Trader wiring


@pytest.mark.unit
def test_trader_without_orchestrator_behaves_like_legacy():
    """Baseline: Trader() with no orchestrator returns conversions=0 and
    ignores cross-product plumbing entirely."""
    trader = Trader()
    state = TradingState(
        traderData="", timestamp=0, listings={}, order_depths={},
        own_trades={}, market_trades={}, position={},
        observations=Observation(),
    )
    orders, conv, td = trader.run(state)
    assert conv == 0


@pytest.mark.unit
def test_trader_with_orchestrator_routes_engine_conversions():
    """Orchestrator-emitted conversions bubble up to Trader.run return."""
    e = _FakeEngine(engine_id="e1", conversions_to_emit=5)
    orch = EngineOrchestrator(engines=[e])
    trader = Trader(orchestrator=orch)
    state = TradingState(
        traderData="", timestamp=0, listings={}, order_depths={},
        own_trades={}, market_trades={}, position={},
        observations=Observation(),
    )
    _, conv, _ = trader.run(state)
    assert conv == 5
    assert e.step_calls == 1


@pytest.mark.unit
def test_trader_skips_per_product_dispatch_for_owned_products():
    """An engine's owned products do not also go through per-product dispatch."""
    # This regression test: without the handled_products check, an
    # owned product's strategy could emit contradictory orders.
    engine_order = Order("EMERALDS", 9999, 3)
    e = _FakeEngine(
        engine_id="e1",
        owned=frozenset({"EMERALDS"}),
        orders_to_emit=(engine_order,),
    )
    orch = EngineOrchestrator(engines=[e])
    trader = Trader(orchestrator=orch)
    state = TradingState(
        traderData="", timestamp=0, listings={},
        order_depths={"EMERALDS": _make_depth()},
        own_trades={}, market_trades={},
        position={"EMERALDS": 0},
        observations=Observation(),
    )
    orders, _, _ = trader.run(state)
    # The engine's order should be the only one for EMERALDS.
    assert orders.get("EMERALDS") == [engine_order]


@pytest.mark.unit
def test_trader_passes_remote_quotes_from_conversion_observations():
    """ConversionObservation → RemoteQuote plumbing reaches StatArbEngine."""
    cfg = StatArbConfig(
        local_product="MAC",
        conversion_spec=ConversionSpec(
            transport_fee=1.0, conv_cap_per_tick=10,
        ),
    )
    engine = StatArbEngine(
        config=cfg, risk=PortfolioRiskManager(), bus=SignalBus(),
    )
    orch = EngineOrchestrator(engines=[engine])
    trader = Trader(orchestrator=orch)

    # Local bid at 110 >> remote + transport ⇒ should emit a sell-local.
    obs = Observation(conversionObservations={
        "MAC": ConversionObservation(
            bidPrice=100.0, askPrice=102.0, transportFees=1.0,
            exportTariff=0.0, importTariff=0.0, sunlight=0.0, humidity=0.0,
        ),
    })
    state = TradingState(
        traderData="", timestamp=0, listings={},
        order_depths={"MAC": _make_depth(bid=110, ask=112)},
        own_trades={}, market_trades={},
        position={"MAC": 0}, observations=obs,
    )
    orders, _, _ = trader.run(state)
    mac_orders = orders.get("MAC", [])
    assert any(o.quantity < 0 for o in mac_orders), (
        f"expected sell-local from stat-arb engine; got {mac_orders}"
    )


# ============================================================= helpers


def _make_depth(bid: int = 100, ask: int = 102):
    from src.datamodel import OrderDepth
    d = OrderDepth()
    d.buy_orders = {bid: 50}
    d.sell_orders = {ask: -50}
    return d
