"""Cross-exchange conversion layer (fixes D7 for stat-arb products).

Handles IMC Prosperity-style cross-exchange arbitrage (P2 Orchids, P3
Macarons). The core abstraction: a local tradable book + a remote
"conversion" exchange with its own best-bid / best-ask, import / export
tariffs, transport cost, per-unit storage cost.

The arb is a two-legged lock:

    sell locally at price P_L if:  P_L > conversion_ask + import_tariff + transport

    buy locally at price P_L if:   P_L < conversion_bid - export_tariff - transport

and then convert the position at the remote exchange.

Key findings from R1/R2 and P3 top-team archaeology:

- **Signed break-even** handles negative tariffs (subsidies) — the
  Macaron edge.
- **Batched conversions (3× cap)** handle the per-tick conversion
  limit: stockpile during high-fill windows so conversions can happen
  continuously even when the bot is absent. Both P3 top-2 teams missed
  this and left ~2× P&L on the table (transcript-1).
- **External signal = regime flag**, not linear regressor. Percentile
  over rolling window: <25th = squeeze (buy-and-hold), >75th = glut
  (sell aggressively), middle = normal arb.
- **Fill-rate probe**: for hidden-taker bots, the fill probability
  depends on the exact price-offset to mid. Thompson bandit
  auto-calibrates the best offset.

Pure-function building blocks plus one stateful ``ConversionLayer``
that tracks inventory across ticks (for stockpile batching).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

TariffSide = Literal["import", "export"]


@dataclass(frozen=True)
class ConversionSpec:
    """Static tariff / transport parameters for one cross-exchange product."""

    transport_fee: float = 0.0
    """Per-unit transport cost, applied on every conversion (both directions)."""

    import_tariff: float = 0.0
    """Added to cost when buying remote + importing. NEGATIVE = subsidy."""

    export_tariff: float = 0.0
    """Added to cost when selling locally + exporting. NEGATIVE = subsidy."""

    storage_cost: float = 0.0
    """Per-unit-per-tick cost of holding inventory (long or short)."""

    conv_cap_per_tick: int = 10
    """Maximum units that can be converted per tick (IMC limit)."""

    def __post_init__(self) -> None:
        if self.conv_cap_per_tick <= 0:
            raise ValueError("conv_cap_per_tick must be > 0")
        if self.storage_cost < 0:
            raise ValueError("storage_cost must be >= 0")


@dataclass(frozen=True)
class RemoteQuote:
    """Best-bid / best-ask on the conversion exchange, per tick."""

    bid: float
    """Remote bid — we sell INTO this (import direction: ours → remote)."""

    ask: float
    """Remote ask — we buy FROM this (export direction: remote → ours).

    Naming follows "what does it cost US" convention. Some IMC docs use
    the opposite sign; this module keeps the convention explicit.
    """


# ============================================================= break-even


def sell_local_break_even(spec: ConversionSpec, remote: RemoteQuote) -> float:
    """Minimum LOCAL BID we'd need in order to profitably sell local + buy remote.

    We want: local_bid_price  >  sell_local_break_even.
    If the condition holds, we sell locally and immediately buy remote
    to flatten, locking in the difference.
    """
    # We sell locally at price P_L, then buy remote at remote.ask,
    # paying transport + import_tariff. Profit per unit = P_L - remote.ask - transport - import_tariff.
    # Break-even when profit = 0 ⇒ P_L = remote.ask + transport + import_tariff.
    return remote.ask + spec.transport_fee + spec.import_tariff


def buy_local_break_even(spec: ConversionSpec, remote: RemoteQuote) -> float:
    """Maximum LOCAL ASK at which we'd profitably buy local + sell remote.

    We want: local_ask_price  <  buy_local_break_even.
    """
    return remote.bid - spec.transport_fee - spec.export_tariff


def arb_edge(
    *,
    local_bid: float | None,
    local_ask: float | None,
    spec: ConversionSpec,
    remote: RemoteQuote,
) -> float:
    """Per-unit arb edge at current books. Positive = arb available.

    Picks the direction (sell-local or buy-local) that produces edge,
    or 0 if neither holds.
    """
    best_edge = 0.0
    if local_bid is not None:
        be = sell_local_break_even(spec, remote)
        best_edge = max(best_edge, local_bid - be)
    if local_ask is not None:
        be = buy_local_break_even(spec, remote)
        best_edge = max(best_edge, be - local_ask)
    return best_edge


# ============================================================= stockpile


@dataclass(frozen=True)
class StockpileConfig:
    """Batched-execution parameters.

    Transcript-1: optimal batch = ~3× conv_cap_per_tick. Smaller leaves
    P&L on the table (can't convert when bot absent); larger accumulates
    excess storage cost.
    """

    batch_multiplier: float = 3.0
    """Target batch size = batch_multiplier × conv_cap_per_tick."""

    max_inventory_buffer: int | None = None
    """Hard cap on stockpile size. None = use position limit."""


def target_batch_size(
    spec: ConversionSpec,
    config: StockpileConfig,
    arb_edge_per_unit: float,
    current_inventory: int,
) -> int:
    """How many units to trade LOCALLY this tick if arb is open.

    Returns a non-negative size. Zero when no arb edge or at inventory cap.
    Positive = do the local leg (remote conversion happens next tick).
    """
    if arb_edge_per_unit <= 0:
        return 0
    target = int(math.floor(config.batch_multiplier * spec.conv_cap_per_tick))
    # Don't exceed the buffer cap (if any).
    if config.max_inventory_buffer is not None:
        room = max(0, config.max_inventory_buffer - abs(current_inventory))
        target = min(target, room)
    return target


def conversion_size(
    spec: ConversionSpec,
    inventory: int,
) -> int:
    """Number of units to convert this tick.

    Positive = buy remote (net-short locally becomes flat).
    Negative = sell remote (net-long locally becomes flat).
    Capped at conv_cap_per_tick.
    """
    sign = -1 if inventory > 0 else (1 if inventory < 0 else 0)
    if sign == 0:
        return 0
    amount = min(abs(inventory), spec.conv_cap_per_tick)
    return sign * amount


# ============================================================= regime flag


@dataclass
class RegimeDetector:
    """Percentile-based regime flag on an external signal (sunlight etc).

    Fixes F4 hidden-alpha finding: treat external signals as DISCRETE
    regime flags, NOT linear regressors. A 99% R² linear fit is a
    lookahead-leakage tell.
    """

    lookback_window: int = 100
    """Rolling window for percentile calculation."""

    squeeze_percentile: float = 0.25
    """Below this → 'squeeze' regime (accumulate inventory)."""

    glut_percentile: float = 0.75
    """Above this → 'glut' regime (offload)."""

    # Bounded deque: O(1) append + automatic eviction. Previously a plain
    # list with ``pop(0)`` which is O(n) per observation — the per-tick
    # cost was small but scaled quadratically with lookback_window.
    _history: deque[float] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_history", deque(maxlen=self.lookback_window))

    def observe(self, value: float) -> None:
        self._history.append(value)

    def regime(self, current_value: float) -> Literal["squeeze", "normal", "glut"]:
        if len(self._history) < 10:
            return "normal"
        sorted_hist = sorted(self._history)
        n = len(sorted_hist)
        lo_idx = int(self.squeeze_percentile * n)
        hi_idx = int(self.glut_percentile * n)
        lo_val = sorted_hist[lo_idx]
        hi_val = sorted_hist[hi_idx]
        if current_value <= lo_val:
            return "squeeze"
        if current_value >= hi_val:
            return "glut"
        return "normal"


# ============================================================= fill probe


@dataclass
class FillRateProbe:
    """Thompson-bandit probe for hidden-taker fill price.

    P3 macaron finding: placing sell at `int(external_bid + 0.5)` got
    filled ~60%. The exact price-offset to mid matters more than the
    direction. This probe iteratively adjusts the offset and tracks
    fill success rate per offset, converging on the optimum.

    Simpler than full Thompson sampling — uses a success/trial count
    per offset and picks the offset with the highest Laplace-smoothed
    success rate (eps-greedy with eps=0.1 for exploration).
    """

    min_offset: int = -3
    max_offset: int = 3
    exploration_epsilon: float = 0.1
    _trials: dict[int, int] = field(default_factory=dict)
    _successes: dict[int, int] = field(default_factory=dict)

    def _rate(self, offset: int) -> float:
        s = self._successes.get(offset, 0)
        t = self._trials.get(offset, 0)
        # Laplace smoothing.
        return (s + 1) / (t + 2)

    def pick_offset(self, seed_rng: "random.Random | None" = None) -> int:
        import random as _r

        rng = seed_rng or _r.Random()
        if rng.random() < self.exploration_epsilon:
            return rng.randint(self.min_offset, self.max_offset)
        offsets = list(range(self.min_offset, self.max_offset + 1))
        return max(offsets, key=self._rate)

    def record(self, offset: int, *, filled: bool) -> None:
        self._trials[offset] = self._trials.get(offset, 0) + 1
        if filled:
            self._successes[offset] = self._successes.get(offset, 0) + 1

    def best_offset(self) -> int:
        offsets = list(range(self.min_offset, self.max_offset + 1))
        return max(offsets, key=self._rate)
