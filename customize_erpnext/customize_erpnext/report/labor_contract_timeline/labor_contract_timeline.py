# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""One row per employee: the four contract stages side by side plus appendices — HR's
"who has to sign what, and when" view (the layout of their tracking workbook)."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import date_diff, getdate

from customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract import (
	APPENDIX,
	CONTRACT_SUFFIX,
	business_today,
	leaves_before,
)

STAGES = ("HD", "HD1", "HD2", "HD3")
UNSIGNED = ("Upcoming", "Overdue")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	columns = [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link",
		 "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data",
		 "width": 180},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link",
		 "options": "Designation", "width": 140},
		{"fieldname": "custom_section", "label": _("Section"), "fieldtype": "Link",
		 "options": "Section", "width": 110},
		{"fieldname": "custom_group", "label": _("Group"), "fieldtype": "Link",
		 "options": "Group", "width": 110},
		{"fieldname": "date_of_joining", "label": _("Date of Joining"), "fieldtype": "Date",
		 "width": 105},
	]
	for stage in STAGES:
		columns.append({"fieldname": f"{stage}_start", "label": _("{0} From").format(stage),
						"fieldtype": "Date", "width": 100})
		if stage != "HD3":
			columns.append({"fieldname": f"{stage}_end", "label": _("{0} To").format(stage),
							"fieldtype": "Date", "width": 100})
		columns.append({"fieldname": f"{stage}_status", "label": _("{0} Status").format(stage),
						"fieldtype": "Data", "width": 90})
	columns += [
		{"fieldname": "appendices", "label": _("Appendices"), "fieldtype": "Int", "width": 95},
		{"fieldname": "unsigned_appendices", "label": _("Unsigned Appendices"),
		 "fieldtype": "Int", "width": 95},
		{"fieldname": "next_sign_date", "label": _("Next Sign Date"), "fieldtype": "Date",
		 "width": 110},
		{"fieldname": "next_document", "label": _("Next Document"), "fieldtype": "Data",
		 "width": 150},
		{"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 85},
		{"fieldname": "relieving_date", "label": _("Relieving Date"), "fieldtype": "Date",
		 "width": 105},
	]
	return columns


def _employees(filters, today):
	conditions = ["1 = 1"]
	values = {"today": today}
	# An unchecked Check filter is not sent at all, so test truthiness
	if filters.get("active_only"):
		conditions.append(
			"emp.status = 'Active' AND (emp.relieving_date IS NULL OR emp.relieving_date > %(today)s)"
		)
	for field in ("employee", "custom_section", "custom_group"):
		if filters.get(field):
			column = "name" if field == "employee" else field
			conditions.append(f"emp.{column} = %({field})s")
			values[field] = filters[field]

	return frappe.db.sql(
		f"""
		SELECT emp.name AS employee, emp.employee_name, emp.designation, emp.custom_section,
			emp.custom_group, emp.date_of_joining, emp.relieving_date
		FROM `tabEmployee` emp
		WHERE {" AND ".join(conditions)}
			AND EXISTS (SELECT 1 FROM `tabLabor Contract` lc WHERE lc.employee = emp.name)
		ORDER BY emp.name
		""",
		values, as_dict=True,
	)


def get_data(filters):
	today = getdate(business_today())
	employees = _employees(filters, today)
	if not employees:
		return []

	documents = defaultdict(list)
	for doc in frappe.db.sql(
		"""
		SELECT name, employee, document_type, contract_type, start_date, end_date, status,
			next_sign_date, next_contract_type, next_stage_created
		FROM `tabLabor Contract`
		WHERE employee IN %(employees)s
		ORDER BY start_date, creation
		""",
		{"employees": [e.employee for e in employees]}, as_dict=True,
	):
		documents[doc.employee].append(doc)

	rows = []
	for emp in employees:
		row = frappe._dict(emp)
		docs = documents.get(emp.employee, [])
		appendices = [d for d in docs if d.document_type == APPENDIX]
		contracts = [d for d in docs if d.document_type != APPENDIX]

		# Later documents of the same stage (a re-signed -2) overwrite earlier ones
		for doc in contracts:
			stage = CONTRACT_SUFFIX.get(doc.contract_type)
			if stage:
				row[f"{stage}_start"] = doc.start_date
				row[f"{stage}_end"] = doc.end_date
				row[f"{stage}_status"] = doc.status

		row.appendices = len(appendices)
		row.unsigned_appendices = sum(1 for d in appendices if d.status in UNSIGNED)

		# Next thing to sign: the earliest unsigned document; otherwise the stage after
		# the latest contract, unless the employee leaves before it starts.
		pending = [
			d for d in docs
			if d.status in UNSIGNED and not leaves_before(emp.relieving_date, d.start_date)
		]
		if pending:
			row.next_sign_date = pending[0].start_date
			row.next_document = pending[0].name
		elif contracts:
			last = contracts[-1]
			if (
				last.next_sign_date and not last.next_stage_created
				and not leaves_before(emp.relieving_date, last.next_sign_date)
			):
				row.next_sign_date = last.next_sign_date
				row.next_document = CONTRACT_SUFFIX.get(last.next_contract_type) or ""
		if row.next_sign_date:
			row.days_left = date_diff(row.next_sign_date, today)

		if filters.get("needs_signing") and not pending:
			continue
		rows.append(row)

	if filters.get("needs_signing") or filters.get("sort_by_next_sign_date"):
		rows.sort(key=lambda r: (r.next_sign_date is None, r.next_sign_date or today, r.employee))
	return rows
