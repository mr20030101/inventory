"""Request bodies (Pydantic). Services do the business validation; these check shape and types."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Condition = Literal["new", "good", "fair", "poor", "damaged"]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=5000)

    def data(self) -> dict:
        return self.model_dump(exclude_unset=True, mode="json")


class LoginIn(Body):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class PasswordChangeIn(Body):
    current_password: str
    new_password: str


class UserIn(Body):
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    password: str | None = None
    roles: list[str] | None = None
    employee_id: str | None = None


class PasswordResetIn(Body):
    password: str


class ReferenceIn(Body):
    model_config = ConfigDict(extra="allow")


class AssetIn(Body):
    asset_code: str | None = None
    name: str | None = None
    description: str | None = None
    category_id: str | None = None
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    acquisition_date: date | None = None
    acquisition_cost: Decimal | None = None
    funding_source: str | None = None
    donor: str | None = None
    supplier_id: str | None = None
    purchase_reference: str | None = None
    warranty_expiry: date | None = None
    condition: Condition | None = None
    room_id: str | None = None
    department_id: str | None = None


class AssignIn(Body):
    employee_id: str | None = None
    department_id: str | None = None
    room_id: str | None = None
    condition: Condition | None = None
    acknowledged: bool = False
    notes: str = ""


class ReturnIn(Body):
    condition: Condition
    notes: str = ""


class TransferIn(Body):
    room_id: str | None = None
    department_id: str | None = None
    reason: str = ""


class LifecycleIn(Body):
    action: Literal["send_to_maintenance", "complete_maintenance", "mark_missing", "recover", "mark_damaged",
                    "retire", "dispose"]
    reason: str = ""
    condition: Condition | None = None
    event_date: date | None = None


class AssetBulkIn(Body):
    """The same action applied to several assets in one transaction: all succeed or nothing changes."""
    action: Literal["assign", "return", "transfer", "lifecycle", "condition"]
    asset_ids: list[str] = Field(min_length=1, max_length=500)
    employee_id: str | None = None
    department_id: str | None = None
    room_id: str | None = None
    condition: Condition | None = None
    acknowledged: bool = False
    notes: str = ""
    reason: str = ""
    lifecycle_action: Literal["send_to_maintenance", "complete_maintenance", "mark_missing", "recover",
                              "mark_damaged", "retire", "dispose"] | None = None
    event_date: date | None = None


class ConditionIn(Body):
    condition: Condition
    note: str = ""


class ArchiveIn(Body):
    reason: str


class StockItemIn(Body):
    item_code: str | None = None
    name: str | None = None
    description: str | None = None
    category_id: str | None = None
    unit_of_measure: str | None = None
    minimum_stock: Decimal | None = None
    reorder_level: Decimal | None = None
    track_expiry: bool | None = None
    is_active: bool | None = None


class MovementIn(Body):
    movement_type: Literal["OPENING", "RECEIPT", "ISSUE", "RETURN", "DAMAGE", "EXPIRY", "ADJUSTMENT_IN",
                           "ADJUSTMENT_OUT"]
    item_id: str
    location_id: str
    quantity: Decimal
    unit_cost: Decimal | None = None
    batch_id: str | None = None
    batch_no: str | None = None
    expiry_date: date | None = None
    department_id: str | None = None
    employee_id: str | None = None
    supplier_id: str | None = None
    reference: str = ""
    reason: str = ""
    request_id: str | None = Field(default=None, max_length=60)


class MovementLineIn(Body):
    item_id: str
    quantity: Decimal
    unit_cost: Decimal | None = None
    batch_no: str | None = None
    expiry_date: date | None = None


class MovementBatchIn(Body):
    """One movement type for several items in one transaction (e.g. one requisition or one delivery note)."""
    movement_type: Literal["OPENING", "RECEIPT", "ISSUE", "RETURN", "DAMAGE", "EXPIRY", "ADJUSTMENT_IN",
                           "ADJUSTMENT_OUT"]
    location_id: str
    lines: list[MovementLineIn] = Field(min_length=1, max_length=200)
    department_id: str | None = None
    employee_id: str | None = None
    supplier_id: str | None = None
    reference: str = ""
    reason: str = ""
    request_id: str | None = Field(default=None, max_length=50)


class StockTransferIn(Body):
    item_id: str
    from_location_id: str
    to_location_id: str
    quantity: Decimal
    batch_id: str | None = None
    reference: str = ""
    reason: str = ""


class BorrowIn(Body):
    asset_id: str
    borrower_id: str | None = None  # defaults to the signed-in user's own employee record
    purpose: str = ""
    date_needed: date | None = None
    expected_return: date


class BorrowBatchIn(Body):
    """Several pieces of equipment in one go (e.g. a camera and a tripod): one request each, all or nothing."""
    asset_ids: list[str] = Field(min_length=1, max_length=50)
    borrower_id: str | None = None
    purpose: str = ""
    date_needed: date | None = None
    expected_return: date


class BulkDecisionIn(Body):
    request_ids: list[str] = Field(min_length=1, max_length=500)
    approve: bool
    note: str = ""


class DecisionIn(Body):
    approve: bool
    note: str = ""


class ConditionNoteIn(Body):
    condition: Condition
    note: str = ""


class SettingsIn(Body):
    school_name: str | None = None
    currency_symbol: str | None = None
    asset_code_prefix: str | None = None
    item_code_prefix: str | None = None
