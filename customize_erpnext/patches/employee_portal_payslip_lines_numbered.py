# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""post_model_sync: the Mini App Label of Employee Portal Settings > Payslip Lines is
shown word for word, line number and formula letters included (26/10/2026) - add them to
the labels filled in by employee_portal_payslip_lines_v5 ("Lương cơ bản" ->
"1 Lương cơ bản (a)"). Rows already starting with their number are left alone.
Idempotent.
"""

import re

import frappe

from customize_erpnext.api.employee_portal.payslip import FORMULA_RE

SETTINGS = "Employee Portal Settings"


def execute():
	frappe.clear_cache(doctype=SETTINGS)
	settings = frappe.get_single(SETTINGS)
	settings.sync_payslip_lines()
	for row in settings.payslip_lines:
		text = " ".join((row.portal_label or "").split())
		if not text or re.match(rf"^{re.escape(row.code)}(\s|$)", text):
			continue
		text = f"{row.code} {text}"
		m = FORMULA_RE.search(row.erp_label or "")
		if m and not FORMULA_RE.search(text):
			letters = re.sub(r"\s+", "", m.group(1))
			text += f" ({letters})"
		row.portal_label = text
	settings.flags.ignore_permissions = True
	settings.save()
