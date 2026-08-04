# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	"""Same columns as the "Labor Contract Report 1" report builder view."""
	return [
		{"fieldname": "name", "label": _("ID"), "fieldtype": "Link",
		 "options": "Labor Contract", "width": 180},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link",
		 "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data",
		 "width": 190},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link",
		 "options": "Designation", "width": 150},
		{"fieldname": "custom_section", "label": _("Section"), "fieldtype": "Link",
		 "options": "Section", "width": 120},
		{"fieldname": "custom_group", "label": _("Group"), "fieldtype": "Link",
		 "options": "Group", "width": 120},
		{"fieldname": "contract_type", "label": _("Contract Type"), "fieldtype": "Link",
		 "options": "Employment Type", "width": 200},
		{"fieldname": "start_date", "label": _("Start Date"), "fieldtype": "Date",
		 "width": 110},
		{"fieldname": "end_date", "label": _("End Date"), "fieldtype": "Date",
		 "width": 110},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "next_sign_date", "label": _("Next Sign Date"), "fieldtype": "Date",
		 "width": 120},
		{"fieldname": "next_contract_type", "label": _("Next Contract Type"),
		 "fieldtype": "Link", "options": "Employment Type", "width": 200},
	]


def _build_conditions(filters):
	conditions = []
	values = {}

	# The two date ranges are independent: Start Date narrows to contracts that
	# began in a period, Next Sign Date to contracts due for renewal in one.
	date_ranges = [
		("start_date", "from_start_date", "to_start_date"),
		("next_sign_date", "from_next_sign_date", "to_next_sign_date"),
	]
	for field, from_key, to_key in date_ranges:
		if filters.get(from_key):
			conditions.append(f"lc.{field} >= %({from_key})s")
			values[from_key] = filters[from_key]
		if filters.get(to_key):
			conditions.append(f"lc.{field} <= %({to_key})s")
			values[to_key] = filters[to_key]

	for field in ("employee", "status", "contract_type", "custom_section", "custom_group"):
		if filters.get(field):
			conditions.append(f"lc.{field} = %({field})s")
			values[field] = filters[field]

	if filters.get("employee_status"):
		conditions.append("emp.status = %(employee_status)s")
		values["employee_status"] = filters["employee_status"]

	where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
	return where, values


def get_data(filters):
	where, values = _build_conditions(filters)

	return frappe.db.sql(
		f"""
		SELECT
			lc.name, lc.employee, lc.employee_name, lc.designation,
			lc.custom_section, lc.custom_group, lc.contract_type,
			lc.start_date, lc.end_date, lc.status,
			lc.next_sign_date, lc.next_contract_type
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		{where}
		ORDER BY lc.next_sign_date IS NULL, lc.next_sign_date, lc.employee
		""",
		values,
		as_dict=True,
	)
