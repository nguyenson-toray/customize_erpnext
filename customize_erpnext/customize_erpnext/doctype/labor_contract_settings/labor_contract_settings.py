# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Labor Contract Settings — the Monday email (user request 22/10/2026).

Every Monday 08:00 (hooks.py scheduler_events cron "0 8 * * 1"): contracts whose End Date
falls in this week, and every contract / appendix created but not signed yet. Default
recipient son.nt@tiqn.com.vn; HR Manager changes the list here.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
	date_diff,
	escape_html,
	get_first_day_of_week,
	get_last_day_of_week,
	get_url_to_form,
	getdate,
	split_emails,
	validate_email_address,
)

from customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract import (
	APPENDIX,
	business_today,
)
from customize_erpnext.customize_erpnext.report.labor_contract_report.labor_contract_report import (
	OVERDUE_LEGAL_DAYS,
)

MAX_ROWS = 300


class LaborContractSettings(Document):
	def validate(self):
		for email in split_emails(self.weekly_email_recipients or ""):
			validate_email_address(email, throw=True)


def _recipients(settings):
	return split_emails(settings.weekly_email_recipients or "")


def send_weekly_contract_email():
	"""Scheduler entry point. Off, or nobody to send to → nothing."""
	settings = frappe.get_cached_doc("Labor Contract Settings")
	recipients = _recipients(settings)
	if not (settings.weekly_email_enabled and recipients):
		return
	_send(recipients)


@frappe.whitelist()
def send_weekly_email_now():
	"""Settings form button — same email, to the saved recipients, ignoring the On switch."""
	frappe.only_for(("HR Manager", "System Manager"))
	recipients = _recipients(frappe.get_doc("Labor Contract Settings"))
	if not recipients:
		frappe.throw(_("Please enter at least one recipient"))
	_send(recipients)
	return _("Queued for {0}").format(", ".join(recipients))


def _send(recipients):
	today = getdate(business_today())
	week_start, week_end = get_first_day_of_week(today), get_last_day_of_week(today)
	expiring = _expiring(week_start, week_end)
	unsigned = _unsigned()

	frappe.sendmail(
		recipients=recipients,
		subject=_("Labor Contracts {0}–{1}: {2} expiring, {3} not signed").format(
			_dmy(week_start), _dmy(week_end), len(expiring), len(unsigned)
		),
		message=_build_html(today, week_start, week_end, expiring, unsigned),
		now=False,
	)


def _expiring(week_start, week_end):
	"""Contracts ending this week, for employees still working after it ends (someone
	leaving at the end of their contract needs no next one)."""
	return frappe.db.sql(
		"""
		SELECT lc.name, lc.employee, lc.employee_name, emp.designation, lc.contract_type,
			lc.end_date, lc.status, lc.next_contract_type,
			(SELECT CONCAT(nx.name, '|', nx.status) FROM `tabLabor Contract` nx
			 WHERE nx.employee = lc.employee AND nx.document_type = 'Contract'
			   AND nx.start_date > lc.start_date
			 ORDER BY nx.start_date, nx.creation DESC LIMIT 1) AS next_document
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		WHERE lc.document_type = 'Contract'
		  AND lc.end_date BETWEEN %(week_start)s AND %(week_end)s
		  AND emp.status != 'Left'
		  -- relieving_date = first day off
		  AND (emp.relieving_date IS NULL OR emp.relieving_date > DATE_ADD(lc.end_date, INTERVAL 1 DAY))
		ORDER BY lc.end_date, lc.employee
		""",
		{"week_start": week_start, "week_end": week_end},
		as_dict=True,
	)


def _unsigned():
	"""Created but not signed — same rule as the Mark as Signed picker: a document that
	starts on/after the employee's first day off is never going to be signed."""
	return frappe.db.sql(
		"""
		SELECT lc.name, lc.employee, lc.employee_name, lc.document_type, lc.contract_type,
			lc.start_date, lc.status
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		WHERE lc.status IN ('Upcoming', 'Overdue')
		  AND emp.status != 'Left'
		  AND (emp.relieving_date IS NULL OR emp.relieving_date > lc.start_date)
		ORDER BY lc.start_date, lc.employee
		""",
		as_dict=True,
	)


# -----------------------------------------------------------------------------
# HTML — plain tables with bgcolor attributes so Outlook keeps them when forwarded
# -----------------------------------------------------------------------------

TH = 'style="padding:4px 8px;border:1px solid #d1d5db;text-align:left;font-weight:bold;"'
TD = 'style="padding:4px 8px;border:1px solid #d1d5db;"'


def _dmy(value):
	return getdate(value).strftime("%d/%m/%Y") if value else ""


def _label(value):
	"""Translated record name (Employment Type…); "" stays "" — _("") is the .po header."""
	return _(value) if value else ""


def _link(name):
	return f'<a href="{get_url_to_form("Labor Contract", name)}">{escape_html(name)}</a>'


def _table(headers, rows, total):
	if not rows:
		return f'<p style="color:#6b7280;">{_("None")}</p>'
	head = "".join(f"<th {TH}>{escape_html(h)}</th>" for h in headers)
	body = "".join(
		f'<tr{" bgcolor=\"#fee2e2\"" if highlight else ""}>'
		+ "".join(f"<td {TD}>{cell}</td>" for cell in cells)
		+ "</tr>"
		for cells, highlight in rows[:MAX_ROWS]
	)
	more = (
		f'<p style="color:#6b7280;">{_("...and {0} more — see the Labor Contract Report.").format(total - MAX_ROWS)}</p>'
		if total > MAX_ROWS else ""
	)
	return (
		'<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:13px;">'
		f'<tr bgcolor="#f3f4f6">{head}</tr>{body}</table>{more}'
	)


def _build_html(today, week_start, week_end, expiring, unsigned):
	expiring_rows = []
	for r in expiring:
		if r.next_document:
			next_name, next_status = r.next_document.split("|", 1)
			next_cell = f"{_link(next_name)} ({escape_html(_(next_status))})"
		elif r.next_contract_type:
			next_cell = f'<b style="color:#b91c1c;">{_("Not Created")}</b>'
		else:
			next_cell = ""
		expiring_rows.append(([
			_link(r.name), escape_html(r.employee), escape_html(r.employee_name or ""),
			escape_html(r.designation or ""), escape_html(_label(r.contract_type)),
			_dmy(r.end_date), escape_html(_(r.status)), next_cell,
		], r.status != "Signed"))

	unsigned_rows = []
	for r in unsigned:
		start = getdate(r.start_date)
		days_overdue = date_diff(today, start) if start < today else None
		unsigned_rows.append(([
			_link(r.name), escape_html(r.employee), escape_html(r.employee_name or ""),
			escape_html(_("Appendix") if r.document_type == APPENDIX else _label(r.contract_type)),
			_dmy(start), escape_html(_(r.status)), str(days_overdue) if days_overdue else "",
		], (days_overdue or 0) > OVERDUE_LEGAL_DAYS))

	return f"""
	<div style="font-family:Arial,sans-serif;font-size:14px;">
		<h3 style="margin:0 0 8px;">{_("Contracts expiring this week ({0} – {1})").format(_dmy(week_start), _dmy(week_end))}: {len(expiring)}</h3>
		{_table([_("Document No"), _("Employee"), _("Employee Name"), _("Designation"), _("Contract Type"),
			_("End Date"), _("Status"), _("Next Contract")], expiring_rows, len(expiring))}
		<h3 style="margin:20px 0 8px;">{_("Created but not signed yet")}: {len(unsigned)}</h3>
		<p style="color:#6b7280;margin:0 0 8px;">{_("Red rows: more than {0} days past the start date (Labor Code 2019, Article 20.2).").format(OVERDUE_LEGAL_DAYS)}</p>
		{_table([_("Document No"), _("Employee"), _("Employee Name"), _("Type"), _("Start / Effective Date"),
			_("Status"), _("Days Overdue")], unsigned_rows, len(unsigned))}
	</div>
	"""
