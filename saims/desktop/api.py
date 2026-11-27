"""HTTP client for the SAIMS API. Every screen goes through this; nothing touches the database."""
from __future__ import annotations

import ssl
import uuid
from typing import Any

import httpx

from saims import API_VERSION, __version__, tls


class ApiError(Exception):
    def __init__(self, message: str, code: str = "error", status: int = 0):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


class Api:
    def __init__(self, base_url: str, verify: ssl.SSLContext | bool = True):
        """`verify`: True checks HTTPS certificates against the system's authorities; an SSL context pins the
        certificate of a server shared on the local network (see saims/tls.py)."""
        self.token: str | None = None
        self.me: dict[str, Any] = {}
        self._cache: dict[str, Any] = {}
        self._http: httpx.Client | None = None
        self.rebase(base_url, verify)
        self.on_session_expired = None  # callback set by the main window

    def rebase(self, base_url: str, verify: ssl.SSLContext | bool = True) -> None:
        """Point at a new address (e.g. the built-in server restarted to share on the network); the session stays."""
        if self._http is not None:
            self._http.close()
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=f"{self.base_url}/api/{API_VERSION}", timeout=30.0, verify=verify,
                                  headers={"User-Agent": f"SAIMS-Desktop/{__version__}"})

    # ------------------------------------------------------------- transport
    def request(self, method: str, path: str, *, json: Any = None, params: dict | None = None,
                raw: bool = False) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        if params:
            params = {k: v for k, v in params.items() if v not in (None, "", False)}
        try:
            resp = self._http.request(method, path, json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:
            if tls.is_certificate_error(exc):
                raise ApiError(f"The server at {self.base_url} did not present a security certificate this "
                               "computer trusts.", "untrusted_certificate") from None
            raise ApiError(f"Cannot reach the SAIMS server at {self.base_url}.\n{exc}", "network") from None
        if resp.status_code >= 400:
            try:
                err = resp.json()["error"]
                message, code = err["message"], err["code"]
            except Exception:  # noqa: BLE001 - non-JSON error page
                message, code = f"Server error ({resp.status_code}).", "http"
            if resp.status_code == 401 and self.token and code == "unauthenticated" and self.on_session_expired:
                self.on_session_expired()
            raise ApiError(message, code, resp.status_code)
        if method != "GET":
            self._cache.clear()
        return resp.content if raw else resp.json()

    def get(self, path: str, **params) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, json: Any = None) -> Any:
        return self.request("POST", path, json=json or {})

    def patch(self, path: str, json: Any) -> Any:
        return self.request("PATCH", path, json=json)

    # ------------------------------------------------------------- session
    def info(self) -> dict[str, Any]:
        return self.get("/info")

    def login(self, username: str, password: str) -> dict[str, Any]:
        data = self.post("/auth/login", {"username": username, "password": password})
        self.token, self.me = data["token"], data["user"]
        return self.me

    def logout(self) -> None:
        if self.token:
            try:
                self.post("/auth/logout")
            except ApiError:
                pass
        self.token, self.me = None, {}
        self._cache.clear()

    def can(self, *permissions: str) -> bool:
        held = set(self.me.get("permissions", []))
        return all(p in held for p in permissions)

    def can_any(self, *permissions: str) -> bool:
        held = set(self.me.get("permissions", []))
        return any(p in held for p in permissions)

    # ------------------------------------------------------------- lookups (cached until the next change)
    def lookup(self, key: str, **params) -> list[dict[str, Any]]:
        cache_key = f"{key}?{sorted(params.items())}"
        if cache_key not in self._cache:
            try:
                self._cache[cache_key] = self.get(f"/ref/{key}", **params)
            except ApiError as exc:
                if exc.status == 403:
                    return []
                raise
        return self._cache[cache_key]

    def settings(self) -> dict[str, str]:
        if "settings" not in self._cache:
            self._cache["settings"] = self.get("/settings")
        return self._cache["settings"]

    @staticmethod
    def request_id() -> str:
        return uuid.uuid4().hex
