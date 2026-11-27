"""Audit log viewer (read-only: the API offers no way to edit or delete entries)."""
from __future__ import annotations

import json

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QSplitter, QVBoxLayout
from PySide6.QtCore import Qt

from saims.desktop.api import ApiError
from saims.desktop.ui import formatting as fmt
from saims.desktop.ui.pages.base import Page
from saims.desktop.ui.widgets import Column, DataTable, show_error


class AuditPage(Page):
    title = "Audit Log"

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        today = QDate.currentDate()
        self.start, self.end = QDateEdit(today.addDays(-30)), QDateEdit(today)
        for d in (self.start, self.end):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd MMM yyyy")
            d.dateChanged.connect(self.refresh)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search action or summary…")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.refresh)
        for w in (QLabel("From"), self.start, QLabel("to"), self.end, self.search):
            bar.addWidget(w)
        export = self.button("Export", lambda: self.export(self.table, "Audit log"), permission="reports.export")
        bar.addWidget(export)
        layout.addLayout(bar)
        split = QSplitter(Qt.Orientation.Vertical)
        self.table = DataTable([
            Column("When", "created_at", fmt.when), Column("User", "username"), Column("Action", "action"),
            Column("Record", "entity_type"), Column("Summary", "summary"),
            Column("Result", "success", lambda s: "OK" if s else "Failed",
                   color=lambda r: None if r["success"] else "danger"),
        ])
        self.table.selectionModel().selectionChanged.connect(self._show)
        split.addWidget(self.table)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Select an entry to see the recorded before / after values.")
        split.addWidget(self.detail)
        split.setSizes([500, 160])
        layout.addWidget(split)
        note = QLabel("Entries are append-only. Nobody, including administrators, can edit or delete them "
                      "through SAIMS.")
        note.setObjectName("Hint")
        layout.addWidget(note)

    def refresh(self) -> None:
        try:
            rows = self.api.get("/audit-logs", q=self.search.text(), start=self.start.date().toString("yyyy-MM-dd"),
                                end=self.end.date().toString("yyyy-MM-dd"), limit=2000)
        except ApiError as exc:
            return show_error(self, exc)
        self.table.set_rows(rows)

    def _show(self) -> None:
        row = self.table.selected()
        if not row:
            return self.detail.clear()
        text = f"{row['action']} on {row['entity_type']} {row['entity_id']}\n{row['summary']}"
        if row["changes"]:
            try:
                text += "\n\n" + json.dumps(json.loads(row["changes"]), indent=2, ensure_ascii=False)
            except ValueError:
                text += "\n\n" + row["changes"]
        self.detail.setPlainText(text)
