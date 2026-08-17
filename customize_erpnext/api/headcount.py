# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Single source of truth for who counts as workforce.

The HR Overview dashboard and the Daily Attendance dashboard both publish a Net
Headcount and a Maternity figure. They used to compute them separately — same
intent, two queries — and the moment maternity leave started setting employees to
`Inactive` the two drifted apart in different ways. Everything either dashboard
needs now comes from here, so they cannot disagree again.

Two rules worth stating outright:

**Scope** is the employee-ID prefix plus the Exclude Employee IDs setting, the
same gate the attendance engine applies. Other companies' staff badge in on site,
so leaving them in inflates headcount and produces absences nobody owns.

**Net headcount is set subtraction, never arithmetic subtraction.** Employees on
maternity leave are `Inactive`, so they are already outside the Active set and
there is nothing left to take away; subtracting a count would remove 32 people
twice. Taking the set difference removes exactly the people who are in both, which
stays correct whether the maternity sync has run or not.
"""

import frappe

# Employee statuses that still mean "on maternity leave, coming back". Inactive is
# what the Employee Maternity sync sets for the duration of the leave; Active
# covers a record the sync has not caught up with yet. Left is excluded — they are
# gone, not on leave.
MATERNITY_EMPLOYEE_STATUSES = ("Active", "Inactive")


def _prefix():
	from customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler import (
		_get_employee_prefix,
	)

	return _get_employee_prefix()


def _excluded_ids():
	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
		get_excluded_employee_ids,
	)

	return get_excluded_employee_ids()


def employee_scope_sql(alias="e"):
	"""SQL fragment + params restricting a query to the counted workforce."""
	clause = f" AND {alias}.name LIKE %(prefix)s"
	params = {"prefix": f"{_prefix()}%"}
	excluded = _excluded_ids()
	if excluded:
		clause += f" AND {alias}.name NOT IN %(excluded)s"
		params["excluded"] = tuple(sorted(excluded))
	return clause, params


def employee_scope_filters(extra=None):
	"""Same scope for the ORM.

	A list rather than a dict because two conditions apply to `name`, which a dict
	cannot express.
	"""
	filters = [
		[k, "=", v] if not isinstance(v, (list, tuple)) else [k, v[0], v[1]]
		for k, v in (extra or {}).items()
	]
	prefix = _prefix()
	if prefix:
		filters.append(["name", "like", f"{prefix}%"])
	excluded = _excluded_ids()
	if excluded:
		filters.append(["name", "not in", sorted(excluded)])
	return filters


def active_employees():
	"""Employees with status Active, within scope."""
	return set(
		frappe.get_all("Employee", filters=employee_scope_filters({"status": "Active"}), pluck="name")
	)


def maternity_leave_employees(employee_statuses=MATERNITY_EMPLOYEE_STATUSES):
	"""People currently on maternity leave, within scope.

	Returns distinct employees, not records: one employee can hold several
	Employee Maternity rows (a second cycle, or a duplicate), so counting rows
	overcounts people.
	"""
	clause, params = employee_scope_sql("e")
	params = dict(params, statuses=tuple(employee_statuses))
	return set(
		frappe.db.sql(
			f"""
			SELECT DISTINCT em.employee
			FROM `tabEmployee Maternity` em
			JOIN `tabEmployee` e ON e.name = em.employee
			WHERE em.status = 'Maternity Leave' AND e.status IN %(statuses)s
			{clause}
			""",
			params,
			pluck=True,
		)
	)


def new_joiners(date):
	"""Employees whose first day is `date`.

	They are counted and displayed, but kept out of every other calculation. Day
	one is almost always recorded as Half Day (243 of 335 such records over three
	months), and Half Day counts as absent — leaving them in would report a whole
	intake as absent. On 2026-08-11 that was 21 of 28 Half Days, inflating the
	absent figure by 29%.
	"""
	return set(
		frappe.get_all(
			"Employee",
			filters=employee_scope_filters({"status": "Active", "date_of_joining": date}),
			pluck="name",
		)
	)


def not_yet_employed(date):
	"""Active employees whose first day is still in the future on `date`.

	Only bites when looking at a past date — someone hired last Friday is Active
	today but was not on the payroll on Monday, so counting them would show up as
	phantom missing attendance in the reconciliation line.
	"""
	return set(
		frappe.get_all(
			"Employee",
			filters=employee_scope_filters({"status": "Active", "date_of_joining": (">", date)}),
			pluck="name",
		)
	)


def net_headcount_set(date=None):
	"""Employees actually available to work on `date` (default today).

	The one definition of net headcount, used by the HR Overview card, the Daily
	Attendance dashboard and the daily email alike: Active, less maternity leave,
	less anyone whose first day is that date or later.

	Set subtraction, deliberately — see the module docstring. Returned as a set so
	callers can slice it further instead of running the query again.
	"""
	from frappe.utils import getdate, nowdate

	date = str(getdate(date or nowdate()))
	return (
		active_employees()
		- maternity_leave_employees()
		- new_joiners(date)
		- not_yet_employed(date)
	)
