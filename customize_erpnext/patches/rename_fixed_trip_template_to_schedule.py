# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""pre_model_sync: rename DocType `TIQN Fixed Trip Template` -> `TIQN Fixed Trip Schedule`.

vehicle_management/API_CONTRACT.md renamed the concept and the Mini App refers to it as a
Schedule. Renaming BEFORE the model sync matters: the app folder now only ships
`tiqn_fixed_trip_schedule`, so a sync that ran first would see the old DocType as
an orphan and delete it - taking the six configured schedules with it.

The field rename (`template_name` -> `schedule_name`) and the docname rename
(TIQN-FTT-00x -> TIQN-FST-00x) run afterwards, in
`rename_fixed_trip_schedule_fields`, because `rename_field` needs the new field
to already exist in the meta.

Idempotent.
"""

import frappe
from frappe.model.rename_doc import rename_doc

OLD = "TIQN Fixed Trip Template"
NEW = "TIQN Fixed Trip Schedule"


def execute():
	if not frappe.db.exists("DocType", OLD):
		return
	if frappe.db.exists("DocType", NEW):
		return

	# frappe.rename_doc() (the wrapper in frappe/__init__.py) does not take
	# ignore_permissions - that argument only exists on
	# frappe.model.rename_doc.rename_doc, which is what we want here anyway
	# because a patch runs as Administrator with no request context.
	rename_doc("DocType", OLD, NEW, force=True, ignore_permissions=True)
	frappe.db.set_value("DocType", NEW, "autoname", "TIQN-FST-.###", update_modified=False)
