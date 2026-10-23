"""Renewal-risk features (N9) computed from DepositTrack's own database history.

Features describe an institution's history at a decision point before an instrument
matures (prefix encoding, as in the predictive-monitoring benchmark): past renewals and
how many were late, how fast it answers queries, open flags, time to maturity, amount,
and recency-weighted activity (temporal decay, as in the regulatory-graphs paper).
"""

import math
from dataclasses import dataclass, field
from datetime import date

DECAY_DAYS = 90.0

FEATURE_NAMES = [
    "past_renewals",
    "past_late_renewals",
    "late_ratio",
    "median_response_days",
    "open_flags",
    "days_to_maturity",
    "log_amount",
    "activity_decay",
    "days_since_last_action",
]


@dataclass
class History:
    """What is known about an institution at the decision date."""

    as_of: date
    maturity: date
    amount: float
    open_flags: int = 0
    renewals: list[tuple[date, date | None]] = field(default_factory=list)  # (maturity, submitted)
    response_days: list[float] = field(default_factory=list)
    action_dates: list[date] = field(default_factory=list)


def _median(values: list[float]) -> float:
    if not values:
        return -1.0  # no queries answered yet
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def features(h: History) -> list[float]:
    past = [(m, s) for m, s in h.renewals if m < h.as_of]
    late = sum(1 for m, s in past if s is None or s > m)
    actions = [d for d in h.action_dates if d <= h.as_of]
    decay = sum(math.exp(-(h.as_of - d).days / DECAY_DAYS) for d in actions)
    since = (h.as_of - max(actions)).days if actions else 999
    return [
        float(len(past)),
        float(late),
        late / len(past) if past else -1.0,
        _median(h.response_days),
        float(h.open_flags),
        float((h.maturity - h.as_of).days),
        math.log1p(max(h.amount, 0.0)),
        decay,
        float(since),
    ]


def describe(name: str, value: float) -> str:
    """Plain-language reason for one feature value (English; the UI translates by code)."""
    if name == "past_late_renewals":
        return f"{int(value)} earlier renewal(s) arrived after maturity"
    if name == "late_ratio":
        return (
            "no earlier renewals on record"
            if value < 0
            else f"{value:.0%} of earlier renewals were late"
        )
    if name == "median_response_days":
        return (
            "no queries answered yet"
            if value < 0
            else f"answers queries in a median {value:.0f} days"
        )
    if name == "open_flags":
        return f"{int(value)} open discrepancy flag(s)"
    if name == "days_to_maturity":
        return f"{int(value)} days to maturity"
    if name == "activity_decay":
        return f"recent activity score {value:.1f}"
    if name == "days_since_last_action":
        return f"last action {int(value)} days ago"
    if name == "past_renewals":
        return f"{int(value)} earlier renewal(s)"
    if name == "log_amount":
        return f"amount Rs. {math.expm1(value):,.0f}"
    return f"{name} = {value}"
