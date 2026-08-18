# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Chặn `working_hours` theo đơn nghỉ phép, và phát hiện "xin nghỉ nhưng vẫn đi làm".

## Quy tắc (do TIQN chốt 18/08/2026)

| Loại đơn | `working_hours` |
|---|---|
| `KL` (nghỉ không lương) | **giữ nguyên** giờ thực tế — logic hiện tại theo in/out |
| Đơn TRỌN ngày (≠ KL) | **0** |
| Đơn NỬA ngày | **min(giờ thực tế, 4)** |
| Không có đơn | giữ nguyên |

## Ba field, đừng nhầm

| Field | Nghĩa |
|---|---|
| `standard_working_hours` | độ dài danh nghĩa của **ca** (8,0 ở mọi bản ghi). KHÔNG đụng |
| `custom_actual_working_hours` | giờ **thực tế** theo check in/out — không bao giờ bị chặn |
| `working_hours` | **cơ sở chốt lương** — bị chặn theo bảng trên |

Vì sao phải tách chứ không chặn thẳng `working_hours`:

1. Chặn thẳng là **xoá mất bằng chứng** — không còn cách nào biết người đó thực tế làm 8 giờ,
   mà đó chính là thứ HR cần để quyết định huỷ đơn.
2. Phát hiện bất thường thành **điều kiện lọc được** (`actual > working_hours`), không phụ thuộc
   vào việc dò chuỗi trong note.
3. **Idempotent**: chạy lại bulk update bao nhiêu lần cũng ra cùng kết quả. Chặn tại chỗ thì lần
   chạy sau đọc giá trị đã chặn rồi chặn tiếp.

## 🔴 KHÔNG được đụng tới tăng ca

638 bản ghi vừa có nghỉ nửa ngày vừa có tăng ca, tổng **1.320,8 giờ OT final**. Hàm này chỉ sửa
`working_hours`, **không** sửa `in_time` / `out_time` / các field OT. Cắt `out_time` để chặn giờ
sẽ xoá sạch số OT đó.

(Ngày Chủ Nhật engine đặt `actual_overtime = working_hours`. Hiện **0 ngày nghỉ nào rơi vào Chủ
Nhật** nên hai nhánh không giao nhau — nếu sau này có, phải kiểm lại chỗ đó.)
"""

from frappe.utils import flt

# Nghỉ không lương: quy tắc nói rõ vẫn tính giờ theo in/out như hiện tại.
UNCAPPED_ABBR = {"KL"}

HALF_DAY_CAP = 4.0

# Ngưỡng để coi là "xin nghỉ nhưng vẫn đi làm" — đủ mạnh để nhắc HR xem lại đơn.
SUSPICIOUS_HALF_DAY_HOURS = 7.0    # đơn nửa ngày mà làm gần trọn ngày
SUSPICIOUS_FULL_DAY_HOURS = 4.0    # đơn trọn ngày mà làm quá nửa ngày


def cap_working_hours(actual_hours, abbreviation, is_half_day: bool, has_leave: bool) -> float:
	"""Giờ dùng để chốt lương.

	`has_leave` tách riêng khỏi `abbreviation` vì có bản ghi gắn đơn nghỉ mà abbreviation rỗng
	(đơn draft chưa được engine gắn mã ở lần chạy trước).
	"""
	actual = flt(actual_hours)

	if not has_leave:
		return actual

	if (abbreviation or "").strip() in UNCAPPED_ABBR:
		return actual

	if is_half_day:
		return min(actual, HALF_DAY_CAP)

	return 0.0


def leave_hour_note(actual_hours, capped_hours, abbreviation, is_half_day: bool) -> str | None:
	"""Note cho `custom_note` khi giờ thực tế vượt giờ được tính. `None` nếu bình thường."""
	actual = flt(actual_hours)
	capped = flt(capped_hours)

	if actual <= capped:
		return None

	abbr = (abbreviation or "").strip() or "?"
	kind = "Half-day leave" if is_half_day else "Full-day leave"
	note = f"{kind} ({abbr}) but worked {actual:.2f}h"

	if not is_half_day:
		note += " - hours not counted"
	else:
		note += f" - capped to {capped:.2f}h"

	threshold = SUSPICIOUS_HALF_DAY_HOURS if is_half_day else SUSPICIOUS_FULL_DAY_HOURS
	if actual >= threshold:
		note += " - check if LA should be cancelled"

	return note


def is_suspicious(actual_hours, abbreviation, is_half_day: bool, has_leave: bool) -> bool:
	"""Có đáng đưa vào sheet Important Note để HR xem huỷ đơn không."""
	if not has_leave or (abbreviation or "").strip() in UNCAPPED_ABBR:
		return False
	threshold = SUSPICIOUS_HALF_DAY_HOURS if is_half_day else SUSPICIOUS_FULL_DAY_HOURS
	return flt(actual_hours) >= threshold


def should_suppress_late_early(abbreviation, has_leave: bool) -> bool:
	"""Có đơn nghỉ đã duyệt thì KHÔNG đánh đi trễ / về sớm.

	Nghỉ nửa ngày phép năm buổi sáng rồi vào lúc 12:03 **không phải đi trễ** — đó là nghỉ đã được
	duyệt. Engine chỉ so `in_time` với giờ vào ca nên không biết điều đó.

	Hậu quả nếu không sửa: quy chế mục 3.3 trừ **100.000đ mỗi lần** đi trễ/về sớm vào thưởng
	chuyên cần. Đo 18/08/2026: **918 bản ghi** nghỉ nửa ngày bị gắn `late_entry` và **737** bị gắn
	`early_exit` — tiền thật.

	`KL` là ngoại lệ, cùng lý do với `cap_working_hours()`: quy chế coi đi trễ/về sớm chính là một
	dạng nghỉ không lương (mục 3.3, mã `<1`), nên ở đó cờ trễ/sớm vẫn có nghĩa.

	⚠ Leave Application **không có** field cho biết nghỉ nửa nào (sáng hay chiều) —
	`custom_half_day_period` không tồn tại. Nên không thể chỉ bỏ đúng một cờ; bỏ cả hai là lựa
	chọn an toàn hơn: gắn nhầm thì mất tiền của người lao động, bỏ sót thì chỉ mất một khoản trừ.
	Nếu sau này có field ghi rõ nửa nào, siết lại ở đây.
	"""
	if not has_leave:
		return False
	return (abbreviation or "").strip() not in UNCAPPED_ABBR


def apply_to_attendance(att_data: dict) -> None:
	"""Áp quy tắc lên một dict chấm công, **sửa tại chỗ**.

	Đặt `custom_actual_working_hours` = giờ engine vừa tính, rồi chặn `working_hours`. Ghi thêm
	một dòng vào `custom_note` khi có bất thường.

	⚠ Phải gọi **trước** `_check_attendance_changes()`: nếu gọi sau, bản ghi bị coi là "không
	đổi" nên cap không bao giờ được ghi xuống DB.

	Nhận diện nửa ngày bằng `status == 'Half Day'`. Nghỉ TRỌN ngày mà có checkin thì engine đặt
	status = 'Present' — vẫn đúng là trọn ngày nên `is_half_day = False`, cap về 0.
	Hai đơn nửa ngày cùng ngày (dual leave) phủ kín cả ngày ⇒ cap về 0, không phải 4.
	"""
	actual = flt(att_data.get("working_hours"), 2)
	att_data["custom_actual_working_hours"] = actual

	has_leave = bool(att_data.get("leave_type") or att_data.get("leave_application"))
	if not has_leave:
		return

	abbr = att_data.get("custom_leave_application_abbreviation")
	is_dual = bool(att_data.get("custom_leave_type_2") or att_data.get("custom_leave_application_2"))
	is_half_day = att_data.get("status") == "Half Day" and not is_dual

	capped = cap_working_hours(actual, abbr, is_half_day, has_leave)
	att_data["working_hours"] = flt(capped, 2)

	# Nghỉ đã duyệt thì vào muộn / về sớm là đương nhiên, không phải vi phạm.
	if should_suppress_late_early(abbr, has_leave):
		att_data["late_entry"] = 0
		att_data["early_exit"] = 0

	note = leave_hour_note(actual, capped, abbr, is_half_day)
	if note:
		existing = (att_data.get("custom_note") or "").strip()
		att_data["custom_note"] = f"{existing}; {note}" if existing else note
