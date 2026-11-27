"""FastAPI application factory.

Run the server:  python -m saims.backend   (see README for production settings)
"""
from __future__ import annotations

import html
import logging
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select

from saims import API_VERSION, APP_FULL_NAME, __version__
from saims.backend.api.v1 import assets, auth, borrowing, reference, stock, system, users
from saims.backend.config import Settings
from saims.backend.database import make_engine, make_session_factory
from saims.backend.errors import DomainError
from saims.backend.migrate import upgrade
from saims.backend.models import User
from saims.backend.security import hash_password
from saims.backend.services.auth import ensure_roles
from saims.backend.services.common import put_setting, setting

log = logging.getLogger("saims")
MAX_BODY_BYTES = 2 * 1024 * 1024


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def initialise(sessions, settings: Settings) -> None:
    """Permissions, default roles, and a first administrator on an empty database."""
    with sessions() as db:
        ensure_roles(db)
        if db.scalar(select(func.count()).select_from(User)) == 0:
            if settings.seed_demo_data:
                from saims.backend.seed import seed_demo
                seed_demo(db)
                return
            from saims.backend.models import Role
            password = os.environ.get("SAIMS_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            role = db.scalar(select(Role).where(Role.code == "super_admin"))
            db.add(User(username="admin", full_name="System Administrator", password_hash=hash_password(password),
                        roles=[role]))
            db.commit()
            if not os.environ.get("SAIMS_ADMIN_PASSWORD"):
                log.warning("Created the first administrator. Username: admin  Password: %s  "
                            "(change it after signing in)", password)
        if not setting(db, "school_name"):
            put_setting(db, "school_name", "Demo School")
            db.commit()


_LANDING = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>SAIMS server</title>
<style>body{{font-family:system-ui,sans-serif;background:#d3e5ec;color:#1f3b47;margin:0;padding:48px 16px}}
main{{max-width:560px;margin:auto;background:#f5fafc;border:1px solid #c5dae2;border-radius:12px;padding:28px}}
h1{{margin:0 0 4px;color:#1f4a5a}} .ok{{color:#2e7d5b;font-weight:600}} code{{background:#e4f0f4;padding:2px 6px;
border-radius:4px}} .muted{{color:#5e7a86;font-size:.9em}}</style></head><body><main>
<h1>SAIMS</h1><p class="muted">{school}</p>
<p class="ok">&#10003; The SAIMS server is running and this computer can reach it.</p>
<p>SAIMS is used through the SAIMS desktop app (a web version is planned). In the app, choose
<b>School server…</b> on the sign-in screen and enter:</p><p><code>{address}</code></p>
<p class="muted">The first time, the app shows a security code: check it matches the one shown on the sharing
computer (user menu &#9656; Share on the local network…). Version {version}.</p></main></body></html>"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    upgrade(settings.database_url)
    engine = make_engine(settings.database_url)
    sessions = make_session_factory(engine)
    initialise(sessions, settings)

    app = FastAPI(title=f"SAIMS API — {APP_FULL_NAME}", version=__version__,
                  docs_url=f"/api/{API_VERSION}/docs", openapi_url=f"/api/{API_VERSION}/openapi.json", redoc_url=None)
    app.state.settings, app.state.engine, app.state.sessions = settings, engine, sessions

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return _error(413, "too_large", "Request is too large.")
        return await call_next(request)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError):
        return _error(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
        return _error(422, "validation", f"{field.replace('_', ' ').capitalize()}: {first.get('msg', 'is invalid')}")

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception):
        log.exception("Unhandled error")
        return _error(500, "server_error", "Unexpected server error. It has been logged.")

    prefix = f"/api/{API_VERSION}"
    for module in (auth, users, reference, assets, stock, borrowing, system):
        app.include_router(module.router, prefix=prefix)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def landing(request: Request):
        """What a web browser shows at the server address: confirms it is reachable and how to connect."""
        with app.state.sessions() as db:
            school = setting(db, "school_name", "")
        address = html.escape(str(request.base_url).rstrip("/"))
        return _LANDING.format(school=html.escape(school), address=address, version=__version__)

    return app
