# Whitelisted data sources for HR Overview dashboard "Custom" number cards.
#
# A Custom Number Card calls one of these with `filters` (the card's own baked
# filters) and expects a dict: {"value", "fieldtype", "route", "route_options"}.
# Kept read-only and cheap — cards refresh on every dashboard load.

import frappe


def _employee_scope():
	"""SQL clause + params keeping other companies' on-site staff out of headcount.

	Same Exclude Employee IDs setting the attendance engine uses, so the two can
	never report a different workforce.
	"""
	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
		get_excluded_employee_ids,
	)

	excluded = get_excluded_employee_ids()
	if not excluded:
		return "", {}
	return " AND e.name NOT IN %(excluded)s", {"excluded": tuple(sorted(excluded))}


def _maternity_leave_people():
	"""Number of ACTIVE employees currently on maternity leave, counted once.

	An employee can hold more than one Employee Maternity record (a duplicate or
	an overlapping re-entry), so counting records overcounts people — count
	DISTINCT employees instead. Restricted to Active employees so it lines up
	with the Active headcount it is subtracted from.
	"""
	clause, params = _employee_scope()
	return frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT em.employee)
		FROM `tabEmployee Maternity` em
		JOIN `tabEmployee` e ON e.name = em.employee
		WHERE em.status = 'Maternity Leave' AND e.status = 'Active'
		{clause}
		""",
		params,
	)[0][0]


@frappe.whitelist()
def maternity_leave(filters=None):
	"""People on maternity leave right now (distinct, active)."""
	return {
		"value": _maternity_leave_people(),
		"fieldtype": "Int",
		"route": ["query-report", "Employee Maternity Report"],
		"route_options": {"maternity_type": "Maternity Leave", "status": "Active"},
	}


@frappe.whitelist()
def net_headcount(filters=None):
	"""Active employees who are actually available today = Active - on Maternity Leave.

	Maternity employees keep status "Active" (they are on leave, not relieved),
	so a plain Active count includes them; this subtracts the ones currently on
	maternity leave, counted as distinct people.
	"""
	clause, params = _employee_scope()
	active = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabEmployee` e WHERE e.status = 'Active' {clause}", params
	)[0][0]

	return {
		"value": active - _maternity_leave_people(),
		"fieldtype": "Int",
		"route": ["List", "Employee"],
		"route_options": {"status": "Active"},
	}
