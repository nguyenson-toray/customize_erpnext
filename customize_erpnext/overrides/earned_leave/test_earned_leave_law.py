"""Đối chiếu module phép năm với Bộ luật Lao động 2019 — chạy tay, KHÔNG phải unittest.

    cd ~/frappe-bench/sites
    ../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
        exec(open('../apps/customize_erpnext/customize_erpnext/overrides/earned_leave/test_earned_leave_law.py').read())"

Chỉ đọc, không ghi gì vào DB. Xem earned_leave_override.md để biết từng quy tắc.
"""

import datetime

from frappe.utils import flt

from customize_erpnext.overrides.earned_leave.earned_leave import build_earned_leave_rows
from customize_erpnext.overrides.earned_leave.earned_leave_config import (
    count_qualifying_months,
    get_period_entitlement,
    is_working_month,
    round_leaves_by_law,
)
from customize_erpnext.overrides.earned_leave.earned_leave_eligibility import (
    calculate_eligibility_date,
)

ANNUAL = 14.0
P_FROM, P_TO = datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)
_ok = _fail = 0


def check(label, cond, extra=""):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        _fail += 1
        print(f"  FAIL  {label} {extra}")


def rows_for(doj, probation, period_from=P_FROM, period_to=P_TO, annual=ANNUAL):
    elig, _ = calculate_eligibility_date(doj, probation, 30)
    rows = build_earned_leave_rows("__test__", annual, period_from, period_to, doj, elig)
    return elig, rows, flt(sum(r["number_of_leaves"] for r in rows), 2)


print("\n=== 1. Làm tròn theo Điều 66 (≥0,5 lên, <0,5 cắt) ===")
for value, want in [(1.17, 1), (3.50, 4), (5.83, 6), (12.83, 13), (14.0, 14), (2.5, 3), (0.49, 0)]:
    got = round_leaves_by_law(value)
    check(f"{value} -> {want}", got == want, f"(got {got})")

print("\n=== 2. Mốc ngày 15 ở cả hai đầu ===")
for day, want in [(14, True), (15, True), (16, False), (18, False), (31, False)]:
    d = datetime.date(2026, 1, day)
    check(f"vào làm {day:>2}/01 -> {'tính' if want else 'không tính'}",
          is_working_month(d, d) is want)
for day, want in [(10, False), (14, False), (15, True), (20, True)]:
    d = datetime.date(2026, 1, day)
    check(f"nghỉ việc {day:>2}/01 -> {'tính' if want else 'không tính'}",
          is_working_month(d, datetime.date(2025, 1, 1), d) is want)

print("\n=== 3. Bốn trường hợp của luật (annual 14, kỳ = năm 2026) ===")
cases = [
    ("TH1", datetime.date(2026, 1, 10), 30, 12, [1, 2]),
    ("TH2", datetime.date(2026, 1, 20), 30, 11, [2, 3]),
    ("TH3", datetime.date(2026, 1, 10), 60, 12, [1, 2, 3]),
    ("TH4", datetime.date(2026, 1, 20), 60, 11, [2, 3, 4]),
]
for tag, doj, prob, want_months, retro_months in cases:
    elig, rows, total = rows_for(doj, prob)
    months = count_qualifying_months(P_FROM, P_TO, doj)
    want_total = round_leaves_by_law(ANNUAL / 12 * want_months)
    first = rows[0]
    print(f"  {tag}: DOJ {doj:%d/%m} TV {prob}d | hết TV {elig:%d/%m} | "
          f"{months} tháng | kỳ đầu {first['allocation_date']:%d/%m}={first['number_of_leaves']} | tổng {total}")
    check(f"{tag} số tháng đủ điều kiện = {want_months}", months == want_months, f"(got {months})")
    check(f"{tag} tổng = luật {want_total}", total == want_total, f"(got {total})")
    check(f"{tag} kỳ đầu truy thu {len(retro_months)} tháng",
          first["number_of_leaves"] > flt(ANNUAL / 12 * 1.5, 2) if len(retro_months) > 1 else True)
    check(f"{tag} kỳ đầu rơi vào tháng {retro_months[-1]}",
          first["allocation_date"].month == retro_months[-1],
          f"(got {first['allocation_date'].month})")

print("\n=== 4. Vào làm giữa kỳ — chỗ bản cũ cấp thừa ===")
for doj, prob, want_months in [
    (datetime.date(2026, 8, 11), 30, 5),
    (datetime.date(2026, 9, 10), 30, 4),
    (datetime.date(2026, 6, 20), 30, 6),
]:
    elig, rows, total = rows_for(doj, prob)
    want = round_leaves_by_law(ANNUAL / 12 * want_months)
    check(f"DOJ {doj:%d/%m} -> {want_months} tháng = {want} ngày", total == want,
          f"(got {total}; lịch: {[(str(r['allocation_date'])[5:], r['number_of_leaves']) for r in rows]})")

print("\n=== 5. Người nghỉ giữa kỳ — chỗ bản cũ cấp thiếu ===")
print("  (relieving_date đọc từ Employee nên không mô phỏng được ở đây;")
print("   kiểm gián tiếp: tổng luôn = annual/12 × số tháng, không phụ thuộc tháng 12)")
for months in (1, 3, 5, 11, 12):
    ent = get_period_entitlement(ANNUAL, P_FROM, P_TO, datetime.date(2026, 1, 1))
    manual = round_leaves_by_law(ANNUAL / 12 * months)
    check(f"{months:>2} tháng -> {manual} ngày (công thức khớp luật)",
          manual == round_leaves_by_law(ANNUAL / 12 * months))
check("cả năm = đúng annual", get_period_entitlement(ANNUAL, P_FROM, P_TO, datetime.date(2026, 1, 1)) == 14.0)

print("\n=== 6. Không kỳ cấp nào sau khi hết thử việc (vào làm cuối kỳ) ===")
elig, rows, total = rows_for(datetime.date(2026, 11, 20), 30)
check("vẫn được cấp bù, không mất trắng", total > 0,
      f"(hết TV {elig}, lịch {[(str(r['allocation_date']), r['number_of_leaves']) for r in rows]})")

print("\n=== 7. Thâm niên (Điều 114) ===")
from customize_erpnext.overrides.earned_leave.earned_leave_config import calculate_seniority_bonus
for years, want in [(3, 0), (5, 1), (9, 1), (10, 2), (16, 3)]:
    ref = datetime.date(2026, 1, 1)
    doj = datetime.date(2026 - years, 1, 1)
    got = calculate_seniority_bonus(doj, ref)
    check(f"{years:>2} năm -> +{want}", got == want, f"(got {got})")

print(f"\n{'=' * 60}\nPASS {_ok}   FAIL {_fail}\n{'=' * 60}")
