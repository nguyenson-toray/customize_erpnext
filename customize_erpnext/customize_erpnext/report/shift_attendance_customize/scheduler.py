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
def send_daily_attendance_report(report_date=None, recipients=None, force_update_attendance=0, bypass_holiday_check=0):
	"""
	Enqueue Daily Attendance Report to run in background.
	Returns immediately so UI doesn't timeout.

	Args:
		force_update_attendance: 1 = recalculate attendance before generating report
		                         0 = use existing attendance data as-is
	"""
	import re

	# Parse recipients early for validation
	if recipients:
		if isinstance(recipients, str):
			recipient_list = [email.strip() for email in re.split(r'[\n,]', recipients) if email.strip()]
		else:
			recipient_list = list(recipients)
	else:
		recipient_list = []

	if not recipient_list:
		return {"status": "error", "message": "No recipients specified"}

	# Resolve report_date
	if report_date:
		if isinstance(report_date, str):
			report_date_str = str(get_datetime(report_date).date())
		else:
			report_date_str = str(report_date)
	else:
		report_date_str = today()

	do_force_update = bool(int(force_update_attendance or 0))
	do_bypass = bool(int(bypass_holiday_check or 0))

	frappe.enqueue(
		_send_daily_attendance_report_job,
		queue="long",
		timeout=600,
		report_date_str=report_date_str,
		recipient_list=recipient_list,
		force_update_attendance=do_force_update,
		bypass_holiday_check=do_bypass
	)

	action = "Recalculating attendance then generating" if do_force_update else "Generating"
	return {
		"status": "success",
		"message": f"{action} report for {len(recipient_list)} recipients in background"
	}


def _is_holiday_or_sunday(date_str):
	"""Check if date is a Holiday (from default company Holiday List) or Sunday."""
	from frappe.utils import getdate

	check_date = getdate(date_str)

	# Check Sunday (weekday 6 = Sunday)
	if check_date.weekday() == 6:
		return True

	# Check Holiday List from default company
	default_company = frappe.defaults.get_defaults().get("company")
	if default_company:
		holiday_list = frappe.db.get_value("Company", default_company, "default_holiday_list")
		if holiday_list and frappe.db.exists("Holiday", {
			"parent": holiday_list,
			"holiday_date": check_date
		}):
			return True

	return False


def _send_daily_attendance_report_job(report_date_str, recipient_list, force_update_attendance=False, bypass_holiday_check=False):
	"""
	Background job: generate and send Daily Attendance Report via email.
	Skips sending on Holidays and Sundays unless bypass_holiday_check is True (UI-triggered).

	Args:
		force_update_attendance: True = recalculate attendance before generating report
		bypass_holiday_check: True = skip holiday/Sunday check (used when triggered from UI)
	"""
	# Skip sending on Holiday & Sunday (unless explicitly bypassed from UI)
	if not bypass_holiday_check and _is_holiday_or_sunday(report_date_str):
		frappe.logger().info(f"Skipping Daily Attendance Report for {report_date_str} — Holiday or Sunday")
		return

	try:
		# Recalculate attendance if requested
		if force_update_attendance:
			from customize_erpnext.overrides.shift_type.shift_type_optimized import _core_process_attendance_logic_optimized
			from frappe.utils import getdate
			frappe.logger().info(f"[Daily Report] Force updating attendance for {report_date_str}")
			_core_process_attendance_logic_optimized(
				employees=[],
				days=[getdate(report_date_str)],
				from_date=report_date_str,
				to_date=report_date_str,
				fore_get_logs=True
			)
			frappe.logger().info(f"[Daily Report] Attendance recalculation complete for {report_date_str}")

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

		# Get employees with status 'Left' but still have checkins on report date
		left_with_checkins = get_left_employees_with_checkins(report_date_str)
		stats['left_with_checkins'] = left_with_checkins
		stats['left_with_checkins_count'] = len(left_with_checkins)

		# Get early-checkout Day-shift employees (7 ≤ working_hours < 8, checkout 16:xx)
		# These may be pregnant/nursing employees not yet registered in Employee Maternity
		early_checkout_list, early_checkout_date = get_early_checkout_day_shift(report_date_str)
		stats['early_checkout_list'] = early_checkout_list
		stats['early_checkout_count'] = len(early_checkout_list)
		stats['early_checkout_date'] = early_checkout_date

		# Get last employee checkin time
		last_checkin_time = get_last_employee_checkin_time()

		# Generate email content
		email_subject = f"Báo cáo hiện diện / vắng ngày {formatdate(report_date_str, 'dd/MM/yyyy')}"
		email_content = generate_email_content(report_date_str, stats, data, last_checkin_time)

		# Generate Excel file
		excel_file_path, excel_file_name = generate_excel_report(report_date_str, data, stats)

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

	except Exception as e:
		frappe.logger().error(f"Error sending Daily Attendance Report: {str(e)}")
		frappe.log_error(
			title="Daily Attendance Report Scheduler Error",
			message=frappe.get_traceback()
		)


def calculate_attendance_statistics(report_date, data):
	"""
	Calculate statistics for the report:
	- Total active employees
	- Total present
	- Total absent (excluding on leave)
	- Total on leave (On Leave, Half Day)
	- Working hours summary
	"""
	# Count employees who were active on report_date
	# (not current Active count — some may have left since then)
	total_employees = frappe.db.sql("""
		SELECT COUNT(*) FROM `tabEmployee`
		WHERE (date_of_joining IS NULL OR date_of_joining <= %(date)s)
		  AND (
		      status = 'Active'
		      OR (status = 'Left' AND relieving_date >= %(date)s)
		  )
	""", {"date": report_date})[0][0]

	# Separate employees by status
	present_employees = []
	absent_employees = []
	on_leave_employees = []
	maternity_employees = []

	total_working_hours = 0
	total_actual_overtime = 0
	total_approved_overtime = 0
	total_final_overtime = 0

	# Query Employee Maternity for employees on maternity leave on report_date
	# (maternity_from_date..maternity_to_date only — not pregnant/young_child)
	maternity_emp_set = set(frappe.db.sql_list("""
		SELECT employee FROM `tabEmployee Maternity`
		WHERE maternity_from_date <= %(date)s AND maternity_to_date >= %(date)s
	""", {"date": report_date}))

	# Bulk-load employee details (designation, attendance_device_id) in ONE query
	all_employees = set(row.get('employee') for row in data if row.get('employee'))
	# Also include maternity employees who may have no attendance record
	all_employees.update(maternity_emp_set)
	emp_details_map = {}
	if all_employees:
		emp_details = frappe.db.sql("""
			SELECT name, employee_name, department, custom_group, designation, attendance_device_id
			FROM `tabEmployee`
			WHERE name IN %(employees)s AND status = 'Active'
		""", {"employees": list(all_employees)}, as_dict=True)
		for ed in emp_details:
			emp_details_map[ed.name] = ed

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

			# Get employee details from pre-loaded map
			emp_doc = emp_details_map.get(employee, {})
			emp_info = {
				'employee': employee,
				'employee_name': row.get('employee_name'),
				'department': row.get('department'),
				'custom_group': row.get('custom_group'),
				'shift': row.get('shift'),
				'leave_type': row.get('leave_type'),
				'leave_application': row.get('leave_application'),
				'half_day_status': row.get('half_day_status'),
				'designation': emp_doc.get('designation') or '',
				'attendance_device_id': emp_doc.get('attendance_device_id') or ''
			}

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

	# Add maternity employees from EM who have no attendance record (expected after simplification)
	# Also move any maternity employee who appeared as Absent into maternity list
	absent_emp_names = {e['employee'] for e in absent_employees}
	for emp in maternity_emp_set:
		emp_doc = emp_details_map.get(emp, {})
		if not emp_doc:
			continue  # Skip inactive or unknown employees
		mat_info = {
			'employee': emp,
			'employee_name': emp_doc.get('employee_name', ''),
			'department': emp_doc.get('department', ''),
			'custom_group': emp_doc.get('custom_group', ''),
			'shift': '',
			'leave_type': None,
			'leave_application': None,
			'half_day_status': None,
			'designation': emp_doc.get('designation') or '',
			'attendance_device_id': emp_doc.get('attendance_device_id') or ''
		}
		if emp not in employee_data:
			# No attendance record → add directly to maternity list
			maternity_employees.append(mat_info)
		elif emp in absent_emp_names:
			# Was marked Absent (old data before fix) → move to maternity list
			absent_employees = [e for e in absent_employees if e['employee'] != emp]
			maternity_employees.append(mat_info)

	# Sort lists by custom_group (A-Z)
	present_employees = sorted(present_employees, key=lambda x: (x.get("custom_group") or "").lower())
	absent_employees = sorted(absent_employees, key=lambda x: (x.get("custom_group") or "").lower())
	on_leave_employees = sorted(on_leave_employees, key=lambda x: (x.get("custom_group") or "").lower())
	maternity_employees = sorted(maternity_employees, key=lambda x: (x.get("custom_group") or "").lower())

	# Calculate counts
	total_present = len(present_employees)
	total_absent = len(absent_employees)
	on_leave_count = len(on_leave_employees)
	maternity_count = len(maternity_employees)

	return {
		"total_employees": total_employees,
		"total_present": total_present,
		"total_absent": total_absent,
		"on_leave_count": on_leave_count,
		"maternity_count": maternity_count,
		"total_working_hours": round(total_working_hours, 2),
		"total_actual_overtime": round(total_actual_overtime, 2),
		"total_approved_overtime": round(total_approved_overtime, 2),
		"total_final_overtime": round(total_final_overtime, 2),
		"present_employees": present_employees,
		"absent_employees": absent_employees,
		"on_leave_employees": on_leave_employees,
		"maternity_employees": maternity_employees
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


def _timedelta_to_time(td):
	"""Convert timedelta to time object"""
	if isinstance(td, timedelta):
		total_seconds = int(td.total_seconds())
		return time_obj(total_seconds // 3600, (total_seconds % 3600) // 60, total_seconds % 60)
	return td


def get_incomplete_checkins(start_date, end_date):
	"""
	Get list of employees who have incomplete check-ins from start_date to end_date.
	Optimized: eliminates correlated subqueries and N+1 query patterns.
	"""
	from collections import defaultdict

	# Step 1: Pre-load shift registrations for the date range (1 query)
	shift_reg_map = {}  # (employee, date) -> shift
	shift_regs = frappe.db.sql("""
		SELECT srd.employee, srd.shift, srd.begin_date, srd.end_date, sr.creation
		FROM `tabShift Registration Detail` srd
		JOIN `tabShift Registration` sr ON srd.parent = sr.name
		WHERE sr.docstatus = 1
		  AND srd.begin_date <= %(end_date)s
		  AND srd.end_date >= %(start_date)s
		ORDER BY sr.creation DESC
	""", {"start_date": start_date, "end_date": end_date}, as_dict=True)

	# Build map: (employee, date) -> shift (latest registration wins)
	for sr in shift_regs:
		emp = sr.employee
		d = sr.begin_date
		while d <= sr.end_date:
			key = (emp, d)
			if key not in shift_reg_map:
				shift_reg_map[key] = sr.shift
			d += timedelta(days=1)

	# Step 2: Pre-load shift begin/end times (1 query)
	shift_times = {}
	for sn in frappe.db.sql("""
		SELECT shift_name, begin_time, end_time FROM `tabShift Name`
	""", as_dict=True):
		shift_times[sn.shift_name] = {
			'begin_time': _timedelta_to_time(sn.begin_time),
			'end_time': _timedelta_to_time(sn.end_time)
		}

	# Step 3: Main query - simple aggregation, no correlated subqueries
	employees_with_checkins = frappe.db.sql("""
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
			COUNT(ec.name) AS checkin_count
		FROM `tabEmployee` e
		INNER JOIN `tabEmployee Checkin` ec
			ON e.name = ec.employee
			AND ec.time >= %(start)s
			AND ec.time < %(end)s
			AND ec.device_id IS NOT NULL
		WHERE e.status = 'Active'
		GROUP BY e.name, DATE(ec.time)
		ORDER BY DATE(ec.time) DESC, e.name ASC
	""", {
		"start": f"{start_date} 00:00:00",
		"end": f"{end_date} 23:59:59"
	}, as_dict=True)

	# Step 4: Resolve shift for each row using pre-loaded map
	for emp in employees_with_checkins:
		key = (emp.employee_code, emp.checkin_date)
		shift = shift_reg_map.get(key)
		if not shift:
			shift = 'Canteen' if emp.custom_group == 'Canteen' else 'Day'
		emp['shift'] = shift
		times = shift_times.get(shift, {})
		emp['begin_time'] = times.get('begin_time')
		emp['end_time'] = times.get('end_time')

	# Step 5: Pre-load ALL checkin times for candidates with >= 2 checkins (1 bulk query)
	# Also pre-load all manual checkins for the date range
	candidates = [(emp.get('employee_code'), emp.get('checkin_date')) for emp in employees_with_checkins]
	if not candidates:
		return []

	# Get unique employees
	candidate_employees = list(set(c[0] for c in candidates))

	# Bulk load all device checkins (for Rule 2/3 check)
	all_device_checkins = defaultdict(list)  # (employee, date) -> [time, ...]
	device_rows = frappe.db.sql("""
		SELECT employee, time
		FROM `tabEmployee Checkin`
		WHERE employee IN %(employees)s
		  AND time >= %(start)s
		  AND time < %(end)s
		  AND device_id IS NOT NULL
		ORDER BY employee, time
	""", {
		"employees": candidate_employees,
		"start": f"{start_date} 00:00:00",
		"end": f"{end_date} 23:59:59"
	}, as_dict=True)
	for row in device_rows:
		key = (row.employee, row.time.date())
		all_device_checkins[key].append(row.time)

	# Bulk load all manual checkins
	all_manual_checkins = defaultdict(list)  # (employee, date) -> [{...}, ...]
	manual_rows = frappe.db.sql("""
		SELECT employee, TIME(time) as checkin_time, time,
			custom_reason_for_manual_check_in,
			custom_other_reason_for_manual_check_in
		FROM `tabEmployee Checkin`
		WHERE employee IN %(employees)s
		  AND time >= %(start)s
		  AND time < %(end)s
		  AND device_id IS NULL
		ORDER BY employee, time
	""", {
		"employees": candidate_employees,
		"start": f"{start_date} 00:00:00",
		"end": f"{end_date} 23:59:59"
	}, as_dict=True)
	for row in manual_rows:
		key = (row.employee, row.time.date())
		all_manual_checkins[key].append(row)

	# Step 6: Filter incomplete check-ins using pre-loaded data
	incomplete_list = []
	for emp in employees_with_checkins:
		is_incomplete = False
		checkin_count = emp.get('checkin_count')
		checkin_date = emp.get('checkin_date')
		employee_code = emp.get('employee_code')

		# Rule 1: Only 1 check-in
		if checkin_count == 1:
			is_incomplete = True
		# Rule 2 & 3: >= 2 check-ins but all before begin_time OR all after end_time
		elif checkin_count >= 2:
			begin_time = emp.get('begin_time')
			end_time = emp.get('end_time')

			checkin_times = [t.time() for t in all_device_checkins.get((employee_code, checkin_date), [])]

			# Rule 2: All check-ins <= begin_time
			if begin_time and checkin_times and isinstance(begin_time, time_obj):
				if all(ct <= begin_time for ct in checkin_times):
					is_incomplete = True

			# Rule 3: All check-ins >= end_time
			if end_time and checkin_times and not is_incomplete and isinstance(end_time, time_obj):
				if all(ct >= end_time for ct in checkin_times):
					is_incomplete = True

		if is_incomplete:
			# Use pre-loaded manual checkins
			manual_checkins = all_manual_checkins.get((employee_code, checkin_date), [])

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


def get_early_checkout_day_shift(report_date):
	"""
	Lấy các attendance ngày hôm qua (ca Day) có:
	  - last checkout 16:00–16:59
	  - 7 <= working_hours < 8
	Thứ Hai → lấy thứ Bảy tuần trước (bỏ qua CN).
	Trả về (list, date_str).
	"""
	from frappe.utils import getdate

	yesterday = add_days(report_date, -1)
	yesterday_date = getdate(yesterday)
	# Thứ Hai (weekday=0): hôm qua là CN → dùng thứ Bảy
	if yesterday_date.weekday() == 6:
		yesterday = add_days(yesterday, -1)
		yesterday_date = getdate(yesterday)

	yesterday_str = str(yesterday_date)

	try:
		rows = frappe.db.sql("""
			SELECT
				e.attendance_device_id,
				a.employee,
				e.employee_name,
				e.department,
				e.custom_group,
				e.designation,
				a.attendance_date,
				a.working_hours,
				a.shift,
				MAX(ec.time) AS last_checkout
			FROM `tabAttendance` a
			JOIN `tabEmployee` e ON e.name = a.employee
			LEFT JOIN `tabEmployee Checkin` ec
				ON ec.employee = a.employee
				AND DATE(ec.time) = a.attendance_date
			WHERE a.attendance_date = %(yesterday)s
			  AND a.shift LIKE 'Day%%'
			  AND a.working_hours >= 7
			  AND a.working_hours < 8
			  AND a.docstatus = 1
			GROUP BY
				a.name, a.employee, a.attendance_date, a.working_hours, a.shift,
				e.attendance_device_id, e.employee_name, e.department,
				e.custom_group, e.designation
			HAVING TIME(MAX(ec.time)) >= '16:00:00'
			   AND TIME(MAX(ec.time)) <  '17:00:00'
			ORDER BY e.custom_group, e.employee_name
		""", {"yesterday": yesterday_str}, as_dict=True)
		return rows, yesterday_str
	except Exception as e:
		frappe.logger().error(f"Error in get_early_checkout_day_shift: {str(e)}")
		return [], yesterday_str


def get_left_employees_with_checkins(report_date):
	"""
	Get employees with status 'Left' who still have checkins on report_date.
	Used to alert HR to review these records.
	"""
	try:
		rows = frappe.db.sql("""
			SELECT
				e.attendance_device_id,
				e.name AS employee_code,
				e.employee_name,
				e.department,
				e.custom_group,
				e.designation,
				e.date_of_joining,
				e.relieving_date,
				MIN(ec.time) AS first_check_in,
				MAX(ec.time) AS last_check_out,
				COUNT(ec.name) AS checkin_count
			FROM `tabEmployee` e
			INNER JOIN `tabEmployee Checkin` ec
				ON e.name = ec.employee
				AND DATE(ec.time) = %(report_date)s
			WHERE e.status = 'Left'
			GROUP BY e.name
			ORDER BY e.custom_group, e.employee_name
		""", {"report_date": report_date}, as_dict=True)
		return rows
	except Exception as e:
		frappe.logger().error(f"Error getting left employees with checkins: {str(e)}")
		return []


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
			bg = '#fafafa' if idx % 2 == 0 else '#ffffff'
			absent_rows += f"""
			<tr style="background:{bg}">
				<td class="dc">{idx}</td>
				<td class="dc">{formatted_date}</td>
				<td class="d">{emp.get('attendance_device_id') or ''}</td>
				<td class="d">{emp.get('employee') or ''}</td>
				<td class="d"><strong>{emp.get('employee_name') or ''}</strong></td>
				<td class="d">{emp.get('department') or ''}</td>
				<td class="d">{emp.get('custom_group') or ''}</td>
				<td class="d">{emp.get('shift') or ''}</td>
				<td class="d">{emp.get('designation') or ''}</td>
				<td class="d">{emp.get('leave_type') or ''}</td>
				<td class="dc">{emp.get('leave_application') or ''}</td>
				<td class="dc">{emp.get('half_day_status') or ''}</td>
			</tr>"""
	else:
		absent_rows = """
		<tr>
			<td colspan="12" class="empty-row">Không có nhân viên vắng</td>
		</tr>
		"""

	# Build maternity leave employee table
	maternity_rows = ""
	maternity_list = stats.get('maternity_employees', [])

	if maternity_list:
		for idx, emp in enumerate(maternity_list, 1):
			bg = '#fafafa' if idx % 2 == 0 else '#ffffff'
			maternity_rows += f"""
			<tr style="background:{bg}">
				<td class="dc">{idx}</td>
				<td class="dc">{formatted_date}</td>
				<td class="d">{emp.get('attendance_device_id') or ''}</td>
				<td class="d">{emp.get('employee') or ''}</td>
				<td class="d"><strong>{emp.get('employee_name') or ''}</strong></td>
				<td class="d">{emp.get('department') or ''}</td>
				<td class="d">{emp.get('custom_group') or ''}</td>
				<td class="d">{emp.get('shift') or ''}</td>
				<td class="d">{emp.get('designation') or ''}</td>
				<td class="d">{emp.get('leave_type') or ''}</td>
				<td class="dc">{emp.get('leave_application') or ''}</td>
				<td class="dc">{emp.get('half_day_status') or ''}</td>
			</tr>"""
	else:
		maternity_rows = """
		<tr>
			<td colspan="12" class="empty-row">Không có nhân viên nghỉ thai sản</td>
		</tr>
		"""

	# Build on leave employee table (excluding maternity)
	on_leave_rows = ""
	on_leave_list = stats.get('on_leave_employees', [])

	if on_leave_list:
		for idx, emp in enumerate(on_leave_list, 1):
			bg = '#fafafa' if idx % 2 == 0 else '#ffffff'
			on_leave_rows += f"""
			<tr style="background:{bg}">
				<td class="dc">{idx}</td>
				<td class="dc">{formatted_date}</td>
				<td class="d">{emp.get('attendance_device_id') or ''}</td>
				<td class="d">{emp.get('employee') or ''}</td>
				<td class="d"><strong>{emp.get('employee_name') or ''}</strong></td>
				<td class="d">{emp.get('department') or ''}</td>
				<td class="d">{emp.get('custom_group') or ''}</td>
				<td class="d">{emp.get('shift') or ''}</td>
				<td class="d">{emp.get('designation') or ''}</td>
				<td class="d">{emp.get('leave_type') or ''}</td>
				<td class="dc">{emp.get('leave_application') or ''}</td>
				<td class="dc">{emp.get('half_day_status') or ''}</td>
			</tr>"""
	else:
		on_leave_rows = """
		<tr>
			<td colspan="12" class="empty-row">Không có nhân viên nghỉ phép</td>
		</tr>
		"""

	# Build "Left employees with checkins" warning table
	left_checkin_rows = ""
	left_checkin_list = stats.get('left_with_checkins', [])

	if left_checkin_list:
		for idx, emp in enumerate(left_checkin_list, 1):
			first_in = emp.get('first_check_in')
			last_out = emp.get('last_check_out')
			first_in_str = first_in.strftime("%H:%M:%S %d/%m/%Y") if first_in and hasattr(first_in, 'strftime') else (str(first_in) if first_in else '')
			last_out_str = last_out.strftime("%H:%M:%S %d/%m/%Y") if last_out and hasattr(last_out, 'strftime') else (str(last_out) if last_out else '')
			relieving = emp.get('relieving_date')
			relieving_str = formatdate(relieving, "dd/MM/yyyy") if relieving else ''
			left_checkin_rows += f"""
			<tr style="background:#fff8e1">
				<td class="dc">{idx}</td>
				<td class="d">{emp.get('attendance_device_id') or ''}</td>
				<td class="d">{emp.get('employee_code') or ''}</td>
				<td class="d"><strong>{emp.get('employee_name') or ''}</strong></td>
				<td class="d">{emp.get('department') or ''}</td>
				<td class="d">{emp.get('custom_group') or ''}</td>
				<td class="d">{emp.get('designation') or ''}</td>
				<td class="dc">{relieving_str}</td>
				<td class="dc">{first_in_str}</td>
				<td class="dc">{last_out_str}</td>
				<td class="dc">{emp.get('checkin_count') or 0}</td>
			</tr>"""
	else:
		left_checkin_rows = """
		<tr>
			<td colspan="11" class="empty-row">Không có trường hợp nào</td>
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

			bg = '#fafafa' if idx % 2 == 0 else '#ffffff'
			processed_style = 'color:#1a7a4a;font-weight:700' if manual_checkins else 'color:#999'
			incomplete_checkin_rows += f"""
			<tr style="background:{bg}">
				<td class="dc">{idx}</td>
				<td class="dc">{checkin_date_formatted}</td>
				<td class="d">{emp.get('attendance_device_id') or ''}</td>
				<td class="d">{emp.get('employee_code') or ''}</td>
				<td class="d"><strong>{emp.get('employee_name') or ''}</strong></td>
				<td class="d">{emp.get('department') or ''}</td>
				<td class="d">{emp.get('custom_group') or ''}</td>
				<td class="d">{emp.get('shift') or ''}</td>
				<td class="d">{emp.get('designation') or ''}</td>
				<td class="dc">{first_checkin}</td>
				<td class="dc">{last_checkout}</td>
				<td class="dc">{checkin_count}</td>
				<td class="dc" style="{processed_style}">{manual_checkins or '—'}</td>
				<td class="d">{reason_for_manual}</td>
				<td class="d">{other_reason_for_manual}</td>
			</tr>"""
	else:
		incomplete_checkin_rows = """
		<tr>
			<td colspan="15" class="empty-row">Không có nhân viên chấm công thiếu</td>
		</tr>
		"""

	# Build warning section for Left employees — only if there are any
	left_with_checkins_count = stats.get('left_with_checkins_count', 0)
	if left_with_checkins_count:
		left_warning_section = f"""
	<div style="margin:24px 0 0;border:2px solid #e53935;border-radius:8px;overflow:hidden">
		<div style="background:#e53935;padding:12px 18px;display:flex;align-items:center;gap:10px">
			<span style="font-size:20px">🚨</span>
			<div>
				<div style="color:#fff;font-weight:700;font-size:15px">CẢNH BÁO: Nhân viên đã nghỉ việc vẫn có chấm công ngày {formatted_date}</div>
				<div style="color:rgba(255,255,255,.85);font-size:12px;margin-top:2px">Kiểm tra lại trạng thái nhân viên và dữ liệu chấm công bên dưới</div>
			</div>
		</div>
		<table class="dt" style="margin:0">
			<thead>
				<tr>
					<th class="th-warn" style="width:3%;text-align:center">STT</th>
					<th class="th-warn" style="width:5%">Att ID</th>
					<th class="th-warn" style="width:8%">Employee</th>
					<th class="th-warn" style="width:18%">Employee Name</th>
					<th class="th-warn" style="width:10%">Department</th>
					<th class="th-warn" style="width:8%">Group</th>
					<th class="th-warn" style="width:14%">Designation</th>
					<th class="th-warn" style="width:8%;text-align:center">Ngày nghỉ việc</th>
					<th class="th-warn" style="width:9%;text-align:center">Check-in đầu</th>
					<th class="th-warn" style="width:9%;text-align:center">Check-out cuối</th>
					<th class="th-warn" style="width:5%;text-align:center">Số lần</th>
				</tr>
			</thead>
			<tbody>{left_checkin_rows}</tbody>
		</table>
	</div>"""
	else:
		left_warning_section = ""

	# Build early-checkout table (7 ≤ working_hours < 8, checkout 16:xx, Day shift)
	early_checkout_list = stats.get('early_checkout_list', [])
	early_checkout_count = stats.get('early_checkout_count', 0)
	early_checkout_date = stats.get('early_checkout_date', '')
	early_checkout_date_fmt = formatdate(early_checkout_date, "dd/MM/yyyy") if early_checkout_date else ''

	early_checkout_rows = ""
	if early_checkout_list:
		for idx, emp in enumerate(early_checkout_list, 1):
			bg = '#fafafa' if idx % 2 == 0 else '#ffffff'
			last_co = emp.get('last_checkout')
			last_co_str = last_co.strftime("%H:%M:%S") if last_co and hasattr(last_co, 'strftime') else (str(last_co)[:8] if last_co else '')
			wh = emp.get('working_hours') or 0
			early_checkout_rows += f"""
			<tr style="background:{bg}">
				<td class="dc">{idx}</td>
				<td class="dc">{early_checkout_date_fmt}</td>
				<td class="d">{emp.get('attendance_device_id') or ''}</td>
				<td class="d">{emp.get('employee') or ''}</td>
				<td class="d"><strong>{emp.get('employee_name') or ''}</strong></td>
				<td class="d">{emp.get('department') or ''}</td>
				<td class="d">{emp.get('custom_group') or ''}</td>
				<td class="d">{emp.get('shift') or ''}</td>
				<td class="d">{emp.get('designation') or ''}</td>
				<td class="dc">{last_co_str}</td>
				<td class="dc">{wh:.2f}</td>
			</tr>"""
	else:
		early_checkout_rows = """
		<tr>
			<td colspan="11" class="empty-row">Không có trường hợp nào</td>
		</tr>
		"""

	if early_checkout_count:
		early_checkout_section = f"""
  <div style="margin:24px 0 0;border:2px solid #f57c00;border-radius:8px;overflow:hidden">
    <div style="background:#f57c00;padding:12px 18px;display:flex;align-items:center;gap:10px">
      <span style="font-size:20px">⚠️</span>
      <div>
        <div style="color:#fff;font-weight:700;font-size:15px">Về sớm bất thường — Ca Day ngày {early_checkout_date_fmt} &nbsp;<span style="font-weight:400;font-size:13px">({early_checkout_count} TH)</span></div>
        <div style="color:rgba(255,255,255,.85);font-size:12px;margin-top:2px">Giờ làm 7–8h, checkout 16:xx — Có thể là nhân viên mang thai/nuôi con chưa cập nhật Employee Maternity</div>
      </div>
    </div>
    <table class="dt" style="margin:0">
      <thead><tr>
        <th class="th-warn" style="width:3%;text-align:center">STT</th>
        <th class="th-warn" style="width:5%;text-align:center">Ngày</th>
        <th class="th-warn" style="width:5%">Att ID</th>
        <th class="th-warn" style="width:8%">Employee</th>
        <th class="th-warn" style="width:16%">Employee Name</th>
        <th class="th-warn" style="width:10%">Department</th>
        <th class="th-warn" style="width:8%">Group</th>
        <th class="th-warn" style="width:6%">Shift</th>
        <th class="th-warn" style="width:14%">Designation</th>
        <th class="th-warn" style="width:8%;text-align:center">Check-out cuối</th>
        <th class="th-warn" style="width:7%;text-align:center">Giờ làm</th>
      </tr></thead>
      <tbody>{early_checkout_rows}</tbody>
    </table>
  </div>"""
	else:
		early_checkout_section = ""

	absent_count    = len(stats.get('absent_employees', []))
	maternity_count = stats['maternity_count']
	on_leave_count  = stats['on_leave_count']
	incomplete_count = stats['incomplete_count']
	incomplete_processed = stats['incomplete_processed']
	site_name = get_current_frappe_site_name()

	html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ margin:0; padding:0; background:#f0f2f5; font-family:Arial,sans-serif; font-size:13px; color:#333; }}
  .wrap {{ max-width:1200px; margin:0 auto; background:#fff; }}

  /* ── Header ─────────────────────────────────────────── */
  .hdr {{ background-color:#1b3a6b; background:linear-gradient(135deg,#1b3a6b 0%,#2874a6 100%); padding:22px 28px; }}
  .hdr h1 {{ margin:0; color:#fff !important; font-size:20px; font-weight:700; letter-spacing:.3px; }}
  .hdr p  {{ margin:5px 0 0; color:#d6e8f7 !important; font-size:12px; }}

  /* ── Disclaimer ─────────────────────────────────────── */
  .notice {{ background:#fef9e7; border-left:4px solid #f39c12; padding:9px 18px;
             font-size:12.5px; color:#7d6608; }}

  /* ── Stat cards ─────────────────────────────────────── */
  .stats {{ background:#f4f6f9; padding:16px 20px; border-bottom:1px solid #e0e4ea; }}
  .stats table {{ width:100%; border-collapse:separate; border-spacing:8px; }}
  .card {{ background:#fff; border-radius:8px; padding:12px 10px; text-align:center;
           box-shadow:0 1px 4px rgba(0,0,0,.08); }}
  .card .lbl {{ font-size:10.5px; color:#888; text-transform:uppercase;
                letter-spacing:.4px; margin-bottom:5px; }}
  .card .val {{ font-size:26px; font-weight:800; line-height:1.1; }}
  .c-blue   {{ color:#1f618d; }}
  .c-green  {{ color:#1a7a4a; }}
  .c-red    {{ color:#c0392b; }}
  .c-purple {{ color:#6c3483; }}
  .c-orange {{ color:#ca6f1e; }}
  .c-teal   {{ color:#117a65; }}

  /* ── Section header ──────────────────────────────────── */
  .sec-hdr {{ padding:10px 20px; margin:0; font-size:13.5px; font-weight:700;
              display:flex; align-items:center; gap:7px; }}
  .sec-wrap {{ margin:22px 0 0; border:1px solid #e0e4ea; border-radius:8px; overflow:hidden; }}

  /* ── Data table ──────────────────────────────────────── */
  table.dt {{ width:100%; border-collapse:collapse; }}
  table.dt th {{ padding:8px 10px; font-size:11.5px; font-weight:600;
                 letter-spacing:.2px; text-align:left; }}
  .d  {{ padding:7px 10px; font-size:12.5px; border-bottom:1px solid #f0f0f0;
         vertical-align:middle; }}
  .dc {{ padding:7px 10px; font-size:12.5px; border-bottom:1px solid #f0f0f0;
         vertical-align:middle; text-align:center; }}
  .empty-row {{ padding:14px; text-align:center; color:#aaa; font-style:italic;
                border-bottom:1px solid #f0f0f0; }}

  /* per-section th colours */
  .th-absent   {{ background:#c0392b; color:#fff; }}
  .th-mat      {{ background:#6c3483; color:#fff; }}
  .th-leave    {{ background:#1f618d; color:#fff; }}
  .th-inc      {{ background:#117a65; color:#fff; }}
  .th-warn     {{ background:#b03a2e; color:#fff; }}

  /* per-section sec-hdr colours */
  .sh-absent {{ background:#fdf2f1; border-bottom:3px solid #c0392b; color:#922b21; }}
  .sh-mat    {{ background:#f5eef8; border-bottom:3px solid #6c3483; color:#4a235a; }}
  .sh-leave  {{ background:#eaf2fb; border-bottom:3px solid #1f618d; color:#1a4f7a; }}
  .sh-inc    {{ background:#e8f8f5; border-bottom:3px solid #117a65; color:#0b5345; }}

  /* ── Footer ──────────────────────────────────────────── */
  .ftr {{ background:#f4f6f9; padding:14px 24px; text-align:center;
          color:#aaa; font-size:11.5px; border-top:1px solid #dce1e8; margin-top:24px; }}
</style>
</head>
<body>
<div class="wrap">

  <!-- Header -->
  <div class="hdr" style="background-color:#1b3a6b;background:linear-gradient(135deg,#1b3a6b 0%,#2874a6 100%);padding:22px 28px;">
    <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;letter-spacing:.3px;">📋 Báo cáo Hiện diện / Vắng &nbsp;—&nbsp; {formatted_date}</h1>
    <p style="margin:5px 0 0;color:#d6e8f7;font-size:12px;">Tạo lúc {current_time}{last_data_time_msg}</p>
  </div>

  <!-- Disclaimer -->
  <div class="notice">
    ⚠️ <strong>Lưu ý:</strong> Dữ liệu hiện diện có thể chưa bao gồm nhân viên mới nhận việc trong ngày, nhân viên làm ca 2 — cần kiểm tra lại.
  </div>

  <!-- Stat cards -->
  <div class="stats">
    <table><tr>
      <td><div class="card"><div class="lbl">👥 Tổng Active</div>
          <div class="val c-blue">{stats['total_employees']}</div></div></td>
      <td><div class="card"><div class="lbl">✅ Hiện diện</div>
          <div class="val c-green">{stats['total_present']}</div></div></td>
      <td><div class="card"><div class="lbl">❌ Vắng mặt</div>
          <div class="val c-red">{absent_count}</div></div></td>
      <td><div class="card"><div class="lbl">🤱 Thai sản</div>
          <div class="val c-purple">{maternity_count}</div></div></td>
      <td><div class="card"><div class="lbl">🏖 Nghỉ phép</div>
          <div class="val c-orange">{on_leave_count}</div></div></td>
      <td><div class="card">
          <div class="lbl">⏱ Chấm công thiếu</div>
          <div class="val c-teal">{incomplete_count}</div>
          <div style="font-size:11px;color:#888;margin-top:3px">
            <span style="color:#1a7a4a;font-weight:700">{incomplete_processed}</span> / {incomplete_count} đã xử lý
          </div>
          <div style="font-size:10px;color:#aaa;margin-top:2px">{date_range_formatted}</div>
      </div></td>
    </tr></table>
  </div>

  {left_warning_section}

  <!-- Absent -->
  <div class="sec-wrap">
    <div class="sec-hdr sh-absent">❌ Danh sách vắng mặt &nbsp;<span style="font-weight:400;font-size:12px">({absent_count} người)</span></div>
    <table class="dt">
      <thead><tr>
        <th class="th-absent" style="width:3%;text-align:center">STT</th>
        <th class="th-absent" style="width:6%;text-align:center">Ngày</th>
        <th class="th-absent" style="width:6%">Att ID</th>
        <th class="th-absent" style="width:8%">Employee</th>
        <th class="th-absent" style="width:18%">Employee Name</th>
        <th class="th-absent" style="width:9%">Department</th>
        <th class="th-absent" style="width:8%">Group</th>
        <th class="th-absent" style="width:7%">Shift</th>
        <th class="th-absent" style="width:14%">Designation</th>
        <th class="th-absent" style="width:9%">Leave Type</th>
        <th class="th-absent" style="width:7%;text-align:center">Leave App.</th>
        <th class="th-absent" style="width:7%;text-align:center">Half Day</th>
      </tr></thead>
      <tbody>{absent_rows}</tbody>
    </table>
  </div>

  <!-- Maternity -->
  <div class="sec-wrap">
    <div class="sec-hdr sh-mat">🤱 Nghỉ thai sản &nbsp;<span style="font-weight:400;font-size:12px">({maternity_count} người)</span></div>
    <table class="dt">
      <thead><tr>
        <th class="th-mat" style="width:3%;text-align:center">STT</th>
        <th class="th-mat" style="width:6%;text-align:center">Ngày</th>
        <th class="th-mat" style="width:6%">Att ID</th>
        <th class="th-mat" style="width:8%">Employee</th>
        <th class="th-mat" style="width:18%">Employee Name</th>
        <th class="th-mat" style="width:9%">Department</th>
        <th class="th-mat" style="width:8%">Group</th>
        <th class="th-mat" style="width:7%">Shift</th>
        <th class="th-mat" style="width:14%">Designation</th>
        <th class="th-mat" style="width:9%">Leave Type</th>
        <th class="th-mat" style="width:7%;text-align:center">Leave App.</th>
        <th class="th-mat" style="width:7%;text-align:center">Half Day</th>
      </tr></thead>
      <tbody>{maternity_rows}</tbody>
    </table>
  </div>

  <!-- On Leave -->
  <div class="sec-wrap">
    <div class="sec-hdr sh-leave">🏖 Nghỉ phép &nbsp;<span style="font-weight:400;font-size:12px">({on_leave_count} người)</span></div>
    <table class="dt">
      <thead><tr>
        <th class="th-leave" style="width:3%;text-align:center">STT</th>
        <th class="th-leave" style="width:6%;text-align:center">Ngày</th>
        <th class="th-leave" style="width:6%">Att ID</th>
        <th class="th-leave" style="width:8%">Employee</th>
        <th class="th-leave" style="width:18%">Employee Name</th>
        <th class="th-leave" style="width:9%">Department</th>
        <th class="th-leave" style="width:8%">Group</th>
        <th class="th-leave" style="width:7%">Shift</th>
        <th class="th-leave" style="width:14%">Designation</th>
        <th class="th-leave" style="width:9%">Leave Type</th>
        <th class="th-leave" style="width:7%;text-align:center">Leave App.</th>
        <th class="th-leave" style="width:7%;text-align:center">Half Day</th>
      </tr></thead>
      <tbody>{on_leave_rows}</tbody>
    </table>
  </div>

  <!-- Incomplete check-ins -->
  <div class="sec-wrap">
    <div class="sec-hdr sh-inc">⏱ Chấm công thiếu &nbsp;<span style="font-weight:400;font-size:12px">({incomplete_count} TH &nbsp;·&nbsp; {date_range_formatted})</span></div>
    <table class="dt">
      <thead><tr>
        <th class="th-inc" style="width:3%;text-align:center">STT</th>
        <th class="th-inc" style="width:5%;text-align:center">Ngày</th>
        <th class="th-inc" style="width:5%">Att ID</th>
        <th class="th-inc" style="width:7%">Employee</th>
        <th class="th-inc" style="width:14%">Employee Name</th>
        <th class="th-inc" style="width:8%">Department</th>
        <th class="th-inc" style="width:6%">Group</th>
        <th class="th-inc" style="width:5%">Shift</th>
        <th class="th-inc" style="width:12%">Designation</th>
        <th class="th-inc" style="width:7%;text-align:center">Check-in</th>
        <th class="th-inc" style="width:7%;text-align:center">Check-out</th>
        <th class="th-inc" style="width:4%;text-align:center">Lần</th>
        <th class="th-inc" style="width:6%;text-align:center">Đã xử lý</th>
        <th class="th-inc" style="width:6%">Reason</th>
        <th class="th-inc" style="width:7%">Other Reason</th>
      </tr></thead>
      <tbody>{incomplete_checkin_rows}</tbody>
    </table>
  </div>

  {early_checkout_section}

  <!-- Footer -->
  <div class="ftr">
    Gửi tự động từ <strong>ERPNext</strong> — Site: {site_name} &nbsp;|&nbsp; {current_time}
  </div>

</div>
</body>
</html>"""

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
	all_data.extend(stats.get('maternity_employees', []))
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
		elif emp in stats.get('maternity_employees', []):
			status = 'Maternity Leave'
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
