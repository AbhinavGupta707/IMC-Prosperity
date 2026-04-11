# Tutorial Round 1 — Quick EDA

Source: `data/raw/tutorial_round_1/prices_round_0_day_{-1,-2}.csv`
Rows per product: 20,000 across two days.

## EMERALDS

| metric | value |
|---|---|
| mid mean | 10000.00 |
| mid median | 10000.00 |
| mid stdev | 0.72 |
| mid min / max | 9996.00 / 10004.00 |
| spread mean / median | 15.74 / 16.00 |
| spread min / max | 8.00 / 16.00 |
| best bid volume mean / median / max | 12.5 / 13.0 / 15 |
| best ask volume mean / median / max | 12.5 / 13.0 / 15 |

**Reads:**

- Mid is effectively a constant at 10000. Total drift across 20k rows is 8 ticks.
- Spread is almost always 16 (with occasional tightening to 8). That is a
  *huge* spread for an almost-static product.
- Best-level volume is around 12–13, so a maker quote of size 5 is well
  within what the top of book can absorb.
- The right fair value here is the anchor 10000, possibly nudged toward
  the microprice for book-imbalance tilts.
- The dominant risk is one-sided inventory pileup, not fair-value drift.

## TOMATOES

| metric | value |
|---|---|
| mid mean | 4992.76 |
| mid median | 4995.50 |
| mid stdev | 19.75 |
| mid min / max | 4946.50 / 5036.00 |
| spread mean / median | 13.02 / 13.00 |
| spread min / max | 5.00 / 14.00 |
| best bid volume mean / median / max | 7.4 / 7.0 / 12 |
| best ask volume mean / median / max | 7.4 / 7.0 / 12 |

**Reads:**

- Mid drifts meaningfully — ~90 ticks peak-to-peak, stdev ~20. A constant
  fair value is clearly wrong.
- Spread is narrower and more variable than EMERALDS: usually 13, with
  minimums down to 5 where taker opportunities are least likely to exist.
- Best-level volume is roughly half of EMERALDS, so maker sizes should
  be smaller and inventory discipline tighter.
- The right fair value here is a rolling or weighted mid. The
  short-memory predictive structure hypothesized in the plan is
  consistent with the observed drift.

## Implications for Phase 2 EMERALDS baseline

1. Anchor at 10000 is correct. Use it as the primary fair value.
2. Given spread ~= 16, a maker edge of 2 (quote at 9998 / 10002) should
   capture obvious edge every iteration the book is normal.
3. A taker edge of 1 is enough to cross an ask at 9999 or hit a bid at
   10001 when they appear, which is rare but essentially free money.
4. Keep max_aggressive_size modest (≤ 10) so a single burst of
   one-sided fills cannot breach the 20-unit position limit.
5. Flatten hard once the absolute position exceeds 75% of the limit —
   inventory is the primary failure mode, not mispricing.
