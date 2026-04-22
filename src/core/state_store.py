"""Versioned persistence for the trader's rolling ``EngineState``.

Prosperity calls ``Trader.run()`` in an effectively stateless container.
Anything we want to remember across iterations must live in ``traderData``,
which is a string with a hard 50,000 character budget.

This module is the single authoritative boundary between ``EngineState``
(the in-memory dataclass the engine works with) and the opaque string we
hand back to the platform.

Guarantees:
- ``load()`` never raises on empty, ``None``, or malformed input. It falls
  back to a fresh ``EngineState`` with the current version.
- ``save()`` always returns a string whose length is ``<= max_chars``.
- Schema migration hook ``_migrate`` is called when the stored version is
  older than the current version. Today it is a no-op, but the plumbing is
  in place so strategy history survives a version bump.
- Persisted history lists are clamped at load time so an adversarial or
  accidentally-bloated ``traderData`` cannot grow unbounded after a restart.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict
from typing import Any

from src.core.types import EngineState, ProductMemory

_MAX_PERSISTED_HISTORY = 64
_TRUNCATED_HISTORY_KEEP = 8


class StateStore:
    def __init__(
        self,
        version: int = 1,
        max_chars: int = 50_000,
        max_history: int = _MAX_PERSISTED_HISTORY,
        truncated_history_keep: int = _TRUNCATED_HISTORY_KEEP,
    ) -> None:
        if version < 1:
            raise ValueError("version must be >= 1")
        if max_chars <= 0:
            raise ValueError("max_chars must be > 0")
        if max_history < 0 or truncated_history_keep < 0:
            raise ValueError("history bounds must be >= 0")
        if truncated_history_keep > max_history:
            raise ValueError("truncated_history_keep must be <= max_history")

        self.version = version
        self.max_chars = max_chars
        self.max_history = max_history
        self.truncated_history_keep = truncated_history_keep

    # ------------------------------------------------------------------ load

    def load(self, trader_data: str | None) -> EngineState:
        """Parse ``traderData`` into an ``EngineState``.

        Returns a fresh state on any failure mode. This is intentional:
        a corrupted state blob must never crash ``Trader.run()``.
        """
        if not trader_data:
            return EngineState(version=self.version)

        try:
            raw = json.loads(trader_data)
        except (TypeError, ValueError):
            return EngineState(version=self.version)

        if not isinstance(raw, dict):
            return EngineState(version=self.version)

        stored_version = self._safe_int(raw.get("version"), default=self.version)
        if stored_version != self.version:
            raw = self._migrate(raw, from_version=stored_version)

        state = EngineState(version=self.version)
        raw_products = raw.get("products", {})
        if isinstance(raw_products, dict):
            for product, payload in raw_products.items():
                if not isinstance(product, str) or not isinstance(payload, dict):
                    continue
                state.products[product] = ProductMemory(
                    recent_mids=self._coerce_float_list(payload.get("recent_mids")),
                    recent_spreads=self._coerce_float_list(payload.get("recent_spreads")),
                    counters=self._coerce_int_dict(payload.get("counters")),
                    flags=self._coerce_bool_dict(payload.get("flags")),
                    values=self._coerce_float_dict(payload.get("values")),
                )

        # R3+ engines: engine_id → opaque dict. We don't validate the
        # shape — engines own their own deserialization via from_state().
        raw_engines = raw.get("engines", {})
        if isinstance(raw_engines, dict):
            for engine_id, blob in raw_engines.items():
                if not isinstance(engine_id, str) or not isinstance(blob, dict):
                    continue
                state.engines[engine_id] = blob

        return state

    # ------------------------------------------------------------------ save

    def save(self, state: EngineState) -> str:
        """Serialize ``state`` to a platform-safe string.

        Budget-tiered strategy (each tier shrinks memory, never drops
        engines state — engines own their own pruning via to_state()):
        1. Full encode with current contents.
        2. Truncate per-product mids/spreads to ``truncated_history_keep``.
        3. Drop per-product memory entirely (engines-only).
        4. Final fallback: empty payload with current version.

        Rationale for preferring product-memory drop over engines drop:
        engine state (Welford stats, smile fits, counterparty clusters)
        is cold-start expensive. ProductMemory rolling windows rebuild
        within ~100 ticks; losing engine state re-triggers 200+ tick
        warmup on every basket/options/stat-arb engine.

        ``_encode`` uses ``allow_nan=False`` so NaN/Infinity leaking
        into memory cannot produce spec-violating JSON that Prosperity's
        parser would silently reject. If it raises, we drop all memory
        rather than returning a bad blob.
        """
        try:
            payload = asdict(state)
            payload["version"] = self.version

            encoded = self._encode(payload)
            if len(encoded) <= self.max_chars:
                return encoded

            # Tier 2: truncate per-product rolling history.
            compact: dict[str, Any] = {
                "version": self.version,
                "products": {},
                "engines": dict(state.engines),
            }
            for product, memory in state.products.items():
                compact["products"][product] = {
                    "recent_mids": memory.recent_mids[-self.truncated_history_keep :],
                    "recent_spreads": memory.recent_spreads[-self.truncated_history_keep :],
                    "counters": memory.counters,
                    "flags": memory.flags,
                    "values": memory.values,
                }
            encoded = self._encode(compact)
            if len(encoded) <= self.max_chars:
                return encoded

            # Tier 3: drop product memory, keep engines.
            engines_only = {
                "version": self.version,
                "products": {},
                "engines": dict(state.engines),
            }
            encoded = self._encode(engines_only)
            if len(encoded) <= self.max_chars:
                return encoded
        except ValueError:
            warnings.warn(
                "StateStore.save refused to emit non-finite values "
                "(NaN/Infinity) and dropped all memory for this iteration. "
                "Investigate which strategy wrote the bad value.",
                RuntimeWarning,
                stacklevel=2,
            )

        # Tier 4: empty payload.
        return self._encode(
            {"version": self.version, "products": {}, "engines": {}}
        )

    # -------------------------------------------------------------- migrate

    def _migrate(self, raw: dict[str, Any], *, from_version: int) -> dict[str, Any]:
        """Hook for future schema migrations.

        The base implementation is a no-op and warns loudly when called
        with a mismatched ``from_version``. Subclasses should override
        this to dispatch on ``from_version`` and silently perform
        whatever rewrites the new schema needs.
        """
        if from_version != self.version:
            warnings.warn(
                f"StateStore._migrate invoked with from_version={from_version} "
                f"(current={self.version}) but the base implementation is a no-op. "
                "Override _migrate or bump the schema carefully.",
                UserWarning,
                stacklevel=2,
            )
        return raw

    # ---------------------------------------------------------------- utils

    @staticmethod
    def _encode(payload: dict[str, Any]) -> str:
        return json.dumps(payload, separators=(",", ":"), sort_keys=True, allow_nan=False)

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _coerce_float_list(self, value: Any) -> list[float]:
        if not isinstance(value, list):
            return []
        coerced = [
            float(item)
            for item in value
            if isinstance(item, (int, float)) and not isinstance(item, bool)
        ]
        if len(coerced) > self.max_history:
            coerced = coerced[-self.max_history :]
        return coerced

    @staticmethod
    def _coerce_int_dict(value: Any) -> dict[str, int]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, int] = {}
        for key, item in value.items():
            if isinstance(item, bool):
                continue
            if isinstance(item, (int, float)):
                out[str(key)] = int(item)
        return out

    @staticmethod
    def _coerce_bool_dict(value: Any) -> dict[str, bool]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, bool] = {}
        for key, item in value.items():
            if isinstance(item, bool):
                out[str(key)] = item
        return out

    @staticmethod
    def _coerce_float_dict(value: Any) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, float] = {}
        for key, item in value.items():
            if isinstance(item, bool):
                continue
            if isinstance(item, (int, float)):
                out[str(key)] = float(item)
        return out


class InMemoryStateStore(StateStore):
    """Backtest/research-only state store that skips JSON round-trips."""

    _TOKEN = "__IN_MEMORY_ENGINE_STATE__"

    def __init__(
        self,
        version: int = 1,
        max_chars: int = 50_000,
        max_history: int = _MAX_PERSISTED_HISTORY,
        truncated_history_keep: int = _TRUNCATED_HISTORY_KEEP,
    ) -> None:
        super().__init__(
            version=version,
            max_chars=max_chars,
            max_history=max_history,
            truncated_history_keep=truncated_history_keep,
        )
        self._cached_state: EngineState | None = None

    def load(self, trader_data: str | None) -> EngineState:
        if trader_data == self._TOKEN and self._cached_state is not None:
            return self._cached_state
        return super().load(trader_data)

    def save(self, state: EngineState) -> str:
        self._cached_state = state
        return self._TOKEN

    def clear(self) -> None:
        self._cached_state = None
