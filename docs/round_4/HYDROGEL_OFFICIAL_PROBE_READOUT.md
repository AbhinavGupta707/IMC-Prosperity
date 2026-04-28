# HYDROGEL Official Probe Readout

Date: 2026-04-27

Inputs added under `r4 Sim Results/`:

- `flat 95k.zip` extracted to `r4 Sim Results/flat95k/`
- `new flat 995.zip` extracted to `r4 Sim Results/new_flat995/`

## Headline

The probes confirm the prior HYDROGEL diagnosis:

1. The official 100k HYD score is dominated by carrying a short position into a
   favorable late mark, not by realized round-trip edge.
2. Narrowing HYDROGEL take width from `32` to `28` is worse in the official
   high-mean window because it sells earlier and cheaper, then ends with the
   same `-200` position.
3. More HYD PnL will not come from simple width tightening or arbitrary late
   flattening. It requires regime-aware inventory timing: avoid cheap early
   shorts in high-mean/uptrend windows, then short higher or after a turn.

## Official Results

| candidate | total PnL | HYD PnL | HYD final pos | HYD cash | last HYD fill | comment |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| old `flat995` | 66,586.9 | 1,680 | -200 | 2,005,030 | 23,600 | baseline |
| HYD-only | 1,680 | 1,680 | -200 | 2,005,030 | 23,600 | same HYD sleeve |
| `flat95k` | -4,339 | -4,339 | 0 | -4,339 | 96,600 | forced realization probe |
| `new_flat995` / width28 | 65,794.9 | 888 | -200 | 2,004,238 | 23,000 | width 28 probe |

The width28 probe changes only HYD. Other product PnL is unchanged from old
`flat995`, so the `-792` total delta is exactly the HYD delta.

## Flat95k Interpretation

Old HYD baseline:

- sells to `-200` by `23,600`;
- average sale price is `10025.15`;
- official implied terminal mark is `10016.75`;
- final PnL is `200 * (10025.15 - 10016.75) = 1,680`.

The flat95k probe:

- sells the same early short;
- forcibly buys back the `200` units from `95,000` to `96,600`;
- average cover price is about `10046.85`;
- realized PnL becomes `-4,339`.

Therefore the last part of the official path is worth about `+6,019` to the
baseline short versus forced realization. This is not evidence that the short
entry was good. It is evidence that the official 100k window happened to fall
from the 95k cover region into the terminal mark.

This was expected. The local official-log proxy predicted `-4,153`; the
official upload returned `-4,339`, close enough to trust the HYD replay proxy
for this narrow diagnostic.

## Width28 Interpretation

Width28 reached the same final `-200` position but sold it earlier:

- old width32 reached limit at `23,600`, cash `2,005,030`;
- width28 reached limit at `23,000`, cash `2,004,238`;
- both are marked at the same implied terminal mark `10016.75`;
- width28 loses `792` because its average entry is `3.96` ticks worse.

This rejects the simple hypothesis:

> Current take width is too conservative; just trade more aggressively.

In the official high-mean window, earlier shorting is toxic. If anything, the
official result argues for delaying shorts, widening short entry, capping early
short inventory, or requiring reversal confirmation.

## Path Geometry

Official HYD path windows:

| window | mean mid | min mid | max mid | end mid |
| --- | ---: | ---: | ---: | ---: |
| 0-23.6k | 10013.27 | 9993.0 | 10038.5 | 10035.0 |
| 23.6k-50k | 10032.88 | 10017.0 | 10047.0 | 10042.0 |
| 50k-70k | 10047.08 | 10032.5 | 10061.0 | 10043.0 |
| 70k-95k | 10042.67 | 10029.0 | 10053.0 | 10035.0 |
| 95k-99.9k | 10032.64 | 10016.0 | 10043.5 | 10017.0 |

The static 9988 anchor is too low for this 100k window. It causes the bot to
interpret normal high-regime prices as extreme sells.

## Hindsight Read

The official HYD L1 oracle has:

- force-flat opportunity: `15,585`;
- terminal-mark opportunity: `18,017`;
- current baseline: `1,680`.

The oracle's position path is not short-and-hold. It is dynamic:

- long into the early/middle rising high-regime windows;
- flips short later around the 63k-99.9k region;
- covers into the final if force-flat is required.

That means the missing PnL is dynamic regime/inventory timing, not merely a
better terminal wrapper.

## PnL Extraction Implications

Rejected:

- `width=28` as a broad upgrade;
- arbitrary official 95k flatten as a candidate;
- using the official `+1,680` as evidence that the low static anchor is robust.

Promising next experiments:

1. High-regime short delay/cap
   - If early HYD midpoint regime is above the final anchor, keep short cap
     small until reversal evidence appears.
   - The current early cap ends at 15k, but official damage happens as it builds
     full short between about 22k and 24k.

2. Turn-confirmed short entry
   - Do not sell solely because `bid >= 9988 + width`.
   - Require local slope/rolling-mean rollover, or use much wider sell entries
     while the rolling mean is rising.

3. R4 public-prefix calibration guard
   - The existing R3 public-prefix guard does not match R4 official.
   - A controlled R4 public/high-regime guard could test whether the official
     high-mean slice can be traded with a different anchor, without changing
     the final fallback profile.

4. Dynamic recycling
   - The oracle gap is large because it changes position, not because it takes
     one better entry.
   - The next serious HYD model should target inventory by regime state:
     low-regime fade, high-regime trend/turn, and terminal-risk mode.

## Current Recommendation

Do not promote `new_flat995` / width28.

Keep `flat995` as the safe fallback HYD sleeve for final-style 1M evaluation.

For official-upload learning, the next HYD probe should not be another small
width tweak. It should be a high-regime inventory-control probe: cap or delay
early shorts when the observed first-window mean is far above the 9988 final
anchor.

## Follow-Up Implemented

Implemented the high-regime inventory-control probe family and timing grid:

- `outputs/submissions/r4/submission_r4_probe_hyd_highregime_noshort_60k.py`
- `outputs/submissions/r4/submission_r4_probe_hyd_highregime_cap40_60k.py`
- `outputs/submissions/r4/submission_r4_probe_hyd_highregime_cap80_60k.py`
- `outputs/submissions/r4/submission_r4_probe_hyd_highregime_noshort_50k.py`
- `src/scripts/round_4/evaluate_hydrogel_highregime_grid.py`

Readout:

`docs/round_4/HYDROGEL_HIGHREGIME_PROBES.md`

Main proxy result: no-short until `60k` improves official-log HYD from `1,816`
to `6,613` while keeping the same final `-200` exposure. The gain comes from
selling the short inventory around average `10049.95` instead of `10026.08`,
not from changing the terminal mark. `cap40_60k` is the less aggressive backup
at `5,541`.
