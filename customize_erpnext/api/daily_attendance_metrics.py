# Single source of truth for the "Daily Attendance" dashboard and its daily email.
#
# Both the Dashboard Chart Sources and the email renderer call get_daily_metrics()
# — never the other way round. Fetching numbers back out of the dashboard charts
# does not work: a Group By chart ignores timespan/from_date/to_date entirely
# (frappe/desk/doctype/dashboard_chart/dashboard_chart.py), so those charts report
# all-time totals, not the numbers for one day.
#
# Business rules are documented in 01_docs/daily_attendance_dashboard_plan.md.

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

# Scope, Active set and maternity set are shared with the HR Overview dashboard so
# the two cannot report a different workforce — see api/headcount.py.
from customize_erpnext.api.headcount import (
	active_employees,
	employee_scope_filters as _prefix_filters,
	employee_scope_sql as _employee_scope_sql,
	maternity_leave_employees,
	net_headcount_set,
	new_joiners as _new_joiners,
	not_yet_employed as _not_yet_employed,
)

# Buckets are driven by the Group.group_attendance field, not by code — see
# bucket_order(). Only two buckets are named here, because they carry meaning the
# field alone cannot express: which one gets its own per-line chart, and which one
# absorbs employees the field does not place.
SEWING_BUCKET = "Pro-Sewing"

# Everything that does not name a bucket of its own lands here: Group.group_attendance
# unset (a Select reports that as '' or '0' depending on how the record was created),
# no Group at all, or a stale value no longer offered by the field.
FALLBACK_BUCKET = "Pro-Other"


def bucket_order():
	"""The buckets, in order, straight from Group.group_attendance.

	Never hardcoded: adding, removing, renaming or reordering an option on that
	Select changes the dashboard and the email with no code edit. The blank first
	option (what "unset" looks like) is dropped.
	"""
	options = frappe.get_meta("Group").get_field("group_attendance").options or ""
	return [o.strip() for o in options.split("\n") if o.strip()]


def _fallback_bucket(order):
	"""Where unassigned employees go — the named bucket if the field still offers it.

	Falls back to the last option rather than inventing a column, so renaming
	FALLBACK_BUCKET out of the Select cannot silently drop people from the totals.
	"""
	if FALLBACK_BUCKET in order:
		return FALLBACK_BUCKET
	if order:
		frappe.logger().warning(
			f"Group.group_attendance has no {FALLBACK_BUCKET!r} option; "
			f"unassigned employees are counted under {order[-1]!r}"
		)
		return order[-1]
	return FALLBACK_BUCKET

# Present is the only status that counts as at work. Half Day counts as absent
# (a half day off is still a gap on the line), and absences are not split by
# reason — the director only needs present vs not present.
PRESENT_STATUSES = ("Present", "Work From Home")

TREND_WORKING_DAYS = 14

# Shift resolution: an active Shift Assignment, else this.
DEFAULT_SHIFT = "Day"

_BUCKET_SQL = """
	CASE
		WHEN g.group_attendance IS NULL OR g.group_attendance IN ('', '0')
		THEN %(fallback)s
		ELSE g.group_attendance
	END
"""


def _prefix():
	"""Employee ID prefix from Attendance Calculation Setting.

	Every attendance figure is restricted to employees whose ID carries this
	prefix, matching what the existing 08:15 report does. Test and scratch
	records (Test-9999 and friends) live outside it and would otherwise show up
	as permanently missing attendance.
	"""
	from customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler import (
		_get_employee_prefix,
	)

	return _get_employee_prefix()


def _excluded_ids():
	"""Employees kept out of every figure — staff of other companies on site.

	They badge in and out like everyone else, so they must be removed explicitly
	or they inflate headcount and show up as absences nobody is accountable for.
	"""
	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
		get_excluded_employee_ids,
	)

	return get_excluded_employee_ids()


def _prefix_filters(extra=None):
	"""Employee filters for the ORM: ID prefix in, excluded IDs out.

	Returned as a list rather than a dict because two conditions apply to the
	same `name` field, which a dict cannot express.
	"""
	filters = [[k, "=", v] if not isinstance(v, (list, tuple)) else [k, v[0], v[1]]
	           for k, v in (extra or {}).items()]
	prefix = _prefix()
	if prefix:
		filters.append(["name", "like", f"{prefix}%"])
	excluded = _excluded_ids()
	if excluded:
		filters.append(["name", "not in", sorted(excluded)])
	return filters


def _employee_scope_sql(alias="e"):
	"""SQL fragment + params applying the same scope inside a raw query."""
	clause = f" AND {alias}.name LIKE %(prefix)s"
	params = {"prefix": f"{_prefix()}%"}
	excluded = _excluded_ids()
	if excluded:
		clause += f" AND {alias}.name NOT IN %(excluded)s"
		params["excluded"] = tuple(sorted(excluded))
	return clause, params


def _shifts_on(date):
	"""Which shift each active employee is on for `date`.

	Resolution is simply: an active Shift Assignment wins, otherwise Day. The
	Employee.default_shift field is deliberately not consulted — it says Day for
	all but nine people anyway, and those nine already carry a Shift Assignment,
	so reading it would only add a way for the two sources to disagree.
	"""
	scope, scope_params = _employee_scope_sql("e")
	assigned = dict(
		frappe.db.sql(
			f"""
			SELECT sa.employee, sa.shift_type
			FROM `tabShift Assignment` sa
			JOIN `tabEmployee` e ON e.name = sa.employee
			WHERE sa.docstatus = 1
			  AND sa.status = 'Active'
			  AND sa.start_date <= %(date)s
			  AND (sa.end_date IS NULL OR sa.end_date >= %(date)s)
			  AND e.status = 'Active'
			  {scope}
			ORDER BY sa.start_date
			""",
			{"date": date, **scope_params},
		)
	)

	everyone = frappe.get_all("Employee", filters=_prefix_filters({"status": "Active"}), pluck="name")
	return {emp: assigned.get(emp) or DEFAULT_SHIFT for emp in everyone}


def _late_starting_shifts(date):
	"""Shifts that genuinely have not begun yet, judged against the clock.

	Compared with the current time rather than a fixed cutoff: run at 08:20 the
	14:00 shift is still pending, but run at 14:30 it has started and its people
	count as present or absent like everyone else. A past date is complete by
	definition, so nothing is pending there.
	"""
	now = now_datetime()
	if str(getdate(date)) != str(getdate(now)):
		return set()

	return set(
		frappe.get_all(
			"Shift Type",
			filters={"start_time": (">", now.strftime("%H:%M:%S"))},
			pluck="name",
		)
	)


def _shift2_employees(date, shifts=None):
	"""Employees whose shift for `date` starts after the report is sent.

	The email goes out in the morning; Shift 2 starts at 14:00. Those people have
	not failed to show up, they simply have not started, so they are excluded from
	both Present and Absent.
	"""
	shifts = shifts if shifts is not None else _shifts_on(date)
	late = _late_starting_shifts(date)
	return {emp for emp, shift in shifts.items() if shift in late}


def _excluded_employees(date):
	"""Everyone kept out of the Present/Absent maths, and why."""
	maternity = maternity_leave_employees()
	future = _not_yet_employed(date)
	new_joiners = _new_joiners(date)
	shifts = _shifts_on(date)
	shift2 = _shift2_employees(date, shifts) - new_joiners - maternity - future
	return maternity, new_joiners, shift2, future, shifts


def _attendance_by_bucket(date, excluded, shifts=None):
	"""Present/absent per bucket, per Sewing group and per shift, for one day.

	Grouping joins Employee live rather than reading the custom_section /
	custom_group snapshot stamped on Attendance, which can be stale.
	"""
	shifts = shifts or {}
	order = bucket_order()
	fallback = _fallback_bucket(order)
	scope, scope_params = _employee_scope_sql("e")
	rows = frappe.db.sql(
		f"""
		SELECT
			{_BUCKET_SQL} AS bucket,
			COALESCE(NULLIF(a.employee, ''), '') AS employee,
			COALESCE(g.name, '') AS grp,
			a.status AS status
		FROM `tabAttendance` a
		JOIN `tabEmployee` e ON e.name = a.employee
		LEFT JOIN `tabGroup` g ON g.name = e.custom_group
		WHERE a.docstatus = 1
		  AND a.attendance_date = %(date)s
		  AND e.status = 'Active'
		  {scope}
		""",
		{"date": date, "fallback": fallback, **scope_params},
		as_dict=True,
	)

	by_bucket = {b: {"present": 0, "absent": 0} for b in order}
	by_group = {}
	by_shift = {}
	counted = set()

	for row in rows:
		if row.employee in excluded or row.employee in counted:
			continue
		counted.add(row.employee)

		bucket = row.bucket if row.bucket in by_bucket else fallback
		key = "present" if row.status in PRESENT_STATUSES else "absent"
		by_bucket[bucket][key] += 1

		if bucket == SEWING_BUCKET and row.grp:
			by_group.setdefault(row.grp, {"present": 0, "absent": 0})
			by_group[row.grp][key] += 1

		shift = shifts.get(row.employee)
		if shift:
			by_shift.setdefault(shift, {"present": 0, "absent": 0})
			by_shift[shift][key] += 1

	return by_bucket, by_group, by_shift, counted


def _working_days(end_date, count):
	"""The last `count` working days up to and including end_date.

	Sundays and holidays are skipped so the trend line has no artificial drop to
	zero every week.
	"""
	from customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler import (
		_is_holiday_or_sunday,
	)

	days = []
	cursor = getdate(end_date)
	# Guard the walk so a misconfigured holiday list cannot loop forever.
	for _ in range(count * 5):
		if len(days) >= count:
			break
		if not _is_holiday_or_sunday(str(cursor)):
			days.append(str(cursor))
		cursor = add_days(cursor, -1)
	return list(reversed(days))


@frappe.whitelist()
def get_daily_metrics(date=None):
	"""Every number the Daily Attendance dashboard and email need, for one day.

	Net headcount is the denominator for everything and deliberately excludes both
	maternity leave and same-day new joiners, so neither can skew a rate.
	"""
	date = str(getdate(date or nowdate()))

	maternity, new_joiners, shift2, future, shifts = _excluded_employees(date)
	excluded = maternity | new_joiners | shift2 | future

	# Same set the HR Overview "Headcount" card publishes — one definition, so the
	# two dashboards cannot show different numbers for the same day.
	net_set = net_headcount_set(date)
	net = len(net_set)
	active = len(active_employees()) - len(future)

	# Headcount per shift over the same universe as every other figure here, so
	# the slices add up to net headcount rather than to some other total.
	in_net = set(shifts) & net_set
	shift_headcount = {}
	for emp in in_net:
		shift_headcount[shifts[emp]] = shift_headcount.get(shifts[emp], 0) + 1

	by_bucket, by_group, shift_attendance, counted = _attendance_by_bucket(date, excluded, shifts)
	late = _late_starting_shifts(date)

	present = sum(b["present"] for b in by_bucket.values())
	absent = sum(b["absent"] for b in by_bucket.values())

	# Anyone in the net headcount with no attendance record for the day. A
	# non-zero value means missing data, not a missing person — surfacing it on
	# the dashboard is what stops it going unnoticed.
	unaccounted = net - len(shift2) - len(counted)

	return {
		"date": date,
		"as_of": now_datetime().strftime("%H:%M"),
		"headcount": {
			"active": active,
			"maternity": len(maternity),
			"new_joiners": len(new_joiners),
			"net": net,
		},
		"status": {
			"present": present,
			"absent": absent,
			"shift2_pending": len(shift2),
			"unaccounted": unaccounted,
		},
		"attendance_rate": round(present * 100.0 / net, 1) if net else 0.0,
		"by_bucket": [
			{"bucket": b, "present": v["present"], "absent": v["absent"]}
			for b, v in by_bucket.items()
		],
		"by_group": [
			{"group": g, "present": v["present"], "absent": v["absent"]}
			for g, v in sorted(by_group.items())
		],
		# Shifts that start after the report goes out carry no present/absent at
		# all — they are flagged pending rather than reported as fully absent.
		"by_shift": [
			{
				"shift": s,
				"headcount": c,
				"present": shift_attendance.get(s, {}).get("present", 0),
				"absent": shift_attendance.get(s, {}).get("absent", 0),
				"pending": s in late,
			}
			for s, c in sorted(shift_headcount.items(), key=lambda kv: -kv[1])
		],
	}


# ---------------------------------------------------------------------------
# Chart formatters
#
# The four Dashboard Chart Sources are thin adapters over these, so a number on
# a chart is the same number the email prints. Present and Absent are drawn blue
# and orange rather than the obvious green and red: green/red sit at ΔE 3.5 under
# deuteranopia, which makes the two series indistinguishable for roughly 1 in 12
# men. This pair validates on both the light and dark desk themes.
# ---------------------------------------------------------------------------

PRESENT_COLOR = "#2C7BE5"
ABSENT_COLOR = "#D9722A"
# Overtime is a different measure entirely, so it gets its own hue rather than
# borrowing the present/absent pair. Validated against both on light and dark.
OVERTIME_COLOR = "#1BAF7A"
# Darker step of the same hue, for emphasising the day being reported on.
OVERTIME_TODAY_COLOR = "#0E7350"


@frappe.whitelist()
def get_overtime_registrations(date=None):
	"""Registered overtime headcount across this week and the next.

	A fixed fortnight rather than a rolling window: overtime is registered ahead
	of time, so the chart has to reach into the future to show the load being
	planned, and pinning it to week boundaries keeps the columns in the same
	place from one day to the next. Days with no registrations are kept as zero
	so the fortnight never silently shrinks.

	Which registrations count follows the Include Draft OT Registrations setting,
	the same switch the attendance engine obeys — otherwise this chart could show
	overtime the payroll side is ignoring, or hide overtime it is paying for.
	Cancelled registrations are always dropped.
	"""
	from frappe.utils import get_first_day_of_week

	from customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks import (
		get_include_draft_ot,
	)

	start = getdate(get_first_day_of_week(str(getdate(date or nowdate()))))
	end = add_days(start, 13)
	statuses = (0, 1) if get_include_draft_ot() else (1,)

	found = dict(
		frappe.db.sql(
			"""
			SELECT `date`, COUNT(*) AS qty
			FROM `tabOvertime Registration Detail`
			WHERE docstatus IN %(statuses)s
			  AND `date` BETWEEN %(start)s AND %(end)s
			GROUP BY `date`
			""",
			{"statuses": statuses, "start": start, "end": end},
		)
	)

	return [
		{"date": str(d), "qty": found.get(d, 0)}
		for d in (add_days(start, i) for i in range(14))
	]


def _filter_date(filters):
	filters = frappe.parse_json(filters) if filters else {}
	return (filters or {}).get("date") or nowdate()


def _stacked(labels, present, absent):
	return {
		"labels": labels,
		"datasets": [
			{"name": frappe._("Present"), "values": present},
			{"name": frappe._("Absent"), "values": absent},
		],
	}


def chart_by_group(filters=None):
	"""Present vs absent per attendance bucket, stacked."""
	rows = get_daily_metrics(_filter_date(filters))["by_bucket"]
	return _stacked(
		[r["bucket"] for r in rows],
		[r["present"] for r in rows],
		[r["absent"] for r in rows],
	)


def chart_sewing_lines(filters=None):
	"""Present vs absent per sewing line, stacked."""
	rows = get_daily_metrics(_filter_date(filters))["by_group"]
	return _stacked(
		[r["group"] for r in rows],
		[r["present"] for r in rows],
		[r["absent"] for r in rows],
	)


def chart_overview(filters=None):
	"""Company-wide present vs absent, for the donut."""
	status = get_daily_metrics(_filter_date(filters))["status"]
	return {
		"labels": [frappe._("Present"), frappe._("Absent")],
		"datasets": [{"values": [status["present"], status["absent"]]}],
	}


def chart_by_shift(filters=None):
	"""Headcount per shift.

	One slice carries about 97% of the workforce, so the three small shifts render
	as slivers — see the note in the plan doc if this needs to become a bar chart.
	"""
	rows = get_daily_metrics(_filter_date(filters))["by_shift"]
	return {
		"labels": [r["shift"] for r in rows],
		"datasets": [{"values": [r["headcount"] for r in rows]}],
	}


def chart_trend(filters=None):
	"""Present and Absent head counts over the last working days, as two lines.

	Both series share one y-axis on purpose. A second axis for Absent would make
	the two lines look comparable when they are an order of magnitude apart, which
	is how a 60-person absence gets read as a crisis.
	"""
	filters = frappe.parse_json(filters) if filters else {}
	rows = get_trend(
		days=(filters or {}).get("days") or TREND_WORKING_DAYS,
		end_date=(filters or {}).get("date"),
	)
	return {
		"labels": [r["date"] for r in rows],
		"datasets": [
			{"name": frappe._("Present"), "values": [r["present"] for r in rows]},
			{"name": frappe._("Absent"), "values": [r["absent"] for r in rows]},
		],
	}


# One method backs this dashboard's Number Cards; each card picks its figure
# through the "metric" key in its own filters_json, so adding a card needs no new
# Python.
#
# Net headcount and Maternity are deliberately absent. Both dashboards show the
# same two figures, so they share the same two Number Cards, served by
# api/hr_overview_cards.py — a second card here would be a second thing to keep in
# step. get_daily_metrics() still reports them under "headcount" for the daily
# email, computed from the same api/headcount.py functions those cards use.
CARD_METRICS = {
	"present": (("status", "present"), "Int"),
	"absent": (("status", "absent"), "Int"),
	"attendance_rate": (("attendance_rate",), "Percent"),
	# Present + Absent alone do not add up to net headcount; this card is what
	# makes the missing remainder visible instead of looking like a bug.
	"shift2_pending": (("status", "shift2_pending"), "Int"),
	"new_joiners": (("headcount", "new_joiners"), "Int"),
}


@frappe.whitelist()
def card(filters=None):
	"""Value for one Daily Attendance number card."""
	filters = frappe.parse_json(filters) if filters else {}
	metric = (filters or {}).get("metric") or "present"
	path, fieldtype = CARD_METRICS.get(metric, CARD_METRICS["present"])

	value = get_daily_metrics((filters or {}).get("date"))
	for key in path:
		value = value[key]

	return {"value": value, "fieldtype": fieldtype}


@frappe.whitelist()
def get_trend(days=TREND_WORKING_DAYS, end_date=None):
	"""Attendance rate over the last N working days, oldest first.

	Reuses get_daily_metrics so a point on the trend line is the same number the
	dashboard shows for that day — computing the rate a second way here is how the
	two quietly drift apart.
	"""
	days = int(days or TREND_WORKING_DAYS)
	out = []
	for d in _working_days(end_date or nowdate(), days):
		m = get_daily_metrics(d)
		out.append(
			{
				"date": d,
				"rate": m["attendance_rate"],
				"present": m["status"]["present"],
				"absent": m["status"]["absent"],
			}
		)
	return out
