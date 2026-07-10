import frappe

from customize_erpnext.uniform_control.utils import get_rule_for_tracking
from customize_erpnext.uniform_control.doctype.employee_uniform_profile.employee_uniform_profile import (
    _template_of,
)


def execute():
    """Route existing Employee Uniform Item rows into the new 'shirt_items'
    child table when their Uniform Rule category is Shirt.

    Only the generic `parentfield` column is switched — the tracking data
    itself is unchanged — so no profile resave/recompute is needed.
    """
    if not frappe.db.table_exists("Employee Uniform Item"):
        return

    setting = frappe.get_single("Uniform Setting")
    emp_of = dict(
        frappe.db.sql("SELECT name, employee FROM `tabEmployee Uniform Profile`")
    )

    rows = frappe.db.sql(
        """
        SELECT name, parent, item_template
        FROM `tabEmployee Uniform Item`
        WHERE parenttype = 'Employee Uniform Profile'
        """,
        as_dict=True,
    )

    category_cache = {}  # (employee, template) -> category
    to_shirt = []
    for r in rows:
        emp = emp_of.get(r.parent)
        if not emp or not r.item_template:
            continue
        tmpl = _template_of(r.item_template)
        key = (emp, tmpl)
        if key not in category_cache:
            rule = get_rule_for_tracking(tmpl, emp, setting)
            category_cache[key] = rule.category if rule else None
        if category_cache[key] == "Shirt":
            to_shirt.append(r.name)

    for start in range(0, len(to_shirt), 500):
        chunk = to_shirt[start:start + 500]
        frappe.db.sql(
            """
            UPDATE `tabEmployee Uniform Item`
            SET parentfield = 'shirt_items'
            WHERE name IN %(names)s
            """,
            {"names": tuple(chunk)},
        )
    frappe.db.commit()

    frappe.logger().info(
        f"split_shirt_tracking: moved {len(to_shirt)} row(s) to shirt_items"
    )
