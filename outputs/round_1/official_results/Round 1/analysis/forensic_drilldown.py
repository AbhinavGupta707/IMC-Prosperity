"""Forensic drill-down on Round 1 official results.

Purpose (diagnostic only, no config changes):
- bucketed PnL attribution (4 x 25k buckets) per variant / product
- bucketed trade / execution stats
- bucketed fair-vs-market diagnostics (per the candidate's own fair-value method)

Primary evidence: .json (activitiesLog) for market state & running PnL
Support: .log for trade history (SUBMISSION trades only)
"""

from __future__ import annotations

import csv
import io
import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

ROOT = Path(__file__).resolve().parent.parent
VARIANTS = {
    "Baseline": {
        "json": ROOT / "Baseline" / "115117.json",
        "log": ROOT / "Baseline" / "115117.log",
        "configs": {
            "ASH_COATED_OSMIUM": {
                "fv": "wall_mid",
                "taker_edge": 1.0,
                "maker_edge": 1.0,
                "history": 48,
            },
            "INTARIAN_PEPPER_ROOT": {
                "fv": "linear_drift",
                "taker_edge": 1.0,
                "maker_edge": 1.5,
                "history": 48,
            },
        },
    },
    "Promoted": {
        "json": ROOT / "Promoted" / "115254.json",
        "log": ROOT / "Promoted" / "115254.log",
        "configs": {
            "ASH_COATED_OSMIUM": {
                "fv": "ewma_mid",
                "taker_edge": 0.25,
                "maker_edge": 1.0,
                "history": 48,
                "ewma_alpha": 0.3,
            },
            "INTARIAN_PEPPER_ROOT": {
                "fv": "linear_drift",
                "taker_edge": 2.0,
                "maker_edge": 1.0,
                "history": 32,
            },
        },
    },
    "Alt": {
        "json": ROOT / "Alt" / "115380.json",
        "log": ROOT / "Alt" / "115380.log",
        "configs": {
            "ASH_COATED_OSMIUM": {
                "fv": "wall_mid",
                "taker_edge": 0.5,
                "maker_edge": 1.5,
                "history": 48,
            },
            "INTARIAN_PEPPER_ROOT": {
                "fv": "linear_drift",
                "taker_edge": 2.0,
                "maker_edge": 1.0,
                "history": 32,
            },
        },
    },
}

BUCKETS = [(0, 25_000), (25_000, 50_000), (50_000, 75_000), (75_000, 100_000)]
PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]


# --- Parsers ---------------------------------------------------------------


def _parse_activities(raw: str) -> list[dict]:
    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(raw), delimiter=";")
    for r in reader:
        rows.append(r)
    return rows


def _to_float(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


@dataclass
class Snapshot:
    ts: int
    product: str
    bids: list[tuple[int, int]]  # (price, volume), sorted high->low
    asks: list[tuple[int, int]]  # (price, volume), sorted low->high
    mid: float | None
    pnl_cum: float

    @property
    def best_bid(self) -> int | None:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> int | None:
        return self.asks[0][0] if self.asks else None

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid


def snapshots_from_json(path: Path) -> list[Snapshot]:
    blob = json.loads(path.read_text())
    rows = _parse_activities(blob["activitiesLog"])
    out: list[Snapshot] = []
    for r in rows:
        bids: list[tuple[int, int]] = []
        asks: list[tuple[int, int]] = []
        for lvl in (1, 2, 3):
            bp = _to_float(r.get(f"bid_price_{lvl}"))
            bv = _to_float(r.get(f"bid_volume_{lvl}"))
            if bp is not None and bv is not None:
                bids.append((int(bp), int(bv)))
            ap = _to_float(r.get(f"ask_price_{lvl}"))
            av = _to_float(r.get(f"ask_volume_{lvl}"))
            if ap is not None and av is not None:
                asks.append((int(ap), int(av)))
        bids.sort(key=lambda x: -x[0])
        asks.sort(key=lambda x: x[0])
        # Match shipped code: mid is only valid when BOTH sides present.
        if bids and asks:
            mid: float | None = (bids[0][0] + asks[0][0]) / 2.0
        else:
            mid = None
        pnl = _to_float(r.get("profit_and_loss")) or 0.0
        out.append(
            Snapshot(
                ts=int(r["timestamp"]),
                product=r["product"],
                bids=bids,
                asks=asks,
                mid=mid,
                pnl_cum=pnl,
            )
        )
    return out


def trades_from_log(path: Path) -> list[dict]:
    blob = json.loads(path.read_text())
    return blob.get("tradeHistory", [])


# --- Fair value estimators (mirroring the shipped code) --------------------


def fv_wall_mid(snap: Snapshot, history: list[float], cfg: dict) -> float | None:
    if not snap.bids or not snap.asks:
        return None
    wb = max(snap.bids, key=lambda lv: lv[1])
    wa = max(snap.asks, key=lambda lv: lv[1])
    return (wb[0] + wa[0]) / 2.0


def fv_depth_mid(snap: Snapshot, history: list[float], cfg: dict) -> float | None:
    if not snap.bids or not snap.asks:
        return None
    bvol = sum(v for _, v in snap.bids)
    avol = sum(v for _, v in snap.asks)
    if bvol <= 0 or avol <= 0:
        return None
    bvw = sum(p * v for p, v in snap.bids) / bvol
    avw = sum(p * v for p, v in snap.asks) / avol
    return (bvw + avw) / 2.0


def fv_microprice(snap: Snapshot, history: list[float], cfg: dict) -> float | None:
    if not snap.bids or not snap.asks:
        return None
    bp, bv = snap.bids[0]
    ap, av = snap.asks[0]
    tot = bv + av
    if tot <= 0:
        return None
    return (ap * bv + bp * av) / tot


def fv_mid(snap: Snapshot, history: list[float], cfg: dict) -> float | None:
    return snap.mid


def fv_ewma_mid(snap: Snapshot, history: list[float], cfg: dict) -> float | None:
    alpha = cfg.get("ewma_alpha", 0.3)
    if not history and snap.mid is None:
        return None
    if not history:
        return snap.mid
    ewma = history[0]
    for prior in history[1:]:
        ewma = alpha * prior + (1.0 - alpha) * ewma
    if snap.mid is not None:
        ewma = alpha * snap.mid + (1.0 - alpha) * ewma
    return ewma


def fv_linear_drift(
    snap: Snapshot, history: list[float], cfg: dict
) -> float | None:
    lookback = cfg.get("history", 48) or None
    hist = list(history)
    if lookback:
        hist = hist[-lookback:]
    if not hist and snap.mid is None:
        return None
    if not hist:
        return snap.mid
    ys = [float(y) for y in hist]
    if snap.mid is not None:
        ys.append(float(snap.mid))
    n = len(ys)
    if n < 2:
        return ys[-1]
    xs = list(range(n))
    mx = (n - 1) / 2.0
    my = sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    if vx <= 0:
        return ys[-1]
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = cov / vx
    intercept = my - slope * mx
    return slope * n + intercept


ESTIMATORS: dict[str, Callable[[Snapshot, list[float], dict], float | None]] = {
    "wall_mid": fv_wall_mid,
    "depth_mid": fv_depth_mid,
    "microprice": fv_microprice,
    "mid": fv_mid,
    "ewma_mid": fv_ewma_mid,
    "linear_drift": fv_linear_drift,
}


# --- Bucketing helpers -----------------------------------------------------


def which_bucket(ts: int) -> int:
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo <= ts < hi:
            return i
    return len(BUCKETS) - 1  # clamp any ts == 100_000+ into last bucket


@dataclass
class BucketStats:
    pnl_start: float = 0.0
    pnl_end: float = 0.0
    trade_count: int = 0
    maker_count: int = 0
    taker_count: int = 0
    other_count: int = 0
    trade_size_total: int = 0
    final_position: int = 0
    near_limit_ts_count: int = 0
    # fair-vs-market diagnostics
    fv_minus_ask: list[float] = field(default_factory=list)
    bid_minus_fv: list[float] = field(default_factory=list)
    residual: list[float] = field(default_factory=list)  # fv - mid
    buy_triggers: int = 0
    sell_triggers: int = 0
    # snapshot counts
    snap_count: int = 0
    # position-time near limits
    position_time_steps: int = 0  # number of snapshots
    position_near_limit_steps: int = 0

    @property
    def pnl_delta(self) -> float:
        return self.pnl_end - self.pnl_start

    @property
    def avg_trade_size(self) -> float:
        return self.trade_size_total / self.trade_count if self.trade_count else 0.0

    @property
    def avg_fv_minus_ask(self) -> float:
        return statistics.fmean(self.fv_minus_ask) if self.fv_minus_ask else 0.0

    @property
    def avg_bid_minus_fv(self) -> float:
        return (
            statistics.fmean(self.bid_minus_fv) if self.bid_minus_fv else 0.0
        )

    @property
    def residual_mean(self) -> float:
        return statistics.fmean(self.residual) if self.residual else 0.0

    @property
    def residual_std(self) -> float:
        return (
            statistics.pstdev(self.residual) if len(self.residual) > 1 else 0.0
        )


# --- Main analysis ---------------------------------------------------------


POSITION_LIMIT = 50
NEAR_LIMIT_RATIO = 0.8  # |pos| >= 40 counts as near limit


def classify_trade(
    snaps_by_key: dict[tuple[int, str], Snapshot],
    trade: dict,
) -> Literal["maker", "taker", "other"]:
    ts = trade["timestamp"]
    product = trade["symbol"]
    price = float(trade["price"])
    snap = snaps_by_key.get((ts, product))
    if snap is None:
        return "other"
    bb = snap.best_bid
    ba = snap.best_ask
    if bb is None or ba is None:
        return "other"
    # Heuristic:
    #   - our aggressive (taker) fills cross the spread and print at/through
    #     the opposite side's top (buy >= best_ask, sell <= best_bid).
    #   - our passive (maker) fills get hit at prices inside or at our own
    #     side of the book (buy < best_ask, sell > best_bid).
    if trade["buyer"] == "SUBMISSION":
        return "taker" if price >= ba else "maker"
    else:
        return "taker" if price <= bb else "maker"


def analyze_variant(name: str, info: dict) -> dict:
    snaps = snapshots_from_json(info["json"])
    trades = trades_from_log(info["log"])

    # Split snapshots by product and sort by timestamp
    by_product: dict[str, list[Snapshot]] = {p: [] for p in PRODUCTS}
    for s in snaps:
        if s.product in by_product:
            by_product[s.product].append(s)
    for p in by_product:
        by_product[p].sort(key=lambda s: s.ts)

    snaps_by_key: dict[tuple[int, str], Snapshot] = {
        (s.ts, s.product): s for s in snaps
    }

    # Per-product fair-value recompute using history of mids
    # Use ONLY the fair-value method configured for that product/variant.
    per_product_stats: dict[str, list[BucketStats]] = {
        p: [BucketStats() for _ in BUCKETS] for p in PRODUCTS
    }

    for product in PRODUCTS:
        cfg = info["configs"][product]
        fv_fn = ESTIMATORS[cfg["fv"]]
        hist: list[float] = []  # mids seen so far (excluding current)
        last_pnl = 0.0
        bucket_starts = [0.0, None, None, None]
        bucket_ends = [None, None, None, None]
        prev_end_pnl = 0.0
        current_bucket = 0
        for s in by_product[product]:
            b = which_bucket(s.ts)
            bs = per_product_stats[product][b]
            bs.snap_count += 1

            # PnL boundaries: pnl_cum is cumulative. Record first and last in bucket.
            if bs.snap_count == 1:
                bs.pnl_start = last_pnl  # cumulative pnl at end of prior bucket
            bs.pnl_end = s.pnl_cum
            last_pnl = s.pnl_cum

            # Fair value (using history of prior mids)
            fv = fv_fn(s, hist, cfg)
            if fv is not None:
                if s.best_ask is not None:
                    bs.fv_minus_ask.append(fv - s.best_ask)
                    if (fv - s.best_ask) >= cfg["taker_edge"]:
                        bs.buy_triggers += 1
                if s.best_bid is not None:
                    bs.bid_minus_fv.append(s.best_bid - fv)
                    if (s.best_bid - fv) >= cfg["taker_edge"]:
                        bs.sell_triggers += 1
                if s.mid is not None:
                    bs.residual.append(fv - s.mid)

            # Update history with this timestamp's mid
            if s.mid is not None:
                hist.append(float(s.mid))

        # pnl_start for each bucket = pnl_end of previous bucket
        stats = per_product_stats[product]
        # Recompute pnl_start correctly
        prev_end = 0.0
        for b in range(len(BUCKETS)):
            bs = stats[b]
            bs.pnl_start = prev_end
            if bs.snap_count > 0:
                prev_end = bs.pnl_end
            else:
                bs.pnl_end = prev_end

    # Trade-level stats + position tracking
    # Sort trades by timestamp, track running position per product
    trades_sorted = sorted(trades, key=lambda t: t["timestamp"])
    running_pos: dict[str, int] = {p: 0 for p in PRODUCTS}
    # We will also compute "final position per bucket" by running through
    # trades in order and noting position at the last trade within the bucket;
    # if no trades in bucket, position inherits from previous bucket.
    final_pos_per_bucket: dict[str, list[int]] = {
        p: [0, 0, 0, 0] for p in PRODUCTS
    }
    last_pos_seen = {p: 0 for p in PRODUCTS}

    # Also track position-time near limits: for each product, scan
    # across the 1000 snapshots and know the running position at that ts.
    # We'll compute via event-driven sim, applying trades between ts.

    trades_by_product: dict[str, list[dict]] = {p: [] for p in PRODUCTS}
    for t in trades_sorted:
        if t["symbol"] in trades_by_product:
            trades_by_product[t["symbol"]].append(t)

    for product in PRODUCTS:
        cfg = info["configs"][product]
        # Snapshots in order
        prod_snaps = by_product[product]
        ptrades = trades_by_product[product]
        ti = 0
        pos = 0
        bucket_last_pos = [0, 0, 0, 0]
        bucket_has_trade = [False, False, False, False]
        for s in prod_snaps:
            # Apply trades whose timestamp <= s.ts and not yet applied
            while ti < len(ptrades) and ptrades[ti]["timestamp"] <= s.ts:
                t = ptrades[ti]
                qty = int(t["quantity"])
                if t["buyer"] == "SUBMISSION":
                    pos += qty
                else:
                    pos -= qty
                b_t = which_bucket(int(t["timestamp"]))
                bucket_last_pos[b_t] = pos
                bucket_has_trade[b_t] = True
                bs = per_product_stats[product][b_t]
                bs.trade_count += 1
                bs.trade_size_total += qty
                cls = classify_trade(snaps_by_key, t)
                if cls == "maker":
                    bs.maker_count += 1
                elif cls == "taker":
                    bs.taker_count += 1
                else:
                    bs.other_count += 1
                ti += 1
            # Count near-limit time (at current snapshot ts)
            b = which_bucket(s.ts)
            bs = per_product_stats[product][b]
            bs.position_time_steps += 1
            if abs(pos) >= POSITION_LIMIT * NEAR_LIMIT_RATIO:
                bs.position_near_limit_steps += 1
        # Final position per bucket (if no trades, carry prev)
        carry = 0
        for b in range(len(BUCKETS)):
            if bucket_has_trade[b]:
                carry = bucket_last_pos[b]
            per_product_stats[product][b].final_position = carry

    return {
        "per_product_stats": per_product_stats,
        "total_pnl": json.loads(info["json"].read_text()).get("profit"),
        "final_positions": {
            p: [per_product_stats[p][b].final_position for b in range(4)]
            for p in PRODUCTS
        },
    }


def main() -> None:
    results = {}
    for name, info in VARIANTS.items():
        results[name] = analyze_variant(name, info)

    # Emit a compact CSV table with per-variant/per-bucket/per-product rows
    out_csv = ROOT / "analysis" / "bucket_breakdown.csv"
    out_md = ROOT / "analysis" / "bucket_breakdown.md"
    out_memo = ROOT / "analysis" / "bucket_memo.md"

    headers = [
        "variant",
        "bucket",
        "product",
        "pnl_delta",
        "pnl_cum_end",
        "trade_count",
        "maker",
        "taker",
        "other",
        "avg_size",
        "final_pos",
        "snap_near_limit",
        "snap_count",
        "avg_fv_minus_ask",
        "avg_bid_minus_fv",
        "buy_triggers",
        "sell_triggers",
        "residual_mean",
        "residual_std",
    ]

    rows = []
    for variant in ["Baseline", "Promoted", "Alt"]:
        for b, (lo, hi) in enumerate(BUCKETS):
            bucket_label = f"{lo//1000}k-{hi//1000}k"
            for product in PRODUCTS:
                bs = results[variant]["per_product_stats"][product][b]
                rows.append(
                    [
                        variant,
                        bucket_label,
                        product,
                        round(bs.pnl_delta, 2),
                        round(bs.pnl_end, 2),
                        bs.trade_count,
                        bs.maker_count,
                        bs.taker_count,
                        bs.other_count,
                        round(bs.avg_trade_size, 2),
                        bs.final_position,
                        bs.position_near_limit_steps,
                        bs.position_time_steps,
                        round(bs.avg_fv_minus_ask, 3),
                        round(bs.avg_bid_minus_fv, 3),
                        bs.buy_triggers,
                        bs.sell_triggers,
                        round(bs.residual_mean, 3),
                        round(bs.residual_std, 3),
                    ]
                )

    with out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)

    # Markdown table
    md_lines = ["# Bucketed breakdown (all variants)\n"]
    md_lines.append("| " + " | ".join(headers) + " |")
    md_lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        md_lines.append("| " + " | ".join(str(x) for x in r) + " |")
    md_lines.append("")

    # Total-PnL-by-bucket rollup (ASH+PEPPER summed)
    md_lines.append("## Per-bucket total PnL (ASH + PEPPER)\n")
    md_lines.append("| variant | bucket | total_pnl_delta | ASH_only | PEPPER_only |")
    md_lines.append("|---|---|---|---|---|")
    for variant in ["Baseline", "Promoted", "Alt"]:
        for b, (lo, hi) in enumerate(BUCKETS):
            label = f"{lo//1000}k-{hi//1000}k"
            stats = results[variant]["per_product_stats"]
            ash_pnl = stats["ASH_COATED_OSMIUM"][b].pnl_delta
            pep_pnl = stats["INTARIAN_PEPPER_ROOT"][b].pnl_delta
            tot = ash_pnl + pep_pnl
            md_lines.append(
                f"| {variant} | {label} | {tot:+.2f} | {ash_pnl:+.2f} | {pep_pnl:+.2f} |"
            )
        md_lines.append("|   |   |   |   |   |")

    out_md.write_text("\n".join(md_lines))

    print("Wrote:", out_csv)
    print("Wrote:", out_md)

    # Expose results for the memo generator
    return results


if __name__ == "__main__":
    main()
