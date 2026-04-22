"""Diagnostic D1 — OBI / flow IC test (F1 + F5 predictive-signal hypothesis).

Tests whether book-imbalance and trade-flow signals have predictive power
for next-N-tick mid movement. If IC > 0.03 on either signal, we have
confirmed evidence that a predictive fair-value estimator would add alpha
— and that the existing reactive-only FairValueEngine is leaving P&L
on the table.

Output: per-product (product, N_ticks, IC_obi, IC_flow) table written to
outputs/diagnostics/d1_obi_ic.md.

Usage:
    PYTHONPATH=. .venv/bin/python -m src.scripts.diagnostics.d1_obi_ic
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

_DATA_DIRS = [
    Path("data/raw/round_1"),
    Path("data/raw/round_2"),
]
_FORWARD_HORIZONS = [10, 50, 100, 200, 500]
_OUTPUT = Path("outputs/diagnostics/d1_obi_ic.md")


def _parse_prices(path: Path) -> dict[str, list[dict]]:
    """Return {product: [row_dict, ...]} sorted by (day, timestamp)."""
    rows_by_product: dict[str, list[dict]] = defaultdict(list)
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            try:
                day = int(row["day"])
                ts = int(row["timestamp"])
                product = row["product"]
                b1p = _flt(row.get("bid_price_1"))
                b1v = _flt(row.get("bid_volume_1"))
                a1p = _flt(row.get("ask_price_1"))
                a1v = _flt(row.get("ask_volume_1"))
                mid = _flt(row.get("mid_price"))
            except (KeyError, ValueError):
                continue
            if mid is None or b1p is None or a1p is None:
                continue
            rows_by_product[product].append(
                {
                    "day": day,
                    "ts": ts,
                    "mid": mid,
                    "b1p": b1p,
                    "b1v": b1v or 0.0,
                    "a1p": a1p,
                    "a1v": a1v or 0.0,
                }
            )
    for p in rows_by_product:
        rows_by_product[p].sort(key=lambda r: (r["day"], r["ts"]))
    return rows_by_product


def _flt(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _parse_trades(path: Path) -> dict[tuple[str, int, int], list[dict]]:
    """Return {(product, day, timestamp): [trade_dict, ...]}."""
    day = _day_from_filename(path.name)
    trades_by_key: dict[tuple[str, int, int], list[dict]] = defaultdict(list)
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            try:
                ts = int(row["timestamp"])
                product = row["symbol"]
                qty = int(row["quantity"])
                price = float(row["price"])
            except (KeyError, ValueError):
                continue
            buyer = row.get("buyer") or ""
            seller = row.get("seller") or ""
            # Flow convention: buyer-initiated = +qty, seller-initiated = -qty.
            # If both are labeled, trade is between named parties = 0.
            if buyer and not seller:
                signed = +qty
            elif seller and not buyer:
                signed = -qty
            else:
                signed = 0
            trades_by_key[(product, day, ts)].append(
                {"price": price, "qty": qty, "signed": signed}
            )
    return trades_by_key


def _day_from_filename(name: str) -> int:
    import re

    m = re.search(r"day_(-?\d+)", name)
    return int(m.group(1)) if m else 0


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 30:
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _rank(xs: list[float]) -> list[float]:
    """Average-rank transform (ties get mean rank)."""
    indexed = sorted(enumerate(xs), key=lambda p: p[1])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 30:
        return None
    return _pearson(_rank(xs), _rank(ys))


def _compute_ic(rows: list[dict], trades_by_key: dict, horizon: int) -> dict:
    """Compute OBI IC and flow IC at given forward horizon."""
    obi_feat: list[float] = []
    flow_feat: list[float] = []
    fwd_ret: list[float] = []

    n = len(rows)
    for i in range(n - horizon):
        row = rows[i]
        future = rows[i + horizon]
        # Skip cross-day lookahead.
        if future["day"] != row["day"]:
            continue
        if row["mid"] == 0:
            continue
        ret = (future["mid"] - row["mid"]) / row["mid"]
        # OBI: top-of-book imbalance.
        total = row["b1v"] + row["a1v"]
        if total <= 0:
            continue
        obi = (row["b1v"] - row["a1v"]) / total
        # Flow: signed trade volume at this timestamp.
        key = (row.get("product", ""), row["day"], row["ts"])
        ts_trades = trades_by_key.get(key, [])
        signed_vol = sum(t["signed"] for t in ts_trades)

        obi_feat.append(obi)
        flow_feat.append(float(signed_vol))
        fwd_ret.append(ret)

    return {
        "n": len(fwd_ret),
        "ic_obi_pearson": _pearson(obi_feat, fwd_ret),
        "ic_obi_spearman": _spearman(obi_feat, fwd_ret),
        "ic_flow_pearson": _pearson(flow_feat, fwd_ret),
        "ic_flow_spearman": _spearman(flow_feat, fwd_ret),
    }


def _attach_product(rows: list[dict], product: str) -> None:
    for r in rows:
        r["product"] = product


def main() -> None:
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out_lines: list[str] = [
        "# D1 — OBI / Flow IC Test",
        "",
        "Tests whether top-of-book imbalance (OBI) and signed trade flow "
        "predict next-N-tick mid returns. |IC| > 0.03 indicates alpha the "
        "current reactive FairValueEngine cannot capture.",
        "",
        "| Round | Product | Horizon | N | IC(OBI, Pearson) | IC(OBI, Spearman) | IC(Flow, Pearson) | IC(Flow, Spearman) |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for data_dir in _DATA_DIRS:
        if not data_dir.exists():
            continue
        round_label = data_dir.name
        price_files = sorted(data_dir.glob("prices_*.csv"))
        trade_files = sorted(data_dir.glob("trades_*.csv"))

        # Merge across all days in the round.
        all_rows: dict[str, list[dict]] = defaultdict(list)
        all_trades: dict[tuple[str, int, int], list[dict]] = defaultdict(list)

        for pf in price_files:
            per = _parse_prices(pf)
            for product, rows in per.items():
                _attach_product(rows, product)
                all_rows[product].extend(rows)
        for tf in trade_files:
            for k, v in _parse_trades(tf).items():
                all_trades[k].extend(v)

        for product, rows in sorted(all_rows.items()):
            rows.sort(key=lambda r: (r["day"], r["ts"]))
            for h in _FORWARD_HORIZONS:
                res = _compute_ic(rows, all_trades, h)
                out_lines.append(
                    f"| {round_label} | {product} | {h} | {res['n']} | "
                    f"{_fmt(res['ic_obi_pearson'])} | "
                    f"{_fmt(res['ic_obi_spearman'])} | "
                    f"{_fmt(res['ic_flow_pearson'])} | "
                    f"{_fmt(res['ic_flow_spearman'])} |"
                )

    out_lines += [
        "",
        "## Interpretation",
        "",
        "- **IC > 0.03:** signal has predictive power. Worth wiring into "
        "FairValueEngine as a predictive estimator component.",
        "- **IC > 0.08:** strong signal — comparable to what top quant funds "
        "deploy on real markets. Priority build.",
        "- **IC ~ 0:** signal has no edge in this regime; current reactive "
        "estimators are fine.",
        "- **Spearman >> Pearson:** signal is monotonic but non-linear; "
        "use quantile-based feature rather than raw value.",
        "",
        "## Implications for F1 / F5",
        "",
        "F1 (observational-only FlowAnalyzer): confirmed a leak if |IC(Flow)| > 0.03.",
        "F5 (all estimators reactive): confirmed a leak if |IC(OBI)| > 0.03.",
    ]

    _OUTPUT.write_text("\n".join(out_lines) + "\n")
    print(f"wrote {_OUTPUT}")


def _fmt(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:+.4f}"


if __name__ == "__main__":
    main()
