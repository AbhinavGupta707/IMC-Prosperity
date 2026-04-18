# Round 1 — Forensic Drill-Down on the "Flat First Half" (Diagnostic Only)

Scope: why does the **baseline** variant accumulate almost no PnL in
the first 50 000 timestamps of the official Round-1 run and then
"jump" later? What do the promoted / alt variants do differently?

This is a diagnostic pass. **No configs are changed**, no sweeps are
started, no promotions are proposed.

- Raw tables: [`bucket_breakdown.csv`](./bucket_breakdown.csv) / [`bucket_breakdown.md`](./bucket_breakdown.md)
- Script: [`forensic_drilldown.py`](./forensic_drilldown.py)
- Evidence: primary = `<variant>/<id>.json` (`activitiesLog`);
  support = `<variant>/<id>.log` (`tradeHistory`), `<variant>/<id>.py`
  (configs).

## TL;DR

1. **The "flat first half" is almost entirely a PEPPER problem on
   baseline.** ASH PnL is evenly distributed across the four 25k
   buckets for every variant (~+160 to +310 per bucket). Baseline
   PEPPER is underwater (-114) as late as t=40 000 before rebounding.
2. **Root cause:** baseline PEPPER runs `linear_drift` with
   `history_length=48` and `taker_edge=1.0`. Combined, the fair
   estimate lags the +0.001/tick intraday drift and the sensitive
   trigger threshold lets the bot SELL into the rising market early.
   Baseline ends bucket 1 at position **−8** (net short) versus
   promoted / alt at **+1** (net flat).
3. **What changes at t ≈ 50 000 is NOT the market.** The drift
   (+24 points / 25k bucket), spread (~13), and volatility are
   essentially constant across all four buckets. What changes is
   **baseline's own inventory**: by t ≈ 45 000 it has unwound the
   short and is net long, so the same continuing drift finally marks
   its inventory UP instead of down.
4. **Promoted and alt monetize earlier because their PEPPER config
   filters out the early bad sells.** `taker_edge=2.0` + shorter
   `history_length=32` keeps them flat or mildly long through bucket
   1 and net long (+27 / +32) into bucket 2. They capture the same
   bucket-3 drift gains but without the bucket-1 drawdown first.
5. **ASH behaves symmetrically** for all three variants — the "first
   half flat" story does not apply to ASH. The inter-variant ASH PnL
   gap is driven by maker-edge width (Alt's 1.5 vs Baseline's 1.0 vs
   Promoted's 1.0), not by first-half vs second-half asymmetry.

## 1. Bucketed PnL attribution

Totals from `activitiesLog.profit_and_loss` at bucket boundaries.

| Variant | 0-25k | 25-50k | 50-75k | 75-100k | **Total** | First-half share |
|---------|------:|-------:|-------:|--------:|----------:|-----------------:|
| **Baseline** | +118.07 | +272.77 | +1 187.86 | +697.46 | **+2 276.15** | **17.2 %** |
| **Promoted** | +190.40 | +578.01 | +1 253.52 | +496.17 | **+2 518.11** | 30.5 % |
| **Alt** | +250.56 | +524.35 | +1 424.83 | +840.48 | **+3 040.22** | 25.5 % |

### Per-product split

ASH-only PnL per bucket (first half is *not* anomalous for any
variant on ASH):

| Variant | 0-25k | 25-50k | 50-75k | 75-100k | ASH total |
|---------|------:|-------:|-------:|--------:|----------:|
| Baseline | +175.27 | +160.66 | +290.36 | +205.97 | +832.25 |
| Promoted | +159.50 | +171.41 | +310.30 | +79.69 | +720.91 |
| Alt      | +219.66 | +194.25 | +340.92 | +227.98 | +982.81 |

PEPPER-only PnL per bucket (baseline's flatness is concentrated
here):

| Variant | 0-25k | 25-50k | 50-75k | 75-100k | PEPPER total | First-half share |
|---------|------:|-------:|-------:|--------:|-------------:|-----------------:|
| **Baseline** | **−57.20** | +112.11 | +897.50 | +491.49 | **+1 443.90** | **3.8 %** |
| Promoted | +30.90 | +406.60 | +943.22 | +416.48 | +1 797.20 | 24.3 % |
| Alt      | +30.90 | +330.10 | +1 083.91 | +612.50 | +2 057.41 | 17.5 % |

Finer 10k-step cumulative PnL confirms the mid-day inflection for
baseline PEPPER (drops to **−114 at t=40 000**, rebounds to +57 by
t=50 000, +721 by t=70 000):

```
Baseline PEPPER cum PnL:  t=10k +37 | t=20k −58 | t=30k −74 | t=40k −114 | t=50k +57 | t=70k +721
Promoted PEPPER cum PnL:  t=10k +40 | t=20k  −7 | t=30k +56 | t=40k +130 | t=50k +441 | t=70k +1171
Alt      PEPPER cum PnL:  t=10k +40 | t=20k  −7 | t=30k +56 | t=40k +110 | t=50k +364 | t=70k +1188
```

## 2. Bucketed trade / execution stats

Key numbers from `tradeHistory`. "Maker/Taker" classified by
comparing trade price to best-bid / best-ask at the same timestamp:
a buy at price ≥ best_ask (or a sell at price ≤ best_bid) is
classified as taker; everything else is maker. "Final pos" is the
running position at the last trade inside the bucket (carried
forward if no trades).

### PEPPER

| Variant | Bucket | Trades | Maker/Taker | Avg size | Final pos | Buy trig | Sell trig |
|---------|--------|-------:|------------:|---------:|----------:|---------:|----------:|
| **Baseline** | **0-25k** | **9** | **4 / 5** | 4.67 | **−8** | **2** | **3** |
| Baseline | 25-50k | 14 | 6 / 8 | 4.14 | +18 | 6 | 2 |
| Baseline | 50-75k | 14 | 5 / 7 | 4.79 | +23 | 5 | 3 |
| Baseline | 75-100k | 12 | 5 / 7 | 4.92 | −2 | 2 | 5 |
| **Promoted** | 0-25k | 7 | 4 / 3 | 4.71 | **+1** | 2 | 2 |
| Promoted | 25-50k | 13 | 6 / 7 | 4.08 | **+32** | 6 | 2 |
| Promoted | 50-75k | 12 | 3 / 7 | 5.25 | +7 | 5 | 2 |
| Promoted | 75-100k | 12 | 5 / 7 | 4.92 | −18 | 2 | 3 |
| **Alt** | 0-25k | 7 | 4 / 3 | 4.71 | **+1** | 2 | 2 |
| Alt | 25-50k | 14 | 6 / 8 | 4.14 | +27 | 6 | 2 |
| Alt | 50-75k | 14 | 4 / 8 | 4.93 | +22 | 5 | 2 |
| Alt | 75-100k | 12 | 5 / 7 | 4.92 | −3 | 2 | 3 |

### ASH

| Variant | Bucket | Trades | Maker/Taker | Avg size | Final pos | Buy trig | Sell trig |
|---------|--------|-------:|------------:|---------:|----------:|---------:|----------:|
| Baseline | 0-25k | 22 | 16 / 4 | 4.50 | −17 | 2 | 4 |
| Baseline | 25-50k | 21 | 14 / 6 | 5.10 | −10 | 4 | 2 |
| Baseline | 50-75k | 27 | 15 / 8 | 5.22 | +21 | 4 | 2 |
| Baseline | 75-100k | 20 | 11 / 7 | 5.85 | −12 | 2 | 5 |
| Promoted | 0-25k | 21 | 16 / 3 | 4.52 | −13 | 2 | 3 |
| Promoted | 25-50k | 20 | 14 / 5 | 5.10 | −11 | 3 | 0 |
| Promoted | 50-75k | 22 | 15 / 3 | 4.82 | +25 | 4 | 0 |
| Promoted | 75-100k | 18 | 11 / 5 | 5.56 | −25 | 2 | 3 |
| Alt | 0-25k | 22 | 16 / 4 | 4.59 | −19 | 2 | 5 |
| Alt | 25-50k | 21 | 14 / 6 | 5.10 | −12 | 4 | 2 |
| Alt | 50-75k | 27 | 15 / 8 | 5.22 | +19 | 4 | 2 |
| Alt | 75-100k | 20 | 11 / 7 | 5.85 | −14 | 2 | 5 |

**Time-near-limits**: with `position_limit=50` and a 80 % threshold,
no bucket has any single snapshot with |pos| ≥ 40 for any variant
**except** Alt PEPPER 50-75k, which spends **22 of 250 snapshots**
(~9 %) ≥ 40 long. That matches Alt PEPPER's higher flatten_threshold
(0.9) letting it ride bigger longs. Neither baseline nor promoted
gets near the limit on this day.

## 3. Fair-vs-market diagnostics

Computed from each candidate's own estimator
(baseline ASH → `wall_mid`, promoted ASH → `ewma_mid(α=0.3)`,
alt ASH → `wall_mid`; all PEPPER legs use `linear_drift` with the
per-variant history length). Units: price ticks.

| Variant | Bucket | Product | avg(fv−ask) | avg(bid−fv) | Buy trig | Sell trig | residual μ | residual σ |
|---------|--------|---------|------------:|------------:|---------:|----------:|-----------:|-----------:|
| Baseline | 0-25k  | ASH | −8.11 | −8.22 | 2 | 4 | +0.06 | 1.37 |
| Baseline | 0-25k  | PEP | −6.72 | −7.02 | 2 | 3 | +0.16 | 1.05 |
| Promoted | 0-25k  | ASH | −8.15 | −8.13 | 2 | 3 | +0.01 | 1.04 |
| Promoted | 0-25k  | PEP | −6.73 | −7.01 | 2 | 2 | +0.15 | 1.02 |
| Alt      | 0-25k  | ASH | −8.11 | −8.22 | 2 | 5 | +0.06 | 1.37 |
| Alt      | 0-25k  | PEP | −6.73 | −7.01 | 2 | 2 | +0.15 | 1.02 |

Observations:

- **Fair-minus-best-ask ≈ best-bid-minus-fair ≈ −(spread/2)** across
  all variants / buckets. Both products maintain a fair estimate
  roughly centred in the spread.
- **residual_std is lower for ewma_mid (≈1.0) than wall_mid
  (≈1.37)** on ASH, consistent with the design — EWMA is a smoother
  estimator. That lower noise does NOT translate into extra PnL on
  this official day, because ASH trade count is nearly identical
  across the three variants (80–90).
- **Baseline PEPPER 0-25k has 3 sell triggers vs only 2 buy triggers
  (inverted direction)** on a market with a steady upward drift —
  this is the "selling into the drift" signature.
- **Promoted and Alt PEPPER are symmetric (2 buy / 2 sell) in 0-25k
  and buy-heavy (6 buy / 2 sell) in 25-50k**, which is the right
  direction for a +0.001/tick drifting product.

## 4. Baseline-specific explanation

**Which product causes the flat first half?** INTARIAN_PEPPER_ROOT.
ASH contributes +336 of its own first-half PnL, in line with the
promoted/alt ASH legs. PEPPER contributes **+55 of a day-total
+1 444** (3.8 %). The flatness is entirely on PEPPER.

**What's the failure mode?** Low-quality trades plus wrong-direction
inventory, not lack of activity:

- **Trade count is NOT the bottleneck.** Baseline makes 9 PEPPER
  trades in 0-25k (promoted makes 7, alt makes 7). Baseline trades
  *more*, not less.
- **Trade quality / direction is the bottleneck.** Baseline sells 25
  PEPPER units and buys 17 in 0-25k — a net short of 8 into a
  market drifting +0.001/tick. By t=40 000 cumulative PEPPER PnL is
  at its worst (−114) because the short position is marked to
  market against the continuing drift.
- **Inventory drag dominates.** The first-half PEPPER PnL sign is
  driven by MTM on the inherited short position, not by bad spread
  capture per trade. Compare realized spread captured in 75-100k
  (when baseline is near-flat inventory): +492 / 12 trades ≈ +41 /
  trade. That is PROFITABLE per trade once inventory isn't fighting
  the drift.
- **The fair-value estimator lags, but not by much.** PEPPER
  `residual_mean` is +0.16 in 0-25k for baseline (fair is 0.16
  points above mid, consistent with a one-step-ahead forecast of a
  +0.001/tick drift × ~50-100 recent ticks of lookback). It's not
  catastrophically wrong — it's slightly behind, and combined with
  a taker_edge of 1.0 (one tick), the bot will trigger on even
  small deviations in the wrong direction.
- **Conservatism is NOT the issue.** Baseline PEPPER's maker_edge
  (1.5) is WIDER than promoted/alt (1.0); its flatten_threshold
  (0.8) is LOOSER than promoted (0.7); it actually trades MORE
  aggressively in 0-25k (9 fills vs 7). The problem is the taker
  edge is too TIGHT, not too conservative.

**What changes in the market after ~50 000?** Almost nothing. The
mid drift is +26 ticks in 0-25k, +24.5 in 25-50k, +24 in 50-75k,
+24.5 in 75-100k — flat. Spread is ~13.7 every bucket. What
actually changes is baseline's *own* net position:

- End of 0-25k: **−8** (short, losing)
- End of 25-50k: **+18** (long, MTM starts helping)
- End of 50-75k: **+23** (long, rides +24 drift → +897 bucket PnL)
- End of 75-100k: −2 (flat, exits nicely)

The bucket-3 "jump" for all variants is the mechanical consequence
of being long (+18 to +32 into a +24-point rise) — about 18-32 × 24
≈ +430 to +770 of MTM, plus realised spread captured. It is
**not** a market regime change.

## 5. Comparison against promoted and alt

Why promoted / alt start monetising earlier:

1. **Fair value responsiveness (PEPPER).** Both promoted and alt run
   `linear_drift` with `history_length=32` (vs baseline's 48). Shorter
   lookback → slope estimate adapts faster to the current local
   gradient. With 48 samples (4 800 ticks of data), baseline's slope
   is a smoothed average that under-reacts to the consistent +0.001
   slope early in the day; with 32 samples it locks on sooner. Residual
   means are similar (+0.15 vs +0.15), so the *value* of the forecast
   is similar; what differs is the *responsiveness*.
2. **Threshold aggressiveness (PEPPER).** Promoted / alt set
   `taker_edge = 2.0` vs baseline's 1.0. That single parameter
   eliminates the spurious 0-25k sell triggers that get baseline
   short. With a 2.0 threshold in 0-25k, promoted / alt have 2 buy
   / 2 sell triggers (symmetric); baseline has 2 / 3 (wrong-side
   bias). That asymmetry is the proximal cause of baseline's −8
   vs promoted's +1 bucket-end inventory.
3. **Fill behaviour — ASH.** Promoted runs ASH on `ewma_mid` with
   `taker_edge=0.25`. Despite the tiny taker edge, it does NOT fire
   extra taker fills on ASH (3 taker in 0-25k vs baseline's 4, alt's
   4) — because `ewma_mid` is smoother (residual_std ≈ 1.04 vs
   wall_mid's ≈ 1.37), so the taker inequality
   `fv − best_ask ≥ 0.25` rarely crosses even at a low threshold.
   Promoted's ASH ends up doing fewer total trades (81 vs 89/89),
   and the difference is NOT compensated by better markouts on the
   official fill model. This is the ASH-specific under-performance
   finding from the Phase-7 memo, reproduced at bucket resolution
   (Promoted ASH's bucket 75-100k is the cleanest failure point:
   +79.69 vs baseline's +205.97 and alt's +227.98).
4. **Inventory behaviour.** Because promoted / alt avoid the
   early short, by t=50 000 they are +32 / +27 long PEPPER
   (baseline +18). More long inventory means more MTM gain on the
   same drift in bucket 3. Baseline's bucket 3 PEPPER is +897
   versus promoted's +943 and alt's +1 084 — a 5 %-20 % gap that
   compounds.
5. **Asymmetry by product / side.** The advantage is **entirely on
   PEPPER, and entirely on the sell side of bucket 1**. ASH
   sell-trigger counts in 0-25k are 4 (baseline) / 3 (promoted) /
   5 (alt) — no pattern. PEPPER sell-trigger counts in 0-25k are
   3 / 2 / 2 — the exact delta between baseline and promoted /
   alt. One fewer premature PEPPER sell in 0-25k is worth roughly
   the full PnL gap.

## 6. Directional implications (flagged, not applied)

These follow the rule from `CLAUDE.md` — evidence-calibrated
observations, not prescriptions. No config is changed in this
memo.

- On a **single-day, 1 000-snapshot** run, `history_length=48` on
  `linear_drift` warms up slower than `32` and produces a
  wrong-direction trigger in the first bucket. Directionally
  consistent with the Phase-7 "Q1-Q2 warm-up flag".
- `taker_edge=1.0` on PEPPER is tight enough to fire on
  noise-level deviations early in the day when the slope estimate
  hasn't locked on. `taker_edge=2.0` (promoted / alt) filters
  those out cleanly.
- Baseline's PEPPER leg is the single biggest cause of the +2 276
  vs +2 518 / +3 040 gap. Its ASH leg is actually competitive
  with Alt's (+832 vs +983) — not the weak point.
- `ewma_mid` with `taker_edge=0.25` on ASH (Promoted) is the
  second-biggest PnL drag: it under-trades compared with both
  `wall_mid` variants across every bucket. Bucket 75-100k is the
  most visible drop-off.

## 7. Acceptance

| Criterion | Status |
|-----------|--------|
| Bucketed PnL attribution (4 × 25k) for each variant / product | ✅ `bucket_breakdown.csv`, `bucket_breakdown.md`, and §1 above |
| Bucketed trade / execution stats per variant / product | ✅ §2 (maker/taker, avg size, final pos, near-limit time) |
| Fair-vs-market diagnostics per variant / product / bucket | ✅ §3 (fv-ask, bid-fv, triggers, residual μ/σ) |
| Baseline-specific explanation of the flat first half | ✅ §4 (PEPPER, inventory drag + wrong-side triggers) |
| Comparison against promoted / alt | ✅ §5 (fair-value responsiveness, threshold, fill, inventory, asymmetry) |
| No config changes, no new sweeps | ✅ diagnostic pass only |
