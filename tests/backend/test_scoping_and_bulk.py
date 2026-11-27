"""Teacher self-service scope, built-in role upgrades, bulk (all-or-nothing) actions and multi-value filters."""
from datetime import date, timedelta

from sqlalchemy import select

from saims.backend.models import AuditLog, Role, StockMovement, SystemSetting
from saims.backend.services import auth


def new_asset(api, world, name="Camera"):
    return api.ok("POST", "/assets", {"name": name, "room_id": world["room1"]}, as_user="custodian")


def due(days=3):
    return (date.today() + timedelta(days=days)).isoformat()


# ------------------------------------------------------------------ teacher scope
def test_teacher_sees_only_own_assets(api, world):
    mine, other = new_asset(api, world, "Laptop A"), new_asset(api, world, "Laptop B")
    api.ok("POST", f"/assets/{mine['id']}/assign", {"employee_id": world["emp"]}, as_user="custodian")
    api.ok("POST", f"/assets/{other['id']}/assign", {"employee_id": world["emp2"]}, as_user="custodian")
    listed = api.ok("GET", "/assets", as_user="teacher")
    assert [a["id"] for a in listed] == [mine["id"]]
    assert api.get(f"/assets/{mine['id']}", as_user="teacher").status_code == 200
    assert api.get(f"/assets/{other['id']}", as_user="teacher").status_code == 404  # not revealed
    assert api.get(f"/assets/{other['id']}/qr.png", as_user="teacher").status_code == 404
    assert api.get("/stock/items", as_user="teacher").status_code == 403
    dash = api.ok("GET", "/dashboard", as_user="teacher")
    assert [a["id"] for a in dash["my_assets"]] == [mine["id"]]


def test_teacher_requests_only_for_self_and_sees_only_own(api, world):
    a, b = new_asset(api, world, "Tablet"), new_asset(api, world, "Tripod")
    catalogue = api.ok("GET", "/borrowing/catalogue", as_user="teacher")
    assert {"id", "asset_code", "name", "status_label"} <= set(catalogue[0]) and "acquisition_cost" not in catalogue[0]
    # No borrower given: it is the teacher's own employee record.
    own = api.ok("POST", "/borrowing", {"asset_id": a["id"], "expected_return": due()}, as_user="teacher")
    assert own["borrower"] == "Ada Lovelace"
    r = api.post("/borrowing", {"asset_id": a["id"], "borrower_id": world["emp2"], "expected_return": due()},
                 as_user="teacher")
    assert r.status_code == 400 and "yourself" in r.json()["error"]["message"]
    # Someone else's request is invisible to the teacher and cannot be cancelled by them.
    theirs = api.ok("POST", "/borrowing", {"asset_id": b["id"], "borrower_id": world["emp2"],
                                           "expected_return": due()}, as_user="custodian")
    assert [x["id"] for x in api.ok("GET", "/borrowing", as_user="teacher")] == [own["id"]]
    assert api.post(f"/borrowing/{theirs['id']}/cancel", as_user="teacher").status_code == 404
    assert len(api.ok("GET", "/borrowing", as_user="custodian")) == 2


def test_builtin_roles_upgrade_on_existing_database(app):
    with app.state.sessions() as db:
        role = db.scalar(select(Role).where(Role.code == "employee"))
        role.permissions = [p for p in db.scalars(select(Role).where(Role.code == "auditor")).one().permissions]
        db.get(SystemSetting, "roles_version").value = "1"
        db.commit()
        auth.ensure_roles(db)
        role = db.scalar(select(Role).where(Role.code == "employee"))
        assert {p.code for p in role.permissions} == {"dashboard.view", "assets.view_own", "borrowing.view_own",
                                                      "borrowing.request"}
        assert db.scalar(select(AuditLog).where(AuditLog.action == "role.update")) is not None


# ------------------------------------------------------------------ bulk actions
def test_bulk_assign_is_all_or_nothing(api, world):
    ids = [new_asset(api, world, f"Laptop {i}")["id"] for i in range(3)]
    api.ok("POST", f"/assets/{ids[1]}/lifecycle", {"action": "send_to_maintenance"}, as_user="custodian")
    r = api.post("/assets/bulk", {"action": "assign", "asset_ids": ids, "employee_id": world["emp"]},
                 as_user="custodian")
    assert r.status_code == 409
    message = r.json()["error"]["message"]
    assert "Nothing was changed" in message and message.startswith(api.ok("GET", f"/assets/{ids[1]}")["asset_code"])
    statuses = {api.ok("GET", f"/assets/{i}")["status"] for i in (ids[0], ids[2])}
    assert statuses == {"available"}  # the first asset was rolled back too
    ok = api.ok("POST", "/assets/bulk", {"action": "assign", "asset_ids": [ids[0], ids[2]],
                                         "employee_id": world["emp"]}, as_user="custodian")
    assert ok["updated"] == 2
    assert {api.ok("GET", f"/assets/{i}")["status"] for i in (ids[0], ids[2])} == {"assigned"}


def test_bulk_lifecycle_checks_permission(api, world):
    ids = [new_asset(api, world, f"Chair {i}")["id"] for i in range(2)]
    body = {"action": "lifecycle", "lifecycle_action": "retire", "asset_ids": ids, "reason": "Broken"}
    assert api.post("/assets/bulk", body, as_user="custodian").status_code == 403  # custodian cannot retire
    assert api.ok("POST", "/assets/bulk", body, as_user="principal")["updated"] == 2


def test_bulk_decisions(api, world):
    reqs = [api.ok("POST", "/borrowing", {"asset_id": new_asset(api, world, f"Cam {i}")["id"],
                                          "expected_return": due()}, as_user="teacher") for i in range(2)]
    ids = [r["id"] for r in reqs]
    r = api.post("/borrowing/decisions", {"request_ids": ids, "approve": False}, as_user="head")
    assert r.status_code == 400  # rejection needs a reason
    assert api.ok("POST", "/borrowing/decisions", {"request_ids": ids, "approve": True}, as_user="head")["updated"] == 2
    assert {r["status"] for r in api.ok("GET", "/borrowing", as_user="head")} == {"approved"}


def test_borrow_several_items_in_one_request(api, world):
    ids = [new_asset(api, world, n)["id"] for n in ("Camera", "Tripod")]
    made = api.ok("POST", "/borrowing/batch", {"asset_ids": ids, "purpose": "Sports day", "expected_return": due()},
                  as_user="teacher")
    assert len(made) == 2 and {m["purpose"] for m in made} == {"Sports day"}
    api.ok("POST", f"/assets/{ids[0]}/lifecycle", {"action": "mark_missing", "reason": "Lost"}, as_user="custodian")
    r = api.post("/borrowing/batch", {"asset_ids": ids, "expected_return": due()}, as_user="teacher")
    assert r.status_code == 409 and len(api.ok("GET", "/borrowing", as_user="teacher")) == 2


# ------------------------------------------------------------------ filters and batch stock movements
def test_multi_value_filters(api, world):
    a, b, c = (new_asset(api, world, n) for n in ("A", "B", "C"))
    api.ok("POST", f"/assets/{a['id']}/assign", {"employee_id": world["emp"]}, as_user="custodian")
    api.ok("POST", f"/assets/{b['id']}/lifecycle", {"action": "send_to_maintenance"}, as_user="custodian")
    got = api.ok("GET", "/assets?status=assigned&status=under_maintenance")
    assert {x["id"] for x in got} == {a["id"], b["id"]}
    assert {x["id"] for x in api.ok("GET", "/assets?status=available")} == {c["id"]}


def test_issue_several_items_in_one_transaction(api, world):
    items = [api.ok("POST", "/stock/items", {"name": n, "unit_of_measure": "box", "category_id": world["ccat"]},
                    as_user="custodian")["id"] for n in ("Chalk", "Markers")]
    for i in items:
        api.ok("POST", "/stock/movements", {"movement_type": "RECEIPT", "item_id": i, "location_id": world["store1"],
                                            "quantity": "10", "unit_cost": "2"}, as_user="custodian")
    body = {"movement_type": "ISSUE", "location_id": world["store1"], "department_id": world["dept"],
            "reference": "REQ-1", "request_id": "batch-abc",
            "lines": [{"item_id": items[0], "quantity": "3"}, {"item_id": items[1], "quantity": "50"}]}
    r = api.post("/stock/movements/batch", body, as_user="custodian")
    assert r.status_code == 409 and r.json()["error"]["message"].startswith("Markers")
    assert [x["on_hand"] for x in api.ok("GET", "/stock/items")] == ["10", "10"]  # chalk untouched
    body["lines"][1]["quantity"] = "4"
    first = api.ok("POST", "/stock/movements/batch", body, as_user="custodian")
    again = api.ok("POST", "/stock/movements/batch", body, as_user="custodian")  # double-click / retry
    assert len(first) == 2 and {m["id"] for m in again} == {m["id"] for m in first}
    on_hand = {x["name"]: x["on_hand"] for x in api.ok("GET", "/stock/items")}
    assert on_hand == {"Chalk": "7", "Markers": "6"}
    assert api.ok("GET", "/stock/reconcile")["consistent"]


def test_stock_movement_request_ids_fit(app):
    """Batch request ids (id-line:split) fit the column."""
    with app.state.sessions():
        assert StockMovement.__table__.c.request_id.type.length >= 50 + len("-199:9")


def test_browser_landing_page(api):
    r = api.client.get("/")
    assert r.status_code == 200 and "SAIMS server is running" in r.text and "School server" in r.text
