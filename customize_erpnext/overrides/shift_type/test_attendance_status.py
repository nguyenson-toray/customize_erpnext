"""Test `resolve_attendance_status()` — ngưỡng vắng chỉ áp SAU KHI TAN CA.

Không ghi gì vào DB: chỉ gọi hàm thuần, giả lập thời điểm bằng
`frappe.flags.current_datetime`.

Chạy:
    cd /home/frappe/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect()
    exec(open('../apps/customize_erpnext/customize_erpnext/overrides/shift_type/test_attendance_status.py').read())"
"""
from datetime import date, datetime, timedelta

import frappe

from customize_erpnext.overrides.shift_type.shift_type_optimized import (
	is_shift_in_progress,
	resolve_attendance_status,
)

D = date(2026, 8, 11)          # thứ Ba, ngày làm việc bình thường
ok = fail = 0


def check(label, got, want):
	global ok, fail
	good = got == want
	ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
	print(f"  {'✅' if good else '❌'} {label:<52} {got!r}" + ("" if good else f"  ← cần {want!r}"))


def shift(start_h, end_h, absent=2.0, half=4.01):
	return {
		"start_time": timedelta(hours=start_h),
		"end_time": timedelta(hours=end_h),
		"working_hours_threshold_for_absent": absent,
		"working_hours_threshold_for_half_day": half,
	}


DAY = shift(8, 17)             # Day        08:00 → 17:00
SHIFT1 = shift(6, 14)          # Shift 1    06:00 → 14:00
SHIFT2 = shift(14, 22)         # Shift 2    14:00 → 22:00
CANTEEN = shift(6.5, 15.5)     # Canteen 6:30 → 15:30


def at(h, m=0):
	"""Giả lập 'bây giờ' là h:m ngày D."""
	frappe.flags.current_datetime = datetime(D.year, D.month, D.day, int(h), m)


def t(h, m=0, s=0):
	return datetime(D.year, D.month, D.day, h, m, s)


print("PHẦN 1 — is_shift_in_progress(): mỗi ca một giờ tan riêng")
at(16, 44)                      # đúng thời điểm đo được sự cố thật
check("16:44 · Day (tan 17:00)        → chưa tan", is_shift_in_progress(D, DAY), True)
check("16:44 · Shift 2 (tan 22:00)    → chưa tan", is_shift_in_progress(D, SHIFT2), True)
check("16:44 · Shift 1 (tan 14:00)    → đã tan", is_shift_in_progress(D, SHIFT1), False)
check("16:44 · Canteen (tan 15:30)    → đã tan", is_shift_in_progress(D, CANTEEN), False)
at(20, 0)
check("20:00 · Day                    → đã tan", is_shift_in_progress(D, DAY), False)
check("20:00 · Shift 2                → chưa tan", is_shift_in_progress(D, SHIFT2), True)
check("shift_data thiếu end_time      → coi như đã tan",
      is_shift_in_progress(D, {"start_time": timedelta(hours=8)}), False)

print("\nPHẦN 2 — 4 tổ hợp: (chưa tan / đã tan) × (có quẹt / không quẹt)")
at(16, 44)
check("chưa tan · có quẹt · 0 giờ     → Present",
      resolve_attendance_status(0, t(7, 46, 24), t(7, 46, 27), D, DAY), "Present")
check("chưa tan · KHÔNG quẹt          → Absent",
      resolve_attendance_status(0, None, None, D, DAY), "Absent")
at(20, 0)
check("đã tan  · có quẹt · 0 giờ      → Absent",
      resolve_attendance_status(0, t(7, 46, 24), t(7, 46, 27), D, DAY), "Absent")
check("đã tan  · KHÔNG quẹt           → Absent",
      resolve_attendance_status(0, None, None, D, DAY), "Absent")

print("\nPHẦN 3 — 🔴 ca chưa tan phải bỏ qua CẢ HAI ngưỡng")
at(16, 44)
check("0 giờ, ngưỡng absent 2,0 / half 4,01 → KHÔNG được ra Half Day",
      resolve_attendance_status(0, t(7, 46), t(7, 46, 3), D, DAY), "Present")
check("3 giờ (giữa hai ngưỡng)        → Present, không phải Half Day",
      resolve_attendance_status(3.0, t(8), t(11), D, DAY), "Present")
at(20, 0)
check("sau khi tan ca, 3 giờ          → Half Day (ngưỡng có hiệu lực trở lại)",
      resolve_attendance_status(3.0, t(8), t(11), D, DAY), "Half Day")
check("sau khi tan ca, 1 giờ          → Absent",
      resolve_attendance_status(1.0, t(8), t(9), D, DAY), "Absent")
check("sau khi tan ca, 8 giờ          → Present",
      resolve_attendance_status(8.0, t(8), t(17), D, DAY), "Present")

print("\nPHẦN 4 — quẹt đúp ở cửa (ca thật gây ra sự cố)")
at(16, 44)
for emp, h, m, sec in (("TIQN-0036", 7, 46, 3), ("TIQN-0056", 7, 29, 1), ("TIQN-0106", 7, 47, 7)):
	check(f"{emp} quẹt đúp cách {sec}s, ca Day chưa tan → Present",
	      resolve_attendance_status(0, t(h, m), t(h, m, sec), D, DAY), "Present")

print("\nPHẦN 4b — 🔴 quẹt VÀO mà KHÔNG có log RA (quên quẹt ra)")
at(20, 0)   # Day đã tan từ 17:00
check("đã tan ca · có IN · KHÔNG có OUT → Present (đã đến làm)",
      resolve_attendance_status(0, t(5, 54, 18), None, D, DAY), "Present")
at(16, 44)
check("TIQN-1210 · Shift 1 tan 14:00 · IN 05:54, không OUT → Present",
      resolve_attendance_status(0, t(5, 54, 18), None, D, SHIFT1), "Present")
check("có IN, không OUT, ca chưa tan   → Present",
      resolve_attendance_status(0, t(7, 46), None, D, DAY), "Present")
at(20, 0)
check("phân biệt: quẹt ĐÚP (có OUT) sau khi tan ca → Absent",
      resolve_attendance_status(0, t(7, 46), t(7, 46, 3), D, DAY), "Absent")

print("\nPHẦN 5 — NGÀY CŨ luôn tất định (không phụ thuộc giờ chạy)")
OLD = date(2026, 7, 15)
for hour in (0, 8, 16, 23):
	frappe.flags.current_datetime = datetime(2026, 8, 11, hour, 0)
	got = resolve_attendance_status(0, datetime(2026, 7, 15, 7, 46),
	                                datetime(2026, 7, 15, 7, 46, 3), OLD, DAY)
	check(f"ngày 15/07 tính lúc {hour:02d}:00 → Absent (không đổi)", got, "Absent")

frappe.flags.current_datetime = None
print(f"\n{'=' * 62}\nKẾT QUẢ: {ok} đạt / {fail} lỗi")
