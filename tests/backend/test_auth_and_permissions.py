from tests.backend.conftest import PASSWORD

PUBLIC = {"/api/v1/auth/login", "/api/v1/info", "/health"}


def test_every_protected_endpoint_requires_sign_in(app, api):
    paths = {p: ops for p, ops in app.openapi()["paths"].items() if p not in PUBLIC}
    assert sum(len(ops) for ops in paths.values()) > 40
    for template, ops in paths.items():
        path = template.replace("{key}", "departments")
        for part in ("asset_id", "req_id", "user_id", "item_id", "obj_id"):
            path = path.replace("{" + part + "}", "00000000-0000-0000-0000-000000000000")
        for method in ops:
            r = api.client.request(method, path, json={})
            assert r.status_code == 401, f"{method} {path} returned {r.status_code}"
            assert r.json()["error"]["code"] == "unauthenticated"


def test_login_failure_and_lockout(api):
    for _ in range(5):
        r = api.client.post("/api/v1/auth/login", json={"username": "teacher", "password": "wrong-password"})
        assert r.status_code == 401
    r = api.client.post("/api/v1/auth/login", json={"username": "teacher", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "locked"


def test_me_returns_permissions(api):
    me = api.ok("GET", "/auth/me", as_user="teacher")
    assert "borrowing.request" in me["permissions"] and "assets.create" not in me["permissions"]


def test_permission_denied_is_enforced_by_backend(api, world):
    r = api.post("/assets", {"name": "Laptop"}, as_user="teacher")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    r = api.post("/assets", {"name": "Laptop"}, as_user="auditor")
    assert r.status_code == 403
    assert api.get("/audit-logs", as_user="custodian").status_code == 403
    assert api.get("/audit-logs", as_user="auditor").status_code == 200
    assert api.get("/users", as_user="custodian").status_code == 403


def test_deactivating_user_revokes_sessions(api):
    token = api.login("teacher")
    users = {u["username"]: u for u in api.ok("GET", "/users")}
    api.ok("POST", f"/users/{users['teacher']['id']}/deactivate", {})
    r = api.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    r = api.client.post("/api/v1/auth/login", json={"username": "teacher", "password": PASSWORD})
    assert r.status_code == 401


def test_password_reset_revokes_sessions(api):
    token = api.login("teacher")
    users = {u["username"]: u for u in api.ok("GET", "/users")}
    api.ok("POST", f"/users/{users['teacher']['id']}/reset-password", {"password": "new-password-1"})
    assert api.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_logout_revokes_token(api):
    token = api.login("teacher")
    api.ok("POST", "/auth/logout", {}, as_user="teacher")
    assert api.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_role_changes_are_audited(api):
    users = {u["username"]: u for u in api.ok("GET", "/users")}
    api.ok("PATCH", f"/users/{users['teacher']['id']}", {"roles": ["employee", "auditor"]})
    logs = api.ok("GET", "/audit-logs")
    assert any(entry["action"] == "user.roles_change" for entry in logs)


def test_new_user_password_policy(api):
    r = api.post("/users", {"username": "x", "full_name": "X", "password": "short", "roles": ["employee"]})
    assert r.status_code == 400 and "at least 8" in r.json()["error"]["message"]
