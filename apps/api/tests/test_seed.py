"""Demo seed: development accounts linked to a real (imported) institution, nothing deleted."""

import pytest
from sqlalchemy import select

from app.models import Institution, UserAccount
from app.seed import API_ROOT, seed_accounts
from tests.flow_support import make_sessionmaker

SEED_FILE = API_ROOT / "seed" / "demo_seed.json"


@pytest.fixture
def session():
    with make_sessionmaker()() as s:
        yield s


def _account(session, username: str) -> UserAccount:
    return session.scalars(select(UserAccount).where(UserAccount.username == username)).one()


def _old_seed(session) -> Institution:
    """A database seeded by the earlier version: fictional institution, linked accounts."""
    old = Institution(aicte_id="SYN-1-0001", name="Synthetic Institute of Technology, Pune")
    session.add(old)
    session.flush()
    session.add_all(
        [
            UserAccount(username="institution.demo", institution_id=old.id),
            UserAccount(username="scrutiny.demo", institution_id=old.id),
        ]
    )
    session.flush()
    return old


def test_kept_institution_link_is_named_in_a_warning(session, capsys):
    old = _old_seed(session)
    seed_accounts(session, SEED_FILE, None)
    out = capsys.readouterr().out
    assert "institution.demo stays linked to" in out
    assert old.name in out and old.aicte_id in out
    # Nothing is deleted automatically.
    assert session.get(Institution, old.id) is not None
    assert _account(session, "institution.demo").institution_id == old.id


def test_only_the_institution_user_is_linked_to_an_institution(session):
    _old_seed(session)
    real = Institution(aicte_id="1-44661939517", name="ORIENTAL SCHOOL OF HOTEL MANAGEMENT")
    session.add(real)
    session.flush()
    assert seed_accounts(session, SEED_FILE, real.aicte_id) == [real]
    assert _account(session, "institution.demo").institution_id == real.id
    assert _account(session, "scrutiny.demo").institution_id is None


def test_unlinked_institution_user_gets_a_warning(session, capsys):
    seed_accounts(session, SEED_FILE, None)
    assert "institution.demo is not linked to an institution" in capsys.readouterr().out
