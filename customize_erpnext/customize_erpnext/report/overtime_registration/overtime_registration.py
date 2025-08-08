# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import formatdate, format_time, time_diff_in_hours

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {
            "fieldname": "overtime_registration",
            "label": _("Overtime Registration"),
            "fieldtype": "Link",
            "options": "Overtime Registration",
            "width": 180
        },
        {
            "fieldname": "date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 100
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
            "fieldname": "begin_time",
            "label": _("Begin Time"),
            "fieldtype": "Time",
            "width": 100
        },
        {
            "fieldname": "end_time",
            "label": _("End Time"),
            "fieldtype": "Time",
            "width": 100
        },
        {
            "fieldname": "hours",
            "label": _("Hours"),
            "fieldtype": "Float",
            "width": 80,
            "precision": 2
        },
        {
            "fieldname": "reason",
            "label": _("Reason"),
            "fieldtype": "Data",
            "width": 300
        },
        {
            "fieldname": "status",
            "label": _("Status"),
            "fieldtype": "Data",
            "width": 100
        }
    ]

def get_data(filters=None):
    if not filters:
        filters = {}
    
    conditions = []
    values = {}
    
    if filters.get("from_date"):
        conditions.append("detail.date >= %(from_date)s")
        values["from_date"] = filters.get("from_date")
    
    if filters.get("to_date"):
        conditions.append("detail.date <= %(to_date)s")
        values["to_date"] = filters.get("to_date")
    
    if filters.get("employee"):
        conditions.append("detail.employee = %(employee)s")
        values["employee"] = filters.get("employee")
    
    if filters.get("group"):
        conditions.append("emp.group = %(group)s")
        values["group"] = filters.get("group")
    
    if filters.get("status"):
        if filters.get("status") == "Draft":
            conditions.append("parent.docstatus = 0")
        elif filters.get("status") == "Submitted":
            conditions.append("parent.docstatus = 1")
        elif filters.get("status") == "Cancelled":
            conditions.append("parent.docstatus = 2")
    
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    
    query = f"""
        SELECT 
            parent.name as overtime_registration,
            detail.date,
            detail.employee,
            detail.employee_name,
            detail.begin_time,
            detail.end_time,
            detail.reason,
            CASE 
                WHEN parent.docstatus = 0 THEN 'Draft'
                WHEN parent.docstatus = 1 THEN 'Submitted'
                WHEN parent.docstatus = 2 THEN 'Cancelled'
            END as status
        FROM `tabOvertime Registration` parent
        JOIN `tabOvertime Registration Detail` detail ON parent.name = detail.parent
        LEFT JOIN `tabEmployee` emp ON detail.employee = emp.name
        {where_clause}
        ORDER BY detail.date DESC, detail.begin_time ASC
    """
    
    data = frappe.db.sql(query, values, as_dict=1)
    
    for row in data:
        if row.begin_time and row.end_time:
            row.hours = time_diff_in_hours(row.end_time, row.begin_time)
        else:
            row.hours = 0.0
    
    return data