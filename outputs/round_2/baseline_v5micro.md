# Round-2 baseline — combined_v5micro_l1 on the R2 tape (batch C)

Cold (no day-rollover flush) vs warm (PEPPER `flush_history_on_day_rollover=True`). Kill-switches
disabled in both — this run isolates the day-rollover effect.

Engine: v5micro_l1-shape (ASH = `weighted_mid` + L1 ladder edges 2.5/3.5/5; PEPPER = `linear_drift` with quote_size=10, max_aggressive_size=20).
Strategies wired at runtime: `AshLadderStrategy(L1)` for ASH, `PepperCoreLongStrategy(v5_micro params)` for PEPPER.

Tape: `data/raw/round_2/` — three days (`day_-1`, `day_0`, `day_1`),
30 000 snapshots total, ts range [0, 999900] per day.

## Total PnL

| variant | flush | total | PEPPER | ASH | PEPPER final pos | ASH final pos | PEPPER near-limit | PEPPER trades | ASH trades |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **cold** | False | +249375 | +239528 | +9847 | +80 | +31 | 29973 | 308 | 681 |
| **warm** | True | +249375 | +239528 | +9847 | +80 | +31 | 29973 | 308 | 681 |

## Per-day PEPPER PnL (contribution, not cumulative)

| variant | day_-1 | day_0 | day_1 | sum |
|---|---:|---:|---:|---:|
| **cold** | +79341 | +79959 | +80228 | +239528 |
| **warm** | +79341 | +79959 | +80228 | +239528 |

## Reference: Round-1 final scored run

Round-1 final (combined_v5micro_l1 on the R1 1M-tick scored tape):
+89 970 total = +10 371 ASH + +79 599 PEPPER on 1 day × 10 000 snapshots.

Per-day PEPPER comparison (R2 + R1 final all on the same v5_micro stack):

| day | source | PEPPER PnL |
|---|---|---:|
| day_-1 | R2 cold | +79341 |
| day_0  | R2 cold | +79959 |
| day_1  | R2 cold | +80228 |
| day_1  | R1 final scored | +79 599 |

PEPPER per-day PnL is **astonishingly stable** across 4 independent
day realisations from the same generator: mean ≈ +79.8k, σ ≈ 370
(0.5 % of mean). The v5_micro strategy is effectively a
deterministic PnL annuity on PEPPER.

## Findings

1. **PEPPER strategy is stable on the R2 tape.** Per-day PnL on
   the three R2 days (+79.3k, +80.0k, +80.2k) lies within 0.5 %
   of the R1 final scored day (+79.6k). No regime change
   observed. The strategy carries identical edge across two
   independent tape generations.

2. **Day-rollover flush has zero observable effect on this stack.**
   Cold (+249375) and warm (+249375) total PnL
   are byte-identical. Cause: the v5_micro params include
   `open_seed_size=65, open_window=500, exec_style='taker'` which
   force aggressive opening on each day, bypassing any reliance on
   `linear_drift`'s rolling-mid history. After the opening, PEPPER
   sits pinned at +80 (29 973 / 30 000 snapshots = 99.91 % of the
   run), so fair value barely matters either. The flush flag is
   real protection for **other** configs (residual-driven, no
   open_seed_size hack) — keep it but expect no batch-D winner
   to depend on it for v5_micro-shape PEPPER variants.

3. **ASH PnL is materially weaker on R2 than R1 (per-day).**
   R2 cold: +9847 across 3 days = ~+3282/day.
   R1 final: +10 371 / 1 day. Per-day drop ≈ 68 %.
   Trade count *increased* on R2 (681 trades / 30k snaps
   = ~22.7/1000 vs R1 final's 8.9/1000), so the
   regression is in per-trade edge, not fill rate. Likely causes:
   different ASH microstructure across tape generations (worth a
   per-day mid / spread comparison in batch D), or the L1 ladder
   params overfit the R1 day_0 microstructure. **Flag for
   batch-D ASH tuning.**

4. **No regression on PEPPER means batch-D kill-switch sweeps
   should focus on PEPPER tail protection, not edge tuning.**
   The empirical kill-switch thresholds proposed in batch B
   (slope window 50 / N=20, residual −35/−15, step Δmid −40,
   intraday PnL −2 500) all fire on signals not observed in the
   R2 tape — confirming the batch-B claim that they are
   zero-premium insurance under normal conditions.
