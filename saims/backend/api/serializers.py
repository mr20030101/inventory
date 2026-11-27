"""Model → JSON-ready dicts. Decimals are sent as strings so no precision is lost."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saims.backend.models import (
    Asset, AssetAssignment, AssetEvent, AuditLog, BorrowRequest, Building, Category, Department, Employee, Role,
    Room, StockBalance, StockItem, StockMovement, StorageLocation, Supplier, User,
)
from saims.backend.services.assets import CONDITIONS, FUNDING_SOURCES, STATUSES
from saims.backend.services.borrowing import STATUS_LABELS, is_overdue
from saims.backend.services.stock import IN_TYPES, MOVEMENT_LABELS


def _s(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _m(value: Any) -> str:
    """Money: always two decimal places."""
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def user(u: User) -> dict[str, Any]:
    return {"id": _s(u.id), "username": u.username, "email": u.email or "", "full_name": u.full_name,
            "is_active": u.is_active, "last_login_at": _s(u.last_login_at), "employee_id": _s(u.employee_id),
            "roles": [r.code for r in u.roles], "role_names": [r.name for r in u.roles]}


def role(r: Role) -> dict[str, Any]:
    return {"id": _s(r.id), "code": r.code, "name": r.name, "description": r.description,
            "permissions": sorted(p.code for p in r.permissions)}


def reference(obj: Any) -> dict[str, Any]:
    """Departments, buildings, rooms, storage locations, employees, suppliers, categories."""
    base = {"id": _s(obj.id), "is_active": obj.is_active}
    if isinstance(obj, (Department, Building)):
        base.update(code=obj.code, name=obj.name)
    elif isinstance(obj, Room):
        base.update(code=obj.code, name=obj.name, building_id=_s(obj.building_id), building=obj.building.name,
                    floor=obj.floor, kind=obj.kind, department_id=_s(obj.department_id),
                    department=obj.department.name if obj.department else "",
                    label=f"{obj.name} ({obj.building.name})")
    elif isinstance(obj, StorageLocation):
        base.update(code=obj.code, name=obj.name, room_id=_s(obj.room_id), room=obj.room.name if obj.room else "")
    elif isinstance(obj, Employee):
        base.update(employee_no=obj.employee_no, full_name=obj.full_name, name=obj.full_name, position=obj.position,
                    department_id=_s(obj.department_id), department=obj.department.name if obj.department else "",
                    email=obj.email, phone=obj.phone)
    elif isinstance(obj, Supplier):
        base.update(name=obj.name, contact_name=obj.contact_name, email=obj.email, phone=obj.phone,
                    address=obj.address)
    elif isinstance(obj, Category):
        base.update(kind=obj.kind, name=obj.name, parent_id=_s(obj.parent_id),
                    parent=obj.parent.name if obj.parent else "", default_unit=obj.default_unit,
                    label=f"{obj.parent.name} › {obj.name}" if obj.parent else obj.name)
    return base


def asset(a: Asset, custodian: str = "") -> dict[str, Any]:
    return {
        "id": _s(a.id), "asset_code": a.asset_code, "name": a.name, "description": a.description,
        "category_id": _s(a.category_id), "category": a.category.name if a.category else "",
        "brand": a.brand, "model": a.model, "serial_number": a.serial_number or "",
        "acquisition_date": _s(a.acquisition_date), "acquisition_cost": _m(a.acquisition_cost),
        "funding_source": a.funding_source, "funding_label": FUNDING_SOURCES.get(a.funding_source, ""),
        "donor": a.donor, "supplier_id": _s(a.supplier_id), "supplier": a.supplier.name if a.supplier else "",
        "purchase_reference": a.purchase_reference, "warranty_expiry": _s(a.warranty_expiry),
        "condition": a.condition, "condition_label": CONDITIONS.get(a.condition, a.condition),
        "status": a.status, "status_label": STATUSES.get(a.status, a.status),
        "room_id": _s(a.room_id), "room": a.room.name if a.room else "",
        "building": a.room.building.name if a.room else "",
        "department_id": _s(a.department_id), "department": a.department.name if a.department else "",
        "custodian": custodian, "archived": a.archived_at is not None,
        "created_at": _s(a.created_at), "updated_at": _s(a.updated_at),
    }


def assignment(x: AssetAssignment) -> dict[str, Any]:
    return {"id": _s(x.id), "asset_id": _s(x.asset_id), "asset_code": x.asset.asset_code, "asset_name": x.asset.name,
            "employee_id": _s(x.employee_id), "employee": x.employee.full_name if x.employee else "",
            "department": x.department.name if x.department else "", "room": x.room.name if x.room else "",
            "assigned_at": _s(x.assigned_at), "condition_on_release": x.condition_on_release,
            "acknowledged": x.acknowledged, "returned_at": _s(x.returned_at),
            "condition_on_return": x.condition_on_return or ""}


def event(e: AssetEvent) -> dict[str, Any]:
    return {"id": _s(e.id), "event_type": e.event_type, "label": e.event_type.replace("_", " ").capitalize(),
            "from_status": e.from_status, "to_status": e.to_status, "description": e.description,
            "reason": e.reason, "user": e.user.full_name, "created_at": _s(e.created_at)}


def stock_item(row: dict[str, Any]) -> dict[str, Any]:
    i: StockItem = row["item"]
    return {"id": _s(i.id), "item_code": i.item_code, "name": i.name, "description": i.description,
            "category_id": _s(i.category_id), "category": i.category.name if i.category else "",
            "unit_of_measure": i.unit_of_measure, "minimum_stock": _s(i.minimum_stock),
            "reorder_level": _s(i.reorder_level), "average_cost": _s(i.average_cost), "track_expiry": i.track_expiry,
            "is_active": i.is_active, "on_hand": _s(row["on_hand"]), "value": _m(row["value"]),
            "stock_state": row["stock_state"]}


def balance(b: StockBalance) -> dict[str, Any]:
    return {"id": _s(b.id), "item_id": _s(b.item_id), "item_code": b.item.item_code, "item": b.item.name,
            "unit": b.item.unit_of_measure, "location_id": _s(b.location_id), "location": b.location.name,
            "batch_id": _s(b.batch_id), "batch_no": b.batch.batch_no if b.batch else "",
            "expiry_date": _s(b.batch.expiry_date) if b.batch else None, "quantity": _s(b.quantity)}


def movement(m: StockMovement) -> dict[str, Any]:
    sign = 1 if m.movement_type in IN_TYPES else -1
    return {"id": _s(m.id), "item_id": _s(m.item_id), "item_code": m.item.item_code, "item": m.item.name,
            "unit": m.item.unit_of_measure, "location": m.location.name, "movement_type": m.movement_type,
            "type_label": MOVEMENT_LABELS[m.movement_type], "quantity": _s(m.quantity),
            "signed_quantity": _s(m.quantity * sign), "unit_cost": _s(m.unit_cost),
            "batch_no": m.batch.batch_no if m.batch else "", "department": m.department.name if m.department else "",
            "reference": m.reference, "reason": m.reason, "user": m.user.full_name, "created_at": _s(m.created_at)}


def borrow(r: BorrowRequest) -> dict[str, Any]:
    return {"id": _s(r.id), "request_no": r.request_no, "asset_id": _s(r.asset_id), "asset_code": r.asset.asset_code,
            "asset_name": r.asset.name, "borrower_id": _s(r.borrower_id), "borrower": r.borrower.full_name,
            "purpose": r.purpose, "date_needed": _s(r.date_needed), "expected_return": _s(r.expected_return),
            "status": r.status, "status_label": STATUS_LABELS[r.status], "overdue": is_overdue(r),
            "decision_note": r.decision_note, "released_at": _s(r.released_at), "returned_at": _s(r.returned_at),
            "condition_out": r.condition_out or "", "condition_in": r.condition_in or "",
            "created_at": _s(r.created_at)}


def audit_entry(a: AuditLog) -> dict[str, Any]:
    return {"id": _s(a.id), "created_at": _s(a.created_at), "username": a.username, "action": a.action,
            "entity_type": a.entity_type, "entity_id": a.entity_id, "summary": a.summary, "changes": a.changes,
            "success": a.success}
