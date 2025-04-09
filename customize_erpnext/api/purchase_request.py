import frappe
from frappe import _

 
@frappe.whitelist()
def get_email_from_emp_id(emp_id): 
    if not emp_id:
        return ""
    return frappe.db.get_value("Employee", emp_id, "user_id")
@frappe.whitelist()
def get_employee_name_from_emp_id(emp_id): 
    if not emp_id:
        return ""
    return frappe.db.get_value("Employee", emp_id, "employee_name")

@frappe.whitelist()
def get_report_to_from_emp_id(emp_id): 
    if not emp_id:
        return ""
    return frappe.db.get_value("Employee", emp_id, "report_to")