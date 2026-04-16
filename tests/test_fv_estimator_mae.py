"""Tests for fv_estimator_mae: per-tick FV estimator scoring."""
from __future__ import annotations

import pytest

from src.analysis.calibration.fv_estimator_mae import (
    EstimatorScore, render_score_markdown, score_estimators,
)
from src.analysis.calibration.types import BookLevel, FactRow


def _make_facts_with_known_book(
    n: int = 100, fv: float = 5000.0, spread: int = 4,
) -> list[FactRow]:
    """Generate facts where mid is exactly fv (best_bid+best_ask)/2."""
    half = spread // 2
    return [
        FactRow(
            timestamp=i * 100, product="P", server_fv=fv,
            bids=(BookLevel(price=int(fv) - half, volume=10),),
            asks=(BookLevel(price=int(fv) + half, volume=10),),
            mid_price=fv, pnl=0.0,
        )
        for i in range(n)
    ]


def test_score_estimators_returns_estimator_scores():
    facts = _make_facts_with_known_book(50)
    scores = score_estimators(facts)
    assert all(isinstance(s, EstimatorScore) for s in scores)
    assert len(scores) > 0
    # Names should be unique.
    names = {s.name for s in scores}
    assert len(names) == len(scores)


def test_mid_estimator_is_perfect_when_book_centered_on_fv():
    """If best_bid + best_ask = 2 * server_fv exactly, mid MAE should be 0."""
    facts = _make_facts_with_known_book(100, fv=5000.0, spread=4)
    scores = score_estimators(facts)
    mid_score = next(s for s in scores if s.name == "mid")
    assert mid_score.mae == 0.0
    assert mid_score.bias == 0.0


def test_estimators_sorted_by_mae_ascending():
    """Result tuple should be sorted: best estimator first."""
    facts = _make_facts_with_known_book(100)
    scores = score_estimators(facts)
    maes = [s.mae for s in scores]
    assert maes == sorted(maes)


def test_anchor_value_recovered_when_provided():
    facts = _make_facts_with_known_book(100, fv=10000.0)
    scores = score_estimators(facts, anchor_value=10000.0)
    anchor_scores = [s for s in scores if s.name.startswith("anchor")]
    assert len(anchor_scores) == 1
    # Anchor of 10000 against fv=10000 gives MAE 0.
    assert anchor_scores[0].mae == 0.0


def test_anchor_skipped_when_not_provided():
    facts = _make_facts_with_known_book(100)
    scores = score_estimators(facts, anchor_value=None)
    anchor_scores = [s for s in scores if s.name.startswith("anchor")]
    assert len(anchor_scores) == 0


def test_bias_signed_correctly():
    """Constant offset between estimator and FV should produce signed bias."""
    # If the book is shifted so mid = fv + 2 (not centered), mid bias = +2.
    facts = []
    for i in range(50):
        facts.append(FactRow(
            timestamp=i * 100, product="P", server_fv=5000.0,
            # Book centered on 5002 instead of 5000.
            bids=(BookLevel(price=5000, volume=10),),
            asks=(BookLevel(price=5004, volume=10),),
            mid_price=5002.0, pnl=0.0,
        ))
    scores = score_estimators(facts)
    mid_score = next(s for s in scores if s.name == "mid")
    assert mid_score.bias == pytest.approx(+2.0)
    assert mid_score.mae == pytest.approx(2.0)


def test_estimator_with_no_book_skipped():
    """Facts with empty bids/asks should not contribute to the score."""
    facts = [
        FactRow(timestamp=0, product="P", server_fv=5000.0,
                bids=(), asks=(), mid_price=None, pnl=0.0),
    ]
    scores = score_estimators(facts)
    # All estimators that depend on the book should report n_evaluated=0.
    for s in scores:
        if not s.name.startswith("anchor"):
            assert s.n_evaluated == 0


def test_render_markdown_includes_recommendation():
    facts = _make_facts_with_known_book(50)
    scores = score_estimators(facts)
    md = render_score_markdown(scores)
    assert "Recommendation" in md
    assert "MAE" in md


def test_wall_mid_uses_outermost_levels():
    """wall_mid should use the LAST level in bids/asks, not the first."""
    facts = []
    for i in range(20):
        facts.append(FactRow(
            timestamp=i * 100, product="P", server_fv=5000.0,
            # Inner level closer to mid; outer level wider.
            bids=(BookLevel(price=4998, volume=10),
                  BookLevel(price=4992, volume=20)),
            asks=(BookLevel(price=5002, volume=10),
                  BookLevel(price=5008, volume=20)),
            mid_price=5000.0, pnl=0.0,
        ))
    scores = score_estimators(facts)
    wall = next(s for s in scores if s.name == "wall_mid")
    # wall_mid uses outermost = (4992 + 5008) / 2 = 5000.
    assert wall.mae == 0.0


def test_micro_price_size_weighting():
    """When ask_size > bid_size, micro_price should pull toward the bid."""
    facts = []
    for i in range(20):
        facts.append(FactRow(
            timestamp=i * 100, product="P", server_fv=4998.0,
            bids=(BookLevel(price=4995, volume=10),),
            # Ask has 30 size — micro_price weights bid heavier.
            asks=(BookLevel(price=5001, volume=30),),
            mid_price=4998.0, pnl=0.0,
        ))
    scores = score_estimators(facts)
    micro = next(s for s in scores if s.name == "micro_price")
    # micro_price = (5001*10 + 4995*30) / (10+30) = (50010 + 149850) / 40 = 4996.5
    # Truth is 4998. Bias = -1.5. MAE = 1.5.
    assert micro.bias == pytest.approx(-1.5)


def test_weighted_mid_smooths_mid_over_window():
    """weighted_mid_5 should equal a running mean of the last 5 mids."""
    facts = []
    mids = [5000.0, 5001.0, 5002.0, 5003.0, 5004.0, 5005.0, 5006.0]
    for i, m in enumerate(mids):
        facts.append(FactRow(
            timestamp=i * 100, product="P", server_fv=m,
            bids=(BookLevel(price=int(m) - 2, volume=10),),
            asks=(BookLevel(price=int(m) + 2, volume=10),),
            mid_price=m, pnl=0.0,
        ))
    scores = score_estimators(facts, weighted_mid_window=5)
    # weighted_mid_5: at tick 6, history = mids[2..6] = [5002..5006], mean = 5004.
    # truth at tick 6 is 5006. So weighted_mid_5 should LAG truth by ~2.
    wm = next(s for s in scores if s.name == "weighted_mid_5")
    assert wm.bias < 0  # estimator below truth on rising mids
