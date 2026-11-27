"""Sign-in, sessions and user administration."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saims.backend import audit
from saims.backend.config import Settings
from saims.backend.errors import AuthError, Conflict, DomainError
from saims.backend.models import Employee, LoginLog, Permission, Role, SystemSetting, User, UserSession
from saims.backend.permissions import DEFAULT_ROLES, PERMISSIONS, ROLES_VERSION
from saims.backend.security import hash_password, new_token, token_digest, verify_password
from saims.backend.services.common import get_or_404, now, optional, required

_DUMMY_HASH = hash_password("timing-equaliser")


def ensure_roles(db: Session) -> None:
    """Create the permission catalogue and default roles, and update built-in roles when their definition changes."""
    existing = {p.code for p in db.scalars(select(Permission))}
    for code, description in PERMISSIONS.items():
        if code not in existing:
            db.add(Permission(code=code, description=description))
    db.flush()
    perms = {p.code: p for p in db.scalars(select(Permission))}
    roles = {r.code: r for r in db.scalars(select(Role))}
    stored = db.get(SystemSetting, "roles_version")
    outdated = roles and (stored is None or int(stored.value or 0) < ROLES_VERSION)
    for code, (name, description, codes) in DEFAULT_ROLES.items():
        wanted = [perms[c] for c in dict.fromkeys(codes)]
        if code not in roles:
            db.add(Role(code=code, name=name, description=description, permissions=wanted))
        elif outdated:
            role = roles[code]
            before = sorted(p.code for p in role.permissions)
            role.description, role.permissions = description, wanted
            after = sorted(p.code for p in wanted)
            if before != after:
                audit.record(db, None, "role.update", "role", role.id, f"Built-in role {role.name} updated",
                             {"permissions": {"old": before, "new": after}})
    if stored is None:
        db.add(SystemSetting(key="roles_version", value=str(ROLES_VERSION)))
    else:
        stored.value = str(ROLES_VERSION)
    db.commit()


def login(db: Session, settings: Settings, username: str, password: str, client: str = "") -> tuple[str, User]:
    username = (username or "").strip().lower()
    window_start = now() - timedelta(minutes=settings.lockout_minutes)
    recent_failures = db.scalar(
        select(func.count()).select_from(LoginLog).where(
            LoginLog.username == username, LoginLog.event == "login_failed", LoginLog.created_at >= window_start)
    )
    if recent_failures >= settings.max_failed_logins:
        db.add(LoginLog(username=username, event="login_locked", detail="Too many failed attempts", client=client))
        db.commit()
        raise AuthError(f"Too many failed sign-in attempts. Try again in {settings.lockout_minutes} minutes.",
                        "locked")

    user = db.scalar(select(User).where(User.username == username))
    valid = verify_password(user.password_hash if user else _DUMMY_HASH, password or "")
    if not user or not valid or not user.is_active:
        reason = "inactive account" if (user and valid) else "bad credentials"
        db.add(LoginLog(username=username, user_id=user.id if user else None, event="login_failed",
                        detail=reason, client=client))
        db.commit()
        raise AuthError("Incorrect username or password." if reason == "bad credentials"
                        else "This account has been deactivated.", "bad_credentials")

    token = new_token()
    stamp = now()
    db.add(UserSession(user_id=user.id, token_hash=token_digest(token), client=client,
                       expires_at=stamp + timedelta(hours=settings.session_hours)))
    user.last_login_at = stamp
    db.add(LoginLog(username=username, user_id=user.id, event="login_success", client=client))
    db.commit()
    return token, user


def authenticate(db: Session, settings: Settings, token: str) -> tuple[User, UserSession]:
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    stamp = now()
    if session is None or session.revoked_at is not None or session.expires_at <= stamp:
        raise AuthError()
    # Sliding expiry: inactive sessions expire, active ones are extended.
    if stamp - session.last_seen_at > timedelta(minutes=1):
        session.last_seen_at = stamp
        session.expires_at = stamp + timedelta(hours=settings.session_hours)
        db.commit()
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthError("This account has been deactivated.")
    return user, session


def logout(db: Session, user: User, session: UserSession) -> None:
    session.revoked_at = now()
    db.add(LoginLog(username=user.username, user_id=user.id, event="logout"))
    db.commit()


def revoke_sessions(db: Session, user_id) -> int:
    sessions = db.scalars(select(UserSession).where(UserSession.user_id == user_id,
                                                    UserSession.revoked_at.is_(None))).all()
    for s in sessions:
        s.revoked_at = now()
    return len(sessions)


# ------------------------------------------------------------------ user administration
def _roles(db: Session, codes: list[str]) -> list[Role]:
    roles = list(db.scalars(select(Role).where(Role.code.in_(codes))))
    if len(roles) != len(set(codes)):
        raise DomainError("One or more roles do not exist.")
    return roles


def _check_password(settings: Settings, password: str) -> None:
    if len(password or "") < settings.min_password_length:
        raise DomainError(f"Password must be at least {settings.min_password_length} characters.")


def create_user(db: Session, settings: Settings, actor: User, data: dict[str, Any]) -> User:
    username = required(data.get("username"), "Username").lower()
    if db.scalar(select(User).where(User.username == username)):
        raise Conflict(f'Username "{username}" is already taken.')
    email = (data.get("email") or "").strip().lower() or None
    if email and db.scalar(select(User).where(User.email == email)):
        raise Conflict(f'Email "{email}" is already used by another account.')
    _check_password(settings, data.get("password", ""))
    user = User(username=username, email=email, full_name=required(data.get("full_name"), "Full name"),
                password_hash=hash_password(data["password"]), roles=_roles(db, data.get("roles") or []),
                employee_id=employee.id if (employee := optional(db, Employee, data.get("employee_id"),
                                                                    "Employee")) else None)
    db.add(user)
    db.flush()
    audit.record(db, actor, "user.create", "user", user.id, f"Created user {username}",
                 {"roles": data.get("roles") or []})
    db.commit()
    return user


def update_user(db: Session, actor: User, user_id, data: dict[str, Any]) -> User:
    user = get_or_404(db, User, user_id, "User")
    before = {"full_name": user.full_name, "email": user.email, "roles": sorted(r.code for r in user.roles)}
    if "full_name" in data:
        user.full_name = required(data["full_name"], "Full name")
    if "email" in data:
        email = (data["email"] or "").strip().lower() or None
        if email and db.scalar(select(User).where(User.email == email, User.id != user.id)):
            raise Conflict(f'Email "{email}" is already used by another account.')
        user.email = email
    if "roles" in data:
        if user.id == actor.id and "super_admin" in before["roles"] and "super_admin" not in data["roles"]:
            raise DomainError("You cannot remove your own Super Administrator role.")
        user.roles = _roles(db, data["roles"])
    after = {"full_name": user.full_name, "email": user.email, "roles": sorted(r.code for r in user.roles)}
    changes = audit.diff(before, after)
    action = "user.roles_change" if "roles" in changes else "user.update"
    audit.record(db, actor, action, "user", user.id, f"Updated user {user.username}", changes)
    db.commit()
    return user


def set_active(db: Session, actor: User, user_id, active: bool) -> User:
    user = get_or_404(db, User, user_id, "User")
    if user.id == actor.id and not active:
        raise DomainError("You cannot deactivate your own account.")
    user.is_active = active
    revoked = 0 if active else revoke_sessions(db, user.id)
    audit.record(db, actor, "user.activate" if active else "user.deactivate", "user", user.id,
                 f"{'Reactivated' if active else 'Deactivated'} {user.username}"
                 + (f"; revoked {revoked} session(s)" if revoked else ""))
    db.commit()
    return user


def reset_password(db: Session, settings: Settings, actor: User, user_id, password: str) -> None:
    user = get_or_404(db, User, user_id, "User")
    _check_password(settings, password)
    user.password_hash = hash_password(password)
    revoked = revoke_sessions(db, user.id)
    audit.record(db, actor, "user.password_reset", "user", user.id,
                 f"Reset password for {user.username}; revoked {revoked} session(s)")
    db.commit()


def change_own_password(db: Session, settings: Settings, user: User, current: str, new: str) -> None:
    if not verify_password(user.password_hash, current or ""):
        raise DomainError("Current password is incorrect.")
    _check_password(settings, new)
    user.password_hash = hash_password(new)
    audit.record(db, user, "user.password_change", "user", user.id, "Changed own password")
    db.commit()
