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
				"label": _("Leave Application"),
				"fieldname": "leave_application",
				"fieldtype": "Link",
				"options": "Leave Application",
				"width": 150,
			},
			{
				"label": _("Leave Type"),
				"fieldname": "leave_type",
				"fieldtype": "Link",
				"options": "Leave Type",
				"width": 120,
			},
			{
				"label": _("Status for Other Half"),
				"fieldname": "half_day_status",
				"fieldtype": "Data",
				"width": 150,
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

		# Hide Leave Application columns if filter is not enabled
		if not (filters and filters.get("show_leave_application")):
			columns = [col for col in columns if col.get("fieldname") not in
					   ["leave_application", "leave_type", "half_day_status"]]

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

	present_records = on_leave_records = absent_records = late_entries = early_exits = 0

	for entry in data:
		# Check status (may contain HTML tags after formatting)
		status_text = entry.get("status")
		if isinstance(status_text, str):
			if "Present" in status_text:
				present_records += 1
			elif "On Leave" in status_text or "Half Day" in status_text:
				on_leave_records += 1
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
			"value": on_leave_records,
			"indicator": "Blue",
			"label": _("On Leave Records"),
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
				attendance.leave_type,
				attendance.half_day_status,
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
			query = query.where(attendance.attendance_date >= filters['from_date'])
		elif filter_key == "to_date":
			query = query.where(attendance.attendance_date <= filters['to_date'])
		elif filter_key == "late_entry" and not is_summary:
			query = query.where(attendance.late_entry == 1)
		elif filter_key == "early_exit" and not is_summary:
			query = query.where(attendance.early_exit == 1)
		elif filter_key == "status" and not is_summary:
			query = query.where(attendance.status == filters['status'])
		elif filter_key == "group":
			query = query.where(employee.custom_group == filters['group'])
		elif filter_key == "employee":
			query = query.where(attendance.employee == filters['employee'])
		elif filter_key == "shift":
			query = query.where(attendance.shift == filters['shift'])
		elif filter_key == "department":
			query = query.where(attendance.department == filters['department'])
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
			elif d.status == "On Leave":
				d.status = '<span style="color: blue; font-weight: bold;">On Leave</span>'
			elif d.status == "Half Day":
				d.status = '<span style="color: orange; font-weight: bold;">Half Day</span>'
			elif d.status == "Work From Home":
				d.status = '<span style="color: purple; font-weight: bold;">Work From Home</span>'

	return data


def format_float_precision(value):
	"""Format float values with proper precision"""
	if not value:
		return 0
	precision = cint(frappe.db.get_default("float_precision")) or 2
	return flt(value, precision)


# ========== Excel Export Functions ==========

@frappe.whitelist()
def export_attendance_excel(filters=None):
	"""Export attendance data to Excel format similar to the C&B template"""
	import json
	import time
	if isinstance(filters, str):
		filters = json.loads(filters)

	# Estimate operation size
	date_range = get_export_date_range(filters)
	num_days = len(date_range['dates'])

	# Get employee count estimate
	filters_temp = {
		"from_date": date_range['from_date'],
		"to_date": date_range['to_date']
	}

	emp_filter = ""
	if filters.get('department'):
		dept_list = filters['department'] if isinstance(filters['department'], list) else [filters['department']]
		dept_str = "', '".join(dept_list)
		emp_filter += f" AND emp.department IN ('{dept_str}')"

	employee_count = frappe.db.sql(f"""
		SELECT COUNT(DISTINCT emp.name) as count
		FROM `tabEmployee` emp
		WHERE (
			(emp.status = 'Active'
			 AND (emp.date_of_joining IS NULL OR emp.date_of_joining <= %(to_date)s))
			OR
			(emp.status = 'Left'
			 AND (emp.date_of_joining IS NULL OR emp.date_of_joining <= %(to_date)s)
			 AND (emp.relieving_date IS NULL OR emp.relieving_date > %(from_date)s))
		)
		{emp_filter}
	""", filters_temp, as_dict=1)[0].count

	total_operations = employee_count * num_days

	# If operation is large (>30000 operations), run in background
	# With ~850 employees, this allows up to ~35 days sync export
	if total_operations > 30000:
		job_id = f"export_excel_{int(time.time())}"

		frappe.enqueue(
			'customize_erpnext.customize_erpnext.report.shift_attendance_customize.shift_attendance_customize.export_attendance_excel_job',
			queue='default',
			timeout=1800,  # 30 minutes
			job_id=job_id,
			filters=filters
		)

		return {
			'background_job': True,
			'job_id': job_id,
			'total_operations': total_operations,
			'message': f'Large export ({employee_count} employees × {num_days} days = {total_operations} records) queued for background processing. You will receive a notification when ready.'
		}

	# Small operation - run synchronously
	return export_attendance_excel_sync(filters)


def export_attendance_excel_sync(filters):
	"""Synchronous Excel export for small datasets"""
	import json
	import openpyxl
	import tempfile
	import os

	if isinstance(filters, str):
		filters = json.loads(filters)

	# Always use fresh data from the report to ensure consistency
	# Force summary = 0 for Excel export to get daily detail data
	export_filters = filters.copy() if filters else {}
	export_filters['summary'] = 0

	# Get data using existing get_data function
	data = get_data(export_filters)
	employee_data = convert_attendance_data_to_excel_format(data, export_filters)

	# Create Excel file
	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "Timesheet"

	# Get date range based on current filters
	date_range = get_export_date_range(filters)

	# Setup Excel headers and data
	setup_excel_headers(ws, date_range, filters)
	all_employees, current_row, first_employee_row = populate_employee_data(ws, employee_data, date_range)

	# Add total row (only if we have employees)
	if first_employee_row is not None:
		add_total_row(ws, all_employees, current_row, date_range, first_employee_row)
	total_row_end = current_row + 1

	# Add footer with signatures and notes
	add_excel_footer(ws, total_row_end, date_range)

	# Apply formatting (account for department headers + total row)
	total_rows = len(all_employees) + len(employee_data) + 1  # employees + dept headers + total row
	apply_excel_formatting(ws, total_rows, len(date_range['dates']), date_range)

	# Create filename
	from frappe.utils import formatdate
	filename = f"Attendance_{date_range['from_date'].strftime('%Y%m%d')}_to_{date_range['to_date'].strftime('%Y%m%d')}.xlsx"
	# Sanitize filename for file system
	filename = filename.replace('/', '_').replace('\\', '_').replace(' ', '_')

	# Save to temporary file
	temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
	wb.save(temp_file.name)
	temp_file.close()

	# Save file to Frappe's private files
	try:
		with open(temp_file.name, 'rb') as f:
			file_content = f.read()

		# Create a File document in Frappe
		file_doc = frappe.get_doc({
			'doctype': 'File',
			'file_name': filename,
			'is_private': 0,  # Public file so it can be downloaded
			'content': file_content
		})
		file_doc.save(ignore_permissions=True)
		frappe.db.commit()

		# Clean up temp file
		os.unlink(temp_file.name)

		# Schedule file deletion after 2 minutes (enough time for download)
		frappe.enqueue(
			'customize_erpnext.customize_erpnext.report.shift_attendance_customize.shift_attendance_customize.delete_export_file',
			queue='short',
			timeout=300,
			file_name=file_doc.name,
			enqueue_after_commit=True
		)

		return {
			'file_url': file_doc.file_url,
			'filename': filename
		}
	except Exception as e:
		# Clean up temp file on error
		if os.path.exists(temp_file.name):
			os.unlink(temp_file.name)
		frappe.log_error(f"Error saving Excel file: {str(e)}", "Attendance Export Error")
		frappe.throw(_("Failed to save Excel file. Please try again or contact support."))


def export_attendance_excel_job(filters):
	"""Background job for Excel export"""
	try:
		frappe.publish_progress(0, title="Starting Excel export...",
							  description="Generating attendance Excel file in background")

		result = export_attendance_excel_sync(filters)

		frappe.publish_realtime(
			event='excel_export_complete',
			message={
				"success": True,
				"file_url": result.get('file_url'),
				"filename": result.get('filename'),
				"message": f"Excel export completed! File: {result.get('filename')}"
			},
			user=frappe.session.user
		)

		return result

	except Exception as e:
		frappe.log_error(f"Background Excel export failed: {str(e)}", "Excel Export Error")
		frappe.publish_realtime(
			event='excel_export_complete',
			message={
				"success": False,
				"error": str(e),
				"message": "Excel export failed. Please try again or contact support."
			},
			user=frappe.session.user
		)
		raise e


def get_export_date_range(filters):
	"""Get date range based on current report filters"""
	from frappe.utils import getdate, add_days, formatdate

	# Use from_date and to_date from filters
	from_date = getdate(filters.get("from_date")) if filters.get("from_date") else getdate()
	to_date = getdate(filters.get("to_date")) if filters.get("to_date") else getdate()

	# Generate all dates in range
	dates = []
	current_date = from_date
	while current_date <= to_date:
		dates.append(current_date)
		current_date = add_days(current_date, 1)

	# Create display info
	period_name = f"{formatdate(from_date)} - {formatdate(to_date)}"

	return {
		'from_date': from_date,
		'to_date': to_date,
		'dates': dates,
		'period_name': period_name
	}


def clean_department_name(dept_name):
	"""Remove '- TIQN' suffix from department names"""
	if dept_name and dept_name.endswith(' - TIQN'):
		return dept_name.replace(' - TIQN', '')
	return dept_name or ''


def decimal_round(value, precision=2):
	"""Round decimal values properly"""
	from decimal import Decimal, ROUND_HALF_UP
	if value is None or value == '':
		return 0
	return float(Decimal(str(value)).quantize(Decimal(10) ** -precision, rounding=ROUND_HALF_UP))


def convert_attendance_data_to_excel_format(report_data, filters):
	"""Convert report data to Excel format for attendance export"""
	if not report_data:
		return []

	# Get date range for columns
	date_range = get_export_date_range(filters)

	# Group data by employee
	employee_data = {}
	for row in report_data:
		employee_id = row.get('employee')
		if not employee_id:
			continue

		if employee_id not in employee_data:
			employee_data[employee_id] = {
				'employee_id': employee_id,
				'employee_name': row.get('employee_name', '') or '',
				'date_of_joining': row.get('date_of_joining'),
				'relieving_date': row.get('relieving_date'),
				'custom_group': row.get('custom_group', '') or '',
				'department': clean_department_name(row.get('department', '') or ''),
				'designation': '',  # Not available in Attendance, will get from Employee
				'daily_data': {}
			}

		# Add daily attendance data
		attendance_date = row.get('attendance_date')
		if attendance_date:
			# Handle different date formats
			if hasattr(attendance_date, 'strftime'):
				date_key = attendance_date.strftime('%Y-%m-%d')
			else:
				date_key = str(attendance_date)

			# Convert working hours to working days
			working_hours = row.get('working_hours', 0) or 0
			status = row.get('status', '')

			# Always show all data including zeros
			if working_hours > 0:
				working_days = decimal_round(working_hours / 8, 2)
				employee_data[employee_id]['daily_data'][date_key] = working_days
			elif status and 'Present' in str(status):
				# Present but no working hours - show 0
				employee_data[employee_id]['daily_data'][date_key] = 0
			else:
				# No working day - leave blank for other statuses or missing data
				employee_data[employee_id]['daily_data'][date_key] = ''

	# Get all active employees for the period
	period_start = filters.get("from_date", "1900-01-01")
	period_end = filters.get("to_date", "2099-12-31")

	# Get employee conditions for filtering
	emp_filter = ""
	if filters.get('department'):
		dept_list = filters['department'] if isinstance(filters['department'], list) else [filters['department']]
		dept_str = "', '".join(dept_list)
		emp_filter += f" AND emp.department IN ('{dept_str}')"

	if filters.get('employee'):
		emp_filter += f" AND emp.name = '{filters['employee']}'"

	if filters.get('group'):
		emp_filter += f" AND emp.custom_group = '{filters['group']}'"

	# Get all active employees that should be included
	all_active_employees = frappe.db.sql(f"""
		SELECT DISTINCT emp.name as employee,
			emp.employee_name,
			emp.department,
			emp.custom_group,
			emp.date_of_joining,
			emp.relieving_date,
			emp.designation
		FROM `tabEmployee` emp
		WHERE (
			-- Show employees who were active during any part of the period
			((emp.date_of_joining IS NULL OR emp.date_of_joining <= '{period_end}')
			 AND (emp.relieving_date IS NULL OR emp.relieving_date >= '{period_start}'))
		)
		-- Exclude Inactive employees
		AND emp.status IN ('Active', 'Left')
		{emp_filter}
	""", as_dict=1)

	# Add missing employees to employee_data
	for emp in all_active_employees:
		if emp.employee not in employee_data:
			employee_data[emp.employee] = {
				'employee_id': emp.employee,
				'employee_name': emp.employee_name or '',
				'date_of_joining': emp.date_of_joining,
				'relieving_date': emp.relieving_date,
				'custom_group': emp.custom_group or '',
				'department': clean_department_name(emp.department or ''),
				'designation': emp.designation or '',
				'daily_data': {}
			}
		else:
			# Update designation for existing employees
			employee_data[emp.employee]['designation'] = emp.designation or ''

	# Convert to list and sort
	result = list(employee_data.values())

	# Get sort order from filters (default: Ascending)
	sort_order = filters.get('sort_order', 'Ascending')
	is_descending = (sort_order == 'Descending')

	# Get split_department option (default: True)
	split_department = filters.get('split_department', 1)

	# Sort by department, group, name (with optional reverse)
	result.sort(
		key=lambda x: (
			x.get('department', '') or '',
			x.get('custom_group', '') or '',
			x.get('employee_name', '') or ''
		),
		reverse=is_descending
	)

	# Ensure all employees have entries for all dates in range
	for emp in result:
		for date_obj in date_range['dates']:
			date_key = date_obj.strftime('%Y-%m-%d')
			if date_key not in emp['daily_data']:
				emp['daily_data'][date_key] = ''

	# Group by department if split_department is enabled
	if split_department:
		grouped_result = []
		current_dept = None
		dept_employees = []

		for emp in result:
			emp_dept = emp.get('department', '') or 'No Department'

			if current_dept != emp_dept:
				# Add previous department group
				if current_dept is not None and dept_employees:
					grouped_result.append({
						'type': 'department_header',
						'department': current_dept,
						'employees': dept_employees
					})

				# Start new department group
				current_dept = emp_dept
				dept_employees = [emp]
			else:
				dept_employees.append(emp)

		# Add the last department group
		if current_dept is not None and dept_employees:
			grouped_result.append({
				'type': 'department_header',
				'department': current_dept,
				'employees': dept_employees
			})

		return grouped_result
	else:
		# No department grouping - return flat list
		# Wrap in a single group for consistent structure
		return [{
			'type': 'no_department_header',
			'department': 'All Employees',
			'employees': result
		}]


def setup_excel_headers(ws, date_range, _filters):
	"""Setup Excel headers similar to template"""
	from openpyxl.styles import Font, Alignment

	# Calculate total columns needed
	total_cols = 8 + len(date_range['dates']) + 2  # Basic columns (8) + dates + total + confirmation

	# Row 1: Main title (merge and center)
	ws.cell(row=1, column=1, value="EMPLOYEE TIMESHEET")
	ws.cell(row=1, column=1).font = Font(name='Times New Roman', size=12, bold=True)
	ws.cell(row=1, column=1).alignment = Alignment(horizontal='center', vertical='center')
	ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)

	# Row 2: Vietnamese title (merge and center)
	ws.cell(row=2, column=1, value="BẢNG CHẤM CÔNG NHÂN VIÊN")
	ws.cell(row=2, column=1).font = Font(name='Times New Roman', size=12, bold=True)
	ws.cell(row=2, column=1).alignment = Alignment(horizontal='center', vertical='center')
	ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)

	# Row 3: Period and date range (merge and center)
	from_date_str = date_range['from_date'].strftime('%d %b %y')
	to_date_str = date_range['to_date'].strftime('%d %b %y')
	ws.cell(row=3, column=1, value=f"{date_range['period_name']} ({from_date_str} - {to_date_str})")
	ws.cell(row=3, column=1).font = Font(name='Times New Roman', size=10)
	ws.cell(row=3, column=1).alignment = Alignment(horizontal='center', vertical='center')
	ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=total_cols)

	# Row 5: Column headers
	headers = [
		"No./ STT",
		"Employee ID /Mã NV",
		"Full name/Họ tên",
		"Ngày kí hợp đồng",
		"Resign on/ Nghỉ việc",
		"Line/ Chuyền",
		"Section/ Bộ phận",
		"Position/Chức vụ"
	]

	# Set fixed headers (columns 1-8) and merge with rows 6-7
	for i, header in enumerate(headers, 1):
		cell = ws.cell(row=5, column=i, value=header)
		cell.font = Font(name='Times New Roman', bold=True, size=10)
		cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
		# Merge each header cell with the 2 rows below (rows 6 and 7)
		ws.merge_cells(start_row=5, start_column=i, end_row=7, end_column=i)

	# Set last two headers (total first, then confirmation)
	total_col = 9 + len(date_range['dates'])
	confirmation_col = total_col + 1

	ws.cell(row=5, column=total_col, value="Total working days/Tổng ngày công")
	ws.cell(row=5, column=total_col).font = Font(name='Times New Roman', bold=True, size=10)
	ws.cell(row=5, column=total_col).alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
	# Merge total column with rows 6-7
	ws.merge_cells(start_row=5, start_column=total_col, end_row=7, end_column=total_col)

	ws.cell(row=5, column=confirmation_col, value="Xác nhận")
	ws.cell(row=5, column=confirmation_col).font = Font(name='Times New Roman', bold=True, size=10)
	ws.cell(row=5, column=confirmation_col).alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
	# Merge confirmation column with rows 6-7
	ws.merge_cells(start_row=5, start_column=confirmation_col, end_row=7, end_column=confirmation_col)

	# Merge and set "DATE IN THE MONTH/ NGÀY TRONG THÁNG" header
	if len(date_range['dates']) > 0:
		date_start_col = 9
		date_end_col = 8 + len(date_range['dates'])
		ws.cell(row=5, column=date_start_col, value="DATE IN THE MONTH/ NGÀY TRONG THÁNG")
		ws.cell(row=5, column=date_start_col).font = Font(name='Times New Roman', bold=True, size=10)
		ws.cell(row=5, column=date_start_col).alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
		ws.merge_cells(start_row=5, start_column=date_start_col, end_row=5, end_column=date_end_col)

	# Row 6: Dates (only day number)
	for i, date_obj in enumerate(date_range['dates']):
		col = 9 + i  # Start from column 9
		ws.cell(row=6, column=col, value=date_obj.day)  # Only day number
		cell = ws.cell(row=6, column=col)
		cell.font = Font(name='Times New Roman', size=9)
		cell.alignment = Alignment(horizontal='center')

	# Row 7: Day of week
	for i, date_obj in enumerate(date_range['dates']):
		col = 9 + i
		day_of_week = date_obj.strftime('%a')[:1]  # First letter of day
		ws.cell(row=7, column=col, value=day_of_week)
		cell = ws.cell(row=7, column=col)
		cell.font = Font(name='Times New Roman', size=9, bold=True)
		cell.alignment = Alignment(horizontal='center')


def populate_employee_data(ws, employee_data, date_range):
	"""Populate employee data into Excel with department grouping"""
	from openpyxl.styles import PatternFill, Font, Alignment

	start_row = 8
	current_row = start_row
	total_columns = 9 + len(date_range['dates']) + 2  # Basic + dates + total + confirmation

	# Create light gray fill for department headers
	dept_fill = PatternFill(start_color='E0E0E0', end_color='E0E0E0', fill_type='solid')

	all_employees = []  # Keep track of all employees for total calculation
	stt_counter = 1  # Continuous numbering across departments
	first_employee_row = None  # Track first employee row for SUM formulas

	for dept_group in employee_data:
		# Check if we should add department header
		if dept_group.get('type') == 'department_header':
			# Add department header row
			dept_name = dept_group['department']
			ws.cell(row=current_row, column=1, value=dept_name)
			dept_cell = ws.cell(row=current_row, column=1)
			dept_cell.font = Font(name='Times New Roman', bold=True, size=10)
			dept_cell.alignment = Alignment(horizontal='left', vertical='center')

			# Apply gray background to entire row
			for col in range(1, total_columns):
				cell = ws.cell(row=current_row, column=col)
				cell.fill = dept_fill

			current_row += 1

			# Add employees in this department
			for emp in dept_group['employees']:
				all_employees.append(emp)  # Track for totals
				# Track first employee row for formulas
				if first_employee_row is None:
					first_employee_row = current_row
				populate_single_employee_row(ws, emp, current_row, date_range, stt_counter)
				stt_counter += 1
				current_row += 1

		elif dept_group.get('type') == 'no_department_header':
			# No department header - just add employees directly
			for emp in dept_group['employees']:
				all_employees.append(emp)  # Track for totals
				# Track first employee row for formulas
				if first_employee_row is None:
					first_employee_row = current_row
				populate_single_employee_row(ws, emp, current_row, date_range, stt_counter)
				stt_counter += 1
				current_row += 1

	return all_employees, current_row, first_employee_row


def populate_single_employee_row(ws, emp, row, date_range, stt_number):
	"""Populate a single employee row"""
	from datetime import datetime
	from openpyxl.styles import Font, Alignment
	from openpyxl.utils import get_column_letter

	# Basic employee info
	ws.cell(row=row, column=1, value=stt_number)  # STT
	ws.cell(row=row, column=2, value=emp['employee_id'])
	ws.cell(row=row, column=3, value=emp['employee_name'])

	# Format dates as dd/mm/yyyy
	if emp['date_of_joining']:
		if hasattr(emp['date_of_joining'], 'strftime'):
			ws.cell(row=row, column=4, value=emp['date_of_joining'].strftime('%d/%m/%Y'))
		else:
			# Parse string date and format
			try:
				date_obj = datetime.strptime(str(emp['date_of_joining']), '%Y-%m-%d')
				ws.cell(row=row, column=4, value=date_obj.strftime('%d/%m/%Y'))
			except:
				ws.cell(row=row, column=4, value=str(emp['date_of_joining']))
	else:
		ws.cell(row=row, column=4, value='')

	if emp['relieving_date']:
		if hasattr(emp['relieving_date'], 'strftime'):
			ws.cell(row=row, column=5, value=emp['relieving_date'].strftime('%d/%m/%Y'))
		else:
			# Parse string date and format
			try:
				date_obj = datetime.strptime(str(emp['relieving_date']), '%Y-%m-%d')
				ws.cell(row=row, column=5, value=date_obj.strftime('%d/%m/%Y'))
			except:
				ws.cell(row=row, column=5, value=str(emp['relieving_date']))
	else:
		ws.cell(row=row, column=5, value='')

	ws.cell(row=row, column=6, value=emp['custom_group'])
	ws.cell(row=row, column=7, value='')  # Section - not available in Attendance
	ws.cell(row=row, column=8, value=emp['designation'])  # Position/Chức vụ

	# Set font and alignment for employee data (size 8)
	for col in range(1, 9):  # Columns 1-8
		cell = ws.cell(row=row, column=col)
		cell.font = Font(name='Times New Roman', size=8)
		# Left-align these specific columns
		cell.alignment = Alignment(horizontal='left', vertical='center')

	# Daily attendance data
	for j, date_obj in enumerate(date_range['dates']):
		col = 9 + j
		date_key = date_obj.strftime('%Y-%m-%d')
		value = emp['daily_data'].get(date_key, '')
		ws.cell(row=row, column=col, value=value)

		# Center align attendance data with font
		cell = ws.cell(row=row, column=col)
		cell.font = Font(name='Times New Roman', size=8)
		cell.alignment = Alignment(horizontal='center', vertical='center')

	# Add total working days column with SUM formula
	total_col = 9 + len(date_range['dates'])
	# Create SUM formula for this row's daily attendance data
	start_col_letter = get_column_letter(9)  # First date column
	end_col_letter = get_column_letter(8 + len(date_range['dates']))  # Last date column
	sum_formula = f"=SUM({start_col_letter}{row}:{end_col_letter}{row})"
	cell = ws.cell(row=row, column=total_col, value=sum_formula)
	cell.font = Font(name='Times New Roman', size=8)
	cell.alignment = Alignment(horizontal='center', vertical='center')

	# Add confirmation column (empty)
	confirmation_col = total_col + 1
	cell = ws.cell(row=row, column=confirmation_col, value='')
	cell.font = Font(name='Times New Roman', size=8)
	cell.alignment = Alignment(horizontal='center', vertical='center')


def add_total_row(ws, _all_employees, total_row, date_range, first_employee_row):
	"""Add total row at the end with SUM formulas"""
	from openpyxl.utils import get_column_letter
	from openpyxl.styles import PatternFill, Font, Alignment

	# Create light gray fill for total row
	total_fill = PatternFill(start_color='E0E0E0', end_color='E0E0E0', fill_type='solid')
	total_columns = 9 + len(date_range['dates']) + 2  # Basic + dates + total + confirmation

	ws.cell(row=total_row, column=1, value="TOTAL")
	ws.cell(row=total_row, column=1).font = Font(name='Times New Roman', bold=True, size=8)
	ws.cell(row=total_row, column=1).alignment = Alignment(horizontal='center', vertical='center')

	# Add SUM formulas for each date column
	last_employee_row = total_row - 1  # Row just before TOTAL row
	for j, date_obj in enumerate(date_range['dates']):
		col = 9 + j
		col_letter = get_column_letter(col)
		# Create SUM formula from first employee row to last employee row
		sum_formula = f"=SUM({col_letter}{first_employee_row}:{col_letter}{last_employee_row})"
		ws.cell(row=total_row, column=col, value=sum_formula)

		ws.cell(row=total_row, column=col).font = Font(name='Times New Roman', bold=True, size=8)
		ws.cell(row=total_row, column=col).alignment = Alignment(horizontal='center', vertical='center')

	# Add grand total SUM formula in Total working days column
	total_col = 9 + len(date_range['dates'])
	total_col_letter = get_column_letter(total_col)
	# Sum all individual employee total working days
	grand_total_formula = f"=SUM({total_col_letter}{first_employee_row}:{total_col_letter}{last_employee_row})"
	ws.cell(row=total_row, column=total_col, value=grand_total_formula)
	ws.cell(row=total_row, column=total_col).font = Font(name='Times New Roman', bold=True, size=8)
	ws.cell(row=total_row, column=total_col).alignment = Alignment(horizontal='center', vertical='center')

	# Add gray background to entire TOTAL row
	for col in range(1, total_columns):
		cell = ws.cell(row=total_row, column=col)
		cell.fill = total_fill


def add_excel_footer(ws, current_row, date_range):
	"""Add footer with signatures and notes exactly like the template"""
	from datetime import date
	from openpyxl.styles import Font, Alignment

	total_columns = 8 + len(date_range['dates']) + 2  # Basic columns + dates + total + confirmation

	# Add some space before footer
	footer_start_row = current_row + 2

	# Add location and date
	date_row = footer_start_row
	current_date = date.today()
	date_str_en = f"Quang Ngai, {current_date.strftime('%d %b %Y')}"
	date_str_vn = f"Quảng Ngãi, ngày {current_date.day} tháng {current_date.month:02d} năm {current_date.year}"

	# Position date in column 29 area (right side)
	date_col = min(total_columns - 10, 25)  # Adjust based on total columns
	ws.cell(row=date_row, column=date_col, value=date_str_en)
	ws.cell(row=date_row, column=date_col).font = Font(name='Times New Roman', size=10)
	ws.cell(row=date_row, column=date_col).alignment = Alignment(horizontal='center', vertical='center')

	date_row_vn = date_row + 1
	ws.cell(row=date_row_vn, column=date_col, value=date_str_vn)
	ws.cell(row=date_row_vn, column=date_col).font = Font(name='Times New Roman', size=10)
	ws.cell(row=date_row_vn, column=date_col).alignment = Alignment(horizontal='center', vertical='center')

	# Signature section
	signature_row = date_row_vn + 1

	# Three signature columns as per template
	# Left signature (Col 3 area) - Prepared by
	ws.cell(row=signature_row, column=3, value="Prepared by")
	ws.cell(row=signature_row, column=3).font = Font(name='Times New Roman', bold=True, size=10)
	ws.cell(row=signature_row, column=3).alignment = Alignment(horizontal='center', vertical='center')

	# Middle signature (Col 15 area) - Verified by
	middle_col = min(15, total_columns // 2)
	ws.cell(row=signature_row, column=middle_col, value="Verified by")
	ws.cell(row=signature_row, column=middle_col).font = Font(name='Times New Roman', bold=True, size=10)
	ws.cell(row=signature_row, column=middle_col).alignment = Alignment(horizontal='center', vertical='center')

	# Right signature (Col 29 area) - Approved by
	right_col = min(total_columns - 5, date_col)
	ws.cell(row=signature_row, column=right_col, value="Approved by")
	ws.cell(row=signature_row, column=right_col).font = Font(name='Times New Roman', bold=True, size=10)
	ws.cell(row=signature_row, column=right_col).alignment = Alignment(horizontal='center', vertical='center')

	# Job titles
	title_row = signature_row + 1
	ws.cell(row=title_row, column=3, value="C&B Executive")
	ws.cell(row=title_row, column=3).font = Font(name='Times New Roman', size=10)
	ws.cell(row=title_row, column=3).alignment = Alignment(horizontal='center', vertical='center')

	ws.cell(row=title_row, column=middle_col, value="Office Department Manager")
	ws.cell(row=title_row, column=middle_col).font = Font(name='Times New Roman', size=10)
	ws.cell(row=title_row, column=middle_col).alignment = Alignment(horizontal='center', vertical='center')

	ws.cell(row=title_row, column=right_col, value="Head of Branch")
	ws.cell(row=title_row, column=right_col).font = Font(name='Times New Roman', size=10)
	ws.cell(row=title_row, column=right_col).alignment = Alignment(horizontal='center', vertical='center')

	# Names
	name_row = signature_row + 6
	ws.cell(row=name_row, column=3, value="Phạm Thị Kim Loan")
	ws.cell(row=name_row, column=3).font = Font(name='Times New Roman', size=10)
	ws.cell(row=name_row, column=3).alignment = Alignment(horizontal='center', vertical='center')

	ws.cell(row=name_row, column=middle_col, value="Nguyễn Thị Yến Ni")
	ws.cell(row=name_row, column=middle_col).font = Font(name='Times New Roman', size=10)
	ws.cell(row=name_row, column=middle_col).alignment = Alignment(horizontal='center', vertical='center')

	ws.cell(row=name_row, column=right_col, value="KITAJIMA MOTOHARU")
	ws.cell(row=name_row, column=right_col).font = Font(name='Times New Roman', size=10)
	ws.cell(row=name_row, column=right_col).alignment = Alignment(horizontal='center', vertical='center')


def apply_excel_formatting(ws, num_employees, num_dates, date_range):
	"""Apply formatting to Excel worksheet"""
	from openpyxl.utils import get_column_letter
	from openpyxl.styles import Border, Side, PatternFill

	# Set column widths
	ws.column_dimensions['A'].width = 8   # STT
	ws.column_dimensions['B'].width = 12  # Employee ID
	ws.column_dimensions['C'].width = 25  # Name
	ws.column_dimensions['D'].width = 12  # Join date
	ws.column_dimensions['E'].width = 12  # Resign date
	ws.column_dimensions['F'].width = 12  # Group
	ws.column_dimensions['G'].width = 15  # Section
	ws.column_dimensions['H'].width = 15  # Position

	# Set width for date columns
	for i in range(num_dates):
		col_letter = get_column_letter(9 + i)
		ws.column_dimensions[col_letter].width = 4

	# Set width for total and confirmation columns
	total_col = get_column_letter(9 + num_dates)
	confirmation_col = get_column_letter(9 + num_dates + 1)
	ws.column_dimensions[total_col].width = 9  # Total working days
	ws.column_dimensions[confirmation_col].width = 12  # Xác nhận

	# Set row heights
	ws.row_dimensions[5].height = 30  # Header row
	ws.row_dimensions[6].height = 20  # Date row
	ws.row_dimensions[7].height = 15  # Day row

	# Apply borders to data area
	thin_border = Border(
		left=Side(style='thin'),
		right=Side(style='thin'),
		top=Side(style='thin'),
		bottom=Side(style='thin')
	)

	# Header borders and background (light blue-gray)
	header_fill = PatternFill(start_color='B0C4DE', end_color='B0C4DE', fill_type='solid')  # Light steel blue
	sunday_fill = PatternFill(start_color='D3D3D3', end_color='D3D3D3', fill_type='solid')  # Gray for Sundays

	# Calculate total columns including new ones
	total_columns = 9 + num_dates + 2  # Basic + dates + confirmation + total

	# Apply to headers (rows 5-7)
	for row in range(5, 8):
		for col in range(1, total_columns):
			cell = ws.cell(row=row, column=col)
			cell.border = thin_border
			cell.fill = header_fill

	# Apply to data rows (including total row)
	for row in range(8, 8 + num_employees):  # num_employees already includes total row
		for col in range(1, total_columns):
			cell = ws.cell(row=row, column=col)

			# Apply border to regular employee rows only
			cell.border = thin_border

			# Check if this is a Sunday column
			if col >= 9 and col < 9 + num_dates:  # Date columns only
				date_index = col - 9
				if date_index < len(date_range['dates']):
					date_obj = date_range['dates'][date_index]
					if date_obj.weekday() == 6:  # Sunday = 6 in Python weekday()
						# Only apply Sunday fill if not already a department/total row
						if not cell.fill or cell.fill.start_color.rgb != 'FFE0E0E0':
							cell.fill = sunday_fill


def delete_export_file(file_name):
	"""Delete exported Excel file after download
	This function is called via background job after a delay to allow download to complete
	"""
	import time

	# Wait 2 minutes before deleting to ensure download completes
	time.sleep(120)

	try:
		if frappe.db.exists('File', file_name):
			frappe.delete_doc('File', file_name, ignore_permissions=True)
			frappe.db.commit()
	except Exception as e:
		# Log error but don't raise - file cleanup is not critical
		frappe.log_error(f"Failed to delete export file {file_name}: {str(e)}", "Export File Cleanup")
