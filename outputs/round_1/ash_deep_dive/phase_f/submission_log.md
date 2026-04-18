# Phase F — submission log

One row per official upload. All rows reference bundles under
`outputs/submissions/round_1/limit_80/`. **All 10 bundles uploaded
and scored.**

## Column key

- **Batch** — Phase-F sub-batch (F1 control, F2 empirical winners, F3 composites / hybrids).
- **Candidate** — cell_id per PLAN.md sec 7.1.
- **Bundle** — filename of the `.py` uploaded.
- **IMC ID** — submission ID assigned by the platform.
- **Predicted ASH** — Phase-E `day_0_real` prediction (most similar to an official day).
- **Official ASH** — observed ASH PnL on the scoring day.
- **Δ** — observed − predicted ASH.
- **Official total** — total PnL (ASH + PEPPER).

## Log — SCORED

| Batch | Candidate | Bundle | IMC ID | Status | Predicted ASH | Official ASH | Δ | Official total |
|---|---|---|---:|---|---:|---:|---:|---:|
| F1 | C_h1_alt control | `trader_round1_test.py` | 162 376 | SCORED | +2 541 | **+959.78** | −1 581 | +8 245.78 |
| F2c | B1 weighted_mid | `trader_round1_ash_deep_f2c.py` | 197 551 | SCORED | +3 387 | **+1 035.53** | −2 351 | +8 321.53 |
| F3a | D5 weighted_m25_c2 | `trader_round1_ash_deep_f3a.py` | 197 684 | SCORED | +3 346 | **+1 394.56** | −1 951 | **+8 680.56** |
| F3b | D7 weighted_as_g2e-6 | `trader_round1_ash_deep_f3b.py` | 197 840 | SCORED | +3 336 | +953.66 | −2 382 | +8 239.66 |
| F2b | D6 m25_as_continuous | `trader_round1_ash_deep_f2b.py` | 198 401 | SCORED | +3 136 | +1 250.00 | −1 886 | +8 536.00 |
| F2a | C1 as_g2e-06 | `trader_round1_ash_deep_f2a.py` | 198 522 | SCORED | +2 943 | +1 059.94 | −1 883 | +8 345.94 |
| F2d | B2 m25_t05 | `trader_round1_ash_deep_f2d.py` | 198 682 | SCORED | +2 546 | +1 222.38 | −1 324 | +8 508.38 |
| F3d | C1 as_g5e-7 | `trader_round1_ash_deep_f3d.py` | 198 789 | SCORED | +2 943 | +1 268.00 | −1 675 | +8 554.00 |
| F3c | D8 cartea_b01 | `trader_round1_ash_deep_f3c.py` | 198 882 | SCORED | +2 673 | +1 230.34 | −1 443 | +8 516.34 |
| F3e | C3 cartea_b03 | `trader_round1_ash_deep_f3e.py` | 198 988 | SCORED | +2 294 | +1 096.62 | −1 197 | +8 382.62 |
| G1 | wall_mid swap test | `trader_round1_ash_deep_g1.py` | pending | PLANNED | +3 058 → ~1 407 | — | — | — |
| G5 | F3a + skew c=1 | `trader_round1_ash_deep_g5.py` | pending | PLANNED | +3 495 → ~1 468 | — | — | — |
| H5 | slow-FV τ=500 c=2 | `trader_round1_ash_deep_h5.py` | 206 680 | SCORED | +1 908 → +801 (emp) / +1 639 (fs) | **+888.38** | −751 (vs fs) | +8 174.38 |
| I2a | 4-level ladder (2.5/5/8/12) | `trader_round1_ash_deep_i2a.py` | 209 357 | SCORED | +3 666 → +1 540 (emp) / +9 834 (fs) | **+1 365.34** | −175 (vs emp) | +8 651.34 |
| **J2** | **3-level inner-heavy ladder (3/1/1)** | `trader_round1_ash_deep_j2.py` | **211 226** | **SCORED** | +3 653 → +1 461 (proj) | **+1 646.97** | **+186** (beat proj!) | **+8 932.97** |
| J3 | 4-level spread-gated ladder | `trader_round1_ash_deep_j3.py` | 211 375 | SCORED | +3 631 → +1 452 (proj) | +1 371.75 | −80 | +8 657.75 |
| J7 | weighted 3/1/1/1 + gated combo | `trader_round1_ash_deep_j7.py` | 211 553 | SCORED | +3 581 → +1 468 (proj) | +1 166.28 | −302 | +8 452.28 |
| **K2** | **tight outer (2.5/4/6, weights 3/1/1)** | `trader_round1_ash_deep_k2.py` | **213 280** | **SCORED** | +3 497 → +1 577 (proj J2 ratio) | **+1 764.88** | **+188** (beat J2 proj) | **+9 050.88** |
| **K5** | **asym (buy 2.5/4/6, sell 2.5/5/8)** | `trader_round1_ash_deep_k5.py` | **212 807** | **SCORED** | +3 581 | **+1 737.00** | +90 vs J2 | **+9 023.00** |
| K1 | inner-heavy 4/1/1 on 2.5/5/8 | `trader_round1_ash_deep_k1.py` | 213 473 | SCORED | +3 516 | +1 241.41 | −406 vs J2 | +8 527.41 |
| K3 | 4-level (2.5/5/8/12, weights 3/1/1/1) | `trader_round1_ash_deep_k3.py` | 213 029 | SCORED | +3 582 | +1 166.28 | −481 vs J2 | +8 452.28 |
| **L1** | **tighter outer (2.5/3.5/5, 3/1/1)** | `trader_round1_ash_deep_l1.py` | **214 525** | **SCORED** | +3 459 | **+1 786.31** | **+21 vs K2** | **+9 072.31** |
| L2 | split outer (2.5/4.5/7) | `trader_round1_ash_deep_l2.py` | 214 875 | SCORED | +3 482 | +1 726.56 | −38 vs K2 | +9 012.56 |
| L4 | 4-level tight (2.5/4/6/8) | `trader_round1_ash_deep_l4.py` | 215 034 | SCORED | +3 535 | +1 259.84 | −505 vs K2 | +8 545.84 |
| L5 | K2 + sizes (1/3/5) | `trader_round1_ash_deep_l5.py` | 215 204 | SCORED | +3 497 | +1 770.44 | +6 vs K2 | +9 056.44 |
| L5b | K2 + sizes (1/2/4) | `trader_round1_ash_deep_l5b.py` | 215 477 | SCORED | +3 497 | +1 770.44 | +6 vs K2 | +9 056.44 |
| L6 | K2 weights 5/2/2 | `trader_round1_ash_deep_l6.py` | 215 623 | SCORED | +3 515 | +1 688.69 | −76 vs K2 | +8 974.69 |

PEPPER PnL was **+7 286.00 on every single submission** (as designed —
buy_hold_80 pin held perfectly across all 10 variants).

## Top-level ranking (ASH-only PnL, descending)

1. **L1** +1 786.31 (**+826.53 vs baseline, +391.75 vs F3a, +21.44 vs K2**) — tighter outer ladder (2.5/3.5/5, 3/1/1)
2. L5/L5b +1 770.44 (+810.66) — K2 + size mults (no effect: identical to K2)
3. K2 +1 764.88 (+805.10) — tight outer ladder (2.5/4/6, 3/1/1)
4. K5 +1 737.00 (+777.22) — asymmetric (buy tight, sell wide)
5. L2 +1 726.56 (+766.78) — split outer (2.5/4.5/7)
6. L6 +1 688.69 (+728.91) — K2 with weights 5/2/2
7. J2 +1 646.97 (+687.19) — 3-level inner-heavy ladder (3/1/1 on 2.5/5/8)
8. F3a +1 394.56 (+434.78) — D5 empirical stack
3. J3 +1 371.75 (+411.97) — 4-level spread-gated ladder
4. I2a +1 365.34 (+405.56) — equal-weight 4-level ladder
5. F3d +1 268.00 (+308.22) — AS γ=5e-7
6. F2b +1 250.00 (+290.22) — m=2.5 + AS-continuous flatten
7. F3c +1 230.34 (+270.56) — ultra-mild Cartea β=0.1
8. F2d +1 222.38 (+262.59) — m=2.5 config-only
9. J7 +1 166.28 (+206.50) — weighted + gated combo (over-filtered)
10. F3e +1 096.62 (+136.84) — Cartea β=0.3
11. F2a +1 059.94 (+100.16) — AS γ=2e-6
12. F2c +1 035.53 (+75.75) — weighted_mid
13. baseline +959.78 (ref) — shipped `round1_test` (= C_h1_alt + buy_hold)
14. F3b +953.66 (−6.12) — D7 weighted_mid + AS
15. H5 +888.38 (−71.40) — slow-FV τ=500 (hypothesis refuted)

See `phase_f_analysis.md` for the deep-dive interpretation.
