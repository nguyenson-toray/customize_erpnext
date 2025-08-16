# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import formatdate, time_diff_in_hours

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {
            "fieldname": "group",
            "label": _("Group"),
            "fieldtype": "Data",
            "width": 120
        },
        {
            "fieldname": "total_employees_submitted",
            "label": _("Total Employee (Submitted)"),
            "fieldtype": "Int",
            "width": 200
        },
        {
            "fieldname": "total_hours_submitted",
            "label": _("Total Hours (Submitted)"),
            "fieldtype": "Float",
            "width": 200,
            "precision": 1
        },
        {
            "fieldname": "total_employees_draft",
            "label": _("Total Employee (Draft)"),
            "fieldtype": "Int",
            "width": 200
        },
        {
            "fieldname": "total_hours_draft",
            "label": _("Total Hours (Draft)"),
            "fieldtype": "Float",
            "width": 200,
            "precision": 1
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
    
    if filters.get("group"):
        conditions.append("detail.group = %(group)s")
        values["group"] = filters.get("group")
    
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    
    query = f"""
        SELECT 
            COALESCE(detail.group, 'No Group') as `group`,
            COUNT(DISTINCT CASE WHEN parent.docstatus = 1 THEN detail.employee END) as total_employees_submitted,
            SUM(
                CASE 
                    WHEN parent.docstatus = 1 AND detail.begin_time IS NOT NULL AND detail.end_time IS NOT NULL 
                    THEN TIME_TO_SEC(TIMEDIFF(detail.end_time, detail.begin_time)) / 3600.0
                    ELSE 0 
                END
            ) as total_hours_submitted,
            COUNT(DISTINCT CASE WHEN parent.docstatus = 0 THEN detail.employee END) as total_employees_draft,
            SUM(
                CASE 
                    WHEN parent.docstatus = 0 AND detail.begin_time IS NOT NULL AND detail.end_time IS NOT NULL 
                    THEN TIME_TO_SEC(TIMEDIFF(detail.end_time, detail.begin_time)) / 3600.0
                    ELSE 0 
                END
            ) as total_hours_draft
            
        FROM `tabOvertime Registration` parent
        JOIN `tabOvertime Registration Detail` detail ON parent.name = detail.parent
        {where_clause}
        GROUP BY COALESCE(detail.group, 'No Group')
        ORDER BY COALESCE(detail.group, 'No Group')
    """
    
    data = frappe.db.sql(query, values, as_dict=1)
    
    # Ensure numeric fields are properly formatted
    for row in data:
        row.group = row.get('group') or 'No Group'
        row.total_employees_submitted = row.total_employees_submitted or 0
        row.total_hours_submitted = row.total_hours_submitted or 0.0
        row.total_employees_draft = row.total_employees_draft or 0
        row.total_hours_draft = row.total_hours_draft or 0.0
    
    return data
