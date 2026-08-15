# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt
"""Print the paper "GIẤY YÊU CẦU XÁC NHẬN CÔNG" form from Attendance Requests.

One A4 page per Employee.custom_group, because that is how the paper form works:
a single sheet is signed by one team leader for several employees at once. A
standard Print Format cannot do this — it renders one document at a time, while
one sheet spans many Attendance Requests.
"""

import base64
import json
import os
from collections import OrderedDict
from functools import lru_cache

import frappe
from frappe import _
from frappe.utils import format_date, get_datetime, getdate, now_datetime

from customize_erpnext.overrides.attendance_request.bulk_create import PAPER_REASON_INDEX

LOGO_PATH = "customize_erpnext/public/images/logo_500.jpg"


@lru_cache(maxsize=1)
def _logo_base64() -> str:
	"""Company logo inlined as base64.

	wkhtmltopdf runs outside the request, so an /assets/... URL is not reachable
	and a file:// path is blocked by default — embedding is the reliable route.
	Declared once in the stylesheet so it is not repeated per page.
	"""
	path = os.path.join(frappe.get_app_path("customize_erpnext"), "..", LOGO_PATH)
	path = os.path.normpath(path)
	if not os.path.exists(path):
		frappe.log_error(title="Attendance confirmation form: logo not found", message=path)
		return ""
	with open(path, "rb") as f:
		return base64.b64encode(f.read()).decode()


@frappe.whitelist()
def download_confirmation_forms(names: str | list) -> None:
	"""Build one PDF holding every group's sheet and push it as a download."""
	frappe.has_permission("Attendance Request", throw=True)

	if isinstance(names, str):
		names = json.loads(names)
	if not names:
		frappe.throw(_("No Attendance Request selected."))

	# Re-read the names through a permission-checked query. build_pages() uses
	# frappe.get_all, which skips permissions, and this endpoint accepts arbitrary
	# names — without this an employee could print a colleague's sheet, complete
	# with their name, title and working hours. get_list applies role and User
	# Permission filters, so HR keeps seeing everything.
	names = frappe.get_list(
		"Attendance Request",
		filters={"name": ("in", names)},
		pluck="name",
		order_by="name asc",
	)
	if not names:
		frappe.throw(_("You are not permitted to print the selected requests."))

	pages = build_pages(names)
	if not pages:
		frappe.throw(_("The selected requests have no check in/out rows to print."))

	html = frappe.render_template(
		"customize_erpnext/overrides/attendance_request/confirmation_form.html",
		{"pages": pages, "logo_b64": _logo_base64()},
	)

	from frappe.utils.pdf import get_pdf

	pdf = get_pdf(
		html,
		options={
			"page-size": "A4",
			"orientation": "Portrait",
			"margin-top": "10mm",
			"margin-bottom": "8mm",
			"margin-left": "10mm",
			"margin-right": "10mm",
			"encoding": "UTF-8",
		},
	)

	# Quy ước app: file dữ liệu tải về luôn có hậu tố thời điểm xuất
	stamp = now_datetime().strftime("%y%m%d %H%M%S")
	frappe.local.response.filename = f"Attendance Confirmation Forms {stamp}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"


def _default_company() -> str | None:
	"""Fallback only — the company normally comes off the Attendance Request."""
	return frappe.db.get_single_value("Global Defaults", "default_company")


def build_pages(names: list) -> list:
	"""Group the requests' rows into one page dict per custom_group."""
	requests = frappe.get_all(
		"Attendance Request",
		filters={"name": ("in", names)},
		fields=["name", "employee", "employee_name", "reason", "explanation", "company"],
		order_by="employee asc",
	)
	if not requests:
		return []

	employees = list({r.employee for r in requests})
	emp_info = {
		e.name: e
		for e in frappe.get_all(
			"Employee",
			filters={"name": ("in", employees)},
			fields=["name", "employee_name", "designation", "department", "custom_group"],
			order_by="name asc",
		)
	}

	details = frappe.get_all(
		"Attendance Request Checkin Detail",
		filters={"parent": ("in", [r.name for r in requests])},
		fields=[
			"parent",
			"date",
			"new_in_time",
			"new_out_time",
			"existing_in_time",
			"existing_out_time",
			"remark",
		],
		order_by="date asc",
	)
	details_by_parent = {}
	for d in details:
		details_by_parent.setdefault(d.parent, []).append(d)

	groups = OrderedDict()
	for req in requests:
		emp = emp_info.get(req.employee) or frappe._dict()
		for row in details_by_parent.get(req.name, []):
			if not (row.new_in_time or row.new_out_time):
				continue  # nothing supplemented on that date — not on the paper

			key = (emp.get("department") or "", emp.get("custom_group") or "")
			page = groups.setdefault(
				key,
				{
					"department": emp.get("department"),
					"group": emp.get("custom_group"),
					"company": req.company or _default_company(),
					"print_date": format_date(getdate(), "dd/MM/yyyy"),
					"rows": [],
					"reasons": set(),
					"other_reason": None,
				},
			)
			page["reasons"].add(req.reason)
			if req.reason in ("Other", "First Working Day") and req.explanation:
				page["other_reason"] = req.explanation

			cells = _in_out_cells(row)
			page["rows"].append(
				{
					"employee": req.employee,
					"employee_name": req.employee_name or emp.get("employee_name"),
					"designation": emp.get("designation"),
					"date": format_date(row.date, "dd/MM/yyyy"),
					**cells,
					"remark": row.remark,
				}
			)

	pages = []
	for page in groups.values():
		reasons = page.pop("reasons")
		# Mixed reasons on one sheet cannot all be ticked; fall back to "other"
		page["reason_index"] = (
			PAPER_REASON_INDEX.get(next(iter(reasons)), 3) if len(reasons) == 1 else 3
		)
		pages.append(page)

	pages.sort(key=lambda p: (p["department"] or "zzz", p["group"] or "zzz"))
	return pages


def _in_out_cells(row) -> dict:
	"""Earliest time of the day -> "Giờ vào", latest -> "Giờ ra".

	Cannot simply print existing_in_time as the IN column: when the day has a
	single scan the attendance engine always stores it in `in_time`, even when
	that scan was really a check OUT (employee forgot to scan in). Printing it as
	the IN would drop the only real time the employee has, on the very sheet they
	are asked to sign. Sorting every known time fixes both directions.

	Times are "HH:MM" strings, so a lexical sort is chronological.
	"""
	times = []
	for value in (row.existing_in_time, row.existing_out_time):
		if value:
			times.append((str(value)[:5], False))
	for value in (row.new_in_time, row.new_out_time):
		if value:
			times.append((_fmt_time(value), True))

	if not times:
		return {"in_time": None, "out_time": None, "in_supplemented": False, "out_supplemented": False}

	times.sort(key=lambda x: x[0])
	first, last = times[0], times[-1]

	if len(times) == 1:
		return {
			"in_time": first[0],
			"out_time": None,
			"in_supplemented": first[1],
			"out_supplemented": False,
		}

	return {
		"in_time": first[0],
		"out_time": last[0],
		"in_supplemented": first[1],
		"out_supplemented": last[1],
	}


def _fmt_time(value) -> str:
	total = int(value.total_seconds()) if hasattr(value, "total_seconds") else None
	if total is not None:
		return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
	return get_datetime(str(value)).strftime("%H:%M")
