# Phase E — Final recommendation

## One-screen answer

| Question | Answer |
|---|---|
| Best PEPPER candidate found? | **`F5_buy1.5_sell3`** as the clean improvement; **`F6_alt_inv_buy1_sell3`** as the higher-upside alternate. |
| Does it meaningfully fix the early-day problem? | **Cannot be confirmed from this local search.** The local 1000-cadence view does not trade in bucket 0 (estimator warm-up dominates), so early-window knobs (F1 / F2 / F4) could not differentiate from Promoted. The mechanism in F5 (wider sell edge) is **directionally aligned** with the Baseline forensic, but proof requires an official run. |
| ASH leg to pair with any new PEPPER? | **Alt / H1 wall-based ASH** (`wall_mid, taker=0.5, maker=1.5, skew=4.0, flatten=0.7, h=48`). No change from H1. |
| Prepare a new upload candidate now? | **YES — one.** A new `F5 + wall-based ASH` bundle is the one upload justified by this pass. `F6` is a second optional upload if there is slot budget; it imports Alt's tail risk by design. |
| Current **Promoted** should remain unchanged? | **YES.** No change to the Promoted engine config. It remains the safety-floor control. |
| Next IMC upload shortlist? | See §3 below. |

## 1. Headline numbers

| Candidate | off_pep | local_pep | off_near_limit | Δ off_pep vs Promoted | Projected Δ official PEPPER |
|-----------|--------:|----------:|---------------:|----------------------:|----------------------------:|
| Promoted (control)  | +16 321.0 | +54 015.0 |  80 | —        | 0 (observed +1 797) |
| Alt (control, known official) | +21 087.0 | +78 844.0 | 331 | +4 766   | +260 (observed +2 057) |
| **F5_buy1.5_sell3** | +18 661.0 | +92 938.0 | 184 | **+2 340** | ~**+200-300** |
| **F6_alt_inv_buy1_sell3** | +22 107.0 | +129 453.0 | 345 | **+5 786** | ~**+600-700** |

Projection uses the observed Alt local-to-official ratio (~10×) to
translate a 1000-cadence PnL delta into an expected official PnL
delta. Ratios are noisy at single-point scale; these are
order-of-magnitude guides only.

## 2. Promoted vs Alt vs H1 unchanged

Per the scope rules, zero changes to the engine factories
`round1_promoted_engine_config`, `round1_alt_engine_config`,
`round1_h1_engine_config`, or to `round1_baseline_engine_config`.
No submission bundle was re-exported; the three currently-uploaded
bundles remain exactly as shipped.

## 3. Next IMC upload shortlist

Three candidates, ordered by risk budget:

| Slot | Config | Base | Status |
|------|--------|------|--------|
| **A — keep**  | Promoted (as currently uploaded)  | `round1_promoted_engine_config` | Already in the environment. Baseline safety floor. |
| **B — keep**  | H1 hybrid (as currently uploaded) | `round1_h1_engine_config`       | Already in the environment. Current best uploaded at +2 780 total. |
| **C — NEW**   | `F5_buy1.5_sell3` + Alt ASH       | **new factory required**        | Clean PEPPER improvement: same inventory profile as H1, add asymmetric taker edges (1.5 buy / 3.0 sell). |
| **D — optional NEW** | `F6_alt_inv_buy1_sell3` + Alt ASH | **new factory required** | Higher-upside. Matches Alt's flatten/skew PLUS asymmetric taker. Only promote if upload slot budget allows and we accept Alt-level near-limit exposure. |

### Why not replace anything?

- **Promoted** is the only shipped variant that has **zero near-limit
  exposure** on the one official day. If we ever need a
  tail-protected fallback this is it.
- **H1** is the shipped best real upload (+2 780). Replacing it
  is not justified because the `F5` and `F6` candidates are
  *projections*; they have not been verified on an official run.
- Promoted / Alt / H1 already cover 3 distinct risk profiles
  (clean / upside / hybrid). C or D is additive, not a replacement.

## 4. If we can only upload ONE new candidate

**Upload `F5_buy1.5_sell3` + Alt ASH.**

Rationale in descending order of weight:

1. **Strictly dominates Promoted on 3-day local (+72 %)** while
   keeping Promoted's flatten / skew profile — we are changing the
   smallest possible surface area (two new fields) to test a
   specific hypothesis. If this upload performs worse than Promoted
   on official, we know the single tested change (asymmetric taker
   edges) is the cause, and we can revert cleanly.
2. **Directionally aligned with the forensic.** The official-day
   Baseline failure was "one extra sell in PEPPER bucket 0." F5
   widens the sell edge; this is the surgical fix to that failure
   mode.
3. **Near-limit cost is ~2× Promoted (184 vs 80), still ~2× LOWER
   than Alt (331).** Sits between the two known risk profiles.
4. **Mechanism is testable in isolation.** If the next official
   run shows the same F5 candidate improves PEPPER PnL with
   unchanged near-limit count, we have proof of the mechanism and
   can think about layering flatten=0.9 on top for Round 2.

## 5. What this pass could NOT answer

- **Whether the Baseline-specific early-bucket sell problem is
  directly fixed by any of the early-window families (F1, F2, F4).**
  Our local 1000-cadence view does not fire trades in bucket 0, so
  these families registered as no-ops. An authoritative test needs
  either (a) a second official run with one of these configs or
  (b) a denser local replay that matches official bucket-0 fill
  density.
- **The absolute official PnL impact of F5 / F6.** Our best
  projection uses a single-point local-to-official ratio (~10×) and
  is an order-of-magnitude guide at most.
- **Robustness across unseen days / directions.** All local days and
  the one official day had the same +0.001/tick PEPPER drift. If an
  unseen day has a flat or reversing drift, F5 / F6's widened sell
  edge would reduce capture on the downside and produce long-
  accumulation drag. This is an unknowable risk from the current
  data.

## 6. Action items (if implemented)

None executed in this pass. If Slot C is to be uploaded:

1. Add a new factory, e.g. `round1_f5_engine_config`, in
   `src/core/config.py` (analogous to `round1_h1_engine_config`)
   with the `F5_buy1.5_sell3` PEPPER leg + wall-based ASH leg.
2. Add a variant to `src/scripts/round_1/export_round1_submission.py`
   so `--variant f5` exports a new bundle.
3. Extend `tests/test_submission_export.py` with a smoke test.
4. Export and validate the bundle (size / suite green).

All of the above is **deferred until explicit user approval**, per
the scope rules of this pass. No engine factories, no submission
bundles, and no shipped files were changed.

## 7. Engine surface added by this pass

The PEPPER strategy families required 8 additive `ProductConfig`
fields and ~30 lines of time-conditional branching in
`SignalEngine.build_market_making_intent`. All fields default to
neutral no-ops; the full test suite is green at 434 tests (415
pre-existing + 19 targeted new ones) and byte-compares on all
existing configs confirm zero behavior change when the new knobs are
at defaults. The 8 fields:

```
taker_edge_buy, taker_edge_sell        # Family 5
early_window                           # common gate
early_taker_edge_buy,                  # Family 1
early_taker_edge_sell
early_short_cap                        # Family 2
early_short_skew_mult,                 # Family 4
early_short_flatten
```

These exist as engine knobs and have tests; they have not been used
in any shipped config and will not be unless explicitly promoted.
