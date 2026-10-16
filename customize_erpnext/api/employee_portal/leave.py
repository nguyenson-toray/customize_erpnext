# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Leave endpoints - API_CONTRACT.md §8 (read side; creating / cancelling is M3)."""

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

from customize_erpnext.api.employee_portal.core import PortalError, ctx, fmt_date, fmt_datetime, portal_api
from customize_erpnext.api.employee_portal.notifications import paging
from customize_erpnext.employee_portal.attendance_data import annual_leave_types, leave_balances, leave_type_label
from customize_erpnext.employee_portal.documents import attachments, document_payload, verify
from customize_erpnext.employee_portal.requests_common import (
	DOCUMENT_LEAVE_TYPES,
	leave_status,
	person,
	status_label,
)

LA_FIELDS = [
	"name",
	"leave_type",
	"from_date",
	"to_date",
	"half_day",
	"half_day_date",
	"total_leave_days",
	"status",
	"docstatus",
	"creation",
	"owner",
]


def _has_field(fieldname):
	return frappe.get_meta("Leave Application").has_field(fieldname)


def _source(row):
	value = row.get("custom_source") if _has_field("custom_source") else None
	if value:
		return "MINI_APP" if value == "Mini App" else "DESK"
	return "MINI_APP" if row.get("owner") == "portal@tiqn.com.vn" else "DESK"


def _list_item(r, doc_counts):
	status = leave_status(r.status, r.docstatus)
	return {
		"id": r.name,
		"leave_type": r.leave_type,
		"leave_type_label": leave_type_label(r.leave_type),
		"from_date": fmt_date(r.from_date),
		"to_date": fmt_date(r.to_date),
		"half_day": bool(r.half_day),
		"half_day_date": fmt_date(r.half_day_date) if r.half_day else None,
		"days": r.total_leave_days,
		"status": status,
		"status_label": status_label(status),
		"needs_documents": bool(r.get("custom_needs_documents")),
		"document_count": doc_counts.get(r.name, 0),
		"source": _source(r),
		"created_at": fmt_datetime(r.creation),
	}


@portal_api(methods=("GET",), feature="leave_view")
def get_leave_balances(year=None):
	employee = ctx().employee
	current_year = getdate(nowdate()).year
	year = cint(year) or current_year
	on_date = nowdate() if year == current_year else f"{year}-12-25"
	balances = leave_balances(employee, on_date)

	annual = None
	for leave_type in annual_leave_types():
		if leave_type in balances:
			annual = {"leave_type": leave_type, "label": leave_type_label(leave_type), **balances[leave_type]}
			break
	others = [
		{"leave_type": lt, "label": leave_type_label(lt), "balance": None, "note": _("Per medical documents", context="Portal")}
		for lt in DOCUMENT_LEAVE_TYPES
	]
	return {"year": year, "annual": annual, "others": others}


@portal_api(methods=("GET",), feature="leave_view")
def get_leave_applications(year=None, status=None, page=None, page_size=None):
	employee = ctx().employee
	year = cint(year) or getdate(nowdate()).year
	page, page_size = paging(page, page_size)
	fields = list(LA_FIELDS)
	for extra in ("custom_source", "custom_needs_documents"):
		if _has_field(extra):
			fields.append(extra)
	rows = frappe.get_all(
		"Leave Application",
		filters={"employee": employee, "from_date": ["between", [f"{year}-01-01", f"{year}-12-31"]]},
		fields=fields,
		order_by="from_date desc, creation desc",
	)
	years = sorted(
		{getdate(d).year for d in frappe.get_all("Leave Application", {"employee": employee}, pluck="from_date")}
		| {getdate(nowdate()).year},
		reverse=True,
	)
	counts = {"ALL": len(rows), "PENDING": 0, "APPROVED": 0, "REJECTED": 0, "CANCELLED": 0}
	for r in rows:
		counts[leave_status(r.status, r.docstatus)] += 1
	wanted = (status or "").strip().upper()
	if wanted:
		if wanted not in counts or wanted == "ALL":
			raise PortalError("VALIDATION", _("Unknown status {0}.").format(status), field="status")
		rows = [r for r in rows if leave_status(r.status, r.docstatus) == wanted]

	page_rows = rows[(page - 1) * page_size : page * page_size]
	doc_counts = {}
	if page_rows:
		for r in frappe.db.sql(
			"""SELECT attached_to_name, COUNT(*) n FROM `tabFile`
			   WHERE attached_to_doctype='Leave Application' AND attached_to_name IN %s GROUP BY attached_to_name""",
			[tuple(r.name for r in page_rows)],
			as_dict=True,
		):
			doc_counts[r.attached_to_name] = r.n
	return {
		"years_available": years,
		"counts": counts,
		"items": [_list_item(r, doc_counts) for r in page_rows],
		"page": page,
		"page_size": page_size,
		"has_more": len(rows) > page * page_size,
	}


def leave_detail(name):
	"""LeaveApplicationDetail of the caller's application `name` (NOT_FOUND otherwise)."""
	c = ctx()
	doc = frappe.db.get_value("Leave Application", name, "*", as_dict=True) if name else None
	if not doc or doc.employee != c.employee:
		raise PortalError("NOT_FOUND", _("Not found."))

	status = leave_status(doc.status, doc.docstatus)
	files = attachments("Leave Application", doc.name)
	allows_documents = doc.leave_type in DOCUMENT_LEAVE_TYPES
	source = _source(doc)
	needs_documents = bool(doc.get("custom_needs_documents"))
	documents_note = doc.get("custom_documents_request_note")
	approver_note = doc.get("custom_approver_note")
	approver = person(doc.leave_approver)
	max_files = cint(frappe.db.get_single_value("Employee Portal Settings", "max_files")) or 5

	timeline = [
		{"event": "SUBMITTED", "label": _("Submitted", context="Portal"), "at": fmt_datetime(doc.creation), "by": None, "note": None, "done": True}
	]
	if needs_documents:
		timeline.append(
			{"event": "DOCUMENTS_REQUESTED", "label": _("Documents requested", context="Portal"), "at": None,
			 "by": approver["full_name"] if approver else None, "note": documents_note, "done": True}
		)
	decided_by = frappe.utils.get_fullname(doc.modified_by) if doc.modified_by else None
	if status == "PENDING":
		timeline.append(
			{"event": "UNDER_REVIEW", "label": _("Under review", context="Portal"), "at": None,
			 "by": approver["full_name"] if approver else None, "note": None, "done": False}
		)
	else:
		event = {"APPROVED": "APPROVED", "REJECTED": "REJECTED", "CANCELLED": "CANCELLED"}[status]
		timeline.append(
			{"event": event, "label": status_label(status), "at": fmt_datetime(doc.modified), "by": decided_by,
			 "note": approver_note, "done": True}
		)

	editable = not c.read_only and status == "PENDING" and doc.docstatus == 0
	return {
		"id": doc.name,
		"leave_type": doc.leave_type,
		"leave_type_label": leave_type_label(doc.leave_type),
		"from_date": fmt_date(doc.from_date),
		"to_date": fmt_date(doc.to_date),
		"half_day": bool(doc.half_day),
		"half_day_date": fmt_date(doc.half_day_date) if doc.half_day else None,
		"days": doc.total_leave_days,
		"reason": doc.description,
		"status": status,
		"status_label": status_label(status),
		"source": source,
		"created_at": fmt_datetime(doc.creation),
		"approver": approver,
		"needs_documents": needs_documents,
		"documents_request_note": documents_note,
		"approver_note": approver_note,
		"timeline": timeline,
		"documents": [document_payload(f, c.employee, can_delete=editable) for f in files],
		"allows_documents": allows_documents,
		"can_cancel": editable and source == "MINI_APP",
		"can_add_documents": bool(
			allows_documents and not c.read_only and status in ("PENDING", "APPROVED") and len(files) < max_files
		),
	}


@portal_api(methods=("GET",), feature="leave_view")
def get_leave_application(id=None):
	return leave_detail(id)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def download_document(sig=None):
	"""Stream a private attachment named by a signed link (documents.sign). No token:
	the signature replaces it and expires after 10 minutes."""
	checked = verify(sig)
	if not checked:
		raise frappe.PermissionError
	file_name, employee = checked
	f = frappe.get_doc("File", file_name)
	# The file must still belong to one of that employee's own requests.
	owner_employee = None
	if f.attached_to_doctype in ("Leave Application", "Attendance Request") and f.attached_to_name:
		owner_employee = frappe.db.get_value(f.attached_to_doctype, f.attached_to_name, "employee")
	if owner_employee != employee:
		raise frappe.PermissionError
	frappe.local.response.filename = f.file_name
	frappe.local.response.filecontent = f.get_content()
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"
