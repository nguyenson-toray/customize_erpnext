"""Kiểm phạm vi recalc attendance khi lưu/xoá Employee Maternity (plan maternity_recalc_scope.md).

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    import customize_erpnext.overrides
    exec(open('../apps/customize_erpnext/customize_erpnext/customize_erpnext/doctype/employee_maternity/test_maternity_recalc_scope.py').read())"

CHỈ ĐỌC: không ghi DB, không queue job. PHẦN 1–3 là hàm thuần; PHẦN 4 đối chiếu
`maternity_phases`/`phase_effect` với engine (`preload_reference_data` +
`check_maternity_status_cached`) trên toàn bộ hồ sơ thật — lệch là phạm vi recalc sai.
"""

import io
import contextlib
from datetime import datetime

import frappe
from frappe.utils import add_days, getdate

from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting import (
	attendance_calculation_setting as ACS,
)
from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity import (
	changed_dates,
	contiguous_segments,
	maternity_phases,
	phase_effect,
	recalc_upper_bound,
)

ok = fail = 0
UPPER = getdate("2026-10-30")


def check(label, got, want=True):
	global ok, fail
	good = got == want
	ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
	print(f"  {'✅' if good else '❌'} {label:<62} {'' if good else f'{got!r} ← cần {want!r}'}")


def base(**overrides):
	doc = frappe._dict(
		employee="TIQN-TEST",
		pregnant_from_date="2025-01-01", pregnant_to_date="2025-06-30",
		estimated_due_date="2025-07-05", apply_hour_reduction=0,
		maternity_from_date="2025-07-01", maternity_to_date="2025-12-31",
		youg_child_from_date="2026-01-01", youg_child_to_date="2026-06-30",
	)
	doc.update(overrides)
	return doc


def diff(old, new, upper=UPPER):
	return changed_dates(maternity_phases(old), maternity_phases(new), upper)


def span(a, b):
	return (getdate(b) - getdate(a)).days + 1


def run():
	print("\nPHẦN 1 — phạm vi theo thay đổi")
	new = diff(None, base())
	check("Hồ sơ mới → đủ 3 giai đoạn", len(new), span("2025-01-01", "2026-06-30"))
	check("Hồ sơ mới → gồm ngày kỳ đã chốt (2025-01-01)", getdate("2025-01-01") in new)

	ext = diff(base(), base(maternity_to_date="2026-01-03", youg_child_from_date="2026-01-04"))
	check("Kéo dài thai sản +3 ngày → 3 ngày", [str(d) for d in ext],
		["2026-01-01", "2026-01-02", "2026-01-03"])

	hr = diff(base(), base(apply_hour_reduction=1))
	check("Bật giảm giờ → chỉ khoảng Mang thai", (len(hr), str(hr[0]), str(hr[-1])),
		(span("2025-01-01", "2025-06-30"), "2025-01-01", "2025-06-30"))

	check("Sửa estimated_due_date (có pregnant_to) → 0 ngày",
		diff(base(), base(estimated_due_date="2025-07-20")), [])
	check("pregnant_to trống → dùng estimated_due_date (như engine)",
		diff(base(pregnant_to_date="2025-06-30"), base(pregnant_to_date=None, estimated_due_date="2025-06-30")), [])
	check("Không đổi gì → 0 ngày", diff(base(), base()), [])

	moved = diff(base(), base(employee="TIQN-OTHER"))
	check("Cùng ngày, chỉ khác employee → 0 (đổi NV xử lý ở _collect)", moved, [])
	old_emp = changed_dates(maternity_phases(base()), [], UPPER)
	check("Xoá / NV cũ khi đổi employee → toàn bộ ngày", len(old_emp), span("2025-01-01", "2026-06-30"))

	print("\nPHẦN 2 — cắt trên")
	check("relieving 2025-08-01 → mốc 2025-07-31",
		str(recalc_upper_bound(None, on_date="2026-10-30", relieving_date="2025-08-01")), "2025-07-31")
	check("Không relieving → hôm nay",
		str(recalc_upper_bound(None, on_date="2026-10-30", relieving_date=None)), "2026-10-30")
	cut = diff(None, base(), recalc_upper_bound(None, on_date="2026-10-30", relieving_date="2025-08-01"))
	check("Hồ sơ mới + relieving → ngày cuối 2025-07-31", str(cut[-1]), "2025-07-31")
	future = diff(None, base(youg_child_to_date="2027-03-31"))
	check("Giai đoạn kéo sang tương lai → ngày cuối = hôm nay", str(future[-1]), str(UPPER))

	print("\nPHẦN 3 — tách đoạn + giờ cao điểm")
	both_ends = diff(base(), base(pregnant_to_date="2025-06-28", maternity_from_date="2025-06-29",
		maternity_to_date="2026-01-02", youg_child_from_date="2026-01-03"))
	check("Dịch 2 đầu thai sản → 2 đoạn rời nhau",
		[(str(a), str(b)) for a, b in contiguous_segments(both_ends)],
		[("2025-06-29", "2025-06-30"), ("2026-01-01", "2026-01-02")])
	check("Một đoạn liên tục → 1 đoạn",
		len(contiguous_segments(new)), 1)
	check("Danh sách rỗng → 0 đoạn", contiguous_segments([]), [])

	real = ACS.get_attendance_settings
	try:
		ACS.get_attendance_settings = lambda: frappe._dict(peak_times="16:00,16:15", peak_window_minutes=15)
		d = datetime(2026, 10, 30)
		check("16:05 trong khung → hết lúc 16:15",
			ACS.peak_window_end(d.replace(hour=16, minute=5)), d.replace(hour=16, minute=15))
		check("16:15 khung kế tiếp → hết lúc 16:30",
			ACS.peak_window_end(d.replace(hour=16, minute=15)), d.replace(hour=16, minute=30))
		check("15:59 ngoài khung → None", ACS.peak_window_end(d.replace(hour=15, minute=59)), None)
		check("is_peak_time khớp peak_window_end", ACS.is_peak_time(d.replace(hour=16, minute=5)), True)
	finally:
		ACS.get_attendance_settings = real

	print("\nPHẦN 4 — đối chiếu với engine trên hồ sơ thật (NV chỉ có 1 hồ sơ)")
	from customize_erpnext.overrides.shift_type import shift_type_optimized as E

	records = frappe.get_all("Employee Maternity", fields=[
		"name", "employee", "pregnant_from_date", "pregnant_to_date", "estimated_due_date",
		"apply_hour_reduction", "maternity_from_date", "maternity_to_date",
		"youg_child_from_date", "youg_child_to_date",
	])
	counts = {}
	for r in records:
		counts[r.employee] = counts.get(r.employee, 0) + 1
	singles = [r for r in records if counts[r.employee] == 1 and maternity_phases(r)]
	with contextlib.redirect_stdout(io.StringIO()):
		ref = E.preload_reference_data([r.employee for r in singles], "2020-01-01", "2030-12-31")

	mismatches, compared = [], 0
	for r in singles:
		phases = maternity_phases(r)
		day, end = min(p[1] for p in phases), max(p[2] for p in phases)
		day = add_days(day, -3)
		end = add_days(end, 3)
		while day <= end:
			mine = phase_effect(phases, day)
			status, benefit = E.check_maternity_status_cached(r.employee, day, ref)
			engine = (status, bool(benefit)) if status else None
			compared += 1
			if mine != engine:
				mismatches.append((r.name, str(day), mine, engine))
				break
			day = add_days(day, 1)
	check(f"{len(singles)} hồ sơ / {compared} ngày khớp engine", mismatches, [])

	print(f"\n{'='*40}\n  {ok} OK · {fail} FAIL")


if __name__ == "__main__":
	run()
