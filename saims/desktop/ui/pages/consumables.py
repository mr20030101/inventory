"""Consumables: items with stock levels, stock per location, the movement ledger and expiring batches.

Select several items to receive, issue or return them together in one transaction (one requisition or one
delivery note)."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QPlainTextEdit, QPushButton, QTableWidget, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from saims.desktop.api import ApiError
from saims.desktop.ui import formatting as fmt
from saims.desktop.ui.forms import Field, ref_options, run_form
from saims.desktop.ui.pages.base import Page
from saims.desktop.ui.widgets import (
    CheckCombo, Column, DataTable, hint, money_col, qty_col, show_error, status_color,
)

STATE_LABELS = {"ok": "OK", "low": "Low", "out": "Out of stock"}
MOVEMENT_TYPES = {"OPENING": "Opening balance", "RECEIPT": "Receipt", "ISSUE": "Issue", "RETURN": "Return",
                  "DAMAGE": "Damaged", "EXPIRY": "Expired", "ADJUSTMENT_IN": "Adjustment (+)",
                  "ADJUSTMENT_OUT": "Adjustment (−)", "TRANSFER_IN": "Transfer in", "TRANSFER_OUT": "Transfer out"}


class ConsumablesPage(Page):
    title = "Consumables"

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # ------------------------------------------------------------- items
        items = QWidget()
        il = QVBoxLayout(items)
        il.setContentsMargins(0, 8, 0, 0)
        f = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search item code or name…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_items)
        self.category = CheckCombo("All categories", "categories")
        self.category.changed.connect(self.refresh_items)
        self.low_only = QCheckBox("Low / out of stock only")
        self.low_only.toggled.connect(self.refresh_items)
        f.addWidget(self.search, 3)
        f.addWidget(self.category, 1)
        f.addWidget(self.low_only)
        il.addLayout(f)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.new_btn = self.button("New item", self.new_item, "layers", True, "inventory.manage_items")
        self.edit_btn = self.button("Edit", self.edit_item, permission="inventory.manage_items")
        self.receive_btn = self.button("Receive", lambda: self.movement("RECEIPT"), permission="inventory.receive")
        self.issue_btn = self.button("Issue", lambda: self.movement("ISSUE"), permission="inventory.issue")
        self.return_btn = self.button("Return", lambda: self.movement("RETURN"), permission="inventory.return")
        self.transfer_btn = self.button("Transfer", self.transfer, "movements", permission="inventory.transfer")
        self.adjust_btn = QPushButton("Adjust")
        menu = QMenu(self)
        menu.addAction("Record damaged stock…", lambda: self.movement("DAMAGE"))
        menu.addAction("Record expired stock…", lambda: self.movement("EXPIRY"))
        menu.addSeparator()
        menu.addAction("Adjustment: add stock…", lambda: self.movement("ADJUSTMENT_IN"))
        menu.addAction("Adjustment: remove stock…", lambda: self.movement("ADJUSTMENT_OUT"))
        menu.addSeparator()
        menu.addAction("Opening balance…", lambda: self.movement("OPENING"))
        self.adjust_btn.setMenu(menu)
        self.adjust_btn.setVisible(api.can("inventory.adjust"))
        for b in (self.new_btn, self.edit_btn, self.receive_btn, self.issue_btn, self.return_btn,
                  self.transfer_btn, self.adjust_btn):
            bar.addWidget(b)
        bar.addStretch()
        self.count = QLabel()
        self.count.setObjectName("Hint")
        bar.addWidget(self.count)
        self._make_items_table()
        bar.addWidget(self.export_button(self.items, "Consumable items"))
        il.addLayout(bar)
        il.addWidget(self.items)
        il.addWidget(hint("Tip: Ctrl/Shift-click several items to receive, issue or return them together on one "
                          "reference."))
        self.tabs.addTab(items, "Items")
        self._build_other_tabs(api)

    def _make_items_table(self) -> None:
        self.items = DataTable([
            Column("Code", "item_code"), Column("Item", "name"), Column("Category", "category"),
            qty_col("On hand", "on_hand"), Column("Unit", "unit_of_measure"), qty_col("Reorder at", "reorder_level"),
            Column("Stock", "stock_state", lambda s: STATE_LABELS.get(s, s), color=status_color("stock_state")),
            money_col("Avg cost", "average_cost"), money_col("Value", "value"),
            Column("Expiry tracked", "track_expiry", lambda v: "Yes" if v else ""),
        ], multi=True)
        self.items.selectionModel().selectionChanged.connect(self._update)
        self.items.doubleClicked.connect(lambda _: self._show_item_movements())

    def _build_other_tabs(self, api) -> None:
        # ------------------------------------------------------------- balances
        bal = QWidget()
        bl = QVBoxLayout(bal)
        bl.setContentsMargins(0, 8, 0, 0)
        bf = QHBoxLayout()
        self.location = CheckCombo("All locations", "locations")
        self.location.changed.connect(self.refresh_balances)
        bf.addWidget(QLabel("Storage location"))
        bf.addWidget(self.location)
        bf.addStretch()
        bl.addLayout(bf)
        self.balances = DataTable([
            Column("Location", "location"), Column("Code", "item_code"), Column("Item", "item"),
            Column("Batch", "batch_no"), Column("Expires", "expiry_date", fmt.day), qty_col("Quantity", "quantity"),
            Column("Unit", "unit"),
        ])
        bl.addWidget(self.balances)
        self.tabs.addTab(bal, "Stock by location")

        # ------------------------------------------------------------- movements
        mov = QWidget()
        ml = QVBoxLayout(mov)
        ml.setContentsMargins(0, 8, 0, 0)
        mf = QHBoxLayout()
        today = QDate.currentDate()
        self.start = self._date(today.addDays(-60))
        self.end = self._date(today)
        self.mtype = CheckCombo("All types", "types")
        self.mtype.set_options([(v, k) for k, v in MOVEMENT_TYPES.items()])
        self.msearch = QLineEdit()
        self.msearch.setPlaceholderText("Item, reference or reason…")
        self.msearch.setClearButtonEnabled(True)
        for w in (self.start, self.end):
            w.dateChanged.connect(self.refresh_movements)
        self.mtype.changed.connect(self.refresh_movements)
        self.msearch.returnPressed.connect(self.refresh_movements)
        self.item_filter: dict | None = None
        self.item_chip = QPushButton()
        self.item_chip.setObjectName("Link")
        self.item_chip.clicked.connect(self._clear_item_filter)
        self.item_chip.hide()
        for w in (QLabel("From"), self.start, QLabel("to"), self.end, self.mtype, self.msearch, self.item_chip):
            mf.addWidget(w)
        mf.addStretch()
        if api.can("reports.export"):
            e = QPushButton("Export")
            e.clicked.connect(lambda: self.export(self.movements, "Stock movements",
                                                  filters=f"{self.start.date().toString('yyyy-MM-dd')} to "
                                                          f"{self.end.date().toString('yyyy-MM-dd')}"))
            mf.addWidget(e)
        ml.addLayout(mf)
        self.movements = DataTable([
            Column("Date", "created_at", fmt.when), Column("Item", "item"), Column("Type", "type_label"),
            Column("Quantity", "signed_quantity", fmt.signed, numeric=True,
                   color=lambda r: "ok" if not r["signed_quantity"].startswith("-") else "danger"),
            Column("Unit", "unit"), Column("Location", "location"), Column("Batch", "batch_no"),
            Column("Issued to", "department"), money_col("Unit cost", "unit_cost"), Column("Reference", "reference"),
            Column("Reason", "reason"), Column("By", "user"),
        ])
        ml.addWidget(self.movements)
        self.tabs.addTab(mov, "Movement ledger")

        # ------------------------------------------------------------- expiring
        exp = QWidget()
        el = QVBoxLayout(exp)
        el.setContentsMargins(0, 8, 0, 0)
        self.expiring = DataTable([
            Column("Item", "item"), Column("Batch", "batch_no"), Column("Expiry date", "expiry_date", fmt.day),
            qty_col("Quantity", "quantity"), Column("Unit", "unit"),
            Column("State", "expired", lambda e: "Expired" if e else "Expiring soon",
                   color=lambda r: "danger" if r["expired"] else "warning"),
        ])
        el.addWidget(QLabel("Batches with stock that expire within 90 days. Record expired stock with "
                            "Adjust ▸ Record expired stock."))
        el.addWidget(self.expiring)
        self.tabs.addTab(exp, "Expiring batches")
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        self._filters_loaded = False
        self._update()

    @staticmethod
    def _date(value: QDate) -> QDateEdit:
        d = QDateEdit(value)
        d.setCalendarPopup(True)
        d.setDisplayFormat("dd MMM yyyy")
        return d

    def _load_filters(self) -> None:
        for combo, key, params in ((self.category, "categories", {"kind": "consumable"}),
                                   (self.location, "storage-locations", {})):
            combo.set_options([(r["name"], r["id"]) for r in self.api.lookup(key, **params)])
        self._filters_loaded = True

    # ------------------------------------------------------------------ refresh
    def refresh(self) -> None:
        if not self._filters_loaded:
            self._load_filters()
        [self.refresh_items, self.refresh_balances, self.refresh_movements, self.refresh_expiring][
            self.tabs.currentIndex()]()

    def _get(self, path, **params):
        try:
            return self.api.get(path, **params)
        except ApiError as exc:
            show_error(self, exc)
            return None

    def refresh_items(self) -> None:
        rows = self._get("/stock/items", q=self.search.text(), category_id=self.category.values(),
                         low_only=self.low_only.isChecked())
        if rows is not None:
            self.items.set_rows(rows)
            low = sum(r["stock_state"] != "ok" for r in rows)
            self.count.setText(f"{len(rows)} items · {low} low or out")
            self._update()

    def _items_count(self) -> None:
        base = " · ".join(self.count.text().split(" · ")[:2])
        n = len(self.items.selected_rows())
        self.count.setText(f"{base} · {n} selected" if n > 1 else base)

    def refresh_balances(self) -> None:
        rows = self._get("/stock/balances", location_id=self.location.values())
        if rows is not None:
            self.balances.set_rows(rows)

    def refresh_movements(self) -> None:
        rows = self._get("/stock/movements", start=self.start.date().toString("yyyy-MM-dd"),
                         end=self.end.date().toString("yyyy-MM-dd"), movement_type=self.mtype.values(),
                         q=self.msearch.text(), item_id=self.item_filter["id"] if self.item_filter else None)
        if rows is not None:
            self.movements.set_rows(rows)

    def refresh_expiring(self) -> None:
        rows = self._get("/stock/expiring", days=90)
        if rows is not None:
            self.expiring.set_rows(rows)

    def show_record(self, item_id: str) -> None:
        self.tabs.setCurrentIndex(0)
        self.search.clear()
        self.low_only.setChecked(False)
        self.refresh_items()
        self.items.select_id(item_id)

    def _show_item_movements(self) -> None:
        row = self.items.selected()
        if not row:
            return
        self.item_filter = row
        self.item_chip.setText(f"Showing {row['name']} only ✕")
        self.item_chip.show()
        self.start.setDate(QDate.currentDate().addYears(-2))
        self.tabs.setCurrentIndex(2)

    def _clear_item_filter(self) -> None:
        self.item_filter = None
        self.item_chip.hide()
        self.refresh_movements()

    def _update(self) -> None:
        rows = self.items.selected_rows()
        one = len(rows) == 1
        for b in (self.receive_btn, self.issue_btn, self.return_btn, self.adjust_btn):
            b.setEnabled(bool(rows))  # one or several items
        for b in (self.edit_btn, self.transfer_btn):
            b.setEnabled(one)
        suffix = f" ({len(rows)})" if len(rows) > 1 else ""
        self.receive_btn.setText("Receive" + suffix)
        self.issue_btn.setText("Issue" + suffix)
        self.return_btn.setText("Return" + suffix)
        self._items_count()

    # ------------------------------------------------------------------ actions
    def _item_fields(self, new: bool) -> list[Field]:
        fields = [Field("item_code", "Item code", placeholder="Leave blank to generate")] if new else []
        return fields + [
            Field("name", "Item name", required=True),
            Field("category_id", "Category", "choice", options=ref_options(self.api, "categories", kind="consumable")),
            Field("unit_of_measure", "Unit of measure", required=True, default="piece",
                  placeholder="piece, box, ream, bottle, kg…"),
            Field("reorder_level", "Reorder level", "decimal", default="0",
                  help="Flagged as low stock at or below this quantity."),
            Field("minimum_stock", "Minimum stock", "decimal", default="0"),
            Field("track_expiry", "Batches", "bool", placeholder="Track batch numbers and expiry dates"),
            Field("description", "Description", "multiline"),
        ]

    def new_item(self) -> None:
        if run_form(self, "New consumable item", self._item_fields(True), None,
                    lambda v: self.api.post("/stock/items", v)):
            self.refresh_items()

    def edit_item(self) -> None:
        row = self.items.selected()
        if row and run_form(self, f"Edit {row['item_code']}", self._item_fields(False), row,
                            lambda v: self.api.patch(f"/stock/items/{row['id']}", v)):
            self.refresh_items()

    def movement(self, kind: str) -> None:
        rows = self.items.selected_rows()
        if len(rows) > 1:
            dialog = StockLinesDialog(self.api, kind, rows, self)
            if dialog.exec():
                self.refresh_items()
            return
        row = self.items.selected()
        if not row:
            return
        api = self.api
        unit = row["unit_of_measure"]
        fields = [Field("location_id", "Storage location", "choice", required=True, allow_empty=False,
                        options=ref_options(api, "storage-locations")),
                  Field("quantity", f"Quantity ({unit})", "decimal", required=True)]
        intro = f"{row['name']} — {fmt.qty(row['on_hand'])} {unit} on hand in total."
        if kind in {"RECEIPT", "OPENING"}:
            fields.append(Field("unit_cost", "Unit cost", "decimal", required=True, extra={"decimals": 4},
                                default=row["average_cost"] if row["average_cost"] != "0" else ""))
            if kind == "RECEIPT":
                fields.append(Field("supplier_id", "Supplier", "choice", options=ref_options(api, "suppliers")))
            if row["track_expiry"]:
                fields += [Field("batch_no", "Batch / lot number", required=True),
                           Field("expiry_date", "Expiry date", "date", required=True)]
        if kind == "ISSUE":
            fields += [Field("department_id", "Issued to department", "choice",
                             options=ref_options(api, "departments")),
                       Field("employee_id", "Issued to employee", "choice", editable_choice=True,
                             options=ref_options(api, "employees", "full_name"))]
            if row["track_expiry"]:
                intro += " Batches closest to expiry are issued first."
        if kind == "RETURN":
            fields.append(Field("department_id", "Returned by department", "choice",
                                options=ref_options(api, "departments")))
        fields.append(Field("reference", "Reference", placeholder={
            "RECEIPT": "Delivery note / invoice no.", "ISSUE": "Requisition no."}.get(kind, "")))
        needs_reason = kind in {"DAMAGE", "EXPIRY", "ADJUSTMENT_IN", "ADJUSTMENT_OUT"}
        fields.append(Field("reason", "Reason", "multiline", required=needs_reason))
        request_id = api.request_id()  # makes a double-click or retry safe
        if run_form(self, f"{MOVEMENT_TYPES[kind]} — {row['name']}", fields, None,
                    lambda v: api.post("/stock/movements", {**v, "movement_type": kind, "item_id": row["id"],
                                                             "request_id": request_id}),
                    submit_label=f"Record {MOVEMENT_TYPES[kind].lower()}", intro=intro):
            self.refresh_items()

    def transfer(self) -> None:
        row = self.items.selected()
        if not row:
            return
        opts = ref_options(self.api, "storage-locations")
        fields = [Field("from_location_id", "From", "choice", options=opts, required=True, allow_empty=False),
                  Field("to_location_id", "To", "choice", options=opts, required=True, allow_empty=False),
                  Field("quantity", f"Quantity ({row['unit_of_measure']})", "decimal", required=True),
                  Field("reference", "Reference"), Field("reason", "Reason", "multiline")]
        if run_form(self, f"Transfer — {row['name']}", fields, None,
                    lambda v: self.api.post("/stock/transfers", {**v, "item_id": row["id"]}),
                    submit_label="Transfer", intro="Both sides are recorded together; the school total is unchanged."):
            self.refresh_items()


class StockLinesDialog(QDialog):
    """One movement (receive, issue, return, adjust…) for several items, saved as one transaction."""

    def __init__(self, api, kind: str, rows: list[dict], parent=None):
        super().__init__(parent)
        self.api, self.kind = api, kind
        self.request_id = api.request_id()  # a double-click or retry records the batch once
        label = MOVEMENT_TYPES[kind]
        self.setWindowTitle(f"{label} — {len(rows)} items")
        self.setMinimumWidth(720)
        self.costs = kind in {"RECEIPT", "OPENING"}
        self.batches = self.costs and any(r["track_expiry"] for r in rows)
        layout = QVBoxLayout(self)
        intro = QLabel("All lines are saved together on one reference. If any line cannot be recorded "
                       "(for example, not enough stock), nothing is saved."
                       + (" Batches closest to expiry are issued first." if kind == "ISSUE" else ""))
        intro.setObjectName("Hint")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.location = self._combo(api.lookup("storage-locations"), "name", empty=False)
        form.addRow("Storage location *", self.location)
        self.department = self.employee = self.supplier = None
        if kind in {"ISSUE", "RETURN"}:
            self.department = self._combo(api.lookup("departments"), "name")
            form.addRow("Issued to department" if kind == "ISSUE" else "Returned by department", self.department)
        if kind == "ISSUE":
            self.employee = self._combo(api.lookup("employees"), "full_name")
            form.addRow("Issued to employee", self.employee)
        if kind == "RECEIPT":
            self.supplier = self._combo(api.lookup("suppliers"), "name")
            form.addRow("Supplier", self.supplier)
        self.reference = QLineEdit()
        self.reference.setPlaceholderText({"RECEIPT": "Delivery note / invoice no.",
                                           "ISSUE": "Requisition no."}.get(kind, ""))
        form.addRow("Reference", self.reference)
        self.needs_reason = kind in {"DAMAGE", "EXPIRY", "ADJUSTMENT_IN", "ADJUSTMENT_OUT"}
        self.reason = QPlainTextEdit()
        self.reason.setFixedHeight(56)
        form.addRow("Reason *" if self.needs_reason else "Reason", self.reason)
        layout.addLayout(form)

        headers = ["Item", "On hand", "Quantity"] + (["Unit cost"] if self.costs else []) + \
                  (["Batch no.", "Expiry"] if self.batches else []) + [""]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(self.table, 1)
        self.lines: list[dict] = []
        for r in rows:
            self._add_line(r)

        add_row = QHBoxLayout()
        self.add_combo = QComboBox()
        self.add_combo.setEditable(True)
        self.add_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.add_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.add_combo.lineEdit().setPlaceholderText("Add another item…")
        self._all_items = {r["id"]: r for r in (api.get("/stock/items") or [])}
        for item in self._all_items.values():
            self.add_combo.addItem(f"{item['item_code']}  {item['name']}", item["id"])
        self.add_combo.setCurrentIndex(-1)
        add = QPushButton("Add line")
        add.clicked.connect(self._add_selected)
        add_row.addWidget(self.add_combo, 1)
        add_row.addWidget(add)
        layout.addLayout(add_row)

        self.error = QLabel()
        self.error.setObjectName("FormError")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(f"Record {label.lower()}")
        ok.setObjectName("Primary")
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _combo(rows: list[dict], label: str, empty: bool = True) -> QComboBox:
        combo = QComboBox()
        if empty:
            combo.addItem("(none)", None)
        for r in rows:
            combo.addItem(r.get(label) or r.get("name", ""), r["id"])
        return combo

    @staticmethod
    def _number(decimals: int, value: str = "") -> QLineEdit:
        edit = QLineEdit(value)
        validator = QDoubleValidator(0, 1e12, decimals)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        edit.setValidator(validator)
        return edit

    def _add_line(self, item: dict) -> None:
        if any(line["item"]["id"] == item["id"] for line in self.lines):
            return
        r = self.table.rowCount()
        self.table.insertRow(r)
        name = QLabel(f"{item['name']}  ({item['unit_of_measure']})")
        self.table.setCellWidget(r, 0, name)
        self.table.setCellWidget(r, 1, QLabel(fmt.qty(item["on_hand"])))
        line = {"item": item, "quantity": self._number(3)}
        self.table.setCellWidget(r, 2, line["quantity"])
        col = 3
        if self.costs:
            cost = item["average_cost"] if item["average_cost"] not in ("0", "0.00") else ""
            line["unit_cost"] = self._number(4, cost)
            self.table.setCellWidget(r, col, line["unit_cost"])
            col += 1
        if self.batches:
            line["batch_no"], line["expiry"] = QLineEdit(), QDateEdit(QDate.currentDate().addYears(1))
            line["expiry"].setCalendarPopup(True)
            line["expiry"].setDisplayFormat("dd MMM yyyy")
            for w in (line["batch_no"], line["expiry"]):
                w.setEnabled(bool(item["track_expiry"]))
            self.table.setCellWidget(r, col, line["batch_no"])
            self.table.setCellWidget(r, col + 1, line["expiry"])
            col += 2
        remove = QToolButton()
        remove.setText("✕")
        remove.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        remove.setToolTip("Remove this line")
        remove.clicked.connect(lambda _=False, ln=line: self._remove(ln))
        self.table.setCellWidget(r, col, remove)
        self.lines.append(line)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _add_selected(self) -> None:
        item = self._all_items.get(self.add_combo.currentData())
        if item and self.add_combo.currentText() == self.add_combo.itemText(self.add_combo.currentIndex()):
            if item["track_expiry"] and self.costs and not self.batches:
                return self._show(f"{item['name']} tracks batches; record it on its own with Receive.")
            self._add_line(item)
            self.add_combo.setCurrentIndex(-1)

    def _remove(self, line: dict) -> None:
        i = self.lines.index(line)
        self.lines.pop(i)
        self.table.removeRow(i)

    def _show(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()

    def _submit(self) -> None:
        if not self.lines:
            return self._show("Add at least one item.")
        if self.needs_reason and not self.reason.toPlainText().strip():
            return self._show("A reason is required.")
        lines = []
        for line in self.lines:
            item = line["item"]
            qty = line["quantity"].text().replace(",", "").strip()
            if not qty:
                return self._show(f"Enter the quantity of {item['name']}, or remove the line.")
            data = {"item_id": item["id"], "quantity": qty}
            if self.costs:
                cost = line["unit_cost"].text().replace(",", "").strip()
                if not cost:
                    return self._show(f"Enter the unit cost of {item['name']}.")
                data["unit_cost"] = cost
            if self.batches and item["track_expiry"]:
                if not line["batch_no"].text().strip():
                    return self._show(f"Enter the batch number of {item['name']}.")
                data["batch_no"] = line["batch_no"].text().strip()
                data["expiry_date"] = line["expiry"].date().toString("yyyy-MM-dd")
            lines.append(data)
        body = {"movement_type": self.kind, "location_id": self.location.currentData(), "lines": lines,
                "reference": self.reference.text().strip(), "reason": self.reason.toPlainText().strip(),
                "request_id": self.request_id}
        for key, combo in (("department_id", self.department), ("employee_id", self.employee),
                           ("supplier_id", self.supplier)):
            if combo is not None and combo.currentData():
                body[key] = combo.currentData()
        try:
            self.api.post("/stock/movements/batch", body)
        except ApiError as exc:
            return self._show(exc.message)
        self.accept()
