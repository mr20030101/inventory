"""Sign-in window: brand panel plus server choice and credentials."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from urllib.parse import urlsplit

from saims import APP_FULL_NAME, __version__, tls
from saims.desktop import client_settings
from saims.desktop.api import Api, ApiError
from saims.desktop.ui import theme
from saims.desktop.ui.sharing import TrustDialog

DEMO_ACCOUNTS = [("admin", "Super Administrator"), ("principal", "School Administrator"),
                 ("custodian", "Property Custodian"), ("head.science", "Department Head"),
                 ("teacher", "Teacher"), ("auditor", "Auditor"), ("maintenance", "Maintenance Staff")]


class LoginDialog(QDialog):
    def __init__(self, start_local_server, parent=None):
        """start_local_server() -> (address, certificate check) of the built-in server (started on first use)."""
        super().__init__(parent)
        self.start_local_server = start_local_server
        self.api: Api | None = None
        self.prefs = client_settings.load()
        self.setWindowTitle(f"SAIMS — Sign in")
        self.setMinimumSize(860, 540)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        brand = QFrame()
        brand.setObjectName("LoginBrand")
        brand.setFixedWidth(360)
        bl = QVBoxLayout(brand)
        bl.setContentsMargins(36, 48, 36, 32)
        logo = QLabel()
        logo.setPixmap(theme.logo(260, reverse=True))
        logo.setAccessibleName(APP_FULL_NAME)
        logo.setToolTip(APP_FULL_NAME)
        self.school = QLabel("")
        self.school.setObjectName("BrandName")
        self.school.setWordWrap(True)
        bl.addWidget(logo)
        bl.addSpacing(28)
        bl.addWidget(self.school)
        bl.addStretch()
        self.demo_box = QLabel()
        self.demo_box.setObjectName("BrandSub")
        self.demo_box.setWordWrap(True)
        self.demo_box.setTextFormat(Qt.TextFormat.RichText)
        bl.addWidget(self.demo_box)
        ver = QLabel(f"Version {__version__}")
        ver.setObjectName("BrandSub")
        bl.addWidget(ver)
        row.addWidget(brand)

        panel = QFrame()
        panel.setObjectName("LoginPanel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(56, 56, 56, 40)
        pl.setSpacing(10)
        head = QLabel("Sign in")
        head.setObjectName("Welcome")
        pl.addWidget(head)
        hint = QLabel("Use your SAIMS account. Ask the school administrator if you need one.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        pl.addWidget(hint)
        pl.addSpacing(12)
        pl.addWidget(QLabel("Server"))
        self.mode = QComboBox()
        self.mode.addItem("This computer (built-in demo server)", "local")
        self.mode.addItem("School server…", "remote")
        self.mode.setCurrentIndex(max(self.mode.findData(self.prefs["server_mode"]), 0))
        self.url = QLineEdit(self.prefs["server_url"])
        self.url.setPlaceholderText("https://192.168.1.20:8765  or  https://saims.yourschool.example")
        self.mode.currentIndexChanged.connect(self._mode_changed)
        pl.addWidget(self.mode)
        pl.addWidget(self.url)
        pl.addWidget(QLabel("Username"))
        self.username = QLineEdit(self.prefs["last_username"])
        pl.addWidget(self.username)
        pl.addWidget(QLabel("Password"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self.sign_in)
        self.username.returnPressed.connect(self.password.setFocus)
        pl.addWidget(self.password)
        self.error = QLabel()
        self.error.setObjectName("FormError")
        self.error.setWordWrap(True)
        self.error.hide()
        pl.addWidget(self.error)
        pl.addSpacing(6)
        self.go = QPushButton("Sign in")
        self.go.setObjectName("Primary")
        self.go.setMinimumHeight(38)
        self.go.clicked.connect(self.sign_in)
        pl.addWidget(self.go)
        pl.addStretch()
        row.addWidget(panel, 1)
        self._mode_changed()
        (self.password if self.username.text() else self.username).setFocus()

    def _mode_changed(self) -> None:
        local = self.mode.currentData() == "local"
        self.url.setVisible(not local)
        if local:
            self.school.setText("Demo data loads automatically on first start.")
            self.demo_box.setText("<b>Demo accounts</b> (password <b>demo1234</b>)<br>"
                                  + "<br>".join(f"{u} — {r}" for u, r in DEMO_ACCOUNTS))
        else:
            self.school.setText("")
            self.demo_box.setText("")

    def _connect_remote(self, base: str) -> tuple[Api, dict] | None:
        """Connect to a school server. Servers with a certificate from a public authority just work; a SAIMS
        shared from another computer has its own certificate, which someone confirms once by its security code
        and this computer then remembers ("pins")."""
        parts = urlsplit(base)
        host, port = parts.hostname or "", parts.port or 443
        key = f"{host}:{port}"
        pins = dict(self.prefs.get("trusted_servers") or {})
        changed = False
        if key in pins:
            api = Api(base, tls.pinned_context(pins[key]))
            try:
                return api, api.info()
            except ApiError as exc:
                if exc.code != "untrusted_certificate":
                    raise
                changed = True  # the server now presents a different certificate
        else:
            api = Api(base)
            try:
                return api, api.info()
            except ApiError as exc:
                if exc.code != "untrusted_certificate":
                    raise
        try:
            pem = tls.fetch_certificate(host, port)
        except OSError as exc:
            raise ApiError(f"Cannot read the server's security certificate: {exc}", "network") from None
        QApplication.restoreOverrideCursor()
        trusted = TrustDialog(f"{host}:{port}", tls.short_code(pem), changed, self).exec()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        if not trusted:
            self._fail("Not connected: the server's security code was not confirmed.")
            return None
        api = Api(base, tls.pinned_context(pem))
        info = api.info()
        pins[key] = pem
        client_settings.save({"trusted_servers": pins})
        self.prefs["trusted_servers"] = pins
        return api, info

    def _fail(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()

    def sign_in(self) -> None:
        self.error.hide()
        local = self.mode.currentData() == "local"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.go.setEnabled(False)
        self.go.setText("Starting…" if local else "Signing in…")
        QApplication.processEvents()
        try:
            if local:
                base, verify = self.start_local_server()
                api = Api(base, verify)
                info = api.info()
            else:
                base = self.url.text().strip().rstrip("/")
                if base and "://" not in base:
                    base = f"https://{base}"
                    self.url.setText(base)
                if not base.startswith(("http://", "https://")) or len(base) < 10:
                    return self._fail("Enter the school server address, e.g. https://192.168.1.20:8765")
                if base.startswith("http://") and not base.startswith(("http://127.0.0.1", "http://localhost")):
                    return self._fail("Use an https:// address so passwords are encrypted in transit.")
                connected = self._connect_remote(base)
                if connected is None:
                    return None
                api, info = connected
            if info.get("api_version") != "v1":
                return self._fail(f"This server uses API {info.get('api_version')}; update SAIMS Desktop.")
            api.login(self.username.text(), self.password.text())
        except ApiError as exc:
            return self._fail(exc.message)
        except Exception as exc:  # noqa: BLE001 - e.g. built-in server failed to start
            return self._fail(str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self.go.setEnabled(True)
            self.go.setText("Sign in")
        client_settings.save({"server_mode": self.mode.currentData(), "server_url": self.url.text().strip(),
                              "last_username": self.username.text().strip()})
        self.api = api
        self.accept()
