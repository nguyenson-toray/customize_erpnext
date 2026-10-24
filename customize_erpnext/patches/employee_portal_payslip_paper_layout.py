# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Payslip in the order of the paper payslip (24/10/2026) - post_model_sync, idempotent.

The paper payslip is one list 1 -> 9 with two value columns: Unit/ĐVT and Amount.
1. Salary Component.custom_portal_qty_unit (created here: fixtures sync runs AFTER
   patches). Set = the line also has a Unit/ĐVT value, stored in `sc_<code>_qty`.
2. 1.2 and 2.1-2.3 were days/hours only; on paper they also carry an amount. Their
   number moves to `sc_<code>_qty` and the component becomes a VND line. 7.4 / 7.5 get
   a Unit/ĐVT value (days).
3. Parent lines as printed: 1.1-1.2 under 1, 2.1-2.3 under 2, 6.x under 6, 7.x under 7
   (only where no parent is set yet).
4. custom_portal_order = paper order (= code order: 1, 1.1, 1.2, 2, ... 3.10, 4, ... 9).
5. Mini App shows zero lines as "-" like the paper (show_zero_lines = 1).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from customize_erpnext.employee_portal.utils import component_fieldname, component_qty_fieldname

PAYSLIP = "TIQN Payslip"
QTY_UNITS = {"1.2": "Day", "2.1": "Hour", "2.2": "Hour", "2.3": "Hour", "7.4": "Day", "7.5": "Day"}
PARENTS = {"1": ["1.1", "1.2"], "2": ["2.1", "2.2", "2.3"], "6": [f"6.{i}" for i in range(1, 7)], "7": [f"7.{i}" for i in range(1, 8)]}


def execute():
	frappe.reload_doc("employee_portal", "doctype", "tiqn_payslip")
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "custom_portal_qty_unit",
					"label": "Portal Unit/ĐVT Value",
					"fieldtype": "Select",
					"options": "\nDay\nHour",
					"insert_after": "custom_portal_order",
					"description": "Set when the paper payslip shows a number in the Unit/ĐVT column next to the amount "
					"(e.g. 27 days for 1.2). Needs field sc_<code>_qty on TIQN Payslip",
				}
			]
		},
		update=False,
	)
	frappe.clear_cache(doctype="Salary Component")
	components = {
		r.abbr: r
		for r in frappe.get_all(
			"Salary Component",
			fields=["name", "salary_component_abbr as abbr", "custom_portal_unit as unit", "custom_portal_qty_unit as qty_unit",
				"custom_portal_parent as parent", "custom_portal_section as section"],
		)
		if r.abbr
	}
	columns = set(frappe.db.get_table_columns(PAYSLIP))

	for code, qty_unit in QTY_UNITS.items():
		c = components.get(code)
		if not c or c.qty_unit:
			continue
		values = {"custom_portal_qty_unit": qty_unit}
		if (c.unit or "VND") != "VND":
			amount, qty = component_fieldname(code), component_qty_fieldname(code)
			if amount in columns and qty in columns:
				frappe.db.sql(f"UPDATE `tab{PAYSLIP}` SET `{qty}` = `{amount}`, `{amount}` = 0")
			values["custom_portal_unit"] = "VND"
		frappe.db.set_value("Salary Component", c.name, values, update_modified=False)

	for parent_code, codes in PARENTS.items():
		parent = components.get(parent_code)
		if not parent:
			continue
		for code in codes:
			c = components.get(code)
			if c and not c.parent:
				frappe.db.set_value("Salary Component", c.name, "custom_portal_parent", parent.name, update_modified=False)

	for code, c in components.items():
		if c.section in (None, "", "Hidden"):
			continue
		parts = [int(p) for p in code.split(".") if p.isdigit()]
		if parts:
			order = parts[0] * 100 + (parts[1] if len(parts) > 1 else 0)
			frappe.db.set_value("Salary Component", c.name, "custom_portal_order", order, update_modified=False)

	frappe.db.set_single_value("Employee Portal Settings", "show_zero_lines", 1)
