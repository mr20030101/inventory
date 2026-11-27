"""Demo school data for presentations. Everything goes through the real services,
so ledgers, histories and the audit log are consistent; timestamps are then backdated.

All names, codes and suppliers are fictional.
"""
from __future__ import annotations

import random
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from saims.backend.models import (
    AssetAssignment, AssetEvent, AuditLog, BorrowRequest, Role, StockBatch, StockMovement, User,
)
from saims.backend.security import hash_password
from saims.backend.services import assets, borrowing, reference, stock
from saims.backend.services.common import put_setting

DEMO_PASSWORD = "demo1234"
DEMO_USERS = [
    # username, full name, role, employee no
    ("admin", "System Administrator", "super_admin", None),
    ("principal", "Dr. Grace Okafor", "school_admin", "EMP-001"),
    ("custodian", "Daniel Reyes", "custodian", "EMP-002"),
    ("head.science", "Priya Nair", "department_head", "EMP-003"),
    ("teacher", "Tom Becker", "employee", "EMP-004"),
    ("auditor", "Helen Park", "auditor", None),
    ("maintenance", "Samuel Mensah", "maintenance", "EMP-005"),
]


@contextmanager
def backdate(db: Session, when: datetime):
    """Give every row created inside the block the timestamp `when`."""
    start = datetime.now(timezone.utc) - timedelta(seconds=1)
    yield
    for model, col in ((AuditLog, AuditLog.created_at), (AssetEvent, AssetEvent.created_at),
                       (StockMovement, StockMovement.created_at), (StockBatch, StockBatch.created_at)):
        db.execute(update(model).where(col >= start).values(created_at=when))
    db.execute(update(AssetAssignment).where(AssetAssignment.assigned_at >= start).values(assigned_at=when))
    for col in ("created_at", "decided_at", "released_at", "returned_at"):
        c = getattr(BorrowRequest, col)
        db.execute(update(BorrowRequest).where(c >= start).values({col: when}))
    db.commit()


def _at(days_ago: int, hour: int = 10) -> datetime:
    d = date.today() - timedelta(days=days_ago)
    return datetime.combine(d, time(hour, random.randint(0, 59)), tzinfo=timezone.utc)


def seed_demo(db: Session) -> None:
    random.seed(7)
    roles = {r.code: r for r in db.scalars(select(Role))}
    for key, value in {"school_name": "Hillcrest Demo School", "currency_symbol": "$", "demo_mode": "1",
                       "asset_code_prefix": "HDS", "item_code_prefix": "CON"}.items():
        put_setting(db, key, value)
    db.commit()

    admin = User(username="admin", full_name="System Administrator", password_hash=hash_password(DEMO_PASSWORD),
                 roles=[roles["super_admin"]])
    db.add(admin)
    db.commit()

    ref = lambda key, **data: reference.create(db, admin, key, data)  # noqa: E731
    with backdate(db, _at(200, 8)):
        dept = {code: ref("departments", code=code, name=name) for code, name in [
            ("ADM", "Administration"), ("SCI", "Science"), ("MAT", "Mathematics"), ("ENG", "English"),
            ("ICT", "ICT"), ("PE", "Physical Education"), ("LIB", "Library"), ("FAC", "Facilities & Maintenance")]}
        bld = {code: ref("buildings", code=code, name=name) for code, name in [
            ("MAIN", "Main Building"), ("SCB", "Science Block"), ("GYM", "Sports Hall")]}
        rooms = {}
        for code, name, b, floor, kind, d in [
            ("M-101", "Principal's Office", "MAIN", "1", "office", "ADM"),
            ("M-102", "Staff Room", "MAIN", "1", "office", "ADM"),
            ("M-201", "Classroom 2A", "MAIN", "2", "classroom", "ENG"),
            ("M-202", "Classroom 2B", "MAIN", "2", "classroom", "MAT"),
            ("M-203", "Classroom 2C", "MAIN", "2", "classroom", "MAT"),
            ("M-204", "Computer Lab 1", "MAIN", "2", "laboratory", "ICT"),
            ("M-G01", "Library", "MAIN", "Ground", "library", "LIB"),
            ("M-G02", "Main Stockroom", "MAIN", "Ground", "storeroom", "ADM"),
            ("M-G03", "Clinic", "MAIN", "Ground", "office", "ADM"),
            ("S-101", "Chemistry Lab", "SCB", "1", "laboratory", "SCI"),
            ("S-102", "Biology Lab", "SCB", "1", "laboratory", "SCI"),
            ("S-103", "Science Prep Room", "SCB", "1", "storeroom", "SCI"),
            ("G-001", "Sports Hall", "GYM", "Ground", "hall", "PE"),
            ("G-002", "PE Equipment Store", "GYM", "Ground", "storeroom", "PE"),
            ("M-G04", "Maintenance Workshop", "MAIN", "Ground", "workshop", "FAC"),
        ]:
            rooms[code] = ref("rooms", code=code, name=name, building_id=bld[b].id, floor=floor, kind=kind,
                              department_id=dept[d].id)
        stores = {code: ref("storage-locations", code=code, name=name, room_id=rooms[r].id) for code, name, r in [
            ("ST-MAIN", "Main Stockroom", "M-G02"), ("ST-SCI", "Science Prep Room", "S-103"),
            ("ST-PE", "PE Equipment Store", "G-002"), ("ST-CLN", "Clinic Cabinet", "M-G03")]}
        sup = {key: ref("suppliers", name=name, contact_name=contact, email=email, phone=phone)
               for key, name, contact, email, phone in [
                   ("office", "Northgate Office Supplies", "Maria Lopez", "orders@northgate.example", "555-0101"),
                   ("tech", "BrightTech Computers", "Kevin Wu", "sales@brighttech.example", "555-0102"),
                   ("lab", "LabWorks Scientific", "Anita Shah", "lab@labworks.example", "555-0103"),
                   ("sport", "ActiveSport Equipment", "Leo Brandt", "team@activesport.example", "555-0104"),
                   ("med", "MedCare Supplies", "Ruth Adeyemi", "care@medcare.example", "555-0105")]}
        cat = {}
        for name, parent in [("IT Equipment", None), ("Laptops", "IT Equipment"), ("Desktop Computers", "IT Equipment"),
                             ("Projectors & Displays", "IT Equipment"), ("Printers", "IT Equipment"),
                             ("Tablets & Cameras", "IT Equipment"), ("Furniture", None),
                             ("Laboratory Equipment", None), ("Sports Equipment", None),
                             ("Library Equipment", None), ("Audio-Visual Equipment", None)]:
            cat[name] = ref("categories", kind="asset", name=name, parent_id=cat[parent].id if parent else None)
        ccat = {name: ref("categories", kind="consumable", name=name, default_unit=unit) for name, unit in [
            ("Office Supplies", "box"), ("Cleaning Supplies", "bottle"), ("Laboratory Consumables", "box"),
            ("Medical Supplies", "box"), ("Maintenance Supplies", "piece")]}

        emp = {}
        staff = [
            ("EMP-001", "Dr. Grace Okafor", "Principal", "ADM"), ("EMP-002", "Daniel Reyes", "Property Custodian", "ADM"),
            ("EMP-003", "Priya Nair", "Head of Science", "SCI"), ("EMP-004", "Tom Becker", "English Teacher", "ENG"),
            ("EMP-005", "Samuel Mensah", "Maintenance Technician", "FAC"),
            ("EMP-006", "Aisha Rahman", "Mathematics Teacher", "MAT"), ("EMP-007", "Lucas Ferreira", "ICT Teacher", "ICT"),
            ("EMP-008", "Mei Lin", "Chemistry Teacher", "SCI"), ("EMP-009", "Jonah Clarke", "PE Teacher", "PE"),
            ("EMP-010", "Sofia Rossi", "Librarian", "LIB"), ("EMP-011", "Kwame Asante", "Biology Teacher", "SCI"),
            ("EMP-012", "Elena Petrova", "Mathematics Teacher", "MAT"), ("EMP-013", "Ravi Kumar", "ICT Technician", "ICT"),
            ("EMP-014", "Hannah Schmidt", "School Nurse", "ADM"), ("EMP-015", "Omar Haddad", "English Teacher", "ENG"),
            ("EMP-016", "Nora Lindqvist", "Administrative Officer", "ADM"),
        ]
        for no, name, pos, d in staff:
            first, last = name.replace("Dr. ", "").split(" ", 1)
            emp[no] = ref("employees", employee_no=no, full_name=name, position=pos, department_id=dept[d].id,
                          email=f"{first.lower()}.{last.lower().replace(' ', '')}@hillcrest.example", phone="")

        users = {"admin": admin}
        for username, full_name, role, emp_no in DEMO_USERS[1:]:
            u = User(username=username, full_name=full_name, password_hash=hash_password(DEMO_PASSWORD),
                     roles=[roles[role]], employee_id=emp[emp_no].id if emp_no else None)
            db.add(u)
            users[username] = u
        db.commit()

    cust = users["custodian"]

    # ----------------------------------------------------------- assets
    def reg(name, category, room, cost, days_ago, brand="", model="", serial=None, supplier="tech",
            funding="school_funds", warranty_years=0, condition="good", donor=""):
        acquired = date.today() - timedelta(days=days_ago)
        with backdate(db, _at(days_ago, 9)):
            return assets.register(db, cust, {
                "name": name, "category_id": cat[category].id, "room_id": rooms[room].id, "brand": brand,
                "model": model, "serial_number": serial, "acquisition_cost": str(cost),
                "acquisition_date": acquired.isoformat(), "supplier_id": sup[supplier].id,
                "funding_source": funding, "donor": donor, "condition": condition,
                "purchase_reference": f"PO-{acquired.year}-{random.randint(100, 999)}",
                "warranty_expiry": (acquired + timedelta(days=365 * warranty_years)).isoformat()
                if warranty_years else None})

    laptops = [reg("Laptop", "Laptops", "M-102", 780, 400 + i * 3, "Lenovo", "ThinkPad E14",
                   f"PF4LX{2300 + i}", warranty_years=3, condition="good") for i in range(12)]
    desktops = [reg("Desktop computer", "Desktop Computers", "M-204", 650, 520, "Dell", "OptiPlex 7010",
                    f"DLX7010-{4100 + i}", warranty_years=3) for i in range(15)]
    projectors = [reg("Projector", "Projectors & Displays", r, 540, 610, "Epson", "EB-W51", f"EPW51-{880 + i}",
                      warranty_years=2) for i, r in enumerate(["M-201", "M-202", "M-203", "S-101", "S-102", "M-G01"])]
    display = reg("Interactive display 75\"", "Projectors & Displays", "M-204", 3150, 160, "Promethean",
                  "ActivPanel 9", "PRM-AP9-5512", funding="grant", warranty_years=5, condition="new")
    printers = [reg("Laser printer", "Printers", r, 420, 300, "HP", "LaserJet Pro 4002", f"HPLJ-{770 + i}",
                    warranty_years=1) for i, r in enumerate(["M-102", "M-101"])]
    microscopes = [reg("Microscope", "Laboratory Equipment", "S-102", 465, 700, "Olympus", "CX23",
                       f"OLY-CX23-{150 + i}", supplier="lab") for i in range(8)]
    balances = [reg("Digital balance", "Laboratory Equipment", "S-101", 310, 450, "Ohaus", "Scout SKX",
                    f"OHS-{620 + i}", supplier="lab") for i in range(3)]
    fume = reg("Fume cupboard", "Laboratory Equipment", "S-101", 4800, 900, "LabWorks", "FC-1200", "LWFC-0091",
               supplier="lab", funding="government")
    cameras = [reg("Digital camera", "Tablets & Cameras", "M-G01", 690, 250, "Canon", "EOS 250D",
                   f"CN250D-{31 + i}") for i in range(2)]
    tablets = [reg("Tablet", "Tablets & Cameras", "M-G01", 399, 220, "Apple", "iPad 10th gen",
                   f"DMPX{9100 + i}", warranty_years=1) for i in range(5)]
    pa = reg("Portable PA system", "Audio-Visual Equipment", "G-001", 560, 330, "Yamaha", "Stagepas 400BT",
             "YSP-400-221", supplier="sport")
    rowers = [reg("Rowing machine", "Sports Equipment", "G-001", 980, 380, "Concept2", "RowErg",
                  f"C2-RE-{410 + i}", supplier="sport", funding="donation",
                  donor="Hillcrest Parents' Association") for i in range(2)]
    desks = [reg("Teacher's desk", "Furniture", r, 260, 1200, supplier="office")
             for r in ["M-201", "M-202", "M-203", "S-101"]]
    cabinets = [reg("Filing cabinet, 4-drawer", "Furniture", r, 210, 1100, supplier="office")
                for r in ["M-101", "M-102", "M-102"]]
    scanner = reg("Barcode scanner", "Library Equipment", "M-G01", 145, 600, "Zebra", "DS2208", "ZB-DS2208-77")
    old_proj = reg("Projector (old)", "Projectors & Displays", "M-G02", 480, 2400, "Epson", "EB-X41", "EPX41-012")
    old_pc = reg("Desktop computer (old)", "Desktop Computers", "M-G02", 590, 2600, "Dell", "OptiPlex 3020",
                 "DL3020-0007")

    # Assignments: laptops to teachers, lab PCs and projectors to their rooms.
    holders = ["EMP-004", "EMP-006", "EMP-007", "EMP-008", "EMP-009", "EMP-011", "EMP-012", "EMP-015"]
    for laptop, who in zip(laptops, holders):
        with backdate(db, _at(380, 11)):
            assets.assign(db, cust, laptop.id, {"employee_id": emp[who].id, "condition": "good",
                                                "acknowledged": True, "notes": "Staff laptop issue"})
    for pc in desktops:
        with backdate(db, _at(500, 12)):
            assets.assign(db, cust, pc.id, {"room_id": rooms["M-204"].id, "department_id": dept["ICT"].id,
                                            "condition": "good"})
    for p in projectors[:5]:
        with backdate(db, _at(600, 12)):
            assets.assign(db, cust, p.id, {"room_id": p.room_id, "condition": "good"})
    with backdate(db, _at(150, 10)):
        assets.assign(db, cust, display.id, {"room_id": rooms["M-204"].id, "employee_id": emp["EMP-007"].id,
                                             "condition": "new", "acknowledged": True})
    with backdate(db, _at(290, 10)):
        assets.assign(db, cust, printers[0].id, {"department_id": dept["ADM"].id, "condition": "good"})

    # Lifecycle stories
    with backdate(db, _at(45, 14)):
        assets.lifecycle(db, cust, laptops[2].id, "mark_missing", "Not returned at end of term; staff member "
                                                               "reports it left in Classroom 2B")
    with backdate(db, _at(30, 9)):
        assets.lifecycle(db, cust, projectors[3].id, "mark_damaged", "Lamp housing cracked after fall from mount")
    with backdate(db, _at(12, 9)):
        assets.lifecycle(db, cust, laptops[9].id, "send_to_maintenance", "Battery not holding charge")
    with backdate(db, _at(20, 15)):
        assets.lifecycle(db, cust, microscopes[7].id, "mark_damaged", "Fine focus knob stripped")
    with backdate(db, _at(90, 9)):
        assets.lifecycle(db, cust, old_proj.id, "retire", "End of life; replaced by EB-W51 units")
    with backdate(db, _at(400, 9)):
        assets.lifecycle(db, cust, old_pc.id, "retire", "Hardware failure, beyond economical repair")
    with backdate(db, _at(380, 9)):
        assets.lifecycle(db, users["principal"], old_pc.id, "dispose",
                         "Sent to certified e-waste recycler, certificate EW-2219")
    with backdate(db, _at(60, 11)):
        assets.transfer(db, cust, cabinets[2].id, {"room_id": rooms["M-G01"].id,
                                                   "reason": "Library needed extra storage"})

    # ----------------------------------------------------------- borrowing
    teacher, head = users["teacher"], users["head.science"]

    def borrow(asset, who, purpose, needed_ago, days):
        # Teachers request for themselves (EMP-004 is the "teacher" account); the custodian files the others.
        by = teacher if who == "EMP-004" else users["custodian"]
        with backdate(db, _at(max(needed_ago + 2, 0), 8)):
            return borrowing.create(db, by, {
                "asset_id": asset.id, "borrower_id": emp[who].id, "purpose": purpose,
                "date_needed": (date.today() - timedelta(days=needed_ago)).isoformat(),
                "expected_return": (date.today() - timedelta(days=needed_ago - days)).isoformat()})

    r1 = borrow(microscopes[0], "EMP-011", "Year 9 field study", 40, 5)
    with backdate(db, _at(41, 9)):
        borrowing.decide(db, head, r1.id, True, "Approved")
    with backdate(db, _at(40, 8)):
        borrowing.release(db, cust, r1.id, "good")
    with backdate(db, _at(35, 15)):
        borrowing.receive_return(db, cust, r1.id, "good")

    r2 = borrow(cameras[0], "EMP-004", "Drama club performance recording", 12, 7)
    with backdate(db, _at(13, 9)):
        borrowing.decide(db, head, r2.id, True, "OK for the drama club")
    with backdate(db, _at(12, 8)):
        borrowing.release(db, cust, r2.id, "good")

    r3 = borrow(pa, "EMP-004", "Sports day announcements", -3, 2)
    with backdate(db, _at(1, 10)):
        borrowing.decide(db, users["principal"], r3.id, True, "Approved for sports day")

    borrow(tablets[0], "EMP-004", "Reading assessment in Classroom 2A", -5, 3)
    borrow(rowers[0], "EMP-009", "After-school fitness club", -7, 30)
    r6 = borrow(cameras[1], "EMP-006", "Personal weekend use", 3, 2)
    with backdate(db, _at(2, 9)):
        borrowing.decide(db, head, r6.id, False, "School equipment is for school activities only")
    r7 = borrow(tablets[1], "EMP-012", "Maths app trial", 8, 4)
    with backdate(db, _at(9, 9)):
        borrowing.decide(db, head, r7.id, True, "")
    with backdate(db, _at(8, 8)):
        borrowing.release(db, cust, r7.id, "good")
    with backdate(db, _at(3, 14)):
        borrowing.receive_return(db, cust, r7.id, "good", "Returned early")

    # ----------------------------------------------------------- consumables
    items = {}
    for code, name, category, unit, reorder, minimum, expiry in [
        ("A4", "A4 copy paper, 500 sheets", "Office Supplies", "ream", 60, 30, False),
        ("WBM", "Whiteboard markers, assorted", "Office Supplies", "box", 10, 5, False),
        ("TNR", "Toner cartridge HP 149A", "Office Supplies", "piece", 3, 2, False),
        ("PEN", "Ballpoint pens, blue", "Office Supplies", "box", 8, 4, False),
        ("SOAP", "Liquid hand soap, 500 ml", "Cleaning Supplies", "bottle", 20, 10, False),
        ("DIS", "Disinfectant, 5 L", "Cleaning Supplies", "bottle", 6, 3, False),
        ("TOW", "Paper towels", "Cleaning Supplies", "roll", 40, 20, False),
        ("ETH", "Ethanol 70%, 1 L", "Laboratory Consumables", "bottle", 6, 3, True),
        ("GLV", "Nitrile gloves, medium", "Laboratory Consumables", "box", 10, 5, True),
        ("LIT", "Litmus paper strips", "Laboratory Consumables", "pack", 5, 2, False),
        ("BND", "Adhesive bandages", "Medical Supplies", "box", 5, 2, True),
        ("PCM", "Paracetamol 500 mg, 20 tablets", "Medical Supplies", "pack", 10, 5, True),
        ("WIP", "Antiseptic wipes", "Medical Supplies", "box", 6, 3, True),
        ("LED", "LED bulb, 9 W", "Maintenance Supplies", "piece", 15, 8, False),
        ("CBL", "Cable ties, 200 mm", "Maintenance Supplies", "pack", 4, 2, False),
    ]:
        with backdate(db, _at(190, 8)):
            items[code] = stock.create_item(db, cust, {
                "name": name, "category_id": ccat[category].id, "unit_of_measure": unit,
                "reorder_level": reorder, "minimum_stock": minimum, "track_expiry": expiry})

    def move(kind, code, store, qty, days_ago, **extra):
        with backdate(db, _at(days_ago, random.choice([9, 10, 11, 13, 14]))):
            stock.record(db, cust, {"movement_type": kind, "item_id": items[code].id,
                                    "location_id": stores[store].id, "quantity": str(qty), **extra})

    def issue(code, store, qty, days_ago, d, ref=""):
        move("ISSUE", code, store, qty, days_ago, department_id=dept[d].id, reference=ref)

    # Opening balances, then six months of deliveries and issues.
    move("OPENING", "A4", "ST-MAIN", 80, 185, unit_cost="4.80", reference="Opening count")
    move("OPENING", "WBM", "ST-MAIN", 14, 185, unit_cost="9.50")
    move("OPENING", "TNR", "ST-MAIN", 4, 185, unit_cost="68.00")
    move("OPENING", "PEN", "ST-MAIN", 20, 185, unit_cost="3.20")
    move("OPENING", "SOAP", "ST-MAIN", 30, 185, unit_cost="2.40")
    move("OPENING", "DIS", "ST-MAIN", 8, 185, unit_cost="11.90")
    move("OPENING", "TOW", "ST-MAIN", 60, 185, unit_cost="1.10")
    move("OPENING", "LIT", "ST-SCI", 9, 185, unit_cost="3.60")
    move("OPENING", "LED", "ST-MAIN", 25, 185, unit_cost="3.75")
    move("OPENING", "CBL", "ST-MAIN", 6, 185, unit_cost="2.90")
    move("OPENING", "ETH", "ST-SCI", 6, 185, unit_cost="7.20", batch_no="ETH-2405",
         expiry_date=(date.today() + timedelta(days=40)).isoformat())
    move("OPENING", "GLV", "ST-SCI", 12, 185, unit_cost="8.40", batch_no="GLV-A17",
         expiry_date=(date.today() + timedelta(days=400)).isoformat())
    move("OPENING", "BND", "ST-CLN", 6, 185, unit_cost="4.10", batch_no="BND-311",
         expiry_date=(date.today() + timedelta(days=500)).isoformat())
    move("OPENING", "PCM", "ST-CLN", 14, 185, unit_cost="1.95", batch_no="PCM-8812",
         expiry_date=(date.today() + timedelta(days=25)).isoformat())
    move("OPENING", "WIP", "ST-CLN", 5, 185, unit_cost="5.30", batch_no="WIP-1102",
         expiry_date=(date.today() - timedelta(days=6)).isoformat())

    depts_for = {"A4": ["ENG", "MAT", "ADM", "SCI", "ICT"], "WBM": ["ENG", "MAT", "SCI"], "PEN": ["ADM", "ENG", "MAT"],
                 "SOAP": ["FAC"], "TOW": ["FAC"], "DIS": ["FAC"], "LED": ["FAC"]}
    ref_no = 1000
    for month in range(6):
        base = 180 - month * 30
        move("RECEIPT", "A4", "ST-MAIN", 50, base - 2, unit_cost=str(Decimal("4.80") + Decimal(month) / 20),
             supplier_id=sup["office"].id, reference=f"DN-{5100 + month}")
        move("RECEIPT", "SOAP", "ST-MAIN", 15, base - 3, unit_cost="2.40", supplier_id=sup["office"].id,
             reference=f"DN-{5200 + month}")
        move("RECEIPT", "TOW", "ST-MAIN", 30, base - 3, unit_cost="1.10", supplier_id=sup["office"].id)
        if month % 2 == 0:
            move("RECEIPT", "WBM", "ST-MAIN", 6, base - 4, unit_cost="9.80", supplier_id=sup["office"].id)
            move("RECEIPT", "PEN", "ST-MAIN", 6, base - 4, unit_cost="3.20", supplier_id=sup["office"].id)
            move("RECEIPT", "LED", "ST-MAIN", 10, base - 5, unit_cost="3.60", supplier_id=sup["office"].id)
        for week in range(4):
            day = base - 6 - week * 7
            if day < 1:
                continue
            for code, ds in depts_for.items():
                qty = {"A4": random.randint(6, 12), "WBM": 1, "PEN": 1, "SOAP": random.randint(2, 4),
                       "TOW": random.randint(4, 8), "DIS": 1, "LED": random.randint(0, 2)}[code]
                if qty and random.random() < 0.8:
                    ref_no += 1
                    try:
                        issue(code, "ST-MAIN", qty, day, random.choice(ds), f"REQ-{ref_no}")
                    except Exception:  # skip issues that would exceed stock in the random history
                        db.rollback()
        try:
            issue("TNR", "ST-MAIN", 1, base - 10, "ADM", f"REQ-{ref_no}")
        except Exception:
            db.rollback()
    move("RECEIPT", "A4", "ST-MAIN", 40, 6, unit_cost="5.10", supplier_id=sup["office"].id, reference="DN-5190")
    move("RECEIPT", "TNR", "ST-MAIN", 2, 70, unit_cost="71.50", supplier_id=sup["tech"].id, reference="INV-T8812")
    move("RECEIPT", "ETH", "ST-SCI", 6, 50, unit_cost="7.40", supplier_id=sup["lab"].id, batch_no="ETH-2502",
         expiry_date=(date.today() + timedelta(days=330)).isoformat(), reference="LW-4471")
    move("RECEIPT", "GLV", "ST-SCI", 10, 50, unit_cost="8.60", supplier_id=sup["lab"].id, batch_no="GLV-B02",
         expiry_date=(date.today() + timedelta(days=700)).isoformat(), reference="LW-4471")
    for d in (150, 110, 75, 40, 15):
        issue("ETH", "ST-SCI", 2, d, "SCI", "Lab practicals")
        issue("GLV", "ST-SCI", 3, d, "SCI", "Lab practicals")
    issue("LIT", "ST-SCI", 5, 60, "SCI")
    for d in (160, 120, 80, 33, 9):
        issue("BND", "ST-CLN", 1, d, "ADM", "Clinic use")
        issue("PCM", "ST-CLN", 2, d, "ADM", "Clinic use")
    move("DAMAGE", "SOAP", "ST-MAIN", 2, 28, reason="Bottles split in storage")
    move("ADJUSTMENT_OUT", "A4", "ST-MAIN", 3, 18, reason="Stocktake count lower than record", reference="ST-Q3")
    with backdate(db, _at(16, 13)):
        stock.transfer(db, cust, {"item_id": items["GLV"].id, "from_location_id": stores["ST-SCI"].id,
                                  "to_location_id": stores["ST-CLN"].id, "quantity": "2",
                                  "reference": "Clinic request"})
