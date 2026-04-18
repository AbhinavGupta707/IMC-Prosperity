from __future__ import annotations
from datamodel import Order, OrderDepth, Trade, TradingState
from collections.abc import Sequence
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal
import json
from typing import Protocol
import warnings
from dataclasses import asdict
from typing import Any
from collections import Counter
import math
from dataclasses import dataclass
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
import logging

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))

def bounded_append(values: list[float], value: float, maxlen: int) -> None:
    values.append(value)
    if len(values) > maxlen:
        del values[:len(values) - maxlen]

def weighted_average(values: Sequence[float], weights: Sequence[float]) -> float:
    if len(values) != len(weights):
        raise ValueError('values and weights must have the same length')
    total_weight = float(sum(weights))
    if total_weight == 0:
        raise ValueError('weights must not sum to zero')
    return sum((value * weight for value, weight in zip(values, weights, strict=True))) / total_weight
Product = str
Timestamp = int
Scalar = int | float | str | bool
ExecutionMode = Literal['idle', 'maker', 'taker', 'recovery', 'hybrid']

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
    source: Literal['own', 'market'] = 'market'

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
        if self.best_bid is None or self.best_ask is None:
            return None
        total = self.best_bid.volume + self.best_ask.volume
        if total <= 0:
            return None
        return (self.best_bid.volume - self.best_ask.volume) / total

    @property
    def microprice(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        total = self.best_bid.volume + self.best_ask.volume
        if total <= 0:
            return None
        return (self.best_bid.price * self.best_ask.volume + self.best_ask.price * self.best_bid.volume) / total

    def total_bid_volume(self, depth: int | None=None) -> int:
        levels = self.bids if depth is None else self.bids[:depth]
        return sum((level.volume for level in levels))

    def total_ask_volume(self, depth: int | None=None) -> int:
        levels = self.asks if depth is None else self.asks[:depth]
        return sum((level.volume for level in levels))

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
    mode: ExecutionMode = 'idle'
    buy_below: float | None = None
    sell_above: float | None = None
    quote: QuoteIntent | None = None
    rationale: str = ''
    metadata: Mapping[str, Scalar] = field(default_factory=_empty_scalar_map)

@dataclass(frozen=True)
class ScannerConfig:
    enabled: bool = True
    extrema_window: int = 20
    extrema_tolerance: float = 1.0
    flow_decay: float = 0.8
    repeated_size_threshold: int = 3
    verbosity: int = 0

@dataclass(frozen=True)
class ResidualConfig:
    enabled: bool = False
    residual_edge: float = 2.0
    residual_size: int = 2

@dataclass(frozen=True)
class FlowReport:
    product: Product
    timestamp: Timestamp
    repeated_sizes: Mapping[int, int]
    net_flow: int
    flow_score: float
    near_high: bool
    near_low: bool
    flags: tuple[str, ...]
    metadata: Mapping[str, Scalar] = field(default_factory=_empty_scalar_map)
KNOWN_STRATEGY_NAMES: tuple[str, ...] = ('buy_and_hold', 'market_making')
KNOWN_ESTIMATOR_NAMES: tuple[str, ...] = ('anchor', 'depth_mid', 'ewma_mid', 'filtered_wall_mid', 'hybrid_wall_micro', 'linear_drift', 'microprice', 'mid', 'rolling_mid', 'wall_mid', 'weighted_mid')

def _format_known_names(names: tuple[str, ...]) -> str:
    return ', '.join(names) if names else '<none>'

@dataclass(frozen=True)
class ProductConfig:
    position_limit: int
    strategy_name: str
    fair_value_method: str
    fair_value_fallbacks: tuple[str, ...] = ()
    tick_size: int = 1
    anchor_price: float | None = None
    taker_edge: float = 1.0
    maker_edge: float = 1.0
    quote_size: int = 5
    max_aggressive_size: int = 10
    inventory_skew: float = 2.0
    flatten_threshold: float = 0.8
    history_length: int = 32
    ewma_alpha: float | None = None
    taker_edge_buy: float | None = None
    taker_edge_sell: float | None = None
    early_window: int = 0
    early_taker_edge_buy: float | None = None
    early_taker_edge_sell: float | None = None
    early_short_cap: int | None = None
    early_short_skew_mult: float = 1.0
    early_short_flatten: float | None = None

    def __post_init__(self) -> None:
        pass

@dataclass(frozen=True)
class EngineConfig:
    state_version: int = 1
    max_trader_data_chars: int = 50000
    diagnostics_verbosity: int = 1
    products: dict[str, ProductConfig] = field(default_factory=dict)
    scanner_config: ScannerConfig = field(default_factory=ScannerConfig)
    residual_config: ResidualConfig = field(default_factory=ResidualConfig)

    def __post_init__(self) -> None:
        pass

    def product_config(self, product: str) -> ProductConfig | None:
        return self.products.get(product)

def default_engine_config() -> EngineConfig:
    return EngineConfig(products={'EMERALDS': ProductConfig(position_limit=80, strategy_name='market_making', fair_value_method='anchor', fair_value_fallbacks=('microprice', 'mid'), anchor_price=10000.0, taker_edge=1.0, maker_edge=2.0, quote_size=5, max_aggressive_size=10, inventory_skew=8.0, flatten_threshold=0.75, history_length=32), 'TOMATOES': ProductConfig(position_limit=80, strategy_name='market_making', fair_value_method='wall_mid', fair_value_fallbacks=('mid', 'microprice'), taker_edge=1.0, maker_edge=1.0, quote_size=4, max_aggressive_size=8, inventory_skew=12.0, flatten_threshold=0.7, history_length=48), 'ASH_COATED_OSMIUM': ProductConfig(position_limit=80, strategy_name='market_making', fair_value_method='wall_mid', fair_value_fallbacks=('mid', 'microprice'), anchor_price=10000.0, taker_edge=1.0, maker_edge=1.0, quote_size=5, max_aggressive_size=10, inventory_skew=4.0, flatten_threshold=0.7, history_length=48), 'INTARIAN_PEPPER_ROOT': ProductConfig(position_limit=80, strategy_name='market_making', fair_value_method='linear_drift', fair_value_fallbacks=('depth_mid', 'hybrid_wall_micro', 'mid'), taker_edge=1.0, maker_edge=1.5, quote_size=4, max_aggressive_size=8, inventory_skew=2.0, flatten_threshold=0.8, history_length=48)})
ROUND1_PRODUCTS: tuple[str, ...] = ('ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT')

def round1_engine_config() -> EngineConfig:
    base = default_engine_config()
    products = {name: config for name in ROUND1_PRODUCTS if (config := base.product_config(name)) is not None}
    return EngineConfig(state_version=base.state_version, max_trader_data_chars=base.max_trader_data_chars, diagnostics_verbosity=base.diagnostics_verbosity, products=products, scanner_config=base.scanner_config, residual_config=base.residual_config)

def _round1_engine_with(**per_product_overrides: dict[str, object]) -> EngineConfig:
    from dataclasses import replace
    base = round1_engine_config()
    products = dict(base.products)
    for product, overrides in per_product_overrides.items():
        current = base.product_config(product)
        if current is None:
            continue
        products[product] = replace(current, **overrides)
    return EngineConfig(state_version=base.state_version, max_trader_data_chars=base.max_trader_data_chars, diagnostics_verbosity=base.diagnostics_verbosity, products=products, scanner_config=base.scanner_config, residual_config=base.residual_config)

def round1_baseline_engine_config() -> EngineConfig:
    return round1_engine_config()

def round1_promoted_engine_config() -> EngineConfig:
    return _round1_engine_with(ASH_COATED_OSMIUM=dict(fair_value_method='ewma_mid', fair_value_fallbacks=('mid', 'microprice'), maker_edge=1.0, taker_edge=0.25, inventory_skew=4.0, flatten_threshold=0.7, history_length=48), INTARIAN_PEPPER_ROOT=dict(fair_value_method='linear_drift', fair_value_fallbacks=('depth_mid', 'hybrid_wall_micro', 'mid'), maker_edge=1.0, taker_edge=2.0, inventory_skew=2.0, flatten_threshold=0.7, history_length=32))

def round1_h1_engine_config() -> EngineConfig:
    return _round1_engine_with(ASH_COATED_OSMIUM=dict(fair_value_method='wall_mid', fair_value_fallbacks=('mid', 'microprice'), maker_edge=1.5, taker_edge=0.5, inventory_skew=4.0, flatten_threshold=0.7, history_length=48), INTARIAN_PEPPER_ROOT=dict(fair_value_method='linear_drift', fair_value_fallbacks=('depth_mid', 'hybrid_wall_micro', 'mid'), maker_edge=1.0, taker_edge=2.0, inventory_skew=2.0, flatten_threshold=0.7, history_length=32))

def round1_f5_engine_config() -> EngineConfig:
    return _round1_engine_with(ASH_COATED_OSMIUM=dict(fair_value_method='wall_mid', fair_value_fallbacks=('mid', 'microprice'), maker_edge=1.5, taker_edge=0.5, inventory_skew=4.0, flatten_threshold=0.7, history_length=48), INTARIAN_PEPPER_ROOT=dict(fair_value_method='linear_drift', fair_value_fallbacks=('depth_mid', 'hybrid_wall_micro', 'mid'), maker_edge=1.0, taker_edge=2.0, taker_edge_buy=1.5, taker_edge_sell=3.0, inventory_skew=2.0, flatten_threshold=0.7, history_length=32))

def round1_test_engine_config() -> EngineConfig:
    return _round1_engine_with(ASH_COATED_OSMIUM=dict(fair_value_method='wall_mid', fair_value_fallbacks=('mid', 'microprice'), maker_edge=1.5, taker_edge=0.5, inventory_skew=4.0, flatten_threshold=0.7, history_length=48), INTARIAN_PEPPER_ROOT=dict(strategy_name='buy_and_hold', fair_value_method='mid', fair_value_fallbacks=(), max_aggressive_size=80))

def round1_v2_clean_engine_config() -> EngineConfig:
    return round1_test_engine_config()

def _round1_ladder_base() -> EngineConfig:
    return _round1_engine_with(ASH_COATED_OSMIUM=dict(strategy_name='ash_ladder', fair_value_method='weighted_mid', fair_value_fallbacks=('wall_mid', 'mid'), maker_edge=2.5, taker_edge=0.5, flatten_threshold=0.7), INTARIAN_PEPPER_ROOT=dict(strategy_name='buy_and_hold', fair_value_method='mid', fair_value_fallbacks=(), max_aggressive_size=80))

def _round1_pepper_candidate_base(pepper_strategy_name: str, *, max_aggressive_size: int=20, quote_size: int=5) -> EngineConfig:
    return _round1_engine_with(ASH_COATED_OSMIUM=dict(strategy_name='ash_ladder', fair_value_method='weighted_mid', fair_value_fallbacks=('wall_mid', 'mid'), maker_edge=2.5, taker_edge=0.5, flatten_threshold=0.7), INTARIAN_PEPPER_ROOT=dict(strategy_name=pepper_strategy_name, fair_value_method='linear_drift', fair_value_fallbacks=('depth_mid', 'hybrid_wall_micro', 'mid'), max_aggressive_size=max_aggressive_size, quote_size=quote_size, history_length=32))

def round1_pepper_passive_maker_engine_config() -> EngineConfig:
    return _round1_pepper_candidate_base('pepper_passive_maker')

def round1_pepper_drift_asymmetric_engine_config() -> EngineConfig:
    return _round1_pepper_candidate_base('pepper_drift_asymmetric')

def round1_pepper_imbalance_timer_engine_config() -> EngineConfig:
    return _round1_pepper_candidate_base('pepper_imbalance_timer')

def round1_pepper_flow_overlay_engine_config() -> EngineConfig:
    return _round1_pepper_candidate_base('pepper_flow_overlay')

def round1_pepper_passive_opener_engine_config() -> EngineConfig:
    return _round1_pepper_candidate_base('pepper_passive_opener')

def round1_ash_deep_k1_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_ash_deep_k2_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_ash_deep_k3_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_ash_deep_k5_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_ash_deep_l1_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_ash_deep_l2_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_ash_deep_l4_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_ash_deep_l5_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_ash_deep_l5b_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_ash_deep_l6_engine_config() -> EngineConfig:
    return _round1_ladder_base()

def round1_combined_v5micro_l1_engine_config() -> EngineConfig:
    return _round1_engine_with(ASH_COATED_OSMIUM=dict(strategy_name='ash_ladder', fair_value_method='weighted_mid', fair_value_fallbacks=('wall_mid', 'mid'), maker_edge=2.5, taker_edge=0.5, flatten_threshold=0.7), INTARIAN_PEPPER_ROOT=dict(strategy_name='pepper_core_long', fair_value_method='linear_drift', fair_value_fallbacks=('depth_mid', 'hybrid_wall_micro', 'mid'), taker_edge=2.0, maker_edge=1.0, quote_size=10, max_aggressive_size=20, inventory_skew=2.0, flatten_threshold=0.7, history_length=32))

def round1_combined_v6_engine_config() -> EngineConfig:
    return _round1_engine_with(ASH_COATED_OSMIUM=dict(strategy_name='ash_ladder', fair_value_method='weighted_mid', fair_value_fallbacks=('wall_mid', 'mid'), maker_edge=2.5, taker_edge=0.5, flatten_threshold=0.7), INTARIAN_PEPPER_ROOT=dict(strategy_name='pepper_v6_combined', fair_value_method='linear_drift', fair_value_fallbacks=('depth_mid', 'hybrid_wall_micro', 'mid'), taker_edge=2.0, maker_edge=1.0, quote_size=10, max_aggressive_size=20, inventory_skew=2.0, flatten_threshold=0.7, history_length=32))

def round1_alt_engine_config() -> EngineConfig:
    return _round1_engine_with(ASH_COATED_OSMIUM=dict(fair_value_method='wall_mid', fair_value_fallbacks=('mid', 'microprice'), maker_edge=1.5, taker_edge=0.5, inventory_skew=4.0, flatten_threshold=0.7, history_length=48), INTARIAN_PEPPER_ROOT=dict(fair_value_method='linear_drift', fair_value_fallbacks=('depth_mid', 'hybrid_wall_micro', 'mid'), maker_edge=1.0, taker_edge=2.0, inventory_skew=1.0, flatten_threshold=0.9, history_length=32))

class DecisionLogger:

    def __init__(self, max_events: int=256) -> None:
        self.max_events = max_events
        self.events: list[dict[str, object]] = []

    def record(self, event: dict[str, object]) -> None:
        self.events.append(event)
        if len(self.events) > self.max_events:
            del self.events[:len(self.events) - self.max_events]

    def to_json(self, max_chars: int=4000) -> str:
        payload = json.dumps(self.events, separators=(',', ':'), sort_keys=True)
        if len(payload) <= max_chars:
            return payload
        return payload[:max_chars - 3] + '...'

class MarketDataAdapter:

    def normalize_state(self, state: TradingState) -> dict[str, NormalizedSnapshot]:
        snapshots: dict[str, NormalizedSnapshot] = {}
        for product, order_depth in state.order_depths.items():
            bids, asks = self._normalize_depth(order_depth)
            trades = self._normalize_trades(state.own_trades.get(product, []) if state.own_trades else [], state.market_trades.get(product, []) if state.market_trades else [])
            snapshots[product] = NormalizedSnapshot(product=product, timestamp=state.timestamp, bids=bids, asks=asks, position=state.position.get(product, 0) if state.position else 0, trades=trades)
        return snapshots

    @staticmethod
    def _normalize_depth(order_depth: OrderDepth) -> tuple[tuple[BookLevel, ...], tuple[BookLevel, ...]]:
        buys = getattr(order_depth, 'buy_orders', {}) or {}
        sells = getattr(order_depth, 'sell_orders', {}) or {}
        bids = tuple((BookLevel(price=int(price), volume=int(volume)) for price, volume in sorted(buys.items(), key=lambda item: item[0], reverse=True) if int(volume) > 0))
        asks = tuple((BookLevel(price=int(price), volume=abs(int(volume))) for price, volume in sorted(sells.items(), key=lambda item: item[0]) if int(volume) != 0))
        return (bids, asks)

    @staticmethod
    def _normalize_trades(own_trades: list[Trade], market_trades: list[Trade]) -> tuple[TradePrint, ...]:
        combined: list[TradePrint] = []
        combined.extend((TradePrint(price=int(trade.price), quantity=int(trade.quantity), buyer=trade.buyer, seller=trade.seller, timestamp=int(trade.timestamp), source='own') for trade in own_trades or []))
        combined.extend((TradePrint(price=int(trade.price), quantity=int(trade.quantity), buyer=trade.buyer, seller=trade.seller, timestamp=int(trade.timestamp), source='market') for trade in market_trades or []))
        combined.sort(key=lambda trade: trade.timestamp)
        return tuple(combined)
_DEFAULT_EWMA_ALPHA = 0.3

class Estimator(Protocol):
    name: str

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        ...

class AnchorEstimator:
    name = 'anchor'

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        if config.anchor_price is None:
            return None
        return FairValueEstimate(price=float(config.anchor_price), method=self.name, confidence=1.0, components=MappingProxyType({'anchor_price': float(config.anchor_price)}))

class MidEstimator:
    name = 'mid'

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        if snapshot.mid is None:
            return None
        return FairValueEstimate(price=float(snapshot.mid), method=self.name, confidence=0.7)

class MicropriceEstimator:
    name = 'microprice'

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        if snapshot.microprice is None:
            return None
        components: Mapping[str, Scalar] = MappingProxyType({'imbalance': float(snapshot.book_imbalance or 0.0)})
        return FairValueEstimate(price=float(snapshot.microprice), method=self.name, confidence=0.8, components=components)

class RollingMidEstimator:
    name = 'rolling_mid'

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        history = list(memory.recent_mids)
        if snapshot.mid is not None:
            history.append(float(snapshot.mid))
        if not history:
            return None
        return FairValueEstimate(price=sum(history) / len(history), method=self.name, confidence=0.65)

class WeightedMidEstimator:
    name = 'weighted_mid'

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        lookback = config.history_length if config.history_length > 0 else 0
        history = memory.recent_mids[-lookback:] if lookback > 0 else []
        if snapshot.mid is None:
            if not history:
                return None
            weights = list(range(1, len(history) + 1))
            return FairValueEstimate(price=weighted_average(history, weights), method=self.name, confidence=0.55)
        values = [*history, float(snapshot.mid)]
        weights = list(range(1, len(values) + 1))
        return FairValueEstimate(price=weighted_average(values, weights), method=self.name, confidence=0.7)

class EwmaMidEstimator:
    name = 'ewma_mid'

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        alpha = config.ewma_alpha if config.ewma_alpha is not None else _DEFAULT_EWMA_ALPHA
        history = memory.recent_mids
        current = snapshot.mid
        if not history and current is None:
            return None
        bootstrap = False
        if not history:
            ewma = float(current)
            bootstrap = True
        else:
            ewma = float(history[0])
            for prior_mid in history[1:]:
                ewma = alpha * float(prior_mid) + (1.0 - alpha) * ewma
            if current is None:
                bootstrap = len(history) == 1
            else:
                ewma = alpha * float(current) + (1.0 - alpha) * ewma
        components: dict[str, Scalar] = {'alpha': float(alpha)}
        if bootstrap:
            components['bootstrap'] = 1.0
        return FairValueEstimate(price=ewma, method=self.name, confidence=0.72, components=MappingProxyType(components))

class LinearDriftEstimator:
    name = 'linear_drift'

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        lookback = config.history_length if config.history_length > 0 else None
        history = list(memory.recent_mids)
        if lookback is not None:
            history = history[-lookback:]
        current = snapshot.mid
        if not history and current is None:
            return None
        if not history:
            return FairValueEstimate(price=float(current), method=self.name, confidence=0.3, components=MappingProxyType({'bootstrap': 1.0}))
        ys: list[float] = [float(y) for y in history]
        if current is not None:
            ys.append(float(current))
        n = len(ys)
        if n < 2:
            return FairValueEstimate(price=ys[-1], method=self.name, confidence=0.4, components=MappingProxyType({'bootstrap': 1.0, 'samples': float(n)}))
        xs = list(range(n))
        mean_x = (n - 1) / 2.0
        mean_y = sum(ys) / n
        var_x = sum(((x - mean_x) ** 2 for x in xs))
        if var_x <= 0:
            return FairValueEstimate(price=ys[-1], method=self.name, confidence=0.4, components=MappingProxyType({'samples': float(n)}))
        cov_xy = sum(((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)))
        slope = cov_xy / var_x
        intercept = mean_y - slope * mean_x
        forecast = slope * n + intercept
        components: dict[str, Scalar] = {'slope': float(slope), 'intercept': float(intercept), 'samples': float(n)}
        return FairValueEstimate(price=forecast, method=self.name, confidence=0.7, components=MappingProxyType(components))

class DepthMidEstimator:
    name = 'depth_mid'

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        del memory, config
        if not snapshot.bids or not snapshot.asks:
            return None
        bid_volume = sum((level.volume for level in snapshot.bids))
        ask_volume = sum((level.volume for level in snapshot.asks))
        if bid_volume <= 0 or ask_volume <= 0:
            return None
        bid_vwap = sum((level.price * level.volume for level in snapshot.bids)) / bid_volume
        ask_vwap = sum((level.price * level.volume for level in snapshot.asks)) / ask_volume
        return FairValueEstimate(price=(bid_vwap + ask_vwap) / 2.0, method=self.name, confidence=0.75, components=MappingProxyType({'bid_vwap': bid_vwap, 'ask_vwap': ask_vwap}))

class WallMidEstimator:
    name = 'wall_mid'

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        del memory, config
        if not snapshot.bids or not snapshot.asks:
            return None
        wall_bid = max(snapshot.bids, key=lambda l: l.volume)
        wall_ask = max(snapshot.asks, key=lambda l: l.volume)
        return FairValueEstimate(price=(wall_bid.price + wall_ask.price) / 2.0, method=self.name, confidence=0.75, components=MappingProxyType({'wall_bid_price': wall_bid.price, 'wall_ask_price': wall_ask.price, 'wall_bid_vol': wall_bid.volume, 'wall_ask_vol': wall_ask.volume}))

class FilteredWallMidEstimator:
    name = 'filtered_wall_mid'
    _TOP_N = 3
    _MIN_VOLUME_RATIO = 0.25

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        del memory, config
        if not snapshot.bids or not snapshot.asks:
            return None
        top_bids = snapshot.bids[:self._TOP_N]
        top_asks = snapshot.asks[:self._TOP_N]
        wall_bid, bid_filtered = self._pick_wall(top_bids)
        wall_ask, ask_filtered = self._pick_wall(top_asks)
        if wall_bid is None or wall_ask is None:
            return None
        return FairValueEstimate(price=(wall_bid.price + wall_ask.price) / 2.0, method=self.name, confidence=0.75, components=MappingProxyType({'wall_bid_price': wall_bid.price, 'wall_ask_price': wall_ask.price, 'filtered_out_count': bid_filtered + ask_filtered}))

    @staticmethod
    def _pick_wall(levels: tuple[BookLevel, ...]) -> tuple[BookLevel | None, int]:
        if not levels:
            return (None, 0)
        max_vol = max((l.volume for l in levels))
        threshold = max_vol * FilteredWallMidEstimator._MIN_VOLUME_RATIO
        indexed = [(i, l) for i, l in enumerate(levels) if l.volume >= threshold]
        filtered_count = len(levels) - len(indexed)
        if not indexed:
            return (None, filtered_count)
        indexed.sort(key=lambda x: (-x[1].volume, x[0]))
        return (indexed[0][1], filtered_count)

class HybridWallMicroEstimator:
    name = 'hybrid_wall_micro'
    wall_weight: float = 0.5

    def __init__(self) -> None:
        self._wall = WallMidEstimator()
        self._micro = MicropriceEstimator()

    def estimate(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate | None:
        wall_est = self._wall.estimate(snapshot, memory, config)
        micro_est = self._micro.estimate(snapshot, memory, config)
        if wall_est is not None and micro_est is not None:
            price = self.wall_weight * wall_est.price + (1 - self.wall_weight) * micro_est.price
            return FairValueEstimate(price=price, method=self.name, confidence=0.75, components=MappingProxyType({'wall_mid_price': wall_est.price, 'microprice': micro_est.price, 'wall_weight': self.wall_weight}))
        if wall_est is not None:
            return FairValueEstimate(price=wall_est.price, method=self.name, confidence=0.75, components=MappingProxyType({'wall_mid_price': wall_est.price, 'wall_weight': 1.0}))
        if micro_est is not None:
            return FairValueEstimate(price=micro_est.price, method=self.name, confidence=0.75, components=MappingProxyType({'microprice': micro_est.price, 'wall_weight': 0.0}))
        return None
ESTIMATORS: Mapping[str, Estimator] = MappingProxyType({'anchor': AnchorEstimator(), 'mid': MidEstimator(), 'microprice': MicropriceEstimator(), 'rolling_mid': RollingMidEstimator(), 'weighted_mid': WeightedMidEstimator(), 'ewma_mid': EwmaMidEstimator(), 'linear_drift': LinearDriftEstimator(), 'depth_mid': DepthMidEstimator(), 'wall_mid': WallMidEstimator(), 'filtered_wall_mid': FilteredWallMidEstimator(), 'hybrid_wall_micro': HybridWallMicroEstimator()})

class FairValueEngine:

    def __init__(self, estimators: Mapping[str, Estimator] | None=None) -> None:
        self._estimators: dict[str, Estimator] = dict(estimators or ESTIMATORS)

    def register(self, estimator: Estimator) -> None:
        self._estimators[estimator.name] = estimator

    def known_estimators(self) -> tuple[str, ...]:
        return tuple(sorted(self._estimators))

    def estimate(self, product: str, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> FairValueEstimate:
        del product
        chain: list[str] = [config.fair_value_method, *config.fair_value_fallbacks]
        for name in chain:
            estimator = self._estimators.get(name)
            if estimator is None:
                continue
            result = estimator.estimate(snapshot, memory, config)
            if result is not None:
                return result
        if config.anchor_price is not None:
            return FairValueEstimate(price=float(config.anchor_price), method='anchor_fallback', confidence=0.1)
        return FairValueEstimate(price=0.0, method='zero_fallback', confidence=0.0)

    def estimate_all(self, snapshot: NormalizedSnapshot, memory: ProductMemory, config: ProductConfig) -> dict[str, FairValueEstimate]:
        results: dict[str, FairValueEstimate] = {}
        for name, estimator in self._estimators.items():
            result = estimator.estimate(snapshot, memory, config)
            if result is not None:
                results[name] = result
        return results
_MAX_PERSISTED_HISTORY = 64
_TRUNCATED_HISTORY_KEEP = 8

class StateStore:

    def __init__(self, version: int=1, max_chars: int=50000, max_history: int=_MAX_PERSISTED_HISTORY, truncated_history_keep: int=_TRUNCATED_HISTORY_KEEP) -> None:
        if version < 1:
            raise ValueError('version must be >= 1')
        if max_chars <= 0:
            raise ValueError('max_chars must be > 0')
        if max_history < 0 or truncated_history_keep < 0:
            raise ValueError('history bounds must be >= 0')
        if truncated_history_keep > max_history:
            raise ValueError('truncated_history_keep must be <= max_history')
        self.version = version
        self.max_chars = max_chars
        self.max_history = max_history
        self.truncated_history_keep = truncated_history_keep

    def load(self, trader_data: str | None) -> EngineState:
        if not trader_data:
            return EngineState(version=self.version)
        try:
            raw = json.loads(trader_data)
        except (TypeError, ValueError):
            return EngineState(version=self.version)
        if not isinstance(raw, dict):
            return EngineState(version=self.version)
        stored_version = self._safe_int(raw.get('version'), default=self.version)
        if stored_version != self.version:
            raw = self._migrate(raw, from_version=stored_version)
        state = EngineState(version=self.version)
        raw_products = raw.get('products', {})
        if not isinstance(raw_products, dict):
            return state
        for product, payload in raw_products.items():
            if not isinstance(product, str) or not isinstance(payload, dict):
                continue
            state.products[product] = ProductMemory(recent_mids=self._coerce_float_list(payload.get('recent_mids')), recent_spreads=self._coerce_float_list(payload.get('recent_spreads')), counters=self._coerce_int_dict(payload.get('counters')), flags=self._coerce_bool_dict(payload.get('flags')), values=self._coerce_float_dict(payload.get('values')))
        return state

    def save(self, state: EngineState) -> str:
        try:
            payload = asdict(state)
            payload['version'] = self.version
            encoded = self._encode(payload)
            if len(encoded) <= self.max_chars:
                return encoded
            compact: dict[str, Any] = {'version': self.version, 'products': {}}
            for product, memory in state.products.items():
                compact['products'][product] = {'recent_mids': memory.recent_mids[-self.truncated_history_keep:], 'recent_spreads': memory.recent_spreads[-self.truncated_history_keep:], 'counters': memory.counters, 'flags': memory.flags, 'values': memory.values}
            encoded = self._encode(compact)
            if len(encoded) <= self.max_chars:
                return encoded
        except ValueError:
            warnings.warn('StateStore.save refused to emit non-finite values (NaN/Infinity) and dropped all product memory for this iteration. Investigate which strategy wrote the bad value.', RuntimeWarning, stacklevel=2)
        return self._encode({'version': self.version, 'products': {}})

    def _migrate(self, raw: dict[str, Any], *, from_version: int) -> dict[str, Any]:
        if from_version != self.version:
            warnings.warn(f'StateStore._migrate invoked with from_version={from_version} (current={self.version}) but the base implementation is a no-op. Override _migrate or bump the schema carefully.', UserWarning, stacklevel=2)
        return raw

    @staticmethod
    def _encode(payload: dict[str, Any]) -> str:
        return json.dumps(payload, separators=(',', ':'), sort_keys=True, allow_nan=False)

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _coerce_float_list(self, value: Any) -> list[float]:
        if not isinstance(value, list):
            return []
        coerced = [float(item) for item in value if isinstance(item, (int, float)) and (not isinstance(item, bool))]
        if len(coerced) > self.max_history:
            coerced = coerced[-self.max_history:]
        return coerced

    @staticmethod
    def _coerce_int_dict(value: Any) -> dict[str, int]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, int] = {}
        for key, item in value.items():
            if isinstance(item, bool):
                continue
            if isinstance(item, (int, float)):
                out[str(key)] = int(item)
        return out

    @staticmethod
    def _coerce_bool_dict(value: Any) -> dict[str, bool]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, bool] = {}
        for key, item in value.items():
            if isinstance(item, bool):
                out[str(key)] = item
        return out

    @staticmethod
    def _coerce_float_dict(value: Any) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, float] = {}
        for key, item in value.items():
            if isinstance(item, bool):
                continue
            if isinstance(item, (int, float)):
                out[str(key)] = float(item)
        return out

class InMemoryStateStore(StateStore):
    _TOKEN = '__IN_MEMORY_ENGINE_STATE__'

    def __init__(self, version: int=1, max_chars: int=50000, max_history: int=_MAX_PERSISTED_HISTORY, truncated_history_keep: int=_TRUNCATED_HISTORY_KEEP) -> None:
        super().__init__(version=version, max_chars=max_chars, max_history=max_history, truncated_history_keep=truncated_history_keep)
        self._cached_state: EngineState | None = None

    def load(self, trader_data: str | None) -> EngineState:
        if trader_data == self._TOKEN and self._cached_state is not None:
            return self._cached_state
        return super().load(trader_data)

    def save(self, state: EngineState) -> str:
        self._cached_state = state
        return self._TOKEN

    def clear(self) -> None:
        self._cached_state = None
_KEY_FLOW_SCORE = 'scan_flow_score'
_KEY_STEP_COUNT = 'scan_step_count'

class FlowAnalyzer:

    def __init__(self, config: ScannerConfig) -> None:
        self.config = config

    def scan(self, snapshot: NormalizedSnapshot, memory: ProductMemory) -> FlowReport | None:
        if not self.config.enabled:
            return None
        market_trades = tuple((t for t in snapshot.trades if t.source == 'market'))
        repeated_sizes = _count_sizes(market_trades)
        net_flow = _compute_net_flow(market_trades)
        total_volume = sum((t.quantity for t in market_trades)) or 1
        old_score = memory.values.get(_KEY_FLOW_SCORE, 0.0)
        normalised = max(-1.0, min(1.0, net_flow / total_volume))
        new_score = self.config.flow_decay * old_score + (1.0 - self.config.flow_decay) * normalised
        new_score = max(-1.0, min(1.0, new_score))
        recent_high, recent_low = _derive_extrema(memory.recent_mids, self.config.extrema_window)
        near_high = _any_near(market_trades, recent_high, self.config.extrema_tolerance)
        near_low = _any_near(market_trades, recent_low, self.config.extrema_tolerance)
        flags = _build_flags(repeated_sizes=repeated_sizes, flow_score=new_score, near_high=near_high, near_low=near_low, threshold=self.config.repeated_size_threshold)
        memory.values[_KEY_FLOW_SCORE] = new_score
        memory.counters[_KEY_STEP_COUNT] = memory.counters.get(_KEY_STEP_COUNT, 0) + 1
        return FlowReport(product=snapshot.product, timestamp=snapshot.timestamp, repeated_sizes=MappingProxyType(repeated_sizes), net_flow=net_flow, flow_score=round(new_score, 6), near_high=near_high, near_low=near_low, flags=flags, metadata=MappingProxyType({'market_trade_count': len(market_trades), 'total_volume': total_volume}))

def _count_sizes(trades: tuple[TradePrint, ...]) -> dict[int, int]:
    return dict(Counter((t.quantity for t in trades)))

def _compute_net_flow(trades: tuple[TradePrint, ...]) -> int:
    net = 0
    for t in trades:
        has_buyer = t.buyer is not None and t.buyer != ''
        has_seller = t.seller is not None and t.seller != ''
        if has_buyer and (not has_seller):
            net += t.quantity
        elif has_seller and (not has_buyer):
            net -= t.quantity
    return net

def _derive_extrema(recent_mids: list[float], window: int) -> tuple[float | None, float | None]:
    if not recent_mids:
        return (None, None)
    tail = recent_mids[-window:] if window > 0 else recent_mids
    return (max(tail), min(tail))

def _any_near(trades: tuple[TradePrint, ...], level: float | None, tolerance: float) -> bool:
    if level is None or not trades:
        return False
    return any((abs(t.price - level) <= tolerance for t in trades))

def _build_flags(*, repeated_sizes: dict[int, int], flow_score: float, near_high: bool, near_low: bool, threshold: int) -> tuple[str, ...]:
    flags: list[str] = []
    for qty, count in sorted(repeated_sizes.items()):
        if count >= threshold:
            flags.append(f'repeated_size_{qty}x{count}')
    if flow_score > 0.5:
        flags.append('buy_pressure')
    elif flow_score < -0.5:
        flags.append('sell_pressure')
    if near_high:
        flags.append('near_local_high')
    if near_low:
        flags.append('near_local_low')
    return tuple(flags)

def _effective_taker_edges(config: ProductConfig, *, in_early_window: bool) -> tuple[float, float]:
    buy = config.taker_edge_buy if config.taker_edge_buy is not None else config.taker_edge
    sell = config.taker_edge_sell if config.taker_edge_sell is not None else config.taker_edge
    if in_early_window:
        if config.early_taker_edge_buy is not None:
            buy = config.early_taker_edge_buy
        if config.early_taker_edge_sell is not None:
            sell = config.early_taker_edge_sell
    return (buy, sell)

class SignalEngine:

    def build_market_making_intent(self, product: str, snapshot: NormalizedSnapshot, fair_value: FairValueEstimate, config: ProductConfig) -> SignalIntent:
        in_early_window = config.early_window > 0 and snapshot.timestamp < config.early_window
        buy_taker_edge, sell_taker_edge = _effective_taker_edges(config, in_early_window=in_early_window)
        position_ratio = snapshot.position / config.position_limit if config.position_limit else 0.0
        skew_multiplier = 1.0
        if in_early_window and snapshot.position < 0 and (config.early_short_skew_mult != 1.0):
            skew_multiplier = config.early_short_skew_mult
        skew = position_ratio * config.inventory_skew * skew_multiplier
        effective_flatten = config.flatten_threshold
        if in_early_window and snapshot.position < 0 and (config.early_short_flatten is not None):
            effective_flatten = config.early_short_flatten
        flattening = abs(position_ratio) >= effective_flatten
        buy_below: float | None = fair_value.price - buy_taker_edge - skew
        sell_above: float | None = fair_value.price + sell_taker_edge - skew
        raw_bid = math.floor(fair_value.price - config.maker_edge - skew)
        raw_ask = math.ceil(fair_value.price + config.maker_edge - skew)
        if snapshot.best_ask is not None:
            raw_bid = min(raw_bid, snapshot.best_ask.price - config.tick_size)
        if snapshot.best_bid is not None:
            raw_ask = max(raw_ask, snapshot.best_bid.price + config.tick_size)
        bid_size = config.quote_size
        ask_size = config.quote_size
        mode: ExecutionMode = 'hybrid'
        rationale = 'market_make_around_fair_value'
        if flattening:
            mode = 'recovery'
            rationale = 'inventory_recovery'
            if snapshot.position > 0:
                bid_size = 0
                buy_below = None
                raw_ask = min(raw_ask, math.floor(fair_value.price))
            elif snapshot.position < 0:
                ask_size = 0
                sell_above = None
                raw_bid = max(raw_bid, math.ceil(fair_value.price))
        if in_early_window and config.early_short_cap is not None and (snapshot.position <= config.early_short_cap):
            sell_above = None
            ask_size = 0
            if mode != 'recovery':
                mode = 'recovery'
                rationale = 'early_short_cap'
        quote = QuoteIntent(bid_price=raw_bid if bid_size > 0 else None, bid_size=bid_size, ask_price=raw_ask if ask_size > 0 else None, ask_size=ask_size)
        return SignalIntent(product=product, fair_value=fair_value, mode=mode, buy_below=buy_below, sell_above=sell_above, quote=quote, rationale=rationale, metadata={'position_ratio': round(position_ratio, 4), 'skew': round(skew, 4), 'flattening': flattening, 'in_early_window': in_early_window})

class ExecutionEngine:

    def generate_orders(self, snapshot: NormalizedSnapshot, intent: SignalIntent, config: ProductConfig) -> list[Order]:
        orders: list[Order] = []
        remaining_buy = config.max_aggressive_size
        remaining_sell = config.max_aggressive_size
        if intent.buy_below is not None:
            for ask in snapshot.asks:
                if ask.price > intent.buy_below or remaining_buy <= 0:
                    break
                quantity = min(ask.volume, remaining_buy)
                if quantity > 0:
                    orders.append(Order(snapshot.product, ask.price, quantity))
                    remaining_buy -= quantity
        if intent.sell_above is not None:
            for bid in snapshot.bids:
                if bid.price < intent.sell_above or remaining_sell <= 0:
                    break
                quantity = min(bid.volume, remaining_sell)
                if quantity > 0:
                    orders.append(Order(snapshot.product, bid.price, -quantity))
                    remaining_sell -= quantity
        if intent.quote is not None:
            if intent.quote.bid_price is not None and intent.quote.bid_size > 0:
                orders.append(Order(snapshot.product, intent.quote.bid_price, intent.quote.bid_size))
            if intent.quote.ask_price is not None and intent.quote.ask_size > 0:
                orders.append(Order(snapshot.product, intent.quote.ask_price, -intent.quote.ask_size))
        return orders

@dataclass(frozen=True)
class Capacity:
    buy: int
    sell: int

class RiskManager:

    @staticmethod
    def remaining_buy_capacity(position: int, limit: int) -> int:
        if limit < 0:
            raise ValueError('limit must be >= 0')
        return max(0, limit - position)

    @staticmethod
    def remaining_sell_capacity(position: int, limit: int) -> int:
        if limit < 0:
            raise ValueError('limit must be >= 0')
        return max(0, limit + position)

    @classmethod
    def capacity(cls, position: int, limit: int) -> Capacity:
        return Capacity(buy=cls.remaining_buy_capacity(position, limit), sell=cls.remaining_sell_capacity(position, limit))

    @staticmethod
    def inventory_ratio(position: int, limit: int) -> float:
        if limit <= 0:
            return 0.0
        return position / limit

    def clip_orders(self, product: str, orders: list[Order], current_position: int, limit: int) -> list[Order]:
        if limit < 0:
            raise ValueError('limit must be >= 0')
        buy_capacity = self.remaining_buy_capacity(current_position, limit)
        sell_capacity = self.remaining_sell_capacity(current_position, limit)
        clipped: list[Order] = []
        for order in orders:
            if order.symbol != product:
                raise ValueError(f'risk.clip_orders: order symbol {order.symbol!r} does not match product {product!r}')
            if order.quantity == 0:
                continue
            if order.quantity > 0:
                quantity = min(order.quantity, buy_capacity)
                if quantity > 0:
                    clipped.append(Order(order.symbol, order.price, quantity))
                    buy_capacity -= quantity
            else:
                quantity = min(-order.quantity, sell_capacity)
                if quantity > 0:
                    clipped.append(Order(order.symbol, order.price, -quantity))
                    sell_capacity -= quantity
        return clipped

class ResidualAllocator:

    def __init__(self, config: ResidualConfig) -> None:
        self._config = config

    def augment_orders(self, *, product: str, orders: list[Order], snapshot: NormalizedSnapshot, fair_value: float, position: int, limit: int, mode: ExecutionMode='maker') -> list[Order]:
        if not self._config.enabled:
            return orders
        if mode == 'recovery':
            return orders
        buy_capacity = max(0, limit - position)
        sell_capacity = max(0, limit + position)
        main_bid_prices: set[int] = set()
        main_ask_prices: set[int] = set()
        for order in orders:
            if order.quantity > 0:
                buy_capacity -= order.quantity
                main_bid_prices.add(order.price)
            elif order.quantity < 0:
                sell_capacity -= abs(order.quantity)
                main_ask_prices.add(order.price)
        buy_capacity = max(0, buy_capacity)
        sell_capacity = max(0, sell_capacity)
        residual_orders: list[Order] = []
        if buy_capacity > 0:
            bid_price = math.floor(fair_value - self._config.residual_edge)
            bid_size = min(self._config.residual_size, buy_capacity)
            best_ask = snapshot.best_ask
            crosses_spread = best_ask is not None and bid_price >= best_ask.price
            duplicates_main = bid_price in main_bid_prices
            if bid_size > 0 and (not crosses_spread) and (not duplicates_main):
                residual_orders.append(Order(product, bid_price, bid_size))
        if sell_capacity > 0:
            ask_price = math.ceil(fair_value + self._config.residual_edge)
            ask_size = min(self._config.residual_size, sell_capacity)
            best_bid = snapshot.best_bid
            crosses_spread = best_bid is not None and ask_price <= best_bid.price
            duplicates_main = ask_price in main_ask_prices
            if ask_size > 0 and (not crosses_spread) and (not duplicates_main):
                residual_orders.append(Order(product, ask_price, -ask_size))
        if not residual_orders:
            return orders
        return [*orders, *residual_orders]

@dataclass(frozen=True)
class StrategyContext:
    product: str
    snapshot: NormalizedSnapshot
    memory: ProductMemory
    config: ProductConfig

class BaseStrategy(ABC):

    @abstractmethod
    def generate_intent(self, context: StrategyContext) -> SignalIntent:
        raise NotImplementedError

class MarketMakingStrategy(BaseStrategy):

    def __init__(self, fair_value_engine: FairValueEngine, signal_engine: SignalEngine) -> None:
        self.fair_value_engine = fair_value_engine
        self.signal_engine = signal_engine

    def generate_intent(self, context: StrategyContext) -> SignalIntent:
        fair_value = self.fair_value_engine.estimate(context.product, context.snapshot, context.memory, context.config)
        return self.signal_engine.build_market_making_intent(context.product, context.snapshot, fair_value, context.config)
_TAKE_ANY_ASK: float = 1000000000.0

class BuyAndHoldStrategy(BaseStrategy):

    def __init__(self, fair_value_engine: FairValueEngine | None=None, signal_engine: SignalEngine | None=None) -> None:
        del fair_value_engine, signal_engine

    def generate_intent(self, context: StrategyContext) -> SignalIntent:
        mid = context.snapshot.mid if context.snapshot.mid is not None else 0.0
        return SignalIntent(product=context.product, fair_value=FairValueEstimate(price=mid, method='buy_and_hold'), mode='taker', buy_below=_TAKE_ANY_ASK, sell_above=None, quote=QuoteIntent(bid_price=None, bid_size=0, ask_price=None, ask_size=0), rationale='buy_and_hold')
StrategyFactory = Callable[[FairValueEngine, SignalEngine], BaseStrategy]
STRATEGY_REGISTRY: Mapping[str, StrategyFactory] = MappingProxyType({'market_making': MarketMakingStrategy, 'buy_and_hold': BuyAndHoldStrategy})
__all__ = ['STRATEGY_REGISTRY', 'BaseStrategy', 'BuyAndHoldStrategy', 'MarketMakingStrategy', 'StrategyFactory']
_LOG = logging.getLogger(__name__)

class Trader:

    def __init__(self, config: EngineConfig | None=None, *, state_store: StateStore | None=None, reraise_exceptions: bool=False) -> None:
        self.config = config or round1_combined_v6_engine_config()
        self.state_store = state_store or StateStore(version=self.config.state_version, max_chars=self.config.max_trader_data_chars)
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

    def _build_strategies(self) -> dict[str, BaseStrategy]:
        strategies: dict[str, BaseStrategy] = {}
        for product_config in self.config.products.values():
            name = product_config.strategy_name
            if name in strategies:
                continue
            factory = STRATEGY_REGISTRY.get(name)
            if factory is None:
                _LOG.warning('Unknown strategy %r for product config; will be skipped', name)
                continue
            strategies[name] = factory(self.fair_value_engine, self.signal_engine)
        return strategies

    def bid(self) -> int:
        return 15

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        try:
            return self._run_body(state)
        except Exception:
            _LOG.exception('Trader.run crashed; returning empty orders')
            if self._reraise_exceptions:
                raise
            return ({}, 0, state.traderData)

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
            legal_orders = self._step_product(product=product, snapshot=snapshot, memory=memory, product_config=product_config, strategy=strategy, timestamp=state.timestamp)
            results[product] = legal_orders
            self._update_memory(memory, snapshot, product_config.history_length)
        trader_data = self.state_store.save(engine_state)
        conversions = 0
        return (results, conversions, trader_data)

    def _step_product(self, *, product: str, snapshot: NormalizedSnapshot, memory: ProductMemory, product_config: ProductConfig, strategy: BaseStrategy, timestamp: int) -> list[Order]:
        flow_report = self.flow_analyzer.scan(snapshot, memory)
        context = StrategyContext(product=product, snapshot=snapshot, memory=memory, config=product_config)
        intent = strategy.generate_intent(context)
        raw_orders = self.execution_engine.generate_orders(snapshot, intent, product_config)
        raw_orders = self.residual_allocator.augment_orders(product=product, orders=raw_orders, snapshot=snapshot, fair_value=intent.fair_value.price, position=snapshot.position, limit=product_config.position_limit, mode=intent.mode)
        legal_orders = self.risk_manager.clip_orders(product=product, orders=raw_orders, current_position=snapshot.position, limit=product_config.position_limit)
        event: dict[str, object] = {'timestamp': timestamp, 'product': product, 'fair_value': round(intent.fair_value.price, 4), 'method': intent.fair_value.method, 'position': snapshot.position, 'mode': intent.mode, 'orders': [(order.price, order.quantity) for order in legal_orders]}
        if flow_report is not None:
            verbosity = self.config.scanner_config.verbosity
            if verbosity >= 2:
                event['flow_report'] = {'net_flow': flow_report.net_flow, 'flow_score': flow_report.flow_score, 'near_high': flow_report.near_high, 'near_low': flow_report.near_low, 'flags': list(flow_report.flags), 'repeated_sizes': dict(flow_report.repeated_sizes)}
            elif verbosity >= 1:
                event['scan_flags'] = list(flow_report.flags)
        self.logger.record(event)
        return legal_orders

    @staticmethod
    def _update_memory(memory: ProductMemory, snapshot: NormalizedSnapshot, history_length: int) -> None:
        if history_length <= 0:
            return
        if snapshot.mid is not None:
            bounded_append(memory.recent_mids, float(snapshot.mid), history_length)
        if snapshot.spread is not None:
            bounded_append(memory.recent_spreads, float(snapshot.spread), history_length)

    def reset(self) -> None:
        self.logger = DecisionLogger()

    def engine_state_from(self, trader_data: str | None) -> EngineState:
        return self.state_store.load(trader_data)

@dataclass(frozen=True)
class LadderParams:
    edges: tuple[float, ...] = (2.5, 5.0, 8.0, 12.0)
    size_mults: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0)
    skew_coef: float = 2.0
    flatten_threshold: float = 0.7
    weights: tuple[int, ...] | None = None
    spread_gate_enabled: bool = False
    gate_spread: int = 16
    inventory_asymmetric: bool = False
    buy_edges: tuple[float, ...] | None = None
    buy_size_mults: tuple[float, ...] | None = None
    buy_weights: tuple[int, ...] | None = None
    sell_edges: tuple[float, ...] | None = None
    sell_size_mults: tuple[float, ...] | None = None
    sell_weights: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        pass

class AshLadderStrategy(BaseStrategy):

    def __init__(self, fair_value_engine: FairValueEngine, signal_engine: SignalEngine, params: LadderParams) -> None:
        self.fair_value_engine = fair_value_engine
        self.signal_engine = signal_engine
        self.params = params

    def _build_schedule(self, weights: tuple[int, ...] | None, n: int, cache_name: str) -> tuple[int, ...]:
        cached = getattr(self, cache_name, None)
        if cached is not None:
            return cached
        if weights is None:
            sched = tuple(range(n))
        else:
            sched = []
            for i, w in enumerate(weights):
                sched.extend([i] * int(w))
            if not sched:
                sched = list(range(n))
            sched = tuple(sched)
        object.__setattr__(self, cache_name, sched)
        return sched

    def _pick_level(self, counter: int, snapshot: NormalizedSnapshot) -> int:
        params = self.params
        sched = self._build_schedule(params.weights, len(params.edges), '_cached_schedule')
        return sched[counter % len(sched)]

    def _pick_side_level(self, counter: int, side: str) -> tuple[float, float] | None:
        params = self.params
        if side == 'buy':
            edges = params.buy_edges
            mults = params.buy_size_mults
            weights = params.buy_weights
            cache = '_cached_buy_schedule'
        else:
            edges = params.sell_edges
            mults = params.sell_size_mults
            weights = params.sell_weights
            cache = '_cached_sell_schedule'
        if edges is None:
            return None
        sched = self._build_schedule(weights, len(edges), cache)
        idx = sched[counter % len(sched)]
        return (float(edges[idx]), float(mults[idx]))

    def generate_intent(self, context: StrategyContext) -> SignalIntent:
        product = context.product
        snapshot = context.snapshot
        config = context.config
        memory = context.memory
        params = self.params
        fair_value = self.fair_value_engine.estimate(product, snapshot, memory, config)
        counter = int(memory.counters.get('ash_ladder_counter', 0))
        level = self._pick_level(counter, snapshot)
        edge = float(params.edges[level])
        size_mult = float(params.size_mults[level])
        memory.counters['ash_ladder_counter'] = counter + 1
        if params.spread_gate_enabled and level > 0:
            if snapshot.best_bid is not None and snapshot.best_ask is not None:
                book_spread = int(snapshot.best_ask.price - snapshot.best_bid.price)
                if book_spread < params.gate_spread:
                    level = 0
                    edge = float(params.edges[0])
                    size_mult = float(params.size_mults[0])
        position_ratio = snapshot.position / config.position_limit if config.position_limit else 0.0
        skew = params.skew_coef * position_ratio
        flattening = abs(position_ratio) >= params.flatten_threshold
        buy_below: float | None = fair_value.price - config.taker_edge - skew
        sell_above: float | None = fair_value.price + config.taker_edge - skew
        bid_edge = edge
        ask_edge = edge
        bid_mult = size_mult
        ask_mult = size_mult
        buy_ps = self._pick_side_level(counter, 'buy')
        if buy_ps is not None:
            bid_edge, bid_mult = buy_ps
        sell_ps = self._pick_side_level(counter, 'sell')
        if sell_ps is not None:
            ask_edge, ask_mult = sell_ps
        if params.inventory_asymmetric and level > 0:
            inner_edge = float(params.edges[0])
            if snapshot.position > 0:
                bid_edge = inner_edge
            elif snapshot.position < 0:
                ask_edge = inner_edge
        raw_bid = math.floor(fair_value.price - bid_edge - skew)
        raw_ask = math.ceil(fair_value.price + ask_edge - skew)
        if snapshot.best_ask is not None:
            raw_bid = min(raw_bid, snapshot.best_ask.price - config.tick_size)
        if snapshot.best_bid is not None:
            raw_ask = max(raw_ask, snapshot.best_bid.price + config.tick_size)
        base_size = config.quote_size
        bid_size = max(1, int(round(base_size * bid_mult)))
        ask_size = max(1, int(round(base_size * ask_mult)))
        mode: ExecutionMode = 'hybrid'
        rationale = f'ash_ladder_lvl{level}'
        if flattening:
            mode = 'recovery'
            rationale = 'ash_ladder_recovery'
            if snapshot.position > 0:
                bid_size = 0
                buy_below = None
                raw_ask = min(raw_ask, math.floor(fair_value.price))
            elif snapshot.position < 0:
                ask_size = 0
                sell_above = None
                raw_bid = max(raw_bid, math.ceil(fair_value.price))
        quote = QuoteIntent(bid_price=raw_bid if bid_size > 0 else None, bid_size=bid_size, ask_price=raw_ask if ask_size > 0 else None, ask_size=ask_size)
        metadata: dict[str, Scalar] = {'position_ratio': round(position_ratio, 4), 'skew': round(skew, 4), 'edge': edge, 'level': level, 'size_mult': size_mult, 'flattening': flattening}
        return SignalIntent(product=product, fair_value=fair_value, mode=mode, buy_below=buy_below, sell_above=sell_above, quote=quote, rationale=rationale, metadata=MappingProxyType(metadata))
_TAKE_ANY_ASK: float = 1000000000.0

@dataclass(frozen=True)
class V6CombinedParams:
    base_long: int = 65
    floor: int = 0
    ceiling: int = 80
    step: int = 8
    opening_passive_window: int = 3
    opening_seed_size: int = 50
    opening_taker_fallback_tick: int = 3
    opening_no_short: bool = True
    opening_max_size_per_tick: int = 20
    passive_bid_improve: int = 1
    add_thresh: float = 3.0
    trim_thresh: float = 8.0
    add_gain: float = 5.0
    trim_gain: float = 2.0
    guard_window: int = 32
    guard_negative_slope: float = 0.01
    guard_r2_min: float = 0.0
    guard_target: int = 0
    micro_residual_threshold: float = 3.0
    micro_imbalance_threshold: float = 0.3
    micro_add_size: int = 2
    micro_trim_size: int = 2
    maker_base_bid_edge: float = 3.0
    maker_base_ask_edge: float = 5.0
    maker_quote_size: int = 5
    maker_inventory_skew_coef: float = 0.04
    min_spread_for_maker: int = 4
    drift_slope_skew_factor: float = 10.0
    drift_max_asymmetry: float = 3.0
    drift_slope_r2_min: float = 0.3
    drift_reversal_slope_threshold: float = 0.02
    drift_reversal_r2_min: float = 0.3
    drift_reversal_target: int = 0
    exec_style: str = 'hybrid'
    hybrid_threshold: float = 2.0

    def __post_init__(self) -> None:
        pass

class PepperV6CombinedStrategy(BaseStrategy):
    _TICK_KEY = 'v6_tick_count'

    def __init__(self, fair_value_engine: FairValueEngine, signal_engine: SignalEngine, params: V6CombinedParams) -> None:
        self.fair_value_engine = fair_value_engine
        self.signal_engine = signal_engine
        self.params = params

    def generate_intent(self, context: StrategyContext) -> SignalIntent:
        product = context.product
        snapshot = context.snapshot
        memory = context.memory
        config = context.config
        params = self.params
        fair_value: FairValueEstimate = self.fair_value_engine.estimate(product, snapshot, memory, config)
        fair_price = float(fair_value.price)
        effective_ceiling = min(params.ceiling, config.position_limit)
        tick_count = memory.counters.get(self._TICK_KEY, 0)
        memory.counters[self._TICK_KEY] = tick_count + 1
        below_seed = snapshot.position < params.opening_seed_size and params.opening_seed_size > 0
        in_passive_open = tick_count < params.opening_passive_window and below_seed
        in_taker_fallback = tick_count >= params.opening_taker_fallback_tick and below_seed
        best_bid = snapshot.best_bid
        best_ask = snapshot.best_ask
        spread = snapshot.spread
        mid = float(snapshot.mid) if snapshot.mid is not None else fair_price
        residual = mid - fair_price
        imbalance = snapshot.book_imbalance
        drift_fit = _ols_fit_recent_mids(memory.recent_mids, snapshot.mid, window=params.guard_window)
        slope: float = 0.0
        fit_r2: float = 0.0
        fit_samples: int = 0
        if drift_fit is not None:
            slope, fit_r2, fit_samples = drift_fit
        guard_active = params.guard_window > 0 and slope <= -params.guard_negative_slope and (fit_r2 >= params.guard_r2_min)
        reversal_active = slope <= -params.drift_reversal_slope_threshold and fit_r2 >= params.drift_reversal_r2_min
        asymmetry: float = 0.0
        if fit_r2 >= params.drift_slope_r2_min:
            asymmetry = min(params.drift_max_asymmetry, params.drift_slope_skew_factor * abs(slope))
        bid_price: int | None = None
        ask_price: int | None = None
        bid_size: int = 0
        ask_size: int = 0
        taker_buy: float | None = None
        taker_sell: float | None = None
        raw_target: int = params.opening_seed_size
        effective_target: int = snapshot.position
        micro_bias: int = 0
        if in_passive_open and best_bid is not None:
            passive_px = best_bid.price + params.passive_bid_improve
            if best_ask is not None:
                passive_px = min(passive_px, best_ask.price - config.tick_size)
            buy_capacity = min(effective_ceiling - snapshot.position, params.opening_seed_size - snapshot.position, params.opening_max_size_per_tick)
            if buy_capacity > 0:
                bid_price = int(passive_px)
                bid_size = int(buy_capacity)
        if in_taker_fallback:
            taker_buy = _TAKE_ANY_ASK
        past_opening = not below_seed or tick_count >= max(params.opening_passive_window, params.opening_taker_fallback_tick + 2)
        if past_opening:
            raw_target = compute_target_position(residual, base_long=params.base_long, add_thresh=params.add_thresh, trim_thresh=params.trim_thresh, add_gain=params.add_gain, trim_gain=params.trim_gain, floor=params.floor, ceiling=effective_ceiling)
            micro_bias = _micro_target_bias(residual, imbalance, residual_threshold=params.micro_residual_threshold, imbalance_threshold=params.micro_imbalance_threshold, add_size=params.micro_add_size, trim_size=params.micro_trim_size)
            raw_target += micro_bias
            raw_target = max(params.floor, min(effective_ceiling, raw_target))
            if guard_active:
                raw_target = min(raw_target, params.guard_target)
            if reversal_active:
                raw_target = min(raw_target, params.drift_reversal_target)
            raw_gap = raw_target - snapshot.position
            step_clipped = max(-params.step, min(params.step, raw_gap))
            effective_target = snapshot.position + step_clipped
            effective_target = max(params.floor, min(effective_ceiling, effective_target))
            effective_gap = effective_target - snapshot.position
            maker_enabled = params.maker_quote_size > 0 and (spread is None or spread >= params.min_spread_for_maker)
            if maker_enabled and bid_price is None:
                inventory_dev = snapshot.position - params.base_long
                inv_skew = params.maker_inventory_skew_coef * inventory_dev
                bid_edge = params.maker_base_bid_edge
                ask_edge = params.maker_base_ask_edge
                if reversal_active:
                    bid_edge += asymmetry
                    ask_edge -= asymmetry
                else:
                    bid_edge -= asymmetry
                    ask_edge += asymmetry
                bid_edge = max(0.0, bid_edge + inv_skew)
                ask_edge = max(0.0, ask_edge - inv_skew)
                raw_bid_px = math.floor(fair_price - bid_edge)
                raw_ask_px = math.ceil(fair_price + ask_edge)
                if best_ask is not None:
                    raw_bid_px = min(raw_bid_px, best_ask.price - config.tick_size)
                if best_bid is not None:
                    raw_ask_px = max(raw_ask_px, best_bid.price + config.tick_size)
                if best_bid is not None:
                    raw_bid_px = max(raw_bid_px, best_bid.price + config.tick_size)
                if best_ask is not None:
                    raw_ask_px = min(raw_ask_px, best_ask.price - config.tick_size)
                if raw_ask_px <= raw_bid_px:
                    raw_bid_px = raw_ask_px - config.tick_size
                qs = params.maker_quote_size
                buy_capacity = effective_ceiling - snapshot.position
                sell_capacity = snapshot.position - params.floor
                if effective_gap > 0:
                    if buy_capacity > 0:
                        bid_price = raw_bid_px
                        bid_size = min(qs, buy_capacity)
                elif effective_gap < 0:
                    if sell_capacity > 0:
                        ask_price = raw_ask_px
                        ask_size = min(qs, sell_capacity)
                else:
                    half_qs = max(1, qs // 2)
                    if buy_capacity > 0:
                        bid_price = raw_bid_px
                        bid_size = min(half_qs, buy_capacity)
                    if sell_capacity > 0:
                        ask_price = raw_ask_px
                        ask_size = min(half_qs, sell_capacity)
            taker_eligible = params.exec_style == 'taker' or (params.exec_style == 'hybrid' and abs(residual) >= params.hybrid_threshold)
            if taker_eligible and (not below_seed):
                if effective_gap > 0:
                    taker_buy = fair_price - config.taker_edge
                elif effective_gap < 0:
                    taker_sell = fair_price + config.taker_edge
        if snapshot.position >= effective_ceiling:
            bid_price = None
            bid_size = 0
            taker_buy = None
        if snapshot.position <= params.floor:
            ask_price = None
            ask_size = 0
            taker_sell = None
        if below_seed and params.opening_no_short:
            ask_price = None
            ask_size = 0
            taker_sell = None
        quote = QuoteIntent(bid_price=bid_price if bid_size > 0 else None, bid_size=bid_size, ask_price=ask_price if ask_size > 0 else None, ask_size=ask_size)
        metadata: dict[str, Scalar] = {'fair_value': round(fair_price, 4), 'residual': round(residual, 4), 'imbalance': round(imbalance, 4) if imbalance is not None else 'none', 'slope': round(slope, 6), 'fit_r2': round(fit_r2, 4), 'fit_samples': fit_samples, 'asymmetry': round(asymmetry, 4), 'guard_active': guard_active, 'reversal_active': reversal_active, 'tick_count': tick_count, 'below_seed': below_seed, 'in_passive_open': in_passive_open, 'in_taker_fallback': in_taker_fallback, 'past_opening': past_opening, 'position': snapshot.position, 'base_long': params.base_long, 'raw_target': raw_target, 'effective_target': effective_target, 'micro_bias': micro_bias, 'floor': params.floor, 'ceiling': effective_ceiling}
        return SignalIntent(product=product, fair_value=fair_value, mode='hybrid', buy_below=taker_buy, sell_above=taker_sell, quote=quote, rationale='pepper_v6_combined', metadata=MappingProxyType(metadata))
_ASH_COMBINED_V6A_PARAMS = LadderParams(edges=(2.5, 3.5, 5.0), size_mults=(1.0, 1.5, 2.0), skew_coef=2.0, flatten_threshold=0.7, weights=(3, 1, 1))

def _ash_combined_v6a_factory(fve: FairValueEngine, sig: SignalEngine) -> BaseStrategy:
    return AshLadderStrategy(fve, sig, _ASH_COMBINED_V6A_PARAMS)
_PEP_COMBINED_V6A_PARAMS = V6CombinedParams(base_long=80, floor=0, ceiling=80, step=8, opening_passive_window=3, opening_seed_size=65, opening_taker_fallback_tick=3, opening_no_short=True, opening_max_size_per_tick=20, passive_bid_improve=1, add_thresh=3.0, trim_thresh=8.0, add_gain=5.0, trim_gain=2.0, guard_window=32, guard_negative_slope=0.01, guard_r2_min=0.0, guard_target=0, micro_residual_threshold=3.0, micro_imbalance_threshold=0.3, micro_add_size=2, micro_trim_size=2, maker_base_bid_edge=3.0, maker_base_ask_edge=5.0, maker_quote_size=0, maker_inventory_skew_coef=0.04, min_spread_for_maker=4, drift_slope_skew_factor=10.0, drift_max_asymmetry=3.0, drift_slope_r2_min=0.3, drift_reversal_slope_threshold=0.02, drift_reversal_r2_min=0.3, drift_reversal_target=0, exec_style='hybrid', hybrid_threshold=2.0)

def _pep_combined_v6a_factory(fve: FairValueEngine, sig: SignalEngine) -> BaseStrategy:
    return PepperV6CombinedStrategy(fve, sig, _PEP_COMBINED_V6A_PARAMS)
KNOWN_STRATEGY_NAMES = tuple(sorted(set(KNOWN_STRATEGY_NAMES) | {'ash_ladder', 'pepper_v6_combined'}))
STRATEGY_REGISTRY = MappingProxyType(dict(STRATEGY_REGISTRY, **{'ash_ladder': _ash_combined_v6a_factory, 'pepper_v6_combined': _pep_combined_v6a_factory}))
