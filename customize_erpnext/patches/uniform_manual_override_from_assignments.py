"""Uniform Control 09/11/2026 — Manual Override gets a strict meaning:
  - off: Employee Uniform Profile.shirt_item / cap_item = the Uniform Rule result,
    kept in sync automatically (no more Apply Defaults);
  - on: HR's pick wins (a blank field still follows the rule).

Profiles whose Shirt or Cap differs from the rule result today (imported shirts,
caps set before a newer rule) are ticked so nothing changes for them; their
fields equal to the rule are cleared (they keep following the rule). Every other
profile gets the rule result. Managed employees only (Uniform Setting prefix).
Idempotent: a second run finds nothing to change.
"""
import frappe
from frappe.utils import cint


def execute():
    from customize_erpnext.uniform_control.utils import (
        ASSIGN_FIELDS, clear_rules_cache, get_default_assignments, get_employee_id_prefix,
    )

    if not frappe.db.has_column("Employee Uniform Profile", "manual_override"):
        return
    clear_rules_cache()
    prefix = get_employee_id_prefix()
    profiles = frappe.db.sql(
        """
        SELECT p.name, p.manual_override, p.shirt_item, p.cap_item,
               e.designation, e.grade, e.gender, e.custom_group, e.custom_section
        FROM `tabEmployee Uniform Profile` p
        JOIN `tabEmployee` e ON e.name = p.employee
        WHERE p.employee LIKE %(like)s
        """,
        {"like": f"{prefix}%" if prefix else "%"}, as_dict=True,
    )
    ticked = synced = 0
    for p in profiles:
        rule = get_default_assignments(p)
        if cint(p.manual_override):
            continue  # already HR's pick
        differs = any(
            p.get(field) and p.get(field) != rule.get(cat) for cat, field in ASSIGN_FIELDS.items()
        )
        if differs:
            new = {"manual_override": 1}
            for cat, field in ASSIGN_FIELDS.items():
                if p.get(field) and p.get(field) == rule.get(cat):
                    new[field] = None
            ticked += 1
        else:
            new = {field: rule.get(cat) for cat, field in ASSIGN_FIELDS.items()}
            if all((p.get(f) or None) == (v or None) for f, v in new.items()):
                continue
            synced += 1
        frappe.db.set_value("Employee Uniform Profile", p.name, new, update_modified=False)
    print(f"Uniform profiles: {len(profiles)} checked, {ticked} set to Manual Override, "
          f"{synced} synced to the rules")
