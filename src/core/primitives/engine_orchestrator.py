"""EngineOrchestrator — coordinates cross-product engines.

Design principles:

- **One orchestrator per Trader.** Owns a SignalBus, a CrashTelemetryState,
  and a reference to PortfolioRiskManager shared with per-product strategies.

- **Engines are plugins.** The orchestrator doesn't know about baskets or
  options specifically. Any object that implements the ``PersistableEngine``
  protocol can be registered.

- **Product ownership is explicit.** Each engine declares which products it
  owns via ``owned_products``. The orchestrator surfaces an aggregate set
  so the Trader can skip per-product dispatch for owned products (preventing
  conflicting orders).

- **State persistence is first-class.** ``to_state()`` / ``from_state()``
  round-trip through ``EngineState.engines[engine_id]``. The orchestrator
  handles save/restore; engines own their own serialization shape.

- **Crash-safe dispatch.** Every ``engine.step()`` call is wrapped in
  ``run_with_telemetry``. A single engine crash does not take down the
  entire tick.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from src.core.primitives.crash_telemetry import (
    CrashTelemetryConfig,
    CrashTelemetryState,
    restore_telemetry,
    run_with_telemetry,
    snapshot_telemetry,
)
from src.core.primitives.portfolio_context import PortfolioSnapshot
from src.core.primitives.portfolio_risk import PortfolioRiskManager, ProductTag
from src.core.primitives.signal_bus import SignalBus
from src.core.types import EngineState
from src.datamodel import Order


@runtime_checkable
class PersistableEngine(Protocol):
    """Contract every orchestrated engine must satisfy."""

    @property
    def engine_id(self) -> str:
        """Stable identifier used for state persistence keying."""
        ...

    @property
    def owned_products(self) -> frozenset[str]:
        """Products this engine emits orders for (inclusive of any hedge legs).

        Per-product dispatch is skipped for owned products to prevent
        conflicting orders. An empty set is valid (engine reads state but
        emits no orders this tick — e.g., CounterpartyIntel in pure
        observation mode).
        """
        ...

    def step(
        self, portfolio: PortfolioSnapshot, *, current_tick: int,
    ) -> "EngineStepResult":
        """Emit orders + conversions + tags for this tick."""
        ...

    def to_state(self) -> dict:
        """JSON-serializable snapshot for traderData persistence."""
        ...

    def from_state(self, blob: dict) -> None:
        """Restore from a previously-saved blob. Missing keys → defaults."""
        ...


@dataclass(frozen=True)
class EngineStepResult:
    """Unified return type for every engine step.

    Empty defaults let engines omit what they don't produce (e.g., a pure
    MM engine has conversions=0; a stat-arb engine has conversions != 0;
    a counterparty intelligence engine has orders=[]).
    """

    orders: list[Order] = field(default_factory=list)
    conversions: int = 0
    tags: dict[str, ProductTag] = field(default_factory=dict)


@dataclass
class OrchestratorStepSummary:
    """Aggregate output from one orchestrator tick.

    The Trader consumes ``orders_by_product`` + ``total_conversions`` and
    skips per-product dispatch for products in ``handled_products``.
    """

    orders_by_product: dict[str, list[Order]] = field(
        default_factory=lambda: defaultdict(list)
    )
    total_conversions: int = 0
    tags: dict[str, ProductTag] = field(default_factory=dict)
    handled_products: set[str] = field(default_factory=set)
    errored_engines: list[str] = field(default_factory=list)


class EngineOrchestrator:
    """Central dispatcher for cross-product engines.

    Lifecycle per Trader tick:
    1. ``restore(engine_state)`` — load saved state once at Trader init OR
       every tick (Trader.run() is re-entrant in the Prosperity container).
    2. ``step(portfolio, current_tick=...)`` — runs each engine, aggregates
       results.
    3. ``persist(engine_state)`` — writes fresh state back before
       StateStore.save().
    """

    def __init__(
        self,
        engines: list[PersistableEngine] | None = None,
        *,
        risk: PortfolioRiskManager | None = None,
        crash_config: CrashTelemetryConfig | None = None,
        signal_bus: SignalBus | None = None,
    ) -> None:
        self._engines: list[PersistableEngine] = list(engines or [])
        # Canonical wiring: every engine that wants its emits to reach
        # other engines MUST share this bus. Construct the bus first,
        # pass it to ``signal_bus`` here AND to each engine's ``bus=``
        # constructor argument. If ``signal_bus`` is None, we create a
        # fresh bus — callers who did not share one explicitly can reach
        # it via ``orchestrator.signal_bus`` and pass it to subsequent
        # components.
        self.signal_bus = signal_bus or SignalBus()
        self.risk = risk or PortfolioRiskManager()
        self._crash_config = crash_config or CrashTelemetryConfig()
        self._telemetry = CrashTelemetryState()
        self._validate_engine_ids()

    def _validate_engine_ids(self) -> None:
        seen: set[str] = set()
        for engine in self._engines:
            eid = engine.engine_id
            if not eid:
                raise ValueError(
                    f"Engine {type(engine).__name__} has empty engine_id; "
                    f"state persistence will collide."
                )
            if eid in seen:
                raise ValueError(
                    f"Duplicate engine_id {eid!r}; engine_id must be unique."
                )
            seen.add(eid)

    # ========================================================= lifecycle

    def restore(self, engine_state: EngineState) -> None:
        """Pull per-engine state blobs + crash telemetry from EngineState."""
        for engine in self._engines:
            blob = engine_state.engines.get(engine.engine_id, {})
            if isinstance(blob, dict):
                engine.from_state(blob)
        telemetry_blob = engine_state.engines.get("__telemetry__", {})
        if isinstance(telemetry_blob, dict) and telemetry_blob:
            self._telemetry = restore_telemetry(telemetry_blob)

    def persist(self, engine_state: EngineState) -> None:
        """Push per-engine state back into EngineState for StateStore.save()."""
        for engine in self._engines:
            try:
                blob = engine.to_state()
            except Exception:  # noqa: BLE001 — a bad to_state must not halt the tick
                blob = {}
            if not isinstance(blob, dict):
                blob = {}
            engine_state.set_engine_state(engine.engine_id, blob)
        engine_state.set_engine_state(
            "__telemetry__", snapshot_telemetry(self._telemetry),
        )

    # ========================================================= step

    def step(
        self, portfolio: PortfolioSnapshot, *, current_tick: int,
    ) -> OrchestratorStepSummary:
        """Run every engine, aggregate their orders + conversions + tags."""
        summary = OrchestratorStepSummary()
        # Clear signal bus at tick start. Emitters republish each tick;
        # consumers see a fresh view.
        self.signal_bus.clear()

        if self._telemetry.is_halted():
            # Global kill-switch active: engines are all halted until cooloff.
            self._telemetry.tick_cooloff()
            return summary

        for engine in self._engines:
            for product in engine.owned_products:
                summary.handled_products.add(product)

        for engine in self._engines:
            result, raised = run_with_telemetry(
                lambda e=engine: e.step(portfolio, current_tick=current_tick),
                tick=current_tick,
                product=engine.engine_id,
                state=self._telemetry,
                config=self._crash_config,
                default=EngineStepResult(),
            )
            if raised:
                summary.errored_engines.append(engine.engine_id)
                continue
            for order in result.orders:
                summary.orders_by_product[order.symbol].append(order)
            summary.total_conversions += result.conversions
            summary.tags.update(result.tags)

        return summary

    # ========================================================= introspection

    @property
    def engine_count(self) -> int:
        return len(self._engines)

    @property
    def telemetry(self) -> CrashTelemetryState:
        return self._telemetry

    def engine_ids(self) -> tuple[str, ...]:
        return tuple(e.engine_id for e in self._engines)
