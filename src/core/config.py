"""Engine and per-product configuration.

``ProductConfig`` is a frozen dataclass that binds every tunable knob for
one product. ``EngineConfig`` bundles a set of product configs with
runtime-wide knobs such as the state store version and the trader data
char budget.

Fair value resolution:

- ``fair_value_method`` names the primary estimator.
- ``fair_value_fallbacks`` is an ordered tuple of estimator names that
  will be tried in turn if the primary returns ``None`` (missing data,
  insufficient history, etc.). The doctrine requires a fallback path to
  always exist; this is where it lives.

Validation happens at construction time so misconfigured runs fail
immediately instead of producing subtle bad behavior deep inside the
live loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KNOWN_STRATEGY_NAMES: tuple[str, ...] = ("market_making",)
KNOWN_ESTIMATOR_NAMES: tuple[str, ...] = (
    "anchor",
    "depth_mid",
    "ewma_mid",
    "microprice",
    "mid",
    "rolling_mid",
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


@dataclass(frozen=True)
class EngineConfig:
    state_version: int = 1
    max_trader_data_chars: int = 50_000
    diagnostics_verbosity: int = 1
    products: dict[str, ProductConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state_version < 1:
            raise ValueError("EngineConfig.state_version must be >= 1")
        if self.max_trader_data_chars <= 0:
            raise ValueError("EngineConfig.max_trader_data_chars must be > 0")

    def product_config(self, product: str) -> ProductConfig | None:
        return self.products.get(product)


def default_engine_config() -> EngineConfig:
    # Both tutorial products use the shared market-making strategy, differing
    # only by their fair-value choice. maker_edge is kept at a principled 2
    # (tick beyond the anchor) rather than the data-fit value of 8 we briefly
    # used to chase the tutorial trade tape. See docs/eda_tutorial_round_1.md
    # for why the tutorial replay under-rewards inside-spread makers.
    return EngineConfig(
        products={
            "EMERALDS": ProductConfig(
                position_limit=20,
                strategy_name="market_making",
                fair_value_method="anchor",
                fair_value_fallbacks=("microprice", "mid"),
                anchor_price=10_000.0,
                taker_edge=1.0,
                maker_edge=2.0,
                quote_size=5,
                max_aggressive_size=10,
                inventory_skew=2.0,
                flatten_threshold=0.75,
                history_length=32,
            ),
            "TOMATOES": ProductConfig(
                position_limit=20,
                strategy_name="market_making",
                fair_value_method="weighted_mid",
                fair_value_fallbacks=("mid", "microprice"),
                taker_edge=1.0,
                maker_edge=1.0,
                quote_size=4,
                max_aggressive_size=8,
                inventory_skew=3.0,
                flatten_threshold=0.7,
                history_length=48,
            ),
        }
    )
