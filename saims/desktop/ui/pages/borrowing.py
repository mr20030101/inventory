"""Borrowing requests: request → approve / reject → release → receive return.

Several pending requests can be approved or rejected together, and one request can cover several pieces of
equipment. People who see only their own requests (teachers) get "My Requests"."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout

from saims.desktop.api import ApiError
from saims.desktop.ui import formatting as fmt
from saims.desktop.ui.forms import CONDITIONS, Field, dict_options, run_form
from saims.desktop.ui.pages.base import Page
from saims.desktop.ui.widgets import CheckCombo, Column, DataTable, confirm, hint, show_error, status_color

STATUS = {"pending": "Pending approval", "approved": "Approved", "released": "On loan", "returned": "Returned",
          "rejected": "Rejected", "cancelled": "Cancelled", "lost": "Lost"}


class BorrowingPage(Page):
    title = "Borrowing"

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        self.own = not api.can("borrowing.view")
        self._make_table()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.status = CheckCombo("All requests", "statuses")
        self.status.set_options([(v, k) for k, v in STATUS.items()])
        self.status.changed.connect(self.refresh)
        self.overdue = QCheckBox("Overdue only")
        self.overdue.toggled.connect(self.refresh)
        self.new_btn = self.button("New request", self.new_request, "swap", True, "borrowing.request")
        self.approve_btn = self.button("Approve", lambda: self.decide(True), permission="borrowing.approve")
        self.reject_btn = self.button("Reject", lambda: self.decide(False), permission="borrowing.approve")
        self.release_btn = self.button("Release", self.release, permission="borrowing.release")
        self.return_btn = self.button("Receive return", self.receive, permission="borrowing.receive_return")
        self.cancel_btn = self.button("Cancel request", self.cancel, permission="borrowing.request")
        for w in (self.status, self.overdue, self.new_btn, self.approve_btn, self.reject_btn, self.release_btn,
                  self.return_btn, self.cancel_btn):
            bar.addWidget(w)
        bar.addStretch()
        self.count = QLabel()
        self.count.setObjectName("Hint")
        bar.addWidget(self.count)
        if not self.own:
            bar.addWidget(self.export_button(self.table, "Borrowing requests",
                                             lambda: self.status.summary() if self.status.values() else ""))
        layout.addLayout(bar)
        layout.addWidget(self.table)
        if api.can("borrowing.approve"):
            layout.addWidget(hint("Tip: select several pending requests (Ctrl/Shift-click) to approve or reject "
                                  "them together."))
        self._update()

    def _make_table(self) -> DataTable:
        self.table = DataTable([
            Column("Request", "request_no"), Column("Asset", "asset_code"), Column("Item", "asset_name"),
            Column("Borrower", "borrower"),
            Column("Status", "status_label", color=lambda r: "danger" if r["overdue"] else status_color()(r)),
            Column("Needed", "date_needed", fmt.day), Column("Due back", "expected_return", fmt.day,
                                                             color=lambda r: "danger" if r["overdue"] else None),
            Column("Returned", "returned_at", fmt.when), Column("Purpose", "purpose"),
            Column("Decision note", "decision_note"),
        ], multi=self.api.can("borrowing.approve"))
        self.table.setColumnHidden(3, self.own)  # "Borrower" is always yourself
        self.table.selectionModel().selectionChanged.connect(self._update)
        return self.table

    def refresh(self) -> None:
        try:
            rows = self.api.get("/borrowing", status=self.status.values(), overdue_only=self.overdue.isChecked())
        except ApiError as exc:
            return show_error(self, exc)
        for r in rows:
            if r["overdue"]:
                r["status_label"] = f"Overdue ({(date.today() - date.fromisoformat(r['expected_return'])).days} d)"
        self.table.set_rows(rows)
        self.count.setText(f"{len(rows)} requests · {sum(r['overdue'] for r in rows)} overdue")
        self._update()

    def show_record(self, req_id: str) -> None:
        self.status.clear_selection(emit=False)
        self.overdue.setChecked(False)
        self.refresh()
        self.table.select_id(req_id)

    def _update(self) -> None:
        rows = self.table.selected_rows()
        s = (self.table.selected() or {}).get("status")
        all_pending = bool(rows) and all(r["status"] == "pending" for r in rows)
        self.approve_btn.setEnabled(all_pending)
        self.reject_btn.setEnabled(all_pending)
        suffix = f" ({len(rows)})" if len(rows) > 1 else ""
        self.approve_btn.setText("Approve" + suffix)
        self.reject_btn.setText("Reject" + suffix)
        self.release_btn.setEnabled(s == "approved")
        self.return_btn.setEnabled(s == "released")
        self.cancel_btn.setEnabled(s in {"pending", "approved"})

    def new_request(self) -> None:
        api = self.api
        try:
            catalogue = api.get("/borrowing/catalogue")
        except ApiError as exc:
            return show_error(self, exc)
        fields = [
            Field("asset_ids", "Equipment", "multi", required=True, placeholder="Choose one or more items…",
                  options=[(f"{a['asset_code']}  {a['name']}  ({a['status_label']})", a["id"]) for a in catalogue],
                  extra={"noun": "items"}, help="Tick several items to borrow them together, e.g. a camera and a "
                                                 "tripod. Each gets its own request number."),
        ]
        if not self.own:  # staff may request on someone's behalf; teachers always request for themselves
            fields.append(Field("borrower_id", "Borrower", "choice", required=True, allow_empty=False,
                                editable_choice=True, options=[(e["full_name"], e["id"]) for e in api.lookup("employees")],
                                default=api.me.get("employee_id")))
        fields += [
            Field("purpose", "Purpose", "multiline", required=True),
            Field("date_needed", "Needed on", "date", required=True),
            Field("expected_return", "Return by", "date", required=True,
                  default=(date.today() + timedelta(days=3)).isoformat()),
        ]
        if run_form(self, "New borrowing request", fields, None, lambda v: api.post("/borrowing/batch", v),
                    submit_label="Submit request",
                    intro="The request goes to an approver. Equipment is released only once it is approved and "
                          "available."):
            self.refresh()

    def decide(self, approve: bool) -> None:
        rows = self.table.selected_rows()
        if not rows:
            return
        fields = [Field("note", "Note" if approve else "Reason for rejecting", "multiline", required=not approve)]
        if len(rows) > 1:
            listing = "\n".join(f"{r['request_no']}  {r['borrower']}: {r['asset_name']}" for r in rows[:10])
            more = f"\n…and {len(rows) - 10} more" if len(rows) > 10 else ""
            verb = "Approve" if approve else "Reject"
            if run_form(self, f"{verb} {len(rows)} requests", fields, None,
                        lambda v: self.api.post("/borrowing/decisions", {"request_ids": [r["id"] for r in rows],
                                                                         "approve": approve, **v}),
                        submit_label=f"{verb} all", intro=f"{listing}{more}\n\nThe same note is recorded on each. "
                                                          "If any one cannot be decided, nothing changes."):
                self.refresh()
            return
        row = rows[0]
        if run_form(self, f"{'Approve' if approve else 'Reject'} {row['request_no']}", fields, None,
                    lambda v: self.api.post(f"/borrowing/{row['id']}/decision", {"approve": approve, **v}),
                    submit_label="Approve" if approve else "Reject",
                    intro=f"{row['borrower']} requests {row['asset_code']} {row['asset_name']} from "
                          f"{fmt.day(row['date_needed'])} to {fmt.day(row['expected_return'])}.\n"
                          f"Purpose: {row['purpose']}"):
            self.refresh()

    def release(self) -> None:
        row = self.table.selected()
        fields = [Field("condition", "Condition on release", "choice", options=dict_options(CONDITIONS),
                        allow_empty=False, default="good")]
        if row and run_form(self, f"Release {row['asset_code']}", fields, None,
                            lambda v: self.api.post(f"/borrowing/{row['id']}/release", v), submit_label="Release",
                            intro=f"Hand {row['asset_name']} to {row['borrower']}, due back "
                                  f"{fmt.day(row['expected_return'])}."):
            self.refresh()

    def receive(self) -> None:
        row = self.table.selected()
        fields = [Field("condition", "Condition on return", "choice", options=dict_options(CONDITIONS),
                        allow_empty=False, default="good",
                        help="Choose Damaged to flag the asset for follow-up."),
                  Field("note", "Note", "multiline")]
        if row and run_form(self, f"Receive {row['asset_code']}", fields, None,
                            lambda v: self.api.post(f"/borrowing/{row['id']}/return", v),
                            submit_label="Record return"):
            self.refresh()

    def cancel(self) -> None:
        row = self.table.selected()
        if row and confirm(self, "Cancel request", f"Cancel {row['request_no']}?"):
            self.call(lambda: self.api.post(f"/borrowing/{row['id']}/cancel"))
