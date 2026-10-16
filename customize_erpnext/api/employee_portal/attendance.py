# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Attendance, overtime and explanation (read side) - API_CONTRACT.md §9."""

import calendar
import datetime

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from customize_erpnext.api.employee_portal.core import (
	PortalError,
	ctx,
	feature_enabled,
	fmt_date,
	fmt_datetime,
	portal_api,
)
from customize_erpnext.api.employee_portal.notifications import paging
from customize_erpnext.employee_portal import attendance_data as ad
from customize_erpnext.employee_portal.requests_common import person, request_blocker, status_label
from customize_erpnext.employee_portal.utils import (
	expected_pay_date,
	period_bounds,
	period_label,
	period_of_date,
	validate_period,
)

SUPPLEMENT_REASONS = ("Forget Check In/Out", "Machine Error", "First Working Day", "Other")
REASON_LABELS = {
	"On Duty": "Business trip / working outside",
	"Work From Home": "Working remotely",
	"Forget Check In/Out": "Forgot to check in/out",
	"Machine Error": "Attendance machine error",
	"First Working Day": "First working day",
	"Other": "Other reason",
}


def ot_status_label(status):
	return _(OT_STATUS_LABELS[status], context="Portal")


OT_STATUS_LABELS = {
	"APPROVED": "Approved",
	"PENDING": "Pending Approval",
	"REGISTERED": "Registered",
	"DRAFT": "Draft",
}


def ot_registration_payload(r):
	return {
		"id": r["registration"],
		"date": fmt_date(r["date"]),
		"weekday_label": ad.weekday_label(r["date"], short=True),
		"begin": r["begin"],
		"end": r["end"],
		"hours": r["hours"],
		"reason": r["reason"] or None,
		"status": r["status"],
		"status_label": ot_status_label(r["status"]),
	}


def _hours(value):
	"""Attendance OT duration -> hours rounded to 2 decimals, None when there is none."""
	value = round(flt(value), 2)
	return value or None


def reason_label(reason):
	return _(REASON_LABELS.get(reason, reason or ""), context="Portal") if reason else None


def _month(month):
	month = (month or "").strip() or nowdate()[:7]
	try:
		year, mon = (int(x) for x in validate_period(month).split("-"))
	except (frappe.ValidationError, ValueError):
		raise PortalError("VALIDATION", _("Month must look like YYYY-MM."), field="month")
	return datetime.date(year, mon, 1), datetime.date(year, mon, calendar.monthrange(year, mon)[1])


def _period(period):
	period = (period or "").strip() or period_of_date(nowdate())
	try:
		return validate_period(period)
	except frappe.ValidationError:
		raise PortalError("VALIDATION", _("Period must look like YYYY-MM."), field="period")


def _explanation_dates(employee, from_date, to_date):
	"""Dates covered by a non-cancelled attendance request of the employee."""
	out = {}
	for r in frappe.get_all(
		"Attendance Request",
		filters={"employee": employee, "docstatus": ["<", 2], "from_date": ["<=", to_date], "to_date": [">=", from_date]},
		fields=["name", "from_date", "to_date"],
	):
		for d in ad.daterange(max(getdate(r.from_date), from_date), min(getdate(r.to_date), to_date)):
			out.setdefault(d, []).append(r.name)
	return out


# ---------------------------------------------------------------------------
@portal_api(methods=("GET",), feature="attendance")
def get_attendance_calendar(month=None):
	c = ctx()
	start, end = _month(month)
	today = getdate(nowdate())
	holidays = ad.holidays_between(c.employee, start, end)
	att = ad.attendance_rows(c.employee, start, end)
	explained = _explanation_dates(c.employee, start, end)
	joined = getdate(c.employee_row.get("date_of_joining")) if c.employee_row.get("date_of_joining") else None

	summary = {"present": 0, "leave": 0, "absent": 0, "late_early": 0, "holiday": 0}
	# Calendar month straight from Attendance (not the pay period - get_attendance_summary is).
	# features.overtime off -> no OT anywhere in the calendar.
	show_ot = feature_enabled("overtime")
	overtime_summary = {
		"actual_hours": round(sum(flt(a.ot_final) for a in att.values()), 2),
		"approved_hours": round(sum(flt(a.ot_approved) for a in att.values()), 2),
	} if show_ot else None
	days = []
	for d in ad.daterange(start, end):
		a = att.get(d)
		display, label = ad.day_display(d, a, holidays.get(d), today)
		if joined and d < joined and not a:
			display, label = "FUTURE" if d > today else "DAY_OFF", None
		leave_abbr = ((a.abbr or "").strip() or None) if a else None
		if display == "LATE_EARLY" and a and a.late_entry:
			minutes = ad.late_early_minutes(a, ad.shift_for(c.employee, d))[0]
			if minutes:
				label = _("Late {0} min", context="Portal").format(minutes)
		days.append(
			{
				"date": fmt_date(d),
				"display": display,
				"label": label,
				"leave_abbr": leave_abbr,
				"late": bool(a and a.late_entry),
				"early": bool(a and a.early_exit),
				"has_explanation": d in explained,
				"overtime_hours": _hours(a.ot_final) if a and show_ot else None,
			}
		)
		if display in ("PRESENT", "LATE_EARLY"):
			summary["present"] += 1
		if display == "LATE_EARLY":
			summary["late_early"] += 1
		elif display in ("LEAVE", "HALF_LEAVE"):
			summary["leave"] += 1
		elif display == "ABSENT":
			summary["absent"] += 1
		elif display == "HOLIDAY" and d <= today:
			summary["holiday"] += 1

	today_payload = None
	if start <= today <= end:
		punches = ad.checkins_for_day(c.employee, today)
		today_payload = {
			"date": fmt_date(today),
			"check_in": ad.fmt_time(punches[0].time) if punches else None,
			"check_out": ad.fmt_time(punches[-1].time) if len(punches) > 1 else None,
		}
	return {
		"month": start.strftime("%Y-%m"),
		"summary": summary,
		"overtime_summary": overtime_summary,
		"today": today_payload,
		"days": days,
	}


# ---------------------------------------------------------------------------
@portal_api(methods=("GET",), feature="attendance")
def get_attendance_day(date=None):
	c = ctx()
	if not date:
		raise PortalError("VALIDATION", _("Invalid date."), field="date")
	try:
		d = getdate(date)
	except Exception:
		raise PortalError("VALIDATION", _("Invalid date."), field="date")
	today = getdate(nowdate())
	a = ad.attendance_rows(c.employee, d, d).get(d)
	holiday = ad.holidays_between(c.employee, d, d).get(d)
	shift = ad.shift_for(c.employee, d)
	display, label = ad.day_display(d, a, holiday, today)
	punches = ad.checkins_for_day(c.employee, d, a.name if a else None)

	late = early = 0
	if a:
		late, early = ad.late_early_minutes(a, shift)
	leave = None
	if a and (a.abbr or a.leave_type):
		leave = {
			"leave_type_label": ad.leave_type_label(a.leave_type),
			"abbr": (a.abbr or "").strip() or None,
			"half_day": "/" in (a.abbr or ""),
			"application_id": a.leave_application,
		}

	explanations = []
	for r in frappe.get_all(
		"Attendance Request",
		filters={"employee": c.employee, "docstatus": ["<", 2], "from_date": ["<=", d], "to_date": [">=", d]},
		fields=["name", "reason", "docstatus"] + (["custom_approval_status"] if _ar_has("custom_approval_status") else []),
		order_by="creation desc",
	):
		status = explanation_status(r)
		explanations.append(
			{"id": r.name, "reason_label": reason_label(r.reason), "status": status, "status_label": status_label(status)}
		)

	blocked = None
	if d > today:
		blocked = {"code": "FUTURE_DATE", "message": _("You can only explain a past day.")}
	elif any(e["status"] == "PENDING" for e in explanations):
		blocked = {"code": "PENDING_EXISTS", "message": _("An explanation for this day is already waiting for approval.")}
	else:
		blocked = request_blocker(c.employee, c.read_only, feature="explanation_create")

	working_hours = flt(a.working_hours) if a else 0
	show_ot = feature_enabled("overtime")
	return {
		"date": fmt_date(d),
		"weekday_label": ad.weekday_label(d),
		"display": display,
		"status_label": label or (_("Present", context="Portal") if a and a.status in ("Present", "Half Day") else None),
		"late_minutes": late,
		"early_minutes": early,
		"check_in": ad.fmt_time(a.in_time) if a and a.in_time else (ad.fmt_time(punches[0].time) if punches else None),
		"check_out": ad.fmt_time(a.out_time) if a and a.out_time else (ad.fmt_time(punches[-1].time) if len(punches) > 1 else None),
		"shift": ad.public_shift(shift),
		"working_hours": round(working_hours, 2),
		"working_hours_label": ad.hours_label(working_hours),
		"overtime_hours": round(flt(a.ot_final), 2) if a else 0,
		"approved_overtime_hours": round(flt(a.ot_approved), 2) if a and show_ot else None,
		"overtime_registrations": [ot_registration_payload(r) for r in ad.overtime_registrations(c.employee, d, d)]
		if show_ot
		else [],
		"leave": leave,
		"punches": ad.punches_payload(punches),
		"explanations": explanations,
		"can_explain": blocked is None,
		"explain_blocked": blocked,
	}


# ---------------------------------------------------------------------------
@portal_api(methods=("GET",), feature="attendance")
def get_attendance_summary(period=None):
	c = ctx()
	period = _period(period)
	s = ad.period_summary(c.employee, period)
	pay_date = expected_pay_date(period)
	pending_ot = sum(1 for r in ad.overtime_registrations(c.employee, s["from_date"], s["to_date"]) if r["status"] == "PENDING")
	return {
		"period": period,
		"period_label": _("Month {0}").format(period_label(period)),
		"from_date": fmt_date(s["from_date"]),
		"to_date": fmt_date(s["to_date"]),
		"provisional": s["provisional"],
		"as_of": fmt_date(s["as_of"]),
		"cutoff_date": fmt_date(s["to_date"]),
		"adjust_until": fmt_date(ad.adjust_until(period)) if pay_date else None,
		"payable_days": {"value": s["payable_days"], "standard": s["standard_days"], "source": s["source"]},
		"present_days": s["present_days"],
		"paid_leave_days": s["paid_leave_days"],
		"holiday_days": s["holiday_days"],
		"unpaid_absent_days": s["unpaid_absent_days"],
		"late_early": {"count": s["late_early_count"], "minutes": s["late_early_minutes"]},
		"overtime": {"hours": s["ot_hours"], "source": s["source"], "pending_registrations": pending_ot},
	}


# ---------------------------------------------------------------------------
@portal_api(methods=("GET",), feature="overtime")
def get_overtime(period=None):
	c = ctx()
	period = _period(period)
	from_date, to_date = period_bounds(period)
	rows = ad.overtime_registrations(c.employee, from_date, to_date)
	summary = ad.period_summary(c.employee, period)
	return {
		"period": period,
		"from_date": fmt_date(from_date),
		"to_date": fmt_date(to_date),
		"registered_approved_hours": round(sum(r["hours"] for r in rows if r["status"] in ("APPROVED", "REGISTERED")), 2),
		"registered_pending_hours": round(sum(r["hours"] for r in rows if r["status"] == "PENDING"), 2),
		"actual_hours": summary["ot_hours"],
		# `registration_id` kept for clients built before contract 1.1.3 (same value as `id`).
		"items": [{**ot_registration_payload(r), "registration_id": r["registration"]} for r in rows],
	}


# ---------------------------------------------------------------------------
# Explanations (Attendance Request) - read side
# ---------------------------------------------------------------------------
def _ar_has(fieldname):
	return frappe.get_meta("Attendance Request").has_field(fieldname)


def explanation_status(r):
	if cint(r.get("docstatus")) == 2:
		return "CANCELLED"
	approval = r.get("custom_approval_status")
	if approval in ("Rejected", "Cancelled"):
		return approval.upper()
	if cint(r.get("docstatus")) == 1:
		return "APPROVED"
	return "PENDING"


def explanation_detail(name):
	c = ctx()
	doc = frappe.get_doc("Attendance Request", name) if name and frappe.db.exists("Attendance Request", name) else None
	if not doc or doc.employee != c.employee:
		raise PortalError("NOT_FOUND", _("Not found."))
	status = explanation_status(doc.as_dict())
	times = [
		{"date": fmt_date(r.date), "check_in": ad.fmt_time(r.new_in_time), "check_out": ad.fmt_time(r.new_out_time)}
		for r in (doc.get("custom_checkin_details") or [])
	]
	source = doc.get("custom_source")
	source = "MINI_APP" if source == "Mini App" or doc.owner == "portal@tiqn.com.vn" else "DESK"
	approver_user = doc.get("custom_approver") or frappe.db.get_value("Employee", doc.employee, "leave_approver")
	decided = status in ("APPROVED", "REJECTED")
	return {
		"id": doc.name,
		"reason": doc.reason,
		"reason_label": reason_label(doc.reason),
		"from_date": fmt_date(doc.from_date),
		"to_date": fmt_date(doc.to_date),
		"explanation": doc.explanation,
		"times": times,
		"status": status,
		"status_label": status_label(status),
		"approver": person(approver_user),
		"approver_note": doc.get("custom_approver_note"),
		"source": source,
		"created_at": fmt_datetime(doc.creation),
		"decided_at": fmt_datetime(doc.modified) if decided else None,
		"can_cancel": status == "PENDING" and doc.docstatus == 0 and source == "MINI_APP" and not c.read_only,
	}


@portal_api(methods=("GET",), feature="attendance")
def get_attendance_requests(status=None, page=None, page_size=None):
	c = ctx()
	page, page_size = paging(page, page_size)
	fields = ["name", "reason", "from_date", "to_date", "docstatus", "creation"]
	if _ar_has("custom_approval_status"):
		fields.append("custom_approval_status")
	rows = frappe.get_all(
		"Attendance Request", filters={"employee": c.employee}, fields=fields, order_by="from_date desc, creation desc"
	)
	wanted = (status or "").strip().upper()
	if wanted:
		rows = [r for r in rows if explanation_status(r) == wanted]
	page_rows = rows[(page - 1) * page_size : page * page_size]
	return {
		"items": [
			{
				"id": r.name,
				"reason_label": reason_label(r.reason),
				"from_date": fmt_date(r.from_date),
				"to_date": fmt_date(r.to_date),
				"status": explanation_status(r),
				"status_label": status_label(explanation_status(r)),
				"created_at": fmt_datetime(r.creation),
			}
			for r in page_rows
		],
		"page": page,
		"page_size": page_size,
		"has_more": len(rows) > page * page_size,
	}


@portal_api(methods=("GET",), feature="attendance")
def get_attendance_request(id=None):
	return explanation_detail(id)
