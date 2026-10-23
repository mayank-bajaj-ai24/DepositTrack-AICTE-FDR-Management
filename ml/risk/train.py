"""Train the renewal-risk method (N9) on a real public event log, as a proxy, and report it.

There is no public log of FDR renewals, so the method is trained and measured on the BPI
Challenge 2017 log (a Dutch bank's loan applications, CC BY 4.0, via Kaggle). Its closest
counterpart to "an institution misses its renewal" is "the customer does not return the
offer documents before the bank's deadline, so the application is cancelled".

    apps/api/.venv/Scripts/python ml/download_open_data.py bpi-2017
    apps/api/.venv/Scripts/python ml/risk/train.py --log <path>/bpi_2017_cleaned.csv

Same method as planned for DepositTrack (predictive-monitoring benchmark): prefix features at
weekly decision points while a case is open, a LightGBM classifier for P(deadline missed)
and a direct regressor for days to the outcome, SHAP contributions as reasons. The split is
by time (earlier applications train, later ones test). The model is written to
models/renewal_risk_proxy/, which the API does not load: it measures the method, it does not
score AICTE institutions (decided by the maintainer; live scoring needs DepositTrack's own
history).
"""

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATASET = "BPI Challenge 2017 loan applications (CC BY 4.0) - proxy, not FDR renewals"
MISSED, MET, EXCLUDED = "A_Cancelled", "A_Pending", "A_Denied"
OFFER_SENT = ("O_Sent (mail and online)", "O_Sent (online only)")
DECAY_DAYS = 7.0
STEP = timedelta(days=7)
FEATURE_NAMES = [
    "days_since_created",
    "days_since_first_offer",
    "offers_sent",
    "offers_returned",
    "incomplete_count",
    "calls_incomplete_files",
    "calls_after_offers",
    "events_last_7d",
    "activity_decay",
    "days_since_last_event",
    "log_requested_amount",
    "is_limit_raise",
]


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def read_cases(log: Path) -> dict[str, dict]:
    cases: dict[str, dict] = defaultdict(lambda: {"events": []})
    with open(log, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            case = cases[row["case:concept:name"]]
            case["events"].append(
                (_ts(row["time:timestamp"]), row["concept:name"], row["lifecycle:transition"])
            )
            case["amount"] = float(row["case:RequestedAmount"] or 0)
            case["limit_raise"] = row["case:ApplicationType"] == "Limit raise"
    for case in cases.values():
        case["events"].sort()
    return cases


def outcome(case: dict) -> tuple[str, datetime] | None:
    for ts, name, _ in case["events"]:
        if name in (MISSED, MET, EXCLUDED):
            return name, ts
    return None


def prefix_features(case: dict, at: datetime) -> list[float]:
    seen = [e for e in case["events"] if e[0] <= at]
    created = seen[0][0]
    sent = [ts for ts, name, _ in seen if name in OFFER_SENT]
    last = seen[-1][0]
    day = 86400.0

    def count(name: str, transition: str | None = None) -> int:
        return sum(1 for _, n, t in seen if n == name and (transition is None or t == transition))

    return [
        (at - created).total_seconds() / day,
        (at - sent[0]).total_seconds() / day if sent else -1.0,
        float(len(sent)),
        float(count("O_Returned")),
        float(count("A_Incomplete")),
        float(count("W_Call incomplete files", "start")),
        float(count("W_Call after offers", "start")),
        float(sum(1 for ts, _, _ in seen if (at - ts).total_seconds() <= 7 * day)),
        float(sum(math.exp(-(at - ts).total_seconds() / day / DECAY_DAYS) for ts, _, _ in seen)),
        (at - last).total_seconds() / day,
        math.log1p(case["amount"]),
        float(case["limit_raise"]),
    ]


def decision_points(cases: dict[str, dict]):
    """Weekly points from the first offer sent until the outcome; one row each."""
    rows = []
    for case_id, case in cases.items():
        result = outcome(case)
        if result is None or result[0] == EXCLUDED:
            continue
        name, ended = result
        sent = [ts for ts, n, _ in case["events"] if n in OFFER_SENT]
        if not sent or sent[0] >= ended:
            continue
        at = sent[0]
        while at < ended:
            rows.append(
                {
                    "case": case_id,
                    "created": case["events"][0][0],
                    "at": at,
                    "x": prefix_features(case, at),
                    "missed": int(name == MISSED),
                    "days_to_outcome": (ended - at).total_seconds() / 86400.0,
                    "ended": ended,
                }
            )
            at += STEP
    return rows


def case_split(rows: list[dict], train: float, val: float):
    order = sorted({(r["created"], r["case"]) for r in rows})
    ids = [c for _, c in order]
    a, b = int(len(ids) * train), int(len(ids) * (train + val))
    part = (
        {c: "train" for c in ids[:a]} | {c: "val" for c in ids[a:b]} | {c: "test" for c in ids[b:]}
    )
    out: dict[str, list[dict]] = {"train": [], "val": [], "test": []}
    for r in rows:
        out[part[r["case"]]].append(r)
    return out


def per_case_alarm(rows: list[dict], probs: np.ndarray, threshold: float):
    """Per case: missed or not, and the first decision point whose risk reached the threshold."""
    cases: dict[str, dict] = {}
    for r, p in zip(rows, probs, strict=True):
        c = cases.setdefault(r["case"], {"missed": r["missed"], "ended": r["ended"], "first": None})
        if p >= threshold and (c["first"] is None or r["at"] < c["first"]):
            c["first"] = r["at"]
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True, help="bpi_2017_cleaned.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "models")
    parser.add_argument("--target-false-alarm", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error, roc_auc_score

    print("reading log", flush=True)
    rows = decision_points(read_cases(args.log))
    parts = case_split(rows, 0.6, 0.2)

    def arrays(part: str):
        data = parts[part]
        X = np.array([r["x"] for r in data])
        return (
            X,
            np.array([r["missed"] for r in data]),
            np.array([r["days_to_outcome"] for r in data]),
        )

    X_tr, yc_tr, yr_tr = arrays("train")
    X_va, yc_va, yr_va = arrays("val")
    X_te, yc_te, yr_te = arrays("test")
    params = {
        "objective": "binary",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 50,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "seed": args.seed,
        "verbose": -1,
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

    # Alarm threshold from validation cases: at most the target share of met deadlines
    # ever alarmed.
    p_va = classifier.predict(X_va)
    met_max: dict[str, float] = {}
    for r, p in zip(parts["val"], p_va, strict=True):
        if not r["missed"]:
            met_max[r["case"]] = max(met_max.get(r["case"], 0.0), float(p))
    threshold = float(np.quantile(list(met_max.values()), 1 - args.target_false_alarm))

    p_te = classifier.predict(X_te)
    cases = per_case_alarm(parts["test"], p_te, threshold)
    missed = [c for c in cases.values() if c["missed"]]
    met = [c for c in cases.values() if not c["missed"]]
    caught = [c for c in missed if c["first"] is not None]
    leads = [(c["ended"] - c["first"]).total_seconds() / 86400.0 for c in caught]

    contrib = classifier.predict(X_te, pred_contrib=True)[:, :-1]
    mean_abs = np.abs(contrib).mean(axis=0)
    reasons = dict(
        sorted(zip(FEATURE_NAMES, mean_abs.round(4).tolist(), strict=True), key=lambda kv: -kv[1])
    )
    metrics = {
        "data": DATASET,
        "cases_train": len({r["case"] for r in parts["train"]}),
        "cases_validation": len({r["case"] for r in parts["val"]}),
        "cases_test": len(cases),
        "decision_points_test": len(parts["test"]),
        "boosting_rounds": classifier.best_iteration,
        "auc_decision_points": round(float(roc_auc_score(yc_te, p_te)), 4),
        "regressor_mae_days": round(float(mean_absolute_error(yr_te, regressor.predict(X_te))), 2),
        "alarm_threshold": round(threshold, 4),
        "missed_cases_caught": round(len(caught) / max(1, len(missed)), 4),
        "met_cases_false_alarm": round(
            sum(c["first"] is not None for c in met) / max(1, len(met)), 4
        ),
        "mean_lead_time_days": round(float(np.mean(leads)), 1) if leads else None,
        "median_lead_time_days": round(float(np.median(leads)), 1) if leads else None,
        "mean_abs_shap": reasons,
    }
    out = args.out / "renewal_risk_proxy"
    out.mkdir(parents=True, exist_ok=True)
    classifier.save_model(str(out / "classifier.txt"))
    regressor.save_model(str(out / "regressor.txt"))
    (out / "meta.json").write_text(
        json.dumps(
            {
                "features": FEATURE_NAMES,
                "alarm_threshold": threshold,
                "data": DATASET,
                "live_scoring": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
