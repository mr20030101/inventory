"""Main window: teal sidebar navigation, header bar and page stack."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from inventory_app import APP_NAME, __version__, csv_io, database
from inventory_app.paths import data_dir
from inventory_app.repository import InventoryError, Repository
from inventory_app.sample_data import load_sample_data
from inventory_app.ui import theme
from inventory_app.ui.dashboard import DashboardView
from inventory_app.ui.dialogs import SettingsDialog
from inventory_app.ui.lookups import CategoriesView, SuppliersView
from inventory_app.ui.movements import MovementsView
from inventory_app.ui.products import ProductsView
from inventory_app.ui.reports import ReportsView
from inventory_app.ui.widgets import confirm

PAGES = [
    ("dashboard", "Dashboard"),
    ("box", "Products"),
    ("movements", "Stock Movements"),
    ("tag", "Categories"),
    ("truck", "Suppliers"),
    ("reports", "Reports"),
]


class MainWindow(QMainWindow):
    def __init__(self, repo: Repository, db_file: Path):
        super().__init__()
        self.repo, self.db_file = repo, db_file
        self.resize(1280, 820)
        self.setMinimumSize(1060, 680)

        self.dashboard = DashboardView(repo)
        self.products = ProductsView(repo)
        self.movements = MovementsView(repo)
        self.views = [self.dashboard, self.products, self.movements,
                      CategoriesView(repo), SuppliersView(repo), ReportsView(repo)]
        self.reports = self.views[5]

        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_sidebar())
        right = QWidget()
        right.setObjectName("Content")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_header())
        self.stack = QStackedWidget()
        for view in self.views:
            self.stack.addWidget(view)
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(18, 16, 18, 16)
        page_layout.addWidget(self.stack)
        right_layout.addWidget(page, 1)
        row.addWidget(right, 1)
        self.setCentralWidget(root)

        self.products.show_history.connect(self._show_history)
        self.dashboard.open_low_stock.connect(self._show_reorder)
        QShortcut(QKeySequence.StandardKey.Quit, self, self.close)
        QShortcut(QKeySequence("Ctrl+K"), self, self.search.setFocus)

        self._apply_branding()
        self.nav_group.button(0).setChecked(True)
        self._go(0)

    # ------------------------------------------------------------------ layout
    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 26, 0, 18)
        layout.setSpacing(4)

        self.avatar = QLabel()
        self.avatar.setObjectName("Avatar")
        self.avatar.setFixedSize(68, 68)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand = QLabel()
        self.brand.setObjectName("BrandName")
        self.brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand.setWordWrap(True)
        sub = QLabel(APP_NAME)
        sub.setObjectName("BrandSub")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for w in (self.avatar, self.brand, sub):
            wrap = QHBoxLayout()
            wrap.setContentsMargins(0, 0, 14, 0)
            wrap.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)
            layout.addLayout(wrap)
        layout.addSpacing(22)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for i, (_icon, label) in enumerate(PAGES):
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIconSize(QSize(18, 18))
            self.nav_group.addButton(btn, i)
            self.nav_buttons.append(btn)
            layout.addWidget(btn)
        self.nav_group.idClicked.connect(self._go)
        layout.addStretch()

        self.data_btn = QPushButton("Data")
        self.data_btn.setObjectName("NavButton")
        self.data_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.data_btn.setIconSize(QSize(18, 18))
        self.data_btn.clicked.connect(self._show_data_menu)
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setObjectName("NavButton")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setIconSize(QSize(18, 18))
        self.settings_btn.clicked.connect(self._settings)
        layout.addWidget(self.data_btn)
        layout.addWidget(self.settings_btn)
        layout.addSpacing(8)
        version = QLabel(f"v{__version__}")
        version.setObjectName("Version")
        version.setContentsMargins(16, 0, 0, 0)
        layout.addWidget(version)
        return sidebar

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 12, 22, 12)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel()
        self.title.setObjectName("Welcome")
        self.subtitle = QLabel(date.today().strftime("%A, %d %B %Y"))
        self.subtitle.setObjectName("Hint")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        layout.addLayout(titles)
        layout.addStretch()

        self.search = QLineEdit()
        self.search.setObjectName("HeaderSearch")
        self.search.setPlaceholderText("Search products…  (Ctrl+K)")
        self.search.setClearButtonEnabled(True)
        self.search_action = self.search.addAction(theme.icon("search", "muted"), QLineEdit.ActionPosition.TrailingPosition)
        self.search.textEdited.connect(self._global_search)
        self.search.returnPressed.connect(lambda: self._global_search(self.search.text()))
        layout.addWidget(self.search)
        layout.addSpacing(10)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ThemeToggle")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.setIconSize(QSize(18, 18))
        self.theme_btn.setCheckable(True)
        self.theme_btn.setFixedSize(54, 26)
        self.theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_btn)

        self.bell = QToolButton()
        self.bell.setObjectName("Bell")
        self.bell.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bell.setIconSize(QSize(20, 20))
        self.bell.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.bell.clicked.connect(self._show_reorder)
        layout.addWidget(self.bell)
        return header

    # -------------------------------------------------------------- behaviour
    def _go(self, index: int) -> None:
        self.nav_buttons[index].setChecked(True)
        self.stack.setCurrentIndex(index)
        self._refresh_current()

    def _refresh_current(self) -> None:
        index = self.stack.currentIndex()
        if index == 0:
            name = self.repo.get_setting("business_name", "")
            self.title.setText(f"Welcome{', ' + name if name else ' back'}!")
        else:
            self.title.setText(PAGES[index][1])
        self.stack.currentWidget().refresh()
        self._update_bell()

    def _update_bell(self) -> None:
        low = self.repo.summary()["low_stock"]
        self.bell.setText(str(low) if low else "")
        self.bell.setProperty("alert", low > 0)
        self.bell.setIcon(theme.icon("bell", "warn_fg" if low else "text"))
        self.bell.setToolTip(f"{low} product(s) at or below reorder level" if low else "No low-stock alerts")
        self.bell.style().unpolish(self.bell)
        self.bell.style().polish(self.bell)

    def _global_search(self, text: str) -> None:
        if self.stack.currentWidget() is not self.products:
            self._go(1)
        self.products.search.setText(text)

    def _show_history(self, product_id: int) -> None:
        self._go(2)
        self.movements.show_product(product_id)

    def _show_reorder(self) -> None:
        self._go(5)
        self.reports.tabs.setCurrentIndex(1)

    def _apply_branding(self) -> None:
        name = self.repo.get_setting("business_name", "") or "My Business"
        initials = "".join(w[0] for w in name.split()[:2]).upper() or "IM"
        self.avatar.setText(initials)
        self.brand.setText(name)
        self.setWindowTitle(f"{name} — {APP_NAME}")
        self._apply_icons()

    def _apply_icons(self) -> None:
        for btn, (icon_name, _) in zip(self.nav_buttons, PAGES):
            btn.setIcon(theme.icon(icon_name, "sidebar_text", checked_token="nav_active_text"))
        self.data_btn.setIcon(theme.icon("data", "sidebar_text"))
        self.settings_btn.setIcon(theme.icon("settings", "sidebar_text"))
        self.search_action.setIcon(theme.icon("search", "muted"))
        dark = theme.current_name() == "dark"
        self.theme_btn.setChecked(dark)
        self.theme_btn.setIcon(QIcon(theme.knob(dark)))
        self.theme_btn.setToolTip("Switch to light mode" if dark else "Switch to dark mode")

    def _toggle_theme(self) -> None:
        name = "light" if theme.current_name() == "dark" else "dark"
        self.repo.set_setting("theme", name)
        theme.apply(QApplication.instance(), name)
        self._apply_icons()
        self._refresh_current()
        self.update()

    def _show_data_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Import products from CSV…", self._import_csv)
        menu.addAction("Export products to CSV…", self._export_csv)
        menu.addSeparator()
        menu.addAction("Back up database…", self._backup)
        menu.addAction("Restore from backup…", self._restore)
        menu.addAction("Open data folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))
        menu.addSeparator()
        sample = menu.addAction("Load sample data", self._load_sample)
        sample.setEnabled(not self.repo.list_products())
        menu.addAction(f"About {APP_NAME}", self._about)
        menu.exec(self.data_btn.mapToGlobal(self.data_btn.rect().topRight()))

    # ----------------------------------------------------------------- actions
    def _settings(self) -> None:
        if SettingsDialog(self.repo, self).exec():
            self._apply_branding()
            self._refresh_current()

    def _import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import products", "", "CSV files (*.csv);;All files (*)")
        if not path:
            return
        try:
            result = csv_io.import_products(self.repo, path)
        except (InventoryError, OSError, UnicodeDecodeError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        message = f"Created {result.created} and updated {result.updated} products."
        if result.errors:
            shown = "\n".join(result.errors[:15])
            more = f"\n…and {len(result.errors) - 15} more" if len(result.errors) > 15 else ""
            message += f"\n\n{len(result.errors)} rows were skipped:\n{shown}{more}"
        QMessageBox.information(self, "Import complete", message)
        self._refresh_current()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export products", "products.csv", "CSV files (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            count = csv_io.export_products(self.repo, path)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export complete", f"Exported {count} products to\n{path}")

    def _backup(self) -> None:
        default = str(Path.home() / f"inventory-backup-{date.today().isoformat()}.db")
        path, _ = QFileDialog.getSaveFileName(self, "Back up database", default, "Database files (*.db)")
        if not path:
            return
        try:
            target = sqlite3.connect(path)
            with target:
                self.repo.conn.backup(target)
            target.close()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))
            return
        QMessageBox.information(self, "Backup complete", f"Database backed up to\n{path}")

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore from backup", str(Path.home()),
                                              "Database files (*.db);;All files (*)")
        if not path:
            return
        if not database.is_inventory_db(path):
            QMessageBox.critical(self, "Restore failed", "That file is not an Inventory Manager database.")
            return
        if not confirm(self, "Restore from backup",
                       "Replace ALL current data with the contents of this backup?\n\n"
                       "Consider backing up the current data first."):
            return
        try:
            source = sqlite3.connect(path)
            source.backup(self.repo.conn)
            source.close()
            database.migrate(self.repo.conn)
        except (sqlite3.Error, RuntimeError) as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        theme.apply(QApplication.instance(), self.repo.get_setting("theme", theme.current_name()))
        self._apply_branding()
        self._refresh_current()
        QMessageBox.information(self, "Restore complete", "Data restored from backup.")

    def _load_sample(self) -> None:
        try:
            load_sample_data(self.repo)
        except InventoryError as exc:
            QMessageBox.warning(self, "Sample data", str(exc))
        self._refresh_current()

    def _about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<b>{APP_NAME}</b> {__version__}<br>Desktop stock inventory for Windows and Linux."
                          f"<br><br>Database:<br><code>{self.db_file}</code>")
