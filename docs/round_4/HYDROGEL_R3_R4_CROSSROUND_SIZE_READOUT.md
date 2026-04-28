# HYDROGEL R3/R4 Cross-Round Size Readout

Date: 2026-04-27

## Question

What do Round 3 historical data, Round 3 final submission data, Round 4
historical data, and Round 4 simulator uploads jointly imply for the final HYD
choice among `long40`, `long80`, and `long120`?

## Key Finding

The Round 3 final 1M HYD book path matches Round 4 historical day 3 exactly.

Comparison:

| check | value |
|---|---:|
| R3 final HYD rows | 10,000 |
| R4 historical day 3 HYD rows | 10,000 |
| joined timestamps | 10,000 |
| best bid mismatches | 0 |
| best ask mismatches | 0 |
| mid mismatches | 0 |

This matters because the R4 official 100k simulator path is the first 100k of
that same path. The official upload path is useful for fill calibration, but it
is not independent evidence for the final 1M hidden distribution.

## Round 3 Final HYD Attribution

Submitted Round 3 final combined strategy:

`outputs/submissions/submission_r3_combined_hydrogel_publicguard_1m9988_tw32_velvet_v2_flat980.py`

Official final result:

| metric | value |
|---|---:|
| total PnL | 178,797 |
| HYD PnL | 54,597 |
| HYD touch-liquidated PnL | 53,544 |
| final HYD position | +128 |
| final HYD mid | 10,001 |
| HYD buy qty | 1,272 |
| HYD sell qty | 1,144 |
| avg buy | 9,977.59 |
| avg sell | 10,022.67 |
| HYD trade rows | 227 |
| HYD min PnL | -7,086.62 |
| HYD peak PnL | 55,604.38 |
| HYD max drawdown | -11,756.62 |

HYD checkpoint PnL on the final 1M path:

| timestamp | mid | HYD PnL |
|---:|---:|---:|
| 99,900 | 10,017 | 1,680 |
| 100,000 | 10,014 | 2,152.5 |
| 500,000 | 10,040 | 24,306.91 |
| 900,000 | 9,957 | 48,895.5 |
| 999,900 | 10,001 | 54,597 |

The first 100k was not where Round 3 final HYD made most of its money. The
first 100k is the same high-continuation prefix that makes the old R3-derived
R4 sleeve look weak. The 1M result became strong because the remaining path
gave mean-reversion and recycling opportunities.

## R3 Simulator Lesson

Representative R3 100k official HYD-only runs:

| run | HYD PnL | final pos | comment |
|---|---:|---:|---|
| `aggressive_new_418798` | 19,880 | 0 | realized/flat cycle |
| `99553_imbgate_432460` | 28,097.625 | +200 | publicguard-style residual long |
| `v2_guarded_426894` | 39,295.625 | +200 | high 100k score, more terminal residual |

Those results came from 100k paths with clean cycle/rebound geometry. They do
not imply that every 100k high prefix should produce 20k HYD. The R3 final 1M
shows the opposite: the same first 100k high prefix made only 1,680 HYD before
the rest of the 1M path unlocked the larger alpha.

## R4 Long-Size Map

Local R4 HYD-only replay, using the current abortgate high-regime structure:

| strategy | day 1 1M | day 2 1M | day 3/R3 final path 1M | 3-day total | 3-day avg |
|---|---:|---:|---:|---:|---:|
| `long40` | 48,959 | 62,414 | 56,320 | 167,693 | 55,898 |
| `long80` | 48,959 | 62,414 | 56,817 | 168,190 | 56,063 |
| `long120` | 48,959 | 62,414 | 57,296 | 168,669 | 56,223 |

Day 1 and day 2 are unchanged because the high-regime start trigger does not
activate. The whole size decision is concentrated in paths like day 3 / R3
final.

Official R4 100k upload calibration:

| strategy | official HYD | touch-liquidated HYD | final pos | avg buy | avg sell | HYD min |
|---|---:|---:|---:|---:|---:|---:|
| `long40` | 7,151 | 5,501 | -200 | 10,030.25 | 10,047.91 | -942.12 |
| `long80` | 7,657 | 6,007 | -200 | 10,031.84 | 10,047.73 | -1,488.62 |
| `long120` | 8,052 | 6,402 | -200 | 10,033.33 | 10,047.60 | -2,292.50 |

Marginal frontier:

| move | official HYD gain | day3/full-path local gain | 3-day avg gain | HYD min worsens |
|---|---:|---:|---:|---:|
| `40 -> 80` | +506 | +497 | +165.7 | -546.5 |
| `80 -> 120` | +395 | +479 | +159.7 | -803.9 |

## Interpretation

The robust signal is not "bigger is always better."

The robust signal is:

1. HYD is still a mean-reversion/recycling asset over a full 1M path.
2. The stale R3 sleeve shorts too early in high-continuation starts.
3. A high-regime overlay is justified.
4. The exact size of that overlay is a risk trade, not a new alpha family.

The independent evidence for `long120` over `long80` is weak:

- `long120` wins the known official/day3/R3-final prefix.
- But that prefix is not independent of the historical path now available.
- The incremental 1M average gain over `long80` is only about 160 HYD across the
  three R4 historical days.
- The official-path gain over `long80` is only 395 HYD.
- The early-path drawdown worsens by about 804 HYD.

## Expected 1M HYD Performance

Under the current local R4/R3-final-style distribution, the three long variants
cluster around:

| strategy | expected HYD from 3-day local average |
|---|---:|
| `long40` | about 55.9k |
| `long80` | about 56.1k |
| `long120` | about 56.2k |

This is not a guarantee for the final unseen 1M. It says the final HYD choice
should be expected in the mid-50k range if the hidden 1M has similar
mean-reversion/recycling geometry. The first 100k score alone is a bad proxy
for final 1M HYD because the R3 final path made only 1.7k in the first 100k
but 54.6k by the end.

## Final Pick

For final 1M robustness:

`abortgate18_long80_60`

For max official-path EV:

`abortgate18_long120_60`

After the cross-round readout, the preferred professional choice is
`abortgate18_long80_60` unless the whole portfolio deliberately wants the
higher-variance HYD sleeve. The `long120` edge over `long80` is real on the
known path, but too small and too path-dependent to call robustly optimal.

The important decision is to keep the high-regime overlay at all. The difference
between 80 and 120 is second-order; the difference between stale early shorting
and guarded high-regime inventory is first-order.
