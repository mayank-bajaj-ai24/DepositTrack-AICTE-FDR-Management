"""Tests for ml/risk/train.py on a tiny hand-written event log (no download)."""

import argparse
import csv
import importlib.util
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "risk_train", Path(__file__).resolve().parents[1] / "risk" / "train.py"
)
rt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rt)

T0 = datetime(2016, 1, 1, 9, 0)
SENT = "O_Sent (mail and online)"
COLUMNS = [
    "org:resource",
    "concept:name",
    "lifecycle:transition",
    "time:timestamp",
    "case:ApplicationType",
    "case:concept:name",
    "case:RequestedAmount",
]


def ev(case, day, name, resource="User_1", transition="complete", amount="1000.0"):
    return {
        "org:resource": resource,
        "concept:name": name,
        "lifecycle:transition": transition,
        "time:timestamp": (T0 + timedelta(days=day)).isoformat(),
        "case:ApplicationType": "New credit",
        "case:concept:name": case,
        "case:RequestedAmount": amount,
    }


LOG = [
    # lapse: system cancels after ~31 days with no return -> missed, 5 weekly points
    ev("lapse", 0, "A_Create Application"),
    ev("lapse", 1, SENT),
    ev("lapse", 32, "A_Cancelled"),
    # returned on day 10, later pending -> not missed, points stop at the return (days 1, 8)
    ev("returned", 0, "A_Create Application"),
    ev("returned", 1, SENT),
    ev("returned", 10, "O_Returned"),
    ev("returned", 25, "A_Pending"),
    # staff cancel before any return (customer withdrew) -> not missed
    ev("withdrew", 2, "A_Create Application"),
    ev("withdrew", 3, SENT),
    ev("withdrew", 6, "A_Cancelled", resource="User_42"),
    # denied before any return -> kept, not missed
    ev("denied", 3, "A_Create Application"),
    ev("denied", 4, SENT),
    ev("denied", 9, "A_Denied", resource="User_7"),
    # returned, then system cancels -> the return decides: not missed
    ev("late_cancel", 4, "A_Create Application"),
    ev("late_cancel", 5, SENT),
    ev("late_cancel", 7, "O_Returned"),
    ev("late_cancel", 40, "A_Cancelled"),
    # never sent an offer
    ev("no_offer", 5, "A_Create Application"),
    # still open with no outcome, sent long before the log end
    ev("open", 6, "A_Create Application"),
    ev("open", 7, SENT),
    # sent within the censoring window before the log end (day 100)
    ev("recent", 80, "A_Create Application"),
    ev("recent", 90, SENT),
    ev("recent", 100, "A_Cancelled"),
]


@pytest.fixture
def cases(tmp_path):
    path = tmp_path / "log.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(LOG)
    return rt.read_cases(path)


def test_outcome_labels(cases):
    assert rt.outcome(cases["lapse"]) == (1, T0 + timedelta(days=32))
    assert rt.outcome(cases["returned"]) == (0, T0 + timedelta(days=10))
    assert rt.outcome(cases["withdrew"])[0] == 0
    assert rt.outcome(cases["denied"])[0] == 0
    assert rt.outcome(cases["late_cancel"]) == (0, T0 + timedelta(days=7))
    assert rt.outcome(cases["open"]) is None


def test_decision_points_rows_and_left_out_cases(cases):
    rows, counts = rt.decision_points(cases)
    by_case: dict[str, list] = {}
    for r in rows:
        by_case.setdefault(r["case"], []).append(r)
    assert set(by_case) == {"lapse", "returned", "withdrew", "denied", "late_cancel"}
    assert counts == {"no_offer": 1, "ended_before_offer": 0, "censored": 1, "open": 1}
    assert [r["week"] for r in by_case["lapse"]] == [0, 1, 2, 3, 4]
    assert {r["missed"] for r in by_case["lapse"]} == {1}
    assert [r["at"] for r in by_case["returned"]] == [
        T0 + timedelta(days=1),
        T0 + timedelta(days=8),
    ]
    assert by_case["returned"][1]["days_to_outcome"] == pytest.approx(2.0)
    assert all(r["at"] < r["ended"] for r in rows)


def brute_features(case, at):
    """The straightforward per-point computation the one-pass version must match."""
    seen = [e for e in case["events"] if e[0] <= at]
    sent = [ts for ts, name, *_ in seen if name in rt.OFFER_SENT]

    def count(name, transition=None):
        return sum(1 for _, n, t, _ in seen if n == name and transition in (None, t))

    return [
        rt._days(at - seen[0][0]),
        rt._days(at - sent[0]) if sent else -1.0,
        float(len(sent)),
        float(count("A_Incomplete")),
        float(count("W_Call incomplete files", "start")),
        float(count("W_Call after offers", "start")),
        float(sum(1 for ts, *_ in seen if rt._days(at - ts) <= 7)),
        sum(math.exp(-rt._days(at - ts) / rt.DECAY_DAYS) for ts, *_ in seen),
        rt._days(at - seen[-1][0]),
        math.log1p(case["amount"]),
        float(case["limit_raise"]),
    ]


def test_one_pass_features_match_the_direct_computation(cases):
    case = cases["lapse"]
    case["events"] += [
        (T0 + timedelta(days=3), "A_Incomplete", "complete", "User_3"),
        (T0 + timedelta(days=9), "W_Call incomplete files", "start", "User_3"),
        (T0 + timedelta(days=9, hours=1), "W_Call after offers", "start", "User_3"),
        (T0 + timedelta(days=16), SENT, "complete", "User_1"),
    ]
    case["events"].sort()
    points = [T0 + timedelta(days=d) for d in (1, 8, 15, 22, 29)]
    rows = rt.prefix_rows(case, points)
    assert len(rows) == len(points)
    assert all(len(row) == len(rt.FEATURE_NAMES) for row in rows)
    for at, row in zip(points, rows, strict=True):
        assert row == pytest.approx(brute_features(case, at))


def test_case_split_is_by_creation_time(cases):
    rows, _ = rt.decision_points(cases)
    parts = rt.case_split(rows, 0.6, 0.2)
    members = {p: {r["case"] for r in parts[p]} for p in parts}
    assert members == {
        "train": {"lapse", "returned", "withdrew"},
        "val": {"denied"},
        "test": {"late_cancel"},
    }


def test_threshold_calibration_and_alarm_summary():
    t = [T0 + timedelta(days=7 * i) for i in range(3)]
    rows = [
        {"case": "m", "missed": 1, "ended": t[2] + timedelta(days=3), "at": t[0]},
        {"case": "m", "missed": 1, "ended": t[2] + timedelta(days=3), "at": t[1]},
        {"case": "a", "missed": 0, "ended": t[1], "at": t[0]},
        {"case": "b", "missed": 0, "ended": t[1], "at": t[0]},
    ]
    cases = rt.case_scores(rows, [0.4, 0.9, 0.2, 0.6])
    assert cases["m"]["points"] == [(t[0], 0.4), (t[1], 0.9)]
    threshold = rt.calibrate_threshold(cases, 0.5)
    assert threshold == pytest.approx(0.4)
    summary = rt.alarm_summary(cases, 0.5)
    assert summary["missed_cases_caught"] == 1.0
    assert summary["not_missed_cases_false_alarm"] == 0.5
    assert summary["mean_lead_time_days"] == pytest.approx(10.0)
    with pytest.raises(ValueError):
        rt.calibrate_threshold({"m": cases["m"]}, 0.1)


def test_auc_by_week_reports_pooled_and_early_weeks():
    rows = [{"missed": m, "week": w} for w in (0, 1) for m in (0, 1)]
    result = rt.auc_by_week(rows, [0.1, 0.9, 0.8, 0.2], weeks=2)
    assert result["pooled"] == 0.75
    assert result["by_week"] == {"0": 1.0, "1": 0.0}
    assert result["weighted_mean_weeks_0_1"] == 0.5


def test_single_class_split_and_bad_false_alarm_are_rejected():
    with pytest.raises(SystemExit, match="test split"):
        rt.check_parts({"train": [{"missed": 0}, {"missed": 1}], "test": [{"missed": 0}]})
    for bad in ("0", "1", "1.5", "-0.1"):
        with pytest.raises(argparse.ArgumentTypeError):
            rt.false_alarm_share(bad)
    assert rt.false_alarm_share("0.1") == 0.1
