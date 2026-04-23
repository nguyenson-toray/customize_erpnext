# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

# NOTE: Maternity tracking functions have been moved to Employee Maternity doctype.
# See: customize_erpnext/customize_erpnext/doctype/employee_maternity/employee_maternity.py
# Old functions removed:
#   - check_maternity_tracking_changes_for_attendance()
#   - auto_update_attendance_on_maternity_change()
#   - background_update_attendance_for_maternity()

import frappe
from frappe.utils import today, getdate

@frappe.whitelist()
def auto_mark_employees_as_left():
    """
    Scheduled daily at 00:00.
    Updates Employee status from 'Active' to 'Left' if:
      - relieving_date not null and less than or equal to today
    #   - reason_for_leaving is not null/empty
    """
    today_date = getdate(today())

    employees = frappe.get_all(
        "Employee",
        filters=[
            ["relieving_date", "is", "set"],                    # not null
            ["relieving_date", "<=", today()],                  # <= today
           
        ],
        fields=["name", "employee_name", "relieving_date", "reason_for_leaving"],
    )

    if not employees:
        frappe.logger().info("[auto_mark_employees_as_left] No employees to update.")
        return

    updated = []
    errors = []

    for emp in employees:
        try:
            frappe.db.set_value(
                "Employee",
                emp["name"],
                "status",
                "Left",
                update_modified=True,
            )
            updated.append(emp["name"])
        except Exception as e:
            errors.append({"employee": emp["name"], "error": str(e)})
            frappe.log_error(
                title=f"[auto_mark_employees_as_left] Failed: {emp['name']}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()

    frappe.logger().info(
        f"[auto_mark_employees_as_left] Updated {len(updated)} employee(s) to 'Left': {updated}"
    )

    if errors:
        frappe.logger().error(
            f"[auto_mark_employees_as_left] {len(errors)} error(s): {errors}"
        )
