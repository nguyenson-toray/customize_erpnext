import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt, cint, getdate, formatdate

from customize_erpnext.uniform_control.utils import get_item_available_qty
from customize_erpnext.uniform_control.doctype.employee_uniform_profile.employee_uniform_profile import (
    update_profile_after_allocation,
    revert_profile_after_cancel,
)


class UniformAllocation(Document):
    def validate(self):
        self._set_defaults()
        self._fill_available_qty()
        self._calc_total_qty()

    def before_submit(self):
        self._check_active_employees()
        self._check_type_consistency()
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
            self.set_warehouse = frappe.db.get_single_value(
                "Uniform Setting", "uniform_warehouse"
            )
        # Amended docs copy status from the cancelled original — reset while draft
        if self.docstatus == 0:
            self.status = "Draft"

    def _fill_available_qty(self):
        if not self.set_warehouse:
            return
        for row in self.items or []:
            if row.item_code:
                row.available_qty = get_item_available_qty(row.item_code, self.set_warehouse)

    def _calc_total_qty(self):
        self.total_qty = sum(cint(r.qty) for r in self.items or [])

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

    def _check_type_consistency(self):
        """New Issue must not contain already-issued employees; Supplement must
        not contain never-issued ones. Replacement is the manual escape hatch."""
        if self.allocation_type not in ("New Issue", "Supplement"):
            return

        employees = list({row.employee for row in self.items or [] if row.employee})
        if not employees:
            return

        # Tracking stores the exact variant; group by template (variant_of)
        issued = {}
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
            issued[(r.employee, r.template)] = r

        problems = []
        for row in self.items or []:
            template = _get_template(row.item_code)
            rec = issued.get((row.employee, template))
            total = cint(rec.total_issued_qty) if rec else 0

            if self.allocation_type == "New Issue" and total > 0:
                problems.append(
                    _("Row {0}: {1} already received {2} (last issued {3}). Use Supplement or Replacement.").format(
                        row.idx, row.employee, template, formatdate(rec.last_issue_date)
                    )
                )
            elif self.allocation_type == "Supplement" and total == 0:
                problems.append(
                    _("Row {0}: {1} has never been issued {2}. Use New Issue instead.").format(
                        row.idx, row.employee, template
                    )
                )

        if problems:
            frappe.throw(
                _("Rows do not match the Allocation Type:<br>") + "<br>".join(problems)
            )

    def _check_stock(self):
        # Multiple rows can share the same variant — check the aggregated qty
        required = {}
        for row in self.items or []:
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
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Issue"
        se.posting_date = self.posting_date
        se.company = self.company
        se.from_warehouse = self.set_warehouse

        # One detail row per allocation row, tagged with employee for traceability
        for row in self.items or []:
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
                se.cancel()

    def _update_profiles(self):
        for row in self.items or []:
            update_profile_after_allocation(
                employee=row.employee,
                item_code=row.item_code,
                qty=cint(row.qty),
                posting_date=self.posting_date,
            )

    def _revert_profiles(self):
        for row in self.items or []:
            revert_profile_after_cancel(
                employee=row.employee,
                item_template=_get_template(row.item_code),
            )


def _get_template(item_code):
    """Return variant_of (template) for an item, or item_code itself if no template."""
    template = frappe.db.get_value("Item", item_code, "variant_of")
    return template or item_code
