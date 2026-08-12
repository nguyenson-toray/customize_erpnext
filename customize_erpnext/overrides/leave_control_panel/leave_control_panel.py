# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Leave Control Panel — chọn nhân viên theo **khoảng làm việc**, không theo trạng thái hiện tại.

HRMS gốc (`leave_control_panel.py:195`) lọc cứng `[["status", "=", "Active"]]`. Cấp phép cho
một kỳ đã qua thì điều đó **sai**: người nghỉ việc giữa kỳ vẫn được hưởng phép năm cho những
tháng đã làm (Điều 66 NĐ 145/2020 — xem `leave_application/QUY_DINH_NGHI_PHEP_2025.md`),
nhưng họ đã mang `status = Left` nên không hiện ra để chọn.

Override: lấy mọi nhân viên có **khoảng làm việc giao với kỳ cấp phép**

    date_of_joining <= to_date  AND  (relieving_date IS NULL OR relieving_date >= from_date)

Đo trên dữ liệu TIQN kỳ 26/12/2025 → 25/12/2026:

    chỉ Active (HRMS gốc)          1.036
    làm việc trong kỳ (override)   1.508   (+447 Left nghỉ giữa kỳ, +25 Inactive)
    nghỉ TRƯỚC kỳ -> vẫn loại        893

Không đụng phần còn lại: bộ lọc company/department/... và việc loại người đã có allocation
(`get_employees_without_allocations`) giữ nguyên của HRMS.
"""

import frappe

# Trạng thái coi như KHÔNG còn làm việc mà lại thiếu ngày nghỉ việc -> loại, vì không có
# cách nào biết họ có làm trong kỳ hay không. Hiện dữ liệu TIQN có 0 bản ghi kiểu này.
TERMINATED_STATUSES = ("Left",)


def custom_get_employees(self, advanced_filters: list) -> list:
	"""Thay `LeaveControlPanel.get_employees` — bỏ lọc `status = Active`."""
	from_date, to_date = self.get_from_to_date()

	if not (to_date and (from_date or self.dates_based_on == "Joining Date")):
		return []

	filters = self.get_filters() + list(advanced_filters or [])
	filters.append(["date_of_joining", "<=", to_date])

	# `filters` bị AND với nhau nên không diễn tả được "relieving_date rỗng HOẶC >= from_date";
	# `or_filters` được AND với `filters` và OR lẫn nhau, đúng thứ cần.
	or_filters = []
	if from_date and self.dates_based_on != "Joining Date":
		or_filters = [
			["relieving_date", "is", "not set"],
			["relieving_date", ">=", from_date],
		]

	all_employees = frappe.get_list(
		"Employee",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name", "employee", "employee_name", "company", "department",
			"date_of_joining", "relieving_date", "status",
		],
	)

	# Đã nghỉ việc mà không có ngày nghỉ -> không xác định được có làm trong kỳ hay không
	all_employees = [
		d for d in all_employees
		if not (d.status in TERMINATED_STATUSES and not d.relieving_date)
	]

	if not all_employees:
		return []
	return self.get_employees_without_allocations(all_employees, from_date, to_date)


def custom_get_filters(self):
	"""Như HRMS gốc nhưng **bỏ** `["status", "=", "Active"]`.

	Khoảng làm việc mới là điều kiện đúng, xử lý ở `custom_get_employees()`.
	"""
	filter_fields = [
		"company",
		"employment_type",
		"branch",
		"department",
		"designation",
		"employee_grade",
	]
	filters = []
	for d in filter_fields:
		if self.get(d):
			filters.append(["grade" if d == "employee_grade" else d, "=", self.get(d)])
	return filters
