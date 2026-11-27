"""Base page and a generic list page for reference data."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget

from saims.desktop.api import Api, ApiError
from saims.desktop.ui import theme
from saims.desktop.ui.export import export_table
from saims.desktop.ui.forms import Field, run_form
from saims.desktop.ui.widgets import Column, DataTable, confirm, show_error


class Page(QWidget):
    title = ""

    def __init__(self, api: Api, parent=None):
        super().__init__(parent)
        self.api = api

    def refresh(self) -> None:  # pragma: no cover - overridden
        pass

    def button(self, text: str, slot: Callable, icon: str | None = None, primary: bool = False,
               permission: str | None = None) -> QPushButton:
        b = QPushButton(text)
        if icon:
            b.setIcon(theme.icon(icon, "on_accent" if primary else "text"))
        if primary:
            b.setObjectName("Primary")
        b.clicked.connect(slot)
        if permission and not self.api.can(permission):
            b.setVisible(False)
        return b

    def export(self, table: DataTable, title: str, kind: str = "xlsx", filters: str = "",
               selected_only: bool = False) -> None:
        headers, rows = table.visible_table(selected_only)
        if selected_only:
            filters = "; ".join(x for x in (filters, f"{len(rows)} selected rows") if x)
        export_table(self, kind, title, headers, rows,
                     {"school": self.api.settings().get("school_name", ""), "user": self.api.me.get("full_name"),
                      "filters": filters})

    def export_button(self, table: DataTable, title: str, filters: Callable[[], str] = lambda: "") -> QPushButton:
        """Export ▾ menu: Excel, CSV or PDF; with rows selected, choose to export only those."""
        button = QPushButton("Export")
        menu = QMenu(button)
        only = menu.addAction("Only the selected rows")
        only.setCheckable(True)
        menu.addSeparator()
        for kind, label in (("xlsx", "Excel workbook"), ("csv", "CSV file"), ("pdf", "PDF document")):
            menu.addAction(label, lambda k=kind: self.export(table, title, k, filters(),
                                                             only.isChecked() and only.isEnabled()))

        def before_show() -> None:
            n = len(table.selected_rows())
            only.setText(f"Only the {n} selected row{'s' if n != 1 else ''}" if n else "Only the selected rows")
            only.setEnabled(n > 0)
            only.setChecked(n > 1)

        menu.aboutToShow.connect(before_show)
        button.setMenu(menu)
        button.setVisible(self.api.can("reports.export"))
        return button

    def call(self, fn: Callable[[], Any], refresh: bool = True) -> Any:
        try:
            result = fn()
        except ApiError as exc:
            show_error(self, exc)
            return None
        if refresh:
            self.refresh()
        return result


class RecordList(Page):
    """List + create / edit / archive for a reference resource (/ref/<key>)."""

    def __init__(self, api: Api, key: str, noun: str, columns: list[Column], fields: Callable[[], list[Field]],
                 manage_permission: str, parent=None, params: dict | None = None):
        super().__init__(api, parent)
        self.key, self.noun, self.fields, self.params = key, noun, fields, params or {}
        self.manage = api.can(manage_permission)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"Search {noun.lower()}s…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.show_archived = QCheckBox("Show archived")
        self.show_archived.toggled.connect(self.refresh)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.show_archived)
        self.add_btn = self.button(f"New {noun.lower()}", self.add, "box", primary=True)
        self.edit_btn = self.button("Edit", self.edit)
        self.archive_btn = self.button("Archive", self.toggle_archive)
        for b in (self.add_btn, self.edit_btn, self.archive_btn):
            b.setVisible(self.manage)
            bar.addWidget(b)
        layout.addLayout(bar)
        self.table = DataTable(columns, row_color=lambda r: None if r.get("is_active", True) else "muted")
        self.table.doubleClicked.connect(lambda _: self.edit())
        self.table.selectionModel().selectionChanged.connect(self._update)
        layout.addWidget(self.table)
        self.count = QLabel()
        self.count.setObjectName("Hint")
        layout.addWidget(self.count)
        self._rows: list[dict] = []

    def refresh(self) -> None:
        try:
            self._rows = self.api.get(f"/ref/{self.key}", include_inactive=self.show_archived.isChecked(),
                                      **self.params)
        except ApiError as exc:
            show_error(self, exc)
            return
        self._filter()

    def _filter(self) -> None:
        q = self.search.text().strip().lower()
        rows = [r for r in self._rows if not q or q in " ".join(str(v) for v in r.values()).lower()]
        self.table.set_rows(rows)
        self.count.setText(f"{len(rows)} {self.noun.lower()}{'s' if len(rows) != 1 else ''}")
        self._update()

    def _update(self) -> None:
        row = self.table.selected()
        self.edit_btn.setEnabled(row is not None)
        self.archive_btn.setEnabled(row is not None)
        self.archive_btn.setText("Restore" if row and not row.get("is_active", True) else "Archive")

    def add(self) -> None:
        if run_form(self, f"New {self.noun.lower()}", self.fields(), {**self.params},
                    lambda v: self.api.post(f"/ref/{self.key}", {**self.params, **v})):
            self.refresh()

    def edit(self) -> None:
        row = self.table.selected()
        if row and self.manage and run_form(self, f"Edit {self.noun.lower()}", self.fields(), row,
                                            lambda v: self.api.patch(f"/ref/{self.key}/{row['id']}", v)):
            self.refresh()

    def toggle_archive(self) -> None:
        row = self.table.selected()
        if not row:
            return
        active = row.get("is_active", True)
        name = row.get("name") or row.get("full_name")
        if active and not confirm(self, f"Archive {self.noun.lower()}",
                                  f"Archive {name}? It will be hidden from lists but its history is kept."):
            return
        self.call(lambda: self.api.post(f"/ref/{self.key}/{row['id']}/{'archive' if active else 'restore'}"))
