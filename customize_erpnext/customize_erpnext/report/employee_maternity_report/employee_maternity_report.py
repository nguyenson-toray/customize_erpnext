# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _


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
			"width": 120
		},
		{
			"fieldname": "employee_name",
			"label": _("Employee Name"),
			"fieldtype": "Data",
			"width": 180
		},
		{
			"fieldname": "department",
			"label": _("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": 120
		},
		{
			"fieldname": "custom_section",
			"label": _("Section"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "custom_group",
			"label": _("Group"),
			"fieldtype": "Data",
			"width": 100
		}
	]

	if show_detail:
		columns.append({
			"fieldname": "number_of_pregnancies",
			"label": _("Number of Pregnancies"),
			"fieldtype": "Int",
			"width": 140
		})

	columns.extend([
		{
			"fieldname": "date_of_joining",
			"label": _("Date of Joining"),
			"fieldtype": "Date",
			"width": 110
		},
		{
			"fieldname": "seniority",
			"label": _("Seniority (Months)"),
			"fieldtype": "Int",
			"width": 120
		},
		{
			"fieldname": "type",
			"label": _("Maternity Type"),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "from_date",
			"label": _("From Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "to_date",
			"label": _("To Date"),
			"fieldtype": "Date",
			"width": 100
		}
	])

	if show_detail:
		columns.append({
			"fieldname": "duration_days",
			"label": _("Duration (Days)"),
			"fieldtype": "Int",
			"width": 120
		})

	columns.extend([
		{
			"fieldname": "estimated_due_date",
			"label": _("Estimated Due Date"),
			"fieldtype": "Date",
			"width": 120
		},
		{
			"fieldname": "date_of_birth",
			"label": _("Date of Birth"),
			"fieldtype": "Date",
			"width": 120
		},
		{
			"fieldname": "gestational_age",
			"label": _("Gestational Age"),
			"fieldtype": "Float",
			"precision": 1,
			"width": 120
		},
		{
			"fieldname": "note",
			"label": _("Note"),
			"fieldtype": "Data",
			"width": 200
		}
	])

	if show_detail:
		columns.append({
			"fieldname": "relieving_date",
			"label": _("Relieving Date"),
			"fieldtype": "Date",
			"width": 120
		})

	columns.append({
		"fieldname": "status",
		"label": _("Status"),
		"fieldtype": "Data",
		"width": 100
	})

	return columns


def get_data(filters):
	"""Get report data"""
	conditions = get_conditions(filters)

	data = frappe.db.sql(f"""
		SELECT
			emp.name as employee,
			emp.employee_name,
			emp.department,
			emp.custom_section,
			emp.custom_group,
			emp.date_of_joining,
			emp.relieving_date,
			TIMESTAMPDIFF(MONTH, emp.date_of_joining, CURDATE()) as seniority,
			mt.type,
			mt.from_date,
			mt.to_date,
			DATEDIFF(COALESCE(mt.to_date, CURDATE()), mt.from_date) + 1 as duration_days,
			mt.estimated_due_date,
			mt.date_of_birth,
			mt.note,
			(SELECT COUNT(*) FROM `tabEmployee Maternity` mt2
			 WHERE mt2.employee = emp.name AND mt2.type = 'Pregnant') as number_of_pregnancies,
			CASE
				WHEN mt.type = 'Pregnant' AND mt.estimated_due_date IS NOT NULL
				THEN ROUND(9.5 - (TIMESTAMPDIFF(MONTH, CURDATE(), mt.estimated_due_date) + 1), 1)
				ELSE NULL
			END as gestational_age,
			CASE
				WHEN CURDATE() < mt.from_date THEN 'Upcoming'
				WHEN mt.to_date IS NULL OR CURDATE() BETWEEN mt.from_date AND mt.to_date THEN 'Active'
				ELSE 'Completed'
			END as status
		FROM `tabEmployee` emp
		INNER JOIN `tabEmployee Maternity` mt ON emp.name = mt.employee
		WHERE {conditions}
		ORDER BY emp.department, emp.custom_section, emp.custom_group, emp.employee_name, mt.from_date DESC
	""", filters, as_dict=1)

	return data


def get_conditions(filters):
	"""Build WHERE conditions based on filters"""
	conditions = ["1=1"]

	if filters.get("employee"):
		conditions.append("emp.name = %(employee)s")

	if filters.get("employee_name"):
		conditions.append("emp.employee_name LIKE %(employee_name_like)s")
		filters["employee_name_like"] = f"%{filters.get('employee_name')}%"

	if filters.get("department"):
		conditions.append("emp.department = %(department)s")

	if filters.get("custom_section"):
		conditions.append("emp.custom_section = %(custom_section)s")

	if filters.get("custom_group"):
		conditions.append("emp.custom_group = %(custom_group)s")

	if filters.get("maternity_type"):
		conditions.append("mt.type = %(maternity_type)s")

	if filters.get("from_date"):
		conditions.append("mt.from_date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("mt.to_date <= %(to_date)s")

	if filters.get("status"):
		status_condition = ""
		if filters.get("status") == "Upcoming":
			status_condition = "CURDATE() < mt.from_date"
		elif filters.get("status") == "Active":
			status_condition = "CURDATE() BETWEEN mt.from_date AND mt.to_date"
		elif filters.get("status") == "Completed":
			status_condition = "CURDATE() > mt.to_date"

		if status_condition:
			conditions.append(f"({status_condition})")

	return " AND ".join(conditions)
