# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Shared query for the two TIQN Quiz result reports (detail + summary)."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from customize_erpnext.employee_quiz import service

STATUS_FILTERS = {
	"Completed": ("Submitted", "Expired"),
	"In Progress": ("In Progress",),
	"All": ("In Progress", "Submitted", "Expired"),
}


def get_responses(filters):
	"""Attempts matching the report filters, oldest first per quiz/employee.

	Unticked Check filters are not sent by the browser — read them with .get().
	"""
	conditions = ["r.status in %(statuses)s"]
	values = {"statuses": STATUS_FILTERS.get(filters.get("status") or "Completed", STATUS_FILTERS["Completed"])}

	if filters.get("quiz"):
		conditions.append("r.quiz = %(quiz)s")
		values["quiz"] = filters.quiz
	if filters.get("from_date"):
		conditions.append("date(r.started_at) >= %(from_date)s")
		values["from_date"] = getdate(filters.from_date)
	if filters.get("to_date"):
		conditions.append("date(r.started_at) <= %(to_date)s")
		values["to_date"] = getdate(filters.to_date)
	if filters.get("section"):
		conditions.append("r.custom_section = %(section)s")
		values["section"] = filters.section
	if filters.get("group"):
		conditions.append("r.custom_group = %(group)s")
		values["group"] = filters.group
	if filters.get("employee"):
		conditions.append("r.employee = %(employee)s")
		values["employee"] = filters.employee
	if filters.get("result") == "Passed":
		conditions.append("r.passed = 1 and r.status in ('Submitted', 'Expired')")
	elif filters.get("result") == "Not Passed":
		conditions.append("r.passed = 0 and r.status in ('Submitted', 'Expired')")
	if cint(filters.get("counted_only")):
		# The attempt that counts: the employee's latest submitted one.
		conditions.append(
			"""r.status in ('Submitted', 'Expired') and not exists (
				select 1 from `tabTIQN Quiz Response` r2
				where r2.quiz = r.quiz and r2.employee = r.employee
					and r2.status in ('Submitted', 'Expired') and r2.creation > r.creation)"""
		)

	return frappe.db.sql(
		f"""
		select r.name, r.quiz, r.quiz_title, r.employee, r.employee_name, r.custom_section,
			r.custom_group, e.date_of_joining, r.status, r.attempt_no, r.started_at,
			r.submitted_at, r.duration_sec, r.score, r.max_score, r.percentage, r.passed
		from `tabTIQN Quiz Response` r
		left join `tabEmployee` e on e.name = r.employee
		where {" and ".join(conditions)}
		order by r.quiz, r.employee, r.attempt_no
		""",
		values,
		as_dict=True,
	)


def duration_text(seconds):
	if seconds is None:  # still in progress / not started
		return ""
	seconds = cint(seconds)
	return f"{seconds // 60:02d}:{seconds % 60:02d}"


def result_text(row):
	if row.status not in ("Submitted", "Expired"):
		return ""
	return _("Passed") if row.passed else _("Not Passed")


def base_columns():
	return [
		{"fieldname": "name", "label": _("Response"), "fieldtype": "Link", "options": "TIQN Quiz Response", "width": 135},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 105},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "custom_section", "label": _("Section"), "fieldtype": "Link", "options": "Section", "width": 130},
		{"fieldname": "custom_group", "label": _("Group"), "fieldtype": "Link", "options": "Group", "width": 110},
		{"fieldname": "date_of_joining", "label": _("Date of Joining"), "fieldtype": "Date", "width": 105},
		{"fieldname": "attempt_no", "label": _("Attempt"), "fieldtype": "Int", "width": 70},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 95},
		{"fieldname": "started_at", "label": _("Start Time"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "submitted_at", "label": _("Completion Time"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "duration", "label": _("Duration (mm:ss)"), "fieldtype": "Data", "width": 90},
		{"fieldname": "score", "label": _("Total Points"), "fieldtype": "Float", "precision": 2, "width": 90},
		{"fieldname": "max_score", "label": _("Max Points"), "fieldtype": "Float", "precision": 2, "width": 90},
		{"fieldname": "percentage", "label": _("Percentage"), "fieldtype": "Percent", "width": 95},
		{"fieldname": "result", "label": _("Result"), "fieldtype": "Data", "width": 95},
	]


def finish_row(row):
	row["duration"] = duration_text(row.duration_sec)
	row["result"] = result_text(row)
	if row.status not in ("Submitted", "Expired"):
		row["score"] = row["max_score"] = row["percentage"] = None
	return row


def not_started_rows(filters):
	"""Employees allowed to take the picked quiz who have not started it — only
	with "Include Not Started" ticked and no Result filter (they have no result).
	With All Active Employees that is every active employee not started yet."""
	if not (filters.get("quiz") and cint(filters.get("include_not_started")) and not filters.get("result")):
		return []
	quiz = frappe.get_doc("TIQN Quiz", filters.quiz)
	started = set(frappe.get_all("TIQN Quiz Response", filters={"quiz": quiz.name}, pluck="employee", distinct=True))
	rows = service.eligible_employees(
		quiz, section=filters.get("section"), group=filters.get("group"), employee=filters.get("employee")
	)
	return [
		frappe._dict(r, quiz=quiz.name, quiz_title=quiz.title, status="Not Started")
		for r in rows
		if r.employee not in started
	]


def summary_cards(rows):
	done = [r for r in rows if r.get("status") in ("Submitted", "Expired")]
	passed = sum(1 for r in done if r.passed)
	return [
		{"value": len(done), "label": _("Completed Attempts"), "datatype": "Int", "indicator": "Blue"},
		{"value": passed, "label": _("Passed"), "datatype": "Int", "indicator": "Green"},
		{"value": len(done) - passed, "label": _("Not Passed"), "datatype": "Int", "indicator": "Red"},
		{
			"value": round(passed / len(done) * 100, 1) if done else 0,
			"label": _("Pass Rate"),
			"datatype": "Percent",
			"indicator": "Green",
		},
		{
			"value": round(sum(flt(r.percentage) for r in done) / len(done), 1) if done else 0,
			"label": _("Average Score"),
			"datatype": "Percent",
			"indicator": "Blue",
		},
	]
