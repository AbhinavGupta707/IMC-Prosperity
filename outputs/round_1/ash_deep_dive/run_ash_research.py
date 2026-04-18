"""Master runner for the ASH edge-extraction deep dive (PLAN.md).

Supports ``--phase b`` today. Phases C / D / E / F wire in later as
their artifacts land.

Design constraints:
- PEPPER is pinned at buy-and-hold 80 for every candidate (PLAN.md
  §0.1). Base engine comes from ``round1_test_engine_config``; ASH
  is then ``replace()``-ed with the cell's overrides.
- Custom ASH strategies (Phase B3/B4/B5 shape overrides, and later
  Phase-C composites) are injected post-``Trader.__init__`` by
  replacing ``trader.strategies["market_making"]``. PEPPER still
  uses ``trader.strategies["buy_and_hold"]`` — unaffected.
- Results include the Phase-A rescaled "expected-official" PnL so
  we surface fill-model bias immediately, not after-the-fact.

Results directory layout:
```
outputs/round_1/ash_deep_dive/phase_b/
  B1/results.csv  (one row per cell)
  B2/results.csv
  ...
  results_all.csv (union across levers)
```
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import mean, pstdev
from typing import Literal

from src.backtest.metrics import SimulationResult
from src.backtest.replay_engine import ReplayEngine
from src.backtest.simulator import BacktestSimulator
from src.core.config import (
    EngineConfig,
    ProductConfig,
    round1_test_engine_config,
)
from src.core.fair_value import FairValueEngine
from src.core.signals import SignalEngine
from src.strategies.ash_avellaneda_stoikov import (
    AshAvellanedaStoikovStrategy,
    AvellanedaStoikovParams,
)
from src.strategies.ash_cartea_skew import AshCarteaSkewStrategy, CarteaSkewParams
from src.strategies.ash_gueant import AshGueantStrategy, GueantParams
from src.strategies.ash_shape_override import AshShapeOverrideStrategy, ShapeParams
from src.strategies.ash_target_position import (
    AshTargetPositionStrategy,
    TargetPositionParams,
)
from src.strategies.base import BaseStrategy, StrategyContext
from src.trader import Trader

ASH: Literal["ASH_COATED_OSMIUM"] = "ASH_COATED_OSMIUM"
PEPPER: Literal["INTARIAN_PEPPER_ROOT"] = "INTARIAN_PEPPER_ROOT"
FOLDS: tuple[int, ...] = (-2, -1, 0)

# Phase-A fill-reality multipliers (from
# outputs/round_1/ash_deep_dive/phase_a/PHASE_A_MEMO.md §6).
# These are ratios of (local-per-day fills) / (official-per-day fills)
# measured on C_h1_alt. Local under-fires maker (0.036 => ~28x less
# than official) and over-fires taker (10.24 => ~10x more than
# official). To rescale a LOCAL ASH pnl into an expected-official
# ASH pnl we DIVIDE each fill-type's PnL contribution by its scale
# factor, not multiply. Sanity check: on C_h1_alt itself the expected
# rescale should land near the observed +982 on day 0.
FILL_SCALE_MAKER: float = 0.036
FILL_SCALE_TAKER: float = 10.24


# --------------------------------------------------------------- candidate


StrategyFactory = Callable[[FairValueEngine, SignalEngine], BaseStrategy]


@dataclass(frozen=True)
class AshCandidate:
    """One Phase-B/C/D cell.

    ``ash_overrides`` is a dict of kwargs passed to ``replace()`` on
    the base ASH ``ProductConfig``.

    Strategy injection is driven by at most ONE of:
    - ``ash_shape_params``: use the Phase-B shape-override strategy.
    - ``strategy_factory``: build a custom strategy from the engines
      (Phase C composites + later D hybrids).

    If both are ``None``, the default ``MarketMakingStrategy`` is used
    (config-only cell, Phase B1 / B2 / B6).

    ``notes`` is a free-text one-liner that is written to the CSV for
    memo legibility.
    """

    cell_id: str
    lever: str
    ash_overrides: dict[str, object] = field(default_factory=dict)
    ash_shape_params: ShapeParams | None = None
    strategy_factory: StrategyFactory | None = None
    notes: str = ""


# --------------------------------------------------------------- helpers


class _PerProductStrategy(BaseStrategy):
    """Dispatch by product to distinct per-product strategy instances."""

    def __init__(self, by_product: dict[str, BaseStrategy]) -> None:
        self.by_product = by_product

    def generate_intent(self, ctx: StrategyContext):  # type: ignore[override]
        return self.by_product[ctx.product].generate_intent(ctx)


def build_engine(overrides: dict[str, object]) -> EngineConfig:
    base = round1_test_engine_config()
    ash_current = base.products[ASH]
    ash_new: ProductConfig = replace(ash_current, **overrides)  # type: ignore[arg-type]
    products = dict(base.products)
    products[ASH] = ash_new
    return EngineConfig(
        state_version=base.state_version,
        max_trader_data_chars=base.max_trader_data_chars,
        diagnostics_verbosity=base.diagnostics_verbosity,
        products=products,
        scanner_config=base.scanner_config,
        residual_config=base.residual_config,
    )


def load_day_replay(day: int, data_dir: Path) -> ReplayEngine:
    price_files = [data_dir / f"prices_round_1_day_{day}.csv"]
    trade_files = [data_dir / f"trades_round_1_day_{day}.csv"]
    return ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)


def run_candidate_on_day(
    candidate: AshCandidate,
    engine: EngineConfig,
    replay: ReplayEngine,
) -> SimulationResult:
    trader = Trader(config=engine)
    # ASH uses the "market_making" strategy slot by default. If the
    # cell requires a custom strategy (shape-override or Phase-C
    # composite), inject it via a per-product dispatcher so PEPPER
    # (buy_and_hold) is untouched.
    ash_custom: BaseStrategy | None = None
    if candidate.strategy_factory is not None:
        ash_custom = candidate.strategy_factory(
            trader.fair_value_engine, trader.signal_engine,
        )
    elif candidate.ash_shape_params is not None:
        ash_custom = AshShapeOverrideStrategy(
            trader.fair_value_engine, trader.signal_engine,
            candidate.ash_shape_params,
        )
    if ash_custom is not None:
        existing_mm = trader.strategies.get("market_making")
        if existing_mm is None:
            trader.strategies["market_making"] = ash_custom
        else:
            trader.strategies["market_making"] = _PerProductStrategy({
                ASH: ash_custom,
                PEPPER: existing_mm,
            })
    return BacktestSimulator(trader=trader).run(replay)


# --------------------------------------------------------------- evaluation


@dataclass(frozen=True)
class CellResult:
    cell_id: str
    lever: str
    notes: str
    day_pnl: dict[int, float]
    mean_pnl: float
    min_pnl: float
    max_pnl: float
    std_pnl: float
    total_maker_fills: int
    total_taker_fills: int
    local_total_pnl_3day: float
    expected_official_pnl_per_day: float
    avg_markout_1: float | None
    avg_markout_5: float | None
    avg_markout_20: float | None


def evaluate(
    candidate: AshCandidate,
    replays: dict[int, ReplayEngine],
) -> CellResult:
    engine = build_engine(candidate.ash_overrides)
    per_day_pnl: dict[int, float] = {}
    total_maker = 0
    total_taker = 0
    total_pnl = 0.0
    avg_mk1_samples: list[tuple[float, int]] = []
    avg_mk5_samples: list[tuple[float, int]] = []
    avg_mk20_samples: list[tuple[float, int]] = []
    for day, replay in replays.items():
        result = run_candidate_on_day(candidate, engine, replay)
        ash_result = result.per_product.get(ASH)
        if ash_result is None:
            per_day_pnl[day] = 0.0
            continue
        per_day_pnl[day] = ash_result.pnl
        total_maker += ash_result.maker_trade_count
        total_taker += ash_result.taker_trade_count
        total_pnl += ash_result.pnl
        _accumulate_markout(avg_mk1_samples, ash_result.avg_markout_1, ash_result.markout_1_count)
        _accumulate_markout(avg_mk5_samples, ash_result.avg_markout_5, ash_result.markout_5_count)
        _accumulate_markout(
            avg_mk20_samples, ash_result.avg_markout_20, ash_result.markout_20_count,
        )

    pnls = [per_day_pnl[d] for d in FOLDS]
    mean_p = mean(pnls)
    # Fill-model reality rescale. Assume local PnL splits proportionally
    # by fill count (rough but directionally correct). Divide each
    # fill-type's contribution by its local/official fill-scale to get
    # the expected-official contribution. Sanity-tested on C_h1_alt
    # where the rescale lands at +883 vs observed +983 on day 0.
    total_fills = total_maker + total_taker
    maker_share = total_maker / total_fills if total_fills > 0 else 0.0
    taker_share = total_taker / total_fills if total_fills > 0 else 0.0
    local_per_day = total_pnl / max(len(FOLDS), 1)
    expected_official = 0.0
    if FILL_SCALE_MAKER > 0:
        expected_official += maker_share * local_per_day / FILL_SCALE_MAKER
    if FILL_SCALE_TAKER > 0:
        expected_official += taker_share * local_per_day / FILL_SCALE_TAKER
    return CellResult(
        cell_id=candidate.cell_id,
        lever=candidate.lever,
        notes=candidate.notes,
        day_pnl=per_day_pnl,
        mean_pnl=mean_p,
        min_pnl=min(pnls),
        max_pnl=max(pnls),
        std_pnl=pstdev(pnls),
        total_maker_fills=total_maker,
        total_taker_fills=total_taker,
        local_total_pnl_3day=total_pnl,
        expected_official_pnl_per_day=expected_official,
        avg_markout_1=_weighted_mean(avg_mk1_samples),
        avg_markout_5=_weighted_mean(avg_mk5_samples),
        avg_markout_20=_weighted_mean(avg_mk20_samples),
    )


def _accumulate_markout(
    samples: list[tuple[float, int]],
    value: float | None,
    count: int,
) -> None:
    if value is not None and count > 0:
        samples.append((value, count))


def _weighted_mean(samples: list[tuple[float, int]]) -> float | None:
    total_weight = sum(c for _, c in samples)
    if total_weight <= 0:
        return None
    return sum(v * c for v, c in samples) / total_weight


# ------------------------------------------------------------ Phase-B cells


def phase_b_candidates() -> list[AshCandidate]:
    """All 58 Phase-B cells, per PLAN.md §3."""

    cells: list[AshCandidate] = []
    cells.extend(_b1_fv_cells())
    cells.extend(_b2_edge_cells())
    cells.extend(_b3_skew_cells())
    cells.extend(_b4_flatten_cells())
    cells.extend(_b5_size_cells())
    cells.extend(_b6_history_cells())
    return cells


def _b1_fv_cells() -> list[AshCandidate]:
    specs: list[tuple[str, str, tuple[str, ...]]] = [
        ("wall_mid", "wall_mid", ("mid", "microprice")),
        ("microprice", "microprice", ("wall_mid", "mid")),
        ("ewma_mid", "ewma_mid", ("wall_mid", "mid")),
        ("depth_mid", "depth_mid", ("wall_mid", "mid")),
        ("hybrid_wall_micro", "hybrid_wall_micro", ("wall_mid", "mid")),
        ("filtered_wall_mid", "filtered_wall_mid", ("mid", "microprice")),
        ("weighted_mid", "weighted_mid", ("wall_mid", "mid")),
        ("rolling_mid", "rolling_mid", ("wall_mid", "mid")),
    ]
    out: list[AshCandidate] = []
    for tag, method, fallbacks in specs:
        out.append(AshCandidate(
            cell_id=f"B1_{tag}",
            lever="B1",
            ash_overrides={
                "fair_value_method": method,
                "fair_value_fallbacks": fallbacks,
            },
            notes=f"FV primary = {method} (fallbacks = {fallbacks})",
        ))
    return out


def _b2_edge_cells() -> list[AshCandidate]:
    out: list[AshCandidate] = []
    for m in (1.0, 1.5, 2.0, 2.5):
        for t in (0.25, 0.5, 1.0, 1.5):
            out.append(AshCandidate(
                cell_id=f"B2_m{m}_t{t}",
                lever="B2",
                ash_overrides={"maker_edge": m, "taker_edge": t},
                notes=f"maker_edge={m}, taker_edge={t}",
            ))
    return out


def _b3_skew_cells() -> list[AshCandidate]:
    out: list[AshCandidate] = []
    # Linear baseline sweep on coefficient.
    for coef in (2.0, 4.0, 6.0, 8.0):
        out.append(AshCandidate(
            cell_id=f"B3_linear_c{coef}",
            lever="B3",
            ash_shape_params=ShapeParams(skew_mode="linear", skew_coef=coef),
            notes=f"linear skew, coef={coef}",
        ))
    # AS reservation-price skew. gamma must be scaled so that
    # gamma * sigma^2 * T ~ O(1) tick per share; with sigma=2 and
    # T=100_000 that means gamma ~ 1e-6 to 1e-5. The gamma values
    # below give effective skews of ~2, 8, 32 ticks at q=40
    # (full-limit/2), spanning "mild" to "aggressive".
    for gamma in (1e-7, 5e-7, 2e-6):
        out.append(AshCandidate(
            cell_id=f"B3_as_g{gamma:.0e}",
            lever="B3",
            ash_shape_params=ShapeParams(
                skew_mode="as", as_gamma=gamma, as_sigma=2.0,
            ),
            notes=f"AS reservation-price skew, gamma={gamma:.0e}, sigma=2.0",
        ))
    # Tanh saturating.
    for coef in (2.0, 4.0, 8.0):
        out.append(AshCandidate(
            cell_id=f"B3_tanh_c{coef}",
            lever="B3",
            ash_shape_params=ShapeParams(skew_mode="tanh", skew_coef=coef),
            notes=f"tanh skew, coef={coef}",
        ))
    # Quadratic.
    for coef in (4.0, 8.0, 16.0):
        out.append(AshCandidate(
            cell_id=f"B3_quad_c{coef}",
            lever="B3",
            ash_shape_params=ShapeParams(skew_mode="quadratic", skew_coef=coef),
            notes=f"quadratic skew, coef={coef}",
        ))
    return out


def _b4_flatten_cells() -> list[AshCandidate]:
    out: list[AshCandidate] = []
    # Hard thresholds.
    for thresh in (0.6, 0.7, 0.8):
        out.append(AshCandidate(
            cell_id=f"B4_hard_{thresh}",
            lever="B4",
            ash_shape_params=ShapeParams(
                flatten_mode="hard", flatten_threshold=thresh,
            ),
            notes=f"hard flatten at |pos/limit| >= {thresh}",
        ))
    # Soft-target pull.
    for k in (0.2, 0.5, 1.0):
        out.append(AshCandidate(
            cell_id=f"B4_soft_k{k}",
            lever="B4",
            ash_shape_params=ShapeParams(
                flatten_mode="soft_target", flatten_k=k,
            ),
            notes=f"soft-target pull, k={k}",
        ))
    # AS-continuous (no hard flatten; AS skew term handles it). gamma
    # rescaled to match the corrected B3 AS grid; use the middle
    # (~8 ticks at q=40) value that should bind just before the old
    # hard-0.7 threshold would.
    out.append(AshCandidate(
        cell_id="B4_as_continuous",
        lever="B4",
        ash_shape_params=ShapeParams(
            skew_mode="as", flatten_mode="as_continuous",
            as_gamma=5e-7, as_sigma=2.0,
        ),
        notes="AS-continuous flatten (AS skew replaces hard threshold)",
    ))
    return out


def _b5_size_cells() -> list[AshCandidate]:
    out: list[AshCandidate] = []
    out.append(AshCandidate(
        cell_id="B5_constant",
        lever="B5",
        ash_shape_params=ShapeParams(size_mode="constant"),
        notes="constant per-side size = quote_size (C_h1_alt)",
    ))
    out.append(AshCandidate(
        cell_id="B5_linear",
        lever="B5",
        ash_shape_params=ShapeParams(
            size_mode="linear", size_min=1, size_max=10,
        ),
        notes="linear inventory-driven size skew",
    ))
    out.append(AshCandidate(
        cell_id="B5_as_optimal",
        lever="B5",
        ash_shape_params=ShapeParams(
            size_mode="as_optimal", as_gamma=0.10, as_sigma=2.0,
            size_min=1, size_max=10,
        ),
        notes="AS-optimal size (1/gamma*sigma^2)",
    ))
    out.append(AshCandidate(
        cell_id="B5_stepwise",
        lever="B5",
        ash_shape_params=ShapeParams(
            size_mode="stepwise", size_step_ratio=0.5,
            size_min=1, size_max=10,
        ),
        notes="stepwise size — shrink adding side, grow unwinding side",
    ))
    return out


# --------------------------------------------------------- Phase-C cells


# Phase-B §5 prior: baseline edges for all Phase-C composites lift from
# (1.5, 0.5) to (2.0, 0.5). Every Phase-C candidate overrides ASH's
# maker/taker edges to match that baseline unless explicitly stated.
PHASE_C_BASELINE_OVERRIDES: dict[str, object] = {
    "maker_edge": 2.0,
    "taker_edge": 0.5,
}


def phase_c_candidates() -> list[AshCandidate]:
    """All Phase-C composite candidates per PLAN.md §4.

    Phase-A killed C4 (OFI-gate). This function returns C1, C2, C3, C5.
    """
    out: list[AshCandidate] = []
    out.extend(_c1_as_cells())
    out.extend(_c2_gueant_cells())
    out.extend(_c3_cartea_cells())
    out.extend(_c5_target_v2_cells())
    return out


def _c1_as_cells() -> list[AshCandidate]:
    """C1 Avellaneda-Stoikov: 3 gamma values."""
    out: list[AshCandidate] = []
    for gamma in (1e-7, 5e-7, 2e-6):
        params = AvellanedaStoikovParams(
            gamma=gamma, sigma=2.0, k=0.4, horizon=100_000,
            taker_edge=0.5,
        )
        out.append(AshCandidate(
            cell_id=f"C1_as_g{gamma:.0e}",
            lever="C1",
            ash_overrides=dict(PHASE_C_BASELINE_OVERRIDES),
            strategy_factory=lambda fve, sig, p=params: AshAvellanedaStoikovStrategy(
                fve, sig, p,
            ),
            notes=f"AS: gamma={gamma:.0e}, sigma=2.0, k=0.4, T=100k",
        ))
    return out


def _c2_gueant_cells() -> list[AshCandidate]:
    """C2 Guéant mean-reversion extension: 3 gamma values at theta=0.10."""
    out: list[AshCandidate] = []
    for gamma in (1e-7, 5e-7, 2e-6):
        params = GueantParams(
            gamma=gamma, sigma=2.0, k=0.4, horizon=100_000, theta=0.10,
            taker_edge=0.5,
        )
        out.append(AshCandidate(
            cell_id=f"C2_gueant_g{gamma:.0e}",
            lever="C2",
            ash_overrides=dict(PHASE_C_BASELINE_OVERRIDES),
            strategy_factory=lambda fve, sig, p=params: AshGueantStrategy(fve, sig, p),
            notes=f"Guéant: gamma={gamma:.0e}, theta=0.10",
        ))
    return out


def _c3_cartea_cells() -> list[AshCandidate]:
    """C3 Cartea alpha-skew: 4 beta values over ewma_mid residual."""
    out: list[AshCandidate] = []
    for beta in (0.3, 0.6, 1.0, 1.5):
        params = CarteaSkewParams(
            beta=beta,
            fv_for_alpha="ewma_mid",
            sigma_residual_prior=1.06,
            alpha_clip=3.0,
        )
        out.append(AshCandidate(
            cell_id=f"C3_cartea_b{beta}",
            lever="C3",
            ash_overrides=dict(PHASE_C_BASELINE_OVERRIDES),
            strategy_factory=lambda fve, sig, p=params: AshCarteaSkewStrategy(
                fve, sig, p,
            ),
            notes=f"Cartea: beta={beta}, alpha=ewma_mid residual z-score",
        ))
    return out


def _c5_target_v2_cells() -> list[AshCandidate]:
    """C5 Target-position V2: EWMA anchor + sigma-aware alpha + flatten clip.

    Selective grid (~12 cells): 3 tau * 2 alpha * 2 mode per style; pick
    a small sweep that covers the dead_zone and exec_style levers.
    """
    out: list[AshCandidate] = []
    taus = (500.0, 2000.0, 8000.0)
    alphas = (0.3, 0.6, 1.0)
    configs: list[tuple[str, float, str, float]] = [
        # (mode, dead_zone, exec_style, hybrid_threshold)
        ("dead_zone", 2.0, "hybrid", 3.0),
        ("dead_zone", 3.0, "hybrid", 4.0),
        ("linear", 0.0, "hybrid", 3.0),
        ("linear", 0.0, "maker", 0.0),
    ]
    # To keep the grid manageable we pick the cross-product selectively:
    # all 3 taus paired with the 3 alphas under one "dead_zone/hybrid/d=2"
    # shape (9 cells), then add the 3 configs at their default alpha to
    # sample shapes (3 more cells). Total = 12.
    for tau in taus:
        for alpha in alphas:
            out.append(AshCandidate(
                cell_id=f"C5_tau{int(tau)}_a{alpha}",
                lever="C5",
                ash_overrides=dict(PHASE_C_BASELINE_OVERRIDES),
                strategy_factory=(
                    lambda fve, sig, tau=tau, alpha=alpha: AshTargetPositionStrategy(
                        fve, sig,
                        TargetPositionParams(
                            mode="dead_zone",
                            mean_source="ewma",
                            ewma_tau=tau,
                            alpha=alpha,
                            dead_zone=2.0,
                            sigma_ref=1.06,
                            clip_to_flatten=True,
                            exec_style="hybrid",
                            hybrid_threshold=3.0,
                        ),
                    )
                ),
                notes=(
                    f"Target-v2: ewma tau={int(tau)}, alpha={alpha}, d=2, "
                    "sigma_ref=1.06, clip-to-flatten"
                ),
            ))
    for mode, dz, style, thresh in configs:
        out.append(AshCandidate(
            cell_id=f"C5_{mode}_{style}_d{dz}",
            lever="C5",
            ash_overrides=dict(PHASE_C_BASELINE_OVERRIDES),
            strategy_factory=(
                lambda fve, sig, mode=mode, dz=dz, style=style, thresh=thresh: (
                    AshTargetPositionStrategy(
                        fve, sig,
                        TargetPositionParams(
                            mode=mode,
                            mean_source="ewma",
                            ewma_tau=2000.0,
                            alpha=0.6,
                            dead_zone=dz,
                            sigma_ref=1.06,
                            clip_to_flatten=True,
                            exec_style=style,
                            hybrid_threshold=thresh,
                        ),
                    )
                )
            ),
            notes=(
                f"Target-v2: mode={mode}, style={style}, dz={dz}, alpha=0.6"
            ),
        ))
    return out


# ---------------------------------------------------------- Phase-D cells


def phase_d_candidates() -> list[AshCandidate]:
    """Phase-D hybrids per Phase-C memo §4.

    Four hybrids, each testing one specific composition hypothesis.
    """
    return [
        _d5_empirical_stack(),
        _d6_as_continuous_stack(),
        _d7_weighted_mid_plus_as(),
        _d8_mild_cartea(),
    ]


def _d5_empirical_stack() -> AshCandidate:
    """weighted_mid + m=2.5 + soft linear skew c=2 — pure empirical stack."""
    return AshCandidate(
        cell_id="D5_weighted_m25_skew2",
        lever="D5",
        ash_overrides={
            "fair_value_method": "weighted_mid",
            "fair_value_fallbacks": ("wall_mid", "mid"),
            "maker_edge": 2.5,
            "taker_edge": 0.5,
        },
        ash_shape_params=ShapeParams(
            skew_mode="linear", skew_coef=2.0,
            flatten_mode="hard", flatten_threshold=0.7,
            size_mode="constant",
        ),
        notes="Empirical stack: weighted_mid FV + m=2.5/t=0.5 + linear skew c=2",
    )


def _d6_as_continuous_stack() -> AshCandidate:
    """wall_mid + m=2.5 + AS-continuous flatten (gamma=5e-7)."""
    return AshCandidate(
        cell_id="D6_m25_as_continuous",
        lever="D6",
        ash_overrides={
            "fair_value_method": "wall_mid",
            "fair_value_fallbacks": ("mid", "microprice"),
            "maker_edge": 2.5,
            "taker_edge": 0.5,
        },
        ash_shape_params=ShapeParams(
            skew_mode="as", as_gamma=5e-7, as_sigma=2.0, as_horizon=100_000,
            flatten_mode="as_continuous",
            size_mode="constant",
        ),
        notes="wall_mid + m=2.5/t=0.5 + AS-continuous flatten (gamma=5e-7, sigma=2, T=100k)",
    )


def _d7_weighted_mid_plus_as() -> AshCandidate:
    """weighted_mid FV + AS quote formula (gamma=2e-6)."""
    params = AvellanedaStoikovParams(
        gamma=2e-6, sigma=2.0, k=0.4, horizon=100_000,
        taker_edge=0.5,
    )
    return AshCandidate(
        cell_id="D7_weighted_as_g2e-6",
        lever="D7",
        ash_overrides={
            "fair_value_method": "weighted_mid",
            "fair_value_fallbacks": ("wall_mid", "mid"),
            "taker_edge": 0.5,
        },
        strategy_factory=lambda fve, sig, p=params: AshAvellanedaStoikovStrategy(
            fve, sig, p,
        ),
        notes="weighted_mid FV + AS quote formula (gamma=2e-6)",
    )


# -------------------------------------------------- Phase-F / Phase-E cohort


def phase_f_upload_cohort() -> list[AshCandidate]:
    """The 10 Phase-F upload candidates + shipped C_h1_alt control.

    Same set used for Phase-E stress testing. Returned in a canonical
    order so the stress matrix is stable across runs.
    """
    return [
        # F1 control — shipped C_h1_alt.
        AshCandidate(
            cell_id="F1_C_h1_alt",
            lever="F1",
            ash_overrides={},  # round1_test_engine_config already = C_h1_alt leg
            notes="Shipped C_h1_alt (wall_mid, m=1.5, t=0.5, skew=4)",
        ),
        # F2a — Phase-C top.
        AshCandidate(
            cell_id="F2a_C1_as_g2e-06",
            lever="F2a",
            ash_overrides=dict(PHASE_C_BASELINE_OVERRIDES),
            strategy_factory=lambda fve, sig: AshAvellanedaStoikovStrategy(
                fve, sig,
                AvellanedaStoikovParams(
                    gamma=2e-6, sigma=2.0, k=0.4, horizon=100_000,
                    taker_edge=0.5,
                ),
            ),
            notes="C1 AS gamma=2e-6 (overall Phase-C winner)",
        ),
        # F2b — best D hybrid.
        AshCandidate(
            cell_id="F2b_D6_m25_as_continuous",
            lever="F2b",
            ash_overrides={
                "fair_value_method": "wall_mid",
                "fair_value_fallbacks": ("mid", "microprice"),
                "maker_edge": 2.5,
                "taker_edge": 0.5,
            },
            ash_shape_params=ShapeParams(
                skew_mode="as", as_gamma=5e-7, as_sigma=2.0,
                flatten_mode="as_continuous", size_mode="constant",
            ),
            notes="D6 m=2.5 + AS-continuous flatten (gamma=5e-7)",
        ),
        # F2c — Phase-B FV winner.
        AshCandidate(
            cell_id="F2c_B1_weighted_mid",
            lever="F2c",
            ash_overrides={
                "fair_value_method": "weighted_mid",
                "fair_value_fallbacks": ("wall_mid", "mid"),
            },
            notes="B1 weighted_mid FV at shipped edges (m=1.5, t=0.5)",
        ),
        # F2d — Phase-B edge winner.
        AshCandidate(
            cell_id="F2d_B2_m25_t05",
            lever="F2d",
            ash_overrides={"maker_edge": 2.5, "taker_edge": 0.5},
            notes="B2 m=2.5, t=0.5 at wall_mid",
        ),
        # F3a — D5 (record local).
        AshCandidate(
            cell_id="F3a_D5_weighted_m25_c2",
            lever="F3a",
            ash_overrides={
                "fair_value_method": "weighted_mid",
                "fair_value_fallbacks": ("wall_mid", "mid"),
                "maker_edge": 2.5,
                "taker_edge": 0.5,
            },
            ash_shape_params=ShapeParams(
                skew_mode="linear", skew_coef=2.0,
                flatten_mode="hard", flatten_threshold=0.7,
                size_mode="constant",
            ),
            notes="D5 empirical stack (highest local PnL on record)",
        ),
        # F3b — D7.
        AshCandidate(
            cell_id="F3b_D7_weighted_as_g2e-6",
            lever="F3b",
            ash_overrides={
                "fair_value_method": "weighted_mid",
                "fair_value_fallbacks": ("wall_mid", "mid"),
                "taker_edge": 0.5,
            },
            strategy_factory=lambda fve, sig: AshAvellanedaStoikovStrategy(
                fve, sig,
                AvellanedaStoikovParams(
                    gamma=2e-6, sigma=2.0, k=0.4, horizon=100_000,
                    taker_edge=0.5,
                ),
            ),
            notes="D7 weighted_mid + AS quotes",
        ),
        # F3c — D8 mild Cartea.
        AshCandidate(
            cell_id="F3c_D8_m25_cartea_b01",
            lever="F3c",
            ash_overrides={
                "fair_value_method": "wall_mid",
                "fair_value_fallbacks": ("mid", "microprice"),
                "maker_edge": 2.5,
                "taker_edge": 0.5,
            },
            strategy_factory=lambda fve, sig: AshCarteaSkewStrategy(
                fve, sig,
                CarteaSkewParams(
                    beta=0.1, fv_for_alpha="ewma_mid",
                    sigma_residual_prior=1.06, alpha_clip=3.0,
                ),
            ),
            notes="D8 m=2.5 + Cartea beta=0.1",
        ),
        # F3d — safer AS gamma.
        AshCandidate(
            cell_id="F3d_C1_as_g5e-7",
            lever="F3d",
            ash_overrides=dict(PHASE_C_BASELINE_OVERRIDES),
            strategy_factory=lambda fve, sig: AshAvellanedaStoikovStrategy(
                fve, sig,
                AvellanedaStoikovParams(
                    gamma=5e-7, sigma=2.0, k=0.4, horizon=100_000,
                    taker_edge=0.5,
                ),
            ),
            notes="C1 AS gamma=5e-7 (safer AS variant)",
        ),
        # F3e — mild Cartea only C3 cell above baseline.
        AshCandidate(
            cell_id="F3e_C3_cartea_b03",
            lever="F3e",
            ash_overrides=dict(PHASE_C_BASELINE_OVERRIDES),
            strategy_factory=lambda fve, sig: AshCarteaSkewStrategy(
                fve, sig,
                CarteaSkewParams(
                    beta=0.3, fv_for_alpha="ewma_mid",
                    sigma_residual_prior=1.06, alpha_clip=3.0,
                ),
            ),
            notes="C3 Cartea beta=0.3 (only C3 cell above baseline)",
        ),
    ]


# -------------------------------------------------- Phase-E stress matrix


PHASE_E_STRESS_DIR = Path("data/raw/round_1_ash_stress")
PHASE_E_TAPE_LABELS: tuple[str, ...] = (
    "ash_flat",
    "ash_amp3x",
    "ash_narrow_spread",
    "ash_thin_book",
    "ash_anchor_shift",
    "ash_one_sided_heavy",
)


def _load_stress_tape(label: str) -> ReplayEngine:
    # Skip the trades file — the replay engine expects a numeric "day"
    # in the trades filename and our tapes use descriptive labels. The
    # stress transforms only affect the price book, not the trade tape,
    # so dropping trades is equivalent to passing an empty market-trade
    # list for every snapshot.
    price_files = [PHASE_E_STRESS_DIR / f"prices_round_1_day_{label}.csv"]
    return ReplayEngine.from_files(price_paths=price_files, trade_paths=[])


@dataclass(frozen=True)
class StressCell:
    """Single (candidate, tape) evaluation."""

    cell_id: str
    tape: str
    ash_pnl: float
    maker_fills: int
    taker_fills: int
    final_position: int


def run_phase_e(out_dir: Path, data_dir: Path) -> None:
    print("[phase-e] generating stress results for the Phase-F upload cohort",
          file=sys.stderr)
    print(f"[phase-e] loading {len(PHASE_E_TAPE_LABELS)} stress tape(s) from "
          f"{PHASE_E_STRESS_DIR}", file=sys.stderr)
    replays = {tape: _load_stress_tape(tape) for tape in PHASE_E_TAPE_LABELS}
    # Also load real day-0 as the stress-matrix reference tape.
    replays["day_0_real"] = load_day_replay(0, data_dir)

    cohort = phase_f_upload_cohort()
    print(f"[phase-e] running {len(cohort)} candidate(s) x "
          f"{len(replays)} tape(s)", file=sys.stderr)

    cells: list[StressCell] = []
    t0 = time.time()
    for cand in cohort:
        engine = build_engine(cand.ash_overrides)
        for tape, replay in replays.items():
            result = run_candidate_on_day(cand, engine, replay)
            ashr = result.per_product.get(ASH)
            pnl = ashr.pnl if ashr else 0.0
            mk = ashr.maker_trade_count if ashr else 0
            tk = ashr.taker_trade_count if ashr else 0
            fp = ashr.final_position if ashr else 0
            cells.append(StressCell(
                cell_id=cand.cell_id, tape=tape,
                ash_pnl=pnl, maker_fills=mk, taker_fills=tk, final_position=fp,
            ))
            print(f"[phase-e] {cand.cell_id:<32s} @ {tape:<22s} "
                  f"pnl={pnl:+8.1f}  mk/tk={mk:>4d}/{tk:>4d}  "
                  f"pos={fp:+4d}", file=sys.stderr)
    elapsed = time.time() - t0
    print(f"[phase-e] done in {elapsed:.1f}s", file=sys.stderr)

    _write_stress_matrix(out_dir, cells, cohort)


def _write_stress_matrix(
    out_dir: Path, cells: list[StressCell], cohort: list[AshCandidate],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Long format (one row per (cell, tape)).
    long_path = out_dir / "stress_matrix_long.csv"
    with long_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "cell_id", "tape", "ash_pnl", "maker_fills", "taker_fills", "final_position",
        ])
        w.writeheader()
        for c in cells:
            w.writerow({
                "cell_id": c.cell_id, "tape": c.tape,
                "ash_pnl": f"{c.ash_pnl:.2f}",
                "maker_fills": c.maker_fills,
                "taker_fills": c.taker_fills,
                "final_position": c.final_position,
            })
    # Wide format (one row per candidate, one column per tape).
    tapes_ordered = [*list(PHASE_E_TAPE_LABELS), "day_0_real"]
    wide_path = out_dir / "stress_matrix.csv"
    with wide_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cell_id", "notes", *tapes_ordered, "worst_pnl", "best_pnl"])
        by_cell: dict[str, dict[str, float]] = {}
        for c in cells:
            by_cell.setdefault(c.cell_id, {})[c.tape] = c.ash_pnl
        for cand in cohort:
            row_pnls = [by_cell.get(cand.cell_id, {}).get(t) for t in tapes_ordered]
            row_vals = [f"{v:.2f}" if v is not None else "" for v in row_pnls]
            real_pnls = [v for v in row_pnls if v is not None]
            worst = min(real_pnls) if real_pnls else 0.0
            best = max(real_pnls) if real_pnls else 0.0
            w.writerow([
                cand.cell_id, cand.notes, *row_vals,
                f"{worst:.2f}", f"{best:.2f}",
            ])
    print(f"[phase-e] wrote {long_path}", file=sys.stderr)
    print(f"[phase-e] wrote {wide_path}", file=sys.stderr)


def _d8_mild_cartea() -> AshCandidate:
    """wall_mid + m=2.5 + ultra-mild Cartea beta=0.1."""
    params = CarteaSkewParams(
        beta=0.1, fv_for_alpha="ewma_mid",
        sigma_residual_prior=1.06, alpha_clip=3.0,
    )
    return AshCandidate(
        cell_id="D8_m25_cartea_b0.1",
        lever="D8",
        ash_overrides={
            "fair_value_method": "wall_mid",
            "fair_value_fallbacks": ("mid", "microprice"),
            "maker_edge": 2.5,
            "taker_edge": 0.5,
        },
        strategy_factory=lambda fve, sig, p=params: AshCarteaSkewStrategy(fve, sig, p),
        notes="wall_mid + m=2.5/t=0.5 + ultra-mild Cartea beta=0.1 on ewma_mid residual",
    )


def _b6_history_cells() -> list[AshCandidate]:
    out: list[AshCandidate] = []
    for fv in ("wall_mid", "ewma_mid"):
        for h in (16, 32, 48, 64, 96):
            out.append(AshCandidate(
                cell_id=f"B6_{fv}_h{h}",
                lever="B6",
                ash_overrides={
                    "fair_value_method": fv,
                    "fair_value_fallbacks": (
                        ("mid", "microprice") if fv == "wall_mid" else ("wall_mid", "mid")
                    ),
                    "history_length": h,
                },
                notes=f"history_length={h}, fv={fv}",
            ))
    return out


# -------------------------------------------------------------- CSV writer


def write_results_csv(path: Path, rows: Sequence[CellResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "cell_id", "lever", "notes",
        "day_-2_pnl", "day_-1_pnl", "day_0_pnl",
        "mean_pnl", "min_pnl", "max_pnl", "std_pnl",
        "total_maker_fills", "total_taker_fills",
        "local_total_pnl_3day", "expected_official_pnl_per_day",
        "avg_markout_1", "avg_markout_5", "avg_markout_20",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({
                "cell_id": r.cell_id,
                "lever": r.lever,
                "notes": r.notes,
                "day_-2_pnl": f"{r.day_pnl.get(-2, 0.0):.2f}",
                "day_-1_pnl": f"{r.day_pnl.get(-1, 0.0):.2f}",
                "day_0_pnl": f"{r.day_pnl.get(0, 0.0):.2f}",
                "mean_pnl": f"{r.mean_pnl:.2f}",
                "min_pnl": f"{r.min_pnl:.2f}",
                "max_pnl": f"{r.max_pnl:.2f}",
                "std_pnl": f"{r.std_pnl:.2f}",
                "total_maker_fills": r.total_maker_fills,
                "total_taker_fills": r.total_taker_fills,
                "local_total_pnl_3day": f"{r.local_total_pnl_3day:.2f}",
                "expected_official_pnl_per_day": f"{r.expected_official_pnl_per_day:.2f}",
                "avg_markout_1": f"{r.avg_markout_1:.3f}" if r.avg_markout_1 is not None else "",
                "avg_markout_5": f"{r.avg_markout_5:.3f}" if r.avg_markout_5 is not None else "",
                "avg_markout_20": f"{r.avg_markout_20:.3f}" if r.avg_markout_20 is not None else "",
            })


def fmt_result_line(r: CellResult) -> str:
    mk = f"{r.avg_markout_1:+.2f}" if r.avg_markout_1 is not None else "  n/a"
    return (
        f"{r.cell_id:<28s} "
        f"mean={r.mean_pnl:+9.1f}  "
        f"[{r.min_pnl:+7.1f} .. {r.max_pnl:+7.1f}]  "
        f"std={r.std_pnl:5.1f}  "
        f"mk/tk={r.total_maker_fills:>4d}/{r.total_taker_fills:>4d}  "
        f"exp_off={r.expected_official_pnl_per_day:+7.1f}  "
        f"mk1={mk}"
    )


# ------------------------------------------------------------------ CLI


def run_phase(
    phase: str,
    out_dir: Path,
    data_dir: Path,
    levers: Sequence[str] | None = None,
) -> None:
    """Shared runner for Phase B / Phase C / Phase D sweeps.

    ``phase`` is a free-form lower-case tag used as the log prefix; the
    candidate list is dispatched by ``phase`` via ``_candidates_for_phase``.
    """
    tag = f"phase-{phase}"
    print(f"[{tag}] loading {len(FOLDS)} day(s) from {data_dir}", file=sys.stderr)
    replays = {d: load_day_replay(d, data_dir) for d in FOLDS}
    all_cells = _candidates_for_phase(phase)
    if levers is not None:
        selected = {ell.upper() for ell in levers}
        all_cells = [c for c in all_cells if c.lever in selected]
    print(f"[{tag}] running {len(all_cells)} cell(s)", file=sys.stderr)

    results: list[CellResult] = []
    t0 = time.time()
    for i, cand in enumerate(all_cells, 1):
        print(f"[{tag}]  ({i:>3}/{len(all_cells)}) {cand.cell_id}", file=sys.stderr)
        r = evaluate(cand, replays)
        results.append(r)
        print("         " + fmt_result_line(r), file=sys.stderr)
    elapsed = time.time() - t0
    print(f"[{tag}] done in {elapsed:.1f}s", file=sys.stderr)

    # Master CSV.
    out_dir.mkdir(parents=True, exist_ok=True)
    write_results_csv(out_dir / "results_all.csv", results)
    # Per-lever CSVs.
    by_lever: dict[str, list[CellResult]] = {}
    for r in results:
        by_lever.setdefault(r.lever, []).append(r)
    for lever, rows in by_lever.items():
        write_results_csv(out_dir / lever / "results.csv", rows)

    # Summary JSON for the memo to consume.
    summary = {
        "phase": phase,
        "n_cells": len(results),
        "elapsed_sec": elapsed,
        "best_overall_mean": max((r.mean_pnl for r in results), default=0.0),
        "best_overall_exp_off": max(
            (r.expected_official_pnl_per_day for r in results), default=0.0,
        ),
        "by_lever": {
            lever: {
                "best_cell_by_mean": max(rows, key=lambda r: r.mean_pnl).cell_id,
                "best_mean": max(r.mean_pnl for r in rows),
                "best_cell_by_exp_off": max(
                    rows, key=lambda r: r.expected_official_pnl_per_day,
                ).cell_id,
                "best_exp_off": max(r.expected_official_pnl_per_day for r in rows),
                "worst_mean": min(r.mean_pnl for r in rows),
                "n": len(rows),
            } for lever, rows in by_lever.items()
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"[{tag}] wrote {out_dir / 'results_all.csv'}", file=sys.stderr)
    print(f"[{tag}] wrote {out_dir / 'summary.json'}", file=sys.stderr)


def phase_g_candidates() -> list[AshCandidate]:
    """Phase-G exploration beyond the F3a grid corners.

    F3a (the Phase-F winner) sat at the *corner* of the Phase-B grid
    — maker_edge=2.5 (max tested) and skew_coef=2.0 (min tested). The
    monotone gradients suggest further gains are available past those
    corners. Phase-G probes them:

    - G1: wall_mid + m=2.5 + skew c=2 — F3a tuning, wall_mid FV. Tests
      whether the FV choice or the edge/skew tuning is driving F3a.
    - G3: weighted_mid + m=3.0 + skew c=2 — F3a with wider maker edge.
    - G4: wall_mid + m=3.0 + skew c=2 — G1 with wider edge.
    - G5: weighted_mid + m=2.5 + skew c=1 — F3a with softer skew.
    - G6: weighted_mid + m=2.5 + skew c=0.5 — F3a with even softer skew.
    - G7: weighted_mid + m=3.5 + skew c=2 — extreme maker edge.
    """
    def cell(cell_id: str, fv: str, fb: tuple[str, ...], m: float,
             c: float, note: str) -> AshCandidate:
        return AshCandidate(
            cell_id=cell_id,
            lever="G",
            ash_overrides={
                "fair_value_method": fv, "fair_value_fallbacks": fb,
                "maker_edge": m, "taker_edge": 0.5,
            },
            ash_shape_params=ShapeParams(
                skew_mode="linear", skew_coef=c,
                flatten_mode="hard", flatten_threshold=0.7,
                size_mode="constant",
            ),
            notes=note,
        )

    return [
        cell("G1_wall_m25_c2", "wall_mid", ("mid", "microprice"), 2.5, 2.0,
             "F3a tuning on wall_mid (FV swap)"),
        cell("G3_weighted_m30_c2", "weighted_mid", ("wall_mid", "mid"), 3.0, 2.0,
             "F3a with m=3.0 (wider edge probe)"),
        cell("G4_wall_m30_c2", "wall_mid", ("mid", "microprice"), 3.0, 2.0,
             "G1 with m=3.0"),
        cell("G5_weighted_m25_c1", "weighted_mid", ("wall_mid", "mid"), 2.5, 1.0,
             "F3a with skew c=1 (softer)"),
        cell("G6_weighted_m25_c05", "weighted_mid", ("wall_mid", "mid"), 2.5, 0.5,
             "F3a with skew c=0.5 (even softer)"),
        cell("G7_weighted_m35_c2", "weighted_mid", ("wall_mid", "mid"), 3.5, 2.0,
             "F3a with m=3.5 (extreme edge)"),
    ]


def phase_h_candidates() -> list[AshCandidate]:
    """Phase-H slow-FV sweep — tests the 'hidden pattern' hypothesis.

    Phase-H investigation (PHASE_H_HIDDEN_PATTERN.md) established that
    ASH is an OU process with half-life ~2 ticks around a slow local
    mean near 10 000. F3a uses weighted_mid (tracks mid tick-by-tick)
    as FV; theory predicts a SLOWER FV should outperform by anchoring
    quotes to the OU mean rather than chasing noise.

    All cells use F3a's engine (m=2.5, t=0.5, size_mode=constant,
    flatten=hard@0.7). history_length is bumped to 2000 so the EWMA
    has enough samples to resolve the long tau.

    - H1: ewma τ=200 (α≈0.005) — moderate anchor
    - H2: ewma τ=1000 (α≈0.001) — strong anchor
    - H3: ewma τ=5000 (α≈0.0002) — near-constant anchor
    - H4: ewma τ=500 (α≈0.002) + skew c=1 (G5 tuning) — slow FV + G5
    - H5: ewma τ=500 (α≈0.002) + skew c=2 — intermediate control
    - H6: ewma τ=500 (α≈0.002) + Cartea β=0.1 alpha-skew — slow FV
          with residual-driven skew on top
    """
    import math

    def tau_to_alpha(tau: float) -> float:
        return 1.0 - math.exp(-1.0 / tau)

    def slow_ewma_cell(
        cell_id: str, tau: float, skew_coef: float, note: str,
    ) -> AshCandidate:
        return AshCandidate(
            cell_id=cell_id,
            lever="H",
            ash_overrides={
                "fair_value_method": "ewma_mid",
                "fair_value_fallbacks": ("wall_mid", "mid"),
                "ewma_alpha": tau_to_alpha(tau),
                "history_length": 2000,
                "maker_edge": 2.5,
                "taker_edge": 0.5,
            },
            ash_shape_params=ShapeParams(
                skew_mode="linear", skew_coef=skew_coef,
                flatten_mode="hard", flatten_threshold=0.7,
                size_mode="constant",
            ),
            notes=note,
        )

    # H6 uses Cartea-alpha skew with slow-FV as the residual anchor.
    cartea_params = CarteaSkewParams(
        beta=0.1,
        fv_for_alpha="ewma_mid",
        sigma_residual_prior=1.06,
        alpha_clip=3.0,
    )
    h6 = AshCandidate(
        cell_id="H6_ewma500_cartea_b01",
        lever="H",
        ash_overrides={
            "fair_value_method": "ewma_mid",
            "fair_value_fallbacks": ("wall_mid", "mid"),
            "ewma_alpha": tau_to_alpha(500.0),
            "history_length": 2000,
            "maker_edge": 2.5,
            "taker_edge": 0.5,
        },
        strategy_factory=(
            lambda fve, sig, p=cartea_params: AshCarteaSkewStrategy(fve, sig, p)
        ),
        notes="ewma τ=500 FV + Cartea alpha-skew β=0.1",
    )

    return [
        slow_ewma_cell(
            "H0a_ewma10_c2", 10.0, 2.0, "ewma τ=10, skew c=2 (very fast)",
        ),
        slow_ewma_cell(
            "H0b_ewma50_c2", 50.0, 2.0, "ewma τ=50, skew c=2",
        ),
        slow_ewma_cell(
            "H0c_ewma100_c2", 100.0, 2.0, "ewma τ=100, skew c=2",
        ),
        slow_ewma_cell(
            "H1_ewma200_c2", 200.0, 2.0, "ewma τ=200, skew c=2",
        ),
        slow_ewma_cell(
            "H2_ewma1000_c2", 1000.0, 2.0, "ewma τ=1000, skew c=2",
        ),
        slow_ewma_cell(
            "H3_ewma5000_c2", 5000.0, 2.0, "ewma τ=5000 (near-constant), skew c=2",
        ),
        slow_ewma_cell(
            "H4_ewma500_c1", 500.0, 1.0, "ewma τ=500, G5 skew c=1",
        ),
        slow_ewma_cell(
            "H5_ewma500_c2", 500.0, 2.0, "ewma τ=500, skew c=2",
        ),
        h6,
    ]


def phase_i_candidates() -> list[AshCandidate]:
    """Phase-I post-Phase-H exploration.

    All cells use F3a's engine (weighted_mid, m=2.5, t=0.5, skew linear
    c=2, hard flatten 0.7, constant size). Each cell toggles one
    Phase-I feature on top. Some cells combine features.

    - I1: passive_only=True — kill taker leg
    - I3a: profit_target=3 — flatten at +3 ticks markout
    - I3b: profit_target=5 — flatten at +5 ticks markout
    - I4a: spread_regime, skip_in_narrow=True, narrow<=12 — skip thin books
    - I4b: spread_regime, wide_mult=0.9 — tighten in wide spread (m=2.25)
    - I4c: spread_regime, wide_mult=1.2 — loosen in wide spread (m=3.0)
    - I5a: scalp_reload, tighten=1 — tighten unwinding side by 1
    - I5b: scalp_reload, tighten=2 — tighten unwinding side by 2
    - I_combo: all four features on (best per-cell settings)
    """
    from src.strategies.ash_phase_i import AshPhaseIStrategy, PhaseIParams

    def shape_default() -> ShapeParams:
        return ShapeParams(
            skew_mode="linear", skew_coef=2.0,
            flatten_mode="hard", flatten_threshold=0.7,
            size_mode="constant",
        )

    def phase_i_cell(
        cell_id: str, params: PhaseIParams, note: str,
    ) -> AshCandidate:
        return AshCandidate(
            cell_id=cell_id,
            lever="I",
            ash_overrides={
                "fair_value_method": "weighted_mid",
                "fair_value_fallbacks": ("wall_mid", "mid"),
                "maker_edge": 2.5,
                "taker_edge": 0.5,
            },
            strategy_factory=(
                lambda fve, sig, p=params: AshPhaseIStrategy(fve, sig, p)
            ),
            notes=note,
        )

    return [
        phase_i_cell(
            "I1_passive_only",
            PhaseIParams(shape=shape_default(), passive_only=True),
            "F3a with taker disabled (passive only)",
        ),
        phase_i_cell(
            "I3a_pt3",
            PhaseIParams(
                shape=shape_default(),
                profit_target_enabled=True, profit_target_ticks=3.0,
            ),
            "F3a + profit-target flatten at +3 ticks markout",
        ),
        phase_i_cell(
            "I3b_pt5",
            PhaseIParams(
                shape=shape_default(),
                profit_target_enabled=True, profit_target_ticks=5.0,
            ),
            "F3a + profit-target flatten at +5 ticks markout",
        ),
        phase_i_cell(
            "I4a_skip_narrow",
            PhaseIParams(
                shape=shape_default(),
                spread_regime_enabled=True, skip_in_narrow=True,
                narrow_spread_threshold=12,
            ),
            "F3a + skip quoting when spread <= 12",
        ),
        phase_i_cell(
            "I4b_tight_in_wide",
            PhaseIParams(
                shape=shape_default(),
                spread_regime_enabled=True,
                wide_spread_threshold=16, wide_maker_edge_mult=0.9,
            ),
            "F3a + tighter quotes when spread>=16 (m=2.25)",
        ),
        phase_i_cell(
            "I4c_loose_in_wide",
            PhaseIParams(
                shape=shape_default(),
                spread_regime_enabled=True,
                wide_spread_threshold=16, wide_maker_edge_mult=1.2,
            ),
            "F3a + wider quotes when spread>=16 (m=3.0)",
        ),
        phase_i_cell(
            "I5a_scalp1",
            PhaseIParams(
                shape=shape_default(),
                scalp_reload_enabled=True, scalp_tighten_ticks=1.0,
            ),
            "F3a + tighten unwinding side by 1 tick",
        ),
        phase_i_cell(
            "I5b_scalp2",
            PhaseIParams(
                shape=shape_default(),
                scalp_reload_enabled=True, scalp_tighten_ticks=2.0,
            ),
            "F3a + tighten unwinding side by 2 ticks",
        ),
        phase_i_cell(
            "I_combo",
            PhaseIParams(
                shape=shape_default(),
                passive_only=False,  # keep taker; too risky to combine with pt
                profit_target_enabled=True, profit_target_ticks=3.0,
                spread_regime_enabled=True,
                wide_spread_threshold=16, wide_maker_edge_mult=0.9,
                scalp_reload_enabled=True, scalp_tighten_ticks=1.0,
            ),
            "F3a + pt3 + tight_in_wide + scalp1 (combined winners)",
        ),
        phase_i_cell(
            "I2a_ladder_4lvl",
            PhaseIParams(
                shape=shape_default(),
                ladder_enabled=True,
                ladder_edges=(2.5, 5.0, 8.0, 12.0),
                ladder_size_mults=(1.0, 1.5, 2.0, 3.0),
            ),
            "F3a + 4-level ladder rotation (2.5/5/8/12)",
        ),
        phase_i_cell(
            "I2b_ladder_3lvl_tight",
            PhaseIParams(
                shape=shape_default(),
                ladder_enabled=True,
                ladder_edges=(2.5, 4.0, 6.0),
                ladder_size_mults=(1.0, 1.0, 1.5),
            ),
            "F3a + 3-level tight ladder (2.5/4/6)",
        ),
        phase_i_cell(
            "I2c_ladder_2lvl",
            PhaseIParams(
                shape=shape_default(),
                ladder_enabled=True,
                ladder_edges=(2.5, 5.0),
                ladder_size_mults=(1.0, 2.0),
            ),
            "F3a + 2-level ladder (2.5 + 5.0 double-size)",
        ),
        phase_i_cell(
            "I2d_ladder_5lvl",
            PhaseIParams(
                shape=shape_default(),
                ladder_enabled=True,
                ladder_edges=(2.5, 4.0, 6.0, 9.0, 13.0),
                ladder_size_mults=(1.0, 1.0, 1.5, 2.0, 3.0),
            ),
            "F3a + 5-level ladder (2.5/4/6/9/13)",
        ),
        _phase_i2a_standalone_cell(),
    ]


def phase_j_candidates() -> list[AshCandidate]:
    """Phase-J ladder variations — attack I2a's volume-loss bottleneck.

    I2a tied F3a on official (+1 365 vs +1 395). Post-mortem showed:
    - Edge per share improved +29% (7.54 vs 5.86 ticks)
    - Volume dropped −29% (168 vs 238 shares)
    - Result: PnL nearly tied

    Phase-J tests ways to keep the edge advantage while recovering
    inner-level volume:

    - J1: weighted rotation 4/1/1/1 → inner gets 57% of ticks
    - J2: weighted rotation 3/1/1 (3-level) → inner gets 60% of ticks
    - J3: spread-gated outer levels → only use outer if spread>=16
    - J4: inventory-asymmetric → outer only on unwinding side
    - J5: tight ladder (2.5/4/6) with weights 2/1/1 → inner 50%
    - J6: ultra-inner-heavy 6/1/1/1 → 67% inner
    - J7: spread_gated + weighted combo
    - J_f3a_control: equivalent to F3a (weights 1/0/0/0) for sanity
    """
    from src.strategies.ash_ladder import AshLadderStrategy, LadderParams

    def ladder_cell(
        cell_id: str, params: LadderParams, note: str,
    ) -> AshCandidate:
        return AshCandidate(
            cell_id=cell_id,
            lever="J",
            ash_overrides={
                "fair_value_method": "weighted_mid",
                "fair_value_fallbacks": ("wall_mid", "mid"),
                "maker_edge": 2.5,
                "taker_edge": 0.5,
            },
            strategy_factory=(
                lambda fve, sig, p=params: AshLadderStrategy(fve, sig, p)
            ),
            notes=note,
        )

    return [
        ladder_cell(
            "J1_weighted_4111",
            LadderParams(
                edges=(2.5, 5.0, 8.0, 12.0),
                size_mults=(1.0, 1.5, 2.0, 3.0),
                weights=(4, 1, 1, 1),
            ),
            "4-level ladder with inner weight 4 (57%/14%/14%/14%)",
        ),
        ladder_cell(
            "J2_weighted_311",
            LadderParams(
                edges=(2.5, 5.0, 8.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(3, 1, 1),
            ),
            "3-level ladder with inner weight 3 (60%/20%/20%)",
        ),
        ladder_cell(
            "J3_spread_gated",
            LadderParams(
                edges=(2.5, 5.0, 8.0, 12.0),
                size_mults=(1.0, 1.5, 2.0, 3.0),
                spread_gate_enabled=True, gate_spread=16,
            ),
            "4-level with outer levels only when spread>=16",
        ),
        ladder_cell(
            "J4_inv_asym",
            LadderParams(
                edges=(2.5, 5.0, 8.0, 12.0),
                size_mults=(1.0, 1.5, 2.0, 3.0),
                inventory_asymmetric=True,
            ),
            "4-level with outer only on unwinding side (by inventory)",
        ),
        ladder_cell(
            "J5_tight_weighted",
            LadderParams(
                edges=(2.5, 4.0, 6.0),
                size_mults=(1.0, 1.0, 1.5),
                weights=(2, 1, 1),
            ),
            "tight 3-level (2.5/4/6) with inner weight 2 (50%/25%/25%)",
        ),
        ladder_cell(
            "J6_ultra_inner",
            LadderParams(
                edges=(2.5, 5.0, 8.0, 12.0),
                size_mults=(1.0, 1.5, 2.0, 3.0),
                weights=(6, 1, 1, 1),
            ),
            "4-level with inner weight 6 (67%/11%/11%/11%)",
        ),
        ladder_cell(
            "J7_gated_weighted",
            LadderParams(
                edges=(2.5, 5.0, 8.0, 12.0),
                size_mults=(1.0, 1.5, 2.0, 3.0),
                weights=(3, 1, 1, 1),
                spread_gate_enabled=True, gate_spread=16,
            ),
            "4-level weighted 3/1/1/1 + spread-gated outer",
        ),
        ladder_cell(
            "J_f3a_control",
            LadderParams(
                edges=(2.5,),
                size_mults=(1.0,),
                weights=(1,),
            ),
            "F3a-equivalent (single level) — sanity control",
        ),
        ladder_cell(
            "J8_I2a_replay",
            LadderParams(
                edges=(2.5, 5.0, 8.0, 12.0),
                size_mults=(1.0, 1.5, 2.0, 3.0),
                weights=(1, 1, 1, 1),
            ),
            "I2a replay (equal weights) — reference point",
        ),
    ]


def phase_k_candidates() -> list[AshCandidate]:
    """Phase-K — tuning the J2 ladder winner.

    J2 won officially (+1 647, +252 vs F3a). Phase-K explores the
    neighborhood to find tighter edges, different weight ratios, and
    asymmetric per-side ladders.

    - K1 (J2_heavier): weights (4,1,1) → inner 67% on (2.5, 5, 8)
    - K2 (J2_tight):   edges (2.5, 4, 6), weights (3,1,1)
    - K3 (J2_4lvl):    edges (2.5, 5, 8, 12), weights (3,1,1,1)
    - K4 (J2_asym):    buy=(2.5,5,8) x (3,1,1), sell=(2.5,4,6) x (3,1,1)
    - K5 (J2_asym_flip): buy=(2.5,4,6) x (3,1,1), sell=(2.5,5,8) x (3,1,1)
    """
    from src.strategies.ash_ladder import AshLadderStrategy, LadderParams

    def ladder_cell(
        cell_id: str, params: LadderParams, note: str,
    ) -> AshCandidate:
        return AshCandidate(
            cell_id=cell_id,
            lever="K",
            ash_overrides={
                "fair_value_method": "weighted_mid",
                "fair_value_fallbacks": ("wall_mid", "mid"),
                "maker_edge": 2.5,
                "taker_edge": 0.5,
            },
            strategy_factory=(
                lambda fve, sig, p=params: AshLadderStrategy(fve, sig, p)
            ),
            notes=note,
        )

    return [
        ladder_cell(
            "K0_J2_replay",
            LadderParams(
                edges=(2.5, 5.0, 8.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(3, 1, 1),
            ),
            "J2 reference (3/1/1 on 2.5/5/8)",
        ),
        ladder_cell(
            "K1_J2_heavier",
            LadderParams(
                edges=(2.5, 5.0, 8.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(4, 1, 1),
            ),
            "J2 with weights 4/1/1 (67% inner)",
        ),
        ladder_cell(
            "K2_J2_tight",
            LadderParams(
                edges=(2.5, 4.0, 6.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(3, 1, 1),
            ),
            "J2 with tighter outer (2.5/4/6, weights 3/1/1)",
        ),
        ladder_cell(
            "K3_J2_4lvl",
            LadderParams(
                edges=(2.5, 5.0, 8.0, 12.0),
                size_mults=(1.0, 1.5, 2.0, 3.0),
                weights=(3, 1, 1, 1),
            ),
            "J2 plus d=12 outer (weights 3/1/1/1)",
        ),
        ladder_cell(
            "K4_J2_asym",
            LadderParams(
                edges=(2.5, 5.0, 8.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(3, 1, 1),
                buy_edges=(2.5, 5.0, 8.0),
                buy_size_mults=(1.0, 1.5, 2.0),
                buy_weights=(3, 1, 1),
                sell_edges=(2.5, 4.0, 6.0),
                sell_size_mults=(1.0, 1.5, 2.0),
                sell_weights=(3, 1, 1),
            ),
            "Asymmetric: buy 2.5/5/8, sell 2.5/4/6",
        ),
        ladder_cell(
            "K5_J2_asym_flip",
            LadderParams(
                edges=(2.5, 5.0, 8.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(3, 1, 1),
                buy_edges=(2.5, 4.0, 6.0),
                buy_size_mults=(1.0, 1.5, 2.0),
                buy_weights=(3, 1, 1),
                sell_edges=(2.5, 5.0, 8.0),
                sell_size_mults=(1.0, 1.5, 2.0),
                sell_weights=(3, 1, 1),
            ),
            "Asymmetric flipped: buy 2.5/4/6, sell 2.5/5/8",
        ),
        ladder_cell(
            "K6_J2_5lvl",
            LadderParams(
                edges=(2.5, 4.0, 6.0, 8.0, 12.0),
                size_mults=(1.0, 1.0, 1.5, 2.0, 3.0),
                weights=(4, 1, 1, 1, 1),
            ),
            "5-level dense ladder (weights 4/1/1/1/1)",
        ),
    ]


def phase_l_candidates() -> list[AshCandidate]:
    """Phase-L — K2 neighborhood with size-scaling + 4-level + residual.

    K2 (tight 2.5/4/6, weights 3/1/1) scored +1 765 officially
    (+370 vs F3a). Phase-L tests further refinements:

    - L0 K2 replay
    - L1 K2_tighter: edges (2.5, 3.5, 5), weights (3,1,1)
    - L2 K2_split: edges (2.5, 4.5, 7), weights (3,1,1)
    - L4 K2_4lvl_tight: edges (2.5, 4, 6, 8), weights (3,1,1,1)
    - L5 K2_bigsize: K2 with size_mults (1, 3, 5) — bigger outer orders
    - L5b K2_midsize: K2 with size_mults (1, 2, 4)
    - L6 K2_lighter: K2 weights (5, 2, 2) — 55% inner vs K2's 60%
    """
    from src.strategies.ash_ladder import AshLadderStrategy, LadderParams

    def ladder_cell(
        cell_id: str, params: LadderParams, note: str,
    ) -> AshCandidate:
        return AshCandidate(
            cell_id=cell_id,
            lever="L",
            ash_overrides={
                "fair_value_method": "weighted_mid",
                "fair_value_fallbacks": ("wall_mid", "mid"),
                "maker_edge": 2.5,
                "taker_edge": 0.5,
            },
            strategy_factory=(
                lambda fve, sig, p=params: AshLadderStrategy(fve, sig, p)
            ),
            notes=note,
        )

    return [
        ladder_cell(
            "L0_K2_replay",
            LadderParams(
                edges=(2.5, 4.0, 6.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(3, 1, 1),
            ),
            "K2 reference",
        ),
        ladder_cell(
            "L1_K2_tighter",
            LadderParams(
                edges=(2.5, 3.5, 5.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(3, 1, 1),
            ),
            "Tighter outer (2.5/3.5/5) weights 3/1/1",
        ),
        ladder_cell(
            "L2_K2_split",
            LadderParams(
                edges=(2.5, 4.5, 7.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(3, 1, 1),
            ),
            "Split difference outer (2.5/4.5/7) weights 3/1/1",
        ),
        ladder_cell(
            "L4_K2_4lvl_tight",
            LadderParams(
                edges=(2.5, 4.0, 6.0, 8.0),
                size_mults=(1.0, 1.5, 2.0, 3.0),
                weights=(3, 1, 1, 1),
            ),
            "4-level K2 extension (2.5/4/6/8, 3/1/1/1)",
        ),
        ladder_cell(
            "L5_K2_bigsize",
            LadderParams(
                edges=(2.5, 4.0, 6.0),
                size_mults=(1.0, 3.0, 5.0),
                weights=(3, 1, 1),
            ),
            "K2 with big outer size_mults (1/3/5)",
        ),
        ladder_cell(
            "L5b_K2_midsize",
            LadderParams(
                edges=(2.5, 4.0, 6.0),
                size_mults=(1.0, 2.0, 4.0),
                weights=(3, 1, 1),
            ),
            "K2 with mid outer size_mults (1/2/4)",
        ),
        ladder_cell(
            "L6_K2_lighter",
            LadderParams(
                edges=(2.5, 4.0, 6.0),
                size_mults=(1.0, 1.5, 2.0),
                weights=(5, 2, 2),
            ),
            "K2 weights 5/2/2 (55% inner)",
        ),
    ]


def _phase_i2a_standalone_cell() -> AshCandidate:
    """I2a_standalone — verify the standalone ash_ladder.py matches I2a."""
    from src.strategies.ash_ladder import AshLadderStrategy, LadderParams

    params = LadderParams(
        edges=(2.5, 5.0, 8.0, 12.0),
        size_mults=(1.0, 1.5, 2.0, 3.0),
        skew_coef=2.0,
        flatten_threshold=0.7,
    )
    return AshCandidate(
        cell_id="I2a_standalone",
        lever="I",
        ash_overrides={
            "fair_value_method": "weighted_mid",
            "fair_value_fallbacks": ("wall_mid", "mid"),
            "maker_edge": 2.5,
            "taker_edge": 0.5,
        },
        strategy_factory=(
            lambda fve, sig, p=params: AshLadderStrategy(fve, sig, p)
        ),
        notes="I2a using standalone ash_ladder.py (uploaded path)",
    )


def _candidates_for_phase(phase: str) -> list[AshCandidate]:
    if phase == "b":
        return phase_b_candidates()
    if phase == "c":
        return phase_c_candidates()
    if phase == "d":
        return phase_d_candidates()
    if phase == "g":
        return phase_g_candidates()
    if phase == "h":
        return phase_h_candidates()
    if phase == "i":
        return phase_i_candidates()
    if phase == "j":
        return phase_j_candidates()
    if phase == "k":
        return phase_k_candidates()
    if phase == "l":
        return phase_l_candidates()
    raise ValueError(f"unsupported phase: {phase!r}")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--phase", required=True, choices=["b", "c", "d", "e", "g", "h", "i", "j", "k", "l"])
    p.add_argument("--levers", nargs="*", default=None,
                   help="Subset of lever IDs to run (e.g. 'B1 B2' / 'C1 C3'). "
                        "Default: all levers for the phase.")
    p.add_argument("--data-dir", type=Path,
                   default=Path("data/raw/round_1"))
    p.add_argument("--out", type=Path,
                   default=Path("outputs/round_1/ash_deep_dive"))
    return p.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    out_dir = args.out / f"phase_{args.phase}"
    if args.phase == "e":
        run_phase_e(out_dir, args.data_dir)
    else:
        run_phase(args.phase, out_dir, args.data_dir, levers=args.levers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
