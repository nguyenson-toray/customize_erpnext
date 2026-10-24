# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Simpler payslip setup (24/10/2026) - post_model_sync, idempotent.

1. Which lines show days / hours moves from Salary Component.custom_portal_qty_unit to
   Employee Portal Settings > Day / Hour Columns; the custom field is deleted (and taken
   out of fixtures/custom_field.json, which syncs AFTER patches).
2. "Viewed" = TIQN Payslip.first_viewed_on only: viewed / view_count / last_viewed_on
   and the TIQN Payslip View Log DocType go.
3. Report Portal Readiness goes (replaced by Payslip Period Summary).
4. Settings > Check Formulas on Import starts ticked (behaviour so far).
"""

import frappe

PAYSLIP = "TIQN Payslip"
SETTINGS = "Employee Portal Settings"
QTY_FIELD = "Salary Component-custom_portal_qty_unit"
DEFAULT_UNITS = {"1.2": "Day", "2.1": "Hour", "2.2": "Hour", "2.3": "Hour", "7.4": "Day", "7.5": "Day"}
DROPPED_COLUMNS = ("viewed", "view_count", "last_viewed_on")


def execute():
	frappe.reload_doc("employee_portal", "doctype", "tiqn_portal_qty_unit")
	frappe.reload_doc("employee_portal", "doctype", "employee_portal_settings")
	move_qty_units()
	drop_view_tracking()
	if frappe.db.exists("Report", "Portal Readiness"):
		frappe.delete_doc("Report", "Portal Readiness", force=True, ignore_missing=True)


def move_qty_units():
	settings = frappe.get_single(SETTINGS)
	if not settings.payslip_qty_units:
		units = {}
		if "custom_portal_qty_unit" in frappe.db.get_table_columns("Salary Component"):
			units = dict(
				frappe.db.sql(
					"SELECT name, custom_portal_qty_unit FROM `tabSalary Component` WHERE IFNULL(custom_portal_qty_unit, '') != ''"
				)
			)
		if not units:
			units = {
				name: DEFAULT_UNITS[abbr]
				for name, abbr in frappe.get_all(
					"Salary Component",
					filters={"salary_component_abbr": ["in", list(DEFAULT_UNITS)]},
					fields=["name", "salary_component_abbr"],
					as_list=True,
				)
			}
		abbr_of = dict(frappe.get_all("Salary Component", fields=["name", "salary_component_abbr"], as_list=True))
		for name in sorted(units, key=lambda n: [int(p) for p in str(abbr_of.get(n) or "").split(".") if p.isdigit()]):
			settings.append("payslip_qty_units", {"salary_component": name, "unit": units[name]})
	settings.validate_payslip_formulas = 1  # a new Single field has no value yet; runs once
	settings.flags.ignore_permissions = True
	settings.save()

	if frappe.db.exists("Custom Field", QTY_FIELD):
		frappe.delete_doc("Custom Field", QTY_FIELD, force=True, ignore_missing=True)
	if "custom_portal_qty_unit" in frappe.db.get_table_columns("Salary Component"):
		frappe.db.sql_ddl("ALTER TABLE `tabSalary Component` DROP COLUMN `custom_portal_qty_unit`")
	frappe.clear_cache(doctype="Salary Component")


def drop_view_tracking():
	columns = set(frappe.db.get_table_columns(PAYSLIP))
	for column in DROPPED_COLUMNS:
		if column in columns:
			frappe.db.sql_ddl(f"ALTER TABLE `tab{PAYSLIP}` DROP COLUMN `{column}`")
	if frappe.db.exists("DocType", "TIQN Payslip View Log"):
		frappe.delete_doc("DocType", "TIQN Payslip View Log", force=True, ignore_missing=True)
	frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabTIQN Payslip View Log`")
	frappe.clear_cache(doctype=PAYSLIP)
