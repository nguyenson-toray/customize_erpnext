"""
Employee Checkin Overrides - New Algorithm
Implements attendance calculation with:
- Working hours excluding lunch break
- Maternity benefit support
- Overtime from registrations
- Pre-shift, lunch-break, and post-shift OT
"""
import frappe
from frappe.utils import flt, cint, time_diff_in_hours, getdate, now_datetime
from datetime import datetime, time, timedelta
from collections import defaultdict
import time as time_module
from hrms.hr.doctype.employee_checkin.employee_checkin import (
	update_attendance_in_checkins,handle_attendance_exception
)
from customize_erpnext.api.employee.employee_utils import (
	check_employee_maternity_status
)
# Constants for minimum thresholds
MIN_MINUTES_OT = 15                    # Minimum total OT
MIN_MINUTES_PRE_SHIFT_OT = 60          # Minimum pre-shift OT



def check_maternity_benefit(employee, attendance_date):
	"""Check if employee has maternity benefit
	- Pregnant: Requires apply_pregnant_benefit = 1 in Maternity Tracking
	- Maternity Leave: Auto benefit
	- Young Child: Auto benefit
	"""
	maternity_records = frappe.db.sql("""
		SELECT type, from_date, to_date, apply_pregnant_benefit
		FROM `tabMaternity Tracking`
		WHERE parent = %(employee)s
		  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
		  AND from_date <= %(date)s
		  AND to_date >= %(date)s
	""", {"employee": employee, "date": attendance_date}, as_dict=1)

	if not maternity_records:
		return False

	for record in maternity_records:
		record_type_lower = record.type.lower() if record.type else ""
		if (record_type_lower == 'young child' or
			record.type in ['Young Child', 'Maternity Leave']):
			return True
		elif record.type == 'Pregnant':
			if record.apply_pregnant_benefit == 1:
				return True

	return False

def timedelta_to_time(td, default=None):
	"""Convert timedelta to time object

	Args:
		td: timedelta or time object (can be None)
		default: default value to return if td is None

	Returns:
		time object or default value
	"""
	if td is None:
		return default
	if isinstance(td, time):
		return td
	elif isinstance(td, timedelta):
		total_seconds = int(td.total_seconds())
		hours = total_seconds // 3600
		minutes = (total_seconds % 3600) // 60
		seconds = total_seconds % 60
		return time(hours, minutes, seconds)
	else:
		raise TypeError(f"Expected time or timedelta, got {type(td)}")


def calculate_morning_hours(check_in, check_out, shift_start_time, shift_break_start_time):
	"""Calculate morning hours (shift_start -> break_start)

	Special case: If check-in before shift start and check-out before lunch break,
	working_hours = check_out - shift_start
	"""
	if not check_in or not check_out:
		return 0

	shift_start_t = timedelta_to_time(shift_start_time)
	break_start_t = timedelta_to_time(shift_break_start_time)
	if not shift_start_t:
		return 0
	# If no break time, use shift end as break start (full morning)
	if not break_start_t:
		break_start_t = shift_start_t

	shift_start = datetime.combine(check_in.date(), shift_start_t)
	break_start = datetime.combine(check_in.date(), break_start_t)

	# Special case: check in before shift and check out before lunch
	if check_in < shift_start and check_out <= break_start:
		if check_out > shift_start:
			return time_diff_in_hours(check_out, shift_start)
		else:
			return 0

	# Normal case
	morning_start = check_in if check_in > shift_start else shift_start
	morning_end = check_out if check_out < break_start else break_start

	if morning_end <= morning_start:
		return 0

	return time_diff_in_hours(morning_end, morning_start)


def calculate_afternoon_hours(check_in, check_out, shift_end_break_time, shift_end_time, has_maternity):
	"""Calculate afternoon hours with maternity benefit

	Maternity benefit: Off 1 hour early but still counted as full hours
	"""
	if not check_in or not check_out:
		return 0

	shift_end_t = timedelta_to_time(shift_end_time)
	break_end_t = timedelta_to_time(shift_end_break_time)
	if not shift_end_t:
		return 0
	# If no break time, use shift end as break end (full afternoon from shift start)
	if not break_end_t:
		break_end_t = shift_end_t

	afternoon_hours = 0
	break_end = datetime.combine(check_in.date(), break_end_t)
	shift_end = datetime.combine(check_in.date(), shift_end_t)
	afternoon_start = check_in if check_in > break_end else break_end

	afternoon_end = check_out if check_out < shift_end else shift_end

	if afternoon_end <= afternoon_start:
		return 0
	afternoon_hours = time_diff_in_hours(afternoon_end, afternoon_start)
	if afternoon_hours > 0 and has_maternity:
		# Add 1 hour for maternity benefit if applicable
		afternoon_hours += 1
	return afternoon_hours


def custom_calculate_working_hours_overtime(employee, attendance_date, in_time, out_time, shift_type_details, has_maternity_benefit=False):
	# Initialize all variables
	total_hours = 0
	actual_overtime_duration = 0
	custom_approved_overtime_duration = 0
	custom_final_overtime_duration = 0
	late_entry = False
	early_exit = False

	# Calculate shift_start and shift_end from start_time and end_time
	shift_start = datetime.combine(in_time.date(), timedelta_to_time(shift_type_details.start_time))
	shift_end = datetime.combine(in_time.date(), timedelta_to_time(shift_type_details.end_time))

	morning_hours = calculate_morning_hours(in_time, out_time, shift_type_details.start_time, shift_type_details.custom_begin_break_time)
	afternoon_hours = calculate_afternoon_hours(in_time, out_time, shift_type_details.custom_end_break_time, shift_type_details.end_time, has_maternity_benefit)
	total_hours = morning_hours + afternoon_hours

	if out_time >= shift_end + timedelta(minutes=cint(shift_type_details.custom_overtime_minutes_threshold)):
		actual_overtime_duration = get_actual_overtime_duration(
			employee,
			attendance_date,
			in_time,
			out_time,
			shift_type_details
		) or 0
		
	else:
		actual_overtime_duration = 0
		
	custom_approved_overtime_duration = get_approved_overtime(employee, attendance_date)
	custom_final_overtime_duration = min(custom_approved_overtime_duration, actual_overtime_duration)
	# Check late entry
	if (
		cint(shift_type_details.enable_late_entry_marking)
		and in_time
		and in_time > shift_start + timedelta(minutes=cint(shift_type_details.late_entry_grace_period))
	):
		late_entry = True

	# Check early exit	
	if (
		cint(shift_type_details.enable_early_exit_marking)
		and out_time
		and out_time < shift_end - timedelta(minutes=cint(shift_type_details.early_exit_grace_period))
	):
		early_exit = True

	return total_hours, late_entry, early_exit, actual_overtime_duration, custom_approved_overtime_duration, custom_final_overtime_duration, shift_type_details.get("overtime_type")			




def get_approved_overtime(employee, attendance_date):
	"""Get approved overtime from Overtime Registration

	Returns:
		float: Total approved overtime hours from submitted registrations
	"""

	# Query submitted overtime registrations (docstatus = 1)
	approved_ot = frappe.db.sql("""
		SELECT SUM(TIMESTAMPDIFF(MINUTE, ord.begin_time, ord.end_time) / 60.0) as total_hours
		FROM `tabOvertime Registration Detail` ord
		JOIN `tabOvertime Registration` or_doc ON ord.parent = or_doc.name
		WHERE ord.employee = %(employee)s
		  AND ord.date = %(date)s
		  AND or_doc.docstatus = 1
	""", {"employee": employee, "date": attendance_date}, as_dict=1)

	return flt(approved_ot[0].total_hours) if approved_ot and approved_ot[0].total_hours else 0


def get_actual_overtime_duration(employee, attendance_date, in_time, out_time, shift_type_details):
	"""Calculate actual overtime

	Overtime = Pre-shift OT + Lunch break OT + Post-shift OT

	Args:
		employee: Employee ID
		attendance_date: Attendance date
		check_in: Check-in datetime
		check_out: Check-out datetime
		shift_config: Shift configuration dict
		has_maternity: Whether employee has maternity benefit

	Returns:
		float: Total actual overtime hours
	"""
	if not in_time or not out_time:
		return 0

	# Get shift times - these are required
	shift_start_time = timedelta_to_time(shift_type_details.get("start_time"))
	shift_end_time = timedelta_to_time(shift_type_details.get("end_time"))
	if not shift_start_time or not shift_end_time:
		return 0

	shift_start = datetime.combine(in_time.date(), shift_start_time)
	shift_end = datetime.combine(in_time.date(), shift_end_time)

	# Get break times - these are optional
	break_start_time = timedelta_to_time(shift_type_details.get("custom_begin_break_time"))
	break_end_time = timedelta_to_time(shift_type_details.get("custom_end_break_time"))
	has_break = break_start_time and break_end_time
	if has_break:
		break_start = datetime.combine(in_time.date(), break_start_time)
		break_end = datetime.combine(in_time.date(), break_end_time)
	else:
		break_start = None
		break_end = None

	# Pre-shift overtime (only if OT registration exists)
	pre_shift_ot = 0
	if in_time < shift_start:
		has_pre_shift_reg = check_pre_shift_ot_registration(
			employee, attendance_date, in_time.time(), shift_start.time()
		)
		if has_pre_shift_reg:
			pre_shift_ot = time_diff_in_hours(shift_start, in_time)
			# Apply minimum threshold
			if pre_shift_ot * 60 < MIN_MINUTES_PRE_SHIFT_OT:
				pre_shift_ot = 0

	# Lunch break overtime (only if shift has lunch break and registration exists)
	lunch_break_ot = 0
	if has_break and break_start_time != break_end_time:
		if (in_time < break_start and out_time > break_end and
			check_lunch_break_ot_registration(employee, attendance_date, break_start.time(), break_end.time())):
				lunch_break_ot = time_diff_in_hours(break_end, break_start)
		else:
			lunch_break_ot = 0

	# Post-shift overtime (adjusted for maternity benefit)
	post_shift_ot = 0
	expected_end = shift_end 
	if out_time > expected_end:
		post_shift_ot = time_diff_in_hours(out_time, expected_end)
		if post_shift_ot < MIN_MINUTES_OT / 60:
			post_shift_ot = 0

	total_ot = pre_shift_ot + lunch_break_ot + post_shift_ot

	# Apply minimum total OT threshold
	if total_ot * 60 < MIN_MINUTES_OT:
		total_ot = 0

	return total_ot


def check_pre_shift_ot_registration(employee, attendance_date, check_in_time, shift_start_time):
	"""Check if pre-shift OT registration exists"""
	registrations = frappe.db.sql("""
		SELECT COUNT(*) as count
		FROM `tabOvertime Registration Detail` ord
		JOIN `tabOvertime Registration` or_doc ON ord.parent = or_doc.name
		WHERE ord.employee = %(employee)s
		  AND ord.date = %(date)s
		  AND or_doc.docstatus = 1
		  AND ord.begin_time <= %(shift_start_time)s
		  AND ord.end_time >= %(check_in_time)s
	""", {
		"employee": employee,
		"date": attendance_date,
		"shift_start_time": shift_start_time,
		"check_in_time": check_in_time
	}, as_dict=1)

	return registrations[0].count > 0 if registrations else False


def check_lunch_break_ot_registration(employee, attendance_date, break_start_time, break_end_time):
	"""Check if lunch break OT registration exists"""
	registrations = frappe.db.sql("""
		SELECT COUNT(*) as count
		FROM `tabOvertime Registration Detail` ord
		JOIN `tabOvertime Registration` or_doc ON ord.parent = or_doc.name
		WHERE ord.employee = %(employee)s
		  AND ord.date = %(date)s
		  AND or_doc.docstatus = 1
		  AND (
			  -- OT registration overlaps with lunch break period
			  (ord.begin_time <= %(break_end)s AND ord.end_time >= %(break_start)s)
		  )
	""", {
		"employee": employee,
		"date": attendance_date,
		"break_start": break_start_time,
		"break_end": break_end_time
	}, as_dict=1)

	return registrations[0].count > 0 if registrations else False

def custom_mark_attendance_and_link_log(
	logs, 
	attendance_date, 
	shift=None, 
):
	"""Creates an attendance and links the attendance to the Employee Checkin.
	Note: If attendance is already present for the given date, the logs are marked as skipped and no exception is thrown.

	:param logs: The List of 'Employee Checkin'.
	:param attendance_status: Attendance status to be marked. One of: (Present, Absent, Half Day, Skip). Note: 'On Leave' is not supported by this function.
	:param attendance_date: Date of the attendance to be created.
	:param working_hours: (optional)Number of working hours for the given date.
	"""
	if not logs or len(logs)==0:
		return
	log_names = [x.name for x in logs]
	employee = logs[0].employee 
	try:
		frappe.db.savepoint("attendance_creation")

		attendance = custom_create_or_update_attendance(
			logs=logs,
			employee=employee,
			attendance_date=attendance_date,
			shift=shift 
		)
		 
		update_attendance_in_checkins(log_names, attendance.name)
		return attendance

	except frappe.ValidationError as e:
		handle_attendance_exception(log_names, e)
		return None
def custom_create_or_update_attendance( 
	logs,
	employee,
	attendance_date,
	shift=None,overtime_type=None
):
	"""Custom create or update attendance with new overtime calculation

	This function is called by HRMS's process_auto_attendance.
	We override it to add our custom overtime fields.

	Note: overtime_type parameter is kept for compatibility with HRMS but not used
	"""
	# Check maternity benefit
	overtime_type = logs[0].get("overtime_type") if logs else None
	late_entry = early_exit = False
	working_hours = 0
	in_time = None
	out_time = None
	maternity_status = None
	maternity_status, custom_maternity_benefit = check_employee_maternity_status(employee, attendance_date)
	attendance = None
	shift_type_details = frappe.db.get_value(
		"Shift Type",
		shift,
		["start_time", "end_time", "custom_begin_break_time", "custom_end_break_time", "custom_standard_working_hours", "overtime_type","custom_overtime_minutes_threshold", "enable_late_entry_marking", "late_entry_grace_period", "enable_early_exit_marking", "early_exit_grace_period"],
		as_dict=True
	)
	# Maternity benefit: reduce shift end_time by 60 minutes
	if custom_maternity_benefit:
		# shift_type_details.end_time is a timedelta object (e.g., timedelta(hours=17) for 17:00)
		shift_type_details.end_time = shift_type_details.end_time - timedelta(hours=1)

	# Initialize status (will be set to "Present" if updating existing attendance)
	status = "Present"

	attendance_update_data = {
		"employee": employee,
		"attendance_date": attendance_date,
		"status": status,
		"shift": shift,
		"custom_maternity_benefit": custom_maternity_benefit,
		"standard_working_hours": shift_type_details.custom_standard_working_hours
		}
	if attendance := get_existing_attendance(employee, attendance_date):
		# Update existing attendance
		status = "Present"
		custom_approved_overtime_duration = 0
		# Combine logs from existing attendance and new logs
		current_logs = [attendance.get("in_time"), attendance.get("out_time")]
		combine_logs_times = list({log.time for log in logs}.union({t for t in current_logs if t}))
		combine_logs_times.sort()
		# Always set in_time to earliest
		in_time = combine_logs_times[0]

		# Only set out_time if we have more than 1 unique log
		if len(combine_logs_times) > 1:
			out_time = combine_logs_times[-1]
		else:
			out_time = None

		# Only calculate working hours if both in_time and out_time exist
		if in_time and out_time:
			working_hours, late_entry, early_exit, actual_overtime_duration, custom_approved_overtime_duration, custom_final_overtime_duration, overtime_type = custom_calculate_working_hours_overtime(
				employee,
				attendance_date,
				in_time,
				out_time,
				shift_type_details,
				custom_maternity_benefit
			)
		else:
			# Only 1 log - set defaults
			working_hours = 0
			late_entry = False
			early_exit = False
			actual_overtime_duration = 0
			custom_approved_overtime_duration = 0
			custom_final_overtime_duration = 0
			overtime_type = None

		# Update attendance
		attendance_update_data.update({
			"status": status,
			"in_time": in_time,
			"out_time": out_time,
			"working_hours": working_hours,
			"late_entry": late_entry,
			"early_exit": early_exit,
			"actual_overtime_duration": actual_overtime_duration,
			"custom_approved_overtime_duration": custom_approved_overtime_duration,
			"custom_final_overtime_duration": custom_final_overtime_duration,
			"overtime_type": overtime_type})
		frappe.db.set_value("Attendance", attendance.name, attendance_update_data)
		return frappe.get_doc("Attendance", attendance.name)
	else:
		# Create new attendance
		attendance = frappe.new_doc("Attendance")
		attendance.employee = employee
		attendance.attendance_date = attendance_date
		attendance.shift = shift
		attendance.custom_maternity_benefit = custom_maternity_benefit

		# Check if we have logs
		if len(logs) == 0:
			attendance.status = "Absent"
		else:
			attendance.status = "Present"
			# Get unique log times and sort
			log_times = sorted(list({log.time for log in logs}))

			# Always set in_time to earliest
			attendance.in_time = log_times[0]

			# Only set out_time if we have more than 1 unique log
			if len(log_times) > 1:
				attendance.out_time = log_times[-1]
				# Calculate working hours only when both in_time and out_time exist
				attendance.total_working_hours, attendance.late_entry, attendance.early_exit, attendance.actual_overtime_duration, attendance.custom_approved_overtime_duration, attendance.custom_final_overtime_duration, attendance.overtime_type = custom_calculate_working_hours_overtime(
					employee,
					attendance_date,
					attendance.in_time,
					attendance.out_time,
					shift_type_details,
					custom_maternity_benefit
				)
			else:
				# Only 1 log - don't set out_time, set defaults
				attendance.out_time = None
				attendance.total_working_hours = 0
				attendance.late_entry = False
				attendance.early_exit = False
				attendance.actual_overtime_duration = 0
				attendance.custom_approved_overtime_duration = 0
				attendance.custom_final_overtime_duration = 0
				attendance.overtime_type = None

		attendance.save()
		attendance.submit()
	return attendance


def get_existing_attendance(employee, attendance_date):
	"""Get existing attendance record """
	attendance_name = frappe.db.exists(
		"Attendance",
		{
			"employee": employee,
			"attendance_date": attendance_date,
		},
	)

	if attendance_name:
		attendance_doc = frappe.get_doc("Attendance", attendance_name)
		return attendance_doc
	return None


def update_employee_checkin(doc, from_hook=True):
	"""Update employee checkin with shift and log_type

	Can be called from:
	- Hook when employee_checkin: on_update, after_insert, after_delete
	- bulk_update_employee_checkin function

	Args:
		doc: Employee Checkin document or name
		from_hook: Whether called from hook (default True)

	Returns:
		Updated document
	"""
	# Load document if name is passed
	if isinstance(doc, str):
		doc = frappe.get_doc("Employee Checkin", doc)

	# Fetch shift using default HRMS method
	try:
		doc.fetch_shift()
	except Exception as e:
		frappe.log_error(f"Error in fetch_shift for {doc.name}", str(e))

	# If shift is None or empty after fetch_shift, set to 'Day' as default
	# This ensures all checkins have a shift assigned even if they fall outside defined shift timings
	if not doc.shift:
		doc.shift = 'Day'
		doc.offshift = 0
		# Add comment to document
		try:
			doc.add_comment("Comment", text="Not found Shift for this checkin, set shift to default: Day")
		except Exception:
			pass

	# Get all checkins for this employee on this date, ordered by time
	checkin_date = getdate(doc.time)
	checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": doc.employee,
			"time": ["between", [f"{checkin_date} 00:00:00", f"{checkin_date} 23:59:59"]],
		},
		fields=["name", "log_type", "time"],
		order_by="time ASC"
	)

	if not checkins:
		return doc

	# Update first check-in of the day to IN
	first_checkin = checkins[0]
	if first_checkin.log_type != "IN":
		frappe.db.set_value("Employee Checkin", first_checkin.name, "log_type", "IN", update_modified=False)
		if first_checkin.name == doc.name:
			doc.log_type = "IN"

	# Update last check-in of the day to OUT (if more than one)
	if len(checkins) > 1:
		last_checkin = checkins[-1]
		if last_checkin.log_type != "OUT":
			frappe.db.set_value("Employee Checkin", last_checkin.name, "log_type", "OUT", update_modified=False)
			if last_checkin.name == doc.name:
				doc.log_type = "OUT"
	else:
		# Only one checkin - set it to IN
		if doc.log_type != "IN":
			frappe.db.set_value("Employee Checkin", doc.name, "log_type", "IN", update_modified=False)
			doc.log_type = "IN"

	# Update shift and offshift fields in database directly
	frappe.db.set_value("Employee Checkin", doc.name, {
		"shift": doc.shift,
		"offshift": doc.offshift
	}, update_modified=False)

	return doc


@frappe.whitelist()
def bulk_update_employee_checkin(from_date=None, to_date=None):
	"""Bulk update employee checkins with shift and log_type - OPTIMIZED

	Args:
		from_date: Start date in yyyy-mm-dd format (optional)
		to_date: End date in yyyy-mm-dd format (optional)

	Usage:
		# Update all checkins
		bulk_update_employee_checkin()

		# Update checkins in date range
		bulk_update_employee_checkin('2024-01-01', '2024-12-31')

	Performance optimizations:
		- Batch size: 500 (vs 100)
		- Pre-group checkins by (employee, date) to avoid repeated queries
		- Use SQL CASE WHEN for bulk updates (single query per batch)
		- Bulk add comments at the end
	"""
	print(f"\n{'='*80}")
	print(f"🔄 BULK UPDATE EMPLOYEE CHECKINS")
	print(f"{'='*80}")
	start_time = time_module.time()

	# Build SQL query with OR condition
	# CRITICAL: Update ALL checkins in date range to ensure correct shift from Shift Assignment
	# This ensures all checkins for same employee-date have same shift
	# Previous logic only updated NULL fields, causing inconsistent shift values
	conditions = ["1=1"]  # Always true - will update all checkins in date range
	params = {}

	# Add date range filter if provided
	if from_date and to_date:
		conditions.append("time BETWEEN %(from_date)s AND %(to_date)s")
		params["from_date"] = f"{from_date} 00:00:00"
		params["to_date"] = f"{to_date} 23:59:59"
	elif from_date:
		conditions.append("time >= %(from_date)s")
		params["from_date"] = f"{from_date} 00:00:00"
	elif to_date:
		conditions.append("time <= %(to_date)s")
		params["to_date"] = f"{to_date} 23:59:59"
	else:
		# If no date range specified, only update checkins with NULL/incomplete fields
		# This prevents updating all historical checkins unnecessarily
		conditions.append("(shift IS NULL OR log_type IS NULL OR offshift = 1 OR shift_start IS NULL OR shift_end IS NULL OR shift_actual_start IS NULL OR shift_actual_end IS NULL)")

	where_clause = " AND ".join(conditions)

	# STEP 1: Get all employee checkins in date range (with all fields for comparison)
	checkins = frappe.db.sql(f"""
		SELECT name, employee, time, shift, log_type, offshift,
			   shift_start, shift_end, shift_actual_start, shift_actual_end
		FROM `tabEmployee Checkin`
		WHERE {where_clause}
		ORDER BY employee, time ASC
	""", params, as_dict=1)

	if not checkins:
		print("   ℹ️  No employee checkins found to update")
		return 0

	print(f"   Found {len(checkins)} employee checkins to update")

	# STEP 2: Pre-group checkins by (employee, date)
	print("   📦 Grouping checkins by employee and date...")
	checkins_by_date = defaultdict(list)

	for checkin in checkins:
		checkin_date = getdate(checkin.time)
		key = (checkin.employee, checkin_date)
		checkins_by_date[key].append(checkin)

	print(f"   Found {len(checkins_by_date)} unique (employee, date) combinations")

	# STEP 2.5: Preload Shift Assignments for all employee-dates
	print("   📦 Preloading Shift Assignments...")

	# Get unique employees and date range
	unique_employees = list(set(checkin.employee for checkin in checkins))
	checkin_dates = [getdate(checkin.time) for checkin in checkins]
	min_date = min(checkin_dates) if checkin_dates else None
	max_date = max(checkin_dates) if checkin_dates else None

	# Load shift assignments for date range
	shift_assignments_by_employee = defaultdict(list)
	if min_date and max_date:
		assignments = frappe.get_all(
			"Shift Assignment",
			filters={
				"employee": ["in", unique_employees],
				"docstatus": 1,
				"status": "Active",
				"start_date": ["<=", max_date]
			},
			fields=["employee", "shift_type", "start_date", "end_date"]
		)
		for assign in assignments:
			shift_assignments_by_employee[assign.employee].append(assign)

	# Load employee default shifts
	employee_defaults = {}
	emp_data = frappe.get_all(
		"Employee",
		filters={"name": ["in", unique_employees]},
		fields=["name", "default_shift"]
	)
	for emp in emp_data:
		employee_defaults[emp.name] = emp.default_shift

	print(f"   ✓ Loaded {len(assignments) if min_date and max_date else 0} shift assignments")

	# Helper function to get shift for employee on date
	def get_employee_shift_for_date(employee, checkin_date):
		"""Get shift for employee on specific date from Shift Assignment or default shift"""
		# Check shift assignments first (priority 1)
		assignments = shift_assignments_by_employee.get(employee, [])
		for assign in assignments:
			if assign.start_date <= checkin_date:
				if not assign.end_date or assign.end_date >= checkin_date:
					if assign.shift_type:  # Ensure shift_type is not None
						return assign.shift_type

		# Fallback to default shift (priority 2)
		default_shift = employee_defaults.get(employee)
		if default_shift:
			return default_shift

		# Final fallback to 'Day' if no shift found (priority 3)
		return 'Day'

	# STEP 3: Process in batches and collect bulk updates
	batch_size = 500
	total_checked = 0
	total_updated = 0
	total_skipped = 0
	total_errors = 0
	bulk_updates = []
	checkins_need_comment = []  # Track checkins that need "set to Day" comment

	print(f"   Processing in batches of {batch_size}...")

	for i in range(0, len(checkins), batch_size):
		batch = checkins[i:i + batch_size]
		batch_num = (i // batch_size) + 1

		for checkin in batch:
			try:
				# Get document (minimal load, no hooks)
				doc = frappe.get_doc("Employee Checkin", checkin.name)
				doc.flags.ignore_hooks = True

				# CRITICAL: Get shift for DATE from Shift Assignment (not from checkin TIME window)
				# This ensures all checkins for same employee-date have same shift
				checkin_date = getdate(doc.time)

				# Get correct shift from Shift Assignment or employee default
				doc.shift = get_employee_shift_for_date(doc.employee, checkin_date)
				doc.offshift = 0
				set_to_day = False

				# Validate shift exists before proceeding
				if not doc.shift:
					frappe.log_error(f"No shift found for employee {doc.employee} on {checkin_date}", "Checkin Update Error")
					doc.shift = 'Day'  # Safe fallback

				# Populate shift timing fields
				try:
					from datetime import datetime, timedelta
					from frappe.utils import get_time

					# Verify shift type exists
					if not frappe.db.exists("Shift Type", doc.shift):
						frappe.log_error(f"Shift Type '{doc.shift}' not found for checkin {doc.name}", "Shift Type Missing")
						doc.shift = 'Day'  # Fallback to Day shift

					# Get shift type configuration
					shift_type = frappe.get_cached_doc("Shift Type", doc.shift)

					# Calculate shift start and end based on shift timings
					# IMPORTANT: Frappe stores Time fields as timedelta, need to convert to time object
					shift_start_time = get_time(shift_type.start_time)
					shift_end_time = get_time(shift_type.end_time)

					# Create shift_start datetime (shift start time on checkin date)
					doc.shift_start = datetime.combine(checkin_date, shift_start_time)

					# Create shift_end datetime (shift end time on checkin date, or next day if overnight)
					doc.shift_end = datetime.combine(checkin_date, shift_end_time)
					if shift_end_time < shift_start_time:
						# Overnight shift
						doc.shift_end += timedelta(days=1)

					# For actual shift timings, add tolerance from shift type
					begin_checkin_before = shift_type.begin_check_in_before_shift_start_time or 0
					allow_checkout_after = shift_type.allow_check_out_after_shift_end_time or 0

					doc.shift_actual_start = doc.shift_start - timedelta(minutes=begin_checkin_before)
					doc.shift_actual_end = doc.shift_end + timedelta(minutes=allow_checkout_after)

				except Exception as e:
					frappe.log_error(f"Error populating shift timing for {doc.name}", str(e))

				# Determine log_type based on position in day
				checkin_date = getdate(doc.time)
				key = (doc.employee, checkin_date)
				day_checkins = checkins_by_date[key]

				# Find position of this checkin in the day
				if len(day_checkins) == 1:
					# Only one checkin - set to IN
					doc.log_type = "IN"
				else:
					# Multiple checkins - first = IN, last = OUT
					if day_checkins[0].name == doc.name:
						doc.log_type = "IN"
					elif day_checkins[-1].name == doc.name:
						doc.log_type = "OUT"
					# Middle checkins keep their current log_type or set to None

				# Check if any field has changed before adding to bulk update
				total_checked += 1
				has_changes = False

				# Compare new values with old values from database
				if doc.shift != checkin.shift:
					has_changes = True
				elif doc.offshift != (checkin.offshift or 0):
					has_changes = True
				elif doc.log_type != checkin.log_type:
					has_changes = True
				elif doc.shift_start != checkin.shift_start:
					has_changes = True
				elif doc.shift_end != checkin.shift_end:
					has_changes = True
				elif doc.shift_actual_start != checkin.shift_actual_start:
					has_changes = True
				elif doc.shift_actual_end != checkin.shift_actual_end:
					has_changes = True

				# Only add to bulk update if there are actual changes
				if has_changes:
					bulk_updates.append({
						'name': doc.name,
						'shift': doc.shift,
						'offshift': doc.offshift,
						'log_type': doc.log_type,
						'shift_start': doc.shift_start,
						'shift_end': doc.shift_end,
						'shift_actual_start': doc.shift_actual_start,
						'shift_actual_end': doc.shift_actual_end
					})

					# Track if need comment
					if set_to_day:
						checkins_need_comment.append(doc.name)

					total_updated += 1
				else:
					total_skipped += 1

			except Exception as e:
				total_errors += 1
				print(f"   ❌ Error processing checkin {checkin.name}: {str(e)}")
				frappe.log_error(f"Error updating checkin {checkin.name}", str(e))

		# STEP 4: Bulk update using SQL CASE WHEN (single query per batch)
		if bulk_updates:
			try:
				names = [u['name'] for u in bulk_updates]

				# Helper function to format datetime values for SQL
				def format_datetime_for_sql(dt_value):
					"""Format datetime value for SQL CASE WHEN"""
					if dt_value is None:
						return 'NULL'
					# Convert datetime to string in SQL format
					from datetime import datetime
					if isinstance(dt_value, datetime):
						# Format as 'YYYY-MM-DD HH:MM:SS'
						return f"'{dt_value.strftime('%Y-%m-%d %H:%M:%S')}'"
					return frappe.db.escape(str(dt_value))

				# Build CASE WHEN clauses for each field
				shift_cases = " ".join([
					f"WHEN '{u['name']}' THEN {frappe.db.escape(u['shift']) if u['shift'] else 'NULL'}"
					for u in bulk_updates
				])
				offshift_cases = " ".join([
					f"WHEN '{u['name']}' THEN {u['offshift']}"
					for u in bulk_updates
				])
				log_type_cases = " ".join([
					f"WHEN '{u['name']}' THEN {frappe.db.escape(u['log_type']) if u['log_type'] else 'NULL'}"
					for u in bulk_updates
				])
				shift_start_cases = " ".join([
					f"WHEN '{u['name']}' THEN {format_datetime_for_sql(u['shift_start'])}"
					for u in bulk_updates
				])
				shift_end_cases = " ".join([
					f"WHEN '{u['name']}' THEN {format_datetime_for_sql(u['shift_end'])}"
					for u in bulk_updates
				])
				shift_actual_start_cases = " ".join([
					f"WHEN '{u['name']}' THEN {format_datetime_for_sql(u['shift_actual_start'])}"
					for u in bulk_updates
				])
				shift_actual_end_cases = " ".join([
					f"WHEN '{u['name']}' THEN {format_datetime_for_sql(u['shift_actual_end'])}"
					for u in bulk_updates
				])

				# Single UPDATE query with CASE WHEN
				frappe.db.sql(f"""
					UPDATE `tabEmployee Checkin`
					SET
						shift = CASE name {shift_cases} END,
						offshift = CASE name {offshift_cases} END,
						log_type = CASE name {log_type_cases} END,
						shift_start = CASE name {shift_start_cases} END,
						shift_end = CASE name {shift_end_cases} END,
						shift_actual_start = CASE name {shift_actual_start_cases} END,
						shift_actual_end = CASE name {shift_actual_end_cases} END,
						modified = NOW(),
						modified_by = %s
					WHERE name IN ({','.join(['%s'] * len(names))})
				""", [frappe.session.user] + names)

				print(f"   ✅ Batch {batch_num} completed: {len(bulk_updates)} records updated")

			except Exception as e:
				print(f"   ❌ SQL Error in batch {batch_num}: {str(e)}")
				frappe.log_error(f"Bulk SQL update error - batch {batch_num}", str(e))

				# Fallback to individual updates
				for update in bulk_updates:
					try:
						frappe.db.set_value(
							"Employee Checkin",
							update['name'],
							{
								'shift': update['shift'],
								'offshift': update['offshift'],
								'log_type': update['log_type'],
								'shift_start': update['shift_start'],
								'shift_end': update['shift_end'],
								'shift_actual_start': update['shift_actual_start'],
								'shift_actual_end': update['shift_actual_end']
							},
							update_modified=True
						)
					except Exception as e2:
						print(f"   ❌ Fallback update failed for {update['name']}: {str(e2)}")

			# Clear bulk_updates for next batch
			bulk_updates = []

		# Commit after each batch
		frappe.db.commit()

	# STEP 5: Bulk add comments for checkins set to 'Day'
	if checkins_need_comment:
		print(f"\n   💬 Adding comments to {len(checkins_need_comment)} checkins set to 'Day'...")
		for checkin_name in checkins_need_comment:
			try:
				doc = frappe.get_doc("Employee Checkin", checkin_name)
				doc.add_comment("Comment", text="Not found Shift for this checkin, set shift to default: Day")
			except Exception:
				pass  # Ignore comment errors
		frappe.db.commit()

	elapsed = time_module.time() - start_time
	print(f"\n{'='*80}")
	print(f"✅ BULK UPDATE COMPLETED")
	print(f"   Total checked: {total_checked}")
	print(f"   Total updated: {total_updated} (records with changes)")
	print(f"   Total skipped: {total_skipped} (no changes needed)")
	print(f"   Errors: {total_errors}")
	print(f"   Time: {elapsed:.2f}s ({total_checked/elapsed:.1f} records/sec)" if elapsed > 0 else "   Time: 0s")
	print(f"{'='*80}\n")

	return total_updated


def update_remaining_checkins_after_delete(doc, method):
	"""
	Update log_type for remaining checkins after a checkin is deleted.

	Called from after_delete hook, this function updates the remaining checkins
	in the same day to ensure first checkin = IN and last checkin = OUT.

	Args:
		doc: Employee Checkin document that was deleted
		method: Hook method name (after_delete)
	"""
	if not doc.employee or not doc.time:
		return

	checkin_date = getdate(doc.time)

	# Get all remaining checkins for this employee on this date
	remaining_checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": doc.employee,
			"time": ["between", [f"{checkin_date} 00:00:00", f"{checkin_date} 23:59:59"]],
		},
		fields=["name", "log_type", "time"],
		order_by="time ASC"
	)

	if not remaining_checkins:
		return

	# Update first checkin to IN
	if remaining_checkins[0].log_type != "IN":
		frappe.db.set_value("Employee Checkin", remaining_checkins[0].name, "log_type", "IN", update_modified=False)

	# Update last checkin to OUT (if more than one)
	if len(remaining_checkins) > 1:
		if remaining_checkins[-1].log_type != "OUT":
			frappe.db.set_value("Employee Checkin", remaining_checkins[-1].name, "log_type", "OUT", update_modified=False)


def update_attendance_on_checkin_delete(doc, method):
	"""
	Update or delete attendance when employee checkin is deleted.

	Logic:
	- If there are remaining checkins: Recalculate attendance from remaining checkins
	- If no remaining checkins: Delete the attendance record

	Args:
		doc: Employee Checkin document being deleted
		method: Hook method name (after_delete)
	"""
	if not doc.employee or not doc.time:
		return

	employee = doc.employee
	checkin_date = getdate(doc.time)
	_recalculate_attendance(employee, checkin_date)


def _recalculate_attendance(employee, checkin_date):
	"""
	Recalculate attendance for employee on specific date using remaining checkins.

	Args:
		employee: Employee ID
		checkin_date: Date to recalculate
	"""
	# Lazy import to avoid circular import
	from customize_erpnext.overrides.shift_type.shift_type_optimized import _core_process_attendance_logic_optimized

	_core_process_attendance_logic_optimized(
		[employee],
		[checkin_date],
		checkin_date,
		checkin_date,
		fore_get_logs=True
	)


def _is_peak_hours():

	"""
	Check if current time is during peak hours when mass checkins occur.

	Peak hours:
	- 07:30 to 07:55 
	- 17:00 to 17:15
	- 19:00 to 19:15

	Returns:
		bool: True if during peak hours, False otherwise
	"""  
	current_time = now_datetime().time()
	hour = current_time.hour
	minute = current_time.minute

	# Morning shift start: 07:30 - 07:55
	if hour == 7 and 30 <= minute <= 55:
		return True 
	
	# Evening shift end: 17:00 - 17:15
	if hour == 17 and minute <= 15:
		return True

	# Night shift end: 19:00 - 19:15
	if hour == 19 and minute <= 15:
		return True

	return False


def update_attendance_on_checkin_insert(doc, method):
	"""
	Recalculate attendance when a new employee checkin is created.
	Skips recalculation during peak hours to avoid system overload.

	Args:
		doc: Employee Checkin document being inserted
		method: Hook method name (after_insert)
	"""
	if not doc.employee or not doc.time:
		return

	# Skip attendance recalculation during peak hours
	if _is_peak_hours():
		return

	employee = doc.employee
	checkin_date = getdate(doc.time)

	_recalculate_attendance(employee, checkin_date)


def update_attendance_on_checkin_update(doc, method):
	"""
	Recalculate attendance when employee checkin is updated.
	Skips recalculation during peak hours to avoid system overload.

	Args:
		doc: Employee Checkin document being updated
		method: Hook method name (on_update)
	"""
	if not doc.employee or not doc.time:
		return

	# Skip attendance recalculation during peak hours
	if _is_peak_hours():
		return

	employee = doc.employee
	checkin_date = getdate(doc.time)

	_recalculate_attendance(employee, checkin_date)


'''
 From bench console:
  # Update all checkins with null shift or log_type
  from customize_erpnext.overrides.employee_checkin.employee_checkin import bulk_update_employee_checkin
  bulk_update_employee_checkin()

  # Update checkins in a date range
  bulk_update_employee_checkin('2025-10-28', '2025-10-28')
'''