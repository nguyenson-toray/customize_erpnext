import frappe
from frappe.model.document import Document
from frappe.utils import cint, today, add_months, date_diff, getdate

from customize_erpnext.uniform_control.utils import (
    get_reissue_months,
    get_shoe_rack_for_employee,
    apply_default_rules,
    load_active_rules,
)


class EmployeeUniformProfile(Document):
    def validate(self):
        setting = frappe.get_single("Uniform Setting")  # loaded once for this save
        self.shoe_rack_location = get_shoe_rack_for_employee(self.employee)
        # Fill shirt/cap defaults from rules when empty (unless manually overridden)
        if not self.manual_override and self.employee:
            apply_default_rules(self, setting=setting, force=False)
        self._refresh_items(setting)

    def _refresh_items(self, setting):
        """Recompute next_due_date + status on every save — single source of
        truth. Lets HR backfill history manually (item + last_issue_date) and
        get due dates generated automatically. Runs over BOTH tracking tables
        (shirts + other items)."""
        reminder_days = cint(setting.reminder_days_before) or 30
        for row in self.all_tracking_rows():
            row.next_due_date = self._compute_next_due(row, setting)
            row.status = _compute_item_status(row, reminder_days)

    def all_tracking_rows(self):
        """Every issuance-tracking row, across the shirt and other tables."""
        return list(self.shirt_items or []) + list(self.items or [])

    def find_tracking_row(self, template):
        """Locate a tracking row (either table) whose item resolves to template."""
        return next(
            (r for r in self.all_tracking_rows()
             if _template_of(r.item_template) == template),
            None,
        )

    def tracking_field_for(self, template, setting=None):
        """Which child table an item belongs to: 'shirt_items' when its rule
        category is Shirt, else 'items'."""
        return tracking_field_for(self.employee, template, setting)

    def _compute_next_due(self, row, setting):
        if not row.last_issue_date:
            return None
        cycle = get_reissue_months(_template_of(row.item_template), self.employee, setting)
        return add_months(row.last_issue_date, cycle) if cycle else None


def _template_of(item):
    """Template of an item (variant_of), or the item itself if it's a template."""
    return (frappe.db.get_value("Item", item, "variant_of") or item) if item else item


def tracking_field_for(employee, template, setting=None):
    """Child table a tracking row belongs to: 'shirt_items' for shirts, else
    'items' (caps, shoes, bottles, ...).

    "Is a shirt" is a property of the ITEM, so classify by item: the template
    is any active Shirt rule's item, or the employee's assigned shirt_item.
    (Matching the employee's own rule instead would mis-route shirts for
    employees no Shirt rule matches — e.g. missing gender.)"""
    tmpl = _template_of(template)
    shirt_rule_items = {
        r.item for r in load_active_rules() if r.category == "Shirt" and r.item
    }
    if tmpl in shirt_rule_items:
        return "shirt_items"
    shirt_item = frappe.db.get_value(
        "Employee Uniform Profile", {"employee": employee}, "shirt_item"
    ) if employee else None
    if shirt_item and _template_of(shirt_item) == tmpl:
        return "shirt_items"
    return "items"


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


def update_profile_after_allocation(employee, item_code, qty, posting_date):
    """Called from Uniform Allocation controller after submit. Stores the exact
    variant issued; rows are grouped per template (one slot per garment type).
    next_due_date and status are computed in validate on save."""
    profile_name = frappe.db.get_value("Employee Uniform Profile", {"employee": employee})
    if not profile_name:
        return

    template = _template_of(item_code)
    profile = frappe.get_doc("Employee Uniform Profile", profile_name)
    row = profile.find_tracking_row(template)
    if row:
        row.item_template = item_code
        row.last_issue_date = posting_date
        row.last_issue_qty = qty
        row.total_issued_qty = (row.total_issued_qty or 0) + qty
    else:
        profile.append(profile.tracking_field_for(template), {
            "item_template": item_code,
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
    row = profile.find_tracking_row(item_template)
    if not row:
        return

    history = frappe.db.sql(
        """
        SELECT uai.qty, uai.item_code, ua.posting_date
        FROM `tabUniform Allocation Item` uai
        INNER JOIN `tabUniform Allocation` ua ON ua.name = uai.parent
        INNER JOIN `tabItem` i ON i.name = uai.item_code
        WHERE uai.docstatus = 1
          AND uai.employee = %s
          AND COALESCE(NULLIF(i.variant_of, ''), i.name) = %s
        ORDER BY ua.posting_date ASC
        """,
        (employee, item_template),
        as_dict=True,
    )

    if history:
        last_date = max(getdate(h.posting_date) for h in history)
        row.total_issued_qty = sum(cint(h.qty) for h in history)
        row.last_issue_date = last_date
        last = [h for h in history if getdate(h.posting_date) == last_date]
        row.last_issue_qty = sum(cint(h.qty) for h in last)
        row.item_template = last[-1].item_code  # exact variant of the latest issue
    else:
        row.total_issued_qty = 0
        row.last_issue_qty = 0
        row.last_issue_date = None

    profile.save(ignore_permissions=True)
