# Copyright (c) 2025, IT Team - TIQN
# License: MIT

"""
Leave Utilities

Helper functions for handling dual leave applications on single attendance.

Business Rules (TIQN):
- 1 Attendance can link to 2 Half Day Leave Applications
- Combined abbreviation displayed on timesheet (e.g., OP/2, COP/2)
- Working days calculated based on paid/unpaid leave types
"""

import frappe
from frappe import _
from frappe.utils import getdate


# =============================================================================
# LEAVE TYPE ABBREVIATION MAPPING
# =============================================================================
# Map Leave Type names to their abbreviations
# Update this mapping when new Leave Types are added

LEAVE_TYPE_ABBREVIATIONS = {
    # Paid Leaves
    "Annual Leave": "P",           # Phép năm
    "Sick Leave": "O",             # Ốm
    "Child Sick Leave": "CO",      # Con ốm
    "Compensatory Off": "BU",      # Bù

    # Unpaid Leaves
    "Leave Without Pay": "K",      # Không lương
    "Unpaid Leave": "K",           # Không lương (alias)

    # Other
    "Casual Leave": "NV",          # Nghỉ việc riêng
    "Maternity Leave": "TS",       # Thai sản
    "Paternity Leave": "TS",       # Thai sản (nam)
}

# Leave types that count as paid (for working_days calculation)
PAID_LEAVE_TYPES = [
    "Annual Leave",
    "Sick Leave",
    "Child Sick Leave",
    "Compensatory Off",
    "Casual Leave",
    "Maternity Leave",
    "Paternity Leave",
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_leave_type_abbreviation(leave_type):
    """
    Get abbreviation for a leave type.

    Priority:
    1. Custom field `custom_abbreviation` on Leave Type doctype
    2. Mapping in LEAVE_TYPE_ABBREVIATIONS
    3. First 2 characters of leave type name

    Args:
        leave_type: Leave Type name

    Returns:
        str: Abbreviation (e.g., "P", "O", "CO", "K")
    """
    if not leave_type:
        return ""

    # Try custom field first
    custom_abbr = frappe.db.get_value("Leave Type", leave_type, "custom_abbreviation")
    if custom_abbr:
        return custom_abbr

    # Try mapping
    if leave_type in LEAVE_TYPE_ABBREVIATIONS:
        return LEAVE_TYPE_ABBREVIATIONS[leave_type]

    # Fallback: first 2 characters
    return leave_type[:2].upper()


def is_paid_leave_type(leave_type):
    """
    Check if a leave type is paid (counts toward working days).

    Priority:
    1. Custom field `custom_is_paid_leave` on Leave Type doctype
    2. Mapping in PAID_LEAVE_TYPES
    3. Check `is_lwp` (Leave Without Pay) field - if True, it's unpaid

    Args:
        leave_type: Leave Type name

    Returns:
        bool: True if paid leave
    """
    if not leave_type:
        return False

    # Try custom field first
    custom_is_paid = frappe.db.get_value("Leave Type", leave_type, "custom_is_paid_leave")
    if custom_is_paid is not None:
        return bool(custom_is_paid)

    # Check is_lwp field
    is_lwp = frappe.db.get_value("Leave Type", leave_type, "is_lwp")
    if is_lwp:
        return False  # Leave Without Pay is unpaid

    # Check mapping
    return leave_type in PAID_LEAVE_TYPES


def get_combined_abbreviation(leave_type_1, leave_type_2=None):
    """
    Calculate combined abbreviation for attendance display.

    Examples:
        ("Sick Leave", None) → "O/2" (single half day)
        ("Sick Leave", "Annual Leave") → "OP/2"
        ("Child Sick Leave", "Annual Leave") → "COP/2"
        ("Sick Leave", "Leave Without Pay") → "OK/2"

    Args:
        leave_type_1: First leave type (morning/first half)
        leave_type_2: Second leave type (afternoon/second half), optional

    Returns:
        str: Combined abbreviation (e.g., "OP/2", "O/2")
    """
    if not leave_type_1:
        return ""

    abbr1 = get_leave_type_abbreviation(leave_type_1)

    if not leave_type_2:
        # Single half day leave
        return f"{abbr1}/2"

    abbr2 = get_leave_type_abbreviation(leave_type_2)
    return f"{abbr1}{abbr2}/2"


def get_working_days_for_leave(leave_type_1, leave_type_2=None, is_half_day=True):
    """
    Calculate working days (thời gian tính công) for payroll.

    Business Rules:
    - Full day leave: 0 working days (không tính công)
    - Half day (1 LA):
        - Paid leave: 0.5 working days
        - Unpaid leave: 0 working days
    - Half day + Half day (2 LA):
        - At least 1 paid: 0.5 working days
        - Both unpaid: 0 working days

    Args:
        leave_type_1: First leave type
        leave_type_2: Second leave type (optional)
        is_half_day: Whether this is half day attendance

    Returns:
        float: Working days (0, 0.5, or 1)
    """
    if not is_half_day:
        # Full day leave = no working days
        return 0

    is_lt1_paid = is_paid_leave_type(leave_type_1)
    is_lt2_paid = is_paid_leave_type(leave_type_2) if leave_type_2 else False

    if leave_type_2:
        # 2 Half Day leaves (full day absence)
        if is_lt1_paid or is_lt2_paid:
            return 0.5  # At least 1 paid leave
        return 0  # Both unpaid
    else:
        # 1 Half Day leave
        return 0.5 if is_lt1_paid else 0


def get_total_leave_days(leave_type_1, leave_type_2=None):
    """
    Calculate total leave days for attendance.

    Args:
        leave_type_1: First leave type
        leave_type_2: Second leave type (optional)

    Returns:
        float: Total leave days (0.5 or 1.0)
    """
    if not leave_type_1:
        return 0

    if leave_type_2:
        return 1.0  # Both halves are leave
    return 0.5  # Single half day


def find_other_half_day_leave(employee, leave_date, exclude_la=None):
    """
    Find another Half Day Leave Application for the same employee and date.

    Args:
        employee: Employee ID
        leave_date: Date to check
        exclude_la: Leave Application name to exclude from search

    Returns:
        dict or None: Leave Application details if found
    """
    filters = [
        ["employee", "=", employee],
        ["half_day", "=", 1],
        ["half_day_date", "=", getdate(leave_date)],
        ["docstatus", "=", 1],  # Only submitted
    ]

    if exclude_la:
        filters.append(["name", "!=", exclude_la])

    other_la = frappe.get_all(
        "Leave Application",
        filters=filters,
        fields=["name", "leave_type", "custom_abbreviation"],
        limit=1
    )

    return other_la[0] if other_la else None


def find_attendance_for_leave(employee, attendance_date):
    """
    Find existing attendance for employee on a specific date.

    Args:
        employee: Employee ID
        attendance_date: Date to check

    Returns:
        dict or None: Attendance details if found
    """
    attendance = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": getdate(attendance_date),
            "docstatus": ["!=", 2],  # Not cancelled
        },
        fields=[
            "name", "status", "leave_type", "leave_application",
            "custom_leave_type_2", "custom_leave_application_2",
            "custom_leave_application_abbreviation", "working_hours"
        ],
        limit=1
    )

    return attendance[0] if attendance else None


def update_attendance_with_dual_leave(attendance_name, leave_type_1, leave_application_1,
                                       leave_type_2=None, leave_application_2=None):
    """
    Update attendance record with dual leave information.

    Args:
        attendance_name: Attendance document name
        leave_type_1: First leave type
        leave_application_1: First leave application name
        leave_type_2: Second leave type (optional)
        leave_application_2: Second leave application name (optional)
    """
    # Calculate combined values
    combined_abbr = get_combined_abbreviation(leave_type_1, leave_type_2)

    # Determine status
    if leave_type_2:
        status = "On Leave"  # Both halves are leave
    else:
        status = "Half Day"  # Only one half is leave

    # Update attendance
    update_dict = {
        "status": status,
        "leave_type": leave_type_1,
        "leave_application": leave_application_1,
        "custom_leave_type_2": leave_type_2,
        "custom_leave_application_2": leave_application_2,
        "custom_leave_application_abbreviation": combined_abbr,
    }

    # Set half_day_status for Half Day attendance
    if status == "Half Day":
        update_dict["half_day_status"] = "Present"  # Other half was worked
        update_dict["modify_half_day_status"] = 0
    else:
        update_dict["half_day_status"] = None
        update_dict["modify_half_day_status"] = 0

    frappe.db.set_value("Attendance", attendance_name, update_dict)

    return combined_abbr


# =============================================================================
# ATTENDANCE CREATION/UPDATE FOR LEAVE
# =============================================================================

def create_attendance_for_leave(leave_application_doc, date):
    """
    Create or update attendance for a leave application.

    Handles the case where:
    1. No attendance exists → Create new
    2. Attendance exists with work (Present) → Update to Half Day/On Leave
    3. Attendance exists with another LA → Add as 2nd leave

    Args:
        leave_application_doc: Leave Application document
        date: Attendance date

    Returns:
        str: Attendance name
    """
    employee = leave_application_doc.employee
    leave_type = leave_application_doc.leave_type
    la_name = leave_application_doc.name
    is_half_day = (
        leave_application_doc.half_day and
        leave_application_doc.half_day_date and
        getdate(leave_application_doc.half_day_date) == getdate(date)
    )

    # Find existing attendance
    existing_att = find_attendance_for_leave(employee, date)

    if existing_att:
        att_name = existing_att.name

        # Check if attendance already has a leave application
        if existing_att.leave_application and existing_att.leave_application != la_name:
            # This is the 2nd leave application for this date
            if is_half_day:
                # Update with 2nd leave
                combined_abbr = update_attendance_with_dual_leave(
                    att_name,
                    existing_att.leave_type,  # LA1
                    existing_att.leave_application,
                    leave_type,  # LA2
                    la_name
                )

                frappe.msgprint(
                    _("Attendance {0} updated with 2nd leave: {1}").format(
                        att_name, combined_abbr
                    ),
                    indicator="green",
                    alert=True
                )
            else:
                # Full day leave - this shouldn't happen if there's already a leave
                frappe.throw(
                    _("Attendance {0} already has leave application {1}").format(
                        att_name, existing_att.leave_application
                    )
                )
        else:
            # Update existing attendance with this leave (1st leave or update)
            status = "Half Day" if is_half_day else "On Leave"
            abbr = get_leave_type_abbreviation(leave_type)
            combined_abbr = f"{abbr}/2" if is_half_day else abbr

            update_dict = {
                "status": status,
                "leave_type": leave_type,
                "leave_application": la_name,
                "custom_leave_application_abbreviation": combined_abbr,
            }

            if status == "Half Day":
                # Check if there's checkin data
                if existing_att.working_hours and existing_att.working_hours > 0:
                    update_dict["half_day_status"] = "Present"
                    update_dict["modify_half_day_status"] = 0
                else:
                    update_dict["half_day_status"] = "Present"
                    update_dict["modify_half_day_status"] = 1

            frappe.db.set_value("Attendance", att_name, update_dict)

            frappe.msgprint(
                _("Attendance {0} updated to {1} ({2})").format(
                    att_name, status, combined_abbr
                ),
                indicator="green",
                alert=True
            )

        return att_name
    else:
        # Create new attendance
        status = "Half Day" if is_half_day else "On Leave"
        abbr = get_leave_type_abbreviation(leave_type)
        combined_abbr = f"{abbr}/2" if is_half_day else abbr

        doc = frappe.new_doc("Attendance")
        doc.employee = employee
        doc.employee_name = leave_application_doc.employee_name
        doc.attendance_date = date
        doc.company = leave_application_doc.company
        doc.leave_type = leave_type
        doc.leave_application = la_name
        doc.status = status
        doc.custom_leave_application_abbreviation = combined_abbr

        if status == "Half Day":
            doc.half_day_status = "Present"
            doc.modify_half_day_status = 1  # Will be updated by auto_attendance

        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True)
        doc.submit()

        return doc.name


def remove_leave_from_attendance(leave_application_doc, date):
    """
    Remove leave application link from attendance when LA is cancelled.

    If attendance has 2 leaves, remove the cancelled one and update abbreviation.
    If attendance has 1 leave, either delete or reset attendance.

    Args:
        leave_application_doc: Leave Application document being cancelled
        date: Attendance date
    """
    employee = leave_application_doc.employee
    la_name = leave_application_doc.name

    existing_att = find_attendance_for_leave(employee, date)

    if not existing_att:
        return

    att_name = existing_att.name

    # Check if this LA is LA1 or LA2
    is_la1 = existing_att.leave_application == la_name
    is_la2 = existing_att.custom_leave_application_2 == la_name

    if is_la1 and existing_att.custom_leave_application_2:
        # LA1 is being cancelled, but LA2 exists → swap LA2 to LA1
        new_lt1 = existing_att.custom_leave_type_2
        new_la1 = existing_att.custom_leave_application_2
        new_abbr = get_combined_abbreviation(new_lt1, None)

        frappe.db.set_value("Attendance", att_name, {
            "leave_type": new_lt1,
            "leave_application": new_la1,
            "custom_leave_type_2": None,
            "custom_leave_application_2": None,
            "custom_leave_application_abbreviation": new_abbr,
            "status": "Half Day",
            "half_day_status": "Present",
        })

    elif is_la2:
        # LA2 is being cancelled → remove LA2, keep LA1
        new_abbr = get_combined_abbreviation(existing_att.leave_type, None)

        frappe.db.set_value("Attendance", att_name, {
            "custom_leave_type_2": None,
            "custom_leave_application_2": None,
            "custom_leave_application_abbreviation": new_abbr,
            "status": "Half Day",
            "half_day_status": "Present",
        })

    elif is_la1:
        # Only LA1, no LA2 → cancel attendance
        att_doc = frappe.get_doc("Attendance", att_name)
        if att_doc.docstatus == 1:
            att_doc.cancel()


print("✅ Leave Utils loaded")
