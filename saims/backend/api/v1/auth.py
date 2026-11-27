from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from saims.backend.api import serializers as ser
from saims.backend.api.deps import current_session, current_user, get_db, get_settings
from saims.backend.api.schemas import LoginIn, PasswordChangeIn
from saims.backend.config import Settings
from saims.backend.models import User
from saims.backend.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _me(user: User) -> dict:
    return {**ser.user(user), "permissions": sorted(user.permission_codes)}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    client = f"{request.client.host if request.client else ''} {request.headers.get('User-Agent', '')}"[:200]
    token, user = auth.login(db, settings, body.username, body.password, client)
    return {"token": token, "user": _me(user)}


@router.post("/logout")
def logout(pair=Depends(current_session), db: Session = Depends(get_db)):
    user, session = pair
    auth.logout(db, db.merge(user), db.merge(session))
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return _me(user)


@router.post("/password")
def change_password(body: PasswordChangeIn, user: User = Depends(current_user), db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)):
    auth.change_own_password(db, settings, db.merge(user), body.current_password, body.new_password)
    return {"ok": True}
