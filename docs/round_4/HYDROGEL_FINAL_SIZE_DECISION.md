# HYDROGEL Final Size Decision

Date: 2026-04-27

## Question

Is `abortgate18_long120_60` actually optimal, or are we just increasing
exposure on one official 100k path?

## Short Answer

`long120` is not proven to be the universal best HYD setting. It is the highest
EV point that remains defensible under the current evidence.

The robust conclusion is:

| choice | interpretation |
|---|---|
| `abortgate18_long80_60` | cleaner risk-adjusted default |
| `abortgate18_long120_60` | max-EV HYD choice if the portfolio can absorb more path risk |
| `long160+` | not justified for a robust final submission |

## Why This Is Not Blind Size Creep

The official frontier shows positive but diminishing marginal cash edge:

| move | official HYD gain | early HYD min worsening |
|---|---:|---:|
| `40 -> 80` | +506 | -547 |
| `80 -> 120` | +395 | -804 |

The `80 -> 120` improvement is real cash PnL, not terminal mark inflation:

| run | HYD cash | terminal mark component | final pos |
|---|---:|---:|---:|
| `long80` | 2,011,007 | -2,003,400 | -200 |
| `long120` | 2,011,402 | -2,003,400 | -200 |

The final HYD exposure is unchanged. The extra risk is path risk while carrying
a larger long inventory before the release window.

## Why We Stop At 120

Local size frontier:

| target | official-proxy HYD | official-proxy min HYD | official-proxy max DD |
|---:|---:|---:|---:|
| 80 | 7,867 | -1,161 | -4,100 |
| 120 | 8,346 | -1,892 | -4,100 |
| 160 | 8,596 | -2,843 | -4,800 |
| 200 | 8,776 | -3,842 | -6,000 |

The marginal expected gain collapses after 120 while inventory path damage
accelerates. That is the overfitting boundary.

Rolling false-trigger stress also worsens:

| target | rolling mean | worst window | p10 |
|---:|---:|---:|---:|
| 80 | -2,895 | -16,800 | -8,648 |
| 120 | -3,133 | -18,600 | -9,448 |
| 160 | -3,371 | -22,600 | -10,000 |
| 200 | -3,609 | -26,600 | -10,320 |

`long120` is still within the defensible range. `long160` and `long200` are not:
they mainly add tail exposure for small incremental edge.

## Final Research Judgment

If optimizing HYD alone for expected PnL:

`abortgate18_long120_60`

If optimizing for the most conservative non-overfit final portfolio:

`abortgate18_long80_60`

If forced to choose one HYD module for a high-PnL final submission with the
current stable non-HYD stack, the preferred choice is `abortgate18_long120_60`.
The reason is that the extra PnL is cash-realized, terminal exposure is
unchanged, and both local and official frontiers agree through 120.

But the confidence gap between 80 and 120 is not huge. This should be treated as
a portfolio risk decision, not as a discovered new alpha source.
