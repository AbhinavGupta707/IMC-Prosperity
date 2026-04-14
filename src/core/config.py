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

from src.core.types import ResidualConfig, ScannerConfig

KNOWN_STRATEGY_NAMES: tuple[str, ...] = ("market_making",)
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
    scanner_config: ScannerConfig = field(default_factory=ScannerConfig)
    residual_config: ResidualConfig = field(default_factory=ResidualConfig)

    def __post_init__(self) -> None:
        if self.state_version < 1:
            raise ValueError("EngineConfig.state_version must be >= 1")
        if self.max_trader_data_chars <= 0:
            raise ValueError("EngineConfig.max_trader_data_chars must be > 0")

    def product_config(self, product: str) -> ProductConfig | None:
        return self.products.get(product)


def default_engine_config() -> EngineConfig:
    # Tutorial products (EMERALDS, TOMATOES) plus Round-1 products
    # (ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT). All share the
    # market-making strategy and differ only by configuration. See
    # ``outputs/round_1/notes/strategy_family_proposal.md`` for the
    # per-product Round-1 family rationale.
    return EngineConfig(
        products={
            "EMERALDS": ProductConfig(
                position_limit=80,
                strategy_name="market_making",
                fair_value_method="anchor",
                fair_value_fallbacks=("microprice", "mid"),
                anchor_price=10_000.0,
                taker_edge=1.0,
                maker_edge=2.0,
                quote_size=5,
                max_aggressive_size=10,
                inventory_skew=8.0,
                flatten_threshold=0.75,
                history_length=32,
            ),
            "TOMATOES": ProductConfig(
                position_limit=80,
                strategy_name="market_making",
                fair_value_method="wall_mid",
                fair_value_fallbacks=("mid", "microprice"),
                taker_edge=1.0,
                maker_edge=1.0,
                quote_size=4,
                max_aggressive_size=8,
                inventory_skew=12.0,
                flatten_threshold=0.7,
                history_length=48,
            ),
            # --- Round 1 ---
            # ASH_COATED_OSMIUM: anchored oscillator at ~10 000 with a
            # 16-tick stable spread; classic wide-spread maker product.
            # Primary wall_mid tracks the center of mass of the visible
            # book and was the most cross-day robust in Phase 1
            # (outputs/round_1/research/ash_coated_osmium_dossier.md).
            # Position limit is a placeholder pending official
            # confirmation.
            "ASH_COATED_OSMIUM": ProductConfig(
                position_limit=50,
                strategy_name="market_making",
                fair_value_method="wall_mid",
                fair_value_fallbacks=("mid", "microprice"),
                anchor_price=10_000.0,  # fallback only (not primary)
                taker_edge=1.0,
                maker_edge=1.0,
                quote_size=5,
                max_aggressive_size=10,
                inventory_skew=4.0,
                flatten_threshold=0.7,
                history_length=48,
            ),
            # INTARIAN_PEPPER_ROOT: deterministic drift +0.1 per
            # timestamp step with a +1 000 overnight jump. Fair value
            # is tracked by the `linear_drift` estimator (added in
            # Phase 3) with a book-aware fallback chain for warm-up
            # and one-sided snapshots. See
            # outputs/round_1/research/intarian_pepper_root_dossier.md.
            #
            # Fallback-chain design note: this product has no
            # `anchor_price`, so the `FairValueEngine.estimate`
            # zero-fallback (price=0.0) is only avoided when at least
            # one entry in the chain always returns a value. The chain
            # below is ordered so that `linear_drift` (always returns
            # something after warm-up) and `mid` cover that role.
            # Candidates like `depth_mid` and `hybrid_wall_micro` cannot
            # be used as primaries here without adding such a safety
            # net — see outputs/round_1/notes/phase4_sweep_shortlist.md.
            "INTARIAN_PEPPER_ROOT": ProductConfig(
                position_limit=50,
                strategy_name="market_making",
                fair_value_method="linear_drift",
                fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
                taker_edge=1.0,
                maker_edge=1.5,
                quote_size=4,
                max_aggressive_size=8,
                inventory_skew=2.0,
                flatten_threshold=0.8,
                history_length=48,
            ),
        }
    )


ROUND1_PRODUCTS: tuple[str, ...] = ("ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT")


def round1_engine_config() -> EngineConfig:
    """Engine config containing **only** the Round-1 products.

    Round-1 research scripts (sweeps, dossier, backtest runner) should
    use this so the tutorial products (EMERALDS, TOMATOES) do not
    silently join a round-1 replay. This keeps ``default_engine_config``
    intact for the tutorial harness while giving round-1 tooling a
    focused baseline to ``replace()`` from.
    """
    base = default_engine_config()
    products = {
        name: config
        for name in ROUND1_PRODUCTS
        if (config := base.product_config(name)) is not None
    }
    return EngineConfig(
        state_version=base.state_version,
        max_trader_data_chars=base.max_trader_data_chars,
        diagnostics_verbosity=base.diagnostics_verbosity,
        products=products,
        scanner_config=base.scanner_config,
        residual_config=base.residual_config,
    )
