# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Payslip endpoints - API_CONTRACT.md §10.

`get_payslip_periods` NEVER returns amounts: the list screen can be shown to someone
else holding the phone without exposing a year of salary. Amounts only come from
`get_payslip`, which is POST because the first call marks the payslip viewed.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, today

from customize_erpnext.api.employee_portal.core import PortalError, ctx, fmt_date, fmt_datetime, portal_api
from customize_erpnext.employee_portal import payslip_structure as pss
from customize_erpnext.employee_portal.utils import (
	expected_pay_date,
	get_settings,
	period_bounds,
	period_label,
	period_of_date,
	shift_period,
	validate_period,
)



def _published(employee):
	return frappe.get_all(
		"TIQN Payslip",
		filters={"employee": employee, "status": "Published"},
		fields=[
			"name", "period", "period_from", "period_to", "pay_date", "published_on", "first_viewed_on", "content_version",
		],
		order_by="period desc",
	)


@portal_api(methods=("GET",), feature="payslip")
def get_payslip_periods(year=None):
	c = ctx()
	rows = _published(c.employee)
	current_year = int(period_of_date(today())[:4])
	year = cint(year) or current_year

	years = {int(r.period[:4]) for r in rows} | {current_year}
	published_periods = {r.period for r in rows}

	# The last period that has ENDED is the one HR is about to publish.
	candidate = shift_period(period_of_date(today()), -1)
	upcoming = None
	relieving = c.employee_row.get("relieving_date")
	joined = c.employee_row.get("date_of_joining")
	candidate_from, candidate_to = period_bounds(candidate)
	worked_in_candidate = (not relieving or getdate(relieving) > candidate_from) and (
		not joined or getdate(joined) <= candidate_to
	)
	if candidate not in published_periods and int(candidate[:4]) == year and worked_in_candidate:
		pay = expected_pay_date(candidate)
		upcoming = {
			"period": candidate,
			"label": _("Month {0}").format(period_label(candidate)),
			"status": "NOT_PUBLISHED",
			"expected_pay_date": fmt_date(pay),
		}

	items = [
		{
			"period": r.period,
			"label": _("Month {0}").format(period_label(r.period)),
			"status": "PUBLISHED",
			"period_from": fmt_date(r.period_from),
			"period_to": fmt_date(r.period_to),
			"pay_date": fmt_date(r.pay_date),
			"published_on": fmt_datetime(r.published_on),
			"content_version": r.content_version,
			"is_new": not r.first_viewed_on,
		}
		for r in rows
		if int(r.period[:4]) == year
	]
	return {"year": year, "years_available": sorted(years, reverse=True), "upcoming": upcoming, "items": items}


@portal_api(methods=("POST",), feature="payslip")
def get_payslip(period=None, include_zero=None):
	c = ctx()
	try:
		period = validate_period(period)
	except frappe.ValidationError:
		raise PortalError("VALIDATION", _("Period must look like YYYY-MM."), field="period")

	name = frappe.db.get_value("TIQN Payslip", {"employee": c.employee, "period": period, "status": "Published"})
	if not name:
		raise PortalError("NOT_FOUND", _("This payslip is not available."))
	doc = frappe.get_doc("TIQN Payslip", name)

	if include_zero in (None, ""):
		include_zero = cint(get_settings().show_zero_lines)
	include_zero = bool(cint(include_zero))

	data = build_payslip_payload(doc, include_zero)

	if not doc.first_viewed_on:
		_mark_viewed(doc.name)
	return data


def _mark_viewed(name):
	"""First view only: after a publish ~1000 people open their payslip within minutes,
	and every later open (back / forth, "hide 0") must not write. `IS NULL` in SQL so two
	requests at once keep the earliest; update_modified stays untouched (HR edits only)."""
	ps = frappe.qb.DocType("TIQN Payslip")
	(
		frappe.qb.update(ps)
		.set(ps.first_viewed_on, now_datetime())
		.where(ps.name == name)
		.where(ps.first_viewed_on.isnull())
	).run()


# ---------------------------------------------------------------------------
# "(a)", "(c=a+b)", "(j=f-g+h+i)" in a label - the letters of the paper payslip, lower-case
# a-j only so "(8%)" never matches. Since the Payslip Structure (28/10/2026) the formula
# text is its own field; kept for the patches that read the older labels.
FORMULA_RE = re.compile(r"\(\s*([a-j](?:\s*=\s*[a-j](?:\s*[+-]\s*[a-j])*)?)\s*\)")


def build_payslip_rows(doc, include_zero):
	"""`rows` (contract 1.3.0) from the payslip's own copy of its lines."""
	return pss.rows_from_snapshot(pss.snapshot_of(doc), include_zero)


def build_payslip_payload(doc, include_zero):
	snapshot = pss.snapshot_of(doc)
	return {
		"period": doc.period,
		"label": _("Payslip {0}").format(period_label(doc.period)),
		"period_from": fmt_date(doc.period_from),
		"period_to": fmt_date(doc.period_to),
		"pay_date": fmt_date(doc.pay_date),
		"published_on": fmt_datetime(doc.published_on),
		# 1.9.0: changes with any change of the content (labels applied later included) -
		# with published_on, the cache key of newer Mini App builds.
		"content_version": doc.get("content_version") or pss.content_version(snapshot),
		"currency": "VND",
		"net_pay": int(round(flt(doc.net_pay))),
		# Free text C&B typed in the Note column for the whole payslip (1.8.0); null = none.
		"note": (doc.get("note") or "").strip() or None,
		"include_zero": include_zero,
		"employee": {
			"employee_id": doc.employee,
			"full_name": doc.employee_name,
			"department": doc.department,
			"section": doc.section,
			"group": doc.group,
		},
		"rows": pss.rows_from_snapshot(snapshot, include_zero),
		"sections": pss.sections_from_snapshot(snapshot, include_zero),
	}
