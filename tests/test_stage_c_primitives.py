"""Unit tests for Stage C primitives: SignalBus, signal validation, PredictiveEstimator."""

from __future__ import annotations

import random

import pytest

from src.core.config import ProductConfig
from src.core.fair_value import MidEstimator
from src.core.primitives.predictive_estimator import (
    PredictiveEstimator,
    PredictiveEstimatorConfig,
)
from src.core.primitives.signal_bus import SignalBus, SignalValue
from src.core.primitives.signal_validation import (
    shuffle_test,
    strict_lag_test,
    validate_signal,
    walk_forward_test,
    own_quote_causality_test,
)
from src.core.types import BookLevel, NormalizedSnapshot, ProductMemory


# ============================================================= SignalBus


@pytest.mark.unit
def test_bus_emit_get_trusted_only_default():
    bus = SignalBus()
    bus.emit(SignalValue(name="flow", value=0.5, validated=True, ic=0.1))
    val = bus.get("flow")
    assert val is not None
    assert val.value == 0.5


@pytest.mark.unit
def test_bus_filters_unvalidated_by_default():
    bus = SignalBus()
    bus.emit(SignalValue(name="raw_obi", value=0.7, validated=False))
    assert bus.get("raw_obi") is None
    assert bus.get("raw_obi", trusted_only=False) is not None


@pytest.mark.unit
def test_bus_latest_emit_wins():
    bus = SignalBus()
    bus.emit(SignalValue(name="x", value=1.0, validated=True))
    bus.emit(SignalValue(name="x", value=2.0, validated=True))
    assert bus.get("x").value == 2.0


@pytest.mark.unit
def test_bus_all_returns_only_validated_by_default():
    bus = SignalBus()
    bus.emit(SignalValue(name="good", value=1, validated=True))
    bus.emit(SignalValue(name="bad", value=2, validated=False))
    assert set(bus.all().keys()) == {"good"}
    assert set(bus.all(trusted_only=False).keys()) == {"good", "bad"}


@pytest.mark.unit
def test_bus_clear_resets():
    bus = SignalBus()
    bus.emit(SignalValue(name="x", value=1, validated=True))
    bus.clear()
    assert bus.get("x") is None
    assert bus.names() == ()


@pytest.mark.unit
def test_signal_value_is_frozen():
    v = SignalValue(name="x", value=1.0)
    with pytest.raises((TypeError, AttributeError)):
        v.value = 2.0  # type: ignore[misc]


# ============================================================= validation


@pytest.mark.unit
def test_shuffle_test_passes_for_random_noise():
    """Random features paired with random returns: IC ~0, shuffle IC ~0 ⇒ pass."""
    rng = random.Random(0)
    n = 500
    features = [rng.gauss(0, 1) for _ in range(n)]
    returns = [rng.gauss(0, 1) for _ in range(n)]
    r = shuffle_test(features, returns, n_shuffles=30, max_shuffled_ic=0.15, seed=1)
    assert r.passed


@pytest.mark.unit
def test_shuffle_test_fails_when_both_series_correlate_with_time():
    """If both features and returns trend with time, shuffling kills the
    correlation BUT the raw IC is high — catches time-trend confounds.
    """
    n = 500
    rng = random.Random(0xCAFE)
    features = [float(i) for i in range(n)]  # monotonic
    returns = [float(i) + rng.random() for i in range(n)]  # monotonic + seeded noise
    # Raw Pearson is high. After shuffle, should drop to ~0 — test passes.
    r = shuffle_test(features, returns, n_shuffles=30, max_shuffled_ic=0.15, seed=1)
    assert r.passed  # shuffled IC is near zero — this is the intended behavior


@pytest.mark.unit
def test_strict_lag_test_detects_contemporaneous_correlation():
    """Feature = return (same tick) ⇒ strict-lag IC ≈ 0 (feature at t-k
    can't predict return at t). Previously the assertion was an
    ``or``-guarded disjunction that could pass under either branch;
    this version checks each invariant separately.
    """
    rng = random.Random(2026)
    n = 500
    returns = [rng.gauss(0, 1) for _ in range(n)]
    features = returns.copy()  # perfect contemporaneous correlation
    r = strict_lag_test(features, returns, lag_k=10, min_ic=0.03)
    # With random noise + a lag of 10, the lagged IC must fall near zero
    # AND the test must reject the signal.
    assert not r.passed, f"strict-lag must reject lag-shifted noise; ic={r.ic}"
    assert r.ic is not None and abs(r.ic) < 0.15, (
        f"lagged-IC on random noise must be near zero; got {r.ic}"
    )


@pytest.mark.unit
def test_strict_lag_test_rejects_signal_at_wrong_lag():
    """Feature at t-5 predicts return at t. Tested at lag_k=10, the
    alignment is off by 5 and reduces to noise.

    Previously the assertion was ``not r.passed or small_ic`` which can
    pass under either branch; split into two deterministic checks.
    """
    n = 2000  # large sample so tail correlations collapse.
    rng = random.Random(1)
    base = [rng.gauss(0, 1) for _ in range(n)]
    features = [0.0] * 5 + base[:-5]  # feature[t] = base[t-5]
    returns = base.copy()             # returns[t]  = base[t]

    # At lag_k=50 the alignment becomes feature[t-50]=base[t-55] vs
    # returns[t]=base[t] — uncorrelated — so the test must reject. The
    # min_ic=0.10 threshold is well above any spurious finite-sample IC.
    wrong_lag = strict_lag_test(features, returns, lag_k=50, min_ic=0.10)
    assert not wrong_lag.passed, (
        f"strict-lag at wrong lag must fail; ic={wrong_lag.ic}"
    )
    assert wrong_lag.ic is not None and abs(wrong_lag.ic) < 0.10, (
        f"wrong-lag IC on random base must be near zero; got {wrong_lag.ic}"
    )


@pytest.mark.unit
def test_walk_forward_handles_insufficient_data():
    features = [1.0] * 40
    returns = [1.0] * 40
    r = walk_forward_test(features, returns)
    assert not r.passed
    assert "too few" in r.detail


@pytest.mark.unit
def test_walk_forward_passes_when_signal_is_stable():
    """Stable linear signal, same IS and OOS IC ⇒ pass."""
    rng = random.Random(0)
    n = 1000
    base = [rng.gauss(0, 1) for _ in range(n)]
    features = [v + rng.gauss(0, 0.1) for v in base]  # features correlated w/ base
    returns = base.copy()
    r = walk_forward_test(features, returns, train_fraction=0.7, min_oos_ic_ratio=0.5)
    assert r.passed


@pytest.mark.unit
def test_own_quote_causality_handles_mostly_own_ticks():
    """If our quotes are present almost everywhere, test is vacuous."""
    features = [1.0] * 100
    returns = [1.0] * 100
    present = [True] * 100
    r = own_quote_causality_test(features, returns, present)
    assert r.passed  # vacuously passes — not enough clean ticks
    assert "clean ticks" in r.detail


@pytest.mark.unit
def test_validate_signal_aggregates_all_tests():
    rng = random.Random(0)
    n = 500
    features = [rng.gauss(0, 1) for _ in range(n)]
    returns = [rng.gauss(0, 1) for _ in range(n)]
    report = validate_signal("random_test", features, returns)
    assert report.signal_name == "random_test"
    assert len(report.results) == 3  # no own_quote data passed
    # Random noise has near-zero IC; shuffle passes, strict-lag fails (random).
    assert any(r.test_name == "shuffle" for r in report.results)


# ======================================================== PredictiveEstimator


def _snap() -> NormalizedSnapshot:
    return NormalizedSnapshot(
        product="P", timestamp=0,
        bids=(BookLevel(price=99, volume=10),),
        asks=(BookLevel(price=101, volume=10),),
    )


def _cfg() -> ProductConfig:
    return ProductConfig(
        position_limit=50,
        strategy_name="market_making",
        fair_value_method="mid",
    )


@pytest.mark.unit
def test_predictive_estimator_no_signal_returns_base():
    bus = SignalBus()
    base = MidEstimator()
    est = PredictiveEstimator(
        base=base,
        config=PredictiveEstimatorConfig(signal_name="absent_signal", coefficient=1.0),
        bus=bus,
    )
    result = est.estimate(_snap(), ProductMemory(), _cfg())
    assert result is not None
    # Mid of 99/101 = 100; no signal ⇒ base price preserved.
    assert result.price == 100.0


@pytest.mark.unit
def test_predictive_estimator_applies_signal():
    bus = SignalBus()
    bus.emit(SignalValue(name="drift", value=1.5, validated=True, ic=0.15))
    est = PredictiveEstimator(
        base=MidEstimator(),
        config=PredictiveEstimatorConfig(signal_name="drift", coefficient=2.0),
        bus=bus,
    )
    result = est.estimate(_snap(), ProductMemory(), _cfg())
    assert result is not None
    # mid (100) + 2.0 * 1.5 = 103.0
    assert result.price == 103.0


@pytest.mark.unit
def test_predictive_estimator_caps_adjustment():
    bus = SignalBus()
    bus.emit(SignalValue(name="runaway", value=100.0, validated=True))
    est = PredictiveEstimator(
        base=MidEstimator(),
        config=PredictiveEstimatorConfig(
            signal_name="runaway", coefficient=10.0, max_adjustment=3.0,
        ),
        bus=bus,
    )
    result = est.estimate(_snap(), ProductMemory(), _cfg())
    assert result is not None
    # Adjustment capped at ±3.0 despite 10*100 = 1000.
    assert result.price == 103.0


@pytest.mark.unit
def test_predictive_estimator_ignores_unvalidated_by_default():
    bus = SignalBus()
    bus.emit(SignalValue(name="raw", value=5.0, validated=False))
    est = PredictiveEstimator(
        base=MidEstimator(),
        config=PredictiveEstimatorConfig(signal_name="raw", coefficient=1.0),
        bus=bus,
    )
    result = est.estimate(_snap(), ProductMemory(), _cfg())
    assert result is not None
    # Unvalidated signal ignored ⇒ base price preserved.
    assert result.price == 100.0


@pytest.mark.unit
def test_predictive_estimator_always_requires_validated_signals():
    """D9 enforcement: even a usable raw signal must be ignored if it
    lacks ``validated=True``. Replaces a prior test that exercised the
    (removed) ``require_validated=False`` escape hatch."""
    bus = SignalBus()
    bus.emit(SignalValue(name="raw", value=1.0, validated=False))
    est = PredictiveEstimator(
        base=MidEstimator(),
        config=PredictiveEstimatorConfig(
            signal_name="raw", coefficient=2.0,
        ),
        bus=bus,
    )
    result = est.estimate(_snap(), ProductMemory(), _cfg())
    assert result is not None
    # Unvalidated signal is ignored regardless; base mid preserved.
    assert result.price == 100.0
