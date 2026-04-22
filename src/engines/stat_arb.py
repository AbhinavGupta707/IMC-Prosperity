"""StatArbEngine (E3) — cross-exchange arb with conversion layer.

Composition of Stage A-D primitives:
- ConversionLayer (D): signed break-even, batched stockpile, regime flags
- PortfolioContext (B): read local + remote state
- PortfolioRiskManager (B): conversion tracking
- SignalBus (C): emit / consume the external-signal regime flag

Engine is small — the heavy math is in conversions.layer. Responsibilities:
- Fetch the local book + remote quote + external signal from PortfolioContext
- Detect arb edge via signed break-even
- Decide batch size via stockpile optimizer (3× conv_cap_per_tick)
- Switch to accumulation mode on `squeeze` regime, offload on `glut`
- Return (orders, conversions, tags)

Note: Prosperity separates orders from conversions. This engine returns
both — caller integrates them into the trader's output.
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

    # Which external-signal stream to consume from the bus.
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

    def step(
        self,
        portfolio: PortfolioSnapshot,
        *,
        remote: RemoteQuote,
        external_signal_value: float | None = None,
    ) -> tuple[list[Order], int, dict[str, ProductTag]]:
        """Emit orders + conversion amount + tags.

        Returns (orders, conversion_qty, tags):
        - orders: local-book orders
        - conversion_qty: signed conversion this tick (positive=import)
        - tags: {product: ProductTag} for cross-product risk
        """
        snap = portfolio.for_product(self.config.local_product)
        if snap is None:
            return [], 0, {}

        pos = portfolio.position_of(self.config.local_product)

        # Update regime detector if we have an external signal.
        regime: str = "normal"
        if external_signal_value is not None:
            self._regime.observe(external_signal_value)
            regime = self._regime.regime(external_signal_value)
            # Publish for downstream consumers.
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
            return [], conv_qty, self._build_tags()

        orders: list[Order] = []
        # Sell-local direction: local_bid > sell_be ⇒ sell locally at bid.
        if local_bid is not None:
            sell_be = sell_local_break_even(self.config.conversion_spec, remote)
            if local_bid > sell_be:
                batch = target_batch_size(
                    spec=self.config.conversion_spec,
                    config=self.config.stockpile_config,
                    arb_edge_per_unit=local_bid - sell_be,
                    current_inventory=pos,
                )
                if batch > 0 and snap.best_bid is not None:
                    size = min(batch, snap.best_bid.volume)
                    if size > 0:
                        orders.append(Order(
                            self.config.local_product,
                            snap.best_bid.price,
                            -size,
                        ))

        # Buy-local direction.
        if local_ask is not None:
            buy_be = buy_local_break_even(self.config.conversion_spec, remote)
            if local_ask < buy_be:
                batch = target_batch_size(
                    spec=self.config.conversion_spec,
                    config=self.config.stockpile_config,
                    arb_edge_per_unit=buy_be - local_ask,
                    current_inventory=pos,
                )
                if batch > 0 and snap.best_ask is not None:
                    size = min(batch, snap.best_ask.volume)
                    if size > 0:
                        orders.append(Order(
                            self.config.local_product,
                            snap.best_ask.price,
                            size,
                        ))

        # Squeeze-regime overlay: accumulate long up to max_squeeze_inventory.
        if regime == "squeeze" and pos < self.config.max_squeeze_inventory:
            if snap.best_ask is not None:
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

        return orders, conv_qty, self._build_tags()

    def _build_tags(self) -> dict[str, ProductTag]:
        return {
            self.config.local_product: ProductTag(
                product=self.config.local_product,
                strategy_tag="arb",
                arb_group=f"statarb_{self.config.local_product}",
            )
        }
