"""End-to-end smoke test for the Round-2 export pipeline.

Covers the full path:
    factory → bundle build → bid wrap → AST compression →
    write to disk → exec in clean namespace → instantiate Trader →
    bid()/run() contract.

The unit tests already cover individual layers (bid plumbing,
day-rollover flush, kill-switch evaluator, validator). This file
catches the **integration** failures that only show up when you
actually exec the bundled `.py` — bundler layout drift, missing
imports in the inlined strategies, subtle name collisions between
the live engine and the inlined classes, etc.

Tests run for two `--bid` values (0 and 2300) so we cover both the
Round-1-shape unwrapped path and the Round-2 `with_bid_value`
wrapped path.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.datamodel import Listing, Order, OrderDepth, TradingState
from src.scripts.round_2.export_round2_submission import export_variant_to_path
from src.scripts.validate_submission import validate_source

ASH = "ASH_COATED_OSMIUM"
PEPPER = "INTARIAN_PEPPER_ROOT"


def _build_state() -> TradingState:
    """Construct a minimal TradingState for both Round-2 products.

    Mids chosen near the empirical R2 day_0 opening prices (PEPPER
    ~12 998, ASH ~10 007) so the strategies operate in a realistic
    range. Position 0 — strategies will fire opening-phase logic.
    """
    ash_depth = OrderDepth()
    ash_depth.buy_orders = {9998: 21}
    ash_depth.sell_orders = {10016: -13}

    pep_depth = OrderDepth()
    pep_depth.buy_orders = {12990: 20}
    pep_depth.sell_orders = {13007: -11}

    return TradingState(
        traderData="",
        timestamp=0,
        listings={
            ASH: Listing(symbol=ASH, product=ASH, denomination="XIRECS"),
            PEPPER: Listing(symbol=PEPPER, product=PEPPER, denomination="XIRECS"),
        },
        order_depths={ASH: ash_depth, PEPPER: pep_depth},
        own_trades={ASH: [], PEPPER: []},
        market_trades={ASH: [], PEPPER: []},
        position={ASH: 0, PEPPER: 0},
        observations={},  # type: ignore[arg-type]
    )


def _exec_bundle(bundle_path: Path, module_name: str) -> Any:
    """Exec a bundled submission file in an isolated module namespace.

    The bundle imports ``from datamodel import ...``; we shim that
    to the repo's ``src.datamodel`` so the bundle resolves on the
    test host. The new module is registered in ``sys.modules`` (the
    Python 3.14 dataclass machinery requires this for frozen
    dataclasses to bind correctly).
    """
    sys.modules.setdefault(
        "datamodel",
        __import__(
            "src.datamodel",
            fromlist=["Order", "OrderDepth", "Trade", "TradingState", "Listing"],
        ),
    )
    spec = importlib.util.spec_from_file_location(module_name, bundle_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load bundle spec for {bundle_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    except Exception:
        # Clean up the failed registration so a subsequent test does
        # not pick up a half-loaded module.
        sys.modules.pop(module_name, None)
        raise


@pytest.fixture
def clean_sys_modules() -> None:
    """Drop any test-bundle modules registered by previous tests."""
    keys_to_drop = [k for k in sys.modules if k.startswith("r2_e2e_")]
    for k in keys_to_drop:
        del sys.modules[k]


@pytest.mark.integration
@pytest.mark.parametrize("bid", [0, 2_300])
def test_export_round2_bundle_executes_and_returns_correct_bid(
    bid: int, clean_sys_modules: None, tmp_path: Path
) -> None:
    """Full pipeline: export → exec → bid() and run() contract."""
    output = export_variant_to_path(out_dir=tmp_path, bid_value=bid)
    assert output.exists()
    assert output.stat().st_size > 50_000, "bundle suspiciously small"

    # Validator must accept the freshly exported file.
    report = validate_source(output.read_text())
    assert report.ok, f"validator rejected fresh bundle: {report.format()}"

    module = _exec_bundle(output, f"r2_e2e_bid_{bid}")
    trader = module.Trader()

    # Contract #1: bid() returns the embedded value, regardless of
    # whether `with_bid_value` wrapping was applied.
    assert trader.bid() == bid

    # Contract #2: the engine config carries the same bid_value.
    assert trader.config.bid_value == bid

    # Contract #3: both R2 products are configured in the bundle.
    assert ASH in trader.config.products
    assert PEPPER in trader.config.products

    # Contract #4: research strategies are registered (the bundler
    # extends KNOWN_STRATEGY_NAMES + STRATEGY_REGISTRY at runtime).
    assert "ash_ladder" in trader.strategies
    assert "pepper_core_long" in trader.strategies

    # Contract #5: run(state) returns a 3-tuple with the expected
    # shape (orders dict, conversions int, traderData str).
    state = _build_state()
    result = trader.run(state)
    assert isinstance(result, tuple) and len(result) == 3
    orders, conversions, trader_data = result
    assert isinstance(orders, dict)
    assert isinstance(conversions, int) and conversions == 0
    assert isinstance(trader_data, str) and len(trader_data) > 0

    # Contract #6: orders, where present, are well-formed Order
    # instances for the configured products.
    for product, product_orders in orders.items():
        assert product in {ASH, PEPPER}
        for order in product_orders:
            assert isinstance(order, Order)
            assert isinstance(order.price, int)
            assert isinstance(order.quantity, int)
            assert order.quantity != 0


@pytest.mark.integration
def test_export_round2_bundle_has_no_residual_src_imports(tmp_path: Path) -> None:
    """The bundle must be self-contained — no `from src.*` imports.

    This is also enforced by the validator, but we add an explicit
    test so a regression in the bundler surfaces with a clear name.
    """
    output = export_variant_to_path(out_dir=tmp_path, bid_value=0)
    body = output.read_text()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import src.", "from src.", "from src ", "import src ")):
            raise AssertionError(
                f"Round-2 bundle leaks src.* import: {stripped!r}"
            )


@pytest.mark.integration
def test_export_round2_bundle_does_not_publish_param_dump(tmp_path: Path) -> None:
    """Per batch-E review F6: the shipped bundle must NOT contain a
    grep-able dump of our ladder edges / weights / kill-switch
    thresholds. Two layers of protection both apply:
    (1) build_bundle(redact_params=True) strips the param dump from
        the banner; and
    (2) the AST-compress step in this export removes ALL comments
        anyway, including any unredacted banner.

    This test asserts the *outcome* — competitor reading the uploaded
    file cannot grep for the param-dump labels — independent of which
    layer is doing the work, so a regression in either still fails
    here.
    """
    output = export_variant_to_path(out_dir=tmp_path, bid_value=0)
    body = output.read_text()
    forbidden_strings = (
        "ASH params:",
        "PEPPER params:",
        "Embedded product configs:",
    )
    for needle in forbidden_strings:
        assert needle not in body, (
            f"Bundle is leaking {needle!r} — banner redaction OR "
            "AST-compress comment-strip has regressed."
        )


@pytest.mark.integration
def test_export_round2_bundle_bid_wrapping_visible_in_source(tmp_path: Path) -> None:
    """The factory-call rewrite must produce one of two known shapes:
    `... or {factory}()` for bid=0, or `... or with_bid_value({factory}(), N)`
    for bid > 0. Catches regressions in `_wrap_factory_call_with_bid`.
    """
    out_zero = export_variant_to_path(out_dir=tmp_path / "bid0", bid_value=0)
    out_2300 = export_variant_to_path(out_dir=tmp_path / "bid2300", bid_value=2_300)
    body_zero = out_zero.read_text()
    body_2300 = out_2300.read_text()
    assert (
        "self.config = config or round2_v5micro_wide113_engine_config()"
        in body_zero
    ), "bid=0 export should leave the factory call unwrapped"
    assert (
        "with_bid_value(round2_v5micro_wide113_engine_config(), 2300)"
        in body_2300
    ), "bid=2300 export should wrap the factory call"
