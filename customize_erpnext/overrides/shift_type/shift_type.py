"""
Shift Type Overrides - Custom get_attendance
Uses the new calculate_working_hours from employee_checkin overrides
"""

import frappe
from itertools import groupby
from datetime import timedelta
from frappe.utils import  cint, create_batch, getdate, get_datetime

from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday
from customize_erpnext.overrides.employee_checkin.employee_checkin import (
	custom_mark_attendance_and_link_log
)
from customize_erpnext.api.employee.employee_utils import (
	check_employee_maternity_status
)

EMPLOYEE_CHUNK_SIZE = 20
SPECIAL_HOUR_FORCE_UPDATE = [8, 23]
@frappe.whitelist()
def get_employee_checkins_name_with_null_shift(from_date: str, to_date: str) -> list[str]:
	"""
	Get names of Employee Checkin records with null shift within a date range

	Args:
		from_date: Start date for the range
		to_date: End date for the range

	Returns:
		List of Employee Checkin names with null shift
	"""
	print(f"🔍 get_employee_checkins_name_with_null_shift: from_date={from_date}, to_date={to_date}")

	checkin_names = frappe.get_all(
		"Employee Checkin",
		filters={
			"time": ["between", [from_date, to_date]],
			"shift": ["is", "not set"],
			"skip_auto_attendance": 0
		},
		pluck="name"
	)

	print(f"   Found {len(checkin_names)} checkins with null shift")
	return checkin_names

@frappe.whitelist()
def update_fields_for_employee_checkins(checkin_names: list[str]):
	"""
	Update the shift-related fields of Employee Checkin records by calling fetch_shift()

	Args:
		checkin_names: List of names of the Employee Checkin records to update
	"""
	if not checkin_names:
		print("   No checkins to update")
		return

	print(f"🔄 update_fields_for_employee_checkins: Updating {len(checkin_names)} checkins")

	updated_count = 0
	for checkin_name in checkin_names:
		try:
			# Get the Employee Checkin document
			checkin_doc = frappe.get_doc("Employee Checkin", checkin_name)

			# Call fetch_shift() to update shift-related fields
			checkin_doc.fetch_shift()

			# Save the document
			checkin_doc.save(ignore_permissions=True)
			updated_count += 1

		except Exception as e:
			frappe.log_error(
				message=f"Error updating checkin {checkin_name}: {str(e)}",
				title="Update Employee Checkin Fields Error"
			)
			print(f"   ❌ Error updating checkin {checkin_name}: {str(e)}")

	frappe.db.commit()
	print(f"   ✅ Successfully updated {updated_count}/{len(checkin_names)} checkins")
	 
@frappe.whitelist()
def custom_get_employee_checkins(self) -> list[dict]:
	"""
	Get employee checkins for auto attendance processing.

	Args:
		called_from: Source of the call - 'ui' or 'hook'. If None, will auto-detect.
	"""
	print(f"custom_get_employee_checkins called for Shift Type: {self.name}") 
	fore_get_logs = False
	# Check if this is a web request (UI) or background job (hook)
	if (hasattr(frappe.local, 'request') and frappe.local.request) or frappe.utils.now_datetime().hour == 8   or frappe.utils.now_datetime().hour == 23:
		# Call from UI or 8h or 23h : process full day checkins
		fore_get_logs = True
	if fore_get_logs:
		end_of_last_sync_of_checkin_day = self.last_sync_of_checkin.replace(
		hour=23,
		minute=59,
		second=59,
		microsecond=999999)
		filters={
			"skip_auto_attendance": 0,
			"time": (">=", self.process_attendance_after), 	
			"shift_actual_end": ("<", end_of_last_sync_of_checkin_day),
			"shift": self.name,
			"offshift": 0,
		}
	else:
		filters={
				"skip_auto_attendance": 0,
				"attendance": ("is", "not set"),
				"time": (">=", self.process_attendance_after),
				"shift_actual_end": ("<", self.last_sync_of_checkin),
				"shift": self.name,
				"offshift": 0,
			}
	print(f"custom_get_employee_checkins called with filters: {filters}")
	return frappe.get_all(
		"Employee Checkin",
		fields=[
			"name",
			"employee",
			"log_type",
			"time",
			"shift",
			"shift_start",
			"shift_end",
			"shift_actual_start",
			"shift_actual_end",
			"device_id",
			"overtime_type",
		],
		filters=filters,
		order_by="employee,time",
	)
@frappe.whitelist()
def custom_update_last_sync_of_checkin():
	"""
	Called from hooks - Updates last_sync_of_checkin for auto attendance shifts

	CRITICAL: Must use shift_end (not current_datetime) to avoid filtering out valid checkins.
	This matches HRMS original logic.
	"""
	from hrms.hr.doctype.shift_type.shift_type import get_actual_shift_end
	from frappe.utils import get_datetime
	
	shifts = frappe.get_all(
		"Shift Type",
		# filters={"enable_auto_attendance": 1, "auto_update_last_sync": 1},
		filters={"enable_auto_attendance": 1},
		fields=["name", "last_sync_of_checkin", "start_time", "end_time"],
	)
	current_datetime = frappe.flags.current_datetime or frappe.utils.now_datetime()
	current_hour = frappe.utils.now_datetime().hour
	is_web_request = hasattr(frappe.local, 'request') and frappe.local.request
	is_special_hour = current_hour in SPECIAL_HOUR_FORCE_UPDATE  # 8AM or 11PM

	fore_update = is_web_request or is_special_hour
	print(f"-----++----custom_update_last_sync_of_checkin : fore_update = {fore_update}")
	for shift in shifts:
		# CRITICAL: Use shift_end, not current_datetime
		# shift_end = shift end time + grace period (e.g., 18:00 for 08:00-17:00 shift)
		shift_end = get_actual_shift_end(shift, current_datetime)

		update_last_sync = None
		if shift.last_sync_of_checkin:
			# Only update if: last_sync < shift_end < current_datetime
			if get_datetime(shift.last_sync_of_checkin) < shift_end < current_datetime:
				update_last_sync = True
		elif shift_end < current_datetime:
			# First time or shift_end has passed
			update_last_sync = True

		if update_last_sync:
			# Set last_sync = shift_end + 1 minute (NOT current_datetime)
			# Example: shift_end = 18:00 → last_sync = 18:01
			# Next run will filter: shift_actual_end < 18:01 ✅ CORRECT
			frappe.db.set_value(
				"Shift Type", shift.name, "last_sync_of_checkin", shift_end + timedelta(minutes=1)
			)
		if fore_update:
			frappe.db.set_value(
				"Shift Type", shift.name, "last_sync_of_checkin", current_datetime
			)		
			print(f"----------------custom_update_last_sync_of_checkin : {shift.name} => {current_datetime}")


def custom_should_mark_attendance(self, employee: str, attendance_date: str) -> bool:
	"""Determines whether attendance should be marked on holidays or not"""
	if self.mark_auto_attendance_on_holidays:
		# no need to check if date is a holiday or not, is_not_joined_or_relieved or not
		# since attendance should be marked on all days
		return True
	
	is_not_joined_or_relieved = frappe.db.exists(
		"Employee",
		{
			"name": employee,
			"status": ["in", ["Left", "Active"]],
			"date_of_joining": [">", attendance_date],
		},
	) or frappe.db.exists(
		"Employee",
		{
			"name": employee,
			"status": ["in", ["Left", "Active"]],
			"relieving_date": ["<", attendance_date],
		},
	)
	holiday_list = self.get_holiday_list(employee)
	if is_holiday(holiday_list, attendance_date) or is_not_joined_or_relieved:
		print(f"custom_should_mark_attendance =>  False for employee={employee} on date={attendance_date} (holiday or not joined/relieved)")
		return False
	print(f"custom_should_mark_attendance =>  True for employee={employee} on date={attendance_date}")
	return True



@frappe.whitelist()
def get_employee_shift(employee, attendance_date):
	"""
	Get employee's shift for the given date

	Args:
		employee: Employee ID
		attendance_date: Date to check

	Returns:
		str: Shift name or None
	"""
	# First check shift assignment
	shift_assignment = frappe.db.get_value(
		"Shift Assignment",
		{
			"employee": employee,
			"start_date": ["<=", attendance_date],
			"docstatus": 1,
			"status": "Active"
		},
		["shift_type", "end_date"],
		as_dict=True,
		order_by="start_date desc"
	)

	if shift_assignment:
		# Check if assignment has end_date and it's before attendance_date
		if shift_assignment.end_date and getdate(shift_assignment.end_date) < getdate(attendance_date):
			return None
		return shift_assignment.shift_type

	# Fallback to employee's default shift
	default_shift = frappe.db.get_value("Employee", employee, "default_shift")
	return default_shift

@frappe.whitelist()
def custom_process_auto_attendance(self, employees=None, days=None):
	"""
	Process auto attendance for shift type

	Args:
		employees: Optional list of employee IDs to process. If None, processes all active employees.
		days: Optional list of dates to process. If None, uses process_attendance_after to last_sync_of_checkin range.
	"""
	if (
		not cint(self.enable_auto_attendance)
		or not self.process_attendance_after
		or not self.last_sync_of_checkin
	):
		print(f"custom_process_auto_attendance => return : enable_auto_attendance={self.enable_auto_attendance}, process_attendance_after={self.process_attendance_after}, last_sync_of_checkin={self.last_sync_of_checkin}")
		return

	# Convert parameters to lists if provided
	if employees and isinstance(employees, str):
		import json
		employees = json.loads(employees)

	# Normalize days parameter to list of date objects
	if days:
		if isinstance(days, str):
			import json
			days = json.loads(days)

		# Convert all items to date objects
		from datetime import date
		normalized_days = []
		for day in days:
			if isinstance(day, str):
				normalized_days.append(frappe.utils.getdate(day))
			elif isinstance(day, date):
				normalized_days.append(day)
		days = normalized_days

	print(f"custom_process_auto_attendance: enable_auto_attendance={self.enable_auto_attendance}, process_attendance_after={self.process_attendance_after}, last_sync_of_checkin={self.last_sync_of_checkin}")
	print(f"custom_process_auto_attendance for Shift Type: {self.name}, employees filter: {employees}, days filter: {days}")

	

	print("\n" + "="*80)
	print("STEP 2: Get employee checkins for attendance processing")
	print("="*80)

	logs = self.get_employee_checkins() # ➡️ call custom_get_employee_checkins

	# Filter logs by employees if specified
	if employees:
		logs = [log for log in logs if log["employee"] in employees]
	print(f"Found {len(logs)} checkin logs for processing after employee filter")	
	group_key = lambda x: (x["employee"], x["shift_start"])  # noqa
	for key, group in groupby(sorted(logs, key=group_key), key=group_key):
		single_shift_logs = list(group)
		attendance_date = key[1].date()
		employee = key[0]

		# Skip if days filter is specified and this date is not in the list
		if days and attendance_date not in days:
			continue

		if not self.should_mark_attendance(employee, attendance_date): # ➡️ call custom_should_mark_attendance
			continue
		custom_mark_attendance_and_link_log(
			single_shift_logs,
			attendance_date,
			self.name # shift_name
		)

	# commit after processing checkin logs to avoid losing progress
	frappe.db.commit()  # nosemgrep

@frappe.whitelist()
def mark_bulk_attendance_absent_maternity_leave(employees=None, days=None):
	"""
	Mark absent or maternity leave attendance for unmarked days
	Automatically determines shift for each employee/date

	Args:
		employees: Optional list of employee IDs. If None, processes all active employees
		days: List of dates to process. Required.

	Returns:
		None - Creates and submits Attendance documents
	"""
	# Debug logging - Log input parameters
	frappe.logger().info("="*80)
	frappe.logger().info("📋 mark_bulk_attendance_absent_maternity_leave called")
	frappe.logger().info(f"   employees type: {type(employees)}")
	frappe.logger().info(f"   employees value: {employees}")
	frappe.logger().info(f"   days type: {type(days)}")
	frappe.logger().info(f"   days value: {days}")

	if employees:
		frappe.logger().info(f"   employees count: {len(employees)}")
		if len(employees) <= 5:
			frappe.logger().info(f"   employees list: {employees}")
		else:
			frappe.logger().info(f"   first 5 employees: {employees[:5]}")
	else:
		frappe.logger().info(f"   employees: None (will fetch all active employees)")

	if days:
		frappe.logger().info(f"   days count: {len(days)}")
		if len(days) <= 5:
			frappe.logger().info(f"   days list: {days}")
		else:
			frappe.logger().info(f"   first 5 days: {days[:5]}")
	frappe.logger().info("="*80)

	if not days:
		# get config of master_shift shift (Day)
		master_shift_config = frappe.get_all('Shift Type',
			fields=["process_attendance_after", "last_sync_of_checkin"],
			filters={"custom_master_shift": 1})
		# days = list day from process_attendance_after to last_sync_of_checkin.day
		if master_shift_config:
			print(f"master_shift_config : {master_shift_config}")
			from datetime import timedelta
			config = master_shift_config[0]
			start_date = getdate(config.process_attendance_after)
			end_date = getdate(config.last_sync_of_checkin)
			days = []
			current_date = start_date
			while current_date <= end_date:
				days.append(current_date)
				current_date += timedelta(days=1)
		else:
			days = []

		if not days:
			frappe.logger().warning("⚠️ mark_bulk_attendance_absent_maternity_leave: No days provided, skipping")
			print(f"⚠️ mark_bulk_attendance_absent_maternity_leave: No days provided, skipping")
			return

	# employees=None is valid (will process all active employees)
	employee_count = len(employees) if employees else "all active"
	print(f"📋 mark_bulk_attendance_absent_maternity_leave: days={len(days)}, employees={employee_count}")

	# Convert days to date objects
	from datetime import date
	days_list = []
	for day in days:
		if isinstance(day, str):
			days_list.append(frappe.utils.getdate(day))
		elif isinstance(day, date):
			days_list.append(day)
		else:
			days_list.append(day)

	# Get employees list
	if employees:
		all_employees = employees
	else:
		# Get employees who are active during the date range
		# Filter criteria:
		# 1. date_of_joining <= max(days) (already joined by end of period)
		# 2. For Active employees: no additional check needed
		# 3. For Left employees: relieving_date >= min(days) (still working during period)
		# This prevents processing employees who:
		# - Left before the date range started
		# - Haven't joined yet by the end of the date range
		from_date = min(days_list)
		to_date = max(days_list)

		all_employees = frappe.db.sql("""
			SELECT name
			FROM `tabEmployee`
			WHERE (date_of_joining IS NULL OR date_of_joining <= %(to_date)s)
			  AND (
				  status = 'Active'
				  OR (status = 'Left' AND (relieving_date IS NULL OR relieving_date >= %(from_date)s))
			  )
			ORDER BY name
		""", {"from_date": from_date, "to_date": to_date}, pluck=True)

	for batch in create_batch(all_employees, EMPLOYEE_CHUNK_SIZE):
		# Collect all attendance docs for this batch
		attendance_docs = []

		for employee in batch:
			# Get existing attendance for these specific days
			existing_attendance = frappe.get_all(
				"Attendance",
				filters={
					"employee": employee,
					"attendance_date": ["in", days_list],
					"docstatus": ["!=", 2]
				},
				pluck="attendance_date"
			)

			# Calculate unmarked days
			unmarked_days = [day for day in days_list if day not in existing_attendance]

			if not unmarked_days:
				continue

			# Filter out days where employee hasn't joined or already left
			# Get employee details once
			emp_details = frappe.db.get_value(
				"Employee",
				employee,
				["date_of_joining", "relieving_date", "status"],
				as_dict=True
			)

			filtered_unmarked_days = []
			for day in unmarked_days:
				# Check if employee has joined
				if emp_details.date_of_joining and getdate(emp_details.date_of_joining) > getdate(day):
					continue

				# Check if employee has left
				if emp_details.status == "Left" and emp_details.relieving_date and getdate(emp_details.relieving_date) < getdate(day):
					continue

				filtered_unmarked_days.append(day)

			if not filtered_unmarked_days:
				continue

			print(f"----marking absent for employee {employee} for {len(filtered_unmarked_days)} days")

			# Prepare attendance docs for each unmarked day
			for date in filtered_unmarked_days:
				# Check maternity status
				maternity_status, custom_maternity_benefit = check_employee_maternity_status(employee, date)

				# Determine attendance status
				status = 'Maternity Leave' if maternity_status == 'Maternity Leave' else 'Absent'

				# Determine shift - check assignment first, then default shift
				from customize_erpnext.api.employee.employee_utils import get_default_shift_of_employee
				shift = get_default_shift_of_employee(employee, date) or 'Day'

				# Create attendance document
				doc_dict = {
					"doctype": "Attendance",
					"employee": employee,
					"attendance_date": get_datetime(date),
					"status": status,
					"shift": shift,
					"custom_maternity_benefit": custom_maternity_benefit
				}
				print(f"doc_dict : {doc_dict}")
				# Insert (but don't submit yet)
				attendance = frappe.get_doc(doc_dict).insert()
				attendance_docs.append(attendance)

		# Batch submit all attendance docs
		print(f"📝 Submitting {len(attendance_docs)} attendance records in batch...")
		for doc in attendance_docs:
			try:
				doc.submit()
			except Exception as e:
				# Log error but continue with other docs
				frappe.log_error(
					message=f"Error submitting attendance for {doc.employee} on {doc.attendance_date}: {str(e)}",
					title="Attendance Submit Error"
				)
				print(f"❌ Failed to submit attendance for {doc.employee} on {doc.attendance_date}: {str(e)}")

		frappe.db.commit()  # nosemgrep
		print(f"✅ Committed {len(attendance_docs)} attendance records")
		frappe.logger().info(f"✅ Batch completed: {len(attendance_docs)} attendance records committed")

	# Final summary log
	frappe.logger().info("="*80)
	frappe.logger().info("✅ mark_bulk_attendance_absent_maternity_leave completed")
	frappe.logger().info("="*80)


# ============================================================================
# CORE ATTENDANCE PROCESSING - Shared Logic
# ============================================================================

def _core_process_attendance_logic(employees, days, from_date, to_date):
	"""
	Core attendance processing logic shared across all execution paths.

	Args:
		employees: List of employee IDs or None for all active employees
		days: List of date objects
		from_date: Start date (date object or string)
		to_date: End date (date object or string)

	Returns:
		dict: Processing statistics including per_shift breakdown
	"""
	import time
	start_time = time.time()

	# Convert dates to strings for SQL queries
	from_date_str = str(from_date) if not isinstance(from_date, str) else from_date
	to_date_str = str(to_date) if not isinstance(to_date, str) else to_date

	# Initialize stats
	stats = {
		"shifts_processed": 0,
		"per_shift": {},
		"total_employees": len(employees) if employees else frappe.db.count("Employee", filters={"status": ("!=", "Inactive")}),
		"total_days": len(days) if days else 1,
		"errors": 0
	}

	# ========================================================================
	# STEP 1: Fix checkins with null shift
	# ========================================================================
	frappe.logger().info(f"📋 Processing attendance: {from_date_str} to {to_date_str}")

	checkin_names = get_employee_checkins_name_with_null_shift(from_date_str, to_date_str)
	if checkin_names:
		update_fields_for_employee_checkins(checkin_names)
		frappe.logger().info(f"Fixed {len(checkin_names)} checkins with null shift")

	# ========================================================================
	# STEP 2: Process auto-enabled shifts
	# ========================================================================
	shift_list = frappe.get_all("Shift Type", filters={"enable_auto_attendance": "1"}, pluck="name")
	frappe.logger().info(f"Processing {len(shift_list)} auto-enabled shifts")

	for shift in shift_list:
		try:
			# Count before
			count_before = frappe.db.count("Attendance", {
				"shift": shift,
				"attendance_date": ["between", [from_date, to_date]]
			})

			# Process attendance for this shift
			doc = frappe.get_cached_doc("Shift Type", shift)
			doc.process_auto_attendance(employees=employees, days=days)

			# Count after
			count_after = frappe.db.count("Attendance", {
				"shift": shift,
				"attendance_date": ["between", [from_date, to_date]]
			})

			stats["shifts_processed"] += 1
			stats["per_shift"][shift] = {
				"before": count_before,
				"after": count_after,
				"new_or_updated": count_after - count_before,
				"records": count_after
			}

		except Exception as e:
			stats["errors"] += 1
			frappe.log_error(message=str(e), title=f"Process Auto Attendance Error - {shift}")
			frappe.logger().error(f"Error processing shift {shift}: {str(e)}")

	# ========================================================================
	# STEP 3: Mark absent/maternity leave
	# ========================================================================
	try:
		mark_bulk_attendance_absent_maternity_leave(employees, days)
		frappe.logger().info("Marked absent/maternity for employees without check-ins")
	except Exception as e:
		stats["errors"] += 1
		frappe.log_error(message=str(e), title="Mark Absent Error")
		frappe.logger().error(f"Error marking absent: {str(e)}")

	# ========================================================================
	# STEP 4: Recount ALL shifts (including non-auto-enabled)
	# ========================================================================
	all_shifts_with_attendance = frappe.db.sql("""
		SELECT shift, COUNT(*) as count
		FROM `tabAttendance`
		WHERE attendance_date BETWEEN %(from_date)s AND %(to_date)s
		AND docstatus < 2
		GROUP BY shift
	""", {"from_date": from_date, "to_date": to_date}, as_dict=True)

	for shift_data in all_shifts_with_attendance:
		shift_name = shift_data.shift
		final_count = shift_data.count

		if shift_name in stats["per_shift"]:
			# Update auto-enabled shift with final count
			before_count = stats["per_shift"][shift_name]["before"]
			stats["per_shift"][shift_name]["after"] = final_count
			stats["per_shift"][shift_name]["new_or_updated"] = final_count - before_count
		else:
			# Add non-auto-enabled shift
			stats["per_shift"][shift_name] = {
				"records": final_count,
				"operations": 0,
				"before": 0,
				"after": final_count,
				"new_or_updated": final_count
			}

	# ========================================================================
	# STEP 5: Calculate final metrics
	# ========================================================================
	processing_time = round(time.time() - start_time, 2)

	total_new_or_updated = sum(shift_data["new_or_updated"] for shift_data in stats["per_shift"].values())
	total_after = sum(shift_data["after"] for shift_data in stats["per_shift"].values())

	# Get unique employees with attendance
	employees_with_attendance = frappe.db.sql("""
		SELECT COUNT(DISTINCT employee)
		FROM `tabAttendance`
		WHERE attendance_date BETWEEN %s AND %s
		AND docstatus < 2
	""", (from_date, to_date))[0][0]

	employees_processed = stats["total_employees"]
	employees_skipped = employees_processed - employees_with_attendance

	# Add to stats
	stats.update({
		"processing_time": processing_time,
		"actual_records": total_new_or_updated,
		"total_records_in_db": total_after,
		"employees_with_attendance": employees_with_attendance,
		"employees_skipped": employees_skipped,
		"records_per_second": round(total_new_or_updated / processing_time, 2) if processing_time > 0 else 0
	})

	frappe.logger().info(f"✅ Completed: {total_new_or_updated} records, {employees_with_attendance}/{employees_processed} employees, {processing_time}s")

	return stats


@frappe.whitelist()
def set_process_attendance_after_and_last_sync_of_checkin_for_all_shifts(process_attendance_after=None, last_sync_of_checkin=None):
	"""
	Set process_attendance_after and last_sync_of_checkin for all shifts with auto attendance enabled

	Args:
		process_attendance_after: Datetime string or None to skip updating this field
		last_sync_of_checkin: Datetime string or None to skip updating this field
	"""
	# Validate inputs - convert empty strings or 'null' to None
	if not process_attendance_after or process_attendance_after == 'null':
		process_attendance_after = None
	if not last_sync_of_checkin or last_sync_of_checkin == 'null':
		last_sync_of_checkin = None

	# If both are None, nothing to update
	if process_attendance_after is None and last_sync_of_checkin is None:
		frappe.msgprint("No valid values provided. Nothing to update.")
		return

	shift_types = frappe.get_all(
		"Shift Type",
		filters={"enable_auto_attendance": 1},
		fields=["name"],
	)

	for shift_type in shift_types:
		update_data = {}

		if process_attendance_after is not None:
			update_data["process_attendance_after"] = process_attendance_after

		if last_sync_of_checkin is not None:
			update_data["last_sync_of_checkin"] = last_sync_of_checkin

		if update_data:
			frappe.db.set_value("Shift Type", shift_type.name, update_data)

	frappe.db.commit()
	frappe.msgprint(f"Updated {len(shift_types)} shift type(s)")

@frappe.whitelist()
def get_process_attendance_after_and_last_sync_of_checkin_of_first_shift():
	# Just get from the first shift type
	first_shift_type = frappe.get_all("Shift Type", filters={"name": "Day"}, fields=["process_attendance_after", "last_sync_of_checkin"])[0]
	print(f"get_process_attendance_after_and_last_sync_of_checkin_of_first_shift: {first_shift_type}")
	return first_shift_type.process_attendance_after, first_shift_type.last_sync_of_checkin	
@frappe.whitelist()
def custom_process_auto_attendance_for_all_shifts(employees=None, days=None):
	"""
	Process auto attendance for all enabled shift types.

	This is the main entry point called by:
	- Console: process_auto_attendance_for_all_shifts()
	- Hook: hourly_long scheduler
	- UI: Bulk Update Attendance button (sequential path)

	Args:
		employees: Optional list of employee IDs (JSON string or list). If None, processes all active employees.
		days: Optional list of dates (JSON string or list). If None, uses default date range.

	Returns:
		dict: Processing results with shift details
	"""
	# Parse parameters
	if employees and isinstance(employees, str):
		import json
		employees = json.loads(employees)

	if days:
		if isinstance(days, str):
			import json
			days = json.loads(days)

		# Normalize to date objects
		from datetime import date
		normalized_days = []
		for day in days:
			if isinstance(day, str):
				normalized_days.append(frappe.utils.getdate(day))
			elif isinstance(day, date):
				normalized_days.append(day)
		days = normalized_days

	# Get date range
	if days and len(days) > 0:
		from_date = min(days)
		to_date = max(days)
	else:
		from_date = frappe.utils.today()
		to_date = frappe.utils.today()

	# Use core processing logic
	stats = _core_process_attendance_logic(employees, days, from_date, to_date)

	# Build result
	result = {
		"success": True,
		"shifts_processed": stats["shifts_processed"],
		"total_employees": stats["total_employees"],
		"employees_with_attendance": stats["employees_with_attendance"],
		"employees_skipped": stats["employees_skipped"],
		"total_days": stats["total_days"],
		"actual_records": stats["actual_records"],
		"total_records_in_db": stats["total_records_in_db"],
		"per_shift": stats["per_shift"],
		"processing_time": stats["processing_time"],
		"records_per_second": stats["records_per_second"],
		"errors": stats["errors"]
	}

	return result


# ============================================================================
# BULK UPDATE ATTENDANCE - Optimized version with backup/restore
# ============================================================================

@frappe.whitelist()
def bulk_update_attendance(from_date, to_date, employees=None, batch_size=100, force_sync=0):
	"""
	Bulk update attendance with auto sync/async detection

	Features:
	- Auto backup/restore shift parameters (safe for hourly jobs)
	- Smart batching for performance
	- Auto-detection: sync for small data, async for large data
	- Same logic as custom_process_auto_attendance_for_all_shifts

	Args:
		from_date: Start date (string)
		to_date: End date (string)
		employees: Optional employee list as JSON string (e.g., '["EMP-001", "EMP-002"]') or None for all
		batch_size: Records per batch (default 100)
		force_sync: Force synchronous processing (default 0)

	Returns:
		Sync: {success: True, result: {...}}
		Async: {success: True, background_job: True, job_id: "..."}
	"""
	import time
	import json
	from datetime import datetime, timedelta

	# Parse employees parameter
	employee_list = None
	if employees:
		if isinstance(employees, str):
			employee_list = json.loads(employees)
		elif isinstance(employees, list):
			employee_list = employees

	# Convert dates
	from_date = frappe.utils.getdate(from_date)
	to_date = frappe.utils.getdate(to_date)

	# Validate dates
	if from_date > to_date:
		frappe.throw("From Date cannot be greater than To Date")

	# Estimate workload
	days_count = (to_date - from_date).days + 1

	if employee_list:
		employees_count = len(employee_list)
	else:
		# Count employees active in date range (same logic as frontend)
		from customize_erpnext.api.employee.employee_utils import get_employees_active_in_date_range
		active_employees = get_employees_active_in_date_range(
			from_date=str(from_date),
			to_date=str(to_date)
		)
		employees_count = len(active_employees) if active_employees else 0

	estimated_records = employees_count * days_count

	print(f"📊 Workload estimation: {employees_count} employees × {days_count} days = {estimated_records} records")

	# Check force_sync flag
	force_sync = frappe.utils.cint(force_sync)

	# Auto-detection threshold (configurable)
	ASYNC_THRESHOLD = frappe.conf.get("bulk_attendance_async_threshold", 1000)

	if estimated_records >= ASYNC_THRESHOLD and not force_sync:
		# Large dataset → Background job
		print(f"🚀 Large dataset detected ({estimated_records} ≥ {ASYNC_THRESHOLD}). Queuing background job...")

		job = frappe.enqueue(
			method='customize_erpnext.overrides.shift_type.shift_type._bulk_update_attendance_worker',
			queue='long',
			timeout=7200,  # 2 hours max
			now=False,
			from_date=str(from_date),
			to_date=str(to_date),
			employees=employee_list,
			batch_size=int(batch_size),
			is_background_job=True,
			job_name=f'Bulk Update Attendance {from_date} to {to_date}',
			enqueue_after_commit=True
		)

		return {
			"success": True,
			"background_job": True,
			"job_id": job.id if hasattr(job, 'id') else 'queued',
			"estimated_records": estimated_records,
			"message": f"Large dataset detected ({estimated_records} records). Processing in background..."
		}
	else:
		# Small dataset OR force_sync → Synchronous processing
		if force_sync:
			print(f"⚡ Force sync enabled. Processing {estimated_records} records synchronously...")
		else:
			print(f"⚡ Small dataset ({estimated_records} < {ASYNC_THRESHOLD}). Processing synchronously...")

		result = _bulk_update_attendance_worker(
			from_date=str(from_date),
			to_date=str(to_date),
			employees=employee_list,
			batch_size=int(batch_size)
		)

		return {
			"success": True,
			"background_job": False,
			"result": result
		}


def _bulk_update_attendance_worker(from_date, to_date, employees=None, batch_size=100, is_background_job=False):
	"""
	Bulk attendance worker with automatic backup/restore of shift parameters.

	This function is called by:
	- UI: Bulk Update Attendance button (large dataset path >300 records)
	- Can run synchronously or as background job

	Args:
		from_date: Start date (string)
		to_date: End date (string)
		employees: Optional employee list
		batch_size: Batch size (currently unused)
		is_background_job: Whether this is running as a background job

	Returns:
		dict: Processing results
	"""
	from datetime import timedelta
	import time
	start_time = time.time()

	frappe.logger().info(f"Bulk update: {from_date} to {to_date}, {len(employees) if employees else 'all'} employees")

	# ========================================================================
	# STEP 1: BACKUP shift parameters
	# ========================================================================
	shift_backups = {}
	shift_list = frappe.get_all("Shift Type",
		filters={"enable_auto_attendance": 1},
		fields=["name", "process_attendance_after", "last_sync_of_checkin"]
	)

	for shift in shift_list:
		shift_backups[shift.name] = {
			"process_attendance_after": shift.process_attendance_after,
			"last_sync_of_checkin": shift.last_sync_of_checkin
		}

	frappe.logger().info(f"Backed up {len(shift_backups)} shifts")

	try:
		# ================================================================
		# STEP 2: SET temporary parameters
		# ================================================================
		temp_process_after = from_date
		temp_last_sync = str(to_date) + " 23:59:59"

		for shift_name in shift_backups.keys():
			frappe.db.set_value("Shift Type", shift_name, {
				"process_attendance_after": temp_process_after,
				"last_sync_of_checkin": temp_last_sync
			}, update_modified=False)

		frappe.db.commit()

		# ================================================================
		# STEP 3: BUILD days list
		# ================================================================
		days = []
		current = frappe.utils.getdate(from_date)
		end = frappe.utils.getdate(to_date)

		while current <= end:
			days.append(current)
			current += timedelta(days=1)

		# ================================================================
		# STEP 4: BUILD employees list
		# ================================================================
		if employees:
			employee_list = employees
		else:
			employee_list = frappe.db.sql("""
				SELECT name
				FROM `tabEmployee`
				WHERE (date_of_joining IS NULL OR date_of_joining <= %(to_date)s)
				  AND (
					  status = 'Active'
					  OR (status = 'Left' AND (relieving_date IS NULL OR relieving_date >= %(from_date)s))
				  )
				ORDER BY name
			""", {"from_date": from_date, "to_date": to_date}, pluck=True)

		frappe.logger().info(f"Processing {len(employee_list)} employees, {len(days)} days")

		# ================================================================
		# STEP 5: USE CORE PROCESSING LOGIC
		# ================================================================
		stats = _core_process_attendance_logic(employee_list, days, from_date, to_date)

		# Calculate additional stats for compatibility
		total_operations = sum(
			shift_data.get("operations", len(employee_list) * len(days))
			for shift_data in stats["per_shift"].values()
		)

		result = {
			"success": True,
			"total_operations": total_operations,
			"actual_records": stats["actual_records"],
			"total_records_in_db": stats["total_records_in_db"],
			"errors": stats["errors"],
			"shifts_processed": stats["shifts_processed"],
			"total_employees": stats["total_employees"],
			"employees_with_attendance": stats["employees_with_attendance"],
			"employees_skipped": stats["employees_skipped"],
			"total_days": stats["total_days"],
			"processing_time": stats["processing_time"],
			"records_per_second": stats["records_per_second"],
			"per_shift": stats["per_shift"]
		}

		frappe.logger().info(f"✅ Completed: {stats['actual_records']} records in {stats['processing_time']}s")

	finally:
		# ====================================================================
		# STEP 6: RESTORE original parameters (ALWAYS execute)
		# ====================================================================
		print("🔙 STEP 6: Restoring original parameters...")

		for shift_name, backup_values in shift_backups.items():
			try:
				frappe.db.set_value("Shift Type", shift_name, {
					"process_attendance_after": backup_values["process_attendance_after"],
					"last_sync_of_checkin": backup_values["last_sync_of_checkin"]
				}, update_modified=False)
			except Exception as e:
				print(f"✗ Error restoring {shift_name}: {str(e)}")
				frappe.log_error(
					message=str(e),
					title=f"Restore Shift Parameters Error - {shift_name}"
				)

		frappe.db.commit()
		print(f"   ✓ Restored parameters for {len(shift_backups)} shifts")

	# If running as background job, publish realtime notification
	if is_background_job:
		frappe.publish_realtime(
			event='bulk_update_attendance_complete',
			message={
				"success": True,
				"operation": "update_attendance",
				"result": result
			},
			user=frappe.session.user
		)
		frappe.logger().info(f"📡 Published realtime notification to user {frappe.session.user}")
		print(f"📡 Published realtime notification to user {frappe.session.user}")

	return result
