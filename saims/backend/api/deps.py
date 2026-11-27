"""Request dependencies: database session, signed-in user, permission checks."""
from __future__ import annotations

from typing import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from saims.backend.config import Settings
from saims.backend.errors import AuthError, PermissionDenied
from saims.backend.models import User, UserSession
from saims.backend.services import auth


def get_db(request: Request) -> Iterator[Session]:
    db: Session = request.app.state.sessions()
    try:
        yield db
    finally:
        db.close()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise AuthError()
    return header[7:].strip()


def current_session(request: Request, db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)) -> tuple[User, UserSession]:
    return auth.authenticate(db, settings, _token(request))


def current_user(pair: tuple[User, UserSession] = Depends(current_session)) -> User:
    return pair[0]


def require(*permissions: str):
    """Dependency that allows the request only if the user holds every listed permission."""

    def check(user: User = Depends(current_user)) -> User:
        held = user.permission_codes
        for p in permissions:
            if p not in held:
                raise PermissionDenied(p)
        return user

    return check


def check(user: User, permission: str) -> None:
    if permission not in user.permission_codes:
        raise PermissionDenied(permission)


def require_any(*permissions: str):
    """Dependency that allows the request if the user holds at least one of the listed permissions."""

    def check_any(user: User = Depends(current_user)) -> User:
        if not user.permission_codes & set(permissions):
            raise PermissionDenied(" or ".join(permissions))
        return user

    return check_any


def own_only(user: User, full: str, own: str) -> bool:
    """True when the user may see only their own records (holds `own` but not `full`)."""
    held = user.permission_codes
    return full not in held and own in held
