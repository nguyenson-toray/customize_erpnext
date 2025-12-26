# Attendance Overrides Module
"""
AttendanceOverrides - Apply Monkey Patches
"""

import frappe
from customize_erpnext.overrides.attendance.attendance import custom_attendance_validate


# Apply monkey patch
try:
	from hrms.hr.doctype.attendance.attendance import Attendance

	# Override the validate method
	Attendance.validate = custom_attendance_validate

	frappe.logger().info("✅ Attendance.validate monkey patched successfully (includes Maternity Leave)")
except Exception as e:
	frappe.log_error(f"Failed to monkey patch Attendance.validate: {str(e)}", "Attendance Monkey Patch Error")
	frappe.logger().error(f"Failed to monkey patch Attendance.validate: {str(e)}")
