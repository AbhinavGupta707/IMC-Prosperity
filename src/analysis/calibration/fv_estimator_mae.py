"""Score per-tick FV estimators against ground-truth recovered server FV.

Use case: round-2 day 2, after calibration, before running the full MC
cohort. Compute MAE (and bias) for every standard FV estimator on the
recovered server FV. The estimator with the lowest MAE is the best
foundation for any market-making strategy on that product.

Estimators evaluated (each is a per-tick scalar derived from the
visible book):

    mid          (best_bid + best_ask) / 2
    wall_mid     midpoint of the OUTERMOST visible bid/ask
    micro_price  size-weighted mid: (best_ask*bid_size + best_bid*ask_size) / (bid_size + ask_size)
    weighted_mid simple mean of recent N mids (rolling window)
    depth_mid    volume-weighted average of all visible levels
    anchor_10000 constant 10000 (PEPPER-like products)

The output ranks estimators by MAE. Whichever estimator has the lowest
MAE is the strategy's recommended FV foundation.

Time complexity: O(n_ticks * n_estimators). For 10k ticks and 6
estimators, runs in ~50ms.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from src.analysis.calibration.types import FactRow

WEIGHTED_MID_DEFAULT_WINDOW = 5


@dataclass(frozen=True)
class EstimatorScore:
    """One estimator's accuracy vs recovered server FV."""

    name: str
    mae: float            # mean absolute error
    bias: float           # mean error (signed; + means estimator above FV)
    rmse: float           # root mean squared error
    n_evaluated: int      # ticks where estimator was computable
    description: str


def score_estimators(
    facts: Sequence[FactRow],
    *,
    weighted_mid_window: int = WEIGHTED_MID_DEFAULT_WINDOW,
    anchor_value: float | None = None,
) -> tuple[EstimatorScore, ...]:
    """Compute MAE / bias / RMSE for every estimator vs server_fv.

    ``anchor_value`` enables the constant-FV estimator (useful for
    PEPPER-like products); if None, the anchor estimator is skipped.

    Returns scores sorted by MAE ascending (best estimator first).
    """
    scores: list[EstimatorScore] = []
    for name, fn, desc in _ESTIMATORS:
        scores.append(_score_one(facts, name, fn, desc))
    scores.append(_score_one(
        facts,
        f"weighted_mid_{weighted_mid_window}",
        _make_weighted_mid(weighted_mid_window),
        f"rolling-mean of last {weighted_mid_window} mids",
    ))
    if anchor_value is not None:
        scores.append(_score_one(
            facts,
            f"anchor_{int(anchor_value)}",
            lambda f, _val=anchor_value: _val,
            f"constant {anchor_value}",
        ))
    scores.sort(key=lambda s: s.mae)
    return tuple(scores)


def render_score_markdown(scores: Sequence[EstimatorScore]) -> str:
    """Markdown-table render of estimator scores ranked by MAE."""
    lines = [
        "# FV estimator MAE ranking",
        "",
        "Per-tick estimator scored against recovered server fair value.",
        "Lower MAE = better foundation for market-making strategies.",
        "Bias indicates systematic offset (estimator - true FV).",
        "",
        "| rank | estimator | MAE | bias | RMSE | n | description |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for i, s in enumerate(scores, start=1):
        lines.append(
            f"| {i} | `{s.name}` | {s.mae:.4f} | {s.bias:+.4f} | "
            f"{s.rmse:.4f} | {s.n_evaluated} | {s.description} |"
        )
    if scores:
        best = scores[0]
        lines.append("")
        lines.append(
            f"**Recommendation**: use `{best.name}` as the FV foundation. "
            f"MAE {best.mae:.4f} (≈ {best.mae * 2:.2f} ticks of typical "
            f"per-tick noise). Bias {best.bias:+.4f} suggests "
            f"{'a small ' + ('positive' if best.bias > 0 else 'negative') + ' systematic offset' if abs(best.bias) > 0.05 else 'no meaningful systematic bias'}."
        )
    return "\n".join(lines)


# --------------------------------------------------------------- internals


def _mid(fact: FactRow) -> float | None:
    if not fact.bids or not fact.asks:
        return None
    return 0.5 * (fact.bids[0].price + fact.asks[0].price)


def _wall_mid(fact: FactRow) -> float | None:
    """Midpoint of the OUTERMOST visible bid/ask (Bot-1 wall)."""
    if not fact.bids or not fact.asks:
        return None
    return 0.5 * (fact.bids[-1].price + fact.asks[-1].price)


def _micro_price(fact: FactRow) -> float | None:
    if not fact.bids or not fact.asks:
        return None
    bid = fact.bids[0]
    ask = fact.asks[0]
    total_size = bid.volume + ask.volume
    if total_size <= 0:
        return None
    # Size-weighted: weighted toward the side with MORE size on the touch.
    return (ask.price * bid.volume + bid.price * ask.volume) / total_size


def _depth_mid(fact: FactRow) -> float | None:
    """Volume-weighted average across ALL visible levels both sides."""
    total_volume = 0
    weighted_sum = 0.0
    for level in fact.bids:
        weighted_sum += level.price * level.volume
        total_volume += level.volume
    for level in fact.asks:
        weighted_sum += level.price * level.volume
        total_volume += level.volume
    if total_volume == 0:
        return None
    return weighted_sum / total_volume


_ESTIMATORS = [
    ("mid", _mid, "(best_bid + best_ask) / 2"),
    ("wall_mid", _wall_mid, "midpoint of outermost visible bid/ask"),
    ("micro_price", _micro_price, "size-weighted touch mid"),
    ("depth_mid", _depth_mid, "volume-weighted avg of all visible levels"),
]


def _make_weighted_mid(window: int):
    """Return a stateful estimator: rolling mean of last `window` mids."""
    history: list[float] = []

    def estimator(fact: FactRow) -> float | None:
        m = _mid(fact)
        if m is None:
            return None
        history.append(m)
        if len(history) > window:
            history.pop(0)
        return float(np.mean(history))

    return estimator


def _score_one(
    facts: Sequence[FactRow], name: str, fn, description: str,
) -> EstimatorScore:
    errors: list[float] = []
    for fact in facts:
        try:
            est = fn(fact)
        except Exception:  # noqa: BLE001  - estimator should never raise; if it does, skip
            est = None
        if est is None:
            continue
        errors.append(est - fact.server_fv)
    if not errors:
        return EstimatorScore(
            name=name, mae=float("inf"), bias=0.0, rmse=float("inf"),
            n_evaluated=0, description=description,
        )
    arr = np.asarray(errors, dtype=float)
    return EstimatorScore(
        name=name,
        mae=float(np.mean(np.abs(arr))),
        bias=float(np.mean(arr)),
        rmse=float(np.sqrt(np.mean(arr ** 2))),
        n_evaluated=len(arr),
        description=description,
    )
