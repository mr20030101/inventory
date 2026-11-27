"""SAIMS Desktop entry point."""
from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from saims import APP_FULL_NAME, __version__
from saims.desktop import client_settings
from saims.desktop.local_server import LocalServer
from saims.desktop.ui import theme
from saims.desktop.ui.login import LoginDialog
from saims.desktop.ui.main_window import MainWindow
from saims.paths import data_dir, resource_path


class DesktopApp:
    """Owns the built-in server (and whether it is shared on the network) and the sign-in / main windows."""

    def __init__(self, app: QApplication):
        self.app = app
        self.server: LocalServer | None = None
        self.window: MainWindow | None = None
        prefs = client_settings.load()
        self.sharing, self.share_port = bool(prefs["share_on_network"]), int(prefs["share_port"])

    def local_server(self) -> tuple[str, object]:
        """Start the built-in server on first use; returns (address, certificate check) for this computer."""
        if self.server is None:
            server = LocalServer(seed_demo=True, share=self.sharing, port=self.share_port)
            try:
                server.start()
            except RuntimeError:
                if not self.sharing:
                    raise
                # The sharing port is taken: start unshared so this computer still works, and say so later.
                logging.warning("Could not share on port %s; starting unshared.", self.share_port)
                self.sharing = False
                server = LocalServer(seed_demo=True)
                server.start()
            self.server = server
        return self.server.url, self.server.verify

    # ------------------------------------------------------------ SharingController
    def security_code(self) -> str:
        return self.server.security_code if self.server else ""

    def set_sharing(self, on: bool, port: int) -> None:
        """Restart the built-in server shared (HTTPS on all interfaces) or private; signed-in users stay signed in."""
        if self.server and on == self.sharing and port == self.share_port:
            return
        old = self.server
        if old:
            old.stop()
        new = LocalServer(seed_demo=True, share=on, port=port)
        try:
            new.start()
        except Exception:
            if old:  # put the previous server back so this computer keeps working
                self.server = LocalServer(seed_demo=True, share=self.sharing, port=self.share_port)
                self.server.start()
                if self.window:
                    self.window.api.rebase(self.server.url, self.server.verify)
            raise
        self.server, self.sharing, self.share_port = new, on, port
        client_settings.save({"share_on_network": on, "share_port": port})
        if self.window:
            self.window.api.rebase(new.url, new.verify)
            self.window.update_sharing_badge()

    # ------------------------------------------------------------ windows
    def show_login(self, reason: str = "") -> bool:
        dialog = LoginDialog(self.local_server)
        if reason:
            dialog._fail(reason)
        if not dialog.exec():
            self.app.quit()
            return False
        local = dialog.mode.currentData() == "local"
        self.window = MainWindow(dialog.api, sharing=self if local else None)
        self.window.signed_out.connect(self.show_login)
        self.window.show()
        return True

    def shutdown(self) -> None:
        if self.server:
            self.server.stop()


def self_test() -> int:
    """Start the built-in server, sign in and check the data. Used to verify installed builds."""
    from saims.desktop.api import Api
    server = LocalServer(seed_demo=True)
    try:
        api = Api(server.start())
        api.login("admin", "demo1234")
        ok = api.get("/stock/reconcile")["consistent"] and len(api.get("/assets")) > 0
        print(f"SAIMS {__version__} self-test: {'OK' if ok else 'FAILED'} "
              f"({len(api.get('/assets'))} assets, data in {data_dir()})")
        return 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        print(f"SAIMS self-test FAILED: {exc}")
        return 1
    finally:
        server.stop()


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    logging.basicConfig(filename=str(data_dir() / "saims-desktop.log"), level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("SAIMS")
    app.setApplicationDisplayName("SAIMS")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("saims")
    app.setStyle("Fusion")
    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 10))
    app.setFont(font)
    icon = resource_path("saims/assets/icon.png")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    app.setQuitOnLastWindowClosed(False)
    theme.apply(app, client_settings.load()["theme"])
    desktop = DesktopApp(app)
    app.aboutToQuit.connect(desktop.shutdown)
    app.lastWindowClosed.connect(app.quit)
    if not desktop.show_login():
        desktop.shutdown()
        return 0
    return app.exec()
