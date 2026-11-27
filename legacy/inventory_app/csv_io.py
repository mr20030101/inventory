"""CSV import and export. Files use UTF-8 with a BOM so Excel opens them correctly."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from inventory_app.repository import InventoryError, Repository

PRODUCT_COLUMNS = [
    "sku", "name", "category", "supplier", "unit", "cost_price", "sell_price",
    "quantity", "reorder_level", "location", "barcode", "description",
]


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


def write_csv(path: str | Path, headers: Sequence[str], rows: Iterable[Sequence]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def export_products(repo: Repository, path: str | Path) -> int:
    products = repo.list_products()
    write_csv(path, PRODUCT_COLUMNS, (
        [p.get(c) if c not in ("category", "supplier") else (p.get(c) or "") for c in PRODUCT_COLUMNS]
        for p in products
    ))
    return len(products)


def import_products(repo: Repository, path: str | Path) -> ImportResult:
    """Create or update products by SKU.

    Only "sku" is required (plus "name" for new products). Blank cells leave
    existing values unchanged. A quantity that differs from stock on hand is
    recorded as a stock adjustment.
    """
    result = ImportResult()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise InventoryError("The CSV file is empty.")
        fieldnames = {name.strip().lower(): name for name in reader.fieldnames if name}
        if "sku" not in fieldnames:
            raise InventoryError('The CSV file needs a "sku" column.')
        for line_no, raw in enumerate(reader, start=2):
            row = {key: (raw.get(original) or "").strip() for key, original in fieldnames.items()}
            if not any(row.values()):
                continue
            try:
                _import_row(repo, row, result)
            except InventoryError as exc:
                result.errors.append(f"Line {line_no}: {exc}")
    return result


def _import_row(repo: Repository, row: dict[str, str], result: ImportResult) -> None:
    sku = row.get("sku", "")
    if not sku:
        raise InventoryError("SKU is missing.")
    existing = repo.get_product_by_sku(sku)
    data = dict(existing) if existing else {"sku": sku}
    for key in ("name", "unit", "cost_price", "sell_price", "reorder_level",
                "location", "barcode", "description"):
        if row.get(key):
            data[key] = row[key]
    if row.get("category"):
        data["category_id"] = repo.category_id_for(row["category"])
    if row.get("supplier"):
        data["supplier_id"] = repo.supplier_id_for(row["supplier"])

    quantity = row.get("quantity", "")
    counted = None
    if quantity:
        try:
            counted = int(float(quantity))
        except ValueError:
            raise InventoryError("Quantity must be a whole number.") from None
        if counted < 0:
            raise InventoryError("Quantity cannot be negative.")
    if existing:
        repo.update_product(existing["id"], data)
        if counted is not None:
            if counted != existing["quantity"]:
                repo.record_movement(existing["id"], "adjust", counted, reference="CSV import")
        result.updated += 1
    else:
        repo.add_product(data, initial_quantity=counted or 0, reference="CSV import")
        result.created += 1
