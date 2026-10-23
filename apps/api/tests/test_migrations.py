import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.config import get_settings
from app.db.base import Base
from app.models import Anchor, AnchorEvent, Event

API_ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path, monkeypatch) -> tuple[Config, str]:
    url = f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"
    monkeypatch.setenv("DT_DATABASE_URL", url)
    get_settings.cache_clear()
    return Config(str(API_ROOT / "alembic.ini")), url


def test_migrations_upgrade_and_downgrade(tmp_path, monkeypatch):
    cfg, url = _config(tmp_path, monkeypatch)
    try:
        command.upgrade(cfg, "head")
        tables = set(inspect(create_engine(url)).get_table_names())
        assert set(Base.metadata.tables) <= tables

        command.downgrade(cfg, "base")
        assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}
    finally:
        get_settings.cache_clear()


def test_upgrade_gives_existing_anchors_the_batches_they_were_made_from(tmp_path, monkeypatch):
    """Anchors from before 0004 keep verifying: their ts-range batch becomes membership rows."""
    cfg, url = _config(tmp_path, monkeypatch)
    try:
        command.upgrade(cfg, "0003")
        engine = create_engine(url)
        t0 = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
        events = [uuid.uuid4() for _ in range(3)]
        receipted, plain = uuid.uuid4(), uuid.uuid4()
        old_anchor = sa.table(
            "anchor",
            sa.column("id", sa.Uuid()),
            sa.column("batch_start", sa.DateTime(timezone=True)),
            sa.column("batch_end", sa.DateTime(timezone=True)),
            sa.column("merkle_root", sa.String()),
            sa.column("store_tx", sa.String()),
            sa.column("ts", sa.DateTime(timezone=True)),
        )
        with engine.begin() as c:
            c.execute(
                sa.insert(Event.__table__),
                [
                    {
                        "id": event_id,
                        "actor_id": "system",
                        "role": "system",
                        "action": "test.legacy",
                        "ts": t0 + timedelta(minutes=i),
                        "seq": i + 1,
                        "hash": f"{i:064x}",
                    }
                    for i, event_id in enumerate(events)
                ],
            )
            c.execute(
                sa.insert(old_anchor),
                [
                    {
                        "id": receipted,
                        "batch_start": t0,
                        "batch_end": t0 + timedelta(minutes=1),
                        "merkle_root": "a" * 64,
                        "store_tx": "7",
                        "ts": t0,
                    },
                    {
                        "id": plain,
                        "batch_start": t0 + timedelta(minutes=2),
                        "batch_end": t0 + timedelta(minutes=2),
                        "merkle_root": "b" * 64,
                        "store_tx": None,
                        "ts": t0,
                    },
                ],
            )

        command.upgrade(cfg, "head")
        with engine.connect() as c:
            members = c.execute(
                sa.select(AnchorEvent.anchor_id, AnchorEvent.event_id).order_by(
                    AnchorEvent.anchor_id, AnchorEvent.position
                )
            ).all()
            keys = dict(c.execute(sa.select(Anchor.id, Anchor.store_key)).all())
        assert sorted(members) == sorted(
            [(receipted, events[0]), (receipted, events[1]), (plain, events[2])]
        )
        assert keys == {
            receipted: "depositrack:anchor:2026-10-22T10:01:00+00:00",
            plain: None,
        }
    finally:
        get_settings.cache_clear()
