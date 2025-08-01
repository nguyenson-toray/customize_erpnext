# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ShiftRegistration(Document):
	pass


def validate_duplicate_employees(doc, method):
    """Kiểm tra trùng lặp nhân viên trong danh sách"""
    if not doc.employees_list:
        return
        
    employees_seen = []
    
    for row in doc.employees_list:
        if row.employee:
            if row.employee in employees_seen:
                frappe.throw(
                    f"Nhân viên {row.employee} đã được chọn nhiều lần trong danh sách. "
                    "Vui lòng chỉ chọn mỗi nhân viên một lần.",
                    title="Lỗi Validation"
                )
            employees_seen.append(row.employee)