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
    # See ``outputs/round_1/fastsearch/pepper_memo.md``.
    taker_edge_buy: float | None = None
    taker_edge_sell: float | None = None
    early_window: int = 0
    early_taker_edge_buy: float | None = None
    early_taker_edge_sell: float | None = None
    early_short_cap: int | None = None
    early_short_skew_mult: float = 1.0
    early_short_flatten: float | None = None
    # Round-2 day-rollover handling: when True, the trader detects a
    # timestamp reset (snapshot.timestamp < last seen) and flushes
    # ``memory.recent_mids`` and ``memory.recent_spreads`` for this
    # product before the strategy runs. Required for any product whose
    # fair value depends on a fitted line that mis-anchors when stale
    # cross-day mids leak in (PEPPER's ``linear_drift`` is the
    # canonical case). Default False preserves Round-1 behaviour for
    # every other product.
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
        # An ``early_short_cap`` of e.g. -8 would allow a short of 8 before
        # the cap kicks in; 0 forbids ever going short. Very negative
        # caps are effectively a no-op. No hard numeric bound — just
        # flag values that are structurally nonsense.
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
    # Read by Trader.bid() and surfaced once per round.
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
            # position_limit=80 — IMC-confirmed Round-1 per-product cap.
            "ASH_COATED_OSMIUM": ProductConfig(
                position_limit=80,
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
            # timestamp step; the drift runs *continuously* across day
            # boundaries on the sample data, so the daily mean rises
            # ~1 000 per day (the Phase-2 "+1 000 overnight jump"
            # framing was a misread — see the dossier corrigendum
            # under outputs/round_1/research/intarian_pepper_root_dossier.md).
            # Fair value is tracked by the `linear_drift` estimator
            # (added in Phase 3) with a book-aware fallback chain for
            # warm-up and one-sided snapshots.
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
            # position_limit=80 — IMC-confirmed Round-1 per-product cap.
            "INTARIAN_PEPPER_ROOT": ProductConfig(
                position_limit=80,
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


# Phase-6 upload variants. Each is a thin wrapper that overrides the
# per-product fair-value / edge / inventory parameters on top of the
# round-1 baseline. The three variants together are the Phase-6 upload
# shortlist (see ``docs/round_1/upload_plan.md``).


def _round1_engine_with(**per_product_overrides: dict[str, object]) -> EngineConfig:
    """Helper: apply per-product field overrides on top of round1_engine_config."""
    from dataclasses import replace

    base = round1_engine_config()
    products = dict(base.products)
    for product, overrides in per_product_overrides.items():
        current = base.product_config(product)
        if current is None:
            continue
        products[product] = replace(current, **overrides)
    return EngineConfig(
        state_version=base.state_version,
        max_trader_data_chars=base.max_trader_data_chars,
        diagnostics_verbosity=base.diagnostics_verbosity,
        products=products,
        scanner_config=base.scanner_config,
        residual_config=base.residual_config,
    )


def round1_baseline_engine_config() -> EngineConfig:
    """Phase-6 baseline / control — Phase-3 Round-1 defaults verbatim."""
    return round1_engine_config()


def round1_promoted_engine_config() -> EngineConfig:
    """Phase-6 promoted / robust default. See
    ``outputs/round_1/notes/phase5_review_shortlist.md``.
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            fair_value_method="ewma_mid",
            fair_value_fallbacks=("mid", "microprice"),
            maker_edge=1.0,
            taker_edge=0.25,
            inventory_skew=4.0,
            flatten_threshold=0.7,
            history_length=48,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            fair_value_method="linear_drift",
            fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
            maker_edge=1.0,
            taker_edge=2.0,
            inventory_skew=2.0,
            flatten_threshold=0.7,
            history_length=32,
        ),
    )


def round1_h1_engine_config() -> EngineConfig:
    """Phase-8.5 hybrid H1 — promoted PEPPER + alt wall_mid ASH.

    Additive; does not replace promoted / alt. See
    ``outputs/round_1/phase8_5/hybrid_memo.md``.
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            fair_value_method="wall_mid",
            fair_value_fallbacks=("mid", "microprice"),
            maker_edge=1.5,
            taker_edge=0.5,
            inventory_skew=4.0,
            flatten_threshold=0.7,
            history_length=48,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            fair_value_method="linear_drift",
            fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
            maker_edge=1.0,
            taker_edge=2.0,
            inventory_skew=2.0,
            flatten_threshold=0.7,
            history_length=32,
        ),
    )


def round1_f5_engine_config() -> EngineConfig:
    """Phase-9 fastsearch F5 candidate — asymmetric-taker PEPPER + alt ASH.

    ASH leg = H1 / Alt wall_mid leg. PEPPER leg = promoted leg with
    per-side taker edges (buy=1.5, sell=3.0); all other PEPPER knobs
    match promoted. Additive export; does not replace promoted / H1 /
    alt. See ``outputs/round_1/fastsearch/final_recommendation.md``.
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            fair_value_method="wall_mid",
            fair_value_fallbacks=("mid", "microprice"),
            maker_edge=1.5,
            taker_edge=0.5,
            inventory_skew=4.0,
            flatten_threshold=0.7,
            history_length=48,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            fair_value_method="linear_drift",
            fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
            maker_edge=1.0,
            taker_edge=2.0,
            taker_edge_buy=1.5,
            taker_edge_sell=3.0,
            inventory_skew=2.0,
            flatten_threshold=0.7,
            history_length=32,
        ),
    )


def round1_test_engine_config() -> EngineConfig:
    """Test — wall-based ASH (same as F5/H1) + buy-and-hold PEPPER.

    Directional upper-bound reference; additive; never replaces a
    shipped bundle.
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            fair_value_method="wall_mid",
            fair_value_fallbacks=("mid", "microprice"),
            maker_edge=1.5,
            taker_edge=0.5,
            inventory_skew=4.0,
            flatten_threshold=0.7,
            history_length=48,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            strategy_name="buy_and_hold",
            fair_value_method="mid",
            fair_value_fallbacks=(),
            # Bump max_aggressive_size so one tick is enough to fill
            # the full position limit (80). Keeps the remaining
            # session truly "hold".
            max_aggressive_size=80,
        ),
    )


def round1_v2_clean_engine_config() -> EngineConfig:
    """v2_clean stub — delegates to round1_test for import chain."""
    return round1_test_engine_config()


def _round1_ladder_base() -> EngineConfig:
    """Shared base for Phase-J/K ladder variants."""
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            strategy_name="ash_ladder",
            fair_value_method="weighted_mid",
            fair_value_fallbacks=("wall_mid", "mid"),
            maker_edge=2.5,
            taker_edge=0.5,
            flatten_threshold=0.7,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            strategy_name="buy_and_hold",
            fair_value_method="mid",
            fair_value_fallbacks=(),
            max_aggressive_size=80,
        ),
    )


def _round1_pepper_candidate_base(
    pepper_strategy_name: str, *, max_aggressive_size: int = 20, quote_size: int = 5,
) -> EngineConfig:
    """Shared base for the 5 new PEPPER research-strategy uploads.

    Keeps K2's winning ASH ladder unchanged so ASH PnL contribution is
    held constant across the 5 PEPPER candidates.
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            strategy_name="ash_ladder",
            fair_value_method="weighted_mid",
            fair_value_fallbacks=("wall_mid", "mid"),
            maker_edge=2.5,
            taker_edge=0.5,
            flatten_threshold=0.7,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            strategy_name=pepper_strategy_name,
            fair_value_method="linear_drift",
            fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
            max_aggressive_size=max_aggressive_size,
            quote_size=quote_size,
            history_length=32,
        ),
    )


def round1_pepper_passive_maker_engine_config() -> EngineConfig:
    """PEPPER passive-maker: inside-spread maker with asymmetric long bias."""
    return _round1_pepper_candidate_base("pepper_passive_maker")


def round1_pepper_drift_asymmetric_engine_config() -> EngineConfig:
    """PEPPER Fodra-Labadie asymmetric maker with reversal guard."""
    return _round1_pepper_candidate_base("pepper_drift_asymmetric")


def round1_pepper_imbalance_timer_engine_config() -> EngineConfig:
    """PEPPER imbalance-timer: drift carry + OFI-gated adds/trims."""
    return _round1_pepper_candidate_base("pepper_imbalance_timer")


def round1_pepper_flow_overlay_engine_config() -> EngineConfig:
    """PEPPER flow-overlay: drift carry + trade-tape EWMA bias."""
    return _round1_pepper_candidate_base("pepper_flow_overlay")


def round1_pepper_passive_opener_engine_config() -> EngineConfig:
    """PEPPER passive-opener: passive-first opening + drift-maker carry."""
    return _round1_pepper_candidate_base("pepper_passive_opener")


def round1_ash_deep_k1_engine_config() -> EngineConfig:
    """Phase-K K1 — J2_heavier (weights 4/1/1 on 2.5/5/8)."""
    return _round1_ladder_base()


def round1_ash_deep_k2_engine_config() -> EngineConfig:
    """Phase-K K2 — J2_tight (2.5/4/6 with weights 3/1/1)."""
    return _round1_ladder_base()


def round1_ash_deep_k3_engine_config() -> EngineConfig:
    """Phase-K K3 — J2_4lvl (2.5/5/8/12 with weights 3/1/1/1)."""
    return _round1_ladder_base()


def round1_ash_deep_k5_engine_config() -> EngineConfig:
    """Phase-K K5 — J2_asym_flip (buy tight, sell wide)."""
    return _round1_ladder_base()


def round1_ash_deep_l1_engine_config() -> EngineConfig:
    """Phase-L L1 — K2_tighter (2.5/3.5/5)."""
    return _round1_ladder_base()


def round1_ash_deep_l2_engine_config() -> EngineConfig:
    """Phase-L L2 — K2_split (2.5/4.5/7)."""
    return _round1_ladder_base()


def round1_ash_deep_l4_engine_config() -> EngineConfig:
    """Phase-L L4 — K2_4lvl_tight (2.5/4/6/8, weights 3/1/1/1)."""
    return _round1_ladder_base()


def round1_ash_deep_l5_engine_config() -> EngineConfig:
    """Phase-L L5 — K2_bigsize (size_mults 1/3/5)."""
    return _round1_ladder_base()


def round1_ash_deep_l5b_engine_config() -> EngineConfig:
    """Phase-L L5b — K2_midsize (size_mults 1/2/4)."""
    return _round1_ladder_base()


def round1_ash_deep_l6_engine_config() -> EngineConfig:
    """Phase-L L6 — K2_lighter (weights 5/2/2)."""
    return _round1_ladder_base()


def round1_combined_v5micro_l1_engine_config() -> EngineConfig:
    """Combined: v5_micro PEPPER (guarded carry + micro overlay) + L1 ASH ladder (2.5/3.5/5).

    PEPPER leg: pepper_core_long with the v5_micro params (best official
    PEPPER +7,315). Uses the same product config shape as the standalone
    v5_micro bundle.

    ASH leg: ash_ladder (L1 winning config, official +1,786). Uses
    weighted_mid fair value, matching the Phase-J/K/L ladder family.
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            strategy_name="ash_ladder",
            fair_value_method="weighted_mid",
            fair_value_fallbacks=("wall_mid", "mid"),
            maker_edge=2.5,
            taker_edge=0.5,
            flatten_threshold=0.7,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            strategy_name="pepper_core_long",
            fair_value_method="linear_drift",
            fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
            taker_edge=2.0,
            maker_edge=1.0,
            quote_size=10,
            max_aggressive_size=20,
            inventory_skew=2.0,
            flatten_threshold=0.7,
            history_length=32,
        ),
    )


def round1_combined_v6_engine_config() -> EngineConfig:
    """Combined v6: passive-opening PEPPER + L1 ASH ladder (2.5/3.5/5).

    PEPPER leg: pepper_v6_combined with passive opening, core-long
    overlay, inside-spread maker cycling, and drift asymmetry.

    ASH leg: ash_ladder (L1 winning config, official +1,786). Same as
    the v5micro+L1 bundle.
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            strategy_name="ash_ladder",
            fair_value_method="weighted_mid",
            fair_value_fallbacks=("wall_mid", "mid"),
            maker_edge=2.5,
            taker_edge=0.5,
            flatten_threshold=0.7,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            strategy_name="pepper_v6_combined",
            fair_value_method="linear_drift",
            fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
            taker_edge=2.0,
            maker_edge=1.0,
            quote_size=10,
            max_aggressive_size=20,
            inventory_skew=2.0,
            flatten_threshold=0.7,
            history_length=32,
        ),
    )


def round1_alt_engine_config() -> EngineConfig:
    """Phase-6 higher-upside alternate. See
    ``outputs/round_1/notes/phase5_review_shortlist.md``.
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            fair_value_method="wall_mid",
            fair_value_fallbacks=("mid", "microprice"),
            maker_edge=1.5,
            taker_edge=0.5,
            inventory_skew=4.0,
            flatten_threshold=0.7,
            history_length=48,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            fair_value_method="linear_drift",
            fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
            maker_edge=1.0,
            taker_edge=2.0,
            inventory_skew=1.0,
            flatten_threshold=0.9,
            history_length=32,
        ),
    )


def round2_v5micro_wide113_engine_config() -> EngineConfig:
    """Round-2 promoted: v5_micro PEPPER + wide-w113 ASH ladder.

    Identical to ``round1_combined_v5micro_l1_engine_config`` on the
    PEPPER leg (the deterministic +80k/day annuity validated in batch
    C). The ASH leg is the **batch-D1 sweep winner** — wider edges
    with outer-heavy weights, which beat the R1 L1 ladder by +20%
    (+1 938 XIRECs) on the R2 tape.

    PEPPER leg: pepper_core_long with v5_micro CoreLongParams (open
    seed=65, window=500, exec_style=taker, guard_window=32, etc.).
    Kill switches DISABLED — batch D2 confirmed the strategy's own
    guard machinery already covers tail protection on this stack.

    ASH leg: ash_ladder with edges (3.0, 5.0, 8.0), size_mults
    (1.0, 2.0, 3.0), weights (1, 1, 3), skew_coef=1.0, flatten=0.7.
    See ``outputs/round_2/ash_sweep.md`` for the sweep evidence.

    Both `strategy_name` values reference research-only strategies
    that are not in the live STRATEGY_REGISTRY; the export bundler
    inlines them and registers them at bundle tail. Calling this
    factory directly outside the bundler will raise — the bundler
    temporarily whitelists the names during construction.

    `bid_value` defaults to 0; the export script's `--bid` flag
    wraps the factory call with `with_bid_value(...)` to embed the
    Round-2 MAF auction bid (recommended 2 300 per batch D3).
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            strategy_name="ash_ladder",
            fair_value_method="weighted_mid",
            fair_value_fallbacks=("wall_mid", "mid"),
            maker_edge=2.5,  # outer ladder edge in wide config
            taker_edge=0.5,
            flatten_threshold=0.7,
            flush_history_on_day_rollover=False,
        ),
        INTARIAN_PEPPER_ROOT=dict(
            strategy_name="pepper_core_long",
            fair_value_method="linear_drift",
            fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
            taker_edge=2.0,
            maker_edge=1.0,
            quote_size=10,
            max_aggressive_size=20,
            inventory_skew=2.0,
            flatten_threshold=0.7,
            history_length=32,
            # Day-rollover flush is a no-op on this stack (batch C
            # showed open_seed_size hack already handles rollover) but
            # we leave the flag enabled for hygiene — costs zero.
            flush_history_on_day_rollover=True,
        ),
    )
