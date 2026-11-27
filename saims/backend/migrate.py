"""Run Alembic migrations programmatically (works from source and inside a PyInstaller build)."""
from __future__ import annotations

from alembic import command
from alembic.config import Config

from saims.paths import resource_path


def alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(resource_path("saims/backend/migrations")))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def upgrade(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
