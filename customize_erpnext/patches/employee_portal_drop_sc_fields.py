"""Payslip Structure phase 2 (28/10/2026): the lines live on TIQN Payslip Structure and
each payslip keeps its own copy (`lines_json`), so the hidden per-line fields go:

1. the `sc_*` columns of TIQN Payslip (the fields left the DocType JSON; Frappe keeps a
   column until it is dropped by hand);
2. Employee Portal Settings > Payslip Lines = child DocType TIQN Portal Payslip Line, and
   the Check Formulas on Import value.

Idempotent.
"""

import frappe

CHILD = "TIQN Portal Payslip Line"
SETTINGS = "Employee Portal Settings"


def execute():
	columns = [c for c in frappe.db.get_table_columns("TIQN Payslip") if c.startswith("sc_")]
	if columns:
		frappe.db.sql_ddl(
			"ALTER TABLE `tabTIQN Payslip` " + ", ".join(f"DROP COLUMN `{c}`" for c in columns)
		)

	if frappe.db.exists("DocType", CHILD):
		frappe.delete_doc("DocType", CHILD, force=True, ignore_missing=True)
	if frappe.db.table_exists(CHILD):
		frappe.db.sql_ddl(f"DROP TABLE `tab{CHILD}`")

	frappe.db.delete("Singles", {"doctype": SETTINGS, "field": ("in", ("validate_payslip_formulas", "payslip_lines"))})
	frappe.clear_cache(doctype="TIQN Payslip")
	frappe.clear_cache(doctype=SETTINGS)
