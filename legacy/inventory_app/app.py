"""Application start-up."""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from inventory_app import APP_NAME, __version__, database, paths
from inventory_app.repository import Repository
from inventory_app.ui import formatting, theme
from inventory_app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("InventoryManager")
    app.setDesktopFileName("inventory-manager")
    app.setStyle("Fusion")
    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 10))
    app.setFont(font)
    icon_file = paths.resource_path("inventory_app/assets/icon.png")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    db_file = paths.db_path()
    try:
        conn = database.connect(db_file)
    except Exception as exc:  # noqa: BLE001 - show any start-up failure to the user
        QMessageBox.critical(None, APP_NAME, f"Could not open the database:\n{db_file}\n\n{exc}")
        return 1
    repo = Repository(conn)
    formatting.set_currency(repo.get_setting("currency", "$"))
    theme.apply(app, repo.get_setting("theme", "light"))

    window = MainWindow(repo, db_file)
    window.show()
    code = app.exec()
    conn.close()
    return code
