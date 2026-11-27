"""All reads and writes of inventory data go through Repository.

Product quantities only ever change through stock movements, so every change
to stock is recorded in the movement history.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

MOVEMENT_TYPES = {"in": "Stock In", "out": "Stock Out", "adjust": "Adjustment"}

PRODUCT_FIELDS = (
    "sku", "name", "description", "barcode", "category_id", "supplier_id",
    "unit", "cost_price", "sell_price", "reorder_level", "location",
)
SUPPLIER_FIELDS = ("name", "contact_name", "email", "phone", "address", "notes")


class InventoryError(Exception):
    """A user-facing error: invalid input or an operation that is not allowed."""


def now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cursor.fetchall()]


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ----------------------------------------------------------------- settings
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    @property
    def allow_negative_stock(self) -> bool:
        return self.get_setting("allow_negative_stock", "0") == "1"

    # --------------------------------------------------------------- categories
    def list_categories(self) -> list[dict[str, Any]]:
        return _rows(self.conn.execute(
            "SELECT c.id, c.name, COUNT(p.id) AS product_count "
            "FROM categories c LEFT JOIN products p ON p.category_id = c.id "
            "GROUP BY c.id ORDER BY c.name COLLATE NOCASE"
        ))

    def add_category(self, name: str) -> int:
        name = _required(name, "Category name")
        try:
            with self.conn:
                return self.conn.execute("INSERT INTO categories(name) VALUES(?)", (name,)).lastrowid
        except sqlite3.IntegrityError:
            raise InventoryError(f'A category named "{name}" already exists.') from None

    def rename_category(self, category_id: int, name: str) -> None:
        name = _required(name, "Category name")
        try:
            with self.conn:
                self.conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
        except sqlite3.IntegrityError:
            raise InventoryError(f'A category named "{name}" already exists.') from None

    def delete_category(self, category_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    def category_id_for(self, name: str) -> int | None:
        """Id of the named category, creating it if needed. Blank names give None."""
        name = (name or "").strip()
        if not name:
            return None
        row = self.conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else self.add_category(name)

    # ---------------------------------------------------------------- suppliers
    def list_suppliers(self) -> list[dict[str, Any]]:
        return _rows(self.conn.execute(
            "SELECT s.*, COUNT(p.id) AS product_count "
            "FROM suppliers s LEFT JOIN products p ON p.supplier_id = s.id "
            "GROUP BY s.id ORDER BY s.name COLLATE NOCASE"
        ))

    def get_supplier(self, supplier_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        return dict(row) if row else None

    def add_supplier(self, data: dict[str, Any]) -> int:
        values = self._clean_supplier(data)
        try:
            with self.conn:
                return self.conn.execute(
                    f"INSERT INTO suppliers({', '.join(SUPPLIER_FIELDS)}) "
                    f"VALUES({', '.join('?' * len(SUPPLIER_FIELDS))})",
                    [values[f] for f in SUPPLIER_FIELDS],
                ).lastrowid
        except sqlite3.IntegrityError:
            raise InventoryError(f'A supplier named "{values["name"]}" already exists.') from None

    def update_supplier(self, supplier_id: int, data: dict[str, Any]) -> None:
        values = self._clean_supplier(data)
        try:
            with self.conn:
                self.conn.execute(
                    f"UPDATE suppliers SET {', '.join(f + ' = ?' for f in SUPPLIER_FIELDS)} WHERE id = ?",
                    [values[f] for f in SUPPLIER_FIELDS] + [supplier_id],
                )
        except sqlite3.IntegrityError:
            raise InventoryError(f'A supplier named "{values["name"]}" already exists.') from None

    def delete_supplier(self, supplier_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))

    def supplier_id_for(self, name: str) -> int | None:
        name = (name or "").strip()
        if not name:
            return None
        row = self.conn.execute("SELECT id FROM suppliers WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else self.add_supplier({"name": name})

    @staticmethod
    def _clean_supplier(data: dict[str, Any]) -> dict[str, str]:
        values = {f: str(data.get(f) or "").strip() for f in SUPPLIER_FIELDS}
        values["name"] = _required(values["name"], "Supplier name")
        return values

    # ----------------------------------------------------------------- products
    _PRODUCT_SELECT = (
        "SELECT p.*, c.name AS category, s.name AS supplier, "
        "p.quantity * p.cost_price AS stock_value, "
        "p.quantity <= p.reorder_level AS is_low "
        "FROM products p "
        "LEFT JOIN categories c ON c.id = p.category_id "
        "LEFT JOIN suppliers s ON s.id = p.supplier_id "
    )

    def list_products(
        self,
        search: str = "",
        category_id: int | None = None,
        supplier_id: int | None = None,
        low_stock_only: bool = False,
    ) -> list[dict[str, Any]]:
        where, params = [], []
        if search.strip():
            like = f"%{search.strip()}%"
            where.append("(p.sku LIKE ? OR p.name LIKE ? OR p.barcode LIKE ? "
                         "OR p.location LIKE ? OR p.description LIKE ?)")
            params += [like] * 5
        if category_id is not None:
            where.append("p.category_id = ?")
            params.append(category_id)
        if supplier_id is not None:
            where.append("p.supplier_id = ?")
            params.append(supplier_id)
        if low_stock_only:
            where.append("p.quantity <= p.reorder_level")
        sql = self._PRODUCT_SELECT
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY p.name COLLATE NOCASE"
        return _rows(self.conn.execute(sql, params))

    def get_product(self, product_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(self._PRODUCT_SELECT + "WHERE p.id = ?", (product_id,)).fetchone()
        return dict(row) if row else None

    def get_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        row = self.conn.execute(self._PRODUCT_SELECT + "WHERE p.sku = ?", (sku.strip(),)).fetchone()
        return dict(row) if row else None

    def add_product(self, data: dict[str, Any], initial_quantity: int = 0, reference: str = "Initial stock") -> int:
        values = self._clean_product(data)
        initial_quantity = _int(initial_quantity, "Initial quantity")
        if initial_quantity < 0:
            raise InventoryError("Initial quantity cannot be negative.")
        stamp = now()
        try:
            with self.conn:
                product_id = self.conn.execute(
                    f"INSERT INTO products({', '.join(PRODUCT_FIELDS)}, quantity, created_at, updated_at) "
                    f"VALUES({', '.join('?' * len(PRODUCT_FIELDS))}, 0, ?, ?)",
                    [values[f] for f in PRODUCT_FIELDS] + [stamp, stamp],
                ).lastrowid
                if initial_quantity:
                    self._apply_movement(product_id, "in", initial_quantity, reference, "", allow_negative=False)
        except sqlite3.IntegrityError:
            raise InventoryError(f'A product with SKU "{values["sku"]}" already exists.') from None
        return product_id

    def update_product(self, product_id: int, data: dict[str, Any]) -> None:
        values = self._clean_product(data)
        try:
            with self.conn:
                self.conn.execute(
                    f"UPDATE products SET {', '.join(f + ' = ?' for f in PRODUCT_FIELDS)}, updated_at = ? "
                    "WHERE id = ?",
                    [values[f] for f in PRODUCT_FIELDS] + [now(), product_id],
                )
        except sqlite3.IntegrityError:
            raise InventoryError(f'A product with SKU "{values["sku"]}" already exists.') from None

    def delete_product(self, product_id: int) -> None:
        """Delete a product and its movement history."""
        with self.conn:
            self.conn.execute("DELETE FROM products WHERE id = ?", (product_id,))

    @staticmethod
    def _clean_product(data: dict[str, Any]) -> dict[str, Any]:
        values = {
            "sku": _required(data.get("sku"), "SKU"),
            "name": _required(data.get("name"), "Product name"),
            "description": str(data.get("description") or "").strip(),
            "barcode": str(data.get("barcode") or "").strip(),
            "category_id": data.get("category_id"),
            "supplier_id": data.get("supplier_id"),
            "unit": str(data.get("unit") or "").strip() or "pcs",
            "cost_price": round(_float(data.get("cost_price", 0), "Cost price"), 4),
            "sell_price": round(_float(data.get("sell_price", 0), "Sell price"), 4),
            "reorder_level": _int(data.get("reorder_level", 0), "Reorder level"),
            "location": str(data.get("location") or "").strip(),
        }
        for field, label in (("cost_price", "Cost price"), ("sell_price", "Sell price"),
                             ("reorder_level", "Reorder level")):
            if values[field] < 0:
                raise InventoryError(f"{label} cannot be negative.")
        return values

    # -------------------------------------------------------------------- stock
    def record_movement(
        self,
        product_id: int,
        kind: str,
        quantity: int,
        reference: str = "",
        note: str = "",
        allow_negative: bool | None = None,
    ) -> int:
        """Apply a stock movement and return the product's new quantity.

        kind "in" and "out" take the number of units moved; "adjust" takes the
        counted quantity on hand and records the difference.
        """
        if allow_negative is None:
            allow_negative = self.allow_negative_stock
        with self.conn:
            return self._apply_movement(product_id, kind, quantity, reference, note, allow_negative)

    def _apply_movement(self, product_id, kind, quantity, reference, note, allow_negative) -> int:
        if kind not in MOVEMENT_TYPES:
            raise InventoryError(f"Unknown movement type: {kind}")
        quantity = _int(quantity, "Quantity")
        row = self.conn.execute(
            "SELECT quantity, cost_price, unit FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if row is None:
            raise InventoryError("Product not found.")
        current = row["quantity"]
        if kind == "adjust":
            if quantity < 0:
                raise InventoryError("Counted quantity cannot be negative.")
            change = quantity - current
        else:
            if quantity <= 0:
                raise InventoryError("Quantity must be greater than zero.")
            change = quantity if kind == "in" else -quantity
            if kind == "out" and current + change < 0 and not allow_negative:
                raise InventoryError(
                    f"Not enough stock: {current} {row['unit']} on hand, {quantity} requested."
                )
        new_quantity = current + change
        stamp = now()
        self.conn.execute(
            "UPDATE products SET quantity = ?, updated_at = ? WHERE id = ?",
            (new_quantity, stamp, product_id),
        )
        self.conn.execute(
            "INSERT INTO stock_movements(product_id, kind, qty_change, quantity_after, unit_cost, "
            "reference, note, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (product_id, kind, change, new_quantity, row["cost_price"],
             (reference or "").strip(), (note or "").strip(), stamp),
        )
        return new_quantity

    def list_movements(
        self,
        start: str | None = None,
        end: str | None = None,
        product_id: int | None = None,
        kind: str | None = None,
        search: str = "",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Movements newest first. start/end are inclusive YYYY-MM-DD dates."""
        where, params = [], []
        if start:
            where.append("date(m.created_at) >= ?")
            params.append(start)
        if end:
            where.append("date(m.created_at) <= ?")
            params.append(end)
        if product_id is not None:
            where.append("m.product_id = ?")
            params.append(product_id)
        if kind:
            where.append("m.kind = ?")
            params.append(kind)
        if search.strip():
            like = f"%{search.strip()}%"
            where.append("(p.sku LIKE ? OR p.name LIKE ? OR m.reference LIKE ? OR m.note LIKE ?)")
            params += [like] * 4
        sql = ("SELECT m.*, p.sku, p.name AS product_name, p.unit "
               "FROM stock_movements m JOIN products p ON p.id = m.product_id ")
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY m.created_at DESC, m.id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = _rows(self.conn.execute(sql, params))
        for r in rows:
            r["kind_label"] = MOVEMENT_TYPES[r["kind"]]
        return rows

    # ------------------------------------------------------------------ reports
    def summary(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT COUNT(*) AS products, "
            "COALESCE(SUM(quantity), 0) AS units, "
            "COALESCE(SUM(quantity * cost_price), 0) AS cost_value, "
            "COALESCE(SUM(quantity * sell_price), 0) AS retail_value, "
            "COALESCE(SUM(quantity <= reorder_level), 0) AS low_stock, "
            "COALESCE(SUM(quantity <= 0), 0) AS out_of_stock "
            "FROM products"
        ).fetchone()
        return dict(row)

    def reorder_list(self) -> list[dict[str, Any]]:
        rows = self.list_products(low_stock_only=True)
        for r in rows:
            r["suggested_order"] = max(r["reorder_level"] * 2 - r["quantity"], 1)
            r["suggested_cost"] = r["suggested_order"] * r["cost_price"]
        rows.sort(key=lambda r: ((r["supplier"] or "~").lower(), r["name"].lower()))
        return rows

    def valuation_by_category(self) -> list[dict[str, Any]]:
        return _rows(self.conn.execute(
            "SELECT COALESCE(c.name, '(Uncategorised)') AS category, "
            "COUNT(p.id) AS products, SUM(p.quantity) AS units, "
            "SUM(p.quantity * p.cost_price) AS cost_value, "
            "SUM(p.quantity * p.sell_price) AS retail_value "
            "FROM products p LEFT JOIN categories c ON c.id = p.category_id "
            "GROUP BY c.id ORDER BY cost_value DESC"
        ))

    def monthly_flow(self, months: int = 6, today: date | None = None) -> list[dict[str, Any]]:
        """Units received and removed per calendar month, oldest first, including empty months."""
        today = today or date.today()
        keys = []
        year, month = today.year, today.month
        for _ in range(months):
            keys.append(f"{year:04d}-{month:02d}")
            year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        keys.reverse()
        totals = {
            r["month"]: r for r in self.conn.execute(
                "SELECT substr(created_at, 1, 7) AS month, "
                "SUM(CASE WHEN kind = 'in' THEN qty_change ELSE 0 END) AS units_in, "
                "SUM(CASE WHEN kind = 'out' THEN -qty_change ELSE 0 END) AS units_out "
                "FROM stock_movements WHERE substr(created_at, 1, 7) >= ? GROUP BY month",
                (keys[0],),
            )
        }
        return [{
            "month": k,
            "label": datetime.strptime(k, "%Y-%m").strftime("%b"),
            "units_in": totals[k]["units_in"] if k in totals else 0,
            "units_out": totals[k]["units_out"] if k in totals else 0,
        } for k in keys]

    def top_products_out(self, days: int = 30, limit: int = 10) -> list[dict[str, Any]]:
        """Products with the most units removed (stock out) in the last `days` days."""
        since = (date.today() - timedelta(days=days - 1)).isoformat()
        return _rows(self.conn.execute(
            "SELECT p.id, p.sku, p.name, SUM(-m.qty_change) AS units_out "
            "FROM stock_movements m JOIN products p ON p.id = m.product_id "
            "WHERE m.kind = 'out' AND date(m.created_at) >= ? "
            "GROUP BY p.id ORDER BY units_out DESC, p.name COLLATE NOCASE LIMIT ?",
            (since, limit),
        ))

    def movement_summary(self, start: str | None, end: str | None) -> list[dict[str, Any]]:
        where, params = [], []
        if start:
            where.append("date(m.created_at) >= ?")
            params.append(start)
        if end:
            where.append("date(m.created_at) <= ?")
            params.append(end)
        sql = (
            "SELECT p.sku, p.name, p.unit, p.quantity, "
            "SUM(CASE WHEN m.kind = 'in' THEN m.qty_change ELSE 0 END) AS units_in, "
            "SUM(CASE WHEN m.kind = 'out' THEN -m.qty_change ELSE 0 END) AS units_out, "
            "SUM(CASE WHEN m.kind = 'adjust' THEN m.qty_change ELSE 0 END) AS adjusted, "
            "SUM(CASE WHEN m.kind = 'out' THEN -m.qty_change * m.unit_cost ELSE 0 END) AS cost_out, "
            "COUNT(m.id) AS movements "
            "FROM stock_movements m JOIN products p ON p.id = m.product_id "
        )
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "GROUP BY p.id ORDER BY units_out DESC, p.name COLLATE NOCASE"
        return _rows(self.conn.execute(sql, params))


def _required(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise InventoryError(f"{label} is required.")
    return text


def _int(value: Any, label: str) -> int:
    try:
        number = float(str(value).strip() or 0)
    except ValueError:
        raise InventoryError(f"{label} must be a whole number.") from None
    if number != int(number):
        raise InventoryError(f"{label} must be a whole number.")
    return int(number)


def _float(value: Any, label: str) -> float:
    try:
        return float(str(value).strip().replace(",", "") or 0)
    except ValueError:
        raise InventoryError(f"{label} must be a number.") from None
