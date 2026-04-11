# IMC Prosperity Engine

Reusable trading engine and research harness for IMC Prosperity.

## Philosophy

This repository is built around a simple idea:

- keep the live trading path thin
- keep the offline research path rich
- encode market logic through explicit modules
- optimize only after correctness and interpretability exist

The architectural principles are defined in [ARCHITECTURE_DOCTRINE.md](/Users/abhinavgupta/Desktop/IMC/ARCHITECTURE_DOCTRINE.md).

## Current Scope

The repository currently contains:

- the architecture doctrine
- the official algorithm guide export
- tutorial research and planning notes
- a reusable project skeleton for the live bot and offline harness
- tutorial CSVs copied into `data/raw/tutorial_round_1`
- a **manual-round toolkit** (`src/manual_rounds/`) with solvers for
  the five recurring manual-round families (graph, bid, crowding,
  hybrid, portfolio) and round-day CLI runners

This is the foundation for building:

1. a production-safe `Trader.run()` engine
2. a replay and review system for tutorial and round data
3. round-specific strategy modules on top of shared core services
4. a parallel manual-round workstream for the closed-form puzzles each
   round ships alongside the algo challenge

## Repository Layout

```text
data/
  raw/
  processed/

docs/
  manual_round_playbook.md
  manual_round_agent_brief.md

notebooks/

src/
  datamodel.py
  trader.py
  core/
  strategies/
  backtest/
  manual_rounds/       # solvers + priors + artifact writer
  scripts/             # CLI runners (algo + manual)

tests/
```

## Development Workflow

Recommended loop:

1. build or refine one core module
2. validate with unit tests
3. replay tutorial data offline
4. inspect logs and review artifacts
5. only then tune strategy parameters

## Quick Start

Create a virtual environment, install dependencies, and run the smoke checks:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=. pytest
PYTHONPATH=. python -m src.scripts.validate_submission
PYTHONPATH=. python -m src.scripts.run_backtest
PYTHONPATH=. python -m src.scripts.compare_fair_values
PYTHONPATH=. python -m src.scripts.run_parameter_sweep
PYTHONPATH=. python -m src.scripts.run_phase6_emeralds_sweep --label phase6_emeralds
PYTHONPATH=. python -m src.scripts.run_phase6_tomatoes_sweep --label phase6_tomatoes
PYTHONPATH=. python -m src.scripts.run_review --label smoke
```

`run_review` writes an enriched Phase 4a review pack under
`outputs/review_packs/<run_id>/` containing metric aggregates with
markouts and entry-edge, per-trade records, step-indexed series,
chart PNGs, a provenance manifest, and a human review template.
See [`docs/phase_4_review_discipline_note.md`](docs/phase_4_review_discipline_note.md)
for how to read each artifact.

`run_phase6_emeralds_sweep` and `run_phase6_tomatoes_sweep` are the
Phase 6 cross-day robustness entry points. Each runs its sweep grid
on `day_-2`, `day_-1`, and the combined tape, intersects the plateau
bands across all three slices, applies the four sweep-level checks
of the six-part Phase 6 promotion gate, and writes a per-sub-sweep
`plateau_intersection.{json,txt}` (plus, for TOMATOES, a top-level
`product_comparison.{json,txt}`) under
`outputs/sweeps/<run_id>_phase6_<product>/`. See
[`docs/phase_6_robustness_note.md`](docs/phase_6_robustness_note.md)
for the methodology, the per-product verdicts, and the cross-day
validation read on the Phase 5 EWMA narrow peak.

## Manual rounds

Each Prosperity round ships a closed-form manual puzzle alongside the
algo challenge. `src/manual_rounds/` contains solvers for the five
recurring families (graph/path, sealed bid, game-theoretic crowding,
average-bid hybrid, news portfolio) plus CLI runners that accept a JSON
input and emit a standardized artifact pack under
`outputs/manual_rounds/<run_id>/` — `answer.json`,
`top_alternatives.json`, `assumptions.json`, `sensitivity.json`, and a
rendered `submission_note.md`. See
[`docs/manual_round_playbook.md`](docs/manual_round_playbook.md) for the
operator guide (round → family → runner) and
[`src/manual_rounds/README.md`](src/manual_rounds/README.md) for worked
examples from every public round.

## Important Files

- [ARCHITECTURE_DOCTRINE.md](/Users/abhinavgupta/Desktop/IMC/ARCHITECTURE_DOCTRINE.md)
- [Writing an Algorithm in Python.html](/Users/abhinavgupta/Desktop/IMC/Writing%20an%20Algorithm%20in%20Python.html)
- [Implementation Plan.md](/Users/abhinavgupta/Desktop/IMC/Tutorial/Implementation%20Plan.md)
- [Manual Strategy Plan.md](/Users/abhinavgupta/Desktop/IMC/Tutorial/Manual%20Strategy%20Plan.md)
- [manual_round_playbook.md](/Users/abhinavgupta/Desktop/IMC/docs/manual_round_playbook.md)
- [manual_round_agent_brief.md](/Users/abhinavgupta/Desktop/IMC/docs/manual_round_agent_brief.md)
- [deep-research-report.md](/Users/abhinavgupta/Desktop/IMC/Tutorial/deep-research-report.md)
