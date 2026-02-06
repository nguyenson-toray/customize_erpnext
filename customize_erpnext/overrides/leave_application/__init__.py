# Leave Application Overrides Module
"""
LeaveApplicationOverrides - Apply Monkey Patches

Customizations:
1. Allow Half Day leave when attendance already exists with partial working hours
2. Support dual Half Day leave applications on single attendance
3. Calculate combined abbreviation (e.g., OP/2, COP/2)
4. Handle cancel properly for dual leave scenario
"""

import frappe
from customize_erpnext.overrides.leave_application.leave_application import (
	custom_validate_attendance,
	custom_create_or_update_attendance,
)


# Apply monkey patch
try:
	from hrms.hr.doctype.leave_application.leave_application import LeaveApplication

	# Override the validate_attendance method
	LeaveApplication.validate_attendance = custom_validate_attendance

	# Override the create_or_update_attendance method
	LeaveApplication.create_or_update_attendance = custom_create_or_update_attendance

	frappe.logger().info("✅ LeaveApplication.validate_attendance monkey patched")
	frappe.logger().info("✅ LeaveApplication.create_or_update_attendance monkey patched")
except Exception as e:
	frappe.log_error(f"Failed to monkey patch LeaveApplication: {str(e)}", "LeaveApplication Monkey Patch Error")
	frappe.logger().error(f"Failed to monkey patch LeaveApplication: {str(e)}")
