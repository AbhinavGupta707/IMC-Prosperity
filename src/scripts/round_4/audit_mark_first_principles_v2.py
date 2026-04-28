"""First-principles re-audit of Round 4 Mark alpha.

Goals:
- Quantify Mark22 OTM basket spillover into untouched strikes.
- Test sequential basket prediction beyond what was previously measured.
- Test Mark67 buy -> seller-next sequence broader than Mark55 only.
- Compute matched-frequency negative controls for Mark22 vs generic VEV bursts.
- Estimate per-Mark realistic edge ceilings with capacity & spread cost.

Outputs CSVs under outputs/round_4/mark_first_principles/.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_DATA_DIR = "/Users/abhinavgupta/Desktop/IMC-r4-counterparty/data/raw/round_4"
DEFAULT_OUT_DIR = "/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_first_principles"

OTM_STRIKES = ("VEV_5300", "VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500")
NEAR_STRIKES = ("VEV_5000", "VEV_5100", "VEV_5200")
ALL_VEV = (
    "VEV_4000",
    "VEV_4500",
    "VEV_5000",
    "VEV_5100",
    "VEV_5200",
    "VEV_5300",
    "VEV_5400",
    "VEV_5500",
    "VEV_6000",
    "VEV_6500",
)
HORIZONS = (1_000, 5_000, 10_000, 30_000)


@dataclass(frozen=True)
class Trade:
    day: int
    timestamp: int
    buyer: str
    seller: str
    symbol: str
    price: float
    quantity: int


@dataclass(frozen=True)
class Quote:
    day: int
    timestamp: int
    bid: float
    ask: float
    mid: float


def load_trades(data_dir: str, days: Iterable[int]) -> list[Trade]:
    rows: list[Trade] = []
    for day in days:
        path = os.path.join(data_dir, f"trades_round_4_day_{day}.csv")
        with open(path, newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                rows.append(
                    Trade(
                        day=day,
                        timestamp=int(row["timestamp"]),
                        buyer=row["buyer"].strip(),
                        seller=row["seller"].strip(),
                        symbol=row["symbol"].strip(),
                        price=float(row["price"]),
                        quantity=int(row["quantity"]),
                    )
                )
    return rows


def load_quotes(data_dir: str, days: Iterable[int]) -> dict[tuple[int, str], list[Quote]]:
    by_day_sym: dict[tuple[int, str], list[Quote]] = defaultdict(list)
    for day in days:
        path = os.path.join(data_dir, f"prices_round_4_day_{day}.csv")
        with open(path, newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                bid = row.get("bid_price_1") or ""
                ask = row.get("ask_price_1") or ""
                mid = row.get("mid_price") or ""
                if not bid or not ask or not mid:
                    continue
                try:
                    bid_v = float(bid)
                    ask_v = float(ask)
                    mid_v = float(mid)
                except ValueError:
                    continue
                by_day_sym[(day, row["product"])].append(
                    Quote(
                        day=day,
                        timestamp=int(row["timestamp"]),
                        bid=bid_v,
                        ask=ask_v,
                        mid=mid_v,
                    )
                )
    for v in by_day_sym.values():
        v.sort(key=lambda q: q.timestamp)
    return by_day_sym


def quote_at_or_before(quotes: list[Quote], ts: int) -> Quote | None:
    """Linear scan; data is small enough this is fine for the audit."""
    last: Quote | None = None
    for q in quotes:
        if q.timestamp > ts:
            break
        last = q
    return last


def detect_mark22_baskets(trades: list[Trade]) -> list[dict]:
    by_day_ts: dict[tuple[int, int], list[Trade]] = defaultdict(list)
    for t in trades:
        if t.seller != "Mark 22":
            continue
        if not t.symbol.startswith("VEV_"):
            continue
        by_day_ts[(t.day, t.timestamp)].append(t)
    baskets: list[dict] = []
    for (day, ts), group in by_day_ts.items():
        symbols = sorted({t.symbol for t in group})
        baskets.append(
            {
                "day": day,
                "timestamp": ts,
                "n_legs": len(symbols),
                "symbols": tuple(symbols),
                "qty_total": sum(t.quantity for t in group),
                "qty_max": max(t.quantity for t in group),
                "buyer_set": tuple(sorted({t.buyer for t in group})),
            }
        )
    baskets.sort(key=lambda b: (b["day"], b["timestamp"]))
    return baskets


def signed_mid_change(
    quotes_by_sym: dict[tuple[int, str], list[Quote]],
    day: int,
    symbol: str,
    ts: int,
    horizon: int,
) -> float | None:
    qs = quotes_by_sym.get((day, symbol))
    if qs is None:
        return None
    base = quote_at_or_before(qs, ts)
    if base is None:
        return None
    fut = quote_at_or_before(qs, ts + horizon)
    if fut is None or fut.timestamp == base.timestamp:
        return None
    return fut.mid - base.mid


def basket_spillover(
    baskets: list[dict], quotes_by_sym: dict[tuple[int, str], list[Quote]]
) -> list[dict]:
    rows: list[dict] = []
    for b in baskets:
        hit = set(b["symbols"])
        for sym in ALL_VEV:
            for h in HORIZONS:
                d = signed_mid_change(
                    quotes_by_sym, b["day"], sym, b["timestamp"], h
                )
                if d is None:
                    continue
                rows.append(
                    {
                        "day": b["day"],
                        "timestamp": b["timestamp"],
                        "n_legs": b["n_legs"],
                        "qty_total": b["qty_total"],
                        "symbol": sym,
                        "in_basket": sym in hit,
                        "horizon": h,
                        "mid_change": d,
                    }
                )
    return rows


def aggregate_spillover(rows: list[dict]) -> list[dict]:
    """Average mid_change by (day, symbol, in_basket, horizon)."""
    bucket: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        key = (r["day"], r["symbol"], r["in_basket"], r["horizon"])
        bucket[key].append(r["mid_change"])
    out: list[dict] = []
    for (day, sym, ib, h), vals in sorted(bucket.items()):
        if not vals:
            continue
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / max(n - 1, 1)
        std = math.sqrt(var)
        out.append(
            {
                "day": day,
                "symbol": sym,
                "in_basket": ib,
                "horizon": h,
                "n": n,
                "mean_mid_change": round(mean, 4),
                "std_mid_change": round(std, 4),
                "se_mid_change": round(std / math.sqrt(n), 4) if n > 1 else float("nan"),
            }
        )
    return out


def basket_to_basket(baskets: list[dict]) -> dict[str, list[dict]]:
    """Compute inter-basket arrival per day and conditional next-basket-within-h."""
    by_day: dict[int, list[dict]] = defaultdict(list)
    for b in baskets:
        by_day[b["day"]].append(b)
    intervals: list[dict] = []
    next_within: list[dict] = []
    for day, items in by_day.items():
        items.sort(key=lambda x: x["timestamp"])
        for i in range(len(items) - 1):
            cur = items[i]
            nxt = items[i + 1]
            dt = nxt["timestamp"] - cur["timestamp"]
            intervals.append(
                {
                    "day": day,
                    "timestamp": cur["timestamp"],
                    "next_timestamp": nxt["timestamp"],
                    "delta_ticks": dt,
                    "n_legs": cur["n_legs"],
                    "next_n_legs": nxt["n_legs"],
                }
            )
        for cur in items:
            t = cur["timestamp"]
            for h in HORIZONS:
                hit = any(
                    0 < (other["timestamp"] - t) <= h for other in items if other is not cur
                )
                next_within.append(
                    {
                        "day": day,
                        "timestamp": t,
                        "n_legs": cur["n_legs"],
                        "horizon": h,
                        "next_basket_within": int(hit),
                    }
                )
    return {"intervals": intervals, "next_within": next_within}


def matched_frequency_control(
    baskets: list[dict], all_trades: list[Trade]
) -> list[dict]:
    """For each Mark22 basket timestamp, find a non-Mark22 VEV trade burst with
    similar size at a different timestamp on the same day. Compute matched
    forward mid-change in OTM strikes for both."""
    by_day_ts_nonm22: dict[tuple[int, int], int] = defaultdict(int)
    for t in all_trades:
        if not t.symbol.startswith("VEV_"):
            continue
        if t.seller == "Mark 22" or t.buyer == "Mark 22":
            continue
        by_day_ts_nonm22[(t.day, t.timestamp)] += t.quantity
    timestamps_by_day_qty: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for (day, ts), qty in by_day_ts_nonm22.items():
        timestamps_by_day_qty[day].append((qty, ts))
    used_per_day: dict[int, set[int]] = defaultdict(set)
    rows: list[dict] = []
    for b in baskets:
        target_qty = b["qty_total"]
        candidates = sorted(
            timestamps_by_day_qty.get(b["day"], []),
            key=lambda x: abs(x[0] - target_qty),
        )
        for qty, ts in candidates:
            if ts in used_per_day[b["day"]]:
                continue
            used_per_day[b["day"]].add(ts)
            rows.append(
                {
                    "day": b["day"],
                    "basket_ts": b["timestamp"],
                    "basket_qty": target_qty,
                    "control_ts": ts,
                    "control_qty": qty,
                }
            )
            break
    return rows


def compute_arm_edges(
    arm_rows: list[dict],
    quotes_by_sym: dict[tuple[int, str], list[Quote]],
    ts_field: str,
    qty_field: str,
) -> list[dict]:
    """For each arm-trigger timestamp, compute average forward mid-change in OTM strikes."""
    out: list[dict] = []
    for r in arm_rows:
        for sym in OTM_STRIKES + NEAR_STRIKES:
            for h in HORIZONS:
                d = signed_mid_change(
                    quotes_by_sym, r["day"], sym, r[ts_field], h
                )
                if d is None:
                    continue
                out.append(
                    {
                        "day": r["day"],
                        "trigger_ts": r[ts_field],
                        "trigger_qty": r[qty_field],
                        "symbol": sym,
                        "horizon": h,
                        "mid_change": d,
                    }
                )
    return out


def aggregate_arm(rows: list[dict], arm_label: str) -> list[dict]:
    bucket: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        key = (r["day"], r["symbol"], r["horizon"])
        bucket[key].append(r["mid_change"])
    out: list[dict] = []
    for (day, sym, h), vals in sorted(bucket.items()):
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / max(n - 1, 1)
        std = math.sqrt(var)
        out.append(
            {
                "arm": arm_label,
                "day": day,
                "symbol": sym,
                "horizon": h,
                "n": n,
                "mean_mid_change": round(mean, 4),
                "std_mid_change": round(std, 4),
                "se_mid_change": round(std / math.sqrt(n), 4) if n > 1 else float("nan"),
            }
        )
    return out


def mark67_next_seller(trades: list[Trade]) -> list[dict]:
    """For each Mark67 buy of VELVET, find the next VELVET sell event by counterparty within H."""
    velvet = [t for t in trades if t.symbol == "VELVETFRUIT_EXTRACT"]
    velvet.sort(key=lambda t: (t.day, t.timestamp))
    rows: list[dict] = []
    for i, t in enumerate(velvet):
        if t.buyer != "Mark 67":
            continue
        for h in HORIZONS:
            counts: dict[str, int] = defaultdict(int)
            qty: dict[str, int] = defaultdict(int)
            for other in velvet[i + 1 :]:
                if other.day != t.day:
                    break
                if other.timestamp - t.timestamp > h:
                    break
                counts[other.seller] += 1
                qty[other.seller] += other.quantity
            for seller in ("Mark 14", "Mark 22", "Mark 49", "Mark 55", "Mark 01"):
                rows.append(
                    {
                        "day": t.day,
                        "trigger_ts": t.timestamp,
                        "trigger_qty": t.quantity,
                        "horizon": h,
                        "next_seller": seller,
                        "n_events": counts.get(seller, 0),
                        "qty_events": qty.get(seller, 0),
                    }
                )
    return rows


def write_csv(rows: list[dict], path: str, fieldnames: list[str] | None = None) -> None:
    if not rows:
        Path(path).write_text("")
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    p.add_argument("--days", type=int, nargs="+", default=[1, 2, 3])
    args = p.parse_args()

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    print(f"Loading trades from {args.data_dir} for days {args.days}")
    trades = load_trades(args.data_dir, args.days)
    print(f"  {len(trades):,} rows")
    print("Loading quotes")
    quotes_by_sym = load_quotes(args.data_dir, args.days)
    print(f"  {len(quotes_by_sym)} (day, symbol) panels")

    baskets = detect_mark22_baskets(trades)
    print(f"Detected {len(baskets)} Mark22 OTM baskets")

    print("Computing basket spillover...")
    spillover_rows = basket_spillover(baskets, quotes_by_sym)
    write_csv(spillover_rows, os.path.join(args.out_dir, "basket_spillover_raw.csv"))
    spillover_agg = aggregate_spillover(spillover_rows)
    write_csv(spillover_agg, os.path.join(args.out_dir, "basket_spillover_summary.csv"))

    print("Computing basket-to-basket sequencing...")
    bb = basket_to_basket(baskets)
    write_csv(bb["intervals"], os.path.join(args.out_dir, "basket_intervals.csv"))
    write_csv(bb["next_within"], os.path.join(args.out_dir, "basket_next_within.csv"))
    next_within_rate: dict[tuple[int, int], list[int]] = defaultdict(list)
    for r in bb["next_within"]:
        next_within_rate[(r["day"], r["horizon"])].append(r["next_basket_within"])
    summary_rows = []
    for (day, h), vals in sorted(next_within_rate.items()):
        if not vals:
            continue
        rate = sum(vals) / len(vals)
        summary_rows.append(
            {"day": day, "horizon": h, "n_baskets": len(vals), "next_within_rate": round(rate, 4)}
        )
    write_csv(summary_rows, os.path.join(args.out_dir, "basket_next_within_summary.csv"))

    print("Computing matched-frequency control arm...")
    matched = matched_frequency_control(baskets, trades)
    write_csv(matched, os.path.join(args.out_dir, "matched_control_pairs.csv"))

    treatment_rows = [
        {"day": b["day"], "trigger_ts": b["timestamp"], "trigger_qty": b["qty_total"]}
        for b in baskets
    ]
    treatment_arm = compute_arm_edges(
        treatment_rows, quotes_by_sym, "trigger_ts", "trigger_qty"
    )
    treatment_agg = aggregate_arm(treatment_arm, "treatment_mark22")

    control_arm = compute_arm_edges(
        matched, quotes_by_sym, "control_ts", "control_qty"
    )
    control_agg = aggregate_arm(control_arm, "control_nonmark22")

    paired_rows = treatment_agg + control_agg
    write_csv(paired_rows, os.path.join(args.out_dir, "paired_arm_summary.csv"))

    paired_diff_rows: list[dict] = []
    treatment_lookup = {(r["day"], r["symbol"], r["horizon"]): r for r in treatment_agg}
    for cr in control_agg:
        key = (cr["day"], cr["symbol"], cr["horizon"])
        tr = treatment_lookup.get(key)
        if tr is None:
            continue
        paired_diff_rows.append(
            {
                "day": cr["day"],
                "symbol": cr["symbol"],
                "horizon": cr["horizon"],
                "treatment_n": tr["n"],
                "treatment_mean": tr["mean_mid_change"],
                "control_n": cr["n"],
                "control_mean": cr["mean_mid_change"],
                "diff": round(tr["mean_mid_change"] - cr["mean_mid_change"], 4),
            }
        )
    write_csv(paired_diff_rows, os.path.join(args.out_dir, "paired_arm_diff.csv"))

    print("Computing Mark67 -> next-seller sequencing...")
    m67_rows = mark67_next_seller(trades)
    write_csv(m67_rows, os.path.join(args.out_dir, "mark67_next_seller_raw.csv"))

    m67_agg: dict[tuple, list[float]] = defaultdict(list)
    for r in m67_rows:
        key = (r["day"], r["horizon"], r["next_seller"])
        m67_agg[key].append(r["n_events"])
    m67_summary: list[dict] = []
    for (day, h, seller), vals in sorted(m67_agg.items()):
        n = len(vals)
        rate_pos = sum(1 for v in vals if v > 0) / n if n else 0
        avg_count = sum(vals) / n if n else 0
        m67_summary.append(
            {
                "day": day,
                "horizon": h,
                "next_seller": seller,
                "n_triggers": n,
                "rate_any": round(rate_pos, 4),
                "avg_count": round(avg_count, 3),
            }
        )
    write_csv(m67_summary, os.path.join(args.out_dir, "mark67_next_seller_summary.csv"))

    print("\nDone. Key outputs:")
    for fname in (
        "basket_spillover_summary.csv",
        "basket_next_within_summary.csv",
        "paired_arm_diff.csv",
        "mark67_next_seller_summary.csv",
    ):
        print(f"  {os.path.join(args.out_dir, fname)}")


if __name__ == "__main__":
    main()
