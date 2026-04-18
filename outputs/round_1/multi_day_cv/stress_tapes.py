"""Generate synthetic 1M-tick adversarial tapes from day -2 data.

Each tape is a MUTATION of the real day -2 tape. The bid/ask/volume
structure is preserved exactly; only the *mid* trajectory (and the
bid/ask prices shifted accordingly) is remapped. This keeps the
simulator's book-walk mechanics honest while varying only the
price evolution.

Tapes produced:
  - flat:     zero drift. Pure oscillation around a constant mid.
  - reversed: slope INVERTED (-0.001/tick). Price falls ~1000 over the day.
  - high_vol: drift preserved, residuals × 3.
  - stepped:  +0.001/tick for first half, -0.001/tick for second half.
  - mild_reversed: shallow negative drift (half-magnitude reversal).
  - late_reversed: normal drift until late in the day, then sharp reversal.
  - reversed_high_vol: full reversed drift with residuals × 3.
  - shock_down_recover: transient mid-day drawdown that later recovers.

Written to data/raw/round_1_stress/prices_round_1_day_{tape}.csv.
"""

from __future__ import annotations

import csv
from pathlib import Path

REAL_DAY = -2
SRC_DIR = Path("data/raw/round_1")
OUT_DIR = Path("data/raw/round_1_stress")
PRODUCT = "INTARIAN_PEPPER_ROOT"
HALF_DAY = 500_000
LATE_PIVOT = 750_000
DAY_END = 999_900


def load_day_rows(day: int) -> list[dict]:
    path = SRC_DIR / f"prices_round_1_day_{day}.csv"
    with path.open() as f:
        return list(csv.DictReader(f, delimiter=";"))


def fit_drift(rows: list[dict]) -> tuple[float, float]:
    data = []
    for r in rows:
        if r["product"] != PRODUCT or not r["mid_price"]:
            continue
        m = float(r["mid_price"])
        if m < 1000 or m > 20000:
            continue
        data.append((int(r["timestamp"]), m))
    n = len(data)
    sx = sum(t for t, _ in data); sy = sum(m for _, m in data)
    sxx = sum(t * t for t, _ in data); sxy = sum(t * m for t, m in data)
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    intercept = (sy - slope * sx) / n
    return slope, intercept


def shift_row(row: dict, new_mid: float, original_mid: float) -> dict:
    """Shift every price field in the row by (new_mid - original_mid)."""
    delta = new_mid - original_mid
    out = dict(row)
    for key in (
        "bid_price_1", "bid_price_2", "bid_price_3",
        "ask_price_1", "ask_price_2", "ask_price_3",
    ):
        if out.get(key):
            try:
                out[key] = str(int(round(float(out[key]) + delta)))
            except ValueError:
                pass
    if out.get("mid_price"):
        out["mid_price"] = f"{new_mid:.1f}"
    return out


def make_tape(label: str, transform_mid) -> None:
    """transform_mid(ts, original_mid, slope, intercept) -> new_mid."""
    rows = load_day_rows(REAL_DAY)
    slope, intercept = fit_drift(rows)
    # day-stamp becomes the label-specific "day" value for file metadata, but
    # we keep the timestamp/product structure intact.
    new_rows = []
    for r in rows:
        try:
            orig_mid = float(r["mid_price"]) if r["mid_price"] else None
        except ValueError:
            orig_mid = None
        if orig_mid is None or orig_mid < 1000 or orig_mid > 20000:
            # Non-PEPPER (ASH) rows or corrupted mid — pass through unchanged.
            new_rows.append(r)
            continue
        if r["product"] != PRODUCT:
            new_rows.append(r)
            continue
        ts = int(r["timestamp"])
        new_mid = transform_mid(ts, orig_mid, slope, intercept)
        new_rows.append(shift_row(r, new_mid, orig_mid))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"prices_{label}.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter=";")
        writer.writeheader()
        writer.writerows(new_rows)
    return out_path


def flat(ts, orig_mid, slope, intercept):
    """Subtract the drift component — residual around a constant baseline."""
    drift_line = slope * ts + intercept
    residual = orig_mid - drift_line
    return intercept + residual


def reversed_drift(ts, orig_mid, slope, intercept):
    """Invert drift: original slope +0.001 → new slope −0.001."""
    drift_line = slope * ts + intercept
    residual = orig_mid - drift_line
    new_drift = -slope * ts + intercept
    return new_drift + residual


def high_vol(ts, orig_mid, slope, intercept):
    """Amplify residual by 3x, drift unchanged."""
    drift_line = slope * ts + intercept
    residual = orig_mid - drift_line
    return drift_line + 3.0 * residual


def stepped(ts, orig_mid, slope, intercept):
    """+slope for first half, -slope for second half."""
    drift_line = slope * ts + intercept
    residual = orig_mid - drift_line
    if ts <= HALF_DAY:
        new_drift = slope * ts + intercept
    else:
        # Continuous at ts=half, then reverses.
        mid_at_half = slope * HALF_DAY + intercept
        new_drift = mid_at_half - slope * (ts - HALF_DAY)
    return new_drift + residual


def mild_reversed(ts, orig_mid, slope, intercept):
    """Half-strength negative drift for sensitivity testing."""
    drift_line = slope * ts + intercept
    residual = orig_mid - drift_line
    new_drift = (-0.5 * slope * ts) + intercept
    return new_drift + residual


def late_reversed(ts, orig_mid, slope, intercept):
    """Keep drift-up most of the day, then reverse sharply late."""
    drift_line = slope * ts + intercept
    residual = orig_mid - drift_line
    if ts <= LATE_PIVOT:
        new_drift = drift_line
    else:
        mid_at_pivot = slope * LATE_PIVOT + intercept
        # Reverse at 3x slope so the late-day drawdown is meaningful.
        new_drift = mid_at_pivot - (3.0 * slope * (ts - LATE_PIVOT))
    return new_drift + residual


def reversed_high_vol(ts, orig_mid, slope, intercept):
    """Full reversed drift plus amplified residual noise."""
    drift_line = slope * ts + intercept
    residual = orig_mid - drift_line
    new_drift = -slope * ts + intercept
    return new_drift + (3.0 * residual)


def shock_down_recover(ts, orig_mid, slope, intercept):
    """Transient drawdown: tests false-positive guard de-risking."""
    drift_line = slope * ts + intercept
    residual = orig_mid - drift_line
    shock = 0.0
    if HALF_DAY <= ts <= DAY_END:
        width = DAY_END - HALF_DAY
        progress = (ts - HALF_DAY) / width if width > 0 else 0.0
        # Negative triangular shock that bottoms at 300 ticks midway
        # through the second half, then recovers back to baseline.
        shock = -300.0 * (1.0 - abs((2.0 * progress) - 1.0))
    return drift_line + residual + shock


TAPES = {
    "flat": flat,
    "reversed": reversed_drift,
    "high_vol": high_vol,
    "stepped": stepped,
    "mild_reversed": mild_reversed,
    "late_reversed": late_reversed,
    "reversed_high_vol": reversed_high_vol,
    "shock_down_recover": shock_down_recover,
}


if __name__ == "__main__":
    for label, fn in TAPES.items():
        path = make_tape(label, fn)
        print(f"  wrote {path}")
