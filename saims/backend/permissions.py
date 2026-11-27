"""Permission catalogue and default roles (specification section 3)."""
from __future__ import annotations

PERMISSIONS: dict[str, str] = {
    "dashboard.view": "View the dashboard",
    "assets.view": "View assets",
    "assets.view_own": "View assets assigned to me",
    "assets.create": "Register assets",
    "assets.update": "Edit asset details and condition",
    "assets.archive": "Archive asset records",
    "assets.assign": "Assign and return assets",
    "assets.transfer": "Transfer assets between locations",
    "assets.dispose": "Retire and dispose of assets",
    "assets.mark_missing": "Mark assets missing, damaged or recovered",
    "inventory.view": "View consumable stock",
    "inventory.manage_items": "Create and edit consumable items",
    "inventory.receive": "Receive stock",
    "inventory.issue": "Issue stock",
    "inventory.return": "Record stock returns",
    "inventory.adjust": "Adjust stock, record damage and expiry",
    "inventory.transfer": "Transfer stock between storage locations",
    "departments.view": "View departments",
    "departments.manage": "Manage departments",
    "locations.view": "View buildings, rooms and storage",
    "locations.manage": "Manage buildings, rooms and storage",
    "employees.view": "View employees",
    "employees.manage": "Manage employees",
    "suppliers.view": "View suppliers",
    "suppliers.manage": "Manage suppliers",
    "categories.manage": "Manage categories",
    "borrowing.view": "View borrowing requests",
    "borrowing.view_own": "View my own borrowing requests",
    "borrowing.request": "Submit borrowing requests",
    "borrowing.approve": "Approve or reject borrowing requests",
    "borrowing.release": "Release borrowed equipment",
    "borrowing.receive_return": "Receive returned equipment",
    "maintenance.view": "View maintenance",
    "maintenance.manage": "Send assets to and from maintenance",
    "reports.view": "View reports",
    "reports.export": "Export reports",
    "users.view": "View user accounts",
    "users.create": "Create user accounts",
    "users.update": "Edit user accounts and roles",
    "users.deactivate": "Deactivate users and reset passwords",
    "roles.manage": "Manage roles and permissions",
    "system.settings": "Change system settings",
    "system.backup": "Create backups",
    "system.restore": "Restore backups",
    "system.audit_logs.view": "View the audit log",
}

# Everyday read access; excludes the sensitive audit log and user list.
_VIEW = [p for p in PERMISSIONS if p.endswith(".view") and p not in {"system.audit_logs.view", "users.view"}]

# Bump when DEFAULT_ROLES change: built-in roles in existing databases are then brought up to date on start.
ROLES_VERSION = 2

DEFAULT_ROLES: dict[str, tuple[str, str, list[str]]] = {
    "super_admin": ("Super Administrator", "Full system configuration and administration", list(PERMISSIONS)),
    "school_admin": ("School Administrator", "School operations and approvals", [
        p for p in PERMISSIONS if not p.startswith(("roles.", "system.restore"))
    ]),
    "custodian": ("Property Custodian", "Manages assets, stock, assignments and transfers", _VIEW + [
        "assets.create", "assets.update", "assets.assign", "assets.transfer", "assets.mark_missing",
        "inventory.manage_items", "inventory.receive", "inventory.issue", "inventory.return", "inventory.adjust",
        "inventory.transfer", "borrowing.request", "borrowing.release", "borrowing.receive_return",
        "maintenance.manage", "employees.manage", "suppliers.manage", "categories.manage", "reports.export",
    ]),
    "department_head": ("Department Head", "Views department inventory and approves requests", [
        "dashboard.view", "assets.view", "inventory.view", "departments.view", "locations.view",
        "employees.view", "borrowing.view", "borrowing.request", "borrowing.approve", "maintenance.view",
        "reports.view", "reports.export",
    ]),
    # Specification section 3: "View assigned assets and submit requests" — only their own records.
    "employee": ("Teacher / Employee", "Views assets assigned to them and submits requests", [
        "dashboard.view", "assets.view_own", "borrowing.view_own", "borrowing.request",
    ]),
    "auditor": ("Auditor", "Read-only access to records and audit reports", _VIEW + [
        "reports.export", "system.audit_logs.view",
    ]),
    "maintenance": ("Maintenance Staff", "Manages assigned maintenance tasks", [
        "dashboard.view", "assets.view", "locations.view", "maintenance.view", "maintenance.manage",
    ]),
}
