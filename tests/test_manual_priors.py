"""Unit tests for the crowd-prior helpers."""

from __future__ import annotations

import pytest

from src.manual_rounds.nash_crowd import CrowdCell
from src.manual_rounds.priors import (
    concentrated_on,
    inverse_nash,
    mix_priors,
    nice_number_overlay,
    proportional_to_multiplier,
    proportional_to_ratio,
    uniform_prior,
)


@pytest.fixture
def cells() -> tuple[CrowdCell, ...]:
    return (
        CrowdCell(name="A", multiplier=10, inhabitants=1),
        CrowdCell(name="B", multiplier=40, inhabitants=4),
        CrowdCell(name="C", multiplier=90, inhabitants=10),
    )


@pytest.mark.unit
def test_uniform_prior_sums_to_one(cells: tuple[CrowdCell, ...]) -> None:
    p = uniform_prior(cells)
    assert sum(p.values()) == pytest.approx(1.0)
    assert p["A"] == p["B"] == p["C"]


@pytest.mark.unit
def test_proportional_to_multiplier(cells: tuple[CrowdCell, ...]) -> None:
    p = proportional_to_multiplier(cells, exponent=1.0)
    # Weights proportional to multipliers 10 : 40 : 90 -> 1 : 4 : 9.
    total = 10 + 40 + 90
    assert p["A"] == pytest.approx(10 / total)
    assert p["C"] == pytest.approx(90 / total)


@pytest.mark.unit
def test_proportional_to_ratio(cells: tuple[CrowdCell, ...]) -> None:
    p = proportional_to_ratio(cells, exponent=1.0)
    # Ratios m/i = 10 : 10 : 9 -> all weights proportional to those.
    total = 10 + 10 + 9
    assert p["A"] == pytest.approx(10 / total)
    assert p["C"] == pytest.approx(9 / total)


@pytest.mark.unit
def test_inverse_nash_flips_ordering() -> None:
    base = {"A": 0.7, "B": 0.2, "C": 0.1}
    out = inverse_nash(base)
    # Cell with the smallest Nash share becomes the biggest in the
    # anti-Nash distribution.
    assert max(out, key=lambda k: out[k]) == "C"
    assert min(out, key=lambda k: out[k]) == "A"
    assert sum(out.values()) == pytest.approx(1.0)


@pytest.mark.unit
def test_concentrated_on_sums_to_one(cells: tuple[CrowdCell, ...]) -> None:
    p = concentrated_on(cells, targets=["A"], bleed=0.1)
    assert sum(p.values()) == pytest.approx(1.0)
    assert p["A"] > p["B"]
    assert p["B"] == pytest.approx(p["C"])


@pytest.mark.unit
def test_concentrated_on_rejects_unknown(cells: tuple[CrowdCell, ...]) -> None:
    with pytest.raises(ValueError):
        concentrated_on(cells, targets=["Z"])


@pytest.mark.unit
def test_nice_number_overlay_boosts_targets(cells: tuple[CrowdCell, ...]) -> None:
    base = uniform_prior(cells)
    out = nice_number_overlay(cells, base, nice_cell_names=["A"], boost=1.0)
    # Cell A should now carry more mass than B or C.
    assert out["A"] > out["B"]
    assert out["B"] == pytest.approx(out["C"])
    assert sum(out.values()) == pytest.approx(1.0)


@pytest.mark.unit
def test_mix_priors_matches_manual_linear_combo(cells: tuple[CrowdCell, ...]) -> None:
    u = uniform_prior(cells)
    c = concentrated_on(cells, targets=["B"], bleed=0.0)
    mixed = mix_priors([(0.5, u), (0.5, c)])
    # Cell B's mixed weight = 0.5 * 1/3 + 0.5 * 1 = 0.6667
    assert mixed["B"] == pytest.approx(0.5 * (1 / 3) + 0.5 * 1.0)
    assert sum(mixed.values()) == pytest.approx(1.0)


@pytest.mark.unit
def test_mix_priors_rejects_mismatched_keys() -> None:
    with pytest.raises(ValueError):
        mix_priors([(1.0, {"A": 0.5, "B": 0.5}), (1.0, {"A": 1.0})])
