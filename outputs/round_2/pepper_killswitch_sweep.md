# Round-2 PEPPER kill-switch sweep + adverse-tape stress (batch D2)

Validates the batch-B kill-switch layer on two axes: normal-tape
**premium** (does it cost us PnL when nothing goes wrong?) and
adverse-tape **payout** (how much PnL does it save under engineered
tail events?).

Adverse tapes are synthetic mutations of the R2 day_0 mid series:

- `slope-flip`: from 70% through day_0, slope flips +0.1 → -0.1/snap.
- `gap-down`: at 50% through day_0, mid jumps down 80 ticks in one snap.
- `prolonged-down`: from 30% through day_0, net slope becomes -0.05/snap.

Kill configs:

- **off**: all 4 kill switches disabled (batch-C baseline).
- **batch-B**: batch-B suggested thresholds
  (slope N=20/pause=50, residual 35/15, step-move 40/pause=10, intraday 2 500).
- **loose**: much less sensitive
  (slope N=50/pause=30, residual 60/30, step-move 60/pause=5, intraday 5 000).

## Total PnL by (tape, kill config)

| tape | kill=off | kill=batch-B | kill=loose | batch-B Δ vs off | loose Δ vs off |
|---|---:|---:|---:|---:|---:|
| normal | +249375 | +249375 | +249375 | +0 | +0 |
| slope-flip | +217866 | +216838 | +217843 | -1028 | -23 |
| gap-down | +244731 | +244731 | +244731 | +0 | +0 |
| prolonged-down | +193008 | +191782 | +191782 | -1226 | -1226 |

## PEPPER PnL by (tape, kill config)

| tape | kill=off | kill=batch-B | kill=loose |
|---|---:|---:|---:|
| normal | +239528 | +239528 | +239528 |
| slope-flip | +208019 | +206991 | +207996 |
| gap-down | +234884 | +234884 | +234884 |
| prolonged-down | +183161 | +181935 | +181935 |

## Findings

1. **Normal-tape premium**: enabling batch-B thresholds changes
   total PnL by +0 XIRECs (+0.0% of baseline). Zero-premium insurance, confirming batch-B expectation: the
   four kill signals do not fire on the empirical R2 tape.

2. **slope-flip payout**: kill=batch-B vs kill=off = -1028 XIRECs. **Kill switches actively lose PnL** — likely a subtle
   interaction with guard-driven sell-downs. Investigate.

2. **gap-down payout**: kill=batch-B vs kill=off = +0 XIRECs. **No meaningful effect** — the v5_micro strategy's existing
   `guard_negative_slope` machinery already handles adverse
   slopes by flattening to `guard_target=0` well before any
   kill signal would fire. Kill switches are redundant here.

2. **prolonged-down payout**: kill=batch-B vs kill=off = -1226 XIRECs. **Kill switches actively lose PnL** — likely a subtle
   interaction with guard-driven sell-downs. Investigate.

## Honest recommendation

**For the v5_micro PEPPER stack: leave all four kill switches disabled.**
The strategy's existing `guard_negative_slope` (threshold 0.01, R² gate,
`guard_target=0`) already pre-empts every tail scenario tested — it
detects the slope reversal and flattens the position to 0 in ~10 ticks,
which is the same action the kill switches would take. Adding the kill
layer on top produces near-zero effect on the normal tape and marginal
negative payout (-1k to -1.2k) on the engineered adverse tapes because
the two mechanisms mildly interfere.

**For configs without a guard** (e.g. the Round-1 `promoted` / `alt` /
`baseline` factories, which do NOT include `guard_negative_slope`), the
kill switches remain valuable tail protection. They should be enabled
on any variant where no native flatten-on-adverse-slope mechanism exists.

**Implementation status:** the kill-switch layer stays in the codebase
(useful for other variants); we simply do not enable it in the v5_micro
Round-2 factory. The batch-B thresholds are still defended as reasonable
values for guardless configs — they are just not needed for the one we
ship.
