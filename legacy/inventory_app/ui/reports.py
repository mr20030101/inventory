"""Reports: valuation, reorder list and movement summary, each exportable to CSV."""
from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

from inventory_app.repository import Repository
from inventory_app.ui import formatting as fmt
from inventory_app.ui.movements import date_edit
from inventory_app.ui.widgets import Column, DataTable


class _Report(QWidget):
    filename = "report.csv"

    def __init__(self, table: DataTable, parent=None):
        super().__init__(parent)
        self.layout_ = QVBoxLayout(self)
        self.controls = QHBoxLayout()
        self.controls.addStretch()
        export = QPushButton("Export CSV")
        export.clicked.connect(lambda: self.table.export_csv(self, self.filename))
        self.controls.addWidget(export)
        self.layout_.addLayout(self.controls)
        self.table = table
        self.layout_.addWidget(table)
        self.footer = QLabel()
        self.footer.setObjectName("Hint")
        self.layout_.addWidget(self.footer)


class ValuationReport(_Report):
    filename = "stock-valuation.csv"

    def __init__(self, repo: Repository, parent=None):
        super().__init__(DataTable([
            Column("Category", "category"),
            Column("Products", "products", fmt.qty, numeric=True),
            Column("Units", "units", fmt.qty, numeric=True),
            Column("Value at cost", "cost_value", fmt.money, numeric=True),
            Column("Value at retail", "retail_value", fmt.money, numeric=True),
        ]), parent)
        self.repo = repo

    def refresh(self) -> None:
        rows = self.repo.valuation_by_category()
        self.table.set_rows(rows)
        cost = sum(r["cost_value"] or 0 for r in rows)
        retail = sum(r["retail_value"] or 0 for r in rows)
        self.footer.setText(f"Total at cost {fmt.money(cost)} · at retail {fmt.money(retail)} · "
                            f"potential margin {fmt.money(retail - cost)}")


class ReorderReport(_Report):
    filename = "reorder-list.csv"

    def __init__(self, repo: Repository, parent=None):
        super().__init__(DataTable([
            Column("Supplier", "supplier"), Column("SKU", "sku"), Column("Name", "name"),
            Column("On hand", "quantity", fmt.qty, numeric=True),
            Column("Reorder at", "reorder_level", fmt.qty, numeric=True),
            Column("Suggested order", "suggested_order", fmt.qty, numeric=True),
            Column("Unit cost", "cost_price", fmt.money, numeric=True),
            Column("Order cost", "suggested_cost", fmt.money, numeric=True),
        ]), parent)
        self.repo = repo

    def refresh(self) -> None:
        rows = self.repo.reorder_list()
        self.table.set_rows(rows)
        self.footer.setText(f"{len(rows)} products at or below their reorder level · suggested orders "
                            f"bring stock to twice the reorder level · estimated cost "
                            f"{fmt.money(sum(r['suggested_cost'] for r in rows))}")


class MovementSummaryReport(_Report):
    filename = "movement-summary.csv"

    def __init__(self, repo: Repository, parent=None):
        super().__init__(DataTable([
            Column("SKU", "sku"), Column("Name", "name"),
            Column("Units in", "units_in", fmt.qty, numeric=True),
            Column("Units out", "units_out", fmt.qty, numeric=True),
            Column("Adjusted", "adjusted", fmt.signed, numeric=True),
            Column("Cost of units out", "cost_out", fmt.money, numeric=True),
            Column("On hand now", "quantity", fmt.qty, numeric=True),
            Column("Movements", "movements", fmt.qty, numeric=True),
        ]), parent)
        self.repo = repo
        today = QDate.currentDate()
        self.start = date_edit(QDate(today.year(), today.month(), 1))
        self.end = date_edit(today)
        self.start.dateChanged.connect(self.refresh)
        self.end.dateChanged.connect(self.refresh)
        for i, w in enumerate((QLabel("From"), self.start, QLabel("to"), self.end)):
            self.controls.insertWidget(i, w)

    def refresh(self) -> None:
        rows = self.repo.movement_summary(self.start.date().toString("yyyy-MM-dd"),
                                          self.end.date().toString("yyyy-MM-dd"))
        self.table.set_rows(rows)
        self.footer.setText(f"{fmt.qty(sum(r['units_in'] for r in rows))} units in · "
                            f"{fmt.qty(sum(r['units_out'] for r in rows))} units out · "
                            f"cost of goods out {fmt.money(sum(r['cost_out'] for r in rows))}")


class ReportsView(QWidget):
    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.reports = [ValuationReport(repo), ReorderReport(repo), MovementSummaryReport(repo)]
        for report, title in zip(self.reports, ("Stock valuation", "Reorder list", "Movement summary")):
            self.tabs.addTab(report, title)
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        layout.addWidget(self.tabs)

    def refresh(self) -> None:
        self.tabs.currentWidget().refresh()
