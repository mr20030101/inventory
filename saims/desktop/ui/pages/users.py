"""User accounts and the role / permission matrix."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from saims.desktop.api import ApiError
from saims.desktop.ui import formatting as fmt
from saims.desktop.ui import theme
from saims.desktop.ui.forms import Field, run_form
from saims.desktop.ui.pages.base import Page
from saims.desktop.ui.widgets import Column, DataTable, confirm, show_error


class UserDialog(QDialog):
    def __init__(self, api, roles: list[dict], user: dict | None, parent=None):
        super().__init__(parent)
        self.api, self.user = api, user
        self.setWindowTitle(f"Edit {user['username']}" if user else "New user")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.username = QLineEdit(user["username"] if user else "")
        self.username.setEnabled(user is None)
        self.full_name = QLineEdit(user["full_name"] if user else "")
        self.email = QLineEdit(user["email"] if user else "")
        self.employee = None
        form.addRow("Username *", self.username)
        form.addRow("Full name *", self.full_name)
        form.addRow("Email", self.email)
        if user is None:
            self.password = QLineEdit()
            self.password.setEchoMode(QLineEdit.EchoMode.Password)
            self.password.setPlaceholderText("At least 8 characters")
            form.addRow("Password *", self.password)
        layout.addLayout(form)
        layout.addWidget(QLabel("Roles"))
        self.role_boxes = {}
        for r in roles:
            box = QCheckBox(f"{r['name']} — {r['description']}")
            box.setChecked(bool(user and r["code"] in user["roles"]))
            self.role_boxes[r["code"]] = box
            layout.addWidget(box)
        self.error = QLabel()
        self.error.setObjectName("FormError")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("Primary")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        data = {"full_name": self.full_name.text(), "email": self.email.text(),
                "roles": [c for c, b in self.role_boxes.items() if b.isChecked()]}
        try:
            if self.user:
                self.api.patch(f"/users/{self.user['id']}", data)
            else:
                self.api.post("/users", {**data, "username": self.username.text(), "password": self.password.text()})
        except ApiError as exc:
            self.error.setText(exc.message)
            self.error.show()
            return
        self.accept()


class UsersPage(Page):
    title = "Users & Roles"

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        users = QWidget()
        ul = QVBoxLayout(users)
        ul.setContentsMargins(0, 8, 0, 0)
        bar = QHBoxLayout()
        self.new_btn = self.button("New user", self.new_user, "people", True, "users.create")
        self.edit_btn = self.button("Edit / roles", self.edit_user, permission="users.update")
        self.active_btn = self.button("Deactivate", self.toggle_active, permission="users.deactivate")
        self.reset_btn = self.button("Reset password", self.reset_password, "key", permission="users.deactivate")
        for b in (self.new_btn, self.edit_btn, self.active_btn, self.reset_btn):
            bar.addWidget(b)
        bar.addStretch()
        ul.addLayout(bar)
        self.table = DataTable([
            Column("Username", "username"), Column("Full name", "full_name"),
            Column("Roles", "role_names", lambda v: ", ".join(v)), Column("Email", "email"),
            Column("Status", "is_active", lambda a: "Active" if a else "Deactivated",
                   color=lambda r: "ok" if r["is_active"] else "danger"),
            Column("Last sign-in", "last_login_at", fmt.when),
        ])
        self.table.selectionModel().selectionChanged.connect(self._update)
        self.table.doubleClicked.connect(lambda _: self.edit_user())
        ul.addWidget(self.table)
        note = QLabel("Deactivating a user or resetting their password signs them out everywhere immediately.")
        note.setObjectName("Hint")
        ul.addWidget(note)
        self.tabs.addTab(users, "Users")
        self.matrix = QTableWidget()
        self.matrix.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.matrix.setAlternatingRowColors(True)
        self.tabs.addTab(self.matrix, "Role permissions")
        self.roles: list[dict] = []
        self._update()

    def refresh(self) -> None:
        try:
            self.table.set_rows(self.api.get("/users"))
            self.roles = self.api.get("/roles")
            perms = self.api.get("/permissions")
        except ApiError as exc:
            return show_error(self, exc)
        self.matrix.setRowCount(len(perms))
        self.matrix.setColumnCount(len(self.roles))
        self.matrix.setHorizontalHeaderLabels([r["name"] for r in self.roles])
        self.matrix.setVerticalHeaderLabels([p["description"] for p in perms])
        ok = QBrush(theme.color("ok"))
        for i, p in enumerate(perms):
            for j, r in enumerate(self.roles):
                item = QTableWidgetItem("✓" if p["code"] in r["permissions"] else "")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(ok)
                item.setToolTip(p["code"])
                self.matrix.setItem(i, j, item)
        self.matrix.resizeColumnsToContents()
        self._update()

    def _update(self) -> None:
        row = self.table.selected()
        for b in (self.edit_btn, self.active_btn, self.reset_btn):
            b.setEnabled(row is not None)
        self.active_btn.setText("Reactivate" if row and not row["is_active"] else "Deactivate")

    def new_user(self) -> None:
        if UserDialog(self.api, self.roles, None, self).exec():
            self.refresh()

    def edit_user(self) -> None:
        row = self.table.selected()
        if row and self.api.can("users.update") and UserDialog(self.api, self.roles, row, self).exec():
            self.refresh()

    def toggle_active(self) -> None:
        row = self.table.selected()
        if not row:
            return
        if row["is_active"] and not confirm(self, "Deactivate user",
                                            f"Deactivate {row['full_name']}? They are signed out immediately."):
            return
        self.call(lambda: self.api.post(f"/users/{row['id']}/{'deactivate' if row['is_active'] else 'activate'}"))

    def reset_password(self) -> None:
        row = self.table.selected()
        if row and run_form(self, f"Reset password — {row['username']}",
                            [Field("password", "New password", "password", required=True,
                                   help="At least 8 characters. Share it with the user securely.")], None,
                            lambda v: self.api.post(f"/users/{row['id']}/reset-password", v),
                            submit_label="Reset password"):
            self.refresh()
