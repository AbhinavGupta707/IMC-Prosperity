"""Entrypoint for the Prosperity live trading container.

Responsibilities of this file are deliberately narrow:

1. Restore persistent state from ``state.traderData``.
2. Normalize the incoming ``TradingState`` into canonical snapshots.
3. Dispatch each known product to its configured strategy via the
   ``STRATEGY_REGISTRY`` in ``src/strategies/``.
4. Route the strategy's intent through execution and risk layers.
5. Update rolling per-product memory.
6. Serialize next-iteration state back into ``traderData``.
7. Return ``(orders, conversions, traderData)``.

This file never contains product-specific pricing or execution
heuristics. Those live in ``strategies/`` and ``core/``.

Safety: ``run()`` is wrapped in a top-level safety net. If any
downstream module raises, the trader returns an empty orders dict and
preserves the previous ``traderData`` so the Prosperity container does
not crash. Tests can set ``_reraise_exceptions=True`` to opt out and
surface errors.
"""

from __future__ import annotations

import logging

from src.core.config import EngineConfig, ProductConfig, default_engine_config
from src.core.execution import ExecutionEngine
from src.core.fair_value import FairValueEngine
from src.core.logger import DecisionLogger
from src.core.market_data import MarketDataAdapter
from src.core.residual import ResidualAllocator
from src.core.risk import RiskManager
from src.core.signals import SignalEngine
from src.core.state_store import StateStore
from src.core.types import EngineState, NormalizedSnapshot, ProductMemory
from src.core.utils import bounded_append
from src.datamodel import Order, TradingState
from src.signals.flow_analyzer import FlowAnalyzer
from src.strategies import STRATEGY_REGISTRY
from src.strategies.base import BaseStrategy, StrategyContext

_LOG = logging.getLogger(__name__)


class Trader:
    def __init__(
        self,
        config: EngineConfig | None = None,
        *,
        reraise_exceptions: bool = False,
    ) -> None:
        self.config = config or default_engine_config()
        self.state_store = StateStore(
            version=self.config.state_version,
            max_chars=self.config.max_trader_data_chars,
        )
        self.market_data = MarketDataAdapter()
        self.fair_value_engine = FairValueEngine()
        self.signal_engine = SignalEngine()
        self.execution_engine = ExecutionEngine()
        self.risk_manager = RiskManager()
        self.residual_allocator = ResidualAllocator(self.config.residual_config)
        self.flow_analyzer = FlowAnalyzer(self.config.scanner_config)
        self.logger = DecisionLogger()
        self._reraise_exceptions = reraise_exceptions
        self.strategies: dict[str, BaseStrategy] = self._build_strategies()

    # ---------------------------------------------------------- setup

    def _build_strategies(self) -> dict[str, BaseStrategy]:
        strategies: dict[str, BaseStrategy] = {}
        for product_config in self.config.products.values():
            name = product_config.strategy_name
            if name in strategies:
                continue
            factory = STRATEGY_REGISTRY.get(name)
            if factory is None:
                _LOG.warning("Unknown strategy %r for product config; will be skipped", name)
                continue
            strategies[name] = factory(self.fair_value_engine, self.signal_engine)
        return strategies

    # ---------------------------------------------------------- contract

    # Some Prosperity rounds require a ``bid()`` method on Trader.
    # Keep this stub so contract changes do not break submissions.
    def bid(self) -> int:
        return 15

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        """Entry point called by the Prosperity container.

        Wraps ``_run_body`` in a top-level safety net. An unhandled
        exception in any sub-module would otherwise crash the container
        and lose the iteration entirely.
        """
        try:
            return self._run_body(state)
        except Exception:
            _LOG.exception("Trader.run crashed; returning empty orders")
            if self._reraise_exceptions:
                raise
            return {}, 0, state.traderData

    # ---------------------------------------------------------- body

    def _run_body(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        engine_state = self.state_store.load(state.traderData)
        engine_state.version = self.config.state_version

        snapshots = self.market_data.normalize_state(state)
        results: dict[str, list[Order]] = {}

        for product, snapshot in snapshots.items():
            product_config = self.config.product_config(product)
            if product_config is None:
                results[product] = []
                continue

            strategy = self.strategies.get(product_config.strategy_name)
            if strategy is None:
                results[product] = []
                continue

            memory = engine_state.for_product(product)
            legal_orders = self._step_product(
                product=product,
                snapshot=snapshot,
                memory=memory,
                product_config=product_config,
                strategy=strategy,
                timestamp=state.timestamp,
            )
            results[product] = legal_orders
            self._update_memory(memory, snapshot, product_config.history_length)

        trader_data = self.state_store.save(engine_state)
        conversions = 0
        return results, conversions, trader_data

    # ---------------------------------------------------------- per-product

    def _step_product(
        self,
        *,
        product: str,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        product_config: ProductConfig,
        strategy: BaseStrategy,
        timestamp: int,
    ) -> list[Order]:
        # Observational flow scan — never alters strategy behaviour.
        flow_report = self.flow_analyzer.scan(snapshot, memory)

        context = StrategyContext(
            product=product,
            snapshot=snapshot,
            memory=memory,
            config=product_config,
        )
        intent = strategy.generate_intent(context)
        raw_orders = self.execution_engine.generate_orders(snapshot, intent, product_config)
        raw_orders = self.residual_allocator.augment_orders(
            product=product,
            orders=raw_orders,
            snapshot=snapshot,
            fair_value=intent.fair_value.price,
            position=snapshot.position,
            limit=product_config.position_limit,
            mode=intent.mode,
        )
        legal_orders = self.risk_manager.clip_orders(
            product=product,
            orders=raw_orders,
            current_position=snapshot.position,
            limit=product_config.position_limit,
        )

        event: dict[str, object] = {
            "timestamp": timestamp,
            "product": product,
            "fair_value": round(intent.fair_value.price, 4),
            "method": intent.fair_value.method,
            "position": snapshot.position,
            "mode": intent.mode,
            "orders": [(order.price, order.quantity) for order in legal_orders],
        }
        if flow_report is not None:
            verbosity = self.config.scanner_config.verbosity
            if verbosity >= 2:
                event["flow_report"] = {
                    "net_flow": flow_report.net_flow,
                    "flow_score": flow_report.flow_score,
                    "near_high": flow_report.near_high,
                    "near_low": flow_report.near_low,
                    "flags": list(flow_report.flags),
                    "repeated_sizes": dict(flow_report.repeated_sizes),
                }
            elif verbosity >= 1:
                event["scan_flags"] = list(flow_report.flags)
        self.logger.record(event)
        return legal_orders

    @staticmethod
    def _update_memory(
        memory: ProductMemory, snapshot: NormalizedSnapshot, history_length: int
    ) -> None:
        if history_length <= 0:
            return
        if snapshot.mid is not None:
            bounded_append(memory.recent_mids, float(snapshot.mid), history_length)
        if snapshot.spread is not None:
            bounded_append(memory.recent_spreads, float(snapshot.spread), history_length)

    # ---------------------------------------------------------- helpers

    def reset(self) -> None:
        """Drop any transient in-memory state (diagnostics only)."""
        self.logger = DecisionLogger()

    def engine_state_from(self, trader_data: str | None) -> EngineState:
        """Expose the state store to callers that need to inspect memory."""
        return self.state_store.load(trader_data)
