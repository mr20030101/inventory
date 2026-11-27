"""Consumable stock (specification sections 4.3 and 5.5).

`stock_movements` is the immutable source of truth. `stock_balances` is a cache
updated in the same transaction, and `reconcile()` checks the two agree.
Stock is valued at weighted average cost.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from saims.backend import audit
from saims.backend.errors import Conflict, DomainError
from saims.backend.models import (
    Category, Department, Employee, StockBalance, StockBatch, StockItem, StockMovement, StorageLocation, Supplier,
    User,
)
from saims.backend.services.common import (
    as_list, as_uuid, as_uuids, commit, get_or_404, money, next_number, optional, quantity, required, setting,
)

IN_TYPES = {"OPENING", "RECEIPT", "RETURN", "ADJUSTMENT_IN", "TRANSFER_IN"}
OUT_TYPES = {"ISSUE", "DAMAGE", "EXPIRY", "ADJUSTMENT_OUT", "TRANSFER_OUT"}
MOVEMENT_LABELS = {
    "OPENING": "Opening balance", "RECEIPT": "Receipt", "RETURN": "Return", "ADJUSTMENT_IN": "Adjustment (+)",
    "TRANSFER_IN": "Transfer in", "ISSUE": "Issue", "DAMAGE": "Damaged", "EXPIRY": "Expired",
    "ADJUSTMENT_OUT": "Adjustment (−)", "TRANSFER_OUT": "Transfer out",
}
# Permission needed for each movement type the API accepts directly.
MOVEMENT_PERMISSIONS = {
    "OPENING": "inventory.receive", "RECEIPT": "inventory.receive", "ISSUE": "inventory.issue",
    "RETURN": "inventory.return", "DAMAGE": "inventory.adjust", "EXPIRY": "inventory.adjust",
    "ADJUSTMENT_IN": "inventory.adjust", "ADJUSTMENT_OUT": "inventory.adjust",
}
REASON_REQUIRED = {"DAMAGE", "EXPIRY", "ADJUSTMENT_IN", "ADJUSTMENT_OUT"}
ZERO = Decimal("0")


# ------------------------------------------------------------------ items
def _clean_item(db: Session, data: dict[str, Any], current: StockItem | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if current is None or "name" in data:
        values["name"] = required(data.get("name"), "Item name")
    if "description" in data:
        values["description"] = str(data.get("description") or "").strip()
    if "unit_of_measure" in data or current is None:
        values["unit_of_measure"] = str(data.get("unit_of_measure") or "").strip() or "piece"
    for key, label in (("minimum_stock", "Minimum stock"), ("reorder_level", "Reorder level")):
        if key in data:
            values[key] = quantity(data.get(key) or 0, label, allow_zero=True)
    if "category_id" in data:
        cat = optional(db, Category, data.get("category_id"), "Category")
        if cat and cat.kind != "consumable":
            raise DomainError("Choose a consumable category.")
        values["category_id"] = cat.id if cat else None
    if "track_expiry" in data:
        values["track_expiry"] = bool(data.get("track_expiry"))
    return values


def create_item(db: Session, user: User, data: dict[str, Any]) -> StockItem:
    values = _clean_item(db, data)
    code = str(data.get("item_code") or "").strip()
    if not code:
        prefix = setting(db, "item_code_prefix", "ITM")
        code = f"{prefix}-{next_number(db, 'stock-item'):05d}"
    if db.scalar(select(StockItem.id).where(StockItem.item_code == code)):
        raise Conflict(f"Item code {code} already exists.", "duplicate_code")
    item = StockItem(item_code=code, **values)
    db.add(item)
    db.flush()
    audit.record(db, user, "stock_item.create", "stock_item", item.id, f"Created item {code} {item.name}")
    commit(db)
    return item


def update_item(db: Session, user: User, item_id, data: dict[str, Any]) -> StockItem:
    item = get_or_404(db, StockItem, item_id, "Item")
    fields = [k for k in ("name", "description", "unit_of_measure", "minimum_stock", "reorder_level",
                          "category_id", "track_expiry", "is_active") if k in data]
    before = audit.snapshot(item, fields)
    for key, value in _clean_item(db, data, item).items():
        setattr(item, key, value)
    if "is_active" in data:
        item.is_active = bool(data["is_active"])
    audit.record(db, user, "stock_item.update", "stock_item", item.id, f"Updated item {item.item_code}",
                 audit.diff(before, audit.snapshot(item, fields)))
    commit(db)
    return item


# ------------------------------------------------------------------ movements
def _balance(db: Session, item_id, location_id, batch_id) -> StockBalance:
    key = str(batch_id) if batch_id else ""
    row = db.execute(select(StockBalance).where(
        StockBalance.item_id == item_id, StockBalance.location_id == location_id, StockBalance.batch_key == key,
    ).with_for_update()).scalar_one_or_none()
    if row is None:
        row = StockBalance(item_id=item_id, location_id=location_id, batch_id=batch_id, batch_key=key, quantity=ZERO)
        db.add(row)
        db.flush()
    return row


def _allocate(db: Session, item: StockItem, location: StorageLocation, qty: Decimal,
              batch_id=None) -> list[tuple[StockBalance, Decimal]]:
    """Pick balances to take `qty` from: the given batch, else earliest expiry first. Rows are locked."""
    stmt = (select(StockBalance).outerjoin(StockBatch, StockBalance.batch_id == StockBatch.id)
            .where(StockBalance.item_id == item.id, StockBalance.location_id == location.id,
                   StockBalance.quantity > 0)
            .order_by(case((StockBatch.expiry_date.is_(None), 1), else_=0), StockBatch.expiry_date,
                      StockBatch.created_at)
            .with_for_update())
    if batch_id:
        stmt = stmt.where(StockBalance.batch_id == as_uuid(batch_id, "batch"))
    rows = list(db.scalars(stmt))
    available = sum((r.quantity for r in rows), ZERO)
    if available < qty:
        raise Conflict(
            f"Not enough {item.name} at {location.name}: {_fmt(available)} {item.unit_of_measure} available, "
            f"{_fmt(qty)} requested.", "insufficient_stock")
    picks, remaining = [], qty
    for row in rows:
        take = min(row.quantity, remaining)
        picks.append((row, take))
        remaining -= take
        if remaining == 0:
            break
    return picks


def _fmt(q: Decimal) -> str:
    return f"{q.normalize():f}"


def item_total(db: Session, item_id) -> Decimal:
    return db.scalar(select(func.coalesce(func.sum(StockBalance.quantity), 0))
                     .where(StockBalance.item_id == item_id)) or ZERO


def record(db: Session, user: User, data: dict[str, Any]) -> list[StockMovement]:
    """Record one stock movement (it may split across batches). Returns the movements written."""
    kind = str(data.get("movement_type") or "").upper()
    if kind not in MOVEMENT_PERMISSIONS:
        raise DomainError("Unknown movement type.")
    request_id = str(data.get("request_id") or "").strip() or None
    if request_id:
        existing = list(db.scalars(select(StockMovement).where(or_(
            StockMovement.request_id == request_id, StockMovement.request_id.like(f"{request_id}:%")))))
        if existing:
            return existing  # duplicate submission: already recorded
    item = get_or_404(db, StockItem, data.get("item_id"), "Item")
    if not item.is_active:
        raise DomainError(f"{item.name} is inactive.")
    location = get_or_404(db, StorageLocation, data.get("location_id"), "Storage location")
    qty = quantity(data.get("quantity"))
    reason = str(data.get("reason") or "").strip()
    if kind in REASON_REQUIRED and not reason:
        raise DomainError("A reason is required for damage, expiry and adjustments.")
    department = optional(db, Department, data.get("department_id"), "Department")
    employee = optional(db, Employee, data.get("employee_id"), "Employee")
    supplier = optional(db, Supplier, data.get("supplier_id"), "Supplier")
    if kind == "ISSUE" and not (department or employee):
        raise DomainError("Choose the department or employee receiving the stock.")
    common = dict(item_id=item.id, location_id=location.id, movement_type=kind, reference=str(
        data.get("reference") or "").strip(), reason=reason, performed_by=user.id,
        department_id=department.id if department else (employee.department_id if employee else None),
        employee_id=employee.id if employee else None, supplier_id=supplier.id if supplier else None)

    movements: list[StockMovement] = []
    if kind in IN_TYPES:
        if kind == "OPENING" and db.scalar(select(StockMovement.id).where(StockMovement.item_id == item.id)):
            raise Conflict("Opening balance is only allowed before any other movement of this item.",
                           "opening_not_allowed")
        batch = _batch_for_receipt(db, item, data, kind)
        unit_cost = item.average_cost
        if kind in {"OPENING", "RECEIPT"}:
            unit_cost = money(data.get("unit_cost"), "Unit cost")
            on_hand = item_total(db, item.id)
            total = on_hand + qty
            if total > 0:
                item.average_cost = ((on_hand * item.average_cost + qty * unit_cost) / total).quantize(Decimal("0.0001"))
        bal = _balance(db, item.id, location.id, batch.id if batch else None)
        bal.quantity += qty
        movements.append(StockMovement(batch_id=batch.id if batch else None, quantity=qty, unit_cost=unit_cost,
                                       **common))
    else:
        for bal, take in _allocate(db, item, location, qty, data.get("batch_id") or None):
            bal.quantity -= take
            movements.append(StockMovement(batch_id=bal.batch_id, quantity=take, unit_cost=item.average_cost,
                                           **common))
    for i, m in enumerate(movements):
        if request_id:
            m.request_id = request_id if i == 0 else f"{request_id}:{i}"
        db.add(m)
    db.flush()
    audit.record(db, user, f"stock.{kind.lower()}", "stock_item", item.id,
                 f"{MOVEMENT_LABELS[kind]} {_fmt(qty)} {item.unit_of_measure} {item.name} at {location.name}",
                 {"reference": common["reference"], "reason": reason} if (reason or common["reference"]) else None)
    commit(db)
    return movements


def _batch_for_receipt(db: Session, item: StockItem, data: dict[str, Any], kind: str) -> StockBatch | None:
    if data.get("batch_id"):
        return get_or_404(db, StockBatch, data["batch_id"], "Batch")
    batch_no = str(data.get("batch_no") or "").strip()
    expiry = data.get("expiry_date") or None
    if not batch_no:
        if item.track_expiry and kind in {"OPENING", "RECEIPT"}:
            raise DomainError(f"{item.name} tracks expiry dates: enter a batch number and expiry date.")
        return None
    batch = db.scalar(select(StockBatch).where(StockBatch.item_id == item.id, StockBatch.batch_no == batch_no))
    if batch is None:
        if item.track_expiry and not expiry:
            raise DomainError("Enter the batch expiry date.")
        try:
            expiry_date = date.fromisoformat(str(expiry)) if expiry else None
        except ValueError:
            raise DomainError("Expiry date must be a date (YYYY-MM-DD).") from None
        batch = StockBatch(item_id=item.id, batch_no=batch_no, expiry_date=expiry_date)
        db.add(batch)
        db.flush()
    return batch


def transfer(db: Session, user: User, data: dict[str, Any]) -> uuid.UUID:
    """Move stock between storage locations. Both sides are written in one transaction."""
    item = get_or_404(db, StockItem, data.get("item_id"), "Item")
    source = get_or_404(db, StorageLocation, data.get("from_location_id"), "Source location")
    target = get_or_404(db, StorageLocation, data.get("to_location_id"), "Destination location")
    if source.id == target.id:
        raise DomainError("Source and destination must be different.")
    qty = quantity(data.get("quantity"))
    ref = uuid.uuid4()
    reference = str(data.get("reference") or "").strip()
    for bal, take in _allocate(db, item, source, qty, data.get("batch_id") or None):
        bal.quantity -= take
        _balance(db, item.id, target.id, bal.batch_id).quantity += take
        for loc, kind in ((source, "TRANSFER_OUT"), (target, "TRANSFER_IN")):
            db.add(StockMovement(item_id=item.id, location_id=loc.id, batch_id=bal.batch_id, movement_type=kind,
                                 quantity=take, unit_cost=item.average_cost, reference=reference,
                                 reason=str(data.get("reason") or ""), transfer_ref=ref, performed_by=user.id))
    audit.record(db, user, "stock.transfer", "stock_item", item.id,
                 f"Transferred {_fmt(qty)} {item.unit_of_measure} {item.name}: {source.name} → {target.name}")
    commit(db)
    return ref


# ------------------------------------------------------------------ queries
def items_with_totals(db: Session, q: str = "", category_id=None, low_only: bool = False,
                      include_inactive: bool = False) -> list[dict[str, Any]]:
    total = func.coalesce(func.sum(StockBalance.quantity), 0).label("on_hand")
    stmt = (select(StockItem, total).outerjoin(StockBalance, StockBalance.item_id == StockItem.id)
            .group_by(StockItem.id).order_by(StockItem.name))
    if not include_inactive:
        stmt = stmt.where(StockItem.is_active.is_(True))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(StockItem.item_code.ilike(like), StockItem.name.ilike(like)))
    if ids := as_uuids(category_id, "category"):
        stmt = stmt.where(StockItem.category_id.in_(ids))
    rows = []
    for item, on_hand in db.execute(stmt).unique():
        on_hand = Decimal(str(on_hand))
        state = "out" if on_hand <= 0 else "low" if on_hand <= item.reorder_level else "ok"
        if low_only and state == "ok":
            continue
        rows.append({"item": item, "on_hand": on_hand, "stock_state": state,
                     "value": (on_hand * item.average_cost).quantize(Decimal("0.01"))})
    return rows


def balances(db: Session, item_id=None, location_id=None) -> list[StockBalance]:
    stmt = select(StockBalance).where(StockBalance.quantity != 0)
    if item_id:
        stmt = stmt.where(StockBalance.item_id == as_uuid(item_id, "item"))
    if ids := as_uuids(location_id, "location"):
        stmt = stmt.where(StockBalance.location_id.in_(ids))
    return list(db.scalars(stmt))


def movements(db: Session, item_id=None, location_id=None, movement_type=None,
              start: date | None = None, end: date | None = None, q: str = "", limit: int = 1000
              ) -> list[StockMovement]:
    stmt = select(StockMovement).join(StockItem, StockMovement.item_id == StockItem.id)
    if item_id:
        stmt = stmt.where(StockMovement.item_id == as_uuid(item_id, "item"))
    if ids := as_uuids(location_id, "location"):
        stmt = stmt.where(StockMovement.location_id.in_(ids))
    if kinds := as_list(movement_type):
        stmt = stmt.where(StockMovement.movement_type.in_(kinds))
    if start:
        stmt = stmt.where(func.date(StockMovement.created_at) >= start.isoformat())
    if end:
        stmt = stmt.where(func.date(StockMovement.created_at) <= end.isoformat())
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(StockItem.name.ilike(like), StockItem.item_code.ilike(like),
                              StockMovement.reference.ilike(like), StockMovement.reason.ilike(like)))
    return list(db.scalars(stmt.order_by(StockMovement.created_at.desc()).limit(limit)).unique())


def expiring_batches(db: Session, days: int = 60) -> list[dict[str, Any]]:
    limit = date.today() + timedelta(days=days)
    stmt = (select(StockBatch, StockItem, func.sum(StockBalance.quantity))
            .join(StockItem, StockBatch.item_id == StockItem.id)
            .join(StockBalance, StockBalance.batch_id == StockBatch.id)
            .where(StockBatch.expiry_date.is_not(None), StockBatch.expiry_date <= limit)
            .group_by(StockBatch.id, StockItem.id).having(func.sum(StockBalance.quantity) > 0)
            .order_by(StockBatch.expiry_date))
    return [{"batch": b, "item": i, "quantity": Decimal(str(q)),
             "expired": b.expiry_date < date.today()} for b, i, q in db.execute(stmt)]


def reconcile(db: Session) -> list[dict[str, Any]]:
    """Compare cached balances with ledger totals. An empty list means they agree."""
    sign = case((StockMovement.movement_type.in_(IN_TYPES), StockMovement.quantity), else_=-StockMovement.quantity)
    ledger = {(i, l, b): Decimal(str(q)) for i, l, b, q in db.execute(
        select(StockMovement.item_id, StockMovement.location_id, StockMovement.batch_id, func.sum(sign))
        .group_by(StockMovement.item_id, StockMovement.location_id, StockMovement.batch_id))}
    cached = {(r.item_id, r.location_id, r.batch_id): r.quantity for r in db.scalars(select(StockBalance))}
    problems = []
    for key in set(ledger) | set(cached):
        a, b = ledger.get(key, ZERO), cached.get(key, ZERO)
        if a != b:
            problems.append({"item_id": str(key[0]), "location_id": str(key[1]),
                             "batch_id": str(key[2]) if key[2] else None, "ledger": str(a), "cached": str(b)})
    return problems
