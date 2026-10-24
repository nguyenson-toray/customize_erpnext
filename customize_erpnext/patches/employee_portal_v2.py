# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Employee Portal v2 (23/10/2026) - post_model_sync, idempotent.

1. TIQN Payslip Detail (child table) -> one `sc_<code>` field per component on TIQN
   Payslip. Rows are copied first, then the child DocType is dropped. Runs before
   migrate's "Removing orphan doctypes", which would otherwise drop the table unread.
2. Delete the fake TEST-SEED payslips (+ their view log and notifications).
3. Backfill viewed / view_count / last_viewed_on from the view log.
4. Mini App features for the payslip phase: payslip + notifications on, the rest off.
   Runs once, so HR can switch features back on afterwards.
"""

import frappe
from frappe.utils import flt

from customize_erpnext.employee_portal.utils import component_fieldname

CHILD = "TIQN Payslip Detail"
PARENT = "TIQN Payslip"
SEED_BATCH = "TEST-SEED"
FEATURES_ON = ("feature_payslip", "feature_notifications")
FEATURES_OFF = (
	"feature_attendance",
	"feature_overtime",
	"feature_explanation_create",
	"feature_leave_view",
	"feature_leave_create",
	"feature_oa_invite",
)


def execute():
	frappe.reload_doc("employee_portal", "doctype", "tiqn_payslip")
	copy_child_rows()
	delete_seed_payslips()
	drop_child_doctype()
	backfill_viewed()
	set_payslip_phase_features()


def copy_child_rows():
	if not frappe.db.table_exists(CHILD):
		return
	columns = set(frappe.db.get_table_columns(PARENT))
	rows = frappe.db.sql(f"SELECT parent, abbr, amount FROM `tab{CHILD}` WHERE parenttype = %s", PARENT, as_dict=True)
	skipped = set()
	for r in rows:
		field = component_fieldname(r.abbr)
		if field not in columns:
			skipped.add(r.abbr)
			continue
		frappe.db.set_value(PARENT, r.parent, field, flt(r.amount), update_modified=False)
	if skipped:
		print(f"employee_portal_v2: no field for component codes {sorted(skipped)} - values not copied")


def delete_seed_payslips():
	for name in frappe.get_all(PARENT, filters={"import_batch": SEED_BATCH}, pluck="name"):
		if frappe.db.table_exists("TIQN Payslip View Log"):  # dropped by employee_portal_simplify_v3
			frappe.db.delete("TIQN Payslip View Log", {"payslip": name})
		frappe.db.delete("TIQN Portal Notification", {"reference_doctype": PARENT, "reference_name": name})
		if frappe.db.table_exists(CHILD):
			frappe.db.delete(CHILD, {"parent": name, "parenttype": PARENT})
		frappe.db.delete(PARENT, {"name": name})


def drop_child_doctype():
	if frappe.db.exists("DocType", CHILD):
		frappe.delete_doc("DocType", CHILD, force=True, ignore_missing=True)
	frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{CHILD}`")


def backfill_viewed():
	if not frappe.db.table_exists("TIQN Payslip View Log"):  # dropped by employee_portal_simplify_v3
		return
	frappe.db.sql(
		"""
		UPDATE `tabTIQN Payslip` p
		JOIN (
			SELECT payslip, COUNT(*) AS n, MIN(viewed_on) AS first_on, MAX(viewed_on) AS last_on
			FROM `tabTIQN Payslip View Log` GROUP BY payslip
		) v ON v.payslip = p.name
		SET p.viewed = 1, p.view_count = v.n, p.last_viewed_on = v.last_on,
		    p.first_viewed_on = IFNULL(p.first_viewed_on, v.first_on)
		WHERE IFNULL(p.view_count, 0) = 0
		"""
	)


def set_payslip_phase_features():
	for field in FEATURES_ON:
		frappe.db.set_single_value("Employee Portal Settings", field, 1)
	for field in FEATURES_OFF:
		frappe.db.set_single_value("Employee Portal Settings", field, 0)
