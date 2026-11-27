import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from inventory_app import database  # noqa: E402
from inventory_app.repository import Repository  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    conn = database.connect(tmp_path / "test.db")
    yield Repository(conn)
    conn.close()
