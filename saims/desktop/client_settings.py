"""Per-user desktop preferences (server address, theme, last username, network sharing, trusted servers)."""
from __future__ import annotations

import json
from typing import Any

from saims.paths import data_dir

_FILE = "desktop-settings.json"
DEFAULTS = {
    "server_mode": "local", "server_url": "https://", "theme": "light", "last_username": "",
    # This computer shares its built-in server on the local network (HTTPS on share_port).
    "share_on_network": False, "share_port": 8765,
    # Servers whose certificate someone confirmed by its security code: {"host:port": "PEM certificate"}.
    "trusted_servers": {},
}


def load() -> dict[str, Any]:
    try:
        data = json.loads((data_dir() / _FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save(values: dict[str, Any]) -> None:
    try:
        (data_dir() / _FILE).write_text(json.dumps({**load(), **values}, indent=2), encoding="utf-8")
    except OSError:
        pass
