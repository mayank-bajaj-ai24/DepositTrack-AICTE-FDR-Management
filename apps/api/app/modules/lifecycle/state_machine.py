"""Instrument lifecycle state machine (M7, plan §7.1).

Only the transitions in TRANSITIONS are legal. Every accepted transition returns an
audit event payload; callers must persist it through the audit chain (M6).
"""

from dataclasses import dataclass

from app.modules.lifecycle.states import InstrumentState as S

TRANSITIONS: dict[S, frozenset[S]] = {
    S.DRAFT: frozenset({S.SUBMITTED}),
    S.SUBMITTED: frozenset({S.SCRUTINY}),
    S.SCRUTINY: frozenset({S.DISCREPANCY, S.REJECTED, S.VERIFIED}),
    S.DISCREPANCY: frozenset({S.SCRUTINY}),
    S.REJECTED: frozenset(),
    S.VERIFIED: frozenset({S.ACTIVE}),
    S.ACTIVE: frozenset({S.EXPIRING, S.MATURED, S.RELEASING}),
    S.EXPIRING: frozenset({S.RENEWED, S.OVERDUE}),
    S.OVERDUE: frozenset({S.RENEWED}),
    S.RENEWED: frozenset(),
    S.MATURED: frozenset({S.RELEASING}),
    S.RELEASING: frozenset({S.RELEASED}),
    S.RELEASED: frozenset({S.ARCHIVED}),
    S.ARCHIVED: frozenset(),
}

TERMINAL_STATES: frozenset[S] = frozenset(s for s, targets in TRANSITIONS.items() if not targets)

# Entering these states triggers automatic escalation (M8).
ESCALATING_STATES: frozenset[S] = frozenset({S.OVERDUE})


class IllegalTransitionError(ValueError):
    def __init__(self, current: S, target: S):
        super().__init__(f"Illegal transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


@dataclass(frozen=True)
class TransitionResult:
    new_state: S
    escalate: bool
    audit_action: str
    audit_before: dict
    audit_after: dict


def can_transition(current: S, target: S) -> bool:
    return target in TRANSITIONS[current]


def transition(current: S, target: S, reason: str | None = None) -> TransitionResult:
    """Validate a state change and describe the audit event it must produce."""
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)
    return TransitionResult(
        new_state=target,
        escalate=target in ESCALATING_STATES,
        audit_action="instrument.state_changed",
        audit_before={"state": current.value},
        audit_after={"state": target.value, "reason": reason},
    )
