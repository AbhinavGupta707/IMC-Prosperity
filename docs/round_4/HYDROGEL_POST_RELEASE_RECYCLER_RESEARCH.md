# HYDROGEL Post-Release Recycler Research

Date: 2026-04-27

## Question

Can we extract additional HYDROGEL alpha after the high-regime release around
60k by covering part of the short and re-shorting later?

## Method

Script:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.evaluate_hydrogel_post_release_recycler
```

Outputs:

- `outputs/round_4/hydrogel_post_release_recycler/post_release_recycler_full_replay.csv`
- `outputs/round_4/hydrogel_post_release_recycler/post_release_recycler_price_windows.csv`
- `outputs/round_4/hydrogel_post_release_recycler/post_release_recycler_price_summary.csv`

I tested two families:

- blunt `drop_cover`: cover after a post-release drop. This is a negative
  control because it changes terminal exposure if no rebound appears.
- `turn_recycle`: cover only after a drop and a local turn, then re-short only
  if the rebound pays a profit threshold.

The rolling price stress reports both raw score delta versus holding the
`-200` short and terminal-equalized delta that forces the policy back to `-200`
at the terminal bid. Terminal-equalized delta is the cleaner realized-recycler
measure.

## Official-Proxy Full Replay

Base official-proxy HYD for abortgate-long40 is `7370`.

| candidate | mode | pnl | delta_vs_base | final_pos | max_drawdown | events |
| --- | --- | --- | --- | --- | --- | --- |
| abortgate_long40_base | base | 7370.00 | 0.00 | -200 | -4100.00 |  |
| turn_cover_drop32_turn8_profit10_qty40 | turn_recycle | 7370.00 | 0.00 | -200 | -4100.00 |  |
| cover_drop28_qty40_no_force | drop_cover | 7228.00 | -142.00 | -200 | -4131.50 | cover@67300:10041x40\|reshort@68800:10043x40 |
| cover_drop20_qty40_no_force | drop_cover | 6969.00 | -401.00 | -200 | -3831.00 | cover@65800:10045x40\|reshort@69500:10048x40 |
| turn_cover_drop16_turn8_profit10_qty40 | turn_recycle | 6039.00 | -1331.00 | -160 | -3991.00 | cover@68400:10049x40 |
| turn_cover_drop24_turn8_profit10_qty40 | turn_recycle | 6039.00 | -1331.00 | -160 | -3991.00 | cover@68400:10049x40 |
| turn_cover_drop24_turn8_profit10_qty40_force | turn_recycle | 5935.00 | -1435.00 | -173 | -3991.00 | cover@68400:10049x40\|force@99900:10009x40 |
| cover_drop12_qty40_no_force | drop_cover | 5783.00 | -1587.00 | -160 | -3280.00 | cover@63600:10056x40 |

## Full 1M Replay Check

The controlled-cover versions are worse on the only historical full-day path
where the early high-regime trigger fires. This is important because the final
competition score is 1M ticks, not the 100k calibration slice.

| case | candidate | PnL | delta vs base | final pos | max drawdown | events |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| hist_day_3_1m | abortgate_long40_base | 56,320 | 0 | 12 | -12,100 |  |
| hist_day_3_1m | cover_drop28_qty40_no_force | 56,178 | -142 | 12 | -12,100 | cover@67300:10041x40\|reshort@68800:10043x40 |
| hist_day_3_1m | cover_drop20_qty40_no_force | 55,919 | -401 | 12 | -12,100 | cover@65800:10045x40\|reshort@69500:10048x40 |
| hist_day_3_1m | turn_cover_drop24_turn8_profit10_qty40_force | 55,073 | -1,247 | 12 | -12,100 | cover@68400:10049x40\|force@99900:10009x40 |
| hist_day_3_1m | turn_cover_drop16_turn8_profit10_qty40 | 34,778 | -21,542 | 12 | -18,526 | cover@68400:10049x40\|reshort@456000:10059x40 |
| hist_day_3_1m | cover_drop12_qty40_no_force | 34,621 | -21,699 | 12 | -18,615 | cover@63600:10056x40\|reshort@455900:10056x40 |

The large `-21k` loss is the key failure mode. Holding a partial cover for a
long time does not just alter terminal exposure; it changes the live position
state seen by the inner HYD engine and causes it to miss or distort later cycle
management.

## Best Rolling Historical Policies

Sorted by terminal-equalized mean across historical high-trigger windows:

| candidate | hist_windows | hist_raw_mean | hist_raw_min | hist_equalized_mean | hist_equalized_min | hist_action_rate | official_raw_delta | official_events |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cover_drop28_qty20_no_force | 28 | -179.64 | -1360.00 | -225.71 | -1520.00 | 0.75 | 40.00 | cover@67300:10041.0x20\|reshort@68800:10043.0x20 |
| turn_cover_drop32_turn4_profit6_qty20 | 28 | -233.21 | -1420.00 | -313.57 | -1580.00 | 0.89 | 0.00 |  |
| cover_drop20_qty20_no_force | 28 | -262.14 | -1520.00 | -325.00 | -1680.00 | 1.00 | 60.00 | cover@65800:10045.0x20\|reshort@69500:10048.0x20 |
| turn_cover_drop32_turn4_profit10_qty20 | 28 | -220.71 | -1420.00 | -330.00 | -1580.00 | 0.89 | 0.00 |  |
| turn_cover_drop32_turn8_profit6_qty20 | 28 | -246.07 | -1340.00 | -332.14 | -1500.00 | 0.89 | 0.00 |  |
| turn_cover_drop32_turn8_profit10_qty20 | 28 | -233.57 | -1340.00 | -342.86 | -1500.00 | 0.89 | 0.00 |  |
| cover_drop12_qty20_no_force | 28 | -304.64 | -1540.00 | -373.57 | -1700.00 | 1.00 | -780.00 | cover@63600:10056.0x20 |
| turn_cover_drop24_turn4_profit10_qty20 | 28 | -327.50 | -1420.00 | -436.43 | -1580.00 | 1.00 | -560.00 | cover@67800:10045.0x20 |
| turn_cover_drop24_turn4_profit6_qty20 | 28 | -343.21 | -1420.00 | -440.71 | -1580.00 | 1.00 | -560.00 | cover@67800:10045.0x20 |
| turn_cover_drop24_turn8_profit10_qty20 | 28 | -331.07 | -1340.00 | -445.71 | -1500.00 | 1.00 | -640.00 | cover@68400:10049.0x20 |

## Negative Controls

Worst blunt cover policies:

| candidate | hist_raw_mean | hist_raw_min | hist_equalized_mean | hist_action_rate | official_raw_delta | official_events |
| --- | --- | --- | --- | --- | --- | --- |
| cover_drop12_qty80_no_force | -1218.57 | -6160.00 | -1494.29 | 1.00 | -3120.00 | cover@63600:10056.0x80 |
| cover_drop20_qty80_no_force | -1048.57 | -6080.00 | -1300.00 | 1.00 | 240.00 | cover@65800:10045.0x80\|reshort@69500:10048.0x80 |
| cover_drop28_qty80_no_force | -718.57 | -5440.00 | -902.86 | 0.75 | 160.00 | cover@67300:10041.0x80\|reshort@68800:10043.0x80 |

## Readout

The post-release recycler does not justify promotion into the final HYD
strategy.

Reasons:

1. Every active rolling policy has negative mean delta. The best terminal-
   equalized historical result is still about `-226` HYD per triggered window.
2. Blunt covering is structurally dangerous. It often improves the feeling of
   inventory risk while giving up valuable terminal short exposure.
3. Turn-confirmed recyclers avoid some bad official actions when very strict,
   but the active versions are still negative on rolling stress and can damage
   full-day replay badly.
4. Official/day-3 post-60k does not offer a clean causal cover/re-short cycle.
   The profitable official HYD shape is still mostly: sell/release high, then
   keep the short into the late lower mark.
5. The remaining hindsight gap is real, but the causal tests say most of it is
   not low-hanging post-release recycling. It is path hindsight.

## Recommendation

Keep `abortgate15_long40_60` / `abortgate15_long20_60` as the HYD finalists.
Do not add a post-release recycler unless we make it tiny and diagnostic only.

If upload budget remains, a recycler upload is lower priority than finalizing
the HYD/non-HYD stack. The only defensible version would be a tiny diagnostic
negative-control pair, not a final candidate. Expected impact is approximately
`0` to negative on the official-style path; realistic upside is at most
hundreds of HYD in a favorable drop-and-rebound path, with demonstrated downside
from `-1k` to `-20k+` if it changes the live HYD position state.
