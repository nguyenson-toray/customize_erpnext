# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Attendance / leave / overtime numbers for ONE employee, for the Mini App.

Nothing here invents a rule. Each number comes from the source the Desk already uses:

| Number                     | Source                                                            |
|----------------------------|-------------------------------------------------------------------|
| Working days of one day    | `timesheet_working_days(abbr, working_hours)` - the Timesheet sheet |
| Holidays / Sundays         | the Holiday List covering the date (Employee's, else any year list)|
| Shift                      | Shift Assignment -> Employee.default_shift -> "Day"                |
| Annual leave balance       | HRMS `get_leave_details` (what the Leave Application form shows)   |
| Overtime hours (paid)      | Attendance.custom_final_overtime_duration                          |
| OT registrations           | Overtime Registration Detail; drafts count when include_draft_ot  |

Period totals are ALWAYS summed from Attendance, even after the payslip is published
(D14 "take 1.2 / 2.1-2.3 from the payslip" was dropped 15/10/2026): calendar, day and
summary must add up. The paid numbers are shown on the payslip itself.
"""

import datetime
from contextlib import contextmanager

import frappe
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime, nowdate

from customize_erpnext.employee_portal.utils import expected_pay_date, period_bounds

# Full-day codes of the leave rules (QUY_DINH_NGHI_PHEP_2025 §3) that are PAID.
PAID_LEAVE_CODES = {"P": 1.0, "P/2": 0.5, "MC": 1.0, "HS": 1.0, "HL": 1.0, "HL/2": 0.5}
# Leave Type names are bilingual data ("Phép năm/ Annual leave"); the Vietnamese half is
# what employees read. One override where the short half alone reads badly.
LEAVE_LABEL_OVERRIDES = {
	"Nghỉ hưởng BHXH/ Social insurance leave - Ốm đau": "Nghỉ ốm (BHXH)",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
@contextmanager
def as_administrator():
	"""HRMS balance helpers call validate_leave_access() against the session user; the
	portal service user has no Employee permission. Read-only use, restored at once."""
	previous = frappe.session.user
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(previous)


def leave_type_label(leave_type):
	""""Nghỉ hưởng lương/ Paid leave - Hỉ sự" -> "Hỉ sự"; "Phép năm/ Annual leave" -> "Phép năm"."""
	if not leave_type:
		return None
	if leave_type in LEAVE_LABEL_OVERRIDES:
		return LEAVE_LABEL_OVERRIDES[leave_type]
	if " - " in leave_type:
		label = leave_type.rsplit(" - ", 1)[1].strip()
		return f"{label} (BHXH)" if "BHXH" in leave_type else label
	return leave_type.split("/", 1)[0].strip()


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAYS_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _p(text):
	"""Translate a Mini App label (context "Portal" keeps it apart from Desk translations)."""
	return frappe._(text, context="Portal")


def weekday_label(date, short=False):
	date = getdate(date)
	return _p((WEEKDAYS_SHORT if short else WEEKDAYS)[date.weekday()])


def fmt_time(value):
	if not value:
		return None
	if isinstance(value, datetime.timedelta):
		total = int(value.total_seconds())
		return f"{total // 3600 % 24:02d}:{total // 60 % 60:02d}"
	return get_datetime(value).strftime("%H:%M")


def hours_label(hours):
	minutes = int(round(flt(hours) * 60))
	if minutes % 60:
		return _p("{0} h {1:02d}").format(minutes // 60, minutes % 60)
	return _p("{0} h").format(minutes // 60)


def daterange(start, end):
	d = getdate(start)
	end = getdate(end)
	while d <= end:
		yield d
		d = add_days(d, 1)


# ---------------------------------------------------------------------------
# Holidays & shifts
# ---------------------------------------------------------------------------
def holidays_between(employee, from_date, to_date):
	"""{date: {"weekly_off": bool, "label": str}} from the Holiday List(s) covering the range.

	Every Employee.holiday_list is NULL at TIQN and the year lists run 26/12 -> 25/12,
	so a range can span two lists; all lists overlapping the range are read.
	"""
	from frappe.utils import strip_html

	explicit = frappe.db.get_value("Employee", employee, "holiday_list")
	if explicit:
		lists = [explicit]
	else:
		lists = frappe.get_all(
			"Holiday List",
			filters={"from_date": ["<=", to_date], "to_date": [">=", from_date]},
			pluck="name",
		)
	if not lists:
		return {}
	rows = frappe.get_all(
		"Holiday",
		filters={"parent": ["in", lists], "holiday_date": ["between", [from_date, to_date]]},
		fields=["holiday_date", "weekly_off", "description"],
	)
	out = {}
	for r in rows:
		d = getdate(r.holiday_date)
		label = _p(strip_html(r.description or "").strip()) if not r.weekly_off else _p("Sunday")
		if d not in out or not r.weekly_off:
			out[d] = {"weekly_off": bool(r.weekly_off), "label": label or None}
	return out


def shift_for(employee, date):
	from customize_erpnext.overrides.shift_type.shift_type import get_employee_shift

	name = get_employee_shift(employee, date) or "Day"
	shift = frappe.get_cached_value("Shift Type", name, ["start_time", "end_time"], as_dict=True)
	if not shift:
		return None
	return {"name": name, "label": shift_label(name), "start": fmt_time(shift.start_time), "end": fmt_time(shift.end_time), "_start": shift.start_time, "_end": shift.end_time}


def shift_label(name):
	return _p("Office Hours") if name == "Day" else name


def public_shift(shift):
	return {k: v for k, v in shift.items() if not k.startswith("_") and k != "name"} if shift else None


# ---------------------------------------------------------------------------
# Attendance rows
# ---------------------------------------------------------------------------
ATT_FIELDS = [
	"name",
	"attendance_date",
	"status",
	"leave_type",
	"leave_application",
	"custom_leave_application_abbreviation as abbr",
	"working_hours",
	"in_time",
	"out_time",
	"late_entry",
	"early_exit",
	"shift",
	"custom_final_overtime_duration as ot_final",
	"custom_approved_overtime_duration as ot_approved",
]


def attendance_rows(employee, from_date, to_date):
	rows = frappe.get_all(
		"Attendance",
		filters={"employee": employee, "attendance_date": ["between", [from_date, to_date]], "docstatus": ["!=", 2]},
		fields=ATT_FIELDS,
		order_by="attendance_date asc, docstatus desc",
	)
	out = {}
	for r in rows:
		out.setdefault(getdate(r.attendance_date), r)
	return out


def day_working_days(att):
	from customize_erpnext.overrides.shift_attendance.timesheet_leave import timesheet_working_days

	return timesheet_working_days((att.abbr or "").strip(), att.working_hours)


def is_full_leave(att):
	abbr = (att.abbr or "").strip()
	if att.status == "On Leave":
		return True
	return bool(abbr) and "/" not in abbr and flt(att.working_hours) == 0


def late_early_minutes(att, shift):
	late = early = 0
	if not shift:
		return late, early
	date = getdate(att.attendance_date)
	if att.late_entry and att.in_time and shift.get("_start") is not None:
		start = datetime.datetime.combine(date, datetime.time()) + shift["_start"]
		late = max(0, int((get_datetime(att.in_time) - start).total_seconds() // 60))
	if att.early_exit and att.out_time and shift.get("_end") is not None:
		end = datetime.datetime.combine(date, datetime.time()) + shift["_end"]
		early = max(0, int((end - get_datetime(att.out_time)).total_seconds() // 60))
	return late, early


def day_display(date, att, holiday, today):
	"""Colour bucket of one calendar day (API_CONTRACT.md §9 table) + its label."""
	if date > today:
		return ("HOLIDAY", holiday["label"]) if holiday and not holiday["weekly_off"] else ("FUTURE", None)
	if att:
		abbr = (att.abbr or "").strip()
		if abbr == "KL" and flt(att.working_hours) > 0:
			return "LATE_EARLY", _p("Late / Left Early")
		if abbr and "/" in abbr:
			return "HALF_LEAVE", leave_type_label(att.leave_type) or abbr
		if is_full_leave(att):
			return "LEAVE", leave_type_label(att.leave_type) or abbr or _p("On Leave")
		if att.status == "Absent":
			return "ABSENT", _p("Absent")
		if att.late_entry or att.early_exit:
			return "LATE_EARLY", _p("Late / Left Early")
		return "PRESENT", None
	if holiday:
		return ("DAY_OFF", _p("Sunday")) if holiday["weekly_off"] else ("HOLIDAY", holiday["label"])
	if date == today:
		return "TODAY", None
	return "NO_DATA", None


# ---------------------------------------------------------------------------
# Check-ins
# ---------------------------------------------------------------------------
def checkins_for_day(employee, date, attendance=None):
	"""Punches of one day. Prefers checkins linked to the Attendance (night shifts cross
	midnight); falls back to the calendar day."""
	filters = {"employee": employee}
	if attendance:
		filters["attendance"] = attendance
		rows = frappe.get_all(
			"Employee Checkin",
			filters=filters,
			fields=["time", "log_type", "device_id", "custom_reason_for_manual_check_in"],
			order_by="time asc",
		)
		if rows:
			return rows
	start = datetime.datetime.combine(getdate(date), datetime.time())
	return frappe.get_all(
		"Employee Checkin",
		filters={"employee": employee, "time": ["between", [start, start + datetime.timedelta(days=1, seconds=-1)]]},
		fields=["time", "log_type", "device_id", "custom_reason_for_manual_check_in"],
		order_by="time asc",
	)


def punches_payload(rows):
	out = []
	for i, r in enumerate(rows):
		direction = r.log_type if r.log_type in ("IN", "OUT") else ("IN" if i % 2 == 0 else "OUT")
		manual = not r.device_id or bool(r.custom_reason_for_manual_check_in)
		item = {"time": fmt_time(r.time), "direction": direction, "device_name": None if manual else r.device_id}
		if manual:
			item["manual"] = True
		out.append(item)
	return out


# ---------------------------------------------------------------------------
# Payslip override of the provisional numbers (D14)
# ---------------------------------------------------------------------------
# Period summary
# ---------------------------------------------------------------------------
def adjust_until(period):
	"""Last day C&B may still correct the period's attendance: the day before pay day
	(the 4th of the next month), or the period end when no pay day is configured."""
	pay_date = expected_pay_date(period)
	return add_days(pay_date, -1) if pay_date else period_bounds(period)[1]


def period_summary(employee, period, today=None):
	"""Totals of the period, ALWAYS summed from Attendance - the same source as the
	calendar and day screens. Never taken from the payslip (D14 dropped 15/10/2026):
	the official paid numbers are on the payslip itself (lines 1.2, 2.1-2.3).

	`provisional` = C&B may still adjust the period (today <= adjust_until)."""
	today = getdate(today or nowdate())
	from_date, to_date = period_bounds(period)
	emp = frappe.db.get_value("Employee", employee, ["date_of_joining", "relieving_date"], as_dict=True)
	start = max(from_date, getdate(emp.date_of_joining)) if emp.date_of_joining else from_date
	end = to_date
	if emp.relieving_date:
		end = min(end, add_days(getdate(emp.relieving_date), -1))
	as_of = min(today, to_date)

	holidays = holidays_between(employee, from_date, to_date)
	att = attendance_rows(employee, from_date, to_date)
	shifts = {}

	standard = sum(1 for d in daterange(start, end) if not (holidays.get(d) or {}).get("weekly_off"))
	payable = present = paid_leave = holiday_days = absent = 0.0
	late_count = late_minutes = 0
	for d in daterange(start, min(end, as_of)):
		h = holidays.get(d)
		a = att.get(d)
		if a:
			payable += day_working_days(a)
			if flt(a.working_hours) > 0:
				present += 1
			paid_leave += PAID_LEAVE_CODES.get((a.abbr or "").strip(), 0)
			if a.status == "Absent" and not (a.abbr or "").strip():
				absent += 1
			if a.late_entry or a.early_exit:
				if d not in shifts:
					shifts[d] = shift_for(employee, d)
				le, ee = late_early_minutes(a, shifts[d])
				late_count += 1
				late_minutes += le + ee
		if h and not h["weekly_off"] and not (a and flt(a.working_hours) > 0):
			# A paid public holiday that was not worked.
			holiday_days += 1
			payable += 1
		elif not a and not h and d < today:
			absent += 1

	ot_actual = sum(flt(a.ot_final) for a in att.values())
	result = {
		"period": period,
		"from_date": from_date,
		"to_date": to_date,
		"as_of": as_of,
		"provisional": today <= getdate(adjust_until(period)),
		"payable_days": round(payable, 2),
		"standard_days": standard,
		"present_days": present,
		"paid_leave_days": paid_leave,
		"holiday_days": holiday_days,
		"unpaid_absent_days": absent,
		"late_early_count": late_count,
		"late_early_minutes": late_minutes,
		"ot_hours": round(ot_actual, 2),
		"source": "ERP",
	}
	return result


# ---------------------------------------------------------------------------
# Overtime registrations
# ---------------------------------------------------------------------------
def include_draft_ot():
	return bool(frappe.db.get_single_value("Attendance Calculation Setting", "include_draft_ot"))


def overtime_registrations(employee, from_date, to_date):
	"""Overtime Registration Detail rows of the employee. Rejected (docstatus 1 with
	workflow_state Rejected) and Cancelled never appear - they are not overtime.

	Status: APPROVED (submitted, Approved) · PENDING (workflow Pending) · REGISTERED
	(Draft, but the attendance engine counts drafts because include_draft_ot is on) ·
	DRAFT (Draft while that flag is off - shown, but not counted as overtime).
	"""
	rows = frappe.db.sql(
		"""
		SELECT d.date, d.begin_time, d.end_time, d.reason, p.name AS registration,
		       p.docstatus, p.workflow_state
		FROM `tabOvertime Registration Detail` d
		JOIN `tabOvertime Registration` p ON p.name = d.parent
		WHERE d.employee = %s AND d.date BETWEEN %s AND %s AND p.docstatus < 2
		ORDER BY d.date DESC, d.begin_time DESC
		""",
		(employee, from_date, to_date),
		as_dict=True,
	)
	drafts_count = include_draft_ot()
	out = []
	for r in rows:
		state = (r.workflow_state or "").strip()
		if state in ("Rejected", "Cancelled"):
			continue
		if r.docstatus == 1:
			status = "APPROVED"
		elif state == "Pending":
			status = "PENDING"
		elif drafts_count:
			status = "REGISTERED"
		else:
			status = "DRAFT"
		hours = 0.0
		if r.begin_time is not None and r.end_time is not None:
			secs = (r.end_time - r.begin_time).total_seconds()
			if secs < 0:
				secs += 86400
			hours = round(secs / 3600, 2)
		out.append({"date": getdate(r.date), "begin": fmt_time(r.begin_time), "end": fmt_time(r.end_time), "hours": hours, "reason": r.reason, "status": status, "registration": r.registration})
	return out


# ---------------------------------------------------------------------------
# Annual leave balance
# ---------------------------------------------------------------------------
def annual_leave_types():
	return frappe.get_all("Leave Type", filters={"is_earned_leave": 1}, pluck="name")


def leave_balances(employee, date=None):
	from hrms.hr.doctype.leave_application.leave_application import get_leave_details

	with as_administrator():
		details = get_leave_details(employee, date or nowdate())
	out = {}
	for leave_type, d in (details.get("leave_allocation") or {}).items():
		allocated = flt(d.get("total_leaves"))
		taken = flt(d.get("leaves_taken"))
		pending = flt(d.get("leaves_pending_approval"))
		remaining = flt(d.get("remaining_leaves"))
		out[leave_type] = {
			"allocated": allocated,
			"used": taken,
			"pending": pending,
			"remaining": remaining,
			"available": round(remaining - pending, 2),
		}
	return out


def employee_today(employee, now=None):
	"""Payload of the "Hôm nay" card on the home screen."""
	now = now or now_datetime()
	today = now.date()
	shift = shift_for(employee, today)
	punches = checkins_for_day(employee, today)
	holiday = holidays_between(employee, today, today).get(today)
	att = attendance_rows(employee, today, today).get(today)
	on_leave = bool(att and is_full_leave(att)) or bool(
		frappe.db.exists(
			"Leave Application",
			{"employee": employee, "status": "Approved", "docstatus": ["<", 2], "from_date": ["<=", today], "to_date": [">=", today], "half_day": 0},
		)
	)
	check_in = fmt_time(punches[0].time) if punches else None
	check_out = fmt_time(punches[-1].time) if len(punches) > 1 else None

	if on_leave and not punches:
		state = "ON_LEAVE"
	elif holiday and not punches:
		state = "DAY_OFF" if holiday["weekly_off"] else "HOLIDAY"
	elif not punches:
		state = "NOT_CHECKED_IN"
	else:
		end = None
		if shift and shift.get("_end") is not None:
			end = datetime.datetime.combine(today, datetime.time()) + shift["_end"]
		state = "DONE" if len(punches) > 1 and end and get_datetime(punches[-1].time) >= end else "WORKING"
	labels = {
		"NOT_CHECKED_IN": "Not Checked In",
		"WORKING": "Working",
		"DONE": "Checked Out",
		"ON_LEAVE": "On Leave",
		"HOLIDAY": "Holiday",
		"DAY_OFF": "Day Off",
	}
	updated = max((get_datetime(p.time) for p in punches), default=None)
	return {
		"date": today,
		"weekday_label": weekday_label(today),
		"state": state,
		"state_label": _p(labels[state]),
		"check_in": check_in,
		"check_out": check_out,
		"shift": None if state in ("HOLIDAY", "DAY_OFF") else public_shift(shift),
		"updated_at": updated,
	}

