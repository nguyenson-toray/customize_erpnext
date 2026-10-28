# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""One pay period: how many payslips are published, how many employees opened theirs,
and the main figures per employee."""

import frappe
from frappe import _
from frappe.utils import flt

from customize_erpnext.employee_portal.utils import validate_period

# Main figures of the payslip: TIQN Payslip columns filled from the lines that carry a
# Report Column in the Payslip Structure (28/10/2026) - the same whatever the lines are.
MAIN_FIELDS = ("basic_pay", "overtime_pay", "gross_pay", "total_deductions", "net_pay")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	try:
		period = validate_period(filters.period)
	except frappe.ValidationError:
		frappe.throw(_("Period must look like YYYY-MM."))

	meta = frappe.get_meta("TIQN Payslip")
	main = [(f, _(meta.get_label(f))) for f in MAIN_FIELDS]

	conditions = {"period": period}
	if filters.status:
		conditions["status"] = filters.status
	if filters.viewed:
		conditions["first_viewed_on"] = ["is", "set" if filters.viewed == "Viewed" else "not set"]
	if filters.final_settlement:
		conditions["final_settlement"] = 1 if filters.final_settlement == "Yes" else 0
	rows = frappe.get_all(
		"TIQN Payslip",
		filters=conditions,
		fields=[
			"name", "employee", "employee_name", "designation", "department", "section", "group", "status",
			"final_settlement", "period_from", "period_to", "pay_date", "published_on", "first_viewed_on",
		]
		+ [f for f, _l in main],
		order_by="employee",
	)
	for no, r in enumerate(rows, start=1):
		r.no = no

	columns = [
		{"fieldname": "no", "label": _("No."), "fieldtype": "Int", "width": 55},
		{"fieldname": "name", "label": _("Payslip"), "fieldtype": "Link", "options": "TIQN Payslip", "width": 150},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 105},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Data", "width": 140},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Data", "width": 120},
		{"fieldname": "section", "label": _("Section"), "fieldtype": "Data", "width": 100},
		{"fieldname": "group", "label": _("Group"), "fieldtype": "Data", "width": 100},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "final_settlement", "label": _("Final Settlement"), "fieldtype": "Check", "width": 80},
		{"fieldname": "period_from", "label": _("Period From"), "fieldtype": "Date", "width": 95},
		{"fieldname": "period_to", "label": _("Period To"), "fieldtype": "Date", "width": 95},
		{"fieldname": "pay_date", "label": _("Pay Date"), "fieldtype": "Date", "width": 95},
	]
	columns += [
		{"fieldname": f, "label": label, "fieldtype": "Currency", "options": "currency", "precision": 0, "width": 130}
		for f, label in main
	]
	columns += [
		{"fieldname": "published_on", "label": _("Published On"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "first_viewed_on", "label": _("First Viewed On"), "fieldtype": "Datetime", "width": 150},
	]
	for r in rows:
		r.currency = "VND"

	published = [r for r in rows if r.status == "Published"]
	viewed = sum(1 for r in published if r.first_viewed_on)
	summary = [
		{"label": _("Published"), "value": len(published), "indicator": "green"},
		{"label": _("Viewed"), "value": viewed, "indicator": "blue"},
		{"label": _("Not Viewed"), "value": len(published) - viewed, "indicator": "orange"},
		{
			"label": _("% Viewed"),
			"value": f"{round(100 * viewed / len(published))}%" if published else "-",
			"indicator": "blue",
		},
		{"label": _("Draft"), "value": sum(1 for r in rows if r.status == "Draft"), "indicator": "gray"},
		{"label": _("Final Settlement"), "value": sum(1 for r in rows if r.final_settlement), "indicator": "gray"},
		{
			"label": _("Total Net Pay"),
			"value": sum(flt(r.net_pay) for r in rows),
			"datatype": "Currency",
			"currency": "VND",
			"indicator": "green",
		},
	]
	return columns, rows, None, None, summary
