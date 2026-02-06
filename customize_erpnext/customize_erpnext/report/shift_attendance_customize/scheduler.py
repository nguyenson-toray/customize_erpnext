import frappe
from frappe import _
from frappe.utils import today, formatdate, get_datetime, add_days
from datetime import datetime, time as time_obj, timedelta
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
import os
import tempfile
from customize_erpnext.api.site_restriction import only_for_sites

@frappe.whitelist()
def send_daily_attendance_report(report_date=None, recipients=None):
	"""
	Send Daily Attendance Report via email
	Can be called manually from Report with custom date and recipients

	Args:
		report_date: Optional date string (YYYY-MM-DD format). Defaults to today.
		recipients: Optional list or comma-separated string of email addresses.
				   Defaults to predefined list.
	"""
	try:
		# Get report date - use provided date or default to today
		if report_date:
			# Handle both string and date object inputs
			if isinstance(report_date, str):
				report_date_obj = get_datetime(report_date).date()
			else:
				report_date_obj = report_date
			report_date_str = str(report_date_obj)
		else:
			report_date_obj = get_datetime(today()).date()
			report_date_str = today()

		# Import the report get_data function
		from customize_erpnext.customize_erpnext.report.shift_attendance_customize.shift_attendance_customize import get_data

		# Prepare filters for single date report
		filters = {
			"from_date": report_date_str,
			"to_date": report_date_str,
			"summary": 0,
			"detail_join_resign_date": 1
		}

		# Get report data
		data = get_data(filters)

		# Calculate statistics
		stats = calculate_attendance_statistics(report_date_str, data)

		# Get incomplete check-ins from day 26 of previous month to yesterday
		from frappe.utils import get_first_day, add_months
		current_month_first = get_first_day(report_date_str)
		prev_month_26 = add_days(add_months(current_month_first, -1), 25)
		yesterday = add_days(report_date_str, -1)
		incomplete_checkins = get_incomplete_checkins(prev_month_26, yesterday)

		# Add incomplete checkins to stats
		stats['incomplete_checkins'] = incomplete_checkins
		stats['incomplete_count'] = len(incomplete_checkins)
		stats['incomplete_processed'] = len([emp for emp in incomplete_checkins if emp.get('manual_checkins', '')])

		# Get last employee checkin time
		last_checkin_time = get_last_employee_checkin_time()

		# Generate email content
		email_subject = f"Báo cáo hiện diện / vắng ngày {formatdate(report_date_str, 'dd/MM/yyyy')}"
		email_content = generate_email_content(report_date_str, stats, data, last_checkin_time)

		# Generate Excel file
		excel_file_path, excel_file_name = generate_excel_report(report_date_str, data, stats)

		# Parse recipients
		if recipients:
			# Handle both list and newline/comma-separated string
			if isinstance(recipients, str):
				# Split by newlines and commas, remove empty strings
				import re
				recipient_list = [email.strip() for email in re.split(r'[\n,]', recipients) if email.strip()]
			else:
				recipient_list = recipients 
		# Send email with Excel attachment
		frappe.sendmail(
			recipients=recipient_list,
			subject=email_subject,
			message=email_content,
			attachments=[{
				'fname': excel_file_name,
				'fcontent': open(excel_file_path, 'rb').read()
			}],
			delayed=False
		)

		# Clean up temporary file
		try:
			os.remove(excel_file_path)
		except Exception as cleanup_error:
			frappe.logger().warning(f"Failed to clean up temp file {excel_file_path}: {str(cleanup_error)}")

		frappe.logger().info(f"Daily Attendance Report sent successfully for {report_date_str}")

		return {
			"status": "success",
			"message": f"Report sent successfully to {len(recipient_list)} recipients"
		}

	except Exception as e:
		frappe.logger().error(f"Error sending Daily Attendance Report: {str(e)}")
		frappe.log_error(
			title="Daily Attendance Report Scheduler Error",
			message=frappe.get_traceback()
		)
		return {
			"status": "error",
			"message": str(e)
		}


def calculate_attendance_statistics(report_date, data):
	"""
	Calculate statistics for the report:
	- Total active employees
	- Total present
	- Total absent (excluding on leave)
	- Total on leave (On Leave, Half Day)
	- Working hours summary
	"""
	# Count total active employees
	total_employees = frappe.db.count("Employee", filters={"status": "Active"})

	# Separate employees by status
	present_employees = []
	absent_employees = []
	on_leave_employees = []

	total_working_hours = 0
	total_actual_overtime = 0
	total_approved_overtime = 0
	total_final_overtime = 0

	# Group data by employee
	employee_data = {}
	for row in data:
		employee = row.get('employee')
		if employee not in employee_data:
			employee_data[employee] = row

			status = row.get('status')
			# Status may contain HTML tags, so extract the text
			if isinstance(status, str):
				if 'Present' in status or 'Sunday' in status:
					status_clean = 'Present'
				elif 'On Leave' in status or 'Half Day' in status:
					status_clean = 'On Leave'
				elif 'Absent' in status:
					status_clean = 'Absent'
				else:
					status_clean = status
			else:
				status_clean = status

			working_hours = row.get('working_hours', 0) or 0
			actual_overtime = row.get('actual_overtime_duration', 0) or 0
			approved_overtime = row.get('custom_approved_overtime_duration', 0) or 0
			final_overtime = row.get('final_overtime_duration', 0) or 0

			# Get employee details for the lists
			emp_info = {
				'employee': employee,
				'employee_name': row.get('employee_name'),
				'department': row.get('department'),
				'custom_group': row.get('custom_group'),
				'shift': row.get('shift'),
				'leave_type': row.get('leave_type'),
				'leave_application': row.get('leave_application'),
				'half_day_status': row.get('half_day_status'),
				'designation': '',  # Will need to get from Employee doctype
				'attendance_device_id': ''  # Will need to get from Employee doctype
			}

			# Get additional employee details
			emp_doc = frappe.get_value('Employee', employee, ['designation', 'attendance_device_id'], as_dict=True)
			if emp_doc:
				emp_info['designation'] = emp_doc.get('designation') or ''
				emp_info['attendance_device_id'] = emp_doc.get('attendance_device_id') or ''

			if status_clean == 'Present':
				present_employees.append(emp_info)
				total_working_hours += working_hours
				total_actual_overtime += actual_overtime
				total_approved_overtime += approved_overtime
				total_final_overtime += final_overtime
			elif status_clean == 'On Leave':
				on_leave_employees.append(emp_info)
			elif status_clean == 'Absent':
				absent_employees.append(emp_info)

	# Sort lists by custom_group (A-Z)
	present_employees = sorted(present_employees, key=lambda x: (x.get("custom_group") or "").lower())
	absent_employees = sorted(absent_employees, key=lambda x: (x.get("custom_group") or "").lower())
	on_leave_employees = sorted(on_leave_employees, key=lambda x: (x.get("custom_group") or "").lower())

	# Calculate counts
	total_present = len(present_employees)
	total_absent = len(absent_employees)
	on_leave_count = len(on_leave_employees)

	return {
		"total_employees": total_employees,
		"total_present": total_present,
		"total_absent": total_absent,
		"on_leave_count": on_leave_count,
		"total_working_hours": round(total_working_hours, 2),
		"total_actual_overtime": round(total_actual_overtime, 2),
		"total_approved_overtime": round(total_approved_overtime, 2),
		"total_final_overtime": round(total_final_overtime, 2),
		"present_employees": present_employees,
		"absent_employees": absent_employees,
		"on_leave_employees": on_leave_employees
	}


def get_last_employee_checkin_time():
	"""
	Get the last employee checkin time from the system
	Returns formatted time string or None if no checkins found
	"""
	try:
		last_checkin = frappe.db.sql("""
			SELECT MAX(time) as last_time
			FROM `tabEmployee Checkin`
		""", as_dict=True)

		if last_checkin and last_checkin[0].get('last_time'):
			last_time = last_checkin[0].get('last_time')
			# Format as datetime string
			if isinstance(last_time, str):
				last_time = get_datetime(last_time)
			return last_time.strftime("%H:%M:%S %d/%m/%Y")
		return None
	except Exception as e:
		frappe.logger().error(f"Error getting last checkin time: {str(e)}")
		return None


def get_incomplete_checkins(start_date, end_date):
	"""
	Get list of employees who have incomplete check-ins from start_date to end_date
	"""
	employees_with_checkins = frappe.db.sql(f"""
		SELECT
			e.attendance_device_id,
			e.name AS employee_code,
			e.employee_name,
			e.department,
			e.custom_group,
			e.designation,
			DATE(ec.time) AS checkin_date,
			MIN(ec.time) AS first_check_in,
			MAX(ec.time) AS last_check_out,
			COUNT(ec.name) AS checkin_count,
			COALESCE(
				(SELECT srd.shift
				 FROM `tabShift Registration Detail` srd
				 JOIN `tabShift Registration` sr ON srd.parent = sr.name
				 WHERE srd.employee = e.name
				   AND srd.begin_date <= DATE(ec.time)
				   AND srd.end_date >= DATE(ec.time)
				   AND sr.docstatus = 1
				 ORDER BY sr.creation DESC
				 LIMIT 1),
				CASE
					WHEN e.custom_group = 'Canteen' THEN 'Canteen'
					ELSE 'Day'
				END
			) AS shift,
			sn.begin_time,
			sn.end_time
		FROM
			`tabEmployee` e
		INNER JOIN
			`tabEmployee Checkin` ec
		ON
			e.name = ec.employee
			AND DATE(ec.time) >= '{start_date}'
			AND DATE(ec.time) <= '{end_date}'
			AND ec.device_id IS NOT NULL
		LEFT JOIN
			`tabShift Name` sn
		ON
			sn.shift_name = COALESCE(
				(SELECT srd.shift
				 FROM `tabShift Registration Detail` srd
				 JOIN `tabShift Registration` sr ON srd.parent = sr.name
				 WHERE srd.employee = e.name
				   AND srd.begin_date <= DATE(ec.time)
				   AND srd.end_date >= DATE(ec.time)
				   AND sr.docstatus = 1
				 ORDER BY sr.creation DESC
				 LIMIT 1),
				CASE
					WHEN e.custom_group = 'Canteen' THEN 'Canteen'
					ELSE 'Day'
				END
			)
		WHERE
			e.status = 'Active'
		GROUP BY
			e.name, DATE(ec.time)
		ORDER BY
			DATE(ec.time) DESC, e.name ASC
	""", as_dict=1)

	# Filter employees with incomplete check-ins
	incomplete_list = []
	for emp in employees_with_checkins:
		is_incomplete = False
		checkin_count = emp.get('checkin_count')
		checkin_date = emp.get('checkin_date')

		# Rule 1: Only 1 check-in
		if checkin_count == 1:
			is_incomplete = True
		# Rule 2 & 3: >= 2 check-ins but all before begin_time OR all after end_time
		elif checkin_count >= 2:
			begin_time = emp.get('begin_time')
			end_time = emp.get('end_time')

			# Convert begin_time to time object
			if begin_time:
				if isinstance(begin_time, timedelta):
					total_seconds = int(begin_time.total_seconds())
					hours = total_seconds // 3600
					minutes = (total_seconds % 3600) // 60
					seconds = total_seconds % 60
					begin_time = time_obj(hours, minutes, seconds)

			# Convert end_time to time object
			if end_time:
				if isinstance(end_time, timedelta):
					total_seconds = int(end_time.total_seconds())
					hours = total_seconds // 3600
					minutes = (total_seconds % 3600) // 60
					seconds = total_seconds % 60
					end_time = time_obj(hours, minutes, seconds)

			# Get all automatic check-in times
			all_checkins = frappe.db.sql(f"""
				SELECT time
				FROM `tabEmployee Checkin`
				WHERE employee = '{emp.get('employee_code')}'
				  AND DATE(time) = '{checkin_date}'
				  AND device_id IS NOT NULL
				ORDER BY time
			""", as_dict=1)

			# Rule 2: All check-ins <= begin_time
			if begin_time and all_checkins and isinstance(begin_time, type(time_obj(0, 0, 0))):
				all_before_or_at_begin = True
				for checkin in all_checkins:
					checkin_time = checkin.get('time').time()
					if checkin_time > begin_time:
						all_before_or_at_begin = False
						break

				if all_before_or_at_begin:
					is_incomplete = True

			# Rule 3: All check-ins >= end_time
			if end_time and all_checkins and not is_incomplete and isinstance(end_time, type(time_obj(0, 0, 0))):
				all_after_or_at_end = True
				for checkin in all_checkins:
					checkin_time = checkin.get('time').time()
					if checkin_time < end_time:
						all_after_or_at_end = False
						break

				if all_after_or_at_end:
					is_incomplete = True

		if is_incomplete:
			# Get manual check-ins
			manual_checkins = frappe.db.sql(f"""
				SELECT
					TIME(time) as checkin_time,
					custom_reason_for_manual_check_in,
					custom_other_reason_for_manual_check_in
				FROM `tabEmployee Checkin`
				WHERE employee = '{emp.get('employee_code')}'
				  AND DATE(time) = '{checkin_date}'
				  AND device_id IS NULL
				ORDER BY time
			""", as_dict=1)

			# Format manual check-ins
			manual_checkin_times = []
			reasons = []
			other_reasons = []

			for mc in manual_checkins:
				if mc.get('checkin_time'):
					manual_checkin_times.append(str(mc.get('checkin_time')))
				if mc.get('custom_reason_for_manual_check_in'):
					reasons.append(mc.get('custom_reason_for_manual_check_in'))
				if mc.get('custom_other_reason_for_manual_check_in'):
					other_reasons.append(mc.get('custom_other_reason_for_manual_check_in'))

			emp['manual_checkins'] = ', '.join(manual_checkin_times) if manual_checkin_times else ''
			emp['reason_for_manual'] = ', '.join(set(reasons)) if reasons else ''
			emp['other_reason_for_manual'] = ', '.join(set(other_reasons)) if other_reasons else ''

			incomplete_list.append(emp)

	return incomplete_list


def get_current_frappe_site_name():
	"""Get current Frappe site name"""
	try:
		return frappe.local.site or "ERPNext"
	except:
		return "ERPNext"


def generate_email_content(report_date, stats, data, last_checkin_time=None):
	"""
	Generate HTML email content with statistics and three employee lists
	"""
	formatted_date = formatdate(report_date, "dd/MM/yyyy")
	current_time = datetime.now().strftime("%H:%M:%S %d/%m/%Y")

	# Format last checkin time message
	last_data_time_msg = ""
	if last_checkin_time:
		last_data_time_msg = f"<br>Thời điểm chấm công sau cùng: {last_checkin_time}"

	# Get date range for incomplete checkins
	from frappe.utils import get_first_day, add_months
	current_month_first = get_first_day(report_date)
	prev_month_26 = add_days(add_months(current_month_first, -1), 25)
	yesterday = add_days(report_date, -1)
	date_range_formatted = f"{formatdate(prev_month_26, 'dd/MM/yyyy')} - {formatdate(yesterday, 'dd/MM/yyyy')}"

	# Build absent employee table (excluding on leave)
	absent_rows = ""
	absent_list = stats.get('absent_employees', [])

	if absent_list:
		for idx, emp in enumerate(absent_list, 1):
			absent_rows += f"""
			<tr>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{idx}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{formatted_date}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('attendance_device_id') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_name') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('department') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('custom_group') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('shift') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('designation') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('leave_type') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{emp.get('leave_application') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{emp.get('half_day_status') or ''}</td>
			</tr>
			"""
	else:
		absent_rows = """
		<tr>
			<td colspan="12" style="border: 1px solid #ddd; padding: 8px; text-align: center; color: #999;">
				Không có nhân viên vắng
			</td>
		</tr>
		"""

	# Build on leave employee table
	on_leave_rows = ""
	on_leave_list = stats.get('on_leave_employees', [])

	if on_leave_list:
		for idx, emp in enumerate(on_leave_list, 1):
			on_leave_rows += f"""
			<tr>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{idx}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{formatted_date}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('attendance_device_id') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_name') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('department') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('custom_group') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('shift') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('designation') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('leave_type') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{emp.get('leave_application') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{emp.get('half_day_status') or ''}</td>
			</tr>
			"""
	else:
		on_leave_rows = """
		<tr>
			<td colspan="12" style="border: 1px solid #ddd; padding: 8px; text-align: center; color: #999;">
				Không có nhân viên nghỉ phép
			</td>
		</tr>
		"""

	# Build incomplete check-ins table
	incomplete_checkin_rows = ""
	incomplete_list = stats.get('incomplete_checkins', [])

	if incomplete_list:
		for idx, emp in enumerate(incomplete_list, 1):
			checkin_count = emp.get('checkin_count') or 0
			checkin_date = emp.get('checkin_date')
			checkin_date_formatted = formatdate(checkin_date, "dd/MM/yyyy") if checkin_date else ""

			first_checkin = ""
			last_checkout = ""

			if checkin_count == 1:
				# Single checkin - determine if check-in or check-out
				single_time = emp.get("first_check_in")
				if single_time:
					if isinstance(single_time, str):
						single_time = get_datetime(single_time)
					formatted_time = single_time.strftime("%H:%M:%S %d/%m/%Y")
					single_time_only = single_time.time()

					begin_time = emp.get('begin_time')
					end_time = emp.get('end_time')

					# Convert timedelta to time
					if begin_time and isinstance(begin_time, timedelta):
						total_seconds = int(begin_time.total_seconds())
						hours = total_seconds // 3600
						minutes = (total_seconds % 3600) // 60
						seconds = total_seconds % 60
						begin_time = time_obj(hours, minutes, seconds)

					if end_time and isinstance(end_time, timedelta):
						total_seconds = int(end_time.total_seconds())
						hours = total_seconds // 3600
						minutes = (total_seconds % 3600) // 60
						seconds = total_seconds % 60
						end_time = time_obj(hours, minutes, seconds)

					# Calculate distance from begin and end time
					if begin_time and end_time:
						single_seconds = single_time_only.hour * 3600 + single_time_only.minute * 60 + single_time_only.second
						begin_seconds = begin_time.hour * 3600 + begin_time.minute * 60 + begin_time.second
						end_seconds = end_time.hour * 3600 + end_time.minute * 60 + end_time.second

						distance_to_begin = abs(single_seconds - begin_seconds)
						distance_to_end = abs(single_seconds - end_seconds)

						if distance_to_begin < distance_to_end:
							first_checkin = formatted_time
						else:
							last_checkout = formatted_time
					else:
						noon_seconds = 12 * 3600
						single_seconds = single_time_only.hour * 3600 + single_time_only.minute * 60 + single_time_only.second
						if single_seconds < noon_seconds:
							first_checkin = formatted_time
						else:
							last_checkout = formatted_time
			else:
				# Multiple checkins
				first_checkin_time = emp.get("first_check_in")
				if first_checkin_time:
					if isinstance(first_checkin_time, str):
						first_checkin_time = get_datetime(first_checkin_time)
					first_checkin = first_checkin_time.strftime("%H:%M:%S %d/%m/%Y")

				last_checkout_time = emp.get("last_check_out")
				if last_checkout_time:
					if isinstance(last_checkout_time, str):
						last_checkout_time = get_datetime(last_checkout_time)
					last_checkout = last_checkout_time.strftime("%H:%M:%S %d/%m/%Y")

			# Get manual check-in info
			manual_checkins = emp.get('manual_checkins', '')
			reason_for_manual = emp.get('reason_for_manual', '')
			other_reason_for_manual = emp.get('other_reason_for_manual', '')

			incomplete_checkin_rows += f"""
			<tr>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{idx}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{checkin_date_formatted}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('attendance_device_id') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_code') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_name') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('department') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('custom_group') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('shift') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{emp.get('designation') or ''}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{first_checkin}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{last_checkout}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{checkin_count}</td>
				<td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{manual_checkins}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{reason_for_manual}</td>
				<td style="border: 1px solid #ddd; padding: 8px;">{other_reason_for_manual}</td>
			</tr>
			"""
	else:
		incomplete_checkin_rows = """
		<tr>
			<td colspan="15" style="border: 1px solid #ddd; padding: 8px; text-align: center; color: #999;">
				Không có nhân viên chấm công thiếu
			</td>
		</tr>
		"""

	html_content = f"""
	<html>
	<head>
		<style>
			body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
			.summary {{ margin: 20px 0; padding: 15px; background-color: #f5f5f5; border-radius: 5px; }}
			.summary-item {{ margin: 10px 0; font-size: 14px; }}
			.summary-item strong {{ color: #333; }}
			table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
			th {{ background-color: #4CAF50; color: white; padding: 10px; text-align: left; border: 1px solid #ddd; }}
			.number {{ color: #2196F3; font-weight: bold; }}
			.present {{ color: #4CAF50; font-weight: bold; }}
			.absent {{ color: #f44336; font-weight: bold; }}
			.maternity {{ color: #FF9800; font-weight: bold; }}
			.incomplete {{ color: #9C27B0; font-weight: bold; }}
		</style>
	</head>
	<body>
		<h2 style="color: #333;">Báo cáo hiện diện / vắng ngày {formatted_date}</h2>

		<div class="summary">
			<h3 style="margin-top: 0; color: #555;">Email này được gửi tự động từ hệ thống ERPNext (Site: {get_current_frappe_site_name()}) vào lúc {current_time}{last_data_time_msg}</h3>
			<h3 style="margin-top: 0; color: #555;">Tổng quan:</h3>
			<div class="summary-item">
				<strong>Số lượng nhân viên (Active):</strong>
				<span class="number">{stats['total_employees']}</span> người
			</div>
			<div class="summary-item">
				<strong>Số lượng hiện diện:</strong>
				<span class="present">{stats['total_present']}</span> người
			</div>
			<div class="summary-item">
				<strong>Số lượng vắng (không bao gồm nghỉ phép):</strong>
				<span class="absent">{stats['total_absent']}</span> người
			</div>
			<div class="summary-item">
				<strong>Số lượng nghỉ phép (On Leave / Half Day):</strong>
				<span class="maternity">{stats['on_leave_count']}</span> người
			</div>
			<div class="summary-item">
				<strong>Số lượng chấm công thiếu từ {date_range_formatted}:</strong>
				<span class="incomplete">{stats['incomplete_count']}</span> trường hợp
				<br>
				<strong>Đã xử lý:</strong>
				<span style="color: #4CAF50; font-weight: bold;">{stats['incomplete_processed']}</span> / <span class="incomplete">{stats['incomplete_count']}</span>
				<br>
				<small style="color: #666;">(Chỉ có 1 lần chấm công hoặc thiếu giờ chấm công vào/ra theo ca (Trên máy chấm công))</small>
			</div>
		</div>

		<h3 style="color: #555;">Danh sách nhân viên vắng (không bao gồm nghỉ phép):</h3>
		<table>
			<thead>
				<tr>
					<th style="width: 4%; text-align: center;">STT</th>
					<th style="width: 6%; text-align: center;">Ngày</th>
					<th style="width: 7%;">Att ID</th>
					<th style="width: 9%;">Employee</th>
					<th style="width: 14%;">Employee Name</th>
					<th style="width: 10%;">Department</th>
					<th style="width: 9%;">Group</th>
					<th style="width: 8%;">Shift</th>
					<th style="width: 11%;">Designation</th>
					<th style="width: 10%;">Leave Type</th>
					<th style="width: 12%; text-align: center;">Leave Application</th>
					<th style="width: 10%; text-align: center;">Status for Other Half</th>
				</tr>
			</thead>
			<tbody>
				{absent_rows}
			</tbody>
		</table>

		<h3 style="color: #555; margin-top: 30px;">Danh sách nhân viên nghỉ phép (On Leave / Half Day):</h3>
		<table>
			<thead>
				<tr>
					<th style="width: 4%; text-align: center;">STT</th>
					<th style="width: 6%; text-align: center;">Ngày</th>
					<th style="width: 7%;">Att ID</th>
					<th style="width: 9%;">Employee</th>
					<th style="width: 14%;">Employee Name</th>
					<th style="width: 10%;">Department</th>
					<th style="width: 9%;">Group</th>
					<th style="width: 8%;">Shift</th>
					<th style="width: 11%;">Designation</th>
					<th style="width: 10%;">Leave Type</th>
					<th style="width: 12%; text-align: center;">Leave Application</th>
					<th style="width: 10%; text-align: center;">Status for Other Half</th>
				</tr>
			</thead>
			<tbody>
				{on_leave_rows}
			</tbody>
		</table>

		<h3 style="color: #555; margin-top: 30px;">Danh sách nhân viên chấm công thiếu từ {date_range_formatted}:</h3>
		<table>
			<thead>
				<tr>
					<th style="width: 3%; text-align: center;">STT</th>
					<th style="width: 6%; text-align: center;">Ngày</th>
					<th style="width: 6%;">Att ID</th>
					<th style="width: 8%;">Employee</th>
					<th style="width: 12%;">Employee Name</th>
					<th style="width: 10%;">Department</th>
					<th style="width: 8%;">Group</th>
					<th style="width: 7%;">Shift</th>
					<th style="width: 10%;">Designation</th>
					<th style="width: 8%; text-align: center;">Check-in</th>
					<th style="width: 8%; text-align: center;">Check-out</th>
					<th style="width: 4%; text-align: center;">Số lần chấm</th>
					<th style="width: 8%; text-align: center;">Đã xử lý</th>
					<th style="width: 6%;">Reason</th>
					<th style="width: 6%;">Other Reason</th>
				</tr>
			</thead>
			<tbody>
				{incomplete_checkin_rows}
			</tbody>
		</table>

	</body>
	</html>
	"""

	return html_content


def generate_excel_report(report_date, data, stats):
	"""
	Generate Excel file with 2 sheets:
	1. Absent-Maternity Leave-Present: All attendance data for the day
	2. Missing check-ins from day 26 of previous month to yesterday
	"""
	# Create a new workbook
	wb = openpyxl.Workbook()

	# Remove default sheet
	wb.remove(wb.active)

	# Define styles
	header_font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
	header_fill = PatternFill(start_color='4CAF50', end_color='4CAF50', fill_type='solid')
	header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

	cell_font = Font(name='Arial', size=10)
	cell_alignment = Alignment(horizontal='left', vertical='center')
	center_alignment = Alignment(horizontal='center', vertical='center')

	border = Border(
		left=Side(style='thin', color='000000'),
		right=Side(style='thin', color='000000'),
		top=Side(style='thin', color='000000'),
		bottom=Side(style='thin', color='000000')
	)

	formatted_date = formatdate(report_date, "dd/MM/yyyy")

	# Sheet 1: All attendance data (Absent-OnLeave-Present)
	ws1 = wb.create_sheet("Absent-OnLeave-Present")

	# Combine all employee data sorted by status
	all_data = []
	all_data.extend(stats.get('absent_employees', []))
	all_data.extend(stats.get('on_leave_employees', []))
	all_data.extend(stats.get('present_employees', []))

	# Add headers for Sheet 1
	headers1 = ["STT", "Ngày", "Att ID", "Employee", "Employee Name", "Department", "Group", "Shift", "Designation", "Leave Type", "Leave Application", "Status for Other Half", "Status"]
	for col_num, header in enumerate(headers1, 1):
		cell = ws1.cell(row=1, column=col_num)
		cell.value = header
		cell.font = header_font
		cell.fill = header_fill
		cell.alignment = header_alignment
		cell.border = border

	# Add data for Sheet 1
	for idx, emp in enumerate(all_data, 1):
		# Determine status
		if emp in stats.get('absent_employees', []):
			status = 'Absent'
		elif emp in stats.get('on_leave_employees', []):
			status = 'On Leave'
		else:
			status = 'Present'

		row_data = [
			idx,
			formatted_date,
			emp.get('attendance_device_id') or '',
			emp.get('employee') or '',
			emp.get('employee_name') or '',
			emp.get('department') or '',
			emp.get('custom_group') or '',
			emp.get('shift') or '',
			emp.get('designation') or '',
			emp.get('leave_type') or '',
			emp.get('leave_application') or '',
			emp.get('half_day_status') or '',
			status
		]

		for col_num, value in enumerate(row_data, 1):
			cell = ws1.cell(row=idx + 1, column=col_num)
			cell.value = value
			cell.font = cell_font
			if col_num in [1, 2]:  # STT and Date columns
				cell.alignment = center_alignment
			else:
				cell.alignment = cell_alignment
			cell.border = border

	# Adjust column widths for Sheet 1
	ws1.column_dimensions['A'].width = 6   # STT
	ws1.column_dimensions['B'].width = 12  # Date
	ws1.column_dimensions['C'].width = 10  # Att ID
	ws1.column_dimensions['D'].width = 12  # Employee
	ws1.column_dimensions['E'].width = 25  # Employee Name
	ws1.column_dimensions['F'].width = 20  # Department
	ws1.column_dimensions['G'].width = 15  # Group
	ws1.column_dimensions['H'].width = 12  # Shift
	ws1.column_dimensions['I'].width = 20  # Designation
	ws1.column_dimensions['J'].width = 15  # Leave Type
	ws1.column_dimensions['K'].width = 20  # Leave Application
	ws1.column_dimensions['L'].width = 15  # Status

	# Sheet 2: Incomplete check-ins
	from frappe.utils import get_first_day, add_months
	current_month_first = get_first_day(report_date)
	prev_month_26 = add_days(add_months(current_month_first, -1), 25)
	yesterday = add_days(report_date, -1)
	from_date_str = formatdate(prev_month_26, "dd/MM/yyyy")
	to_date_str = formatdate(yesterday, "dd/MM/yyyy")

	# Sheet name cannot contain / character, so use - instead
	sheet_name = f"Missing {from_date_str} to {to_date_str}".replace('/', '-')
	ws2 = wb.create_sheet(sheet_name)

	# Add headers for Sheet 2
	headers2 = ["STT", "Ngày", "Att ID", "Employee", "Employee Name", "Department", "Group", "Shift", "Designation",
				"Check-in", "Check-out", "Số lần chấm", "Đã xử lý", "Reason", "Other Reason"]
	for col_num, header in enumerate(headers2, 1):
		cell = ws2.cell(row=1, column=col_num)
		cell.value = header
		cell.font = header_font
		cell.fill = header_fill
		cell.alignment = header_alignment
		cell.border = border

	# Add data for Sheet 2
	incomplete_list = stats.get('incomplete_checkins', [])
	for idx, emp in enumerate(incomplete_list, 1):
		checkin_date = emp.get('checkin_date')
		checkin_date_formatted = formatdate(checkin_date, "dd/MM/yyyy") if checkin_date else ""
		checkin_count = emp.get('checkin_count') or 0

		# Determine check-in and check-out times (same logic as email)
		first_checkin = ""
		last_checkout = ""

		if checkin_count == 1:
			single_time = emp.get("first_check_in")
			if single_time:
				if isinstance(single_time, str):
					single_time = get_datetime(single_time)
				formatted_time = single_time.strftime("%H:%M:%S")
				first_checkin = formatted_time
		else:
			first_checkin_time = emp.get("first_check_in")
			if first_checkin_time:
				if isinstance(first_checkin_time, str):
					first_checkin_time = get_datetime(first_checkin_time)
				first_checkin = first_checkin_time.strftime("%H:%M:%S")

			last_checkout_time = emp.get("last_check_out")
			if last_checkout_time:
				if isinstance(last_checkout_time, str):
					last_checkout_time = get_datetime(last_checkout_time)
				last_checkout = last_checkout_time.strftime("%H:%M:%S")

		row_data = [
			idx,
			checkin_date_formatted,
			emp.get('attendance_device_id') or '',
			emp.get('employee_code') or '',
			emp.get('employee_name') or '',
			emp.get('department') or '',
			emp.get('custom_group') or '',
			emp.get('shift') or '',
			emp.get('designation') or '',
			first_checkin,
			last_checkout,
			checkin_count,
			emp.get('manual_checkins', ''),
			emp.get('reason_for_manual', ''),
			emp.get('other_reason_for_manual', '')
		]

		for col_num, value in enumerate(row_data, 1):
			cell = ws2.cell(row=idx + 1, column=col_num)
			cell.value = value
			cell.font = cell_font
			if col_num in [1, 2, 10, 11, 12, 13]:  # STT, Date, Check-in, Check-out, Count, Manual columns
				cell.alignment = center_alignment
			else:
				cell.alignment = cell_alignment
			cell.border = border

	# Adjust column widths for Sheet 2
	ws2.column_dimensions['A'].width = 6   # STT
	ws2.column_dimensions['B'].width = 12  # Date
	ws2.column_dimensions['C'].width = 10  # Att ID
	ws2.column_dimensions['D'].width = 12  # Employee
	ws2.column_dimensions['E'].width = 25  # Employee Name
	ws2.column_dimensions['F'].width = 20  # Department
	ws2.column_dimensions['G'].width = 15  # Group
	ws2.column_dimensions['H'].width = 12  # Shift
	ws2.column_dimensions['I'].width = 20  # Designation
	ws2.column_dimensions['J'].width = 12  # Check-in
	ws2.column_dimensions['K'].width = 12  # Check-out
	ws2.column_dimensions['L'].width = 12  # Số lần chấm
	ws2.column_dimensions['M'].width = 15  # Đã xử lý
	ws2.column_dimensions['N'].width = 20  # Reason
	ws2.column_dimensions['O'].width = 20  # Other Reason

	# Save to temporary file
	temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
	wb.save(temp_file.name)
	temp_file.close()

	file_name = f"Attendance_Report_{formatted_date.replace('/', '')}.xlsx"

	return temp_file.name, file_name

@only_for_sites("erp.tiqn.local")
def send_daily_attendance_report_scheduled():
	"""
	Scheduled function to send daily attendance report at 8:15 AM
	Sends report for TODAY (current date) to track current presence/absence
	"""
	import frappe
	from frappe.utils import nowdate

	# Get today's date (not yesterday - we want to see current attendance at 8:15 AM)
	report_date = nowdate()

	# Default recipients
	recipients = ["it@tiqn.com.vn", "hoanh.ltk@tiqn.com.vn", "loan.ptk@tiqn.com.vn", "ni.nht@tiqn.com.vn", "binh.dtt@tiqn.com.vn"]
	recipients_str = "\n".join(recipients)

	try:
		# Call the main send function
		result = send_daily_attendance_report(report_date, recipients_str)

		frappe.logger().info(f"Daily attendance report scheduled send completed for {report_date}: {result}")
		return result

	except Exception as e:
		frappe.logger().error(f"Failed to send scheduled daily attendance report: {str(e)}")
		frappe.log_error(
			title="Daily Attendance Report Scheduled Send Failed",
			message=f"Error sending report for {report_date}: {str(e)}"
		)
		raise
