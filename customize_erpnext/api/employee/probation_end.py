# -*- coding: utf-8 -*-
# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Ngày kết thúc hợp đồng thử việc — tự tính từ ngày vào làm + Probation Days.

    custom_finish_probation_contract = date_of_joining + custom_probation_days - 1

Cùng công thức `end_date` của Labor Contract (`start + period - 1`: thử việc 30 ngày từ 01/11
kết thúc 30/11, không phải 01/12). Cùng thuật toán với `probation_end()` trong
`public/js/custom_scripts/employee.js` — sửa một nơi thì sửa cả hai.

Hook validate tính lại mỗi lần lưu (form, Data Import, onboarding). Thiếu ngày vào làm, hoặc
Probation Days trống/0 (chức danh đặc biệt, không thử việc) → để trống.
"""

import frappe
from frappe.utils import add_days, cint, getdate

END_FIELD = "custom_finish_probation_contract"
DAYS_FIELD = "custom_probation_days"
DOJ_FIELD = "date_of_joining"


def probation_end(date_of_joining, probation_days):
	"""datetime.date kết thúc thử việc, hoặc None."""
	days = cint((probation_days or "").strip() if isinstance(probation_days, str) else probation_days)
	if not date_of_joining or days <= 0:
		return None
	return getdate(add_days(date_of_joining, days - 1))


def set_employee_probation_end(doc, method=None):
	"""doc_events Employee.validate — ngày kết thúc thử việc luôn theo ngày vào làm + Probation Days."""
	if not doc.meta.has_field(END_FIELD):
		return
	doc.set(END_FIELD, probation_end(doc.get(DOJ_FIELD), doc.get(DAYS_FIELD)))


def backfill_employee_probation_end(dry_run=1):
	"""Điền/sửa ngày kết thúc thử việc cho mọi Employee (ghi thẳng, không đổi `modified`).

	    bench --site erp.tiqn.local execute \
	        customize_erpnext.api.employee.probation_end.backfill_employee_probation_end --kwargs "{'dry_run': 0}"
	"""
	dry_run = cint(dry_run)
	rows = frappe.get_all("Employee", fields=["name", DOJ_FIELD, DAYS_FIELD, END_FIELD])
	changes = []
	for r in rows:
		new = probation_end(r.get(DOJ_FIELD), r.get(DAYS_FIELD))
		old = getdate(r.get(END_FIELD)) if r.get(END_FIELD) else None
		if new != old:
			changes.append((r.name, old, new))
	if not dry_run:
		for name, _old, new in changes:
			frappe.db.set_value("Employee", name, END_FIELD, new, update_modified=False)
		frappe.db.commit()
	summary = {
		"total": len(rows),
		"changed": len(changes),
		"filled": sum(1 for _n, o, n in changes if o is None and n),
		"cleared": sum(1 for _n, o, n in changes if o and n is None),
		"corrected": sum(1 for _n, o, n in changes if o and n),
		"dry_run": bool(dry_run),
		"sample": [(n, str(o or ""), str(x or "")) for n, o, x in changes[:5]],
	}
	print(summary)
	return summary
