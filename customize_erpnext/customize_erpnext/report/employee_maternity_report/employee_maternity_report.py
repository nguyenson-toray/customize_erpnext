# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, date_diff
from datetime import date


def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data


def get_columns(filters=None):
	"""Define report columns"""
	show_detail = filters and filters.get("detail")

	columns = [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{
			"fieldname": "employee_name",
			"label": _("Employee Name"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "department",
			"label": _("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": 120,
		},
		{
			"fieldname": "custom_section",
			"label": _("Section"),
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"fieldname": "custom_group",
			"label": _("Group"),
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"fieldname": "date_of_joining",
			"label": _("Date of Joining"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "seniority",
			"label": _("Seniority (Months)"),
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"fieldname": "type",
			"label": _("Maternity Type"),
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"fieldname": "from_date",
			"label": _("From Date"),
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"fieldname": "to_date",
			"label": _("To Date"),
			"fieldtype": "Date",
			"width": 100,
		},
	]

	if show_detail:
		columns.append({
			"fieldname": "duration_days",
			"label": _("Duration (Days)"),
			"fieldtype": "Int",
			"width": 120,
		})

	columns.extend([
		{
			"fieldname": "estimated_due_date",
			"label": _("Estimated Due Date"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "date_of_birth",
			"label": _("Date of Birth"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "gestational_age",
			"label": _("Gestational Age (Months)"),
			"fieldtype": "Float",
			"precision": 1,
			"width": 140,
		},
		{
			"fieldname": "note",
			"label": _("Note"),
			"fieldtype": "Data",
			"width": 200,
		},
	])

	if show_detail:
		columns.append({
			"fieldname": "relieving_date",
			"label": _("Relieving Date"),
			"fieldtype": "Date",
			"width": 120,
		})

	columns.append({
		"fieldname": "status",
		"label": _("Status"),
		"fieldtype": "Data",
		"width": 100,
	})

	return columns


def get_data(filters):
	"""
	Query Employee Maternity (cấu trúc mới: 1 record/employee) và expand
	thành nhiều rows — mỗi row là 1 giai đoạn (Pregnant / Maternity Leave / Young Child).
	"""
	conditions, params = _build_conditions(filters)

	records = frappe.db.sql(f"""
		SELECT
			emp.name         AS employee,
			emp.employee_name,
			emp.department,
			emp.custom_section,
			emp.custom_group,
			emp.date_of_joining,
			emp.relieving_date,
			mt.pregnant_from_date,
			mt.pregnant_to_date,
			mt.estimated_due_date,
			mt.maternity_from_date,
			mt.maternity_to_date,
			mt.youg_child_from_date,
			mt.youg_child_to_date,
			mt.date_of_birth,
			mt.apply_benefit,
			mt.note
		FROM `tabEmployee` emp
		INNER JOIN `tabEmployee Maternity` mt ON emp.name = mt.employee
		WHERE {conditions}
		ORDER BY emp.department, emp.custom_section, emp.custom_group, emp.employee_name
	""", params, as_dict=True)

	today_date = date.today()
	data = []
	maternity_type_filter = filters.get("maternity_type") if filters else None

	for rec in records:
		seniority = _calc_seniority(rec.date_of_joining, today_date)

		# Expand thành các rows theo từng giai đoạn
		periods = [
			{
				"type": "Pregnant",
				"from_date": rec.pregnant_from_date,
				"to_date": rec.pregnant_to_date,
			},
			{
				"type": "Maternity Leave",
				"from_date": rec.maternity_from_date,
				"to_date": rec.maternity_to_date,
			},
			{
				"type": "Young Child",
				"from_date": rec.youg_child_from_date,
				"to_date": rec.youg_child_to_date,
			},
		]

		for period in periods:
			if not period["from_date"]:
				continue  # Giai đoạn chưa có dữ liệu

			# Filter theo maternity_type nếu có
			if maternity_type_filter and period["type"] != maternity_type_filter:
				continue

			from_date = period["from_date"]
			to_date = period["to_date"]

			# Filter theo date range từ filters
			if filters:
				if filters.get("from_date") and from_date < getdate(filters["from_date"]):
					continue
				if filters.get("to_date") and to_date and to_date > getdate(filters["to_date"]):
					continue

			# Status
			status = _calc_status(from_date, to_date, today_date)
			if filters and filters.get("status") and status != filters["status"]:
				continue

			# Duration
			eff_to = to_date or rec.estimated_due_date
			duration_days = (date_diff(eff_to, from_date) + 1) if eff_to else None

			# Gestational age (chỉ cho Pregnant)
			gestational_age = None
			if period["type"] == "Pregnant" and rec.estimated_due_date:
				gestational_age = _calc_gestational_age(rec.estimated_due_date, today_date)

			data.append({
				"employee": rec.employee,
				"employee_name": rec.employee_name,
				"department": rec.department,
				"custom_section": rec.custom_section,
				"custom_group": rec.custom_group,
				"date_of_joining": rec.date_of_joining,
				"seniority": seniority,
				"type": period["type"],
				"from_date": from_date,
				"to_date": to_date,
				"duration_days": duration_days,
				"estimated_due_date": rec.estimated_due_date if period["type"] == "Pregnant" else None,
				"date_of_birth": rec.date_of_birth if period["type"] == "Young Child" else None,
				"gestational_age": gestational_age,
				"note": rec.note,
				"relieving_date": rec.relieving_date,
				"status": status,
			})

	return data


def _build_conditions(filters):
	"""Build WHERE clause và params dict"""
	if not filters:
		filters = {}

	conditions = ["1=1"]
	params = {}

	if filters.get("employee"):
		conditions.append("emp.name = %(employee)s")
		params["employee"] = filters["employee"]

	if filters.get("employee_name"):
		conditions.append("emp.employee_name LIKE %(employee_name_like)s")
		params["employee_name_like"] = f"%{filters['employee_name']}%"

	if filters.get("department"):
		conditions.append("emp.department = %(department)s")
		params["department"] = filters["department"]

	if filters.get("custom_section"):
		conditions.append("emp.custom_section = %(custom_section)s")
		params["custom_section"] = filters["custom_section"]

	if filters.get("custom_group"):
		conditions.append("emp.custom_group = %(custom_group)s")
		params["custom_group"] = filters["custom_group"]

	return " AND ".join(conditions), params


def _calc_seniority(date_of_joining, today_date):
	if not date_of_joining:
		return 0
	from dateutil.relativedelta import relativedelta
	rd = relativedelta(today_date, getdate(date_of_joining))
	return rd.years * 12 + rd.months


def _calc_gestational_age(estimated_due_date, today_date):
	"""Gestational age in months: 9.5 - (complete months to due date + 1)"""
	from dateutil.relativedelta import relativedelta
	edd = getdate(estimated_due_date)
	if edd <= today_date:
		return 9.5
	rd = relativedelta(edd, today_date)
	months_diff = rd.years * 12 + rd.months
	return round(9.5 - (months_diff + 1), 1)


def _calc_status(from_date, to_date, today_date):
	if not from_date:
		return None
	from_d = getdate(from_date)
	if today_date < from_d:
		return "Upcoming"
	if to_date is None or from_d <= today_date <= getdate(to_date):
		return "Active"
	return "Completed"
