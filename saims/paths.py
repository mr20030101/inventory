"""Per-OS locations for local data and bundled resources."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Folder for the demo database and client settings. SAIMS_DATA_DIR overrides it."""
    override = os.environ.get("SAIMS_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "SAIMS"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "SAIMS"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "saims"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """Path to a bundled file, from source or inside a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative
