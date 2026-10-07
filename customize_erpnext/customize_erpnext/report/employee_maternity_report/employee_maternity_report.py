# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Employee Maternity Report — 1 màn hình, lọc theo khoảng ngày [from_date, to_date].

Viết lại 07/10/2026 theo yêu cầu "đơn giản, dễ dùng": bỏ chế độ As On Date / Snapshot,
bỏ tách 3 dòng giai đoạn. Muốn xem "hôm nay" thì chọn From = To = hôm nay.

Mỗi dòng = 1 hồ sơ thai sản có ít nhất 1 sự kiện trong kỳ. 5 nhóm (thẻ số phía trên,
đếm DISTINCT employee — 1 NV có thể nằm ở nhiều nhóm):
  Pregnant / Maternity Leave / Young Child : giai đoạn CHẠM kỳ (user chốt bỏ "bắt đầu trong kỳ")
  Returned to Work : maternity_to_date + 1 ∈ kỳ, chưa nghỉ việc tới ngày đó
  Left             : Employee.status = Left và relieving_date ∈ kỳ (user chốt 06/10/2026)

⚠ relieving_date = ngày ĐẦU TIÊN nghỉ việc: "còn làm tại X" là relieving_date > X.
Mọi giai đoạn bị CẮT tại relieving_date - 1 — người đã nghỉ việc không còn được tính
là đang mang thai / nghỉ thai sản / con nhỏ (record của họ đã đóng `Inactive`).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, nowdate

from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity import (
	_gestational_age_months,
)

GROUPS = ("Pregnant", "Maternity Leave", "Young Child", "Returned to Work", "Left")

_GROUP_FLAG = {
	"Pregnant": "is_pregnant",
	"Maternity Leave": "is_maternity",
	"Young Child": "is_young_child",
	"Returned to Work": "is_returned",
	"Left": "is_left",
}

# Nhãn hiển thị khác khoá nhóm: "Returned" nghe như chỉ đếm người ĐÃ đi làm lại, trong khi
# nhóm này gồm cả ngày đi làm lại trong TƯƠNG LAI (user cần xem "tháng sau bao nhiêu người").
# Khoá "Returned to Work" giữ nguyên vì là giá trị filter `show` + route đã lưu.
_LABEL = {"Returned to Work": "Return to Work"}

_INDICATOR = {
	"Pregnant": "Blue",
	"Maternity Leave": "Orange",
	"Young Child": "Green",
	"Returned to Work": "Purple",
	"Left": "Red",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = _get_period(filters)

	records = _get_records(filters)
	left_record = _left_record_by_employee(records)

	rows = []
	for rec in records:
		row = _build_row(rec, from_date, to_date, left_record.get(rec.employee) == rec.maternity_record)
		if row:
			rows.append(row)

	summary = [
		{
			"value": len({r["employee"] for r in rows if r[_GROUP_FLAG[g]]}),
			"label": _(_LABEL.get(g, g)),
			"datatype": "Int",
			"indicator": _INDICATOR[g],
		}
		for g in GROUPS
	]

	show = filters.get("show")
	if show in _GROUP_FLAG:
		rows = [r for r in rows if r[_GROUP_FLAG[show]]]

	# ⚠ Không được default 1: query_report.js (get_filter_values) BỎ mọi filter có giá trị
	# falsy → bỏ tick Compact View thì key "compact" KHÔNG được gửi lên. Thiếu key = đầy đủ;
	# mặc định Rút gọn đến từ `default: 1` của filter trong JS.
	return get_columns(cint(filters.get("compact"))), rows, None, None, summary


def _get_period(filters):
	from_date = getdate(filters.get("from_date") or nowdate())
	to_date = getdate(filters.get("to_date") or from_date)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date"))
	return from_date, to_date


def _get_records(filters):
	conditions = ["1=1"]
	params = {}
	for key, column in (
		("department", "emp.department"),
		("custom_group", "emp.custom_group"),
	):
		if filters.get(key):
			conditions.append(f"{column} = %({key})s")
			params[key] = filters[key]

	return frappe.db.sql(f"""
		SELECT
			mt.name          AS maternity_record,
			emp.name         AS employee,
			emp.employee_name,
			emp.department,
			emp.custom_group,
			emp.status       AS employee_status,
			emp.relieving_date,
			mt.child_order,
			mt.is_twins,
			mt.pregnant_from_date,
			mt.pregnant_to_date,
			mt.pregnancy_notified_date,
			mt.estimated_due_date,
			mt.maternity_from_date AS mat_from,
			mt.maternity_to_date,
			mt.leave_months,
			mt.youg_child_from_date,
			mt.youg_child_to_date,
			mt.note
		FROM `tabEmployee` emp
		INNER JOIN `tabEmployee Maternity` mt ON emp.name = mt.employee
		WHERE {" AND ".join(conditions)}
		ORDER BY emp.department, emp.custom_group, emp.employee_name, mt.name
	""", params, as_dict=True)


def _build_row(rec, from_date, to_date, owns_left_event):
	"""Dòng report của 1 hồ sơ, hoặc None nếu hồ sơ không có sự kiện nào trong kỳ."""
	relieving = getdate(rec.relieving_date) if rec.relieving_date else None

	pregnant = _in_period(rec.pregnant_from_date, rec.pregnant_to_date, from_date, to_date, relieving)
	maternity = _in_period(rec.mat_from, rec.maternity_to_date, from_date, to_date, relieving)
	# Chưa có ngày sinh con (Young Child To trống) → chưa tính là Con nhỏ (user chốt 07/10/2026).
	young_child = bool(rec.youg_child_to_date) and _in_period(
		rec.youg_child_from_date, rec.youg_child_to_date, from_date, to_date, relieving
	)

	return_date = add_days(getdate(rec.maternity_to_date), 1) if rec.maternity_to_date else None
	returned = bool(
		return_date
		and from_date <= return_date <= to_date
		and not (relieving and relieving <= return_date)
	)

	left = owns_left_event and bool(relieving and from_date <= relieving <= to_date)

	flags = {
		"is_pregnant": pregnant,
		"is_maternity": maternity,
		"is_young_child": young_child,
		"is_returned": returned,
		"is_left": left,
	}
	if not any(flags.values()):
		return None

	return {
		"maternity_record": rec.maternity_record,
		"employee": rec.employee,
		"employee_name": rec.employee_name,
		"department": rec.department,
		"custom_group": rec.custom_group,
		"child_order": rec.child_order or None,
		"is_twins": rec.is_twins,
		"events": ", ".join(_(_LABEL.get(g, g)) for g in GROUPS if flags[_GROUP_FLAG[g]]),
		"pregnant_from_date": rec.pregnant_from_date,
		"pregnant_to_date": rec.pregnant_to_date,
		"pregnancy_notified_date": rec.pregnancy_notified_date,
		"estimated_due_date": rec.estimated_due_date,
		"gestational_age": _gestational_age(rec, to_date, relieving),
		"maternity_from_date": rec.mat_from,
		"maternity_to_date": rec.maternity_to_date,
		"leave_months": rec.leave_months or None,
		"return_date": return_date,
		"youg_child_to_date": rec.youg_child_to_date,
		"relieving_date": rec.relieving_date,
		"left_during": _left_during(rec) if relieving else None,
		"note": rec.note,
		**{k: int(v) for k, v in flags.items()},
	}


def _in_period(start, end, from_date, to_date, relieving=None):
	"""Giai đoạn [start, end] có chạm kỳ không. `end` trống = còn đang diễn ra.
	Giai đoạn bị cắt tại relieving_date - 1 (từ ngày nghỉ việc là hết chế độ)."""
	if not start:
		return False
	start = getdate(start)
	end = getdate(end) if end else None
	if relieving:
		last_day = add_days(relieving, -1)
		end = min(end, last_day) if end else last_day
		if end < start:
			return False
	return start <= to_date and (end is None or end >= from_date)


def _gestational_age(rec, day, relieving):
	"""Tuổi thai (tháng) tại `day` (= To Date) — CHỈ khi đang ở giai đoạn Mang thai,
	cùng công thức với form (`_gestational_age_months`). Đã sinh / chưa mang thai /
	đã nghỉ việc → trống, không phải 9,5 hay 0."""
	if not rec.estimated_due_date:
		return None
	if not _in_period(rec.pregnant_from_date, rec.pregnant_to_date, day, day, relieving):
		return None
	return _gestational_age_months(rec.estimated_due_date, day)


def _left_record_by_employee(records):
	"""Gán sự kiện nghỉ việc cho ĐÚNG 1 hồ sơ mỗi NV: hồ sơ mới nhất bắt đầu trước
	ngày nghỉ việc. NV có 2 chu kỳ thai sản không bị đếm/hiện dòng nghỉ việc 2 lần.

	Chỉ người status `Left` — user chốt 06/10/2026: theo ngày nghỉ việc + status.
	⚠ `.strip()`: 1.393 Employee mang status `"Left "` có dấu cách.
	"""
	result = {}
	best_start = {}
	for rec in records:
		if (rec.employee_status or "").strip() != "Left" or not rec.relieving_date:
			continue
		start = rec.pregnant_from_date or rec.mat_from or rec.youg_child_from_date
		start = getdate(start) if start else None
		if start and start > getdate(rec.relieving_date):
			continue  # hồ sơ bắt đầu SAU khi đã nghỉ việc — không phải chu kỳ này
		prev = best_start.get(rec.employee, "unset")
		if prev == "unset" or (start and (prev is None or start > prev)):
			best_start[rec.employee] = start
			result[rec.employee] = rec.maternity_record
	return result


def _left_during(rec):
	"""Giai đoạn chứa ngày nghỉ việc (relieving_date = ngày đầu tiên không còn làm)."""
	day = getdate(rec.relieving_date)

	def within(start, end):
		return start and getdate(start) <= day and (not end or day <= getdate(end))

	first = rec.pregnant_from_date or rec.mat_from
	if first and day <= getdate(first):
		return _("Before Pregnancy")
	if within(rec.pregnant_from_date, rec.pregnant_to_date):
		return _("Pregnant")
	if within(rec.mat_from, rec.maternity_to_date):
		return _("Maternity Leave")
	if rec.maternity_to_date and day == add_days(getdate(rec.maternity_to_date), 1):
		return _("Did Not Return")  # đúng ngày lẽ ra quay lại thì nghỉ luôn
	if rec.youg_child_to_date and within(rec.youg_child_from_date, rec.youg_child_to_date):
		return _("Young Child")
	return _("After Young Child Period")


# Chế độ Rút gọn (mặc định, user chốt 07/10/2026) chỉ giữ 4 mốc của chu kỳ:
# bắt đầu mang thai → bắt đầu nghỉ thai sản → đi làm lại → kết thúc chu kỳ,
# cộng ngày nghỉ việc. Các cột dưới đây chỉ hiện khi bỏ tick "Compact View".
# Maternity To bỏ được vì = Return Date - 1.
# Rút gọn còn bỏ thêm Department (user chốt 07/10/2026: đã có Group).
# Đầy đủ: mỗi giai đoạn đủ 2 cột ngày Từ – Đến; 2 cột "Return Date" / "Cycle End" của
# chế độ Rút gọn chính là Young Child From / To nên chỉ đổi nhãn.
_FULL_ONLY_COLUMNS = {
	"department", "pregnant_to_date", "pregnancy_notified_date", "estimated_due_date",
	"gestational_age", "maternity_to_date",
}
_FULL_LABELS = {"return_date": "Young Child From", "youg_child_to_date": "Young Child To"}


def get_columns(compact=1):
	def col(fieldname, label, fieldtype="Data", width=110, options=None):
		c = {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}
		if options:
			c["options"] = options
		return c

	columns = [
		col("maternity_record", "Maternity Record", "Link", 150, "Employee Maternity"),
		col("employee", "Employee", "Link", 110, "Employee"),
		col("employee_name", "Employee Name", width=170),
		col("department", "Department", "Link", 120, "Department"),
		col("custom_group", "Group", width=100),
		col("child_order", "Child Number", "Int", 90),
		col("is_twins", "Twins", "Check", 60),
		col("events", "In Period", width=200),
		col("pregnant_from_date", "Pregnant From", "Date"),
		col("pregnant_to_date", "Pregnant To", "Date"),
		col("pregnancy_notified_date", "Pregnancy Notified Date", "Date", 130),
		col("estimated_due_date", "Estimated Due Date", "Date", 120),
		{**col("gestational_age", "Gestational Age (Months)", "Float", 110), "precision": 1},
		col("maternity_from_date", "Maternity From", "Date"),
		col("maternity_to_date", "Maternity To", "Date"),
		col("leave_months", "Leave Months", "Int", 90),
		col("return_date", "Return Date", "Date"),
		# = Young Child To Date (con đủ 12 tháng). Chưa có ngày sinh con thì để trống
		# — user chốt không tạm tính theo ngày dự sinh.
		col("youg_child_to_date", "Cycle End", "Date"),
		col("relieving_date", "Relieving Date", "Date"),
		col("left_during", "Left at Phase", width=150),
		col("note", "Note", width=200),
	]
	if compact:
		return [c for c in columns if c["fieldname"] not in _FULL_ONLY_COLUMNS]
	for c in columns:
		if c["fieldname"] in _FULL_LABELS:
			c["label"] = _(_FULL_LABELS[c["fieldname"]])
	return columns
