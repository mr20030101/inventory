"""Asset register and lifecycle (specification sections 4.2 and 4.7).

Status only changes through the actions below, each of which checks the
current status, writes an asset event and an audit entry in one transaction.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from saims.backend import audit
from saims.backend.errors import Conflict, DomainError
from saims.backend.models import (
    Asset, AssetAssignment, AssetEvent, BorrowRequest, Category, Department, Employee, Room, Supplier, User,
)
from saims.backend.services.common import (
    as_list, as_uuid, as_uuids, commit, get_or_404, money, next_number, now, optional, required, setting,
)

STATUSES = {
    "available": "Available", "assigned": "Assigned", "borrowed": "Borrowed",
    "under_maintenance": "Under maintenance", "damaged": "Damaged", "missing": "Missing",
    "retired": "Retired", "disposed": "Disposed",
}
CONDITIONS = {"new": "New", "good": "Good", "fair": "Fair", "poor": "Poor", "damaged": "Damaged"}
FUNDING_SOURCES = {
    "school_funds": "School funds", "government": "Government allocation", "grant": "Grant",
    "donation": "Donation", "other": "Other",
}

_EDITABLE = ["name", "description", "category_id", "brand", "model", "serial_number", "acquisition_date",
             "acquisition_cost", "funding_source", "donor", "supplier_id", "purchase_reference",
             "warranty_expiry", "department_id"]


def _require_status(asset: Asset, allowed: set[str], action: str) -> None:
    if asset.archived_at is not None:
        raise DomainError(f"{asset.asset_code} is archived.")
    if asset.status not in allowed:
        raise Conflict(f"Cannot {action}: {asset.asset_code} is {STATUSES[asset.status].lower()}.",
                       "invalid_status")


def _event(db: Session, asset: Asset, user: User, event_type: str, description: str,
           old_status: str | None = None, reason: str = "") -> None:
    db.add(AssetEvent(asset_id=asset.id, event_type=event_type, from_status=old_status,
                      to_status=asset.status if old_status else None, description=description,
                      reason=reason, performed_by=user.id))


def _clean(db: Session, data: dict[str, Any], current: Asset | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if current is None or "name" in data:
        values["name"] = required(data.get("name"), "Asset name")
    for key in ("description", "brand", "model", "donor", "purchase_reference"):
        if key in data:
            values[key] = str(data.get(key) or "").strip()
    if "serial_number" in data:
        serial = str(data.get("serial_number") or "").strip() or None
        if serial:
            clash = db.scalar(select(Asset).where(Asset.serial_number == serial))
            if clash and (current is None or clash.id != current.id):
                raise Conflict(f"Serial number {serial} is already registered to {clash.asset_code}.",
                               "duplicate_serial")
        values["serial_number"] = serial
    if "category_id" in data:
        cat = optional(db, Category, data.get("category_id"), "Category")
        if cat and cat.kind != "asset":
            raise DomainError("Choose an asset category.")
        values["category_id"] = cat.id if cat else None
    if "supplier_id" in data:
        values["supplier_id"] = s.id if (s := optional(db, Supplier, data.get("supplier_id"), "Supplier")) else None
    if "department_id" in data:
        values["department_id"] = d.id if (d := optional(db, Department, data.get("department_id"),
                                                         "Department")) else None
    for key in ("acquisition_date", "warranty_expiry"):
        if key in data:
            values[key] = _date(data.get(key), key.replace("_", " ").capitalize())
    if "acquisition_cost" in data:
        values["acquisition_cost"] = money(data.get("acquisition_cost"), "Acquisition cost")
    if "funding_source" in data:
        source = data.get("funding_source") or "school_funds"
        if source not in FUNDING_SOURCES:
            raise DomainError("Unknown funding source.")
        values["funding_source"] = source
    return values


def _date(value: Any, label: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise DomainError(f"{label} must be a date (YYYY-MM-DD).") from None


def generate_code(db: Session) -> str:
    prefix = setting(db, "asset_code_prefix", "AST")
    year = date.today().year
    while True:
        code = f"{prefix}-{year}-{next_number(db, f'asset-{year}'):05d}"
        if not db.scalar(select(Asset.id).where(Asset.asset_code == code)):
            return code


def register(db: Session, user: User, data: dict[str, Any]) -> Asset:
    values = _clean(db, data)
    code = str(data.get("asset_code") or "").strip() or generate_code(db)
    if db.scalar(select(Asset.id).where(Asset.asset_code == code)):
        raise Conflict(f"Asset code {code} already exists.", "duplicate_code")
    condition = data.get("condition") or "good"
    if condition not in CONDITIONS:
        raise DomainError("Unknown condition.")
    room = optional(db, Room, data.get("room_id"), "Room")
    asset = Asset(asset_code=code, condition=condition, status="available", room_id=room.id if room else None,
                  **values)
    if room and not asset.department_id:
        asset.department_id = room.department_id
    db.add(asset)
    db.flush()
    _event(db, asset, user, "registered", f"Registered in {room.name if room else 'no location'}"
           f", condition {CONDITIONS[condition].lower()}")
    audit.record(db, user, "asset.create", "asset", asset.id, f"Registered {code} {asset.name}",
                 audit.snapshot(asset, ["asset_code", "name", "serial_number", "acquisition_cost", "status"]))
    commit(db)
    return asset


def update(db: Session, user: User, asset_id, data: dict[str, Any]) -> Asset:
    asset = get_or_404(db, Asset, asset_id, "Asset")
    if asset.status == "disposed":
        raise Conflict("Disposed assets cannot be edited.", "invalid_status")
    data = {k: v for k, v in data.items() if k in _EDITABLE}
    before = audit.snapshot(asset, list(data))
    for key, value in _clean(db, data, asset).items():
        setattr(asset, key, value)
    changes = audit.diff(before, audit.snapshot(asset, list(data)))
    if changes:
        _event(db, asset, user, "updated", "Details updated: " + ", ".join(changes))
        audit.record(db, user, "asset.update", "asset", asset.id, f"Updated {asset.asset_code}", changes)
    commit(db)
    return asset


def set_condition(db: Session, user: User, asset_id, condition: str, note: str = "") -> Asset:
    asset = get_or_404(db, Asset, asset_id, "Asset")
    _require_status(asset, set(STATUSES) - {"disposed"}, "change the condition")
    if condition not in CONDITIONS:
        raise DomainError("Unknown condition.")
    old = asset.condition
    asset.condition = condition
    _event(db, asset, user, "condition_changed", f"Condition {old} → {condition}", reason=note)
    audit.record(db, user, "asset.condition", "asset", asset.id, f"{asset.asset_code} condition {old} → {condition}")
    commit(db)
    return asset


def active_assignment(db: Session, asset_id) -> AssetAssignment | None:
    return db.scalar(select(AssetAssignment).where(AssetAssignment.asset_id == asset_id,
                                                   AssetAssignment.returned_at.is_(None)))


def assign(db: Session, user: User, asset_id, data: dict[str, Any]) -> AssetAssignment:
    asset = get_or_404(db, Asset, asset_id, "Asset")
    _require_status(asset, {"available"}, "assign")
    employee = optional(db, Employee, data.get("employee_id"), "Employee")
    department = optional(db, Department, data.get("department_id"), "Department")
    room = optional(db, Room, data.get("room_id"), "Room")
    if not (employee or department or room):
        raise DomainError("Choose an employee, department or room to assign the asset to.")
    if employee and not employee.is_active:
        raise DomainError(f"{employee.full_name} is not an active employee.")
    condition = data.get("condition") or asset.condition
    if condition not in CONDITIONS:
        raise DomainError("Unknown condition.")
    assignment = AssetAssignment(
        asset_id=asset.id, employee_id=employee.id if employee else None,
        department_id=department.id if department else (employee.department_id if employee else asset.department_id),
        room_id=room.id if room else None, assigned_by=user.id, condition_on_release=condition,
        acknowledged=bool(data.get("acknowledged")), notes=str(data.get("notes") or ""),
    )
    db.add(assignment)
    old = asset.status
    asset.status, asset.condition = "assigned", condition
    if room:
        asset.room_id = room.id
    if assignment.department_id:
        asset.department_id = assignment.department_id
    to = employee.full_name if employee else (department.name if department else room.name)
    _event(db, asset, user, "assigned", f"Assigned to {to}", old, str(data.get("notes") or ""))
    audit.record(db, user, "asset.assign", "asset", asset.id, f"Assigned {asset.asset_code} to {to}")
    commit(db)
    return assignment


def return_assignment(db: Session, user: User, asset_id, condition: str, notes: str = "") -> Asset:
    asset = get_or_404(db, Asset, asset_id, "Asset")
    _require_status(asset, {"assigned"}, "return")
    assignment = active_assignment(db, asset.id)
    if condition not in CONDITIONS:
        raise DomainError("Unknown condition.")
    if assignment:
        assignment.returned_at, assignment.returned_by = now(), user.id
        assignment.condition_on_return = condition
    old = asset.status
    asset.condition = condition
    asset.status = "damaged" if condition == "damaged" else "available"
    who = assignment.employee.full_name if assignment and assignment.employee else "assignee"
    _event(db, asset, user, "returned", f"Returned by {who}, condition {condition}", old, notes)
    audit.record(db, user, "asset.return", "asset", asset.id, f"{asset.asset_code} returned by {who}")
    commit(db)
    return asset


def transfer(db: Session, user: User, asset_id, data: dict[str, Any]) -> Asset:
    asset = get_or_404(db, Asset, asset_id, "Asset")
    _require_status(asset, {"available", "assigned", "damaged"}, "transfer")
    room = optional(db, Room, data.get("room_id"), "Room")
    department = optional(db, Department, data.get("department_id"), "Department")
    if not room and not department:
        raise DomainError("Choose the destination room or department.")
    reason = required(data.get("reason"), "Transfer reason")
    parts = []
    if room and room.id != asset.room_id:
        parts.append(f"room {asset.room.name if asset.room else '—'} → {room.name}")
        asset.room_id = room.id
        if not department and room.department_id:
            department = room.department
    if department and department.id != asset.department_id:
        parts.append(f"department {asset.department.name if asset.department else '—'} → {department.name}")
        asset.department_id = department.id
    if not parts:
        raise DomainError("The asset is already at that location.")
    assignment = active_assignment(db, asset.id)
    if assignment:
        if room:
            assignment.room_id = room.id
        if department:
            assignment.department_id = department.id
    _event(db, asset, user, "transferred", "Transferred: " + "; ".join(parts), reason=reason)
    audit.record(db, user, "asset.transfer", "asset", asset.id, f"{asset.asset_code} " + "; ".join(parts))
    commit(db)
    return asset


# Each lifecycle action: (allowed from, new status, event type, audit action, needs reason)
_ACTIONS: dict[str, tuple[set[str], str, str, bool]] = {
    "send_to_maintenance": ({"available", "damaged"}, "under_maintenance", "maintenance_started", False),
    "complete_maintenance": ({"under_maintenance"}, "available", "maintenance_completed", False),
    "mark_missing": ({"available", "assigned", "borrowed", "damaged"}, "missing", "marked_missing", True),
    "recover": ({"missing"}, "available", "recovered", False),
    "mark_damaged": ({"available", "assigned"}, "damaged", "marked_damaged", True),
    "retire": ({"available", "damaged"}, "retired", "retired", True),
    "dispose": ({"retired"}, "disposed", "disposed", True),
}
ACTION_LABELS = {
    "send_to_maintenance": "send to maintenance", "complete_maintenance": "complete maintenance",
    "mark_missing": "mark missing", "recover": "record recovery", "mark_damaged": "mark damaged",
    "retire": "retire", "dispose": "dispose of",
}


def lifecycle(db: Session, user: User, asset_id, action: str, reason: str = "", condition: str | None = None,
              event_date: date | None = None) -> Asset:
    if action not in _ACTIONS:
        raise DomainError("Unknown action.")
    allowed, new_status, event_type, needs_reason = _ACTIONS[action]
    asset = get_or_404(db, Asset, asset_id, "Asset")
    _require_status(asset, allowed, ACTION_LABELS[action])
    if needs_reason:
        required(reason, "Reason")
    if action == "complete_maintenance" and condition == "damaged":
        new_status = "damaged"
    if condition:
        if condition not in CONDITIONS:
            raise DomainError("Unknown condition.")
        asset.condition = condition
    elif action == "mark_damaged":
        asset.condition = "damaged"
    # Missing, damaged or borrowed-and-lost assets close any open assignment, keeping the record.
    if new_status in {"missing", "damaged"}:
        assignment = active_assignment(db, asset.id)
        if assignment:
            assignment.returned_at, assignment.returned_by = now(), user.id
            assignment.condition_on_return = new_status
    if asset.status == "borrowed" and new_status == "missing":
        loan = db.scalar(select(BorrowRequest).where(BorrowRequest.asset_id == asset.id,
                                                     BorrowRequest.status == "released"))
        if loan:
            loan.status, loan.returned_at, loan.received_by = "lost", now(), user.id
            loan.condition_in, loan.return_note = "missing", reason
    old = asset.status
    asset.status = new_status
    when = f" on {event_date.isoformat()}" if event_date else ""
    _event(db, asset, user, event_type, f"{STATUSES[old]} → {STATUSES[new_status]}{when}", old, reason)
    audit.record(db, user, f"asset.{action}", "asset", asset.id,
                 f"{asset.asset_code}: {STATUSES[old]} → {STATUSES[new_status]}", {"reason": reason})
    commit(db)
    return asset


def archive(db: Session, user: User, asset_id, reason: str) -> Asset:
    """Hide a record registered in error. Assets are never physically deleted."""
    asset = get_or_404(db, Asset, asset_id, "Asset")
    required(reason, "Reason")
    if asset.status not in {"available", "retired", "disposed"}:
        raise Conflict("Only available, retired or disposed assets can be archived.", "invalid_status")
    asset.archived_at = now()
    _event(db, asset, user, "archived", "Record archived", reason=reason)
    audit.record(db, user, "asset.archive", "asset", asset.id, f"Archived {asset.asset_code}", {"reason": reason})
    commit(db)
    return asset


def search(db: Session, q: str = "", status=None, category_id=None, department_id=None,
           room_id=None, employee_id=None, include_archived: bool = False) -> list[Asset]:
    """Filters take one value or a list (any of them matches)."""
    stmt = select(Asset)
    if not include_archived:
        stmt = stmt.where(Asset.archived_at.is_(None))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Asset.asset_code.ilike(like), Asset.name.ilike(like), Asset.serial_number.ilike(like),
                              Asset.brand.ilike(like), Asset.model.ilike(like)))
    if statuses := as_list(status):
        stmt = stmt.where(Asset.status.in_(statuses))
    if ids := as_uuids(category_id, "category"):
        stmt = stmt.where(Asset.category_id.in_(ids))
    if ids := as_uuids(department_id, "department"):
        stmt = stmt.where(Asset.department_id.in_(ids))
    if ids := as_uuids(room_id, "room"):
        stmt = stmt.where(Asset.room_id.in_(ids))
    if employee_id:
        stmt = stmt.join(AssetAssignment, (AssetAssignment.asset_id == Asset.id)
                         & AssetAssignment.returned_at.is_(None)).where(AssetAssignment.employee_id == as_uuid(employee_id, "employee"))
    return list(db.scalars(stmt.order_by(Asset.asset_code)).unique())


def custodians(db: Session, asset_ids: list) -> dict:
    """Map asset id → employee name of the active assignment."""
    if not asset_ids:
        return {}
    rows = db.scalars(select(AssetAssignment).where(AssetAssignment.asset_id.in_(asset_ids),
                                                    AssetAssignment.returned_at.is_(None)))
    return {a.asset_id: (a.employee.full_name if a.employee else
                         a.department.name if a.department else a.room.name if a.room else "") for a in rows}


def history(db: Session, asset_id) -> list[AssetEvent]:
    return list(db.scalars(select(AssetEvent).where(AssetEvent.asset_id == asset_id)
                           .order_by(AssetEvent.created_at.desc())))


def counts_by_status(db: Session) -> dict[str, int]:
    rows = db.execute(select(Asset.status, func.count()).where(Asset.archived_at.is_(None)).group_by(Asset.status))
    return {status: n for status, n in rows}
