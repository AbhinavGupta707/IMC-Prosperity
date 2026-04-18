# Phase B — ASH memo (concise)

## How ASH moves

Anchored oscillator around ~10 000 with a steady **~16-tick stable
spread** and book that is visible at 1–2 levels most of the time.
Residual volatility is low; drift is effectively zero on the official
day (mid moves roughly ±20 over 100 000 timestamps, with no
directional bias). Trade density is healthy (≈85 filled PEPPER-side
trades per variant per day).

Source: `outputs/round_1/research/ash_coated_osmium_dossier.md`,
plus the fair-vs-market residuals in
`outputs/round_1/official_results/analysis/bucket_breakdown.md`
(`residual_std` ≈ 1.04 for `ewma_mid`, ≈ 1.37 for `wall_mid`).

## Where the ASH edge comes from

**Mixed — passive spread capture DOMINATED, taker role minor.**

- The 16-tick stable spread with a visible book is tailor-made for a
  **maker**. Baseline and Alt capture ≈16 maker fills per 25k vs 3-8
  taker fills — maker is the workhorse.
- `maker_edge` width is the primary PnL lever on ASH. Promoted's
  `ewma_mid + maker_edge=1.0 + taker_edge=0.25` produces the best
  markouts and the lowest `residual_std`, but **under-fires the maker**
  on the official day: 81 total ASH trades vs 89/89 for Baseline/Alt.
  That's worth **−112 to −262** total ASH PnL against wall-based
  variants.
- Fair-value **estimator choice is almost cosmetic** given the book
  structure. `residual_mean` is within ±0.06 of zero for every
  variant; the real difference is maker firing rate, which flows
  from `maker_edge` + the floor/ceil rounding of `raw_bid/raw_ask`
  around the fair value.

## What is the best ASH leg today

**Wall-based ASH (H1 / Alt leg)** = `wall_mid` / `maker_edge=1.5` /
`taker_edge=0.5` / `inventory_skew=4.0` / `flatten_threshold=0.7` /
`history_length=48`.

- Delivers **+982.81** on the official day vs Promoted's +720.91
  (+261.90 improvement, ≈36 % more ASH PnL).
- Zero near-limit snapshots on this data point.
- H1 validates it in combination with the Promoted PEPPER leg without
  introducing any new tail risk. This is the shipped proof that
  wall-based ASH is the right leg.

## What remains uncertain on ASH

- **Single data point.** We only have the 2026-04-14 official day.
  Phase-5 sweeps saw wall_mid and ewma_mid roughly comparable in
  local replay; Alt's +262 gain over Promoted on ASH is a real win
  but it has not been replicated in a second official run.
- **Maker-edge width at 1.5 is not proven vs 1.0.** In local
  replay the two wall-based legs are close; the official data point
  favors 1.5, but the sample is tiny.
- The `ewma_mid` under-trade could in principle be fixed by loosening
  `taker_edge` (e.g. `ewma_mid + taker=0.5`). We do NOT run this
  ablation in the current pass — the search budget is fully on
  PEPPER by design.

## ASH policy for this pass

**Freeze ASH at the H1 / Alt wall-based leg** in every PEPPER
candidate.  This gives us a clean PEPPER comparison and avoids
re-opening ASH tuning. Two side-check ASH variants are evaluated
at the end (`wall_mid taker=0.5 maker=1.0` and the shipped `ewma_mid
taker=0.25`) to confirm the wall-based leg still wins when paired
with the best new PEPPER candidate — nothing more.
