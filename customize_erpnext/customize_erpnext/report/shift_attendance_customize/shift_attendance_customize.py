# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)
	report_summary = get_report_summary(data, filters)
	return columns, data, None, None, report_summary


def get_columns(filters):
	"""Define columns based on Excel file structure"""
	is_summary = filters and filters.get("summary")

	if is_summary:
		# Summary mode: show aggregated data
		columns = [
			{
				"label": _("Shift"),
				"fieldname": "shift",
				"fieldtype": "Link",
				"options": "Shift Type",
				"width": 100,
			},
			{
				"label": _("Employee"),
				"fieldname": "employee",
				"fieldtype": "Link",
				"options": "Employee",
				"width": 110,
			},
			{
				"fieldname": "employee_name",
				"fieldtype": "Data",
				"label": _("Employee Name"),
				"width": 170,
				# "hidden": 1,
			},
			{
				"label": _("Group"),
				"fieldname": "custom_group",
				"fieldtype": "Link",
				"options": "Group",
				"width": 120,
			},
			{
				"label": _("Date of Joining"),
				"fieldname": "date_of_joining",
				"fieldtype": "Date",
				"width": 100,
			},
			{
				"label": _("Relieving Date"),
				"fieldname": "relieving_date",
				"fieldtype": "Date",
				"width": 100,
			},
			{
				"label": _("Total Working Hours"),
				"fieldname": "working_hours",
				"fieldtype": "Float",
				"width": 120,
			},
			{
				"label": _("Total Working Day"),
				"fieldname": "working_day",
				"fieldtype": "Float",
				"width": 120,
			},
			{
				"label": _("Total Actual OT"),
				"fieldname": "actual_overtime_duration",
				"fieldtype": "Float",
				"width": 120,
			},
			{
				"label": _("Total Approved OT"),
				"fieldname": "custom_approved_overtime_duration",
				"fieldtype": "Float",
				"width": 120,
			},
			{
				"label": _("Total Final OT"),
				"fieldname": "final_overtime_duration",
				"fieldtype": "Float",
				"width": 120,
			},
			{
				"label": _("Department"),
				"fieldname": "department",
				"fieldtype": "Link",
				"options": "Department",
				"width": 150,
			},
		]
	else:
		# Detail mode: show individual attendance records
		columns = [
			{
				"label": _("Date"),
				"fieldname": "attendance_date",
				"fieldtype": "Date",
				"width": 100,
			},
			{
				"label": _("Shift"),
				"fieldname": "shift",
				"fieldtype": "Link",
				"options": "Shift Type",
				"width": 70,
			},
			{
				"label": _("Employee"),
				"fieldname": "employee",
				"fieldtype": "Link",
				"options": "Employee",
				"width": 230,
			},
			{
				"fieldname": "employee_name",
				"fieldtype": "Data",
				"label": _("Employee Name"),
				"width": 160,
				"hidden": 1,
			},
			{
				"label": _("Group"),
				"fieldname": "custom_group",
				"fieldtype": "Link",
				"options": "Group",
				"width": 120,
			},
			{
				"label": _("Status"),
				"fieldname": "status",
				"fieldtype": "Data",
				"width": 90,
			},
			{
				"label": _("In Time"),
				"fieldname": "in_time",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("Out Time"),
				"fieldname": "out_time",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("Working Hours"),
				"fieldname": "working_hours",
				"fieldtype": "Float",
				"width": 100,
			},
			{
				"label": _("Working Day"),
				"fieldname": "working_day",
				"fieldtype": "Float",
				"width": 100,
			},
			{
				"label": _("Actual OT"),
				"fieldname": "actual_overtime_duration",
				"fieldtype": "Float",
				"width": 100,
			},
			{
				"label": _("Approved OT"),
				"fieldname": "custom_approved_overtime_duration",
				"fieldtype": "Float",
				"width": 100,
			},
			{
				"label": _("Final OT"),
				"fieldname": "final_overtime_duration",
				"fieldtype": "Float",
				"width": 100,
			},
			{
				"label": _("Maternity Benefit"),
				"fieldname": "custom_maternity_benefit",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("Late Entry"),
				"fieldname": "late_entry",
				"fieldtype": "Check",
				"width": 60,
			},
			{
				"label": _("Early Exit"),
				"fieldname": "early_exit",
				"fieldtype": "Check",
				"width": 60,
			},
			{
				"label": _("Leave Application"),
				"fieldname": "leave_application",
				"fieldtype": "Link",
				"options": "Leave Application",
				"width": 150,
			},
			{
				"label": _("Department"),
				"fieldname": "department",
				"fieldtype": "Link",
				"options": "Department",
				"width": 150,
			},
			{
				"label": _("Attendance ID"),
				"fieldname": "name",
				"fieldtype": "Link",
				"options": "Attendance",
				"width": 120,
			},
		]

		# Add Join/Resign Date columns if filter is enabled
		if filters and filters.get("detail_join_resign_date"):
			join_resign_columns = [
				{
					"label": _("Date of Joining"),
					"fieldname": "date_of_joining",
					"fieldtype": "Date",
					"width": 100,
				},
				{
					"label": _("Relieving Date"),
					"fieldname": "relieving_date",
					"fieldtype": "Date",
					"width": 100,
				},
			]
			# Insert after Early Exit column (index 15)
			columns[15:15] = join_resign_columns

	return columns


def get_data(filters):
	query = get_query(filters)
	data = query.run(as_dict=True)
	data = update_data(data)
	return data


def get_report_summary(data, filters):
	"""Generate report summary with required statistics"""
	# Hide report summary in Summary mode
	if filters and filters.get("summary"):
		return None

	if not data:
		return None

	present_records = maternity_leave_records = absent_records = late_entries = early_exits = 0

	for entry in data:
		# Check status (may contain HTML tags after formatting)
		status_text = entry.get("status")
		if isinstance(status_text, str):
			if "Present" in status_text:
				present_records += 1
			elif "Maternity Leave" in status_text:
				maternity_leave_records += 1
			elif "Absent" in status_text:
				absent_records += 1

		if entry.get("late_entry"):
			late_entries += 1
		if entry.get("early_exit"):
			early_exits += 1

	return [
		{
			"value": present_records,
			"indicator": "Green",
			"label": _("Present Records"),
			"datatype": "Int",
		},
		{
			"value": maternity_leave_records,
			"indicator": "Purple",
			"label": _("Maternity Leave Records"),
			"datatype": "Int",
		},
		{
			"value": absent_records,
			"indicator": "Red",
			"label": _("Absent Records"),
			"datatype": "Int",
		},
		{
			"value": late_entries,
			"indicator": "Red",
			"label": _("Late Entries"),
			"datatype": "Int",
		},
		{
			"value": early_exits,
			"indicator": "Red",
			"label": _("Early Exits"),
			"datatype": "Int",
		},
	]


def get_query(filters):
	"""Build query to fetch attendance records - SIMPLE query from Attendance only"""
	from pypika.functions import Sum

	attendance = frappe.qb.DocType("Attendance")
	employee = frappe.qb.DocType("Employee")
	is_summary = filters and filters.get("summary")

	if is_summary:
		# Summary mode: aggregate data by employee
		query = (
			frappe.qb.from_(attendance)
			.left_join(employee)
			.on(attendance.employee == employee.name)
			.select(
				attendance.shift,
				attendance.employee,
				attendance.employee_name,
				employee.custom_group,
				employee.date_of_joining,
				employee.relieving_date,
				attendance.department,
				Sum(attendance.working_hours).as_("working_hours"),
			)
			.where(attendance.docstatus == 1)
			.groupby(
				attendance.shift,
				attendance.employee,
				attendance.employee_name,
				employee.custom_group,
				employee.date_of_joining,
				employee.relieving_date,
				attendance.department
			)
			.orderby(attendance.shift)
			.orderby(employee.custom_group)
			.orderby(attendance.employee)
		)

		# Add custom overtime fields aggregation if they exist
		try:
			query = query.select(
				Sum(attendance.actual_overtime_duration).as_("actual_overtime_duration"),
				Sum(attendance.custom_approved_overtime_duration).as_("custom_approved_overtime_duration"),
				Sum(attendance.custom_final_overtime_duration).as_("final_overtime_duration"),
			)
		except AttributeError:
			pass

	else:
		# Detail mode: show individual attendance records
		query = (
			frappe.qb.from_(attendance)
			.left_join(employee)
			.on(attendance.employee == employee.name)
			.select(
				attendance.name,
				attendance.employee,
				attendance.employee_name,
				attendance.shift,
				attendance.attendance_date,
				attendance.status,
				attendance.in_time,
				attendance.out_time,
				attendance.working_hours,
				attendance.late_entry,
				attendance.early_exit,
				attendance.department,
				attendance.company,
				attendance.leave_application,
				employee.custom_group,
				employee.date_of_joining,
				employee.relieving_date,
			)
			.where(attendance.docstatus == 1)
			.orderby(attendance.attendance_date)
			.orderby(attendance.shift)
			.orderby(employee.custom_group)
			.orderby(attendance.employee)
		)

		# Add custom fields if they exist
		try:
			query = query.select(
				attendance.actual_overtime_duration.as_("actual_overtime_duration"),
				attendance.custom_approved_overtime_duration,
				attendance.custom_final_overtime_duration.as_("final_overtime_duration"),
				attendance.custom_maternity_benefit,
			)
		except AttributeError:
			pass

	# Apply filters
	for filter_key in filters:
		if filter_key == "from_date":
			query = query.where(attendance.attendance_date >= filters.from_date)
		elif filter_key == "to_date":
			query = query.where(attendance.attendance_date <= filters.to_date)
		elif filter_key == "late_entry" and not is_summary:
			query = query.where(attendance.late_entry == 1)
		elif filter_key == "early_exit" and not is_summary:
			query = query.where(attendance.early_exit == 1)
		elif filter_key == "status" and not is_summary:
			query = query.where(attendance.status == filters.status)
		elif filter_key == "group":
			query = query.where(employee.custom_group == filters.group)
		elif filter_key == "employee":
			query = query.where(attendance.employee == filters.employee)
		elif filter_key == "shift":
			query = query.where(attendance.shift == filters.shift)
		elif filter_key == "department":
			query = query.where(attendance.department == filters.department)
		# Skip summary and detail_join_resign_date filters in query
		elif filter_key in ["summary", "detail_join_resign_date"]:
			continue

	return query


def update_data(data):
	"""Update data with calculated fields and formatting"""
	for d in data:
		# Calculate Working Day = Total Working Hours / 8
		if d.get("working_hours"):
			d.working_day = flt(d.working_hours / 8.0, 2)
		else:
			d.working_day = 0

		# Format working hours
		d.working_hours = format_float_precision(d.working_hours)

		# Format actual and final overtime duration
		if d.get("actual_overtime_duration"):
			d.actual_overtime_duration = format_float_precision(d.actual_overtime_duration)
		if d.get("custom_approved_overtime_duration"):
			d.custom_approved_overtime_duration = format_float_precision(d.custom_approved_overtime_duration)
		if d.get("final_overtime_duration"):
			d.final_overtime_duration = format_float_precision(d.final_overtime_duration)

		# Format in/out time - simple string format (only in detail mode)
		if d.get("in_time") and hasattr(d.in_time, 'strftime'):
			d.in_time = d.in_time.strftime('%H:%M:%S')
		if d.get("out_time") and hasattr(d.out_time, 'strftime'):
			d.out_time = d.out_time.strftime('%H:%M:%S')

		# Add color styling for status (only in detail mode)
		if d.get("status"):
			if d.status == "Present":
				d.status = '<span style="color: green; font-weight: bold;">Present</span>'
			elif d.status == "Absent":
				d.status = '<span style="color: red; font-weight: bold;">Absent</span>'
			elif d.status == "Maternity Leave":
				d.status = '<span style="color: purple; font-weight: bold;">Maternity Leave</span>'

	return data


def format_float_precision(value):
	"""Format float values with proper precision"""
	if not value:
		return 0
	precision = cint(frappe.db.get_default("float_precision")) or 2
	return flt(value, precision)
