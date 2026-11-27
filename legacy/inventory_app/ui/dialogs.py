"""Forms for editing products, suppliers, stock movements and settings."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QSpinBox, QVBoxLayout,
)

from inventory_app.repository import MOVEMENT_TYPES, InventoryError, Repository
from inventory_app.ui import formatting

MAX_QTY = 1_000_000_000


class _FormDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        outer = QVBoxLayout(self)
        self.form = QFormLayout()
        outer.addLayout(self.form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("Primary")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

    def _on_accept(self) -> None:
        try:
            self.save()
        except InventoryError as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        self.accept()

    def save(self) -> None:
        raise NotImplementedError


def _money_box(value: float = 0.0) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(0, 1e9)
    box.setDecimals(2)
    box.setPrefix(formatting.currency())
    box.setGroupSeparatorShown(True)
    box.setValue(value)
    return box


def _qty_box(value: int = 0, minimum: int = 0) -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, MAX_QTY)
    box.setGroupSeparatorShown(True)
    box.setValue(value)
    return box


def _lookup_combo(items: list[dict], selected_id: int | None) -> QComboBox:
    combo = QComboBox()
    combo.addItem("(none)", None)
    for item in items:
        combo.addItem(item["name"], item["id"])
    index = combo.findData(selected_id)
    combo.setCurrentIndex(max(index, 0))
    return combo


class ProductDialog(_FormDialog):
    def __init__(self, repo: Repository, product: dict | None = None, parent=None):
        super().__init__("Edit Product" if product else "New Product", parent)
        self.repo = repo
        self.product = product
        self.product_id: int | None = product["id"] if product else None
        p = product or {}

        self.sku = QLineEdit(p.get("sku", ""))
        self.name = QLineEdit(p.get("name", ""))
        self.barcode = QLineEdit(p.get("barcode", ""))
        self.category = _lookup_combo(repo.list_categories(), p.get("category_id"))
        self.supplier = _lookup_combo(repo.list_suppliers(), p.get("supplier_id"))
        self.unit = QLineEdit(p.get("unit", "pcs"))
        self.unit.setPlaceholderText("pcs, box, kg…")
        self.cost = _money_box(p.get("cost_price", 0.0))
        self.price = _money_box(p.get("sell_price", 0.0))
        self.reorder = _qty_box(p.get("reorder_level", 0))
        self.reorder.setToolTip("The product is flagged as low stock when quantity falls to this level.")
        self.location = QLineEdit(p.get("location", ""))
        self.location.setPlaceholderText("Shelf, bin or room")
        self.description = QPlainTextEdit(p.get("description", ""))
        self.description.setFixedHeight(70)

        self.form.addRow("SKU *", self.sku)
        self.form.addRow("Name *", self.name)
        self.form.addRow("Barcode", self.barcode)
        self.form.addRow("Category", self.category)
        self.form.addRow("Supplier", self.supplier)
        self.form.addRow("Unit", self.unit)
        self.form.addRow("Cost price", self.cost)
        self.form.addRow("Sell price", self.price)
        self.form.addRow("Reorder level", self.reorder)
        self.form.addRow("Location", self.location)
        self.form.addRow("Description", self.description)
        if product is None:
            self.initial_qty = _qty_box(0)
            self.form.addRow("Opening stock", self.initial_qty)
        else:
            note = QLabel(f"On hand: {formatting.qty(p['quantity'])} {p['unit']}. "
                          "Use Stock In / Stock Out / Adjust to change it.")
            note.setWordWrap(True)
            note.setObjectName("Hint")
            self.form.addRow("", note)

    def data(self) -> dict:
        return {
            "sku": self.sku.text(), "name": self.name.text(), "barcode": self.barcode.text(),
            "category_id": self.category.currentData(), "supplier_id": self.supplier.currentData(),
            "unit": self.unit.text(), "cost_price": self.cost.value(), "sell_price": self.price.value(),
            "reorder_level": self.reorder.value(), "location": self.location.text(),
            "description": self.description.toPlainText(),
        }

    def save(self) -> None:
        if self.product_id is None:
            self.product_id = self.repo.add_product(self.data(), self.initial_qty.value())
        else:
            self.repo.update_product(self.product_id, self.data())


class StockDialog(_FormDialog):
    def __init__(self, repo: Repository, product: dict, kind: str, parent=None):
        super().__init__(f"{MOVEMENT_TYPES[kind]}: {product['name']}", parent)
        self.repo, self.product, self.kind = repo, product, kind
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(MOVEMENT_TYPES[kind])

        on_hand = QLabel(f"{formatting.qty(product['quantity'])} {product['unit']}")
        self.form.addRow("Product", QLabel(f"{product['sku']} — {product['name']}"))
        self.form.addRow("On hand", on_hand)
        if kind == "adjust":
            self.quantity = _qty_box(max(product["quantity"], 0))
            label = "Counted quantity"
        else:
            self.quantity = _qty_box(1, minimum=1)
            label = "Quantity received" if kind == "in" else "Quantity removed"
        self.quantity.setSuffix(f" {product['unit']}")
        self.form.addRow(label, self.quantity)
        self.reference = QLineEdit()
        self.reference.setPlaceholderText(
            {"in": "Purchase order / delivery no.", "out": "Invoice / order no.",
             "adjust": "Stocktake reference"}[kind])
        self.form.addRow("Reference", self.reference)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Damaged, returned, sold…" if kind != "in" else "Optional")
        self.form.addRow("Note", self.note)
        self.result_label = QLabel()
        self.result_label.setObjectName("Hint")
        self.form.addRow("New quantity", self.result_label)
        self.quantity.valueChanged.connect(self._update_preview)
        self._update_preview()
        self.quantity.setFocus()
        self.quantity.selectAll()

    def _new_quantity(self) -> int:
        q, current = self.quantity.value(), self.product["quantity"]
        return {"in": current + q, "out": current - q, "adjust": q}[self.kind]

    def _update_preview(self) -> None:
        new = self._new_quantity()
        self.result_label.setText(f"{formatting.qty(new)} {self.product['unit']}"
                                  f"  ({formatting.signed(new - self.product['quantity'])})")

    def save(self) -> None:
        self.repo.record_movement(self.product["id"], self.kind, self.quantity.value(),
                                  self.reference.text(), self.note.text())


class SupplierDialog(_FormDialog):
    def __init__(self, repo: Repository, supplier: dict | None = None, parent=None):
        super().__init__("Edit Supplier" if supplier else "New Supplier", parent)
        self.repo, self.supplier = repo, supplier
        s = supplier or {}
        self.name = QLineEdit(s.get("name", ""))
        self.contact = QLineEdit(s.get("contact_name", ""))
        self.email = QLineEdit(s.get("email", ""))
        self.phone = QLineEdit(s.get("phone", ""))
        self.address = QPlainTextEdit(s.get("address", ""))
        self.address.setFixedHeight(60)
        self.notes = QPlainTextEdit(s.get("notes", ""))
        self.notes.setFixedHeight(60)
        self.form.addRow("Name *", self.name)
        self.form.addRow("Contact", self.contact)
        self.form.addRow("Email", self.email)
        self.form.addRow("Phone", self.phone)
        self.form.addRow("Address", self.address)
        self.form.addRow("Notes", self.notes)

    def save(self) -> None:
        data = {"name": self.name.text(), "contact_name": self.contact.text(), "email": self.email.text(),
                "phone": self.phone.text(), "address": self.address.toPlainText(),
                "notes": self.notes.toPlainText()}
        if self.supplier:
            self.repo.update_supplier(self.supplier["id"], data)
        else:
            self.repo.add_supplier(data)


class SettingsDialog(_FormDialog):
    def __init__(self, repo: Repository, parent=None):
        super().__init__("Settings", parent)
        self.repo = repo
        self.business = QLineEdit(repo.get_setting("business_name", ""))
        self.business.setPlaceholderText("Shown in the window title")
        self.currency = QLineEdit(repo.get_setting("currency", "$"))
        self.currency.setMaxLength(4)
        self.negative = QCheckBox("Allow stock to go below zero")
        self.negative.setChecked(repo.allow_negative_stock)
        self.form.addRow("Business name", self.business)
        self.form.addRow("Currency symbol", self.currency)
        self.form.addRow("", self.negative)

    def save(self) -> None:
        self.repo.set_setting("business_name", self.business.text().strip())
        self.repo.set_setting("currency", self.currency.text().strip())
        self.repo.set_setting("allow_negative_stock", "1" if self.negative.isChecked() else "0")
        formatting.set_currency(self.currency.text().strip())
