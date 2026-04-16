"""Synthesize trade arrivals + joint (offset, size) draws per product.

Two-stage sampler:

  Stage 1 - **Arrival times via renewal process**. Sample inter-arrival
  gaps from the empirical gap distribution observed in the calibration
  trade tape. This preserves any clustering that an iid-Bernoulli
  model would erase. (Round-1 ASH/PEPPER trade gaps fail the
  geometric-fit KS test at 0.73 — Bernoulli is rejected, so we use
  a renewal-process model with empirical gaps.)

  Stage 2 - **Joint (offset, size) draws**. For each arrival, sample
  a complete (price_offset_from_fv, quantity) pair from the empirical
  joint distribution observed in real trades. Trade direction
  (buy vs sell) is then a deterministic function of offset sign:
  positive offset = buy (took the ask), negative = sell (hit the bid).
  This eliminates the (price > FV) heuristic and matches the natural
  data-generating process by construction.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from src.analysis.calibration.types import FactRow, TradeRow


@dataclass(frozen=True)
class SyntheticTrade:
    """A trade emitted by the simulator at one tick."""

    timestamp: int
    product: str
    price: int
    quantity: int
    side: str  # "buy" (lifted ask) or "sell" (hit bid); derived from offset sign


@dataclass(frozen=True)
class TradeSamplerStats:
    """Diagnostic summary of a fitted trade sampler."""

    product: str
    n_trades: int
    p_active_per_tick: float
    n_unique_offsets: int
    n_unique_sizes: int
    mean_gap: float
    n_gap_observations: int


class TradeSampler:
    """Sample synthetic trades for one product.

    Initialize with the historical trades + facts (used to recover
    inter-arrival gaps and align trade timestamps). Then call
    ``sample_session`` to emit a list of SyntheticTrade for one
    synthetic session.
    """

    def __init__(
        self,
        *,
        product: str,
        trades: Sequence[TradeRow],
        facts: Sequence[FactRow],
        tick_step: int = 100,
    ) -> None:
        self._product = product
        self._tick_step = tick_step
        # Filter trades to this product, sort by timestamp.
        product_trades = sorted(
            (t for t in trades if t.product == product),
            key=lambda t: t.timestamp,
        )
        # Filter facts to this product so we can compute trade offsets.
        product_facts = sorted(
            (f for f in facts if f.product == product),
            key=lambda f: f.timestamp,
        )
        if not product_facts:
            raise ValueError(
                f"TradeSampler for {product}: no facts found"
            )
        fv_by_ts = {f.timestamp: f.server_fv for f in product_facts}
        self._n_ticks_calibration = len(product_facts)

        # Build joint (offset, size) samples for trades that we can
        # align to a fact (have a server FV at the trade's timestamp).
        joint_samples: list[tuple[int, int]] = []
        for trade in product_trades:
            fv = fv_by_ts.get(trade.timestamp)
            if fv is None:
                continue  # Trade arrived between snapshots; skip.
            offset = trade.price - fv
            joint_samples.append((int(round(offset)), int(trade.quantity)))
        self._joint_samples = joint_samples

        # Build inter-arrival gap distribution in TICK units (not raw timestamps).
        # An "arrival" is a tick where >=1 trade landed; multiple trades
        # at the same timestamp count as one arrival event for gap
        # purposes (they're handled by trades-per-tick distribution).
        active_ticks = sorted({t.timestamp // tick_step for t in product_trades})
        if len(active_ticks) >= 2:
            gaps = np.diff(np.asarray(active_ticks, dtype=int))
            self._gap_samples = gaps.tolist()
        else:
            self._gap_samples = []  # too few trades to fit a renewal process

        # Trades-per-active-tick distribution (handles second-trade-on-same-tick).
        per_tick_counts: dict[int, int] = {}
        for trade in product_trades:
            tick = trade.timestamp // tick_step
            per_tick_counts[tick] = per_tick_counts.get(tick, 0) + 1
        self._trades_per_active_tick = list(per_tick_counts.values())

        # Cache first-arrival jitter cap to avoid recomputing per call.
        self._first_arrival_max = (
            max(1, int(np.ceil(np.mean(self._gap_samples))))
            if self._gap_samples else 1
        )

    @property
    def stats(self) -> TradeSamplerStats:
        n_trades = sum(1 for _ in self._joint_samples)
        n_active = len(self._gap_samples) + 1 if self._gap_samples else 0
        p_active = n_active / self._n_ticks_calibration if self._n_ticks_calibration else 0.0
        unique_offsets = len({o for o, _ in self._joint_samples})
        unique_sizes = len({s for _, s in self._joint_samples})
        mean_gap = float(np.mean(self._gap_samples)) if self._gap_samples else 0.0
        return TradeSamplerStats(
            product=self._product,
            n_trades=n_trades,
            p_active_per_tick=p_active,
            n_unique_offsets=unique_offsets,
            n_unique_sizes=unique_sizes,
            mean_gap=mean_gap,
            n_gap_observations=len(self._gap_samples),
        )

    def sample_session(
        self,
        *,
        fv_path: np.ndarray,
        rng: np.random.Generator,
    ) -> list[SyntheticTrade]:
        """Spawn the trade tape for one synthetic session.

        Args:
            fv_path: synthetic FV path of length n_ticks (from fv_evolver).
            rng: numpy Generator for all stochastic draws.

        Returns:
            List of SyntheticTrade events with timestamps in
            [0, n_ticks * tick_step). Side is derived from
            sign(offset).
        """
        n_ticks = len(fv_path)
        if not self._joint_samples or not self._gap_samples:
            return []

        # Step 1: sample arrival ticks via renewal process with empirical gaps.
        arrival_ticks: list[int] = []
        # Start: sample uniformly over [0, mean_gap) for first arrival,
        # avoids systematic bias toward t=0 vs t=large.
        first_offset = int(rng.integers(0, self._first_arrival_max))
        cursor = first_offset
        while cursor < n_ticks:
            arrival_ticks.append(cursor)
            gap = int(self._gap_samples[rng.integers(0, len(self._gap_samples))])
            cursor += max(gap, 1)  # safety: gap >= 1 to avoid infinite loop on degenerate gaps

        # Step 2: per arrival, sample number of trades and their (offset, size).
        out: list[SyntheticTrade] = []
        joint_arr_off = np.asarray([o for o, _ in self._joint_samples], dtype=int)
        joint_arr_size = np.asarray([s for _, s in self._joint_samples], dtype=int)
        for tick in arrival_ticks:
            n_trades_here = int(self._trades_per_active_tick[
                rng.integers(0, len(self._trades_per_active_tick))
            ])
            for _ in range(n_trades_here):
                idx = int(rng.integers(0, len(joint_arr_off)))
                offset = int(joint_arr_off[idx])
                size = int(joint_arr_size[idx])
                price = int(round(fv_path[tick] + offset))
                # P0-3 fix: zero-offset trades (price == FV exactly,
                # possible at quantization grid points) used to emit
                # side="unknown" which the matcher silently dropped.
                # Now: randomize side 50/50 so the trade still
                # participates in matching.
                if offset > 0:
                    side = "buy"
                elif offset < 0:
                    side = "sell"
                else:
                    side = "buy" if rng.random() < 0.5 else "sell"
                out.append(SyntheticTrade(
                    timestamp=tick * self._tick_step,
                    product=self._product,
                    price=price,
                    quantity=size,
                    side=side,
                ))
        return out
