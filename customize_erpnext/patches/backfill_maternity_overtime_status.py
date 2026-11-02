"""Điền 2 field mới của `Employee Maternity` cho hồ sơ cũ (02/11/2026):
  seventh_month_date = Ngày dự sinh - 3 tháng
  overtime_status    = Allowed / Not Allowed tại hôm nay (chỉ khi đang Mang thai)

Dùng đúng hai hàm của controller để khớp với lần save / job 00:10 sau này.
Ghi bằng `db.set_value(update_modified=False)` — không chạy validate/hook, không đổi
status hay ngày nào khác. Idempotent.

Dry-run: bench --site <site> execute customize_erpnext.patches.backfill_maternity_overtime_status.execute --kwargs "{'dry_run': 1}"
"""

from collections import Counter
from datetime import date

import frappe

from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity import (
	_has_left,
	overtime_status,
	seventh_month_date,
)


def execute(dry_run=0):
	rows = frappe.db.sql(
		"""
		SELECT em.name, em.estimated_due_date, em.pregnant_from_date, em.pregnant_to_date,
		       em.seventh_month_date, em.overtime_status,
		       emp.relieving_date, emp.status AS employee_status
		FROM `tabEmployee Maternity` em
		LEFT JOIN `tabEmployee` emp ON emp.name = em.employee
		""",
		as_dict=True,
	)
	today_date = date.today()
	stats = Counter()
	for r in rows:
		m7 = seventh_month_date(r.estimated_due_date)
		has_left = _has_left(r.relieving_date, r.employee_status, today_date)
		ot = overtime_status(
			r.estimated_due_date, r.pregnant_from_date, r.pregnant_to_date, today_date,
			has_left=has_left,
		)
		stats[ot or "(blank)"] += 1
		changes = {}
		if r.seventh_month_date != m7:
			changes["seventh_month_date"] = m7
		if (r.overtime_status or "") != (ot or ""):
			changes["overtime_status"] = ot
		if not changes:
			continue
		stats["updated"] += 1
		if not dry_run:
			frappe.db.set_value("Employee Maternity", r.name, changes, update_modified=False)

	print(f"backfill_maternity_overtime_status: {len(rows)} records, {dict(stats)}"
		+ (" (dry run)" if dry_run else ""))
	return dict(stats)
