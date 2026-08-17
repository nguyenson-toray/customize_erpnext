"""
Employee Reminders Overrides - Apply Monkey Patches
"""

import frappe
from customize_erpnext.overrides.employee_reminders.employee_reminders import (
	custom_send_holidays_reminder_in_advance,
)
import hrms.controllers.employee_reminders as hrms_employee_reminders

# Save original functions (for debugging/rollback)
if not hasattr(hrms_employee_reminders, '_original_send_holidays_reminder_in_advance'):
	hrms_employee_reminders._original_send_holidays_reminder_in_advance = (
		hrms_employee_reminders.send_holidays_reminder_in_advance
	)


# Replace with custom functions
hrms_employee_reminders.send_holidays_reminder_in_advance = custom_send_holidays_reminder_in_advance

frappe.logger().info("✅ Monkey patch applied: /customize_erpnext/overrides/employee_reminders/employee_reminders")
