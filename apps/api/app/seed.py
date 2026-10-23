"""Seed the database for a demo.

    python -m app.seed demo [--seed-file seed/demo_seed.json]
                            [--synthetic ../../data/synthetic --count 12]

1. Institutions and user accounts from the seed file (fictional data).
2. One obligation per institution from the policy's deposit requirements. With the real
   policy (all values unconfirmed) no obligations are created.
3. Optionally, synthetic FDRs submitted through the normal intake pipeline (OCR, checks,
   audit), spread across the institutions.
"""

import argparse
import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.core import clock
from app.core.config import get_settings
from app.core.configfiles import load_config
from app.core.policy import get_policy
from app.db.session import get_engine
from app.models import Institution, Obligation, UserAccount
from app.modules.audit.service import Actor
from app.modules.extraction.ocr import load_image
from app.modules.extraction.service import extract
from app.modules.instruments.intake import submit_instrument
from app.modules.lifecycle.states import InstrumentKind
from app.modules.storage.store import build_store

API_ROOT = Path(__file__).resolve().parents[1]


def seed_reference(session, seed_file: Path) -> dict[str, Institution]:
    data = json.loads(seed_file.read_text(encoding="utf-8"))
    by_aicte: dict[str, Institution] = {}
    for row in data["institutions"]:
        inst = session.scalars(
            select(Institution).where(Institution.aicte_id == row["aicte_id"])
        ).first()
        if inst is None:
            inst = Institution(**row)
            session.add(inst)
            session.flush()
        by_aicte[inst.aicte_id] = inst
    for row in data["accounts"]:
        account = session.scalars(
            select(UserAccount).where(UserAccount.username == row["username"])
        ).first()
        if account is None:
            account = UserAccount(username=row["username"])
            session.add(account)
        aicte_id = row.get("institution_aicte_id")
        account.institution_id = by_aicte[aicte_id].id if aicte_id else None
        account.region = row.get("region")
        account.bank_code = row.get("bank_code")
    session.flush()
    return by_aicte


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


def seed_instruments(
    session, institutions: list[Institution], source: Path, count: int, policy
) -> int:
    settings = get_settings()
    store = build_store(settings)
    rules = load_config("extraction.yaml")

    def extractor(data: bytes, content_type: str | None):
        return extract(load_image(data, content_type), rules, settings.models_dir)

    submitted = 0
    for index, path in enumerate(sorted(source.glob("*.json"))[:count]):
        record = json.loads(path.read_text(encoding="utf-8"))
        image_bytes = (source / record["image"]).read_bytes()
        result = extractor(image_bytes, "image/png")
        declared = {name: f.value for name, f in result.fields.items()}
        institution = institutions[index % len(institutions)]
        submit_instrument(
            session,
            store=store,
            policy=policy,
            actor=Actor(username=f"seed:{institution.aicte_id}", role="institution"),
            roles=frozenset({"institution"}),
            institution_id=institution.id,
            kind=InstrumentKind.FDR,
            declared=declared,
            file_bytes=image_bytes,
            content_type="image/png",
            extractor=lambda data, ct, r=result: r,
        )
        submitted += 1
        print(f"  submitted {record['id']} for {institution.name}")
    return submitted


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="app.seed")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--seed-file", type=Path, default=API_ROOT / "seed" / "demo_seed.json")
    demo.add_argument("--synthetic", type=Path, default=None)
    demo.add_argument("--count", type=int, default=12)
    args = parser.parse_args(argv)

    from sqlalchemy.orm import Session

    settings = get_settings()
    policy = get_policy(settings.policy_file)
    with Session(get_engine()) as session:
        institutions = list(seed_reference(session, args.seed_file).values())
        print(f"Institutions: {len(institutions)}")
        print(f"Obligations created: {seed_obligations(session, institutions, policy)}")
        if args.synthetic:
            submitted = seed_instruments(session, institutions, args.synthetic, args.count, policy)
            print(f"Instruments submitted: {submitted}")
        session.commit()


if __name__ == "__main__":
    main()
