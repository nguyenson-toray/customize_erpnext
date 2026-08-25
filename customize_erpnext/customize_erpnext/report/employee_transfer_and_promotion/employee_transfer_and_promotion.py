# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt
"""Employee Transfer and Promotion — one row per property change.

Both doctypes keep their changes in the same child table (Employee Property History),
so the two are read with one UNION and shown side by side.

Grain is one row per CHANGED PROPERTY, not one row per document: a single transfer that
moves both Group and Designation produces two rows sharing the same Document. That keeps
"From" / "To" meaningful and lets HR filter on Property.

The join is a LEFT JOIN on purpose. A document with no property rows at all is a real
failure mode here — an import that filled only the `Property` label column leaves
`fieldname` empty, and such a document submits without changing anything. Those rows show
up with an empty Property instead of silently vanishing from the report.
"""

import frappe
from frappe import _
from frappe.utils import get_year_start, getdate, nowdate

# filter value -> doctype, date field
SOURCES = {
	"Transfer": ("Employee Transfer", "transfer_date", "transfer_details"),
	"Promotion": ("Employee Promotion", "promotion_date", "promotion_details"),
}

DOCSTATUS_LABEL = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "document_type", "label": _("Type"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "document",
			"label": _("Document"),
			"fieldtype": "Dynamic Link",
			"options": "document_type",
			"width": 190,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 110,
		},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 190},
		{
			"fieldname": "department",
			"label": _("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": 150,
		},
		{"fieldname": "property", "label": _("Property"), "fieldtype": "Data", "width": 140},
		{"fieldname": "from_value", "label": _("From"), "fieldtype": "Data", "width": 160},
		{"fieldname": "to_value", "label": _("To"), "fieldtype": "Data", "width": 160},
	]


def get_data(filters):
	from_date = getdate(filters.from_date or get_year_start(nowdate()))
	to_date = getdate(filters.to_date or nowdate())
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date"))

	wanted = [filters.type] if filters.type else list(SOURCES)

	rows = []
	for key in wanted:
		doctype, date_field, table_field = SOURCES[key]
		rows += _fetch(doctype, date_field, table_field, from_date, to_date, filters)

	rows.sort(key=lambda r: (r["date"], r["document"], r["idx"]), reverse=True)

	labels = _property_labels()
	for row in rows:
		row["status"] = DOCSTATUS_LABEL.get(row.pop("docstatus"), "")
		row.pop("idx", None)
		# `fieldname` vẫn nằm trong data (formatter dùng để tô đỏ dòng không đổi gì)
		# nhưng không còn là một cột hiển thị.
		row["property"] = labels.get(row.get("fieldname")) or row.get("property")

	return rows


def _property_labels() -> dict:
	"""fieldname -> nhãn chuẩn của field trên Employee.

	Không đọc cột `property` của phiếu vì đó là nhãn do người import gõ tay: file nhập
	ngày 2026-08-25 ghi "Desination" cho 25 dòng.
	"""
	meta = frappe.get_meta("Employee")
	return {df.fieldname: _(df.label) for df in meta.fields if df.label}


def _fetch(doctype, date_field, table_field, from_date, to_date, filters):
	conditions = ["d.`{0}` between %(from_date)s and %(to_date)s".format(date_field)]
	values = {
		"from_date": from_date,
		"to_date": to_date,
		"doctype": doctype,
		"table_field": table_field,
	}

	if filters.employee:
		conditions.append("d.employee = %(employee)s")
		values["employee"] = filters.employee

	if filters.status:
		conditions.append("d.docstatus = %(docstatus)s")
		values["docstatus"] = next(k for k, v in DOCSTATUS_LABEL.items() if v == filters.status)
	else:
		# Cancelled documents are noise unless explicitly asked for.
		conditions.append("d.docstatus < 2")

	return frappe.db.sql(
		"""
		select
			d.`{date_field}`		as `date`,
			%(doctype)s				as document_type,
			d.name					as document,
			d.docstatus				as docstatus,
			d.employee				as employee,
			d.employee_name			as employee_name,
			d.department			as department,
			h.property				as property,
			h.fieldname				as fieldname,
			h.current				as from_value,
			h.new					as to_value,
			ifnull(h.idx, 0)		as idx
		from `tab{doctype}` d
		left join `tabEmployee Property History` h
			on h.parent = d.name
			and h.parenttype = %(doctype)s
			and h.parentfield = %(table_field)s
		where {conditions}
		""".format(
			date_field=date_field,
			doctype=doctype,
			conditions=" and ".join(conditions),
		),
		values,
		as_dict=True,
	)
