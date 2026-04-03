# -*- coding: utf-8 -*-
# Copyright (c) 2024, IT Team - TIQN and contributors
# For license information, please see license.txt

"""
Employee Validation
- Auto-fill employee code and attendance_device_id on insert if not provided
- Block changes to employee/attendance_device_id if Attendance records exist
- Duplicate enforcement is handled by the unique constraint on the doctype fields
"""

from __future__ import unicode_literals
import re
import frappe
from frappe import _
from customize_erpnext.api.employee.employee_utils import (
    allow_change_name_attendance_device_id,
    get_next_employee_code,
    get_next_attendance_device_id,
    set_series,
)


def _split_employee_name_parts(employee_name):
    """Tách họ tên đầy đủ → (first_name, middle_name, last_name)
    VD: "Nguyễn Văn An" → ("Nguyễn", "Văn", "An")
    """
    parts = (employee_name or '').strip().split()
    if not parts:
        return ('', '', '')
    if len(parts) == 1:
        return (parts[0], '', '')
    return (parts[0], ' '.join(parts[1:-1]), parts[-1])


def before_insert_employee(doc, method=None):
    """
    - Split employee_name → first/middle/last_name (critical for Data Import mandatory check)
    - Auto-fill employee code and attendance_device_id if not provided
    - Sync naming series so Frappe's set_new_name() (which runs AFTER before_insert with
      autoname='naming_series:') generates the exact same code we intend.
      set_series() stores (intended - 1) because Frappe does current + 1 on use.
    """
    if doc.employee_name:
        first, mid, last = _split_employee_name_parts(doc.employee_name)
        doc.first_name = first
        doc.middle_name = mid
        doc.last_name = last

    if not doc.employee:
        doc.employee = get_next_employee_code()

    # Sync series for any TIQN- code (auto-filled or pre-filled from Excel)
    m = re.match(r'TIQN-(\d+)', doc.employee or '')
    if m:
        set_series('TIQN-', int(m.group(1)))

    if not doc.attendance_device_id:
        doc.attendance_device_id = str(get_next_attendance_device_id())


def validate_employee_changes(doc, method=None):
    """
    - Sync first/middle/last_name from employee_name (always, including import)
    - Block changes to employee ID / attendance_device_id if Attendance records exist
    """
    if doc.employee_name:
        first, mid, last = _split_employee_name_parts(doc.employee_name)
        doc.first_name = first
        doc.middle_name = mid
        doc.last_name = last

    if doc.is_new() or not doc.name:
        return

    if allow_change_name_attendance_device_id(doc.name):
        return

    old_doc = frappe.db.get_value(
        'Employee', doc.name, ['name', 'attendance_device_id'], as_dict=True
    )
    if not old_doc:
        return

    if doc.name != old_doc.get('name'):
        frappe.throw(
            _("Cannot change Employee ID for {0} because this employee has existing Attendance records. Please contact HR administrator.").format(doc.name),
            title=_("Employee ID Change Not Allowed")
        )

    if str(old_doc.get('attendance_device_id') or '') != str(doc.get('attendance_device_id') or ''):
        frappe.throw(
            _("Cannot change Attendance Device ID for {0} because this employee has existing Attendance records. Current value: {1}. Please contact HR administrator.").format(
                doc.name, old_doc.get('attendance_device_id') or ''
            ),
            title=_("Attendance Device ID Change Not Allowed")
        )


def prevent_employee_deletion(doc, method=None):
    """Prevent deletion if Attendance records exist."""
    if not allow_change_name_attendance_device_id(doc.name):
        frappe.throw(
            _("Cannot delete Employee {0} because this employee has existing Attendance records.").format(doc.name),
            title=_("Employee Deletion Not Allowed")
        )
