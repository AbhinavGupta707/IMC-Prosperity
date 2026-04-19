# Round-2 ASH FINE sweep around wide_w113 (D1 winner)

PEPPER frozen at v5_micro. 37 candidates spanning 3-level edge fine-grain (16), weight × skew fine-grain (12), and 4-level ladders (9). Reference row is the D1 winner `wide_w113`.

## Winner: `3lvl_e3_5_8_x.5_w113_s1_f0.7`

- ASH PnL: **+11827** (vs wide_w113 reference +11785, Δ = +42)
- ASH trades: 810 (ref 810)
- Per-day: day_-1=+3755, day_0=+4030, day_1=+4042
- σ across days: 162

### Winning LadderParams

```python
LadderParams(
    edges=(3.0, 5.0, 8.0),
    size_mults=(0.5, 2.0, 3.0),
    weights=(1, 1, 3),
    skew_coef=1.0,
    flatten_threshold=0.7,
)
```

## Top 15 candidates by ASH PnL

| rank | label | ASH PnL | trades | σ | day_-1 | day_0 | day_1 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `3lvl_e3_5_8_x.5_w113_s1_f0.7` | +11827 | 810 | 162 | +3755 | +4030 | +4042 |
| 2 | `3lvl_e3_5_8_w114_s1_f0.7` | +11804 | 821 | 143 | +3806 | +3910 | +4088 |
| 3 | `wide_w113_REF` | +11785 | 810 | 153 | +3755 | +3988 | +4042 |
| 4 | `3lvl_e2.5_5_8_w113_s1_f0.7` | +11785 | 810 | 153 | +3755 | +3988 | +4042 |
| 5 | `3lvl_e3_5_8_x4_w113_s1_f0.7` | +11785 | 810 | 153 | +3755 | +3988 | +4042 |
| 6 | `3lvl_e3_5_8_w113_s1_f0.7` | +11785 | 810 | 153 | +3755 | +3988 | +4042 |
| 7 | `3lvl_e3_4.5_8_w113_s1_f0.7` | +11770 | 809 | 158 | +3744 | +3984 | +4042 |
| 8 | `3lvl_e3_4_8_w113_s1_f0.7` | +11770 | 809 | 158 | +3744 | +3984 | +4042 |
| 9 | `3lvl_e3_5_8_eq_w113_s1_f0.7` | +11738 | 805 | 186 | +3699 | +4035 | +4004 |
| 10 | `3lvl_e3_5_8_w124_s1_f0.7` | +11564 | 799 | 163 | +3667 | +3955 | +3942 |
| 11 | `3lvl_e3_5_8_w112_s1_f0.7` | +11558 | 794 | 141 | +3696 | +3971 | +3891 |
| 12 | `4lvl_e1.5_3_5_8_w1113_s1_f0.7` | +11361 | 776 | 105 | +3718 | +3735 | +3908 |
| 13 | `4lvl_e2_3_5_8_w1113_s1_f0.7` | +11361 | 776 | 105 | +3718 | +3735 | +3908 |
| 14 | `3lvl_e3_5_8_w123_s1_f0.7` | +11343 | 781 | 90 | +3718 | +3741 | +3884 |
| 15 | `3lvl_e3_5_8_w213_s1_f0.7` | +11340 | 773 | 93 | +3718 | +3735 | +3887 |

## Bottom 5 candidates by ASH PnL

| rank | label | ASH PnL | trades | σ |
|---:|---|---:|---:|---:|
| 33 | `3lvl_e3_5_10_w113_s1_f0.7` | +10554 | 699 | 40 |
| 34 | `4lvl_e3_5_8_12_w1113_s1_f0.7` | +10415 | 709 | 163 |
| 35 | `4lvl_e3_5_8_15_w1113_s1_f0.7` | +10369 | 706 | 167 |
| 36 | `4lvl_e2_4_6_10_eq_s1_f0.7` | +10158 | 700 | 145 |
| 37 | `3lvl_e3_5_12_w113_s1_f0.7` | +9959 | 667 | 64 |

## Reference

`wide_w113` (batch-D1 winner): edges (3.0, 5.0, 8.0), weights (1, 1, 3), skew 1.0, flatten 0.7.
ASH PnL +11785, trades 810, per-day {-1: 3755.0, 0: 3988.0, 1: 4042.0}, σ 153.

## Notes

- **No material improvement** over D1 winner (best Δ = +42).
  `wide_w113` was already at or near the local optimum.
