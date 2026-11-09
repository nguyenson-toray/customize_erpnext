import frappe
from frappe.model.document import Document
from frappe.utils import cint, add_months, getdate

from customize_erpnext.uniform_control.utils import (
    EMPLOYEE_FIELDS,
    compute_item_status,
    get_reissue_months,
    get_reminder_days,
    get_shoe_rack_for_employee,
    load_active_rules,
    resolve_assignment,
    sync_assignment,
    template_of,
)


class EmployeeUniformProfile(Document):
    def onload(self):
        # "What this employee gets" table on the form
        self.set_onload("assignment", self.get_assignment())

    def validate(self):
        self.shoe_rack_location = get_shoe_rack_for_employee(self.employee)
        # Without Manual Override, Shirt / Cap always follow the Uniform Rules
        sync_assignment(self)
        self._refresh_items()

    def get_assignment(self):
        """Sizes (from the Employee) + the item per category this employee gets."""
        if not self.employee:
            return {}
        emp = frappe.db.get_value("Employee", self.employee, EMPLOYEE_FIELDS, as_dict=True)
        if not emp:
            return {}
        items = resolve_assignment(emp, self)
        return {
            "sizes": {"gender": emp.gender, "shirt": emp.custom_shirt_size,
                      "shoe": emp.custom_shoe_size},
            "items": [dict(v, category=cat) for cat, v in items.items()],
        }

    def _refresh_items(self):
        """Recompute next_due_date + status on every save — single source of
        truth. Runs over BOTH tracking tables (shirts + other items)."""
        reminder_days = get_reminder_days()
        for row in self.all_tracking_rows():
            row.next_due_date = self._compute_next_due(row)
            row.status = compute_item_status(row.last_issue_date, row.next_due_date, reminder_days)

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

    def _compute_next_due(self, row):
        if not row.last_issue_date:
            return None
        cycle = get_reissue_months(_template_of(row.item_template), self.employee)
        return add_months(row.last_issue_date, cycle) if cycle else None


def _template_of(item):
    """Template of an item (variant_of), or the item itself if it's a template."""
    return template_of(item)


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
    return compute_item_status(row.last_issue_date, row.next_due_date, reminder_days)


def _allocation_history(employee, template, exclude_allocation=None):
    """Submitted Uniform Allocation rows of an employee for a template."""
    return frappe.db.sql(
        """
        SELECT uai.qty, uai.item_code, ua.posting_date
        FROM `tabUniform Allocation Item` uai
        INNER JOIN `tabUniform Allocation` ua ON ua.name = uai.parent
        INNER JOIN `tabItem` i ON i.name = uai.item_code
        WHERE uai.docstatus = 1
          AND uai.employee = %(employee)s
          AND COALESCE(NULLIF(i.variant_of, ''), i.name) = %(template)s
          AND uai.parent != %(exclude)s
        ORDER BY ua.posting_date ASC
        """,
        {"employee": employee, "template": template, "exclude": exclude_allocation or ""},
        as_dict=True,
    )


def apply_history(row, history):
    """Tracking row = history imported before ERP (base_* fields) + the
    submitted allocations. Used by cancel and Rebuild Tracking, so neither
    wipes the imported history."""
    base_total = cint(row.get("base_total_qty"))
    if history:
        last_date = max(getdate(h.posting_date) for h in history)
        last = [h for h in history if getdate(h.posting_date) == last_date]
        row.total_issued_qty = base_total + sum(cint(h.qty) for h in history)
        row.last_issue_date = last_date
        row.last_issue_qty = sum(cint(h.qty) for h in last)
        row.item_template = last[-1].item_code  # exact variant of the latest issue
    elif row.get("base_last_issue_date") or base_total:
        row.item_template = row.get("base_item") or row.item_template
        row.last_issue_date = row.get("base_last_issue_date")
        row.last_issue_qty = cint(row.get("base_last_issue_qty"))
        row.total_issued_qty = base_total
    else:
        row.total_issued_qty = 0
        row.last_issue_qty = 0
        row.last_issue_date = None


def update_profile_after_allocation(employee, item_code, qty, posting_date, allocation=None):
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
        # First ERP allocation on an imported row: keep the imported history so
        # a cancel can restore it (apply_history).
        if (not row.get("base_last_issue_date") and not cint(row.get("base_total_qty"))
                and (row.last_issue_date or cint(row.total_issued_qty))
                and not _allocation_history(employee, template, allocation)):
            row.base_item = row.item_template
            row.base_last_issue_date = row.last_issue_date
            row.base_last_issue_qty = cint(row.last_issue_qty)
            row.base_total_qty = cint(row.total_issued_qty)
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

    # on_cancel runs after docstatus = 2 is written, so the cancelled allocation
    # is no longer part of the history
    apply_history(row, _allocation_history(employee, item_template))
    profile.save(ignore_permissions=True)
