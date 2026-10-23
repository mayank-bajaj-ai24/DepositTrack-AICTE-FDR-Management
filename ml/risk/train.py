"""Train the renewal-risk method (N9) on a real public event log, as a proxy, and report it.

There is no public log of FDR renewals, so the method is trained and measured on the BPI
Challenge 2017 log (a Dutch bank's loan applications, CC BY 4.0, via Kaggle). Its closest
counterpart to "an institution misses its renewal" is "the customer does not return the
offer documents, so the system cancels the application when the deadline lapses".

    apps/api/.venv/Scripts/python ml/download_open_data.py bpi-2017
    apps/api/.venv/Scripts/python ml/risk/train.py --out models

Labels (decided per case, from what happened first after the first offer was sent):
- missed (1): the application is cancelled by the system (User_1, the deadline lapse) before
  any offer is returned;
- not missed (0): an offer is returned, or staff cancel (customer withdrew) or deny the
  application before any return. No case is dropped for its outcome, so the test population
  is the one the model would have to score.
Decision points are weekly from the first offer sent until that first outcome (the returned
documents end the question). Cases whose first offer falls within CENSOR_DAYS of the end of
the log are left out, since their deadline cannot have lapsed yet.

Same method as planned for DepositTrack (predictive-monitoring benchmark): prefix features at
weekly decision points, a LightGBM classifier for P(deadline missed) and a direct regressor
for days to the outcome, SHAP contributions as reasons. The split is by time (earlier
applications train, later ones test). The AUC is reported pooled over all decision points and
per week since the first offer, next to simple hand-rule baselines, because the pooled figure
mostly measures how long a case has been open. The model is written to
models/renewal_risk_proxy/, which the API does not load: it measures the method, it does not
score AICTE institutions (decided by the maintainer; live scoring needs DepositTrack's own
history). The pipeline functions after the BPI-specific part (case_split, case_scores,
calibrate_threshold, alarm_summary) take plain rows and are not tied to this log.
"""

import argparse
import csv
import json
import math
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = ROOT / "data" / "bpi-2017" / "bpi_2017_cleaned.csv"
DATASET = "BPI Challenge 2017 loan applications (CC BY 4.0) - proxy, not FDR renewals"
CANCELLED, DENIED, PENDING, RETURNED = "A_Cancelled", "A_Denied", "A_Pending", "O_Returned"
SYSTEM_USER = "User_1"
OFFER_SENT = ("O_Sent (mail and online)", "O_Sent (online only)")
DECAY_DAYS = 7.0
STEP = timedelta(days=7)
CENSOR_DAYS = 35
EARLY_WEEKS = 5  # weeks 0-4 after the first offer: when a warning is still useful
DAY = 86400.0
FEATURE_NAMES = [
    "days_since_created",
    "days_since_first_offer",
    "offers_sent",
    "incomplete_count",
    "calls_incomplete_files",
    "calls_after_offers",
    "events_last_7d",
    "activity_decay",
    "days_since_last_event",
    "log_requested_amount",
    "is_limit_raise",
]
BASELINES = ("days_since_first_offer", "days_since_last_event")


def _days(delta: timedelta) -> float:
    return delta.total_seconds() / DAY


def read_cases(log: Path) -> dict[str, dict]:
    """Cases by id: events as (timestamp, activity, transition, resource), in time order."""
    cases: dict[str, dict] = defaultdict(lambda: {"events": []})
    with open(log, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            case = cases[row["case:concept:name"]]
            case["events"].append(
                (
                    datetime.fromisoformat(row["time:timestamp"]),
                    row["concept:name"],
                    row["lifecycle:transition"],
                    row.get("org:resource", ""),
                )
            )
            case["amount"] = float(row["case:RequestedAmount"] or 0)
            case["limit_raise"] = row["case:ApplicationType"] == "Limit raise"
    for case in cases.values():
        case["events"].sort()
    return dict(cases)


def first_offer(case: dict) -> datetime | None:
    return next((ts for ts, name, *_ in case["events"] if name in OFFER_SENT), None)


def outcome(case: dict) -> tuple[int, datetime] | None:
    """(missed, when) from the case's first decisive event, or None while it is open."""
    for ts, name, _, resource in case["events"]:
        if name == RETURNED or name in (DENIED, PENDING):
            return 0, ts
        if name == CANCELLED:
            return int(resource == SYSTEM_USER), ts
    return None


def prefix_rows(case: dict, points: list[datetime]) -> list[list[float]]:
    """Features at each decision point, in one forward pass over the case's events."""
    events = case["events"]
    created = events[0][0]
    sent_first = None
    sent = incomplete = calls_incomplete = calls_offers = 0
    decay, decay_at = 0.0, None
    window: deque[datetime] = deque()
    last = created
    i, rows = 0, []
    for at in points:
        if decay_at is not None:
            decay *= math.exp(-_days(at - decay_at) / DECAY_DAYS)
        decay_at = at
        while i < len(events) and events[i][0] <= at:
            ts, name, transition, _ = events[i]
            i += 1
            last = ts
            window.append(ts)
            decay += math.exp(-_days(at - ts) / DECAY_DAYS)
            if name in OFFER_SENT:
                sent += 1
                sent_first = sent_first or ts
            elif name == "A_Incomplete":
                incomplete += 1
            elif name == "W_Call incomplete files" and transition == "start":
                calls_incomplete += 1
            elif name == "W_Call after offers" and transition == "start":
                calls_offers += 1
        while window and _days(at - window[0]) > 7:
            window.popleft()
        rows.append(
            [
                _days(at - created),
                _days(at - sent_first) if sent_first else -1.0,
                float(sent),
                float(incomplete),
                float(calls_incomplete),
                float(calls_offers),
                float(len(window)),
                decay,
                _days(at - last),
                math.log1p(case["amount"]),
                float(case["limit_raise"]),
            ]
        )
    return rows


def decision_points(cases: dict[str, dict], censor_days: int = CENSOR_DAYS):
    """Weekly points from the first offer until the first outcome; one row each.

    Returns (rows, counts): counts says how many cases were left out and why.
    """
    log_end = max(case["events"][-1][0] for case in cases.values())
    cutoff = log_end - timedelta(days=censor_days)
    rows, counts = [], {"no_offer": 0, "ended_before_offer": 0, "censored": 0, "open": 0}
    for case_id, case in cases.items():
        sent = first_offer(case)
        if sent is None:
            counts["no_offer"] += 1
            continue
        if sent > cutoff:
            counts["censored"] += 1
            continue
        result = outcome(case)
        if result is None:
            counts["open"] += 1
            continue
        missed, ended = result
        if ended <= sent:
            counts["ended_before_offer"] += 1
            continue
        points, at = [], sent
        while at < ended:
            points.append(at)
            at += STEP
        for week, (at, x) in enumerate(zip(points, prefix_rows(case, points), strict=True)):
            rows.append(
                {
                    "case": case_id,
                    "created": case["events"][0][0],
                    "at": at,
                    "week": week,
                    "x": x,
                    "missed": missed,
                    "days_to_outcome": _days(ended - at),
                    "ended": ended,
                }
            )
    return rows, counts


def case_split(rows: list[dict], train: float, val: float) -> dict[str, list[dict]]:
    """Split by case creation time: the earliest cases train, the latest test."""
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


def case_scores(rows: list[dict], probs) -> dict[str, dict]:
    """Per case: missed or not, when it ended, and its (time, probability) points in order."""
    cases: dict[str, dict] = {}
    for r, p in zip(rows, probs, strict=True):
        c = cases.setdefault(r["case"], {"missed": r["missed"], "ended": r["ended"], "points": []})
        c["points"].append((r["at"], float(p)))
    for c in cases.values():
        c["points"].sort()
    return cases


def calibrate_threshold(cases: dict[str, dict], target_false_alarm: float) -> float:
    """Lowest threshold that alarms at most the target share of not-missed cases."""
    peaks = [max(p for _, p in c["points"]) for c in cases.values() if not c["missed"]]
    if not peaks:
        raise ValueError("no not-missed cases to calibrate the alarm threshold on")
    return float(np.quantile(peaks, 1 - target_false_alarm))


def first_alarm(case: dict, threshold: float) -> datetime | None:
    return next((at for at, p in case["points"] if p >= threshold), None)


def alarm_summary(cases: dict[str, dict], threshold: float) -> dict:
    missed = [c for c in cases.values() if c["missed"]]
    met = [c for c in cases.values() if not c["missed"]]
    alarms = {id(c): first_alarm(c, threshold) for c in cases.values()}
    leads = [_days(c["ended"] - alarms[id(c)]) for c in missed if alarms[id(c)] is not None]
    return {
        "missed_cases_caught": round(len(leads) / max(1, len(missed)), 4),
        "not_missed_cases_false_alarm": round(
            sum(alarms[id(c)] is not None for c in met) / max(1, len(met)), 4
        ),
        "mean_lead_time_days": round(float(np.mean(leads)), 1) if leads else None,
        "median_lead_time_days": round(float(np.median(leads)), 1) if leads else None,
    }


def auc_by_week(rows: list[dict], scores, weeks: int = EARLY_WEEKS) -> dict:
    """AUC pooled, per week since the first offer, and the size-weighted mean of early weeks."""
    from sklearn.metrics import roc_auc_score

    y = np.array([r["missed"] for r in rows])
    scores = np.asarray(scores, dtype=float)
    week = np.array([r["week"] for r in rows])
    by_week, sizes = {}, {}
    for w in range(weeks):
        mask = week == w
        if mask.any() and len(set(y[mask])) == 2:
            by_week[str(w)] = round(float(roc_auc_score(y[mask], scores[mask])), 4)
            sizes[str(w)] = int(mask.sum())
    total = sum(sizes.values())
    return {
        "pooled": round(float(roc_auc_score(y, scores)), 4),
        "by_week": by_week,
        f"weighted_mean_weeks_0_{weeks - 1}": round(
            sum(by_week[w] * sizes[w] for w in by_week) / total, 4
        )
        if total
        else None,
    }


def check_parts(parts: dict[str, list[dict]]) -> None:
    for name, data in parts.items():
        labels = {r["missed"] for r in data}
        if labels != {0, 1}:
            raise SystemExit(
                f"the {name} split has {len(data)} decision points and labels {sorted(labels)}; "
                "it needs both missed and not-missed cases"
            )


def false_alarm_share(value: str) -> float:
    share = float(value)
    if not 0 < share < 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1 (exclusive)")
    return share


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log", type=Path, default=DEFAULT_LOG, help="bpi_2017_cleaned.csv (default: %(default)s)"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "models")
    parser.add_argument("--target-false-alarm", type=false_alarm_share, default=0.10)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    if not args.log.exists():
        raise SystemExit(
            f"{args.log} not found; run ml/download_open_data.py bpi-2017 or pass --log"
        )

    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error

    print("reading log", flush=True)
    rows, left_out = decision_points(read_cases(args.log))
    parts = case_split(rows, 0.6, 0.2)
    check_parts(parts)

    def arrays(part: str):
        data = parts[part]
        return (
            np.array([r["x"] for r in data]),
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

    threshold = calibrate_threshold(
        case_scores(parts["val"], classifier.predict(X_va)), args.target_false_alarm
    )
    p_te = classifier.predict(X_te)
    test_cases = case_scores(parts["test"], p_te)

    contrib = classifier.predict(X_te, pred_contrib=True)[:, :-1]
    mean_abs = np.abs(contrib).mean(axis=0)
    reasons = dict(
        sorted(zip(FEATURE_NAMES, mean_abs.round(4).tolist(), strict=True), key=lambda kv: -kv[1])
    )
    metrics = {
        "data": DATASET,
        "cases_train": len({r["case"] for r in parts["train"]}),
        "cases_validation": len({r["case"] for r in parts["val"]}),
        "cases_test": len(test_cases),
        "cases_missed_test": sum(c["missed"] for c in test_cases.values()),
        "cases_left_out": left_out,
        "decision_points_test": len(parts["test"]),
        "boosting_rounds": classifier.best_iteration,
        "auc": auc_by_week(parts["test"], p_te),
        "baseline_auc": {
            name: auc_by_week(parts["test"], X_te[:, FEATURE_NAMES.index(name)])
            for name in BASELINES
        },
        "regressor_mae_days": round(float(mean_absolute_error(yr_te, regressor.predict(X_te))), 2),
        "target_false_alarm": args.target_false_alarm,
        "alarm_threshold": round(threshold, 4),
        **alarm_summary(test_cases, threshold),
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
