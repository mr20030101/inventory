"""Dashboard, filtered by the user's permissions.

Staff see school-wide tiles, charts, alerts and activity. People who see only their own records (teachers) get a
personal dashboard: their assets, their borrowing requests and reminders meant for them."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QScrollArea, QVBoxLayout, QWidget,
)

from saims.desktop.api import ApiError
from saims.desktop.ui import formatting as fmt
from saims.desktop.ui import theme
from saims.desktop.ui.charts import DonutChart, HBarChart, LineChart
from saims.desktop.ui.pages.base import Page
from saims.desktop.ui.widgets import Card, Column, DataTable, Tile, show_error, status_color

STATUS_ORDER = ["assigned", "available", "borrowed", "under_maintenance", "damaged", "missing"]
STATUS_LABELS = {"assigned": "Assigned", "available": "Available", "borrowed": "Borrowed",
                 "under_maintenance": "In maintenance", "damaged": "Damaged", "missing": "Missing"}
SEVERITY_ICON = {"critical": ("alert", "danger"), "warning": ("alert", "warning"), "info": ("bell", "info")}


class DashboardPage(Page):
    title = "Dashboard"
    navigate = Signal(str, str)  # target page, record id

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("ScrollBody")
        scroll.setWidget(body)
        stack = QVBoxLayout(body)
        stack.setContentsMargins(0, 0, 6, 0)
        self.staff = QWidget()
        self.personal = self._build_personal()
        stack.addWidget(self.staff)
        stack.addWidget(self.personal)
        self.personal.hide()
        grid = QGridLayout(self.staff)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(14)

        overview = Card("Overview")
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.tiles = {
            "assets": Tile("box", "Assets in service"),
            "consumables": Tile("layers", "Consumable items"),
            "value": Tile("trend", "Inventory value"),
            "attention": Tile("alert", "Need attention", tone="warn"),
        }
        for t in self.tiles.values():
            tiles.addWidget(t, 1)
        overview.body.addLayout(tiles)
        self.valuation = QLabel()
        self.valuation.setObjectName("CardSub")
        overview.title_row.addWidget(self.valuation)
        grid.addWidget(overview, 0, 0, 1, 3)

        # Borrowing summary (small card, like the design's "No of users")
        self.borrow_card = Card("Borrowing")
        row = QHBoxLayout()
        self.borrow_icon = QLabel()
        self.borrow_icon.setObjectName("TileIcon")
        self.borrow_icon.setFixedSize(44, 44)
        self.borrow_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.borrow_icon)
        row.addStretch()
        self.borrow_card.body.addLayout(row)
        self.on_loan = QLabel("0")
        self.on_loan.setObjectName("BigNumber")
        self.borrow_sub = QLabel()
        self.borrow_sub.setObjectName("Hint")
        self.borrow_card.body.addWidget(self.on_loan)
        self.borrow_card.body.addWidget(self.borrow_sub)
        self.borrow_card.body.addStretch()
        self.borrow_card.setMinimumWidth(190)
        grid.addWidget(self.borrow_card, 1, 0)

        status_card = Card("Assets by Status")
        self.donut = DonutChart()
        status_card.body.addWidget(self.donut)
        grid.addWidget(status_card, 1, 1)

        dept_card = Card("Assets by Department")
        dept_card.subtitle.setText("in service")
        self.bars = HBarChart()
        dept_card.body.addWidget(self.bars)
        grid.addWidget(dept_card, 1, 2, 2, 1)

        flow_card = Card("Consumables Received vs Issued")
        flow_card.subtitle.setText("value per month, last 6 months")
        self.line = LineChart()
        self.line.empty_text = "No stock movements yet"
        flow_card.body.addWidget(self.line)
        grid.addWidget(flow_card, 2, 0, 1, 2)

        alerts_card = Card("Needs Attention")
        alerts_card.subtitle.setText("double-click to open")
        self.alerts = self._alert_list()
        alerts_card.body.addWidget(self.alerts)
        grid.addWidget(alerts_card, 3, 0, 1, 2)

        recent_card = Card("Recent Activity")
        self.recent = DataTable([Column("When", "when", fmt.when), Column("User", "user"),
                                 Column("What", "summary")])
        self.recent.setMinimumHeight(220)
        recent_card.body.addWidget(self.recent)
        grid.addWidget(recent_card, 3, 2)

        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 4)
        grid.setRowMinimumHeight(1, 240)
        grid.setRowMinimumHeight(2, 260)

    def _alert_list(self) -> QListWidget:
        alerts = QListWidget()
        alerts.setObjectName("History")
        alerts.setIconSize(QSize(18, 18))
        alerts.itemDoubleClicked.connect(self._open_alert)
        alerts.setMinimumHeight(220)
        return alerts

    def _build_personal(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(14)
        overview = Card("My Overview")
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.my_tiles = {
            "assets": Tile("box", "Assigned to you"),
            "pending": Tile("swap", "Requests waiting"),
            "on_loan": Tile("clipboard", "Borrowed now"),
            "overdue": Tile("alert", "Overdue", tone="warn"),
        }
        for t in self.my_tiles.values():
            tiles.addWidget(t, 1)
        overview.body.addLayout(tiles)
        grid.addWidget(overview, 0, 0, 1, 2)

        assets_card = Card("My Assets")
        assets_card.subtitle.setText("double-click to open")
        self.my_assets = DataTable([Column("Code", "asset_code"), Column("Item", "name"),
                                    Column("Condition", "condition"), Column("Room", "room"),
                                    Column("Since", "since", fmt.day),
                                    Column("Signed for", "acknowledged", lambda v: "Yes" if v else "Not yet",
                                           color=lambda r: None if r["acknowledged"] else "warning")])
        self.my_assets.setMinimumHeight(220)
        self.my_assets.doubleClicked.connect(
            lambda _: (r := self.my_assets.selected()) and self.navigate.emit("assets", r["id"]))
        assets_card.body.addWidget(self.my_assets)
        grid.addWidget(assets_card, 1, 0)

        req_card = Card("My Borrowing Requests")
        req_card.subtitle.setText("latest 10")
        self.my_requests = DataTable([Column("Request", "request_no"), Column("Item", "asset_name"),
                                      Column("Status", "status_label",
                                             color=lambda r: "danger" if r["status_label"] == "Overdue"
                                             else status_color()(r)),
                                      Column("Due back", "expected_return", fmt.day)])
        self.my_requests.setMinimumHeight(220)
        self.my_requests.doubleClicked.connect(
            lambda _: (r := self.my_requests.selected()) and self.navigate.emit("borrowing", r["id"]))
        req_card.body.addWidget(self.my_requests)
        grid.addWidget(req_card, 1, 1)

        alerts_card = Card("For You")
        alerts_card.subtitle.setText("double-click to open")
        self.my_alerts = self._alert_list()
        alerts_card.body.addWidget(self.my_alerts)
        grid.addWidget(alerts_card, 2, 0)

        recent_card = Card("My Recent Activity")
        self.my_recent = DataTable([Column("When", "when", fmt.when), Column("What", "summary")])
        self.my_recent.setMinimumHeight(220)
        recent_card.body.addWidget(self.my_recent)
        grid.addWidget(recent_card, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return page

    def _fill_alerts(self, target: QListWidget, alerts: list[dict]) -> None:
        target.clear()
        for alert in alerts:
            icon, token = SEVERITY_ICON[alert["severity"]]
            item = QListWidgetItem(theme.icon(icon, token), alert["text"])
            item.setData(Qt.ItemDataRole.UserRole, (alert["target"], alert.get("id", "")))
            target.addItem(item)
        if not alerts:
            target.addItem(QListWidgetItem(theme.icon("shield", "ok"), "Nothing needs attention right now."))

    def _refresh_personal(self, d: dict) -> None:
        for t in self.my_tiles.values():
            t.update_icon()
        mine = d.get("my_assets") or []
        b = d.get("my_borrowing") or {"pending": 0, "approved": 0, "on_loan": 0, "overdue": 0, "requests": []}
        self.my_tiles["assets"].set_value(str(len(mine)), "Assets assigned to you")
        self.my_tiles["pending"].set_value(str(b["pending"]), f"Waiting for approval · {b['approved']} approved")
        self.my_tiles["on_loan"].set_value(str(b["on_loan"]), "Borrowed now")
        self.my_tiles["overdue"].set_value(str(b["overdue"]), "Overdue — please return")
        self.my_assets.set_rows(mine)
        self.my_requests.set_rows(b["requests"])
        self._fill_alerts(self.my_alerts, d.get("alerts", []))
        self.my_recent.set_rows(d.get("recent_activity", []))

    def refresh(self) -> None:
        try:
            d = self.api.get("/dashboard")
        except ApiError as exc:
            show_error(self, exc)
            return
        personal = "assets" not in d and ("my_assets" in d or "my_borrowing" in d)
        self.staff.setVisible(not personal)
        self.personal.setVisible(personal)
        if personal:
            return self._refresh_personal(d)
        for t in self.tiles.values():
            t.update_icon()
        a, c, b = d.get("assets"), d.get("consumables"), d.get("borrowing")
        if a:
            self.tiles["assets"].set_value(f"{a['total']:,}", f"In service · {a['assigned']} assigned")
        if c:
            self.tiles["consumables"].set_value(f"{c['items']:,}", f"Consumables · {c['low'] + c['out']} low")
        total = fmt.dec(a["value"] if a else 0) + fmt.dec(c["value"] if c else 0)
        self.tiles["value"].set_value(fmt.compact_money(total), "Inventory value")
        self.tiles["value"].setToolTip(d.get("valuation_note", ""))
        self.valuation.setText("Value: assets at cost, consumables at average cost")
        attention = (a["attention"] if a else 0) + (c["out"] + c["expired"] if c else 0) + (b["overdue"] if b else 0)
        self.tiles["attention"].set_value(str(attention), "Need attention")
        self.tiles["attention"].setToolTip("Missing or damaged assets, out-of-stock or expired items, overdue loans")

        self.borrow_card.setVisible(b is not None)
        if b:
            self.borrow_icon.setPixmap(theme.pixmap("swap", theme.color("icon_fg").name(), 24))
            self.on_loan.setText(str(b["on_loan"]))
            self.borrow_sub.setText(f"On loan now\n{b['overdue']} overdue · {b['pending']} pending")
        if a:
            self.donut.set_data([(STATUS_LABELS[s], a["by_status"].get(s, 0)) for s in STATUS_ORDER], max_slices=5)
            self.bars.set_data([(r["name"], r["count"]) for r in d.get("assets_by_department", [])])
        flow = d.get("stock_flow") or []
        self.line.set_data([m["label"] for m in flow], [
            ("Received", [float(m["received"]) for m in flow], "chart3"),
            ("Issued", [float(m["issued"]) for m in flow], "chart4"),
        ])
        self._fill_alerts(self.alerts, d.get("alerts", []))
        self.recent.set_rows(d.get("recent_activity", []))

    def _open_alert(self, item: QListWidgetItem) -> None:
        target = item.data(Qt.ItemDataRole.UserRole)
        if target:
            self.navigate.emit(*target)
