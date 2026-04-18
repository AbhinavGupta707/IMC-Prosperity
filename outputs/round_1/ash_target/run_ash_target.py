"""Phase-10 ASH target-position family search.

Evaluates 3 control ASH legs + ~13 target-position candidates on two
views of the local replay:

1. **Official-cadence view** — day 0, filtered to ``timestamp % 1000
   == 0`` (matches the IMC sample rate on the one official day).
2. **Full 3-day × 10k replay** — robustness check.

Every candidate freezes PEPPER at the **Promoted** leg and varies only
ASH. Target-position candidates route ASH through
``AshTargetPositionStrategy`` (research-only; not in live bundle)
while PEPPER continues through the shipped ``MarketMakingStrategy``.
The dispatch is done via ``_PerProductStrategy`` which is only
instantiated inside this runner.

Outputs (same directory):

- ``ash_candidates.csv``
- ``ash_candidates.md``

Usage::

    PYTHONPATH=. .venv/bin/python \\
        outputs/round_1/ash_target/run_ash_target.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

from src.backtest.metrics import SimulationResult
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config import (
    EngineConfig,
    ProductConfig,
    round1_h1_engine_config,
    round1_promoted_engine_config,
)
from src.core.fair_value import FairValueEngine
from src.core.signals import SignalEngine
from src.strategies.ash_target_position import (
    AshTargetPositionStrategy,
    TargetPositionParams,
)
from src.strategies.base import BaseStrategy, StrategyContext
from src.strategies.market_making import MarketMakingStrategy
from src.trader import Trader

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path("data/raw/round_1")
ASH = "ASH_COATED_OSMIUM"
PEPPER = "INTARIAN_PEPPER_ROOT"
OFFICIAL_CADENCE_STEP = 1_000
OFFICIAL_CADENCE_DAY = 0


# ---------------------------------------------------------------------------
# Per-product strategy dispatch (runner-only; live bundle untouched)
# ---------------------------------------------------------------------------


class _PerProductStrategy(BaseStrategy):
    """Route each product to its own configured strategy instance."""

    def __init__(self, by_product: dict[str, BaseStrategy]) -> None:
        self.by_product = by_product
        # Pick any per-product strategy as the default fallback.
        self._default = next(iter(by_product.values()))

    def generate_intent(self, context: StrategyContext):  # type: ignore[override]
        return self.by_product.get(context.product, self._default).generate_intent(context)


def _wrap_trader_with_ash_target(trader: Trader, params: TargetPositionParams) -> None:
    """Swap ``trader.strategies['market_making']`` for a per-product dispatcher.

    ASH routes to ``AshTargetPositionStrategy`` with ``params``; every
    other product keeps ``MarketMakingStrategy``.
    """
    fve = trader.fair_value_engine
    sig = trader.signal_engine
    mm = MarketMakingStrategy(fve, sig)
    tp = AshTargetPositionStrategy(fve, sig, params)
    trader.strategies["market_making"] = _PerProductStrategy({ASH: tp, PEPPER: mm})


# ---------------------------------------------------------------------------
# Candidate configs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AshCandidate:
    label: str
    engine: EngineConfig
    # When None, run as a control with standard MarketMakingStrategy.
    target_params: TargetPositionParams | None
    # One-line note shown in the markdown table.
    note: str


def _swap(engine: EngineConfig, product: str, **overrides) -> EngineConfig:
    base = engine.product_config(product)
    assert base is not None, product
    new_products = dict(engine.products)
    new_products[product] = replace(base, **overrides)
    return EngineConfig(
        state_version=engine.state_version,
        max_trader_data_chars=engine.max_trader_data_chars,
        diagnostics_verbosity=engine.diagnostics_verbosity,
        products=new_products,
        scanner_config=engine.scanner_config,
        residual_config=engine.residual_config,
    )


def _promoted_base() -> EngineConfig:
    """Base config: ASH = H1/Alt wall_mid leg, PEPPER = Promoted.

    This base is used for every **target-position** candidate. The ASH
    fair_value_method can be overridden per candidate (anchor vs
    wall_mid). Default here is ``anchor`` so the residual ``price -
    mean`` is computed against the stable anchor price 10 000 rather
    than a book-driven mid.
    """
    base = round1_h1_engine_config()
    # Switch ASH to anchor-based FV so mean is a constant 10_000.
    # Maker/taker edges inherit the H1/Alt leg (maker=1.5, taker=0.5).
    return _swap(
        base,
        ASH,
        fair_value_method="anchor",
        fair_value_fallbacks=("wall_mid", "mid", "microprice"),
    )


def _anchor_target_engine(
    *, maker_edge: float = 1.5, taker_edge: float = 0.5
) -> EngineConfig:
    base = _promoted_base()
    return _swap(
        base,
        ASH,
        maker_edge=maker_edge,
        taker_edge=taker_edge,
    )


def _wall_target_engine(
    *, maker_edge: float = 1.5, taker_edge: float = 0.5
) -> EngineConfig:
    base = round1_h1_engine_config()
    return _swap(
        base,
        ASH,
        fair_value_method="wall_mid",
        fair_value_fallbacks=("mid", "microprice"),
        maker_edge=maker_edge,
        taker_edge=taker_edge,
    )


# ---- Controls ------------------------------------------------------


def _control_promoted() -> AshCandidate:
    # Use the shipped promoted engine as-is.
    return AshCandidate(
        label="C_promoted",
        engine=round1_promoted_engine_config(),
        target_params=None,
        note="Promoted (ewma_mid m=1.0 t=0.25)",
    )


def _control_h1_alt() -> AshCandidate:
    return AshCandidate(
        label="C_h1_alt",
        engine=round1_h1_engine_config(),
        target_params=None,
        note="H1/Alt/F5 ASH leg (wall_mid m=1.5 t=0.5)",
    )


def _control_baseline() -> AshCandidate:
    # Baseline ASH = wall_mid m=1.0 t=1.0.
    base = round1_h1_engine_config()
    engine = _swap(
        base, ASH,
        fair_value_method="wall_mid",
        fair_value_fallbacks=("mid", "microprice"),
        maker_edge=1.0,
        taker_edge=1.0,
    )
    return AshCandidate(
        label="C_baseline",
        engine=engine,
        target_params=None,
        note="Baseline ASH (wall_mid m=1.0 t=1.0)",
    )


# ---- Target-position family -----------------------------------------


def _L(label: str, *, alpha: float, cap: int, style: str, threshold: float = 2.0) -> AshCandidate:
    return AshCandidate(
        label=label,
        engine=_anchor_target_engine(),
        target_params=TargetPositionParams(
            mode="linear", mean_source="anchor",
            alpha=alpha, cap=cap, exec_style=style, hybrid_threshold=threshold,
        ),
        note=f"linear a={alpha} cap={cap} {style} th={threshold}",
    )


def _D(
    label: str,
    *,
    d: float,
    alpha: float,
    cap: int,
    style: str,
    threshold: float = 2.0,
    maker_edge: float = 1.5,
) -> AshCandidate:
    return AshCandidate(
        label=label,
        engine=_anchor_target_engine(maker_edge=maker_edge),
        target_params=TargetPositionParams(
            mode="dead_zone", mean_source="anchor",
            dead_zone=d, alpha=alpha, cap=cap,
            exec_style=style, hybrid_threshold=threshold,
        ),
        note=f"dz d={d} a={alpha} cap={cap} {style} th={threshold} me={maker_edge}",
    )


def _V(
    label: str, *, gamma: float, alpha: float, cap: int, threshold: float
) -> AshCandidate:
    return AshCandidate(
        label=label,
        engine=_anchor_target_engine(),
        target_params=TargetPositionParams(
            mode="convex", mean_source="anchor",
            alpha=alpha, gamma=gamma, cap=cap,
            exec_style="hybrid", hybrid_threshold=threshold,
        ),
        note=f"convex g={gamma} a={alpha} cap={cap} hybrid th={threshold}",
    )


def _W(
    label: str, *, d: float, alpha: float, cap: int, threshold: float = 2.0
) -> AshCandidate:
    return AshCandidate(
        label=label,
        engine=_wall_target_engine(),
        target_params=TargetPositionParams(
            mode="dead_zone", mean_source="fair",
            dead_zone=d, alpha=alpha, cap=cap,
            exec_style="hybrid", hybrid_threshold=threshold,
        ),
        note=f"wall-mean dz d={d} a={alpha} cap={cap} hybrid th={threshold}",
    )


def candidate_list() -> list[AshCandidate]:
    out: list[AshCandidate] = [
        _control_promoted(),
        _control_h1_alt(),
        _control_baseline(),
        # Linear
        _L("L1_hybrid",    alpha=5,  cap=40, style="hybrid"),
        _L("L2_hybrid_hi", alpha=10, cap=40, style="hybrid"),
        _L("L3_taker",     alpha=5,  cap=40, style="taker"),
        _L("L4_maker",     alpha=5,  cap=40, style="maker"),
        # Dead-zone
        _D("D1_hybrid",          d=1, alpha=8,  cap=40, style="hybrid"),
        _D("D2_hybrid_hi",       d=2, alpha=10, cap=40, style="hybrid"),
        _D("D3_maker",           d=1, alpha=8,  cap=40, style="maker"),
        _D("D4_taker",           d=1, alpha=8,  cap=40, style="taker"),
        _D("D5_wide_maker",      d=2, alpha=10, cap=40, style="hybrid",
           threshold=3.0, maker_edge=2.0),
        # Convex
        _V("V1_gamma15", gamma=1.5, alpha=3,   cap=40, threshold=2.0),
        _V("V2_gamma20", gamma=2.0, alpha=1.5, cap=40, threshold=3.0),
        # Wall-mean sanity checks
        _W("W1_wall_dz1", d=1, alpha=8, cap=40, threshold=2.0),
        _W("W2_wall_dz0", d=0, alpha=5, cap=40, threshold=2.0),
        # Mild-alpha / small-cap variants — test whether a softer
        # target avoids the saturation seen in the base grid.
        _D("D6_mild",       d=2, alpha=3, cap=20, style="hybrid", threshold=3.0),
        _D("D7_deep_dz",    d=4, alpha=5, cap=30, style="hybrid", threshold=4.0),
        _L("L5_mild",       alpha=2, cap=20, style="hybrid", threshold=2.0),
    ]
    return out


# ---------------------------------------------------------------------------
# Replay loaders
# ---------------------------------------------------------------------------


def _load_full_replay() -> ReplayEngine:
    price_files = sorted(DATA_DIR.glob("prices_round_1_day_*.csv"))
    trade_files = sorted(DATA_DIR.glob("trades_round_1_day_*.csv"))
    if not price_files:
        raise SystemExit(f"No price files in {DATA_DIR}")
    return ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)


def _official_cadence_replay(full: ReplayEngine) -> ReplayEngine:
    filtered: list[ReplayStep] = [
        s
        for s in full.steps
        if s.day == OFFICIAL_CADENCE_DAY and s.timestamp % OFFICIAL_CADENCE_STEP == 0
    ]
    return ReplayEngine(filtered)


# ---------------------------------------------------------------------------
# Runner / metrics
# ---------------------------------------------------------------------------


def _run_candidate(candidate: AshCandidate, replay: ReplayEngine) -> SimulationResult:
    trader = Trader(config=candidate.engine)
    if candidate.target_params is not None:
        _wrap_trader_with_ash_target(trader, candidate.target_params)
    return BacktestSimulator(trader=trader).run(replay)


def _bucket_pnl(result: SimulationResult, product: str) -> list[float]:
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    buckets = (25_000, 50_000, 75_000, 100_000)
    totals = [0.0] * len(buckets)
    if not series:
        return totals
    by_day: dict[int, list[tuple[int, float]]] = {}
    for (day, ts), (_ts, val) in zip(keys, series):
        by_day.setdefault(day, []).append((ts, val))
    for _day, day_series in by_day.items():
        day_start = day_series[0][1] if day_series else 0.0
        prev_val = day_start
        for i, end_ts in enumerate(buckets):
            last_val = prev_val
            for ts, v in day_series:
                if ts < end_ts:
                    last_val = v
            totals[i] += last_val - prev_val
            prev_val = last_val
    return totals


def _summary(result: SimulationResult, product: str) -> dict:
    pr = result.per_product.get(product)
    if pr is None:
        return {}
    buckets = _bucket_pnl(result, product)
    avg_size = (
        (pr.buy_trade_quantity + pr.sell_trade_quantity) / pr.trade_count
        if pr.trade_count else 0.0
    )
    maker_pct = (
        pr.maker_trade_count / pr.trade_count if pr.trade_count else 0.0
    )
    return {
        "pnl": pr.pnl,
        "trades": pr.trade_count,
        "maker": pr.maker_trade_count,
        "taker": pr.taker_trade_count,
        "maker_pct": maker_pct,
        "avg_size": avg_size,
        "final_pos": pr.final_position,
        "near_limit": pr.steps_near_limit,
        "mk1": pr.avg_markout_1,
        "mk5": pr.avg_markout_5,
        "mk20": pr.avg_markout_20,
        "b0": buckets[0],
        "b1": buckets[1],
        "b2": buckets[2],
        "b3": buckets[3],
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score(off: dict, local: dict) -> float:
    """Composite score — higher = better.

    Formula (weights chosen to be interpretable, not hidden):

        score = off_ash_pnl
              + 0.20 * min(off_b0, off_b1, off_b2, off_b3)   # cross-bucket floor
              + 0.02 * local_ash_pnl                         # robustness bonus
              - 0.5  * |off_final_pos|                       # penalize drift
              - 1.0  * off_near_limit                        # risk
    """
    if not off:
        return float("-inf")
    off_pnl = off.get("pnl", 0.0)
    buckets = [off.get(f"b{i}", 0.0) for i in range(4)]
    bucket_floor = min(buckets) if buckets else 0.0
    local_pnl = local.get("pnl", 0.0)
    final_pos = off.get("final_pos", 0)
    near_limit = off.get("near_limit", 0)
    return (
        off_pnl
        + 0.20 * bucket_floor
        + 0.02 * local_pnl
        - 0.5 * abs(final_pos)
        - 1.0 * near_limit
    )


# ---------------------------------------------------------------------------
# Output emission
# ---------------------------------------------------------------------------


_COLS: tuple[str, ...] = (
    "label",
    "note",
    # Official-cadence view
    "off_ash",
    "off_b0",
    "off_b1",
    "off_b2",
    "off_b3",
    "off_trades",
    "off_maker",
    "off_taker",
    "off_maker_pct",
    "off_avg_size",
    "off_final_pos",
    "off_near_limit",
    "off_mk1",
    "off_mk5",
    "off_mk20",
    "off_pep",
    # 3-day local
    "local_ash",
    "local_trades",
    "local_final_pos",
    "local_near_limit",
    # Composite
    "score",
    "delta_vs_h1",
)


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def _emit_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in _COLS})


def _emit_md(path: Path, rows: list[dict]) -> None:
    header = (
        "# ASH target-position candidates (sorted by score)\n\n"
        "- `off_*` columns: official-cadence view (day 0 filtered to\n"
        "  `ts % 1000 == 0`, ~1000 snapshots).\n"
        "- `local_*` columns: full 3-day × 10k replay.\n"
        "- `delta_vs_h1`: `off_ash` minus the C_h1_alt row's `off_ash`.\n"
        "- Scoring formula (see `run_ash_target.py:score`):\n\n"
        "        score = off_ash\n"
        "              + 0.20 * min(off_b0..b3)\n"
        "              + 0.02 * local_ash\n"
        "              - 0.5  * |off_final_pos|\n"
        "              - 1.0  * off_near_limit\n\n"
        "All candidates share the Promoted PEPPER leg.\n\n"
    )
    lines = [header]
    lines.append("| " + " | ".join(_COLS) + " |")
    lines.append("|" + "|".join(["---"] * len(_COLS)) + "|")
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in _COLS) + " |")
    lines.append("")
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    full = _load_full_replay()
    official = _official_cadence_replay(full)
    print(
        f"[loaded] full 3-day = {len(full.steps)} steps | "
        f"official-cadence = {len(official.steps)} steps"
    )

    cands = candidate_list()
    rows: list[dict] = []
    h1_off_ash: float | None = None

    for i, c in enumerate(cands, start=1):
        r_off = _run_candidate(c, official)
        r_local = _run_candidate(c, full)
        off = _summary(r_off, ASH)
        off_pep = _summary(r_off, PEPPER)
        local = _summary(r_local, ASH)
        s = score(off, local)

        if c.label == "C_h1_alt":
            h1_off_ash = off.get("pnl", 0.0)

        rows.append(
            {
                "label": c.label,
                "note": c.note,
                "off_ash": off.get("pnl"),
                "off_b0": off.get("b0"),
                "off_b1": off.get("b1"),
                "off_b2": off.get("b2"),
                "off_b3": off.get("b3"),
                "off_trades": off.get("trades"),
                "off_maker": off.get("maker"),
                "off_taker": off.get("taker"),
                "off_maker_pct": off.get("maker_pct"),
                "off_avg_size": off.get("avg_size"),
                "off_final_pos": off.get("final_pos"),
                "off_near_limit": off.get("near_limit"),
                "off_mk1": off.get("mk1"),
                "off_mk5": off.get("mk5"),
                "off_mk20": off.get("mk20"),
                "off_pep": off_pep.get("pnl"),
                "local_ash": local.get("pnl"),
                "local_trades": local.get("trades"),
                "local_final_pos": local.get("final_pos"),
                "local_near_limit": local.get("near_limit"),
                "score": s,
            }
        )
        print(
            f"[{i:>2}/{len(cands)}] {c.label:<14s} "
            f"off_ash={off.get('pnl', 0):+8.1f} "
            f"b0={off.get('b0', 0):+6.1f} b3={off.get('b3', 0):+6.1f} "
            f"trades={off.get('trades', 0):>3d} "
            f"mk={off.get('maker_pct', 0):.2f} "
            f"pos={off.get('final_pos', 0):+4d} "
            f"nl={off.get('near_limit', 0):>3d} "
            f"local={local.get('pnl', 0):+9.1f} "
            f"score={s:+8.1f}"
        )

    # Annotate delta vs H1/Alt baseline.
    if h1_off_ash is not None:
        for r in rows:
            if r.get("off_ash") is not None:
                r["delta_vs_h1"] = r["off_ash"] - h1_off_ash

    rows.sort(key=lambda r: r["score"] if r.get("score") is not None else float("-inf"), reverse=True)

    _emit_csv(ROOT / "ash_candidates.csv", rows)
    _emit_md(ROOT / "ash_candidates.md", rows)

    print(f"\nWrote:")
    print(f"  - {ROOT / 'ash_candidates.csv'}")
    print(f"  - {ROOT / 'ash_candidates.md'}")

    # Terminal top-5 summary.
    print("\nTop 5 by score:")
    for r in rows[:5]:
        print(
            f"  {r['label']:<14s} score={r['score']:+8.1f} "
            f"off_ash={r['off_ash']:+8.1f} "
            f"Δvs_h1={r.get('delta_vs_h1', 0):+7.1f} "
            f"near={r['off_near_limit']:>3d} "
            f"pos={r['off_final_pos']:+4d}"
        )


if __name__ == "__main__":
    main()
