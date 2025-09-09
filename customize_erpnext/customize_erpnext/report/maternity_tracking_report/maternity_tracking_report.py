# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, formatdate


def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data


def get_columns(filters=None):
	"""Define report columns"""
	show_detail = filters and filters.get("detail")
	
	# Base columns - always shown
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
	
	# Detail columns - only shown if detail=true
	if show_detail:
		columns.extend([
			{
				"fieldname": "number_of_pregnancies",
				"label": _("Number of Pregnancies"),
				"fieldtype": "Int",
				"width": 140
			}
		])
	
	# Continue with main columns
	columns.extend([
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
	
	# Detail-only columns
	if show_detail:
		columns.append({
			"fieldname": "duration_days",
			"label": _("Duration (Days)"),
			"fieldtype": "Int",
			"width": 120
		})
	
	# Main columns continue
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
			"fieldname": "pregnancy_months",
			"label": _("Pregnancy Months"),
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
	
	# Detail-only columns at end
	if show_detail:
		columns.extend([
			{
				"fieldname": "date_of_joining",
				"label": _("Date of Joining"),
				"fieldtype": "Date",
				"width": 120
			},
			{
				"fieldname": "relieving_date",
				"label": _("Relieving Date"),
				"fieldtype": "Date",
				"width": 120
			}
		])
	
	# Status always shown
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
			mt.type,
			mt.from_date,
			mt.to_date,
			DATEDIFF(COALESCE(mt.to_date, CURDATE()), mt.from_date) + 1 as duration_days,
			mt.estimated_due_date,
			mt.date_of_birth,
			mt.note,
			(SELECT COUNT(*) FROM `tabMaternity Tracking` mt2 
			 WHERE mt2.parent = emp.name AND mt2.type = 'Pregnant') as number_of_pregnancies,
			CASE 
				WHEN mt.type = 'Pregnant' AND mt.estimated_due_date IS NOT NULL 
				     AND (mt.to_date IS NULL OR CURDATE() BETWEEN mt.from_date AND mt.to_date)
				THEN 9.5 - (TIMESTAMPDIFF(MONTH, CURDATE(), mt.estimated_due_date) + 1)
				ELSE NULL
			END as pregnancy_months,
			CASE 
				WHEN CURDATE() < mt.from_date THEN 'Upcoming'
				WHEN mt.to_date IS NULL OR CURDATE() BETWEEN mt.from_date AND mt.to_date THEN 'Active'
				ELSE 'Completed'
			END as status
		FROM `tabEmployee` emp
		INNER JOIN `tabMaternity Tracking` mt ON emp.name = mt.parent
		WHERE {conditions}
		ORDER BY emp.department, emp.custom_section, emp.custom_group, emp.employee_name, mt.from_date DESC
	""", filters, as_dict=1)
	
	return data


def get_conditions(filters):
	"""Build WHERE conditions based on filters"""
	conditions = ["1=1"]  # Remove emp.status = 'Active' to include all employees with maternity tracking
	
	# Employee filter
	if filters.get("employee"):
		conditions.append("emp.name = %(employee)s")
	
	# Employee name filter (using LIKE for partial matching)
	if filters.get("employee_name"):
		conditions.append("emp.employee_name LIKE %(employee_name_like)s")
		filters["employee_name_like"] = f"%{filters.get('employee_name')}%"
	
	# Department filter
	if filters.get("department"):
		conditions.append("emp.department = %(department)s")
	
	# Section filter
	if filters.get("custom_section"):
		conditions.append("emp.custom_section = %(custom_section)s")
	
	# Group filter
	if filters.get("custom_group"):
		conditions.append("emp.custom_group = %(custom_group)s")
	
	# Maternity type filter
	if filters.get("maternity_type"):
		conditions.append("mt.type = %(maternity_type)s")
	
	# Date range filters
	if filters.get("from_date"):
		conditions.append("mt.from_date >= %(from_date)s")
	
	if filters.get("to_date"):
		conditions.append("mt.to_date <= %(to_date)s")
	
	# Status filter
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


def get_chart_data(data, filters):
	"""Generate chart data for the report"""
	if not data:
		return None
	
	# Group by maternity type
	type_count = {}
	status_count = {}
	
	for row in data:
		# Count by type
		mat_type = row.get("type") or "Unknown"
		type_count[mat_type] = type_count.get(mat_type, 0) + 1
		
		# Count by status
		status = row.get("status") or "Unknown"
		status_count[status] = status_count.get(status, 0) + 1
	
	return {
		"data": {
			"labels": list(type_count.keys()),
			"datasets": [
				{
					"name": "Count",
					"values": list(type_count.values())
				}
			]
		},
		"type": "donut",
		"height": 300,
		"colors": ["#ff6384", "#36a2eb", "#ffce56", "#4bc0c0"]
	}