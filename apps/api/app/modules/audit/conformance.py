"""Conformance replay (N10): check each instrument's event log against procedural
constraints and report the four result types from the compliance-monitoring review:
quantify (share conforming), qualify (violated or not), localize (which event),
explain (why)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models import Event


@dataclass(frozen=True)
class Violation:
    constraint_id: str
    seq: int
    action: str
    explanation: str


def _matches(event: Event, target: dict) -> bool:
    if event.action != target["action"]:
        return False
    state = target.get("state")
    return state is None or (event.after or {}).get("state") == state


def _ts(event: Event) -> datetime:
    return event.ts if event.ts.tzinfo else event.ts.replace(tzinfo=UTC)


def replay(events: list[Event], constraints: list[dict], now: datetime) -> list[Violation]:
    violations: list[Violation] = []
    for c in constraints:
        kind = c["kind"]
        for index, event in enumerate(events):
            if kind == "precedence" and _matches(event, c["target"]):
                earlier = {e.action for e in events[:index]}
                if not earlier & set(c["requires_any"]):
                    violations.append(
                        Violation(
                            c["id"],
                            event.seq,
                            event.action,
                            f"{c['description']}: none of {c['requires_any']} happened before",
                        )
                    )
            elif kind == "response" and _matches(event, c["trigger"]):
                deadline = _ts(event) + timedelta(days=c["within_days"])
                followed = any(
                    e.action == c["expects"] and _ts(e) <= deadline for e in events[index + 1 :]
                )
                if not followed and now > deadline:
                    violations.append(
                        Violation(
                            c["id"],
                            event.seq,
                            event.action,
                            f"{c['description']}: no {c['expects']} "
                            f"within {c['within_days']} day(s)",
                        )
                    )
            elif kind == "reason_required" and _matches(event, c["target"]):
                if not (event.reason or "").strip():
                    violations.append(
                        Violation(
                            c["id"], event.seq, event.action, f"{c['description']}: reason missing"
                        )
                    )
    return violations
