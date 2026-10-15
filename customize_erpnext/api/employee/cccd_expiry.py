# -*- coding: utf-8 -*-
# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Ngày hết hạn CCCD — tự tính từ ngày sinh + ngày cấp (Luật Căn cước 2023).

Cùng thuật toán với `_cccdExpiryISO` trên trang `/employee-self-update-info` và `cccd_expiry()`
trong `public/js/custom_scripts/employee.js` — sửa một nơi thì sửa cả ba.

- Mốc đổi thẻ: 14 / 25 / 40 / 60 tuổi → hết hạn vào NGÀY SINH của tuổi mốc.
- Cấp trong vòng 2 năm trước một mốc → tính sang mốc kế tiếp.
- Cấp từ 58 tuổi trở lên (trong 2 năm trước mốc 60, hoặc sau 60) → KHÔNG THỜI HẠN → để trống.
- Sinh 29/02, năm hết hạn không nhuận → 28/02 (bản JS cũ trả "YYYY-02-29" không tồn tại).

`custom_id_card__date_of_expired` trên Employee là read_only; hook validate tính lại mỗi lần lưu
(form, Data Import, đồng bộ từ self-update, onboarding). Thiếu ngày sinh hoặc ngày cấp → để trống.
"""

import frappe
from frappe.utils import getdate

ISSUE_FIELD = "custom_id_card_date_of_issue"
EXPIRY_FIELD = "custom_id_card__date_of_expired"
DOB_FIELD = "date_of_birth"
_MILESTONES = (14, 25, 40, 60)


def cccd_expiry(dob, issue):
	"""datetime.date hết hạn, hoặc None (thiếu dữ liệu / không thời hạn)."""
	if not dob or not issue:
		return None
	try:
		dob, issue = getdate(dob), getdate(issue)
	except Exception:
		return None
	age = issue.year - dob.year - ((issue.month, issue.day) < (dob.month, dob.day))
	exp_age = None
	for i, m in enumerate(_MILESTONES):
		if age < m:
			if age >= m - 2:
				exp_age = _MILESTONES[i + 1] if i + 1 < len(_MILESTONES) else None
			else:
				exp_age = m
			break
	if exp_age is None:
		return None
	year = dob.year + exp_age
	try:
		return dob.replace(year=year)
	except ValueError:  # 29/02 → năm không nhuận
		return dob.replace(year=year, day=28)


def cccd_expiry_iso(dob, issue):
	d = cccd_expiry(dob, issue)
	return d.isoformat() if d else ""


def set_employee_cccd_expiry(doc, method=None):
	"""doc_events Employee.validate — ngày hết hạn luôn theo ngày sinh + ngày cấp."""
	if not doc.meta.has_field(EXPIRY_FIELD) or not doc.meta.has_field(ISSUE_FIELD):
		return
	doc.set(EXPIRY_FIELD, cccd_expiry(doc.get(DOB_FIELD), doc.get(ISSUE_FIELD)))


def backfill_employee_expiry(dry_run=1):
	"""Điền/sửa ngày hết hạn cho mọi Employee (ghi thẳng, không đổi `modified`).

	    bench --site erp.tiqn.local execute \
	        customize_erpnext.api.employee.cccd_expiry.backfill_employee_expiry --kwargs "{'dry_run': 0}"
	"""
	dry_run = frappe.utils.cint(dry_run)
	rows = frappe.get_all("Employee", fields=["name", DOB_FIELD, ISSUE_FIELD, EXPIRY_FIELD])
	changes = []
	for r in rows:
		new = cccd_expiry(r.get(DOB_FIELD), r.get(ISSUE_FIELD))
		old = getdate(r.get(EXPIRY_FIELD)) if r.get(EXPIRY_FIELD) else None
		if new != old:
			changes.append((r.name, old, new))
	if not dry_run:
		for name, _old, new in changes:
			frappe.db.set_value("Employee", name, EXPIRY_FIELD, new, update_modified=False)
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
