"""Monkey patch hai report số dư phép — chỉ phép năm + tính trong bộ nhớ.

Frappe phân giải script report bằng `frappe.get_attr("<module path>.execute")` **lúc chạy**
(`Report.execute_module`), nên gán đè thuộc tính `execute` của module là đủ — không cần sửa
file trong `apps/hrms`.

Xem `leave_report_core.py` (vì sao + số đo) và `leave_reports.md` (hướng dẫn dùng).
"""

import frappe


def _patch():
	import hrms.hr.report.employee_leave_balance.employee_leave_balance as bal_mod
	import hrms.hr.report.employee_leave_balance_summary.employee_leave_balance_summary as sum_mod

	from customize_erpnext.overrides.leave_reports.employee_leave_balance import custom_execute as bal
	from customize_erpnext.overrides.leave_reports.employee_leave_balance_summary import (
		custom_execute as summ,
	)

	# Giữ bản gốc để test đối chiếu (test_leave_reports.py) gọi lại được.
	if not hasattr(bal_mod, "_tiqn_original_execute"):
		bal_mod._tiqn_original_execute = bal_mod.execute
	if not hasattr(sum_mod, "_tiqn_original_execute"):
		sum_mod._tiqn_original_execute = sum_mod.execute

	bal_mod.execute = bal
	sum_mod.execute = summ


try:
	_patch()
	print("✅ Leave balance reports override loaded")
except Exception as e:
	frappe.log_error(
		f"Failed to apply leave report patches: {str(e)}", "Leave Report Monkey Patch Error"
	)
