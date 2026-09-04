# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Cờ `Employee.custom_is_maternity_leave` và sub-status của hồ sơ thai sản.

Chỉ `Maternity Leave` nghĩa là người đó thật sự vắng mặt — `Pregnant` và
`Young Child` vẫn đi làm bình thường (chỉ được giảm 1 giờ cuối ca), nên hai giai
đoạn đó không bật cờ.

## 🔴 KHÔNG bao giờ đổi `Employee.status` sang `Inactive`

Bản trước của module này lật `Active -> Inactive` khi vào kỳ nghỉ thai sản. Đã bỏ
hẳn, và đừng dựng lại — bốn lý do, đo trên chính site này:

1. **Mất dữ liệu quẹt thẻ.** `hrms/hr/doctype/employee_checkin/employee_checkin.py:29`
   gọi `validate_active_employee()` -> throw với Inactive. Máy chấm công đẩy dữ liệu
   qua API (64.226 bản ghi/tháng) sẽ lỗi. Mà chuyện "HR ghi sai ngày, nhân viên đi làm
   thật" ĐANG xảy ra: 4 người / 66 lần check-in rơi vào kỳ nghỉ thai sản.
2. **Engine tính công bỏ qua** (`shift_type_optimized.py`: chỉ `Active` hoặc `Left`).
3. **Export Excel bỏ qua** (`standard_export.py`: cùng điều kiện).
4. **Leave Control Panel bỏ qua** (`hrms .../leave_control_panel.py:195` lọc `Active`)
   -> không cấp phép năm, trong khi Điều 65 NĐ 145/2020 vẫn tính thời gian nghỉ thai
   sản là thời gian làm việc để hưởng phép năm.

Ngoài ra `status` là field mà hàng chục luồng khác cùng ghi: ngày 25/08/2026 một
thao tác cập nhật Employee hàng loạt đã ghi đè 34 người vừa được lật sang `Inactive`
về lại `Active`, và cơ chế cũ (chỉ chạy khi CÓ CHUYỂN TIẾP) không bao giờ sửa lại.
Cờ riêng + khẳng định lại mỗi đêm là để không lặp lại chuyện đó.

## Nguồn sự thật

Cờ lấy từ `Employee Maternity.status == "Maternity Leave"`, **không** lấy từ khoảng
ngày. Phải đúng nguồn này vì `api/headcount.py::maternity_leave_employees()` — thứ
quyết định Net Headcount trên dashboard và daily email — cũng đọc chính nó. Dùng
khoảng ngày thì hai bên lệch nhau: đo 04/09/2026 có 28 record phủ hôm nay nhưng chỉ
27 mang status `Maternity Leave` (record còn lại thuộc người đã nghỉ việc, đã được
đóng thành `Inactive`).

`custom_sub_status` là field HTML: không có cột trong DB, không lưu gì.
`get_employee_sub_status()` suy ra từ Employee Maternity mỗi lần form render.
"""

import frappe
from frappe.utils import cint, getdate

MATERNITY_LEAVE = "Maternity Leave"

# Cờ chỉ-đọc trên Employee. Có cột thật trong `tabEmployee` (khác `custom_sub_status`
# là HTML ảo) để Number Card / Dashboard Chart kiểu "Document Type" lọc được — loại
# đó chỉ lọc được field nằm trên chính doctype, không join sang Employee Maternity.
MATERNITY_FLAG_FIELD = "custom_is_maternity_leave"

# Which Employee Maternity record wins when an employee holds several (a second
# cycle, or a duplicate). Lower number = higher priority. Records with a blank
# status never win — they describe no phase at all.
PHASE_PRIORITY = {
	MATERNITY_LEAVE: 0,
	"Pregnant": 1,
	"Young Child": 2,
	"Inactive": 3,
}

PHASE_INDICATOR = {
	MATERNITY_LEAVE: "orange",
	"Pregnant": "blue",
	"Young Child": "green",
	"Inactive": "gray",
}


# =============================================================================
# Employee.status sync
# =============================================================================

def sync_maternity_flag(employee, exclude_record=None):
	"""Ghi lại `Employee.custom_is_maternity_leave` cho MỘT nhân viên.

	Suy ra từ DB chứ không nhận trạng thái từ caller: một nhân viên có thể giữ nhiều
	hồ sơ Employee Maternity (chu kỳ thứ hai, hoặc trùng), nên rời khỏi một hồ sơ
	không chứng minh được người đó đã đi làm lại.

	`exclude_record`: bắt buộc truyền khi gọi từ `on_trash`. Frappe chạy `on_trash`
	TRƯỚC khi xoá dòng khỏi DB, nên nếu không loại record đang xoá ra thì nó vẫn tự
	đếm mình và cờ không bao giờ được gỡ.

	Dùng `db.set_value` chứ không `doc.save()`: vòng đời Employee xoá cache toàn site
	và vô hiệu hoá User liên kết ở mỗi lần save, cả hai đều không thuộc về một thay
	đổi giai đoạn thai sản. `update_modified=False` để không đụng `modified` — nếu
	không, job 00:10 mỗi đêm sẽ đẩy 1.000+ nhân viên lên đầu list "vừa sửa".
	"""
	if not employee:
		return

	current = frappe.db.get_value("Employee", employee, MATERNITY_FLAG_FIELD)
	if current is None and not frappe.db.exists("Employee", employee):
		return  # nhân viên đã bị xoá

	target = 1 if _has_other_maternity_leave(employee, exclude_record) else 0
	if cint(current) == target:
		return

	frappe.db.set_value(
		"Employee", employee, MATERNITY_FLAG_FIELD, target, update_modified=False
	)


def sync_all_maternity_flags():
	"""Khẳng định lại cờ cho TOÀN BỘ nhân viên. Trả về `{"set": n, "cleared": n}`.

	🔴 Khẳng định lại TẤT CẢ, không chỉ record vừa đổi giai đoạn. Đây đúng là chỗ bản
	cũ sai: nó chỉ ghi khi có chuyển tiếp, nên khi một thao tác hàng loạt ghi đè mất
	giá trị (25/08/2026, 34 người) thì không lần chạy nào sau đó sửa lại.

	Hai câu UPDATE theo tập, không lặp từng người: site có 1.042 nhân viên Active và
	job này chạy hằng đêm.
	"""
	on_leave = set(
		frappe.db.sql_list(
			"SELECT DISTINCT employee FROM `tabEmployee Maternity`"
			" WHERE status = %s AND employee IS NOT NULL",
			MATERNITY_LEAVE,
		)
	)
	flagged = set(
		frappe.db.sql_list(
			f"SELECT name FROM `tabEmployee` WHERE `{MATERNITY_FLAG_FIELD}` = 1"
		)
	)

	to_set = on_leave - flagged
	to_clear = flagged - on_leave

	for names, value in ((to_set, 1), (to_clear, 0)):
		if not names:
			continue
		frappe.db.sql(
			f"UPDATE `tabEmployee` SET `{MATERNITY_FLAG_FIELD}` = %(value)s"
			" WHERE name IN %(names)s",
			{"value": value, "names": tuple(names)},
		)

	return {"set": len(to_set), "cleared": len(to_clear)}


def _has_other_maternity_leave(employee, exclude_record):
	filters = {"employee": employee, "status": MATERNITY_LEAVE}
	if exclude_record:
		filters["name"] = ("!=", exclude_record)
	return bool(frappe.db.exists("Employee Maternity", filters))


# =============================================================================
# Sub-status (display only — nothing is stored)
# =============================================================================

def _phase_start(row):
	"""First day of the phase the record's status refers to."""
	if row.status == "Pregnant":
		return row.pregnant_from_date
	if row.status == MATERNITY_LEAVE:
		return row.maternity_from_date or row.maternity_from_date_estimate
	if row.status == "Young Child":
		return row.youg_child_from_date
	return row.youg_child_to_date  # Inactive = everything already finished


def get_current_maternity_record(employee):
	"""The maternity record that describes the employee right now, or None.

	Deterministic by design: an employee can hold two or three records and a bare
	`LIMIT 1` would pick an arbitrary one. Ranks by phase priority, then by the
	latest phase start, then by the most recently touched record.
	"""
	if not employee:
		return None

	rows = frappe.get_all(
		"Employee Maternity",
		filters={"employee": employee, "status": ("in", list(PHASE_PRIORITY))},
		fields=[
			"name", "status", "modified",
			"pregnant_from_date", "pregnant_to_date",
			"maternity_from_date", "maternity_from_date_estimate", "maternity_to_date",
			"youg_child_from_date", "youg_child_to_date",
		],
	)
	if not rows:
		return None

	def sort_key(row):
		start = _phase_start(row)
		return (
			PHASE_PRIORITY.get(row.status, 99),
			-(getdate(start).toordinal() if start else 0),
			-row.modified.timestamp(),
		)

	return sorted(rows, key=sort_key)[0]


def _phase_range(row):
	if row.status == "Pregnant":
		return row.pregnant_from_date, row.pregnant_to_date
	if row.status == MATERNITY_LEAVE:
		return (row.maternity_from_date or row.maternity_from_date_estimate), row.maternity_to_date
	if row.status == "Young Child":
		return row.youg_child_from_date, row.youg_child_to_date
	return None, row.youg_child_to_date


@frappe.whitelist()
def get_employee_sub_status(employee):
	"""Payload for the `custom_sub_status` HTML field. Returns None when there is
	nothing to show.

	Maternity is currently the only source of a sub-status, but the shape is kept
	generic (`label`/`source`/`reference`) so other reasons for Inactive or
	Suspended can be added without changing the client.
	"""
	row = get_current_maternity_record(employee)
	if not row:
		return None

	from_date, to_date = _phase_range(row)
	return {
		"label": row.status,
		"indicator": PHASE_INDICATOR.get(row.status, "gray"),
		"source": "Employee Maternity",
		"reference": row.name,
		"from_date": str(from_date) if from_date else None,
		"to_date": str(to_date) if to_date else None,
		"on_leave": row.status == MATERNITY_LEAVE,
	}


def is_inactive_for_maternity(employee):
	"""True when the employee is Inactive because they are on maternity leave.

	Used to hold the linked User account open — being on maternity leave is not a
	reason to lock somebody out of their payslips and leave applications.
	"""
	if not employee:
		return False
	return _has_other_maternity_leave(employee, exclude_record=None)
