# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Every line of every payslip of one pay period, one column per line - read from each
payslip's own copy of its lines (Payslip Structure, 28/10/2026), so the columns are the
lines of that period whatever the structure of other periods. Replaces exporting the old
`sc_*` fields."""

import json

import frappe
from frappe import _

from customize_erpnext.employee_portal import payslip_structure as pss
from customize_erpnext.employee_portal.utils import code_key, validate_period


def execute(filters=None):
	filters = frappe._dict(filters or {})
	try:
		period = validate_period(filters.period)
	except frappe.ValidationError:
		frappe.throw(_("Period must look like YYYY-MM."))

	conditions = {"period": period}
	for f in ("status", "section", "group"):
		if filters.get(f):
			conditions[f] = filters.get(f)
	payslips = frappe.get_all(
		"TIQN Payslip",
		filters=conditions,
		fields=["name", "employee", "employee_name", "designation", "section", "group", "status", "structure", "lines_json"],
		order_by="employee",
	)

	# Columns = the lines found on the payslips (one structure per period; the union keeps
	# a column even if a payslip was somehow imported with fewer lines).
	lines = {}
	rows = []
	for no, ps in enumerate(payslips, start=1):
		row = {k: ps[k] for k in ("name", "employee", "employee_name", "designation", "section", "group", "status", "structure")}
		row.update(no=no)
		for r in json.loads(ps.lines_json or "[]"):
			lines.setdefault(r["code"], r)
			if (r.get("unit") or "VND") == "VND":
				row[_amount_field(r["code"])] = r.get("amount")
			if r.get("quantity") is not None:
				row[_quantity_field(r["code"])] = r.get("quantity")
		rows.append(row)

	columns = [
		# Data, not Int: the report's total row would add the row numbers up.
		{"fieldname": "no", "label": _("No."), "fieldtype": "Data", "width": 55},
		{"fieldname": "name", "label": _("Payslip"), "fieldtype": "Link", "options": "TIQN Payslip", "width": 150},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 105},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Data", "width": 120},
		{"fieldname": "section", "label": _("Section"), "fieldtype": "Data", "width": 100},
		{"fieldname": "group", "label": _("Group"), "fieldtype": "Data", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
	]
	for code in sorted(lines, key=code_key):
		r = lines[code]
		unit = pss.quantity_unit_of(r)
		if unit:
			columns.append(
				{
					"fieldname": _quantity_field(code),
					"label": f"{code} {_('Days') if unit == 'Day' else _('Hours')}",
					"fieldtype": "Float",
					"precision": 2,
					"width": 90,
				}
			)
		if (r.get("unit") or "VND") == "VND":
			columns.append(
				{
					"fieldname": _amount_field(code),
					"label": f"{code} {r.get('label_en') or ''}".strip(),
					"fieldtype": "Float",
					"precision": 0,
					"width": 130,
				}
			)
	columns.append({"fieldname": "structure", "label": _("Payslip Structure"), "fieldtype": "Link", "options": "TIQN Payslip Structure", "width": 120})
	return columns, rows


def _amount_field(code):
	return "l_" + code.replace(".", "_")


def _quantity_field(code):
	return "q_" + code.replace(".", "_")
