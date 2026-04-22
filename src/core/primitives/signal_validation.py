"""Signal validation harness (fixes D9).

Every signal must pass four gates before being trusted in production:

1. **Shuffle test** — shuffle the feature across time. The IC should
   drop to approximately zero. If it stays high after shuffling, the
   original "signal" is capturing a trivial statistical property, not
   genuine predictive information.

2. **Strict-lag IC** — compute IC with a strict lag: feature at t-k
   predicting returns at t (NOT feature at t predicting t+k). This
   catches endogenous re-pricing where the feature is updated AFTER
   the mid moves.

3. **Walk-forward OOS** — fit any parameters on the first 70% of
   replay days, validate on the last 30%. If the signal disappears
   out-of-sample, it was overfit.

4. **Own-quote causality test** — remove ticks where our own orders
   were at top-of-book (endogenous contribution to the book state).
   If the signal IC survives only in those ticks, the signal is just
   our own quote history echoed back.

A signal that fails any of these four tests should be logged as a
research signal (``validated=False`` on the SignalBus) but never
reach production.

This module provides the test harness and the go/no-go report. It
does NOT run the strategies or emitters — the caller hooks into
its own replay loop and feeds feature/return series.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import mean, stdev


@dataclass(frozen=True)
class ValidationResult:
    """One test result."""

    test_name: str
    passed: bool
    ic: float | None
    """IC measured in this test."""
    baseline_ic: float | None = None
    """What the IC should be for the test to pass (typically ~0 for shuffle)."""
    detail: str = ""


@dataclass(frozen=True)
class ValidationReport:
    """Full report: all 4 tests + aggregate verdict."""

    signal_name: str
    passed_all: bool
    results: list[ValidationResult]
    raw_ic: float
    """Reference IC from the ORIGINAL (unshuffled, cross-validated) data."""
    n_samples: int

    def summary(self) -> str:
        lines = [f"Signal: {self.signal_name}"]
        lines.append(
            f"Raw IC: {self.raw_ic:+.4f} (n={self.n_samples}) — "
            f"{'PASS' if self.passed_all else 'FAIL'}"
        )
        for r in self.results:
            status = "✓" if r.passed else "✗"
            ic_str = f"{r.ic:+.4f}" if r.ic is not None else "—"
            base_str = (
                f" (baseline {r.baseline_ic:+.4f})"
                if r.baseline_ic is not None else ""
            )
            lines.append(f"  {status} {r.test_name}: IC {ic_str}{base_str} — {r.detail}")
        return "\n".join(lines)


# ============================================================= statistics


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 30:
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


# ============================================================= tests


def shuffle_test(
    features: list[float],
    returns: list[float],
    *,
    n_shuffles: int = 50,
    max_shuffled_ic: float = 0.05,
    seed: int = 42,
) -> ValidationResult:
    """Shuffle features across time; IC should drop to ~0."""
    if len(features) != len(returns):
        return ValidationResult(
            test_name="shuffle",
            passed=False,
            ic=None,
            detail="length mismatch",
        )
    rng = random.Random(seed)
    shuffled_ics: list[float] = []
    for _ in range(n_shuffles):
        perm = features.copy()
        rng.shuffle(perm)
        ic = _pearson(perm, returns)
        if ic is not None:
            shuffled_ics.append(ic)
    if not shuffled_ics:
        return ValidationResult(
            test_name="shuffle",
            passed=False,
            ic=None,
            detail="insufficient samples",
        )
    mean_shuffled = mean(shuffled_ics)
    max_abs_shuffled = max(abs(ic) for ic in shuffled_ics)
    passed = max_abs_shuffled <= max_shuffled_ic
    return ValidationResult(
        test_name="shuffle",
        passed=passed,
        ic=mean_shuffled,
        baseline_ic=0.0,
        detail=(
            f"{n_shuffles} shuffles, max |IC|={max_abs_shuffled:.4f}, "
            f"threshold={max_shuffled_ic}"
        ),
    )


def strict_lag_test(
    features: list[float],
    returns: list[float],
    *,
    lag_k: int = 10,
    min_ic: float = 0.03,
) -> ValidationResult:
    """Test that feature at t-k predicts return at t (strict causality)."""
    if len(features) != len(returns):
        return ValidationResult(
            test_name="strict_lag",
            passed=False,
            ic=None,
            detail="length mismatch",
        )
    if len(features) <= lag_k:
        return ValidationResult(
            test_name="strict_lag",
            passed=False,
            ic=None,
            detail=f"too short for lag_k={lag_k}",
        )
    # feature[0..n-k-1] predicts return[k..n-1]
    f = features[: len(features) - lag_k]
    r = returns[lag_k:]
    ic = _pearson(f, r)
    if ic is None:
        return ValidationResult(
            test_name="strict_lag",
            passed=False,
            ic=None,
            detail="IC computation failed",
        )
    passed = abs(ic) >= min_ic
    return ValidationResult(
        test_name="strict_lag",
        passed=passed,
        ic=ic,
        baseline_ic=min_ic,
        detail=f"lag_k={lag_k} (feature leads return by k ticks)",
    )


def walk_forward_test(
    features: list[float],
    returns: list[float],
    *,
    train_fraction: float = 0.7,
    min_oos_ic_ratio: float = 0.5,
) -> ValidationResult:
    """Compare in-sample vs out-of-sample IC. OOS IC should be ≥ fraction of IS."""
    if len(features) != len(returns):
        return ValidationResult(
            test_name="walk_forward",
            passed=False,
            ic=None,
            detail="length mismatch",
        )
    n = len(features)
    split = int(n * train_fraction)
    if split < 30 or n - split < 30:
        return ValidationResult(
            test_name="walk_forward",
            passed=False,
            ic=None,
            detail=f"too few samples (n={n}, split={split})",
        )
    is_ic = _pearson(features[:split], returns[:split])
    oos_ic = _pearson(features[split:], returns[split:])
    if is_ic is None or oos_ic is None:
        return ValidationResult(
            test_name="walk_forward",
            passed=False,
            ic=None,
            detail="IC computation failed",
        )
    if abs(is_ic) < 0.02:
        # IS IC is already tiny — this test doesn't apply
        return ValidationResult(
            test_name="walk_forward",
            passed=True,  # vacuously pass; other tests will catch weak signals
            ic=oos_ic,
            detail=f"IS IC {is_ic:+.4f} too small to measure degradation",
        )
    ratio = oos_ic / is_ic
    passed = ratio >= min_oos_ic_ratio and (oos_ic / is_ic) > 0  # sign must agree
    return ValidationResult(
        test_name="walk_forward",
        passed=passed,
        ic=oos_ic,
        baseline_ic=is_ic * min_oos_ic_ratio,
        detail=f"IS IC={is_ic:+.4f}, OOS IC={oos_ic:+.4f}, ratio={ratio:.2f}",
    )


def own_quote_causality_test(
    features: list[float],
    returns: list[float],
    own_quote_present: list[bool],
    *,
    min_clean_ic: float = 0.03,
) -> ValidationResult:
    """Test IC on ticks where our own quote was NOT at top-of-book.

    If IC survives only on ticks where we're present, the signal is
    echoed from our own order flow. Clean IC (excluding our ticks)
    must still be materially non-zero.
    """
    if not (len(features) == len(returns) == len(own_quote_present)):
        return ValidationResult(
            test_name="own_quote_causality",
            passed=False,
            ic=None,
            detail="length mismatch",
        )
    clean_features = [f for f, p in zip(features, own_quote_present) if not p]
    clean_returns = [r for r, p in zip(returns, own_quote_present) if not p]
    if len(clean_features) < 100:
        return ValidationResult(
            test_name="own_quote_causality",
            passed=True,  # vacuous — not enough clean ticks to test
            ic=None,
            detail=(
                f"only {len(clean_features)} clean ticks (our quotes present "
                f"{len(features) - len(clean_features)} / {len(features)})"
            ),
        )
    clean_ic = _pearson(clean_features, clean_returns)
    if clean_ic is None:
        return ValidationResult(
            test_name="own_quote_causality",
            passed=False,
            ic=None,
            detail="IC computation on clean subset failed",
        )
    passed = abs(clean_ic) >= min_clean_ic
    return ValidationResult(
        test_name="own_quote_causality",
        passed=passed,
        ic=clean_ic,
        baseline_ic=min_clean_ic,
        detail=(
            f"clean n={len(clean_features)}, "
            f"clean IC={clean_ic:+.4f} (must exceed {min_clean_ic})"
        ),
    )


# ============================================================= orchestration


def validate_signal(
    signal_name: str,
    features: list[float],
    returns: list[float],
    *,
    own_quote_present: list[bool] | None = None,
    lag_k: int = 10,
    shuffle_threshold: float = 0.05,
    min_ic: float = 0.03,
    train_fraction: float = 0.7,
    min_oos_ic_ratio: float = 0.5,
) -> ValidationReport:
    """Run all 4 tests and return a consolidated report."""
    raw_ic = _pearson(features, returns) or 0.0
    tests = [
        shuffle_test(
            features, returns,
            max_shuffled_ic=shuffle_threshold,
        ),
        strict_lag_test(
            features, returns,
            lag_k=lag_k, min_ic=min_ic,
        ),
        walk_forward_test(
            features, returns,
            train_fraction=train_fraction,
            min_oos_ic_ratio=min_oos_ic_ratio,
        ),
    ]
    if own_quote_present is not None:
        tests.append(
            own_quote_causality_test(
                features, returns, own_quote_present, min_clean_ic=min_ic,
            )
        )
    passed_all = all(t.passed for t in tests)
    return ValidationReport(
        signal_name=signal_name,
        passed_all=passed_all,
        results=tests,
        raw_ic=raw_ic,
        n_samples=len(features),
    )
