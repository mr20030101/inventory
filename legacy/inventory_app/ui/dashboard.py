"""Dashboard laid out like the design: overview tiles, then chart cards."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from inventory_app.repository import Repository
from inventory_app.ui import formatting as fmt
from inventory_app.ui import theme
from inventory_app.ui.charts import DonutChart, HBarChart, LineChart
from inventory_app.ui.widgets import Card, Tile


class DashboardView(QScrollArea):
    open_low_stock = Signal()

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("ScrollBody")
        self.setWidget(body)
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 4, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        # Row 0: overview tiles
        overview = Card("Overview")
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.tiles = {
            "products": Tile("box", "Total Products"),
            "units": Tile("layers", "Units on Hand"),
            "cost_value": Tile("trend", "Stock Value"),
            "low_stock": Tile("alert", "Low / Out of Stock", tone="warn"),
        }
        for tile in self.tiles.values():
            tiles.addWidget(tile, 1)
        overview.body.addLayout(tiles)
        self.reorder_btn = QPushButton("View reorder list")
        self.reorder_btn.clicked.connect(self.open_low_stock)
        overview.title_row.addWidget(self.reorder_btn)
        grid.addWidget(overview, 0, 0, 1, 3)

        # Row 1: suppliers / value donut / top movers
        self.suppliers_card = Card("Suppliers")
        icon_row = QHBoxLayout()
        self.supplier_icon = QLabel()
        self.supplier_icon.setObjectName("TileIcon")
        self.supplier_icon.setFixedSize(44, 44)
        self.supplier_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_row.addWidget(self.supplier_icon)
        icon_row.addStretch()
        self.suppliers_card.body.addLayout(icon_row)
        self.supplier_count = QLabel("0")
        self.supplier_count.setObjectName("BigNumber")
        self.supplier_sub = QLabel()
        self.supplier_sub.setObjectName("Hint")
        self.suppliers_card.body.addWidget(self.supplier_count)
        self.suppliers_card.body.addWidget(self.supplier_sub)
        self.suppliers_card.body.addStretch()
        self.suppliers_card.setMinimumWidth(190)
        grid.addWidget(self.suppliers_card, 1, 0)

        value_card = Card("Inventory Value")
        value_card.subtitle.setText("by category, at cost")
        self.donut = DonutChart()
        value_card.body.addWidget(self.donut)
        grid.addWidget(value_card, 1, 1)

        top_card = Card("Top 10 Products by Units Out")
        top_card.subtitle.setText("last 30 days")
        self.bars = HBarChart()
        self.bars.empty_text = "No stock out in the last 30 days"
        top_card.body.addWidget(self.bars)
        grid.addWidget(top_card, 1, 2, 2, 1)

        # Row 2: flow line chart
        flow_card = Card("Stock In vs Out")
        flow_card.subtitle.setText("last 6 months")
        self.line = LineChart()
        self.line.empty_text = "No stock movements in the last 6 months"
        flow_card.body.addWidget(self.line)
        grid.addWidget(flow_card, 2, 0, 1, 2)

        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 4)
        grid.setRowStretch(1, 2)
        grid.setRowStretch(2, 3)

    def refresh(self) -> None:
        s = self.repo.summary()
        self.tiles["products"].set_value(fmt.qty(s["products"]))
        self.tiles["units"].set_value(fmt.qty(s["units"]))
        self.tiles["cost_value"].set_value(fmt.money(s["cost_value"]))
        self.tiles["low_stock"].set_value(f"{fmt.qty(s['low_stock'])} / {fmt.qty(s['out_of_stock'])}")
        for tile in self.tiles.values():
            tile.update_icon()
        self.tiles["cost_value"].setToolTip(f"Retail value: {fmt.money(s['retail_value'])}")

        suppliers = self.repo.list_suppliers()
        categories = self.repo.list_categories()
        self.supplier_icon.setPixmap(theme.pixmap("truck", theme.color("icon_fg").name(), 24))
        self.supplier_count.setText(fmt.qty(len(suppliers)))
        self.supplier_sub.setText(f"Active suppliers\n{len(categories)} categories")

        self.donut.set_data([(r["category"], r["cost_value"] or 0) for r in self.repo.valuation_by_category()])
        self.bars.set_data([(r["name"], r["units_out"]) for r in self.repo.top_products_out()])
        flow = self.repo.monthly_flow()
        self.line.set_data([m["label"] for m in flow], [
            ("In", [m["units_in"] for m in flow], "chart3"),
            ("Out", [m["units_out"] for m in flow], "chart4"),
        ])
