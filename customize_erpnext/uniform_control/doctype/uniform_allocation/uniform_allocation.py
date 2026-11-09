import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt, cint, formatdate

from customize_erpnext.uniform_control.utils import get_item_available_qty, template_of
from customize_erpnext.uniform_control.doctype.employee_uniform_profile.employee_uniform_profile import (
    update_profile_after_allocation,
    revert_profile_after_cancel,
)

# One kind of allocation (simplified 09/11/2026): every row carries its own reason.
# Get Employees fills New Issue / Periodic Supplement; rows added by hand pick
# Damaged / Lost / Size Change.
ISSUE_REASONS = ("New Issue", "Periodic Supplement", "Damaged", "Lost", "Size Change")


class UniformAllocation(Document):
    def validate(self):
        self._set_defaults()
        self._dedupe_items()
        self._fill_available_qty()
        self._calc_total_qty()
        self._warn_reason_mismatch()

    def before_submit(self):
        self._check_active_employees()
        self._check_reasons()
        self._check_stock()

    def on_submit(self):
        self._create_stock_entry()
        self._update_profiles()
        self.db_set("status", "Submitted")

    def on_cancel(self):
        self._cancel_stock_entry()
        self._revert_profiles()
        self.db_set("status", "Cancelled")

    # ------------------------------------------------------------------ helpers

    def _set_defaults(self):
        if not self.posting_date:
            self.posting_date = today()
        if not self.set_warehouse:
            self.set_warehouse = frappe.db.get_single_value("Uniform Setting", "uniform_warehouse")
        if not self.set_warehouse:
            frappe.throw(_("Set the Uniform Warehouse in Uniform Setting first."))
        # The company owning the uniform warehouse (no hardcoded name)
        company = frappe.db.get_value("Warehouse", self.set_warehouse, "company")
        if company:
            self.company = company
        # Amended docs copy status from the cancelled original — reset while draft
        if self.docstatus == 0:
            self.status = "Draft"

    def _fill_available_qty(self):
        for row in self.items or []:
            if row.item_code:
                row.available_qty = get_item_available_qty(row.item_code, self.set_warehouse)

    def _calc_total_qty(self):
        self.total_qty = sum(cint(r.qty) for r in self.items or [])

    def _dedupe_items(self):
        """Remove duplicate rows (same employee + item) — can pile up from
        repeated 'Get Employees'. Keep the first, warn about the rest."""
        seen = set()
        kept, removed = [], []
        for row in self.items or []:
            key = (row.employee, row.item_code)
            if key in seen:
                removed.append("{0} / {1}".format(row.employee, row.item_code))
                continue
            seen.add(key)
            kept.append(row)
        if removed:
            self.set("items", kept)
            frappe.msgprint(
                _("Removed {0} duplicate row(s) (same employee + item):<br>").format(len(removed))
                + "<br>".join(removed),
                title=_("Duplicates Removed"), indicator="orange",
            )

    def _issued_totals(self):
        """{(employee, template): tracking row} for the employees on this doc."""
        employees = list({row.employee for row in self.items or [] if row.employee})
        if not employees:
            return {}
        out = {}
        for r in frappe.db.sql(
            """
            SELECT p.employee,
                   COALESCE(NULLIF(i.variant_of, ''), i.name) AS template,
                   eui.total_issued_qty, eui.last_issue_date
            FROM `tabEmployee Uniform Item` eui
            INNER JOIN `tabEmployee Uniform Profile` p ON p.name = eui.parent
            INNER JOIN `tabItem` i ON i.name = eui.item_template
            WHERE p.employee IN %(employees)s
            """,
            {"employees": employees},
            as_dict=True,
        ):
            out[(r.employee, r.template)] = r
        return out

    def _warn_reason_mismatch(self):
        """Not blocking: a 'New Issue' row for someone who already received that
        uniform type is usually a mistake (re-issue or replacement)."""
        if self.docstatus != 0 or not self.items:
            return
        issued = self._issued_totals()
        notes = []
        for row in self.items:
            if row.issue_reason != "New Issue" or not row.item_code:
                continue
            rec = issued.get((row.employee, template_of(row.item_code)))
            if rec and cint(rec.total_issued_qty) > 0:
                notes.append(_("Row {0}: {1} already received {2} (last issued {3}).").format(
                    row.idx, row.employee, template_of(row.item_code), formatdate(rec.last_issue_date)))
        if notes:
            frappe.msgprint("<br>".join(notes), title=_("Check Issue Reason"), indicator="orange")

    def _check_reasons(self):
        missing = [str(r.idx) for r in self.items or [] if r.issue_reason not in ISSUE_REASONS]
        if missing:
            frappe.throw(_("Choose an Issue Reason on row(s) {0}.").format(", ".join(missing)))

    def _check_active_employees(self):
        for row in self.items or []:
            emp = frappe.db.get_value(
                "Employee", row.employee, ["status", "relieving_date"], as_dict=True
            )
            if not emp:
                frappe.throw(_("Row {0}: Employee {1} not found.").format(row.idx, row.employee))
            if emp.status != "Active" or emp.relieving_date:
                frappe.throw(
                    _("Row {0}: Employee {1} is not Active or has a relieving date.").format(
                        row.idx, row.employee
                    )
                )

    def _check_stock(self):
        # Multiple rows can share the same variant — check the aggregated qty.
        # Reuse-old-item rows come from recovered stock, not the warehouse → skip.
        required = {}
        for row in self.items or []:
            if row.reuse_old_item:
                continue
            required[row.item_code] = required.get(row.item_code, 0) + cint(row.qty)

        shortage = []
        for item_code, qty in required.items():
            avail = get_item_available_qty(item_code, self.set_warehouse)
            if qty > flt(avail):
                shortage.append(
                    _("{0}: needs {1} in total but only {2} available in {3}.").format(
                        item_code, qty, avail, self.set_warehouse
                    )
                )
        if shortage:
            frappe.throw(
                _("Insufficient stock for the following items:<br>") + "<br>".join(shortage)
            )

    def _create_stock_entry(self):
        # Reuse-old-item rows don't move warehouse stock — exclude them.
        issue_rows = [r for r in (self.items or []) if not r.reuse_old_item]
        if not issue_rows:
            # Everything is a reused item → no stock movement, no Stock Entry.
            return

        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Issue"
        se.posting_date = self.posting_date
        se.company = self.company
        se.from_warehouse = self.set_warehouse

        # One detail row per allocation row, tagged with employee for traceability
        for row in issue_rows:
            se.append("items", {
                "item_code": row.item_code,
                "qty": cint(row.qty),
                "s_warehouse": self.set_warehouse,
                "custom_uniform_employee": row.employee,
                "custom_uniform_allocation": self.name,
            })

        se.insert(ignore_permissions=True)
        se.submit()

        self.db_set("stock_entry", se.name)

    def _cancel_stock_entry(self):
        if self.stock_entry:
            se = frappe.get_doc("Stock Entry", self.stock_entry)
            if se.docstatus == 1:
                se.flags.ignore_permissions = True
                se.cancel()

    def _update_profiles(self):
        for row in self.items or []:
            update_profile_after_allocation(
                employee=row.employee,
                item_code=row.item_code,
                qty=cint(row.qty),
                posting_date=self.posting_date,
                allocation=self.name,
            )

    def _revert_profiles(self):
        for row in self.items or []:
            revert_profile_after_cancel(
                employee=row.employee,
                item_template=template_of(row.item_code),
            )
