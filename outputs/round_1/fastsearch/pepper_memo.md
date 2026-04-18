# Phase B — PEPPER memo (concise)

## How PEPPER moves

**Deterministic intraday drift** of roughly +0.001 price units per
timestamp (≈ +24 to +26 ticks per 25 000-timestamp bucket on the
official day, flat within ±1 tick across all four buckets). Spread
≈ 13–14 ticks. Volatility around the drift is modest.

The drift is **continuous across the session** — there is no visible
"open" or "close" regime shift inside a day; the market is just a
slow-upward conveyor belt with an idiosyncratic spread. Source:
`outputs/round_1/official_results/analysis/bucket_memo.md` §4,
corroborated by `outputs/round_1/research/intarian_pepper_root_dossier.md`.

## What the fair value probably is

The product's fair value tracks the rolling linear trend of mid-price.
`linear_drift` with a `history_length` around 32 locks on to the
+0.001/tick slope quickly; `history_length=48` is measurably slower
(that is the Baseline-vs-Promoted distinction). Residual means on the
official day:

| Variant | h  | residual_μ b0 | residual_σ b0 |
|---------|----|--------------:|---------------:|
| Baseline | 48 | +0.155 | 1.054 |
| Promoted | 32 | +0.149 | 1.021 |
| Alt      | 32 | +0.149 | 1.021 |

In other words the fair estimate is **NOT catastrophically wrong** for
Baseline — it's about **0.15 ticks above mid** in bucket 0, same as the
others, and the estimator is essentially tracking the drift. The
difference is responsiveness: Baseline's estimator lags by ~0.1-0.2
ticks more in the transient, which combined with `taker_edge=1.0`
becomes material.

## What the Baseline did wrong early

From the forensic drill-down
(`outputs/round_1/official_results/analysis/bucket_memo.md` §4):

1. **Taker edge too tight.** `taker_edge=1.0` fires on ~1-tick
   deviations. On a slowly-drifting market whose mid wobbles ±1-2
   ticks around the slope, that guarantees noise-level sell triggers.
   Baseline's bucket 0 trigger count is **2 buy / 3 sell** — wrong
   direction for a rising market.
2. **Position −8 into the drift.** Those extra sells compound into a
   net short of 8 at t=25 000. The subsequent +24-tick drift then
   marks the short to market **negatively** for the rest of bucket 1.
3. **Cumulative PEPPER hits −114 at t=40 000** before the inventory
   flips long (around t=45 000 when the bot finally unwinds). Only
   after that does the same continuing drift start *helping* the MTM.
4. **Bucket-1 through bucket-3 are mechanical.** They are the
   consequence of whichever inventory the bot ended bucket-0 with.
   Promoted / Alt end bucket-0 at **+1** (flat), so by bucket-2 they
   are long +32 / +27 and the drift is paying them. Baseline ends
   bucket-0 at **−8** and spends bucket-1 digging out.

**The bucket-3 "jump" at t≈50 000 is NOT a market regime change.** It
is just Baseline's inventory finally going long enough for the same
drift to stop hurting and start helping.

## What PEPPER interventions are most plausible

The forensic pinpoints **bucket 0 of PEPPER** as 100 % of the
Promoted-vs-Baseline gap that is attributable to PEPPER. Everything
downstream of bucket 0 is mechanical. So the high-leverage
interventions are the ones that directly change **bucket-0
entry quality / inventory**:

1. **Family 1 — Early sell suppression.** Widen the *sell* taker edge
   only in the first ~25k ticks (leave the buy side at promoted's
   2.0). This directly removes the "one extra sell" that ends bucket
   0 at −8 vs +1. Cost: might also miss a genuine bucket-0 sell if the
   drift reverses (unlikely on this data, but a source of
   local-vs-official mismatch).
2. **Family 2 — Early short-cap.** Bluntly forbid going beyond a
   given short inventory in the first ~25k ticks. Guarantees
   entry-bucket floor is ≥ cap. Cost: the bot cannot take a genuine
   early sell opportunity either; if the drift weakens the bot will
   be carrying a larger long into bucket 1.
3. **Family 5 — Buy-biased asymmetric taker edge.** Same logical
   direction as Family 1 but permanent (all-day), not time-gated.
   Keeps a tight buy edge (1.0 or tighter) to accumulate aggressively
   on the drift AND a wider sell edge (2.5-3.0) to avoid the
   wrong-side sells.
4. **Family 4 — Stronger short recovery early.** If we DO take a few
   early sells, recover faster (higher skew / earlier flatten on the
   short side). A partial remedy; less surgical than Family 2.
5. **Family 3 — Faster fair value.** Reducing `history_length` below
   32 (h=16, h=24) is a related hypothesis; on the official data we
   can't directly test a time-conditional history change (the
   estimator carries state), so this is tested **full-day** only.
   The risk is that h=16 over-reacts to noise.

Interventions 1 and 5 (widen sell edge) are the most surgical because
the forensic identified the proximal cause as **one extra sell in
bucket 0**. Intervention 2 (hard cap) is the sharpest backstop.

## What remains uncertain on PEPPER

- **Asymmetry in the data.** The +0.001/tick drift is a single
  data-generating process. If the official live round runs on a
  different day with a *negative* drift, every "widen sell edge"
  candidate becomes a liability and a *widen buy edge* candidate
  becomes the right move. We can only guarantee directional
  robustness across the 3 local days, not across unseen days.
- **Local-vs-official fill disagreement.** Phase-8.5 saw **+78 844**
  local PEPPER PnL for Alt vs only +2 057 official PEPPER. The
  local model over-fills the drift by about 40×. We treat the
  local score only as a ranking signal, not as an absolute PnL
  forecast.
- **Near-limit tail risk.** Alt PEPPER's `flatten_threshold=0.9` +
  `inventory_skew=1.0` rides a larger long into the drift for more
  upside — but also spent 22 of 250 snapshots near the +40 limit in
  bucket 2 on the official day. If the drift stalls while at +40,
  the single-data-point MTM win becomes a liability. Candidates
  that recover Alt's upside *without* the near-limit tail are
  strictly better.
- **No second official day.** Everything here is triangulating off
  one official run per variant. The fastsearch candidates will be
  compared across three local days to partially mitigate this, but
  the official cadence remains a single observation.
