"""Shared engine types.

These types are the stable vocabulary spoken by every engine layer:
fair value, signals, execution, risk, and strategies.

Design notes:
- ``NormalizedSnapshot`` is frozen. Downstream code should not mutate it.
- ``ProductMemory`` is mutable because it is the authoritative rolling state
  we persist through ``traderData``; mutation is explicit and local.
- ``FairValueEstimate`` and ``SignalIntent`` are frozen so strategy code
  cannot accidentally mutate outputs of the fair value or signal stages.
  Their container fields (``components``, ``metadata``) are typed as
  ``Mapping`` and default to ``MappingProxyType({})`` so mutation is
  rejected at runtime as well as discouraged by the type system.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

Product = str
Timestamp = int
Scalar = int | float | str | bool
ExecutionMode = Literal["idle", "maker", "taker", "recovery", "hybrid"]


def _empty_scalar_map() -> Mapping[str, Scalar]:
    return MappingProxyType({})


@dataclass(frozen=True)
class BookLevel:
    price: int
    volume: int


@dataclass(frozen=True)
class TradePrint:
    price: int
    quantity: int
    buyer: str | None = None
    seller: str | None = None
    timestamp: int = 0
    source: Literal["own", "market"] = "market"


@dataclass(frozen=True)
class NormalizedSnapshot:
    product: Product
    timestamp: Timestamp
    bids: tuple[BookLevel, ...] = ()
    asks: tuple[BookLevel, ...] = ()
    position: int = 0
    trades: tuple[TradePrint, ...] = ()

    @property
    def best_bid(self) -> BookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> BookLevel | None:
        return self.asks[0] if self.asks else None

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid.price + self.best_ask.price) / 2.0

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return float(self.best_ask.price - self.best_bid.price)

    @property
    def book_imbalance(self) -> float | None:
        """Top-of-book imbalance in [-1, 1], positive = bid-heavy."""
        if self.best_bid is None or self.best_ask is None:
            return None
        total = self.best_bid.volume + self.best_ask.volume
        if total <= 0:
            return None
        return (self.best_bid.volume - self.best_ask.volume) / total

    @property
    def microprice(self) -> float | None:
        """Volume-weighted best price, i.e. mid tilted toward the thicker side."""
        if self.best_bid is None or self.best_ask is None:
            return None
        total = self.best_bid.volume + self.best_ask.volume
        if total <= 0:
            return None
        return (
            (self.best_bid.price * self.best_ask.volume)
            + (self.best_ask.price * self.best_bid.volume)
        ) / total

    def total_bid_volume(self, depth: int | None = None) -> int:
        levels = self.bids if depth is None else self.bids[:depth]
        return sum(level.volume for level in levels)

    def total_ask_volume(self, depth: int | None = None) -> int:
        levels = self.asks if depth is None else self.asks[:depth]
        return sum(level.volume for level in levels)

    def top_bids(self, depth: int) -> tuple[BookLevel, ...]:
        if depth <= 0:
            return ()
        return self.bids[:depth]

    def top_asks(self, depth: int) -> tuple[BookLevel, ...]:
        if depth <= 0:
            return ()
        return self.asks[:depth]


@dataclass
class ProductMemory:
    recent_mids: list[float] = field(default_factory=list)
    recent_spreads: list[float] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    flags: dict[str, bool] = field(default_factory=dict)
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class EngineState:
    version: int = 1
    products: dict[Product, ProductMemory] = field(default_factory=dict)

    def for_product(self, product: Product) -> ProductMemory:
        memory = self.products.get(product)
        if memory is None:
            memory = ProductMemory()
            self.products[product] = memory
        return memory


@dataclass(frozen=True)
class FairValueEstimate:
    price: float
    method: str
    confidence: float | None = None
    components: Mapping[str, Scalar] = field(default_factory=_empty_scalar_map)


@dataclass(frozen=True)
class QuoteIntent:
    bid_price: int | None = None
    bid_size: int = 0
    ask_price: int | None = None
    ask_size: int = 0


@dataclass(frozen=True)
class SignalIntent:
    product: Product
    fair_value: FairValueEstimate
    mode: ExecutionMode = "idle"
    buy_below: float | None = None
    sell_above: float | None = None
    quote: QuoteIntent | None = None
    rationale: str = ""
    metadata: Mapping[str, Scalar] = field(default_factory=_empty_scalar_map)


# ---------------------------------------------------------------- scanner


@dataclass(frozen=True)
class ScannerConfig:
    """Controls whether and how verbosely the flow scanner runs.

    Verbosity levels:
    - 0 (default): silent — scanner runs and persists state but adds
      nothing to the decision logger. Suitable for live submission.
    - 1: flags-only — appends ``scan_flags`` to the logger event.
    - 2: full report — appends the complete ``FlowReport`` dict to the
      logger event. Intended for offline review scripts only.
    """

    enabled: bool = True
    extrema_window: int = 20
    extrema_tolerance: float = 1.0
    flow_decay: float = 0.8
    repeated_size_threshold: int = 3
    verbosity: int = 0


@dataclass(frozen=True)
class ResidualConfig:
    """Controls the optional residual capacity utilizer.

    Ships disabled (framework-only). Enable only after the enablement
    gate is passed: compare baseline vs baseline+residual on PnL, trade
    count, maker/taker mix, markouts, and time-near-limits. Record
    results in a review note before flipping the flag.
    """

    enabled: bool = False
    residual_edge: float = 2.0
    residual_size: int = 2


@dataclass(frozen=True)
class FlowReport:
    """Observational summary of trade-flow patterns for a single step.

    All fields are ephemeral — only ``flow_score`` (via
    ``ProductMemory.values``) and ``step_count`` (via
    ``ProductMemory.counters``) are persisted across calls.

    ``net_flow`` is a heuristic proxy for directional pressure, not
    true aggressor-side inference. The sign convention is: buyer-only
    trade -> +qty, seller-only -> -qty, both or neither -> 0.
    """

    product: Product
    timestamp: Timestamp
    repeated_sizes: Mapping[int, int]
    net_flow: int
    flow_score: float
    near_high: bool
    near_low: bool
    flags: tuple[str, ...]
    metadata: Mapping[str, Scalar] = field(default_factory=_empty_scalar_map)
