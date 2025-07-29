# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, get_first_day, get_last_day, add_days, nowdate


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	summary = get_summary(data)
	return columns, data, summary


def get_columns():
	return [
		{
			"fieldname": "request_date",
			"label": _("Request Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "group",
			"label": _("Group"),
			"fieldtype": "Link",
			"options": "Group",
			"width": 120
		},
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 150
		},
		{
			"fieldname": "employee_name",
			"label": _("Employee Name"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "begin_time",
			"label": _("Begin Time"),
			"fieldtype": "Time",
			"width": 80
		},
		{
			"fieldname": "end_time",
			"label": _("End Time"),
			"fieldtype": "Time",
			"width": 80
		},
		{
			"fieldname": "reason",
			"label": _("Reason"),
			"fieldtype": "Data",
			"width": 400
		}
	]


def get_data(filters):
	conditions = get_conditions(filters)
	
	query = """
		SELECT 
			parent.request_date,
			parent.status,
			child.group,
			child.employee,
			child.employee_name,
			child.date,
			child.begin_time,
			child.end_time,
			child.reason
		FROM `tabOvertime Registration` as parent
		INNER JOIN `tabOvertime Registration Detail` as child 
			ON parent.name = child.parent
		WHERE parent.docstatus != 2 {conditions}
		ORDER BY parent.request_date DESC, child.date DESC
	""".format(conditions=conditions)
	
	data = frappe.db.sql(query, filters, as_dict=1)
	
	return data


def get_conditions(filters):
	conditions = []
	
	if filters.get("request_date"):
		conditions.append("parent.request_date = %(request_date)s")
	
	if filters.get("status"):
		conditions.append("parent.status = %(status)s")
	
	if filters.get("from_date") and filters.get("to_date"):
		conditions.append("child.date BETWEEN %(from_date)s AND %(to_date)s")
	
	if filters.get("group"):
		conditions.append("child.group = %(group)s")
	
	if filters.get("employee"):
		conditions.append("child.employee = %(employee)s")
	
	if filters.get("employee_name"):
		conditions.append("child.employee_name LIKE %(employee_name)s")
	
	return " AND " + " AND ".join(conditions) if conditions else ""


def get_summary(data):
	if not data:
		return []
	
	return [
		{
			"value": len(data),
			"label": _("Total Records"),
			"indicator": "Blue"
		}
	]
