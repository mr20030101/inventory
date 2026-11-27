from datetime import date, timedelta


def item(api, world, **extra):
    data = {"name": "A4 paper", "category_id": world["ccat"], "unit_of_measure": "ream", "reorder_level": "10"}
    data.update(extra)
    return api.ok("POST", "/stock/items", data, as_user="custodian")


def move(api, world, item_id, kind, qty, store="store1", as_user="custodian", **extra):
    body = {"movement_type": kind, "item_id": item_id, "location_id": world[store], "quantity": str(qty), **extra}
    return api.post("/stock/movements", body, as_user=as_user)


def on_hand(api, item_id):
    return next(i for i in api.ok("GET", "/stock/items") if i["id"] == item_id)["on_hand"]


def test_receive_issue_and_balance(api, world):
    it = item(api, world)
    assert move(api, world, it["id"], "RECEIPT", "20", unit_cost="5.00").status_code == 200
    assert move(api, world, it["id"], "ISSUE", "2.5", department_id=world["dept"]).status_code == 200
    assert on_hand(api, it["id"]) == "17.5"


def test_issue_more_than_available_rejected(api, world):
    it = item(api, world)
    move(api, world, it["id"], "RECEIPT", 5, unit_cost="1")
    r = move(api, world, it["id"], "ISSUE", 6, department_id=world["dept"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    assert on_hand(api, it["id"]) == "5"


def test_adjustment_needs_reason_and_permission(api, world):
    it = item(api, world)
    move(api, world, it["id"], "RECEIPT", 5, unit_cost="1")
    assert move(api, world, it["id"], "ADJUSTMENT_OUT", 1).status_code == 400
    assert move(api, world, it["id"], "ADJUSTMENT_OUT", 1, as_user="teacher", reason="x").status_code == 403
    assert move(api, world, it["id"], "ADJUSTMENT_OUT", 1, reason="Count").status_code == 200


def test_weighted_average_cost(api, world):
    it = item(api, world)
    move(api, world, it["id"], "RECEIPT", 10, unit_cost="4.00")
    move(api, world, it["id"], "RECEIPT", 10, unit_cost="6.00")
    row = next(i for i in api.ok("GET", "/stock/items") if i["id"] == it["id"])
    assert row["average_cost"] == "5" and row["value"] == "100.00"


def test_transfer_is_atomic_and_keeps_total(api, world):
    it = item(api, world)
    move(api, world, it["id"], "RECEIPT", 10, unit_cost="1")
    r = api.post("/stock/transfers", {"item_id": it["id"], "from_location_id": world["store1"],
                                      "to_location_id": world["store2"], "quantity": "4"}, as_user="custodian")
    assert r.status_code == 200
    bal = {b["location"]: b["quantity"] for b in api.ok("GET", f"/stock/balances?item_id={it['id']}")}
    assert bal == {"Main store": "6", "Science store": "4"} and on_hand(api, it["id"]) == "10"
    r = api.post("/stock/transfers", {"item_id": it["id"], "from_location_id": world["store1"],
                                      "to_location_id": world["store2"], "quantity": "7"}, as_user="custodian")
    assert r.status_code == 409
    assert api.ok("GET", "/stock/reconcile")["consistent"]


def test_batches_issue_earliest_expiry_first(api, world):
    it = item(api, world, name="Gloves", track_expiry=True)
    assert move(api, world, it["id"], "RECEIPT", 5, unit_cost="1").status_code == 400  # batch required
    soon = (date.today() + timedelta(days=10)).isoformat()
    later = (date.today() + timedelta(days=300)).isoformat()
    move(api, world, it["id"], "RECEIPT", 5, unit_cost="1", batch_no="LATE", expiry_date=later)
    move(api, world, it["id"], "RECEIPT", 3, unit_cost="1", batch_no="SOON", expiry_date=soon)
    r = move(api, world, it["id"], "ISSUE", 4, department_id=world["dept"])
    assert [(m["batch_no"], m["quantity"]) for m in r.json()] == [("SOON", "3"), ("LATE", "1")]
    assert any(e["batch_no"] == "SOON" for e in api.ok("GET", "/stock/expiring")) is False  # SOON now empty
    assert api.ok("GET", "/stock/reconcile")["consistent"]


def test_duplicate_submission_is_idempotent(api, world):
    it = item(api, world)
    for _ in range(2):
        assert move(api, world, it["id"], "RECEIPT", 5, unit_cost="1", request_id="abc-123").status_code == 200
    assert on_hand(api, it["id"]) == "5"


def test_opening_balance_only_first(api, world):
    it = item(api, world)
    assert move(api, world, it["id"], "OPENING", 5, unit_cost="1").status_code == 200
    r = move(api, world, it["id"], "OPENING", 5, unit_cost="1")
    assert r.status_code == 409


# ---------------------------------------------------------------- borrowing
def asset(api, world):
    return api.ok("POST", "/assets", {"name": "Camera", "room_id": world["room1"]}, as_user="custodian")


def request(api, world, asset_id, as_user="teacher"):
    return api.post("/borrowing", {"asset_id": asset_id, "borrower_id": world["emp"],
                                   "expected_return": (date.today() + timedelta(days=3)).isoformat()},
                    as_user=as_user)


def test_borrowing_workflow(api, world):
    a = asset(api, world)
    req = request(api, world, a["id"]).json()
    assert req["status"] == "pending"
    assert api.post(f"/borrowing/{req['id']}/release", {"condition": "good"}, as_user="custodian").status_code == 409
    api.ok("POST", f"/borrowing/{req['id']}/decision", {"approve": True}, as_user="head")
    api.ok("POST", f"/borrowing/{req['id']}/release", {"condition": "good"}, as_user="custodian")
    assert api.ok("GET", f"/assets/{a['id']}")["status"] == "borrowed"
    # borrowing an asset that is already out is rejected at release
    second = request(api, world, a["id"]).json()
    api.ok("POST", f"/borrowing/{second['id']}/decision", {"approve": True}, as_user="head")
    r = api.post(f"/borrowing/{second['id']}/release", {"condition": "good"}, as_user="custodian")
    assert r.status_code == 409 and r.json()["error"]["code"] == "asset_unavailable"
    api.ok("POST", f"/borrowing/{req['id']}/return", {"condition": "damaged", "note": "Cracked lens"},
           as_user="custodian")
    assert api.ok("GET", f"/assets/{a['id']}")["status"] == "damaged"


def test_cannot_approve_own_request(api, world):
    a = asset(api, world)
    req = request(api, world, a["id"], as_user="head").json()
    r = api.post(f"/borrowing/{req['id']}/decision", {"approve": True}, as_user="head")
    assert r.status_code == 409 and r.json()["error"]["code"] == "separation_of_duties"


def test_reject_needs_reason(api, world):
    a = asset(api, world)
    req = request(api, world, a["id"]).json()
    assert api.post(f"/borrowing/{req['id']}/decision", {"approve": False}, as_user="head").status_code == 400


def test_dashboard_respects_permissions(api, world):
    # Teachers get a personal dashboard: no school-wide figures, values or other people's records.
    teacher = api.ok("GET", "/dashboard", as_user="teacher")
    assert "assets" not in teacher and "consumables" not in teacher and "borrowing" not in teacher
    assert "my_assets" in teacher and "my_borrowing" in teacher
    custodian = api.ok("GET", "/dashboard", as_user="custodian")
    assert "assets" in custodian and "consumables" in custodian
    assert api.get("/dashboard", as_user="admin").status_code == 200
    reports = [r["key"] for r in api.ok("GET", "/reports", as_user="auditor")]
    assert "user_activity" in reports
    assert api.get("/reports/user_activity", as_user="custodian").status_code == 403


def test_export_is_logged(api, world):
    api.ok("GET", "/reports/asset_register?export=xlsx")
    assert any(e["action"] == "report.export" for e in api.ok("GET", "/audit-logs"))
