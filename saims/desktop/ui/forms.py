"""Declarative forms: describe the fields, get a dialog that validates and submits to the API."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
    QVBoxLayout, QWidget,
)

from saims.desktop.api import ApiError
from saims.desktop.ui.widgets import CheckCombo

Options = list[tuple[str, Any]] | Callable[[], list[tuple[str, Any]]]


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"  # text | multiline | choice | multi | date | decimal | bool | password | info
    required: bool = False
    options: Options | None = None
    allow_empty: bool = True       # choice: offer "(none)"
    empty_label: str = "(none)"
    default: Any = None
    placeholder: str = ""
    help: str = ""
    editable_choice: bool = False  # choice: type to filter
    extra: dict = field(default_factory=dict)


class FormDialog(QDialog):
    """Shows `fields`, calls `submit(values)`; ApiErrors are shown inside the dialog."""

    def __init__(self, parent: QWidget | None, title: str, fields: list[Field], values: dict | None = None,
                 submit: Callable[[dict], Any] | None = None, submit_label: str = "Save", intro: str = "",
                 width: int = 480):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.fields, self.submit, self.result_value = fields, submit, None
        self.widgets: dict[str, QWidget] = {}
        values = values or {}
        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        if intro:
            lead = QLabel(intro)
            lead.setWordWrap(True)
            lead.setObjectName("Hint")
            outer.addWidget(lead)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setVerticalSpacing(8)
        for f in fields:
            w = self._make(f, values.get(f.key, f.default))
            self.widgets[f.key] = w
            label = f"{f.label} *" if f.required else f.label
            form.addRow(label, w)
            if f.help:
                h = QLabel(f.help)
                h.setObjectName("Hint")
                h.setWordWrap(True)
                form.addRow("", h)
        outer.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("FormError")
        self.error.setWordWrap(True)
        self.error.hide()
        outer.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(submit_label)
        ok.setObjectName("Primary")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------ widgets
    def _make(self, f: Field, value: Any) -> QWidget:
        if f.kind == "multiline":
            w = QPlainTextEdit(str(value or ""))
            w.setFixedHeight(70)
            w.setPlaceholderText(f.placeholder)
            return w
        if f.kind == "multi":  # tick several options; the value is a list
            w = CheckCombo(f.placeholder or "Choose…", f.extra.get("noun", "selected"), "Clear selection")
            opts = f.options() if callable(f.options) else (f.options or [])
            w.set_options(list(opts))
            w.set_values(list(value or []), emit=False)
            w.setMinimumContentsLength(30)
            return w
        if f.kind == "choice":
            w = QComboBox()
            opts = f.options() if callable(f.options) else (f.options or [])
            if f.allow_empty:
                w.addItem(f.empty_label, None)
            for text, data in opts:
                w.addItem(text, data)
            if f.editable_choice:
                w.setEditable(True)
                w.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                w.completer().setFilterMode(Qt.MatchFlag.MatchContains)
                w.completer().setCompletionMode(w.completer().CompletionMode.PopupCompletion)
            idx = w.findData(value)
            w.setCurrentIndex(idx if idx >= 0 else 0)
            w.setMinimumContentsLength(24)
            return w
        if f.kind == "date":
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd MMM yyyy")
            w.setMinimumDate(QDate(1990, 1, 1))
            if not f.required:
                w.setSpecialValueText("—")
            if value:
                w.setDate(QDate.fromString(str(value)[:10], "yyyy-MM-dd"))
            else:
                w.setDate(QDate.currentDate() if f.required or f.default == "today" else w.minimumDate())
            return w
        if f.kind == "bool":
            w = QCheckBox(f.placeholder)
            w.setChecked(bool(value))
            return w
        if f.kind == "info":
            w = QLabel(str(value or ""))
            w.setWordWrap(True)
            return w
        w = QLineEdit("" if value is None else str(value))
        w.setPlaceholderText(f.placeholder)
        if f.kind == "password":
            w.setEchoMode(QLineEdit.EchoMode.Password)
        if f.kind == "decimal":
            validator = QDoubleValidator(0, 1e12, f.extra.get("decimals", 3))
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            w.setValidator(validator)
        return w

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in self.fields:
            w = self.widgets[f.key]
            if f.kind == "info":
                continue
            if isinstance(w, QPlainTextEdit):
                out[f.key] = w.toPlainText().strip()
            elif isinstance(w, CheckCombo):
                out[f.key] = w.values()
            elif isinstance(w, QComboBox):
                data = w.currentData()
                if f.editable_choice and w.currentText() != w.itemText(w.currentIndex()):
                    data = None
                out[f.key] = data
            elif isinstance(w, QDateEdit):
                out[f.key] = None if w.date() == w.minimumDate() and not f.required else w.date().toString(
                    "yyyy-MM-dd")
            elif isinstance(w, QCheckBox):
                out[f.key] = w.isChecked()
            else:
                text = w.text().strip()
                out[f.key] = (text.replace(",", "") or None) if f.kind == "decimal" else text
        return out

    def _accept(self) -> None:
        values = self.values()
        for f in self.fields:
            if f.required and values.get(f.key) in (None, "", []):
                return self._show(f"{f.label} is required.")
        if self.submit is None:
            self.result_value = values
            return self.accept()
        try:
            self.result_value = self.submit(values)
        except ApiError as exc:
            return self._show(exc.message)
        self.accept()

    def _show(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()


def run_form(parent, title, fields, values=None, submit=None, **kw) -> Any:
    """Show a form; return the submit result (or the values) if saved, else None."""
    dialog = FormDialog(parent, title, fields, values, submit, **kw)
    return dialog.result_value if dialog.exec() else None


def ref_options(api, key: str, label: str = "name", **params) -> Callable[[], list[tuple[str, Any]]]:
    return lambda: [(r.get(label) or r.get("name", ""), r["id"]) for r in api.lookup(key, **params)]


def dict_options(mapping: dict[str, str]) -> list[tuple[str, str]]:
    return [(label, key) for key, label in mapping.items()]


CONDITIONS = {"new": "New", "good": "Good", "fair": "Fair", "poor": "Poor", "damaged": "Damaged"}
