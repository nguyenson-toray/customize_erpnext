# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""post_model_sync: Door Alert Setting — 4 checks became 2 selects (09/10/2026).

  alert_erp_unlock_after_hours / alert_every_erp_open        -> erp_open_alert
  alert_fingerprint_after_hours / alert_every_fingerprint     -> fingerprint_alert
  ("every" wins -> Always; "after hours" -> After Hours; none -> Off)

The old fields are gone from the meta after the model sync, so their values are
read straight from tabSingles, then those orphan rows are removed. Idempotent:
does nothing once the old rows are gone.
"""

import frappe

DT = "Door Alert Setting"
PAIRS = {
	"erp_open_alert": ("alert_every_erp_open", "alert_erp_unlock_after_hours"),
	"fingerprint_alert": ("alert_every_fingerprint", "alert_fingerprint_after_hours"),
}


def _old(field):
	row = frappe.db.sql("select value from `tabSingles` where doctype=%s and field=%s", (DT, field))
	return row[0][0] if row else None


def execute():
	old_fields = [f for pair in PAIRS.values() for f in pair]
	if not any(_old(f) is not None for f in old_fields):
		return

	for new_field, (every, after_hours) in PAIRS.items():
		if frappe.utils.cint(_old(every)):
			value = "Always"
		elif frappe.utils.cint(_old(after_hours)):
			value = "After Hours"
		else:
			value = "Off"
		frappe.db.set_single_value(DT, new_field, value)

	frappe.db.sql(
		"delete from `tabSingles` where doctype=%s and field in %s", (DT, tuple(old_fields))
	)
