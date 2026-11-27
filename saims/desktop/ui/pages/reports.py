"""Reports: pick a report, set the date range, view and export (CSV, Excel, PDF). Exports are logged."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from saims.desktop.api import ApiError
from saims.desktop.ui import formatting as fmt
from saims.desktop.ui.export import export_table
from saims.desktop.ui.pages.base import Page
from saims.desktop.ui.widgets import Column, DataTable, show_error

DATED = {"stock_movements", "borrowing", "user_activity"}
FORMATTERS = {"money": (fmt.money, True), "number": (fmt.qty, True), "date": (fmt.day, False),
              "datetime": (fmt.when, False), "text": (None, False)}


class ReportsPage(Page):
    title = "Reports"

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        self.list = QListWidget()
        self.list.setObjectName("ReportList")
        self.list.currentItemChanged.connect(lambda *_: self.run())
        split.addWidget(self.list)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.heading = QLabel()
        self.heading.setObjectName("DetailTitle")
        self.meta = QLabel()
        self.meta.setObjectName("Hint")
        self.meta.setWordWrap(True)
        rl.addWidget(self.heading)
        rl.addWidget(self.meta)
        bar = QHBoxLayout()
        today = QDate.currentDate()
        self.start = QDateEdit(today.addDays(-90))
        self.end = QDateEdit(today)
        for d in (self.start, self.end):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd MMM yyyy")
            d.dateChanged.connect(self.run)
        self.from_label, self.to_label = QLabel("From"), QLabel("to")
        for w in (self.from_label, self.start, self.to_label, self.end):
            bar.addWidget(w)
        bar.addStretch()
        self.export_btns = []
        for kind, label in (("xlsx", "Excel"), ("csv", "CSV"), ("pdf", "PDF")):
            b = QPushButton(f"Export {label}")
            b.clicked.connect(lambda _=False, k=kind: self.export_report(k))
            b.setVisible(api.can("reports.export"))
            bar.addWidget(b)
            self.export_btns.append(b)
        rl.addLayout(bar)
        self.table = DataTable([])
        rl.addWidget(self.table, 1)
        self.note = QLabel()
        self.note.setObjectName("Hint")
        self.note.setWordWrap(True)
        rl.addWidget(self.note)
        split.addWidget(right)
        split.setSizes([260, 900])
        layout.addWidget(split)
        self.report: dict | None = None

    def refresh(self) -> None:
        if self.list.count():
            return self.run()
        try:
            reports = self.api.get("/reports")
        except ApiError as exc:
            return show_error(self, exc)
        for r in reports:
            item = QListWidgetItem(r["title"])
            item.setToolTip(r["description"])
            item.setData(Qt.ItemDataRole.UserRole, r["key"])
            self.list.addItem(item)
        if reports:
            self.list.setCurrentRow(0)

    def run(self, export: str | None = None) -> None:
        item = self.list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        dated = key in DATED
        for w in (self.from_label, self.start, self.to_label, self.end):
            w.setVisible(dated)
        params = {"start": self.start.date().toString("yyyy-MM-dd"), "end": self.end.date().toString("yyyy-MM-dd")}
        if export:
            params["export"] = export
        try:
            self.report = self.api.get(f"/reports/{key}", **params)
        except ApiError as exc:
            return show_error(self, exc)
        r = self.report
        self.heading.setText(r["title"])
        rng = f" · {fmt.day(r['filters']['start'])} – {fmt.day(r['filters']['end'])}" if r["filters"] else ""
        self.meta.setText(f"{r['school_name']} · generated {fmt.when(r['generated_at'])} by {r['generated_by']}{rng}"
                          f" · {len(r['rows'])} rows")
        cols = []
        for c in r["columns"]:
            f, numeric = FORMATTERS.get(c["kind"], (None, False))
            cols.append(Column(c["label"], c["key"], f, numeric))
        self.table.source.columns = cols
        self.table.set_rows(r["rows"])
        self.note.setText(r.get("note", ""))

    def export_report(self, kind: str) -> None:
        if not self.report:
            return
        headers, rows = self.table.visible_table()
        r = self.report
        filters = f"{fmt.day(r['filters']['start'])} – {fmt.day(r['filters']['end'])}" if r["filters"] else ""
        if export_table(self, kind, r["title"], headers, rows,
                        {"school": r["school_name"], "user": r["generated_by"], "filters": filters,
                         "note": r.get("note", "")}):
            self.run(export=kind)  # records the export in the audit log
