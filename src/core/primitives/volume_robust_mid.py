"""Volume-robust mid computation (fixes D2 on stable products).

F2 code archaeology found every top-team repo on stable / mean-reverting
products uses a volume-filtered mid as fair value, NOT raw mid-of-best
and NOT time-smoothed mid. This module exposes that computation as a
reusable primitive without going through the FairValueEngine protocol.

Three variants, same family:

- ``max_amount_mid``: midpoint of the largest-volume bid and ask levels
  (TimoDiehm Frankfurt Hedgehogs pattern).
- ``filtered_wall_mid``: same, but filters out levels with volume below
  a threshold (ignore penny-jumpers); pe049395 pattern.
- ``min_volume_wall_mid``: drops levels below ``min_volume`` entirely,
  then picks the top-volume survivor (carter/Alpha Animals pattern).

The primitive returns ``None`` when the book is too thin to produce a
robust mid; callers fall back to a reactive estimator (raw mid or
anchor). Pure function — no state, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.types import BookLevel, NormalizedSnapshot


@dataclass(frozen=True)
class WallMidConfig:
    """Volume-robust mid configuration."""

    min_volume: int = 10
    """Ignore levels with volume below this (penny-jumper filter)."""

    volume_ratio_threshold: float = 0.25
    """Levels with volume < ratio × side-max are filtered (alternative to min_volume)."""

    top_n_levels: int = 3
    """Consider only the top-N levels per side."""

    def __post_init__(self) -> None:
        if self.min_volume < 0:
            raise ValueError("min_volume must be >= 0")
        if not 0.0 <= self.volume_ratio_threshold <= 1.0:
            raise ValueError("volume_ratio_threshold must be in [0, 1]")
        if self.top_n_levels <= 0:
            raise ValueError("top_n_levels must be > 0")


def _pick_wall_by_min_volume(
    levels: tuple[BookLevel, ...],
    min_volume: int,
    top_n: int,
) -> BookLevel | None:
    """Max-volume level among the top-N that meet the min-volume bar."""
    if not levels:
        return None
    candidates = [l for l in levels[:top_n] if l.volume >= min_volume]
    if not candidates:
        # Fall back to best non-empty in the top-N window.
        return levels[0] if levels else None
    return max(candidates, key=lambda l: l.volume)


def _pick_wall_by_ratio(
    levels: tuple[BookLevel, ...],
    ratio: float,
    top_n: int,
) -> BookLevel | None:
    """Max-volume level that meets the ratio-of-side-max threshold."""
    window = levels[:top_n]
    if not window:
        return None
    max_vol = max(l.volume for l in window)
    if max_vol <= 0:
        return None
    threshold = max_vol * ratio
    candidates = [l for l in window if l.volume >= threshold]
    if not candidates:
        return window[0]
    # Largest volume; ties broken by closeness to touch (smallest index).
    return max(candidates, key=lambda l: (l.volume, -window.index(l)))


def max_amount_mid(
    snapshot: NormalizedSnapshot,
    config: WallMidConfig | None = None,
) -> float | None:
    """TimoDiehm / pe049395 style: midpoint of largest-volume bid & ask.

    Uses ``min_volume`` filter. Returns ``None`` if either side has no
    qualifying level. Falls back to best-level if no level meets
    ``min_volume``.
    """
    cfg = config or WallMidConfig()
    if not snapshot.bids or not snapshot.asks:
        return None
    wall_bid = _pick_wall_by_min_volume(snapshot.bids, cfg.min_volume, cfg.top_n_levels)
    wall_ask = _pick_wall_by_min_volume(snapshot.asks, cfg.min_volume, cfg.top_n_levels)
    if wall_bid is None or wall_ask is None:
        return None
    return (wall_bid.price + wall_ask.price) / 2.0


def filtered_wall_mid(
    snapshot: NormalizedSnapshot,
    config: WallMidConfig | None = None,
) -> float | None:
    """Stanford / linear_utility-style filtered wall mid.

    Uses the ratio-of-max filter (levels must have volume ≥ ratio ×
    side-max). More aggressive filtering than ``max_amount_mid``.
    """
    cfg = config or WallMidConfig()
    if not snapshot.bids or not snapshot.asks:
        return None
    wall_bid = _pick_wall_by_ratio(
        snapshot.bids, cfg.volume_ratio_threshold, cfg.top_n_levels,
    )
    wall_ask = _pick_wall_by_ratio(
        snapshot.asks, cfg.volume_ratio_threshold, cfg.top_n_levels,
    )
    if wall_bid is None or wall_ask is None:
        return None
    return (wall_bid.price + wall_ask.price) / 2.0


def walls_and_mid(
    snapshot: NormalizedSnapshot,
    config: WallMidConfig | None = None,
) -> tuple[BookLevel, BookLevel, float] | None:
    """Convenience wrapper returning (wall_bid_level, wall_ask_level, mid).

    Used by strategies that want to quote INSIDE the wall (the F2
    convergent pattern): ``bid_price = wall_bid.price + 1``,
    ``ask_price = wall_ask.price - 1``.
    """
    cfg = config or WallMidConfig()
    if not snapshot.bids or not snapshot.asks:
        return None
    wall_bid = _pick_wall_by_min_volume(snapshot.bids, cfg.min_volume, cfg.top_n_levels)
    wall_ask = _pick_wall_by_min_volume(snapshot.asks, cfg.min_volume, cfg.top_n_levels)
    if wall_bid is None or wall_ask is None:
        return None
    mid = (wall_bid.price + wall_ask.price) / 2.0
    return wall_bid, wall_ask, mid
