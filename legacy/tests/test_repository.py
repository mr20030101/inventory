from datetime import date

import pytest

from inventory_app import csv_io, database
from inventory_app.repository import InventoryError


def make(repo, sku="A1", qty=0, **extra):
    data = {"sku": sku, "name": f"Item {sku}", "cost_price": 2.5, "sell_price": 5, "reorder_level": 3}
    data.update(extra)
    return repo.add_product(data, initial_quantity=qty)


def test_opening_stock_is_recorded_as_movement(repo):
    pid = make(repo, qty=10)
    assert repo.get_product(pid)["quantity"] == 10
    [m] = repo.list_movements()
    assert (m["kind"], m["qty_change"], m["quantity_after"]) == ("in", 10, 10)


def test_stock_in_out_and_adjust(repo):
    pid = make(repo, qty=10)
    assert repo.record_movement(pid, "in", 5) == 15
    assert repo.record_movement(pid, "out", 4) == 11
    assert repo.record_movement(pid, "adjust", 8) == 8
    changes = [m["qty_change"] for m in repo.list_movements(product_id=pid)]
    assert changes == [-3, -4, 5, 10]


def test_cannot_remove_more_than_on_hand_unless_allowed(repo):
    pid = make(repo, qty=2)
    with pytest.raises(InventoryError, match="Not enough stock"):
        repo.record_movement(pid, "out", 3)
    assert repo.get_product(pid)["quantity"] == 2
    assert len(repo.list_movements()) == 1
    repo.set_setting("allow_negative_stock", "1")
    assert repo.record_movement(pid, "out", 3) == -1


@pytest.mark.parametrize("kind,qty", [("in", 0), ("out", -1), ("adjust", -5), ("bogus", 1)])
def test_invalid_movements_rejected(repo, kind, qty):
    pid = make(repo, qty=5)
    with pytest.raises(InventoryError):
        repo.record_movement(pid, kind, qty)


def test_duplicate_sku_is_case_insensitive(repo):
    make(repo, "abc")
    with pytest.raises(InventoryError, match="already exists"):
        make(repo, "ABC")


def test_validation(repo):
    with pytest.raises(InventoryError, match="SKU is required"):
        repo.add_product({"name": "x"})
    with pytest.raises(InventoryError, match="cannot be negative"):
        repo.add_product({"sku": "x", "name": "x", "cost_price": -1})
    with pytest.raises(InventoryError, match="whole number"):
        repo.add_product({"sku": "x", "name": "x", "reorder_level": "1.5"})


def test_filters_and_low_stock(repo):
    cat = repo.category_id_for("Tools")
    make(repo, "LOW", qty=2, category_id=cat)
    make(repo, "OK", qty=20, name="Hammer")
    assert [p["sku"] for p in repo.list_products(low_stock_only=True)] == ["LOW"]
    assert [p["sku"] for p in repo.list_products(category_id=cat)] == ["LOW"]
    assert [p["sku"] for p in repo.list_products(search="hamm")] == ["OK"]
    s = repo.summary()
    assert (s["products"], s["units"], s["low_stock"], s["cost_value"]) == (2, 22, 1, 55.0)
    [r] = repo.reorder_list()
    assert r["suggested_order"] == 4


def test_deleting_category_keeps_products(repo):
    cat = repo.category_id_for("Tools")
    pid = make(repo, category_id=cat)
    repo.delete_category(cat)
    assert repo.get_product(pid)["category_id"] is None


def test_deleting_product_removes_history(repo):
    pid = make(repo, qty=3)
    repo.delete_product(pid)
    assert repo.list_movements() == []


def test_reports(repo):
    a = make(repo, "A", qty=10)
    repo.record_movement(a, "out", 4)
    flow = repo.monthly_flow(6)
    assert len(flow) == 6 and flow[-1]["month"] == date.today().strftime("%Y-%m")
    assert (flow[-1]["units_in"], flow[-1]["units_out"]) == (10, 4)
    assert repo.top_products_out()[0]["units_out"] == 4
    [row] = repo.movement_summary(None, None)
    assert (row["units_in"], row["units_out"], row["cost_out"]) == (10, 4, 10.0)
    assert repo.valuation_by_category()[0]["cost_value"] == 15.0


def test_monthly_flow_wraps_year(repo):
    keys = [m["month"] for m in repo.monthly_flow(3, today=date(2026, 2, 10))]
    assert keys == ["2025-12", "2026-01", "2026-02"]


def test_csv_round_trip(repo, tmp_path):
    make(repo, "A", qty=5, category_id=repo.category_id_for("Tools"))
    path = tmp_path / "out.csv"
    assert csv_io.export_products(repo, path) == 1
    text = path.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == ",".join(csv_io.PRODUCT_COLUMNS)
    path.write_text(
        "SKU,Name,Category,Quantity,Cost_Price\n"
        "A,,,9,\n"                 # update: quantity becomes an adjustment
        "B,New thing,Parts,3,1.5\n"  # create
        ",Missing sku,,1,\n"
        "C,,,,\n"                  # new product without a name
        "D,Bad qty,,many,\n",
        encoding="utf-8")
    result = csv_io.import_products(repo, path)
    assert (result.created, result.updated) == (1, 1)
    assert len(result.errors) == 3
    assert repo.get_product_by_sku("A")["quantity"] == 9
    assert repo.get_product_by_sku("A")["category"] == "Tools"
    b = repo.get_product_by_sku("B")
    assert (b["quantity"], b["category"], b["cost_price"]) == (3, "Parts", 1.5)
    assert repo.get_product_by_sku("D") is None


def test_restore_validation(tmp_path):
    database.connect(tmp_path / "good.db").close()
    (tmp_path / "bad.db").write_bytes(b"not a database")
    assert database.is_inventory_db(tmp_path / "good.db")
    assert not database.is_inventory_db(tmp_path / "bad.db")
