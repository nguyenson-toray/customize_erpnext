"""Kiểm `bulk_update_employee_checkin(only_unlinked_days=True)` (P3 tối ưu job mỗi giờ).

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    import customize_erpnext.overrides
    exec(open('../apps/customize_erpnext/customize_erpnext/overrides/shift_type/test_bulk_update_checkin_unlinked_days.py').read())"

⚠ Test tạo checkin + Attendance riêng (ngày năm 2001, NV có sẵn) rồi `rollback()` — KHÔNG commit.
Ngày A: 3 checkin, log đầu đã link Attendance, 2 log sau chưa link, log_type cố tình sai
        -> phải nạp đủ cả ngày: log đầu = IN, log cuối = OUT.
Ngày B: mọi checkin đã link -> không được đụng (log_type sai giữ nguyên).
"""

import frappe

from customize_erpnext.overrides.employee_checkin.employee_checkin import bulk_update_employee_checkin

DAY_A = "2001-03-05"
DAY_B = "2001-03-06"
ok = fail = 0


def check(label, got, want=True):
	global ok, fail
	good = got == want
	ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
	print(f"  {'✅' if good else '❌'} {label:<58} {'' if good else f'{got!r} ← cần {want!r}'}")


def make_checkin(employee, ts, log_type, attendance=None):
	# INSERT thẳng, KHÔNG qua .insert(): tránh hook after_insert (update_employee_checkin,
	# telemetry HRMS gửi sự kiện ra ngoài) — test chỉ cần dữ liệu thô.
	name = f"TEST-CHK-{frappe.generate_hash(length=10)}"
	now = frappe.utils.now()
	frappe.db.sql("""
		INSERT INTO `tabEmployee Checkin`
			(name, employee, time, log_type, attendance, skip_auto_attendance, offshift,
			 docstatus, creation, modified, owner, modified_by)
		VALUES (%s, %s, %s, %s, %s, 0, 0, 0, %s, %s, 'Administrator', 'Administrator')
	""", (name, employee, ts, log_type, attendance, now, now))
	return name


# 🔴 bulk_update_employee_checkin() tự frappe.db.commit() sau mỗi lô — không chặn thì dữ liệu
# test bị GHI THẬT vào DB và rollback() cuối file vô tác dụng.
_real_commit = frappe.db.commit
frappe.db.commit = lambda *args, **kwargs: None

try:
	employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	assert employee, "no active employee"
	# 'attendance' là Link: dùng tên Attendance giả bằng cách bỏ qua kiểm link (db.set_value không validate)
	linked = "TEST-ATT-UNLINKED-DAYS"

	a1 = make_checkin(employee, f"{DAY_A} 08:00:00", "OUT", linked)
	a2 = make_checkin(employee, f"{DAY_A} 12:00:00", "OUT")
	a3 = make_checkin(employee, f"{DAY_A} 17:00:00", "IN")
	b1 = make_checkin(employee, f"{DAY_B} 08:00:00", "OUT", linked)
	b2 = make_checkin(employee, f"{DAY_B} 17:00:00", "IN", linked)

	bulk_update_employee_checkin(DAY_A, DAY_B, employees=[employee], only_unlinked_days=True)

	lt = lambda n: frappe.db.get_value("Employee Checkin", n, "log_type")
	print("Ngày A (còn checkin chưa link):")
	check("log đầu (đã link) = IN", lt(a1), "IN")
	check("log cuối = OUT", lt(a3), "OUT")
	print("Ngày B (mọi checkin đã link):")
	check("log đầu không bị đụng", lt(b1), "OUT")
	check("log cuối không bị đụng", lt(b2), "IN")

	print("Không có checkin chưa link trong khoảng:")
	check("trả 0", bulk_update_employee_checkin(DAY_B, DAY_B, employees=[employee], only_unlinked_days=True), 0)
finally:
	frappe.db.rollback()
	frappe.db.commit = _real_commit
	leaked = frappe.db.sql("SELECT COUNT(*) FROM `tabEmployee Checkin` WHERE name LIKE 'TEST-CHK-%%'")[0][0]
	print(f"\n{ok} ok, {fail} fail · checkin test còn sót trong DB: {leaked}")
