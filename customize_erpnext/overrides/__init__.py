"""
Main Overrides Module - Import All Monkey Patches

This module applies all monkey patches when imported.
Patches are applied immediately on import, not waiting for boot_session.
"""

import importlib

import frappe

# Mỗi module một try riêng: trước đây cả danh sách nằm trong MỘT try, nên một import lỗi
# (vd. HRMS v16.20 xoá hàm mà shift_type_optimized import) làm im lặng mất luôn mọi module
# đứng sau nó — earned_leave, leave_application, leave_reports... đều chạy logic gốc HRMS.
OVERRIDE_MODULES = [
	"customize_erpnext.overrides.employee_checkin",
	"customize_erpnext.overrides.shift_type",
	"customize_erpnext.overrides.attendance",
	"customize_erpnext.overrides.leave_application",
	"customize_erpnext.overrides.earned_leave",
	"customize_erpnext.overrides.leave_control_panel",
	"customize_erpnext.overrides.leave_reports",
	"customize_erpnext.overrides.shift_attendance",
	"customize_erpnext.overrides.employees_by_age",
	"customize_erpnext.overrides.employee_reminders",
	"customize_erpnext.overrides.lms_file_storage",
]


def _report_failure(what, e):
	frappe.log_error(f"Failed to load override {what}: {e}", "Overrides Import Error")
	frappe.logger().error(f"Failed to load override {what}: {e}")


# Apply monkey patches immediately on module import
# This ensures they're active for all contexts (web, background jobs, console, etc.)
failed = []
for module in OVERRIDE_MODULES:
	try:
		importlib.import_module(module)
	except Exception as e:
		failed.append(module)
		_report_failure(module, e)

# Cơ chế dùng chung cho JS của report (filter + clone). Gọi MỘT lần, sau các module trên vì
# nó tra bảng khai báo của chúng.
try:
	from customize_erpnext.overrides.report_js import patch as patch_report_js

	patch_report_js()
except Exception as e:
	failed.append("report_js")
	_report_failure("report_js", e)

if not failed:
	frappe.logger().info("✅ All overrides loaded successfully (on import)")
