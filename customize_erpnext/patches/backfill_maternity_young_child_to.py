"""Tính lại `Young Child To Date` của hồ sơ cũ theo quy tắc mới (04/11/2026):
  cũ: Date of Birth + 364 ngày — khoảng có 29/02 thì hụt 1 ngày
  mới: trước sinh nhật 1 tuổi 1 ngày (`young_child_end_date()`)

Chỉ đổi đúng field này, bằng `db.set_value(update_modified=False)` — không chạy
validate/hook, không đụng status và KHÔNG tính lại Attendance. Hồ sơ không có ngày sinh
hoặc đang trống Young Child To thì bỏ qua. Idempotent.

Dry-run: bench --site <site> execute customize_erpnext.patches.backfill_maternity_young_child_to.execute --kwargs "{'dry_run': 1}"
"""

import frappe

from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity import (
	young_child_end_date,
)


def execute(dry_run=0):
	rows = frappe.db.sql(
		"""
		SELECT name, date_of_birth, youg_child_to_date
		FROM `tabEmployee Maternity`
		WHERE date_of_birth IS NOT NULL AND youg_child_to_date IS NOT NULL
		""",
		as_dict=True,
	)
	updated = 0
	for r in rows:
		new_to = young_child_end_date(r.date_of_birth)
		if r.youg_child_to_date == new_to:
			continue
		updated += 1
		if not dry_run:
			frappe.db.set_value(
				"Employee Maternity", r.name, "youg_child_to_date", new_to, update_modified=False
			)

	print(f"backfill_maternity_young_child_to: {len(rows)} records, {updated} updated"
		+ (" (dry run)" if dry_run else ""))
	return updated
