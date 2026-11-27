def register(api, world, **extra):
    data = {"name": "Laptop", "category_id": world["acat"], "room_id": world["room1"], "acquisition_cost": "780.50"}
    data.update(extra)
    return api.ok("POST", "/assets", data, as_user="custodian")


def test_register_generates_code_and_history(api, world):
    a = register(api, world, serial_number="SN-1")
    assert a["asset_code"].startswith("AST-") and a["status"] == "available"
    assert a["acquisition_cost"] == "780.50" and a["department"] == "Science"
    detail = api.ok("GET", f"/assets/{a['id']}")
    assert detail["history"][0]["event_type"] == "registered"


def test_duplicate_code_and_serial_rejected(api, world):
    register(api, world, asset_code="X-1", serial_number="SN-1")
    r = api.post("/assets", {"name": "Other", "asset_code": "X-1"}, as_user="custodian")
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_code"
    r = api.post("/assets", {"name": "Other", "serial_number": "SN-1"}, as_user="custodian")
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_serial"


def test_assign_and_return(api, world):
    a = register(api, world)
    api.ok("POST", f"/assets/{a['id']}/assign", {"employee_id": world["emp"], "acknowledged": True}, as_user="custodian")
    detail = api.ok("GET", f"/assets/{a['id']}")
    assert detail["status"] == "assigned" and detail["custodian"] == "Ada Lovelace"
    # cannot assign an asset that is already assigned
    r = api.post(f"/assets/{a['id']}/assign", {"employee_id": world["emp2"]}, as_user="custodian")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_status"
    api.ok("POST", f"/assets/{a['id']}/return", {"condition": "fair"}, as_user="custodian")
    detail = api.ok("GET", f"/assets/{a['id']}")
    assert detail["status"] == "available" and detail["condition"] == "fair"
    assert len(detail["assignments"]) == 1 and detail["assignments"][0]["returned_at"]


def test_transfer_records_source_and_destination(api, world):
    a = register(api, world)
    api.ok("POST", f"/assets/{a['id']}/transfer", {"room_id": world["room2"], "reason": "Moved"}, as_user="custodian")
    detail = api.ok("GET", f"/assets/{a['id']}")
    assert detail["room"] == "Lab 2" and detail["department"] == "ICT"
    assert "Lab 1 → Lab 2" in detail["history"][0]["description"]
    r = api.post(f"/assets/{a['id']}/transfer", {"room_id": world["room2"]}, as_user="custodian")
    assert r.status_code == 400  # reason required


def test_lifecycle_rules(api, world):
    a = register(api, world)
    r = api.post(f"/assets/{a['id']}/lifecycle", {"action": "dispose", "reason": "x"}, as_user="principal")
    assert r.status_code == 409  # must be retired first
    r = api.post(f"/assets/{a['id']}/lifecycle", {"action": "mark_missing"}, as_user="custodian")
    assert r.status_code == 400  # reason required
    api.ok("POST", f"/assets/{a['id']}/lifecycle", {"action": "mark_missing", "reason": "Not found"}, as_user="custodian")
    api.ok("POST", f"/assets/{a['id']}/lifecycle", {"action": "recover"}, as_user="custodian")
    api.ok("POST", f"/assets/{a['id']}/lifecycle", {"action": "retire", "reason": "Old"}, as_user="principal")
    # custodians cannot dispose (no assets.dispose permission)
    r = api.post(f"/assets/{a['id']}/lifecycle", {"action": "dispose", "reason": "Recycled"}, as_user="custodian")
    assert r.status_code == 403
    api.ok("POST", f"/assets/{a['id']}/lifecycle", {"action": "dispose", "reason": "Recycled"}, as_user="principal")
    detail = api.ok("GET", f"/assets/{a['id']}")
    assert detail["status"] == "disposed"
    assert [e["event_type"] for e in detail["history"]][:2] == ["disposed", "retired"]
    assert api.call("DELETE", f"/assets/{a['id']}").status_code == 405  # no physical deletion


def test_employee_with_assets_cannot_be_archived(api, world):
    a = register(api, world)
    api.ok("POST", f"/assets/{a['id']}/assign", {"employee_id": world["emp"]}, as_user="custodian")
    r = api.post(f"/ref/employees/{world['emp']}/archive", as_user="custodian")
    assert r.status_code == 409 and "still has assigned assets" in r.json()["error"]["message"]


def test_qr_code(api, world):
    a = register(api, world)
    r = api.get(f"/assets/{a['id']}/qr.png")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"


def test_asset_actions_are_audited(api, world):
    a = register(api, world)
    api.ok("POST", f"/assets/{a['id']}/assign", {"employee_id": world["emp"]}, as_user="custodian")
    actions = [e["action"] for e in api.ok("GET", "/audit-logs")]
    assert "asset.create" in actions and "asset.assign" in actions
