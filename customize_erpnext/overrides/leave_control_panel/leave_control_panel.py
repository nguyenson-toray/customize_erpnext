# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Leave Control Panel — tuỳ chọn chọn nhân viên theo **khoảng làm việc** thay vì trạng thái.

HRMS gốc (`leave_control_panel.py:195`) lọc cứng `[["status", "=", "Active"]]`. Với việc cấp
phép cho một kỳ **đã qua** thì điều đó thiếu: người nghỉ việc giữa kỳ vẫn được hưởng phép năm
cho những tháng đã làm (Điều 66 NĐ 145/2020 — xem
`leave_application/QUY_DINH_NGHI_PHEP_2025.md`), nhưng họ mang `status = Left` nên không hiện
ra để chọn. Và `filters` của panel chỉ AND thêm được, **không** bỏ được điều kiện Active đó —
nên không có cách nào khác ngoài override.

🔴 **Hành vi mặc định = HRMS gốc.** Chỉ khi HR tick `custom_include_employees_who_left`
(mục "Allocate Leaves", ngay dưới `allocate_based_on_leave_policy`) thì mới nới ra:

    date_of_joining <= to_date  AND  (relieving_date IS NULL OR relieving_date >= from_date)

Mặc định TẮT vì vận hành bình thường **không cần** nó: phép được cấp lúc đầu kỳ / lúc vào làm
khi ai cũng còn Active, rồi scheduler earned leave tự cộng dần và tự dừng khi người ta nghỉ.
Chỉ đợt dựng kỳ hồi tố (như 2026 dựng vào tháng 8/2026) mới cần bật.

Đo trên dữ liệu TIQN kỳ 26/12/2025 → 25/12/2026:

    TẮT — chỉ Active (HRMS gốc)     1.002
    BẬT — làm việc trong kỳ         1.496   (+462 Left nghỉ giữa kỳ, +32 Inactive)
    nghỉ TRƯỚC kỳ -> vẫn loại         895

(Cả hai đã trừ phạm vi của `Attendance Calculation Setting` — xem
`_attendance_setting_filters()`: prefix TIQN loại 17 mã `Intern-*`, exclude list loại 3 mã.)

Cấp phép cho người đã nghỉ là **an toàn**: `earned_leave.py:838` truyền `relieving_date` vào
`get_period_entitlement()` nên họ chỉ nhận đúng số tháng thực làm (nghỉ 05/01 → 0,0 ngày).

Không đụng phần còn lại: bộ lọc company/department/... và việc loại người đã có allocation
(`get_employees_without_allocations`) giữ nguyên của HRMS.

⚠ Panel **không** lọc trùng `Leave Policy Assignment` — nó chỉ loại người đã có
`Leave Allocation`. Còn LPA cũ trong kỳ thì `Allocate Leave` throw
"already assigned for Employee ... for period ...". Xem `scripts/reset_leave_allocation.sql`.
"""

import frappe

INCLUDE_LEFT_FIELD = "custom_include_employees_who_left"

# Trạng thái coi như KHÔNG còn làm việc mà lại thiếu ngày nghỉ việc -> loại, vì không có
# cách nào biết họ có làm trong kỳ hay không.
# `.strip()` là bắt buộc: dữ liệu TIQN có bản ghi mang status "Left " (dấu cách cuối) và
# so sánh chuỗi tuyệt đối sẽ để nó lọt lưới.
TERMINATED_STATUSES = ("Left",)


def _is_terminated_without_date(row) -> bool:
	return (row.status or "").strip() in TERMINATED_STATUSES and not row.relieving_date


def _attendance_setting_filters() -> list:
	"""Cùng phạm vi nhân viên mà engine chấm công dùng — `Attendance Calculation Setting`.

	    Employee ID Prefix   -> chỉ nhân viên `name LIKE '<prefix>%'`
	    Exclude Employee IDs -> loại hẳn các mã liệt kê

	Vì sao dùng lại thay vì tự nghĩ tiêu chí: `exclude_employee_ids` là nhân sự của công ty
	khác làm tại nhà máy (quẹt thẻ như mọi người nhưng không thuộc mình để quản lý), cộng với
	các record test còn sót. Trước đây `Test-9999` lọt vào danh sách cấp phép chính vì panel
	không biết tới setting này.

	Áp cho **cả hai** trạng thái checkbox: đây là câu hỏi "ai là nhân viên của mình", độc lập
	với câu hỏi "có tính người đã nghỉ hay không".

	Import cục bộ: module setting nằm trong app này nhưng import ở top-level sẽ tạo vòng
	(setting -> ... -> overrides) lúc nạp app.
	"""
	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
		get_attendance_settings,
		get_excluded_employee_ids,
	)

	out = []

	prefix = (get_attendance_settings().employee_id_prefix or "").strip()
	if prefix:
		out.append(["name", "like", f"{prefix}%"])

	excluded = get_excluded_employee_ids()
	if excluded:
		# `not in` với list rỗng sinh SQL không hợp lệ -> chỉ thêm khi có phần tử.
		out.append(["name", "not in", sorted(excluded)])

	return out


def custom_get_employees(self, advanced_filters: list) -> list:
	"""Thay `LeaveControlPanel.get_employees`.

	Checkbox TẮT -> giữ nguyên `status = Active` như HRMS gốc.
	Checkbox BẬT -> đổi sang điều kiện khoảng làm việc giao với kỳ.
	"""
	from_date, to_date = self.get_from_to_date()

	if not (to_date and (from_date or self.dates_based_on == "Joining Date")):
		return []

	include_left = bool(self.get(INCLUDE_LEFT_FIELD))
	filters = self.get_filters(include_left=include_left) + list(advanced_filters or [])
	or_filters = []

	if include_left:
		filters.append(["date_of_joining", "<=", to_date])

		# `filters` bị AND với nhau nên không diễn tả được "relieving_date rỗng HOẶC
		# >= from_date"; `or_filters` được AND với `filters` và OR lẫn nhau, đúng thứ cần.
		#
		# ⚠ Chế độ "Joining Date" không có from_date nên KHÔNG lọc được ngày nghỉ việc ->
		# lấy đầu Leave Period làm mốc, nếu không thì mọi nhân viên từng tồn tại đều hiện ra
		# (đo được 2.411 thay vì 1.496).
		boundary = from_date or self._get_period_start_for_left_filter()
		if boundary:
			or_filters = [
				["relieving_date", "is", "not set"],
				["relieving_date", ">=", boundary],
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

	if include_left:
		# Đã nghỉ việc mà không có ngày nghỉ -> không xác định được có làm trong kỳ hay không
		all_employees = [d for d in all_employees if not _is_terminated_without_date(d)]

	if not all_employees:
		return []
	return self.get_employees_without_allocations(all_employees, from_date, to_date)


def custom_get_period_start_for_left_filter(self):
	"""Mốc dưới cho bộ lọc `relieving_date` khi `dates_based_on = "Joining Date"`."""
	if self.get("leave_period"):
		return frappe.db.get_value("Leave Period", self.leave_period, "from_date")
	return None


def custom_get_filters(self, include_left: bool = False):
	"""Như HRMS gốc; chỉ bỏ `["status", "=", "Active"]` khi `include_left`.

	Lúc đó khoảng làm việc mới là điều kiện đúng, xử lý ở `custom_get_employees()`.

	⚠ HRMS gọi hàm này ở chỗ khác không truyền tham số (mặc định `False` = giữ Active),
	nên không được biến `include_left` thành tham số bắt buộc.
	"""
	filters = [] if include_left else [["status", "=", "Active"]]
	filters += _attendance_setting_filters()

	filter_fields = [
		"company",
		"employment_type",
		"branch",
		"department",
		"designation",
		"employee_grade",
	]
	for d in filter_fields:
		if self.get(d):
			filters.append(["grade" if d == "employee_grade" else d, "=", self.get(d)])
	return filters
