"""StatArbEngine (E3) — cross-exchange arb with conversion layer.

Composition of Stage A-D primitives:
- ConversionLayer (D): signed break-even, batched stockpile, regime flags
- PortfolioContext (B): read local book + remote quote state
- PortfolioRiskManager (B): conversion tracking
- SignalBus (C): emit / consume the external-signal regime flag

Engine is small — the heavy math is in conversions.layer. Responsibilities:
- Fetch the local book + remote quote from PortfolioSnapshot
- Read external-signal value from SignalBus (emitted upstream)
- Detect arb edge via signed break-even
- Decide batch size via stockpile optimizer (3× conv_cap_per_tick)
- Switch to accumulation mode on `squeeze` regime, offload on `glut`
- Return EngineStepResult(orders, conversions, tags)

Note: Prosperity separates orders from conversions. This engine returns
both — the orchestrator sums conversions across engines before persisting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.conversions.layer import (
    ConversionSpec,
    RegimeDetector,
    RemoteQuote,
    StockpileConfig,
    arb_edge,
    buy_local_break_even,
    conversion_size,
    sell_local_break_even,
    target_batch_size,
)
from src.core.primitives.engine_orchestrator import EngineStepResult
from src.core.primitives.portfolio_context import PortfolioSnapshot
from src.core.primitives.portfolio_risk import PortfolioRiskManager, ProductTag
from src.core.primitives.signal_bus import SignalBus, SignalValue
from src.datamodel import Order


@dataclass(frozen=True)
class StatArbConfig:
    """Cross-exchange arb configuration."""

    local_product: str
    """The locally-tradable product symbol."""

    conversion_spec: ConversionSpec
    stockpile_config: StockpileConfig = field(default_factory=StockpileConfig)

    # Which external-signal stream to consume from the bus. The signal
    # must be emitted upstream (e.g., by a ConversionIntel engine that
    # reads ConversionObservation.sunlightIndex) BEFORE this engine runs.
    external_signal_name: str | None = None

    # Regime detector wraps the external signal.
    regime_squeeze_pct: float = 0.25
    regime_glut_pct: float = 0.75
    regime_lookback: int = 100

    # In squeeze mode, accumulate up to this absolute inventory before waiting.
    max_squeeze_inventory: int = 75

    # Position limit on local product (fetched from portfolio if 0).
    position_limit_override: int = 0


@dataclass
class StatArbEngine:
    """One cross-exchange arb book."""

    config: StatArbConfig
    risk: PortfolioRiskManager
    bus: SignalBus

    _regime: RegimeDetector = field(init=False)

    def __post_init__(self) -> None:
        self._regime = RegimeDetector(
            lookback_window=self.config.regime_lookback,
            squeeze_percentile=self.config.regime_squeeze_pct,
            glut_percentile=self.config.regime_glut_pct,
        )

    # ====================================================== PersistableEngine

    @property
    def engine_id(self) -> str:
        return f"stat_arb.{self.config.local_product}"

    @property
    def owned_products(self) -> frozenset[str]:
        return frozenset({self.config.local_product})

    def to_state(self) -> dict:
        return {
            "regime_history": list(self._regime._history),
        }

    def from_state(self, blob: dict) -> None:
        from collections import deque as _deque
        try:
            history = blob.get("regime_history", [])
            if isinstance(history, list):
                # Restore into the deque; maxlen will trim if the saved
                # blob is longer than the current lookback window.
                restored = _deque(
                    (float(x) for x in history[-self.config.regime_lookback:]),
                    maxlen=self.config.regime_lookback,
                )
                object.__setattr__(self._regime, "_history", restored)
        except (TypeError, ValueError):
            # Corrupted blob: fall back to fresh detector.
            self._regime = RegimeDetector(
                lookback_window=self.config.regime_lookback,
                squeeze_percentile=self.config.regime_squeeze_pct,
                glut_percentile=self.config.regime_glut_pct,
            )

    # ====================================================== step

    def step(
        self,
        portfolio: PortfolioSnapshot,
        *,
        current_tick: int | None = None,
    ) -> EngineStepResult:
        """Emit orders + conversion qty + tags for this tick.

        Reads the remote quote from ``portfolio.remote_for(local_product)``
        (populated by the conversion adapter) and the external-signal value
        from ``self.bus`` (populated by an upstream conversion-intel emitter).
        """
        _ = current_tick  # part of orchestrator contract; not used here
        snap = portfolio.for_product(self.config.local_product)
        if snap is None:
            return EngineStepResult()

        remote = portfolio.remote_for(self.config.local_product)
        if remote is None:
            # No remote quote this tick → no arb possible, but still return tags
            # so the risk manager sees this engine's footprint.
            return EngineStepResult(tags=self._build_tags())

        pos = portfolio.position_of(self.config.local_product)

        # Read external-signal value from the bus (emitted upstream). Use
        # trusted_only=False because this is a raw observation not a
        # statistically-validated alpha signal — validation happens here
        # inside the regime detector via percentile.
        external_signal_value = self._read_external_signal()

        # Update regime detector if we have an external signal.
        regime: str = "normal"
        if external_signal_value is not None:
            self._regime.observe(external_signal_value)
            regime = self._regime.regime(external_signal_value)
            # Publish a validated regime flag for downstream consumers.
            if self.config.external_signal_name:
                self.bus.emit(
                    SignalValue(
                        name=f"{self.config.external_signal_name}_regime",
                        value={"squeeze": -1.0, "normal": 0.0, "glut": 1.0}[regime],
                        validated=True,
                        metadata={"regime": regime},
                    )
                )

        # Conversion of existing inventory.
        conv_qty = conversion_size(self.config.conversion_spec, pos)

        # Decide direction from arb edge.
        local_bid = snap.best_bid.price if snap.best_bid else None
        local_ask = snap.best_ask.price if snap.best_ask else None
        edge = arb_edge(
            local_bid=local_bid, local_ask=local_ask,
            spec=self.config.conversion_spec, remote=remote,
        )

        if edge <= 0 and regime != "squeeze":
            return EngineStepResult(
                orders=[],
                conversions=conv_qty,
                tags=self._build_tags(),
            )

        # CRITICAL fix: under subsidy tariffs (import_tariff < 0) BOTH directions
        # can have positive break-even edges simultaneously. Emitting both SELL
        # and BUY orders on the same product in the same tick is contradictory.
        # Pick the ONE direction with the larger per-unit edge.
        orders: list[Order] = []
        sell_edge = 0.0
        buy_edge = 0.0
        sell_be = sell_local_break_even(self.config.conversion_spec, remote)
        buy_be = buy_local_break_even(self.config.conversion_spec, remote)
        if local_bid is not None and local_bid > sell_be:
            sell_edge = local_bid - sell_be
        if local_ask is not None and local_ask < buy_be:
            buy_edge = buy_be - local_ask

        chosen_direction: str | None = None
        if sell_edge > buy_edge and sell_edge > 0:
            chosen_direction = "sell"
        elif buy_edge > 0:
            chosen_direction = "buy"

        if chosen_direction == "sell" and snap.best_bid is not None and local_bid is not None:
            batch = target_batch_size(
                spec=self.config.conversion_spec,
                config=self.config.stockpile_config,
                arb_edge_per_unit=sell_edge,
                current_inventory=pos,
            )
            if batch > 0:
                size = min(batch, snap.best_bid.volume)
                if size > 0:
                    orders.append(Order(
                        self.config.local_product,
                        snap.best_bid.price,
                        -size,
                    ))
        elif chosen_direction == "buy" and snap.best_ask is not None and local_ask is not None:
            batch = target_batch_size(
                spec=self.config.conversion_spec,
                config=self.config.stockpile_config,
                arb_edge_per_unit=buy_edge,
                current_inventory=pos,
            )
            if batch > 0:
                size = min(batch, snap.best_ask.volume)
                if size > 0:
                    orders.append(Order(
                        self.config.local_product,
                        snap.best_ask.price,
                        size,
                    ))

        # Squeeze-regime overlay: accumulate long up to max_squeeze_inventory.
        # Only fires when no arb direction was chosen (prevents contradictory
        # SELL-then-BUY on the same tick when arb + squeeze disagree).
        if (
            chosen_direction != "sell"
            and regime == "squeeze"
            and pos < self.config.max_squeeze_inventory
            and snap.best_ask is not None
        ):
            # Additionally: if we already emitted a buy order, skip this overlay
            # to avoid doubling on the same side.
            already_buying = any(o.quantity > 0 for o in orders)
            if not already_buying:
                extra = min(
                    self.config.max_squeeze_inventory - pos,
                    snap.best_ask.volume,
                    self.config.conversion_spec.conv_cap_per_tick * 2,
                )
                if extra > 0:
                    orders.append(Order(
                        self.config.local_product,
                        snap.best_ask.price,
                        extra,
                    ))

        return EngineStepResult(
            orders=orders,
            conversions=conv_qty,
            tags=self._build_tags(),
        )

    # ====================================================== helpers

    def _read_external_signal(self) -> float | None:
        """Look up the raw external-signal value on the bus.

        Upstream emitters (e.g., a ConversionIntelEngine that unpacks
        TradingState.observations.conversionObservations[product]
        .sunlightIndex) publish under ``external_signal_name``. Raw
        observations are emitted with ``validated=False`` by convention
        (they aren't alpha signals), so we fetch with trusted_only=False.
        """
        name = self.config.external_signal_name
        if not name:
            return None
        sv = self.bus.get(name, trusted_only=False)
        if sv is None:
            return None
        try:
            return float(sv.value)
        except (TypeError, ValueError):
            return None

    def _build_tags(self) -> dict[str, ProductTag]:
        return {
            self.config.local_product: ProductTag(
                product=self.config.local_product,
                strategy_tag="arb",
                arb_group=f"statarb_{self.config.local_product}",
            )
        }
