"""Kiểm cờ `include_draft_leave_application` — engine chấm công có tính đơn nghỉ Draft không.

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    import customize_erpnext.overrides
    exec(open('../apps/customize_erpnext/customize_erpnext/overrides/shift_type/test_include_draft_leave.py').read())"

⚠ Test tự đổi giá trị cờ rồi `rollback()` — KHÔNG commit, giá trị thật của site không đổi.
"""

import frappe

from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
	get_attendance_settings,
	get_leave_docstatus_condition,
)
from customize_erpnext.overrides.leave_utils import find_other_half_day_leave_type
from customize_erpnext.overrides.shift_type import shift_type_optimized as E

FLAG = "include_draft_leave_application"
FROM_DATE = "2026-07-26"      # vùng chỉ có đơn Draft, không có đơn đã submit
TO_DATE = "2026-08-25"
ok = fail = 0


def check(label, got, want=True):
	global ok, fail
	good = got == want
	ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
	print(f"  {'✅' if good else '❌'} {label:<58} {'' if good else f'{got!r} ← cần {want!r}'}")


def set_flag(value):
	frappe.db.set_single_value("Attendance Calculation Setting", FLAG, value)
	frappe.clear_cache()


original = get_attendance_settings().get(FLAG)

try:
	print("PHẦN 1 — điều kiện SQL sinh ra")
	set_flag(0)
	check("cờ TẮT → chỉ đơn đã submit", get_leave_docstatus_condition(), "docstatus = 1")
	check("cờ TẮT + alias", get_leave_docstatus_condition("la"), "la.docstatus = 1")
	set_flag(1)
	check("cờ BẬT → tính cả draft", get_leave_docstatus_condition(), "docstatus IN (0, 1)")
	check("cờ BẬT + alias", get_leave_docstatus_condition("la"), "la.docstatus IN (0, 1)")

	print("\nPHẦN 2 — engine preload dữ liệu nghỉ phép")
	# ⚠ Phải dùng ĐÚNG truy vấn của luồng thật (shift_type_optimized.py:1654), không phải
	# `status = Active`. Luồng thật cố ý gồm cả nhân viên đã `Left` còn hạn trong kỳ — nếu test
	# chỉ truyền Active thì sẽ đo thiếu và tưởng đơn của họ bị bỏ.
	emps = frappe.db.sql("""
		SELECT name FROM `tabEmployee` e
		WHERE (date_of_joining IS NULL OR date_of_joining <= %(to_date)s)
		  AND (status = 'Active'
		       OR (status = 'Left' AND (relieving_date IS NULL OR relieving_date >= %(from_date)s))
		       OR (status = 'Left' AND EXISTS (SELECT 1 FROM `tabEmployee Checkin` c
		             WHERE c.employee = e.name AND c.time >= %(from_date)s
		               AND c.time < DATE_ADD(%(to_date)s, INTERVAL 1 DAY))))
		  AND employee LIKE %(prefix)s
	""", {"from_date": FROM_DATE, "to_date": TO_DATE, "prefix": "TIQN%"}, pluck=True)
	n_sub = frappe.db.count("Leave Application", {
		"docstatus": 1, "status": "Approved",
		"from_date": ["<=", TO_DATE], "to_date": [">=", FROM_DATE]})
	n_draft = frappe.db.count("Leave Application", {
		"docstatus": 0, "status": "Approved",
		"from_date": ["<=", TO_DATE], "to_date": [">=", FROM_DATE]})
	print(f"     kỳ {FROM_DATE} → {TO_DATE}: {n_sub} đơn submitted · {n_draft} đơn draft")
	check("kỳ test phải có đơn draft (nếu không phép so vô nghĩa)", n_draft > 0)

	def loaded(flag):
		set_flag(flag)
		d = E.preload_reference_data(emps, FROM_DATE, TO_DATE)
		la = d.get("leave_applications", {})
		return len(la), len({x["leave_application"] for v in la.values() for x in v})

	off_days, off_apps = loaded(0)
	on_days, on_apps = loaded(1)
	print(f"     cờ TẮT: {off_apps} đơn / {off_days} ngày  ·  cờ BẬT: {on_apps} đơn / {on_days} ngày")
	check("cờ TẮT không nhặt đơn draft nào", off_apps, n_sub)
	check("cờ BẬT nhặt thêm đơn", on_apps > off_apps)
	check("cờ BẬT sinh thêm ngày nghỉ", on_days > off_days)

	# Nhân viên đã `Left` nhưng nghỉ việc TRONG/SAU kỳ vẫn phải được tính — đơn của họ cho
	# những ngày còn đi làm là công thật, ảnh hưởng lương tháng cuối.
	n_left_draft = frappe.db.sql("""
		SELECT COUNT(*) FROM `tabLeave Application` la
		JOIN tabEmployee e ON e.name = la.employee
		WHERE la.docstatus = 0 AND la.status = 'Approved'
		  AND la.from_date <= %s AND la.to_date >= %s AND e.status = 'Left'
	""", (TO_DATE, FROM_DATE))[0][0]
	print(f"     trong đó {n_left_draft} đơn thuộc NV đã nghỉ việc")
	check("đơn của NV đã nghỉ việc CŨNG được tính", on_apps, n_sub + n_draft)

	print("\nPHẦN 2b — nhưng ngày SAU relieving_date thì KHÔNG sinh chấm công")
	# Engine chặn hai lớp: should_mark_attendance() trả False khi relieving_date <= ngày,
	# và bước dọn cuối xoá attendance từ relieving_date trở đi nếu không có checkin.
	late = frappe.db.sql("""
		SELECT la.employee, la.from_date, e.relieving_date
		FROM `tabLeave Application` la JOIN tabEmployee e ON e.name = la.employee
		WHERE la.docstatus = 0 AND e.status = 'Left' AND e.relieving_date IS NOT NULL
		  AND la.from_date > e.relieving_date LIMIT 1
	""", as_dict=True)
	if late:
		l = late[0]
		n_att = frappe.db.count("Attendance", {
			"employee": l.employee, "attendance_date": [">=", l.relieving_date]})
		print(f"     {l.employee}: nghỉ việc {l.relieving_date}, đơn {l.from_date}")
		check("không có chấm công từ ngày nghỉ việc trở đi", n_att, 0)
	else:
		print("     (không có đơn nào sau ngày nghỉ việc — bỏ qua)")

	print("\nPHẦN 3 — tra nửa ngày còn lại phải theo CÙNG cờ")
	# Nếu hai đường lệch nhau, cặp (đơn submit + đơn draft) cùng ngày sẽ giải sai half_day_status
	row = frappe.db.sql("""
		SELECT employee, half_day_date, name, leave_type FROM `tabLeave Application`
		WHERE docstatus = 0 AND half_day = 1 AND status = 'Approved' AND half_day_date IS NOT NULL
		LIMIT 1
	""", as_dict=True)
	if row:
		r = row[0]
		set_flag(0)
		off = find_other_half_day_leave_type(r.employee, r.half_day_date, None)
		set_flag(1)
		on = find_other_half_day_leave_type(r.employee, r.half_day_date, None)
		print(f"     mẫu {r.employee} {r.half_day_date}: TẮT→{off!r} · BẬT→{on!r}")
		check("cờ BẬT thấy được đơn draft nửa ngày", on is not None)
		check("cờ TẮT không thấy nó", off, None)
	else:
		print("     (không có đơn draft nửa ngày trong DB — bỏ qua)")

	print("\nPHẦN 4 — mặc định phải là TẮT (không đổi hành vi khi chưa ai bật)")
	meta_default = frappe.get_meta("Attendance Calculation Setting").get_field(FLAG).default
	check("default của field = '0'", meta_default, "0")

finally:
	frappe.db.rollback()
	frappe.clear_cache()
	print(f"\n     đã rollback, cờ về giá trị ban đầu: {get_attendance_settings().get(FLAG)!r}")

print(f"\n{'=' * 68}\nKẾT QUẢ: {ok} đạt / {fail} lỗi")
