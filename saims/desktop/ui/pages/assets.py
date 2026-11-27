"""Asset register: filters, table, detail panel with QR code and history, single and bulk actions."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPainter, QPen, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPushButton, QScrollArea, QSplitter, QVBoxLayout,
)

from saims.desktop.api import ApiError
from saims.desktop.ui import formatting as fmt
from saims.desktop.ui import theme
from saims.desktop.ui.forms import CONDITIONS, Field, dict_options, ref_options, run_form
from saims.desktop.ui.pages.base import Page
from saims.desktop.ui.widgets import (
    CheckCombo, Column, DataTable, STATUS_TOKENS, hint, money_col, show_error, status_color,
)

STATUSES = {"available": "Available", "assigned": "Assigned", "borrowed": "Borrowed",
            "under_maintenance": "Under maintenance", "damaged": "Damaged", "missing": "Missing",
            "retired": "Retired", "disposed": "Disposed"}
FUNDING = {"school_funds": "School funds", "government": "Government allocation", "grant": "Grant",
           "donation": "Donation", "other": "Other"}

# action: (label, allowed statuses, permission, needs reason)
LIFECYCLE = {
    "send_to_maintenance": ("Send to maintenance…", {"available", "damaged"}, "maintenance.manage", False),
    "complete_maintenance": ("Complete maintenance…", {"under_maintenance"}, "maintenance.manage", False),
    "mark_damaged": ("Mark damaged…", {"available", "assigned"}, "assets.mark_missing", True),
    "mark_missing": ("Mark missing…", {"available", "assigned", "borrowed", "damaged"}, "assets.mark_missing", True),
    "recover": ("Record recovery…", {"missing"}, "assets.mark_missing", False),
    "retire": ("Retire…", {"available", "damaged"}, "assets.dispose", True),
    "dispose": ("Dispose…", {"retired"}, "assets.dispose", True),
}


class AssetsPage(Page):
    """Asset register. Select several rows (Ctrl/Shift-click) to act on them together; bulk actions are
    all-or-nothing on the server. People who see only their own assets get a read-only "My Assets" list."""

    title = "Assets"

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        self.own = not api.can("assets.view")
        self._make_table()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search code, name, serial, brand…  or scan a QR label")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.refresh)
        self.search.textChanged.connect(lambda t: self.refresh() if not t else None)
        self.status = CheckCombo("All statuses", "statuses")
        self.status.set_options([(v, k) for k, v in STATUSES.items()])
        self.category = CheckCombo("All categories", "categories")
        self.department = CheckCombo("All departments", "departments")
        self.room = CheckCombo("All rooms", "rooms")
        self.filter_boxes = (self.status, self.category, self.department, self.room)
        filters.addWidget(self.search, 3)
        for combo in self.filter_boxes:
            combo.changed.connect(self.refresh)
            combo.setVisible(not self.own)
            filters.addWidget(combo, 1)
        layout.addLayout(filters)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.register_btn = self.button("Register asset", self.register, "box", True, "assets.create")
        self.edit_btn = self.button("Edit", self.edit, permission="assets.update")
        self.assign_btn = self.button("Assign", self.assign, "people", permission="assets.assign")
        self.return_btn = self.button("Return", self.return_asset, permission="assets.assign")
        self.transfer_btn = self.button("Transfer", self.transfer, "movements", permission="assets.transfer")
        self.more_btn = QPushButton("More actions")
        self.more_btn.clicked.connect(self._more_menu)
        self.more_btn.setVisible(api.can_any(*{p for _, _, p, _ in LIFECYCLE.values()}, "assets.update",
                                             "assets.archive"))
        self.label_btn = self.button("Print QR label", self.print_labels, "qr")
        for b in (self.register_btn, self.edit_btn, self.assign_btn, self.return_btn, self.transfer_btn,
                  self.more_btn, self.label_btn):
            bar.addWidget(b)
        bar.addStretch()
        self.count = QLabel()
        self.count.setObjectName("Hint")
        bar.addWidget(self.count)
        bar.addWidget(self.export_button(self.table, "Asset list", self._filter_text))
        layout.addLayout(bar)

        split = QSplitter()
        split.addWidget(self.table)
        self.detail = AssetDetail(api)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([760, 420])
        layout.addWidget(split, 1)
        if not self.own:
            tip = hint("Tip: Ctrl-click or Shift-click to select several assets and act on them together.")
            layout.addWidget(tip)
        self._loaded_filters = False
        self._update_buttons([])

    def _make_table(self) -> DataTable:
        """The asset table; several rows can be selected for bulk actions (not in the read-only own view)."""
        self.table = DataTable([
            Column("Code", "asset_code"), Column("Name", "name"), Column("Category", "category"),
            Column("Status", "status_label", color=status_color()), Column("Condition", "condition_label"),
            Column("Room", "room"), Column("Department", "department"), Column("Assigned to", "custodian"),
            Column("Serial no.", "serial_number"), money_col("Cost", "acquisition_cost"),
        ], multi=not self.own)
        self.table.selectionModel().selectionChanged.connect(self._selected)
        self.table.doubleClicked.connect(lambda _: self.edit())
        return self.table

    def _filter_text(self) -> str:
        parts = [c.summary() for c in self.filter_boxes if c.values()]
        if self.search.text().strip():
            parts.insert(0, f'"{self.search.text().strip()}"')
        return " · ".join(parts)

    # ------------------------------------------------------------------ data
    def _load_filters(self) -> None:
        if not self.own:
            for combo, key, params in ((self.category, "categories", {"kind": "asset"}),
                                       (self.department, "departments", {}), (self.room, "rooms", {})):
                combo.set_options([(r.get("label") or r["name"], r["id"]) for r in self.api.lookup(key, **params)])
        self._loaded_filters = True

    def refresh(self) -> None:
        if not self._loaded_filters:
            self._load_filters()
        q = self.search.text().strip()
        if q.upper().startswith("SAIMS:ASSET:"):  # scanned QR label
            q = q.split(":", 2)[2]
            self.search.setText(q)
        try:
            rows = self.api.get("/assets", q=q, status=self.status.values(), category_id=self.category.values(),
                                department_id=self.department.values(), room_id=self.room.values())
        except ApiError as exc:
            show_error(self, exc)
            return
        self.table.set_rows(rows)
        self.count.setText(f"{len(rows)} asset{'s' if len(rows) != 1 else ''}")
        if len(rows) == 1:
            self.table.selectRow(0)
        self._selected()

    def show_record(self, asset_id: str) -> None:
        self.search.clear()
        for combo in self.filter_boxes:
            combo.clear_selection(emit=False)
        self.refresh()
        self.table.select_id(asset_id)

    def search_for(self, text: str) -> None:
        self.search.setText(text)
        self.refresh()

    def _selected(self) -> None:
        rows = self.table.selected_rows()
        self._update_buttons(rows)
        n = len(rows)
        base = self.count.text().split(" · ")[0]
        self.count.setText(f"{base} · {n} selected" if n > 1 else base)
        if n > 1:
            self.detail.show_many(rows)
        else:
            self.detail.show_asset(rows[0]["id"] if rows else None)

    def _update_buttons(self, rows: list[dict]) -> None:
        statuses = {r["status"] for r in rows}
        many = len(rows) > 1

        def all_in(allowed: set[str]) -> bool:
            return bool(rows) and statuses <= allowed

        self.edit_btn.setEnabled(len(rows) == 1 and statuses != {"disposed"})
        self.assign_btn.setEnabled(all_in({"available"}))
        self.return_btn.setEnabled(all_in({"assigned"}))
        self.transfer_btn.setEnabled(all_in({"available", "assigned", "damaged"}))
        self.more_btn.setEnabled(bool(rows))
        self.label_btn.setEnabled(bool(rows))
        suffix = f" ({len(rows)})" if many else ""
        self.assign_btn.setText("Assign" + suffix)
        self.return_btn.setText("Return" + suffix)
        self.transfer_btn.setText("Transfer" + suffix)
        self.label_btn.setText(f"Print {len(rows)} QR labels" if many else "Print QR label")
        if many:
            why = "Only available assets can be assigned." if not self.assign_btn.isEnabled() else ""
            self.assign_btn.setToolTip(why)
            self.return_btn.setToolTip("" if self.return_btn.isEnabled() else "Only assigned assets can be returned.")
        else:
            self.assign_btn.setToolTip("")
            self.return_btn.setToolTip("")

    # ------------------------------------------------------------------ helpers for bulk actions
    @staticmethod
    def _codes(rows: list[dict]) -> str:
        codes = [r["asset_code"] for r in rows]
        return ", ".join(codes[:6]) + (f" and {len(codes) - 6} more" if len(codes) > 6 else "")

    def _bulk(self, rows: list[dict], action: str, title: str, fields: list[Field], submit_label: str,
              intro: str = "", extra: dict | None = None) -> None:
        ids = [r["id"] for r in rows]
        lead = f"{len(rows)} assets: {self._codes(rows)}.\nAll are updated together — if any one cannot be, " \
               f"nothing changes."
        if run_form(self, title, fields, None,
                    lambda v: self.api.post("/assets/bulk", {"action": action, "asset_ids": ids, **(extra or {}),
                                                             **v}),
                    submit_label=submit_label, intro=f"{intro}\n\n{lead}" if intro else lead):
            self.refresh()
            self.table.select_ids(ids)

    # ------------------------------------------------------------------ forms
    def _asset_fields(self, new: bool) -> list[Field]:
        api = self.api
        fields = []
        if new:
            fields.append(Field("asset_code", "Asset code", placeholder="Leave blank to generate"))
        fields += [
            Field("name", "Name", required=True, placeholder="e.g. Laptop"),
            Field("category_id", "Category", "choice", options=ref_options(api, "categories", "label", kind="asset")),
            Field("brand", "Brand"), Field("model", "Model"),
            Field("serial_number", "Serial number", placeholder="Must be unique if entered"),
        ]
        if new:
            fields += [Field("room_id", "Location (room)", "choice", options=ref_options(api, "rooms", "label"),
                             editable_choice=True),
                       Field("condition", "Condition", "choice", options=dict_options(CONDITIONS),
                             allow_empty=False, default="good")]
        fields += [
            Field("department_id", "Department", "choice", options=ref_options(api, "departments"),
                  help="Defaults to the room's department." if new else ""),
            Field("acquisition_date", "Acquired on", "date"),
            Field("acquisition_cost", "Acquisition cost", "decimal", placeholder="0.00", extra={"decimals": 2}),
            Field("funding_source", "Funding source", "choice", options=dict_options(FUNDING), allow_empty=False,
                  default="school_funds"),
            Field("donor", "Donor", placeholder="If donated"),
            Field("supplier_id", "Supplier", "choice", options=ref_options(api, "suppliers")),
            Field("purchase_reference", "Purchase reference"),
            Field("warranty_expiry", "Warranty until", "date"),
            Field("description", "Description", "multiline"),
        ]
        return fields

    def register(self) -> None:
        result = run_form(self, "Register asset", self._asset_fields(True), None,
                          lambda v: self.api.post("/assets", {k: val for k, val in v.items() if val not in ("",)}),
                          submit_label="Register")
        if result:
            self.refresh()
            self.table.select_id(result["id"])

    def edit(self) -> None:
        row = self.table.selected()
        if not row or not self.api.can("assets.update") or row["status"] == "disposed":
            return
        if run_form(self, f"Edit {row['asset_code']}", self._asset_fields(False), row,
                    lambda v: self.api.patch(f"/assets/{row['id']}", v)):
            self.refresh()

    def assign(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            return
        api = self.api
        fields = [
            Field("employee_id", "Employee", "choice", options=ref_options(api, "employees", "full_name"),
                  editable_choice=True),
            Field("department_id", "Department", "choice", options=ref_options(api, "departments")),
            Field("room_id", "Room", "choice", options=ref_options(api, "rooms", "label"), editable_choice=True),
            Field("condition", "Condition at release", "choice", options=dict_options(CONDITIONS),
                  allow_empty=len(rows) > 1, empty_label="(keep each asset's condition)",
                  default=rows[0]["condition"] if len(rows) == 1 else None),
            Field("acknowledged", "Acknowledgment", "bool", placeholder="Employee has signed for "
                  + ("this asset" if len(rows) == 1 else "these assets")),
            Field("notes", "Notes", "multiline"),
        ]
        if len(rows) > 1:
            return self._bulk(rows, "assign", f"Assign {len(rows)} assets", fields, "Assign all",
                              "Choose who or where they are assigned to. At least one is required.")
        row = rows[0]
        if run_form(self, f"Assign {row['asset_code']}", fields, None,
                    lambda v: api.post(f"/assets/{row['id']}/assign", v), submit_label="Assign",
                    intro=f"{row['name']} — choose who or where it is assigned to. At least one is required."):
            self.refresh()

    def return_asset(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            return
        fields = [Field("condition", "Condition on return", "choice", options=dict_options(CONDITIONS),
                        allow_empty=len(rows) > 1, empty_label="(keep each asset's condition)",
                        default=rows[0]["condition"] if len(rows) == 1 else None),
                  Field("notes", "Notes", "multiline")]
        if len(rows) > 1:
            return self._bulk(rows, "return", f"Return {len(rows)} assets", fields, "Record returns")
        row = rows[0]
        if run_form(self, f"Return {row['asset_code']}", fields, None,
                    lambda v: self.api.post(f"/assets/{row['id']}/return", v), submit_label="Record return",
                    intro=f"{row['name']} is assigned to {row['custodian'] or 'someone'}."):
            self.refresh()

    def transfer(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            return
        fields = [Field("room_id", "To room", "choice", options=ref_options(self.api, "rooms", "label"),
                        editable_choice=True),
                  Field("department_id", "To department", "choice", options=ref_options(self.api, "departments"),
                        help="Leave blank to use the room's department."),
                  Field("reason", "Reason", "multiline", required=True)]
        if len(rows) > 1:
            return self._bulk(rows, "transfer", f"Transfer {len(rows)} assets", fields, "Transfer all")
        row = rows[0]
        if run_form(self, f"Transfer {row['asset_code']}", fields, None,
                    lambda v: self.api.post(f"/assets/{row['id']}/transfer", v), submit_label="Transfer",
                    intro=f"Currently in {row['room'] or 'no room'}, {row['department'] or 'no department'}."):
            self.refresh()

    def _more_menu(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            return
        statuses = {r["status"] for r in rows}
        menu = QMenu(self)
        if len(rows) > 1:
            menu.addSection(f"{len(rows)} selected assets")
        for action, (label, allowed, perm, _) in LIFECYCLE.items():
            if self.api.can(perm):
                a = menu.addAction(label, lambda act=action: self.lifecycle(act))
                a.setEnabled(statuses <= allowed)
        menu.addSeparator()
        if self.api.can("assets.update"):
            menu.addAction("Update condition…", self.update_condition).setEnabled("disposed" not in statuses)
        if self.api.can("assets.archive"):
            menu.addAction("Archive record…", self.archive).setEnabled(
                len(rows) == 1 and statuses <= {"available", "retired", "disposed"})
        if menu.isEmpty():
            menu.addAction("No actions available for your role").setEnabled(False)
        menu.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def lifecycle(self, action: str) -> None:
        rows = self.table.selected_rows()
        if not rows:
            return
        label, _, _, needs_reason = LIFECYCLE[action]
        fields = [Field("reason", "Reason" if needs_reason else "Notes", "multiline", required=needs_reason)]
        if action == "complete_maintenance":
            fields.append(Field("condition", "Condition after work", "choice", options=dict_options(CONDITIONS),
                                allow_empty=False, default="good",
                                help="Choose Damaged if the repair was not successful."))
        if action in {"mark_missing", "recover"}:
            fields.append(Field("event_date", "Date", "date", default="today"))
        intro = {"dispose": "Disposal is permanent. The records and their history are kept for audit.",
                 "mark_missing": "Any active assignment is closed and the custodian is recorded in the history."
                 }.get(action, "")
        name = label.rstrip("…")
        if len(rows) > 1:
            return self._bulk(rows, "lifecycle", f"{name} — {len(rows)} assets", fields, name, intro,
                              {"lifecycle_action": action})
        row = rows[0]
        if run_form(self, f"{name} — {row['asset_code']}", fields, None,
                    lambda v: self.api.post(f"/assets/{row['id']}/lifecycle", {"action": action, **v}),
                    submit_label=name, intro=intro):
            self.refresh()

    def update_condition(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            return
        fields = [Field("condition", "Condition", "choice", options=dict_options(CONDITIONS), allow_empty=False,
                        default=rows[0]["condition"]), Field("notes", "Note", "multiline")]
        if len(rows) > 1:
            return self._bulk(rows, "condition", f"Condition — {len(rows)} assets", fields, "Update all")
        row = rows[0]
        if run_form(self, f"Condition — {row['asset_code']}", fields, None,
                    lambda v: self.api.post(f"/assets/{row['id']}/condition",
                                            {"condition": v["condition"], "note": v["notes"]})):
            self.refresh()

    def archive(self) -> None:
        row = self.table.selected()
        if not row:
            return
        if run_form(self, f"Archive {row['asset_code']}", [Field("reason", "Reason", "multiline", required=True)],
                    None, lambda v: self.api.post(f"/assets/{row['id']}/archive", v), submit_label="Archive",
                    intro="Use this for records registered in error. Assets are never deleted."):
            self.refresh()

    # ------------------------------------------------------------------ QR labels
    def print_labels(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            return
        codes: list[tuple[dict, QPixmap]] = []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for row in rows:
                qr = QPixmap()
                qr.loadFromData(self.api.request("GET", f"/assets/{row['id']}/qr.png", raw=True))
                codes.append((row, qr))
        except ApiError as exc:
            return show_error(self, exc)
        finally:
            QApplication.restoreOverrideCursor()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if len(codes) == 1:
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A6))
            printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        else:
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        if QPrintDialog(printer, self).exec() != QPrintDialog.DialogCode.Accepted:
            return
        school = self.api.settings().get("school_name", "")
        p = QPainter(printer)
        page = QRectF(printer.pageRect(QPrinter.Unit.DevicePixel))
        if len(codes) == 1:
            _draw_label(p, page, *codes[0], school, 16)
        else:
            cols, per_row = 3, 8  # 24 labels per A4 sheet
            w, h = page.width() / cols, page.height() / per_row
            for n, (row, qr) in enumerate(codes):
                if n and n % (cols * per_row) == 0:
                    printer.newPage()
                i = n % (cols * per_row)
                cell = QRectF(page.x() + (i % cols) * w, page.y() + (i // cols) * h, w, h)
                p.setPen(QPen(Qt.GlobalColor.lightGray, 0))
                p.drawRect(cell)  # cutting guide
                p.setPen(Qt.GlobalColor.black)
                _draw_label(p, cell.adjusted(w * 0.04, h * 0.08, -w * 0.04, -h * 0.08), row, qr, school, 8)
        p.end()


def _draw_label(p: QPainter, area: QRectF, row: dict, qr: QPixmap, school: str, size: int) -> None:
    """QR code on the left, asset code, name and school on the right."""
    side = min(area.height(), area.width() * 0.45)
    p.drawPixmap(QRectF(area.x(), area.y() + (area.height() - side) / 2, side, side).toRect(), qr)
    x = area.x() + side + area.width() * 0.04
    text = QRectF(x, area.y(), area.right() - x, area.height())
    font = QFont()
    font.setPointSize(size)
    font.setBold(True)
    p.setFont(font)
    p.drawText(text.adjusted(0, text.height() * 0.15, 0, 0), Qt.TextFlag.TextWordWrap, row["asset_code"])
    font.setPointSize(max(size - 4, 6))
    font.setBold(False)
    p.setFont(font)
    p.drawText(text.adjusted(0, text.height() * 0.42, 0, 0), Qt.TextFlag.TextWordWrap, f"{row['name']}\n{school}")


class AssetDetail(QScrollArea):
    """Right-hand panel: QR code, key facts, current assignment and history."""

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumWidth(340)
        body = QFrame()
        body.setObjectName("Card")
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 16, 18, 16)
        top = QHBoxLayout()
        titles = QVBoxLayout()
        self.code = QLabel()
        self.code.setObjectName("Hint")
        self.name = QLabel("Select an asset")
        self.name.setObjectName("DetailTitle")
        self.name.setWordWrap(True)
        self.status = QLabel()
        self.status.setObjectName("StatusPill")
        titles.addWidget(self.code)
        titles.addWidget(self.name)
        titles.addWidget(self.status, 0, Qt.AlignmentFlag.AlignLeft)
        titles.addStretch()
        top.addLayout(titles, 1)
        self.qr = QLabel()
        self.qr.setFixedSize(112, 112)
        self.qr.setScaledContents(True)
        top.addWidget(self.qr)
        layout.addLayout(top)
        self.facts = QGridLayout()
        self.facts.setHorizontalSpacing(14)
        self.facts.setVerticalSpacing(5)
        layout.addLayout(self.facts)
        self.assignment = hint()
        layout.addWidget(self.assignment)
        self.history_title = QLabel("History")
        self.history_title.setObjectName("CardTitle")
        layout.addWidget(self.history_title)
        self.history = QListWidget()
        self.history.setObjectName("History")
        self.history.setWordWrap(True)
        self.history.setMinimumHeight(200)
        layout.addWidget(self.history, 1)
        self.show_asset(None)

    def _clear_facts(self) -> None:
        while self.facts.count():
            w = self.facts.takeAt(0).widget()
            if w:
                w.hide()  # hidden now; deleted when the event loop runs
                w.deleteLater()
        self.history.clear()

    def show_many(self, rows: list[dict]) -> None:
        """Summary when several assets are selected."""
        self._clear_facts()
        self.code.setText("")
        self.name.setText(f"{len(rows)} assets selected")
        self.status.hide()
        self.qr.clear()
        self.assignment.setText("Actions in the toolbar apply to all of them together.")
        self.history_title.hide()
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["status_label"]] = counts.get(r["status_label"], 0) + 1
        total = sum(fmt.dec(r["acquisition_cost"]) for r in rows)
        facts = [(label, str(n)) for label, n in sorted(counts.items())] + [("Total cost", fmt.money(total))]
        for i, (key, value) in enumerate(facts):
            k = QLabel(key)
            k.setObjectName("DetailKey")
            self.facts.addWidget(k, i, 0)
            self.facts.addWidget(QLabel(value), i, 1)

    def show_asset(self, asset_id: str | None) -> None:
        self._clear_facts()
        self.history_title.setVisible(bool(asset_id))
        if not asset_id:
            self.code.setText("")
            self.name.setText("Select an asset to see its details and history")
            self.status.hide()
            self.qr.clear()
            self.assignment.setText("")
            return
        try:
            a = self.api.get(f"/assets/{asset_id}")
            png = self.api.request("GET", f"/assets/{asset_id}/qr.png", raw=True)
        except ApiError as exc:
            self.name.setText(exc.message)
            return
        pm = QPixmap()
        pm.loadFromData(png)
        self.qr.setPixmap(pm)
        self.code.setText(a["asset_code"])
        self.name.setText(a["name"])
        token = STATUS_TOKENS.get(a["status"], "muted")
        self.status.setText(a["status_label"])
        self.status.setStyleSheet(f"color: {theme.color(token).name()}; border: 1.5px solid "
                                  f"{theme.color(token).name()};")
        self.status.show()
        facts = [
            ("Category", a["category"]), ("Brand / model", " ".join(x for x in (a["brand"], a["model"]) if x)),
            ("Serial no.", a["serial_number"]), ("Location", f"{a['room']} · {a['building']}" if a["room"] else ""),
            ("Department", a["department"]), ("Condition", a["condition_label"]),
            ("Acquired", fmt.day(a["acquisition_date"])), ("Cost", fmt.money(a["acquisition_cost"])),
            ("Funding", a["funding_label"] + (f" — {a['donor']}" if a["donor"] else "")),
            ("Supplier", a["supplier"]), ("Warranty until", fmt.day(a["warranty_expiry"])),
        ]
        for i, (key, value) in enumerate(f for f in facts if f[1]):
            k = QLabel(key)
            k.setObjectName("DetailKey")
            v = QLabel(value)
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.facts.addWidget(k, i, 0, Qt.AlignmentFlag.AlignTop)
            self.facts.addWidget(v, i, 1)
        x = a.get("assignment")
        if x:
            who = x["employee"] or x["department"] or x["room"]
            self.assignment.setText(f"Assigned to <b>{who}</b> since {fmt.day(x['assigned_at'])}"
                                    + (" · acknowledged" if x["acknowledged"] else " · not yet acknowledged"))
        else:
            self.assignment.setText("")
        for e in a["history"]:
            desc = e["description"]
            first = e["label"].split()[0].lower()
            text = desc if desc.lower().startswith(first) else f"{e['label']} — {desc}"
            if e["reason"]:
                text += f"\nReason: {e['reason']}"
            text += f"\n{fmt.when(e['created_at'])} · {e['user']}"
            self.history.addItem(QListWidgetItem(text))
