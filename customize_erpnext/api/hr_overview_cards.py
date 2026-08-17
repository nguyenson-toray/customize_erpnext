# Whitelisted data sources for HR Overview dashboard "Custom" number cards.
#
# A Custom Number Card calls one of these with `filters` (the card's own baked
# filters) and expects a dict: {"value", "fieldtype", "route", "route_options"}.
# Kept read-only and cheap — cards refresh on every dashboard load.
#
# The figures themselves come from api/headcount.py, shared with the Daily
# Attendance dashboard so the two can never report a different workforce.

import frappe

from customize_erpnext.api.headcount import (
	maternity_leave_employees,
	net_headcount_set,
)


@frappe.whitelist()
def maternity_leave(filters=None):
	"""People on maternity leave right now (distinct people, not records)."""
	return {
		"value": len(maternity_leave_employees()),
		"fieldtype": "Int",
		"route": ["query-report", "Employee Maternity Report"],
		"route_options": {"maternity_type": "Maternity Leave"},
	}


@frappe.whitelist()
def net_headcount(filters=None):
	"""Active employees who are actually available today."""
	return {
		"value": len(net_headcount_set()),
		"fieldtype": "Int",
		"route": ["List", "Employee"],
		"route_options": {"status": "Active"},
	}
