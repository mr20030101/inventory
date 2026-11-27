"""Network sharing with certificate pinning, and the checklist dropdown used for multi-select."""
import os
import socket
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_share_on_network_and_connect_from_another_computer(app, tmp_path, monkeypatch):
    monkeypatch.setenv("SAIMS_DATA_DIR", str(tmp_path))
    from saims.desktop import client_settings
    from saims.desktop.api import Api, ApiError
    from saims.desktop.main import DesktopApp
    from saims.desktop.ui import login as login_mod
    from saims.desktop.ui.main_window import MainWindow

    desktop = DesktopApp(app)
    url, verify = desktop.local_server()
    assert url.startswith("http://127.0.0.1")
    api = Api(url, verify)
    api.login("admin", "demo1234")
    desktop.window = MainWindow(api, sharing=desktop)
    port = free_port()
    try:
        desktop.set_sharing(True, port)
        # The host keeps its session across the restart and now talks HTTPS with the pinned certificate.
        assert api.base_url == f"https://127.0.0.1:{port}"
        assert len(api.get("/assets")) > 0
        assert desktop.window.share_badge.isVisibleTo(desktop.window)
        assert client_settings.load()["share_on_network"] is True

        # Another computer: confirm the security code once, then it is remembered.
        shown = []

        class Confirm:
            def __init__(self, address, code, changed=False, parent=None):
                shown.append((code, changed))

            def exec(self):
                return 1

        monkeypatch.setattr(login_mod, "TrustDialog", Confirm)
        dialog = login_mod.LoginDialog(lambda: (None, None))
        dialog.mode.setCurrentIndex(dialog.mode.findData("remote"))
        dialog.url.setText(f"127.0.0.1:{port}")  # scheme added automatically
        dialog.username.setText("teacher")
        dialog.password.setText("demo1234")
        dialog.sign_in()
        assert dialog.api is not None and dialog.api.me["username"] == "teacher", dialog.error.text()
        assert shown == [(desktop.security_code(), False)]
        assert f"127.0.0.1:{port}" in client_settings.load()["trusted_servers"]

        class Refuse(Confirm):
            def exec(self):
                raise AssertionError("a pinned server must not ask again")

        monkeypatch.setattr(login_mod, "TrustDialog", Refuse)
        again = login_mod.LoginDialog(lambda: (None, None))
        again.mode.setCurrentIndex(again.mode.findData("remote"))
        again.url.setText(f"https://127.0.0.1:{port}")
        again.username.setText("teacher")
        again.password.setText("demo1234")
        again.sign_in()
        assert again.api is not None, again.error.text()

        # A client without the pin (system authorities only) is refused rather than silently trusting.
        with pytest.raises(ApiError) as err:
            Api(f"https://127.0.0.1:{port}").info()
        assert err.value.code == "untrusted_certificate"

        desktop.set_sharing(False, port)
        assert api.base_url.startswith("http://127.0.0.1") and api.get("/auth/me")["username"] == "admin"
    finally:
        desktop.shutdown()


def test_check_combo(app):
    from saims.desktop.ui.widgets import CheckCombo
    combo = CheckCombo("All statuses", "statuses")
    combo.resize(200, 30)
    combo.set_options([("Assigned", "assigned"), ("Borrowed", "borrowed"), ("Missing", "missing")])
    fired = []
    combo.changed.connect(lambda: fired.append(combo.values()))
    assert combo.values() == [] and combo.summary() == "All statuses"
    combo.set_values(["borrowed", "assigned"])
    assert combo.values() == ["assigned", "borrowed"] and fired == [["assigned", "borrowed"]]
    assert combo.summary() in ("Assigned, Borrowed", "2 statuses")
    combo.set_options([("Assigned", "assigned"), ("Damaged", "damaged")])  # keeps ticks that still exist
    assert combo.values() == ["assigned"]
    combo.clear_selection()
    assert combo.values() == []


def test_runs_without_console_like_the_windowed_windows_app(tmp_path, monkeypatch):
    """The Windows build has no console: sys.stdout and sys.stderr are None. The built-in server must still start
    (uvicorn's console logging used to crash it) and the self-test must report through its log file."""
    monkeypatch.setenv("SAIMS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    from saims.desktop.main import self_test
    assert self_test() == 0
    assert "self-test: OK" in (tmp_path / "self-test.log").read_text(encoding="utf-8")
