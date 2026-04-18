# Phase D — PEPPER shortlist (3 candidates)

Three PEPPER candidates selected from the 37 evaluated. All share the
wall-based ASH leg (H1 / Alt leg). Full scored table in
[`pepper_candidates.md`](./pepper_candidates.md).

| Slot | Label | off_pep | local_pep | off_near_limit | off_max_short_fh | score |
|------|-------|--------:|----------:|---------------:|-----------------:|-------:|
| **Control (keep promoted)** | `F0_promoted` | +16 321.0 | +54 015.0 | 80 | 0 | +17 321.3 |
| **Clean improvement**      | `F5_buy1.5_sell3` | +18 661.0 | +92 938.0 | 184 | 0 | **+20 335.8** |
| **Higher-upside alternate**| `F6_alt_inv_buy1_sell3` | +22 107.0 | +129 453.0 | 345 | 0 | **+24 351.1** |

Scale context: the 1000-cadence (`off_*`) view inflates local PnL
roughly 9-10× over the IMC official environment. So an `off_pep`
lead of +2 340 (F5 vs F0) implies roughly **+200-300** of official
PEPPER PnL improvement over Promoted; an `off_pep` lead of +6 786
(F6 vs F0) implies roughly **+600-700** of official PEPPER PnL
improvement. Those are PROJECTIONS — official is the only ground
truth.

## Why these three?

### Control — `F0_promoted` (keep)

Unmodified Promoted PEPPER leg. Has to stay in the shortlist because:

1. It is the only candidate already validated on the official
   environment. Every other candidate is a projection from local
   signal.
2. It has the **lowest near-limit exposure** among the three (80 on
   1000-cadence). That is the safety floor.
3. `controls.md` shows Promoted is already **+353 official PEPPER**
   better than Baseline on the one official day we have. Nothing in
   this search suggests we should roll it back.

### Clean improvement — `F5_buy1.5_sell3`

```
PEPPER overrides vs Promoted:
    taker_edge_buy = 1.5
    taker_edge_sell = 3.0
# everything else identical to Promoted: linear_drift h=32,
# maker_edge=1.0, inventory_skew=2.0, flatten_threshold=0.7
```

This keeps every inventory-management knob at Promoted's shipped
values (skew=2.0, flatten=0.7). The **only** change is a per-side
taker-edge split: **tighter buy (1.5)**, **wider sell (3.0)**.
Empirical picture:

- `off_pep` = **+18 661** (+2 340 vs Promoted's +16 321).
- `local_pep` = **+92 938** (+38 923 vs Promoted's +54 015 — +72 %
  on the 3-day view).
- `off_near_limit` = **184** (vs Promoted's 80 and Alt's 331). Adds
  real exposure but stays well below Alt's tail-risk regime.
- `off_max_short_fh` = 0 (never goes short early — still clean on
  the Baseline failure mode). Same for Promoted and Alt.
- `off_pep_b0..b3` = all 0 because **the bot does not trade in
  bucket 0 on the 1000-cadence view** (see "Methodology caveats"
  below). This is a limitation of the view, not of the candidate.
- Markouts (`mk5`, `mk20`) comparable to Promoted.

Mechanism: the widened sell edge (3.0) prevents the bot from
selling on any ≤ 3-tick fluctuation above fair. On a market with a
persistent upward drift of ~0.001/tick this filters out almost all
wrong-side sells while leaving the tight (1.5) buy edge firing
aggressively on dips. Functionally it is "Promoted's sell discipline,
cranked up by one taker-edge unit."

### Higher-upside alternate — `F6_alt_inv_buy1_sell3`

```
PEPPER overrides vs Promoted:
    taker_edge_buy = 1.0
    taker_edge_sell = 3.0
    inventory_skew = 1.0       # = Alt
    flatten_threshold = 0.9    # = Alt
```

This composites the F5 taker asymmetry with Alt's inventory / flatten
profile (`skew=1.0 + flatten=0.9`, which lets the bot ride bigger
long positions into the drift). Effectively "Alt PEPPER +
asymmetric buy 1.0 / sell 3.0".

- `off_pep` = **+22 107** (+1 020 vs Alt's +21 087, +5 786 vs
  Promoted's +16 321). Highest PEPPER PnL in the search.
- `local_pep` = **+129 453** (+50 609 vs Alt, +75 438 vs Promoted —
  the largest 3-day improvement seen). This is a meaningful signal
  of robustness: the ranking matches across both views.
- `off_near_limit` = **345** (vs Alt's 331). Inherits Alt's
  near-limit exposure PLUS a marginal extra from the asymmetric
  edges. This is the real cost — on a day with less drift, the
  bigger long would be a liability.
- `off_max_short_fh` = 0 (no early short risk).

Why include this despite the near-limit cost? Because on the one
official day we have, Alt (which has the same flatten profile)
already **did** clear +3 040 total PnL with 22 near-limit snapshots.
The F6 candidate is a strict superset of Alt — same inventory, a
more defensible taker profile. If IMC re-runs on a similar
drift-heavy day, F6 should do everything Alt does, better. If IMC
runs on a flat / reversing day, F6 will lose inventory fast
(same as Alt would).

## Why NOT other candidates?

### Early-window families (F1, F2, F4) scored identical to Promoted

Every F1 / F2 / F4 candidate has `off_pep = +16 321`, identical to
Promoted. Reason: **on local day 0 at 1000-cadence, the bot's first
trade is at t ≈ 216 000** (the linear_drift estimator needs ~30-40
snapshots to build a usable slope, and at 1000-tick cadence that is
30-40 k ticks; combined with the wide 13-tick PEPPER spread and the
2.0 taker threshold, nothing crosses earlier). The early-window
overrides (`early_window ∈ {10k, 25k, 50k}`) therefore fire only
inside a zero-trade region. F2's short cap is a no-op because the
bot never goes short in the first half anyway; F4's short-skew
multiplier has no short to amplify. **This is a property of the
data/cadence, not of the mechanism.** See "Methodology caveats"
below.

On the **3-day full-cadence view** (100-tick spacing, denser fills),
F1 candidates do show modest lift (`F1_sellwiden_N25k_b2` local_pep
+921 over Promoted). But the gain is small and not worth promoting
over F5, which achieves much larger gains with a simpler mechanism.

### F3 (shorter history_length) is strictly worse

- `F3_h16`: off_pep = +14 729 (−1 592 vs Promoted).
- `F3_h24`: off_pep = +15 561 (−760 vs Promoted).

Faster fair value is not what the official Baseline needed — the
forensic said Baseline's `residual_mean` was already only 0.006
different from Promoted's. Cutting history further just adds noise.

### F5 mid-range (`buy0.5_sell2.5`, `buy1_sell2.5`, `buy1.5_sell2.5`)

All three cluster at `off_pep = +18 661` — same as `F5_buy1.5_sell3`
on 1000-cadence but with smaller 3-day lift (local_pep 79-81 k vs
93 k for sell=3). We prefer `sell3` as the clean candidate because
it has the largest 3-day margin without changing `off_pep` cost.

### Lower-cost composites (`F6_promoted_flat09`, `F6_promoted_flat08`)

- `F6_promoted_flat09`: off_pep +16 373.5 (+52 vs Promoted),
  off_near_limit **50** (BELOW Promoted's 80). Interesting but small.
- `F6_promoted_flat08`: off_pep +16 373.5, near_limit 50. Tied.

The `flat09` variant has a real safety benefit (fewer near-limit
snapshots) at essentially the same PnL. It's a candidate for a
**later** minor tweak to Promoted itself if we ever want to increase
its safety margin. Not promoted in this pass because it does not
meaningfully move the PnL needle.

## Methodology caveats (read before acting)

1. **Local day 0 ≠ official day.** Our 1000-cadence view is local
   day 0 decimated, NOT the IMC live data. Absolute PnL magnitudes
   differ by ~9-10× between the two.
2. **Early-bucket behavior is invisible at 1000-cadence.** Our bot
   takes 200+ snapshots to start trading in the decimated view.
   The IMC official environment has additional signal (tighter
   spreads, different book structure, or a real drift starting
   earlier) that fires bucket-0 trades for every variant. Our local
   1000-cadence view CANNOT surface early-bucket candidate
   differences.
3. **F5 / F6 wins are projections, not observed.** On local data F5
   beats Promoted and F6 beats Alt. Whether that carries to the
   official environment depends on the fill model agreement, which
   the one official run does not corroborate for these untested
   configs.
4. **Near-limit counts at 1000-cadence are 3-4× the official
   count.** Alt's `off_near_limit = 331` at this cadence corresponds
   to 22 of 250 snapshots (8.8 %) on the official bucket 50-75k.
   Mentally scale near-limit counts down by 10× to compare with
   official.
5. **Single-official-day risk.** All four control variants have been
   tested on exactly one official day. Any candidate promoted from
   this search inherits that single-point risk.
