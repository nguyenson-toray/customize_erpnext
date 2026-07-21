# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt
#
# Counts how many employees registered overtime in each (begin_time, end_time)
# slot over a date window. "Employees" is DISTINCT employees — a person who
# registered the same slot on many days counts once. Reuses the join pattern of
# the Overtime Registration Quantity report.

import frappe
from frappe import _
from frappe.utils import get_first_day_of_week, get_last_day_of_week, getdate, today

STATUS_DOCSTATUS = {
	"Draft": "parent.docstatus = 0",
	"Submitted": "parent.docstatus = 1",
	"All (except Cancelled)": "parent.docstatus < 2",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_apply_defaults(filters)

	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	return columns, data, None, chart


def _apply_defaults(filters):
	if not filters.get("from_date"):
		filters.from_date = get_first_day_of_week(today())
	if not filters.get("to_date"):
		filters.to_date = get_last_day_of_week(today())
	if not filters.get("status"):
		filters.status = "Draft"


def get_columns():
	return [
		{"label": _("Time Slot"), "fieldname": "time_slot", "fieldtype": "Data", "width": 130},
		{"label": _("Begin Time"), "fieldname": "begin_time", "fieldtype": "Time", "width": 100},
		{"label": _("End Time"), "fieldname": "end_time", "fieldtype": "Time", "width": 100},
		{"label": _("Employees"), "fieldname": "employees", "fieldtype": "Int", "width": 110},
		{"label": _("Registrations"), "fieldname": "registrations", "fieldtype": "Int", "width": 120},
		{"label": _("Days"), "fieldname": "days", "fieldtype": "Int", "width": 80},
		{"label": _("Total Hours"), "fieldname": "total_hours", "fieldtype": "Float", "width": 110, "precision": 1},
	]


def get_data(filters):
	conditions = [STATUS_DOCSTATUS.get(filters.status, STATUS_DOCSTATUS["Draft"])]
	values = {}

	if filters.get("from_date"):
		conditions.append("detail.date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("detail.date <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.get("group"):
		conditions.append("detail.group = %(group)s")
		values["group"] = filters.group

	section_join = ""
	if filters.get("section"):
		section_join = "JOIN `tabEmployee` emp ON emp.name = detail.employee"
		conditions.append("emp.custom_section = %(section)s")
		values["section"] = filters.section

	where_clause = "WHERE " + " AND ".join(conditions)

	query = f"""
		SELECT
			detail.begin_time AS begin_time,
			detail.end_time AS end_time,
			COUNT(DISTINCT detail.employee) AS employees,
			COUNT(*) AS registrations,
			COUNT(DISTINCT detail.date) AS days,
			SUM(
				CASE WHEN detail.begin_time IS NOT NULL AND detail.end_time IS NOT NULL
					THEN TIME_TO_SEC(TIMEDIFF(detail.end_time, detail.begin_time)) / 3600.0
					ELSE 0 END
			) AS total_hours
		FROM `tabOvertime Registration Detail` detail
		JOIN `tabOvertime Registration` parent ON parent.name = detail.parent
		{section_join}
		{where_clause}
		GROUP BY detail.begin_time, detail.end_time
		ORDER BY registrations DESC, detail.begin_time
	"""

	rows = frappe.db.sql(query, values, as_dict=True)
	for r in rows:
		r["time_slot"] = _slot_label(r["begin_time"], r["end_time"])
	return rows


def _slot_label(begin, end):
	def fmt(t):
		if t is None:
			return "—"
		secs = int(t.total_seconds()) if hasattr(t, "total_seconds") else int(t)
		return "%02d:%02d" % (secs // 3600, (secs % 3600) // 60)

	return f"{fmt(begin)} - {fmt(end)}"


# Bars shown on the report page. This chart lives on the REPORT PAGE, not on a
# dashboard: the query-report view rebuilds the chart from scratch on every
# filter change (empty + new frappe.Chart), while the dashboard widget re-renders
# Bar/Line via frappe-charts .update(), which piles up DOM and freezes the
# browser on this dataset. The report page path never hits .update().
CHART_TOP_N = 12


def get_chart(data):
	if not data:
		return None

	# Registrations = person-day entries = meals to provision. Top slots only for
	# readability; the table below still lists every slot with exact counts.
	rows = sorted(data, key=lambda r: r["registrations"], reverse=True)[:CHART_TOP_N]
	return {
		"data": {
			"labels": [r["time_slot"] for r in rows],
			"datasets": [{"name": _("Registrations"), "values": [r["registrations"] for r in rows]}],
		},
		"type": "bar",
		"colors": ["#4F9DD9"],
		"valuesOverPoints": 1,  # show the count on top of each bar
	}


