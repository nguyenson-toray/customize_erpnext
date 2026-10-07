"""Điền `Employee Maternity.leave_months` cho hồ sơ cũ từ ngày đã có.

Cột mới có default 6 nên khi thêm cột MỌI hồ sơ cũ đều mang 6 — kể cả người nghỉ
7 tháng (sinh đôi). Mà có `leave_months` thì lần save kế tiếp sẽ TÍNH LẠI
`maternity_to_date` = bắt đầu + 6 tháng → âm thầm cắt 1 tháng nghỉ của họ.

Nên suy ngược từ ngày:
  - ngày kết thúc rơi đúng tròn N tháng → leave_months = N
  - lệch (nghỉ lẻ ngày, dữ liệu cũ) → 0 = "không dùng số tháng", giữ ngày HR đã nhập
  - chưa có ngày nghỉ (còn mang thai) → giữ default 6

`is_twins` KHÔNG suy từ 7 tháng (user chốt 06/10/2026: HR tự kiểm tra).
Ghi bằng `db.set_value(update_modified=False)` — không chạy validate/hook.
Idempotent.

Dry-run: bench --site <site> execute customize_erpnext.patches.backfill_maternity_leave_months.execute --kwargs "{'dry_run': 1}"
"""

from collections import Counter

import frappe

from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity import (
	whole_leave_months,
)


def execute(dry_run=0):
	rows = frappe.db.sql(
		"""
		SELECT name, leave_months,
			maternity_from_date AS mat_from,
			maternity_to_date
		FROM `tabEmployee Maternity`
		WHERE maternity_from_date IS NOT NULL
			AND maternity_to_date IS NOT NULL
		""",
		as_dict=True,
	)

	result = Counter()
	for r in rows:
		months = whole_leave_months(r.mat_from, r.maternity_to_date)
		result[months] += 1
		if int(r.leave_months or 0) != months and not dry_run:
			frappe.db.set_value(
				"Employee Maternity", r.name, "leave_months", months, update_modified=False
			)

	if not dry_run:
		frappe.db.commit()
	print(f"   {'[DRY-RUN] ' if dry_run else ''}leave_months theo số tháng (0 = lệch): {dict(sorted(result.items()))}")
	return dict(result)
