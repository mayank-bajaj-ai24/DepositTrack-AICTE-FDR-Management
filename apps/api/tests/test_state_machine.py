import itertools

import pytest

from app.modules.lifecycle.state_machine import (
    TERMINAL_STATES,
    TRANSITIONS,
    IllegalTransitionError,
    can_transition,
    transition,
)
from app.modules.lifecycle.states import InstrumentState as S

LEGAL = [(src, dst) for src, targets in TRANSITIONS.items() for dst in targets]
ILLEGAL = [(src, dst) for src, dst in itertools.product(S, S) if dst not in TRANSITIONS[src]]


def test_every_state_has_an_entry():
    assert set(TRANSITIONS) == set(S)


@pytest.mark.parametrize(("src", "dst"), LEGAL, ids=lambda s: s.value)
def test_legal_transitions_are_accepted(src, dst):
    result = transition(src, dst, reason="test")
    assert result.new_state == dst
    assert result.audit_before == {"state": src.value}
    assert result.audit_after["state"] == dst.value


@pytest.mark.parametrize(("src", "dst"), ILLEGAL, ids=lambda s: s.value)
def test_illegal_transitions_are_rejected(src, dst):
    assert not can_transition(src, dst)
    with pytest.raises(IllegalTransitionError):
        transition(src, dst)


def test_terminal_states():
    assert TERMINAL_STATES == {S.REJECTED, S.RENEWED, S.ARCHIVED}


def test_only_overdue_escalates():
    assert transition(S.EXPIRING, S.OVERDUE).escalate
    assert not transition(S.EXPIRING, S.RENEWED).escalate


def test_cannot_skip_verification():
    """An instrument cannot become active straight from scrutiny (plan §7.1)."""
    assert not can_transition(S.SCRUTINY, S.ACTIVE)
    assert not can_transition(S.SUBMITTED, S.ACTIVE)


def test_full_renewal_path():
    path = [S.DRAFT, S.SUBMITTED, S.SCRUTINY, S.VERIFIED, S.ACTIVE, S.EXPIRING, S.RENEWED]
    for src, dst in itertools.pairwise(path):
        transition(src, dst)


def test_full_release_path():
    path = [S.ACTIVE, S.MATURED, S.RELEASING, S.RELEASED, S.ARCHIVED]
    for src, dst in itertools.pairwise(path):
        transition(src, dst)
