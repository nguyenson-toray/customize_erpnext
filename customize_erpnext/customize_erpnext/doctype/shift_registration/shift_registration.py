# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ShiftRegistration(Document):
	pass


def validate_duplicate_employees(doc, method):
    """Check for duplicate employees in the list"""
    if not doc.employees_list:
        return
        
    employees_seen = []
    
    for row in doc.employees_list:
        if row.employee:
            if row.employee in employees_seen:
                frappe.throw(
                    _("Employee {0} has been selected multiple times in the list. Please select each employee only once.").format(row.employee),
                    title=_("Validation Error")
                )
            employees_seen.append(row.employee)