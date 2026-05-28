# IMC Prosperity 4 — Quantitative Algorithmic Trading Engine

> **Top 0.7% of 19,000+ teams globally.** Engine, backtesting harness,
> and methodology behind the submission.

This repository is the reusable engine that was built and hardened over
the 10-week IMC Prosperity 4 competition. The same `core/` and `backtest/`
modules drove every round — inventory-aware MM, options pricing with BSM
+ smile, cointegrated-basket arbitrage, conversion, and rank-auction
games — across a 50-product universe.

The final-round algorithm source is intentionally withheld. Everything
that makes the engine reusable — the module split, the backtesting
harness, the cross-day robustness pipeline, the manual-round solver
toolkit, and the methodology docs — is public.

---

## What's interesting about it

**One harness, five qualitatively different games.** `core/` is
round-agnostic — `fair_value`, `signals`, `risk`, `execution`,
`state_store`, and `market_data` are written once and reused. Each round
adds an `engine/` orchestrator and a `strategies/round_N/` directory of
frozen historical research; nothing in `core/` or `backtest/` ever
changes per round.

**Cross-day robustness gate baked into the sweep harness.** Every
parameter promotion runs through `src/backtest/parameter_sweep.py` +
`plateau.py`, which intersect plateau bands across every historical day
slice and require all-day-positive PnL before promotion. The methodology
is codified in
[`docs/phase_6_robustness_note.md`](docs/phase_6_robustness_note.md).

**Review pack as a first-class artifact.** `run_review` produces a
self-contained directory per backtest — metric aggregates with markouts
and entry-edge, per-trade records, step-indexed PnL series, chart PNGs,
provenance manifest, and a human review template. Format and reading
order are in
[`docs/phase_4_review_discipline_note.md`](docs/phase_4_review_discipline_note.md).

**BSM + smile primitives for the options book.** `src/options/bsm.py`
and `smile.py` are the Greek-aware pricing layer used to construct
delta-hedged and Greek-attributed PnL on the options sleeves.

**Manual-round solver framework.** `src/manual_rounds/` is a standalone
toolkit with solvers for the five recurring closed-form families
(graph-path, sealed-bid, game-theoretic crowding, average-bid hybrid,
news portfolio), each with regret tables, value-of-information analysis,
and standardised artifact output.

---

## Architecture at a glance

```
                            ┌──────────────────────────┐
                            │ datamodel.py · trader.py │  ← IMC entry point
                            └──────────┬───────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
       ┌─────────────┐         ┌──────────────┐         ┌──────────────┐
       │   core/     │         │   engines/   │         │ strategies/  │
       │             │         │              │         │              │
       │ fair_value  │         │ basket_arb   │         │ round_1/     │
       │ signals     │  ←uses→ │ stat_arb     │  ←runs→ │ round_3/     │
       │ risk        │         │ options_mm   │         │   hydrogel   │
       │ execution   │         │ r3_engine    │         │   velvet     │
       │ state_store │         │ counterparty │         │   vev_4000   │
       │ market_data │         │   _intel     │         │   voucher_*  │
       └──────┬──────┘         └──────────────┘         └──────────────┘
              │                        ▲
              ▼                        │
       ┌─────────────┐         ┌──────────────┐         ┌──────────────┐
       │  options/   │         │  backtest/   │         │ manual_      │
       │             │         │              │         │  rounds/     │
       │ bsm         │         │ replay_engine│         │              │
       │ smile       │         │ simulator    │         │ graph/bid/   │
       │ (Greeks)    │         │ fill_model   │         │ crowding/    │
       └─────────────┘         │ parameter_   │         │ hybrid/      │
                               │   sweep      │         │ portfolio    │
                               │ plateau      │         │ + priors     │
                               │ drilldown    │         │ + artifacts  │
                               │ metrics      │         └──────────────┘
                               └──────────────┘
```

- **`core/`** is round-agnostic — same code served every round.
- **`engines/`** holds round-specific orchestrators that compose
  strategies into runnable bundles.
- **`strategies/round_N/`** is frozen historical research — preserved,
  not modified.
- **`backtest/`** is the replay + sweep + plateau + drilldown harness.
- **`options/`** holds BSM + smile primitives.
- **`manual_rounds/`** is the standalone closed-form solver toolkit.

---

## Repository tour

| Path | What's there |
|---|---|
| [`src/core/`](src/core/) | `fair_value`, `signals`, `risk`, `execution`, `config`, `state_store`, `market_data`, `logger` |
| [`src/engines/`](src/engines/) | Round orchestrators: `basket_arb`, `stat_arb`, `options_mm`, `r3_engine`, `r3_velvet_options_engine`, `counterparty_intel` |
| [`src/strategies/round_3/`](src/strategies/round_3/) | R3 strategies: hydrogel MR, velvet hedge, velvet options rolling IV, VEV_4000 MM, voucher liquidity / short premium / zero-bid lottery |
| [`src/options/`](src/options/) | BSM pricer + smile primitives |
| [`src/backtest/`](src/backtest/) | Replay engine, simulator, fill model, parameter sweep, plateau intersection, drilldown, charts, metrics, reporting |
| [`src/manual_rounds/`](src/manual_rounds/) | Solvers for graph / bid / crowding / hybrid / portfolio families; CLI runners with standardised artifact output |
| [`src/scripts/`](src/scripts/) | Per-round runners + diagnostics + calibration |
| [`tests/`](tests/) | Pytest suite (unit + integration) |
| [`docs/`](docs/) | Engine docs: architecture, phase methodology notes, runbooks |
| [`data/raw/`](data/raw/) | Tutorial + Round 1–5 public replay CSVs |
| [`ARCHITECTURE_DOCTRINE.md`](ARCHITECTURE_DOCTRINE.md) | Design principles |

---

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Smoke checks
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m src.scripts.validate_submission

# Replay + review on tutorial data
PYTHONPATH=. python -m src.scripts.run_backtest
PYTHONPATH=. python -m src.scripts.run_review --label baseline

# Parameter sweeps with cross-day plateau intersection
PYTHONPATH=. python -m src.scripts.run_phase6_emeralds_sweep --label phase6_emeralds
PYTHONPATH=. python -m src.scripts.run_phase6_tomatoes_sweep --label phase6_tomatoes
```

`run_review` writes a complete review pack to `outputs/review_packs/<id>/`
— see
[`docs/phase_4_review_discipline_note.md`](docs/phase_4_review_discipline_note.md).

`run_phase6_*_sweep` runs each sweep grid on every historical day,
intersects the plateau bands across slices, and writes
`plateau_intersection.{json,txt}` plus a product comparison —
methodology in
[`docs/phase_6_robustness_note.md`](docs/phase_6_robustness_note.md).

---

## Documentation

Engine docs only. Per-round research narrative is intentionally not
published.

- [`ARCHITECTURE_DOCTRINE.md`](ARCHITECTURE_DOCTRINE.md) — design principles
- [`docs/architecture.md`](docs/architecture.md) — modules, data flow, types
- [`docs/adding_a_product.md`](docs/adding_a_product.md) — decision tree for onboarding a new product
- [`docs/new_round_checklist.md`](docs/new_round_checklist.md) — what to do when a new round drops
- [`docs/manual_round_playbook.md`](docs/manual_round_playbook.md) — operator guide for the manual-round solvers
- [`docs/phase_3_fair_value_note.md`](docs/phase_3_fair_value_note.md) — fair-value inference methodology
- [`docs/phase_4_review_discipline_note.md`](docs/phase_4_review_discipline_note.md) — review pack format and reading order
- [`docs/phase_6_robustness_note.md`](docs/phase_6_robustness_note.md) — sweep + plateau intersection methodology
- [`docs/phase_9_submission_checklist.md`](docs/phase_9_submission_checklist.md) — submission packaging and validation
- [`docs/market_making_literature_pass.md`](docs/market_making_literature_pass.md) — literature review
- [`docs/ash_implementation_quickstart.md`](docs/ash_implementation_quickstart.md) — engine quickstart for a delta-one product
- [`docs/calibration_runbook.md`](docs/calibration_runbook.md) — calibration runbook

---

## Tech stack & methodology references

Python 3.12 · `pytest` · `numpy` · `pandas` · standard library only for
the production submission path.

Methodology references: Avellaneda-Stoikov 2008 (MM with inventory
penalty), Stoikov 2018 (microprice), Engle-Granger 1987 (cointegration),
Vidyamurthy 2004 (pairs trading), Cartea-Jaimungal-Penalva 2015 Ch. 9
(OU-based MR), Lo-MacKinlay 1988 (variance ratio).

---

## Status

Competition concluded. Final-round algorithm source remains private;
everything else in this repository is public reference material for the
engine and its methodology.
