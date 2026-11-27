"""SQLAlchemy models. Money and quantities are exact decimals; timestamps are UTC."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Index, Integer, Numeric, String, Table, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saims.backend.database import Base, UTCDateTime, utcnow, uuid_pk

MONEY = Numeric(14, 2)
UNIT_COST = Numeric(14, 4)
QTY = Numeric(12, 3)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)


# --------------------------------------------------------------------------- access control
user_roles = Table(
    "user_roles", Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions", Base.metadata,
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_code", String(64), ForeignKey("permissions.code", ondelete="CASCADE"), primary_key=True),
)


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(200), default="")


class Role(Base, Timestamps):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300), default="")
    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, lazy="selectin")


class User(Base, Timestamps):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")

    @property
    def permission_codes(self) -> set[str]:
        return {p.code for r in self.roles for p in r.permissions}


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    client: Mapped[str] = mapped_column(String(200), default="")


class LoginLog(Base):
    __tablename__ = "login_logs"
    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(100), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event: Mapped[str] = mapped_column(String(30))  # login_success, login_failed, login_locked, logout
    detail: Mapped[str] = mapped_column(String(200), default="")
    client: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


# --------------------------------------------------------------------------- school structure
class Department(Base, Timestamps):
    __tablename__ = "departments"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Building(Base, Timestamps):
    __tablename__ = "buildings"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Room(Base, Timestamps):
    __tablename__ = "rooms"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    building_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("buildings.id", ondelete="RESTRICT"), index=True)
    floor: Mapped[str] = mapped_column(String(30), default="")
    kind: Mapped[str] = mapped_column(String(30), default="classroom")
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    building: Mapped[Building] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")


class StorageLocation(Base, Timestamps):
    __tablename__ = "storage_locations"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    room: Mapped[Room | None] = relationship(lazy="joined")


class Employee(Base, Timestamps):
    __tablename__ = "employees"
    id: Mapped[uuid.UUID] = uuid_pk()
    employee_no: Mapped[str] = mapped_column(String(30), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    position: Mapped[str] = mapped_column(String(100), default="")
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    department: Mapped[Department | None] = relationship(lazy="joined")


class Supplier(Base, Timestamps):
    __tablename__ = "suppliers"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), unique=True)
    contact_name: Mapped[str] = mapped_column(String(150), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base, Timestamps):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("kind", "name"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(20))  # asset | consumable
    name: Mapped[str] = mapped_column(String(150))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    default_unit: Mapped[str] = mapped_column(String(30), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    parent: Mapped["Category | None"] = relationship(remote_side="Category.id", lazy="joined")


# --------------------------------------------------------------------------- assets
class Asset(Base, Timestamps):
    __tablename__ = "assets"
    id: Mapped[uuid.UUID] = uuid_pk()
    asset_code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), index=True)
    brand: Mapped[str] = mapped_column(String(100), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    serial_number: Mapped[str | None] = mapped_column(String(150), unique=True)
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    acquisition_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    funding_source: Mapped[str] = mapped_column(String(30), default="school_funds")
    donor: Mapped[str] = mapped_column(String(200), default="")
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    purchase_reference: Mapped[str] = mapped_column(String(100), default="")
    warranty_expiry: Mapped[date | None] = mapped_column(Date)
    condition: Mapped[str] = mapped_column(String(30), default="good")
    status: Mapped[str] = mapped_column(String(30), default="available", index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    category: Mapped[Category | None] = relationship(lazy="joined")
    room: Mapped[Room | None] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")
    supplier: Mapped[Supplier | None] = relationship(lazy="joined")


class AssetAssignment(Base):
    __tablename__ = "asset_assignments"
    __table_args__ = (
        # At most one active assignment per asset.
        Index("uq_asset_active_assignment", "asset_id", unique=True,
              sqlite_where=text("returned_at IS NULL"), postgresql_where=text("returned_at IS NULL")),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"))
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"))
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    condition_on_release: Mapped[str] = mapped_column(String(30))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    returned_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    returned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    condition_on_return: Mapped[str | None] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text, default="")
    asset: Mapped[Asset] = relationship(lazy="joined")
    employee: Mapped[Employee | None] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")
    room: Mapped[Room | None] = relationship(lazy="joined")


class AssetEvent(Base):
    """Every change to an asset's status, condition, location or custodian."""

    __tablename__ = "asset_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    performed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    user: Mapped[User] = relationship(lazy="joined")


# --------------------------------------------------------------------------- consumables
class StockItem(Base, Timestamps):
    __tablename__ = "stock_items"
    id: Mapped[uuid.UUID] = uuid_pk()
    item_code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), index=True)
    unit_of_measure: Mapped[str] = mapped_column(String(30), default="piece")
    minimum_stock: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    reorder_level: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    average_cost: Mapped[Decimal] = mapped_column(UNIT_COST, default=Decimal("0"))
    track_expiry: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[Category | None] = relationship(lazy="joined")


class StockBatch(Base):
    __tablename__ = "stock_batches"
    __table_args__ = (UniqueConstraint("item_id", "batch_no"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_items.id", ondelete="RESTRICT"), index=True)
    batch_no: Mapped[str] = mapped_column(String(60))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class StockBalance(Base):
    """Cached quantity per item, storage location and batch. The movement ledger is the source of truth."""

    __tablename__ = "stock_balances"
    __table_args__ = (UniqueConstraint("item_id", "location_id", "batch_key"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_items.id", ondelete="RESTRICT"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_locations.id", ondelete="RESTRICT"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stock_batches.id", ondelete="RESTRICT"))
    # batch_id as text, or "" for no batch, so the unique constraint also covers un-batched stock.
    batch_key: Mapped[str] = mapped_column(String(36), default="")
    quantity: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    item: Mapped[StockItem] = relationship(lazy="joined")
    location: Mapped[StorageLocation] = relationship(lazy="joined")
    batch: Mapped[StockBatch | None] = relationship(lazy="joined")


class StockMovement(Base):
    """Immutable stock ledger. Quantity is always a positive magnitude; the type gives the direction."""

    __tablename__ = "stock_movements"
    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_items.id", ondelete="RESTRICT"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_locations.id", ondelete="RESTRICT"), index=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stock_batches.id", ondelete="RESTRICT"))
    movement_type: Mapped[str] = mapped_column(String(30), index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit_cost: Mapped[Decimal] = mapped_column(UNIT_COST, default=Decimal("0"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"))
    reference: Mapped[str] = mapped_column(String(100), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    transfer_ref: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), unique=True)  # idempotency key
    performed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    item: Mapped[StockItem] = relationship(lazy="joined")
    location: Mapped[StorageLocation] = relationship(lazy="joined")
    batch: Mapped[StockBatch | None] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")
    user: Mapped[User] = relationship(lazy="joined")


# --------------------------------------------------------------------------- borrowing
class BorrowRequest(Base, Timestamps):
    __tablename__ = "borrow_requests"
    id: Mapped[uuid.UUID] = uuid_pk()
    request_no: Mapped[str] = mapped_column(String(30), unique=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True)
    borrower_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    purpose: Mapped[str] = mapped_column(Text, default="")
    date_needed: Mapped[date] = mapped_column(Date)
    expected_return: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    released_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    released_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    condition_out: Mapped[str | None] = mapped_column(String(30))
    received_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    returned_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    condition_in: Mapped[str | None] = mapped_column(String(30))
    return_note: Mapped[str] = mapped_column(Text, default="")
    asset: Mapped[Asset] = relationship(lazy="joined")
    borrower: Mapped[Employee] = relationship(lazy="joined")


# --------------------------------------------------------------------------- system
class AuditLog(Base):
    """Append-only activity trail. The API has no update or delete for it."""

    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    username: Mapped[str] = mapped_column(String(100), default="")
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    changes: Mapped[str] = mapped_column(Text, default="")  # JSON of before/after values
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    request_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Sequence(Base):
    """Counters for human-readable codes (asset codes, request numbers)."""

    __tablename__ = "sequences"
    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
