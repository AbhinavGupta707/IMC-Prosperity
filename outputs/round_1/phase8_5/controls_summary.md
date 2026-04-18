# Phase 8.5A — Control reference (official Round-1 results)

Three candidates that have already been run on the official IMC site
(all from commit `b1fc5bf`, uploaded 2026-04-14). Primary evidence is
each variant's `outputs/round_1/official_results/<variant>/*.json`;
the detail comes from the forensic drill-down in
`outputs/round_1/official_results/analysis/bucket_memo.md`.

The numbers below are **frozen** — this is the control set the
Phase-8.5 workstreams (PEPPER + ASH) must beat or at least tie.

## Configs, at a glance

| Variant | ASH config | PEPPER config |
|---------|-----------|---------------|
| **Baseline** | `wall_mid, t=1.0, m=1.0, skew=4.0, flatten=0.7, h=48` | `linear_drift, t=1.0, m=1.5, skew=2.0, flatten=0.8, h=48` |
| **Promoted** | `ewma_mid(α=0.3), t=0.25, m=1.0, skew=4.0, flatten=0.7, h=48` | `linear_drift, t=2.0, m=1.0, skew=2.0, flatten=0.7, h=32` |
| **Alt**      | `wall_mid, t=0.5, m=1.5, skew=4.0, flatten=0.7, h=48`           | `linear_drift, t=2.0, m=1.0, skew=1.0, flatten=0.9, h=32` |

## Official aggregate

| Variant | Total PnL | ASH PnL | PEPPER PnL | Trades (ASH / PEPPER) | Final pos (ASH / PEPPER) |
|---------|----------:|--------:|-----------:|----------------------:|-------------------------:|
| Baseline | **+2 276.15** | +832.25 | +1 443.90 | 89 / 48 | −8 / +1 |
| Promoted | **+2 518.11** | +720.91 | +1 797.20 | 80 / 41 | −21 / −2 |
| Alt      | **+3 040.22** | +982.81 | +2 057.41 | 89 / 45 | −10 / +6 |

## Early-day (first 25k and first 50k) attribution

First 25k (bucket 0 − 25 000):

| Variant | ASH PnL | PEPPER PnL | Σ | PEPPER pos at 25k |
|---------|--------:|-----------:|--:|------------------:|
| Baseline | +175.27 | **−57.20** | +118.07 | **−8** |
| Promoted | +159.50 | +30.90 | +190.40 | +1 |
| Alt | +219.66 | +30.90 | +250.56 | +1 |

First 50k (cumulative through bucket 0-50 000):

| Variant | ASH PnL | PEPPER PnL | Σ | First-half share of day total |
|---------|--------:|-----------:|--:|-------------------------------:|
| Baseline | +335.93 | +54.91 | +390.84 | **17.2 %** |
| Promoted | +330.91 | +437.50 | +768.41 | 30.5 % |
| Alt | +413.91 | +361.00 | +774.91 | 25.5 % |

## Maker / taker split (whole day, per product)

Classification: buy at price ≥ best_ask OR sell at price ≤ best_bid
→ taker; else maker.

| Variant | ASH maker / taker | PEPPER maker / taker |
|---------|-------------------|---------------------|
| Baseline | 56 / 25 (+8 other)  | 20 / 27 (+2 other) |
| Promoted | 56 / 16 (+9 other)  | 18 / 24 (0 other)  |
| Alt      | 56 / 25 (+9 other)  | 19 / 26 (+2 other) |

Promoted ASH's lower taker count (16 vs 25) is the biggest single
driver of its ASH under-performance — ewma_mid + t=0.25 fires
fewer takers than wall_mid + t≥0.5.

## Per-bucket PEPPER position path

| Variant | end 0-25k | end 25-50k | end 50-75k | end 75-100k |
|---------|----------:|-----------:|-----------:|------------:|
| **Baseline** | **−8** | +18 | +23 | −2 |
| Promoted | +1 | +32 | +7 | −18 |
| Alt | +1 | +27 | +22 | −3 |

Only the baseline's 0-25k bucket is significantly on the wrong side
of the drift. Promoted and Alt stay neutral or long through bucket 1.

## Near-limits

With `position_limit=50` and 80 % of limit (= 40 units) as the
threshold, **only Alt PEPPER** spends any snapshots near the limit
this day (22 of 250 snapshots in bucket 50-75k; ~9 % of that bucket).
Baseline and Promoted never touch 40 units on either product.

## One-sentence diagnosis per variant

| Variant | Diagnosis |
|---------|-----------|
| **Baseline** | ASH is competitive (+832), but PEPPER is dragged by an early short (−8 by t=25k) built under a tight `taker_edge=1.0` + slower `h=48` drift estimator; the first-half PnL share (17 %) is the signature. |
| **Promoted** | PEPPER is solid; ASH (+721) underperforms baseline because `ewma_mid + taker_edge=0.25` fires 10–15 fewer takers than wall-mid-based configs for the same edge quality on the official fill model. |
| **Alt** | Best on both legs (+983 ASH, +2 057 PEPPER); relies on Alt PEPPER accumulating a larger long (up to +22 by t=75k) — works on this single day but spends 9 % of bucket-3 snapshots near the 40-unit threshold. |

## Control set for Phase 8.5

These three frozen candidates are the **reference the Phase-8.5
workstreams must beat or match in an interpretable way**. Numbers
above come entirely from the official data; no local replay is mixed
in here.

- **Beat-or-match target on PEPPER** = Promoted +1 797 (day total),
  with special attention to first-25k ≥ +30.90 and PEPPER position
  at t=25 000 staying at ≥ 0.
- **Beat-or-match target on ASH** = Alt +983 (day total) *on the
  official scale* — but the official number isn't available for
  new variants yet, so locally the target is "higher trade count
  and higher per-trade markout than A0 Promoted".
- **Day-total upper bound** = Alt +3 040; any new combined
  candidate has to show a credible path to ≥ this number on the
  official fill model, not just locally.
