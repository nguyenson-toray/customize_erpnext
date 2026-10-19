"""Ngày nghỉ của engine chấm công phải khớp Holiday List Assignment — chạy được trên HRMS cũ lẫn mới.

Chạy:
    bench --site erp.tiqn.local execute customize_erpnext.overrides.shift_type.test_holiday_resolution.run

Chỉ đọc, kết thúc bằng rollback. Đối chiếu `preload_reference_data()` với một cách tính độc lập
viết thẳng bằng SQL (assignment mới nhất có from_date <= ngày, của NV trước rồi của company), cho
mọi NV Active, qua các kỳ vắt năm. Kèm 3 ngày lễ từng bị chấm Absent hàng loạt.
"""

from datetime import timedelta

import frappe
from frappe.utils import getdate

PERIODS = [
	("2025-12-26", "2026-01-25"),  # vắt năm: list "2025" -> "2026"
	("2026-04-26", "2026-05-25"),  # 30/04, 01/05
	("2026-09-26", "2026-10-25"),
	("2026-11-26", "2027-01-25"),  # vắt năm: list "2026" -> "2027"
	("2020-12-01", "2021-01-31"),  # trước assignment đầu tiên
]
# Ngày lễ từng bị chấm Absent cho hàng trăm NV (xem comment mục 4 trong preload_reference_data)
KNOWN_HOLIDAYS = ["2026-01-01", "2026-04-30", "2026-05-01"]

ok = fail = 0


def check(label, cond, extra=""):
	global ok, fail
	if cond:
		ok += 1
		print(f"  PASS  {label}")
	else:
		fail += 1
		print(f"  FAIL  {label}  {extra}")


def expected_holidays(employee, company, start, end):
	"""Cách tính độc lập: mỗi ngày lấy assignment mới nhất (NV trước, company sau)."""
	rows = frappe.db.sql(
		"""select assigned_to, holiday_list, from_date from `tabHoliday List Assignment`
		where docstatus = 1 and assigned_to in %s order by from_date""",
		[(employee, company)],
		as_dict=True,
	)
	by_owner = {employee: [r for r in rows if r.assigned_to == employee],
				company: [r for r in rows if r.assigned_to == company]}
	holidays = {}
	for hl in {r.holiday_list for r in rows}:
		holidays[hl] = set(frappe.get_all("Holiday", filters={"parent": hl}, pluck="holiday_date"))

	result, day = set(), getdate(start)
	while day <= getdate(end):
		for owner in (employee, company):
			active = [r for r in by_owner[owner] if getdate(r.from_date) <= day]
			if active:
				if day in holidays[active[-1].holiday_list]:
					result.add(day)
				break
		else:  # trước assignment đầu tiên: dùng assignment sớm nhất
			first = (by_owner[employee] or by_owner[company] or [None])[0]
			if first and day in holidays[first.holiday_list]:
				result.add(day)
		day += timedelta(days=1)
	return result


def run():
	global ok, fail
	ok = fail = 0
	import hrms.hr.doctype.shift_type.shift_type as hrms_st

	import customize_erpnext.overrides as overrides
	from customize_erpnext.overrides.shift_type.shift_type_optimized import (
		is_holiday_cached,
		preload_reference_data,
	)

	print("\n=== 1. Override đã nạp ===")
	check("không module override nào lỗi", not overrides.failed, overrides.failed)
	check("ShiftType đã được patch", hasattr(hrms_st.ShiftType, "_original_process_auto_attendance"))

	employees = frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "company"])
	sample = employees[:: max(1, len(employees) // 25)]  # cách tính độc lập chậm, lấy mẫu ~25 NV

	for start, end in PERIODS:
		print(f"\n=== 2. Kỳ {start} → {end} ===")
		ref = preload_reference_data([e.name for e in employees], start, end)
		missing = [e.name for e in employees if e.name not in ref["employee_holidays"]]
		check("mọi NV Active có Holiday List", not missing, f"{len(missing)} thiếu: {missing[:5]}")
		diffs = []
		for e in sample:
			got = ref["employee_holidays"].get(e.name, set())
			exp = expected_holidays(e.name, e.company, start, end)
			if got != exp:
				diffs.append((e.name, sorted(got ^ exp)))
		check(f"khớp cách tính độc lập ({len(sample)} NV mẫu)", not diffs, diffs[:3])
		for d in KNOWN_HOLIDAYS:
			day = getdate(d)
			if getdate(start) <= day <= getdate(end):
				not_holiday = [e.name for e in employees if not is_holiday_cached(e.name, day, ref)]
				check(f"{d} là ngày nghỉ của mọi NV", not not_holiday, f"{len(not_holiday)} NV không")

	print(f"\n{'=' * 60}\nPASS {ok}   FAIL {fail}\n{'=' * 60}")
	frappe.db.rollback()
	return {"pass": ok, "fail": fail}
