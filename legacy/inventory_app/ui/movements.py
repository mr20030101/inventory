"""Stock movement history."""
from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from inventory_app.repository import MOVEMENT_TYPES, Repository
from inventory_app.ui import formatting as fmt
from inventory_app.ui.widgets import Column, DataTable


def date_edit(value: QDate) -> QDateEdit:
    edit = QDateEdit(value)
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("yyyy-MM-dd")
    return edit


class MovementsView(QWidget):
    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.product_id: int | None = None
        layout = QVBoxLayout(self)

        filters = QHBoxLayout()
        today = QDate.currentDate()
        self.start = date_edit(today.addDays(-30))
        self.end = date_edit(today)
        self.kind = QComboBox()
        self.kind.addItem("All types", None)
        for key, label in MOVEMENT_TYPES.items():
            self.kind.addItem(label, key)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search product, reference, note…")
        self.search.setClearButtonEnabled(True)
        export = QPushButton("Export CSV")
        export.clicked.connect(lambda: self.table.export_csv(self, "stock-movements.csv"))
        for w in (self.start, self.end, self.kind):
            (w.dateChanged if isinstance(w, QDateEdit) else w.currentIndexChanged).connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(QLabel("From"))
        filters.addWidget(self.start)
        filters.addWidget(QLabel("to"))
        filters.addWidget(self.end)
        filters.addWidget(self.kind)
        filters.addWidget(self.search, 1)
        filters.addWidget(export)
        layout.addLayout(filters)

        self.product_bar = QWidget()
        bar = QHBoxLayout(self.product_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        self.product_label = QLabel()
        clear = QPushButton("Show all products")
        clear.clicked.connect(self.clear_product)
        bar.addWidget(self.product_label)
        bar.addWidget(clear)
        bar.addStretch()
        self.product_bar.hide()
        layout.addWidget(self.product_bar)

        self.table = DataTable([
            Column("Date", "created_at", fmt.timestamp),
            Column("SKU", "sku"),
            Column("Product", "product_name"),
            Column("Type", "kind_label"),
            Column("Change", "qty_change", fmt.signed, numeric=True),
            Column("Balance", "quantity_after", fmt.qty, numeric=True),
            Column("Unit cost", "unit_cost", fmt.money, numeric=True),
            Column("Reference", "reference"),
            Column("Note", "note"),
        ], highlight=lambda r: r["qty_change"] < 0)
        layout.addWidget(self.table)
        self.total_label = QLabel()
        self.total_label.setObjectName("Hint")
        layout.addWidget(self.total_label)

    def show_product(self, product_id: int) -> None:
        product = self.repo.get_product(product_id)
        if not product:
            return
        self.product_id = product_id
        self.product_label.setText(f"Showing history for <b>{product['sku']}</b> — {product['name']}")
        self.product_bar.show()
        first = self.repo.list_movements(product_id=product_id)
        if first:
            self.start.blockSignals(True)
            self.start.setDate(QDate.fromString(first[-1]["created_at"][:10], "yyyy-MM-dd"))
            self.start.blockSignals(False)
        self.end.blockSignals(True)
        self.end.setDate(QDate.currentDate())
        self.end.blockSignals(False)
        self.refresh()

    def clear_product(self) -> None:
        self.product_id = None
        self.product_bar.hide()
        self.refresh()

    def refresh(self) -> None:
        rows = self.repo.list_movements(
            start=self.start.date().toString("yyyy-MM-dd"),
            end=self.end.date().toString("yyyy-MM-dd"),
            product_id=self.product_id,
            kind=self.kind.currentData(),
            search=self.search.text(),
        )
        self.table.set_rows(rows)
        units_in = sum(r["qty_change"] for r in rows if r["qty_change"] > 0)
        units_out = -sum(r["qty_change"] for r in rows if r["qty_change"] < 0)
        self.total_label.setText(
            f"{len(rows)} movements · {fmt.qty(units_in)} units added · {fmt.qty(units_out)} units removed")
