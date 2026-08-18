# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Bảng quy đổi mã nghỉ phép → ngày công, cho sheet **Timesheet** của Export Excel.

Nguồn: `overrides/leave_application/QUY_DINH_NGHI_PHEP_2025.md` mục 3 (phụ lục quy chế
TB-TIQN/2025-0018). Bảng dưới đây phải khớp mục 3 — sửa quy chế thì sửa cả hai chỗ.

Đặt ngoài thư mục `report/shift_attendance_customize/` **có chủ đích**: report đó đang chạy đúng
và được yêu cầu giữ nguyên, nên phần logic mới nằm ở đây, `standard_export.py` chỉ gọi vào.

## Phạm vi

CHỈ sheet Timesheet. Sheet Detail và Summary **giữ nguyên** cách tính `working_hours / 8`.

⚠ Hệ quả đã được chấp nhận: cột Total của Timesheet sẽ **khác** tổng của Summary. Ví dụ một
nhân viên nghỉ 3 ngày `P`: Timesheet +3 ngày công (đúng quy chế), Summary +0 (vì 0 giờ làm).

## Hai chỗ dễ hiểu sai

1. **`P/2` (phép năm nửa ngày) vẫn tính công TRỌN 1 NGÀY** — nửa còn lại đi làm nên đủ lương.
   Quy chế mục 3.1 ghi rõ, và đây là quy tắc bị code hiểu sai nhiều nhất.

2. **`KL` có hai nghĩa tuỳ số giờ làm.** Nghỉ không lương trọn ngày (0 giờ) thì mã là `KL`,
   công 0. Còn đi trễ / về sớm (mục 3.3, mã ghi là `<1`) cũng được ghi `KL` nhưng **có giờ làm**
   → hiển thị SỐ GIỜ, công = `giờ làm / 8`, không phải 0.
"""

from frappe.utils import flt

# Mục 3 — ngày công theo mã. Mã không có trong bảng thì rơi về `giờ làm / 8`.
LEAVE_WORKING_DAYS = {
	# 3.1 Phép năm · 3.2 Nghỉ hưởng lương -> hưởng nguyên ngày công
	"P": 1.0,
	"P/2": 1.0,
	"MC": 1.0,
	"HS": 1.0,
	"HL": 1.0,
	"HL/2": 1.0,
	# 3.3 Nghỉ không lương · 3.4 Nghỉ hưởng BHXH trọn ngày -> không hưởng công
	"KL": 0.0,
	"NB": 0.0,
	"TS": 0.0,
	"DS": 0.0,
	"O": 0.0,
	"CO": 0.0,
	# 3.5 Nửa ngày BHXH + nửa còn lại đi làm / phép năm
	"O/2": 0.5,
	"CO/2": 0.5,
	"OP/2": 0.5,
	"COP/2": 0.5,
	# 3.5 Nửa ngày BHXH + đi trễ/về sớm <= 1h
	"OL/2": 0.4,
	"COL/2": 0.4,
	# 3.5 Nửa ngày BHXH ghép với nhau / với không lương
	"OCO/2": 0.0,
	"OK/2": 0.0,
	"COK/2": 0.0,
}

STANDARD_DAY_HOURS = 8.0


def _hours_as_days(working_hours) -> float:
	return round(flt(working_hours) / STANDARD_DAY_HOURS, 2)


def is_late_or_early_kl(abbr: str, working_hours) -> bool:
	"""`KL` mà vẫn có giờ làm = đi trễ / về sớm (mục 3.3, mã `<1`), không phải nghỉ trọn ngày."""
	return abbr == "KL" and flt(working_hours) > 0


def timesheet_working_days(abbr: str, working_hours) -> float:
	"""Ngày công của một ngày trên sheet Timesheet."""
	abbr = (abbr or "").strip()

	if not abbr:
		return _hours_as_days(working_hours)

	if is_late_or_early_kl(abbr, working_hours):
		return _hours_as_days(working_hours)

	if abbr in LEAVE_WORKING_DAYS:
		return LEAVE_WORKING_DAYS[abbr]

	# Mã lạ (quy chế đổi mà bảng chưa cập nhật) -> không đoán, quay về cách tính theo giờ.
	return _hours_as_days(working_hours)


def timesheet_cell_display(abbr: str, working_hours):
	"""Giá trị hiển thị trong ô.

	Trả về **chuỗi** khi là ngày nghỉ (để in mã), **số** cho ngày làm bình thường, và `None`
	khi không có gì để hiển thị (ô trống, giữ đúng hành vi cũ).
	"""
	abbr = (abbr or "").strip()

	if abbr and not is_late_or_early_kl(abbr, working_hours):
		return abbr

	days = _hours_as_days(working_hours)
	return days if days > 0 else None
