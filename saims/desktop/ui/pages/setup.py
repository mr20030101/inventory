"""School structure and reference lists: departments, buildings, rooms, storage, categories, suppliers."""
from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout

from saims.desktop.ui.forms import Field, ref_options
from saims.desktop.ui.pages.base import Page, RecordList
from saims.desktop.ui.widgets import Column

ROOM_KINDS = ["classroom", "office", "laboratory", "library", "storeroom", "workshop", "hall", "other"]


class SetupPage(Page):
    title = "School Setup"

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        a = api
        lists = [
            ("Departments", "departments.view", RecordList(a, "departments", "Department", [
                Column("Code", "code"), Column("Name", "name")],
                lambda: [Field("code", "Code", required=True), Field("name", "Name", required=True)],
                "departments.manage")),
            ("Buildings", "locations.view", RecordList(a, "buildings", "Building", [
                Column("Code", "code"), Column("Name", "name")],
                lambda: [Field("code", "Code", required=True), Field("name", "Name", required=True)],
                "locations.manage")),
            ("Rooms", "locations.view", RecordList(a, "rooms", "Room", [
                Column("Code", "code"), Column("Name", "name"), Column("Building", "building"),
                Column("Floor", "floor"), Column("Type", "kind", str.capitalize), Column("Department", "department")],
                lambda: [Field("code", "Code", required=True), Field("name", "Name", required=True),
                         Field("building_id", "Building", "choice", required=True, allow_empty=False,
                               options=ref_options(a, "buildings")),
                         Field("floor", "Floor"),
                         Field("kind", "Type", "choice", allow_empty=False,
                               options=[(k.capitalize(), k) for k in ROOM_KINDS]),
                         Field("department_id", "Department", "choice", options=ref_options(a, "departments"))],
                "locations.manage")),
            ("Storage locations", "locations.view", RecordList(a, "storage-locations", "Storage location", [
                Column("Code", "code"), Column("Name", "name"), Column("Room", "room")],
                lambda: [Field("code", "Code", required=True), Field("name", "Name", required=True),
                         Field("room_id", "Room", "choice", options=ref_options(a, "rooms", "label"))],
                "locations.manage")),
            ("Asset categories", "assets.view", RecordList(a, "categories", "Category", [
                Column("Name", "name"), Column("Parent", "parent")],
                lambda: [Field("name", "Name", required=True),
                         Field("parent_id", "Parent category", "choice",
                               options=ref_options(a, "categories", kind="asset"))],
                "categories.manage", params={"kind": "asset"})),
            ("Consumable categories", "inventory.view", RecordList(a, "categories", "Category", [
                Column("Name", "name"), Column("Default unit", "default_unit")],
                lambda: [Field("name", "Name", required=True), Field("default_unit", "Default unit")],
                "categories.manage", params={"kind": "consumable"})),
            ("Suppliers", "suppliers.view", RecordList(a, "suppliers", "Supplier", [
                Column("Name", "name"), Column("Contact", "contact_name"), Column("Email", "email"),
                Column("Phone", "phone")],
                lambda: [Field("name", "Name", required=True), Field("contact_name", "Contact person"),
                         Field("email", "Email"), Field("phone", "Phone"), Field("address", "Address", "multiline")],
                "suppliers.manage")),
        ]
        for title, perm, page in lists:
            if api.can(perm):
                self.tabs.addTab(page, title)
        self.tabs.currentChanged.connect(lambda _: self.refresh())

    def refresh(self) -> None:
        page = self.tabs.currentWidget()
        if page:
            page.refresh()
