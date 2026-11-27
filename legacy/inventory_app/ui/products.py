"""Product list with search, filters and stock actions."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget,
)

from inventory_app.repository import Repository
from inventory_app.ui import formatting as fmt
from inventory_app.ui.dialogs import ProductDialog, StockDialog
from inventory_app.ui.widgets import Column, DataTable, confirm


def is_low(row: dict) -> bool:
    return row["quantity"] <= row["reorder_level"]


class ProductsView(QWidget):
    show_history = Signal(int)

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        layout = QVBoxLayout(self)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search SKU, name, barcode, location…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.category = QComboBox()
        self.category.currentIndexChanged.connect(self.refresh)
        self.supplier = QComboBox()
        self.supplier.currentIndexChanged.connect(self.refresh)
        self.low_only = QCheckBox("Low stock only")
        self.low_only.toggled.connect(self.refresh)
        filters.addWidget(self.search, 3)
        filters.addWidget(self.category, 1)
        filters.addWidget(self.supplier, 1)
        filters.addWidget(self.low_only)
        layout.addLayout(filters)

        actions = QHBoxLayout()
        self.new_btn = QPushButton("New Product")
        self.new_btn.setObjectName("Primary")
        self.new_btn.clicked.connect(self.new_product)
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_product)
        self.in_btn = QPushButton("Stock In")
        self.in_btn.clicked.connect(lambda: self.move_stock("in"))
        self.out_btn = QPushButton("Stock Out")
        self.out_btn.clicked.connect(lambda: self.move_stock("out"))
        self.adjust_btn = QPushButton("Adjust")
        self.adjust_btn.setToolTip("Set the quantity to a counted amount (stocktake)")
        self.adjust_btn.clicked.connect(lambda: self.move_stock("adjust"))
        self.history_btn = QPushButton("History")
        self.history_btn.clicked.connect(self._history)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_product)
        actions.addWidget(self.new_btn)
        actions.addWidget(self.edit_btn)
        actions.addSpacing(16)
        for b in (self.in_btn, self.out_btn, self.adjust_btn, self.history_btn):
            actions.addWidget(b)
        actions.addStretch()
        self.count_label = QLabel()
        self.count_label.setObjectName("Hint")
        actions.addWidget(self.count_label)
        actions.addSpacing(16)
        actions.addWidget(self.delete_btn)
        layout.addLayout(actions)

        self.table = DataTable([
            Column("SKU", "sku"),
            Column("Name", "name"),
            Column("Category", "category"),
            Column("Supplier", "supplier"),
            Column("Location", "location"),
            Column("On hand", "quantity", fmt.qty, numeric=True),
            Column("Unit", "unit"),
            Column("Reorder at", "reorder_level", fmt.qty, numeric=True),
            Column("Cost", "cost_price", fmt.money, numeric=True),
            Column("Price", "sell_price", fmt.money, numeric=True),
            Column("Stock value", "stock_value", fmt.money, numeric=True),
            Column("Barcode", "barcode"),
        ], highlight=is_low)
        self.table.doubleClicked.connect(lambda _: self.edit_product())
        self.table.selectionModel().selectionChanged.connect(self._update_buttons)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.table)

        QShortcut(QKeySequence.StandardKey.New, self, self.new_product)
        QShortcut(QKeySequence.StandardKey.Find, self, self.search.setFocus)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table, self.delete_product)
        self._update_buttons()

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        self._reload_filter(self.category, "All categories", self.repo.list_categories())
        self._reload_filter(self.supplier, "All suppliers", self.repo.list_suppliers())
        rows = self.repo.list_products(
            search=self.search.text(),
            category_id=self.category.currentData(),
            supplier_id=self.supplier.currentData(),
            low_stock_only=self.low_only.isChecked(),
        )
        self.table.set_rows(rows)
        self.count_label.setText(f"{len(rows)} product{'s' if len(rows) != 1 else ''}")
        self._update_buttons()

    @staticmethod
    def _reload_filter(combo: QComboBox, all_label: str, items: list[dict]) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(all_label, None)
        for item in items:
            combo.addItem(item["name"], item["id"])
        combo.setCurrentIndex(max(combo.findData(current), 0))
        combo.blockSignals(False)

    def _update_buttons(self) -> None:
        has = self.table.selected() is not None
        for b in (self.edit_btn, self.in_btn, self.out_btn, self.adjust_btn, self.history_btn, self.delete_btn):
            b.setEnabled(has)

    def _context_menu(self, pos) -> None:
        if self.table.selected() is None:
            return
        menu = QMenu(self)
        menu.addAction("Edit…", self.edit_product)
        menu.addSeparator()
        menu.addAction("Stock In…", lambda: self.move_stock("in"))
        menu.addAction("Stock Out…", lambda: self.move_stock("out"))
        menu.addAction("Adjust…", lambda: self.move_stock("adjust"))
        menu.addAction("Movement History", self._history)
        menu.addSeparator()
        menu.addAction("Delete…", self.delete_product)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # --------------------------------------------------------------- actions
    def new_product(self) -> None:
        dialog = ProductDialog(self.repo, parent=self)
        if dialog.exec():
            self.refresh()
            self.table.select_id(dialog.product_id)

    def edit_product(self) -> None:
        row = self.table.selected()
        if row and ProductDialog(self.repo, self.repo.get_product(row["id"]), self).exec():
            self.refresh()

    def move_stock(self, kind: str) -> None:
        row = self.table.selected()
        if row and StockDialog(self.repo, self.repo.get_product(row["id"]), kind, self).exec():
            self.refresh()

    def delete_product(self) -> None:
        row = self.table.selected()
        if row and confirm(self, "Delete product",
                           f'Delete "{row["name"]}" ({row["sku"]}) and its entire movement history?\n\n'
                           "This cannot be undone."):
            self.repo.delete_product(row["id"])
            self.refresh()

    def _history(self) -> None:
        row = self.table.selected()
        if row:
            self.show_history.emit(row["id"])
