from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from saims.backend.api import serializers as ser
from saims.backend.api.deps import check, current_user, get_db, require
from saims.backend.api.schemas import MovementBatchIn, MovementIn, StockItemIn, StockTransferIn
from saims.backend.models import StockItem, StockMovement, User
from saims.backend.services import stock as svc
from saims.backend.services.common import all_or_nothing, get_or_404

router = APIRouter(prefix="/stock", tags=["consumables"])


@router.get("/items")
def items(q: str = "", category_id: list[str] = Query(default=[]), low_only: bool = False,
          include_inactive: bool = False, _=Depends(require("inventory.view")), db: Session = Depends(get_db)):
    return [ser.stock_item(r) for r in svc.items_with_totals(db, q, category_id, low_only, include_inactive)]


@router.post("/items")
def create_item(body: StockItemIn, user: User = Depends(require("inventory.manage_items")),
                db: Session = Depends(get_db)):
    item = svc.create_item(db, db.merge(user), body.data())
    return ser.stock_item({"item": item, "on_hand": svc.item_total(db, item.id), "value": 0, "stock_state": "out"})


@router.patch("/items/{item_id}")
def update_item(item_id: str, body: StockItemIn, user: User = Depends(require("inventory.manage_items")),
                db: Session = Depends(get_db)):
    item = svc.update_item(db, db.merge(user), item_id, body.data())
    return {"id": str(item.id)}


@router.get("/balances")
def balances(item_id: str | None = None, location_id: list[str] = Query(default=[]),
             _=Depends(require("inventory.view")), db: Session = Depends(get_db)):
    return [ser.balance(b) for b in svc.balances(db, item_id or None, location_id)]


@router.get("/movements")
def movements(item_id: str | None = None, location_id: list[str] = Query(default=[]),
              movement_type: list[str] = Query(default=[]), start: date | None = None, end: date | None = None,
              q: str = "", _=Depends(require("inventory.view")), db: Session = Depends(get_db)):
    return [ser.movement(m) for m in svc.movements(db, item_id or None, location_id, movement_type, start, end, q)]


@router.post("/movements")
def record(body: MovementIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    check(user, svc.MOVEMENT_PERMISSIONS[body.movement_type])
    return [ser.movement(m) for m in svc.record(db, db.merge(user), body.data())]


@router.post("/movements/batch")
def record_batch(body: MovementBatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Several items with one movement type, location and reference, saved as one transaction.

    `request_id` makes a retry or double-click safe: a batch already recorded is returned, not repeated."""
    check(user, svc.MOVEMENT_PERMISSIONS[body.movement_type])
    user = db.merge(user)
    rid = (body.request_id or "").strip() or None
    if rid:
        done = list(db.scalars(select(StockMovement).where(StockMovement.request_id.like(f"{rid}-%"))))
        if done:
            return [ser.movement(m) for m in done]
    common = {k: v for k, v in body.data().items() if k not in {"lines", "request_id"}}
    written = []
    with all_or_nothing(db) as item:
        for i, line in enumerate(body.lines):
            stock_item = get_or_404(db, StockItem, line.item_id, "Item")
            item(stock_item.name)
            written += svc.record(db, user, {**common, **line.data(),
                                             "request_id": f"{rid}-{i}" if rid else None})
    return [ser.movement(m) for m in written]


@router.post("/transfers")
def transfer(body: StockTransferIn, user: User = Depends(require("inventory.transfer")),
             db: Session = Depends(get_db)):
    return {"transfer_ref": str(svc.transfer(db, db.merge(user), body.data()))}


@router.get("/expiring")
def expiring(days: int = 60, _=Depends(require("inventory.view")), db: Session = Depends(get_db)):
    return [{"item_id": str(e["item"].id), "item": e["item"].name, "batch_no": e["batch"].batch_no,
             "expiry_date": e["batch"].expiry_date.isoformat(), "quantity": f"{e['quantity'].normalize():f}",
             "unit": e["item"].unit_of_measure, "expired": e["expired"]} for e in svc.expiring_batches(db, days)]


@router.get("/reconcile")
def reconcile(_=Depends(require("system.settings")), db: Session = Depends(get_db)):
    problems = svc.reconcile(db)
    return {"consistent": not problems, "differences": problems}
