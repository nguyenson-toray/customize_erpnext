# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""`Employee Leave Balance` — chỉ phép năm, tính trong bộ nhớ.

Giữ **nguyên** bộ cột và công thức của HRMS. Thay bốn thứ:
  1. `get_leave_types()` (10 loại) -> filter `Leave Type`, mặc định phép năm, **bỏ trống = tất cả**
  2. các hàm con per-(NV × leave type) -> `LeaveBalanceEngine` (3 query, hằng số)
  3. `get_employees()` -> thêm phạm vi `Attendance Calculation Setting` (prefix + exclude)
  4. `consolidate_leave_types` chỉ áp khi thật sự có **nhiều** leave type + nới cột Employee /
     Employee Name

Xem `leave_report_core.py` để biết vì sao và số đo.

## `consolidate_leave_types` — giữ, nhưng có điều kiện

Filter đó gom dòng theo leave type và chèn một dòng tiêu đề cho mỗi nhóm. Bản gốc để
`default: 1` và chỉ chặn bằng `len(active_employees) > 1`, nên khi report chạy **một** leave type
(trường hợp mặc định ở TIQN) nó sinh đúng một dòng tiêu đề vô nghĩa rồi thụt lề toàn bộ phần còn
lại.

Nên thêm điều kiện `len(leave_types) > 1`: chạy một loại thì bảng phẳng, xoá ô Leave Type để xem
tất cả thì gom nhóm y như bản gốc. Đây là lý do ô chọn được **trả lại** giao diện sau khi từng bị
gỡ — lúc report bị khoá cứng ở một leave type thì nó thừa, nay thì không.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate

from customize_erpnext.overrides.employee_scope import apply_scope_to_query
from customize_erpnext.overrides.leave_reports.leave_report_core import (
	LeaveBalanceEngine,
	resolve_leave_types,
)

Filters = frappe._dict

# Bản gốc để Employee / Employee Name đều 100px — quá hẹp cho mã `TIQN-0002` và họ tên tiếng
# Việt đầy đủ. Đo trên dữ liệu thật: dài nhất 26 ký tự ("Huỳnh Nguyễn Thị Kim Trang"),
# trung bình 20,5.
EMPLOYEE_WIDTH = 150
EMPLOYEE_NAME_WIDTH = 300


def custom_execute(filters: Filters | None = None) -> tuple:
	from hrms.hr.report.employee_leave_balance.employee_leave_balance import get_chart_data

	if filters.to_date <= filters.from_date:
		frappe.throw(_('"From Date" can not be greater than or equal to "To Date"'))

	columns = custom_get_columns()
	data = custom_get_data(filters)
	charts = get_chart_data(data, filters)
	return columns, data, None, charts


def custom_get_columns() -> list[dict]:
	"""Như HRMS gốc, chỉ nới hai cột định danh."""
	from hrms.hr.report.employee_leave_balance.employee_leave_balance import get_columns

	widths = {"employee": EMPLOYEE_WIDTH, "employee_name": EMPLOYEE_NAME_WIDTH}
	columns = get_columns()
	for col in columns:
		if col["fieldname"] in widths:
			col["width"] = widths[col["fieldname"]]
	return columns


def custom_get_employees(filters: Filters) -> list[dict]:
	"""`get_employees()` của HRMS + phạm vi `Attendance Calculation Setting`.

	Chép lại thay vì gọi rồi lọc sau: lọc sau vẫn kéo về cả nghìn dòng thừa rồi mới bỏ đi, và
	`emp_names` truyền cho engine phải là danh sách ĐÃ lọc thì mới đỡ được khối lượng ledger.
	Giữ nguyên kiểu query pypika không kiểm phân quyền của bản gốc — report này vốn chỉ mở cho
	vai trò HR.
	"""
	Employee = frappe.qb.DocType("Employee")
	query = frappe.qb.from_(Employee).select(
		Employee.name,
		Employee.employee_name,
		Employee.department,
	)

	for field in ["company", "department"]:
		if filters.get(field):
			query = query.where(getattr(Employee, field) == filters.get(field))

	if filters.get("employee"):
		query = query.where(Employee.name == filters.get("employee"))

	if filters.get("employee_status"):
		query = query.where(Employee.status == filters.get("employee_status"))

	query = apply_scope_to_query(query, Employee)
	return query.run(as_dict=True)


def custom_get_data(filters: Filters) -> list:
	leave_types = resolve_leave_types(filters)
	if not leave_types:
		frappe.msgprint(_("Please select a Leave Type."), indicator="orange", alert=True)
		return []

	active_employees = custom_get_employees(filters)
	if not active_employees:
		return []

	precision = cint(frappe.db.get_single_value("System Settings", "float_precision"))
	emp_names = [e.name for e in active_employees]
	opening_balance_date = add_days(filters.from_date, -1)

	# Gom nhóm chỉ có nghĩa khi bảng thật sự chứa nhiều leave type — xem docstring module.
	consolidate = bool(
		filters.get("consolidate_leave_types")
		and len(leave_types) > 1
		and len(active_employees) > 1
	)
	data = []

	for leave_type in leave_types:
		engine = LeaveBalanceEngine(leave_type, emp_names)
		if consolidate:
			data.append({"leave_type": leave_type})

		for employee in active_employees:
			row = frappe._dict() if consolidate else frappe._dict({"leave_type": leave_type})
			row.employee = employee.name
			row.employee_name = employee.employee_name

			leaves_taken = engine.leaves_taken(employee.name, filters.from_date, filters.to_date)

			new_allocation = engine.allocated(employee.name, filters.from_date, filters.to_date)
			expired_leaves = engine.expired(employee.name, filters.from_date, filters.to_date)
			carry_forwarded_leaves = engine.carry_forwarded(
				employee.name, filters.from_date, filters.to_date
			)

			# Khớp `is_opening_balance_on_allocation_boundary`: kỳ trước hết hạn đúng hôm trước
			prev = engine.previous_allocation(employee.name, filters.from_date)
			on_allocation_boundary = bool(
				prev and prev.to_date and getdate(prev.to_date) == getdate(opening_balance_date)
			)

			if on_allocation_boundary:
				opening = carry_forwarded_leaves
			else:
				opening = engine.balance_on(employee.name, opening_balance_date)

			allocated_leaves = new_allocation + carry_forwarded_leaves
			if on_allocation_boundary:
				allocated_leaves -= carry_forwarded_leaves

			row.leaves_allocated = flt(allocated_leaves, precision)
			row.leaves_expired = flt(expired_leaves, precision)
			row.opening_balance = flt(opening, precision)
			row.leaves_taken = flt(leaves_taken, precision)
			row.closing_balance = flt(
				allocated_leaves + opening - (row.leaves_expired + leaves_taken), precision
			)
			if consolidate:
				row.indent = 1
			data.append(row)

	return data
