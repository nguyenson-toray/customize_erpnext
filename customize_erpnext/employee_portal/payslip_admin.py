# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Desk side of payslips: Excel template, upload (preview -> import as Draft),
publish and withdraw. Used by the `payslip-upload` page and the "Import from Excel"
button of the TIQN Payslip list. Payroll Officer only.

Excel layout (one row per employee; template since 15/10/2026):

    Period | Period From | Period To | Employee | Employee Name | Department | Section | Group | <44 components>

The older Vietnamese headers (Kỳ lương | MSNV | Họ tên | dept | custom_section |
custom_group) are still read. Period From / Period To are optional and only checked
against the period (26 -> 25): the payslip always stores the standard dates.

Component columns are matched by the leading code of the header
("3.2 Technical allowance/ Phụ cấp kỹ thuật" -> abbr "3.2"), so HR may keep the
long bilingual names, reorder columns or fix a typo in the text part.

Numbers are taken exactly as HR computed them. The formula checks below only WARN -
HR confirms and imports anyway; nothing is ever corrected automatically.
"""

import io
import re
import unicodedata

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime

from customize_erpnext.employee_portal.notify import notify
from customize_erpnext.employee_portal.utils import parse_period_cell, period_bounds, period_label

ROLES = ("Payroll Officer", "System Manager")
TOLERANCE = 1  # VND
QUEUE_THRESHOLD = 150

# Mirrors the letters of the TIQN payroll sheet: c=a+b, f=c+d+e, j=f-g+h+i.
FORMULAS = [
	("3", [("+", "1"), ("+", "2")]),
	("5", [("+", "3"), ("+", "3.1"), ("+", "4")]),
	("9", [("+", "5"), ("-", "6"), ("+", "7"), ("+", "8")]),
]
# Group total = sum of its detail lines (taken from custom_portal_parent).
GROUP_TOTALS = ["3.1", "4", "6", "7"]

IDENT_COLUMNS = {
	"period": ("ky luong", "ky", "period", "thang"),
	"period_from": ("period from", "tu ngay"),
	"period_to": ("period to", "den ngay"),
	"employee": ("msnv", "ma nv", "ma nhan vien", "employee", "employee id"),
	"employee_name": ("ho ten", "ho va ten", "ten", "employee name", "full name"),
	"department": ("dept", "department", "phong ban"),
	"section": ("custom_section", "section"),
	"group": ("custom_group", "group", "to"),
}
IGNORED_COLUMNS = ("stt", "no", "no.", "#")
TEMPLATE_IDENT = ("Period", "Period From", "Period To", "Employee", "Employee Name", "Department", "Section", "Group")
CODE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)(?=\s|$|/|\(|-)")


def _check_role():
	frappe.only_for(ROLES)


def _norm(text):
	text = unicodedata.normalize("NFD", str(text or "")).replace("đ", "d").replace("Đ", "D")
	text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
	return re.sub(r"\s+", " ", text).strip().lower()


def _components():
	"""Salary Components that belong on the payslip (everything not Hidden)."""
	rows = frappe.get_all(
		"Salary Component",
		filters={"custom_portal_section": ["not in", ["", "Hidden"]]},
		fields=["name", "salary_component_abbr as abbr", "custom_portal_order as sort_order", "custom_portal_parent as parent"],
	)
	rows.sort(key=lambda r: (cint(r.sort_order) or 9999, [int(p) for p in str(r.abbr).split(".") if p.isdigit()]))
	return rows


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def download_template():
	_check_role()
	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Font, PatternFill

	wb = Workbook()
	ws = wb.active
	ws.title = "Payslip"
	headers = list(TEMPLATE_IDENT)
	headers += [c.name for c in _components()]
	ws.append(headers)
	example_from, example_to = period_bounds("2026-10")
	ws.append(["2026-10", example_from, example_to, "TIQN-0001", "", "", "", ""] + [None] * (len(headers) - len(TEMPLATE_IDENT)))
	bold = Font(bold=True)
	fill = PatternFill("solid", fgColor="DDEBF7")
	for cell in ws[1]:
		cell.font = bold
		cell.fill = fill
		cell.alignment = Alignment(wrap_text=True, vertical="top")
	ws.row_dimensions[1].height = 60
	for i in range(1, len(headers) + 1):
		ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = 14 if i > len(TEMPLATE_IDENT) else 16
	ws.freeze_panes = ws.cell(row=2, column=len(TEMPLATE_IDENT) + 1).coordinate
	# Period and Employee must stay text, or Excel turns "10-2026" into a date and
	# "0148" into 148; Period From / To are real dates.
	for row in ws.iter_rows(min_row=2, max_row=1000):
		row[0].number_format = row[3].number_format = "@"
		row[1].number_format = row[2].number_format = "yyyy-mm-dd"

	out = io.BytesIO()
	wb.save(out)
	frappe.response["filename"] = "payslip_template.xlsx"
	frappe.response["filecontent"] = out.getvalue()
	frappe.response["type"] = "binary"


# ---------------------------------------------------------------------------
# Parse + validate
# ---------------------------------------------------------------------------
def _read_rows(file_url):
	from openpyxl import load_workbook

	file_doc = frappe.get_doc("File", {"file_url": file_url})
	if not (file_doc.file_name or "").lower().endswith(".xlsx"):
		frappe.throw(_("Please upload an .xlsx file."))
	wb = load_workbook(io.BytesIO(file_doc.get_content()), read_only=True, data_only=True)
	ws = wb.worksheets[0]
	return [list(r) for r in ws.iter_rows(values_only=True)]


def _find_header(rows):
	for i, row in enumerate(rows[:20]):
		names = {_norm(c) for c in row if c not in (None, "")}
		if names & set(IDENT_COLUMNS["employee"]):
			return i
	frappe.throw(_("Could not find the header row. It must contain an MSNV column."))


def _map_columns(header, components):
	by_abbr = {str(c.abbr).strip(): c for c in components}
	mapping = {"ident": {}, "components": {}}
	errors, seen_abbr = [], {}
	for idx, raw in enumerate(header):
		if raw in (None, ""):
			continue
		norm = _norm(raw)
		ident = next((k for k, names in IDENT_COLUMNS.items() if norm in names), None)
		if ident and ident not in mapping["ident"]:
			mapping["ident"][ident] = idx
			continue
		if norm in IGNORED_COLUMNS:
			continue
		m = CODE_RE.match(str(raw))
		comp = by_abbr.get(m.group(1)) if m else None
		if not comp:
			errors.append(_("Column \"{0}\" does not match any payslip Salary Component.").format(raw))
			continue
		if comp.abbr in seen_abbr:
			errors.append(
				_("Columns \"{0}\" and \"{1}\" are both component {2}.").format(seen_abbr[comp.abbr], raw, comp.abbr)
			)
			continue
		seen_abbr[comp.abbr] = raw
		mapping["components"][idx] = comp
	for required in ("period", "employee"):
		if required not in mapping["ident"]:
			errors.append(_("Missing column {0}.").format({"period": "Kỳ lương", "employee": "MSNV"}[required]))
	missing = [c.name for c in components if c.abbr not in seen_abbr]
	return mapping, errors, missing


def _resolve_employee(value, cache):
	text = str(value or "").strip()
	if isinstance(value, float) and value.is_integer():
		text = str(int(value))
	if not text:
		return None
	if text in cache:
		return cache[text]
	name = text if frappe.db.exists("Employee", text) else None
	if not name and text.isdigit():
		guess = f"TIQN-{int(text):04d}"
		name = guess if frappe.db.exists("Employee", guess) else None
	cache[text] = name
	return name


def _date_cell(value):
	"""A Period From / To cell -> date, None when empty, False when unreadable."""
	if value in (None, ""):
		return None
	try:
		return getdate(value)
	except Exception:
		return False


def _number(value):
	if value in (None, ""):
		return 0.0, True
	if isinstance(value, (int, float)):
		return float(value), True
	text = str(value).strip().replace(",", "")
	try:
		return float(text), True
	except ValueError:
		return None, False


def _formula_warnings(amounts, components):
	warnings = []
	by_abbr = {str(c.abbr): c for c in components}

	def val(abbr):
		return amounts.get(abbr, 0.0)

	for target, terms in FORMULAS:
		if target not in amounts or not all(a in amounts for _s, a in terms):
			continue
		expected = sum(val(a) if s == "+" else -val(a) for s, a in terms)
		if abs(expected - val(target)) > TOLERANCE:
			formula = " ".join(f"{s} {a}" for s, a in terms).lstrip("+ ")
			warnings.append(
				_("{0} = {1:,.0f} but {2} = {3:,.0f}").format(target, val(target), formula, expected)
			)
	for total in GROUP_TOTALS:
		parent = by_abbr.get(total)
		if not parent or total not in amounts:
			continue
		children = [str(c.abbr) for c in components if c.parent == parent.name and str(c.abbr) in amounts]
		if not children:
			continue
		expected = sum(val(a) for a in children)
		if abs(expected - val(total)) > TOLERANCE:
			warnings.append(
				_("{0} = {1:,.0f} but the sum of {2} = {3:,.0f}").format(
					total, val(total), ", ".join(children), expected
				)
			)
	return warnings


def parse_upload(file_url):
	components = _components()
	rows = _read_rows(file_url)
	if not rows:
		frappe.throw(_("The file is empty."))
	h = _find_header(rows)
	mapping, header_errors, missing_components = _map_columns(rows[h], components)

	result = {
		"header_errors": header_errors,
		"missing_components": missing_components,
		"rows": [],
		"periods": [],
		"error_count": 0,
		"warning_count": 0,
	}
	if header_errors:
		result["error_count"] = len(header_errors)
		return result

	ident = mapping["ident"]
	emp_cache, seen = {}, {}
	employees = {}
	existing = {}

	for offset, row in enumerate(rows[h + 1 :], start=h + 2):
		def cell(key):
			idx = ident.get(key)
			return row[idx] if idx is not None and idx < len(row) else None

		raw_emp = cell("employee")
		if raw_emp in (None, ""):
			continue
		errors, warnings = [], []
		period = parse_period_cell(cell("period"))
		if not period:
			errors.append(_("Cannot read the period \"{0}\" - use MM-YYYY, e.g. 10-2026.").format(cell("period") or ""))
		employee = _resolve_employee(raw_emp, emp_cache)
		if not employee:
			errors.append(_("Employee {0} does not exist.").format(raw_emp))
		for key, label, bound in (("period_from", "Period From", 0), ("period_to", "Period To", 1)):
			given = _date_cell(cell(key))
			if given is False:
				errors.append(_("{0}: cannot read the date \"{1}\".").format(_(label), cell(key)))
			elif given and period and given != period_bounds(period)[bound]:
				errors.append(
					_("{0} {1} does not match period {2} ({3} - {4}).").format(
						_(label), given, period, *period_bounds(period)
					)
				)

		amounts, details = {}, []
		for idx, comp in mapping["components"].items():
			raw = row[idx] if idx < len(row) else None
			value, ok = _number(raw)
			if not ok:
				errors.append(_("{0}: \"{1}\" is not a number.").format(comp.abbr, raw))
				continue
			amounts[str(comp.abbr)] = value
			details.append({"salary_component": comp.name, "abbr": comp.abbr, "amount": value})

		if employee and period:
			key = (employee, period)
			if key in seen:
				errors.append(_("Duplicate of row {0} (same employee and period).").format(seen[key]))
			seen[key] = offset
			status = existing.get(key)
			if status is None:
				status = frappe.db.get_value("TIQN Payslip", {"employee": employee, "period": period}, "status") or ""
				existing[key] = status
			if status == "Published":
				errors.append(_("The {0} payslip is already published. Withdraw it first.").format(period_label(period)))

		if employee:
			if employee not in employees:
				employees[employee] = frappe.db.get_value(
					"Employee", employee, ["employee_name", "status", "relieving_date"], as_dict=True
				)
			emp = employees[employee]
			name_in_file = str(cell("employee_name") or "").strip()
			if name_in_file and _norm(name_in_file) != _norm(emp.employee_name):
				warnings.append(_("Name in file \"{0}\" differs from ERP \"{1}\".").format(name_in_file, emp.employee_name))
			if period and emp.relieving_date and getdate(emp.relieving_date) <= period_bounds(period)[0]:
				warnings.append(_("Employee left on {0}, before this period started.").format(emp.relieving_date))

		warnings += _formula_warnings(amounts, components)
		if amounts.get("9", 0) < 0:
			warnings.append(_("Net salary is negative."))

		result["rows"].append(
			{
				"row": offset,
				"employee": employee,
				"employee_raw": str(raw_emp),
				"employee_name": str(cell("employee_name") or "").strip() or None,
				"department": str(cell("department") or "").strip() or None,
				"section": str(cell("section") or "").strip() or None,
				"group": str(cell("group") or "").strip() or None,
				"period": period,
				"net_pay": amounts.get("9"),
				"details": details,
				"errors": errors,
				"warnings": warnings,
				"existing_status": existing.get((employee, period)) if employee and period else None,
			}
		)
		result["error_count"] += len(errors)
		result["warning_count"] += len(warnings)

	result["periods"] = sorted({r["period"] for r in result["rows"] if r["period"]})
	if not result["rows"]:
		result["header_errors"].append(_("No employee rows found under the header."))
		result["error_count"] += 1
	return result


@frappe.whitelist(methods=["POST"])
def preview_upload(file_url):
	_check_role()
	data = parse_upload(file_url)
	# The page shows a summary; the full component list per row is not needed there.
	for r in data["rows"]:
		r["component_count"] = len(r.pop("details"))
	return data


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def import_upload(file_url, confirm_warnings=0):
	_check_role()
	data = parse_upload(file_url)
	if data["error_count"]:
		frappe.throw(_("The file still has {0} error(s). Fix them and upload again.").format(data["error_count"]))
	if data["warning_count"] and not cint(confirm_warnings):
		frappe.throw(_("Please confirm the warnings before importing."))

	batch = "UP-" + now_datetime().strftime("%Y%m%d-%H%M%S")
	if len(data["rows"]) > QUEUE_THRESHOLD:
		frappe.enqueue(
			_import_rows,
			queue="long",
			timeout=1800,
			rows=data["rows"],
			batch=batch,
			file_url=file_url,
			user=frappe.session.user,
		)
		return {"queued": True, "batch": batch, "rows": len(data["rows"])}
	count = _import_rows(data["rows"], batch, file_url, frappe.session.user)
	return {"queued": False, "batch": batch, "rows": count}


def _import_rows(rows, batch, file_url, user):
	count = 0
	for r in rows:
		name = frappe.db.get_value("TIQN Payslip", {"employee": r["employee"], "period": r["period"]})
		doc = frappe.get_doc("TIQN Payslip", name) if name else frappe.new_doc("TIQN Payslip")
		if doc.status == "Published":
			# Re-checked here: it may have been published between preview and import.
			frappe.throw(_("{0} {1} is already published.").format(r["employee"], r["period"]))
		# A Withdrawn payslip was published once: employees may have opened it, and its view
		# log + notification link to it. Keep it Withdrawn (Publish takes Withdrawn too) so
		# "Delete Drafts" never tries to delete it.
		was_published = doc.status == "Withdrawn"
		doc.update(
			{
				"employee": r["employee"],
				"employee_name": r["employee_name"] or frappe.db.get_value("Employee", r["employee"], "employee_name"),
				"department": r["department"],
				"section": r["section"],
				"group": r["group"],
				"period": r["period"],
				"status": "Withdrawn" if was_published else "Draft",
				"import_batch": batch,
			}
		)
		doc.set("details", [])
		for d in r["details"]:
			doc.append("details", d)
		doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
		count += 1
	_delete_upload_file(file_url)
	if frappe.flags.in_test:
		return count
	frappe.db.commit()
	frappe.publish_realtime(
		"payslip_import_done", {"batch": batch, "rows": count}, user=user, after_commit=True
	)
	return count


def _delete_upload_file(file_url):
	"""The uploaded workbook holds every salary of the period - do not leave it in File."""
	for name in frappe.get_all("File", {"file_url": file_url}, pluck="name"):
		frappe.delete_doc("File", name, ignore_permissions=True, force=True)


@frappe.whitelist(methods=["POST"])
def discard_upload(file_url):
	_check_role()
	_delete_upload_file(file_url)


# ---------------------------------------------------------------------------
# Publish / withdraw
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def get_period_summary():
	_check_role()
	rows = frappe.db.sql(
		"""
		SELECT period, status, COUNT(*) AS n, SUM(net_pay) AS net_total,
		       MAX(published_on) AS published_on, MAX(modified) AS modified
		FROM `tabTIQN Payslip`
		GROUP BY period, status
		ORDER BY period DESC
		""",
		as_dict=True,
	)
	periods = {}
	for r in rows:
		p = periods.setdefault(
			r.period,
			{"period": r.period, "Draft": 0, "Published": 0, "Withdrawn": 0, "net_total": 0, "published_on": None},
		)
		p[r.status] = r.n
		p["net_total"] += flt(r.net_total)
		if r.published_on and (not p["published_on"] or r.published_on > p["published_on"]):
			p["published_on"] = r.published_on
	out = []
	for p in periods.values():
		p["from_date"], p["to_date"] = period_bounds(p["period"])
		p["views"] = frappe.db.count("TIQN Payslip View Log", {"period": p["period"]})
		out.append(p)
	return out


@frappe.whitelist(methods=["POST"])
def publish_period(period):
	"""Publish every Draft / Withdrawn payslip of `period` and notify each employee."""
	_check_role()
	names = frappe.get_all(
		"TIQN Payslip", filters={"period": period, "status": ["in", ["Draft", "Withdrawn"]]}, pluck="name"
	)
	now = now_datetime()
	label = period_label(period)
	for name in names:
		doc = frappe.get_doc("TIQN Payslip", name)
		doc.status = "Published"
		doc.published_on = now
		doc.published_by = frappe.session.user
		doc.save(ignore_permissions=True)
		notify(
			doc.employee,
			"PAYSLIP_PUBLISHED",
			"Payslip {0}",
			"has been published",
			title_args=(label,),
			target_id=period,
			reference_doctype="TIQN Payslip",
			reference_name=doc.name,
		)
	return {"published": len(names)}


@frappe.whitelist(methods=["POST"])
def withdraw_period(period):
	"""Hide every Published payslip of `period` from the Mini App (to fix and republish)."""
	_check_role()
	names = frappe.get_all("TIQN Payslip", filters={"period": period, "status": "Published"}, pluck="name")
	for name in names:
		doc = frappe.get_doc("TIQN Payslip", name)
		doc.status = "Withdrawn"
		doc.save(ignore_permissions=True)
	# An unread "payslip published" pointing at a withdrawn payslip only leads to "not found".
	for n in frappe.get_all(
		"TIQN Portal Notification",
		filters={"type": "PAYSLIP_PUBLISHED", "target_id": period, "is_read": 0},
		pluck="name",
	):
		frappe.delete_doc("TIQN Portal Notification", n, ignore_permissions=True, force=True)
	return {"withdrawn": len(names)}


@frappe.whitelist(methods=["POST"])
def delete_draft_period(period):
	"""Delete never-published Draft payslips of a period (a wrong upload).

	Withdrawn ones stay: they were published once, employees may have viewed them and
	the view log points at them."""
	_check_role()
	names = frappe.get_all(
		"TIQN Payslip", filters={"period": period, "status": "Draft", "published_on": ["is", "not set"]}, pluck="name"
	)
	for name in names:
		frappe.delete_doc("TIQN Payslip", name, ignore_permissions=True)
	return {"deleted": len(names)}
