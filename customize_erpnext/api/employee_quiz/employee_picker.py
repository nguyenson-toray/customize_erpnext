# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Employee lookups for the Add Employees / Paste Codes buttons on TIQN Quiz and
Employee Self Update Info Setting.

They only return rows; the form adds them to its Employees table and the user
saves once. Nothing here needs a saved quiz — a quiz that is Open with an empty
list cannot be saved, so requiring a save first would be a dead end.
"""

import re

import frappe
from frappe import _
from frappe.utils import getdate

# Forms that use these buttons. The caller must be allowed to edit the form it adds
# rows to (TIQN Quiz: Quiz Manager; the Setting: HR Manager).
FORMS = ("TIQN Quiz", "Employee Self Update Info Setting")
EMPLOYEE_PREFIX = "TIQN-"
ROW_FIELDS = ["name as employee", "employee_name", "department", "custom_section", "custom_group", "date_of_joining"]


def _require_form_write(doctype):
	if doctype not in FORMS or not frappe.has_permission(doctype, "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def find_employees(date_from=None, date_to=None, department=None, section=None, group=None, doctype="TIQN Quiz"):
	"""Active employees matching all filters (none = every active employee), as Employees-table rows."""
	_require_form_write(doctype)
	filters = {"status": "Active"}
	if date_from and date_to:
		filters["date_of_joining"] = ["between", [getdate(date_from), getdate(date_to)]]
	elif date_from:
		filters["date_of_joining"] = [">=", getdate(date_from)]
	elif date_to:
		filters["date_of_joining"] = ["<=", getdate(date_to)]
	if department:
		filters["department"] = department
	if section:
		filters["custom_section"] = section
	if group:
		filters["custom_group"] = group
	return frappe.get_all("Employee", filters=filters, fields=ROW_FIELDS, order_by="name asc")


def _resolve_code(token):
	"""'TIQN-0148' / 'tiqn-0148' / '148' -> employee name, or None."""
	name = frappe.db.get_value("Employee", token)  # case-insensitive under unicode_ci
	if not name and token.isdigit():
		name = frappe.db.get_value("Employee", EMPLOYEE_PREFIX + token.zfill(4))
	return name


@frappe.whitelist()
def resolve_codes(codes, doctype="TIQN Quiz"):
	"""Pasted codes (any separator) -> {rows, not_found, not_active}."""
	_require_form_write(doctype)
	names, not_found = [], []
	for token in dict.fromkeys(t for t in re.split(r"[\s,;]+", codes or "") if t):
		name = _resolve_code(token)
		if not name:
			not_found.append(token)
		elif name not in names:
			names.append(name)
	rows = frappe.get_all("Employee", filters={"name": ["in", names or [""]]}, fields=ROW_FIELDS + ["status"])
	by_name = {r.employee: r for r in rows}
	active = [by_name[n] for n in names if by_name[n].status == "Active"]
	for r in active:
		r.pop("status")
	return {
		"rows": active,
		"not_found": not_found,
		"not_active": [n for n in names if by_name[n].status != "Active"],
	}
