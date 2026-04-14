# Round 1 — Phase 5 Review Shortlist (revised)

Phase 5 was a **review-only phase**: review packs for each Phase-4
shortlist candidate, plus a focused day-boundary / EOD diagnostic
for PEPPER. No new sweep grids were run.

> **Post-official update:** Alt (+3 040) > Promoted (+2 518) >
> Baseline (+2 276) on the official site — order matches this
> shortlist. Promoted's ASH leg (ewma_mid, t=0.25) underperformed
> Baseline's ASH leg on official PnL, which is flagged for review in
> `docs/round_1/official_results_analysis.md`. Shortlist logic is
> not modified by this memo.

## Headline changes vs the Phase-4 shortlist

- **ASH promoted default flips from C1 → C2.** C1 keeps a ~17 %
  raw-PnL lead but C2 wins on every robustness axis: tighter cross-
  day PnL variance (±28 vs ±455), better markouts at every horizon,
  and zero near-limit steps. C1 becomes the higher-upside alternate
  that gets uploaded after C2 validates on the official site.
- **PEPPER promoted default flips from C1 → C1b.** The signals are
  identical (same edges, same markouts, same autocorrelation
  profile); C1 merely has a softer `flatten_threshold` and therefore
  spends 2.3× more steps near the position limit for only +4 % more
  PnL. C1b is the cleaner production default.
- **PEPPER C2 is explicitly confirmed as real edge, not an
  artefact.** Phase-5 question #1 resolves in favour of keeping it as
  a higher-upside alternate: PnL is not time-clustered, markouts
  match C1, and the entire uplift is inventory-driven rather than
  signal-driven. Near-limit exposure (24 %) is the risk to accept.
- **PEPPER day-boundary framing corrected.** The Phase-2 "+1 000
  overnight jump" hypothesis was a misreading; PEPPER mids are
  continuous across day boundaries in the sample data, so a
  hypothetical flatten-before-boundary overlay would *cost* PnL on
  every candidate (−1 100 to −1 275). **No EOD flatten policy is
  recommended.**

## Revised shortlist (for Phase 6)

### ASH_COATED_OSMIUM

| # | Role | FV | history | maker | taker | skew | flatten | PnL | Near-limit | Notes |
|---|------|----|---------|-------|-------|------|---------|-----|------------|-------|
| **C-ASH-A (promoted)** | Robust default | ewma_mid | 48 | 1.0 | 0.25 | 4.0 | 0.7 | +6 447 | **0** | Cross-day σ ≈ 28 (1.3 % of mean). Best markouts at every horizon. No inventory-pinning path. |
| C-ASH-B (alt) | Higher-upside alternate | wall_mid | 48 | 1.5 | 0.5 | 4.0 | 0.7 | +7 747 | 110 | +20 % more PnL on the same sample; taker-heavier edge so more dependent on the local fill model. Upload after C-ASH-A confirms. |

### INTARIAN_PEPPER_ROOT

| # | Role | FV | history | maker | taker | skew | flatten | PnL | Near-limit | Notes |
|---|------|----|---------|-------|-------|------|---------|-----|------------|-------|
| **C-PEP-A (promoted)** | Robust default | linear_drift | 32 | 1.0 | 2.0 | 2.0 | **0.7** | +54 015 | 755 (2.5 %) | Same markouts as C-PEP-B with 57 % less limit pinning. Cleanest production candidate. |
| C-PEP-B (alt) | Higher-upside alternate | linear_drift | 32 | 1.0 | 2.0 | **1.0** | **0.9** | +78 844 | 7 224 (24 %) | Real edge (steady, non-clustered PnL; same markouts). Trade-off is inventory pinning. Directional bet on drift persisting. |
| C-PEP-C (ctrl) | Ultra-safe control | linear_drift | 32 | 1.0 | 2.0 | **4.0** | 0.8 | +35 201 | **0** | 63 % of C-PEP-A's PnL for zero near-limit exposure. Useful as baseline or as a diagnostic third submission. |

## Answers to the four Phase-5 questions

1. **Is PEPPER C2's +78 844 PnL real edge or a limit-pinning
   artefact?** — **Real edge.** Tail-20 % PnL share ≈ 22 %,
   lag-1 autocorr −0.446, markouts identical to C1 at every horizon.
   The +40 % PnL comes from more inventory exposure to the same
   signal, not from a concentrated segment.
2. **C1 vs C1b for PEPPER — which is the cleaner production
   candidate?** — **C1b.** Signal quality is identical to C1 (same
   edge, same markouts, same autocorr), but C1b spends 57 % fewer
   steps at the limit. C1's extra +4 % PnL comes from a more
   permissive flatten threshold, not from better signal quality.
3. **PEPPER day-boundary behaviour?** — **No overnight jump exists**
   in the sample data. Mids are continuous (day -2 close 11 001,
   day -1 open 10 998). The +1 000-per-day *mean shift* in the
   dossier is from intraday drift, not an overnight discontinuity.
   Hypothetical flatten-before-boundary overlay hurts every
   candidate by ~−1 100 to −1 275.
4. **Is ASH C1 genuinely better than C2, or just more dependent on
   local fill assumptions?** — **Mixed.** C1 has genuinely higher
   PnL across every day, but it is 99.7 % taker fills with
   taker_edge sitting at the internal-peak point. C2 has worse PnL
   but materially better markouts per trade and zero limit
   pressure. The plan's "do not ship candidates that depend heavily
   on local fill assumptions" argues for C2 as the default and C1 as
   the alternate.

## Questions that stayed closed

- No new fair-value family was tested.
- No new edge / history / skew / flatten values were swept.
- No Phase-4 claim was re-opened. The Phase-4 shortlist remains the
  parent; Phase-5 only re-ranks and annotates.

## Phase-6 upload ordering (recommendation, not decision)

Per the plan, ordering is Phase 6's to decide, but based on Phase-5
evidence:

1. **Baseline / control.** The Phase-3 MVB config (ASH wall_mid at
   Phase-2 defaults, PEPPER linear_drift at Phase-2 defaults).
   Establishes the reference.
2. **Promoted.** C-ASH-A + C-PEP-A. Expected to clearly beat
   baseline on both products.
3. **Higher-upside.** C-ASH-B + C-PEP-B. Tests whether the local
   fill-model assumptions carry over to the official exchange.
4. (Optional) C-PEP-C as a diagnostic fallback if we want a third
   slot focused on inventory robustness.

## Artefacts

- `outputs/round_1/review_packs/` — six packs (one per candidate),
  each with `summary.json`, `series.json`, `trades.json`,
  `manifest.json`, `notes.md`. Charts rendered for the four
  promoted/alternate candidates.
- `outputs/round_1/notes/phase5_pack_stats.md` — per-candidate
  diagnostic table (per-day PnL, lag-1 autocorr, tail-20 % share,
  EOD positions, maker share).
- `outputs/round_1/notes/phase5_pepper_day_boundary.md` — PEPPER EOD
  detail + flatten-overlay analysis.
- `outputs/round_1/research/{ash_c1,ash_c2,pepper_c1_c1b,pepper_c2,
  pepper_c3}_review_notes.md` — one interpretation note per
  candidate.

## Acceptance (Phase-5 plan)

| Criterion | Status |
|-----------|--------|
| Candidates evaluated visually and mechanically | PASS — review packs + numeric diagnostics + per-candidate notes |
| Weak / noisy candidates filtered out | PASS — ASH C1 demoted to alternate; PEPPER C1 demoted to alternate in favour of C1b |
| Surviving shortlist small and explainable | PASS — 2 ASH + 3 PEPPER, each with explicit role |
| No broad retuning | PASS — no new sweeps; one targeted day-boundary diagnostic only |
