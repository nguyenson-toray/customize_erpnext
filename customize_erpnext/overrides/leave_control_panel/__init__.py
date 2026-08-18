"""Monkey patch Leave Control Panel — chọn nhân viên theo khoảng làm việc.

Xem `leave_control_panel.py` để biết lý do và số liệu.
"""

import frappe

try:
	from hrms.hr.doctype.leave_control_panel.leave_control_panel import LeaveControlPanel

	from customize_erpnext.overrides.leave_control_panel.leave_control_panel import (
		custom_get_employees,
		custom_get_filters,
		custom_get_period_start_for_left_filter,
	)

	# get_employees là @frappe.whitelist(); gán đè giữ nguyên thuộc tính whitelist của
	# phương thức gốc trên class nên client vẫn gọi được qua run_doc_method.
	LeaveControlPanel.get_employees = frappe.whitelist()(custom_get_employees)
	LeaveControlPanel.get_filters = custom_get_filters
	# Helper mới, không có bản gốc để đè — KHÔNG whitelist (chỉ gọi nội bộ).
	LeaveControlPanel._get_period_start_for_left_filter = custom_get_period_start_for_left_filter

	print("✅ Leave Control Panel override loaded")

except Exception as e:
	frappe.log_error(
		f"Failed to apply Leave Control Panel patch: {str(e)}",
		"Leave Control Panel Monkey Patch Error",
	)
