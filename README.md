# SAIMS — School Asset & Inventory Management System

SAIMS tracks a school's fixed assets and consumable supplies: who holds what, where it is, what it cost,
what's running low, and who borrowed it. It follows the specification in
[SAIMS_Software_Requirements_and_Development_Blueprint.md](SAIMS_Software_Requirements_and_Development_Blueprint.md).

**Status: 0.1.0 demo release** (stages 1–3 of the implementation plan). See [CHANGELOG.md](CHANGELOG.md).

## Try the demo

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip ...
.venv/bin/python run_saims.py
```

On the sign-in screen keep **This computer (built-in demo server)** selected. The first start creates a
fictional school, *Hillcrest Demo School*, with about 70 assets, 15 consumables, six months of stock history,
borrowing requests and alerts. Every demo account uses the password `demo1234`:

| Username | Role | What to show |
|---|---|---|
| `admin` | Super Administrator | Everything, including users, roles and the audit log |
| `principal` | School Administrator | Approvals, disposal, settings |
| `custodian` | Property Custodian | Registering, assigning, issuing and receiving stock |
| `head.science` | Department Head | Approving borrowing requests |
| `teacher` | Teacher | A personal dashboard: only their own assets and borrowing requests |
| `auditor` | Auditor | Read-only access plus the audit log |
| `maintenance` | Maintenance Staff | Sending assets to and from maintenance |

Signing in as different users shows that menus, buttons and the data itself follow each role, and the server
refuses anything a role is not allowed to do.

To start again with fresh demo data, close SAIMS and delete the data folder:
`%APPDATA%\SAIMS` on Windows, `~/.local/share/saims` on Linux.

### Demo script (10 minutes)

1. **custodian** → Dashboard: alerts for a missing laptop, out-of-stock disinfectant, an expired batch and
   an overdue camera. Double-click an alert to jump to the record.
2. Assets → select a laptop: QR code, details, and the full history. *Register asset*, then *Assign* it to a
   teacher; *Assign* is now unavailable for it, and the server would refuse a second assignment anyway.
   Tick *Assigned* and *Borrowed* in the status filter to see both at once. Ctrl-click three available laptops
   and *Assign (3)* or *Print 3 QR labels*: bulk actions are all-or-nothing.
3. Consumables → Ctrl-click paper, pens and markers → *Issue (3)*: one requisition, one transaction. Try to
   issue more than is in stock: refused, and nothing is saved. Gloves and medicines show batch expiry tracking.
4. **teacher** → a personal dashboard (their laptop, their requests, an overdue reminder), *My Assets* and
   *My Requests* only. *New request* → tick a tablet and a camera: one request each, submitted together.
5. **head.science** → Borrowing → select both requests → *Approve (2)*. **custodian** → *Release*, then
   *Receive return*.
6. **auditor** → Audit Log: every step above, with who and when. Reports → export to Excel or PDF.

## Share on the local network

For a small school, one computer can serve everyone else on the same network, with no separate server:

1. On that computer, sign in as an administrator (e.g. `admin`) → user menu (your name, top right) →
   **Share on the local network…** → tick *Share* → **Apply**. It shows the address to use (for example
   `https://192.168.1.41:8765`) and a **security code** like `4F2A-9C1B-77E0`.
2. On each other computer: sign-in screen → **School server…** → enter that address → sign in. The first time,
   SAIMS shows the server's security code; check it matches the one on the sharing computer and confirm.

Connections use HTTPS with a certificate the sharing computer creates for itself. Each other computer
remembers ("pins") the confirmed certificate and refuses any other, so passwords cannot be read or intercepted
on the network. If the code ever changes, SAIMS warns before connecting.

Keep the sharing computer on with SAIMS open. If others cannot connect, allow the port through its firewall
(Windows asks the first time; Fedora: `sudo firewall-cmd --add-port=8765/tcp`). Demo accounts all use
`demo1234`, so change passwords before sharing real data. For more than a handful of users, run the dedicated
server below.

## Architecture

```
 Desktop app (PySide6) ──┐
                         ├── HTTPS ──► SAIMS API (FastAPI) ──► PostgreSQL
 Web app (planned)    ───┘             permissions, rules,       (SQLite for demos)
                                        audit log, reports
```

Clients never touch the database; every rule and permission check lives in the server
(`saims/backend/services`). The desktop app can run the server internally on 127.0.0.1 for demos and
single-PC use.

## Running the server for a school

```sh
pip install -r requirements-server.txt
export SAIMS_DATABASE_URL="postgresql+psycopg://saims:PASSWORD@db-host/saims"
export SAIMS_ADMIN_PASSWORD="a-strong-first-password"      # first start only
python -m saims.backend --host 127.0.0.1 --port 8000
```

- The database schema is created and upgraded automatically with Alembic on start.
- Put it behind a reverse proxy (nginx, Caddy, IIS) that provides HTTPS; the desktop app refuses plain
  `http://` except for localhost.
- API documentation: `https://<server>/api/v1/docs`.
- Back up PostgreSQL with `pg_dump` on a schedule and keep a copy off the server. Built-in scheduled
  backups are planned for stage 6.

In the desktop app, choose **School server…** on the sign-in screen and enter the server address.

## Build installers

PyInstaller builds for the platform it runs on, so build each OS on that OS (or push a `v*` tag and let
`.github/workflows/build.yml` build both).

- **Linux:** `./build.sh` → `dist/SAIMS-<version>-linux-x86_64.tar.gz`. Extract it and run `./install.sh`
  (per-user, no root; `./install.sh --uninstall` removes it). Some distros need `libxcb-cursor0`
  (Debian/Ubuntu) or `xcb-util-cursor` (Fedora).
- **Windows:** `build.bat` → `dist\SAIMS\SAIMS.exe`, plus `dist\SAIMS-<version>-Setup.exe` when
  [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed.

Check an installed build with `SAIMS --self-test` (starts the built-in server and verifies the data).

## Tests

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

47 tests cover the specification's acceptance scenarios (section 13): duplicate codes and serials, assigning
unavailable assets, borrowing assets already out, issuing more than is in stock, atomic transfers, duplicate
submissions, user deactivation revoking sessions, permission denial on every endpoint, audit entries,
teachers seeing only their own records, all-or-nothing bulk actions, network sharing with certificate pinning,
and a desktop run-through against the built-in server.

## Project layout

```
saims/
  backend/            server
    models.py           tables (UUID keys, decimal money and quantities, UTC timestamps)
    services/           business rules: assets, stock, borrowing, auth, reports
    api/v1/             HTTP endpoints
    migrations/         Alembic
    seed.py             demo school data
  desktop/            PySide6 client (api.py talks to the server; ui/ holds the screens)
tests/backend, tests/desktop
packaging/            PyInstaller spec, Inno Setup script, Linux installer
branding/             logo kit (svg, icons, print files, colours and usage rules)
legacy/               the earlier single-user Inventory Manager prototype (reference only)
```

## Not in this release

Planned in later stages of the implementation plan: purchasing and receiving, maintenance requests and
schedules, physical inventory sessions with discrepancy review, approval workflows for adjustments and
disposal, the web app, scheduled encrypted backups, two-factor sign-in, and signed automatic updates.
