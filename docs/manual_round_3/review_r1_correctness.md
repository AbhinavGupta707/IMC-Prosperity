# Round 3 Engine — Correctness Review (R1)

**Branch:** `round3-engine`  
**Reviewer:** automated adversarial correctness pass  
**Date:** 2026-04-22  
**Scope:** 11 files, mathematical + logical correctness, static analysis

---

## Summary

| Severity | Count | Files affected |
|---|---|---|
| CRITICAL | 4 | bsm.py, sweep_selector.py, signal_validation.py, stat_arb.py |
| HIGH | 6 | bsm.py, smile.py, options_mm.py, counterparty_intel.py, hysteresis_sizer.py, stat_arb.py |
| MEDIUM | 5 | smile.py, conversions/layer.py, counterparty_intel.py, stat_arb.py, sst.py |
| LOW | 4 | bsm.py, smile.py, sweep_selector.py, hysteresis_sizer.py |

---

## File: `src/options/bsm.py`

### CONFIRMED BUGS

**[CRITICAL] Bisection IV solver returns wildly wrong value when `f(lo) == 0`**  
Line: 207 (`if f_lo * f_mid < 0`)  
Fix complexity: LOW (1 line)

When `call_price(sigma=lo=0.001)` equals `market_price` exactly (deep-ITM options where market price equals intrinsic), `f_lo = 0.0`. The bisection condition `f_lo * f_mid < 0` evaluates to `0.0 * anything = 0.0`, which is **never `< 0`**, so the bisection always updates `lo` upward regardless of where the root is. The solver walks to `hi ≈ 5.0` and returns a value near 5.0 when the correct answer is near 0.001.

Reproduced:
```
S=120, K=100, T=0.5: market = BSM(lo=0.001) = 20.0 (= intrinsic)
iv returned: 5.0000  |  true iv: ~0.001
```

The `SmileFitter.observe()` guard (`iv > max_sensible_iv = 2.0`) silently rejects IVs above 2.0, masking the most extreme cases. But for moderately-deep ITM options where the true IV is below 2.0, a wrong IV will be stored and corrupt the smile.

**Fix:**
```python
if f_lo == 0.0:
    return lo
if f_hi == 0.0:
    return hi
```
Add these two lines immediately after computing `f_lo` and `f_hi` and before the bracket check.

---

**[HIGH] Bracket widening logic has a dead branch when `f_lo > 0` and `f_hi > 0`**  
Lines: 189–200

If `market_price < BSM(lo=0.001)` (can happen for some near-expiry deep-OTM options where time value is nearly zero), both `f_lo` and `f_hi` are positive. The code enters the widening branch but only handles `f_hi < 0 and hi < 10.0`. The case where `f_lo > 0` (root below `lo`) always falls to `return None`, which is correct behavior but the code path is confusing and the missing case is not documented. The intrinsic check at line 173 (`market_price < intrinsic - tol`) may not catch all such cases because BSM at `lo=0.001` can include tiny time value above intrinsic.

This is low probability in practice (OTM options with prices below BSM at vol=0.001) but the missing documentation makes it a maintenance trap.

---

**[LOW] `call_greeks.theta` docstring is self-contradictory**  
Lines: 124, 131–132

The `Greeks` dataclass says `theta: float  # ∂C/∂T`. The function docstring says `Theta is returned per UNIT of time-to-expiry (negative, since extrinsic value decays)`. These two descriptions contradict each other: `∂C/∂T` is mathematically **positive** (more time = more value), but the implementation returns the **negative** of that (the per-unit decay rate, i.e., `-∂C/∂T`).

The actual implementation is correct for trading use (theta < 0 = value lost per unit time passing), but any caller who interprets the field as `∂C/∂T` (per the dataclass comment) will get the sign wrong. Verified:
```
Numerical dC/dT at T=1.0 → T=0.99: +0.0397
theta * (-0.01) = +0.0397  (consistent with theta being -dC/dT)
```

**Fix:** change the dataclass comment to `# -∂C/∂T (value decay per unit of time passing)`.

---

### OK

- `norm_cdf`: A&S 7.1.26 coefficients and the `1/sqrt(2)` argument scaling are **correct**. Verified against `math.erfc` — max error < 7.0e-8. The identity `Φ(-x) = 1 - Φ(x)` is applied correctly.
- `norm_pdf`: correct.
- `_d1_d2`: standard BSM d1/d2 formula, correct for r=0 (Prosperity use case).
- `call_price`: correct.
- `vega`: `S * N'(d1) * sqrt(T)` — verified numerically; units are per 1.0 absolute sigma change (not per 1%), consistent with the docstring.
- `gamma`: `N'(d1) / (S * σ * sqrt(T))` — correct.

---

## File: `src/options/smile.py`

### CONFIRMED BUGS

**[HIGH] Moneyness formula labeled Gatheral-Jacquier but implements a different formula**  
Line: 63, and module docstring

The code computes `m = log(K/S) / sqrt(T)`. The true Gatheral-Jacquier normalized log-moneyness is `m = log(K/F) / (σ * sqrt(T))` where `F = S * exp(r*T)`.

At r=0: `F = S`, so the code's formula becomes `log(K/S) / sqrt(T)` — this correctly omits the interest rate but still **omits the σ normalization**. Without σ in the denominator, the x-axis of the quadratic fit is NOT standardized across different vol regimes. A smile fit at σ=0.2 and a fit at σ=0.4 will have completely different curvatures because the moneyness units are different.

For Prosperity where all vouchers share one underlying and vol doesn't vary wildly across strikes, this is a moderate (not catastrophic) error — the quadratic fit will still work but won't be portable across vol regimes. The key practical impact is that the quadratic coefficients `a, b, c` have no consistent meaning across time.

**Fix:** divide by `sigma * sqrt(T)`. This requires knowing an estimate of sigma. Use EWMA average IV as the normalizing sigma, or just rename the formula to `log(K/S)/sqrt(T)` (Derman-Kani style) and remove the Gatheral-Jacquier attribution.

---

**[MEDIUM] `_warmup_iv` with 2 observed strikes returns `None` for the query strike even if it is one of the observed strikes**  
Lines: 144–148

When exactly 2 strikes have observations and the query `strike` is one of them, the `len(points) < 3` branch checks `if strike in self._per_strike_iv` (correctly). But when the query `strike` is NOT an observed strike (e.g., asking about 100.5 when only 100 and 101 are observed), the function returns `None` — meaning the engine cannot price an option until at least 3 strikes exist. This is a silent failure that the caller cannot distinguish from "no data at all."

**Fix:** in the `< 3` fallback, find the nearest observed strike and return its EWMA if available, rather than returning `None` for unobserved strikes.

---

**[LOW] `_total_obs` is incremented but never used**  
Lines: 87, 101

The field `_total_obs` tracks total observations across all strikes and is serialized in `snapshot()`. The `_in_warmup()` check uses per-strike count, not `_total_obs`. The `fair_iv()` method does not use `_total_obs`. This is dead state that adds serialization overhead without function.

---

**[LOW] EWMA halflife semantics in the rolling mode**  
Lines: 98–100

When a regime shift occurs (IV jumps from 0.20 to 0.40 suddenly), the EWMA with halflife=100 ticks will take ~660 ticks (ln(0.01) / ln(0.5) × 100) to get within 1% of the new level. For a sharp regime change, this makes the fitter systematically mis-price options for hundreds of ticks — exactly the pathology noted in the module docstring about chrispyroberts' team. The rolling window mode (simple mean of last 200 obs) was cited as better, but the code actually returns `_ewma_iv.get(strike)` in rolling mode (line 124), not the rolling mean of the window. So the module is using EWMA in "rolling mode" while the comment implies otherwise.

The 200-obs rolling window is correctly stored in `_per_strike_iv[strike]` (maxlen=200) but its mean is only ever used in `_warmup_iv` (warmup mode). In rolling mode, the EWMA is returned, not the window mean. This is probably intentional (EWMA is smoother) but the docstring is misleading.

---

## File: `src/conversions/layer.py`

### CONFIRMED BUGS

**[MEDIUM] `sell_local_break_even` direction for import tariff is potentially confusing in IMC docs context**  
Lines: 88–98

The formula `remote.ask + transport + import_tariff` is **mathematically correct** for the convention stated. With negative `import_tariff` (subsidy), the break-even falls, which correctly makes the arb easier. However, the IMC docs for Orchids/Macarons use the convention that import tariff is **added to your cost** when importing, so `import_tariff` should always be ≥ 0 in normal use. A negative `import_tariff` in `ConversionSpec` (which is explicitly allowed) represents a subsidy and correctly lowers the break-even. This is OK, but:

The `ConversionSpec.__post_init__` validates `storage_cost >= 0` but **does not validate import/export tariffs** against any range. A caller who accidentally passes `import_tariff = -1000` would silently produce a negative break-even, making the engine think every local bid is profitable.

---

**[MEDIUM] `target_batch_size`: `max_inventory_buffer` check uses `abs(current_inventory)` — direction-agnostic**  
Lines: 166–167

```python
room = max(0, config.max_inventory_buffer - abs(current_inventory))
```

This correctly limits both long and short inventory accumulation. However, the stat_arb engine determines the arb direction (sell-local or buy-local) separately and calls `target_batch_size` without indicating which direction it intends to trade. If the current position is at +25 (cap) and only buy-local arb is available, `target_batch_size` returns 0 (no room), but the sell-local arb direction would have room to go short. The direction-agnostic check is conservative (never overfills) but may suppress valid arb on the opposite side.

This is not a bug per se — it makes the function safe — but it can cause the engine to miss arb opportunities when partially filled in the opposite direction.

---

**[LOW] `FillRateProbe.pick_offset` imports `random` inside the method body**  
Line: 262

`import random as _r` inside a method is executed on every call. For a hot path, this is inefficient (though Python caches imports). More importantly, the type annotation `"random.Random | None"` in the function signature (line 261) is a forward reference string, but `random` is not imported at module level — this would fail type-checking (confirmed by ruff: `F821 Undefined name 'random'`). The import should be at the top of the file.

---

## File: `src/core/primitives/sst.py`

### SUSPICIOUS PATTERNS

**[MEDIUM] Make-phase bid suppression guard is redundant but inconsistent**  
Lines: 271, 287

The outer guard at line 271 (`not (flattening and position > 0)`) prevents entering the bid block when flattening a long position. Then line 287 inside the block sets `bid_size = 0` with the identical condition. The code is redundant: the inner guard can never fire because the outer guard already prevents entering the block in the long-flattening case. The redundancy suggests copy-paste rather than intentional defense-in-depth, and if the outer guard is ever modified, the inner one may not be updated consistently.

---

**[LOW] `_is_toxic` classifies based on `price > mid` / `price < mid`**  
Lines: 148–153

For a trade at exactly `price == mid`, neither `buy_toxic` nor `sell_toxic` fires. This is reasonable for tick-grid prices, but on a product where mid can fall exactly on a tick, all mid-priced fills are invisible to the toxicity filter. For Prosperity vouchers (options), prints exactly at ATM fair value would not be classified as toxic even if very small. This is an edge case but worth documenting.

---

### OK

- `_capacity(position, limit)`: correct. Verified for negative positions: `buy_cap = limit - position = limit - (-pos) = limit + |pos|`, which is the remaining room to get to `+limit`.
- Clear mode: long and short symmetric. Confirmed — sell at `ceil(fair - clear_width)`, buy at `floor(fair + clear_width)`. Both correct.
- Take phase: `buy_cap` is correctly decremented before clear phase; no double-counting.

---

## File: `src/core/primitives/hysteresis_sizer.py`

### CONFIRMED BUGS

**[MEDIUM] At barely-above-entry z-score, `target_position` returns 0 despite being in the active zone**  
Lines: 96–102

```python
normalized = (abs_z - entry_z) / (kill_z - entry_z)  # = 0.0005 at z=2.001
target_abs = int(math.floor(max_position * normalized))  # = floor(60 * 0.0005) = 0
return sign * max(1, target_abs) if target_abs > 0 else 0  # target_abs=0 → return 0
```

The `max(1, ...)` guard is gated on `target_abs > 0`, but `target_abs` is zero for any z-score within the first `(1/max_position) * (kill_z - entry_z)` units above `entry_z`. For default config, this dead band runs from z=2.0 to z≈2.033. Any z in [2.0, 2.033] produces `target=0` even though the sizer has determined we're in the active zone.

Impact: the sizer has a "false entry" band of width ~0.033 sigma units where the entry condition is met but no position is taken. This may cause the engine to believe it entered (checking `if not entry_gate and ...`) while `_current_target_basket` stays at 0.

---

**[HIGH] Kill zone freezes a wrong-sign position**  
Lines: 83–84

```python
if abs_z >= config.kill_z:
    return current_position
```

If the current position is **opposite** to the kill-zone signal (e.g., z=4.1 strongly long, but current_position=-20 from a prior trade that hasn't been exited), the kill zone **prevents unwinding** the misaligned position. The function returns -20, meaning the caller will not issue any unwind order. The engine holds a losing short position while a kill zone blocks all action.

The kill zone is designed to prevent *growing* into a potentially regime-broken trade. But freezing a position that is already misaligned is a secondary behavior that is not documented and can be harmful. The fix should distinguish: if `current_position` and the implied sign of z agree, hold; if they disagree, at minimum allow shrinking toward zero.

---

### OK

- Welford update order: `n += 1`, `delta = x - mean`, `mean += delta/n`, `delta2 = x - mean` (after update), `m2 += delta * delta2` — this is the textbook Welford algorithm. Verified correct against `statistics.stdev`.
- Sign convention: z > 0 → long target (positive sign). Correct.
- Scale function at exact `kill_z`: `normalized = 1.0` → `target_abs = max_position`. Correct.

---

## File: `src/core/primitives/sweep_selector.py`

### CONFIRMED BUGS

**[CRITICAL] `IndexError` crash when all candidate P&L scores are negative**  
Lines: 219, 228–230

```python
tied = [c for c, s in scored if s >= top_score * 0.99]
```

When `top_score` is negative (e.g., -100), `top_score * 0.99 = -99` (less negative, numerically larger). The condition `s >= -99` means only scores that are **better than top** qualify as tied, which is mathematically impossible. `tied` is always empty, and then `winner = tied[0]` raises `IndexError`.

Reproduced:
```python
configs = [baseline(-200 to -190), candidate(-60 to -40)]
select_winner(configs, 'baseline')
# → IndexError: list index out of range (line 230)
```

This crashes the entire selection process when P&L values are negative. Since Prosperity replays commonly produce negative P&L during development and sweep evaluation, this is a hard crash on a common input.

**Fix:**
```python
tied = [c for c, s in scored if abs(s - top_score) <= abs(top_score) * 0.01]
```
This uses absolute deviation relative to absolute score for correct symmetric behavior.

---

**[MEDIUM] Tie-break "within 1%" is meaningless for near-zero scores**  
Line: 219

If `top_score ≈ 0` (break-even strategies), `top_score * 0.99 ≈ 0`, so essentially all candidates with non-negative scores are "tied." This means the entire selection collapses to the tie-breaker for any near-zero P&L sweep, removing the objective function's discrimination power.

---

### OK

- Bootstrap CI computation is statistically valid for `n >= 2`. The percentile index arithmetic (`lo_idx = int(n_bootstrap * (1-confidence)/2)`) correctly rounds down for the lower bound.
- Significance gate (`ci_lower > baseline_ci_upper`) is one-sided and conservative — correct for "pick a winner" decisions.
- `_score_by_quantiles`: normal CDF approximation using `math.erf` is correct. SEM estimate `(upper - lower) / (2 * 1.96)` is the standard 95% CI inverse.

---

## File: `src/core/primitives/signal_validation.py`

### CONFIRMED BUGS

**[CRITICAL] `walk_forward_test` passes for signals with consistently negative IC**  
Lines: 230–231

```python
ratio = oos_ic / is_ic
passed = ratio >= min_oos_ic_ratio and (oos_ic / is_ic) > 0  # sign must agree
```

The second condition `(oos_ic / is_ic) > 0` is identical to `ratio > 0`, making it redundant with the first condition when `min_oos_ic_ratio = 0.5 > 0`. More critically: if IS IC = -0.03 and OOS IC = -0.05 (both negative — signal predicts the **wrong direction** out-of-sample), then:

```
ratio = (-0.05) / (-0.03) = 1.67
passed = (1.67 >= 0.5) AND (1.67 > 0) → True
```

The test **PASSES** for a signal that has negative IC in both periods. A signal that consistently hurts performance is declared valid.

**Fix:**
```python
passed = is_ic > 0 and oos_ic > 0 and ratio >= min_oos_ic_ratio
```
Or more generally: `math.copysign(1, oos_ic) == math.copysign(1, is_ic) and ratio >= min_oos_ic_ratio`.

---

**[HIGH] `own_quote_causality_test` vacuously passes when `< 100` clean ticks exist**  
Lines: 263–271

When the bot is present in nearly all ticks (its quotes are at top-of-book most of the time), `clean_features` will have fewer than 100 elements and the test vacuously returns `passed=True`. This means an endogenous signal (completely driven by own quotes) passes validation if the bot is active enough. In a market-making strategy where the bot quotes most ticks, this test provides almost no protection.

**Fix:** lower the fallback threshold, or change the fallback to `passed=None` / unknown, not `True`.

---

**[MEDIUM] `walk_forward_test` vacuous pass for small IS IC**  
Line: 222–229

If `abs(is_ic) < 0.02`, the test returns `passed=True` vacuously. The intent is correct (can't measure degradation on a tiny signal), but this means a signal with IS IC = 0.019 (slightly too small to measure) passes the walk-forward test unconditionally. Combined with the shuffle test (which only checks `max_abs_shuffled <= 0.05`) and the sign bug above, a signal with IC ≈ 0.019 in-sample would pass all 4 tests. The cross-test threshold consistency is not enforced.

---

## File: `src/engines/basket_arb.py`

### OK

**Welford update order:** Correct. Sequence: `n += 1`, `delta = x - mean_before`, `mean += delta/n`, `delta2 = x - mean_after`, `m2 += delta * delta2`. This is exactly the Welford one-pass algorithm. Verified numerically against `statistics.stdev`.

**Z-score sign convention:** `spread = basket_mid - theoretical`. Positive spread → basket rich → short basket. The code passes `z=-z` to `target_position`, which returns a negative target (short) when basket is rich. Hedge direction: `hedge_qty = -round(hedge_factor * weight * basket_delta)`. Positive basket_delta (buy basket) → negative hedge_qty (sell constituent). Correct.

**Dual gate:** The override `target = self._current_target_basket` when `not entry_gate and abs(z) >= z_thr` fires correctly to hold position when z passes but raw spread does not. Exit (z < exit_z) correctly bypasses the override.

---

## File: `src/engines/options_mm.py`

### CONFIRMED BUGS

**[HIGH] Jump detection uses simple moving average, not EWMA — mislabeled in docstring and engine comment**  
Lines: 323

```python
ewma_abs_r = sum(self._recent_abs_returns) / len(self._recent_abs_returns)
```

This is a **simple moving average** of the last 500 absolute returns. The module docstring says `jump: |r| / EWMA(|r|, 500) > 4` and the comment on `OptionsEngineConfig.jump_window` implies EWMA. An SMA gives equal weight to all observations in the window, whereas EWMA downweights old observations. For jump detection, SMA will be significantly slower to react to changes in the baseline volatility level.

This is not algorithmically broken (SMA threshold detection still works), but the EWMA claim is false and if someone tunes the threshold against an EWMA expectation, they'll get wrong behavior.

**Fix:** Replace with actual EWMA:
```python
# In __post_init__ or on first use:
self._ewma_abs_r: float = 0.0
# In _detect_jump, after computing r:
alpha = 2.0 / (self.config.jump_window + 1)
self._ewma_abs_r = alpha * r + (1 - alpha) * self._ewma_abs_r
if self._ewma_abs_r > 0 and r / self._ewma_abs_r > self.config.jump_threshold:
    ...
```

---

**[HIGH] Kill cooldown re-trigger risk after cooldown expiry**  
Lines: 326–328

When a jump is detected, `_last_underlying_mid` is updated to the jump-point price. When `_in_kill_cooldown` expires, the next tick computes `r = |spot - last_mid_at_jump|`. If the price has moved further from the jump point (not reverted), this can be another large `r`, immediately re-triggering the kill switch. The engine may never resume trading during a sustained trend.

**Fix:** After cooldown expires, reset `_last_underlying_mid = None` (or set it to the current spot) so the first post-cooldown return is computed from a fresh reference.

---

**[HIGH] Whalley-Wilmott band formula has incorrect squaring**  
Lines: 284–293

The code:
```python
gamma_s2 = g.gamma * spot * spot          # = Γ * S²
band = factor * (lam * gamma_s2 * gamma_s2 / (gamma_risk * sigma * sigma)) ** (1/3)
#             = factor * (λ * Γ² * S⁴ / (γ * σ²))^(1/3)
```

The standard Whalley-Wilmott delta hedge bandwidth is `factor * (λ * Γ² * S²)^(1/3)` (simplified at r=0 with time). The code has `Γ²·S⁴` in the numerator (an extra `S²` factor because `gamma_s2` is squared, not `g.gamma` squared). For `S=10000` (Volcanic Rock), the extra `S²` factor inflates the band by `(S²/σ²)^(1/3) = (10^8 / 0.04)^(1/3) ≈ 3,000×`. The WW band will be orders of magnitude too wide and **delta hedging will almost never trigger**, regardless of the threshold setting.

Note: the engine has `delta_hedge_enabled=False` by default, so this bug does not affect production behavior unless the hedge is explicitly enabled.

**Fix:** Use `g.gamma * g.gamma * spot * spot` instead of `gamma_s2 * gamma_s2`:
```python
band = factor * (lam * g.gamma * g.gamma * spot * spot / (gamma_risk * sigma * sigma)) ** (1/3)
```

---

### OK

- `aggregate_delta = sum(pos_i * delta_i)`: correct. Each voucher position contributes `position × delta`. The aggregate hedge rounds this to integer units of the underlying.
- Division by zero in jump detection: guarded by `ewma_abs_r > 0`.
- `_step_voucher` correctly separates bid/ask clipping with `min(bid_price, best_ask - 1)` and `max(ask_price, best_bid + 1)` to avoid crossing.

---

## File: `src/engines/stat_arb.py`

### CONFIRMED BUGS

**[CRITICAL] Both sell-local and buy-local orders can be emitted in the same tick**  
Lines: 134–170

Both the sell-local branch (lines 135–151) and the buy-local branch (lines 153–170) execute unconditionally within the same tick. With negative tariffs (subsidies), both arb directions can be open simultaneously:

- `sell_be = remote.ask + transport + import_tariff` (reduced by subsidy)
- `buy_be = remote.bid - transport - export_tariff` (increased by subsidy)

If `sell_be < local_bid` AND `local_ask < buy_be`, both branches produce orders — a sell and a buy on the **same product in the same tick**. This is a self-crossing order pair and is an invalid state in Prosperity's exchange model.

Additionally, the squeeze-regime overlay (lines 172–185) can **add a BUY order** even when the sell-local arb branch has already added a SELL order in the same tick:
```
orders = [SELL (from sell-local arb), BUY (from squeeze overlay)]
```
No guard prevents this.

**Fix:** Pick one direction per tick. Compute both edges and emit only the side with the larger edge:
```python
if sell_edge > 0 and sell_edge >= buy_edge:
    # emit sell only
elif buy_edge > 0:
    # emit buy only
# squeeze overlay: only if direction agrees with above (or no arb open)
```

---

**[MEDIUM] Observe-before-regime bias in `RegimeDetector`**  
Lines: 106–107 (stat_arb.py), and `RegimeDetector.regime()` in layer.py

```python
self._regime.observe(external_signal_value)   # adds to history
regime = self._regime.regime(external_signal_value)  # value already in history
```

The current value is included in the history that computes its own percentile. This creates a mild look-ahead bias: if the current value is an extreme outlier, it shifts the percentile thresholds in its own favor (pushes the 75th percentile up, making "glut" harder to trigger). For a slow external signal (e.g., sunlight hours), this is negligible. For a fast-moving signal, it can dampen regime transitions.

**Fix:** swap the order: compute regime first, then observe. Or pass the history without the current value to `regime()`.

---

## File: `src/engines/counterparty_intel.py`

### CONFIRMED BUGS

**[HIGH] Fingerprint hash is unstable across mid-price movements**  
Lines: 166–176

```python
aggressor = "B" if trade.price > mid else "S"
key = f"{product}:{aggressor}:{qty_bucket}"
return hashlib.md5(key.encode()).hexdigest()
```

The aggressor classification (`B` vs `S`) flips when the market mid crosses the trade price. The same counterparty bot trading at the same price gets a different hash (`...B...` vs `...S...`) depending on whether mid is above or below that price tick. In a market where mid oscillates around a tick boundary, a single bot will be tracked under **two different fingerprint IDs**, splitting its trade history and causing both IDs to have low trade counts, preventing classification.

This also means the classifier double-counts the same bot's trades under two IDs, potentially classifying the same bot as both "informed" and "MM" at different mids.

---

**[HIGH] Win-rate is permanently downward biased for high-frequency counterparties**  
Lines: 81–83, 200–201, 216–220

`_pending_fills` is a `deque(maxlen=10000)`. When a counterparty generates more than 10,000 fills, old entries are silently dropped from the deque **before** `_resolve_pending` can score them. The `state.wins` counter never gets incremented for those dropped fills, but `state.trade_count` was already incremented in `_record_fill`. The win rate `wins / trade_count` permanently underestimates truth for active counterparties.

**Fix:** Either increase `maxlen`, or decouple trade counting from forward-resolution (e.g., track `pending_win_count` separately from trades that have been resolved).

---

**[MEDIUM] `cum_pnl` measures entry quality vs mid, not directional P&L**  
Lines: 191–192

```python
entry_pnl = (mid - price) * side * qty
state.cum_pnl += entry_pnl
```

For a buy (side=+1): `pnl = (mid - price) * qty`. This is positive only if the bot bought **below mid**. An informed bot that routinely buys at mid (e.g., by lifting the offer when the offer is at mid) will have `entry_pnl ≈ 0` and a non-positive `cum_pnl`. The `_classify` check `state.cum_pnl > 0` will **fail to classify this informed bot**, even if `win_rate > 0.55` and `max_position_abs > 10`.

The forward-horizon win rate (`state.wins`) is the correct measure of informed flow. The `cum_pnl` gate adds a false-negative condition.

---

**[LOW] `_resolve_pending` silently drops matured fills with missing snapshots**  
Lines: 211–213

```python
snap = portfolio.for_product(product)
if snap is None or snap.mid is None:
    continue
```

When a product is absent from the portfolio snapshot (e.g., a product that was delisted or not included in a tick's update), matured pending fills are dropped. The `state.wins` counter is not updated, but `state.trade_count` was already incremented. This has the same downward bias effect as the maxlen issue above, for products that occasionally disappear from snapshots.

---

## Cross-File Issues

**StatArb + SST interaction:** If the StatArbEngine feeds its contradictory orders into an SST-based execution primitive, the SST's position-based logic can compound the contradiction. The SST will try to maintain capacity bounds based on a single `position` integer, but if two orders for the same product arrive in one tick, the fill model is undefined.

**Hysteresis kill zone + BasketArb target tracking:** When `target_position` returns `current_position` (kill zone), `_current_target_basket` stores that frozen value. If the actual fill arrives later and moves `current_basket_pos` away from the frozen target, the next tick's `basket_delta` correctly reflects the actual divergence. No bug here, but the kill zone freezes the *target*, not the *position*, which means the engine may issue small orders to maintain the kill-zone-frozen target if market fills partially execute.

---

## Fix Priority

| Priority | Fix | Estimated effort |
|---|---|---|
| 1 | `bsm.py`: add `if f_lo == 0: return lo` before bisection | 2 lines |
| 2 | `sweep_selector.py`: fix tie-break for negative scores | 1 line |
| 3 | `signal_validation.py`: fix walk_forward sign check | 1 line |
| 4 | `stat_arb.py`: mutex sell-local vs buy-local per tick | ~15 lines |
| 5 | `hysteresis_sizer.py`: fix kill zone wrong-sign freeze | ~5 lines |
| 6 | `options_mm.py`: fix WW formula squaring | 1 line |
| 7 | `options_mm.py`: fix SMA vs EWMA in jump detection | ~5 lines |
| 8 | `options_mm.py`: reset last_mid after cooldown | 1 line |
| 9 | `counterparty_intel.py`: fingerprint without mid dependence | ~5 lines |
| 10 | `smile.py`: fix/rename moneyness formula | 1 line + docstring |

