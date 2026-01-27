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

	frappe.logger().info("✅ All overrides loaded successfully (on import)")

except Exception as e:
	frappe.log_error(f"Failed to load overrides: {str(e)}", "Overrides Import Error")
	frappe.logger().error(f"Failed to load overrides: {str(e)}")


