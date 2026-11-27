"""Category and supplier management."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QMessageBox, QPushButton, QVBoxLayout, QWidget

from inventory_app.repository import InventoryError, Repository
from inventory_app.ui import formatting as fmt
from inventory_app.ui.dialogs import SupplierDialog
from inventory_app.ui.widgets import Column, DataTable, confirm


class _ListView(QWidget):
    title = ""
    noun = ""

    def __init__(self, repo: Repository, columns: list[Column], parent=None):
        super().__init__(parent)
        self.repo = repo
        layout = QVBoxLayout(self)
        buttons = QHBoxLayout()
        self.add_btn = QPushButton(f"New {self.noun}")
        self.add_btn.setObjectName("Primary")
        self.add_btn.clicked.connect(self.add)
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.edit_btn)
        buttons.addStretch()
        buttons.addWidget(self.delete_btn)
        layout.addLayout(buttons)
        self.table = DataTable(columns)
        self.table.doubleClicked.connect(lambda _: self.edit())
        self.table.selectionModel().selectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table)
        self._update_buttons()

    def _update_buttons(self) -> None:
        has = self.table.selected() is not None
        self.edit_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)

    def delete(self) -> None:
        row = self.table.selected()
        if not row:
            return
        extra = (f"\n\n{row['product_count']} product(s) will be left without a {self.noun.lower()}."
                 if row["product_count"] else "")
        if confirm(self, f"Delete {self.noun.lower()}", f'Delete "{row["name"]}"?{extra}'):
            self.remove(row["id"])
            self.refresh()

    def refresh(self) -> None:
        raise NotImplementedError

    def add(self) -> None:
        raise NotImplementedError

    def edit(self) -> None:
        raise NotImplementedError

    def remove(self, row_id: int) -> None:
        raise NotImplementedError


class CategoriesView(_ListView):
    title, noun = "Categories", "Category"

    def __init__(self, repo: Repository, parent=None):
        super().__init__(repo, [Column("Name", "name"),
                                Column("Products", "product_count", fmt.qty, numeric=True)], parent)

    def refresh(self) -> None:
        self.table.set_rows(self.repo.list_categories())
        self._update_buttons()

    def _ask(self, title: str, current: str = "") -> str | None:
        name, ok = QInputDialog.getText(self, title, "Category name:", text=current)
        return name if ok else None

    def add(self) -> None:
        name = self._ask("New Category")
        if name is not None:
            self._run(lambda: self.repo.add_category(name))

    def edit(self) -> None:
        row = self.table.selected()
        if row:
            name = self._ask("Rename Category", row["name"])
            if name is not None:
                self._run(lambda: self.repo.rename_category(row["id"], name))

    def remove(self, row_id: int) -> None:
        self.repo.delete_category(row_id)

    def _run(self, action) -> None:
        try:
            action()
        except InventoryError as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
        self.refresh()


class SuppliersView(_ListView):
    title, noun = "Suppliers", "Supplier"

    def __init__(self, repo: Repository, parent=None):
        super().__init__(repo, [
            Column("Name", "name"), Column("Contact", "contact_name"), Column("Email", "email"),
            Column("Phone", "phone"), Column("Products", "product_count", fmt.qty, numeric=True),
            Column("Notes", "notes"),
        ], parent)

    def refresh(self) -> None:
        self.table.set_rows(self.repo.list_suppliers())
        self._update_buttons()

    def add(self) -> None:
        if SupplierDialog(self.repo, parent=self).exec():
            self.refresh()

    def edit(self) -> None:
        row = self.table.selected()
        if row and SupplierDialog(self.repo, self.repo.get_supplier(row["id"]), self).exec():
            self.refresh()

    def remove(self, row_id: int) -> None:
        self.repo.delete_supplier(row_id)
