# Strategy audit — `trader_round1_ash_deep_f3a.py`

- Strategy: `outputs/submissions/round_1/limit_80/trader_round1_ash_deep_f3a.py`
- FV source: `outputs/round_1/official_results/tutorial/round 1 trader/206432.json`

## ASH_COATED_OSMIUM

- Ticks replayed: **1000**
- Quotes emitted: **1564**
- Fills: **298** (19.1%)
- Realized PnL (mark-to-FV): **+58.00**

### Edge capture

| metric | value | interpretation |
|---|---:|---|
| Mean edge per quote | +1.5582 | favorable (quote on the profitable side of FV) |
| Mean edge per fill | +0.4988 | favorable (quote on the profitable side of FV) |
| Markout h=1 per fill | +0.4694 | favorable (quote on the profitable side of FV) |
| Markout h=5 per fill | +0.4261 | favorable (quote on the profitable side of FV) |
| Markout h=20 per fill | +0.6021 | favorable (quote on the profitable side of FV) |
| Markout h=50 per fill | +1.5674 | favorable (quote on the profitable side of FV) |

### Per-side breakdown

**bid**: n_quotes=1023, n_fills=35, mean_edge=+0.569
  - fill mean_edge=+0.255
  - markout h=1: +0.259
  - markout h=5: +0.190
  - markout h=20: +0.317
  - markout h=50: +1.539
**ask**: n_quotes=541, n_fills=8, mean_edge=+3.429
  - fill mean_edge=+1.567
  - markout h=1: +1.392
  - markout h=5: +1.458
  - markout h=20: +1.849
  - markout h=50: +1.673

## INTARIAN_PEPPER_ROOT

- Ticks replayed: **1000**
- Quotes emitted: **5**
- Fills: **5** (100.0%)
- Realized PnL (mark-to-FV): **+7349.03**

### Edge capture

| metric | value | interpretation |
|---|---:|---|
| Mean edge per quote | -5.9000 | adverse (quote on the unfavorable side of FV) |
| Mean edge per fill | -5.9000 | adverse (quote on the unfavorable side of FV) |
| Markout h=1 per fill | -8.2002 | adverse (quote on the unfavorable side of FV) |
| Markout h=5 per fill | -7.8000 | adverse (quote on the unfavorable side of FV) |
| Markout h=20 per fill | -6.3000 | adverse (quote on the unfavorable side of FV) |
| Markout h=50 per fill | -3.3000 | adverse (quote on the unfavorable side of FV) |

### Per-side breakdown

**bid**: n_quotes=5, n_fills=5, mean_edge=-5.900
  - fill mean_edge=-5.900
  - markout h=1: -8.200
  - markout h=5: -7.800
  - markout h=20: -6.300
  - markout h=50: -3.300
