"""A small demo catalogue for trying the app out."""
from __future__ import annotations

from inventory_app.repository import Repository

_SUPPLIERS = [
    {"name": "Acme Wholesale", "contact_name": "Jordan Lee", "email": "orders@acme.example",
     "phone": "02 9000 1000"},
    {"name": "Northwind Traders", "contact_name": "Sam Patel", "email": "sales@northwind.example",
     "phone": "03 9000 2000"},
]

# sku, name, category, supplier, unit, cost, price, qty, reorder, location
_PRODUCTS = [
    ("PEN-BLU-01", "Ballpoint pen, blue (box of 12)", "Stationery", "Acme Wholesale", "box", 4.20, 8.95, 40, 10, "A1"),
    ("PAP-A4-500", "A4 copy paper, 500 sheets", "Stationery", "Acme Wholesale", "ream", 5.10, 9.50, 6, 15, "A2"),
    ("NTB-A5-RUL", "A5 ruled notebook", "Stationery", "Northwind Traders", "pcs", 2.30, 5.99, 85, 20, "A3"),
    ("USB-C-1M", "USB-C cable, 1 m", "Electronics", "Northwind Traders", "pcs", 3.40, 12.00, 24, 10, "B1"),
    ("MSE-WL-01", "Wireless mouse", "Electronics", "Northwind Traders", "pcs", 11.75, 29.00, 3, 5, "B2"),
    ("HDP-OE-02", "Over-ear headphones", "Electronics", "Northwind Traders", "pcs", 38.00, 89.00, 0, 2, "B3"),
    ("MUG-CER-WH", "Ceramic mug, white", "Kitchen", "Acme Wholesale", "pcs", 1.90, 7.50, 60, 12, "C1"),
    ("CFE-BN-1KG", "Coffee beans, 1 kg", "Kitchen", "Acme Wholesale", "bag", 18.00, 34.00, 9, 8, "C2"),
]


def load_sample_data(repo: Repository) -> None:
    for supplier in _SUPPLIERS:
        repo.add_supplier(supplier)
    for sku, name, category, supplier, unit, cost, price, qty, reorder, location in _PRODUCTS:
        product_id = repo.add_product({
            "sku": sku, "name": name, "unit": unit, "cost_price": cost, "sell_price": price,
            "reorder_level": reorder, "location": location,
            "category_id": repo.category_id_for(category),
            "supplier_id": repo.supplier_id_for(supplier),
        }, initial_quantity=qty + (5 if qty else 0))
        if qty:
            repo.record_movement(product_id, "out", 5, reference="INV-1001", note="Sample sale")
