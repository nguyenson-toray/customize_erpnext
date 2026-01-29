# -*- coding: utf-8 -*-
# Copyright (c) 2024, IT Team - TIQN and contributors
# For license information, please see license.txt

"""
Employee Validation
Prevent changes to name and attendance_device_id if employee has checkin records
"""

from __future__ import unicode_literals
import frappe
from frappe import _
from customize_erpnext.api.employee.employee_utils import allow_change_name_attendance_device_id


def validate_employee_changes(doc, method=None):
    """
    Validate Employee document before save
    Prevent changes to name and attendance_device_id if employee has checkin records

    Args:
        doc: Employee document
        method: Hook method name (validate, before_save, etc.)
    """
    # Skip validation for new documents
    if doc.is_new():
        return

    # Get the original document from database
    if not doc.name:
        return

    # Check if employee can be modified
    can_change = allow_change_name_attendance_device_id(doc.name)

    if not can_change:
        # Get old values from database
        old_doc = frappe.db.get_value(
            'Employee',
            doc.name,
            ['name', 'attendance_device_id'],
            as_dict=True
        )
\
        if not old_doc:
            return

        # Check if name is being changed
        if doc.name != old_doc.get('name'):
            frappe.throw(
                _("Cannot change Employee ID for {0} because this employee has existing attendance records (Employee Checkin). Please contact HR administrator if you need to make this change.").format(doc.name),
                title=_("Employee ID Change Not Allowed")
            )

        # Check if attendance_device_id is being changed
        old_attendance_id = str(old_doc.get('attendance_device_id') or '')
        new_attendance_id = str(doc.get('attendance_device_id') or '')

        if old_attendance_id != new_attendance_id:
            frappe.throw(
                _("Cannot change Attendance Device ID for {0} because this employee has existing attendance records (Employee Checkin). Current value: {1}. Please contact HR administrator if you need to make this change.").format(
                    doc.name,
                    old_attendance_id
                ),
                title=_("Attendance Device ID Change Not Allowed")
            )


def prevent_employee_deletion(doc, method=None):
    """
    Prevent deletion of Employee if employee has checkin records

    Args:
        doc: Employee document
        method: Hook method name (before_delete, on_trash, etc.)
    """
    # Check if employee has checkin records
    can_delete = allow_change_name_attendance_device_id(doc.name)

    if not can_delete:
        frappe.throw(
            _("Cannot delete Employee {0} because this employee has existing attendance records (Employee Checkin).").format(doc.name),
            title=_("Employee Deletion Not Allowed")
        )
