"""Unit tests for Stage D primitives: BSM, IV solver, smile, conversion layer."""

from __future__ import annotations

import math

import pytest

from src.conversions.layer import (
    ConversionSpec,
    FillRateProbe,
    RegimeDetector,
    RemoteQuote,
    StockpileConfig,
    arb_edge,
    buy_local_break_even,
    conversion_size,
    sell_local_break_even,
    target_batch_size,
)
from src.options.bsm import (
    BSMInputs,
    call_greeks,
    call_price,
    implied_vol,
    norm_cdf,
    norm_pdf,
)
from src.options.smile import SmileConfig, SmileFitter, moneyness


# ================================================================= BSM


@pytest.mark.unit
def test_norm_cdf_symmetry():
    assert norm_cdf(0.0) == pytest.approx(0.5, abs=1e-6)
    assert norm_cdf(1.0) + norm_cdf(-1.0) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.unit
def test_norm_cdf_reference_values():
    # Textbook values from Abramowitz-Stegun.
    assert norm_cdf(1.0) == pytest.approx(0.8413, abs=1e-3)
    assert norm_cdf(1.96) == pytest.approx(0.9750, abs=1e-3)
    assert norm_cdf(-1.96) == pytest.approx(0.0250, abs=1e-3)


@pytest.mark.unit
def test_norm_pdf_peak_at_zero():
    assert norm_pdf(0.0) == pytest.approx(1.0 / math.sqrt(2 * math.pi), abs=1e-6)


@pytest.mark.unit
def test_call_price_deep_itm_converges_to_intrinsic():
    """Very deep ITM call, long T, low vol ⇒ price ≈ S - K."""
    inputs = BSMInputs(
        spot=200, strike=100, time_to_expiry=0.01, volatility=0.01,
    )
    p = call_price(inputs)
    assert p == pytest.approx(100.0, abs=0.5)


@pytest.mark.unit
def test_call_price_atm_sanity():
    """ATM call with standard params."""
    inputs = BSMInputs(
        spot=100, strike=100, time_to_expiry=1.0, volatility=0.2,
    )
    p = call_price(inputs)
    # ATM BS ≈ S * 0.4 * sigma * sqrt(T).
    assert p == pytest.approx(7.97, abs=0.5)


@pytest.mark.unit
def test_bsm_inputs_validation():
    with pytest.raises(ValueError):
        BSMInputs(spot=-1, strike=100, time_to_expiry=1.0, volatility=0.2)
    with pytest.raises(ValueError):
        BSMInputs(spot=100, strike=0, time_to_expiry=1.0, volatility=0.2)
    with pytest.raises(ValueError):
        BSMInputs(spot=100, strike=100, time_to_expiry=0, volatility=0.2)
    with pytest.raises(ValueError):
        BSMInputs(spot=100, strike=100, time_to_expiry=1, volatility=0)


@pytest.mark.unit
def test_greeks_atm_delta_near_half():
    inputs = BSMInputs(
        spot=100, strike=100, time_to_expiry=1.0, volatility=0.2,
    )
    g = call_greeks(inputs)
    assert 0.45 <= g.delta <= 0.65
    assert g.gamma > 0
    assert g.vega > 0
    assert g.theta < 0  # call theta negative (time decay)


@pytest.mark.unit
def test_iv_roundtrip():
    """Given a price from BSM, IV solver recovers the input vol."""
    spot, strike, T, vol = 100, 100, 1.0, 0.25
    price = call_price(BSMInputs(spot=spot, strike=strike, time_to_expiry=T, volatility=vol))
    iv = implied_vol(
        market_price=price, spot=spot, strike=strike, time_to_expiry=T,
    )
    assert iv == pytest.approx(vol, abs=1e-4)


@pytest.mark.unit
def test_iv_solver_returns_none_below_intrinsic():
    # Call at strike 100, spot 110: intrinsic = 10. Market price 5 is arb.
    iv = implied_vol(market_price=5, spot=110, strike=100, time_to_expiry=1.0)
    assert iv is None


@pytest.mark.unit
def test_iv_solver_returns_none_on_zero_price():
    assert implied_vol(market_price=0, spot=100, strike=100, time_to_expiry=1.0) is None


# ================================================================= smile


@pytest.mark.unit
def test_moneyness_formula():
    # K=100, S=100 ⇒ log(1) = 0
    assert moneyness(strike=100, spot=100, time_to_expiry=1.0) == 0.0
    # K>S ⇒ positive (OTM call)
    assert moneyness(strike=110, spot=100, time_to_expiry=1.0) > 0
    # K<S ⇒ negative (ITM call)
    assert moneyness(strike=90, spot=100, time_to_expiry=1.0) < 0


@pytest.mark.unit
def test_smile_fitter_ignores_outlier_iv():
    fitter = SmileFitter(config=SmileConfig(max_sensible_iv=1.5, min_sensible_iv=0.05))
    fitter.observe(strike=100, iv=5.0)  # too high
    fitter.observe(strike=100, iv=0.01)  # too low
    fitter.observe(strike=100, iv=0.20)  # OK
    # Only one observation accepted.
    iv = fitter.fair_iv(strike=100, spot=100, time_to_expiry=1.0)
    assert iv == 0.20 or iv is None  # warmup mode returns last-obs


@pytest.mark.unit
def test_smile_warmup_quadratic_fit():
    """With < warmup_threshold obs per strike, smile should fit quadratic across strikes."""
    fitter = SmileFitter(config=SmileConfig(warmup_threshold=100))
    # 3 strikes with measured IVs forming a U-shape.
    for _ in range(10):
        fitter.observe(strike=95, iv=0.25)
        fitter.observe(strike=100, iv=0.18)
        fitter.observe(strike=105, iv=0.25)
    # Query at a new strike, get interpolated value.
    iv = fitter.fair_iv(strike=97, spot=100, time_to_expiry=0.25)
    assert iv is not None
    assert 0.15 < iv < 0.30


@pytest.mark.unit
def test_smile_rolling_mode_after_warmup():
    """With ≥ warmup_threshold obs per strike, use EWMA rolling IV."""
    cfg = SmileConfig(warmup_threshold=10)
    fitter = SmileFitter(config=cfg)
    for _ in range(50):
        fitter.observe(strike=100, iv=0.20)
    for _ in range(50):
        fitter.observe(strike=100, iv=0.30)  # regime shift
    iv = fitter.fair_iv(strike=100, spot=100, time_to_expiry=0.25)
    # EWMA should have tracked toward 0.30, not averaged all 100 obs as 0.25.
    assert iv is not None
    assert iv > 0.22  # moved toward new regime


@pytest.mark.unit
def test_smile_snapshot_restore_roundtrip():
    cfg = SmileConfig(warmup_threshold=5)
    fitter = SmileFitter(config=cfg)
    for _ in range(20):
        fitter.observe(strike=100, iv=0.18)
        fitter.observe(strike=105, iv=0.20)
    snap = fitter.snapshot()
    restored = SmileFitter.restore(snap, cfg)
    assert restored._total_obs == fitter._total_obs
    assert set(restored._per_strike_iv.keys()) == set(fitter._per_strike_iv.keys())


@pytest.mark.unit
def test_smile_empty_returns_none():
    fitter = SmileFitter()
    assert fitter.fair_iv(strike=100, spot=100, time_to_expiry=1.0) is None


# ================================================================= conversion


@pytest.mark.unit
def test_sell_local_break_even():
    spec = ConversionSpec(transport_fee=1.0, import_tariff=2.0)
    remote = RemoteQuote(bid=95.0, ask=100.0)
    # To profit from sell-local → import: local_bid > 100 + 1 + 2 = 103
    assert sell_local_break_even(spec, remote) == 103.0


@pytest.mark.unit
def test_buy_local_break_even():
    spec = ConversionSpec(transport_fee=1.0, export_tariff=3.0)
    remote = RemoteQuote(bid=95.0, ask=100.0)
    # To profit from buy-local → export: local_ask < 95 - 1 - 3 = 91
    assert buy_local_break_even(spec, remote) == 91.0


@pytest.mark.unit
def test_arb_edge_zero_when_no_arb():
    spec = ConversionSpec()
    remote = RemoteQuote(bid=100, ask=100)
    assert arb_edge(local_bid=100, local_ask=100, spec=spec, remote=remote) == 0.0


@pytest.mark.unit
def test_arb_edge_detects_sell_local():
    spec = ConversionSpec()
    remote = RemoteQuote(bid=95, ask=100)
    # Local bid 105 > remote.ask 100 + 0 tariff ⇒ edge = 5.
    edge = arb_edge(local_bid=105, local_ask=108, spec=spec, remote=remote)
    assert edge == 5.0


@pytest.mark.unit
def test_target_batch_size_3x_cap():
    spec = ConversionSpec(conv_cap_per_tick=10)
    cfg = StockpileConfig(batch_multiplier=3.0)
    # Arb is open.
    assert target_batch_size(spec, cfg, arb_edge_per_unit=2.0, current_inventory=0) == 30


@pytest.mark.unit
def test_target_batch_size_zero_when_no_arb():
    spec = ConversionSpec(conv_cap_per_tick=10)
    cfg = StockpileConfig()
    assert target_batch_size(spec, cfg, arb_edge_per_unit=0.0, current_inventory=0) == 0


@pytest.mark.unit
def test_target_batch_size_respects_buffer_cap():
    spec = ConversionSpec(conv_cap_per_tick=10)
    cfg = StockpileConfig(batch_multiplier=3.0, max_inventory_buffer=40)
    # Already hold 30 → only room for 10 more.
    assert target_batch_size(spec, cfg, arb_edge_per_unit=2.0, current_inventory=30) == 10


@pytest.mark.unit
def test_conversion_size_capped_at_tick_limit():
    spec = ConversionSpec(conv_cap_per_tick=10)
    # Hold 50 long → convert away 10 this tick.
    assert conversion_size(spec, inventory=50) == -10
    # Hold 50 short → convert in 10 this tick.
    assert conversion_size(spec, inventory=-50) == 10
    assert conversion_size(spec, inventory=0) == 0


@pytest.mark.unit
def test_regime_detector_percentile_flags():
    d = RegimeDetector(lookback_window=20, squeeze_percentile=0.25, glut_percentile=0.75)
    for v in range(20):  # 0..19
        d.observe(float(v))
    # Value 2 is at the 10th pct ⇒ squeeze.
    assert d.regime(2.0) == "squeeze"
    # Value 17 is at the 85th pct ⇒ glut.
    assert d.regime(17.0) == "glut"
    # Value 10 is at the 50th pct ⇒ normal.
    assert d.regime(10.0) == "normal"


@pytest.mark.unit
def test_regime_detector_returns_normal_on_cold_start():
    d = RegimeDetector()
    for v in [1.0, 2.0]:
        d.observe(v)
    # Not enough data.
    assert d.regime(0.0) == "normal"


@pytest.mark.unit
def test_fill_rate_probe_converges():
    """After many trials, probe picks the offset with highest success rate."""
    import random
    probe = FillRateProbe(min_offset=-2, max_offset=2, exploration_epsilon=0.0)
    # Simulate: offset +1 fills 80% of the time; others 20%.
    for _ in range(500):
        offset = probe.pick_offset()
        filled = (offset == 1 and random.random() < 0.8) or (
            offset != 1 and random.random() < 0.2
        )
        probe.record(offset, filled=filled)
    # best_offset should be +1.
    assert probe.best_offset() == 1


@pytest.mark.unit
def test_conversion_spec_validation():
    with pytest.raises(ValueError):
        ConversionSpec(conv_cap_per_tick=0)
    with pytest.raises(ValueError):
        ConversionSpec(storage_cost=-1.0)
