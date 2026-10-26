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
from customize_erpnext.employee_portal.utils import (
	code_key,
	expected_pay_date,
	get_settings,
	period_bounds,
	payslip_component_fields,
	period_label,
	period_of_date,
	shift_period,
	validate_period,
)

# `section` of utils.payslip_component_fields -> (key, label, sign)
SECTIONS = [
	("Earnings", "EARNINGS", "Earnings", 1),
	("Deductions", "DEDUCTIONS", "Deductions", -1),
	("Others", "OTHERS", "Other Items", 1),
	("Adjustment", "ADJUSTMENT", "Adjustment for Previous Month", 1),
	("Attendance", "ATTENDANCE", "Attendance & Overtime", 0),
]
UNITS = {"VND": "VND", "Day": "DAY", "Hour": "HOUR"}


def _published(employee):
	return frappe.get_all(
		"TIQN Payslip",
		filters={"employee": employee, "status": "Published"},
		fields=["name", "period", "period_from", "period_to", "pay_date", "published_on", "first_viewed_on"],
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
def _amount(value, unit):
	if unit == "VND":
		return int(round(flt(value)))
	value = round(flt(value), 2)
	return int(value) if value == int(value) else value


# "(a)", "(c=a+b)", "(j=f-g+h+i)" in the field label - the letters of the paper
# payslip. Lower-case a-j only, so "(8%)" or "(SI+HI+UI)" never match.
FORMULA_RE = re.compile(r"\(\s*([a-j](?:\s*=\s*[a-j](?:\s*[+-]\s*[a-j])*)?)\s*\)")


def build_payslip_rows(doc, include_zero, components):
	"""`rows` (contract 1.3.0): the paper payslip line by line - components in
	code order (1, 1.1, 1.2, 2, ... 9), each with its Unit/ĐVT
	value and amount. Amounts are positive as printed; deductions are not negated."""
	by_name = {c.name: c for c in components}
	parents = {c.parent for c in components if c.parent in by_name and c.parent != c.name}

	def level(c):
		depth, seen, p = 0, {c.name}, c.parent
		while p in by_name and p not in seen:  # a loop in the config must not hang
			depth += 1
			seen.add(p)
			p = by_name[p].parent
		return depth

	rows = []
	for c in components:
		unit = UNITS.get(c.unit or "VND", "VND")
		value = doc.get(c.fieldname)
		if unit == "VND":
			amount = _amount(value, unit)
			quantity_unit = UNITS.get(c.qty_unit) if c.qty_fieldname else None
			quantity = _amount(doc.get(c.qty_fieldname), quantity_unit) if c.qty_fieldname else None
		else:  # days / hours only (1.1): nothing in the Amount column
			amount, quantity, quantity_unit = None, _amount(value, unit), unit
		is_header = c.row_type in ("Subtotal", "Section Total") or c.name in parents
		if not include_zero and not is_header and not amount and not quantity:
			continue
		# Letters as CnB wrote them in the Mini App text (Settings > Payslip Lines).
		m = FORMULA_RE.search(c.display_label or "")
		rows.append(
			{
				"no": str(c.abbr),
				"display_label": c.display_label,
				"label": c.label or c.name,
				"formula": re.sub(r"\s+", "", m.group(1)) if m else None,
				"quantity": quantity,
				"quantity_unit": quantity_unit,
				"amount": amount,
				"level": level(c),
				"is_header": is_header,
			}
		)
	return rows


def build_payslip_payload(doc, include_zero):
	components = payslip_component_fields()
	config = {c.name: c for c in components}
	# Only components that have a field on TIQN Payslip; same "present" rule as the old
	# child table, where every imported component had a row (0 included).
	amounts, legacy_units = {}, {}
	for c in components:
		if c.section == "Attendance" and c.qty_fieldname:
			# 1.2 / 2.1-2.3 became money lines (24/10/2026); `sections` (deprecated)
			# keeps showing their days / hours in ATTENDANCE as before.
			amounts[c.name] = flt(doc.get(c.qty_fieldname))
			legacy_units[c.name] = c.qty_unit
		else:
			amounts[c.name] = flt(doc.get(c.fieldname))

	def line(cfg, children):
		unit = UNITS.get(legacy_units.get(cfg.name) or cfg.unit or "VND", "VND")
		return {
			"code": cfg.abbr,
			"label": cfg.label or cfg.name,
			"amount": _amount(amounts.get(cfg.name, 0), unit),
			"unit": unit,
			"is_total": cfg.row_type == "Subtotal",
			"children": children,
		}

	sections = []
	for section_value, key, label, sign in SECTIONS:
		members = [cfg for name, cfg in config.items() if cfg.section == section_value and name in amounts]
		members.sort(key=lambda m: code_key(m.abbr))
		total_cfg = next((m for m in members if m.row_type == "Section Total"), None)
		body = [m for m in members if m.row_type != "Section Total"]
		names_in_body = {m.name for m in body}

		def build(parent_name):
			out = []
			for m in body:
				# A component set as its own parent would recurse forever.
				parent = m.parent if m.parent in names_in_body and m.parent != m.name else None
				if parent != parent_name:
					continue
				children = build(m.name)
				if m.row_type == "Subtotal":
					out.append(line(m, children))
				elif include_zero or flt(amounts.get(m.name)) != 0:
					out.append(line(m, children))
			return out

		lines = build(None)
		unit = None if sign == 0 else "VND"
		total = None
		if total_cfg:
			total = _amount(amounts.get(total_cfg.name, 0), UNITS.get(total_cfg.unit or "VND", "VND"))
		elif sign != 0:
			total = 0
		if not lines and total in (None, 0) and not total_cfg:
			continue
		sections.append(
			{"key": key, "label": _(label, context="Payslip"), "sign": sign, "total": total, "unit": unit, "lines": lines}
		)

	return {
		"period": doc.period,
		"label": _("Payslip {0}").format(period_label(doc.period)),
		"period_from": fmt_date(doc.period_from),
		"period_to": fmt_date(doc.period_to),
		"pay_date": fmt_date(doc.pay_date),
		"published_on": fmt_datetime(doc.published_on),
		"currency": "VND",
		"net_pay": int(round(flt(doc.net_pay))),
		"include_zero": include_zero,
		"employee": {
			"employee_id": doc.employee,
			"full_name": doc.employee_name,
			"department": doc.department,
			"section": doc.section,
			"group": doc.group,
		},
		"rows": build_payslip_rows(doc, include_zero, components),
		"sections": sections,
	}
