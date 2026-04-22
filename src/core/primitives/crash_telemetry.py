"""Crash telemetry + kill-switch primitive.

Replaces the silent-exception-swallow pattern in ``trader.run()``. When
a strategy raises:

1. **Log loudly** — stderr traceback with product + tick context so the
   error isn't hidden under an empty-orders return.

2. **Persist an error breadcrumb** — append an error summary to
   ``EngineState.errors`` deque so subsequent ticks can see the history.

3. **Fire a kill-switch** — if the error rate exceeds threshold (default
   3 errors per 100 ticks), force all strategies into ``recovery`` mode
   for a cool-off window.

4. **Expose a heartbeat** — ``last_successful_tick`` lets external
   observers detect a silent hang where the strategy returned empty
   orders without raising (the R1/R2 silent-degradation failure mode).

The primitive is designed to wrap the strategy dispatch loop, not to
replace the existing ``trader.py`` top-level safety net entirely
(Prosperity's container must not crash). Belt-and-suspenders: the
inner crash-telemetry surfaces errors; the outer safety net prevents
container kills.
"""

from __future__ import annotations

import logging
import sys
import traceback
from collections import deque
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, TypeVar

_LOG = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class CrashTelemetryConfig:
    """Crash-telemetry + kill-switch tuning."""

    enabled: bool = True

    # Error history retained in EngineState for diagnosis.
    max_error_history: int = 32

    # Kill-switch: if errors in the last N ticks exceed threshold, halt.
    kill_window_ticks: int = 100
    kill_threshold: int = 3
    """Halt all strategies if >= this many errors occur in kill_window_ticks."""

    # Cool-off: once kill-switch fires, force recovery mode for this many ticks.
    cooloff_ticks: int = 500

    # Whether to also trip on "silent" hangs (strategy returned zero orders
    # for N consecutive ticks on a non-zero book). Separate from errors.
    hang_threshold: int = 1000

    def __post_init__(self) -> None:
        if self.max_error_history <= 0:
            raise ValueError("max_error_history must be > 0")
        if self.kill_window_ticks <= 0:
            raise ValueError("kill_window_ticks must be > 0")
        if self.kill_threshold <= 0:
            raise ValueError("kill_threshold must be > 0")


@dataclass
class CrashTelemetryState:
    """Mutable state persisted across ticks (serializes into traderData).

    Separate from the static config so we can snapshot/restore it via
    the existing StateStore mechanism without breaking the frozen-config
    invariant.
    """

    # (tick, product, error_class, short_message) tuples.
    recent_errors: deque[tuple[int, str, str, str]] = field(default_factory=deque)

    # Count of ticks since last error that caused a halt; for cool-off.
    cooloff_remaining: int = 0

    # Tick number of the last tick where *any* strategy returned >= 1 order.
    last_successful_tick: int = -1

    # Count of consecutive silent ticks (zero orders on a non-empty book).
    silent_streak: int = 0

    def record_error(
        self,
        tick: int,
        product: str,
        error_class: str,
        message: str,
        max_history: int,
    ) -> None:
        self.recent_errors.append((tick, product, error_class, message[:200]))
        while len(self.recent_errors) > max_history:
            self.recent_errors.popleft()

    def errors_in_window(self, current_tick: int, window: int) -> int:
        threshold_tick = current_tick - window
        return sum(1 for t, *_ in self.recent_errors if t >= threshold_tick)

    def is_halted(self) -> bool:
        return self.cooloff_remaining > 0

    def start_cooloff(self, ticks: int) -> None:
        self.cooloff_remaining = max(self.cooloff_remaining, ticks)

    def tick_cooloff(self) -> None:
        if self.cooloff_remaining > 0:
            self.cooloff_remaining -= 1


# ============================================================= API


def run_with_telemetry(
    operation: Callable[[], T],
    *,
    tick: int,
    product: str,
    state: CrashTelemetryState,
    config: CrashTelemetryConfig,
    default: T,
) -> tuple[T, bool]:
    """Execute ``operation()``, catching errors and updating telemetry.

    Returns ``(result_or_default, raised)``. If ``raised`` is True,
    ``result_or_default`` is ``default`` (the fallback) and the error
    has been logged + persisted.

    If the kill-switch fires (threshold exceeded in window), the
    telemetry state starts a cool-off; the caller should check
    ``state.is_halted()`` on subsequent ticks to decide whether to
    suppress strategy dispatch entirely.
    """
    if not config.enabled:
        try:
            return operation(), False
        except Exception:  # noqa: BLE001 — telemetry disabled, re-raise is unsafe
            raise

    try:
        result = operation()
        state.tick_cooloff()
        return result, False
    except Exception as exc:  # noqa: BLE001 — we want every error caught
        error_class = type(exc).__name__
        message = str(exc)
        # Stderr traceback — loud, visible in container logs.
        traceback.print_exc(file=sys.stderr)
        _LOG.error(
            "crash_telemetry: tick=%d product=%s error=%s msg=%s",
            tick, product, error_class, message,
        )
        state.record_error(tick, product, error_class, message, config.max_error_history)

        # Kill-switch evaluation.
        error_count = state.errors_in_window(tick, config.kill_window_ticks)
        if error_count >= config.kill_threshold:
            _LOG.error(
                "crash_telemetry: KILL-SWITCH TRIGGERED — %d errors in last %d ticks "
                "(threshold %d); entering %d-tick cool-off",
                error_count, config.kill_window_ticks, config.kill_threshold,
                config.cooloff_ticks,
            )
            state.start_cooloff(config.cooloff_ticks)

        state.tick_cooloff()
        return default, True


def update_heartbeat(
    *,
    tick: int,
    orders_emitted: int,
    has_non_empty_book: bool,
    state: CrashTelemetryState,
    hang_threshold: int,
) -> bool:
    """Update hang-detection heartbeat. Returns True if a hang is detected.

    A "hang" is a long stretch of silent ticks (zero orders) on a
    non-empty book — the failure mode where our safety net silently
    swallows an exception every tick.
    """
    if orders_emitted > 0:
        state.last_successful_tick = tick
        state.silent_streak = 0
        return False
    if has_non_empty_book:
        state.silent_streak += 1
    if state.silent_streak >= hang_threshold:
        _LOG.error(
            "crash_telemetry: HANG DETECTED — %d consecutive silent ticks on "
            "non-empty book. last_success=%d current=%d",
            state.silent_streak, state.last_successful_tick, tick,
        )
        return True
    return False


def snapshot_telemetry(state: CrashTelemetryState) -> dict:
    """Serializable dict for inclusion in ``traderData`` or logger events."""
    return {
        "recent_errors": list(state.recent_errors),
        "cooloff_remaining": state.cooloff_remaining,
        "last_successful_tick": state.last_successful_tick,
        "silent_streak": state.silent_streak,
    }


def restore_telemetry(payload: dict | None) -> CrashTelemetryState:
    """Rehydrate state from a payload dict (e.g., pulled from traderData)."""
    state = CrashTelemetryState()
    if not isinstance(payload, dict):
        return state
    errors = payload.get("recent_errors", [])
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, (list, tuple)) and len(item) == 4:
                state.recent_errors.append(tuple(item))  # type: ignore[arg-type]
    state.cooloff_remaining = int(payload.get("cooloff_remaining", 0))
    state.last_successful_tick = int(payload.get("last_successful_tick", -1))
    state.silent_streak = int(payload.get("silent_streak", 0))
    return state
