"""Đối chiếu bản tăng tốc với bản HRMS gốc — phải ra CÙNG con số.

Đây là điều kiện để tin bản mới: tăng tốc mà lệch số thì vô nghĩa. Bản gốc được giữ ở
`_tiqn_original_execute` khi monkey patch (xem `__init__.py`).

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    exec(open('../apps/customize_erpnext/customize_erpnext/overrides/leave_reports/test_leave_reports.py').read())"

Đặt `LIMIT = None` để chạy toàn bộ nhân viên (chậm, vì phải chạy cả bản gốc để so).
"""

import time

import frappe

import hrms.hr.report.employee_leave_balance.employee_leave_balance as bal_mod
import hrms.hr.report.employee_leave_balance_summary.employee_leave_balance_summary as sum_mod

LIMIT = 120          # số nhân viên đưa vào đối chiếu; None = tất cả
FROM_DATE = "2025-12-26"
TO_DATE = "2026-12-25"
TOL = 0.0001         # sai số float cho phép

# Đối chiếu cả loại CÓ phân bổ lẫn loại KHÔNG phân bổ — hai nhánh code khác nhau
ANNUAL = frappe.db.get_value("Leave Type", {"is_earned_leave": 1}, "name")
AD_HOC = "Nghỉ hưởng BHXH/ Social insurance leave - Ốm đau"

COMPANY = frappe.db.get_value("Employee", {"status": "Active"}, "company")
ok = fail = 0


def check(label, got, want):
	global ok, fail
	good = abs(float(got or 0) - float(want or 0)) < TOL
	ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
	if not good:
		print(f"  ❌ {label:<58} mới={got!r}  gốc={want!r}")
	return good


# ⚠ Phải lấy nhân viên TRONG phạm vi. Bản mới trả rỗng cho người ngoài phạm vi, nên nếu danh
# sách này chứa họ thì vòng so sánh chạy 0 lần mà test vẫn xanh — mất hết giá trị đối chiếu.
from customize_erpnext.overrides.employee_scope import get_scope, scope_filters

emps = frappe.get_all(
	"Employee",
	filters=[["status", "=", "Active"]] + scope_filters(),
	pluck="name",
	order_by="name",
	limit=LIMIT,
)
print(f"Đối chiếu {len(emps)} nhân viên · kỳ {FROM_DATE} → {TO_DATE}\n")

# ---------------------------------------------------------------- Balance
print("PHẦN 1 — Employee Leave Balance (5 cột số, chỉ so dòng phép năm)")
t_new = t_old = 0.0
for emp in emps:
	f = frappe._dict(
		from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY, employee=emp, leave_type=ANNUAL
	)

	t = time.time()
	new_rows = bal_mod.execute(f)[1]
	t_new += time.time() - t

	t = time.time()
	old_rows = bal_mod._tiqn_original_execute(f)[1]
	t_old += time.time() - t

	old_by_lt = {r.get("leave_type"): r for r in old_rows if r.get("leave_type")}
	for r in new_rows:
		lt = r.get("leave_type")
		if not lt:
			continue
		o = old_by_lt.get(lt)
		if o is None:
			print(f"  ❌ {emp}: bản gốc không có dòng {lt}")
			fail += 1
			continue
		for col in (
			"opening_balance",
			"leaves_allocated",
			"leaves_taken",
			"leaves_expired",
			"closing_balance",
		):
			check(f"{emp} · {col}", r.get(col), o.get(col))

print(f"  thời gian: mới {t_new:.2f}s · gốc {t_old:.2f}s → nhanh hơn {t_old / max(t_new, 1e-9):.1f}×")

# ---------------------------------------------------------------- Summary
print("\nPHẦN 2 — Summary: cột Balance phải khớp closing_balance của report kia")
f = frappe._dict(date=TO_DATE, company=COMPANY, employee=None)
for emp in emps[:40]:
	fs = frappe._dict(date=TO_DATE, company=COMPANY, employee=emp, leave_type=ANNUAL)
	srow = sum_mod.execute(fs)[1]
	if not srow:
		print(f"  ❌ {emp}: Summary không trả dòng nào")
		fail += 1
		continue
	balance_new = srow[0][-1]

	fb = frappe._dict(
		from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY, employee=emp, leave_type=ANNUAL
	)
	brows = [r for r in bal_mod.execute(fb)[1] if r.get("leave_type")]
	check(f"{emp} · Summary.Balance == Balance.closing", balance_new, brows[0].get("closing_balance"))

# --------------------------------- loại KHÔNG phân bổ (9 loại nghỉ phát sinh)
print("\nPHẦN 3 — loại nghỉ phát sinh (không có allocation) cũng phải khớp bản gốc")
for emp in emps:
	f = frappe._dict(
		from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY, employee=emp, leave_type=AD_HOC
	)
	new_rows = [r for r in bal_mod.execute(f)[1] if r.get("leave_type")]
	old_rows = {
		r.get("leave_type"): r
		for r in bal_mod._tiqn_original_execute(f)[1]
		if r.get("leave_type")
	}
	for r in new_rows:
		o = old_rows.get(r["leave_type"])
		for col in ("opening_balance", "leaves_allocated", "leaves_taken", "closing_balance"):
			check(f"{emp} · {AD_HOC[:18]} · {col}", r.get(col), o.get(col))

print("\nPHẦN 4 — Summary.Taken của loại phát sinh KHÔNG được là 0 (điểm mù bản gốc)")
srows = sum_mod.execute(frappe._dict(date=TO_DATE, company=COMPANY, leave_type=AD_HOC))[1]
total_taken = sum(r[4] for r in srows)
check("tổng Taken > 0", total_taken > 0, True)
brows = bal_mod.execute(
	frappe._dict(from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY, leave_type=AD_HOC)
)[1]
check("tổng Taken khớp report Balance", total_taken, sum(r.leaves_taken for r in brows))

print("\nPHẦN 5 — filter leave_type")
rows = bal_mod.execute(
	frappe._dict(from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY, employee=emps[0], leave_type=AD_HOC)
)[1]
check("chỉ trả đúng leave type đã chọn", len({r["leave_type"] for r in rows}), 1)
check("đúng loại", rows[0]["leave_type"] == AD_HOC, True)
# Bỏ trống = xem TẤT CẢ, giống bản HRMS gốc. Mặc định "phép năm" là `default` của ô filter
# (report_js.py), KHÔNG phải hành vi của Python — nếu cả hai chỗ cùng mặc định thì người dùng
# xoá ô chọn cũng vẫn chỉ thấy phép năm.
rows = bal_mod.execute(
	frappe._dict(from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY, employee=emps[0])
)[1]
n_types = frappe.db.count("Leave Type")
check("bỏ trống -> trả đủ mọi leave type", len({r["leave_type"] for r in rows}), n_types)

# Phép năm là loại HR tra nhiều nhất, mà tên tiếng Việt bắt đầu bằng "P" nên sắp theo tên là
# nó rơi xuống CUỐI trong 10 loại (Summary: cột 31→33). Phải nằm đầu.
check("phép năm hiện đầu tiên", rows[0]["leave_type"] == ANNUAL, True)
scols = sum_mod.execute(frappe._dict(date=TO_DATE, company=COMPANY, employee=emps[0]))[0]
check("Summary: nhóm cột phép năm đứng ngay sau Department", scols[3].startswith(ANNUAL), True)
cols = bal_mod.execute(
	frappe._dict(from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY, employee=emps[0])
)[0]
check("employee_name rộng 300", [c for c in cols if c["fieldname"] == "employee_name"][0]["width"], 300)

print("\nPHẦN 6 — phạm vi nhân viên theo Attendance Calculation Setting")
# Bản HRMS gốc không biết tới hai field này nên kéo cả nhân sự công ty khác + bản ghi test vào
# bảng số dư phép, lệch với bảng công và headcount mà không dấu vết nào giải thích.
prefix, excluded = get_scope()
print(f"     prefix {prefix!r} · loại {len(excluded)} mã: {excluded}")

outsiders = [e for e in excluded if frappe.db.exists("Employee", e)]
off_prefix = frappe.db.sql(
	"select name from tabEmployee where name not like %s limit 1", (prefix + "%",), pluck=True
) if prefix else []
outsiders += off_prefix
check("có ít nhất một nhân viên ngoài phạm vi để kiểm", bool(outsiders), True)

for emp in outsiders:
	fo = frappe._dict(from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY, employee=emp)
	check(f"{emp} · Balance loại khỏi kết quả", len(bal_mod.execute(fo)[1]), 0)
	# Bản gốc VẪN trả dòng cho họ -> chứng minh khác biệt đến từ ta, không phải do thiếu dữ liệu
	check(f"{emp} · bản gốc thì vẫn trả", len(bal_mod._tiqn_original_execute(fo)[1]) > 0, True)
	check(
		f"{emp} · Summary loại khỏi kết quả",
		len(sum_mod.execute(frappe._dict(date=TO_DATE, company=COMPANY, employee=emp))[1]),
		0,
	)

# Chạy không lọc employee: số nhân viên trả về phải khớp đúng phạm vi
f_all = frappe._dict(from_date=FROM_DATE, to_date=TO_DATE, company=COMPANY,
                     employee_status="Active", leave_type=ANNUAL)
n_scope = len(frappe.get_all(
	"Employee", filters=[["status", "=", "Active"], ["company", "=", COMPANY]] + scope_filters(),
	pluck="name"))
check("Balance: số NV khớp phạm vi", len({r["employee"] for r in bal_mod.execute(f_all)[1]}), n_scope)
check(
	"Summary: số NV khớp phạm vi",
	len({r[0] for r in sum_mod.execute(
		frappe._dict(date=TO_DATE, company=COMPANY, employee_status="Active", leave_type=ANNUAL))[1]}),
	n_scope,
)

print(f"\n{'=' * 66}\nKẾT QUẢ: {ok} đạt / {fail} lỗi")
