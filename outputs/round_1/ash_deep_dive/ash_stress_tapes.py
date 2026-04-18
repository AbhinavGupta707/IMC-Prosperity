"""Generate ASH-specific stress tapes from day -2 data.

The existing ``outputs/round_1/multi_day_cv/stress_tapes.py`` only
mutates PEPPER rows. This script mirrors its structure but mutates
ASH_COATED_OSMIUM rows (leaves PEPPER unchanged). Each output tape
is a full one-day replay that can be consumed by
``run_ash_research.py --phase e``.

Tapes produced (PLAN.md §6.1):
  - ash_flat           — zero oscillation around the anchor (10 000)
  - ash_amp3x          — residuals around anchor amplified 3x (vol regime)
  - ash_narrow_spread  — touch spread compressed 16 -> 12 ticks
  - ash_thin_book      — level-1 volumes multiplied by 0.5
  - ash_anchor_shift   — anchor steps 10 000 -> 10 025 at mid-day
  - ash_one_sided_heavy — 2x rate of one-sided snapshots

Written to ``data/raw/round_1_ash_stress/prices_round_1_day_<label>.csv``.
The corresponding trades file (if needed) is copied from the source
day so the replay engine sees a valid trade tape.

Each transform preserves the PEPPER rows byte-for-byte so that
Phase-E candidate evaluations keep PEPPER at its pinned buy-and-hold
leg. ASH row transforms are isolated to the price columns
(bid/ask prices, volumes, and the ``mid_price`` column).
"""

from __future__ import annotations

import contextlib
import csv
import random
import shutil
from collections.abc import Callable
from pathlib import Path

SRC_DIR = Path("data/raw/round_1")
OUT_DIR = Path("data/raw/round_1_ash_stress")
SOURCE_DAY = -2
ASH = "ASH_COATED_OSMIUM"
ANCHOR = 10_000
HALF_DAY = 500_000
ONE_SIDED_RATE = 0.16  # 2x the ~8% baseline measured in the Phase-1 dossier


RowTransform = Callable[[dict[str, str], random.Random], dict[str, str]]


# ------------------------------------------------------- helpers


def _row_mid(row: dict[str, str]) -> float | None:
    try:
        v = float(row["mid_price"]) if row.get("mid_price") else None
    except ValueError:
        return None
    return v


def _row_set_mid(row: dict[str, str], new_mid: float) -> None:
    row["mid_price"] = f"{new_mid:.1f}"


def _shift_prices(row: dict[str, str], delta: int) -> None:
    """Shift every bid/ask price column by an integer offset."""
    for col in (
        "bid_price_1", "bid_price_2", "bid_price_3",
        "ask_price_1", "ask_price_2", "ask_price_3",
    ):
        v = row.get(col)
        if not v:
            continue
        try:
            row[col] = str(round(float(v) + delta))
        except ValueError:
            continue


def _tune_l1_volume(row: dict[str, str], factor: float) -> None:
    for col in ("bid_volume_1", "ask_volume_1"):
        v = row.get(col)
        if not v:
            continue
        try:
            scaled = max(1, round(float(v) * factor))
        except ValueError:
            continue
        row[col] = str(scaled)


def _clear_side(row: dict[str, str], side: str) -> None:
    """Remove all levels from one side of the book."""
    for lvl in (1, 2, 3):
        row[f"{side}_price_{lvl}"] = ""
        row[f"{side}_volume_{lvl}"] = ""


# ------------------------------------------------------- transforms


def t_flat(row: dict[str, str], rng: random.Random) -> dict[str, str]:
    """Zero oscillation: mid_price forced to the anchor, prices shifted."""
    del rng
    orig = _row_mid(row)
    if orig is None:
        return row
    delta = ANCHOR - orig
    _shift_prices(row, round(delta))
    _row_set_mid(row, float(ANCHOR))
    return row


def t_amp3x(row: dict[str, str], rng: random.Random) -> dict[str, str]:
    """Residual from anchor amplified 3x (vol regime)."""
    del rng
    orig = _row_mid(row)
    if orig is None:
        return row
    residual = orig - ANCHOR
    new_mid = ANCHOR + 3.0 * residual
    delta = new_mid - orig
    _shift_prices(row, round(delta))
    _row_set_mid(row, new_mid)
    return row


def t_narrow_spread(row: dict[str, str], rng: random.Random) -> dict[str, str]:
    """Pull L1 bid UP by 2 and L1 ask DOWN by 2 (touch shrinks 16 -> 12)."""
    del rng
    bp = row.get("bid_price_1")
    ap = row.get("ask_price_1")
    if bp:
        with contextlib.suppress(ValueError):
            row["bid_price_1"] = str(int(float(bp)) + 2)
    if ap:
        with contextlib.suppress(ValueError):
            row["ask_price_1"] = str(int(float(ap)) - 2)
    # Recompute mid_price if both sides present.
    try:
        b = int(row["bid_price_1"]) if row.get("bid_price_1") else None
        a = int(row["ask_price_1"]) if row.get("ask_price_1") else None
        if b is not None and a is not None:
            row["mid_price"] = f"{(b + a) / 2.0:.1f}"
    except ValueError:
        pass
    return row


def t_thin_book(row: dict[str, str], rng: random.Random) -> dict[str, str]:
    del rng
    _tune_l1_volume(row, factor=0.5)
    return row


def t_anchor_shift(row: dict[str, str], rng: random.Random) -> dict[str, str]:
    """Anchor steps 10000 -> 10025 at timestamp >= HALF_DAY."""
    del rng
    try:
        ts = int(row["timestamp"])
    except ValueError:
        return row
    if ts < HALF_DAY:
        return row
    orig = _row_mid(row)
    if orig is None:
        return row
    residual = orig - ANCHOR
    new_mid = (ANCHOR + 25) + residual
    delta = new_mid - orig
    _shift_prices(row, round(delta))
    _row_set_mid(row, new_mid)
    return row


def t_one_sided_heavy(row: dict[str, str], rng: random.Random) -> dict[str, str]:
    """Drop one side at random with probability ONE_SIDED_RATE.

    Mutates the row to clear one side half the time (evenly split
    between bid-empty and ask-empty) for the target probability.
    """
    draw = rng.random()
    if draw < ONE_SIDED_RATE / 2:
        _clear_side(row, "bid")
        row["mid_price"] = ""  # mid undefined when one-sided
    elif draw < ONE_SIDED_RATE:
        _clear_side(row, "ask")
        row["mid_price"] = ""
    return row


TAPES: dict[str, RowTransform] = {
    "ash_flat": t_flat,
    "ash_amp3x": t_amp3x,
    "ash_narrow_spread": t_narrow_spread,
    "ash_thin_book": t_thin_book,
    "ash_anchor_shift": t_anchor_shift,
    "ash_one_sided_heavy": t_one_sided_heavy,
}


# ------------------------------------------------------- generator


def load_rows(day: int) -> list[dict[str, str]]:
    path = SRC_DIR / f"prices_round_1_day_{day}.csv"
    with path.open(newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        return list(reader)


def write_rows(label: str, rows: list[dict[str, str]]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Give each tape the same "day" field so the replay engine treats
    # it as a single day. We relabel day = 99 for all tapes so they
    # can't accidentally merge with real day files.
    for r in rows:
        r["day"] = "99"
    out = OUT_DIR / f"prices_round_1_day_{label}.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    # Copy the source day's trades file so the replay engine has
    # something to consume. Trades are passed through untouched — the
    # stress transforms only affect the price book, not counterparty
    # trade events.
    src_trades = SRC_DIR / f"trades_round_1_day_{SOURCE_DAY}.csv"
    dst_trades = OUT_DIR / f"trades_round_1_day_{label}.csv"
    if src_trades.exists():
        shutil.copy(src_trades, dst_trades)
    return out


def generate_tape(label: str, transform: RowTransform, *, seed: int = 0) -> Path:
    rng = random.Random(seed)
    rows = load_rows(SOURCE_DAY)
    out_rows: list[dict[str, str]] = []
    for row in rows:
        new_row = dict(row)
        if new_row["product"] == ASH:
            new_row = transform(new_row, rng)
        out_rows.append(new_row)
    path = write_rows(label, out_rows)
    return path


def main() -> int:
    for label, transform in TAPES.items():
        p = generate_tape(label, transform, seed=abs(hash(label)) % (2**31))
        print(f"  wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
