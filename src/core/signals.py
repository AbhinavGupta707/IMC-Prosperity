"""Translate fair value + snapshot + config into a trading intent.

This module converts "what do we believe" (the fair value estimate)
into "what would we want to do about it" (a ``SignalIntent`` naming
taker thresholds, maker prices, and the execution mode). It deliberately
does NOT emit ``Order``s — that's the execution engine's job.

Capacity recovery rule:
- When ``|position / limit| >= flatten_threshold`` the engine enters
  "recovery" mode. It stops adding to the side that already has
  exposure and tightens the opposite side toward fair value.
- In practice that means a long position disables buy intent entirely
  (maker bid size = 0 AND taker ``buy_below`` is set to ``None``) and
  pulls the maker ask in to fair value so inventory unwinds fastest.

Phase-9 early-window extensions:
- ``early_window`` gates the "early" branches by ``snapshot.timestamp``.
- When set, ``taker_edge_buy`` / ``taker_edge_sell`` split the normally
  symmetric taker threshold (useful when the day has a directional
  drift). Their ``early_*`` siblings only apply in the early window.
- ``early_short_cap`` blocks sell intent entirely while short inventory
  is at or below the cap (Family 2 — hard first-half short guard).
- ``early_short_skew_mult`` + ``early_short_flatten`` give a stricter
  recovery profile while short during the early window (Family 4).

All Phase-9 knobs default to neutral values. With defaults, this
module's output is byte-identical to the Phase-8 behavior.
"""

from __future__ import annotations

import math

from src.core.config_core import ProductConfig
from src.core.types import (
    ExecutionMode,
    FairValueEstimate,
    NormalizedSnapshot,
    QuoteIntent,
    SignalIntent,
)


def _effective_taker_edges(
    config: ProductConfig,
    *,
    in_early_window: bool,
) -> tuple[float, float]:
    """Resolve (buy_edge, sell_edge) with per-side / early overrides.

    Resolution order per side:
    1. If in the early window and the ``early_taker_edge_<side>`` is set,
       use it.
    2. Else if the full-day ``taker_edge_<side>`` is set, use it.
    3. Else fall back to the symmetric ``taker_edge``.
    """
    buy = config.taker_edge_buy if config.taker_edge_buy is not None else config.taker_edge
    sell = config.taker_edge_sell if config.taker_edge_sell is not None else config.taker_edge
    if in_early_window:
        if config.early_taker_edge_buy is not None:
            buy = config.early_taker_edge_buy
        if config.early_taker_edge_sell is not None:
            sell = config.early_taker_edge_sell
    return buy, sell


class SignalEngine:
    def build_market_making_intent(
        self,
        product: str,
        snapshot: NormalizedSnapshot,
        fair_value: FairValueEstimate,
        config: ProductConfig,
    ) -> SignalIntent:
        in_early_window = (
            config.early_window > 0 and snapshot.timestamp < config.early_window
        )
        buy_taker_edge, sell_taker_edge = _effective_taker_edges(
            config, in_early_window=in_early_window
        )

        position_ratio = snapshot.position / config.position_limit if config.position_limit else 0.0

        # Skew normally scales linearly with inventory ratio. In the
        # early window while short we can amplify (Family 4) to pull
        # back toward flat faster.
        skew_multiplier = 1.0
        if in_early_window and snapshot.position < 0 and config.early_short_skew_mult != 1.0:
            skew_multiplier = config.early_short_skew_mult
        skew = position_ratio * config.inventory_skew * skew_multiplier

        # Flatten threshold: allow a stricter short-side flatten during
        # the early window (Family 4). Long side and non-early behavior
        # are unchanged.
        effective_flatten = config.flatten_threshold
        if (
            in_early_window
            and snapshot.position < 0
            and config.early_short_flatten is not None
        ):
            effective_flatten = config.early_short_flatten
        flattening = abs(position_ratio) >= effective_flatten

        buy_below: float | None = fair_value.price - buy_taker_edge - skew
        sell_above: float | None = fair_value.price + sell_taker_edge - skew

        raw_bid = math.floor(fair_value.price - config.maker_edge - skew)
        raw_ask = math.ceil(fair_value.price + config.maker_edge - skew)

        if snapshot.best_ask is not None:
            raw_bid = min(raw_bid, snapshot.best_ask.price - config.tick_size)
        if snapshot.best_bid is not None:
            raw_ask = max(raw_ask, snapshot.best_bid.price + config.tick_size)

        bid_size = config.quote_size
        ask_size = config.quote_size
        mode: ExecutionMode = "hybrid"
        rationale = "market_make_around_fair_value"

        if flattening:
            mode = "recovery"
            rationale = "inventory_recovery"
            if snapshot.position > 0:
                # Long: stop buying entirely, pull ask toward fair value.
                bid_size = 0
                buy_below = None
                raw_ask = min(raw_ask, math.floor(fair_value.price))
            elif snapshot.position < 0:
                # Short: stop selling entirely, pull bid toward fair value.
                ask_size = 0
                sell_above = None
                raw_bid = max(raw_bid, math.ceil(fair_value.price))

        # Family 2 — early short-cap. Enforced *after* normal recovery
        # so we don't fight the recovery logic when the position is
        # already above the cap. Effect: once the net short has reached
        # the cap inside the early window, both taker-sell and maker-
        # ask are disabled until the cap is no longer breached (either
        # time passes out of the early window or inventory recovers).
        if (
            in_early_window
            and config.early_short_cap is not None
            and snapshot.position <= config.early_short_cap
        ):
            sell_above = None
            ask_size = 0
            if mode != "recovery":
                mode = "recovery"
                rationale = "early_short_cap"

        quote = QuoteIntent(
            bid_price=raw_bid if bid_size > 0 else None,
            bid_size=bid_size,
            ask_price=raw_ask if ask_size > 0 else None,
            ask_size=ask_size,
        )

        return SignalIntent(
            product=product,
            fair_value=fair_value,
            mode=mode,
            buy_below=buy_below,
            sell_above=sell_above,
            quote=quote,
            rationale=rationale,
            metadata={
                "position_ratio": round(position_ratio, 4),
                "skew": round(skew, 4),
                "flattening": flattening,
                "in_early_window": in_early_window,
            },
        )
