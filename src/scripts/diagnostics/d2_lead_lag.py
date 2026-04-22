"""Diagnostic D2 — Cross-product lead-lag (F4 hypothesis).

Tests whether any product pair has sufficient cross-correlation on lagged
returns to justify a cross-product trading strategy. The current
per-product STRATEGY_REGISTRY architecture cannot exploit this alpha.

|ρ| > 0.15 at any lag = confirmed leak; architectural change warranted.

Usage:
    PYTHONPATH=. .venv/bin/python -m src.scripts.diagnostics.d2_lead_lag
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

_DATA_DIRS = [Path("data/raw/round_1"), Path("data/raw/round_2")]
_LAGS = [-5, -3, -1, 0, 1, 3, 5, 10, 20]
_OUTPUT = Path("outputs/diagnostics/d2_lead_lag.md")


def _parse_mids(data_dir: Path) -> dict[str, list[tuple[int, int, float]]]:
    """Return {product: [(day, ts, mid), ...]} from all day CSVs."""
    by_product: dict[str, list[tuple[int, int, float]]] = defaultdict(list)
    for pf in sorted(data_dir.glob("prices_*.csv")):
        with pf.open(newline="") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                try:
                    day = int(row["day"])
                    ts = int(row["timestamp"])
                    product = row["product"]
                    mid = float(row["mid_price"])
                except (KeyError, ValueError):
                    continue
                by_product[product].append((day, ts, mid))
    for p in by_product:
        by_product[p].sort()
    return by_product


def _returns(rows: list[tuple[int, int, float]]) -> dict[tuple[int, int], float]:
    """(day, ts) -> log-return vs prior (day, ts) within the same day."""
    rets: dict[tuple[int, int], float] = {}
    prev_by_day: dict[int, tuple[int, float]] = {}
    for day, ts, mid in rows:
        if mid <= 0:
            continue
        prev = prev_by_day.get(day)
        if prev is not None and prev[1] > 0:
            import math

            rets[(day, ts)] = math.log(mid / prev[1])
        prev_by_day[day] = (ts, mid)
    return rets


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 30:
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _lag_corr(
    lead_rets: dict[tuple[int, int], float],
    lag_rets: dict[tuple[int, int], float],
    lag: int,
    tick_unit: int = 100,
) -> tuple[float | None, int]:
    """Corr(lead_ret[t], lag_ret[t + lag * tick_unit]).

    lag > 0 means lag_rets leads by `lag` ticks (positive lag = lag_rets is leader).
    Prosperity ticks jump by 100 in the timestamp column.
    """
    xs: list[float] = []
    ys: list[float] = []
    shift = lag * tick_unit
    for (day, ts), ret_a in lead_rets.items():
        ret_b = lag_rets.get((day, ts + shift))
        if ret_b is None:
            continue
        xs.append(ret_a)
        ys.append(ret_b)
    return _pearson(xs, ys), len(xs)


def main() -> None:
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out_lines: list[str] = [
        "# D2 — Cross-Product Lead-Lag Test",
        "",
        "Tests whether lagged returns on product A predict returns on product B. "
        "|ρ| > 0.15 at any lag = confirmed cross-product alpha the current "
        "per-product architecture cannot capture.",
        "",
    ]

    for data_dir in _DATA_DIRS:
        if not data_dir.exists():
            continue
        out_lines += [f"## {data_dir.name}", ""]
        by_product = _parse_mids(data_dir)
        products = sorted(by_product.keys())
        if len(products) < 2:
            out_lines += ["Only one product; skipping.", ""]
            continue

        rets = {p: _returns(by_product[p]) for p in products}

        header = "| Pair (A, B) | " + " | ".join(f"lag={l}" for l in _LAGS) + " | N |"
        sep = "|---|" + "|".join(["---"] * (len(_LAGS) + 1)) + "|"
        out_lines += [header, sep]

        for i, pa in enumerate(products):
            for pb in products[i + 1 :]:
                cells: list[str] = []
                n = 0
                for lag in _LAGS:
                    # For each lag, corr(return on A at t, return on B at t+lag).
                    # lag > 0 → B lags A, meaning A leads B.
                    # lag < 0 → A lags B, meaning B leads A.
                    corr, ncnt = _lag_corr(rets[pa], rets[pb], lag)
                    n = max(n, ncnt)
                    cells.append(_fmt(corr))
                out_lines.append(
                    f"| {pa} → {pb} | " + " | ".join(cells) + f" | {n} |"
                )
        out_lines += [""]

    out_lines += [
        "## Interpretation",
        "",
        "- **|ρ| > 0.15 at ANY lag:** architectural F4 is a confirmed leak. "
        "Cross-product engine needed.",
        "- **Peak at lag > 0:** leftmost product (A) leads rightmost (B). Front-run B.",
        "- **Peak at lag = 0:** contemporaneous correlation; still useful for basket arb.",
        "- **Peak at lag < 0:** second product (B) leads first (A). Swap roles.",
        "- **All lags ~ 0:** products are genuinely independent in this regime; F4 not a leak here.",
    ]

    _OUTPUT.write_text("\n".join(out_lines) + "\n")
    print(f"wrote {_OUTPUT}")


def _fmt(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:+.4f}"


if __name__ == "__main__":
    main()
