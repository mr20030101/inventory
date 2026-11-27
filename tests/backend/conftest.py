import os
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.filterwarnings("ignore", category=DeprecationWarning)

from fastapi.testclient import TestClient  # noqa: E402

from saims.backend.config import Settings  # noqa: E402
from saims.backend.main import create_app  # noqa: E402
from saims.backend.models import Role, User  # noqa: E402
from saims.backend.security import hash_password  # noqa: E402
from saims.backend.services import reference  # noqa: E402
from sqlalchemy import select  # noqa: E402

PASSWORD = "password123"


class Api:
    """Test client that signs in as different users."""

    def __init__(self, client: TestClient):
        self.client = client
        self.tokens: dict[str, str] = {}

    def login(self, username: str) -> str:
        if username not in self.tokens:
            r = self.client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
            assert r.status_code == 200, r.text
            self.tokens[username] = r.json()["token"]
        return self.tokens[username]

    def call(self, method: str, path: str, as_user: str = "admin", **kw):
        headers = {"Authorization": f"Bearer {self.login(as_user)}"}
        return self.client.request(method, f"/api/v1{path}", headers=headers, **kw)

    def get(self, path, as_user="admin", **kw):
        return self.call("GET", path, as_user, **kw)

    def post(self, path, json=None, as_user="admin"):
        return self.call("POST", path, as_user, json=json or {})

    def ok(self, method, path, json=None, as_user="admin"):
        r = self.call(method, path, as_user, json=json) if json is not None else self.call(method, path, as_user)
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def app(tmp_path):
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", seed_demo_data=False)
    os.environ["SAIMS_ADMIN_PASSWORD"] = PASSWORD
    application = create_app(settings)
    with application.state.sessions() as db:
        roles = {r.code: r for r in db.scalars(select(Role))}
        for username, role in [("custodian", "custodian"), ("teacher", "employee"), ("head", "department_head"),
                               ("auditor", "auditor"), ("principal", "school_admin")]:
            db.add(User(username=username, full_name=username.title(), password_hash=hash_password(PASSWORD),
                        roles=[roles[role]]))
        db.commit()
    return application


@pytest.fixture
def api(app):
    return Api(TestClient(app))


@pytest.fixture
def world(app):
    """Minimal school structure: two rooms, two stores, an employee, categories."""
    with app.state.sessions() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        mk = lambda key, **d: reference.create(db, admin, key, d)  # noqa: E731
        dept = mk("departments", code="SCI", name="Science")
        dept2 = mk("departments", code="ICT", name="ICT")
        bld = mk("buildings", code="B1", name="Main")
        room1 = mk("rooms", code="R1", name="Lab 1", building_id=bld.id, department_id=dept.id)
        room2 = mk("rooms", code="R2", name="Lab 2", building_id=bld.id, department_id=dept2.id)
        store1 = mk("storage-locations", code="S1", name="Main store")
        store2 = mk("storage-locations", code="S2", name="Science store")
        emp = mk("employees", employee_no="E1", full_name="Ada Lovelace", department_id=dept.id)
        emp2 = mk("employees", employee_no="E2", full_name="Alan Turing", department_id=dept2.id)
        acat = mk("categories", kind="asset", name="IT Equipment")
        ccat = mk("categories", kind="consumable", name="Office Supplies")
        # The teacher account belongs to Ada (teachers see only their own assets and requests).
        db.scalar(select(User).where(User.username == "teacher")).employee_id = emp.id
        db.commit()
        return {k: str(v.id) for k, v in dict(dept=dept, dept2=dept2, room1=room1, room2=room2, store1=store1,
                                                store2=store2, emp=emp, emp2=emp2, acat=acat, ccat=ccat).items()}
