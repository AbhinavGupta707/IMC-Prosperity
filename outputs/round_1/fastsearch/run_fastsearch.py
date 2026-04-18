"""Phase-9 fastsearch — PEPPER-first strategy-family search.

Evaluates ~30 PEPPER candidates across six families (F0 controls, F1
early sell suppression, F2 early short-cap, F3 faster FV, F4 early
asymmetric recovery, F5 buy-biased asymmetric taker edges) on two
views of the local replay:

1. **Official-cadence view** — day 0 filtered to ``timestamp % 1000
   == 0`` (1 000 snapshots, matches the official IMC sample rate).
2. **Full local robustness view** — all 3 days × 10 000 snapshots.

ASH is held at the H1 / Alt wall-based leg in every PEPPER trial so
the PEPPER comparison is clean. See ``pepper_memo.md`` for family
rationale, ``ash_memo.md`` for the ASH freeze, ``controls.md`` for
the official-result table this search is trying to beat.

Output files are written to this directory:

- ``pepper_candidates.csv`` — all 30+ candidates, both views, score
- ``pepper_candidates.md`` — same as markdown table

The script makes **NO** config promotions or submission exports.
It is a diagnostic runner only.

Usage::

    PYTHONPATH=. .venv/bin/python \
        outputs/round_1/fastsearch/run_fastsearch.py
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from src.backtest.metrics import SimulationResult
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config import (
    EngineConfig,
    ProductConfig,
    round1_alt_engine_config,
    round1_h1_engine_config,
    round1_promoted_engine_config,
)
from src.trader import Trader

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path("data/raw/round_1")
ASH = "ASH_COATED_OSMIUM"
PEPPER = "INTARIAN_PEPPER_ROOT"

# Official-cadence decimation: the IMC environment samples 1 per
# 1000 timestamps. Local files are at 100-tick granularity.
OFFICIAL_CADENCE_STEP = 1_000
# Which of the local days to use as the official-cadence proxy.
# day=0 is the most recent local day, which is the training match
# for the current official run.
OFFICIAL_CADENCE_DAY = 0
# Scoring penalty threshold for first-half short (matches the
# promoted/alt bucket-0 end-position of ~+1 and the baseline −8).
MAX_SHORT_PENALTY_CUTOFF = 8


# ---------------------------------------------------------------------------
# Candidate builders
# ---------------------------------------------------------------------------


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


def _promoted_pepper_overrides() -> dict:
    """Snapshot of the shipped Promoted PEPPER leg, as kwargs for ``replace``.

    The Phase-9 search uses this as the common starting point for
    every candidate so each family knob is evaluated in isolation.
    """
    pc: ProductConfig = round1_promoted_engine_config().product_config(PEPPER)  # type: ignore[assignment]
    return {
        "fair_value_method": pc.fair_value_method,
        "fair_value_fallbacks": pc.fair_value_fallbacks,
        "taker_edge": pc.taker_edge,
        "maker_edge": pc.maker_edge,
        "inventory_skew": pc.inventory_skew,
        "flatten_threshold": pc.flatten_threshold,
        "history_length": pc.history_length,
    }


def _alt_pepper_overrides() -> dict:
    pc: ProductConfig = round1_alt_engine_config().product_config(PEPPER)  # type: ignore[assignment]
    return {
        "fair_value_method": pc.fair_value_method,
        "fair_value_fallbacks": pc.fair_value_fallbacks,
        "taker_edge": pc.taker_edge,
        "maker_edge": pc.maker_edge,
        "inventory_skew": pc.inventory_skew,
        "flatten_threshold": pc.flatten_threshold,
        "history_length": pc.history_length,
    }


def _candidate(label: str, **pepper_overrides) -> tuple[str, EngineConfig]:
    """Build one candidate from the H1 base (wall-based ASH) + PEPPER overrides."""
    base = round1_h1_engine_config()  # ASH = alt wall_mid leg, PEPPER = promoted
    # Reset PEPPER leg to a clean promoted baseline, then layer the family knobs.
    reset = {**_promoted_pepper_overrides(), **pepper_overrides}
    return label, _swap(base, PEPPER, **reset)


def candidate_configs() -> list[tuple[str, EngineConfig]]:
    """Build the full ordered candidate list (~32 PEPPER variants)."""
    out: list[tuple[str, EngineConfig]] = []

    # --- F0 Controls ----------------------------------------------------
    out.append(_candidate("F0_promoted"))  # Promoted PEPPER
    # Alt PEPPER: same base edges but skew=1.0, flatten=0.9
    out.append(
        _candidate(
            "F0_alt",
            inventory_skew=1.0,
            flatten_threshold=0.9,
        )
    )

    # --- F1 Early sell suppression -------------------------------------
    # Promoted already has taker=2.0 symmetrically. Here we RAISE the
    # sell-side edge only, in the early window. Buy side stays at 2.0.
    for N in (10_000, 25_000, 50_000):
        for bonus in (0.5, 1.0, 2.0):
            out.append(
                _candidate(
                    f"F1_sellwiden_N{N // 1000}k_b{bonus:g}",
                    early_window=N,
                    early_taker_edge_sell=2.0 + bonus,
                    # buy stays at full-day taker_edge = 2.0 implicitly
                )
            )

    # --- F2 Early short-cap --------------------------------------------
    for N in (10_000, 25_000, 50_000):
        for cap in (0, -4, -8):
            out.append(
                _candidate(
                    f"F2_shortcap_N{N // 1000}k_c{cap}",
                    early_window=N,
                    early_short_cap=cap,
                )
            )

    # --- F3 Faster FV (full-day history substitute) --------------------
    for h in (16, 24):
        out.append(_candidate(f"F3_h{h}", history_length=h))

    # --- F4 Early asymmetric recovery ----------------------------------
    for N in (10_000, 25_000):
        for mult in (1.5, 2.0):
            out.append(
                _candidate(
                    f"F4_shortrecover_N{N // 1000}k_m{mult:g}",
                    early_window=N,
                    early_short_skew_mult=mult,
                    early_short_flatten=0.6,
                )
            )

    # --- F5 Buy-biased asymmetric taker edges (full-day) ---------------
    for (buy, sell) in (
        (0.5, 2.0),
        (0.5, 2.5),
        (1.0, 2.0),
        (1.0, 2.5),
        (1.5, 2.5),
        (1.5, 3.0),
    ):
        out.append(
            _candidate(
                f"F5_buy{buy:g}_sell{sell:g}",
                taker_edge_buy=buy,
                taker_edge_sell=sell,
            )
        )

    # --- F6 Composites — F5 asymmetric taker × Alt inventory knobs -----
    # Rationale: on the official day Alt's extra PEPPER PnL came from
    # ``flatten_threshold=0.9 + inventory_skew=1.0`` riding a bigger
    # long into the drift. F5's asymmetric taker edges keep us from
    # premature sells in bucket 0. Combining them may keep F5's
    # downside protection AND match Alt's upside — at a cost of more
    # near-limit exposure.
    for (buy, sell) in ((0.5, 2.5), (1.0, 2.5), (1.0, 3.0)):
        out.append(
            _candidate(
                f"F6_alt_inv_buy{buy:g}_sell{sell:g}",
                taker_edge_buy=buy,
                taker_edge_sell=sell,
                inventory_skew=1.0,
                flatten_threshold=0.9,
            )
        )
    # Promoted + alt-flatten only (no taker asymmetry).
    out.append(_candidate("F6_promoted_flat09", flatten_threshold=0.9))
    out.append(_candidate("F6_promoted_flat08", flatten_threshold=0.8))

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
    """Decimate a full 3-day replay to 1-per-1000 timestamps on day 0.

    Matches the official IMC sample rate (1 000 snapshots over
    timestamps 0..999 000) on the most recent training day.
    """
    filtered: list[ReplayStep] = [
        s
        for s in full.steps
        if s.day == OFFICIAL_CADENCE_DAY and s.timestamp % OFFICIAL_CADENCE_STEP == 0
    ]
    return ReplayEngine(filtered)


# ---------------------------------------------------------------------------
# Metric helpers (compatible with phase8_5/run_phase8_5.py)
# ---------------------------------------------------------------------------


def _pnl_by_bucket(
    result: SimulationResult,
    product: str,
    day_buckets: tuple[int, ...] = (25_000, 50_000, 75_000, 100_000),
) -> list[float]:
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    totals = [0.0] * len(day_buckets)
    if not series:
        return totals
    by_day: dict[int, list[tuple[int, float]]] = {}
    for (day, ts), (_ts, val) in zip(keys, series):
        by_day.setdefault(day, []).append((ts, val))
    for _day, day_series in by_day.items():
        day_start = day_series[0][1] if day_series else 0.0
        prev_val = day_start
        for i, end_ts in enumerate(day_buckets):
            last_val = prev_val
            for ts, v in day_series:
                if ts < end_ts:
                    last_val = v
            totals[i] += last_val - prev_val
            prev_val = last_val
    return totals


def _early_day_pnl(result: SimulationResult, product: str, end_ts: int) -> float:
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    if not series:
        return 0.0
    total = 0.0
    current_day = None
    day_start_val = 0.0
    last_val_before_end: float | None = None
    for (day, ts), (_ts, val) in zip(keys, series):
        if day != current_day:
            if current_day is not None and last_val_before_end is not None:
                total += last_val_before_end - day_start_val
            current_day = day
            day_start_val = val
            last_val_before_end = None
        if ts <= end_ts:
            last_val_before_end = val
    if last_val_before_end is not None:
        total += last_val_before_end - day_start_val
    return total


def _max_short_first_half(result: SimulationResult, product: str) -> int:
    records = [r for r in result.trade_records if r.product == product]
    if not records:
        return 0
    by_day: dict[int, list] = {}
    for r in records:
        by_day.setdefault(r.fill_day, []).append(r)
    deepest = 0
    for day, rs in by_day.items():
        rs.sort(key=lambda r: r.fill_timestamp)
        pos = 0
        for r in rs:
            if r.fill_timestamp > 50_000:
                break
            pos += r.quantity if r.side == "buy" else -r.quantity
            deepest = min(deepest, pos)
    return deepest


def _trigger_counts(
    result: SimulationResult, product: str, day_buckets: tuple[int, ...]
) -> list[tuple[int, int]]:
    """Return (buy_trig, sell_trig) per bucket (summed across days).

    Trigger count approximated by number of filled trades on each side
    in the bucket. Only taker fills are true signal triggers, but the
    forensic drilldown uses total filled trades for consistency.
    """
    records = [r for r in result.trade_records if r.product == product]
    out = [[0, 0] for _ in day_buckets]
    if not records:
        return [(0, 0) for _ in day_buckets]
    for r in records:
        # Figure out the bucket
        for i, end_ts in enumerate(day_buckets):
            if r.fill_timestamp < end_ts:
                idx = 0 if r.side == "buy" else 1
                out[i][idx] += 1
                break
    return [(a, b) for a, b in out]


def _end_of_bucket_pos(
    result: SimulationResult,
    product: str,
    day_buckets: tuple[int, ...] = (25_000, 50_000, 75_000, 100_000),
) -> list[int]:
    """Summed end-of-bucket position across days (matches bucket_breakdown)."""
    records = [r for r in result.trade_records if r.product == product]
    if not records:
        return [0] * len(day_buckets)
    by_day: dict[int, list] = {}
    for r in records:
        by_day.setdefault(r.fill_day, []).append(r)
    # For a single-day run we want this bucket-by-bucket; for 3-day we
    # take the last one per day and sum (so we're reporting absolute
    # position at bucket end per day). For the runner we only surface
    # single-day (official-cadence) bucket positions; the 3-day view
    # prints just the final day's bucket positions for sanity.
    # Simplest policy: use day=OFFICIAL_CADENCE_DAY if present, else
    # sum across days.
    target_day = OFFICIAL_CADENCE_DAY if OFFICIAL_CADENCE_DAY in by_day else None
    rows = by_day[target_day] if target_day is not None else records
    rows = sorted(rows, key=lambda r: r.fill_timestamp)
    out: list[int] = []
    pos = 0
    i = 0
    for end_ts in day_buckets:
        while i < len(rows) and rows[i].fill_timestamp < end_ts:
            r = rows[i]
            pos += r.quantity if r.side == "buy" else -r.quantity
            i += 1
        out.append(pos)
    return out


def _summary(
    result: SimulationResult, product: str, *, single_day: bool
) -> dict:
    pr = result.per_product.get(product)
    if pr is None:
        return {}
    buckets = _pnl_by_bucket(result, product)
    triggers = _trigger_counts(
        result, product, (25_000, 50_000, 75_000, 100_000)
    )
    end_pos = _end_of_bucket_pos(result, product)
    avg_size = (
        (pr.buy_trade_quantity + pr.sell_trade_quantity) / pr.trade_count
        if pr.trade_count
        else 0.0
    )
    return {
        "pnl": pr.pnl,
        "trade_count": pr.trade_count,
        "maker_trades": pr.maker_trade_count,
        "taker_trades": pr.taker_trade_count,
        "final_pos": pr.final_position,
        "steps_near_limit": pr.steps_near_limit,
        "avg_entry_edge": pr.avg_entry_edge,
        "avg_markout_1": pr.avg_markout_1,
        "avg_markout_5": pr.avg_markout_5,
        "avg_markout_20": pr.avg_markout_20,
        "avg_size": avg_size,
        "early_25k": _early_day_pnl(result, product, 24_900),
        "early_50k": _early_day_pnl(result, product, 49_900),
        "bucket_0_25": buckets[0],
        "bucket_25_50": buckets[1],
        "bucket_50_75": buckets[2],
        "bucket_75_100": buckets[3],
        "trig_b0": triggers[0],
        "trig_b1": triggers[1],
        "max_short_fh": _max_short_first_half(result, product),
        "end_pos_b0": end_pos[0],
        "end_pos_b1": end_pos[1],
        "end_pos_b2": end_pos[2],
        "end_pos_b3": end_pos[3],
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score(off: dict, three_day: dict) -> float:
    """Phase-9 composite score — weights shown for review, not hidden.

    Primary signal: official-cadence PEPPER PnL. Adjustments:
    - ``+1.0`` per unit of first-half PnL (reward early strength).
    - ``+0.02`` per unit of 3-day PEPPER PnL (small robustness bonus).
    - ``-5.0`` per unit of max-short beyond 8 in the first half.
    - ``-1.0`` per near-limit snapshot on the official-cadence view.
    """
    pnl_off = off.get("pnl", 0.0)
    early50_off = off.get("early_50k", 0.0)
    max_short_fh_off = off.get("max_short_fh", 0)
    near_limit_off = off.get("steps_near_limit", 0)
    pnl_3day = three_day.get("pnl", 0.0)
    short_penalty = 5.0 * max(0, -max_short_fh_off - MAX_SHORT_PENALTY_CUTOFF)
    return (
        pnl_off
        + 1.0 * early50_off
        + 0.02 * pnl_3day
        - short_penalty
        - 1.0 * near_limit_off
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _run(engine: EngineConfig, replay: ReplayEngine) -> SimulationResult:
    trader = Trader(config=engine)
    return BacktestSimulator(trader=trader).run(replay)


_COLS = [
    "label",
    # Official-cadence view (day 0, 1000 snapshots)
    "off_total",
    "off_pep",
    "off_ash",
    "off_pep_early25",
    "off_pep_early50",
    "off_pep_b0",
    "off_pep_b1",
    "off_pep_b2",
    "off_pep_b3",
    "off_pep_trades",
    "off_pep_mkr",
    "off_pep_tkr",
    "off_pep_avg_size",
    "off_pep_buy_b0",
    "off_pep_sell_b0",
    "off_pep_buy_b1",
    "off_pep_sell_b1",
    "off_pep_endpos_b0",
    "off_pep_endpos_b1",
    "off_pep_endpos_b2",
    "off_pep_endpos_b3",
    "off_pep_max_short_fh",
    "off_pep_near_limit",
    "off_pep_mk1",
    "off_pep_mk5",
    "off_pep_mk20",
    # Full 3-day view
    "local_total",
    "local_pep",
    "local_ash",
    "local_pep_early25",
    "local_pep_early50",
    "local_pep_near_limit",
    "local_pep_max_short_fh",
    # Score
    "score",
]


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
        "# PEPPER fastsearch candidates (sorted by score)\n"
        "\n"
        "Columns are split into three groups:\n"
        "\n"
        "- ``off_*`` — official-cadence view (day 0 filtered to ts %%"
        " 1000 == 0, 1000 snapshots). Closest local proxy to the "
        "IMC fill model.\n"
        "- ``local_*`` — full 3-day × 10k snapshot replay. Denser "
        "fill model, used for robustness only.\n"
        "- ``score`` — composite ranking metric. Formula:\n"
        "\n"
        "    score = off_pep + 1.0 * off_pep_early50 + 0.02 * local_pep\n"
        "          - 5.0 * max(0, -off_pep_max_short_fh - 8)\n"
        "          - 1.0 * off_pep_near_limit\n"
        "\n"
        "All candidates share the wall-based ASH leg (H1 / Alt leg). "
        "PEPPER leg varies per candidate.\n"
        "\n"
    )
    lines = [header]
    lines.append("| " + " | ".join(_COLS) + " |")
    lines.append("|" + "|".join(["---"] * len(_COLS)) + "|")
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in _COLS) + " |")
    lines.append("")
    path.write_text("\n".join(lines))


def main() -> None:
    full = _load_full_replay()
    official = _official_cadence_replay(full)
    print(
        f"[loaded] full 3-day = {len(full.steps)} steps | "
        f"official-cadence day {OFFICIAL_CADENCE_DAY} at {OFFICIAL_CADENCE_STEP}-step "
        f"= {len(official.steps)} steps"
    )
    assert (
        len(official.steps) >= 900
    ), "official-cadence view should have ~1000 snapshots"

    rows: list[dict] = []
    for i, (label, engine) in enumerate(candidate_configs()):
        r_off = _run(engine, official)
        r_local = _run(engine, full)
        off = _summary(r_off, PEPPER, single_day=True)
        off_ash = _summary(r_off, ASH, single_day=True)
        local = _summary(r_local, PEPPER, single_day=False)
        local_ash = _summary(r_local, ASH, single_day=False)
        score = _score(off, local)
        rows.append(
            {
                "label": label,
                "off_total": r_off.total_pnl,
                "off_pep": off.get("pnl"),
                "off_ash": off_ash.get("pnl"),
                "off_pep_early25": off.get("early_25k"),
                "off_pep_early50": off.get("early_50k"),
                "off_pep_b0": off.get("bucket_0_25"),
                "off_pep_b1": off.get("bucket_25_50"),
                "off_pep_b2": off.get("bucket_50_75"),
                "off_pep_b3": off.get("bucket_75_100"),
                "off_pep_trades": off.get("trade_count"),
                "off_pep_mkr": off.get("maker_trades"),
                "off_pep_tkr": off.get("taker_trades"),
                "off_pep_avg_size": off.get("avg_size"),
                "off_pep_buy_b0": off.get("trig_b0", (0, 0))[0],
                "off_pep_sell_b0": off.get("trig_b0", (0, 0))[1],
                "off_pep_buy_b1": off.get("trig_b1", (0, 0))[0],
                "off_pep_sell_b1": off.get("trig_b1", (0, 0))[1],
                "off_pep_endpos_b0": off.get("end_pos_b0"),
                "off_pep_endpos_b1": off.get("end_pos_b1"),
                "off_pep_endpos_b2": off.get("end_pos_b2"),
                "off_pep_endpos_b3": off.get("end_pos_b3"),
                "off_pep_max_short_fh": off.get("max_short_fh"),
                "off_pep_near_limit": off.get("steps_near_limit"),
                "off_pep_mk1": off.get("avg_markout_1"),
                "off_pep_mk5": off.get("avg_markout_5"),
                "off_pep_mk20": off.get("avg_markout_20"),
                "local_total": r_local.total_pnl,
                "local_pep": local.get("pnl"),
                "local_ash": local_ash.get("pnl"),
                "local_pep_early25": local.get("early_25k"),
                "local_pep_early50": local.get("early_50k"),
                "local_pep_near_limit": local.get("steps_near_limit"),
                "local_pep_max_short_fh": local.get("max_short_fh"),
                "score": score,
            }
        )
        print(
            f"[{i + 1:>2}/{len(candidate_configs())}] {label:<36s} "
            f"off_pep={off.get('pnl', 0):+8.1f} "
            f"early50={off.get('early_50k', 0):+7.1f} "
            f"max_short={off.get('max_short_fh', 0):+4d} "
            f"near_lim={off.get('steps_near_limit', 0):3d} "
            f"local_pep={local.get('pnl', 0):+8.1f} "
            f"score={score:+9.1f}"
        )

    rows.sort(key=lambda r: r["score"], reverse=True)

    _emit_csv(ROOT / "pepper_candidates.csv", rows)
    _emit_md(ROOT / "pepper_candidates.md", rows)
    print(f"\nDone. Wrote:")
    print(f"  - {ROOT / 'pepper_candidates.csv'}")
    print(f"  - {ROOT / 'pepper_candidates.md'}")

    # Emit a compact top-10 summary in the log to ease downstream analysis.
    print("\nTop 10 by score:")
    print(f"  {'label':<36s} {'score':>8s} {'off_pep':>8s} {'early50':>7s} {'near':>4s} {'ms_fh':>5s}")
    for r in rows[:10]:
        print(
            f"  {r['label']:<36s} {r['score']:>8.1f} "
            f"{r['off_pep']:>+8.1f} {r['off_pep_early50']:>+7.1f} "
            f"{r['off_pep_near_limit']:>4d} {r['off_pep_max_short_fh']:>+5d}"
        )


if __name__ == "__main__":
    main()
