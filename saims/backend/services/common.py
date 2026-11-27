"""Small helpers shared by the domain services."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from saims.backend.errors import DomainError, NotFound
from saims.backend.models import Sequence, SystemSetting

T = TypeVar("T")


def get_or_404(db: Session, model: type[T], obj_id: Any, what: str | None = None) -> T:
    if obj_id is None:
        raise NotFound(what or model.__name__)
    if not isinstance(obj_id, UUID):
        try:
            obj_id = UUID(str(obj_id))
        except ValueError:
            raise NotFound(what or model.__name__) from None
    obj = db.get(model, obj_id)
    if obj is None:
        raise NotFound(what or model.__name__)
    return obj


def optional(db: Session, model: type[T], obj_id: Any, what: str) -> T | None:
    return None if obj_id in (None, "") else get_or_404(db, model, obj_id, what)


def next_number(db: Session, name: str) -> int:
    """Increment and return a named counter inside the caller's transaction."""
    seq = db.execute(select(Sequence).where(Sequence.name == name).with_for_update()).scalar_one_or_none()
    if seq is None:
        seq = Sequence(name=name, value=0)
        db.add(seq)
    seq.value += 1
    db.flush()
    return seq.value


def setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(SystemSetting, key)
    return row.value if row else default


def put_setting(db: Session, key: str, value: str) -> None:
    row = db.get(SystemSetting, key)
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))


def quantity(value: Any, label: str = "Quantity", allow_zero: bool = False) -> Decimal:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise DomainError(f"{label} must be a number.") from None
    if not number.is_finite():
        raise DomainError(f"{label} must be a number.")
    if number < 0 or (number == 0 and not allow_zero):
        raise DomainError(f"{label} must be greater than zero." if not allow_zero else f"{label} cannot be negative.")
    if number != round(number, 3):
        raise DomainError(f"{label} can have at most 3 decimal places.")
    return number


def money(value: Any, label: str = "Amount") -> Decimal:
    try:
        number = Decimal(str(value if value not in (None, "") else "0").strip())
    except (InvalidOperation, ValueError):
        raise DomainError(f"{label} must be a number.") from None
    if not number.is_finite() or number < 0:
        raise DomainError(f"{label} cannot be negative.")
    return number.quantize(Decimal("0.01"))


def required(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DomainError(f"{label} is required.")
    return text


def now() -> datetime:
    return datetime.now(timezone.utc)


def as_uuid(value: Any, label: str = "id") -> UUID | None:
    """Coerce an optional id from a request to a UUID (None stays None)."""
    if value in (None, ""):
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        raise DomainError(f"Invalid {label}.") from None


def as_uuids(values: Any, label: str = "id") -> list[UUID]:
    """Filter helper: one id or a list of ids (repeated query parameters) → UUIDs; blanks are ignored."""
    if values in (None, ""):
        return []
    items = values if isinstance(values, (list, tuple, set)) else [values]
    return [as_uuid(v, label) for v in items if v not in (None, "")]


def as_list(values: Any) -> list[str]:
    if values in (None, ""):
        return []
    items = values if isinstance(values, (list, tuple, set)) else [values]
    return [str(v) for v in items if v not in (None, "")]


def commit(db: Session) -> None:
    """Commit the service's change, unless it runs inside all_or_nothing() (then the whole batch commits once)."""
    if db.info.get("batch"):
        db.flush()
    else:
        db.commit()


@contextmanager
def all_or_nothing(db: Session, labels: Iterable[str] | None = None):
    """Run several service calls as one transaction: either every change is saved or none is.

    Yields a function to call before each item with that item's label (e.g. an asset code); if the item fails,
    the error says which one and that nothing was changed."""
    current = {"label": ""}

    def item(label: str) -> None:
        current["label"] = label

    db.info["batch"] = True
    try:
        yield item
        db.info.pop("batch", None)
        db.commit()
    except DomainError as exc:
        db.info.pop("batch", None)
        db.rollback()
        prefix = f"{current['label']}: " if current["label"] else ""
        exc.message = f"{prefix}{exc.message} Nothing was changed."
        exc.args = (exc.message,)
        raise
    except BaseException:
        db.info.pop("batch", None)
        db.rollback()
        raise
