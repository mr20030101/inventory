"""Equipment borrowing (specification section 4.8): request → approve → release → return."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from saims.backend import audit
from saims.backend.errors import Conflict, DomainError
from saims.backend.models import Asset, AssetEvent, BorrowRequest, Employee, User
from saims.backend.services.assets import CONDITIONS, STATUSES
from saims.backend.services.common import as_list, as_uuid, commit, get_or_404, next_number, now

STATUS_LABELS = {
    "pending": "Pending approval", "approved": "Approved", "rejected": "Rejected", "released": "On loan",
    "returned": "Returned", "cancelled": "Cancelled", "lost": "Lost",
}


def _date(value: Any, label: str) -> date:
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError:
        raise DomainError(f"{label} must be a date (YYYY-MM-DD).") from None


def _status(req: BorrowRequest, allowed: set[str], action: str) -> None:
    if req.status not in allowed:
        raise Conflict(f"Cannot {action}: request {req.request_no} is {STATUS_LABELS[req.status].lower()}.",
                       "invalid_status")


def create(db: Session, user: User, data: dict[str, Any]) -> BorrowRequest:
    asset = get_or_404(db, Asset, data.get("asset_id"), "Asset")
    if asset.archived_at or asset.status in {"retired", "disposed", "missing"}:
        raise Conflict(f"{asset.asset_code} cannot be borrowed ({STATUSES[asset.status].lower()}).", "invalid_status")
    borrower = get_or_404(db, Employee, data.get("borrower_id"), "Borrower")
    if not borrower.is_active:
        raise DomainError(f"{borrower.full_name} is not an active employee.")
    needed = _date(data.get("date_needed") or date.today(), "Date needed")
    expected = _date(data.get("expected_return"), "Expected return date")
    if expected < needed:
        raise DomainError("Expected return date must be on or after the date needed.")
    req = BorrowRequest(request_no=f"BR-{next_number(db, 'borrow'):05d}", asset_id=asset.id,
                        borrower_id=borrower.id, purpose=str(data.get("purpose") or "").strip(),
                        date_needed=needed, expected_return=expected, requested_by=user.id)
    db.add(req)
    db.flush()
    audit.record(db, user, "borrow.request", "borrow_request", req.id,
                 f"{req.request_no}: {borrower.full_name} requests {asset.asset_code}")
    commit(db)
    return req


def decide(db: Session, user: User, req_id, approve: bool, note: str = "") -> BorrowRequest:
    req = get_or_404(db, BorrowRequest, req_id, "Borrow request")
    _status(req, {"pending"}, "approve" if approve else "reject")
    if req.requested_by == user.id and not any(r.code == "super_admin" for r in user.roles):
        raise Conflict("You cannot approve or reject a request you submitted.", "separation_of_duties")
    if not approve and not note.strip():
        raise DomainError("Give a reason for rejecting the request.")
    req.status = "approved" if approve else "rejected"
    req.decided_by, req.decided_at, req.decision_note = user.id, now(), note.strip()
    audit.record(db, user, "borrow.approve" if approve else "borrow.reject", "borrow_request", req.id,
                 f"{req.request_no} {req.status}", {"note": note} if note else None)
    commit(db)
    return req


def cancel(db: Session, user: User, req_id) -> BorrowRequest:
    req = get_or_404(db, BorrowRequest, req_id, "Borrow request")
    _status(req, {"pending", "approved"}, "cancel")
    req.status = "cancelled"
    audit.record(db, user, "borrow.cancel", "borrow_request", req.id, f"{req.request_no} cancelled")
    commit(db)
    return req


def release(db: Session, user: User, req_id, condition: str) -> BorrowRequest:
    req = get_or_404(db, BorrowRequest, req_id, "Borrow request")
    _status(req, {"approved"}, "release")
    asset = req.asset
    if asset.status != "available":
        raise Conflict(f"{asset.asset_code} is {STATUSES[asset.status].lower()} and cannot be released.",
                       "asset_unavailable")
    if condition not in CONDITIONS:
        raise DomainError("Unknown condition.")
    req.status, req.released_by, req.released_at, req.condition_out = "released", user.id, now(), condition
    asset.status, asset.condition = "borrowed", condition
    db.add(AssetEvent(asset_id=asset.id, event_type="borrowed", from_status="available", to_status="borrowed",
                      description=f"Lent to {req.borrower.full_name} until {req.expected_return.isoformat()} "
                                  f"({req.request_no})", performed_by=user.id))
    audit.record(db, user, "borrow.release", "borrow_request", req.id,
                 f"{req.request_no}: {asset.asset_code} released to {req.borrower.full_name}")
    commit(db)
    return req


def receive_return(db: Session, user: User, req_id, condition: str, note: str = "") -> BorrowRequest:
    req = get_or_404(db, BorrowRequest, req_id, "Borrow request")
    _status(req, {"released"}, "receive the return of")
    if condition not in CONDITIONS:
        raise DomainError("Unknown condition.")
    asset = req.asset
    req.status, req.received_by, req.returned_at = "returned", user.id, now()
    req.condition_in, req.return_note = condition, note.strip()
    new_status = "damaged" if condition == "damaged" else "available"
    asset.status, asset.condition = new_status, condition
    late = (date.today() - req.expected_return).days
    db.add(AssetEvent(asset_id=asset.id, event_type="borrow_returned", from_status="borrowed", to_status=new_status,
                      description=f"Returned by {req.borrower.full_name}, condition {condition}"
                                  + (f", {late} day(s) late" if late > 0 else ""),
                      reason=note, performed_by=user.id))
    audit.record(db, user, "borrow.return", "borrow_request", req.id,
                 f"{req.request_no}: {asset.asset_code} returned ({condition})")
    commit(db)
    return req


def search(db: Session, status=None, overdue_only: bool = False, borrower_id=None,
           own_user: User | None = None) -> list[BorrowRequest]:
    """`status` takes one value or a list. `own_user` limits results to requests for or by that user."""
    stmt = select(BorrowRequest).order_by(BorrowRequest.created_at.desc())
    if statuses := as_list(status):
        stmt = stmt.where(BorrowRequest.status.in_(statuses))
    if borrower_id:
        stmt = stmt.where(BorrowRequest.borrower_id == as_uuid(borrower_id, "borrower"))
    if own_user is not None:
        mine = BorrowRequest.requested_by == own_user.id
        if own_user.employee_id:
            mine = mine | (BorrowRequest.borrower_id == own_user.employee_id)
        stmt = stmt.where(mine)
    if overdue_only:
        stmt = stmt.where(BorrowRequest.status == "released", BorrowRequest.expected_return < date.today())
    return list(db.scalars(stmt).unique())


def is_overdue(req: BorrowRequest) -> bool:
    return req.status == "released" and req.expected_return < date.today()
