"""Deep-dive Mark audit covering dimensions not yet measured by prior scripts.

Prior scripts already cover: behavior classification, policy hazard, conditioned
schedule, sequence lattice, microprice/Mark67 overlap, basket spillover, paired
Mark22 vs control. This script adds:

A. Per-(mark, product, side) FIXED PRICE LEVEL distribution.
   "Magic numbers" — does Mark X always sell at the same price? Indicates a
   pegged maker/program rather than a price-discovering trader.

B. Cumulative Mark inventory trajectory over each day.
   Does Mark X end the day flat or net-directional? Identifies inventory-
   neutral vs structural-direction actors.

C. Maker-side depth attribution.
   When Mark X is on a maker side, what fraction of the level-1 volume on that
   side is theirs? If they own the level, jumping ahead by 1 tick is the only
   way to insert ourselves.

D. Pre-trade book state per Mark (spread distribution, time of day).
   Does Mark X fire only at tight spread? In a particular time-of-day window?

E. POST-trade BID/ASK behavior (not just mid):
   For each Mark trade, what's the bid/ask change at 100, 500, 1000, 5000 ticks?
   This is what matters for actually trading — if the bid moves, we can recycle
   inventory.

F. Maker-edge cross-day survival map.
   For each (mark, product, side, role), is the post-trade edge cross-day stable?
"""

from __future__ import annotations

import argparse
import csv
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_DIR = "/Users/abhinavgupta/Desktop/IMC-r4-counterparty/data/raw/round_4"
DEFAULT_OUT_DIR = "/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_deep_dive"
DAYS = (1, 2, 3)
HORIZONS = (100, 500, 1_000, 5_000, 30_000)


@dataclass(frozen=True)
class Trade:
    day: int
    timestamp: int
    buyer: str
    seller: str
    symbol: str
    price: int
    quantity: int


@dataclass
class BookSnap:
    bid: int
    bid_vol: int
    ask: int
    ask_vol: int
    mid: float


def load_trades(data_dir: str) -> list[Trade]:
    rows: list[Trade] = []
    for day in DAYS:
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
                        price=int(float(row["price"])),
                        quantity=int(float(row["quantity"])),
                    )
                )
    return rows


def load_books(data_dir: str) -> dict[tuple[int, str], list[tuple[int, BookSnap]]]:
    by_key: dict[tuple[int, str], list[tuple[int, BookSnap]]] = defaultdict(list)
    for day in DAYS:
        path = os.path.join(data_dir, f"prices_round_4_day_{day}.csv")
        with open(path, newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                bid = row.get("bid_price_1") or ""
                ask = row.get("ask_price_1") or ""
                bid_v = row.get("bid_volume_1") or ""
                ask_v = row.get("ask_volume_1") or ""
                mid = row.get("mid_price") or ""
                if not (bid and ask and mid and bid_v and ask_v):
                    continue
                try:
                    snap = BookSnap(
                        bid=int(float(bid)),
                        bid_vol=int(float(bid_v)),
                        ask=int(float(ask)),
                        ask_vol=int(float(ask_v)),
                        mid=float(mid),
                    )
                except ValueError:
                    continue
                by_key[(day, row["product"])].append((int(row["timestamp"]), snap))
    for v in by_key.values():
        v.sort(key=lambda t: t[0])
    return by_key


def book_at_or_before(snaps: list[tuple[int, BookSnap]], ts: int) -> BookSnap | None:
    last: BookSnap | None = None
    for t, s in snaps:
        if t > ts:
            break
        last = s
    return last


def book_at_or_after(snaps: list[tuple[int, BookSnap]], ts: int) -> BookSnap | None:
    for t, s in snaps:
        if t >= ts:
            return s
    return None


def write_csv(rows: list[dict], path: str) -> None:
    if not rows:
        Path(path).write_text("")
        return
    fieldnames = list(rows[0].keys())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# A. Magic-number price distribution
# ---------------------------------------------------------------------------

def magic_prices(trades: list[Trade]) -> list[dict]:
    by_actor: dict[tuple[str, str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    by_actor_total: dict[tuple[str, str, str], int] = defaultdict(int)
    by_actor_days: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for t in trades:
        for actor, side in ((t.buyer, "buy"), (t.seller, "sell")):
            key = (actor, t.symbol, side)
            by_actor[key][t.price] += t.quantity
            by_actor_total[key] += t.quantity
            by_actor_days[key].add(t.day)
    rows: list[dict] = []
    for key, prices in by_actor.items():
        total = by_actor_total[key]
        if total < 10:
            continue
        actor, sym, side = key
        days = sorted(by_actor_days[key])
        sorted_prices = sorted(prices.items(), key=lambda x: -x[1])
        top1 = sorted_prices[0]
        top1_share = top1[1] / total
        top3_share = sum(q for _, q in sorted_prices[:3]) / total
        rows.append(
            {
                "mark": actor,
                "symbol": sym,
                "side": side,
                "days_seen": len(days),
                "total_qty": total,
                "n_distinct_prices": len(prices),
                "top1_price": top1[0],
                "top1_qty": top1[1],
                "top1_share": round(top1_share, 4),
                "top3_share": round(top3_share, 4),
                "top3_prices": ";".join(str(p) for p, _ in sorted_prices[:3]),
            }
        )
    rows.sort(key=lambda r: -r["top1_share"])
    return rows


# ---------------------------------------------------------------------------
# B. Cumulative inventory trajectory per Mark
# ---------------------------------------------------------------------------

def inventory_trajectory(trades: list[Trade]) -> list[dict]:
    by_actor_day: dict[tuple[str, int, str], list[tuple[int, int]]] = defaultdict(list)
    for t in trades:
        for actor, signed in ((t.buyer, +t.quantity), (t.seller, -t.quantity)):
            by_actor_day[(actor, t.day, t.symbol)].append((t.timestamp, signed))
    rows: list[dict] = []
    for (actor, day, sym), events in by_actor_day.items():
        events.sort()
        cum = 0
        max_long = 0
        max_short = 0
        end_pos = 0
        last_ts = 0
        for ts, q in events:
            cum += q
            max_long = max(max_long, cum)
            max_short = min(max_short, cum)
            end_pos = cum
            last_ts = ts
        rows.append(
            {
                "mark": actor,
                "day": day,
                "symbol": sym,
                "n_events": len(events),
                "first_ts": events[0][0],
                "last_ts": last_ts,
                "max_long": max_long,
                "max_short": max_short,
                "end_pos": end_pos,
                "is_flat_at_end": end_pos == 0,
            }
        )
    rows.sort(key=lambda r: (r["mark"], r["day"], r["symbol"]))
    return rows


# ---------------------------------------------------------------------------
# C. Maker-side depth attribution
# ---------------------------------------------------------------------------

def maker_depth_attribution(
    trades: list[Trade], books: dict[tuple[int, str], list[tuple[int, BookSnap]]]
) -> list[dict]:
    """For each maker trade, compute trade_qty / book_volume_on_that_side at t-1."""
    by_actor: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for t in trades:
        snaps = books.get((t.day, t.symbol))
        if snaps is None:
            continue
        snap = book_at_or_before(snaps, t.timestamp - 1)
        if snap is None:
            continue
        if t.price == snap.bid:
            actor = t.seller
            book_side_vol = snap.bid_vol
            side = "sell_at_bid"
        elif t.price == snap.ask:
            actor = t.buyer
            book_side_vol = snap.ask_vol
            side = "buy_at_ask"
        else:
            continue
        if book_side_vol <= 0:
            continue
        share = t.quantity / book_side_vol
        by_actor[(actor, t.symbol, side)].append(share)
    rows: list[dict] = []
    for (actor, sym, side), shares in by_actor.items():
        if len(shares) < 5:
            continue
        rows.append(
            {
                "mark": actor,
                "symbol": sym,
                "side": side,
                "n": len(shares),
                "avg_share_of_book": round(sum(shares) / len(shares), 4),
                "max_share": round(max(shares), 4),
                "near_full_share_pct": round(
                    sum(1 for s in shares if s >= 0.9) / len(shares), 4
                ),
            }
        )
    rows.sort(key=lambda r: -r["avg_share_of_book"])
    return rows


# ---------------------------------------------------------------------------
# D. Pre-trade book state per Mark
# ---------------------------------------------------------------------------

def pretrade_book_state(
    trades: list[Trade], books: dict[tuple[int, str], list[tuple[int, BookSnap]]]
) -> list[dict]:
    by_actor: dict[tuple[str, str, str, str], list[tuple[int, int, int]]] = defaultdict(list)
    for t in trades:
        snaps = books.get((t.day, t.symbol))
        if snaps is None:
            continue
        snap = book_at_or_before(snaps, t.timestamp - 1)
        if snap is None:
            continue
        spread = snap.ask - snap.bid
        if t.price == snap.bid:
            role = "taker_sell"
            actor = t.seller
        elif t.price == snap.ask:
            role = "taker_buy"
            actor = t.buyer
        elif t.price > snap.bid and t.price < snap.ask:
            # in-spread — typically maker matched at midpoint of two limits
            role = "in_spread"
            actor = t.seller if t.price <= snap.mid else t.buyer
        else:
            role = "other"
            actor = t.seller if t.price < snap.bid else t.buyer
        by_actor[(actor, t.symbol, role, "spread")].append(
            (t.timestamp, spread, snap.bid_vol + snap.ask_vol)
        )
    rows: list[dict] = []
    for key, vals in by_actor.items():
        actor, sym, role, _ = key
        if len(vals) < 5:
            continue
        spreads = [v[1] for v in vals]
        depths = [v[2] for v in vals]
        timestamps = [v[0] for v in vals]
        bins = [0] * 10
        for ts in timestamps:
            day_ts = ts % 1_000_000
            b = min(9, int(day_ts // 100_000))
            bins[b] += 1
        rows.append(
            {
                "mark": actor,
                "symbol": sym,
                "role": role,
                "n": len(vals),
                "avg_spread": round(sum(spreads) / len(spreads), 3),
                "min_spread": min(spreads),
                "max_spread": max(spreads),
                "avg_depth": round(sum(depths) / len(depths), 2),
                "tod_bin0_share": round(bins[0] / len(vals), 4),
                "tod_bin5_share": round(bins[5] / len(vals), 4),
                "tod_bin9_share": round(bins[9] / len(vals), 4),
            }
        )
    rows.sort(key=lambda r: (r["mark"], r["symbol"], r["role"]))
    return rows


# ---------------------------------------------------------------------------
# E. Post-trade BID/ASK behavior per Mark
# ---------------------------------------------------------------------------

def posttrade_bidask(
    trades: list[Trade], books: dict[tuple[int, str], list[tuple[int, BookSnap]]]
) -> list[dict]:
    """For each (mark, product, side, role), average the post-trade bid/ask move."""
    bucket: dict[tuple, list[dict[str, float]]] = defaultdict(list)
    for t in trades:
        snaps = books.get((t.day, t.symbol))
        if snaps is None:
            continue
        snap = book_at_or_before(snaps, t.timestamp - 1)
        if snap is None:
            continue
        if t.price == snap.bid:
            actor = t.seller
            role = "taker_sell"
        elif t.price == snap.ask:
            actor = t.buyer
            role = "taker_buy"
        else:
            continue
        for h in HORIZONS:
            future = book_at_or_after(snaps, t.timestamp + h)
            if future is None:
                continue
            bucket[(actor, t.symbol, role, h, t.day)].append(
                {
                    "dbid": future.bid - snap.bid,
                    "dask": future.ask - snap.ask,
                    "dmid": future.mid - snap.mid,
                }
            )
    out: list[dict] = []
    daily: dict[tuple, dict[int, dict[str, float]]] = defaultdict(dict)
    for (actor, sym, role, h, day), rows in bucket.items():
        if not rows:
            continue
        n = len(rows)
        avg_bid = sum(r["dbid"] for r in rows) / n
        avg_ask = sum(r["dask"] for r in rows) / n
        avg_mid = sum(r["dmid"] for r in rows) / n
        daily[(actor, sym, role, h)][day] = {
            "n": n,
            "dbid": avg_bid,
            "dask": avg_ask,
            "dmid": avg_mid,
        }
    for (actor, sym, role, h), per_day in daily.items():
        if not per_day:
            continue
        n_total = sum(d["n"] for d in per_day.values())
        if n_total < 10:
            continue
        avg_dbid = sum(d["dbid"] * d["n"] for d in per_day.values()) / n_total
        avg_dask = sum(d["dask"] * d["n"] for d in per_day.values()) / n_total
        avg_dmid = sum(d["dmid"] * d["n"] for d in per_day.values()) / n_total
        all_days = (1, 2, 3)
        signs = []
        for day in all_days:
            d = per_day.get(day)
            if d is None:
                continue
            signs.append((d["dbid"] > 0) - (d["dbid"] < 0))
        same_sign = (len(signs) == len(per_day)) and (
            all(s >= 0 for s in signs) or all(s <= 0 for s in signs)
        )
        out.append(
            {
                "mark": actor,
                "symbol": sym,
                "role": role,
                "horizon": h,
                "n": n_total,
                "days_seen": len(per_day),
                "avg_dbid": round(avg_dbid, 3),
                "avg_dask": round(avg_dask, 3),
                "avg_dmid": round(avg_dmid, 3),
                "cross_day_dbid_same_sign": int(same_sign),
            }
        )
    out.sort(key=lambda r: -abs(r["avg_dbid"]))
    return out


# ---------------------------------------------------------------------------
# F. Cumulative Mark inventory: aggregate to daily / cross-product nets
# ---------------------------------------------------------------------------

def daily_inventory_summary(traj: list[dict]) -> list[dict]:
    by_mark_day: dict[tuple[str, int], dict[str, int]] = defaultdict(
        lambda: {"n_events": 0, "n_products": 0, "abs_qty_total": 0, "n_flat": 0, "max_abs_pos": 0}
    )
    for r in traj:
        d = by_mark_day[(r["mark"], r["day"])]
        d["n_events"] += r["n_events"]
        d["n_products"] += 1
        d["abs_qty_total"] += abs(r["max_long"]) + abs(r["max_short"])
        d["max_abs_pos"] = max(d["max_abs_pos"], abs(r["max_long"]), abs(r["max_short"]))
        if r["is_flat_at_end"]:
            d["n_flat"] += 1
    out: list[dict] = []
    for (mark, day), d in sorted(by_mark_day.items()):
        out.append(
            {
                "mark": mark,
                "day": day,
                **d,
                "flat_share": round(d["n_flat"] / max(d["n_products"], 1), 3),
            }
        )
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    args = p.parse_args()
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    print("Loading trades...")
    trades = load_trades(args.data_dir)
    print(f"  {len(trades):,} trades")
    print("Loading books...")
    books = load_books(args.data_dir)
    print(f"  {len(books):,} (day, product) panels")

    print("A. Magic-number price distribution...")
    rows_a = magic_prices(trades)
    write_csv(rows_a, os.path.join(args.out_dir, "magic_prices.csv"))
    print(f"  {len(rows_a)} (mark, product, side) rows")

    print("B. Cumulative inventory trajectory per Mark / day / product...")
    traj = inventory_trajectory(trades)
    write_csv(traj, os.path.join(args.out_dir, "inventory_trajectory.csv"))
    summary_b = daily_inventory_summary(traj)
    write_csv(summary_b, os.path.join(args.out_dir, "daily_inventory_summary.csv"))
    print(f"  {len(traj)} trajectory rows, {len(summary_b)} daily summary rows")

    print("C. Maker-side depth attribution...")
    rows_c = maker_depth_attribution(trades, books)
    write_csv(rows_c, os.path.join(args.out_dir, "maker_depth_attribution.csv"))
    print(f"  {len(rows_c)} depth-attribution rows")

    print("D. Pre-trade book state per Mark...")
    rows_d = pretrade_book_state(trades, books)
    write_csv(rows_d, os.path.join(args.out_dir, "pretrade_book_state.csv"))
    print(f"  {len(rows_d)} pre-trade-state rows")

    print("E. Post-trade bid/ask behavior...")
    rows_e = posttrade_bidask(trades, books)
    write_csv(rows_e, os.path.join(args.out_dir, "posttrade_bidask.csv"))
    print(f"  {len(rows_e)} post-trade-bidask rows")

    print()
    print("Outputs in:", args.out_dir)


if __name__ == "__main__":
    main()
