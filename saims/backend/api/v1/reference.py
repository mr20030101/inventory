"""Departments, buildings, rooms, storage locations, employees, suppliers and categories."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from saims.backend.api import serializers as ser
from saims.backend.api.deps import current_user, get_db
from saims.backend.api.schemas import ReferenceIn
from saims.backend.errors import PermissionDenied
from saims.backend.models import User
from saims.backend.services import reference

router = APIRouter(tags=["reference data"])

# key: (permissions that allow viewing — any one is enough, permission to manage)
ACCESS = {
    "departments": (("departments.view", "assets.view", "inventory.view", "borrowing.request"), "departments.manage"),
    "buildings": (("locations.view", "assets.view"), "locations.manage"),
    "rooms": (("locations.view", "assets.view", "maintenance.view"), "locations.manage"),
    "storage-locations": (("locations.view", "inventory.view"), "locations.manage"),
    "employees": (("employees.view", "borrowing.request", "assets.assign", "inventory.issue"), "employees.manage"),
    "suppliers": (("suppliers.view", "inventory.receive", "assets.create"), "suppliers.manage"),
    "categories": (("assets.view", "inventory.view"), "categories.manage"),
}


def _can_view(user: User, key: str) -> None:
    perms = ACCESS[key][0]
    if not user.permission_codes.intersection(perms):
        raise PermissionDenied(perms[0])


def _can_manage(user: User, key: str) -> None:
    if ACCESS[key][1] not in user.permission_codes:
        raise PermissionDenied(ACCESS[key][1])


@router.get("/ref/{key}")
def list_records(key: str, include_inactive: bool = False, kind: str | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    if key not in ACCESS:
        from saims.backend.errors import NotFound
        raise NotFound("List")
    _can_view(user, key)
    return [ser.reference(o) for o in reference.list_records(db, key, include_inactive, kind)]


@router.post("/ref/{key}")
def create(key: str, body: ReferenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _can_manage(user, key)
    return ser.reference(reference.create(db, db.merge(user), key, body.model_dump()))


@router.patch("/ref/{key}/{obj_id}")
def update(key: str, obj_id: str, body: ReferenceIn, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    _can_manage(user, key)
    return ser.reference(reference.update(db, db.merge(user), key, obj_id, body.model_dump()))


@router.post("/ref/{key}/{obj_id}/archive")
def archive(key: str, obj_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _can_manage(user, key)
    return ser.reference(reference.set_active(db, db.merge(user), key, obj_id, False))


@router.post("/ref/{key}/{obj_id}/restore")
def restore(key: str, obj_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _can_manage(user, key)
    return ser.reference(reference.set_active(db, db.merge(user), key, obj_id, True))
