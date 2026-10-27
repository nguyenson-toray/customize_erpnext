# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""SAMPLE data for Zalo's app reviewers (Settings > Zalo App Review).

A reviewer session (login_method REVIEW) has no employee: `portal_api` answers every
authenticated endpoint from `respond()` here and never runs the real endpoint. Nothing
below reads an Employee, Attendance, Leave Application or TIQN Payslip row; the only
row touched is the reviewer's own TIQN Portal Account (OA follow, notifications seen).

The data is generated from today's date, so the app always looks current. Shapes are
the ones of the real endpoints (test_employee_portal checks the keys match). The
names and amounts are made up; they are Vietnamese data, like real records, not UI.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, nowdate

from customize_erpnext.api.employee_portal import attendance as att_api
from customize_erpnext.api.employee_portal.auth import chat_payload, oa_payload
from customize_erpnext.api.employee_portal.core import (
	PortalError,
	access_payload,
	ctx,
	feature_enabled,
	fmt_date,
	fmt_datetime,
)
from customize_erpnext.api.employee_portal.notifications import paging
from customize_erpnext.api.employee_portal.payslip import build_payslip_payload
from customize_erpnext.employee_portal import attendance_data as ad
from customize_erpnext.employee_portal.requests_common import DOCUMENT_LEAVE_TYPES, status_label
from customize_erpnext.employee_portal.utils import (
	expected_pay_date,
	initials,
	mask_phone,
	period_bounds,
	period_label,
	period_of_date,
	shift_period,
	validate_period,
)

EMPLOYEE_ID = "DEMO-0001"
FULL_NAME = "Nguyễn Văn Mẫu"
DEPARTMENT = "Hành chính"
SECTION = "Văn phòng"
JOINED = datetime.date(2024, 3, 1)
APPROVER = {"full_name": "Trần Thị Duyệt", "initials": "TD", "designation": "Trưởng phòng"}
ANNUAL = "Phép năm/ Annual leave"
SHIFT = {
	"name": "Day",
	"label": ad.shift_label("Day"),
	"start": "08:00",
	"end": "17:00",
	"_start": datetime.timedelta(hours=8),
	"_end": datetime.timedelta(hours=17),
}


def employee():
	return {
		"employee_id": EMPLOYEE_ID,
		"full_name": FULL_NAME,
		"initials": initials(FULL_NAME),
		"designation": "Nhân viên",
		"department": DEPARTMENT,
		"section": SECTION,
		"group": None,
		"date_of_joining": fmt_date(JOINED),
		"relieving_date": None,
		"avatar_url": None,
	}


def respond(endpoint, kwargs):
	handler = HANDLERS.get(endpoint)
	if not handler:  # never fall through to the real endpoint
		raise PortalError("NOT_FOUND", _("Not found."))
	return handler(**kwargs)


# ---------------------------------------------------------------------------
# Account (the reviewer's own TIQN Portal Account row only)
# ---------------------------------------------------------------------------
def _account(*fields):
	return frappe.db.get_value("TIQN Portal Account", ctx().account, list(fields), as_dict=True) or frappe._dict()


def me():
	c = ctx()
	account = _account("followed_oa", "oa_invite_dismissed", "phone")
	return {
		"employee": employee(),
		"access": access_payload(c),
		"zalo_user_id": c.account,
		"login_method": c.login_method,
		"masked_phone": mask_phone(account.phone),
		"session_expires_on": fmt_datetime(c.session_expires_on),
		"oa": oa_payload(account),
		"chat": chat_payload(),
	}


def set_oa_follow(action=None):
	values = {
		"FOLLOWED": {"followed_oa": 1},
		"UNFOLLOWED": {"followed_oa": 0},
		"DISMISSED": {"oa_invite_dismissed": 1},
	}.get((action or "").strip().upper())
	if values is None:
		raise PortalError("VALIDATION", _("action must be FOLLOWED, UNFOLLOWED or DISMISSED."), field="action")
	frappe.db.set_value("TIQN Portal Account", ctx().account, values)
	return oa_payload(_account("followed_oa", "oa_invite_dismissed"))


def set_id_by_oa(id_by_oa=None):
	return {"saved": False}


# ---------------------------------------------------------------------------
# Attendance - one made-up day per date
# ---------------------------------------------------------------------------
def _today():
	return getdate(nowdate())


def _at(d, hhmm):
	h, m = (int(x) for x in hhmm.split(":"))
	return datetime.datetime.combine(d, datetime.time(h, m))


def _holiday(d):
	return {"weekly_off": True, "label": ad.weekday_label(d)} if d.weekday() == 6 else None


def _att(d):
	"""Attendance-like row of `d` (fields of attendance_data.ATT_FIELDS), or None."""
	if d.weekday() == 6 or d >= _today() or d < JOINED:
		return None
	row = frappe._dict(
		name=None, attendance_date=d, status="Present", leave_type=None, leave_application=None, abbr=None,
		working_hours=8, in_time=_at(d, f"07:{45 + d.day % 10}"), out_time=_at(d, "17:02"),
		late_entry=0, early_exit=0, shift="Day", ot_final=0, ot_approved=0,
	)
	if d.day == 18 and d.month % 3 == 1:
		row.update(status="On Leave", leave_type=ANNUAL, abbr="P", working_hours=0, in_time=None, out_time=None)
	elif d.day == 9 and d.month % 4 == 2:
		row.update(status="Half Day", leave_type=ANNUAL, abbr="P/2", working_hours=4, out_time=_at(d, "12:01"))
	elif d.day % 11 == 3:
		row.update(late_entry=1, in_time=_at(d, "08:12"), working_hours=7.8)
	elif d.day % 4 == 0:
		row.update(out_time=_at(d, "19:03"), ot_final=2, ot_approved=2)
	return row


def _punches(d, row):
	if d == _today():
		now = now_datetime()
		return [frappe._dict(time=_at(d, "07:52"), log_type="IN", device_id="Cổng chính", custom_reason_for_manual_check_in=None)] if now >= _at(d, "07:52") else []
	if not row or not row.in_time:
		return []
	return [
		frappe._dict(time=row.in_time, log_type="IN", device_id="Cổng chính", custom_reason_for_manual_check_in=None),
		frappe._dict(time=row.out_time, log_type="OUT", device_id="Cổng chính", custom_reason_for_manual_check_in=None),
	]


def _overtime(from_date, to_date):
	out = []
	for d in ad.daterange(from_date, to_date):
		row = _att(d)
		if row and row.ot_final:
			out.append({"date": d, "begin": "17:00", "end": "19:00", "hours": 2.0, "reason": "Tăng ca theo kế hoạch sản xuất",
			            "status": "APPROVED", "registration": f"DEMO-OT-{d:%Y%m%d}"})
	return sorted(out, key=lambda r: r["date"], reverse=True)


def _summary(period):
	from_date, to_date = period_bounds(period)
	today = _today()
	as_of = min(today, to_date)
	start = max(from_date, JOINED)
	payable = present = paid_leave = 0.0
	late_count = late_minutes = 0
	ot = 0.0
	for d in ad.daterange(start, min(to_date, as_of)):
		row = _att(d)
		if not row:
			continue
		payable += ad.day_working_days(row)
		present += 1 if flt(row.working_hours) > 0 else 0
		paid_leave += ad.PAID_LEAVE_CODES.get(row.abbr or "", 0)
		if row.late_entry:
			late_count += 1
			late_minutes += ad.late_early_minutes(row, SHIFT)[0]
		ot += flt(row.ot_final)
	return {
		"from_date": from_date,
		"to_date": to_date,
		"as_of": as_of,
		"provisional": today <= getdate(ad.adjust_until(period)),
		"payable_days": round(payable, 2),
		"standard_days": sum(1 for d in ad.daterange(start, to_date) if d.weekday() != 6),
		"present_days": present,
		"paid_leave_days": paid_leave,
		"holiday_days": 0.0,
		"unpaid_absent_days": 0.0,
		"late_early_count": late_count,
		"late_early_minutes": late_minutes,
		"ot_hours": round(ot, 2),
		"source": "ERP",
	}


def _workday_back(n):
	"""The n-th working day (Mon-Sat) before today."""
	d = _today()
	while n:
		d = add_days(d, -1)
		if d.weekday() != 6:
			n -= 1
	return d


def _explanations():
	pending, approved = _workday_back(3), _workday_back(9)
	return [
		{"id": "DEMO-AR-2", "reason": "Machine Error", "date": pending, "status": "PENDING",
		 "explanation": "Máy chấm công cổng chính không nhận vân tay buổi sáng.", "check_in": "07:50", "check_out": "17:05"},
		{"id": "DEMO-AR-1", "reason": "Forget Check In/Out", "date": approved, "status": "APPROVED",
		 "explanation": "Quên chấm công lúc ra về.", "check_in": "07:48", "check_out": "17:03"},
	]


def _today_card():
	today = _today()
	punches = _punches(today, None)
	if today.weekday() == 6:
		state = "DAY_OFF"
	elif not punches:
		state = "NOT_CHECKED_IN"
	else:
		state = "WORKING"
	labels = {"NOT_CHECKED_IN": "Not Checked In", "WORKING": "Working", "DAY_OFF": "Day Off"}
	return {
		"date": fmt_date(today),
		"weekday_label": ad.weekday_label(today),
		"state": state,
		"state_label": _(labels[state], context="Portal"),
		"check_in": ad.fmt_time(punches[0].time) if punches else None,
		"check_out": None,
		"shift": None if state == "DAY_OFF" else ad.public_shift(SHIFT),
		"updated_at": fmt_datetime(punches[0].time) if punches else None,
	}


def get_attendance_calendar(month=None):
	start, end = att_api._month(month)
	today = _today()
	show_ot = feature_enabled("overtime")
	explained = {e["date"] for e in _explanations()}
	summary = {"present": 0, "leave": 0, "absent": 0, "late_early": 0, "holiday": 0}
	days, ot_actual = [], 0.0
	for d in ad.daterange(start, end):
		a = _att(d)
		display, label = ad.day_display(d, a, _holiday(d), today)
		if d < JOINED and not a:
			display, label = "DAY_OFF", None
		if display == "LATE_EARLY" and a and a.late_entry:
			label = _("Late {0} min", context="Portal").format(ad.late_early_minutes(a, SHIFT)[0])
		ot_actual += flt(a.ot_final) if a else 0
		days.append(
			{
				"date": fmt_date(d),
				"display": display,
				"label": label,
				"leave_abbr": (a.abbr or None) if a else None,
				"late": bool(a and a.late_entry),
				"early": bool(a and a.early_exit),
				"has_explanation": d in explained,
				"overtime_hours": att_api._hours(a.ot_final) if a and show_ot else None,
			}
		)
		if display in ("PRESENT", "LATE_EARLY"):
			summary["present"] += 1
		if display == "LATE_EARLY":
			summary["late_early"] += 1
		elif display in ("LEAVE", "HALF_LEAVE"):
			summary["leave"] += 1
	today_payload = None
	if start <= today <= end:
		punches = _punches(today, None)
		today_payload = {"date": fmt_date(today), "check_in": ad.fmt_time(punches[0].time) if punches else None, "check_out": None}
	return {
		"month": start.strftime("%Y-%m"),
		"summary": summary,
		"overtime_summary": {"actual_hours": round(ot_actual, 2), "approved_hours": round(ot_actual, 2)} if show_ot else None,
		"today": today_payload,
		"days": days,
	}


def get_attendance_day(date=None):
	try:
		d = getdate(date) if date else None
	except Exception:
		d = None
	if not d:
		raise PortalError("VALIDATION", _("Invalid date."), field="date")
	today = _today()
	a = _att(d)
	display, label = ad.day_display(d, a, _holiday(d), today)
	punches = _punches(d, a)
	late, early = ad.late_early_minutes(a, SHIFT) if a else (0, 0)
	leave = None
	if a and a.abbr:
		leave = {"leave_type_label": ad.leave_type_label(a.leave_type), "abbr": a.abbr, "half_day": "/" in a.abbr, "application_id": None}
	explanations = [
		{"id": e["id"], "reason_label": att_api.reason_label(e["reason"]), "status": e["status"], "status_label": status_label(e["status"])}
		for e in _explanations()
		if e["date"] == d
	]
	if d > today:
		blocked = {"code": "FUTURE_DATE", "message": _("You can only explain a past day.")}
	elif any(e["status"] == "PENDING" for e in explanations):
		blocked = {"code": "PENDING_EXISTS", "message": _("An explanation for this day is already waiting for approval.")}
	elif not feature_enabled("explanation_create"):
		blocked = {"code": "FEATURE_DISABLED", "message": _("This feature is currently turned off.")}
	else:
		blocked = None
	working_hours = flt(a.working_hours) if a else 0
	show_ot = feature_enabled("overtime")
	return {
		"date": fmt_date(d),
		"weekday_label": ad.weekday_label(d),
		"display": display,
		"status_label": label or (_("Present", context="Portal") if a and a.status in ("Present", "Half Day") else None),
		"late_minutes": late,
		"early_minutes": early,
		"check_in": ad.fmt_time(punches[0].time) if punches else None,
		"check_out": ad.fmt_time(punches[-1].time) if len(punches) > 1 else None,
		"shift": ad.public_shift(SHIFT),
		"working_hours": round(working_hours, 2),
		"working_hours_label": ad.hours_label(working_hours),
		"overtime_hours": round(flt(a.ot_final), 2) if a else 0,
		"approved_overtime_hours": round(flt(a.ot_approved), 2) if a and show_ot else None,
		"overtime_registrations": [att_api.ot_registration_payload(r) for r in _overtime(d, d)] if show_ot else [],
		"leave": leave,
		"punches": ad.punches_payload(punches),
		"explanations": explanations,
		"can_explain": blocked is None,
		"explain_blocked": blocked,
	}


def get_attendance_summary(period=None):
	period = att_api._period(period)
	s = _summary(period)
	return {
		"period": period,
		"period_label": _("Month {0}").format(period_label(period)),
		"from_date": fmt_date(s["from_date"]),
		"to_date": fmt_date(s["to_date"]),
		"provisional": s["provisional"],
		"as_of": fmt_date(s["as_of"]),
		"cutoff_date": fmt_date(s["to_date"]),
		"adjust_until": fmt_date(ad.adjust_until(period)) if expected_pay_date(period) else None,
		"payable_days": {"value": s["payable_days"], "standard": s["standard_days"], "source": s["source"]},
		"present_days": s["present_days"],
		"paid_leave_days": s["paid_leave_days"],
		"holiday_days": s["holiday_days"],
		"unpaid_absent_days": s["unpaid_absent_days"],
		"late_early": {"count": s["late_early_count"], "minutes": s["late_early_minutes"]},
		"overtime": {"hours": s["ot_hours"], "source": s["source"], "pending_registrations": 0},
	}


def get_overtime(period=None):
	period = att_api._period(period)
	from_date, to_date = period_bounds(period)
	rows = _overtime(from_date, min(to_date, add_days(_today(), -1)))
	return {
		"period": period,
		"from_date": fmt_date(from_date),
		"to_date": fmt_date(to_date),
		"registered_approved_hours": round(sum(r["hours"] for r in rows), 2),
		"registered_pending_hours": 0,
		"actual_hours": _summary(period)["ot_hours"],
		"items": [{**att_api.ot_registration_payload(r), "registration_id": r["registration"]} for r in rows],
	}


def _explanation_created(e):
	return get_datetime(f"{e['date']} 17:30:00")


def get_attendance_requests(status=None, page=None, page_size=None):
	page, page_size = paging(page, page_size)
	rows = _explanations()
	wanted = (status or "").strip().upper()
	if wanted:
		rows = [e for e in rows if e["status"] == wanted]
	page_rows = rows[(page - 1) * page_size : page * page_size]
	return {
		"items": [
			{
				"id": e["id"],
				"reason_label": att_api.reason_label(e["reason"]),
				"from_date": fmt_date(e["date"]),
				"to_date": fmt_date(e["date"]),
				"status": e["status"],
				"status_label": status_label(e["status"]),
				"created_at": fmt_datetime(_explanation_created(e)),
			}
			for e in page_rows
		],
		"page": page,
		"page_size": page_size,
		"has_more": len(rows) > page * page_size,
	}


def get_attendance_request(id=None):
	e = next((e for e in _explanations() if e["id"] == id), None)
	if not e:
		raise PortalError("NOT_FOUND", _("Not found."))
	decided = e["status"] == "APPROVED"
	return {
		"id": e["id"],
		"reason": e["reason"],
		"reason_label": att_api.reason_label(e["reason"]),
		"from_date": fmt_date(e["date"]),
		"to_date": fmt_date(e["date"]),
		"explanation": e["explanation"],
		"times": [{"date": fmt_date(e["date"]), "check_in": e["check_in"], "check_out": e["check_out"]}],
		"status": e["status"],
		"status_label": status_label(e["status"]),
		"approver": APPROVER,
		"approver_note": "Đã xác nhận." if decided else None,
		"source": "MINI_APP",
		"created_at": fmt_datetime(_explanation_created(e)),
		"decided_at": fmt_datetime(add_days(_explanation_created(e), 1)) if decided else None,
		"can_cancel": False,
	}


# ---------------------------------------------------------------------------
# Leave
# ---------------------------------------------------------------------------
def _annual_type():
	types = ad.annual_leave_types()
	return ANNUAL if ANNUAL in types or not types else types[0]


def _annual_balance():
	used = float(sum(ad.PAID_LEAVE_CODES.get(r.abbr or "", 0) for d in ad.daterange(datetime.date(_today().year, 1, 1), _today()) if (r := _att(d))))
	allocated = float(min(_today().month, 12))
	remaining = round(allocated - used, 2)
	return {"allocated": allocated, "used": used, "pending": 1.0, "remaining": remaining, "available": round(remaining - 1, 2)}


def _leaves():
	"""Two approved (dates the calendar shows as P) + one pending, newest first."""
	today = _today()
	taken = [d for d in ad.daterange(add_days(today, -200), add_days(today, -1)) if (r := _att(d)) and r.abbr == "P"][-2:]
	upcoming = add_days(today, 10)
	while upcoming.weekday() == 6:
		upcoming = add_days(upcoming, 1)
	rows = [{"id": "DEMO-LA-3", "date": upcoming, "status": "PENDING", "reason": "Về quê giải quyết việc gia đình."}]
	for i, d in enumerate(reversed(taken)):
		rows.append({"id": f"DEMO-LA-{2 - i}", "date": d, "status": "APPROVED", "reason": "Việc cá nhân."})
	return rows


def _leave_created(row):
	return get_datetime(f"{add_days(row['date'], -5)} 09:15:00")


def _leave_item(row):
	leave_type = _annual_type()
	return {
		"id": row["id"],
		"leave_type": leave_type,
		"leave_type_label": ad.leave_type_label(leave_type),
		"from_date": fmt_date(row["date"]),
		"to_date": fmt_date(row["date"]),
		"half_day": False,
		"half_day_date": None,
		"days": 1.0,
		"status": row["status"],
		"status_label": status_label(row["status"]),
		"needs_documents": False,
		"document_count": 0,
		"source": "MINI_APP",
		"created_at": fmt_datetime(_leave_created(row)),
	}


def get_leave_balances(year=None):
	year = cint(year) or _today().year
	leave_type = _annual_type()
	annual = {"leave_type": leave_type, "label": ad.leave_type_label(leave_type), **_annual_balance()} if year == _today().year else None
	others = [
		{"leave_type": lt, "label": ad.leave_type_label(lt), "balance": None, "note": _("Per medical documents", context="Portal")}
		for lt in DOCUMENT_LEAVE_TYPES
	]
	return {"year": year, "annual": annual, "others": others}


def get_leave_applications(year=None, status=None, page=None, page_size=None):
	year = cint(year) or _today().year
	page, page_size = paging(page, page_size)
	rows = [r for r in _leaves() if r["date"].year == year]
	counts = {"ALL": len(rows), "PENDING": 0, "APPROVED": 0, "REJECTED": 0, "CANCELLED": 0}
	for r in rows:
		counts[r["status"]] += 1
	wanted = (status or "").strip().upper()
	if wanted:
		if wanted not in counts or wanted == "ALL":
			raise PortalError("VALIDATION", _("Unknown status {0}.").format(status), field="status")
		rows = [r for r in rows if r["status"] == wanted]
	page_rows = rows[(page - 1) * page_size : page * page_size]
	return {
		"years_available": sorted({r["date"].year for r in _leaves()} | {_today().year}, reverse=True),
		"counts": counts,
		"items": [_leave_item(r) for r in page_rows],
		"page": page,
		"page_size": page_size,
		"has_more": len(rows) > page * page_size,
	}


def get_leave_application(id=None):
	row = next((r for r in _leaves() if r["id"] == id), None)
	if not row:
		raise PortalError("NOT_FOUND", _("Not found."))
	created = _leave_created(row)
	timeline = [{"event": "SUBMITTED", "label": _("Submitted", context="Portal"), "at": fmt_datetime(created), "by": None, "note": None, "done": True}]
	if row["status"] == "PENDING":
		timeline.append({"event": "UNDER_REVIEW", "label": _("Under review", context="Portal"), "at": None, "by": APPROVER["full_name"], "note": None, "done": False})
	else:
		timeline.append({"event": "APPROVED", "label": status_label("APPROVED"), "at": fmt_datetime(add_days(created, 1)), "by": APPROVER["full_name"], "note": None, "done": True})
	item = _leave_item(row)
	item.pop("document_count")
	return {
		**item,
		"reason": row["reason"],
		"approver": APPROVER,
		"documents_request_note": None,
		"approver_note": None,
		"timeline": timeline,
		"documents": [],
		"allows_documents": False,
		"can_cancel": False,
		"can_add_documents": False,
	}


# ---------------------------------------------------------------------------
# Payslips - an unsaved TIQN Payslip through the real serialiser
# ---------------------------------------------------------------------------
def _periods():
	"""The last two ENDED periods, both published (newest first)."""
	last = shift_period(period_of_date(_today()), -1)
	return [last, shift_period(last, -1)]


def _published_on(period):
	"""16:00 on the last day of the period: already past (the period has ended) and
	stable - published_at is the Mini App's cache key of the payslip."""
	return get_datetime(f"{period_bounds(period)[1]} 16:00:00")


def _payslip_doc(period):
	from_date, to_date = period_bounds(period)
	ot_normal = 10 if period == _periods()[0] else 6
	ot_weekend = 8 if period == _periods()[0] else 0
	hourly = 6_500_000 / 26 / 8
	v = {
		"sc_1_1": 26, "sc_1_2": 6_250_000, "sc_1_2_qty": 25,
		"sc_2_1": round(ot_normal * hourly * 1.5), "sc_2_1_qty": ot_normal,
		"sc_2_2": round(ot_weekend * hourly * 2), "sc_2_2_qty": ot_weekend,
		"sc_3_2": 300_000, "sc_3_5": 200_000, "sc_3_6": 100_000, "sc_3_8": 150_000,
		"sc_4_1": 300_000, "sc_4_3": 500_000, "sc_4_7": 200_000,
		"sc_6_1": 520_000, "sc_6_2": 97_500, "sc_6_3": 65_000, "sc_6_4": 65_000, "sc_6_5": 0,
		"sc_7_1": 650_000, "sc_8": 0,
	}
	v["sc_1"] = v["sc_1_2"]
	v["sc_2"] = v["sc_2_1"] + v["sc_2_2"]
	v["sc_3"] = v["sc_1"] + v["sc_2"]
	v["sc_3_1"] = sum(v[f"sc_3_{i}"] for i in (2, 5, 6, 8))
	v["sc_4"] = sum(v[f"sc_4_{i}"] for i in (1, 3, 7))
	v["sc_5"] = v["sc_3"] + v["sc_3_1"] + v["sc_4"]
	v["sc_6"] = sum(v[f"sc_6_{i}"] for i in range(1, 6))
	v["sc_7"] = v["sc_7_1"]
	v["sc_9"] = v["sc_5"] - v["sc_6"] + v["sc_7"] + v["sc_8"]
	doc = frappe.new_doc("TIQN Payslip")  # never inserted
	doc.update(v)
	doc.update(
		{
			"employee": EMPLOYEE_ID,
			"employee_name": FULL_NAME,
			"department": DEPARTMENT,
			"section": SECTION,
			"period": period,
			"period_from": from_date,
			"period_to": to_date,
			"pay_date": expected_pay_date(period),
			"published_on": _published_on(period),
			"net_pay": v["sc_9"],
			"note": "Đây là phiếu lương mẫu dành cho bộ phận kiểm duyệt Zalo.",
		}
	)
	return doc


def get_payslip_periods(year=None):
	current_year = int(period_of_date(_today())[:4])
	year = cint(year) or current_year
	periods = _periods()
	seen = {p for p in periods if frappe.cache.get_value(_viewed_key(p))}
	return {
		"year": year,
		"years_available": sorted({int(p[:4]) for p in periods} | {current_year}, reverse=True),
		"upcoming": None,
		"items": [
			{
				"period": p,
				"label": _("Month {0}").format(period_label(p)),
				"status": "PUBLISHED",
				"period_from": fmt_date(period_bounds(p)[0]),
				"period_to": fmt_date(period_bounds(p)[1]),
				"pay_date": fmt_date(expected_pay_date(p)),
				"published_on": fmt_datetime(_published_on(p)),
				"is_new": p not in seen,
			}
			for p in periods
			if int(p[:4]) == year
		],
	}


def _viewed_key(period):
	return f"employee_portal:demo_viewed:{ctx().account}:{period}"


def get_payslip(period=None, include_zero=None):
	try:
		period = validate_period(period)
	except frappe.ValidationError:
		raise PortalError("VALIDATION", _("Period must look like YYYY-MM."), field="period")
	if period not in _periods():
		raise PortalError("NOT_FOUND", _("This payslip is not available."))
	if include_zero in (None, ""):
		include_zero = cint(frappe.db.get_single_value("Employee Portal Settings", "show_zero_lines"))
	frappe.cache.set_value(_viewed_key(period), 1, expires_in_sec=30 * 86400)
	return build_payslip_payload(_payslip_doc(period), bool(cint(include_zero)))


# ---------------------------------------------------------------------------
# Notifications ("seen" mark kept on the reviewer's own account, as for employees)
# ---------------------------------------------------------------------------
def _notifications():
	latest, previous = _periods()
	rows = [
		("DEMO-N-3", "PAYSLIP_PUBLISHED", f"Phiếu lương {period_label(latest)}", "Phiếu lương của bạn đã có. Bấm để xem chi tiết.",
		 _published_on(latest), "PAYSLIP", latest),
		("DEMO-N-2", "GENERAL", "Chào mừng đến với Cổng nhân viên", "Đây là dữ liệu mẫu dành cho bộ phận kiểm duyệt Zalo.",
		 get_datetime(f"{add_days(_today(), -20)} 08:00:00"), None, None),
		("DEMO-N-1", "PAYSLIP_PUBLISHED", f"Phiếu lương {period_label(previous)}", "Phiếu lương của bạn đã có. Bấm để xem chi tiết.",
		 _published_on(previous), "PAYSLIP", previous),
	]
	rows = [frappe._dict(name=r[0], type=r[1], title=r[2], body=r[3], creation=r[4], target_screen=r[5], target_id=r[6]) for r in rows]
	return sorted(rows, key=lambda r: r.creation, reverse=True)


def _seen():
	return _account("notifications_seen_on").notifications_seen_on


def _notification(n, seen):
	return {
		"id": n.name,
		"type": n.type,
		"title": n.title,
		"body": n.body,
		"created_at": fmt_datetime(n.creation),
		"is_read": bool(seen and n.creation <= get_datetime(seen)),
		"target": {"screen": n.target_screen or "NONE", "id": n.target_id or None},
	}


def _unread(seen):
	return sum(1 for n in _notifications() if not seen or n.creation > get_datetime(seen))


def get_notifications(page=None, page_size=None, unread_only=None):
	page, page_size = paging(page, page_size)
	seen = _seen()
	rows = [n for n in _notifications() if not cint(unread_only) or not seen or n.creation > get_datetime(seen)]
	return {
		"unread": _unread(seen),
		"items": [_notification(n, seen) for n in rows[(page - 1) * page_size : page * page_size]],
		"page": page,
		"page_size": page_size,
		"has_more": len(rows) > page * page_size,
	}


def mark_notifications_read(ids=None, all=None):
	if cint(all):
		upto = now_datetime()
	else:
		if isinstance(ids, str):
			ids = frappe.parse_json(ids) if ids.strip().startswith("[") else [x.strip() for x in ids.split(",")]
		ids = {x for x in (ids or []) if x}
		if not ids:
			raise PortalError("VALIDATION", _("Send ids, or all=1."), field="ids")
		mine = [n.creation for n in _notifications() if n.name in ids]
		upto = max(mine) if mine else None
	current = _seen()
	if upto and (not current or upto > get_datetime(current)):
		frappe.db.set_value("TIQN Portal Account", ctx().account, "notifications_seen_on", upto, update_modified=False)
	return {"unread": _unread(_seen())}


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
def get_home():
	c = ctx()
	account = _account("followed_oa", "oa_invite_dismissed")
	data = {
		"employee": employee(),
		"access": access_payload(c),
		"today": None,
		"annual_leave": None,
		"attendance": None,
		"overtime": None,
		"latest_payslip": None,
		"notifications": None,
		"oa": oa_payload(account),
		"chat": chat_payload(),
	}
	if feature_enabled("attendance"):
		data["today"] = _today_card()
		period = period_of_date(_today())
		s = _summary(period)
		data["attendance"] = {
			"period": period,
			"period_label": _("Attendance {0}", context="Portal").format(period.split("-")[1]),
			"payable_days": s["payable_days"],
			"standard_days": s["standard_days"],
			"source": s["source"],
			"provisional": s["provisional"],
		}
		if feature_enabled("overtime"):
			data["overtime"] = {"period": period, "hours": s["ot_hours"], "source": s["source"]}
	if feature_enabled("leave_view"):
		b = _annual_balance()
		data["annual_leave"] = {"year": _today().year, "remaining": b["remaining"], "available": b["available"]}
	if feature_enabled("payslip"):
		latest = _periods()[0]
		data["latest_payslip"] = {
			"period": latest,
			"label": _("Payslip {0}").format(period_label(latest)),
			"published_on": fmt_date(_published_on(latest)),
			"published_at": fmt_datetime(_published_on(latest)),
		}
	if feature_enabled("notifications"):
		seen = _seen()
		notes = _notifications()
		data["notifications"] = {"unread": _unread(seen), "latest": _notification(notes[0], seen) if notes else None}
	return data


HANDLERS = {
	fn.__name__: fn
	for fn in (
		me,
		set_oa_follow,
		set_id_by_oa,
		get_home,
		get_notifications,
		mark_notifications_read,
		get_payslip_periods,
		get_payslip,
		get_attendance_calendar,
		get_attendance_day,
		get_attendance_summary,
		get_overtime,
		get_attendance_requests,
		get_attendance_request,
		get_leave_balances,
		get_leave_applications,
		get_leave_application,
	)
}
