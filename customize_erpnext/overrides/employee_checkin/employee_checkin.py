"""
Employee Checkin Overrides - New Algorithm
Implements attendance calculation with:
- Working hours excluding lunch break
- Maternity benefit support
- Overtime from registrations
- Pre-shift, lunch-break, and post-shift OT
"""
import frappe
from frappe.utils import flt, cint, time_diff_in_hours,getdate
from datetime import datetime, time, timedelta
from hrms.hr.doctype.employee_checkin.employee_checkin import (
	update_attendance_in_checkins,handle_attendance_exception
)
from customize_erpnext.api.employee.employee_utils import (
	check_employee_maternity_status
)
# Constants for minimum thresholds
MIN_MINUTES_OT = 15                    # Minimum total OT
MIN_MINUTES_WORKING_HOURS = 10         # Minimum working hours
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

def timedelta_to_time(td):
	"""Convert timedelta to time object

	Args:
		td: timedelta or time object

	Returns:
		time object
	"""
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

	shift_start = datetime.combine(check_in.date(), timedelta_to_time(shift_start_time))
	break_start = datetime.combine(check_in.date(), timedelta_to_time(shift_break_start_time))

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
	afternoon_hours = 0
	break_end = datetime.combine(check_in.date(), timedelta_to_time(shift_end_break_time))
	shift_end = datetime.combine(check_in.date(), timedelta_to_time(shift_end_time))
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

	shift_start = datetime.combine(in_time.date(), timedelta_to_time(shift_type_details["start_time"]))
	shift_end = datetime.combine(in_time.date(), timedelta_to_time(shift_type_details["end_time"]))
	break_start = datetime.combine(in_time.date(), timedelta_to_time(shift_type_details["custom_begin_break_time"]))
	break_end = datetime.combine(in_time.date(), timedelta_to_time(shift_type_details["custom_end_break_time"]))

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
	if shift_type_details["custom_begin_break_time"] != shift_type_details["custom_end_break_time"]:
		if (in_time < break_start and out_time > break_end and
			check_lunch_break_ot_registration(employee, attendance_date, break_start.time(), break_end.time())):
			lunch_break_ot = time_diff_in_hours(break_end, break_start)
			# Apply minimum threshold
			if lunch_break_ot * 60 < MIN_MINUTES_OT:
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
		print(f"custom_mark_attendance_and_link_log for employee {employee} => NO LOGS => return")
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
	# print all parameters
	print(f"custom_create_or_update_attendance called with employee={employee}, attendance_date={attendance_date}, shift={shift}, overtime_type={overtime_type}")
	# Check maternity benefit
	overtime_type = logs[0].get("overtime_type") if logs else None
	late_entry = early_exit = False
	working_hours = 0
	in_time = None
	out_time = None
	maternity_status = None
	maternity_status, custom_maternity_benefit = check_employee_maternity_status(employee, attendance_date) 
	print(f"       maternity_status: {maternity_status},       custom_maternity_benefit: {custom_maternity_benefit}   ")
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
		print("Updating existing attendance:", attendance.name)
		# Update existing attendance
		status = "Present"
		custom_approved_overtime_duration = 0
		# Combine logs from existing attendance and new logs
		current_logs = [attendance.get("in_time"), attendance.get("out_time")]
		combine_logs_times = list({log.time for log in logs}.union({t for t in current_logs if t}))
		combine_logs_times.sort()
		print("Current log times:", current_logs)
		print("New log times:", [log.time for log in logs])
		print("Combined log times:", combine_logs_times)
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
		print("====>>>>>Creating new attendance for employee:", employee, "on date:", attendance_date)
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
