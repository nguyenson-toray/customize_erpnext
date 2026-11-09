"""Uniform Assignment Preview — what every managed Active employee gets under the
current Uniform Rules: the item per category, resolved to the size variant
(sizes from the Employee; no shoe size = Free Size), with the problems that
would make Get Employees skip a row (no rule, no size, no variant)."""
import frappe
from frappe import _

from customize_erpnext.uniform_control.utils import (
    CATEGORY_VARIANT_BY,
    EMPLOYEE_FIELDS,
    build_variant_cache,
    chosen_item,
    get_employee_id_prefix,
    get_rules_by_category,
    load_active_rules,
    resolve_assignment,
)

CATEGORIES = ("Shirt", "Cap", "Shoe", "Bottle")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return get_columns(), get_data(filters)


def get_columns():
    cols = [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
        {"label": _("Section"), "fieldname": "section", "fieldtype": "Link", "options": "Section", "width": 110},
        {"label": _("Group"), "fieldname": "group", "fieldtype": "Link", "options": "Group", "width": 100},
        {"label": _("Designation"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 140},
        {"label": _("Grade"), "fieldname": "grade", "fieldtype": "Link", "options": "Employee Grade", "width": 90},
        {"label": _("Gender"), "fieldname": "gender", "fieldtype": "Data", "width": 70},
        {"label": _("Shirt Size"), "fieldname": "shirt_size", "fieldtype": "Data", "width": 70},
        {"label": _("Shoe Size"), "fieldname": "shoe_size", "fieldtype": "Data", "width": 75},
        {"label": _("Manual Override"), "fieldname": "manual_override", "fieldtype": "Check", "width": 80},
    ]
    for cat in CATEGORIES:
        cols.append({"label": _(cat), "fieldname": cat.lower(), "fieldtype": "Data", "width": 190})
    cols.append({"label": _("Problems"), "fieldname": "problems", "fieldtype": "Data", "width": 320})
    return cols


def get_data(filters):
    emp_filters = {"status": "Active"}
    prefix = get_employee_id_prefix()
    if prefix:
        emp_filters["name"] = ["like", f"{prefix}%"]
    for f, col in (("department", "department"), ("section", "custom_section"), ("group", "custom_group")):
        if filters.get(f):
            emp_filters[col] = filters.get(f)
    employees = frappe.get_all("Employee", filters=emp_filters, fields=EMPLOYEE_FIELDS, order_by="name asc")
    if not employees:
        return []

    profiles = {
        p.employee: p for p in frappe.get_all(
            "Employee Uniform Profile",
            filters={"employee": ["in", [e.name for e in employees]]},
            fields=["employee", "manual_override", "shirt_item", "cap_item"],
        )
    }
    rule_categories = {r.category for r in load_active_rules() if r.item}
    rules_of = {e.name: get_rules_by_category(e) for e in employees}
    variant_cache = build_variant_cache(list({
        chosen_item(profiles.get(e.name), cat, rule)
        for e in employees for cat, rule in rules_of[e.name].items() if cat in CATEGORY_VARIANT_BY
    }))
    tmpl_cache = {}

    data = []
    for e in employees:
        profile = profiles.get(e.name)
        assignment = resolve_assignment(e, profile, rules_of[e.name], variant_cache, tmpl_cache)
        row = {
            "employee": e.name, "employee_name": e.employee_name, "section": e.custom_section,
            "group": e.custom_group, "designation": e.designation, "grade": e.grade,
            "gender": e.gender, "shirt_size": e.custom_shirt_size, "shoe_size": e.custom_shoe_size,
            "manual_override": (profile or {}).get("manual_override") or 0,
        }
        problems = []
        for cat in CATEGORIES:
            a = assignment.get(cat)
            if not a:
                row[cat.lower()] = ""
                if cat in rule_categories:
                    problems.append(_("No {0} rule").format(_(cat)))
                continue
            row[cat.lower()] = a.variant or a.chosen
            if a.error:
                problems.append(f"{_(cat)}: {a.error}")
        row["problems"] = "; ".join(problems)
        if filters.get("only_problems") and not problems:
            continue
        if filters.get("manual_only") and not row["manual_override"]:
            continue
        data.append(row)
    return data
