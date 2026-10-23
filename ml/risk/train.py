"""Train the renewal-risk models (N9) on simulated event logs and report metrics.

    apps/api/.venv/Scripts/python ml/risk/train.py --out models

Two models, following the predictive-monitoring benchmark's advice: a classifier for
P(renewal is late) and a direct regressor for days late (negative = early), instead of
recursive suffix prediction. Split is by institution, so no institution appears in both
train and test. All numbers are on synthetic data.
"""

import argparse
import json
import random
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.modules.risk.features import FEATURE_NAMES, History, features  # noqa: E402
from simulate import Institution, simulate  # noqa: E402

DECISION_POINTS = list(range(120, 0, -7))  # days before maturity at which risk is scored


def history_at(
    inst: Institution, cycle_index: int, days_before: int, rng: random.Random
) -> History:
    cycle = inst.cycles[cycle_index]
    as_of = cycle.maturity - timedelta(days=days_before)
    return History(
        as_of=as_of,
        maturity=cycle.maturity,
        amount=cycle.amount,
        open_flags=np_poisson(rng, inst.flags_rate),
        renewals=[(c.maturity, c.submitted) for c in inst.cycles[:cycle_index]],
        response_days=[d for when, d in inst.responses if when <= as_of],
        action_dates=[a for a in inst.actions if a <= as_of],
    )


def np_poisson(rng: random.Random, lam: float) -> int:
    count, threshold, product = 0, np.exp(-lam), rng.random()
    while product > threshold:
        count += 1
        product *= rng.random()
    return count


def label(cycle) -> tuple[int, float]:
    if cycle.submitted is None:
        return 1, 120.0
    days_late = float((cycle.submitted - cycle.maturity).days)
    return int(days_late > 0), days_late


def dataset(institutions: list[Institution], seed: int, points=DECISION_POINTS):
    rng = random.Random(seed)
    X, y_cls, y_reg, groups = [], [], [], []
    for inst_index, inst in enumerate(institutions):
        for cycle_index, cycle in enumerate(inst.cycles):
            if cycle_index == 0:
                continue  # need at least one earlier cycle for a prefix
            late, days = label(cycle)
            for days_before in points:
                X.append(features(history_at(inst, cycle_index, days_before, rng)))
                y_cls.append(late)
                y_reg.append(days)
                groups.append((inst_index, cycle_index, days_before))
    return np.array(X), np.array(y_cls), np.array(y_reg), groups


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "models")
    parser.add_argument("--institutions", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--alarm-threshold", type=float, default=0.7)
    args = parser.parse_args()

    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error, roc_auc_score

    institutions = simulate(args.institutions, args.seed)
    n = len(institutions)
    train_end, val_end = int(n * 0.6), int(n * 0.8)
    X_tr, yc_tr, yr_tr, _ = dataset(institutions[:train_end], args.seed)
    X_va, yc_va, yr_va, _ = dataset(institutions[train_end:val_end], args.seed + 2)
    X_te, yc_te, yr_te, g_te = dataset(institutions[val_end:], args.seed + 1)

    params = {
        "objective": "binary",
        "learning_rate": 0.03,
        "num_leaves": 15,
        "min_data_in_leaf": 120,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 5.0,
        "verbose": -1,
        "seed": args.seed,
    }
    stop = [lgb.early_stopping(50, verbose=False)]
    train_set = lgb.Dataset(X_tr, yc_tr, feature_name=FEATURE_NAMES)
    classifier = lgb.train(
        params,
        train_set,
        num_boost_round=2000,
        valid_sets=[lgb.Dataset(X_va, yc_va, reference=train_set)],
        callbacks=stop,
    )
    reg_params = params | {"objective": "regression_l1"}
    reg_set = lgb.Dataset(X_tr, yr_tr, feature_name=FEATURE_NAMES)
    regressor = lgb.train(
        reg_params,
        reg_set,
        num_boost_round=2000,
        valid_sets=[lgb.Dataset(X_va, yr_va, reference=reg_set)],
        callbacks=stop,
    )
    split = train_end

    p = classifier.predict(X_te)
    auc = roc_auc_score(yc_te, p)
    mae = mean_absolute_error(yr_te, regressor.predict(X_te))

    # Lead time: for each late cycle, the earliest decision point at which risk >= threshold.
    first_alarm: dict[tuple[int, int], int] = {}
    caught_cycles, late_cycles = set(), set()
    for (inst, cyc, days_before), prob, late in zip(g_te, p, yc_te, strict=True):
        if not late:
            continue
        late_cycles.add((inst, cyc))
        if prob >= args.alarm_threshold:
            caught_cycles.add((inst, cyc))
            first_alarm[(inst, cyc)] = max(first_alarm.get((inst, cyc), 0), days_before)
    on_time_alarms = sum(
        1
        for (i, c, d), prob, late in zip(g_te, p, yc_te, strict=True)
        if not late and prob >= args.alarm_threshold and d == 30
    )
    on_time_points = sum(
        1 for (i, c, d), late in zip(g_te, yc_te, strict=True) if not late and d == 30
    )

    importance = dict(
        zip(FEATURE_NAMES, classifier.feature_importance("gain").round(1).tolist(), strict=True)
    )
    metrics = {
        "data": "synthetic (simulated event logs)",
        "institutions_train": split,
        "institutions_validation": val_end - train_end,
        "institutions_test": n - val_end,
        "boosting_rounds": classifier.best_iteration,
        "auc": round(float(auc), 4),
        "regressor_mae_days": round(float(mae), 2),
        "alarm_threshold": args.alarm_threshold,
        "late_cycles_caught": round(len(caught_cycles) / max(1, len(late_cycles)), 4),
        "mean_lead_time_days": round(float(np.mean(list(first_alarm.values()))), 1)
        if first_alarm
        else None,
        "false_alarm_rate_at_T30_on_time_cycles": round(on_time_alarms / max(1, on_time_points), 4),
        "feature_importance_gain": importance,
    }
    out = args.out / "renewal_risk"
    out.mkdir(parents=True, exist_ok=True)
    classifier.save_model(str(out / "classifier.txt"))
    regressor.save_model(str(out / "regressor.txt"))
    (out / "meta.json").write_text(
        json.dumps({"features": FEATURE_NAMES, "alarm_threshold": args.alarm_threshold}, indent=2),
        encoding="utf-8",
    )
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
