"""Core config types — ProductConfig, EngineConfig, and the ``with_bid_value``
helper. Split out of ``src/core/config.py`` so the R3 submission bundle can
ship these types without carrying the ~25KB of R1/R2 product-factory
functions that are only relevant to the legacy tutorial / Round-1 /
Round-2 exports.

Import contract:

- Anything that needs ``ProductConfig`` or ``EngineConfig`` (Trader,
  StateStore, Strategy contexts, tests) imports from here.
- R1/R2 export scripts, tests that load shipped variants (promoted,
  alt, v5micro_wide113, etc.), and the default engine config all live
  in ``src/core/config.py`` which re-exports the symbols below and
  adds the factory functions.

Validation happens at construction time so misconfigured runs fail
immediately instead of producing subtle bad behaviour deep inside the
live loop.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from src.core.types import ResidualConfig, ScannerConfig

KNOWN_STRATEGY_NAMES: tuple[str, ...] = ("buy_and_hold", "market_making")
KNOWN_ESTIMATOR_NAMES: tuple[str, ...] = (
    "anchor",
    "depth_mid",
    "ewma_mid",
    "filtered_wall_mid",
    "hybrid_wall_micro",
    "linear_drift",
    "microprice",
    "mid",
    "rolling_mid",
    "wall_mid",
    "weighted_mid",
)


def _format_known_names(names: tuple[str, ...]) -> str:
    return ", ".join(names) if names else "<none>"


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
    # Phase-9 fastsearch knobs (all optional, neutral defaults).
    taker_edge_buy: float | None = None
    taker_edge_sell: float | None = None
    early_window: int = 0
    early_taker_edge_buy: float | None = None
    early_taker_edge_sell: float | None = None
    early_short_cap: int | None = None
    early_short_skew_mult: float = 1.0
    early_short_flatten: float | None = None
    # Round-2 day-rollover flush: when True the trader flushes
    # ``memory.recent_mids`` / ``recent_spreads`` when the simulator's
    # timestamp resets (crosses a new day). Required for products whose
    # fair value depends on a cross-day fitted line that mis-anchors
    # when stale mids leak through.
    flush_history_on_day_rollover: bool = False

    def __post_init__(self) -> None:
        if self.strategy_name not in KNOWN_STRATEGY_NAMES:
            raise ValueError(
                "ProductConfig.strategy_name must be one of "
                f"{_format_known_names(KNOWN_STRATEGY_NAMES)} "
                f"(got {self.strategy_name!r})"
            )

        if self.fair_value_method not in KNOWN_ESTIMATOR_NAMES:
            raise ValueError(
                "ProductConfig.fair_value_method must be one of "
                f"{_format_known_names(KNOWN_ESTIMATOR_NAMES)} "
                f"(got {self.fair_value_method!r})"
            )

        unknown_fallbacks = tuple(
            name for name in self.fair_value_fallbacks if name not in KNOWN_ESTIMATOR_NAMES
        )
        if unknown_fallbacks:
            raise ValueError(
                "ProductConfig.fair_value_fallbacks contains unknown estimator(s) "
                f"{unknown_fallbacks}; known estimators: "
                f"{_format_known_names(KNOWN_ESTIMATOR_NAMES)}"
            )

        if self.position_limit <= 0:
            raise ValueError(
                f"ProductConfig.position_limit must be > 0 (got {self.position_limit})"
            )
        if self.tick_size <= 0:
            raise ValueError(f"ProductConfig.tick_size must be > 0 (got {self.tick_size})")
        if self.quote_size < 0:
            raise ValueError(f"ProductConfig.quote_size must be >= 0 (got {self.quote_size})")
        if self.max_aggressive_size < 0:
            raise ValueError(
                f"ProductConfig.max_aggressive_size must be >= 0 "
                f"(got {self.max_aggressive_size})"
            )
        if self.taker_edge < 0 or self.maker_edge < 0:
            raise ValueError("ProductConfig.*_edge must be >= 0")
        if self.inventory_skew < 0:
            raise ValueError("ProductConfig.inventory_skew must be >= 0")
        if not 0.0 <= self.flatten_threshold <= 1.0:
            raise ValueError(
                f"ProductConfig.flatten_threshold must be in [0, 1] "
                f"(got {self.flatten_threshold})"
            )
        if self.history_length < 0:
            raise ValueError("ProductConfig.history_length must be >= 0")
        if self.ewma_alpha is not None and not 0.0 < self.ewma_alpha <= 1.0:
            raise ValueError(f"ProductConfig.ewma_alpha must be in (0, 1] (got {self.ewma_alpha})")
        if self.fair_value_method == "anchor" and self.anchor_price is None:
            raise ValueError("ProductConfig: fair_value_method='anchor' requires anchor_price")
        if "anchor" in self.fair_value_fallbacks and self.anchor_price is None:
            raise ValueError(
                "ProductConfig: fair_value_fallbacks includes 'anchor' "
                "but anchor_price is not set"
            )
        # --- Phase-9 fastsearch knob validation ---
        if self.taker_edge_buy is not None and self.taker_edge_buy < 0:
            raise ValueError("ProductConfig.taker_edge_buy must be >= 0 when set")
        if self.taker_edge_sell is not None and self.taker_edge_sell < 0:
            raise ValueError("ProductConfig.taker_edge_sell must be >= 0 when set")
        if self.early_window < 0:
            raise ValueError("ProductConfig.early_window must be >= 0")
        if self.early_taker_edge_buy is not None and self.early_taker_edge_buy < 0:
            raise ValueError("ProductConfig.early_taker_edge_buy must be >= 0 when set")
        if self.early_taker_edge_sell is not None and self.early_taker_edge_sell < 0:
            raise ValueError("ProductConfig.early_taker_edge_sell must be >= 0 when set")
        if self.early_short_skew_mult < 0:
            raise ValueError("ProductConfig.early_short_skew_mult must be >= 0")
        if self.early_short_flatten is not None and not 0.0 <= self.early_short_flatten <= 1.0:
            raise ValueError(
                "ProductConfig.early_short_flatten must be in [0, 1] when set "
                f"(got {self.early_short_flatten})"
            )
        if self.early_short_cap is not None and self.early_short_cap > 0:
            raise ValueError(
                "ProductConfig.early_short_cap must be <= 0 when set "
                f"(got {self.early_short_cap}); use 0 to forbid ever going short"
            )


@dataclass(frozen=True)
class EngineConfig:
    state_version: int = 1
    max_trader_data_chars: int = 50_000
    diagnostics_verbosity: int = 1
    products: dict[str, ProductConfig] = field(default_factory=dict)
    scanner_config: ScannerConfig = field(default_factory=ScannerConfig)
    residual_config: ResidualConfig = field(default_factory=ResidualConfig)
    # Round-2 Market Access Fee bid (XIRECs). 0 = abstain from auction.
    # IMC normalises negative bids to 0; we enforce that at construction.
    bid_value: int = 0

    def __post_init__(self) -> None:
        if self.state_version < 1:
            raise ValueError("EngineConfig.state_version must be >= 1")
        if self.max_trader_data_chars <= 0:
            raise ValueError("EngineConfig.max_trader_data_chars must be > 0")
        if not isinstance(self.bid_value, int) or isinstance(self.bid_value, bool):
            raise TypeError(
                f"EngineConfig.bid_value must be int (got {type(self.bid_value).__name__})"
            )
        if self.bid_value < 0:
            raise ValueError(
                f"EngineConfig.bid_value must be >= 0 (got {self.bid_value})"
            )

    def product_config(self, product: str) -> ProductConfig | None:
        return self.products.get(product)


def with_bid_value(config: EngineConfig, bid_value: int) -> EngineConfig:
    """Return a copy of ``config`` with ``bid_value`` overridden.

    Used by the Round-2 export pipeline to inject a per-bundle MAF bid
    without touching the underlying engine factories.
    """
    return dataclasses.replace(config, bid_value=bid_value)


def default_engine_config() -> EngineConfig:
    """Fallback for R3 bundles that drop ``config.py``'s product factories.

    An R3 submission constructs its own ``EngineConfig`` (typically with
    ``products={}`` since the orchestrator owns the products), so this
    stub is only reached when a caller forgot to pass a config. Raise
    loudly rather than return a default that silently enables R1/R2
    behaviour.

    In R2 bundles ``config.py`` is loaded AFTER this module and
    overrides this stub with the real multi-product factory; the name
    resolution is: last definition in the bundle namespace wins.
    """
    raise RuntimeError(
        "default_engine_config() is not available in this submission bundle "
        "(R3 profile drops src/core/config.py). Construct Trader with an "
        "explicit EngineConfig, e.g. Trader(config=EngineConfig(products={}), "
        "orchestrator=orchestrator)."
    )
