"""Unit tests for the submission-note renderer."""

from __future__ import annotations

import pytest

from src.manual_rounds.submission_note import SubmissionNote


@pytest.mark.unit
def test_render_contains_all_sections() -> None:
    note = SubmissionNote(
        round_name="P4-R1",
        family="graph/path",
        chosen_answer="Shell -> X -> Y -> Shell, return 1.089",
        payoff_explanation="Product of rate-matrix edges on a 4x4 graph, 5 hops.",
        core_assumptions=["rate matrix is deterministic", "no hidden frictions"],
        naive_baseline="Shell -> Shell (no trade) = 1.000",
        crowd_adjusted="same as naive (single-agent)",
        robustness_range="path is unique and dominates by ~4%",
        backup_answer="Shell -> X -> Shell, return 1.05",
        failure_mode="rates updated mid-round",
        top_alternatives=["alt1 ~1.05", "alt2 ~1.04"],
    )
    rendered = note.render()
    for section in (
        "# P4-R1 — manual submission note",
        "Problem family",
        "Chosen answer",
        "Payoff structure",
        "Naive (no-opponent) baseline",
        "Crowd / opponent-adjusted answer",
        "Core assumptions",
        "Robustness range",
        "Backup answer if assumptions fail",
        "Biggest failure mode",
        "Top alternatives considered",
    ):
        assert section in rendered
    # Bullets survive.
    assert "- rate matrix is deterministic" in rendered
    assert "- alt1 ~1.05" in rendered


@pytest.mark.unit
def test_render_uses_placeholder_for_missing_fields() -> None:
    note = SubmissionNote(
        round_name="P4-R2",
        family="crowding",
        chosen_answer="pick C5",
        payoff_explanation="standard crowding payoff",
    )
    rendered = note.render()
    assert "_n/a_" in rendered
