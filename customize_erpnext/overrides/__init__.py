"""
Main Overrides Module - Import All Monkey Patches

This module applies all monkey patches when imported.
Patches are applied immediately on import, not waiting for boot_session.
"""

import frappe

# Apply monkey patches immediately on module import
# This ensures they're active for all contexts (web, background jobs, console, etc.)
try:
	import customize_erpnext.overrides.employee_checkin
	import customize_erpnext.overrides.shift_type
	import customize_erpnext.overrides.attendance
	import customize_erpnext.overrides.leave_application
	import customize_erpnext.overrides.earned_leave
	import customize_erpnext.overrides.leave_control_panel
	import customize_erpnext.overrides.leave_reports
	import customize_erpnext.overrides.shift_attendance
	import customize_erpnext.overrides.employees_by_age
	import customize_erpnext.overrides.employee_reminders
	import customize_erpnext.overrides.lms_file_storage

	# Cơ chế dùng chung cho JS của report (filter + clone). Gọi MỘT lần, sau các module trên vì
	# nó tra bảng khai báo của chúng.
	from customize_erpnext.overrides.report_js import patch as patch_report_js

	patch_report_js()

	frappe.logger().info("✅ All overrides loaded successfully (on import)")

except Exception as e:
	frappe.log_error(f"Failed to load overrides: {str(e)}", "Overrides Import Error")
	frappe.logger().error(f"Failed to load overrides: {str(e)}")


