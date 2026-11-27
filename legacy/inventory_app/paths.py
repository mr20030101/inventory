"""Per-OS locations for the database and bundled resources."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Directory holding the user's database. INVENTORY_DATA_DIR overrides it."""
    override = os.environ.get("INVENTORY_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "InventoryManager"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "InventoryManager"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "inventory-manager"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "inventory.db"


def resource_path(relative: str) -> Path:
    """Path to a bundled file, both from source and inside a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative
