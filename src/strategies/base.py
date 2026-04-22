from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.config import ProductConfig
from src.core.types import NormalizedSnapshot, ProductMemory, SignalIntent

if TYPE_CHECKING:  # avoid runtime import cycle
    from src.core.primitives.portfolio_context import PortfolioSnapshot
    from src.core.primitives.signal_bus import SignalBus


@dataclass(frozen=True)
class StrategyContext:
    """Per-product strategy input.

    Legacy fields: ``product``, ``snapshot``, ``memory``, ``config``.

    R3+ optional extensions:
    - ``portfolio``: read-only view of ALL products this tick, for
      strategies that need cross-product state (basket, options, etc.).
    - ``signal_bus``: per-tick signal registry, used by signal-aware
      strategies to consume validated signals emitted by engines upstream.

    Legacy single-product strategies ignore ``portfolio`` and
    ``signal_bus``; the trader populates them only when an
    ``EngineOrchestrator`` has produced them for the tick.
    """

    product: str
    snapshot: NormalizedSnapshot
    memory: ProductMemory
    config: ProductConfig
    portfolio: "PortfolioSnapshot | None" = None
    signal_bus: "SignalBus | None" = None


class BaseStrategy(ABC):
    @abstractmethod
    def generate_intent(self, context: StrategyContext) -> SignalIntent:
        raise NotImplementedError
