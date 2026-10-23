"""Seed the database for a demo.

    python -m app.seed demo --institution-user-aicte-id 1-XXXXXXXXXX [--seed-file ...]

Run `python -m app.masterdata import-institutions` (and `import-banks`) first: institutions
come only from AICTE's public master data, never from this script.

1. User accounts for the Keycloak development users from the seed file. The institution
   user is linked to the real AICTE institution given on the command line.
2. One obligation for each linked institution from the policy's deposit requirements. With
   the real policy (all values unconfirmed) no obligations are created.

No instruments are seeded: FDRs enter through the normal intake (upload) during the demo.
Nothing is deleted: a database seeded by the earlier fictional seed keeps its institutions
until it is reset (alembic downgrade base && alembic upgrade head, see README).
"""

import argparse
import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.core import clock
from app.core.config import get_settings
from app.core.policy import get_policy
from app.db.session import get_engine
from app.models import Institution, Obligation, UserAccount

API_ROOT = Path(__file__).resolve().parents[1]


def seed_accounts(session, seed_file: Path, institution_aicte_id: str | None) -> list[Institution]:
    """Create the development accounts; return the institutions they are linked to."""
    data = json.loads(seed_file.read_text(encoding="utf-8"))
    linked: list[Institution] = []
    institution = None
    if institution_aicte_id:
        institution = session.scalars(
            select(Institution).where(Institution.aicte_id == institution_aicte_id)
        ).first()
        if institution is None:
            raise SystemExit(
                f"No institution {institution_aicte_id}: run `python -m app.masterdata "
                "import-institutions` first and pick an AICTE ID from it"
            )
        linked.append(institution)
    for row in data["accounts"]:
        account = session.scalars(
            select(UserAccount).where(UserAccount.username == row["username"])
        ).first()
        if account is None:
            account = UserAccount(username=row["username"])
            session.add(account)
        if not row.get("institution_user"):
            account.institution_id = None
        elif institution is not None:
            account.institution_id = institution.id
        elif account.institution_id is None:
            print(
                f"Warning: {row['username']} is not linked to an institution; pass "
                "--institution-user-aicte-id"
            )
        else:
            kept = session.get(Institution, account.institution_id)
            print(
                f"Warning: {row['username']} stays linked to {kept.name} "
                f"(AICTE ID {kept.aicte_id}) from an earlier seed. Pass "
                "--institution-user-aicte-id to link a real institution; a database seeded "
                "with the old fictional institutions should be reset first (see README)."
            )
        account.region = row.get("region")
        account.bank_code = row.get("bank_code")
    session.flush()
    return linked


def seed_obligations(session, institutions: list[Institution], policy) -> int:
    requirements = policy.deposit_requirements
    if not requirements:
        return 0
    today = clock.today(session)
    created = 0
    for inst in institutions:
        if session.scalars(select(Obligation).where(Obligation.institution_id == inst.id)).first():
            continue
        req = next(
            (r for r in requirements if r["institution_type"] in ("any", inst.institution_type)),
            None,
        )
        if req is None:
            continue
        session.add(
            Obligation(
                institution_id=inst.id,
                basis_ref=f"{req['approval_case']} requirement ({policy.version})",
                rule_version=policy.version,
                required_amount=req["amount_inr"],
                required_from=today - timedelta(days=365),
                required_until=today + timedelta(days=30 * req["duration_months"]),
            )
        )
        created += 1
    session.flush()
    return created


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="app.seed")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--seed-file", type=Path, default=API_ROOT / "seed" / "demo_seed.json")
    demo.add_argument("--institution-user-aicte-id", default=None)
    args = parser.parse_args(argv)

    from sqlalchemy.orm import Session

    settings = get_settings()
    policy = get_policy(settings.policy_file)
    with Session(get_engine()) as session:
        institutions = seed_accounts(session, args.seed_file, args.institution_user_aicte_id)
        print(f"Linked institutions: {[i.name for i in institutions]}")
        print(f"Obligations created: {seed_obligations(session, institutions, policy)}")
        session.commit()


if __name__ == "__main__":
    main()
