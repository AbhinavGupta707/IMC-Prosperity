"""Engine configuration: core types + R1/R2 product factories.

``ProductConfig``, ``EngineConfig`` and the ``with_bid_value`` helper
have been moved to ``src/core/config_core.py`` so the R3 submission
bundle can ship just the types without carrying the legacy R1/R2
product factories. This module re-exports them for backward
compatibility and adds the R1/R2 product factories (``default_engine_config``,
``round1_*``, ``round2_*``) used by the tutorial / Round-1 / Round-2
export pipelines and the corresponding test suites.

Fair value resolution:

- ``fair_value_method`` names the primary estimator.
- ``fair_value_fallbacks`` is an ordered tuple of estimator names that
  will be tried in turn if the primary returns ``None`` (missing data,
  insufficient history, etc.). The doctrine requires a fallback path to
  always exist; this is where it lives.
"""

from __future__ import annotations

# Re-export core symbols for backward compatibility. Every existing
# import of ``ProductConfig`` / ``EngineConfig`` from this module
# continues to resolve.
import src.core.config_core as _core
from src.core.config_core import (
    KNOWN_ESTIMATOR_NAMES,
    KNOWN_STRATEGY_NAMES,
    EngineConfig,
    ProductConfig,
    with_bid_value,
)


def extend_known_strategy_names(extra: tuple[str, ...]) -> tuple[str, ...]:
    """Grow both this module's and ``config_core``'s whitelists in lockstep.

    The R1 bundlers temporarily add research-only strategy names to
    ``KNOWN_STRATEGY_NAMES`` before calling a factory so validation
    accepts them. ``ProductConfig.__post_init__`` lives in
    ``config_core`` and reads the whitelist from there, so patching
    only this module's copy has no effect. This helper keeps both
    module-level names pointing at the same tuple. Returns the previous
    ``KNOWN_STRATEGY_NAMES`` tuple for restore.
    """
    global KNOWN_STRATEGY_NAMES
    previous = KNOWN_STRATEGY_NAMES
    new_value = tuple(sorted(set(previous) | set(extra)))
    KNOWN_STRATEGY_NAMES = new_value
    _core.KNOWN_STRATEGY_NAMES = new_value
    return previous


def restore_known_strategy_names(previous: tuple[str, ...]) -> None:
    """Undo ``extend_known_strategy_names``."""
    global KNOWN_STRATEGY_NAMES
    KNOWN_STRATEGY_NAMES = previous
    _core.KNOWN_STRATEGY_NAMES = previous

__all__ = [
    "KNOWN_ESTIMATOR_NAMES",
    "KNOWN_STRATEGY_NAMES",
    "EngineConfig",
    "ProductConfig",
    "extend_known_strategy_names",
    "restore_known_strategy_names",
    "ROUND1_PRODUCTS",
    "default_engine_config",
    "round1_alt_engine_config",
    "round1_ash_deep_k1_engine_config",
    "round1_ash_deep_k2_engine_config",
    "round1_ash_deep_k3_engine_config",
    "round1_ash_deep_k5_engine_config",
    "round1_ash_deep_l1_engine_config",
    "round1_ash_deep_l2_engine_config",
    "round1_ash_deep_l4_engine_config",
    "round1_ash_deep_l5_engine_config",
    "round1_ash_deep_l5b_engine_config",
    "round1_ash_deep_l6_engine_config",
    "round1_baseline_engine_config",
    "round1_combined_v5micro_l1_engine_config",
    "round1_combined_v6_engine_config",
    "round1_engine_config",
    "round1_f5_engine_config",
    "round1_h1_engine_config",
    "round1_pepper_drift_asymmetric_engine_config",
    "round1_pepper_flow_overlay_engine_config",
    "round1_pepper_imbalance_timer_engine_config",
    "round1_pepper_passive_maker_engine_config",
    "round1_pepper_passive_opener_engine_config",
    "round1_promoted_engine_config",
    "round1_test_engine_config",
    "round1_v2_clean_engine_config",
    "round2_v5micro_wide113_engine_config",
    "with_bid_value",
]


def default_engine_config() -> EngineConfig:
    # Tutorial products (EMERALDS, TOMATOES) plus Round-1 products
    # (ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT). All share the
    # market-making strategy and differ only by configuration.
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
            "ASH_COATED_OSMIUM": ProductConfig(
                position_limit=80,
                strategy_name="market_making",
                fair_value_method="wall_mid",
                fair_value_fallbacks=("mid", "microprice"),
                anchor_price=10_000.0,
                taker_edge=1.0,
                maker_edge=1.0,
                quote_size=5,
                max_aggressive_size=10,
                inventory_skew=4.0,
                flatten_threshold=0.7,
                history_length=48,
            ),
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
    """Engine config containing **only** the Round-1 products."""
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
    """Phase-6 promoted / robust default."""
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
    """Phase-8.5 hybrid H1 — promoted PEPPER + alt wall_mid ASH."""
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
    """Phase-9 fastsearch F5 candidate — asymmetric-taker PEPPER + alt ASH."""
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
    """Test — wall-based ASH (same as F5/H1) + buy-and-hold PEPPER."""
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
    """Shared base for the 5 new PEPPER research-strategy uploads."""
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
    """Combined: v5_micro PEPPER + L1 ASH ladder."""
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
    """Combined v6: passive-opening PEPPER + L1 ASH ladder."""
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
    """Phase-6 higher-upside alternate."""
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

    See ``outputs/round_2/ash_sweep.md``. The shipped bundle inlines
    ``AshLadderStrategy`` / ``PepperCoreLongStrategy`` and registers
    them at bundle tail. The ProductConfig knobs here are stubs that
    satisfy validation and mirror the actual strategy params so direct
    construction does not silently disagree with the shipped bundle.
    """
    return _round1_engine_with(
        ASH_COATED_OSMIUM=dict(
            strategy_name="ash_ladder",
            fair_value_method="weighted_mid",
            fair_value_fallbacks=("wall_mid", "mid"),
            maker_edge=3.0,
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
            flush_history_on_day_rollover=True,
        ),
    )
