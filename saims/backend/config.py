"""Server settings, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from saims.paths import data_dir


def _default_database_url() -> str:
    return f"sqlite:///{(data_dir() / 'saims.db').as_posix()}"


@dataclass
class Settings:
    # PostgreSQL in production, e.g. postgresql+psycopg://saims:***@db-host/saims
    database_url: str = field(default_factory=lambda: os.environ.get("SAIMS_DATABASE_URL") or _default_database_url())
    session_hours: int = int(os.environ.get("SAIMS_SESSION_HOURS", "8"))
    max_failed_logins: int = int(os.environ.get("SAIMS_MAX_FAILED_LOGINS", "5"))
    lockout_minutes: int = int(os.environ.get("SAIMS_LOCKOUT_MINUTES", "15"))
    min_password_length: int = 8
    # Load demo school data into an empty database (demo mode only).
    seed_demo_data: bool = os.environ.get("SAIMS_SEED_DEMO", "0") == "1"
