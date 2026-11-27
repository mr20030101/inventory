"""Append-only audit trail helper."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from saims.backend.models import AuditLog, User


def _plain(value: Any) -> Any:
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def snapshot(obj: Any, fields: list[str]) -> dict[str, Any]:
    return {f: _plain(getattr(obj, f)) for f in fields}


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {k: {"from": before.get(k), "to": v} for k, v in after.items() if before.get(k) != v}


def record(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: Any = "",
    summary: str = "",
    changes: dict[str, Any] | None = None,
    success: bool = True,
) -> None:
    """Add an audit entry to the current transaction (committed together with the change)."""
    db.add(AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        summary=summary,
        changes=json.dumps(changes, default=str) if changes else "",
        success=success,
    ))
