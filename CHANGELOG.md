# Changelog

All notable changes to SAIMS. Versions follow [Semantic Versioning](https://semver.org).

## Unreleased

### Added
- **Share on the local network** (user menu, administrators): the built-in server serves other computers over
  HTTPS with a certificate it creates itself. Other computers confirm a security code once and then pin that
  certificate; a changed certificate is reported before connecting.
- **Multi-select**:
  - filters are checklists (statuses, categories, departments, rooms, locations, movement types);
  - select several assets to assign, return, transfer, change condition, run lifecycle actions or print a sheet
    of QR labels; select several pending requests to approve or reject. Bulk actions are all-or-nothing on the
    server and name the record that blocked them;
  - issue, receive or return several consumables in one transaction (`POST /stock/movements/batch`);
  - borrow several items in one go (`POST /borrowing/batch`);
  - export only the selected rows.
- `GET /borrowing/catalogue`: equipment that can be requested, without costs or custodians.
- **Logo and brand kit** in `branding/saims-logo/` (box-and-tick mark, Plus Jakarta Sans wordmark): SVG, PNG,
  favicon, print PDF/EPS, patterns, colour tokens and usage rules. The app icon, installer icons and sign-in
  screen use it; `tools/make_icon.py` regenerates the icons from the kit.

### Changed
- **Teacher / Employee role follows the specification ("view assigned assets and submit requests")**: new
  permissions `assets.view_own` and `borrowing.view_own`; teachers see only assets assigned to them and their
  own requests, request only for themselves, and get a personal dashboard instead of school-wide figures.
  Built-in roles in existing databases are updated on start (recorded in the audit log).
- Demo data: the teacher's borrowing requests are their own; other requests are filed by the custodian.
- User menu shows a chevron icon beside the name instead of Qt's corner arrow.
- New dependency: `cryptography` (certificate for network sharing).
- Sidebar redrawn: items are rounded pills inset in the sidebar, with a softer hover state and a
  keyboard-only focus ring.
- Icons are drawn as vectors at the screen's scale (sharp at 125%, 150% and 200%) and redrawn to one
  weight; new icons for Borrowing, School Setup, Audit Log and Settings. Disabled buttons show greyed icons.

## 0.1.0 — 2026-11-27 (demo release)

First demonstration build, covering stages 1–3 of the implementation plan.

### Added
- Server (FastAPI, `/api/v1`) with SQLAlchemy models, Alembic migration `0001`, and consistent JSON errors.
- Sign-in with Argon2id password hashing, expiring sessions, lockout after 5 failed attempts,
  session revocation on sign-out, deactivation and password reset.
- 43 granular permissions and 7 default roles, all enforced by the server.
- Append-only audit log covering asset, stock, borrowing, user, settings and export actions.
- School structure: departments, buildings, rooms, storage locations, employees, suppliers, categories.
- Asset register with generated codes, QR labels, checked lifecycle (assign, return, transfer, maintenance,
  missing, recovered, damaged, retired, disposed) and full history. Assets are archived, never deleted.
- Consumables with an immutable movement ledger, per-location balances, batches with expiry dates
  (issued earliest-expiry first), weighted average cost, atomic transfers, idempotent submissions and
  ledger reconciliation.
- Borrowing workflow: request, approve or reject (not by the requester), release, return, overdue tracking.
- Dashboard, 12 reports with CSV, Excel and PDF export (exports are logged).
- PySide6 desktop client with a built-in server and demo school data for presentations.
- Windows (Inno Setup) and Linux installers.
