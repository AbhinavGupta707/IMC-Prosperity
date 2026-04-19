"""PEPPER core-long + residual-overlay strategy (research-only).

This module is **not** part of the live submission bundle. It lives
under ``src/strategies/`` so it can reuse ``BaseStrategy`` /
``FairValueEngine`` / ``SignalEngine``, but it is wired in only at
runtime by the research runner in
``outputs/round_1/pepper_corelong/run_search.py``. Live configs never
reference it; ``STRATEGY_REGISTRY`` does not list it.

Core idea (see
``outputs/round_1/pepper_corelong/pepper_corelong_memo.md`` for the
full rationale):

    target_position(t) = base_long + overlay(residual(t))

where ``residual(t) = mid(t) - drift_fair(t)`` and ``overlay`` is
deliberately asymmetric:

- residual < -add_thresh → open above base_long (add_gain × excess)
- residual > +trim_thresh → trim below base_long (trim_gain × excess)
- otherwise overlay = 0

The final target is clipped to ``[floor, ceiling]`` with ``floor ≥ 0``
so the strategy never flips net short on a mild positive residual.
Adjustment toward the target is rate-limited by ``step`` units per
tick.

Params are passed via ``CoreLongParams`` on the strategy constructor —
deliberately NOT added to ``ProductConfig`` to keep the live engine
surface untouched, following the same pattern as
``src.strategies.ash_target_position``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType

from src.core.config import ProductConfig
from src.core.fair_value import FairValueEngine
from src.core.signals import SignalEngine
from src.core.types import (
    ExecutionMode,
    FairValueEstimate,
    QuoteIntent,
    Scalar,
    SignalIntent,
)
from src.strategies.base import BaseStrategy, StrategyContext

EXEC_STYLES: tuple[str, ...] = ("maker", "hybrid", "taker")
OPEN_TAKE_MODES: tuple[str, ...] = ("all_asks", "level1_only")

# Opening-phase crossing threshold: high enough to cross any ask
# inside the book, matching ``BuyAndHoldStrategy``'s _TAKE_ANY_ASK
# pattern. Without this, the opening seed would use the default
# ``fair_price - config.taker_edge`` crossing gate, which stays well
# below the best ask and produces zero opening fills.
_OPENING_TAKE_ANY_ASK: float = 1e9


@dataclass(frozen=True)
class CoreLongParams:
    """All tunable knobs for the PEPPER core-long + overlay strategy.

    Defaults correspond to a mild, centered nominal (base_long=30,
    asymmetric bands add<trim, moderate step, hybrid execution).

    Opening acquisition (v2): ``open_seed_size`` > 0 activates an
    explicit tick-0 / early-session acquisition phase that overrides
    the persistent_core + overlay target while
    ``snapshot.timestamp <= open_window``. This is the v1 gap-closer —
    v1 showed all market-making variants leave ~+19 k of first-25k PnL
    on the table because the ``linear_drift`` estimator hasn't warmed
    up enough to trigger a residual-driven buy. Setting
    ``open_seed_size=30`` with ``open_window=0`` forces a taker
    acquisition toward +30 on the first snapshot of each day
    regardless of the estimator's confidence. ``open_no_short=True``
    additionally suppresses sell quotes for the duration of the
    opening window so the bot cannot accidentally trim during the
    seed.

    Validation happens at construction time so bad candidates fail
    the runner, not mid-replay.
    """

    base_long: int = 30
    # Residual threshold magnitudes (always non-negative).
    add_thresh: float = 3.0
    trim_thresh: float = 5.0
    # Linear gains applied to the excess beyond each threshold.
    add_gain: float = 2.0
    trim_gain: float = 1.0
    # Position clipping. floor >= 0 prevents net shorts.
    floor: int = 0
    ceiling: int = 80
    # Max |position change| per tick.
    step: int = 8
    # Execution policy.
    exec_style: str = "hybrid"
    # For hybrid: only cross the spread when |residual| >= this many ticks.
    hybrid_threshold: float = 2.0
    # Maker-side edge tightening (-offset = tighter). Keep at 0 for default.
    maker_edge_offset: float = 0.0
    # ---- v2: opening acquisition ----
    # Target inventory to acquire during the opening window.
    # 0 disables the opening branch (backward compatible with v1).
    open_seed_size: int = 0
    # Opening window: while ``snapshot.timestamp <= open_window`` the
    # target is ``open_seed_size`` (clipped to ceiling) instead of
    # ``base_long + overlay``. open_window=0 means only t=0.
    open_window: int = 0
    # If True, the strategy never emits sell-side intents while in
    # the opening window — forces net-long acquisition.
    open_no_short: bool = True
    # Opening taker mode: either cross every visible ask up to
    # ``max_aggressive_size`` or only take the current best ask level.
    open_take_mode: str = "all_asks"
    # ---- v4: negative-drift protection ----
    # If > 0, fit a rolling OLS line over the most recent mids (plus
    # current mid) and cap the target at ``guard_target`` whenever the
    # fitted slope is <= -guard_negative_slope and the fit quality
    # exceeds ``guard_r2_min``.
    guard_window: int = 0
    guard_negative_slope: float = 0.0
    guard_r2_min: float = 0.0
    guard_target: int = 0
    # ---- v4: residual + imbalance micro-timer ----
    # Small, additive target bias when residual and book imbalance agree.
    micro_residual_threshold: float = 0.0
    micro_imbalance_threshold: float = 1.0
    micro_add_size: int = 0
    micro_trim_size: int = 0
    # ---- v5: adaptive long-cap tiers ----
    # Optional regime-dependent cap on maximum long inventory.
    adaptive_caps_enabled: bool = False
    adaptive_r2_min: float = 0.0
    adaptive_mid_slope: float = 0.0
    adaptive_high_slope: float = 0.0
    adaptive_low_cap: int = 0
    adaptive_mid_cap: int = 0
    adaptive_high_cap: int = 0

    # ---- Round-2 kill-switches (zero-premium tail insurance) ----
    # All four switches are no-ops at the defaults below so existing
    # Round-1 configs pick up zero behaviour change. Each switch fires
    # only on tail-event signals that the empirical PEPPER tape never
    # produced across 6 observed days, but that would matter on a real
    # regime break. A "fired" switch only pauses BUY-side execution;
    # the strategy never force-flattens. See
    # ``docs/round_2/pepper_killswitch_design.md``.
    #
    # Signal #1: rolling slope (consecutive negative snapshots).
    # When ``kill_consecutive_neg_slope_n > 0``: count snapshots whose
    # rolling-OLS slope (over ``kill_slope_window`` mids) is < 0; if
    # the run length crosses the threshold, pause buys for
    # ``kill_slope_pause_snaps`` snapshots.
    kill_slope_window: int = 50
    kill_consecutive_neg_slope_n: int = 0  # 0 disables
    kill_slope_pause_snaps: int = 0
    # Signal #2: residual-vs-drift threshold.
    # When ``kill_residual_threshold > 0`` and ``residual <
    # -kill_residual_threshold``, pause buys until residual >=
    # ``-kill_residual_release`` (release < threshold so we don't
    # flap).
    kill_residual_threshold: float = 0.0  # 0 disables
    kill_residual_release: float = 0.0
    # Signal #3: single-snapshot Δmid spike.
    # When ``kill_step_move_threshold > 0`` and the current mid drops
    # by more than ``kill_step_move_threshold`` vs the previous
    # observed mid, pause buys for ``kill_step_move_pause_snaps``
    # snapshots.
    kill_step_move_threshold: float = 0.0  # 0 disables
    kill_step_move_pause_snaps: int = 0
    # Signal #4: intraday MTM kill (sticky for the rest of the day).
    # Approximated as ``position * (current_mid - day_open_mid)``;
    # when this drops below ``-kill_intraday_pnl_threshold``, the
    # strategy halts BOTH sides for the remainder of the day. Reset
    # at the next day-rollover (detected via timestamp reset).
    kill_intraday_pnl_threshold: float = 0.0  # 0 disables

    def __post_init__(self) -> None:
        if self.base_long < 0:
            raise ValueError(f"base_long must be >= 0 (got {self.base_long})")
        if self.add_thresh < 0:
            raise ValueError(f"add_thresh must be >= 0 (got {self.add_thresh})")
        if self.trim_thresh < 0:
            raise ValueError(f"trim_thresh must be >= 0 (got {self.trim_thresh})")
        if self.add_gain < 0:
            raise ValueError(f"add_gain must be >= 0 (got {self.add_gain})")
        if self.trim_gain < 0:
            raise ValueError(f"trim_gain must be >= 0 (got {self.trim_gain})")
        if self.floor < 0:
            raise ValueError(f"floor must be >= 0 (got {self.floor})")
        if self.ceiling < self.floor:
            raise ValueError(
                f"ceiling must be >= floor (got floor={self.floor}, "
                f"ceiling={self.ceiling})"
            )
        if self.step <= 0:
            raise ValueError(f"step must be > 0 (got {self.step})")
        if self.exec_style not in EXEC_STYLES:
            raise ValueError(
                f"exec_style must be one of {EXEC_STYLES!r} (got {self.exec_style!r})"
            )
        if self.hybrid_threshold < 0:
            raise ValueError(
                f"hybrid_threshold must be >= 0 (got {self.hybrid_threshold})"
            )
        if self.open_seed_size < 0:
            raise ValueError(
                f"open_seed_size must be >= 0 (got {self.open_seed_size})"
            )
        if self.open_seed_size > self.ceiling:
            raise ValueError(
                f"open_seed_size ({self.open_seed_size}) must be <= "
                f"ceiling ({self.ceiling})"
            )
        if self.open_window < 0:
            raise ValueError(f"open_window must be >= 0 (got {self.open_window})")
        if self.open_take_mode not in OPEN_TAKE_MODES:
            raise ValueError(
                f"open_take_mode must be one of {OPEN_TAKE_MODES!r} "
                f"(got {self.open_take_mode!r})"
            )
        if self.guard_window < 0:
            raise ValueError(f"guard_window must be >= 0 (got {self.guard_window})")
        if self.guard_negative_slope < 0:
            raise ValueError(
                "guard_negative_slope must be >= 0 "
                f"(got {self.guard_negative_slope})"
            )
        if not 0.0 <= self.guard_r2_min <= 1.0:
            raise ValueError(
                f"guard_r2_min must be in [0, 1] (got {self.guard_r2_min})"
            )
        guard_enabled = (
            self.guard_window > 0
            or self.guard_negative_slope > 0
            or self.guard_r2_min > 0
        )
        if guard_enabled and not self.floor <= self.guard_target <= self.ceiling:
            raise ValueError(
                "guard_target must lie inside [floor, ceiling] "
                f"(got floor={self.floor}, guard_target={self.guard_target}, "
                f"ceiling={self.ceiling})"
            )
        if self.micro_residual_threshold < 0:
            raise ValueError(
                "micro_residual_threshold must be >= 0 "
                f"(got {self.micro_residual_threshold})"
            )
        if not 0.0 <= self.micro_imbalance_threshold <= 1.0:
            raise ValueError(
                "micro_imbalance_threshold must be in [0, 1] "
                f"(got {self.micro_imbalance_threshold})"
            )
        if self.micro_add_size < 0:
            raise ValueError(
                f"micro_add_size must be >= 0 (got {self.micro_add_size})"
            )
        if self.micro_trim_size < 0:
            raise ValueError(
                f"micro_trim_size must be >= 0 (got {self.micro_trim_size})"
            )
        if not 0.0 <= self.adaptive_r2_min <= 1.0:
            raise ValueError(
                f"adaptive_r2_min must be in [0, 1] (got {self.adaptive_r2_min})"
            )
        if self.adaptive_mid_slope < 0:
            raise ValueError(
                f"adaptive_mid_slope must be >= 0 (got {self.adaptive_mid_slope})"
            )
        if self.adaptive_high_slope < 0:
            raise ValueError(
                f"adaptive_high_slope must be >= 0 (got {self.adaptive_high_slope})"
            )
        if self.adaptive_high_slope < self.adaptive_mid_slope:
            raise ValueError(
                "adaptive_high_slope must be >= adaptive_mid_slope "
                f"(got mid={self.adaptive_mid_slope}, high={self.adaptive_high_slope})"
            )
        adaptive_caps = (
            self.adaptive_low_cap,
            self.adaptive_mid_cap,
            self.adaptive_high_cap,
        )
        if any(cap < 0 for cap in adaptive_caps):
            raise ValueError(
                "adaptive_*_cap must be >= 0 "
                f"(got low={self.adaptive_low_cap}, mid={self.adaptive_mid_cap}, "
                f"high={self.adaptive_high_cap})"
            )
        if self.adaptive_caps_enabled:
            if self.guard_window <= 0:
                raise ValueError(
                    "adaptive_caps_enabled requires guard_window > 0 "
                    f"(got {self.guard_window})"
                )
            if not self.floor <= self.adaptive_low_cap <= self.adaptive_mid_cap <= self.adaptive_high_cap:
                raise ValueError(
                    "adaptive caps must be ordered inside [floor, ceiling] "
                    f"(got floor={self.floor}, low={self.adaptive_low_cap}, "
                    f"mid={self.adaptive_mid_cap}, high={self.adaptive_high_cap}, "
                    f"ceiling={self.ceiling})"
                )
            if self.adaptive_high_cap > self.ceiling:
                raise ValueError(
                    "adaptive_high_cap must be <= ceiling "
                    f"(got high={self.adaptive_high_cap}, ceiling={self.ceiling})"
                )

        # ---- Round-2 kill-switch validation ----
        if self.kill_slope_window < 0:
            raise ValueError(
                f"kill_slope_window must be >= 0 (got {self.kill_slope_window})"
            )
        if self.kill_consecutive_neg_slope_n < 0:
            raise ValueError(
                "kill_consecutive_neg_slope_n must be >= 0 "
                f"(got {self.kill_consecutive_neg_slope_n})"
            )
        if self.kill_slope_pause_snaps < 0:
            raise ValueError(
                f"kill_slope_pause_snaps must be >= 0 (got {self.kill_slope_pause_snaps})"
            )
        slope_kill_enabled = self.kill_consecutive_neg_slope_n > 0
        if slope_kill_enabled:
            if self.kill_slope_window < 2:
                raise ValueError(
                    "kill_slope_window must be >= 2 when the consecutive-slope "
                    f"kill switch is enabled (got {self.kill_slope_window})"
                )
            if self.kill_slope_pause_snaps == 0:
                raise ValueError(
                    "kill_slope_pause_snaps must be > 0 when the "
                    "consecutive-slope kill switch is enabled"
                )
        if self.kill_residual_threshold < 0:
            raise ValueError(
                "kill_residual_threshold must be >= 0 "
                f"(got {self.kill_residual_threshold})"
            )
        if self.kill_residual_release < 0:
            raise ValueError(
                "kill_residual_release must be >= 0 "
                f"(got {self.kill_residual_release})"
            )
        if self.kill_residual_threshold > 0:
            # Release must lie strictly INSIDE the trigger band so we
            # don't flap: release < threshold (hysteresis), release
            # can be 0 to mean "release as soon as residual returns
            # to the drift line or above".
            if self.kill_residual_release >= self.kill_residual_threshold:
                raise ValueError(
                    "kill_residual_release must be < kill_residual_threshold "
                    f"(got threshold={self.kill_residual_threshold}, "
                    f"release={self.kill_residual_release})"
                )
        if self.kill_step_move_threshold < 0:
            raise ValueError(
                "kill_step_move_threshold must be >= 0 "
                f"(got {self.kill_step_move_threshold})"
            )
        if self.kill_step_move_pause_snaps < 0:
            raise ValueError(
                "kill_step_move_pause_snaps must be >= 0 "
                f"(got {self.kill_step_move_pause_snaps})"
            )
        if self.kill_step_move_threshold > 0 and self.kill_step_move_pause_snaps == 0:
            raise ValueError(
                "kill_step_move_pause_snaps must be > 0 when "
                "kill_step_move_threshold is enabled"
            )
        if self.kill_intraday_pnl_threshold < 0:
            raise ValueError(
                "kill_intraday_pnl_threshold must be >= 0 "
                f"(got {self.kill_intraday_pnl_threshold})"
            )


def _ols_fit_recent_mids(
    history: list[float],
    current_mid: float | None,
    *,
    window: int,
) -> tuple[float, float, int] | None:
    """Return (slope, r2, sample_count) for recent mids, or None."""
    if window <= 0:
        return None
    ys = list(history[-window:])
    if current_mid is not None:
        ys.append(float(current_mid))
    n = len(ys)
    if n < 3:
        return None

    xs = list(range(n))
    mean_x = (n - 1) / 2.0
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x <= 0:
        return None

    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = cov_xy / var_x
    intercept = mean_y - slope * mean_x
    fit = [slope * x + intercept for x in xs]
    ss_res = sum((y - yhat) ** 2 for y, yhat in zip(ys, fit, strict=True))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot <= 0:
        r2 = 1.0
    else:
        r2 = max(0.0, 1.0 - (ss_res / ss_tot))
    return float(slope), float(r2), n


def _micro_target_bias(
    residual: float,
    imbalance: float | None,
    *,
    residual_threshold: float,
    imbalance_threshold: float,
    add_size: int,
    trim_size: int,
) -> int:
    """Small additive target nudge when residual and imbalance agree."""
    if imbalance is None:
        return 0
    if residual <= -residual_threshold and imbalance >= imbalance_threshold:
        return add_size
    if residual >= residual_threshold and imbalance <= -imbalance_threshold:
        return -trim_size
    return 0


def _adaptive_long_cap(
    *,
    enabled: bool,
    static_ceiling: int,
    slope: float | None,
    r2: float | None,
    r2_min: float,
    mid_slope: float,
    high_slope: float,
    low_cap: int,
    mid_cap: int,
    high_cap: int,
) -> tuple[int, str]:
    """Return (effective_long_cap, regime_band)."""
    if not enabled:
        return static_ceiling, "disabled"
    if slope is None or r2 is None:
        return static_ceiling, "unavailable"
    if r2 < r2_min:
        return static_ceiling, "low_confidence"
    if slope >= high_slope:
        return min(static_ceiling, high_cap), "high"
    if slope >= mid_slope:
        return min(static_ceiling, mid_cap), "mid"
    return min(static_ceiling, low_cap), "low"


# ---- Round-2 kill-switch state keys on ProductMemory ----
# All kill-switch state lives under these well-known keys so a
# strategy rewrite can clean them up without grepping. Counters are
# integers; flags are 0/1 integers (ProductMemory.flags stores
# booleans, but we keep counts on counters for symmetry). Values are
# floats for mid references.
_KS_SEEN_TS_HIGH = "kill_seen_ts_high"  # high-watermark timestamp
_KS_CONSEC_NEG_SLOPE = "kill_consec_neg_slope"
_KS_SLOPE_PAUSE_LEFT = "kill_slope_pause_left"
_KS_RESIDUAL_ACTIVE = "kill_residual_active"  # 0/1 latch (hysteresis)
_KS_STEP_PAUSE_LEFT = "kill_step_pause_left"
_KS_INTRADAY_HALT = "kill_intraday_halt"  # 0/1, sticky per day
_KSV_DAY_OPEN_MID = "kill_day_open_mid"
_KSV_LAST_MID = "kill_last_mid"


@dataclass(frozen=True)
class KillSwitchDecision:
    """Result of evaluating all four Round-2 kill switches.

    ``buy_paused`` nullifies BUY-side intents for the current step.
    ``all_paused`` nullifies BOTH sides for the current step and is
    sticky for the day (intraday-PnL kill). ``reasons`` is a tuple of
    short tags for diagnostic metadata (order of firing, deduped).
    """

    buy_paused: bool
    all_paused: bool
    reasons: tuple[str, ...]


def _reset_kill_switch_day_state(memory_counters: dict[str, int], memory_values: dict[str, float]) -> None:
    for key in (
        _KS_CONSEC_NEG_SLOPE,
        _KS_SLOPE_PAUSE_LEFT,
        _KS_RESIDUAL_ACTIVE,
        _KS_STEP_PAUSE_LEFT,
        _KS_INTRADAY_HALT,
    ):
        memory_counters.pop(key, None)
    for key in (_KSV_DAY_OPEN_MID, _KSV_LAST_MID):
        memory_values.pop(key, None)


def evaluate_kill_switches(
    *,
    params: CoreLongParams,
    snapshot_timestamp: int,
    current_mid: float | None,
    position: int,
    slope: float | None,
    residual: float | None,
    memory_counters: dict[str, int],
    memory_values: dict[str, float],
) -> KillSwitchDecision:
    """Update kill-switch state and return the firing decision.

    This helper is deliberately side-effectful on ``memory_counters``
    / ``memory_values`` — the latches and countdowns MUST persist
    across snapshots. It is pure otherwise (no I/O, no globals).
    """
    reasons: list[str] = []
    buy_paused = False
    all_paused = False

    # --- Day-rollover reset ---
    seen_high = memory_counters.get(_KS_SEEN_TS_HIGH)
    if seen_high is not None and snapshot_timestamp < seen_high:
        _reset_kill_switch_day_state(memory_counters, memory_values)
    memory_counters[_KS_SEEN_TS_HIGH] = max(
        int(snapshot_timestamp), int(seen_high) if seen_high is not None else 0
    )

    if current_mid is None:
        # No observation this step → leave state alone, report no firing.
        return KillSwitchDecision(False, False, tuple())

    # --- Anchor the day's opening mid (first real observation per day) ---
    if _KSV_DAY_OPEN_MID not in memory_values:
        memory_values[_KSV_DAY_OPEN_MID] = float(current_mid)

    # --- Signal #4: sticky intraday PnL halt ---
    if memory_counters.get(_KS_INTRADAY_HALT, 0):
        # Already halted for the day.
        return KillSwitchDecision(False, True, ("intraday_pnl_halt",))
    if params.kill_intraday_pnl_threshold > 0:
        day_open = memory_values.get(_KSV_DAY_OPEN_MID)
        if day_open is not None:
            intraday_mtm = float(position) * (float(current_mid) - float(day_open))
            if intraday_mtm <= -float(params.kill_intraday_pnl_threshold):
                memory_counters[_KS_INTRADAY_HALT] = 1
                return KillSwitchDecision(
                    False, True, ("intraday_pnl_halt",)
                )

    # --- Signal #1: rolling-slope consecutive-negative counter ---
    if params.kill_consecutive_neg_slope_n > 0:
        pause_left = memory_counters.get(_KS_SLOPE_PAUSE_LEFT, 0)
        if pause_left > 0:
            buy_paused = True
            reasons.append("slope_pause")
            memory_counters[_KS_SLOPE_PAUSE_LEFT] = pause_left - 1
        else:
            consec = memory_counters.get(_KS_CONSEC_NEG_SLOPE, 0)
            if slope is not None and slope < 0:
                consec += 1
            else:
                consec = 0
            if consec >= params.kill_consecutive_neg_slope_n:
                # Firing snap is snap #1 of the pause window; remaining
                # countdown is pause_snaps - 1 (clamped, so pause=1
                # means "pause only this firing snap").
                memory_counters[_KS_SLOPE_PAUSE_LEFT] = max(
                    0, int(params.kill_slope_pause_snaps) - 1
                )
                memory_counters[_KS_CONSEC_NEG_SLOPE] = 0
                buy_paused = True
                reasons.append("slope_fire")
            else:
                memory_counters[_KS_CONSEC_NEG_SLOPE] = consec

    # --- Signal #2: residual-vs-drift latch (hysteresis) ---
    if params.kill_residual_threshold > 0 and residual is not None:
        active = memory_counters.get(_KS_RESIDUAL_ACTIVE, 0)
        if active:
            # Released when residual climbs back above -release.
            if residual >= -float(params.kill_residual_release):
                memory_counters[_KS_RESIDUAL_ACTIVE] = 0
            else:
                buy_paused = True
                reasons.append("residual_pause")
        else:
            if residual <= -float(params.kill_residual_threshold):
                memory_counters[_KS_RESIDUAL_ACTIVE] = 1
                buy_paused = True
                reasons.append("residual_fire")

    # --- Signal #3: single-step Δmid spike (countdown) ---
    if params.kill_step_move_threshold > 0:
        step_left = memory_counters.get(_KS_STEP_PAUSE_LEFT, 0)
        last_mid = memory_values.get(_KSV_LAST_MID)
        fired_this_snap = False
        if last_mid is not None:
            delta = float(current_mid) - float(last_mid)
            if delta <= -float(params.kill_step_move_threshold):
                # Firing snap is #1 of the pause window; remaining
                # countdown is pause_snaps - 1 (clamped).
                step_left = max(0, int(params.kill_step_move_pause_snaps) - 1)
                reasons.append("step_move_fire")
                buy_paused = True
                fired_this_snap = True
                memory_counters[_KS_STEP_PAUSE_LEFT] = step_left
        if not fired_this_snap:
            if step_left > 0:
                buy_paused = True
                reasons.append("step_pause")
                memory_counters[_KS_STEP_PAUSE_LEFT] = step_left - 1

    # Record current mid as the reference for next step's Δmid check.
    memory_values[_KSV_LAST_MID] = float(current_mid)

    return KillSwitchDecision(buy_paused=buy_paused, all_paused=all_paused, reasons=tuple(reasons))


def compute_target_position(
    residual: float,
    *,
    base_long: int,
    add_thresh: float,
    trim_thresh: float,
    add_gain: float,
    trim_gain: float,
    floor: int,
    ceiling: int,
) -> int:
    """Return the signed integer target position for a given residual.

    ``residual = price - drift_fair``. Negative residual (price below
    fair) → target ABOVE base_long. Positive residual → target BELOW
    base_long, clipped at ``floor``.
    """
    if residual < -add_thresh:
        excess = -residual - add_thresh  # > 0
        overlay = add_gain * excess
    elif residual > trim_thresh:
        excess = residual - trim_thresh  # > 0
        overlay = -trim_gain * excess
    else:
        overlay = 0.0

    target = base_long + overlay
    if target < floor:
        target = floor
    elif target > ceiling:
        target = ceiling
    return int(round(target))


def _maker_prices(
    fair_value: float,
    config: ProductConfig,
    snapshot_best_bid_price: int | None,
    snapshot_best_ask_price: int | None,
    maker_edge_offset: float,
) -> tuple[int, int]:
    """Resolve (bid, ask) maker prices: fair ± maker_edge, pulled inside the book."""
    maker_edge = max(0.0, config.maker_edge + maker_edge_offset)
    raw_bid = math.floor(fair_value - maker_edge)
    raw_ask = math.ceil(fair_value + maker_edge)
    if snapshot_best_ask_price is not None:
        raw_bid = min(raw_bid, snapshot_best_ask_price - config.tick_size)
    if snapshot_best_bid_price is not None:
        raw_ask = max(raw_ask, snapshot_best_bid_price + config.tick_size)
    return raw_bid, raw_ask


class PepperCoreLongStrategy(BaseStrategy):
    """Core-long + asymmetric residual-overlay strategy for PEPPER."""

    def __init__(
        self,
        fair_value_engine: FairValueEngine,
        signal_engine: SignalEngine,
        params: CoreLongParams,
    ) -> None:
        self.fair_value_engine = fair_value_engine
        self.signal_engine = signal_engine
        self.params = params

    def generate_intent(self, context: StrategyContext) -> SignalIntent:
        product = context.product
        snapshot = context.snapshot
        config = context.config
        params = self.params

        fair_value: FairValueEstimate = self.fair_value_engine.estimate(
            product, snapshot, context.memory, config
        )
        fair_price = float(fair_value.price)

        # Effective ceiling never exceeds the hard position limit.
        static_ceiling = min(params.ceiling, config.position_limit)

        price: float
        if snapshot.mid is not None:
            price = float(snapshot.mid)
        else:
            price = fair_price
        residual = price - fair_price
        imbalance = snapshot.book_imbalance

        drift_fit = _ols_fit_recent_mids(
            context.memory.recent_mids,
            snapshot.mid,
            window=params.guard_window,
        )
        guard_active = False
        guard_slope: float | None = None
        guard_r2: float | None = None
        guard_samples = 0
        if drift_fit is not None:
            guard_slope, guard_r2, guard_samples = drift_fit
            guard_active = (
                params.guard_window > 0
                and guard_slope <= -params.guard_negative_slope
                and guard_r2 >= params.guard_r2_min
            )
        adaptive_ceiling, adaptive_band = _adaptive_long_cap(
            enabled=params.adaptive_caps_enabled,
            static_ceiling=static_ceiling,
            slope=guard_slope,
            r2=guard_r2,
            r2_min=params.adaptive_r2_min,
            mid_slope=params.adaptive_mid_slope,
            high_slope=params.adaptive_high_slope,
            low_cap=params.adaptive_low_cap,
            mid_cap=params.adaptive_mid_cap,
            high_cap=params.adaptive_high_cap,
        )
        effective_ceiling = adaptive_ceiling

        # ---- Opening acquisition phase (v2) ----
        # snapshot.timestamp resets at the start of every simulated
        # day, so this branch fires once per day. On the local
        # multi-day replay the opening fires on each day; on the
        # official single-day environment it fires once.
        in_opening = (
            params.open_seed_size > 0 and snapshot.timestamp <= params.open_window
        )
        if in_opening:
            raw_target = min(params.open_seed_size, effective_ceiling)
        else:
            raw_target = compute_target_position(
                residual,
                base_long=params.base_long,
                add_thresh=params.add_thresh,
                trim_thresh=params.trim_thresh,
                add_gain=params.add_gain,
                trim_gain=params.trim_gain,
                floor=params.floor,
                ceiling=effective_ceiling,
            )
            micro_bias = _micro_target_bias(
                residual,
                imbalance,
                residual_threshold=params.micro_residual_threshold,
                imbalance_threshold=params.micro_imbalance_threshold,
                add_size=params.micro_add_size,
                trim_size=params.micro_trim_size,
            )
            raw_target += micro_bias
            raw_target = max(params.floor, min(effective_ceiling, raw_target))
        if in_opening:
            micro_bias = 0

        if guard_active:
            raw_target = min(raw_target, params.guard_target)

        # ---- Round-2 kill-switch evaluation ----
        # Uses the guard_window OLS slope as the signal for the
        # rolling-slope check when that window is available; falls back
        # to a dedicated ``kill_slope_window`` fit otherwise so the
        # kill switch can run without the guard_* machinery enabled.
        kill_slope = guard_slope
        if kill_slope is None and params.kill_consecutive_neg_slope_n > 0:
            kill_fit = _ols_fit_recent_mids(
                context.memory.recent_mids,
                snapshot.mid,
                window=params.kill_slope_window,
            )
            if kill_fit is not None:
                kill_slope = kill_fit[0]

        kill_decision = evaluate_kill_switches(
            params=params,
            snapshot_timestamp=snapshot.timestamp,
            current_mid=snapshot.mid,
            position=snapshot.position,
            slope=kill_slope,
            residual=residual,
            memory_counters=context.memory.counters,
            memory_values=context.memory.values,
        )

        # Step-rate-limit the adjustment toward the target.
        raw_gap = raw_target - snapshot.position
        step_clipped_gap = max(-params.step, min(params.step, raw_gap))
        effective_target = snapshot.position + step_clipped_gap
        # Never cross the hard floor/ceiling after the step.
        effective_target = max(params.floor, min(effective_ceiling, effective_target))
        effective_gap = effective_target - snapshot.position

        # ---- Execution eligibility ----
        # Opening phase forces taker to acquire quickly regardless of
        # exec_style / residual magnitude. This is the entire point of
        # the opening seed — acquire at tick 0 without waiting for the
        # drift estimator to warm up.
        taker_eligible = (
            in_opening
            or params.exec_style == "taker"
            or (
                params.exec_style == "hybrid"
                and abs(residual) >= params.hybrid_threshold
            )
        )
        maker_eligible = params.exec_style in ("maker", "hybrid")

        # ---- Taker thresholds ----
        # For a drift asset we cross at `drift_fair ± taker_edge` so the
        # crossing price is anchored to the drift line, not the raw mid.
        # EXCEPTION: during the opening phase we cross aggressively
        # (any ask inside the book) so the seed fills immediately —
        # this is the entire point of the opening knob. Without this
        # exception the default threshold sits ~config.taker_edge
        # below fair while the best ask typically sits ~half-spread
        # above fair, so zero opening fills occur.
        buy_below: float | None = None
        sell_above: float | None = None
        if taker_eligible:
            if effective_gap > 0:
                if in_opening:
                    if (
                        params.open_take_mode == "level1_only"
                        and snapshot.best_ask is not None
                    ):
                        buy_below = float(snapshot.best_ask.price)
                    else:
                        buy_below = _OPENING_TAKE_ANY_ASK
                else:
                    buy_below = fair_price - config.taker_edge
            elif effective_gap < 0:
                # Sells during opening are gated separately below by
                # ``open_no_short``; if overlaid trim still qualifies
                # here (i.e. open_no_short=False), use the normal
                # drift-anchored crossing threshold.
                sell_above = fair_price + config.taker_edge

        # ---- Maker quotes ----
        bid_price: int | None = None
        ask_price: int | None = None
        bid_size = 0
        ask_size = 0

        if maker_eligible:
            raw_bid, raw_ask = _maker_prices(
                fair_value=fair_price,
                config=config,
                snapshot_best_bid_price=(
                    snapshot.best_bid.price if snapshot.best_bid else None
                ),
                snapshot_best_ask_price=(
                    snapshot.best_ask.price if snapshot.best_ask else None
                ),
                maker_edge_offset=params.maker_edge_offset,
            )
            if effective_gap > 0:
                bid_price = raw_bid
                bid_size = min(max(1, effective_gap), config.quote_size or params.step)
            elif effective_gap < 0:
                ask_price = raw_ask
                ask_size = min(max(1, -effective_gap), config.quote_size or params.step)
            else:
                # At target: harvest residual oscillation with small
                # symmetric maker quotes, but only up to remaining
                # capacity on each side.
                buy_capacity = effective_ceiling - snapshot.position
                sell_capacity = snapshot.position - params.floor
                small_size = max(1, (config.quote_size or params.step) // 2)
                if buy_capacity > 0:
                    bid_price = raw_bid
                    bid_size = min(small_size, buy_capacity)
                if sell_capacity > 0:
                    ask_price = raw_ask
                    ask_size = min(small_size, sell_capacity)

        # ---- Hard floor/ceiling gate on the emitted sides ----
        # Never emit buys when at or above the ceiling.
        if snapshot.position >= effective_ceiling:
            buy_below = None
            bid_size = 0
            bid_price = None
        # Never emit sells when at or below the floor.
        if snapshot.position <= params.floor:
            sell_above = None
            ask_size = 0
            ask_price = None

        # ---- Opening-phase sell suppression (v2) ----
        # If ``open_no_short`` is True during the opening window, the
        # strategy must not emit any sell-side intent even if the
        # residual overlay thinks we should trim. This protects the
        # seed from being drained by a transient positive residual
        # while the drift estimator is still warming up.
        if in_opening and params.open_no_short:
            sell_above = None
            ask_size = 0
            ask_price = None

        # ---- Round-2 kill-switch gating ----
        # Four kill switches can independently pause or halt trading.
        # They NEVER force-flatten an existing position; they only
        # suppress new BUY intents (or both sides for intraday-PnL).
        # See ``evaluate_kill_switches`` for firing rules.
        if kill_decision.all_paused:
            buy_below = None
            sell_above = None
            bid_size = 0
            ask_size = 0
            bid_price = None
            ask_price = None
        elif kill_decision.buy_paused:
            buy_below = None
            bid_size = 0
            bid_price = None

        mode: ExecutionMode = "hybrid"
        rationale = "pepper_core_long"

        quote = QuoteIntent(
            bid_price=bid_price if bid_size > 0 else None,
            bid_size=bid_size,
            ask_price=ask_price if ask_size > 0 else None,
            ask_size=ask_size,
        )
        metadata: dict[str, Scalar] = {
            "base_long": params.base_long,
            "residual": round(residual, 4),
            "fair_value": round(fair_price, 4),
            "target_position": raw_target,
            "effective_target": effective_target,
            "position_gap": effective_gap,
            "taker_eligible": taker_eligible,
            "exec_style": params.exec_style,
            "floor": params.floor,
            "ceiling": effective_ceiling,
            "static_ceiling": static_ceiling,
            "in_opening": in_opening,
            "open_seed_size": params.open_seed_size,
            "open_window": params.open_window,
            "open_take_mode": params.open_take_mode,
            "imbalance": round(imbalance, 4) if imbalance is not None else "none",
            "micro_bias": micro_bias,
            "guard_active": guard_active,
            "guard_target": params.guard_target,
            "guard_window": params.guard_window,
            "guard_slope": round(guard_slope, 6) if guard_slope is not None else "none",
            "guard_r2": round(guard_r2, 4) if guard_r2 is not None else "none",
            "guard_samples": guard_samples,
            "adaptive_caps_enabled": params.adaptive_caps_enabled,
            "adaptive_band": adaptive_band,
            "adaptive_ceiling": adaptive_ceiling,
            "kill_buy_paused": kill_decision.buy_paused,
            "kill_all_paused": kill_decision.all_paused,
            "kill_reasons": ",".join(kill_decision.reasons) if kill_decision.reasons else "",
        }
        return SignalIntent(
            product=product,
            fair_value=fair_value,
            mode=mode,
            buy_below=buy_below,
            sell_above=sell_above,
            quote=quote,
            rationale=rationale,
            metadata=MappingProxyType(metadata),
        )
