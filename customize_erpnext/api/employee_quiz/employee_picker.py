# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Employee lookups for the Add Employees / Paste Codes buttons on TIQN Quiz.

They only return rows; the form adds them to its Employees table and the user
saves once. Nothing here needs a saved quiz — a quiz that is Open with an empty
list cannot be saved, so requiring a save first would be a dead end.
"""

import re

import frappe
from frappe import _
from frappe.utils import getdate

MANAGER_ROLES = ("Quiz Manager", "System Manager")
EMPLOYEE_PREFIX = "TIQN-"
ROW_FIELDS = ["name as employee", "employee_name", "department", "custom_section", "custom_group", "date_of_joining"]


def _require_manager():
	if not set(frappe.get_roles()) & set(MANAGER_ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def find_employees(date_from=None, date_to=None, section=None, group=None):
	"""Active employees matching all filters, as Employees-table rows."""
	_require_manager()
	filters = {"status": "Active"}
	if date_from and date_to:
		filters["date_of_joining"] = ["between", [getdate(date_from), getdate(date_to)]]
	elif date_from:
		filters["date_of_joining"] = [">=", getdate(date_from)]
	elif date_to:
		filters["date_of_joining"] = ["<=", getdate(date_to)]
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
def resolve_codes(codes):
	"""Pasted codes (any separator) -> {rows, not_found, not_active}."""
	_require_manager()
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
