# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Phạm vi nhân viên "của mình" — một định nghĩa dùng chung.

`Attendance Calculation Setting` giữ hai field trả lời câu hỏi *ai là nhân viên của TIQN*:

    Employee ID Prefix    -> chỉ nhận `Employee.name LIKE '<prefix>%'`
    Exclude Employee IDs  -> loại hẳn các mã liệt kê

Hai field này KHÔNG phải tuỳ chọn hiển thị. `exclude_employee_ids` là nhân sự của công ty khác
làm việc tại nhà máy — họ quẹt thẻ như mọi người nhưng không thuộc mình để quản lý hay báo cáo —
cộng với các bản ghi test còn sót. Report nào bỏ qua hai field này sẽ cho ra danh sách khác với
bảng công và khác với headcount, và HR không có cách nào biết vì sao lệch.

Module này chỉ để **đọc** setting và đổi ra ba dạng dùng được ở ba nơi khác nhau:

    scope_filters()          -> filter list cho `frappe.get_list` / `frappe.get_all`
    apply_scope_to_query()   -> mệnh đề where cho query pypika (`frappe.qb`)
    in_scope()               -> lọc một danh sách mã đã có sẵn trong bộ nhớ

⚠ Import cục bộ bên trong hàm: module setting nằm cùng app nhưng import ở top-level sẽ tạo vòng
(setting -> ... -> overrides) lúc nạp app.
"""

import frappe


def get_scope() -> tuple[str, list[str]]:
	"""`(prefix, danh sách mã bị loại đã sắp xếp)`. Prefix rỗng = không giới hạn."""
	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
		get_attendance_settings,
		get_excluded_employee_ids,
	)

	prefix = (get_attendance_settings().employee_id_prefix or "").strip()
	excluded = sorted(get_excluded_employee_ids() or ())
	return prefix, excluded


def scope_filters() -> list:
	"""Dạng filter list: `[["name", "like", "TIQN%"], ["name", "not in", [...]]]`."""
	prefix, excluded = get_scope()
	out = []
	if prefix:
		out.append(["name", "like", f"{prefix}%"])
	if excluded:
		# `not in` với list rỗng sinh SQL không hợp lệ -> chỉ thêm khi có phần tử.
		out.append(["name", "not in", excluded])
	return out


def apply_scope_to_query(query, Employee):
	"""Thêm điều kiện vào một query pypika đang dựng. Trả về query mới (pypika bất biến)."""
	prefix, excluded = get_scope()
	if prefix:
		query = query.where(Employee.name.like(f"{prefix}%"))
	if excluded:
		query = query.where(Employee.name.notin(excluded))
	return query


def in_scope(employee_ids) -> list[str]:
	"""Lọc một danh sách mã đã nạp sẵn, giữ nguyên thứ tự."""
	prefix, excluded = get_scope()
	drop = set(excluded)
	return [
		e for e in employee_ids
		if e not in drop and (not prefix or str(e).startswith(prefix))
	]
