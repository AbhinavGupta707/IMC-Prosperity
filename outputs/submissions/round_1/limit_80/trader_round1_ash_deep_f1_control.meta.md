# F1 control — `trader_round1_test.py` (reused)

**Upload label:** F1 (Phase-F control refresh).
**Status:** Bundle already exists at `trader_round1_test.py`; no new
build required.

## What this is

`trader_round1_test.py` — the shipped `round1_test_engine_config`
bundle — already encodes exactly the Phase-F F1 spec:

- **ASH**: wall_mid, m=1.5, t=0.5, skew=4.0, flatten=0.7, h=48
  (identical to C_h1_alt)
- **PEPPER**: buy-and-hold, max_aggressive_size=80 (identical to
  the PLAN's PEPPER pin)

Per `outputs/round_1/ash_deep_dive/PLAN.md` sec 7.1 F1:

> "F1 control — shipped `C_h1_alt` on buy_hold pepper — anchor the
> ASH-only delta frame. Since existing C_h1_alt was uploaded with
> V3_nearhold PEPPER not buy_hold, this gives us an ASH-with-buy_hold
> reference."

The key insight: the previously-shipped `trader_round1_h1.py`
uploaded C_h1_alt + the `round1_h1_engine_config` PEPPER (linear_drift
market-making). The observed official PnL for H1 was +2 780
(ASH +983 + PEPPER +1 797). For the Phase-F calibration table we
want the ASH-only contribution at the **exact PEPPER pin used by
every Phase-F variant**, which is buy_hold_80.

## Fingerprint

| File | SHA256 |
|---|---|
| `trader_round1_test.py` | `fa1ba4e6576d699db3ab6f17779b6de91a6b8fc0929b3a3c2469dd1ca5a4a3bf` |

Size 97 201 bytes; SHA matches the `README.md` table at the `limit=80`
commit. No re-export needed for F1.

## Expected outcome on official

From `outputs/round_1/official_results/`: pure buy-and-hold PEPPER
was tested separately as `trader_round1_test.py` and scored +8 245
total PnL on day 0 (+7 286 PEPPER + +959 ASH). That figure is the
closest historical analog to F1's expected outcome.

The ASH PnL should be approximately +960-990 (matches the
previously-observed `Alt` leg ASH PnL since the ASH configs are
byte-identical between `test` and `h1` engine factories).

## Upload instructions

Upload `outputs/submissions/round_1/limit_80/trader_round1_test.py`
as the F1 control bundle. Record the IMC-assigned submission ID and
append it to `outputs/round_1/ash_deep_dive/phase_f/submission_log.md`
(to be created after the first actual upload).
