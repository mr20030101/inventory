from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from saims.backend.api import serializers as ser
from saims.backend.api.deps import get_db, own_only, require, require_any
from saims.backend.api.schemas import BorrowBatchIn, BorrowIn, BulkDecisionIn, ConditionNoteIn, DecisionIn
from saims.backend.errors import DomainError, NotFound
from saims.backend.models import Asset, BorrowRequest, User
from saims.backend.services import borrowing as svc
from saims.backend.services.assets import STATUSES
from saims.backend.services.common import all_or_nothing, get_or_404

router = APIRouter(prefix="/borrowing", tags=["borrowing"])

VIEW = require_any("borrowing.view", "borrowing.view_own")


def _own(user: User) -> bool:
    return own_only(user, "borrowing.view", "borrowing.view_own")


def _borrower(user: User, requested: str | None) -> str:
    """People who can only see their own requests can only borrow for themselves."""
    if _own(user) or not requested:
        if not user.employee_id:
            raise DomainError("Your account is not linked to an employee record. Ask the administrator to link it.")
        if requested and requested != str(user.employee_id):
            raise DomainError("You can only request equipment for yourself.")
        return str(user.employee_id)
    return requested


@router.get("")
def list_requests(status: list[str] = Query(default=[]), overdue_only: bool = False, user: User = Depends(VIEW),
                  db: Session = Depends(get_db)):
    return [ser.borrow(r) for r in svc.search(db, status, overdue_only, own_user=user if _own(user) else None)]


@router.get("/catalogue")
def catalogue(_=Depends(require("borrowing.request")), db: Session = Depends(get_db)):
    """Equipment that can be requested, with only the details needed to choose it."""
    rows = db.scalars(select(Asset).where(Asset.archived_at.is_(None), Asset.status.in_(["available", "borrowed"]))
                      .order_by(Asset.asset_code)).unique()
    return [{"id": str(a.id), "asset_code": a.asset_code, "name": a.name,
             "category": a.category.name if a.category else "", "status": a.status,
             "status_label": STATUSES[a.status]} for a in rows]


@router.post("")
def create(body: BorrowIn, user: User = Depends(require("borrowing.request")), db: Session = Depends(get_db)):
    data = {**body.data(), "borrower_id": _borrower(user, body.borrower_id)}
    return ser.borrow(svc.create(db, db.merge(user), data))


@router.post("/batch")
def create_batch(body: BorrowBatchIn, user: User = Depends(require("borrowing.request")),
                 db: Session = Depends(get_db)):
    """One request per piece of equipment, saved together: if any cannot be requested, none are."""
    user = db.merge(user)
    common = {k: v for k, v in body.data().items() if k != "asset_ids"}
    common["borrower_id"] = _borrower(user, body.borrower_id)
    created = []
    with all_or_nothing(db) as item:
        for asset_id in dict.fromkeys(body.asset_ids):
            asset = get_or_404(db, Asset, asset_id, "Asset")
            item(asset.asset_code)
            created.append(svc.create(db, user, {**common, "asset_id": asset_id}))
    return [ser.borrow(r) for r in created]


@router.post("/decisions")
def decide_many(body: BulkDecisionIn, user: User = Depends(require("borrowing.approve")),
                db: Session = Depends(get_db)):
    """Approve or reject several pending requests at once (all or nothing)."""
    user = db.merge(user)
    reqs = [get_or_404(db, BorrowRequest, i, "Borrow request") for i in dict.fromkeys(body.request_ids)]
    with all_or_nothing(db) as item:
        for req in reqs:
            item(req.request_no)
            svc.decide(db, user, req.id, body.approve, body.note)
    return {"updated": len(reqs)}


@router.post("/{req_id}/decision")
def decide(req_id: str, body: DecisionIn, user: User = Depends(require("borrowing.approve")),
           db: Session = Depends(get_db)):
    return ser.borrow(svc.decide(db, db.merge(user), req_id, body.approve, body.note))


@router.post("/{req_id}/cancel")
def cancel(req_id: str, user: User = Depends(require("borrowing.request")), db: Session = Depends(get_db)):
    req = get_or_404(db, BorrowRequest, req_id, "Borrow request")
    if _own(user) and req.requested_by != user.id and req.borrower_id != user.employee_id:
        raise NotFound("Borrow request")
    return ser.borrow(svc.cancel(db, db.merge(user), req_id))


@router.post("/{req_id}/release")
def release(req_id: str, body: ConditionNoteIn, user: User = Depends(require("borrowing.release")),
            db: Session = Depends(get_db)):
    return ser.borrow(svc.release(db, db.merge(user), req_id, body.condition))


@router.post("/{req_id}/return")
def receive_return(req_id: str, body: ConditionNoteIn, user: User = Depends(require("borrowing.receive_return")),
                   db: Session = Depends(get_db)):
    return ser.borrow(svc.receive_return(db, db.merge(user), req_id, body.condition, body.note))
