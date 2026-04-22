"""Hysteresis-based position sizer for spread/arb strategies.

Dave Nandi (P3 panel) called this the "leaf" sizing pattern: enter
proportional to spread width, exit asymmetrically. Symmetric entry/
exit leaves 15-25% of reversion P&L on the table because you unwind
before the signal has fully mean-reverted.

Applied to: basket z-score arb, options IV-residual arb, stat-arb
spread, lead-lag pairs. Any situation where a mean-reverting signal
drives position decisions.

Regime thresholds:

- ``|z| < entry_z``: stay flat (no signal strong enough to commit)
- ``entry_z <= |z| < kill_z``: scale position with signal strength
- ``|z| >= kill_z``: stop — likely regime break; don't commit more
- Exit: ``|z| < exit_z`` (tighter than entry; asymmetric)

The sizer returns a target POSITION (not an order). The caller converts
the delta between current and target into orders.

Pure function — no state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class HysteresisConfig:
    """Asymmetric entry/exit z-score thresholds."""

    entry_z: float = 2.0
    """Enter when |z| >= this."""

    exit_z: float = 0.3
    """Exit when |z| < this (tighter than entry — the asymmetry)."""

    kill_z: float = 4.0
    """Suspect regime break when |z| >= this; hold or reduce, don't grow."""

    max_position: int = 60
    """Maximum position magnitude this sizer will target."""

    scale_exponent: float = 1.0
    """Shape of position-vs-z curve inside (entry_z, kill_z). 1.0 = linear.
    2.0 = quadratic (more aggressive sizing at large |z|)."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.exit_z < self.entry_z < self.kill_z:
            raise ValueError(
                "thresholds must satisfy 0 <= exit_z < entry_z < kill_z "
                f"(got {self.exit_z}, {self.entry_z}, {self.kill_z})"
            )
        if self.max_position <= 0:
            raise ValueError("max_position must be > 0")
        if self.scale_exponent <= 0:
            raise ValueError("scale_exponent must be > 0")


def target_position(
    z: float,
    current_position: int,
    config: HysteresisConfig,
) -> int:
    """Compute the target position for a given signal z-score.

    Sign convention: z > 0 means signal predicts asset cheap (long).
    z < 0 means signal predicts asset rich (short).

    Hysteresis behavior:
    - Inside (|z| < exit_z): flatten if we have a position; stay flat otherwise.
    - In entry band (exit_z <= |z| < entry_z): hold whatever we have.
    - Above entry (entry_z <= |z| < kill_z): scale into position.
    - Above kill (|z| >= kill_z): hold, don't grow; may exit.
    """
    abs_z = abs(z)
    sign = 1 if z >= 0 else -1

    # Kill zone — freeze but don't grow in the signal's direction. CRITICAL fix:
    # previously "freeze" meant `return current_position`, which kept WRONG-SIGN
    # positions stuck (e.g., z=+4.1 with current=-20 returned -20, preventing
    # the unwind needed before the regime break). Now: freeze at zero or same
    # sign as signal; any opposite-sign position must at least move toward zero.
    if abs_z >= config.kill_z:
        if current_position * sign >= 0:
            # Same sign as signal (or flat) — hold.
            return current_position
        # Wrong-sign position in kill zone — unwind toward zero.
        return 0

    # Full-exit zone — flatten regardless of current position.
    if abs_z < config.exit_z:
        return 0

    # Hold zone (between exit and entry) — keep current position if we have one.
    if abs_z < config.entry_z:
        return current_position

    # Active zone — scale into position.
    # Normalized strength in [0, 1] mapped to [0, max_position].
    normalized = (abs_z - config.entry_z) / max(
        config.kill_z - config.entry_z, 1e-6
    )
    normalized = min(1.0, max(0.0, normalized))
    scaled = normalized ** config.scale_exponent
    target_abs = int(math.floor(config.max_position * scaled))
    return sign * max(1, target_abs) if target_abs > 0 else 0


def clamp_by_capacity(
    target: int,
    current: int,
    limit: int,
) -> int:
    """Clamp a target position against hard-limit on either side.

    Returns the achievable target given the position limit.
    """
    if limit <= 0:
        return 0
    return max(-limit, min(limit, target))


def sizing_metadata(
    z: float,
    current_position: int,
    target: int,
    config: HysteresisConfig,
) -> dict[str, float | int | str]:
    """Return a dict useful for logging / dashboards."""
    abs_z = abs(z)
    if abs_z < config.exit_z:
        regime = "exit"
    elif abs_z < config.entry_z:
        regime = "hold"
    elif abs_z < config.kill_z:
        regime = "active"
    else:
        regime = "kill"
    return {
        "z": round(z, 4),
        "regime": regime,
        "current": current_position,
        "target": target,
        "delta": target - current_position,
    }
