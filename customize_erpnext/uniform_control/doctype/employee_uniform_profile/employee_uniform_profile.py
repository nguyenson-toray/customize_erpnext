import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, today, add_months, date_diff, getdate

from customize_erpnext.uniform_control.utils import get_policy_for_item, get_shoe_rack_for_employee


class EmployeeUniformProfile(Document):
    def validate(self):
        self.shoe_rack_location = get_shoe_rack_for_employee(self.employee)
        self._refresh_items()

    def _refresh_items(self):
        """Recompute next_due_date + status on every save — single source of
        truth. Lets HR backfill history manually (item + last_issue_date) and
        get due dates generated automatically."""
        reminder_days = (
            cint(frappe.db.get_single_value("Uniform Setting", "reminder_days_before")) or 30
        )
        for row in self.items or []:
            row.next_due_date = self._compute_next_due(row)
            row.status = _compute_item_status(row, reminder_days)

    def _compute_next_due(self, row):
        if not row.last_issue_date:
            return None
        policy = get_policy_for_item(row.item_template, self.employee)
        if not policy or policy.get("one_time_issue"):
            return None
        cycle = cint(policy.get("reissue_cycle_months"))
        return add_months(row.last_issue_date, cycle) if cycle else None


def _compute_item_status(row, reminder_days=30):
    if not row.last_issue_date:
        return "Not Issued"
    if not row.next_due_date:
        return "Active"
    due = getdate(row.next_due_date)
    td = getdate(today())
    if td > due:
        return "Overdue"
    if date_diff(due, td) <= reminder_days:
        return "Due Soon"
    return "Active"


def update_profile_after_allocation(employee, item_template, qty, posting_date):
    """Called from Uniform Allocation controller after submit.
    next_due_date and status are computed in validate on save."""
    profile_name = frappe.db.get_value("Employee Uniform Profile", {"employee": employee})
    if not profile_name:
        return

    profile = frappe.get_doc("Employee Uniform Profile", profile_name)
    row = next((r for r in profile.items if r.item_template == item_template), None)
    if row:
        row.last_issue_date = posting_date
        row.last_issue_qty = qty
        row.total_issued_qty = (row.total_issued_qty or 0) + qty
    else:
        profile.append("items", {
            "item_template": item_template,
            "last_issue_date": posting_date,
            "last_issue_qty": qty,
            "total_issued_qty": qty,
        })

    profile.save(ignore_permissions=True)


def revert_profile_after_cancel(employee, item_template):
    """
    Called from Uniform Allocation controller after cancel.
    Recomputes the profile row from the remaining submitted allocations, so
    cancelling an old allocation does not wipe data from newer ones.
    """
    profile_name = frappe.db.get_value("Employee Uniform Profile", {"employee": employee})
    if not profile_name:
        return

    profile = frappe.get_doc("Employee Uniform Profile", profile_name)
    row = next((r for r in profile.items if r.item_template == item_template), None)
    if not row:
        return

    history = frappe.db.sql(
        """
        SELECT uai.qty, ua.posting_date
        FROM `tabUniform Allocation Item` uai
        INNER JOIN `tabUniform Allocation` ua ON ua.name = uai.parent
        INNER JOIN `tabItem` i ON i.name = uai.item_code
        WHERE uai.docstatus = 1
          AND uai.employee = %s
          AND COALESCE(NULLIF(i.variant_of, ''), i.name) = %s
        """,
        (employee, item_template),
        as_dict=True,
    )

    if history:
        last_date = max(getdate(h.posting_date) for h in history)
        row.total_issued_qty = sum(cint(h.qty) for h in history)
        row.last_issue_date = last_date
        row.last_issue_qty = sum(
            cint(h.qty) for h in history if getdate(h.posting_date) == last_date
        )
    else:
        row.total_issued_qty = 0
        row.last_issue_qty = 0
        row.last_issue_date = None

    profile.save(ignore_permissions=True)
