"""Dashboard, reports, audit log, settings and server information."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saims import API_VERSION, APP_FULL_NAME, __version__
from saims.backend import audit
from saims.backend.api import serializers as ser
from saims.backend.api.deps import current_user, get_db, require
from saims.backend.api.schemas import SettingsIn
from saims.backend.errors import DomainError
from saims.backend.models import AuditLog, User
from saims.backend.services import reports
from saims.backend.services.common import put_setting, setting

router = APIRouter(tags=["system"])

SETTING_DEFAULTS = {"school_name": "Demo School", "currency_symbol": "$", "asset_code_prefix": "AST",
                    "item_code_prefix": "ITM"}


@router.get("/info")
def info(db: Session = Depends(get_db)):
    """Public: lets a client check the server and its API version before signing in."""
    return {"product": "SAIMS", "name": APP_FULL_NAME, "version": __version__, "api_version": API_VERSION,
            "school_name": setting(db, "school_name", SETTING_DEFAULTS["school_name"]),
            "demo": setting(db, "demo_mode", "0") == "1"}


@router.get("/dashboard")
def dashboard(user: User = Depends(require("dashboard.view")), db: Session = Depends(get_db)):
    return reports.dashboard(db, user)


@router.get("/reports")
def report_list(user: User = Depends(require("reports.view"))):
    return reports.available_reports(user)


@router.get("/reports/{key}")
def report(key: str, start: date | None = None, end: date | None = None, export: str | None = None,
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    if export:
        if "reports.export" not in user.permission_codes:
            from saims.backend.errors import PermissionDenied
            raise PermissionDenied("reports.export")
        if export not in {"csv", "xlsx", "pdf"}:
            raise DomainError("Export format must be csv, xlsx or pdf.")
    result = reports.run(db, user, key, start, end)
    if export:
        audit.record(db, db.merge(user), "report.export", "report", key,
                     f"Exported {result['title']} as {export.upper()} ({len(result['rows'])} rows)")
        db.commit()
    return result


@router.get("/audit-logs")
def audit_logs(q: str = "", entity_type: str | None = None, username: str | None = None,
               start: date | None = None, end: date | None = None, limit: int = 500,
               _=Depends(require("system.audit_logs.view")), db: Session = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 5000))
    if q:
        stmt = stmt.where(AuditLog.summary.ilike(f"%{q}%") | AuditLog.action.ilike(f"%{q}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if username:
        stmt = stmt.where(AuditLog.username == username)
    if start:
        stmt = stmt.where(func.date(AuditLog.created_at) >= start.isoformat())
    if end:
        stmt = stmt.where(func.date(AuditLog.created_at) <= end.isoformat())
    return [ser.audit_entry(a) for a in db.scalars(stmt)]


@router.get("/settings")
def get_settings_values(_=Depends(current_user), db: Session = Depends(get_db)):
    return {k: setting(db, k, v) for k, v in SETTING_DEFAULTS.items()}


@router.patch("/settings")
def update_settings(body: SettingsIn, user: User = Depends(require("system.settings")),
                    db: Session = Depends(get_db)):
    data = body.data()
    before = {k: setting(db, k, SETTING_DEFAULTS[k]) for k in data}
    for k, v in data.items():
        put_setting(db, k, (v or "").strip())
    audit.record(db, db.merge(user), "settings.update", "settings", "", "Updated system settings",
                 audit.diff(before, data))
    db.commit()
    return {k: setting(db, k, v) for k, v in SETTING_DEFAULTS.items()}
