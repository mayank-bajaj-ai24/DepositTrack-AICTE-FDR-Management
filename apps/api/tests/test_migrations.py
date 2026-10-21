from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.config import get_settings
from app.db.base import Base

API_ROOT = Path(__file__).resolve().parents[1]


def test_migrations_upgrade_and_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"
    monkeypatch.setenv("DT_DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(API_ROOT / "alembic.ini"))
        command.upgrade(cfg, "head")
        tables = set(inspect(create_engine(url)).get_table_names())
        assert set(Base.metadata.tables) <= tables

        command.downgrade(cfg, "base")
        assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}
    finally:
        get_settings.cache_clear()
