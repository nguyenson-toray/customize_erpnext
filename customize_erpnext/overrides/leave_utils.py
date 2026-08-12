# Copyright (c) 2025, IT Team - TIQN
# License: MIT

"""Helper cho luồng Leave Application → Attendance.

Mọi **quyết định** nghiệp vụ (mã viết tắt, `half_day_status`, loại nghỉ nào vào
`Attendance.leave_type`) nằm ở `overrides/leave_rules.py` — file này chỉ đọc/ghi DB.
Lý do: engine tính công ghi vào cùng các field đó, hai bên phải dùng chung một nguồn.

Đã xoá 2026-08-10 (0 tham chiếu ngoài file này, xem `leave_application/PLAN_LEAVE_OVERRIDE.md`
GĐ 5): `get_working_days_for_leave` · `get_total_leave_days` · `find_other_half_day_leave` ·
`is_paid_leave_type` · `create_attendance_for_leave` · `remove_leave_from_attendance`, cùng hai
dict `LEAVE_TYPE_ABBREVIATIONS` / `PAID_LEAVE_TYPES` khoá theo tên tiếng Anh không khớp Leave Type
thật nào.

Hai thứ trong số đó **sai**, đừng hồi sinh:
  - `is_paid_leave_type()` đọc `Leave Type.custom_is_paid_leave` — field không tồn tại, gọi là nổ.
    Cờ đúng là `is_lwp` (`leave_rules.is_unpaid`).
  - `get_working_days_for_leave()` trả `P/2 → 0,5`; quy định là **1** ngày công.
"""

import frappe
from frappe.utils import getdate

from customize_erpnext.overrides.leave_rules import (
	combined_abbreviation,
	get_abbreviation,
	order_leave_types,
	resolve_half_day_status,
)

ATTENDANCE_FIELDS = [
	"name",
	"status",
	"leave_type",
	"leave_application",
	"custom_leave_type_2",
	"custom_leave_application_2",
	"custom_leave_application_abbreviation",
	"half_day_status",
	"working_hours",
]


def get_leave_type_abbreviation(leave_type):
	"""Mã viết tắt của Leave Type (`custom_abbreviation`)."""
	return get_abbreviation(leave_type)


def get_combined_abbreviation(leave_type_1, leave_type_2=None):
	"""Mã in trên bảng công cho nửa ngày — theo bảng của quy định."""
	return combined_abbreviation(leave_type_1, leave_type_2)


def find_attendance_for_leave(employee, attendance_date):
	"""Attendance chưa cancel của nhân viên trong ngày, hoặc `None`."""
	rows = frappe.get_all(
		"Attendance",
		filters={
			"employee": employee,
			"attendance_date": getdate(attendance_date),
			"docstatus": ["!=", 2],
		},
		fields=ATTENDANCE_FIELDS,
		limit=1,
	)
	return rows[0] if rows else None


def find_other_half_day_leave_type(employee, half_day_date, exclude_leave_application):
	"""Loại nghỉ của đơn **nửa ngày khác** cùng nhân viên, cùng ngày.

	Cần cho `resolve_half_day_status()`: luồng Leave Application chỉ nhìn đơn của chính nó, nên
	nếu không tra thêm thì không biết nửa còn lại là nghỉ có lương hay không lương — mà đó chính
	là thứ quyết định `half_day_status`.
	"""
	rows = frappe.get_all(
		"Leave Application",
		filters={
			"employee": employee,
			"half_day": 1,
			"half_day_date": getdate(half_day_date),
			"status": "Approved",
			"docstatus": 1,
			"name": ["!=", exclude_leave_application or ""],
		},
		fields=["leave_type"],
		order_by="name",
		limit=1,
	)
	return rows[0].leave_type if rows else None


def update_attendance_with_dual_leave(
	attendance_name,
	leave_type_1,
	leave_application_1,
	leave_type_2=None,
	leave_application_2=None,
	has_checkin=False,
):
	"""Ghi hai đơn nghỉ nửa ngày lên một Attendance.

	🔴 Trạng thái là **`Half Day`**, không phải `On Leave`. Hai nửa ngày cộng lại đúng bằng một
	ngày *vắng mặt*, nhưng `On Leave` làm HRMS trừ **trọn ngày**
	(`salary_slip.py:800` đặt `equivalent_lwp = 1`), còn quy định cho `OP/2` = **0,5** ngày công.
	`Half Day` + `leave_type` là nửa `is_lwp` + `half_day_status` mới ra đúng cả 5 tổ hợp.
	"""
	primary, other = order_leave_types(leave_type_1, leave_type_2)
	# leave_application phải đi kèm đúng leave_type sau khi đổi thứ tự
	if other and primary != leave_type_1:
		leave_application_1, leave_application_2 = leave_application_2, leave_application_1

	abbr = combined_abbreviation(primary, other)
	frappe.db.set_value(
		"Attendance",
		attendance_name,
		{
			"status": "Half Day",
			"leave_type": primary,
			"leave_application": leave_application_1,
			"custom_leave_type_2": other,
			"custom_leave_application_2": leave_application_2 if other else None,
			"custom_leave_application_abbreviation": abbr,
			"half_day_status": resolve_half_day_status(has_checkin, other),
		},
	)
	return abbr
