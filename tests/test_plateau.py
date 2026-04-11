"""Unit tests for ``src.backtest.plateau``.

These tests drive the Phase 6 cross-slice plateau helpers without
touching the replay engine: all inputs are hand-built
``ParameterSweepReport`` objects. That keeps the tests fast and
focused on the plateau rule, medoid selection, and promotion gate
logic rather than simulator behaviour.
"""

from __future__ import annotations

import pytest

from src.backtest.parameter_sweep import (
    ParameterSweepReport,
    SweepRow,
)
from src.backtest.plateau import (
    Phase6CrossSliceReport,
    ProductComparison,
    SlicePlateau,
    compare_subsweep_winners,
    filter_inventory_discipline,
    intersect_plateaus,
    medoid,
    plateau_band,
    post_filter_peak,
)


def _row(
    *,
    maker_edge: float = 1.0,
    taker_edge: float = 1.0,
    inventory_skew: float = 2.0,
    flatten_threshold: float = 0.7,
    pnl: float = 0.0,
    trade_count: int = 10,
    maker_share: float | None = 0.05,
    final_position: int = 0,
    steps_near_limit: int = 0,
    extra: dict[str, object] | None = None,
) -> SweepRow:
    params: dict[str, object] = {
        "maker_edge": maker_edge,
        "taker_edge": taker_edge,
        "inventory_skew": inventory_skew,
        "flatten_threshold": flatten_threshold,
    }
    if extra is not None:
        params.update(extra)
    return SweepRow(
        params=params,
        pnl=pnl,
        trade_count=trade_count,
        maker_share=maker_share,
        final_position=final_position,
        steps_near_limit=steps_near_limit,
    )


def _report(
    *,
    run_label: str,
    rows: tuple[SweepRow, ...],
    baseline: SweepRow,
    product: str = "TEST",
    fair_value_method: str = "mid",
) -> ParameterSweepReport:
    return ParameterSweepReport(
        run_label=run_label,
        product=product,
        generated_at="2026-04-11T00:00:00+00:00",
        fair_value_method=fair_value_method,
        baseline=baseline,
        rows=rows,
        aggregates=(),
    )


# --------------------------------------------------------------- filters


@pytest.mark.unit
def test_filter_inventory_discipline_drops_near_limit_rows() -> None:
    rows = (
        _row(maker_edge=1.0, pnl=100.0, steps_near_limit=0),
        _row(maker_edge=2.0, pnl=200.0, steps_near_limit=3),
        _row(maker_edge=3.0, pnl=50.0, steps_near_limit=0),
    )
    survivors = filter_inventory_discipline(rows)
    assert len(survivors) == 2
    assert all(row.steps_near_limit == 0 for row in survivors)
    assert {row.params["maker_edge"] for row in survivors} == {1.0, 3.0}


@pytest.mark.unit
def test_post_filter_peak_returns_none_when_all_rows_filtered() -> None:
    rows = (
        _row(pnl=100.0, steps_near_limit=5),
        _row(pnl=200.0, steps_near_limit=1),
    )
    survivors = filter_inventory_discipline(rows)
    assert post_filter_peak(survivors) is None


@pytest.mark.unit
def test_post_filter_peak_returns_max_pnl_of_survivors() -> None:
    rows = (
        _row(pnl=100.0, steps_near_limit=0),
        _row(pnl=250.0, steps_near_limit=0),
        _row(pnl=500.0, steps_near_limit=1),  # filtered out
        _row(pnl=180.0, steps_near_limit=0),
    )
    survivors = filter_inventory_discipline(rows)
    assert post_filter_peak(survivors) == pytest.approx(250.0)


# --------------------------------------------------------------- band


@pytest.mark.unit
def test_plateau_band_keeps_rows_within_ten_percent_of_post_filter_peak() -> None:
    # Peak after filtering is 200. Band is pnl >= 180.
    rows = (
        _row(maker_edge=1.0, pnl=200.0, steps_near_limit=0),
        _row(maker_edge=2.0, pnl=185.0, steps_near_limit=0),  # in (>= 180)
        _row(maker_edge=3.0, pnl=180.0, steps_near_limit=0),  # in (boundary)
        _row(maker_edge=4.0, pnl=179.99, steps_near_limit=0),  # out
        _row(maker_edge=5.0, pnl=500.0, steps_near_limit=2),  # filtered by inventory
    )
    filtered = filter_inventory_discipline(rows)
    band = plateau_band(filtered)
    band_maker_edges = {row.params["maker_edge"] for row in band}
    assert band_maker_edges == {1.0, 2.0, 3.0}


@pytest.mark.unit
def test_plateau_band_empty_when_no_rows_survive_filter() -> None:
    rows = (_row(pnl=100.0, steps_near_limit=4),)
    filtered = filter_inventory_discipline(rows)
    assert plateau_band(filtered) == ()


# --------------------------------------------------------------- medoid


@pytest.mark.unit
def test_medoid_empty_intersection_returns_none() -> None:
    axis_ranges = {"maker_edge": 2.0}
    assert medoid((), axis_ranges) is None


@pytest.mark.unit
def test_medoid_single_row_returns_that_row() -> None:
    only = _row(maker_edge=2.0, pnl=100.0)
    axis_ranges = {
        "maker_edge": 2.0,
        "taker_edge": 1.0,
        "inventory_skew": 1.0,
        "flatten_threshold": 0.15,
    }
    assert medoid((only,), axis_ranges) is only


@pytest.mark.unit
def test_medoid_picks_geometric_center_of_numeric_intersection() -> None:
    # Three rows along the maker_edge axis: 1.0, 2.0, 3.0.
    # 2.0 is the medoid because its total normalized distance is minimal.
    left = _row(maker_edge=1.0, pnl=100.0)
    mid_row = _row(maker_edge=2.0, pnl=100.0)
    right = _row(maker_edge=3.0, pnl=100.0)
    axis_ranges = {
        "maker_edge": 2.0,
        "taker_edge": 1.0,
        "inventory_skew": 1.0,
        "flatten_threshold": 0.15,
    }
    center = medoid((left, mid_row, right), axis_ranges)
    assert center is mid_row


@pytest.mark.unit
def test_medoid_handles_mixed_categorical_and_numeric_axes() -> None:
    # fair_value_method is categorical: 0 distance if equal, 1 otherwise.
    # maker_edge is numeric and normalized by axis range.
    a = _row(maker_edge=1.0, pnl=100.0, extra={"fair_value_method": "weighted_mid"})
    b = _row(maker_edge=2.0, pnl=110.0, extra={"fair_value_method": "weighted_mid"})
    c = _row(maker_edge=3.0, pnl=90.0, extra={"fair_value_method": "rolling_mid"})
    axis_ranges = {
        "maker_edge": 2.0,
        "taker_edge": 1.0,
        "inventory_skew": 1.0,
        "flatten_threshold": 0.15,
        "fair_value_method": 1.0,  # categorical ranges are ignored but must exist
    }
    # Distances (normalized):
    #   d(a,b) = |1-2|/2 + cat_eq = 0.5 + 0 = 0.5
    #   d(a,c) = |1-3|/2 + cat_neq = 1.0 + 1 = 2.0
    #   d(b,c) = |2-3|/2 + cat_neq = 0.5 + 1 = 1.5
    # Sums: a=2.5, b=2.0, c=3.5 -> b is medoid.
    center = medoid((a, b, c), axis_ranges)
    assert center is b


@pytest.mark.unit
def test_medoid_tie_break_prefers_higher_combined_pnl() -> None:
    # Two rows equidistant from each other: tie-break on pnl.
    a = _row(maker_edge=1.0, pnl=100.0)
    b = _row(maker_edge=3.0, pnl=200.0)
    axis_ranges = {
        "maker_edge": 2.0,
        "taker_edge": 1.0,
        "inventory_skew": 1.0,
        "flatten_threshold": 0.15,
    }
    center = medoid((a, b), axis_ranges)
    assert center is b


# ------------------------------------------------------ intersect_plateaus


def _slices(
    *,
    baseline: SweepRow,
    day_minus_2_rows: tuple[SweepRow, ...],
    day_minus_1_rows: tuple[SweepRow, ...],
    combined_rows: tuple[SweepRow, ...],
) -> dict[str, ParameterSweepReport]:
    return {
        "day_-2": _report(
            run_label="test_day_-2", rows=day_minus_2_rows, baseline=baseline
        ),
        "day_-1": _report(
            run_label="test_day_-1", rows=day_minus_1_rows, baseline=baseline
        ),
        "combined": _report(
            run_label="test_combined", rows=combined_rows, baseline=baseline
        ),
    }


@pytest.mark.unit
def test_intersect_plateaus_disjoint_plateaus_yield_retain_verdict() -> None:
    # Peak on day -2 is at maker_edge=1.0; on day -1 at maker_edge=3.0.
    # Intersection is empty.
    baseline = _row(maker_edge=2.0, pnl=50.0)
    day_minus_2_rows = (
        _row(maker_edge=1.0, pnl=200.0),  # peak
        _row(maker_edge=2.0, pnl=50.0),
        _row(maker_edge=3.0, pnl=10.0),
    )
    day_minus_1_rows = (
        _row(maker_edge=1.0, pnl=10.0),
        _row(maker_edge=2.0, pnl=50.0),
        _row(maker_edge=3.0, pnl=200.0),  # peak
    )
    combined_rows = (
        _row(maker_edge=1.0, pnl=100.0),
        _row(maker_edge=2.0, pnl=50.0),
        _row(maker_edge=3.0, pnl=100.0),
    )
    report = intersect_plateaus(
        _slices(
            baseline=baseline,
            day_minus_2_rows=day_minus_2_rows,
            day_minus_1_rows=day_minus_1_rows,
            combined_rows=combined_rows,
        ),
        product="TEST",
        sub_sweep="disjoint",
    )
    assert report.intersection == ()
    assert report.center is None
    assert report.verdict == "retain"


@pytest.mark.unit
def test_intersect_plateaus_single_row_intersection_yields_narrow_verdict() -> None:
    baseline = _row(maker_edge=2.0, pnl=50.0, trade_count=10, maker_share=0.05)
    shared = _row(maker_edge=1.0, pnl=200.0, trade_count=20, maker_share=0.05)
    day_minus_2_rows = (shared, _row(maker_edge=2.0, pnl=50.0))
    day_minus_1_rows = (shared, _row(maker_edge=3.0, pnl=50.0))
    combined_rows = (shared, _row(maker_edge=2.0, pnl=50.0))
    report = intersect_plateaus(
        _slices(
            baseline=baseline,
            day_minus_2_rows=day_minus_2_rows,
            day_minus_1_rows=day_minus_1_rows,
            combined_rows=combined_rows,
        ),
        product="TEST",
        sub_sweep="narrow",
    )
    assert len(report.intersection) == 1
    assert report.center == shared
    assert report.verdict == "narrow"


@pytest.mark.unit
def test_intersect_plateaus_three_row_intersection_passing_gate_yields_promotion_candidate() -> None:
    # Baseline is 50 pnl / 10 trades / 5% maker. Candidates lift pnl >= 1.1x
    # with zero near-limit, trade count 15 (within 0.5x..3x), and same
    # maker_share. A full cartesian of (maker_edge=1 or 2) x
    # (inventory_skew=2 or 3) is 4 rows; three of them share across all
    # slices and pass the gate.
    baseline = _row(maker_edge=2.0, pnl=50.0, trade_count=10, maker_share=0.05)
    plateau_rows = (
        _row(maker_edge=1.0, inventory_skew=2.0, pnl=100.0, trade_count=15, maker_share=0.05),
        _row(maker_edge=2.0, inventory_skew=2.0, pnl=105.0, trade_count=15, maker_share=0.05),
        _row(maker_edge=2.0, inventory_skew=3.0, pnl=102.0, trade_count=15, maker_share=0.05),
    )
    # Add one inventory-violating row that would be filtered.
    def make_slice_rows() -> tuple[SweepRow, ...]:
        return (
            *plateau_rows,
            _row(maker_edge=3.0, pnl=500.0, steps_near_limit=10, maker_share=0.05),
        )

    report = intersect_plateaus(
        _slices(
            baseline=baseline,
            day_minus_2_rows=make_slice_rows(),
            day_minus_1_rows=make_slice_rows(),
            combined_rows=make_slice_rows(),
        ),
        product="TEST",
        sub_sweep="promotion_candidate",
    )
    assert len(report.intersection) == 3
    assert report.verdict == "promotion_candidate"
    assert report.gate_checks["pnl_lift"] is True
    assert report.gate_checks["inventory"] is True
    assert report.gate_checks["trade_count"] is True
    assert report.gate_checks["regime"] is True
    assert report.center is not None


@pytest.mark.unit
def test_intersect_plateaus_trade_count_blowup_fails_gate() -> None:
    # Baseline: 10 trades. Candidate: 40 trades (> 3x baseline).
    baseline = _row(maker_edge=2.0, pnl=50.0, trade_count=10, maker_share=0.05)
    plateau_rows = (
        _row(maker_edge=1.0, pnl=100.0, trade_count=40, maker_share=0.05),
        _row(maker_edge=2.0, pnl=100.0, trade_count=40, maker_share=0.05),
        _row(maker_edge=3.0, pnl=100.0, trade_count=40, maker_share=0.05),
    )
    report = intersect_plateaus(
        _slices(
            baseline=baseline,
            day_minus_2_rows=plateau_rows,
            day_minus_1_rows=plateau_rows,
            combined_rows=plateau_rows,
        ),
        product="TEST",
        sub_sweep="tradeblow",
    )
    assert report.gate_checks["trade_count"] is False
    assert report.verdict == "retain"


@pytest.mark.unit
def test_intersect_plateaus_regime_flip_fails_gate() -> None:
    baseline = _row(maker_edge=2.0, pnl=50.0, trade_count=10, maker_share=0.50)
    # Candidate flipped to pure-taker (maker_share=0.05): |Δ| = 0.45 > 0.20.
    plateau_rows = (
        _row(maker_edge=1.0, pnl=100.0, trade_count=15, maker_share=0.05),
        _row(maker_edge=2.0, pnl=100.0, trade_count=15, maker_share=0.05),
        _row(maker_edge=3.0, pnl=100.0, trade_count=15, maker_share=0.05),
    )
    report = intersect_plateaus(
        _slices(
            baseline=baseline,
            day_minus_2_rows=plateau_rows,
            day_minus_1_rows=plateau_rows,
            combined_rows=plateau_rows,
        ),
        product="TEST",
        sub_sweep="regimeflip",
    )
    assert report.gate_checks["regime"] is False
    assert report.verdict == "retain"


@pytest.mark.unit
def test_intersect_plateaus_diagnostic_role_skips_gate_and_pins_verdict() -> None:
    # Even if the underlying intersection would be a promotion_candidate,
    # role="diagnostic" forces verdict="diagnostic" with empty gate_checks.
    baseline = _row(maker_edge=2.0, pnl=50.0, trade_count=10, maker_share=0.05)
    plateau_rows = (
        _row(maker_edge=1.0, pnl=200.0, trade_count=15, maker_share=0.05),
        _row(maker_edge=2.0, pnl=200.0, trade_count=15, maker_share=0.05),
        _row(maker_edge=3.0, pnl=200.0, trade_count=15, maker_share=0.05),
    )
    report = intersect_plateaus(
        _slices(
            baseline=baseline,
            day_minus_2_rows=plateau_rows,
            day_minus_1_rows=plateau_rows,
            combined_rows=plateau_rows,
        ),
        product="TEST",
        sub_sweep="ewma_mid_alpha_020",
        role="diagnostic",
    )
    assert report.role == "diagnostic"
    assert report.verdict == "diagnostic"
    assert report.gate_checks == {}


@pytest.mark.unit
def test_intersect_plateaus_baseline_in_band_flag_reflects_plateau_membership() -> None:
    # Baseline sits on the plateau: its pnl is within 10% of peak.
    baseline_in = _row(maker_edge=2.0, pnl=190.0, steps_near_limit=0)
    day_rows_with_baseline_on_plateau = (
        baseline_in,
        _row(maker_edge=1.0, pnl=200.0),  # peak
        _row(maker_edge=3.0, pnl=150.0),
    )
    report_in = intersect_plateaus(
        _slices(
            baseline=baseline_in,
            day_minus_2_rows=day_rows_with_baseline_on_plateau,
            day_minus_1_rows=day_rows_with_baseline_on_plateau,
            combined_rows=day_rows_with_baseline_on_plateau,
        ),
        product="TEST",
        sub_sweep="baseline_in_band",
    )
    assert all(slice_plateau.baseline_in_band for slice_plateau in report_in.per_slice)

    # Baseline sits off the plateau: pnl well below the band.
    baseline_out = _row(maker_edge=2.0, pnl=100.0, steps_near_limit=0)
    day_rows_with_baseline_off_plateau = (
        baseline_out,
        _row(maker_edge=1.0, pnl=300.0),  # peak
        _row(maker_edge=3.0, pnl=150.0),
    )
    report_out = intersect_plateaus(
        _slices(
            baseline=baseline_out,
            day_minus_2_rows=day_rows_with_baseline_off_plateau,
            day_minus_1_rows=day_rows_with_baseline_off_plateau,
            combined_rows=day_rows_with_baseline_off_plateau,
        ),
        product="TEST",
        sub_sweep="baseline_off_band",
    )
    assert all(not slice_plateau.baseline_in_band for slice_plateau in report_out.per_slice)


@pytest.mark.unit
def test_slice_plateau_baseline_in_band_respects_inventory_filter() -> None:
    # A baseline with near-limit stress must be flagged as NOT in band
    # even if its pnl is high.
    near_limit_baseline = _row(pnl=300.0, steps_near_limit=5)
    rows = (
        near_limit_baseline,
        _row(maker_edge=1.0, pnl=200.0, steps_near_limit=0),
    )
    report = intersect_plateaus(
        _slices(
            baseline=near_limit_baseline,
            day_minus_2_rows=rows,
            day_minus_1_rows=rows,
            combined_rows=rows,
        ),
        product="TEST",
        sub_sweep="baseline_near_limit",
    )
    for slice_plateau in report.per_slice:
        assert slice_plateau.baseline_in_band is False


# ------------------------------------------------- compare_subsweep_winners


def _build_cross_slice_report(
    *,
    sub_sweep: str,
    role: str,
    verdict: str,
    intersection_size: int = 0,
    combined_pnl_lift: float = 0.0,
    maker_share_delta: float = 0.0,
    center_pnl: float = 0.0,
) -> Phase6CrossSliceReport:
    """Build a hand-rolled Phase6CrossSliceReport for comparison tests.

    We do not need full per-slice data to test the winner-selection
    tie-break chain, only the fields ``compare_subsweep_winners`` looks
    at: verdict, role, intersection length, and the scoring signals.
    """
    baseline_row = _row(maker_edge=2.0, pnl=100.0, maker_share=0.05)
    center_row = _row(
        maker_edge=2.0,
        pnl=center_pnl or (100.0 * (1.0 + combined_pnl_lift)),
        maker_share=0.05 + maker_share_delta,
    )
    intersection = tuple(
        _row(maker_edge=1.0 + i, pnl=150.0, maker_share=center_row.maker_share)
        for i in range(intersection_size)
    )
    per_slice = tuple(
        SlicePlateau(
            slice_name=name,
            baseline=baseline_row,
            peak_pnl=200.0,
            band_rows=intersection,
            baseline_in_band=False,
        )
        for name in ("day_-2", "day_-1", "combined")
    )
    return Phase6CrossSliceReport(
        product="TEST",
        sub_sweep=sub_sweep,
        role=role,
        run_label=f"cmp_{sub_sweep}",
        generated_at="2026-04-11T00:00:00+00:00",
        per_slice=per_slice,
        intersection=intersection,
        center=center_row if intersection_size > 0 else None,
        gate_checks={} if role == "diagnostic" else {
            "pnl_lift": True,
            "inventory": True,
            "trade_count": True,
            "regime": True,
        },
        verdict=verdict,
        reason="test",
    )


@pytest.mark.unit
def test_compare_subsweep_winners_excludes_diagnostic_role() -> None:
    weighted = _build_cross_slice_report(
        sub_sweep="weighted_mid",
        role="promotion_eligible",
        verdict="retain",
    )
    rolling = _build_cross_slice_report(
        sub_sweep="rolling_mid",
        role="promotion_eligible",
        verdict="retain",
    )
    ewma = _build_cross_slice_report(
        sub_sweep="ewma_mid_alpha_020",
        role="diagnostic",
        verdict="diagnostic",
        intersection_size=5,
        combined_pnl_lift=5.0,
    )

    comparison = compare_subsweep_winners((weighted, rolling, ewma))

    assert "ewma_mid_alpha_020" in comparison.excluded
    assert "ewma_mid_alpha_020" not in comparison.considered
    assert comparison.winner is None
    assert comparison.verdict == "retain"


@pytest.mark.unit
def test_compare_subsweep_winners_both_eligible_retain_yields_retain() -> None:
    weighted = _build_cross_slice_report(
        sub_sweep="weighted_mid",
        role="promotion_eligible",
        verdict="retain",
    )
    rolling = _build_cross_slice_report(
        sub_sweep="rolling_mid",
        role="promotion_eligible",
        verdict="retain",
    )
    comparison = compare_subsweep_winners((weighted, rolling))
    assert comparison.verdict == "retain"
    assert comparison.winner is None


@pytest.mark.unit
def test_compare_subsweep_winners_single_eligible_candidate_wins() -> None:
    weighted = _build_cross_slice_report(
        sub_sweep="weighted_mid",
        role="promotion_eligible",
        verdict="promotion_candidate",
        intersection_size=3,
        combined_pnl_lift=0.2,
    )
    rolling = _build_cross_slice_report(
        sub_sweep="rolling_mid",
        role="promotion_eligible",
        verdict="retain",
    )
    comparison = compare_subsweep_winners((weighted, rolling))
    assert comparison.winner == "weighted_mid"
    assert comparison.verdict == "promotion_candidate"


@pytest.mark.unit
def test_compare_subsweep_winners_tie_break_prefers_larger_intersection() -> None:
    weighted = _build_cross_slice_report(
        sub_sweep="weighted_mid",
        role="promotion_eligible",
        verdict="promotion_candidate",
        intersection_size=3,
        combined_pnl_lift=0.2,
    )
    rolling = _build_cross_slice_report(
        sub_sweep="rolling_mid",
        role="promotion_eligible",
        verdict="promotion_candidate",
        intersection_size=5,
        combined_pnl_lift=0.2,
    )
    comparison = compare_subsweep_winners((weighted, rolling))
    assert comparison.winner == "rolling_mid"


@pytest.mark.unit
def test_compare_subsweep_winners_tie_break_prefers_higher_pnl_lift_when_sizes_match() -> None:
    weighted = _build_cross_slice_report(
        sub_sweep="weighted_mid",
        role="promotion_eligible",
        verdict="promotion_candidate",
        intersection_size=4,
        combined_pnl_lift=0.15,
    )
    rolling = _build_cross_slice_report(
        sub_sweep="rolling_mid",
        role="promotion_eligible",
        verdict="promotion_candidate",
        intersection_size=4,
        combined_pnl_lift=0.30,
    )
    comparison = compare_subsweep_winners((weighted, rolling))
    assert comparison.winner == "rolling_mid"


@pytest.mark.unit
def test_compare_subsweep_winners_tie_break_prefers_smaller_regime_shift_when_rest_ties() -> None:
    weighted = _build_cross_slice_report(
        sub_sweep="weighted_mid",
        role="promotion_eligible",
        verdict="promotion_candidate",
        intersection_size=4,
        combined_pnl_lift=0.20,
        maker_share_delta=0.05,
    )
    rolling = _build_cross_slice_report(
        sub_sweep="rolling_mid",
        role="promotion_eligible",
        verdict="promotion_candidate",
        intersection_size=4,
        combined_pnl_lift=0.20,
        maker_share_delta=0.15,
    )
    comparison = compare_subsweep_winners((weighted, rolling))
    assert comparison.winner == "weighted_mid"


@pytest.mark.unit
def test_compare_subsweep_winners_narrow_sub_sweep_does_not_win_over_retain() -> None:
    weighted = _build_cross_slice_report(
        sub_sweep="weighted_mid",
        role="promotion_eligible",
        verdict="narrow",
        intersection_size=1,
    )
    rolling = _build_cross_slice_report(
        sub_sweep="rolling_mid",
        role="promotion_eligible",
        verdict="retain",
    )
    comparison = compare_subsweep_winners((weighted, rolling))
    # The plan says: if one is narrow and the other is
    # retain/promotion_candidate, the narrow one is archived and the
    # other drives. Here the other is retain, so the product verdict
    # is retain with no winner.
    assert comparison.verdict == "retain"
    assert comparison.winner is None
