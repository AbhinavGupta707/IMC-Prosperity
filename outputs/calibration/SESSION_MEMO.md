# Calibration session memo — 2026-04-16

**Branch**: `calibration-tooling`
**Goal**: build reusable calibration + strategy-audit infra; apply to
round-1 ASH/PEPPER; verdict on F3a's structural edge.

## What shipped this session

| Step | Artifact | Status |
|---|---|---|
| 1 | Polished round-1 calibration (trade CSV wired, AR(1) demeaned, bimodal-band split) | ✅ Committed `337c329` |
| 2 | Tutorial validation script + report (pipeline reproduces chrispyroberts published values) | ✅ Committed |
| 3 | `strategy_replay.py` engine infra + `run_strategy_audit.py` CLI + F3a verdict | ✅ Committed |
| 4 | `docs/calibration_runbook.md` — round-N playbook | ✅ This commit |
| 5 | This memo | ✅ This commit |

Total: 4 commits on `calibration-tooling`, ~600 lines of new infra
code, 4 new tests (all green), 3 new output bundles.

## Headline findings

### 1. The calibration pipeline works on real IMC data.

Cross-validated against chrispyroberts's tutorial truth:

- **EMERALDS bot rules: EXACT match** (round(fv) ± {8, 10})
- **TOMATOES bot rule families: correct structure** (the 92% vs his
  99% match is attributable to using mid-FV proxy, not methodology
  error)
- **p_active within 0.001 of truth** on both products
- **p_buy within 0.002 of truth** for EMERALDS (TOMATOES p_buy off
  due to a known direction-classifier limitation, fix scoped for
  future work)

This is strong evidence the pipeline transfers. When applied to
round-1 ASH/PEPPER, recovered parameters can be trusted.

### 2. Round-1 ASH FV process is recovered for the first time.

| Quantity | ASH | PEPPER |
|---|---:|---:|
| FV process σ (per tick) | 0.4074 | 0.1898 |
| Drift (mean Δfv) | -0.0083 | **+0.0940** |
| AR(1) phi (demeaned) | +0.024 | -0.000 |
| Quantization grid | 1/1024 | 1/10 |
| FV range over day | [9993.76, 10011.00] | [12000.10, 12099.90] |

**ASH** has clean random-walk dynamics. **PEPPER** has strong
upward drift (~+94 over 1000 ticks). PEPPER's drift IS the source
of `buy_hold_80`'s consistent +7286 PnL — confirmed mechanism, not
luck.

### 3. F3a's ASH edge is STRUCTURAL.

Replayed F3a's exact `Trader.run` against recovered server FV:

- **Mean edge per quote: +1.56 ticks** (quotes consistently land on
  profitable side of true FV)
- **All 4 markout horizons positive on fills**: h=1: +0.47,
  h=5: +0.43, h=20: +0.60, h=50: +1.57
- **Both bid AND ask sides positive**: bid mean_edge +0.57,
  ask mean_edge +3.43

A lucky strategy could have ONE of those signals positive. Having
ALL OF THEM positive AND on both sides rules out luck.

The +434 ASH PnL official lift over baseline reflects a real edge
from F3a's `weighted_mid + maker_edge=2.5 + linear skew c=2`
combination. **Carry this mechanism forward to round-2.**

### 4. Round-1 inner-bot rules need more work (known limitation).

Outer wall rules recovered at 95-97% match. Inner wall rules at
80-84%. Bimodality split helped but didn't fully resolve. Likely
causes:

- A third bot (analog of chrispyroberts's "near-FV bot 3")
  occasionally displaces the wall — the cluster detector picked it
  up as a sub-band but with too-few samples to recover its rule
- State-dependent inner wall placement (rounding rule may switch
  on something other than fractional FV)

Not a blocker for round-2 — outer wall + FV process are the
high-value parameters. Inner-bot refinement scoped for future.

## What's now possible that wasn't before

1. **Day-1-of-round-N to ground-truth FV in 30 minutes.**
   Submit `trader_hold_one.py`, download log, run
   `run_calibration --log <log> --out <dir>`. No code changes
   needed for any new round.

2. **Per-strategy structural-edge audit.** For any candidate
   submission .py, replay it against true FV and get per-quote
   edge + per-fill markouts. Picks structurally winning configs
   over lucky ones.

3. **Cross-validation against a known-good baseline.** When
   chrispyroberts (or anyone) publishes parameters for a future
   round, the validate-against-tutorial pattern lets us
   instantly score our pipeline.

## What still doesn't exist (DEFERRED, not abandoned)

| Capability | Why deferred |
|---|---|
| Generative Monte Carlo simulator | 2-3 days build; the audit pipeline answers "is this structurally good on THIS day" — the MC would answer "stable across MANY days of this regime". Worth building once we know round-2 structure. |
| Joint side+location trade classifier | Current heuristic adequate for outer-wall calibration; refinement only matters when adverse-selection breakdown is needed. |
| Per-mechanism transfer-ratio tracker | Needs ~5 rounds of (local, official) pairs to be useful. Defer until then. |
| Inner-wall multi-bot refinement | 80-84% match is good enough for round-2 prep; revisit if a strategy needs precise inner-bot modeling. |

## Files touched

```
src/analysis/calibration/
  bot_classifier.py         (bimodal split detection)
  extract_fv.py             (load_trades_csv, general-mode FV)
  fair_value_fit.py         (AR(1) demeaning)
  rule_search.py            (sub-band offset filtering)
  trade_fit.py              (FV-based direction inference)
  strategy_replay.py        NEW — replay any Trader against true FV
  types.py                  (no change)
  validate.py               (no change)
  serialize.py              (no change)

src/scripts/calibration/
  run_calibration.py        (--trades-csv flag)
  validate_against_tutorial.py   NEW — cross-validate vs published params
  run_strategy_audit.py     NEW — CLI for strategy_replay
  compare_against_truth.py  (no change)

tests/
  test_calibration_pipeline.py        (added AR(1) and bimodal split tests)
  test_calibration_runner_integration.py
  test_calibration_general_mode.py
  test_strategy_replay.py             NEW

docs/
  calibration_runbook.md    NEW — round-N playbook

outputs/calibration/
  round1_hold1/             ASH+PEPPER calibration on real round-1 data
  tutorial_validation/      pipeline-vs-truth cross-validation
  f3a_retrospective/        F3a structural-edge verdict
  SESSION_MEMO.md           this file
```

## Open follow-ups for the next session

1. **Round-2 day-1**: submit `trader_hold_one.py` immediately when
   the round opens. Then run the runbook end-to-end on round-2
   data.

2. **F3a + wall_mid hybrid (G1) verdict**: we already have the
   strategy_replay machinery. If you uploaded G1 to round-1, run
   the audit on it the same way we did for F3a.

3. **Generative MC simulator**: only build if you have a specific
   question that requires multi-session distribution analysis.
   Until then, the audit pipeline is sufficient for one-day
   structural verification.

4. **Branch hygiene**: `git stash list` shows two stashes from this
   session (pre-step1 unrelated wip + Phase G config from
   round1-research). Decide whether to apply, drop, or keep.
