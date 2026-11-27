# Changelog

All notable changes to SAIMS. Versions follow [Semantic Versioning](https://semver.org).

## 0.1.0 — 2026-11-27 (demo release)

First demonstration build, covering stages 1–3 of the implementation plan.

### Added
- Server (FastAPI, `/api/v1`) with SQLAlchemy models, Alembic migration `0001`, and consistent JSON errors.
- Sign-in with Argon2id password hashing, expiring sessions, lockout after 5 failed attempts,
  session revocation on sign-out, deactivation and password reset.
- 45 granular permissions and 7 default roles, all enforced by the server. Teachers see only the assets
  assigned to them and their own borrowing requests, request only for themselves, and get a personal
  dashboard; built-in roles in existing databases are brought up to date on start.
- Append-only audit log covering asset, stock, borrowing, user, role, settings and export actions.
- School structure: departments, buildings, rooms, storage locations, employees, suppliers, categories.
- Asset register with generated codes, QR labels, checked lifecycle (assign, return, transfer, maintenance,
  missing, recovered, damaged, retired, disposed) and full history. Assets are archived, never deleted.
- Consumables with an immutable movement ledger, per-location balances, batches with expiry dates
  (issued earliest-expiry first), weighted average cost, atomic transfers, idempotent submissions and
  ledger reconciliation.
- Borrowing workflow: request, approve or reject (not by the requester), release, return, overdue tracking.
- Multi-select: checklist filters; bulk assign, return, transfer, condition and lifecycle actions on assets;
  approve or reject several requests; a sheet of QR labels; issue, receive or return several consumables in
  one transaction; borrow several items at once; export only selected rows. Bulk actions are all-or-nothing
  and name the record that blocked them.
- Dashboard, 12 reports with CSV, Excel and PDF export (exports are logged; PDFs carry the SAIMS logo).
- PySide6 desktop client with a built-in server and demo school data for presentations.
- Share on the local network: the built-in server can serve other computers over HTTPS with a certificate it
  creates itself; other computers confirm a security code once and then pin that certificate.
- Light and dark themes; vector icons that stay sharp at any display scale.
- Logo and brand kit in `branding/saims-logo/` (SVG, PNG, favicon, print PDF/EPS, colours, usage rules).
- Windows (Inno Setup installer and portable zip) and Linux (per-user installer) builds.
