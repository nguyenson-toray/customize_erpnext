"""Kiểm chứng override `Shift Attendance` + mã nghỉ phép trên sheet Timesheet.

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    import customize_erpnext.overrides
    exec(open('../apps/customize_erpnext/customize_erpnext/overrides/shift_attendance/test_shift_attendance_override.py').read())"

⚠ Khoảng ngày mặc định là THÁNG 6/2026 vì tháng 8 chưa có mã nào — 183 đơn nghỉ tháng 8 còn ở
trạng thái draft nên chưa ghi abbreviation lên Attendance.
"""

import json

import frappe

from customize_erpnext.overrides.shift_attendance.timesheet_leave import (
	LEAVE_WORKING_DAYS,
	timesheet_cell_display,
	timesheet_working_days,
)

FROM_DATE = "2026-06-01"
TO_DATE = "2026-06-10"
ok = fail = 0


def check(label, got, want):
	global ok, fail
	good = got == want
	ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
	print(f"  {'✅' if good else '❌'} {label:<56} {got!r}" + ("" if good else f"  ← cần {want!r}"))


print("PHẦN 1 — bảng mục 3 quy chế: ngày công theo mã")
for abbr, want in [
	("P", 1.0), ("P/2", 1.0), ("MC", 1.0), ("HS", 1.0), ("HL", 1.0), ("HL/2", 1.0),
	("KL", 0.0), ("NB", 0.0), ("TS", 0.0), ("DS", 0.0), ("O", 0.0), ("CO", 0.0),
	("O/2", 0.5), ("CO/2", 0.5), ("OP/2", 0.5), ("COP/2", 0.5),
	("OL/2", 0.4), ("COL/2", 0.4),
	("OCO/2", 0.0), ("OK/2", 0.0), ("COK/2", 0.0),
]:
	check(f"{abbr} → {want} ngày công", timesheet_working_days(abbr, 0), want)

check("bảng phủ đủ 21 mã của mục 3", len(LEAVE_WORKING_DAYS), 21)

print("\nPHẦN 2 — 🔴 P/2 vẫn tính công TRỌN ngày (quy tắc hay bị hiểu sai nhất)")
check("P/2 với 4,28 giờ làm → 1 ngày", timesheet_working_days("P/2", 4.28), 1.0)
check("P/2 hiển thị là 'P/2'", timesheet_cell_display("P/2", 4.28), "P/2")

print("\nPHẦN 3 — 🔴 KL có hai nghĩa tuỳ số giờ làm")
check("KL 0 giờ = nghỉ trọn ngày → 0 công", timesheet_working_days("KL", 0), 0.0)
check("KL 0 giờ hiển thị 'KL'", timesheet_cell_display("KL", 0), "KL")
check("KL 6 giờ = đi trễ/về sớm → 0,75 công", timesheet_working_days("KL", 6), 0.75)
check("KL 6 giờ hiển thị SỐ, không phải chữ", timesheet_cell_display("KL", 6), 0.75)

print("\nPHẦN 4 — ngày không có mã: giữ nguyên hành vi cũ")
check("8 giờ → 1 ngày", timesheet_working_days("", 8), 1.0)
check("4 giờ → 0,5 ngày", timesheet_working_days("", 4), 0.5)
check("0 giờ → ô trống", timesheet_cell_display("", 0), None)
check("8 giờ → hiển thị số 1.0", timesheet_cell_display("", 8), 1.0)
check("mã lạ không đoán bừa, quay về giờ/8", timesheet_working_days("XYZ", 8), 1.0)

print("\nPHẦN 5 — hai report phải trả kết quả GIỐNG HỆT")
from frappe.desk.query_report import run

f = json.dumps({"from_date": FROM_DATE, "to_date": "2026-06-03"})
a = run("Shift Attendance", filters=f, ignore_prepared_report=True)
b = run("Shift Attendance Customize", filters=f, ignore_prepared_report=True)
check("số dòng bằng nhau", len(a["result"]), len(b["result"]))
check("columns giống hệt", a["columns"] == b["columns"], True)
check("data giống hệt", a["result"] == b["result"], True)
check("report_summary giống hệt", a.get("report_summary") == b.get("report_summary"), True)
check("có dữ liệu để phép so sánh có nghĩa", len(a["result"]) > 0, True)

print("\nPHẦN 6 — workbook Excel")
from customize_erpnext.customize_erpnext.report.shift_attendance_customize.standard_export import (
	build_standard_workbook,
)

wb = build_standard_workbook(FROM_DATE, TO_DATE)
check("đủ 6 sheet", wb.sheetnames,
      ["Important Note", "Detail", "Summary", "Timesheet", "Overtime", "Shift"])

ts = wb["Timesheet"]
EMP_FIXED = 8
n_dates = ts.max_column - EMP_FIXED - 1
total_col = EMP_FIXED + n_dates + 1

codes = {}
for row in ts.iter_rows(min_row=2, min_col=EMP_FIXED + 1, max_col=EMP_FIXED + n_dates):
	for c in row:
		if isinstance(c.value, str) and c.value:
			codes[c.value] = codes.get(c.value, 0) + 1
print(f"     mã in ra trên Timesheet: {dict(sorted(codes.items(), key=lambda x: -x[1]))}")
check("có in mã nghỉ phép", len(codes) > 0, True)
check("mọi mã in ra đều thuộc bảng quy chế", set(codes) - set(LEAVE_WORKING_DAYS), set())

# Total của mỗi dòng phải bằng tổng ngày công theo quy chế, không cộng chữ
bad_total = 0
for r in ts.iter_rows(min_row=2):
	days = 0.0
	for c in r[EMP_FIXED:EMP_FIXED + n_dates]:
		if isinstance(c.value, (int, float)):
			days += c.value
		elif isinstance(c.value, str) and c.value:
			days += LEAVE_WORKING_DAYS.get(c.value, 0.0)
	if abs(round(days, 2) - round(r[total_col - 1].value or 0, 2)) > 0.011:
		bad_total += 1
check("Total khớp tổng ngày công (không cộng chữ)", bad_total, 0)

print("\nPHẦN 7 — sheet khác KHÔNG được đổi")
ot = wb["Overtime"]
ot_text = sum(
	1 for row in ot.iter_rows(min_row=2, min_col=EMP_FIXED + 1)
	for c in row if isinstance(c.value, str) and c.value
)
check("Overtime không lẫn chữ nào", ot_text, 0)

# Detail: cột 12 Working(hour) · 13 Actual(hour) · 14 Working(day)
# ⚠ Cột `Actual (hour)` được CHÈN ở vị trí 13 (18/08/2026) nên mọi cột sau đó dịch phải 1.
det = wb["Detail"]
hdrs = [c.value for c in det[1]]
check("Detail có cột Actual (hour)", hdrs[12], "Actual (hour)")
check("   Working (hour) vẫn ở cột 12", hdrs[11], "Working (hour)")
check("   Working (day) dịch sang cột 14", hdrs[13], "Working (day)")

bad_detail = bad_actual = 0
for r in det.iter_rows(min_row=2):
	wh, actual, wd = r[11].value, r[12].value, r[13].value
	if wh is None or wd is None:
		continue
	if abs(round(wh / 8.0, 2) - wd) > 0.011:
		bad_detail += 1
	# Giờ thực tế không bao giờ NHỎ hơn giờ chốt lương
	if actual is not None and actual + 0.011 < wh:
		bad_actual += 1
check("Detail: Working(day) vẫn = Working(hour)/8", bad_detail, 0)
check("Detail: Actual(hour) >= Working(hour) ở mọi dòng", bad_actual, 0)

print(f"\n{'=' * 68}\nKẾT QUẢ: {ok} đạt / {fail} lỗi")
