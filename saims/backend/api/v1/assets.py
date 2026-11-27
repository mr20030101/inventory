import io

import qrcode
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from saims.backend.api import serializers as ser
from saims.backend.api.deps import check, current_user, get_db, own_only, require, require_any
from saims.backend.api.schemas import (
    ArchiveIn, AssetBulkIn, AssetIn, AssignIn, ConditionIn, LifecycleIn, ReturnIn, TransferIn,
)
from saims.backend.errors import DomainError, NotFound
from saims.backend.models import Asset, AssetAssignment, User
from saims.backend.services import assets as svc
from saims.backend.services.common import all_or_nothing, get_or_404

router = APIRouter(prefix="/assets", tags=["assets"])

LIFECYCLE_PERMISSIONS = {
    "send_to_maintenance": "maintenance.manage", "complete_maintenance": "maintenance.manage",
    "mark_missing": "assets.mark_missing", "recover": "assets.mark_missing", "mark_damaged": "assets.mark_missing",
    "retire": "assets.dispose", "dispose": "assets.dispose",
}
BULK_PERMISSIONS = {"assign": "assets.assign", "return": "assets.assign", "transfer": "assets.transfer",
                    "condition": "assets.update"}
VIEW = require_any("assets.view", "assets.view_own")


def _visible(db: Session, user: User, asset_id: str) -> Asset:
    """Load an asset the user may see: any asset, or only those assigned to them for own-only users."""
    asset = get_or_404(db, Asset, asset_id, "Asset")
    if own_only(user, "assets.view", "assets.view_own"):
        assignment = svc.active_assignment(db, asset.id)
        if not (user.employee_id and assignment and assignment.employee_id == user.employee_id):
            raise NotFound("Asset")  # do not reveal that other assets exist
    return asset


def _one(db: Session, asset: Asset) -> dict:
    return ser.asset(asset, svc.custodians(db, [asset.id]).get(asset.id, ""))


@router.get("")
def list_assets(q: str = "", status: list[str] = Query(default=[]), category_id: list[str] = Query(default=[]),
                department_id: list[str] = Query(default=[]), room_id: list[str] = Query(default=[]),
                employee_id: str | None = None, include_archived: bool = False, user: User = Depends(VIEW),
                db: Session = Depends(get_db)):
    if own_only(user, "assets.view", "assets.view_own"):
        if not user.employee_id:
            return []
        employee_id, include_archived = str(user.employee_id), False
    rows = svc.search(db, q, status, category_id, department_id, room_id, employee_id or None, include_archived)
    custody = svc.custodians(db, [a.id for a in rows])
    return [ser.asset(a, custody.get(a.id, "")) for a in rows]


@router.get("/meta")
def meta(_=Depends(current_user)):
    return {"statuses": svc.STATUSES, "conditions": svc.CONDITIONS, "funding_sources": svc.FUNDING_SOURCES}


@router.post("")
def register(body: AssetIn, user: User = Depends(require("assets.create")), db: Session = Depends(get_db)):
    return _one(db, svc.register(db, db.merge(user), body.data()))


@router.post("/bulk")
def bulk(body: AssetBulkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Apply one action to several assets in a single transaction. If any asset cannot take the action, the
    error names it and nothing is changed."""
    user = db.merge(user)
    data = body.data()
    if body.action == "lifecycle":
        if not body.lifecycle_action:
            raise DomainError("Choose the lifecycle action.")
        check(user, LIFECYCLE_PERMISSIONS[body.lifecycle_action])
    else:
        check(user, BULK_PERMISSIONS[body.action])
    assets = [get_or_404(db, Asset, i, "Asset") for i in dict.fromkeys(body.asset_ids)]
    with all_or_nothing(db) as item:
        for asset in assets:
            item(asset.asset_code)
            if body.action == "assign":
                svc.assign(db, user, asset.id, {k: data.get(k) for k in ("employee_id", "department_id", "room_id",
                                                                       "condition", "acknowledged", "notes")})
            elif body.action == "return":
                svc.return_assignment(db, user, asset.id, body.condition or asset.condition, body.notes)
            elif body.action == "transfer":
                svc.transfer(db, user, asset.id, {k: data.get(k) for k in ("room_id", "department_id", "reason")})
            elif body.action == "condition":
                if not body.condition:
                    raise DomainError("Choose the condition.")
                svc.set_condition(db, user, asset.id, body.condition, body.notes)
            else:
                svc.lifecycle(db, user, asset.id, body.lifecycle_action, body.reason, body.condition,
                              body.event_date)
    return {"updated": len(assets)}


@router.get("/{asset_id}")
def detail(asset_id: str, user: User = Depends(VIEW), db: Session = Depends(get_db)):
    asset = _visible(db, user, asset_id)
    assignment = svc.active_assignment(db, asset.id)
    past = db.scalars(select(AssetAssignment).where(AssetAssignment.asset_id == asset.id)
                      .order_by(AssetAssignment.assigned_at.desc())).unique()
    return {**_one(db, asset), "assignment": ser.assignment(assignment) if assignment else None,
            "assignments": [ser.assignment(a) for a in past],
            "history": [ser.event(e) for e in svc.history(db, asset.id)]}


@router.patch("/{asset_id}")
def update(asset_id: str, body: AssetIn, user: User = Depends(require("assets.update")),
           db: Session = Depends(get_db)):
    return _one(db, svc.update(db, db.merge(user), asset_id, body.data()))


@router.post("/{asset_id}/assign")
def assign(asset_id: str, body: AssignIn, user: User = Depends(require("assets.assign")),
           db: Session = Depends(get_db)):
    return ser.assignment(svc.assign(db, db.merge(user), asset_id, body.data()))


@router.post("/{asset_id}/return")
def return_asset(asset_id: str, body: ReturnIn, user: User = Depends(require("assets.assign")),
                 db: Session = Depends(get_db)):
    return _one(db, svc.return_assignment(db, db.merge(user), asset_id, body.condition, body.notes))


@router.post("/{asset_id}/transfer")
def transfer(asset_id: str, body: TransferIn, user: User = Depends(require("assets.transfer")),
             db: Session = Depends(get_db)):
    return _one(db, svc.transfer(db, db.merge(user), asset_id, body.data()))


@router.post("/{asset_id}/lifecycle")
def lifecycle(asset_id: str, body: LifecycleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    check(user, LIFECYCLE_PERMISSIONS[body.action])
    return _one(db, svc.lifecycle(db, db.merge(user), asset_id, body.action, body.reason, body.condition,
                                  body.event_date))


@router.post("/{asset_id}/condition")
def condition(asset_id: str, body: ConditionIn, user: User = Depends(require("assets.update")),
              db: Session = Depends(get_db)):
    return _one(db, svc.set_condition(db, db.merge(user), asset_id, body.condition, body.note))


@router.post("/{asset_id}/archive")
def archive(asset_id: str, body: ArchiveIn, user: User = Depends(require("assets.archive")),
            db: Session = Depends(get_db)):
    return _one(db, svc.archive(db, db.merge(user), asset_id, body.reason))


@router.get("/{asset_id}/qr.png")
def qr_code(asset_id: str, user: User = Depends(VIEW), db: Session = Depends(get_db)):
    asset = _visible(db, user, asset_id)
    img = qrcode.make(f"SAIMS:ASSET:{asset.asset_code}", box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")
