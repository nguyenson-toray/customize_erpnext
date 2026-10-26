# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""TIQN Payslip independent of HRMS payroll (26/10/2026) - post_model_sync, idempotent.

1. The payslip is described by the TIQN Payslip fields alone (utils.payslip_component_fields).
   The display config on Salary Component (custom_portal_*) goes: values are saved to
   private/backups/salary_component_portal_config_<time>.json, then the Custom Fields
   are deleted and the columns dropped (they are also out of fixtures/custom_field.json,
   which syncs AFTER patches).
2. Employee Portal Settings > Day / Hour Columns and its child DocType TIQN Portal Qty
   Unit go: the unit is the end of the `sc_<code>_qty` label ("- Days" / "- Hours").
3. TIQN Portal Link Request counts requests (one record per Zalo account): existing
   records start at 1 request, sent when they were created.
"""

import json
import os

import frappe
from frappe.utils import now_datetime

SALARY_COMPONENT = "Salary Component"
PORTAL_FIELDS = (
	"custom_portal_tab", "custom_portal_section", "custom_portal_row", "custom_portal_parent",
	"custom_portal_column_break", "custom_portal_label", "custom_portal_unit", "custom_portal_order",
)
QTY_UNIT_DT = "TIQN Portal Qty Unit"
LINK_REQUEST = "TIQN Portal Link Request"


def execute():
	drop_salary_component_config()
	drop_qty_unit_table()
	start_request_counts()


def drop_salary_component_config():
	columns = [f for f in PORTAL_FIELDS if f in frappe.db.get_table_columns(SALARY_COMPONENT)]
	if columns:
		rows = frappe.db.sql(
			"SELECT name, salary_component_abbr, {} FROM `tabSalary Component`".format(
				", ".join(f"`{c}`" for c in columns)
			),
			as_dict=True,
		)
		backup_dir = frappe.get_site_path("private", "backups")
		os.makedirs(backup_dir, exist_ok=True)
		path = os.path.join(
			backup_dir, "salary_component_portal_config_{}.json".format(now_datetime().strftime("%y%m%d_%H%M%S"))
		)
		with open(path, "w") as fh:
			json.dump(rows, fh, ensure_ascii=False, indent=1, default=str)

	for fieldname in PORTAL_FIELDS:
		name = f"{SALARY_COMPONENT}-{fieldname}"
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=True, ignore_missing=True)
	# delete_doc of a Custom Field keeps the column - drop the leftovers.
	for column in columns:
		if column in frappe.db.get_table_columns(SALARY_COMPONENT):
			frappe.db.sql_ddl(f"ALTER TABLE `tabSalary Component` DROP COLUMN `{column}`")
	frappe.clear_cache(doctype=SALARY_COMPONENT)


def drop_qty_unit_table():
	if frappe.db.exists("DocType", QTY_UNIT_DT):
		frappe.delete_doc("DocType", QTY_UNIT_DT, force=True, ignore_missing=True)
	if frappe.db.table_exists(QTY_UNIT_DT):
		frappe.db.sql_ddl(f"DROP TABLE `tab{QTY_UNIT_DT}`")


def start_request_counts():
	if not frappe.db.has_column(LINK_REQUEST, "request_count"):
		return
	frappe.db.sql(
		f"""UPDATE `tab{LINK_REQUEST}`
		SET request_count = 1, last_requested_on = IFNULL(last_requested_on, creation)
		WHERE IFNULL(request_count, 0) = 0"""
	)
