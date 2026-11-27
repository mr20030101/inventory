"""Employees and the assets each one is accountable for (clearance view)."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSplitter, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

from saims.desktop.api import ApiError
from saims.desktop.ui import formatting as fmt
from saims.desktop.ui.forms import Field, ref_options
from saims.desktop.ui.pages.base import Page, RecordList
from saims.desktop.ui.widgets import Column, DataTable, status_color


class PeoplePage(Page):
    title = "People"

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Vertical)
        self.list = RecordList(api, "employees", "Employee", [
            Column("Employee no.", "employee_no"), Column("Name", "full_name"), Column("Position", "position"),
            Column("Department", "department"), Column("Email", "email"), Column("Phone", "phone"),
        ], lambda: [
            Field("employee_no", "Employee no.", required=True), Field("full_name", "Full name", required=True),
            Field("position", "Position"),
            Field("department_id", "Department", "choice", options=ref_options(api, "departments")),
            Field("email", "Email"), Field("phone", "Phone"),
        ], "employees.manage")
        self.list.table.selectionModel().selectionChanged.connect(self._show_assets)
        split.addWidget(self.list)
        lower = QWidget()
        ll = QVBoxLayout(lower)
        ll.setContentsMargins(0, 8, 0, 0)
        head = QHBoxLayout()
        self.assets_title = QLabel("Accountable assets")
        self.assets_title.setObjectName("CardTitle")
        head.addWidget(self.assets_title)
        head.addStretch()
        self.clearance_btn = QPushButton("Export clearance list")
        self.clearance_btn.clicked.connect(self._export_clearance)
        head.addWidget(self.clearance_btn)
        ll.addLayout(head)
        self.assets = DataTable([
            Column("Code", "asset_code"), Column("Asset", "name"), Column("Status", "status_label",
                                                                          color=status_color()),
            Column("Condition", "condition_label"), Column("Room", "room"), Column("Cost", "acquisition_cost",
                                                                                  fmt.money, numeric=True),
        ])
        ll.addWidget(self.assets)
        split.addWidget(lower)
        split.setSizes([420, 260])
        layout.addWidget(split)
        self.assets_title.setVisible(api.can("assets.view"))
        lower.setVisible(api.can("assets.view"))

    def refresh(self) -> None:
        self.list.refresh()
        self._show_assets()

    def _show_assets(self) -> None:
        emp = self.list.table.selected()
        self.clearance_btn.setEnabled(bool(emp))
        if not emp or not self.api.can("assets.view"):
            self.assets.set_rows([])
            self.assets_title.setText("Accountable assets — select an employee")
            return
        try:
            rows = self.api.get("/assets", employee_id=emp["id"])
        except ApiError:
            rows = []
        self.assets.set_rows(rows)
        self.assets_title.setText(f"Assets assigned to {emp['full_name']} ({len(rows)})")

    def _export_clearance(self) -> None:
        emp = self.list.table.selected()
        if emp:
            self.export(self.assets, f"Clearance - {emp['full_name']}", "pdf",
                        filters=f"{emp['employee_no']} · {emp['position']} · {emp['department']}")
