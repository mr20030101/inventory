from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from saims.backend.api import serializers as ser
from saims.backend.api.deps import get_db, get_settings, require
from saims.backend.api.schemas import PasswordResetIn, UserIn
from saims.backend.config import Settings
from saims.backend.models import Permission, Role, User
from saims.backend.services import auth

router = APIRouter(tags=["users"])


@router.get("/users")
def list_users(_=Depends(require("users.view")), db: Session = Depends(get_db)):
    return [ser.user(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users")
def create_user(body: UserIn, actor=Depends(require("users.create")), db: Session = Depends(get_db),
                settings: Settings = Depends(get_settings)):
    return ser.user(auth.create_user(db, settings, db.merge(actor), body.data()))


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserIn, actor=Depends(require("users.update")), db: Session = Depends(get_db)):
    return ser.user(auth.update_user(db, db.merge(actor), user_id, body.data()))


@router.post("/users/{user_id}/deactivate")
def deactivate(user_id: str, actor=Depends(require("users.deactivate")), db: Session = Depends(get_db)):
    return ser.user(auth.set_active(db, db.merge(actor), user_id, False))


@router.post("/users/{user_id}/activate")
def activate(user_id: str, actor=Depends(require("users.deactivate")), db: Session = Depends(get_db)):
    return ser.user(auth.set_active(db, db.merge(actor), user_id, True))


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: str, body: PasswordResetIn, actor=Depends(require("users.deactivate")),
                   db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    auth.reset_password(db, settings, db.merge(actor), user_id, body.password)
    return {"ok": True}


@router.get("/roles")
def roles(_=Depends(require("users.view")), db: Session = Depends(get_db)):
    return [ser.role(r) for r in db.scalars(select(Role).order_by(Role.name))]


@router.get("/permissions")
def permissions(_=Depends(require("users.view")), db: Session = Depends(get_db)):
    return [{"code": p.code, "description": p.description} for p in db.scalars(select(Permission).order_by(Permission.code))]
