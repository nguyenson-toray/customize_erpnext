# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""`Employee Leave Balance Summary` — một leave type mỗi lần chạy, tính trong bộ nhớ.

## Bản gốc có một điểm mù nghiêm trọng

HRMS đọc `get_leave_details(employee, date)["leave_allocation"]`, mà dict đó **chỉ chứa leave
type có Leave Allocation**. TIQN chỉ cấp allocation cho phép năm, nên 9 loại còn lại luôn hiện
**0** dù đã nghỉ thật. Đo kỳ 26/12/2025 → 25/12/2026: **3.843,5 ngày** bị báo 0, gồm 1.832 ngày
ốm đau và 935 ngày nghỉ không lương.

(Không phải bug số âm: đã kiểm `TIQN-0882` phép năm allocated 1,0 / taken 10,0 → cả hai report
đều ra **−9,0**. Chỉ leave type KHÔNG có allocation mới bị báo 0.)

Nên report này nay có filter `Leave Type` (**mặc định phép năm**) và nói rõ loại nào qua tên cột.
Chọn một loại nghỉ phát sinh thì Allocated = 0 và Balance = −(đã nghỉ), vì chúng không được phân
bổ — đúng y bản HRMS, chỉ khác là **nhìn thấy được** thay vì bị nuốt thành 0.

**Xoá trắng ô Leave Type** thì hiện đủ 10 loại, mỗi loại một bộ 3 cột — bố cục "mỗi leave type
một nhóm cột" của bản gốc, nhưng KHÔNG còn điểm mù nói trên.

## Phạm vi nhân viên

Chỉ chạy cho nhân viên lọt `Employee ID Prefix` + `Exclude Employee IDs` của
`Attendance Calculation Setting` — xem `overrides/employee_scope.py`.

## Thêm hai cột

Bản gốc chỉ có `remaining`, không cho biết con số đó từ đâu ra. Thêm `Allocated` và `Taken` để
đọc được ngay mà không phải mở report kia — vẫn 1 dòng / nhân viên.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from customize_erpnext.overrides.employee_scope import scope_filters
from customize_erpnext.overrides.leave_reports.leave_report_core import (
	LeaveBalanceEngine,
	resolve_leave_types,
)


def custom_execute(filters=None):
	filters = frappe._dict(filters or {})
	leave_types = resolve_leave_types(filters)
	columns = custom_get_columns(leave_types)
	data = custom_get_data(filters, leave_types)
	return columns, data


def custom_get_columns(leave_types):
	columns = [
		_("Employee") + ":Link/Employee:150",
		_("Employee Name") + "::200",
		_("Department") + ":Link/Department:150",
	]
	# Dùng lại đúng nhãn của report `Employee Leave Balance` thay vì "Allocated/Taken/Balance":
	# vừa nhất quán từ ngữ giữa hai report, vừa tránh dịch những từ quá chung — `_("Balance")`
	# đang được 5 file ERPNext (kế toán) dùng, dịch toàn cục là đụng sang đó.
	for leave_type in leave_types:
		columns.append(_(leave_type) + " - " + _("Leave(s) Allocated") + ":Float:200")
		columns.append(_(leave_type) + " - " + _("Leave(s) Taken") + ":Float:200")
		columns.append(_(leave_type) + " - " + _("Leave Balance") + ":Float:200")
	return columns


def custom_get_conditions(filters):
	"""Filter cho `frappe.get_list("Employee", ...)`.

	Trả về **list** chứ không phải dict như bản gốc: phạm vi
	`Attendance Calculation Setting` cần toán tử `like` / `not in`, mà dạng dict chỉ diễn đạt
	được phép bằng. Hai dạng dùng lẫn nhau được ở `frappe.get_list`.
	"""
	conditions = []
	if filters.get("company"):
		conditions.append(["company", "=", filters.company])
	if filters.get("employee_status"):
		conditions.append(["status", "=", filters.get("employee_status")])
	if filters.get("department"):
		conditions.append(["department", "=", filters.get("department")])
	if filters.get("employee"):
		conditions.append(["name", "=", filters.get("employee")])
	return conditions + scope_filters()


def _period_start(as_on):
	"""Mốc đầu kỳ khi leave type KHÔNG có allocation (9 loại nghỉ phát sinh).

	Không có allocation thì không có `from_date` để tính "đã nghỉ bao nhiêu". Lấy Leave Period
	đang chứa ngày xem — đó cũng là kỳ mà HR dùng để đối chiếu.

	⚠ Thiếu bước này thì cột `Taken` của các loại nghỉ phát sinh **luôn bằng 0** — chính là điểm
	mù của bản HRMS gốc mà report này sinh ra để sửa.
	"""
	period = frappe.db.sql(
		"""SELECT from_date FROM `tabLeave Period`
		   WHERE from_date <= %(d)s AND to_date >= %(d)s
		   ORDER BY from_date DESC LIMIT 1""",
		{"d": as_on},
		as_dict=True,
	)
	return period[0].from_date if period else None


def custom_get_data(filters, leave_types):
	if not leave_types:
		frappe.msgprint(_("Please select a Leave Type."), indicator="orange", alert=True)
		return []

	employees = frappe.get_list(
		"Employee",
		filters=custom_get_conditions(filters),
		fields=["name", "employee_name", "department"],
		order_by="name",
	)
	if not employees:
		return []

	precision = cint(frappe.db.get_single_value("System Settings", "float_precision"))
	emp_names = [e.name for e in employees]
	as_on = filters.get("date") or frappe.utils.nowdate()
	fallback_start = _period_start(as_on)

	# 3 query mỗi leave type, không phụ thuộc số nhân viên
	engines = {lt: LeaveBalanceEngine(lt, emp_names) for lt in leave_types}

	data = []
	for emp in employees:
		row = [emp.name, emp.employee_name, emp.department]
		for lt in leave_types:
			engine = engines[lt]
			alloc = engine.allocation_record_on(emp.name, as_on)
			start = alloc.from_date if alloc else fallback_start

			allocated = flt(alloc.total_leaves_allocated, precision) if alloc else 0.0
			taken = flt(engine.leaves_taken(emp.name, start, as_on), precision) if start else 0.0

			# Có allocation -> dùng công thức HRMS. Không có -> số dư chính là phần đã nghỉ,
			# mang dấu âm, khớp với `closing_balance` của report Employee Leave Balance.
			balance = flt(engine.balance_on(emp.name, as_on), precision) if alloc else -taken

			row += [allocated, taken, balance]
		data.append(row)

	return data
