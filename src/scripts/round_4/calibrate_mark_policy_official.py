"""Apply historical Mark hazard rules to an official simulator log.

This is a calibration check for `audit_mark_policy_hazard.py`. It does not
train on official data; it rebuilds the same panels from one official log and
evaluates the historical rule thresholds.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.scripts.round_4.audit_mark_behavior_classification import (
    _actor_rows,
    _attach_book,
    _book_features,
    _load_official,
)
from src.scripts.round_4.audit_mark_policy_hazard import (
    TARGETS,
    _build_panel_for_target,
    _evaluate_rule,
)


DEFAULT_RULES = Path("outputs/round_4/mark_policy/all_loo_rules.csv")
DEFAULT_LOG = Path("/Users/abhinavgupta/Desktop/IMC/r4 Sim Results/sellonly/497595.log")
DEFAULT_OUT = Path("outputs/round_4/mark_policy/official_rule_calibration.csv")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--official-log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    rules = pd.read_csv(args.rules)
    prices, trades = _load_official(args.official_log)
    book = _book_features(prices)
    actors = _actor_rows(_attach_book(trades, book))

    rows = []
    for spec in TARGETS:
        spec_rules = rules[rules["target"] == spec.label]
        if spec_rules.empty:
            continue
        panel = _build_panel_for_target(spec, book, actors, trades)
        for rule in spec_rules.itertuples(index=False):
            event_col = f"{rule.target}_event_{int(rule.horizon)}"
            qty_col = f"{rule.target}_qty_{int(rule.horizon)}"
            if str(rule.feature) not in panel.columns:
                continue
            metrics = _evaluate_rule(
                panel,
                event_col,
                qty_col,
                str(rule.feature),
                str(rule.direction),
                float(rule.threshold),
            )
            rows.append(
                {
                    "target": rule.target,
                    "horizon": int(rule.horizon),
                    "source_holdout_day": int(rule.holdout_day),
                    "train_rank": int(rule.train_rank),
                    "feature": rule.feature,
                    "direction": rule.direction,
                    "quantile": float(rule.quantile),
                    "threshold": float(rule.threshold),
                    "historical_train_lift": float(rule.train_lift),
                    "historical_test_lift": float(rule.test_lift),
                    "official_support": int(metrics["support"]),
                    "official_positives": int(metrics["positives"]),
                    "official_event_rate": float(metrics["event_rate"]),
                    "official_base_rate": float(metrics["base_rate"]),
                    "official_lift": float(metrics["lift"]),
                    "official_qty_coverage": float(metrics["qty_coverage"]),
                    "official_mean_future_qty": float(metrics["mean_future_qty"]),
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(
            ["official_lift", "official_qty_coverage", "historical_test_lift"],
            ascending=[False, False, False],
            inplace=True,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(out.to_string(index=False))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
