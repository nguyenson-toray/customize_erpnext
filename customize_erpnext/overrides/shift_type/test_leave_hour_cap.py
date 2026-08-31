"""Kiểm quy tắc chặn `working_hours` theo đơn nghỉ phép.

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    import customize_erpnext.overrides
    exec(open('../apps/customize_erpnext/customize_erpnext/overrides/shift_type/test_leave_hour_cap.py').read())"

⚠ Phần 5 GHI vào DB (chạy lại chấm công cho 1 nhân viên 1 ngày) — engine tự commit nên không
rollback được. Nó chỉ tính lại đúng bản ghi mẫu, ra cùng kết quả mọi lần (idempotent).
"""

import frappe

from customize_erpnext.overrides.shift_type.leave_hour_cap import (
	HALF_DAY_CAP,
	should_suppress_late_early,
	apply_to_attendance,
	cap_working_hours,
	is_suspicious,
	leave_hour_note,
)

# Tra theo (nhân viên, ngày) chứ KHÔNG neo tên bản ghi: mọi đợt reset dữ liệu chấm công đều
# xoá rồi tạo lại Attendance với tên hash mới, neo cứng là test chết câm ở PHẦN 5.
SAMPLE_EMP, SAMPLE_DATE = "TIQN-0940", "2026-06-15"   # P/2 · làm 8h · OT final 3.0
SAMPLE_ATT = frappe.db.get_value(
	"Attendance", {"employee": SAMPLE_EMP, "attendance_date": SAMPLE_DATE, "docstatus": 1}, "name")
if not SAMPLE_ATT:
	frappe.throw(f"Không tìm thấy Attendance mẫu của {SAMPLE_EMP} ngày {SAMPLE_DATE}")
ok = fail = 0


def check(label, got, want=True):
	global ok, fail
	good = got == want
	ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
	print(f"  {'✅' if good else '❌'} {label:<58} {'' if good else f'{got!r} ← cần {want!r}'}")


print("PHẦN 1 — bảng quy tắc")
check("không có đơn → giữ nguyên", cap_working_hours(7.5, None, False, False), 7.5)
check("KL trọn ngày → giữ nguyên (theo in/out)", cap_working_hours(6.0, "KL", False, True), 6.0)
check("KL nửa ngày → giữ nguyên", cap_working_hours(6.0, "KL", True, True), 6.0)
check("đơn TRỌN ngày P → 0", cap_working_hours(3.82, "P", False, True), 0.0)
check("đơn TRỌN ngày O → 0", cap_working_hours(3.68, "O", False, True), 0.0)
check("đơn TRỌN ngày TS → 0", cap_working_hours(1.73, "TS", False, True), 0.0)
check("đơn NỬA ngày P/2 làm 8h → 4", cap_working_hours(8.0, "P/2", True, True), HALF_DAY_CAP)
check("đơn NỬA ngày P/2 làm 5.13h → 4", cap_working_hours(5.13, "P/2", True, True), HALF_DAY_CAP)
check("đơn NỬA ngày làm 3h → giữ 3 (min)", cap_working_hours(3.0, "P/2", True, True), 3.0)
check("đơn NỬA ngày O/2 làm 5.98h → 4", cap_working_hours(5.98, "O/2", True, True), HALF_DAY_CAP)

print("\nPHẦN 2 — note")
check("không vượt → không note", leave_hour_note(3.0, 3.0, "P/2", True), None)
check("nửa ngày làm 8h → có cảnh báo huỷ đơn",
      "check if LA should be cancelled" in leave_hour_note(8.0, 4.0, "P/2", True), True)
check("nửa ngày làm 5h → KHÔNG cảnh báo huỷ đơn",
      "check if LA should be cancelled" in leave_hour_note(5.0, 4.0, "P/2", True), False)
check("trọn ngày làm 3.8h → không tính giờ",
      "hours not counted" in leave_hour_note(3.82, 0.0, "P", False), True)
check("trọn ngày làm 3.8h → CÓ cảnh báo (>=4h? không)",
      "check if LA should be cancelled" in leave_hour_note(3.82, 0.0, "P", False), False)
check("trọn ngày làm 5h → CÓ cảnh báo",
      "check if LA should be cancelled" in leave_hour_note(5.0, 0.0, "P", False), True)

print("\nPHẦN 3 — đưa vào Important Note: HỄ BỊ CHẶN GIỜ LÀ BÁO, không dùng ngưỡng")
# Ngưỡng cũ (nửa ngày >=7h) giấu mất 298/312 ca. Ví dụ thật `attendance/0ad5308fc1`:
# nghỉ P/2 làm 6,33h — đã bị chặn, đã có custom_note, nhưng KHÔNG lên Important Note.
check("P/2 làm 8h → có", is_suspicious(8.0, "P/2", True, True), True)
check("P/2 làm 6.33h → CÓ (ngưỡng cũ bỏ sót)", is_suspicious(6.33, "P/2", True, True), True)
check("P/2 làm 5h → CÓ", is_suspicious(5.0, "P/2", True, True), True)
check("P/2 làm 4.01h → CÓ (lọc nhiễu là việc của ngưỡng phút)",
      is_suspicious(4.01, "P/2", True, True), True)
check("P/2 làm ĐÚNG 4h → không, vì không bị chặn", is_suspicious(4.0, "P/2", True, True), False)
check("P/2 làm 3h → không", is_suspicious(3.0, "P/2", True, True), False)
check("P làm 0.04h → CÓ (trọn ngày, cap 0)", is_suspicious(0.04, "P", False, True), True)
check("P làm 0h → không", is_suspicious(0.0, "P", False, True), False)
check("KL làm 8h → KHÔNG (quy tắc miễn KL)", is_suspicious(8.0, "KL", False, True), False)
check("không có đơn → không", is_suspicious(8.0, None, False, False), False)

# Ngưỡng vẫn dùng, nhưng chỉ để NÂNG câu chữ trong note
check("6.33h chưa tới ngưỡng → note KHÔNG nhắc huỷ đơn",
      "check if LA should be cancelled" in leave_hour_note(6.33, 4.0, "P/2", True), False)
check("8h vượt ngưỡng → note CÓ nhắc huỷ đơn",
      "check if LA should be cancelled" in leave_hour_note(8.0, 4.0, "P/2", True), True)

print("\nPHẦN 3b — nghỉ đã duyệt thì KHÔNG đánh đi trễ / về sớm")
# Quy chế mục 3.3 trừ 100.000đ mỗi lần trễ/sớm → gắn nhầm là mất tiền thật của NLĐ.
check("nghỉ nửa ngày P/2 → bỏ cờ", should_suppress_late_early("P/2", True), True)
check("nghỉ trọn ngày P → bỏ cờ", should_suppress_late_early("P", True), True)
check("O/2 → bỏ cờ", should_suppress_late_early("O/2", True), True)
check("KL → GIỮ cờ (trễ/sớm chính là KL, mục 3.3)", should_suppress_late_early("KL", True), False)
check("không có đơn → giữ cờ", should_suppress_late_early(None, False), False)

d7 = {"working_hours": 4.0, "status": "Half Day", "leave_type": "Phép năm/ Annual leave",
      "custom_leave_application_abbreviation": "P/2", "late_entry": 1, "early_exit": 1,
      "custom_note": None}
apply_to_attendance(d7)
check("apply(): late_entry bị bỏ", d7["late_entry"], 0)
check("apply(): early_exit bị bỏ", d7["early_exit"], 0)

d8 = {"working_hours": 6.0, "status": "On Leave", "leave_type": "KL",
      "custom_leave_application_abbreviation": "KL", "late_entry": 1, "early_exit": 0,
      "custom_note": None}
apply_to_attendance(d8)
check("apply(): KL giữ nguyên late_entry", d8["late_entry"], 1)

d9 = {"working_hours": 8.0, "status": "Present", "late_entry": 1, "custom_note": None}
apply_to_attendance(d9)
check("apply(): ngày thường không đơn → giữ late_entry", d9["late_entry"], 1)

print("\nPHẦN 4 — apply_to_attendance() sửa dict tại chỗ")
d = {"working_hours": 8.0, "status": "Half Day", "leave_type": "Phép năm/ Annual leave",
     "custom_leave_application_abbreviation": "P/2", "custom_note": None}
apply_to_attendance(d)
check("actual giữ 8.0", d["custom_actual_working_hours"], 8.0)
check("working_hours chặn còn 4.0", d["working_hours"], 4.0)
check("có note", bool(d["custom_note"]), True)

d2 = {"working_hours": 3.82, "status": "Present", "leave_type": "Phép năm/ Annual leave",
      "custom_leave_application_abbreviation": "P", "custom_note": None}
apply_to_attendance(d2)
check("nghỉ TRỌN ngày + có checkin (status Present) → 0", d2["working_hours"], 0.0)
check("   actual vẫn giữ 3.82", d2["custom_actual_working_hours"], 3.82)

d3 = {"working_hours": 8.0, "status": "Present", "custom_note": None}
apply_to_attendance(d3)
check("ngày thường không đơn → không đụng", d3["working_hours"], 8.0)

d4 = {"working_hours": 6.0, "status": "Half Day", "leave_type": "X",
      "custom_leave_type_2": "Y", "custom_leave_application_abbreviation": "OP/2",
      "custom_note": None}
apply_to_attendance(d4)
check("dual leave phủ kín ngày → 0, không phải 4", d4["working_hours"], 0.0)

d5 = {"working_hours": 6.0, "status": "On Leave", "leave_type": "Nghỉ không lương/ Unpaid leave",
      "custom_leave_application_abbreviation": "KL", "custom_note": None}
apply_to_attendance(d5)
check("KL giữ nguyên giờ", d5["working_hours"], 6.0)
check("   KL không sinh note", d5["custom_note"], None)

d6 = {"working_hours": 8.0, "status": "Half Day", "leave_type": "P",
      "custom_leave_application_abbreviation": "P/2", "custom_note": "Only one check-in record"}
apply_to_attendance(d6)
check("note cũ được giữ, note mới nối thêm",
      d6["custom_note"].startswith("Only one check-in record; "), True)

print("\nPHẦN 5 — bản ghi thật + OT phải BẤT BIẾN")
import json

from customize_erpnext.overrides.shift_type import shift_type_optimized as E

F = ["employee", "attendance_date", "working_hours", "custom_actual_working_hours",
     "actual_overtime_duration", "custom_final_overtime_duration", "in_time", "out_time",
     "custom_note", "custom_leave_application_abbreviation"]
before = frappe.db.get_value("Attendance", SAMPLE_ATT, F, as_dict=1)
import contextlib
import io as _io

with contextlib.redirect_stdout(_io.StringIO()):
	E.bulk_update_attendance_optimized(
		str(before.attendance_date), str(before.attendance_date),
		employees=json.dumps([before.employee]), force_sync=1)
	frappe.db.commit()
after = frappe.db.get_value("Attendance", SAMPLE_ATT, F, as_dict=1)

print(f"     {before.employee} {before.attendance_date} · {before.custom_leave_application_abbreviation}")
check("working_hours = 4.0", after.working_hours, 4.0)
check("custom_actual_working_hours = 8.0", after.custom_actual_working_hours, 8.0)
check("🔴 OT actual KHÔNG đổi", after.actual_overtime_duration, before.actual_overtime_duration)
check("🔴 OT final KHÔNG đổi", after.custom_final_overtime_duration, before.custom_final_overtime_duration)
check("🔴 in_time KHÔNG đổi", after.in_time, before.in_time)
check("🔴 out_time KHÔNG đổi", after.out_time, before.out_time)
check("note có cảnh báo huỷ đơn",
      "check if LA should be cancelled" in (after.custom_note or ""), True)

# Bản ghi thật thứ hai: nghỉ nửa ngày buổi sáng, vào 12:03 → KHÔNG được là đi trễ
LATE_EMP, LATE_DATE = "TIQN-2220", "2026-07-17"   # P/2 · vào 12:03, ca Day 08:00
LATE_SAMPLE = frappe.db.get_value(
	"Attendance", {"employee": LATE_EMP, "attendance_date": LATE_DATE, "docstatus": 1}, "name")
if not LATE_SAMPLE:
	frappe.throw(f"Không tìm thấy Attendance mẫu của {LATE_EMP} ngày {LATE_DATE}")
ls = frappe.db.get_value("Attendance", LATE_SAMPLE,
                         ["late_entry", "early_exit", "custom_leave_application_abbreviation"],
                         as_dict=1)
check(f"{LATE_SAMPLE}: nghỉ P/2 vào 12:03 KHÔNG bị đánh late_entry", ls.late_entry, 0)
check(f"{LATE_SAMPLE}: cũng không bị early_exit", ls.early_exit, 0)

# idempotent: chạy lần nữa, note không nhân đôi
with contextlib.redirect_stdout(_io.StringIO()):
	E.bulk_update_attendance_optimized(
		str(before.attendance_date), str(before.attendance_date),
		employees=json.dumps([before.employee]), force_sync=1)
	frappe.db.commit()
again = frappe.db.get_value("Attendance", SAMPLE_ATT, F, as_dict=1)
check("idempotent: note không nhân đôi", again.custom_note, after.custom_note)
check("idempotent: working_hours không tụt tiếp", again.working_hours, 4.0)
check("idempotent: actual không bị ghi đè bằng giá trị đã chặn",
      again.custom_actual_working_hours, 8.0)

print("\nPHẦN 6 — note phải HIỆN RA trong Excel (cả 2 chỗ)")
# ⚠ `_build_notes()` chỉ dịch những chuỗi ĐÃ KHAI; note nào không khai sẽ biến mất khỏi cột
# Note Checkin mà không báo lỗi. Đây chính là bug đã gặp 18/08/2026.
from customize_erpnext.customize_erpnext.report.shift_attendance_customize.standard_export import (
	build_standard_workbook,
)

d = str(before.attendance_date)
wb = build_standard_workbook(d, d)

det = wb["Detail"]
note_cell = None
for r in det.iter_rows(min_row=2):
	if r[2].value == before.employee:
		note_cell = r[17].value or ""
		check("Detail: Working(hour) = 4.0", r[11].value, 4.0)
		check("Detail: Actual(hour) = 8.0", r[12].value, 8.0)
		break
check("Detail: cột Note Checkin có cảnh báo chặn giờ",
      "chặn còn 4h" in (note_cell or ""), True)
check("Detail: cột Note Checkin có nhắc huỷ đơn",
      "XEM HUỶ ĐƠN NGHỈ" in (note_cell or ""), True)

found = False
for row in wb["Important Note"].iter_rows(min_row=1):
	for c in row:
		if c.value and "Nghỉ phép + đi làm" in str(c.value):
			found = True
check("Important Note: có nhóm [Nghỉ phép + đi làm]", found, True)

# 4 cột phụ để HR tra thẳng bản ghi thay vì đọc chuỗi trong cột Detail
note_ws = wb["Important Note"]
# ⚠ Excel Table neo ref từ A1 nên tiêu đề ở DÒNG 1, dữ liệu từ dòng 2 (trước đây header ở dòng 3)
check("Important Note đủ 8 cột, tiêu đề ở dòng 1", [c.value for c in note_ws[1]],
      ["Type", "Info", "Working Hour", "Working Hour Actual",
       "Leave Application Abbreviation", "Attendance", "Leave Application", "Note"])
check("là Excel Table như các sheet khác",
      [t.displayName for t in note_ws.tables.values()], ["TableImportantNote"])
import re as _re
_keys = []
for _r in note_ws.iter_rows(min_row=2):
	_m = _re.match(r"(\d{2})/(\d{2})/(\d{4}) · (\S+)", str(_r[1].value or ""))
	if _m:
		_keys.append((_r[0].value, f"{_m.group(3)}-{_m.group(2)}-{_m.group(1)}", _m.group(4)))
check("sắp xếp Type → Date → Employee tăng dần", _keys, sorted(_keys))
check("   Info có ngày, mã NV và giờ vào-ra",
      bool(_re.match(r"\d{2}/\d{2}/\d{4} · \S+ .* · \d{2}:\d{2}–", str(note_ws.cell(row=2, column=2).value or ""))), True)
nrow = [r for r in note_ws.iter_rows(min_row=2) if r[0].value == "[Nghỉ phép + đi làm]"]
if nrow:
	r0 = nrow[0]
	check("   Working Hour là SỐ", isinstance(r0[2].value, (int, float)), True)
	check("   Working Hour Actual > Working Hour", r0[3].value > r0[2].value, True)
	check("   có mã nghỉ phép (abbr)", bool(r0[4].value), True)
	check("   có tên bản ghi Attendance", bool(r0[5].value), True)
	check("   có mã đơn nghỉ", bool(r0[6].value), True)

print("\nPHẦN 7 — report: bug ô Check bỏ tick")
from frappe.desk.query_report import run

RF = {"from_date": d, "to_date": d}
off = run("Shift Attendance", filters=json.dumps(RF), ignore_prepared_report=True)

# Giờ thực tế CHỈ hiện trong Excel (cột `Actual (hour)` sheet Detail + sheet Important Note),
# KHÔNG thêm cột vào report — user chốt 18/08/2026, note trong Excel là đủ.
check("report KHÔNG có cột Actual Working Hours",
      "custom_actual_working_hours" in [c["fieldname"] for c in off["columns"]], False)
row = [r for r in off["result"] if r["employee"] == before.employee]
check("Working Hours trên report đã bị chặn", row[0]["working_hours"] if row else None, 4.0)

# 🔴 Bug CÓ SẴN đã sửa: vòng lặp filter chỉ xét KEY nên ô Check bỏ tick vẫn lọc.
# Không liên quan tính năng chặn giờ — giữ lại bản vá kể cả khi bỏ ô Check "Leave but worked".
le0 = run("Shift Attendance", filters=json.dumps({**RF, "late_entry": 0}), ignore_prepared_report=True)
le1 = run("Shift Attendance", filters=json.dumps({**RF, "late_entry": 1}), ignore_prepared_report=True)
ee0 = run("Shift Attendance", filters=json.dumps({**RF, "early_exit": 0}), ignore_prepared_report=True)
check("late_entry=0 KHÔNG lọc (bug cũ: lọc y như =1)", len(le0["result"]), len(off["result"]))
check("early_exit=0 KHÔNG lọc", len(ee0["result"]), len(off["result"]))
check("late_entry=1 vẫn lọc bình thường", len(le1["result"]) < len(off["result"]), True)

print("\nPHẦN 8 — option của dialog Export Excel")
from customize_erpnext.customize_erpnext.report.shift_attendance_customize.standard_export import (
	ALL_SHEETS,
	load_export_universe,
)

GF, GT = "2026-06-01", "2026-06-30"


def _note_rows(wb):
	if "Important Note" not in wb.sheetnames:
		return 0
	return sum(1 for r in wb["Important Note"].iter_rows(min_row=4)
	           if r[0].value and "Nghỉ phép + đi làm" in str(r[0].value))


# (a) ngưỡng phút — càng lớn càng ít dòng, đơn điệu không tăng
counts = []
for g in (0, 15, 60, 241):
	counts.append(_note_rows(build_standard_workbook(GF, GT, leave_gap_minutes=g,
	                                                 sheets=["Important Note"])))
print(f"     ngưỡng 0/15/60/241+ phút → {counts} dòng")
check("ngưỡng lớn hơn thì báo ít hơn (không tăng)",
      all(counts[i] >= counts[i + 1] for i in range(len(counts) - 1)), True)
check("ngưỡng 0 báo nhiều hơn ngưỡng mặc định", counts[0] > counts[1], True)
check("ngưỡng 241+ không còn dòng nào", counts[-1], 0)

# (b) chọn sheet — `with_leave_application=1` (mặc định) LUÔN ép thêm sheet Leave Application,
#     nên phần chọn sheet phải test ở chế độ =0 mới thấy đúng tập đã tick.
check("mặc định đủ 7 sheet", build_standard_workbook(GF, GT).sheetnames, list(ALL_SHEETS))
check("chọn 1 sheet → đúng 1 tab, không có tab rỗng",
      build_standard_workbook(GF, GT, sheets=["Detail"],
                              with_leave_application=False).sheetnames, ["Detail"])
check("bỏ Important Note vẫn không sinh tab 'Sheet'",
      build_standard_workbook(GF, GT, sheets=["Summary", "Shift"],
                              with_leave_application=False).sheetnames, ["Summary", "Shift"])
check("with_leave_application=1 ép thêm sheet dù không tick",
      build_standard_workbook(GF, GT, sheets=["Detail"]).sheetnames,
      ["Detail", "Leave Application"])

# (b2) =0 thay working_hours bằng giờ thực tế và bỏ mã nghỉ trên Timesheet
_ts_on = build_standard_workbook(GF, GT, sheets=["Timesheet"])["Timesheet"]
_ts_off = build_standard_workbook(GF, GT, sheets=["Timesheet"],
                                  with_leave_application=False)["Timesheet"]


def _abbr_cells(ws):
	return sum(1 for row in ws.iter_rows(min_row=2)
	           for c in row[8:] if isinstance(c.value, str) and c.value.strip())


print(f"     ô có mã nghỉ: with=1 → {_abbr_cells(_ts_on)} · with=0 → {_abbr_cells(_ts_off)}")
check("=1 có in mã nghỉ trên Timesheet", _abbr_cells(_ts_on) > 0, True)
check("=0 không còn ô nào là mã nghỉ", _abbr_cells(_ts_off), 0)

# (b3) Important Note KHÔNG đổi giữa hai chế độ
check("Important Note giống nhau ở cả hai chế độ",
      _note_rows(build_standard_workbook(GF, GT, sheets=["Important Note"])),
      _note_rows(build_standard_workbook(GF, GT, sheets=["Important Note"],
                                         with_leave_application=False)))

# (b3b) sheet Detail — cột Actual và luật CN/lễ
def _detail(wb):
	ws = wb["Detail"]
	hdrs = [c.value for c in ws[1]]
	rows = list(ws.iter_rows(min_row=2, values_only=True))
	return hdrs, rows


_h_on, _r_on = _detail(build_standard_workbook(GF, GT, sheets=["Detail"]))
_h_off, _r_off = _detail(build_standard_workbook(GF, GT, sheets=["Detail"],
                                                 with_leave_application=False))
check("=1 Detail có cột Actual (hour)", "Actual (hour)" in _h_on, True)
check("=0 Detail bỏ cột Actual (hour)", "Actual (hour)" in _h_off, False)
check("=0 Detail ít hơn đúng 1 cột", len(_h_on) - len(_h_off), 1)

_i_date, _i_in, _i_out = _h_on.index("Date"), _h_on.index("First In"), _h_on.index("Last Out")
_i_wh, _i_ot = _h_on.index("Working (hour)"), _h_on.index("OT Final")
_sun = [r for r in _r_on if r[_i_date].weekday() == 6]
_sun_idle = [r for r in _sun
             if not r[_i_in] and not r[_i_out] and not (r[_i_wh] or 0) and not (r[_i_ot] or 0)]
print(f"     Detail Chủ Nhật: {len(_sun)} dòng, {len(_sun_idle)} dòng không đi làm")
check("Chủ Nhật không còn dòng của người không đi làm", len(_sun_idle), 0)
check("ngày thường vẫn giữ dòng người vắng",
      any(not r[_i_in] for r in _r_on if r[_i_date].weekday() != 6), True)

# (b4) NV không có Attendance nào trong kỳ bị loại khỏi universe
_uni = load_export_universe(GF, GT)
_emp_in_att = {e for e, _d in _uni["att"]}
check("mọi NV trong universe đều có ít nhất 1 bản ghi Attendance",
      all(e.name in _emp_in_att for e in _uni["employees"]), True)

# (c) chỉ người nghỉ việc trong kỳ
db = set(frappe.db.sql("""SELECT name FROM tabEmployee
	WHERE relieving_date BETWEEN %s AND %s AND name LIKE 'TIQN%%'""", (GF, GT), pluck=True))
got = {e.name for e in load_export_universe(GF, GT, only_resigned=True)["employees"]}
print(f"     only_resigned → {len(got)} NV (DB: {len(db)})")
check("khớp DB tuyệt đối", got, db)
check("   gồm cả người nghỉ ĐÚNG ngày đầu kỳ",
      all(frappe.db.get_value("Employee", e, "relieving_date") is not None for e in got), True)
n_all = len(load_export_universe(GF, GT)["employees"])
check("tắt option thì số NV không đổi", n_all > len(got), True)

print(f"\n{'=' * 68}\nKẾT QUẢ: {ok} đạt / {fail} lỗi")
