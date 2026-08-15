# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt
"""Bulk-create Attendance Requests for days with an incomplete check-in.

HR runs this from the Attendance Request list: pick a date range (default
yesterday), the system finds everyone whose scans are incomplete, proposes a
sensible time for the missing side, HR corrects what it wants, and one DRAFT
Attendance Request per employee is created. The signature forms are then printed
grouped by Employee.custom_group.

Detection reuses `scheduler.get_incomplete_checkins()` — the single source of
truth already used by the daily attendance report. Do NOT re-derive the rules
here; see README.md.
"""

import json
from collections import defaultdict
from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import get_time, getdate

from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
	get_ot_docstatus_condition,
)
from customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler import (
	get_incomplete_checkins,
)

# Paper form "2. De nghi xac nhan cong.pdf" has three tick boxes; map our reasons
# onto them so the printed sheet can pre-tick the right one.
# 1 = employee's own error, 2 = power/machine failure (needs IT sign-off), 3 = other
PAPER_REASON_INDEX = {
	"Forget Check In/Out": 1,
	"Machine Error": 2,
	"First Working Day": 3,
	"Other": 3,
}


# ----------------------------------------------------------------------
# candidate detection
# ----------------------------------------------------------------------
@frappe.whitelist()
def get_incomplete_candidates(from_date: str, to_date: str) -> dict:
	"""One row per (employee, date) whose device scans are incomplete.

	Each row carries a proposed time for the missing side plus two advisory flags
	the dialog uses to pre-untick rows that most likely need no action.

	Gated on WRITE permission for Attendance, not merely read on Attendance
	Request: this scans the whole company and returns colleagues' names, groups,
	titles and working hours. Only HR User / HR Manager / System Manager hold
	Attendance write; the Employee role has read only, so it is shut out.
	"""
	frappe.has_permission("Attendance", ptype="write", throw=True)

	from_date, to_date = str(getdate(from_date)), str(getdate(to_date))
	raw = get_incomplete_checkins(from_date, to_date) or []
	if not raw:
		return {"rows": [], "from_date": from_date, "to_date": to_date}

	employees = [r["employee_code"] for r in raw]
	shift_times = _get_shift_type_times()
	ot_map = _get_ot_map(employees, from_date, to_date)
	all_scans = _get_all_checkin_times(employees, from_date, to_date)
	requested = _get_already_requested({(r["employee_code"], getdate(r["checkin_date"])) for r in raw})

	rows = []
	for r in raw:
		day = getdate(r["checkin_date"])
		employee = r["employee_code"]

		# Shift times come from Shift Type, NOT from the `shift_times` of
		# get_incomplete_checkins(): that helper reads `tabShift Name`, which only
		# holds 4 rows and is missing e.g. "Canteen 6:30 - 15:30" -> begin/end None.
		shift = r.get("shift")
		times = shift_times.get(shift)
		scans = all_scans.get((employee, day), [])

		if not times:
			# Unknown shift: surface the row but with no proposal, HR fills it in
			rows.append(_build_row(r, day, shift, None, None, None, None, requested, scans))
			continue

		start_t, end_t = times["start"], times["end"]
		# Judge on EVERY scan, manual ones included: a day already corrected by
		# hand is no longer missing anything, so proposing a time for it would
		# only invite a duplicate.
		side = _missing_side(scans, start_t, end_t)
		new_in, new_out = (
			_propose_times(employee, day, side, start_t, end_t, ot_map) if side else (None, None)
		)
		rows.append(_build_row(r, day, shift, side, new_in, new_out, times, requested, scans))

	rows.sort(key=lambda x: (x["custom_group"] or "zzz", x["date"], x["employee"]))
	return {"rows": rows, "from_date": from_date, "to_date": to_date}


def _build_row(r, day, shift, side, new_in, new_out, times, requested, scans) -> dict:
	employee = r["employee_code"]
	already_manual = bool((r.get("manual_checkins") or "").strip())
	already_requested = (employee, day) in requested
	# side is None once every scan taken together covers the shift
	resolved = bool(times) and side is None

	return {
		"employee": employee,
		"employee_name": r.get("employee_name"),
		"attendance_device_id": r.get("attendance_device_id"),
		"department": r.get("department"),
		"custom_group": r.get("custom_group"),
		"designation": r.get("designation"),
		"date": str(day),
		"day_of_week": day.strftime("%a"),
		"shift": shift,
		"shift_start": str(times["start"])[:5] if times else None,
		"shift_end": str(times["end"])[:5] if times else None,
		"checkin_count": r.get("checkin_count"),
		"first_check_in": _hhmm(r.get("first_check_in")),
		"last_check_out": _hhmm(r.get("last_check_out")),
		"all_scans": [t.strftime("%H:%M") for t in scans],
		"missing_side": side,  # "in" | "out" | None when nothing is missing
		"resolved": resolved,
		"new_in_time": new_in,
		"new_out_time": new_out,
		# advisory flags — the dialog unticks these rows and highlights them
		"already_manual": already_manual,
		"manual_checkins": r.get("manual_checkins") or "",
		"already_requested": already_requested,
		"selected": not (resolved or already_manual or already_requested),
	}


def _missing_side(scans: list, start_t: time, end_t: time) -> str | None:
	"""Which side is still missing: "in", "out", or None when the day is covered.

	Mirrors the three rules of get_incomplete_checkins(), but fed with EVERY
	check-in of the day instead of machine scans only. That helper deliberately
	ignores manual entries, so a day HR already fixed by hand still shows up in
	its result — running its rules again over the full set is what tells the two
	cases apart.

	The side itself was verified against 5 days HR had corrected by hand on
	2026-08-14 — all five matched.
	"""
	if not scans:
		return "out"

	times = sorted({t.time() for t in scans})
	if len(times) == 1:
		# A single stamp: which side it is depends on where it falls in the shift
		return "out" if times[0] <= _midpoint(start_t, end_t) else "in"

	if times[-1] <= start_t:
		return "out"  # everything happened before the shift began
	if times[0] >= end_t:
		return "in"  # everything happened after the shift ended

	return None  # scans span the shift — nothing left to supplement


def _propose_times(employee, day, side, start_t, end_t, ot_map):
	"""Proposed (new_in_time, new_out_time) as "HH:MM:SS" strings.

	Overtime shifts the proposal only on the matching side: a post-shift OT
	registration moves the check OUT to the end of the OT, a pre-shift one moves
	the check IN to the start of the OT.
	"""
	entries = ot_map.get((employee, day)) or []
	start_td = _to_timedelta(start_t)
	end_td = _to_timedelta(end_t)

	if side == "out":
		post = [e for e in entries if e["begin"] >= end_td]
		proposed = max(e["end"] for e in post) if post else end_td
		return None, _td_to_str(proposed)

	pre = [e for e in entries if e["end"] <= start_td]
	proposed = min(e["begin"] for e in pre) if pre else start_td
	return _td_to_str(proposed), None


# ----------------------------------------------------------------------
# bulk creation
# ----------------------------------------------------------------------
@frappe.whitelist()
def bulk_create_requests(rows, reason: str, explanation: str | None = None) -> dict:
	"""Create ONE draft Attendance Request per employee, covering all their dates.

	Left as a draft on purpose: the paper flow is print -> employee, leader and
	department head sign -> HR-GA submits. Submitting here would rewrite
	attendance before anyone has signed.

	Same HR-only gate as get_incomplete_candidates(): this creates requests on
	behalf of other employees, which the plain Employee role must not do.
	"""
	frappe.has_permission("Attendance Request", ptype="create", throw=True)
	frappe.has_permission("Attendance", ptype="write", throw=True)

	if isinstance(rows, str):
		rows = json.loads(rows)
	if not rows:
		frappe.throw(_("No rows selected."))

	by_employee = defaultdict(list)
	for row in rows:
		if not (row.get("new_in_time") or row.get("new_out_time")):
			continue
		by_employee[row["employee"]].append(row)

	if not by_employee:
		frappe.throw(_("None of the selected rows has a New In or New Out time."))

	created, failed = [], []
	for employee, emp_rows in by_employee.items():
		try:
			created.append(_create_one(employee, emp_rows, reason, explanation))
		except Exception as e:
			failed.append({"employee": employee, "error": str(e)})
			frappe.log_error(
				title=f"Bulk Attendance Request failed for {employee}",
				message=frappe.get_traceback(),
			)

	return {"created": created, "failed": failed}


def _create_one(employee: str, rows: list, reason: str, explanation: str | None) -> str:
	rows = sorted(rows, key=lambda r: getdate(r["date"]))
	dates = [getdate(r["date"]) for r in rows]

	doc = frappe.new_doc("Attendance Request")
	doc.employee = employee
	doc.company = frappe.db.get_value("Employee", employee, "company")
	doc.from_date = dates[0]
	doc.to_date = dates[-1]
	doc.reason = reason
	doc.explanation = explanation
	# Set the shift explicitly: HRMS validate_shifts() throws when the period
	# spans two different Shift Assignments, which a multi-day pick easily does.
	doc.shift = rows[0].get("shift")
	# include_holidays so a Sunday OT correction is not silently skipped
	doc.include_holidays = 1

	# Rows MUST exist before insert: validate() throws "Nothing to Supplement" when
	# the table is empty. sync_checkin_rows() then fills in any gap dates in the
	# period and keeps these times, matching on date.
	for r in rows:
		doc.append(
			"custom_checkin_details",
			{
				"date": getdate(r["date"]),
				"new_in_time": r.get("new_in_time"),
				"new_out_time": r.get("new_out_time"),
				"remark": r.get("remark"),
			},
		)

	doc.insert(ignore_permissions=True)
	return doc.name


# ----------------------------------------------------------------------
# data loading
# ----------------------------------------------------------------------
def _get_shift_type_times() -> dict:
	"""{shift_type: {start, end}} from Shift Type — the doctype that actually
	holds every shift. get_incomplete_checkins() reads `tabShift Name`, which is
	incomplete (4 rows) and returns None times for the rest."""
	result = {}
	for s in frappe.get_all(
		"Shift Type", fields=["name", "start_time", "end_time"], order_by="name asc"
	):
		if s.start_time is None or s.end_time is None:
			continue
		result[s.name] = {"start": _as_time(s.start_time), "end": _as_time(s.end_time)}
	return result


def _get_ot_map(employees: list, from_date: str, to_date: str) -> dict:
	"""{(employee, date): [{begin, end}]} using the SAME docstatus rule as the
	attendance engine (Submitted only, or Draft too when include_draft_ot is ON)."""
	employees = list({e for e in employees if e})
	if not employees:
		return {}

	rows = frappe.db.sql(
		f"""
		SELECT d.employee, d.date, d.begin_time, d.end_time
		FROM `tabOvertime Registration Detail` d
		JOIN `tabOvertime Registration` p ON p.name = d.parent
		WHERE d.employee IN %(employees)s
		  AND d.date BETWEEN %(from_date)s AND %(to_date)s
		  AND {get_ot_docstatus_condition("p")}
		""",
		{"employees": employees, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)

	result = defaultdict(list)
	for r in rows:
		if r.begin_time is None or r.end_time is None:
			continue
		result[(r.employee, getdate(r.date))].append({"begin": r.begin_time, "end": r.end_time})
	return result


def _get_all_checkin_times(employees: list, from_date: str, to_date: str) -> dict:
	"""{(employee, date): [datetime, ...]} — machine scans AND manual entries.

	get_incomplete_checkins() filters on `device_id IS NOT NULL`, so it cannot see
	corrections HR typed in by hand. This is the full picture.
	"""
	employees = list({e for e in employees if e})
	if not employees:
		return {}

	rows = frappe.db.sql(
		"""
		SELECT employee, time
		FROM `tabEmployee Checkin`
		WHERE employee IN %(employees)s
		  AND time BETWEEN %(start)s AND %(end)s
		ORDER BY employee, time
		""",
		{
			"employees": employees,
			"start": f"{from_date} 00:00:00",
			"end": f"{to_date} 23:59:59",
		},
		as_dict=True,
	)

	result = defaultdict(list)
	for r in rows:
		result[(r.employee, r.time.date())].append(r.time)
	return result


def _get_already_requested(keys: set) -> set:
	"""(employee, date) pairs already covered by a draft or submitted request."""
	if not keys:
		return set()

	employees = list({k[0] for k in keys})
	dates = list({k[1] for k in keys})

	rows = frappe.db.sql(
		"""
		SELECT p.employee, d.date
		FROM `tabAttendance Request Checkin Detail` d
		JOIN `tabAttendance Request` p ON p.name = d.parent
		WHERE p.docstatus < 2
		  AND p.employee IN %(employees)s
		  AND d.date IN %(dates)s
		  AND (d.new_in_time IS NOT NULL OR d.new_out_time IS NOT NULL)
		""",
		{"employees": employees, "dates": dates},
		as_dict=True,
	)
	return {(r.employee, getdate(r.date)) for r in rows}


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _hhmm(value) -> str | None:
	return value.strftime("%H:%M") if value else None


def _as_time(value) -> time:
	return get_time(value)


def _to_timedelta(t: time) -> timedelta:
	return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)


def _td_to_str(td: timedelta) -> str:
	total = int(td.total_seconds())
	return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _midpoint(start_t: time, end_t: time) -> time:
	start_td, end_td = _to_timedelta(start_t), _to_timedelta(end_t)
	if end_td <= start_td:  # overnight shift
		end_td += timedelta(days=1)
	mid = start_td + (end_td - start_td) / 2
	mid = timedelta(seconds=int(mid.total_seconds()) % 86400)
	return (datetime.min + mid).time()
