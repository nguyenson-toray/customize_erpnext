"""Uniform Tracking report — current issuance state per employee per
garment, read from the Issuance Tracking child table (Employee Uniform Item)."""
import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link",
         "options": "Employee", "width": 110},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link",
         "options": "Department", "width": 140},
        {"label": _("Section"), "fieldname": "section", "fieldtype": "Link",
         "options": "Section", "width": 120},
        {"label": _("Group"), "fieldname": "group", "fieldtype": "Link",
         "options": "Group", "width": 110},
        {"label": _("Uniform Type"), "fieldname": "template", "fieldtype": "Link",
         "options": "Item", "width": 140},
        {"label": _("Item"), "fieldname": "item", "fieldtype": "Link",
         "options": "Item", "width": 160},
        {"label": _("Last Issue Date"), "fieldname": "last_issue_date", "fieldtype": "Date", "width": 110},
        {"label": _("Last Qty"), "fieldname": "last_issue_qty", "fieldtype": "Int", "width": 80},
        {"label": _("Total Qty"), "fieldname": "total_issued_qty", "fieldtype": "Int", "width": 80},
        {"label": _("Next Due Date"), "fieldname": "next_due_date", "fieldtype": "Date", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
    ]


def get_data(filters):
    conditions = []
    values = {}
    if filters.get("status"):
        conditions.append("eui.status = %(status)s")
        values["status"] = filters.status
    if filters.get("employee"):
        conditions.append("p.employee = %(employee)s")
        values["employee"] = filters.employee
    if filters.get("department"):
        conditions.append("e.department = %(department)s")
        values["department"] = filters.department
    if filters.get("section"):
        conditions.append("e.custom_section = %(section)s")
        values["section"] = filters.section
    if filters.get("group"):
        conditions.append("e.custom_group = %(group)s")
        values["group"] = filters.group
    if filters.get("uniform_type"):
        conditions.append("COALESCE(NULLIF(i.variant_of, ''), i.name) = %(uniform_type)s")
        values["uniform_type"] = filters.uniform_type
    if filters.get("due_from"):
        conditions.append("eui.next_due_date >= %(due_from)s")
        values["due_from"] = filters.due_from
    if filters.get("due_to"):
        conditions.append("eui.next_due_date <= %(due_to)s")
        values["due_to"] = filters.due_to

    where = (" AND " + " AND ".join(conditions)) if conditions else ""

    return frappe.db.sql(
        f"""
        SELECT
            p.employee,
            e.employee_name,
            e.department,
            e.custom_section AS `section`,
            e.custom_group AS `group`,
            COALESCE(NULLIF(i.variant_of, ''), i.name) AS template,
            eui.item_template AS item,
            eui.last_issue_date,
            eui.last_issue_qty,
            eui.total_issued_qty,
            eui.next_due_date,
            eui.status
        FROM `tabEmployee Uniform Item` eui
        INNER JOIN `tabEmployee Uniform Profile` p ON p.name = eui.parent
        LEFT JOIN `tabEmployee` e ON e.name = p.employee
        LEFT JOIN `tabItem` i ON i.name = eui.item_template
        WHERE 1 = 1 {where}
        ORDER BY e.department, e.custom_section, p.employee, item
        """,
        values, as_dict=True,
    )
