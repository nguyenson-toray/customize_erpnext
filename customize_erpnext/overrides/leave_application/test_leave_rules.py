"""Test quy tắc nghỉ phép theo QUY_DINH_NGHI_PHEP_2025.md. Luôn rollback."""
from datetime import timedelta

import frappe
from frappe.utils import getdate

from customize_erpnext.overrides import leave_rules as R

R.clear_cache()
BY_ABBR = R._by_abbr()
EMP = "TIQN-0148"

holidays = {h.holiday_date for h in frappe.get_all(
    "Holiday", filters={"parent": "2026"}, fields=["holiday_date"])}
_d = getdate("2026-11-02")
WORKDAYS = []
while len(WORKDAYS) < 12:
    if _d not in holidays and _d.weekday() != 6:
        WORKDAYS.append(_d)
    _d += timedelta(days=1)

ok = fail = 0


def check(label, got, want):
    global ok, fail
    good = abs((got or 0) - want) < 0.01 if isinstance(want, float) else got == want
    ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
    print(f"  {'✅' if good else '❌'} {label:<40} {got!r}" + ("" if good else f"  ← cần {want!r}"))


def mk_la(leave_type, day, half=False):
    la = frappe.new_doc("Leave Application")
    la.employee, la.leave_type = EMP, leave_type
    la.from_date = la.to_date = day
    la.half_day = 1 if half else 0
    if half:
        la.half_day_date = day
    la.status = "Approved"
    la.flags.ignore_permissions = True
    la.insert()
    la.submit()
    return la


def mk_attendance(day, hours):
    """Attendance đã có sẵn do engine sinh từ checkin (đường ghi thật: bỏ qua validate)."""
    a = frappe.new_doc("Attendance")
    a.employee, a.attendance_date, a.status = EMP, day, "Present"
    a.working_hours = hours
    a.company = frappe.db.get_value("Employee", EMP, "company")
    a.flags.ignore_validate = True
    a.insert(ignore_permissions=True)
    a.submit()
    return a


def att(day):
    n = frappe.db.get_value("Attendance", {"employee": EMP, "attendance_date": day,
                                           "docstatus": ("!=", 2)})
    return frappe.get_doc("Attendance", n) if n else None


print("PHẦN 1 — leave_rules đối chiếu 9 dòng quy định")
f = R.run_regulation_selftest()
check("selftest 9/9", "đạt" if not f else str(f), "đạt")

print("\nPHẦN 2 — nửa ngày + nửa còn lại ĐI LÀM (có checkin)")
for i, (abbr, want_status, want_days) in enumerate([
    ("P", "Present", 1.0),    # quy định: P/2 = 1 ngày công
    ("O", "Present", 0.5),    # quy định: O/2 = 0,5
]):
    d = WORKDAYS[i]
    mk_attendance(d, 4.0)
    mk_la(BY_ABBR[abbr], d, half=True)
    a = att(d)
    check(f"{abbr}/2 status", a.status, "Half Day")
    check(f"{abbr}/2 mã", a.custom_leave_application_abbreviation, f"{abbr}/2")
    check(f"{abbr}/2 half_day_status", a.half_day_status, want_status)
    check(f"{abbr}/2 ngày công", R.expected_payment_days(a.leave_type, a.half_day_status),
          want_days)

print("\nPHẦN 3 — nửa ngày mà nửa còn lại KHÔNG đi làm, KHÔNG có đơn thứ 2")
d = WORKDAYS[2]
mk_la(BY_ABBR["P"], d, half=True)
a = att(d)
check("P nửa ngày, không checkin → Absent", a.half_day_status, "Absent")
check("  ngày công (nửa còn lại vắng)", R.expected_payment_days(a.leave_type, a.half_day_status),
      0.5)

print("\nPHẦN 4 — DUAL leave: 2 đơn nửa ngày cùng ngày, không checkin")
for i, (a1, a2, want_code, want_status, want_days) in enumerate([
    ("O", "P", "OP/2", "Present", 0.5),
    ("CO", "P", "COP/2", "Present", 0.5),
    ("O", "CO", "OCO/2", "Absent", 0.0),
    ("O", "KL", "OK/2", "Absent", 0.0),
]):
    d = WORKDAYS[3 + i]
    mk_la(BY_ABBR[a1], d, half=True)
    mk_la(BY_ABBR[a2], d, half=True)
    a = att(d)
    check(f"{want_code} status", a.status, "Half Day")
    check(f"{want_code} mã", a.custom_leave_application_abbreviation, want_code)
    check(f"{want_code} leave_type là nửa is_lwp", R.is_unpaid(a.leave_type), True)
    check(f"{want_code} half_day_status", a.half_day_status, want_status)
    check(f"{want_code} ngày công", R.expected_payment_days(a.leave_type, a.half_day_status),
          want_days)

print("\nPHẦN 5 — nghỉ trọn ngày")
d = WORKDAYS[8]
mk_la(BY_ABBR["P"], d)
check("P trọn ngày, không checkin → On Leave", att(d).status, "On Leave")
d = WORKDAYS[9]
mk_attendance(d, 5.0)          # < full_day_leave_block_hours nên không bị chặn
mk_la(BY_ABBR["P"], d)
check("P trọn ngày, checkin 5h → Present", att(d).status, "Present")

d = WORKDAYS[11]
mk_attendance(d, 8.0)
try:
    mk_la(BY_ABBR["P"], d)
    check("P trọn ngày trên ngày đã làm 8h → phải CHẶN", "không chặn", "chặn")
except Exception as e:
    check("P trọn ngày trên ngày đã làm 8h → phải CHẶN", type(e).__name__,
          "AttendanceAlreadyMarkedError")

print("\nPHẦN 5b — GĐ 6: ngày Chủ Nhật (engine reset working_hours=0, dồn sang OT)")
sunday_like = WORKDAYS[7]
a = mk_attendance(sunday_like, 0.0)
frappe.db.set_value("Attendance", a.name, "actual_overtime_duration", 10.0)
try:
    mk_la(BY_ABBR["P"], sunday_like)
    check("nghỉ nguyên ngày đè lên ngày làm 10h OT → phải CHẶN", "LỌT QUA", "chặn")
except Exception as e:
    check("nghỉ nguyên ngày đè lên ngày làm 10h OT → phải CHẶN", type(e).__name__,
          "AttendanceAlreadyMarkedError")

print("\nPHẦN 6 — engine check_leave_status_cached(): dual leave phải TẤT ĐỊNH")
from customize_erpnext.overrides.shift_type.shift_type_optimized import check_leave_status_cached

day = WORKDAYS[10]
la_o = {"leave_type": BY_ABBR["O"], "leave_application": "LA-Z-002", "is_half_day": 1,
        "half_day_date": day, "abbreviation": "O"}
la_p = {"leave_type": BY_ABBR["P"], "leave_application": "LA-A-001", "is_half_day": 1,
        "half_day_date": day, "abbreviation": "P"}
res = [tuple(check_leave_status_cached(
    EMP, day, {"leave_applications": {(EMP, day): list(o)}}
)[k] for k in ("status", "leave_type", "abbreviation"))
    for o in ([la_o, la_p], [la_p, la_o])]
check("hai thứ tự đầu vào → cùng kết quả", res[0], res[1])
check("status (không còn 'On Leave')", res[0][0], "Half Day")
check("leave_type là nửa is_lwp", R.is_unpaid(res[0][1]), True)
check("mã", res[0][2], "OP/2")

frappe.db.rollback()
print(f"\n{'=' * 58}\nKẾT QUẢ: {ok} đạt / {fail} lỗi | sau rollback còn "
      f"{frappe.db.count('Leave Application')} Leave Application")
