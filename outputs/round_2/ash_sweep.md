# Round-2 ASH ladder sweep (batch D1)

PEPPER held frozen at v5_micro CoreLongParams (the +80k/day annuity).
ASH leg swept across 3 ladder shapes × 4 weight profiles × 3 skew
× 2 flatten = 72 candidates + L1 baseline.

Tape: 3 R2 days × 10k snapshots each. PEPPER PnL ≈ +239k constant
across all candidates (sanity check that nothing leaked into PEPPER).

## Winner: `wide_w113_s1_f0.7`

- ASH PnL: **+11785** (vs L1 baseline +9847, Δ = ++1938, +20%)
- ASH trades: 810 (baseline 681)
- Per-day PnL: day_-1=+3755, day_0=+3988, day_1=+4042
- σ across days: 153

### Winning LadderParams

```python
LadderParams(
    edges=(3.0, 5.0, 8.0),
    size_mults=(1.0, 2.0, 3.0),
    weights=(1, 1, 3),
    skew_coef=1.0,
    flatten_threshold=0.7,
)
```

## Top 15 candidates by ASH PnL

| rank | label | ASH PnL | ASH trades | per-day σ | day_-1 | day_0 | day_1 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `wide_w113_s1_f0.7` | +11785 | 810 | 153 | +3755 | +3988 | +4042 |
| 2 | `wide_w113_s1_f0.85` | +11769 | 808 | 281 | +3674 | +4228 | +3867 |
| 3 | `wide_w113_s2_f0.7` | +11403 | 820 | 172 | +3602 | +3898 | +3903 |
| 4 | `wide_w113_s2_f0.85` | +11349 | 826 | 119 | +3649 | +3822 | +3878 |
| 5 | `wide_w113_s3_f0.85` | +11078 | 814 | 153 | +3810 | +3749 | +3519 |
| 6 | `wide_weq_s1_f0.85` | +11058 | 749 | 325 | +3437 | +4054 | +3567 |
| 7 | `wide_w113_s3_f0.7` | +11023 | 807 | 185 | +3810 | +3749 | +3464 |
| 8 | `wide_weq_s2_f0.7` | +10798 | 760 | 145 | +3432 | +3683 | +3683 |
| 9 | `wide_weq_s2_f0.85` | +10784 | 770 | 197 | +3378 | +3764 | +3642 |
| 10 | `wide_weq_s1_f0.7` | +10682 | 734 | 179 | +3368 | +3591 | +3723 |
| 11 | `wide_w311_s1_f0.85` | +10605 | 724 | 120 | +3469 | +3673 | +3463 |
| 12 | `wide_w521_s1_f0.85` | +10553 | 708 | 304 | +3363 | +3868 | +3322 |
| 13 | `wide_w311_s2_f0.7` | +10495 | 733 | 104 | +3381 | +3577 | +3537 |
| 14 | `wide_w311_s2_f0.85` | +10491 | 737 | 117 | +3377 | +3503 | +3611 |
| 15 | `wide_w311_s1_f0.7` | +10436 | 713 | 116 | +3406 | +3418 | +3612 |

## Bottom 5 candidates by ASH PnL

| rank | label | ASH PnL | ASH trades | per-day σ |
|---:|---|---:|---:|---:|
| 69 | `L1_w521_s3_f0.85` | +9365 | 679 | 26 |
| 70 | `tight_w311_s3_f0.7` | +9296 | 681 | 121 |
| 71 | `tight_weq_s3_f0.7` | +9257 | 677 | 44 |
| 72 | `tight_weq_s3_f0.85` | +9232 | 675 | 32 |
| 73 | `tight_w311_s3_f0.85` | +9186 | 677 | 60 |

## L1 baseline reference

`L1_baseline`: edges (2.5, 3.5, 5.0), weights (3, 1, 1), skew=2.0, flatten=0.7.
ASH PnL +9847; trades 681; per-day {-1: 3101.0, 0: 3355.0, 1: 3391.0}; σ 158.

## Notes

- **Material uplift recovered:** +1938 ASH PnL over the
  L1 baseline. Update the Round-2 default ASH ladder params to
  `wide_w113_s1_f0.7` for the final submission factory.
- PEPPER is unaffected across all candidates (sanity check):
  the winner's PEPPER PnL is +239528, baseline is +239528. Difference: 0 XIRECs (rounding noise).
