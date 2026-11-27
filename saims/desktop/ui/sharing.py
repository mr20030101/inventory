"""Sharing this computer's SAIMS on the local network, and confirming a shared server from another computer."""
from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout,
)

from saims import tls


class SharingController(Protocol):
    """Implemented by the desktop app, which owns the built-in server."""

    sharing: bool
    share_port: int

    def set_sharing(self, on: bool, port: int) -> None: ...

    def security_code(self) -> str: ...


def _code_label(code: str) -> QLabel:
    label = QLabel(code)
    font = QFont("monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(18)
    font.setBold(True)
    label.setFont(font)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


class ShareDialog(QDialog):
    """Turn network sharing on or off and show the address and security code other computers need."""

    def __init__(self, controller: SharingController, demo_data: bool, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Share on the local network")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(_hint("Other computers on this network (staff room, office, library) can then sign in "
                               "to SAIMS on this computer and work with the same data at the same time."))
        self.enable = QCheckBox("Share SAIMS on this computer with the local network")
        self.enable.setChecked(controller.sharing)
        layout.addWidget(self.enable)
        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port"))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(controller.share_port)
        port_row.addWidget(self.port)
        port_row.addWidget(_hint("Change only if another program already uses it."), 1)
        layout.addLayout(port_row)

        self.details = QFrame()
        self.details.setObjectName("Card")
        dl = QVBoxLayout(self.details)
        dl.setContentsMargins(16, 14, 16, 14)
        heading = QLabel("On the other computers")
        heading.setObjectName("CardTitle")
        dl.addWidget(heading)
        dl.addWidget(_hint("Open SAIMS, choose <b>School server…</b> on the sign-in screen and enter:"))
        self.address = _code_label("")
        self.address.setStyleSheet("font-size: 13pt;")
        addr_row = QHBoxLayout()
        addr_row.addWidget(self.address, 1)
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.address.text()))
        addr_row.addWidget(copy)
        dl.addLayout(addr_row)
        self.others = _hint("")
        dl.addWidget(self.others)
        dl.addSpacing(6)
        dl.addWidget(_hint("The first time, SAIMS shows a security code. Check that it matches this one before "
                           "accepting; it proves they reached this computer and not an impostor:"))
        self.code = _code_label("")
        dl.addWidget(self.code)
        layout.addWidget(self.details)

        notes = ["Keep this computer switched on, awake and with SAIMS open while others use it.",
                 "If the other computers cannot connect, allow SAIMS through this computer's firewall "
                 "(Windows asks the first time; on Linux open the port, e.g. "
                 "<code>sudo firewall-cmd --add-port=PORT/tcp</code>).",
                 "Back up the data folder regularly: everyone's work is stored on this computer."]
        if demo_data:
            notes.insert(0, "<b>This is demo data: every demo account uses the password demo1234, so anyone on "
                            "the network can sign in with it.</b> Change the passwords before sharing real data.")
        self._notes = "<ul style='margin-left:-20px'>" + "".join(f"<li>{n}</li>" for n in notes) + "</ul>"
        self.notes = _hint("")
        layout.addWidget(self.notes)

        self.error = QLabel()
        self.error.setObjectName("FormError")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        apply_btn = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._show_state()

    def _show_state(self) -> None:
        on = self.controller.sharing
        self.details.setVisible(on)
        if on:
            port = self.controller.share_port
            addresses = tls.lan_addresses()
            self.address.setText(f"https://{addresses[0]}:{port}" if addresses else f"https://<this computer>:{port}")
            others = ", ".join(f"https://{a}:{port}" for a in addresses[1:])
            self.others.setText(f"If that does not work, try: {others}" if others else "")
            self.others.setVisible(bool(others))
            self.code.setText(self.controller.security_code())
        self.notes.setText(self._notes.replace("PORT", str(self.port.value())))
        self.adjustSize()

    def _apply(self) -> None:
        self.error.hide()
        try:
            self.controller.set_sharing(self.enable.isChecked(), self.port.value())
        except Exception as exc:  # noqa: BLE001 - port in use, permission denied…
            self.error.setText(str(exc))
            self.error.show()
        self._show_state()


class TrustDialog(QDialog):
    """First connection to a shared SAIMS: confirm its security code matches the one shown on that computer."""

    def __init__(self, address: str, code: str, changed: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm the SAIMS server")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        if changed:
            warn = QLabel("The security code of this server has <b>changed</b> since you last connected. This "
                          "happens if SAIMS was reinstalled there, but it can also mean someone is pretending to "
                          "be the server. Only continue if the code matches the one on the server's screen.")
            warn.setObjectName("FormError")
            warn.setWordWrap(True)
            layout.addWidget(warn)
        layout.addWidget(_hint(f"You are connecting to <b>{address}</b> for the first time." if not changed else
                               f"Server: <b>{address}</b>"))
        layout.addWidget(_hint("On the computer that shares SAIMS, open the user menu ▸ <b>Share on the local "
                               "network…</b> and compare its security code with this one:"))
        layout.addWidget(_code_label(code))
        layout.addWidget(_hint("If they match, this computer remembers the server and will refuse any other. "
                               "If they do not match, cancel and ask your administrator."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.Cancel)
        yes = buttons.button(QDialogButtonBox.StandardButton.Yes)
        yes.setText("The codes match — connect")
        yes.setObjectName("Primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
