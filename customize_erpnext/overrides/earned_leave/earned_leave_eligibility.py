# Copyright (c) 2025, IT Team - TIQN
# License: MIT

"""
Earned Leave Eligibility Check

Functions to determine if an employee is eligible for earned leave allocation.

Business Rules:
- Employee must complete probation period before receiving earned leaves
- Eligibility is checked on allocation date (15th of each month)
- Priority: (1) custom_number_of_probation_days, (2) applicable_after
"""

import frappe
from frappe.utils import add_days, cint, getdate

# Note: No default probation days - use applicable_after as fallback


def get_employee_probation_days(employee):
    """
    Get probation days for employee.

    Logic:
    - If Employee.custom_number_of_probation_days has a value (not null, not 0) → use it
    - If null/not set → return None (caller should use applicable_after)

    Args:
        employee: Employee ID or Employee document

    Returns:
        int or None: Number of probation days, or None if not set
    """
    if isinstance(employee, str):
        probation_days = frappe.db.get_value(
            "Employee", employee, "custom_number_of_probation_days"
        )
    else:
        probation_days = employee.get("custom_number_of_probation_days")

    # Return the value only if it's set and > 0, otherwise None
    probation_value = cint(probation_days)
    return probation_value if probation_value > 0 else None


def get_leave_type_applicable_after(leave_type):
    """
    Get applicable_after days from Leave Type.

    Args:
        leave_type: Leave Type name

    Returns:
        int: Number of days after DOJ before leave is applicable
    """
    return cint(frappe.db.get_value("Leave Type", leave_type, "applicable_after") or 0)


def calculate_eligibility_date(date_of_joining, probation_days, applicable_after):
    """
    Calculate the eligibility date for earned leave allocation.

    Logic:
    - If probation_days is set (not None, > 0): eligibility_date = DOJ + probation_days
    - Else if applicable_after > 0: eligibility_date = DOJ + applicable_after
    - Else: eligibility_date = DOJ (no restriction)

    Priority:
    1. Employee.custom_number_of_probation_days (if has value)
    2. Leave Type.applicable_after (fallback)

    Args:
        date_of_joining: Employee's date of joining
        probation_days: Custom probation days from Employee (None if not set)
        applicable_after: Applicable after days from Leave Type

    Returns:
        tuple: (eligibility_date, reason_description)
    """
    doj = getdate(date_of_joining)

    # Priority 1: Use probation_days from Employee if set
    if probation_days is not None and probation_days > 0:
        eligibility_date = add_days(doj, probation_days)
        reason = f"probation period ({probation_days} days from DOJ)"
    # Priority 2: Use applicable_after from Leave Type
    elif applicable_after > 0:
        eligibility_date = add_days(doj, applicable_after)
        reason = f"applicable_after ({applicable_after} working days from Leave Type)"
    else:
        # No restriction
        eligibility_date = doj
        reason = "no restriction"

    return eligibility_date, reason


def is_employee_eligible_for_earned_leave(employee, allocation_date, leave_type):
    """
    Check if employee is eligible for earned leave on the given allocation date.

    Business Rules:
    1. Get date_of_joining from Employee
    2. Get custom_number_of_probation_days from Employee (if set)
    3. Get applicable_after from Leave Type
    4. Calculate eligibility_date:
       - Priority (1): DOJ + custom_number_of_probation_days (if has value)
       - Fallback (2): DOJ + applicable_after (from Leave Type)
    5. Employee is eligible if allocation_date >= eligibility_date

    Args:
        employee: Employee ID
        allocation_date: Date of allocation (15th of month)
        leave_type: Leave Type name

    Returns:
        dict: {
            "is_eligible": bool,
            "eligibility_date": date,
            "reason": str,
            "date_of_joining": date,
            "probation_days": int or None,
            "applicable_after": int
        }
    """
    # Get employee info
    emp_info = frappe.db.get_value(
        "Employee",
        employee,
        ["date_of_joining", "custom_number_of_probation_days", "employee_name"],
        as_dict=True
    )

    if not emp_info or not emp_info.date_of_joining:
        return {
            "is_eligible": False,
            "eligibility_date": None,
            "reason": "No date of joining found",
            "date_of_joining": None,
            "probation_days": None,
            "applicable_after": 0
        }

    doj = getdate(emp_info.date_of_joining)

    # Get probation days from Employee (None if not set)
    probation_value = cint(emp_info.custom_number_of_probation_days)
    probation_days = probation_value if probation_value > 0 else None

    # Get applicable_after from Leave Type (fallback)
    applicable_after = get_leave_type_applicable_after(leave_type)

    # Calculate eligibility date
    eligibility_date, reason = calculate_eligibility_date(
        doj, probation_days, applicable_after
    )

    # Check eligibility
    allocation_date = getdate(allocation_date)
    is_eligible = allocation_date >= eligibility_date

    return {
        "is_eligible": is_eligible,
        "eligibility_date": eligibility_date,
        "reason": reason,
        "date_of_joining": doj,
        "probation_days": probation_days,
        "applicable_after": applicable_after,
        "employee_name": emp_info.employee_name
    }


def get_first_eligible_allocation_date(employee, leave_type, effective_from, effective_to):
    """
    Get the first allocation date (15th) when employee becomes eligible.

    Used for creating earned leave schedule.

    Args:
        employee: Employee ID
        leave_type: Leave Type name
        effective_from: Start of leave period
        effective_to: End of leave period

    Returns:
        date or None: First eligible allocation date, or None if never eligible in period
    """
    from customize_erpnext.overrides.earned_leave.earned_leave import get_15th_of_month
    from frappe.utils import add_months

    # Get eligibility info
    result = is_employee_eligible_for_earned_leave(
        employee, effective_from, leave_type
    )

    eligibility_date = result["eligibility_date"]
    if not eligibility_date:
        return None

    # Find first 15th >= eligibility_date within the period
    current_15th = get_15th_of_month(getdate(effective_from))

    while current_15th <= getdate(effective_to):
        if current_15th >= eligibility_date:
            return current_15th
        current_15th = get_15th_of_month(add_months(current_15th, 1))

    return None


def log_eligibility_skip(employee, allocation_date, leave_type, eligibility_info):
    """
    Log when an allocation is skipped due to eligibility.

    Args:
        employee: Employee ID
        allocation_date: Date allocation was attempted
        leave_type: Leave Type name
        eligibility_info: Result from is_employee_eligible_for_earned_leave
    """
    message = (
        f"Earned leave allocation skipped for {employee} ({eligibility_info.get('employee_name', '')}):\n"
        f"- Leave Type: {leave_type}\n"
        f"- Allocation Date: {allocation_date}\n"
        f"- Eligibility Date: {eligibility_info['eligibility_date']}\n"
        f"- Reason: {eligibility_info['reason']}\n"
        f"- DOJ: {eligibility_info['date_of_joining']}\n"
        f"- Probation Days: {eligibility_info['probation_days']}\n"
        f"- Applicable After: {eligibility_info['applicable_after']}"
    )

    frappe.log_error(
        message=message,
        title="Earned Leave Eligibility Skip"
    )


print("✅ Earned Leave Eligibility loaded")
