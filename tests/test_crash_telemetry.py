"""Unit tests for crash telemetry + kill-switch primitive."""

from __future__ import annotations

import pytest

from src.core.primitives.crash_telemetry import (
    CrashTelemetryConfig,
    CrashTelemetryState,
    restore_telemetry,
    run_with_telemetry,
    snapshot_telemetry,
    update_heartbeat,
)


@pytest.mark.unit
def test_no_error_returns_operation_result():
    state = CrashTelemetryState()
    config = CrashTelemetryConfig()
    result, raised = run_with_telemetry(
        lambda: "ok",
        tick=0,
        product="TEST",
        state=state,
        config=config,
        default="FALLBACK",
    )
    assert result == "ok"
    assert not raised
    assert not state.recent_errors


@pytest.mark.unit
def test_error_returns_default_and_records():
    state = CrashTelemetryState()
    config = CrashTelemetryConfig()

    def operation():
        raise ValueError("bad input")

    result, raised = run_with_telemetry(
        operation,
        tick=5,
        product="TEST",
        state=state,
        config=config,
        default="FALLBACK",
    )
    assert result == "FALLBACK"
    assert raised
    assert len(state.recent_errors) == 1
    tick, product, error_class, message = state.recent_errors[0]
    assert tick == 5 and product == "TEST"
    assert error_class == "ValueError"
    assert "bad input" in message


@pytest.mark.unit
def test_kill_switch_triggers_after_threshold_errors():
    state = CrashTelemetryState()
    config = CrashTelemetryConfig(
        kill_window_ticks=100, kill_threshold=3, cooloff_ticks=500,
    )

    def bad():
        raise RuntimeError("bang")

    for tick in range(3):
        _, raised = run_with_telemetry(
            bad, tick=tick, product="T", state=state, config=config, default=None,
        )
        assert raised
    assert state.is_halted()
    # cool-off starts at 500 but tick_cooloff decrements on same call ⇒ 499.
    assert 499 <= state.cooloff_remaining <= 500


@pytest.mark.unit
def test_kill_switch_ignores_errors_outside_window():
    state = CrashTelemetryState()
    config = CrashTelemetryConfig(kill_window_ticks=10, kill_threshold=3)

    def bad():
        raise RuntimeError("x")

    # 3 errors but spread over 100 ticks — only latest ones count.
    for tick in [0, 50, 99]:
        run_with_telemetry(
            bad, tick=tick, product="T", state=state, config=config, default=None,
        )
    # At tick 99, only 1 error in last 10 ticks (windows is tick-9..tick+0).
    assert not state.is_halted()


@pytest.mark.unit
def test_cooloff_ticks_down():
    """Previously tautological: asserted only that cooloff reached 0 after
    N ticks, which would pass even if ``tick_cooloff`` zeroed the counter
    immediately. Now checks every intermediate decrement and the
    ``is_halted()`` gate.
    """
    state = CrashTelemetryState()
    state.start_cooloff(5)
    assert state.cooloff_remaining == 5
    assert state.is_halted() is True
    # Walk down one tick at a time and observe each decrement.
    expected_sequence = [4, 3, 2, 1, 0]
    for expected in expected_sequence:
        state.tick_cooloff()
        assert state.cooloff_remaining == expected, (
            f"expected cooloff={expected}, got {state.cooloff_remaining}"
        )
    # Once at 0, halted gate should clear.
    assert state.is_halted() is False
    # Further ticks must not go negative.
    state.tick_cooloff()
    assert state.cooloff_remaining == 0
    assert state.is_halted() is False


@pytest.mark.unit
def test_heartbeat_detects_hang():
    state = CrashTelemetryState()
    hang_threshold = 5
    detected = False
    for tick in range(hang_threshold):
        detected = update_heartbeat(
            tick=tick, orders_emitted=0, has_non_empty_book=True,
            state=state, hang_threshold=hang_threshold,
        )
    assert detected
    assert state.silent_streak == hang_threshold


@pytest.mark.unit
def test_heartbeat_resets_on_order():
    state = CrashTelemetryState()
    for tick in range(3):
        update_heartbeat(
            tick=tick, orders_emitted=0, has_non_empty_book=True,
            state=state, hang_threshold=100,
        )
    assert state.silent_streak == 3
    update_heartbeat(
        tick=3, orders_emitted=5, has_non_empty_book=True,
        state=state, hang_threshold=100,
    )
    assert state.silent_streak == 0
    assert state.last_successful_tick == 3


@pytest.mark.unit
def test_heartbeat_ignores_empty_book():
    state = CrashTelemetryState()
    for tick in range(10):
        update_heartbeat(
            tick=tick, orders_emitted=0, has_non_empty_book=False,
            state=state, hang_threshold=5,
        )
    assert state.silent_streak == 0  # empty book doesn't count as hang


@pytest.mark.unit
def test_snapshot_restore_roundtrip():
    state = CrashTelemetryState()
    state.recent_errors.append((1, "P", "ValueError", "msg"))
    state.cooloff_remaining = 50
    state.last_successful_tick = 100
    state.silent_streak = 3
    snap = snapshot_telemetry(state)
    restored = restore_telemetry(snap)
    assert list(restored.recent_errors) == list(state.recent_errors)
    assert restored.cooloff_remaining == 50
    assert restored.last_successful_tick == 100
    assert restored.silent_streak == 3


@pytest.mark.unit
def test_restore_handles_invalid_payload():
    assert isinstance(restore_telemetry(None), CrashTelemetryState)
    assert isinstance(restore_telemetry("not a dict"), CrashTelemetryState)  # type: ignore[arg-type]
    assert isinstance(restore_telemetry({}), CrashTelemetryState)


@pytest.mark.unit
def test_config_validation():
    with pytest.raises(ValueError):
        CrashTelemetryConfig(max_error_history=0)
    with pytest.raises(ValueError):
        CrashTelemetryConfig(kill_threshold=0)
