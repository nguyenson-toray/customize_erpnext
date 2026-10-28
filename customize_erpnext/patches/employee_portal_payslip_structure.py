"""Payslip Structure (28/10/2026, employee_portal/payslip_structure.py).

1. When no structure exists: PSS-<first payslip period> = the lines the payslip had so far -
   the `sc_*` fields of TIQN Payslip (code, units, parent), Settings > Payslip Lines (Mini
   App text and formula letters), the fixed groups of utils (row type, block) and the
   main lines as Report Columns (1 Basic, 2 Overtime, 5 Gross, 6 Deductions, 9 Net,
   1.1 Standard Days, 1.2 Actual Days, 2.x OT Hours).
2. Every payslip without `lines_json`: its snapshot from its `sc_*` values, the report
   columns and `content_version`. modified / published_on untouched.

The `sc_*` fields stay (hidden, no longer read) until phase 2. Idempotent.
"""

import re

import frappe
from frappe.utils import today

from customize_erpnext.employee_portal import payslip_structure as pss
from customize_erpnext.employee_portal.utils import (
	SECTION_TOTALS,
	SUBTOTALS,
	payslip_component_fields,
	period_of_date,
	shift_period,
	strip_code_formula,
)

FORMULA_LETTERS = re.compile(r"\(\s*([a-j](?:\s*=\s*[a-j](?:\s*[+-]\s*[a-j])*)?)\s*\)")
REPORT_KEYS = {
	"1": "Basic", "2": "Overtime", "5": "Gross", "6": "Deductions", "9": "Net",
	"1.1": "Standard Days", "1.2": "Actual Days", "2.1": "OT Hours", "2.2": "OT Hours", "2.3": "OT Hours",
}


def lines_from_fields(components=None):
	out = []
	for c in components or payslip_component_fields():
		m = FORMULA_LETTERS.search(c.display_label or "") or FORMULA_LETTERS.search(c.name or "")
		out.append(
			frappe._dict(
				code=str(c.abbr),
				label_en=strip_code_formula(c.name) or c.name,
				label_vi=strip_code_formula(c.display_label) or c.display_label,
				formula_display="".join(m.group(1).split()) if m else None,
				unit=c.unit or "VND",
				quantity_unit=c.qty_unit or None,
				parent_code=c.parent_code or None,
				row_type="Section Total" if c.abbr in SECTION_TOTALS else "Subtotal" if c.abbr in SUBTOTALS else "Line",
				section=c.section,
				report_key=REPORT_KEYS.get(str(c.abbr)),
			)
		)
	return out


def values_from_fields(doc, components):
	values = {}
	for c in components:
		v = {}
		if (c.unit or "VND") == "VND":
			v["amount"] = doc.get(c.fieldname)
			if c.qty_fieldname:
				v["quantity"] = doc.get(c.qty_fieldname)
		else:  # days / hours only (1.1): the field holds the days
			v["quantity"] = doc.get(c.fieldname)
		values[str(c.abbr)] = v
	return values


def execute():
	for dt in ("tiqn_payslip_structure_line", "tiqn_payslip_structure", "tiqn_payslip"):
		frappe.reload_doc("employee_portal", "doctype", dt)
	components = payslip_component_fields()
	if not components:
		return

	if not frappe.db.count(pss.STRUCTURE_DT):
		periods = frappe.get_all("TIQN Payslip", pluck="period", distinct=True)
		valid_from = min(periods) if periods else shift_period(period_of_date(today()), -1)
		frappe.get_doc(
			{
				"doctype": pss.STRUCTURE_DT,
				"valid_from": valid_from,
				"description": "Lines of the payslip before Payslip Structures existed (TIQN Payslip fields + Settings > Payslip Lines).",
				"lines": lines_from_fields(components),
			}
		).insert(ignore_permissions=True)

	fields = ["name", "period"] + [f for c in components for f in (c.fieldname, c.qty_fieldname) if f]
	for doc in frappe.get_all("TIQN Payslip", {"lines_json": ("is", "not set")}, fields):
		structure = pss.structure_for_period(doc.period)
		if not structure:
			continue
		snapshot = pss.make_snapshot(pss.structure_lines(structure), values_from_fields(doc, components))
		frappe.db.set_value(
			"TIQN Payslip",
			doc.name,
			{
				"structure": structure,
				"lines_json": pss.dump_snapshot(snapshot),
				"content_version": pss.content_version(snapshot),
				**pss.key_values(snapshot),
			},
			update_modified=False,
		)
