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
"""

from __future__ import annotations

import math

from src.core.config import ProductConfig
from src.core.types import (
    ExecutionMode,
    FairValueEstimate,
    NormalizedSnapshot,
    QuoteIntent,
    SignalIntent,
)


class SignalEngine:
    def build_market_making_intent(
        self,
        product: str,
        snapshot: NormalizedSnapshot,
        fair_value: FairValueEstimate,
        config: ProductConfig,
    ) -> SignalIntent:
        position_ratio = snapshot.position / config.position_limit if config.position_limit else 0.0
        skew = position_ratio * config.inventory_skew
        flattening = abs(position_ratio) >= config.flatten_threshold

        buy_below: float | None = fair_value.price - config.taker_edge - skew
        sell_above: float | None = fair_value.price + config.taker_edge - skew

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
            },
        )
