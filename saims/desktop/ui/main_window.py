"""Main window: teal sidebar, header and pages. Navigation follows the signed-in user's permissions."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from saims import APP_FULL_NAME, __version__
from saims.desktop import client_settings
from saims.desktop.api import Api, ApiError
from saims.desktop.ui import formatting, theme
from saims.desktop.ui.forms import Field, run_form
from saims.desktop.ui.widgets import NavItem
from saims.desktop.ui.pages.assets import AssetsPage
from saims.desktop.ui.pages.audit import AuditPage
from saims.desktop.ui.pages.borrowing import BorrowingPage
from saims.desktop.ui.pages.consumables import ConsumablesPage
from saims.desktop.ui.pages.dashboard import DashboardPage
from saims.desktop.ui.pages.people import PeoplePage
from saims.desktop.ui.pages.reports import ReportsPage
from saims.desktop.ui.pages.setup import SetupPage
from saims.desktop.ui.pages.users import UsersPage

# key, label, icon, page class, permission needed (any of)
PAGES = [
    ("dashboard", "Dashboard", "dashboard", DashboardPage, ("dashboard.view",)),
    ("assets", "Assets", "box", AssetsPage, ("assets.view", "assets.view_own")),
    ("consumables", "Consumables", "layers", ConsumablesPage, ("inventory.view",)),
    ("borrowing", "Borrowing", "swap", BorrowingPage, ("borrowing.view", "borrowing.view_own")),
    ("people", "People", "people", PeoplePage, ("employees.view",)),
    ("setup", "School Setup", "school", SetupPage, ("locations.view", "departments.view", "suppliers.view")),
    ("reports", "Reports", "reports", ReportsPage, ("reports.view",)),
    ("audit", "Audit Log", "history", AuditPage, ("system.audit_logs.view",)),
    ("users", "Users & Roles", "shield", UsersPage, ("users.view",)),
]


class MainWindow(QMainWindow):
    signed_out = Signal(str)  # reason shown on the sign-in screen ("" for a normal sign-out)

    def __init__(self, api: Api, sharing=None):
        """`sharing`: the desktop app when signed in to the built-in server (enables network sharing)."""
        super().__init__()
        self.api = api
        self.sharing = sharing
        api.on_session_expired = lambda: QTimer.singleShot(0, lambda: self._sign_out("Your session has ended. "
                                                                                     "Please sign in again."))
        settings = api.settings()
        formatting.set_currency(settings.get("currency_symbol", "$"))
        self.school_name = settings.get("school_name", "")
        self.setWindowTitle(f"{self.school_name} — SAIMS")
        self.resize(1360, 860)
        self.setMinimumSize(1120, 700)

        # People who only see their own records (teachers) get "My …" pages.
        own_labels = {"assets": ("assets.view", "My Assets"), "borrowing": ("borrowing.view", "My Requests")}
        self.pages = []
        for k, label, icon, cls, perms in PAGES:
            if api.can_any(*perms):
                full, own_label = own_labels.get(k, (None, label))
                self.pages.append((k, own_label if full and not api.can(full) else label, icon, cls(api)))
        self.page_by_key = {k: page for k, _, _, page in self.pages}

        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._sidebar())
        content = QWidget()
        content.setObjectName("Content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._header())
        self.stack = QStackedWidget()
        for _, _, _, page in self.pages:
            self.stack.addWidget(page)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(18, 16, 18, 16)
        hl.addWidget(self.stack)
        cl.addWidget(holder, 1)
        row.addWidget(content, 1)
        self.setCentralWidget(root)

        dash = self.page_by_key.get("dashboard")
        if dash:
            dash.navigate.connect(self.open_record)
        QShortcut(QKeySequence("Ctrl+K"), self, self.search.setFocus)
        QShortcut(QKeySequence("F5"), self, self.refresh_current)
        self._apply_icons()
        self.go(0)

    # ------------------------------------------------------------------ layout
    def _sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(224)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(12, 24, 12, 16)
        layout.setSpacing(4)
        # Product logo on top, then the school this SAIMS belongs to.
        brand = QLabel()
        brand.setPixmap(theme.logo(176, reverse=True))
        brand.setAccessibleName(APP_FULL_NAME)
        brand.setToolTip(APP_FULL_NAME)
        brand.setContentsMargins(6, 0, 0, 0)
        layout.addWidget(brand)
        layout.addSpacing(16)
        school = QFrame()
        school.setObjectName("SchoolBlock")
        row = QHBoxLayout(school)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)
        avatar = QLabel("".join(w[0] for w in self.school_name.split()[:2]).upper() or "S")
        avatar.setObjectName("Avatar")
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name = QLabel(self.school_name)
        name.setObjectName("BrandName")
        name.setWordWrap(True)
        row.addWidget(avatar)
        row.addWidget(name, 1)
        layout.addWidget(school)
        layout.addSpacing(18)
        self.nav = QButtonGroup(self)
        self.nav_buttons: list[NavItem] = []
        for i, (_, label, icon_name, _) in enumerate(self.pages):
            b = NavItem(label, icon_name)
            self.nav.addButton(b, i)
            self.nav_buttons.append(b)
            layout.addWidget(b)
        self.nav.idClicked.connect(self.go)
        layout.addStretch()
        self.settings_btn = NavItem("Settings", "settings", checkable=False)
        self.settings_btn.clicked.connect(self._settings)
        self.settings_btn.setVisible(self.api.can("system.settings"))
        self.logout_btn = NavItem("Sign out", "logout", checkable=False)
        self.logout_btn.clicked.connect(lambda: self._sign_out(""))
        layout.addWidget(self.settings_btn)
        layout.addWidget(self.logout_btn)
        self.share_badge = QLabel()
        self.share_badge.setObjectName("Version")
        self.share_badge.setContentsMargins(NavItem.PAD, 6, 0, 0)
        self.share_badge.setWordWrap(True)
        layout.addWidget(self.share_badge)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("Version")
        ver.setContentsMargins(NavItem.PAD, 2, 0, 0)
        layout.addWidget(ver)
        self.update_sharing_badge()
        return bar

    def update_sharing_badge(self) -> None:
        on = bool(self.sharing and self.sharing.sharing)
        self.share_badge.setVisible(on)
        if on:
            self.share_badge.setText(f"● Shared on the network · port {self.sharing.share_port}")
            self.share_badge.setToolTip("Other computers on this network can sign in to SAIMS on this computer. "
                                        "Open the user menu ▸ Share on the local network… for details.")

    def _header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 12, 22, 12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("Welcome")
        sub = QHBoxLayout()
        self.date = QLabel(date.today().strftime("%A, %d %B %Y"))
        self.date.setObjectName("Hint")
        role = QLabel(" · ".join(self.api.me.get("role_names", [])))
        role.setObjectName("RoleChip")
        sub.addWidget(self.date)
        sub.addWidget(role)
        sub.addStretch()
        titles.addWidget(self.title)
        titles.addLayout(sub)
        layout.addLayout(titles)
        layout.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("HeaderSearch")
        self.search.setPlaceholderText("Find an asset or scan a label…  (Ctrl+K)")
        self.search.setClearButtonEnabled(True)
        self.search_action = self.search.addAction(theme.icon("search", "muted"),
                                                   QLineEdit.ActionPosition.TrailingPosition)
        self.search.returnPressed.connect(self._search)
        self.search.setVisible(self.api.can("assets.view"))
        layout.addWidget(self.search)
        layout.addSpacing(8)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ThemeToggle")
        self.theme_btn.setCheckable(True)
        self.theme_btn.setFixedSize(54, 26)
        self.theme_btn.setIconSize(QSize(18, 18))
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_btn)
        self.bell = QToolButton()
        self.bell.setObjectName("Bell")
        self.bell.setIconSize(QSize(20, 20))
        self.bell.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.bell.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bell.clicked.connect(self._alerts_menu)
        layout.addWidget(self.bell)
        self.user_btn = QToolButton()
        self.user_btn.setObjectName("UserMenu")
        self.user_btn.setText(self.api.me.get("full_name", ""))
        self.user_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.user_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # Chevron drawn as an icon on the right of the name (Qt's own menu arrow sits in the corner).
        self.user_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.user_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.user_btn.setIconSize(QSize(16, 16))
        menu = QMenu(self)
        menu.addAction("Change my password…", self._change_password)
        menu.addAction("About SAIMS", self._about)
        if self.sharing is not None and self.api.can("system.settings"):
            menu.addAction("Share on the local network…", self._share)
        menu.addSeparator()
        menu.addAction("Sign out", lambda: self._sign_out(""))
        self.user_btn.setMenu(menu)
        layout.addWidget(self.user_btn)
        return header

    # ------------------------------------------------------------------ behaviour
    def go(self, index: int) -> None:
        if not self.pages:
            return
        self.nav_buttons[index].setChecked(True)
        self.stack.setCurrentIndex(index)
        key, label, _, page = self.pages[index]
        first = self.api.me.get("full_name", "").replace("Dr. ", "").split(" ")[0]
        self.title.setText(f"Welcome, {first}!" if key == "dashboard" else label)
        self.refresh_current()

    def go_key(self, key: str) -> QWidget | None:
        for i, (k, _, _, page) in enumerate(self.pages):
            if k == key:
                self.go(i)
                return page
        return None

    def refresh_current(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.stack.currentWidget().refresh()
        finally:
            QApplication.restoreOverrideCursor()
        self._update_bell()

    def open_record(self, target: str, record_id: str) -> None:
        page = self.go_key(target)
        if page and record_id and hasattr(page, "show_record"):
            page.show_record(record_id)

    def _search(self) -> None:
        page = self.go_key("assets")
        if page:
            page.search_for(self.search.text().strip())

    def _update_bell(self) -> None:
        try:
            self.alerts = self.api.get("/dashboard").get("alerts", []) if self.api.can("dashboard.view") else []
        except ApiError:
            self.alerts = []
        urgent = [a for a in self.alerts if a["severity"] != "info"]
        self.bell.setText(str(len(urgent)) if urgent else "")
        self.bell.setIcon(theme.icon("bell", "warn_fg" if urgent else "text"))
        self.bell.setProperty("alert", bool(urgent))
        self.bell.style().unpolish(self.bell)
        self.bell.style().polish(self.bell)

    def _alerts_menu(self) -> None:
        menu = QMenu(self)
        if not getattr(self, "alerts", None):
            menu.addAction("No alerts").setEnabled(False)
        for a in self.alerts[:15]:
            icon = theme.icon("alert", {"critical": "danger", "warning": "warning"}.get(a["severity"], "info"))
            menu.addAction(icon, a["text"], lambda t=a["target"], i=a.get("id", ""): self.open_record(t, i))
        menu.exec(self.bell.mapToGlobal(self.bell.rect().bottomLeft()))

    def _apply_icons(self) -> None:
        for btn in (*self.nav_buttons, self.settings_btn, self.logout_btn):
            btn.update()  # nav items read theme colours when they paint
        self.search_action.setIcon(theme.icon("search", "muted"))
        self.user_btn.setIcon(theme.icon("chevron", "muted"))
        dark = theme.current_name() == "dark"
        self.theme_btn.setChecked(dark)
        self.theme_btn.setIcon(QIcon(theme.knob(dark)))
        self.theme_btn.setToolTip("Switch to light mode" if dark else "Switch to dark mode")

    def _toggle_theme(self) -> None:
        name = "light" if theme.current_name() == "dark" else "dark"
        client_settings.save({"theme": name})
        theme.apply(QApplication.instance(), name)
        self._apply_icons()
        self.refresh_current()

    def _settings(self) -> None:
        fields = [Field("school_name", "School name", required=True), Field("currency_symbol", "Currency symbol"),
                  Field("asset_code_prefix", "Asset code prefix", help="New asset codes look like PREFIX-2026-00001."),
                  Field("item_code_prefix", "Consumable code prefix")]
        result = run_form(self, "School settings", fields, self.api.settings(),
                          lambda v: self.api.patch("/settings", v))
        if result:
            formatting.set_currency(result.get("currency_symbol", "$"))
            QMessageBox.information(self, "Settings saved",
                                    "Settings saved. The school name updates the next time you sign in.")
            self.refresh_current()

    def _share(self) -> None:
        from saims.desktop.ui.sharing import ShareDialog
        demo = bool(self.api.info().get("demo"))
        ShareDialog(self.sharing, demo, self).exec()
        self.update_sharing_badge()

    def _about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("About SAIMS")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(8)
        art = QLabel()
        art.setPixmap(theme.logo(260, reverse=theme.current_name() == "dark"))
        layout.addWidget(art)
        layout.addSpacing(10)
        server = "this computer" + (" (shared on the network)" if self.sharing and self.sharing.sharing else "") \
            if self.sharing is not None else self.api.base_url
        for text, name in ((APP_FULL_NAME, "CardTitle"), (f"Version {__version__}", "Hint"),
                           (f"{self.school_name} · server: {server}", "Hint")):
            label = QLabel(text)
            label.setObjectName(name)
            label.setWordWrap(True)
            layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _change_password(self) -> None:
        fields = [Field("current_password", "Current password", "password", required=True),
                  Field("new_password", "New password", "password", required=True, help="At least 8 characters.")]
        if run_form(self, "Change my password", fields, None, lambda v: self.api.post("/auth/password", v)):
            QMessageBox.information(self, "Password changed", "Your password has been changed.")

    def _sign_out(self, reason: str) -> None:
        if not self.isVisible():
            return
        if not reason:
            self.api.logout()
        self.hide()
        self.signed_out.emit(reason)
        self.deleteLater()
