"""Engine and per-product configuration.

``ProductConfig`` is a frozen dataclass that binds every tunable knob for
one product. ``EngineConfig`` bundles a set of product configs with
runtime-wide knobs such as the state store version and the trader data
char budget.

Validation happens at construction time so misconfigured runs fail
immediately instead of producing subtle bad behavior deep inside the
live loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProductConfig:
    position_limit: int
    strategy_name: str
    fair_value_method: str
    tick_size: int = 1
    anchor_price: float | None = None
    taker_edge: float = 1.0
    maker_edge: float = 1.0
    quote_size: int = 5
    max_aggressive_size: int = 10
    inventory_skew: float = 2.0
    flatten_threshold: float = 0.8
    history_length: int = 32

    def __post_init__(self) -> None:
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
        if self.fair_value_method == "anchor" and self.anchor_price is None:
            raise ValueError("ProductConfig: fair_value_method='anchor' requires anchor_price")


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
    return EngineConfig(
        products={
            # EMERALDS maker_edge=8 intentionally quotes at 9992 / 10008
            # (mid - maker_edge and mid + maker_edge) where the tutorial
            # trade tape actually prints. Quoting strictly inside the
            # spread would capture more theoretical edge but produces
            # zero measurable passive fills in the tutorial replay.
            "EMERALDS": ProductConfig(
                position_limit=20,
                strategy_name="stable_anchor",
                fair_value_method="anchor",
                anchor_price=10_000.0,
                taker_edge=1.0,
                maker_edge=8.0,
                quote_size=5,
                max_aggressive_size=10,
                inventory_skew=2.0,
                flatten_threshold=0.75,
                history_length=32,
            ),
            "TOMATOES": ProductConfig(
                position_limit=20,
                strategy_name="adaptive_quote",
                fair_value_method="weighted_mid",
                taker_edge=1.0,
                maker_edge=2.0,
                quote_size=4,
                max_aggressive_size=8,
                inventory_skew=2.5,
                flatten_threshold=0.7,
                history_length=48,
            ),
        }
    )
