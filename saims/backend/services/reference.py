"""Generic create / update / archive for reference data (departments, rooms, employees…).

Records are archived (is_active = false), never physically deleted, so history keeps its links.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from saims.backend import audit
from saims.backend.errors import Conflict, DomainError
from saims.backend.models import (
    AssetAssignment, Building, Category, Department, Employee, Room, StorageLocation, Supplier, User,
)
from saims.backend.services.common import get_or_404, optional, required


@dataclass
class Entity:
    model: type
    name: str               # human name, e.g. "Room"
    entity_type: str        # audit entity type
    fields: dict[str, str]  # field → kind: text | required | fk:<Model> | bool | choice:<a,b>
    unique: list[str] = field(default_factory=list)
    order_by: str = "name"
    can_archive: Callable[[Session, Any], str | None] | None = None  # returns a reason it cannot


def _employee_can_archive(db: Session, emp: Employee) -> str | None:
    active = db.scalar(select(AssetAssignment.id).where(AssetAssignment.employee_id == emp.id,
                                                        AssetAssignment.returned_at.is_(None)))
    return f"{emp.full_name} still has assigned assets. Return or reassign them first." if active else None


ENTITIES: dict[str, Entity] = {
    "departments": Entity(Department, "Department", "department",
                          {"code": "required", "name": "required"}, ["code"]),
    "buildings": Entity(Building, "Building", "building", {"code": "required", "name": "required"}, ["code"]),
    "rooms": Entity(Room, "Room", "room", {
        "code": "required", "name": "required", "building_id": "fk:Building", "floor": "text",
        "kind": "choice:classroom,office,laboratory,library,storeroom,workshop,hall,other",
        "department_id": "fk:Department"}, ["code"], "code"),
    "storage-locations": Entity(StorageLocation, "Storage location", "storage_location",
                                {"code": "required", "name": "required", "room_id": "fk:Room"}, ["code"]),
    "employees": Entity(Employee, "Employee", "employee", {
        "employee_no": "required", "full_name": "required", "position": "text", "department_id": "fk:Department",
        "email": "text", "phone": "text"}, ["employee_no"], "full_name", _employee_can_archive),
    "suppliers": Entity(Supplier, "Supplier", "supplier", {
        "name": "required", "contact_name": "text", "email": "text", "phone": "text", "address": "text"}, ["name"]),
    "categories": Entity(Category, "Category", "category", {
        "kind": "choice:asset,consumable", "name": "required", "parent_id": "fk:Category", "default_unit": "text"}),
}
_MODELS = {"Building": Building, "Department": Department, "Room": Room, "Category": Category}


def _clean(db: Session, ent: Entity, data: dict[str, Any], partial: bool) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name, kind in ent.fields.items():
        if partial and name not in data:
            continue
        value = data.get(name)
        label = name.replace("_id", "").replace("_", " ").capitalize()
        if kind == "required":
            values[name] = required(value, label)
        elif kind == "text":
            values[name] = str(value or "").strip()
        elif kind.startswith("fk:"):
            target = optional(db, _MODELS[kind[3:]], value, label)
            if name == "building_id" and target is None:
                raise DomainError("Building is required.")
            values[name] = target.id if target else None
        elif kind.startswith("choice:"):
            options = kind[7:].split(",")
            value = value or options[0]
            if value not in options:
                raise DomainError(f"{label} must be one of: {', '.join(options)}.")
            values[name] = value
    return values


def list_records(db: Session, key: str, include_inactive: bool = False, kind: str | None = None) -> list:
    ent = ENTITIES[key]
    stmt = select(ent.model)
    if not include_inactive:
        stmt = stmt.where(ent.model.is_active.is_(True))
    if kind and key == "categories":
        stmt = stmt.where(Category.kind == kind)
    return list(db.scalars(stmt.order_by(getattr(ent.model, ent.order_by))).unique())


def _check_unique(db: Session, ent: Entity, values: dict[str, Any], current_id=None) -> None:
    for name in ent.unique:
        if name in values:
            clash = db.scalar(select(ent.model).where(getattr(ent.model, name) == values[name]))
            if clash and clash.id != current_id:
                raise Conflict(f'{ent.name} with {name.replace("_", " ")} "{values[name]}" already exists.',
                               "duplicate")


def create(db: Session, user: User, key: str, data: dict[str, Any]):
    ent = ENTITIES[key]
    values = _clean(db, ent, data, partial=False)
    _check_unique(db, ent, values)
    obj = ent.model(**values)
    db.add(obj)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflict(f"That {ent.name.lower()} already exists.", "duplicate") from None
    audit.record(db, user, f"{ent.entity_type}.create", ent.entity_type, obj.id,
                 f"Created {ent.name.lower()} {values.get('name') or values.get('full_name') or ''}".strip(),
                 {k: str(v) for k, v in values.items()})
    db.commit()
    return obj


def update(db: Session, user: User, key: str, obj_id, data: dict[str, Any]):
    ent = ENTITIES[key]
    obj = get_or_404(db, ent.model, obj_id, ent.name)
    values = _clean(db, ent, data, partial=True)
    if key == "categories" and values.get("parent_id") == obj.id:
        raise DomainError("A category cannot be its own parent.")
    _check_unique(db, ent, values, obj.id)
    before = audit.snapshot(obj, list(values))
    for name, value in values.items():
        setattr(obj, name, value)
    changes = audit.diff(before, audit.snapshot(obj, list(values)))
    if changes:
        audit.record(db, user, f"{ent.entity_type}.update", ent.entity_type, obj.id, f"Updated {ent.name.lower()}",
                     changes)
    db.commit()
    return obj


def set_active(db: Session, user: User, key: str, obj_id, active: bool):
    ent = ENTITIES[key]
    obj = get_or_404(db, ent.model, obj_id, ent.name)
    if not active and ent.can_archive and (problem := ent.can_archive(db, obj)):
        raise Conflict(problem, "in_use")
    obj.is_active = active
    audit.record(db, user, f"{ent.entity_type}.{'restore' if active else 'archive'}", ent.entity_type, obj.id,
                 f"{'Restored' if active else 'Archived'} {ent.name.lower()}")
    db.commit()
    return obj
