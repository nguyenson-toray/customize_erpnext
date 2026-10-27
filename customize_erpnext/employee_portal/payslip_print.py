# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""TIQN Payslip printout - the paper payslip C&B hands to an employee when needed.

Same layout as the paper slip (employee_portal/phiếu lương.png): bilingual lines 1 -> 9,
Unit / Amount, every line printed (0 = "-"). Under the table, one line each (27/10/2026,
not a Remark column per line): transfer deadline (Pay Date) and Remark = the payslip Note. A4 only (27/10/2026): C&B picks A5 on the printer.

- `payslip_print_html(doc)`: Jinja method (hooks.py) - the "TIQN Payslip" Print Format
  renders this, so the form's Print / Ctrl+P shows the same page.
- `download_pdf(names)` (form button): 1 payslip -> PDF straight back. Files are named
  `{Period}_{section}_{group}_{employee}_{employee_name}.pdf`.
- List "Download PDF" (27/10/2026: one button for ticked payslips or a whole period,
  ~1,000 payslips = ~2 min, over the 120 s request timeout): `start_pdf_job` ->
  background job (queue long) -> `pdf_job_status` polled by the list -> `download_pdf_job`.
  ZIP of one PDF each (default) or one combined PDF; a single payslip is always its PDF.
  The result waits in Redis cache (no persistence, 30 min, only for the user who asked)
  and is deleted once downloaded - never a File (it holds salaries).
- Draft / Withdrawn print with a "BẢN NHÁP / DRAFT" watermark: fine for checking,
  not to be handed out.
"""

import base64
import functools
import io
import secrets
import os
import re
import zipfile

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime

from customize_erpnext.api.employee_portal.payslip import FORMULA_RE, build_payslip_rows
from customize_erpnext.employee_portal.utils import payslip_component_fields, strip_code_formula

PAYSLIP_DT = "TIQN Payslip"
ROLES = ("CnB", "System Manager")
MAX_PRINT = 200
MAX_JOB = 3000  # one period is ~1,000
CHUNK = 50  # payslips per wkhtmltopdf run in the background job (~6 s each)
JOB_TTL = 30 * 60  # seconds the period job state / result stay in Redis
JOB_KEY = "tiqn_payslip_pdf:{}"  # state; + ":file" = the result
USER_KEY = "tiqn_payslip_pdf_user:{}"  # token of the user's running job (one at a time)
MODES = ("zip", "combined")
TEMPLATE = "customize_erpnext/employee_portal/payslip_print.html"
PDF_OPTIONS = {
	"page-size": "A4",
	"orientation": "Portrait",
	"margin-top": "10mm",
	"margin-bottom": "10mm",
	"margin-left": "12mm",
	"margin-right": "12mm",
	"encoding": "UTF-8",
}
# Small logo top-left (27/10/2026). Inlined as a data URI: get_pdf runs wkhtmltopdf with
# local file access disabled, and the file is not in public/ (no URL needed).
LOGO_FILE = os.path.join(os.path.dirname(__file__), "logo_blue.png")
MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# Not allowed in a file name on Windows / macOS / Linux (+ control characters).
FILENAME_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


@functools.lru_cache(maxsize=1)
def _logo_data_uri():
	try:
		with open(LOGO_FILE, "rb") as f:
			return "data:image/png;base64," + base64.b64encode(f.read()).decode()
	except OSError:
		return ""  # no logo rather than no printout


def _fmt_money(value):
	value = int(round(flt(value)))
	return f"{value:,}" if value else "-"


def _fmt_qty(value):
	value = round(flt(value), 2)
	if not value:
		return "-"
	return f"{value:,.2f}".rstrip("0").rstrip(".")


def _d(date, fmt="%d/%m/%Y"):
	return getdate(date).strftime(fmt) if date else ""


def payslip_context(doc):
	"""Everything the template needs, worked out once per payslip."""
	components = payslip_component_fields()
	by_code = {str(c.abbr): c for c in components}
	rows = []
	for r in build_payslip_rows(doc, True, components):
		c = by_code[r["no"]]
		m = FORMULA_RE.search(c.display_label or "") or FORMULA_RE.search(c.name or "")
		english = strip_code_formula(c.name) or c.name
		vietnamese = r["label"]
		rows.append(
			frappe._dict(
				no=r["no"],
				english=english,
				vietnamese=vietnamese if vietnamese and vietnamese != english else "",
				formula=re.sub(r"\s+", "", m.group(1)) if m else "",
				unit=_fmt_qty(r["quantity"]) if r["quantity_unit"] else "",
				amount=_fmt_money(r["amount"]) if r["amount"] is not None else "",
				level=r["level"],
				is_header=r["is_header"],
			)
		)
	year, month = (int(x) for x in doc.period.split("-"))
	return {
		"doc": doc,
		"rows": rows,
		"period_en": f"{MONTHS_EN[month - 1]} {year}",
		"period_vi": f"Tháng {month:02d} năm {year}",
		# 26/09/2026 - 25/10/2026 (user, 27/10: clearer than the paper's "26 Sep 26 - 25 Oct 26").
		"period_range": f"{_d(doc.period_from)} - {_d(doc.period_to)}" if doc.period_from and doc.period_to else "",
		"dept": " - ".join(x for x in (doc.section, doc.group) if x),
		"pay_date": _d(doc.pay_date),
		"logo": _logo_data_uri(),
		"note": (doc.get("note") or "").strip(),
		"draft": doc.status != "Published",
	}


def payslip_print_html(doc):
	"""Jinja method for the Print Format: `{{ payslip_print_html(doc) }}`."""
	if isinstance(doc, str):
		doc = frappe.get_doc(PAYSLIP_DT, doc)
	return frappe.render_template(TEMPLATE, payslip_context(doc))


def pdf_filename(doc):
	"""{Period}_{section}_{group}_{employee}_{employee_name}.pdf - empty parts left out."""
	parts = [doc.period, doc.section, doc.group, doc.employee, doc.employee_name]
	parts = [" ".join(FILENAME_BAD.sub(" ", str(p)).split()) for p in parts if p]
	return "_".join(p for p in parts if p) + ".pdf"


def _render_pdf(docs):
	"""One PDF page per payslip, in the order given."""
	from frappe.utils.pdf import get_pdf

	body = '<div style="page-break-after: always"></div>'.join(payslip_print_html(d) for d in docs)
	html = f'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>{body}</body></html>'
	return get_pdf(html, dict(PDF_OPTIONS))


def _split_pages(pdf, count):
	"""[one-page PDF per payslip], or None when the page count does not match (a payslip
	ran onto a second page) - then each payslip is rendered on its own."""
	from pypdf import PdfReader, PdfWriter

	reader = PdfReader(io.BytesIO(pdf))
	if len(reader.pages) != count:
		return None
	out = []
	for page in reader.pages:
		writer = PdfWriter()
		writer.add_page(page)
		buf = io.BytesIO()
		writer.write(buf)
		out.append(buf.getvalue())
	return out


def _load(names, limit=MAX_PRINT):
	if isinstance(names, str):
		names = frappe.parse_json(names) if names.strip().startswith("[") else [names]
	names = list(dict.fromkeys(n for n in (names or []) if n))
	if not names:
		frappe.throw(_("Select at least one payslip."))
	if len(names) > limit:
		frappe.throw(_("Download at most {0} payslips at a time - filter the list first.").format(limit))
	docs = []
	for name in names:
		doc = frappe.get_doc(PAYSLIP_DT, name)
		doc.check_permission("print")
		docs.append(doc)
	# Section -> Group -> employee: printed slips come out ready to hand out per team.
	docs.sort(key=lambda d: (d.period, d.section or "", d.group or "", d.employee))
	return docs


def _one_pdf_each(docs):
	"""[one PDF per payslip], same order: rendered together and split when every payslip
	fits one page, else one by one."""
	pages = _split_pages(_render_pdf(docs), len(docs)) if len(docs) > 1 else None
	return pages if pages is not None else [_render_pdf([d]) for d in docs]


def _named(docs, pdfs):
	"""[(doc, filename, pdf)] - a name used twice (e.g. empty name fields) gets " (2)"."""
	files, used = [], set()
	for doc, pdf in zip(docs, pdfs):
		filename = pdf_filename(doc)
		stem, n = filename[:-4], 2
		while filename in used:
			filename = f"{stem} ({n}).pdf"
			n += 1
		used.add(filename)
		files.append((doc, filename, pdf))
	return files


def _zip(files):
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
		for _doc, name, pdf in files:
			zf.writestr(name, pdf)
	return buf.getvalue()


def _merge(pdfs):
	from pypdf import PdfReader, PdfWriter

	writer = PdfWriter()
	for pdf in pdfs:
		writer.append(PdfReader(io.BytesIO(pdf)))
	buf = io.BytesIO()
	writer.write(buf)
	return buf.getvalue()


def _log_printed(names):
	"""The "Printed PDF" comment on each payslip, without loading the documents."""
	for name in names:
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"comment_email": frappe.session.user,
				"reference_doctype": PAYSLIP_DT,
				"reference_name": name,
				"content": _("Printed PDF"),
			}
		).insert(ignore_permissions=True)


def build_files(names):
	"""[(doc, filename, pdf bytes)] - one per payslip."""
	docs = _load(names)
	return _named(docs, _one_pdf_each(docs))


@frappe.whitelist(methods=["POST"])
def download_pdf(names):
	"""1 payslip -> its PDF; several -> a ZIP with one PDF per payslip."""
	frappe.only_for(ROLES)
	files = build_files(names)
	for doc, _filename, _pdf in files:
		doc.add_comment("Info", _("Printed PDF"))

	if len(files) == 1:
		_doc, filename, content = files[0]
	else:
		periods = {doc.period for doc, _f, _p in files}
		if len(periods) == 1:
			filename = f"{periods.pop()}_{len(files)} payslips.zip"
		else:
			filename = f"Payslips_{len(files)}_{now_datetime().strftime('%y%m%d %H%M%S')}.zip"
		content = _zip(files)
	frappe.response["filename"] = filename
	frappe.response["filecontent"] = content
	frappe.response["type"] = "binary"
	return cint(len(files))


# ---- List "Download PDF": ticked payslips or a whole period (background job) ----


def _job_state(token):
	return frappe.cache.get_value(JOB_KEY.format(token)) or None


def _set_job_state(token, state):
	frappe.cache.set_value(JOB_KEY.format(token), state, expires_in_sec=JOB_TTL)


def _own_job(token):
	"""The caller's job state, or throw: another user's token is as good as none."""
	state = _job_state(token) if token else None
	if not state or state.get("user") != frappe.session.user:
		frappe.throw(_("This download has expired - start it again."))
	return state


def _clean(value):
	return " ".join(FILENAME_BAD.sub(" ", str(value)).split())


@frappe.whitelist()
def pdf_job_options():
	"""Pay periods that have payslips, latest first (Section / Group are Link fields)."""
	frappe.only_for(ROLES)
	return {"periods": frappe.get_all(PAYSLIP_DT, pluck="period", distinct=True, order_by="period desc")}


@frappe.whitelist(methods=["POST"])
def start_pdf_job(names=None, period=None, section=None, group=None, status=None, mode="zip"):
	"""Queue the PDFs of the ticked payslips (`names`) or of a period (optionally one
	Section / Group / status). -> {token, total}"""
	frappe.only_for(ROLES)
	if mode not in MODES:
		frappe.throw(_("Unknown output: {0}").format(mode))
	user = frappe.session.user
	running = frappe.cache.get_value(USER_KEY.format(user))
	if running and (_job_state(running) or {}).get("status") in ("queued", "running"):
		frappe.throw(_("Your previous PDF download is still being prepared - wait for it to finish."))

	if names:
		names = frappe.parse_json(names) if isinstance(names, str) else names
		filters = {"name": ("in", list(dict.fromkeys(names)))}
	elif period:
		filters = {"period": period}
		for field, value in (("section", section), ("group", group), ("status", status)):
			if value:
				filters[field] = value
	else:
		frappe.throw(_("Tick the payslips or pick a pay period."))
	# get_list: only the payslips this user may read.
	rows = frappe.get_list(PAYSLIP_DT, filters=filters, fields=["name", "period"], limit_page_length=0)
	if not rows:
		frappe.throw(_("No payslips match these filters."))
	if len(rows) > MAX_JOB:
		frappe.throw(_("Download at most {0} payslips at a time - filter the list first.").format(MAX_JOB))

	periods = {r.period for r in rows}
	if names and len(periods) > 1:
		stem = f"Payslips_{len(rows)}_{now_datetime().strftime('%y%m%d %H%M%S')}"
	else:
		parts = [_clean(p) for p in ((period, section, group) if not names else (periods.pop(),)) if p]
		stem = "_".join([p for p in parts if p] + [f"{len(rows)} payslips"])
	token = secrets.token_urlsafe(16)
	_set_job_state(
		token,
		{
			"user": user,
			"status": "queued",
			"done": 0,
			"total": len(rows),
			"filename": stem + (".zip" if mode == "zip" else ".pdf"),
			"names": [r.name for r in rows],
		},
	)
	frappe.cache.set_value(USER_KEY.format(user), token, expires_in_sec=JOB_TTL)
	frappe.enqueue(
		"customize_erpnext.employee_portal.payslip_print.build_pdf_job",
		queue="long",
		timeout=JOB_TTL,
		job_id=f"tiqn_payslip_pdf::{token}",
		token=token,
		mode=mode,
	)
	return {"token": token, "total": len(rows)}


def build_pdf_job(token, mode):
	"""Background job: render CHUNK payslips at a time, then park the result in Redis."""
	state = _job_state(token)
	if not state:
		return
	try:
		state["status"] = "running"
		_set_job_state(token, state)
		docs = _load(state["names"], MAX_JOB)
		pdfs = []
		for i in range(0, len(docs), CHUNK):
			chunk = docs[i : i + CHUNK]
			# combined: one PDF per chunk (a long Note may take a payslip onto 2 pages - fine).
			pdfs.extend(_one_pdf_each(chunk) if mode == "zip" or len(docs) == 1 else [_render_pdf(chunk)])
			state["done"] = min(i + CHUNK, len(docs))
			_set_job_state(token, state)
		if len(docs) == 1:  # one payslip: its own PDF, whatever the output picked
			content, state["filename"] = pdfs[0], pdf_filename(docs[0])
		else:
			content = _zip(_named(docs, pdfs)) if mode == "zip" else _merge(pdfs)
		frappe.cache.set_value(JOB_KEY.format(token) + ":file", content, expires_in_sec=JOB_TTL)
		state["status"] = "done"
	except Exception:
		frappe.log_error(title="TIQN Payslip PDF download")
		state["status"] = "error"
	_set_job_state(token, state)
	frappe.cache.delete_value(USER_KEY.format(state["user"]))


@frappe.whitelist()
def pdf_job_status(token):
	frappe.only_for(ROLES)
	state = _own_job(token)
	return {k: state.get(k) for k in ("status", "done", "total", "filename")}


@frappe.whitelist(methods=["POST"])
def download_pdf_job(token):
	"""The finished file, once: deleted from Redis as it is sent."""
	frappe.only_for(ROLES)
	state = _own_job(token)
	content = frappe.cache.get_value(JOB_KEY.format(token) + ":file") if state.get("status") == "done" else None
	if not content:
		frappe.throw(_("This download has expired - start it again."))
	frappe.cache.delete_value([JOB_KEY.format(token), JOB_KEY.format(token) + ":file"])
	_log_printed(state["names"])
	frappe.response["filename"] = state["filename"]
	frappe.response["filecontent"] = content
	frappe.response["type"] = "binary"
	return cint(state["total"])
