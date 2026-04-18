# Phase 8.5 memo — targeted follow-up after the first official upload

Scope: a **small, surgical** pass built on top of the Phase-7/8
forensic drill-down (`outputs/round_1/official_results/analysis/
bucket_memo.md`). Two workstreams only — PEPPER early-day weakness
and ASH official under-trading — using a tight candidate set and
the existing `ReplayEngine` + `BacktestSimulator`.

- No configs in `src/core/config.py` were changed.
- No automatic promotion.
- No new estimators, no broad sweep.

All local numbers below come from `outputs/round_1/phase8_5/run_phase8_5.py`
on 3 days × 10 000 snapshots of `data/raw/round_1/`. Official
numbers come from `outputs/round_1/official_results/<variant>/*.json`.

## Section A — What we tested

### PEPPER (5 candidates, 3 new)

All ASH legs are held at the shipped promoted ASH, so PEPPER
comparisons are clean. Changes are parameter-only — no code changes.

| Label | Change vs shipped Promoted PEPPER | Hypothesis |
|-------|-----------------------------------|------------|
| P0_promoted | — | control |
| P1_alt_upside | `skew=1.0, flatten=0.9` (i.e., the Alt PEPPER leg) | upside reference |
| P2_h16_fast_fv | `history_length=16` | faster fair-value lock-on fixes early drift lag |
| P3_skew4_recovery | `inventory_skew=4.0` | stronger inventory-skew pulls us out of wrong-direction short |
| P4_flat50_early | `flatten_threshold=0.5` | earlier flatten-mode caps inventory exposure |

### ASH (4 candidates, 2 new)

All PEPPER legs are held at the shipped promoted PEPPER. Parameter-
only.

| Label | Change vs shipped Promoted ASH | Hypothesis |
|-------|--------------------------------|------------|
| A0_promoted_ewma_t025 | — | control |
| A1_alt_wall_t05_m15 | `wall_mid, t=0.5, m=1.5` (the Alt ASH leg) | upside reference |
| A2_ewma_t05 | `taker_edge=0.5` | only the taker threshold is wrong on the official fill model |
| A3_wall_t05_m10 | `wall_mid, t=0.5, m=1.0` | only the fair-value choice is wrong (maker_edge stays promoted-style) |

### Combined (3 candidates)

| Label | Make-up |
|-------|---------|
| C0_promoted_control | shipped promoted (ASH: ewma_t025, PEPPER: promoted) |
| C1_best_combined | auto-picked local winners — collapsed to A1+P1 = **shipped Alt** |
| C2_alt_upside | shipped alt |

## Section B — PEPPER conclusions

### B.1 The early-day weakness was not fixed by any param-only variant

| Label | pnl_pep | early_25k | bucket 0-25k | max_short_first_half |
|-------|--------:|----------:|-------------:|---------------------:|
| P0_promoted | +54 015 | +1 264.5 | +1 264.5 | −6 |
| P1_alt_upside | +78 844 | +1 469.0 | +1 469.0 | −6 |
| P2_h16_fast_fv | +50 191 | +936.5 | +936.5 | **−10** |
| P3_skew4_recovery | +35 201 | +807.5 | +807.5 | **−25** |
| P4_flat50_early | +42 594 | +1 179.0 | +1 179.0 | **−10** |

On the local 3-day replay, **all three new PEPPER candidates are
WORSE than the shipped Promoted PEPPER**, both on day-total PnL and
on early-day PnL. P3 (higher skew) is the worst across the board —
it forces unwinds during the drift, and paradoxically ends up going
*deeper* short in the first half of each day.

### B.2 The "early short" signature doesn't reproduce locally for Promoted

On official, Baseline PEPPER ended bucket 0-25k at **position −8**.
On local 3-day replay, Promoted PEPPER's `max_short_first_half` is
only **−6** — a small, transient short. The cold-start, single-day
character of the official run is not reproduced by the local 3-day
replay, where the linear-drift estimator is fully warm by day 0.

### B.3 Is Alt PEPPER genuinely better, or just more inventory?

Local says: Alt is +46 % better than Promoted on PEPPER PnL, at the
same trade count (803 vs 792), similar entry edge (+2.94 vs +2.95),
similar markouts (+3.43 for both at h=20), **but at much higher
near-limit exposure**: 7 224 near-limit steps vs Promoted's 755
(9.6× more). Official-day data showed the same: Alt ended the day
at PEPPER +6 (vs Promoted −2) and spent 22 snapshots above 40 units
in bucket 50-75k. Alt *is* genuinely better by inventory-taking, not
by signal quality — it is a **higher-variance bet**, not a Pareto
improvement.

### B.4 Is there a cleaner PEPPER candidate worth uploading?

Not from this pass. The honest answer is:

- The param-only space around Promoted PEPPER is **exhausted** — no
  obvious win available.
- The only credible path to fixing the early-day weakness is a
  **code-level time-varying rule** (first-N-k sell gate, or hard
  no-short in first 25k, or asymmetric inventory skew). I did not
  build those in this pass; they are the natural next experiment.
- Alt PEPPER remains the higher-upside alternate but at real
  inventory cost.

## Section C — ASH conclusions

### C.1 What drove the official ASH under-performance?

| Label | pnl_ash | trades | taker | mk20 | near_limit |
|-------|--------:|-------:|------:|-----:|-----------:|
| A0_promoted (ewma, t=0.25) | +6 447 | 472 | 461 | +1.93 | 0 |
| A1_alt (wall, t=0.5, m=1.5) | **+7 747** | 766 | 757 | +1.72 | 110 |
| A2_ewma_t05 (ewma, t=0.5) | +5 376 | 387 | 378 | +1.90 | 0 |
| A3_wall_t05_m10 (wall, t=0.5, m=1.0) | +7 696 | 768 | 762 | +1.70 | 135 |

Decomposition:

- **FV choice dominates.** Going from `ewma_mid` (A0) to `wall_mid`
  with the same `taker_edge=0.5` raises local trade count from 472
  → 766 and PnL +6 447 → +7 696-7 747 (+19 %). The official data
  saw the same direction, bigger magnitude (+720 → +983, +36 %).
- **Maker_edge width is neutral locally.** A1 (m=1.5) vs A3 (m=1.0)
  differ by only +51 PnL (less than 1 %). The maker-edge choice is
  a tuning knob, not a structural one.
- **Loosening the taker_edge inside the ewma family (A2) HURTS.**
  Going from t=0.25 → t=0.5 with ewma_mid drops trade count 472 →
  387 and PnL +6 447 → +5 376 (−17 %). Ewma is smooth enough that
  raising the taker threshold just kills trigger count without
  improving markout quality. This rules out "promoted is nearly
  right, just need a slightly looser edge".

### C.2 Was the alt ASH leg genuinely better?

Yes — on both local and official data — and **the reason is the
fair-value family, not the edge width**. Alt's +20 % local uplift
over Promoted and +36 % official uplift are both concentrated on
the `wall_mid` switch. A3 is a near-clone that keeps maker_edge
equal to the promoted default (1.0); locally it ties Alt.

### C.3 Does a middle-ground ASH leg exist and should it be preferred?

A3 (wall_mid, t=0.5, m=1.0) is a legitimate middle-ground:

- Same local PnL as Alt (−50 PnL, statistically indistinguishable)
- Narrower maker quotes (m=1.0) → less inventory swing per passive
  fill → possibly lower cross-day variance
- 135 near-limit steps vs Alt's 110 — same order, slightly higher

Given we only have ONE official data point, choosing A3 over Alt
saves us nothing and loses the one empirically-tested configuration.
If/when we get a second official data point, we can test A3 directly;
until then, A1 (the shipped Alt ASH) is the better-defended choice.

## Section D — Combined candidate recommendation

Local best-combined is **literally the shipped Alt** (A1 × P1).
There is no new combined candidate that *outperforms* Alt locally.

| Candidate | Status | Rationale |
|-----------|--------|-----------|
| **C0_promoted_control** | shipped today | validated by Phase 7: beats baseline, loses to alt |
| **C1 = C2 = Alt** | already uploaded | local winner; official also the best single day |

So the real question is not "what new combined candidate", but
"given the data we have, do we rotate Promoted → Alt as the default,
or hold Promoted and design a code-level PEPPER experiment first".

## Section E — Explicit recommendation

### Should we upload a revised candidate next?

**Not blindly.** The two options are:

1. **Rotate default from Promoted → Alt**. Pros: Alt was the best
   official single-day result and the best local result. Cons: Alt's
   PEPPER leg relies on higher inventory (up to +22 PEPPER long
   officially, 22 near-limit snapshots in bucket 50-75k) — single
   data-point evidence is thin for that robustness claim.
2. **Keep Promoted, build the time-varying PEPPER early-day fix
   next**. A first-25k sell-taker gate or hard early no-short cap
   is the *only* intervention the Phase-8.5 evidence supports for
   closing the early-day gap. Param-only tweaks are exhausted.

### Should we keep the current promoted candidate?

**Yes, keep Promoted as the default shipped bundle for now.** The
Phase-8.5 evidence does not produce a strictly-better combined
candidate; it produces either "Alt" (upside bet, already uploaded)
or "Promoted" (robust default, already uploaded).

### Should we test one more controlled alternate first?

**Yes.** Specifically one new candidate, prepared but not promoted,
that implements a **minimal code-level PEPPER early-day guard**:

- first 25 000 ticks of each day: `sell_taker_edge_multiplier = 1.5`
  (effective sell taker_edge = 3.0 while buy stays at 2.0), AND
- first 25 000 ticks: hard cap `min_position = 0` on PEPPER.

Everything else in Promoted stays the same. This is the smallest
intervention that tests the user's core hypothesis (early short
is the problem) without reopening broader tuning. If it improves
official early-day PEPPER without killing late-day, it becomes the
next Promoted.

**Do NOT upload it blindly.** Prepare it, review the local
output under the same 3-day replay, and only then decide whether
to upload.

---

## Known uncertainties / caveats

1. **Local vs official scale mismatch.** The local replay is 3 × 10k
   snapshots; the official run is 1 × 1000 snapshots. A single-day
   cold-start effect (the PEPPER warm-up) is compressed on official
   and diluted on local. A 1-day local replay would be a cleaner
   surrogate; none exists today.
2. **Local fill model is more generous.** ~2× more PnL gap between
   aggressive and conservative configs locally than officially,
   per the Phase-7 finding. Rankings are consistent; magnitudes are
   not.
3. **Promoted ASH's official under-performance might be fixable
   only by FV swap.** A2 (`ewma_t05`) rules out "just loosen the
   taker edge"; A3 confirms the FV swap is where the PnL is. Any
   future Promoted ASH candidate should start from `wall_mid`.
4. **Alt PEPPER's high near-limit exposure (7 224 local steps, 22
   official bucket-3 snapshots) is a cross-day risk we've not
   stressed.** One day's good behavior is not evidence of
   multi-day robustness.
5. **The code-level early-day PEPPER experiment proposed in
   Section E has not been implemented.** It's a proposal, not a
   result.

## Files created in this pass

- `outputs/round_1/phase8_5/run_phase8_5.py`
- `outputs/round_1/phase8_5/controls_summary.md`
- `outputs/round_1/phase8_5/pepper_candidates.csv` / `.md`
- `outputs/round_1/phase8_5/ash_candidates.csv` / `.md`
- `outputs/round_1/phase8_5/combined_shortlist.csv` / `.md`
- `outputs/round_1/phase8_5/phase8_5_memo.md` (this file)

No edits to `src/core/config.py` or any other production module.
