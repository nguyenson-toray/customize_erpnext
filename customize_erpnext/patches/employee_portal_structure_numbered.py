"""TIQN Payslip Structure named PSS-01, PSS-02... instead of PSS-<valid_from> (29/10/2026):
"PSS-2026-09" read as the structure of period 2026-09 only, while it runs until the next
structure. Renamed in Valid From order (rename_doc carries TIQN Payslip.structure and the
Version log along; content_version holds no structure name, so the Mini App cache is
untouched), the PSS- series set past them, then Valid To Period filled. Idempotent.
"""

import re

import frappe

from customize_erpnext.employee_portal import payslip_structure as pss

NUMBERED = re.compile(r"^PSS-(\d+)$")


def execute():
	rows = frappe.get_all(pss.STRUCTURE_DT, fields=["name"], order_by="valid_from asc")
	last = max((int(m.group(1)) for m in (NUMBERED.match(r.name) for r in rows) if m), default=0)
	for row in rows:
		if NUMBERED.match(row.name):
			continue
		last += 1
		frappe.rename_doc(pss.STRUCTURE_DT, row.name, f"PSS-{last:02d}", force=True, show_alert=False)
	if last:
		frappe.db.sql(
			"""INSERT INTO `tabSeries` (name, current) VALUES ('PSS-', %(n)s)
			ON DUPLICATE KEY UPDATE current = GREATEST(current, %(n)s)""",
			{"n": last},
		)
	pss.refresh_valid_to()
