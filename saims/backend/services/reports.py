"""Dashboard figures and tabular reports (specification sections 4.1 and 4.12)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saims.backend.errors import DomainError, PermissionDenied
from saims.backend.models import (
    Asset, AssetAssignment, AssetEvent, AuditLog, BorrowRequest, Category, StockMovement, User,
)
from saims.backend.services import assets as asset_svc
from saims.backend.services import borrowing as borrow_svc
from saims.backend.services import stock as stock_svc
from saims.backend.services.common import setting

VALUATION_NOTE = ("Assets at acquisition cost (no depreciation). Consumables at weighted average cost. "
                  "Estimates only, not official accounting figures.")


def _d(value: Any) -> str:
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def _month_keys(months: int) -> list[str]:
    today = date.today()
    y, m, keys = today.year, today.month, []
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return keys[::-1]


def dashboard(db: Session, user: User) -> dict[str, Any]:
    perms = user.permission_codes
    out: dict[str, Any] = {"school_name": setting(db, "school_name", "Demo School"),
                           "valuation_note": VALUATION_NOTE, "alerts": []}
    if "assets.view" in perms:
        live = select(Asset).where(Asset.archived_at.is_(None))
        all_assets = list(db.scalars(live).unique())
        by_status = Counter(a.status for a in all_assets)
        in_service = [a for a in all_assets if a.status not in {"retired", "disposed"}]
        out["assets"] = {
            "total": len(in_service), "by_status": dict(by_status),
            "value": _d(sum((a.acquisition_cost for a in in_service), Decimal(0))),
            "assigned": by_status["assigned"], "available": by_status["available"],
            "attention": by_status["missing"] + by_status["damaged"],
            "under_maintenance": by_status["under_maintenance"],
        }
        dept = Counter(a.department.name if a.department else "Unassigned" for a in in_service)
        out["assets_by_department"] = [{"name": n, "count": c} for n, c in dept.most_common(10)]
        cat = Counter(a.category.name if a.category else "Uncategorised" for a in in_service)
        out["assets_by_category"] = [{"name": n, "count": c} for n, c in cat.most_common()]
        warranty = [a for a in in_service if a.warranty_expiry and date.today() <= a.warranty_expiry
                    <= date.today() + timedelta(days=60)]
        for a in sorted(warranty, key=lambda a: a.warranty_expiry)[:3]:
            out["alerts"].append({"kind": "warranty", "severity": "info", "target": "assets", "id": str(a.id),
                                  "text": f"Warranty for {a.asset_code} {a.name} ends {a.warranty_expiry.isoformat()}"})
        for a in [a for a in all_assets if a.status == "missing"][:5]:
            out["alerts"].append({"kind": "missing", "severity": "critical", "target": "assets", "id": str(a.id),
                                  "text": f"{a.asset_code} {a.name} is missing"})
    if "inventory.view" in perms:
        items = stock_svc.items_with_totals(db)
        low = [r for r in items if r["stock_state"] != "ok"]
        expiring = stock_svc.expiring_batches(db, 60)
        out["consumables"] = {
            "items": len(items), "low": sum(1 for r in low if r["stock_state"] == "low"),
            "out": sum(1 for r in low if r["stock_state"] == "out"),
            "value": _d(sum((r["value"] for r in items), Decimal(0))),
            "expiring": sum(1 for e in expiring if not e["expired"]),
            "expired": sum(1 for e in expiring if e["expired"]),
        }
        for r in sorted(low, key=lambda r: r["on_hand"])[:6]:
            i = r["item"]
            out["alerts"].append({
                "kind": "stock", "severity": "critical" if r["stock_state"] == "out" else "warning",
                "target": "consumables", "id": str(i.id),
                "text": f"{i.name}: {'out of stock' if r['stock_state'] == 'out' else 'low stock'} "
                        f"({r['on_hand'].normalize():f} {i.unit_of_measure}, reorder at "
                        f"{i.reorder_level.normalize():f})"})
        for e in expiring[:4]:
            out["alerts"].append({
                "kind": "expiry", "severity": "critical" if e["expired"] else "warning", "target": "consumables",
                "id": str(e["item"].id),
                "text": f"{e['item'].name} batch {e['batch'].batch_no} "
                        f"{'expired' if e['expired'] else 'expires'} {e['batch'].expiry_date.isoformat()}"})
        out["stock_flow"] = _stock_flow(db)
    if "borrowing.view" in perms:
        reqs = borrow_svc.search(db)
        overdue = [r for r in reqs if borrow_svc.is_overdue(r)]
        out["borrowing"] = {"pending": sum(r.status == "pending" for r in reqs),
                            "approved": sum(r.status == "approved" for r in reqs),
                            "on_loan": sum(r.status == "released" for r in reqs), "overdue": len(overdue)}
        for r in overdue[:5]:
            days = (date.today() - r.expected_return).days
            out["alerts"].append({"kind": "overdue", "severity": "critical", "target": "borrowing", "id": str(r.id),
                                  "text": f"{r.asset.asset_code} borrowed by {r.borrower.full_name} is "
                                          f"{days} day(s) overdue"})
        pending = [r for r in reqs if r.status == "pending"]
        if pending and "borrowing.approve" in perms:
            out["alerts"].append({"kind": "pending", "severity": "info", "target": "borrowing", "id": "",
                                  "text": f"{len(pending)} borrowing request(s) waiting for approval"})
    _personal(db, user, perms, out)
    recent = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(12)
    if "system.audit_logs.view" not in perms:
        recent = recent.where(AuditLog.user_id == user.id)
    out["recent_activity"] = [{"when": a.created_at.isoformat(), "user": a.username, "action": a.action,
                               "summary": a.summary} for a in db.scalars(recent)]
    order = {"critical": 0, "warning": 1, "info": 2}
    out["alerts"].sort(key=lambda a: order[a["severity"]])
    return out


def _personal(db: Session, user: User, perms: set[str], out: dict[str, Any]) -> None:
    """For people who see only their own records (e.g. teachers): their assets, requests and reminders."""
    if "assets.view" not in perms and "assets.view_own" in perms:
        mine = []
        if user.employee_id:
            rows = db.scalars(select(AssetAssignment).where(AssetAssignment.employee_id == user.employee_id,
                                                            AssetAssignment.returned_at.is_(None))
                              .order_by(AssetAssignment.assigned_at.desc()))
            mine = [{"id": str(x.asset.id), "asset_code": x.asset.asset_code, "name": x.asset.name,
                     "condition": x.asset.condition.capitalize(), "room": x.asset.room.name if x.asset.room else "",
                     "since": x.assigned_at.isoformat(), "acknowledged": x.acknowledged} for x in rows]
        out["my_assets"] = mine
        for a in mine:
            if not a["acknowledged"]:
                out["alerts"].append({"kind": "acknowledge", "severity": "info", "target": "assets", "id": a["id"],
                                      "text": f"{a['asset_code']} {a['name']}: please sign the acknowledgment "
                                              f"with the property custodian"})
    if "borrowing.view" not in perms and "borrowing.view_own" in perms:
        reqs = borrow_svc.search(db, own_user=user)
        out["my_borrowing"] = {
            "pending": sum(r.status == "pending" for r in reqs), "approved": sum(r.status == "approved" for r in reqs),
            "on_loan": sum(r.status == "released" for r in reqs),
            "overdue": sum(borrow_svc.is_overdue(r) for r in reqs),
            "requests": [{"id": str(r.id), "request_no": r.request_no, "asset_code": r.asset.asset_code,
                          "asset_name": r.asset.name, "status": r.status,
                          "status_label": "Overdue" if borrow_svc.is_overdue(r) else borrow_svc.STATUS_LABELS[r.status],
                          "expected_return": r.expected_return.isoformat()} for r in reqs[:10]],
        }
        recent_cutoff = date.today() - timedelta(days=14)
        for r in reqs:
            if borrow_svc.is_overdue(r):
                days = (date.today() - r.expected_return).days
                out["alerts"].append({"kind": "overdue", "severity": "critical", "target": "borrowing",
                                      "id": str(r.id), "text": f"Please return {r.asset.asset_code} {r.asset.name}: "
                                                               f"{days} day(s) overdue"})
            elif r.status == "approved":
                out["alerts"].append({"kind": "approved", "severity": "info", "target": "borrowing", "id": str(r.id),
                                      "text": f"{r.request_no} approved: collect {r.asset.name} from the "
                                              f"property custodian"})
            elif r.status == "rejected" and r.decided_at and r.decided_at.date() >= recent_cutoff:
                out["alerts"].append({"kind": "rejected", "severity": "warning", "target": "borrowing",
                                      "id": str(r.id), "text": f"{r.request_no} for {r.asset.name} was not approved"
                                      + (f": {r.decision_note}" if r.decision_note else "")})


def _stock_flow(db: Session, months: int = 6) -> list[dict[str, Any]]:
    keys = _month_keys(months)
    start = datetime.strptime(keys[0], "%Y-%m").replace(tzinfo=timezone.utc)
    rows = db.execute(select(StockMovement.created_at, StockMovement.movement_type, StockMovement.quantity,
                             StockMovement.unit_cost).where(StockMovement.created_at >= start))
    received, issued = defaultdict(Decimal), defaultdict(Decimal)
    for created, kind, qty, cost in rows:
        key = created.strftime("%Y-%m")
        if kind in {"RECEIPT", "OPENING"}:
            received[key] += qty * cost
        elif kind == "ISSUE":
            issued[key] += qty * cost
    return [{"month": k, "label": datetime.strptime(k, "%Y-%m").strftime("%b"),
             "received": _d(received[k]), "issued": _d(issued[k])} for k in keys]


# ------------------------------------------------------------------ reports
REPORTS: dict[str, tuple[str, str, str]] = {
    # key: (title, permission needed, description)
    "asset_register": ("Master asset register", "assets.view", "Every asset in service with location and custodian"),
    "assets_by_department": ("Assets by department", "assets.view", "Counts and cost per department"),
    "assets_by_location": ("Assets by room / location", "assets.view", "Counts and cost per room"),
    "assets_by_custodian": ("Assets by custodian", "assets.view", "Assets currently assigned to each employee"),
    "missing_damaged": ("Missing and damaged assets", "assets.view", "Assets needing follow-up"),
    "asset_valuation": ("Inventory valuation", "reports.view", "Asset and consumable value by category"),
    "consumable_register": ("Consumable inventory register", "inventory.view", "Stock on hand and value per item"),
    "low_stock": ("Low-stock report", "inventory.view", "Items at or below their reorder level"),
    "expiring_batches": ("Expiring batches", "inventory.view", "Batches expiring within 90 days"),
    "stock_movements": ("Stock movement report", "inventory.view", "Ledger entries in the date range"),
    "borrowing": ("Borrowing and overdue report", "borrowing.view", "Borrowing requests in the date range"),
    "user_activity": ("User activity report", "system.audit_logs.view", "Audit log entries in the date range"),
}


def available_reports(user: User) -> list[dict[str, str]]:
    perms = user.permission_codes
    return [{"key": k, "title": t, "description": d} for k, (t, p, d) in REPORTS.items()
            if p in perms and "reports.view" in perms]


def _col(key: str, label: str, kind: str = "text") -> dict[str, str]:
    return {"key": key, "label": label, "kind": kind}


def run(db: Session, user: User, key: str, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    if key not in REPORTS:
        raise DomainError("Unknown report.")
    title, perm, _ = REPORTS[key]
    for p in ("reports.view", perm):
        if p not in user.permission_codes:
            raise PermissionDenied(p)
    end = end or date.today()
    start = start or end - timedelta(days=90)
    cols, rows = globals()[f"_report_{key}"](db, start, end)
    return {"key": key, "title": title, "school_name": setting(db, "school_name", "Demo School"),
            "generated_at": datetime.now(timezone.utc).isoformat(), "generated_by": user.full_name,
            "filters": {"start": start.isoformat(), "end": end.isoformat()}
            if key in {"stock_movements", "borrowing", "user_activity"} else {},
            "columns": cols, "rows": rows,
            "note": VALUATION_NOTE if key in {"asset_valuation", "consumable_register"} else ""}


def _live_assets(db: Session) -> list[Asset]:
    return list(db.scalars(select(Asset).where(Asset.archived_at.is_(None)).order_by(Asset.asset_code)).unique())


def _report_asset_register(db, start, end):
    assets = [a for a in _live_assets(db) if a.status != "disposed"]
    custody = asset_svc.custodians(db, [a.id for a in assets])
    cols = [_col("asset_code", "Asset code"), _col("name", "Name"), _col("category", "Category"),
            _col("brand_model", "Brand / model"), _col("serial", "Serial no."), _col("status", "Status"),
            _col("condition", "Condition"), _col("room", "Room"), _col("department", "Department"),
            _col("custodian", "Assigned to"), _col("acquired", "Acquired", "date"),
            _col("cost", "Cost", "money"), _col("funding", "Funding")]
    rows = [{"asset_code": a.asset_code, "name": a.name, "category": a.category.name if a.category else "",
             "brand_model": " ".join(x for x in (a.brand, a.model) if x), "serial": a.serial_number or "",
             "status": asset_svc.STATUSES[a.status], "condition": asset_svc.CONDITIONS[a.condition],
             "room": a.room.name if a.room else "", "department": a.department.name if a.department else "",
             "custodian": custody.get(a.id, ""),
             "acquired": a.acquisition_date.isoformat() if a.acquisition_date else "", "cost": _d(a.acquisition_cost),
             "funding": asset_svc.FUNDING_SOURCES.get(a.funding_source, a.funding_source)} for a in assets]
    return cols, rows


def _group_assets(assets: list[Asset], keyfn) -> list[dict[str, Any]]:
    groups: dict[str, list[Asset]] = defaultdict(list)
    for a in assets:
        groups[keyfn(a)].append(a)
    rows = []
    for name, items in sorted(groups.items()):
        st = Counter(a.status for a in items)
        rows.append({"group": name, "total": len(items), "assigned": st["assigned"] + st["borrowed"],
                     "available": st["available"], "maintenance": st["under_maintenance"],
                     "attention": st["missing"] + st["damaged"],
                     "cost": _d(sum((a.acquisition_cost for a in items), Decimal(0)))})
    return rows


def _group_cols(label: str):
    return [_col("group", label), _col("total", "Assets", "number"), _col("assigned", "In use", "number"),
            _col("available", "Available", "number"), _col("maintenance", "In maintenance", "number"),
            _col("attention", "Missing / damaged", "number"), _col("cost", "Acquisition cost", "money")]


def _report_assets_by_department(db, start, end):
    assets = [a for a in _live_assets(db) if a.status not in {"retired", "disposed"}]
    return _group_cols("Department"), _group_assets(assets, lambda a: a.department.name if a.department else "—")


def _report_assets_by_location(db, start, end):
    assets = [a for a in _live_assets(db) if a.status not in {"retired", "disposed"}]
    return _group_cols("Room"), _group_assets(
        assets, lambda a: f"{a.room.building.name} · {a.room.name}" if a.room else "No location")


def _report_assets_by_custodian(db, start, end):
    rows = db.scalars(select(AssetAssignment).where(AssetAssignment.returned_at.is_(None),
                                                    AssetAssignment.employee_id.is_not(None))).unique()
    cols = [_col("employee", "Employee"), _col("department", "Department"), _col("asset_code", "Asset code"),
            _col("name", "Asset"), _col("assigned", "Assigned on", "date"), _col("condition", "Condition at release"),
            _col("ack", "Acknowledged")]
    out = [{"employee": r.employee.full_name, "department": r.employee.department.name if r.employee.department else "",
            "asset_code": r.asset.asset_code, "name": r.asset.name, "assigned": r.assigned_at.date().isoformat(),
            "condition": asset_svc.CONDITIONS.get(r.condition_on_release, r.condition_on_release),
            "ack": "Yes" if r.acknowledged else "No"} for r in rows]
    return cols, sorted(out, key=lambda r: (r["employee"], r["asset_code"]))


def _report_missing_damaged(db, start, end):
    assets = [a for a in _live_assets(db) if a.status in {"missing", "damaged"}]
    cols = [_col("asset_code", "Asset code"), _col("name", "Name"), _col("status", "Status"),
            _col("room", "Last location"), _col("since", "Since", "date"), _col("reason", "Reason"),
            _col("cost", "Cost", "money")]
    rows = []
    for a in assets:
        ev = db.scalar(select(AssetEvent).where(AssetEvent.asset_id == a.id, AssetEvent.to_status == a.status)
                       .order_by(AssetEvent.created_at.desc()).limit(1))
        rows.append({"asset_code": a.asset_code, "name": a.name, "status": asset_svc.STATUSES[a.status],
                     "room": a.room.name if a.room else "", "since": ev.created_at.date().isoformat() if ev else "",
                     "reason": ev.reason if ev else "", "cost": _d(a.acquisition_cost)})
    return cols, rows


def _report_asset_valuation(db, start, end):
    cols = [_col("type", "Type"), _col("category", "Category"), _col("count", "Records", "number"),
            _col("value", "Value", "money"), _col("method", "Valuation method")]
    groups: dict[str, list[Decimal]] = defaultdict(list)
    for a in _live_assets(db):
        if a.status not in {"retired", "disposed"}:
            groups[a.category.name if a.category else "Uncategorised"].append(a.acquisition_cost)
    rows = [{"type": "Fixed assets", "category": k, "count": len(v), "value": _d(sum(v, Decimal(0))),
             "method": "Acquisition cost"} for k, v in sorted(groups.items())]
    cons: dict[str, list[Decimal]] = defaultdict(list)
    for r in stock_svc.items_with_totals(db):
        cons[r["item"].category.name if r["item"].category else "Uncategorised"].append(r["value"])
    rows += [{"type": "Consumables", "category": k, "count": len(v), "value": _d(sum(v, Decimal(0))),
              "method": "Weighted average cost"} for k, v in sorted(cons.items())]
    return cols, rows


def _consumable_rows(rows):
    labels = {"ok": "OK", "low": "Low", "out": "Out of stock"}
    return [{"item_code": r["item"].item_code, "name": r["item"].name,
             "category": r["item"].category.name if r["item"].category else "",
             "unit": r["item"].unit_of_measure, "on_hand": f"{r['on_hand'].normalize():f}",
             "reorder": f"{r['item'].reorder_level.normalize():f}", "avg_cost": _d(r["item"].average_cost),
             "value": _d(r["value"]), "state": labels[r["stock_state"]]} for r in rows]


_CONSUMABLE_COLS = [_col("item_code", "Item code"), _col("name", "Item"), _col("category", "Category"),
                    _col("unit", "Unit"), _col("on_hand", "On hand", "number"),
                    _col("reorder", "Reorder level", "number"), _col("avg_cost", "Avg cost", "money"),
                    _col("value", "Value", "money"), _col("state", "Stock")]


def _report_consumable_register(db, start, end):
    return _CONSUMABLE_COLS, _consumable_rows(stock_svc.items_with_totals(db))


def _report_low_stock(db, start, end):
    return _CONSUMABLE_COLS, _consumable_rows(stock_svc.items_with_totals(db, low_only=True))


def _report_expiring_batches(db, start, end):
    cols = [_col("item", "Item"), _col("batch", "Batch"), _col("expiry", "Expiry date", "date"),
            _col("qty", "Quantity", "number"), _col("state", "State")]
    return cols, [{"item": e["item"].name, "batch": e["batch"].batch_no, "expiry": e["batch"].expiry_date.isoformat(),
                   "qty": f"{e['quantity'].normalize():f} {e['item'].unit_of_measure}",
                   "state": "Expired" if e["expired"] else "Expiring"} for e in stock_svc.expiring_batches(db, 90)]


def _report_stock_movements(db, start, end):
    cols = [_col("date", "Date", "datetime"), _col("item", "Item"), _col("type", "Type"),
            _col("qty", "Quantity", "number"), _col("location", "Location"), _col("to", "Issued to / from"),
            _col("value", "Value", "money"), _col("reference", "Reference"), _col("user", "By")]
    rows = [{"date": m.created_at.isoformat(), "item": m.item.name, "type": stock_svc.MOVEMENT_LABELS[m.movement_type],
             "qty": f"{m.quantity.normalize():f}", "location": m.location.name,
             "to": m.department.name if m.department else "", "value": _d(m.quantity * m.unit_cost),
             "reference": m.reference, "user": m.user.full_name}
            for m in stock_svc.movements(db, start=start, end=end, limit=5000)]
    return cols, rows


def _report_borrowing(db, start, end):
    cols = [_col("request_no", "Request"), _col("asset", "Asset"), _col("borrower", "Borrower"),
            _col("status", "Status"), _col("needed", "Needed", "date"), _col("due", "Due back", "date"),
            _col("returned", "Returned", "date"), _col("overdue", "Days overdue", "number")]
    rows = []
    for r in borrow_svc.search(db):
        if not (start <= r.created_at.date() <= end) and r.status != "released":
            continue
        late = (date.today() - r.expected_return).days if borrow_svc.is_overdue(r) else 0
        rows.append({"request_no": r.request_no, "asset": f"{r.asset.asset_code} {r.asset.name}",
                     "borrower": r.borrower.full_name, "status": borrow_svc.STATUS_LABELS[r.status],
                     "needed": r.date_needed.isoformat(), "due": r.expected_return.isoformat(),
                     "returned": r.returned_at.date().isoformat() if r.returned_at else "", "overdue": late})
    return cols, rows


def _report_user_activity(db, start, end):
    cols = [_col("when", "When", "datetime"), _col("user", "User"), _col("action", "Action"),
            _col("entity", "Record type"), _col("summary", "Summary")]
    stmt = (select(AuditLog).where(func.date(AuditLog.created_at) >= start.isoformat(),
                                   func.date(AuditLog.created_at) <= end.isoformat())
            .order_by(AuditLog.created_at.desc()).limit(5000))
    return cols, [{"when": a.created_at.isoformat(), "user": a.username, "action": a.action,
                   "entity": a.entity_type, "summary": a.summary} for a in db.scalars(stmt)]
