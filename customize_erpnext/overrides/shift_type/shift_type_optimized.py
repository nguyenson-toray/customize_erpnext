"""
Shift Type Overrides - OPTIMIZED HYBRID VERSION
Performance improvements for bulk attendance processing

Key Optimizations:
1. Preload all reference data once
2. In-memory lookups instead of repeated DB queries
3. Bulk insert/update operations
4. Increased batch sizes
5. Strategic caching

Expected Performance (30 days × 800 employees = 24,000 records):
- Time: ~30s (vs ~120s)
- Queries: ~500 (vs ~150,000)
- Throughput: ~800 records/sec (vs ~200 records/sec)
"""

import frappe
from itertools import groupby
from datetime import timedelta, date
from frappe.utils import create_batch, getdate
from collections import defaultdict
from typing import Dict, List, Set, Optional, Tuple
import time

# ============================================================================
# CONFIGURATION
# ============================================================================

# Optimized batch sizes
EMPLOYEE_CHUNK_SIZE_OPTIMIZED = 100
BULK_INSERT_BATCH_SIZE = 500  # For bulk_insert operations
CHECKIN_UPDATE_BATCH_SIZE = 1000  # For checkin updates (increased for faster processing)
SPECIAL_HOUR_FORCE_UPDATE = [8, 23] 


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _check_attendance_changes(old_att: Dict, new_att: Dict) -> bool:
	"""
	Check if attendance data has changed.
	Returns True if any relevant field is different, False if no changes.
	"""
	from frappe.utils import flt, get_datetime
	from datetime import datetime

	def normalize_datetime(val):
		"""Normalize datetime to string without microseconds for comparison"""
		if val is None:
			return None
		if isinstance(val, datetime):
			return val.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
		if isinstance(val, str) and val:
			try:
				dt = get_datetime(val)
				return dt.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
			except:
				return val
		return str(val) if val else None

	# Fields to compare (most important fields first for early exit)
	fields_to_compare = [
		('status', None, False),           # (field, default, is_datetime)
		('shift', None, False),
		('in_time', None, True),           # datetime field
		('out_time', None, True),          # datetime field
		('working_hours', 0, False),
		('late_entry', 0, False),
		('early_exit', 0, False),
		('leave_type', None, False),
		('leave_application', None, False),
		('custom_leave_application_abbreviation', None, False),  # Leave abbreviation
		('half_day_status', None, False),
		('custom_maternity_benefit', 0, False),
		('actual_overtime_duration', 0, False),
		('custom_approved_overtime_duration', 0, False),
		('custom_final_overtime_duration', 0, False),
		('overtime_type', None, False),
		('standard_working_hours', 0, False),
	]

	for field, default, is_datetime in fields_to_compare:
		old_val = old_att.get(field, default)
		new_val = new_att.get(field, default)

		# Handle numeric comparisons with tolerance
		if isinstance(old_val, (int, float)) or isinstance(new_val, (int, float)):
			if flt(old_val, 4) != flt(new_val, 4):
				return True
		# Handle datetime comparisons (normalize to ignore microseconds)
		elif is_datetime:
			old_norm = normalize_datetime(old_val)
			new_norm = normalize_datetime(new_val)
			if old_norm != new_norm:
				return True
		# Handle string/other comparisons
		elif old_val != new_val:
			old_str = str(old_val) if old_val else None
			new_str = str(new_val) if new_val else None
			if old_str != new_str:
				return True

	return False


def determine_attendance_status(
	working_hours: float,
	working_hours_threshold_for_absent: float,
	working_hours_threshold_for_half_day: float
) -> str:
	"""
	Determine attendance status based on working hours thresholds.

	This matches the original HRMS logic in ShiftType.get_attendance()
	(shift_type.py:251-260).

	Args:
		working_hours: Total working hours calculated from checkins
		working_hours_threshold_for_absent: Threshold below which status is "Absent"
		working_hours_threshold_for_half_day: Threshold below which status is "Half Day"

	Returns:
		str: "Absent", "Half Day", or "Present"
	"""
	from frappe.utils import flt

	# Match original HRMS logic exactly:
	# 1. Check absent threshold first
	if working_hours_threshold_for_absent and flt(working_hours) < flt(working_hours_threshold_for_absent):
		return "Absent"

	# 2. Check half day threshold
	if working_hours_threshold_for_half_day and flt(working_hours) < flt(working_hours_threshold_for_half_day):
		return "Half Day"

	# 3. Default to Present
	return "Present"


# ============================================================================
# OPTIMIZED DATA PRELOADING
# ============================================================================

def preload_reference_data(employee_list: List[str], from_date: str, to_date: str) -> Dict:
	"""
	Preload ALL reference data needed for processing in a single pass.
	This eliminates thousands of individual queries.

	Returns:
		dict: {
			'employees': {emp_id: {...details}},
			'shifts': {shift_name: {...details}},
			'shift_assignments': {emp_id: [{...assignments}]},
			'holidays': {holiday_list: set(dates)},
			'existing_attendance': {(emp, date): attendance_name}
		}
	"""
	print(f"\n{'='*80}")
	print(f"📦 PRELOADING REFERENCE DATA")
	print(f"{'='*80}")
	start = time.time()

	data = {}

	# 1. Load employee details
	print(f"   Loading {len(employee_list)} employee details...")
	data['employees'] = {}
	emp_data = frappe.get_all(
		"Employee",
		filters={"name": ["in", employee_list]} if employee_list else {},
		fields=[
			"name", "employee_name", "status", "date_of_joining",
			"relieving_date", "default_shift", "holiday_list",
			"department", "company"
		]
	)
	for emp in emp_data:
		data['employees'][emp.name] = emp
	print(f"   ✓ Loaded {len(data['employees'])} employees")

	# 2. Load shift type details
	print(f"   Loading shift type details...")
	data['shifts'] = {}
	shifts = frappe.get_all(
		"Shift Type",
		filters={"enable_auto_attendance": 1},
		fields=[
			"name", "start_time", "end_time", "custom_begin_break_time",
			"custom_end_break_time", "custom_standard_working_hours",
			"overtime_type", "custom_overtime_minutes_threshold",
			"enable_late_entry_marking", "late_entry_grace_period",
			"enable_early_exit_marking", "early_exit_grace_period",
			"mark_auto_attendance_on_holidays", "process_attendance_after",
			"last_sync_of_checkin",
			# CRITICAL: Add threshold fields for status determination (matches original HRMS logic)
			"working_hours_threshold_for_half_day",
			"working_hours_threshold_for_absent"
		]
	)
	for shift in shifts:
		data['shifts'][shift.name] = shift
	print(f"   ✓ Loaded {len(data['shifts'])} shift types")

	# 2b. Load Leave Type abbreviations (for custom_leave_application_abbreviation)
	print(f"   Loading leave type abbreviations...")
	data['leave_type_abbreviations'] = {}
	leave_types = frappe.get_all(
		"Leave Type",
		fields=["name", "custom_abbreviation"]
	)
	for lt in leave_types:
		# Use custom_abbreviation if set, otherwise first 2 chars of name
		abbr = lt.custom_abbreviation if lt.custom_abbreviation else lt.name[:2].upper()
		data['leave_type_abbreviations'][lt.name] = abbr
	print(f"   ✓ Loaded {len(data['leave_type_abbreviations'])} leave type abbreviations")

	# 3. Load shift assignments (for date range)
	print(f"   Loading shift assignments...")
	data['shift_assignments'] = defaultdict(list)
	assignments = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": ["in", employee_list] if employee_list else ["is", "set"],
			"docstatus": 1,
			"status": "Active",
			"start_date": ["<=", to_date]
		},
		fields=["employee", "shift_type", "start_date", "end_date"]
	)
	for assign in assignments:
		data['shift_assignments'][assign.employee].append(assign)
	print(f"   ✓ Loaded {len(assignments)} shift assignments for {len(data['shift_assignments'])} employees")

	# 4. Load holidays (unique holiday lists only)
	print(f"   Loading holiday lists...")
	data['holidays'] = {}
	unique_holiday_lists = set(emp.holiday_list for emp in emp_data if emp.holiday_list)

	if unique_holiday_lists:
		holidays = frappe.get_all(
			"Holiday",
			filters={
				"parent": ["in", list(unique_holiday_lists)],
				"holiday_date": ["between", [from_date, to_date]]
			},
			fields=["parent", "holiday_date"]
		)
		for holiday in holidays:
			if holiday.parent not in data['holidays']:
				data['holidays'][holiday.parent] = set()
			data['holidays'][holiday.parent].add(holiday.holiday_date)
	print(f"   ✓ Loaded {len(unique_holiday_lists)} holiday lists")

	# 5. Load existing attendance (to avoid duplicates)
	print(f"   Loading existing attendance...")
	data['existing_attendance'] = {}
	existing = frappe.get_all(
		"Attendance",
		filters={
			"employee": ["in", employee_list] if employee_list else ["is", "set"],
			"attendance_date": ["between", [from_date, to_date]],
			"docstatus": ["!=", 2]
		},
		# Load ALL fields needed for _check_attendance_changes() comparison
		fields=[
			"name", "employee", "attendance_date", "shift", "status",
			"leave_type", "leave_application", "custom_leave_application_abbreviation",
			"custom_leave_type_2", "custom_leave_application_2",  # Dual leave support
			"half_day_status", "in_time", "out_time", "working_hours", "late_entry", "early_exit",
			"custom_maternity_benefit", "actual_overtime_duration",
			"custom_approved_overtime_duration", "custom_final_overtime_duration",
			"overtime_type", "standard_working_hours"
		]
	)
	for att in existing:
		key = (att.employee, att.attendance_date)
		data['existing_attendance'][key] = att
	print(f"   ✓ Loaded {len(data['existing_attendance'])} existing attendance records")

	# 6. Load maternity tracking (Employee Maternity standalone doctype)
	print(f"   Loading maternity tracking...")
	data['maternity_tracking'] = {}

	try:
		if employee_list:
			maternity_records = frappe.db.sql("""
				SELECT employee, type, from_date, to_date, apply_benefit
				FROM `tabEmployee Maternity`
				WHERE employee IN %(employees)s
				  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
				  AND from_date <= %(to_date)s
				  AND to_date >= %(from_date)s
			""", {
				"employees": employee_list,
				"from_date": from_date,
				"to_date": to_date
			}, as_dict=True)
		else:
			maternity_records = frappe.db.sql("""
				SELECT employee, type, from_date, to_date, apply_benefit
				FROM `tabEmployee Maternity`
				WHERE type IN ('Pregnant', 'Maternity Leave', 'Young Child')
				  AND from_date <= %(to_date)s
				  AND to_date >= %(from_date)s
			""", {
				"from_date": from_date,
				"to_date": to_date
			}, as_dict=True)

		for record in maternity_records:
			if record.employee not in data['maternity_tracking']:
				data['maternity_tracking'][record.employee] = []
			data['maternity_tracking'][record.employee].append(record)

		print(f"   ✓ Loaded {len(maternity_records)} maternity tracking records")
	except Exception as e:
		print(f"   ⚠️  Error loading maternity tracking: {str(e)}")

	# 7. Load Leave Applications (Approved leaves)
	print(f"   Loading approved leave applications...")
	data['leave_applications'] = {}

	# Query approved leaves that overlap with date range
	# Based on HRMS attendance.py:check_leave_record() logic
	if employee_list:
		leave_records = frappe.db.sql("""
			SELECT
				employee,
				leave_type,
				from_date,
				to_date,
				half_day,
				half_day_date,
				name as leave_application
			FROM `tabLeave Application`
			WHERE employee IN %(employees)s
			  AND status = 'Approved'
			  AND docstatus = 1
			  AND from_date <= %(to_date)s
			  AND to_date >= %(from_date)s
		""", {
			"employees": employee_list,
			"from_date": from_date,
			"to_date": to_date
		}, as_dict=True)
	else:
		leave_records = frappe.db.sql("""
			SELECT
				employee,
				leave_type,
				from_date,
				to_date,
				half_day,
				half_day_date,
				name as leave_application
			FROM `tabLeave Application`
			WHERE status = 'Approved'
			  AND docstatus = 1
			  AND from_date <= %(to_date)s
			  AND to_date >= %(from_date)s
		""", {
			"from_date": from_date,
			"to_date": to_date
		}, as_dict=True)

	# Build index: (employee, date) -> leave details
	# Expand each leave record to individual dates
	for record in leave_records:
		current_date = getdate(record.from_date)
		end_date = getdate(record.to_date)

		# Get abbreviation for this leave type
		leave_abbr = data['leave_type_abbreviations'].get(record.leave_type, record.leave_type[:2].upper())

		while current_date <= end_date:
			key = (record.employee, current_date)
			data['leave_applications'][key] = {
				'leave_type': record.leave_type,
				'leave_application': record.leave_application,
				'is_half_day': record.half_day,
				'half_day_date': getdate(record.half_day_date) if record.half_day_date else None,
				'abbreviation': leave_abbr
			}
			current_date = frappe.utils.add_days(current_date, 1)

	print(f"   ✓ Loaded {len(leave_records)} leave applications ({len(data['leave_applications'])} leave-days)")

	elapsed = time.time() - start
	print(f"   ⏱️  Preload completed in {elapsed:.2f}s")
	print(f"{'='*80}\n")

	return data


def check_maternity_status_cached(employee: str, attendance_date: date, ref_data: Dict) -> Tuple[Optional[str], bool]:
	"""
	Check employee maternity status using preloaded data (no DB queries).

	Matches original logic from employee_utils.py:check_employee_maternity_status()

	Args:
		employee: Employee ID
		attendance_date: Date to check
		ref_data: Preloaded reference data

	Returns:
		tuple: (maternity_status, apply_pregnant_benefit)
			- maternity_status: 'Pregnant', 'Maternity Leave', 'Young Child', or None
			- apply_pregnant_benefit: True if should reduce working hours by 1 hour
	"""
	maternity_records = ref_data.get('maternity_tracking', {}).get(employee, [])

	for record in maternity_records:
		# Check if date is within the maternity period
		if record['from_date'] <= attendance_date <= record['to_date']:
			maternity_status = record['type']
			apply_pregnant_benefit = False

			# Logic:
			# - Young Child: always apply benefit (reduce working hours)
			# - Maternity Leave: always apply benefit
			# - Pregnant: only if apply_benefit checkbox is ticked
			if record['type'] in ('Young Child', 'Maternity Leave'):
				apply_pregnant_benefit = True
			elif record['type'] == 'Pregnant' and record.get('apply_benefit'):
				apply_pregnant_benefit = True

			return (maternity_status, apply_pregnant_benefit)

	return (None, False)


def check_leave_status_cached(employee: str, attendance_date: date, ref_data: Dict) -> Optional[Dict]:
	"""
	Check if employee has approved leave on this date using preloaded data (no DB queries).

	Based on HRMS attendance.py:check_leave_record() logic.

	Args:
		employee: Employee ID
		attendance_date: Date to check
		ref_data: Preloaded reference data

	Returns:
		dict: {
			'status': 'On Leave' or 'Half Day',
			'leave_type': leave type name,
			'leave_application': leave application ID,
			'abbreviation': combined abbreviation (e.g., 'P/2' for half day)
		}
		or None if no leave found
	"""
	key = (employee, attendance_date)
	leave_data = ref_data.get('leave_applications', {}).get(key)

	if not leave_data:
		return None

	# Check if it's half day
	if leave_data['is_half_day'] and leave_data['half_day_date'] == attendance_date:
		status = 'Half Day'
		# Half day abbreviation format: "P/2"
		abbreviation = f"{leave_data.get('abbreviation', '')}/2"
	else:
		status = 'On Leave'
		# Full day abbreviation: just the leave type abbreviation
		abbreviation = leave_data.get('abbreviation', '')

	return {
		'status': status,
		'leave_type': leave_data['leave_type'],
		'leave_application': leave_data['leave_application'],
		'abbreviation': abbreviation
	}


def get_employee_shift_cached(
	employee: str,
	attendance_date,
	ref_data: Dict
) -> Optional[str]:
	"""
	Get employee's shift for a date using preloaded data (no DB queries).

	Args:
		employee: Employee ID
		attendance_date: Date to check (date or string)
		ref_data: Preloaded reference data

	Returns:
		str: Shift name or None
	"""
	# Ensure attendance_date is a date object
	if isinstance(attendance_date, str):
		attendance_date = getdate(attendance_date)
	elif hasattr(attendance_date, 'date'):
		# datetime object
		attendance_date = attendance_date.date()

	# Check shift assignments (sorted by start_date desc to prioritize newer assignments)
	assignments = ref_data['shift_assignments'].get(employee, [])
	# Sort by start_date descending (newest first)
	sorted_assignments = sorted(
		assignments,
		key=lambda x: getdate(x.start_date) if isinstance(x.start_date, str) else x.start_date,
		reverse=True
	)

	for assign in sorted_assignments:
		# Ensure dates are comparable
		start_date = getdate(assign.start_date) if isinstance(assign.start_date, str) else assign.start_date
		end_date = getdate(assign.end_date) if assign.end_date and isinstance(assign.end_date, str) else assign.end_date

		if start_date <= attendance_date:
			if not end_date or end_date >= attendance_date:
				return assign.shift_type

	# Fallback to default shift
	emp_data = ref_data['employees'].get(employee)
	return emp_data.default_shift if emp_data else None


def is_holiday_cached(
	employee: str,
	attendance_date: date,
	ref_data: Dict
) -> bool:
	"""
	Check if date is a holiday using preloaded data (no DB queries).

	Args:
		employee: Employee ID
		attendance_date: Date to check
		ref_data: Preloaded reference data

	Returns:
		bool: True if holiday, False otherwise
	"""
	emp_data = ref_data['employees'].get(employee)
	if not emp_data or not emp_data.holiday_list:
		return False

	holiday_dates = ref_data['holidays'].get(emp_data.holiday_list, set())
	return attendance_date in holiday_dates


def should_mark_attendance_cached(
	employee: str,
	attendance_date: date,
	shift_name: str,
	ref_data: Dict
) -> bool:
	"""
	Determine if attendance should be marked (optimized with cache).

	Args:
		employee: Employee ID
		attendance_date: Date to check
		shift_name: Shift type name
		ref_data: Preloaded reference data

	Returns:
		bool: True if should mark, False otherwise
	"""
	# Get shift details
	shift_data = ref_data['shifts'].get(shift_name)
	if shift_data and shift_data.mark_auto_attendance_on_holidays:
		return True

	# Check employee status
	emp_data = ref_data['employees'].get(employee)
	if not emp_data:
		return False

	# Check if employee has joined
	if emp_data.date_of_joining and emp_data.date_of_joining > attendance_date:
		return False

	# Check if employee has left
	if emp_data.status == "Left" and emp_data.relieving_date:
		if emp_data.relieving_date <= attendance_date:
			return False

	# Check holiday
	if is_holiday_cached(employee, attendance_date, ref_data):
		return False

	return True


# ============================================================================
# OPTIMIZED BULK OPERATIONS
# ============================================================================

def bulk_insert_attendance_records(attendance_list: List[Dict], ref_data: Dict) -> int:
	"""
	Bulk insert attendance records using frappe.db.bulk_insert.
	Much faster than individual insert() + submit() calls.

	Args:
		attendance_list: List of attendance dicts to insert
		ref_data: Reference data for validation

	Returns:
		int: Number of records inserted
	"""
	if not attendance_list:
		return 0

	print(f"   📝 Bulk inserting {len(attendance_list)} attendance records...")
	start = time.time()

	inserted = 0
	for batch in create_batch(attendance_list, BULK_INSERT_BATCH_SIZE):
		# Prepare values for bulk insert AND track attendance -> log_names mapping
		values = []
		attendance_to_logs_mapping = []  # Track (att_name, log_names) for linking

		# CRITICAL FIX: Double-check database for existing attendance before insert
		# This prevents race conditions when multiple processes run simultaneously
		batch_employees = list(set(att['employee'] for att in batch))
		batch_dates = list(set(str(att['attendance_date']) for att in batch))

		if batch_employees and batch_dates:
			existing_in_db = frappe.db.sql("""
				SELECT employee, attendance_date
				FROM `tabAttendance`
				WHERE employee IN %(employees)s
				AND attendance_date IN %(dates)s
				AND docstatus < 2
			""", {'employees': batch_employees, 'dates': batch_dates}, as_dict=1)

			# Add to cache to prevent duplicate inserts
			for existing in existing_in_db:
				key = (existing['employee'], existing['attendance_date'])
				if key not in ref_data['existing_attendance']:
					ref_data['existing_attendance'][key] = {'name': 'exists_in_db', 'shift': None}

		for att in batch:
			# Skip if already exists (in cache OR just found in DB)
			key = (att['employee'], att['attendance_date'])
			if key in ref_data['existing_attendance']:
				continue

			# Generate name
			att_name = frappe.generate_hash(length=10)

			values.append((
				att_name,  # name
				att['employee'],  # employee
				att.get('employee_name'),  # employee_name
				str(att['attendance_date']),  # attendance_date (convert date to string)
				att.get('shift', 'Day'),  # shift
				att.get('status', 'Present'),  # status
				att.get('leave_type'),  # leave_type
				att.get('leave_application'),  # leave_application
				att.get('custom_leave_application_abbreviation'),  # custom_leave_application_abbreviation
				att.get('company'),  # company
				att.get('department'),  # department
				att.get('working_hours', 0),  # working_hours
				str(att.get('in_time')) if att.get('in_time') else None,  # in_time
				str(att.get('out_time')) if att.get('out_time') else None,  # out_time
				1 if att.get('late_entry', 0) else 0,  # late_entry
				1 if att.get('early_exit', 0) else 0,  # early_exit
				1 if att.get('custom_maternity_benefit', 0) else 0,  # custom_maternity_benefit
				att.get('actual_overtime_duration', 0),  # actual_overtime_duration
				att.get('custom_approved_overtime_duration', 0),  # custom_approved_overtime_duration
				att.get('custom_final_overtime_duration', 0),  # custom_final_overtime_duration
				att.get('overtime_type'),  # overtime_type
				att.get('standard_working_hours', 0),  # standard_working_hours
				1,  # docstatus (submitted)
				frappe.utils.now(),  # creation
				frappe.utils.now(),  # modified
				frappe.session.user,  # owner
				frappe.session.user  # modified_by
			))

			# CRITICAL: Track mapping for linking checkins to attendance (matches original logic!)
			log_names = att.get('log_names', [])
			if log_names:
				attendance_to_logs_mapping.append((att_name, log_names))

			# Add to cache to prevent duplicates in same run (with shift info for stats)
			ref_data['existing_attendance'][key] = {
				'name': att_name,
				'shift': att.get('shift', 'Day')
			}

		# Bulk insert using executemany
		if values:
			try:
				# Use cursor.executemany for true bulk insert
				sql = """
					INSERT INTO `tabAttendance`
					(name, employee, employee_name, attendance_date, shift, status, leave_type, leave_application,
					 custom_leave_application_abbreviation, company, department, working_hours, in_time, out_time,
					 late_entry, early_exit, custom_maternity_benefit, actual_overtime_duration,
					 custom_approved_overtime_duration, custom_final_overtime_duration,
					 overtime_type, standard_working_hours, docstatus, creation, modified, owner, modified_by)
					VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
				"""

				# Get cursor and use executemany
				cursor = frappe.db._cursor
				cursor.executemany(sql, values)
				inserted += len(values)

				frappe.db.commit()

				# CRITICAL: Link checkins to attendance records (matches original logic!)
				# This updates the 'attendance' field in Employee Checkin records
				if attendance_to_logs_mapping:
					from hrms.hr.doctype.employee_checkin.employee_checkin import update_attendance_in_checkins
					for att_name, log_names in attendance_to_logs_mapping:
						try:
							update_attendance_in_checkins(log_names, att_name)
						except Exception as link_error:
							frappe.log_error(
								message=f"Error linking checkins to attendance {att_name}: {str(link_error)}",
								title="Checkin Linking Error"
							)

			except Exception as e:
				frappe.log_error(
					message=f"Bulk insert error: {str(e)}\nSample value: {values[0] if values else 'N/A'}",
					title="Bulk Attendance Insert Error"
				)
				print(f"   ❌ Bulk insert failed: {str(e)}")

	elapsed = time.time() - start
	print(f"   ✓ Inserted {inserted} records in {elapsed:.2f}s ({inserted/elapsed:.0f} rec/s)")

	return inserted


# ============================================================================
# OPTIMIZED CORE PROCESSING LOGIC
# ============================================================================

def _core_process_attendance_logic_optimized(
	employees: List[str],
	days: List[date],
	from_date: str,
	to_date: str,
	fore_get_logs: bool = None
) -> Dict:
	"""
	OPTIMIZED core attendance processing logic using hybrid approach.

	Key Optimizations:
	1. Preload all reference data once (employees, shifts, holidays, etc.)
	2. Use in-memory lookups instead of DB queries in loops
	3. Bulk insert/update operations
	4. Larger batch sizes
	5. Strategic caching

	Args:
		employees: List of employee IDs
		days: List of dates to process
		from_date: Start date string
		to_date: End date string
		fore_get_logs: Force full day processing (like UI or hook 8h/23h)
						None = auto-detect, True = full day, False = incremental

	Expected Performance:
	- Time: ~30s (vs ~120s)
	- Queries: ~500 (vs ~150,000)
	- Throughput: ~800 rec/s (vs ~200 rec/s)

	Returns:
		dict: Processing statistics
	"""
	print(f"\n{'='*80}")
	print(f"🚀 OPTIMIZED ATTENDANCE PROCESSING")
	print(f"{'='*80}")
	overall_start = time.time()

	# Ensure to_date is a date object (not string)
	if isinstance(to_date, str):
		to_date = frappe.utils.getdate(to_date)

	# if to_date > today(): to_date
	if to_date > date.today():
		to_date = date.today()
	# Auto-detect fore_get_logs if not specified
	# Similar logic to custom_get_employee_checkins
	if fore_get_logs is None:
		# Check if this is a web request (UI) or background job at specific hours (8h or 23h)
		current_datetime = frappe.flags.current_datetime or frappe.utils.now_datetime()
		current_hour = current_datetime.hour
		is_web_request = hasattr(frappe.local, 'request') and frappe.local.request
		is_special_hour = current_hour in SPECIAL_HOUR_FORCE_UPDATE  # 8AM or 11PM

		fore_get_logs = is_web_request or is_special_hour

		if fore_get_logs:
			print(f"   🔍 Mode: FULL DAY (fore_get_logs=True)")
			if is_web_request:
				print(f"      Reason: Web request (UI)")
			else:
				print(f"      Reason: Special hour ({current_hour}:00)")
		else:
			print(f"   🔍 Mode: INCREMENTAL (fore_get_logs=False)")
			print(f"      Reason: Background job at hour {current_hour}")

	stats = {
		"shifts_processed": 0,
		"per_shift": {},
		"total_employees": len(employees) if employees else 0,
		"total_days": len(days) if days else 0,
		"errors": 0
	}

	# Convert dates
	from_date_str = str(from_date) if not isinstance(from_date, str) else from_date
	to_date_str = str(to_date) if not isinstance(to_date, str) else to_date

	# Get employee list if not provided
	if not employees:
		employees = frappe.db.sql("""
			SELECT name
			FROM `tabEmployee`
			WHERE (date_of_joining IS NULL OR date_of_joining <= %(to_date)s)
			  AND (
				  status = 'Active'
				  OR (status = 'Left' AND (relieving_date IS NULL OR relieving_date >= %(from_date)s))
			  )
			ORDER BY name
		""", {"from_date": from_date, "to_date": to_date}, pluck=True)
		stats["total_employees"] = len(employees)

	print(f"   Processing {stats['total_employees']} employees × {stats['total_days']} days")

	# ========================================================================
	# STEP 1: PRELOAD ALL REFERENCE DATA
	# ========================================================================
	ref_data = preload_reference_data(employees, from_date_str, to_date_str)

	# Count records before processing (exclude cancelled docstatus=2)
	count_before = {}
	for shift_name in ref_data['shifts'].keys():
		count_before[shift_name] = frappe.db.count("Attendance", {
			"shift": shift_name,
			"attendance_date": ["between", [from_date, to_date]],
			"docstatus": ["!=", 2]
		})

	# ========================================================================
	# STEP 2: FIX NULL SHIFTS IN CHECKINS (Bulk Operation)
	# ========================================================================
	# Update all checkins with null shift, offshift=1, or null log_type
	from customize_erpnext.overrides.employee_checkin.employee_checkin import bulk_update_employee_checkin
	bulk_update_employee_checkin(from_date_str, to_date_str)

	# ========================================================================
	# STEP 3: PROCESS AUTO-ENABLED SHIFTS (Optimized with Preloaded Data)
	# ========================================================================
	print(f"\n{'='*80}")
	print(f"📊 PROCESSING AUTO-ENABLED SHIFTS")
	print(f"{'='*80}")

	for shift_name, shift_data in ref_data['shifts'].items():
		try:
			print(f"\n   Processing shift: {shift_name}")
			shift_start = time.time()

			# Get all checkins for this shift (single query)
			# Note: shift_actual_end can be None for some checkins, so we filter those separately
			# CRITICAL: Match custom_get_employee_checkins logic:
			# - fore_get_logs=True (UI/special hour): NO attendance filter (get all checkins)
			# - fore_get_logs=False (normal hook): Filter attendance="not set" (only unlinked checkins)
			#
			# CRITICAL FIX: Use from_date parameter instead of shift_data.process_attendance_after
			# When called from hook (single employee, single date), we should only process that date
			# Using process_attendance_after would process ALL dates from that config date
			checkin_filters = {
				"skip_auto_attendance": 0,
				"time": ["between", [f"{from_date_str} 00:00:00", f"{to_date_str} 23:59:59"]],
				"shift": shift_name,
				"offshift": 0,
				"employee": ["in", employees] if employees else ["is", "set"]
			}

			# Add attendance filter for incremental mode only
			if not fore_get_logs:
				checkin_filters["attendance"] = ("is", "not set")

			checkins = frappe.get_all(
				"Employee Checkin",
				filters=checkin_filters,
				fields=[
					"name", "employee", "time", "shift", "shift_start",
					"shift_end", "shift_actual_start", "shift_actual_end"
				],
				order_by="employee, time"
			)

			# Filter checkins with shift_actual_end check (handle None values)
			# Logic similar to custom_get_employee_checkins:
			# - fore_get_logs = True (UI or hook 8h/23h): full day (< end_of_day 23:59:59 of to_date)
			# - fore_get_logs = False (normal hook): incremental (< last_sync_of_checkin)
			if fore_get_logs:
				# Full day mode: filter by end of to_date instead of last_sync
				# CRITICAL: Use to_date (processing range end), not last_sync_of_checkin
				# This allows processing current day even when shift hasn't ended yet
				from datetime import datetime

				# Convert to_date string to datetime at end of day
				to_date_obj = frappe.utils.getdate(to_date)
				end_of_to_date = datetime.combine(to_date_obj, datetime.max.time()).replace(microsecond=999999)

				checkins = [
					c for c in checkins
					if c.shift_actual_end is None or c.shift_actual_end < end_of_to_date
				]
			else:
				# Incremental mode: filter by last_sync (original logic)
				checkins = [
					c for c in checkins
					if c.shift_actual_end is None or c.shift_actual_end < shift_data.last_sync_of_checkin
				]

			# CRITICAL: Filter out checkins with None shift_start (cannot group/sort these)
			checkins = [c for c in checkins if c.shift_start is not None]

			print(f"      Found {len(checkins)} checkins")

			if not checkins:
				# CRITICAL FIX: When fore_get_logs=True and no checkins found,
				# check existing attendance and update to Absent if needed
				if fore_get_logs:
					attendance_to_update = []

					for (employee, att_date), old_att in ref_data['existing_attendance'].items():
						# Only process attendance for this shift
						# Handle case where attendance has no shift (default to employee's default shift)
						old_shift = old_att.get('shift')
						if old_shift and old_shift != shift_name:
							# Has shift but doesn't match → skip
							continue
						elif not old_shift:
							# No shift → use HRMS standard logic (Shift Assignment → Employee.default_shift)
							emp_shift = get_employee_shift_cached(employee, att_date, ref_data)
							if emp_shift != shift_name:
								continue

						# Check if should mark attendance for this employee/date
						if should_mark_attendance_cached(employee, att_date, shift_name, ref_data):
							# No checkins found → Check leave, then mark as Absent if no leave
							emp_data = ref_data['employees'].get(employee, {})
							shift_data = ref_data['shifts'].get(shift_name, {})

							# Step 1: Check maternity status (for custom_maternity_benefit only)
							maternity_status, custom_maternity_benefit = check_maternity_status_cached(employee, att_date, ref_data)

							# Step 2: Check Leave Application (PRIORITY 1)
							# Based on HRMS attendance.py:check_leave_record() logic
							leave_status = check_leave_status_cached(employee, att_date, ref_data)

							# Step 3: Determine attendance status
							if leave_status:
								# Has approved leave → "On Leave" or "Half Day"
								status = leave_status['status']
								leave_type = leave_status['leave_type']
								leave_application = leave_status['leave_application']
								leave_abbreviation = leave_status.get('abbreviation')
							else:
								# No leave, no checkins → "Absent"
								# Note: maternity_status is NOT a valid attendance status
								# It's only used for custom_maternity_benefit field
								status = 'Absent'
								leave_type = None
								leave_application = None
								leave_abbreviation = None

							# Step 4: Handle half_day_status for Half Day leave (per HRMS logic)
							# Per HRMS attendance.py:357 - Default half_day_status = "Absent" for Half Day
							# When employee has NO checkin → half_day_status = "Absent"
							if status == 'Half Day':
								half_day_status = 'Absent'
								modify_half_day_status = 0
							else:
								half_day_status = None
								modify_half_day_status = 0

							# Determine correct shift from Shift Assignment
							correct_shift = get_employee_shift_cached(employee, att_date, ref_data)
							if not correct_shift:
								correct_shift = shift_name  # Fallback to current shift

							absence_data = {
								'employee': employee,
								'attendance_date': att_date,
								'attendance_name': old_att['name'],
								'shift': correct_shift,  # Use correct shift from Shift Assignment
								'status': status,
								'leave_type': leave_type,
								'leave_application': leave_application,
								'custom_leave_application_abbreviation': leave_abbreviation,
								'half_day_status': half_day_status,
								'modify_half_day_status': modify_half_day_status,
								'in_time': None,
								'out_time': None,
								'working_hours': 0,
								'late_entry': 0,
								'early_exit': 0,
								'custom_maternity_benefit': custom_maternity_benefit,
								'actual_overtime_duration': 0,
								'custom_approved_overtime_duration': 0,
								'custom_final_overtime_duration': 0,
								'overtime_type': None,
								'standard_working_hours': shift_data.get('custom_standard_working_hours', 0),
								'log_names': []  # No checkins
							}
							# Check if data has actually changed before adding to update list
							if _check_attendance_changes(old_att, absence_data):
								attendance_to_update.append(absence_data)

					# Update existing attendance records to Absent
					if attendance_to_update:
						print(f"      🔄 Updating {len(attendance_to_update)} existing attendance to Absent (no checkins)")
						for att_data in attendance_to_update:
							try:
								att_name = att_data['attendance_name']

								# Direct SQL update
								frappe.db.sql("""
									UPDATE `tabAttendance`
									SET docstatus = 1,
										shift = %(shift)s,
										status = %(status)s,
										leave_type = %(leave_type)s,
										leave_application = %(leave_application)s,
										custom_leave_application_abbreviation = %(custom_leave_application_abbreviation)s,
										custom_leave_type_2 = %(custom_leave_type_2)s,
										custom_leave_application_2 = %(custom_leave_application_2)s,
										half_day_status = %(half_day_status)s,
										modify_half_day_status = %(modify_half_day_status)s,
										in_time = %(in_time)s,
										out_time = %(out_time)s,
										working_hours = %(working_hours)s,
										late_entry = %(late_entry)s,
										early_exit = %(early_exit)s,
										custom_maternity_benefit = %(custom_maternity_benefit)s,
										actual_overtime_duration = %(actual_overtime_duration)s,
										custom_approved_overtime_duration = %(custom_approved_overtime_duration)s,
										custom_final_overtime_duration = %(custom_final_overtime_duration)s,
										overtime_type = %(overtime_type)s,
										standard_working_hours = %(standard_working_hours)s,
										modified = NOW(),
										modified_by = %(user)s
									WHERE name = %(name)s
								""", {
									'name': att_name,
									'shift': att_data.get('shift'),
									'status': att_data.get('status', 'Absent'),
									'leave_type': att_data.get('leave_type'),
									'leave_application': att_data.get('leave_application'),
									'custom_leave_application_abbreviation': att_data.get('custom_leave_application_abbreviation'),
									'custom_leave_type_2': att_data.get('custom_leave_type_2'),
									'custom_leave_application_2': att_data.get('custom_leave_application_2'),
									'half_day_status': att_data.get('half_day_status'),
									'modify_half_day_status': att_data.get('modify_half_day_status', 0),
									'in_time': att_data.get('in_time'),
									'out_time': att_data.get('out_time'),
									'working_hours': att_data.get('working_hours', 0),
									'late_entry': att_data.get('late_entry', 0),
									'early_exit': att_data.get('early_exit', 0),
									'custom_maternity_benefit': att_data.get('custom_maternity_benefit', 0),
									'actual_overtime_duration': att_data.get('actual_overtime_duration', 0),
									'custom_approved_overtime_duration': att_data.get('custom_approved_overtime_duration', 0),
									'custom_final_overtime_duration': att_data.get('custom_final_overtime_duration', 0),
									'overtime_type': att_data.get('overtime_type'),
									'standard_working_hours': att_data.get('standard_working_hours', 0),
									'user': frappe.session.user
								})

								# Unlink any checkins that were previously linked
								frappe.db.sql(f"""
									UPDATE `tabEmployee Checkin`
									SET attendance = NULL
									WHERE attendance = '{att_name}'
								""")
							except Exception as e:
								print(f"         ⚠️  Failed to update {att_data.get('attendance_name', 'unknown')}: {str(e)}")

						# Commit updates
						frappe.db.commit()
						print(f"      💾 Committed {len(attendance_to_update)} attendance updates to database")

				stats["per_shift"][shift_name] = {
					"before": count_before.get(shift_name, 0),
					"after": count_before.get(shift_name, 0),
					"new_or_updated": 0
				}
				continue

			# Group checkins by (employee, shift_start) - same as original
			attendance_to_create = []
			group_key = lambda x: (x["employee"], x["shift_start"])

			for key, group in groupby(sorted(checkins, key=group_key), key=group_key):
				single_shift_logs = list(group)
				attendance_date = key[1].date() if hasattr(key[1], 'date') else getdate(key[1])
				employee = key[0]

				# Check if should mark using cached data (no DB queries!)
				if not should_mark_attendance_cached(employee, attendance_date, shift_name, ref_data):
					print(f'-----should_mark_attendance_cached => {employee} {attendance_date} {ref_data} = > return')
					continue

				# Get employee metadata from preloaded data
				emp_data = ref_data['employees'].get(employee, {})

				# Check maternity status using cached data (MUST match original logic!)
				maternity_status, custom_maternity_benefit = check_maternity_status_cached(employee, attendance_date, ref_data)

				# Get checkin names for linking to attendance (CRITICAL - matches original logic!)
				log_names = [log.name for log in single_shift_logs]

				# Get shift details for overtime calculation
				shift_data = ref_data['shifts'].get(shift_name, {})

				# Get unique log times
				log_times = sorted(list({log.time for log in single_shift_logs}))
				in_time = log_times[0] if log_times else None
				out_time = log_times[-1] if len(log_times) > 1 else None

				# Calculate working hours and overtime (FULL LOGIC from original)
				if in_time and out_time:
					from customize_erpnext.overrides.employee_checkin.employee_checkin import custom_calculate_working_hours_overtime

					# Get shift type details for calculation
					shift_type_details = frappe._dict({
						'start_time': shift_data.get('start_time'),
						'end_time': shift_data.get('end_time'),
						'custom_begin_break_time': shift_data.get('custom_begin_break_time'),
						'custom_end_break_time': shift_data.get('custom_end_break_time'),
						'custom_standard_working_hours': shift_data.get('custom_standard_working_hours'),
						'overtime_type': shift_data.get('overtime_type'),
						'custom_overtime_minutes_threshold': shift_data.get('custom_overtime_minutes_threshold'),
						'enable_late_entry_marking': shift_data.get('enable_late_entry_marking'),
						'late_entry_grace_period': shift_data.get('late_entry_grace_period'),
						'enable_early_exit_marking': shift_data.get('enable_early_exit_marking'),
						'early_exit_grace_period': shift_data.get('early_exit_grace_period')
					})

					# CRITICAL: Maternity benefit reduces shift end_time by 1 hour (MUST match original logic!)
					if custom_maternity_benefit:
						from datetime import timedelta
						shift_type_details.end_time = shift_type_details.end_time - timedelta(hours=1)

					working_hours, late_entry, early_exit, actual_overtime, approved_overtime, final_overtime, overtime_type = custom_calculate_working_hours_overtime(
						employee,
						attendance_date,
						in_time,
						out_time,
						shift_type_details,
						custom_maternity_benefit
					)
				else:
					# Only 1 log or no logs - set defaults
					working_hours = 0
					late_entry = False
					early_exit = False
					actual_overtime = 0
					approved_overtime = 0
					final_overtime = 0
					overtime_type = None

				# CRITICAL: Determine correct shift from Shift Assignment (priority 1) or default shift (priority 2)
				# Do NOT use shift from checkin, as it may be outdated or incorrect
				correct_shift = get_employee_shift_cached(employee, attendance_date, ref_data)
				if not correct_shift:
					correct_shift = shift_name  # Fallback to checkin shift if no assignment/default

				# CRITICAL: Determine attendance status based on working hours thresholds
				# This matches original HRMS logic in ShiftType.get_attendance()
				if working_hours == 0 and not in_time:
					# No logs at all - should not reach here due to earlier filtering, but just in case
					attendance_status = 'Absent'
				elif working_hours == 0 and in_time and not out_time:
					# Employee has IN but no OUT yet - mark as Present (they showed up)
					# Working hours will be calculated when OUT is recorded
					attendance_status = 'Present'
				else:
					attendance_status = determine_attendance_status(
						working_hours=working_hours,
						working_hours_threshold_for_absent=shift_data.get('working_hours_threshold_for_absent', 0),
						working_hours_threshold_for_half_day=shift_data.get('working_hours_threshold_for_half_day', 0)
					)

				# Prepare attendance record with FULL fields (matches original)
				att_data = {
					'employee': employee,
					'employee_name': emp_data.get('employee_name'),
					'attendance_date': attendance_date,
					'shift': correct_shift,  # Use correct shift from Shift Assignment
					'status': attendance_status,  # Use calculated status based on thresholds
					'company': emp_data.get('company'),
					'department': emp_data.get('department'),
					'working_hours': working_hours,
					'in_time': in_time,
					'out_time': out_time,
					'late_entry': late_entry,
					'early_exit': early_exit,
					'custom_maternity_benefit': custom_maternity_benefit,
					'actual_overtime_duration': actual_overtime,
					'custom_approved_overtime_duration': approved_overtime,
					'custom_final_overtime_duration': final_overtime,
					'overtime_type': overtime_type,
					'standard_working_hours': shift_data.get('custom_standard_working_hours', 0),
					'log_names': log_names  # CRITICAL: For linking checkins to attendance
				}

				attendance_to_create.append(att_data)

			# CRITICAL: When fore_get_logs=True, UPDATE existing attendance instead of cancel
			# This preserves document names, references, and audit trail (matches custom_create_or_update_attendance)
			# Separate into new records (insert) and existing records (update)
			attendance_to_insert = []
			attendance_to_update = []
			updated_keys = set()  # Track which (employee, date) have been updated

			for att_data in attendance_to_create:
				key = (att_data['employee'], att_data['attendance_date'])

				if key in ref_data['existing_attendance']:
					if fore_get_logs:
						# Full day mode: UPDATE existing attendance with new data
						old_att = ref_data['existing_attendance'][key]
						att_data['attendance_name'] = old_att['name']  # Add name for update

						# CRITICAL: Preserve leave_type and leave_application from old attendance
						# This handles Half Day leave case: employee has leave but also checks in
						if old_att.get('leave_type') or old_att.get('leave_application'):
							att_data['leave_type'] = old_att.get('leave_type')
							att_data['leave_application'] = old_att.get('leave_application')

							# Preserve dual leave fields (for 2 separate Half Day LAs on same date)
							if old_att.get('custom_leave_type_2'):
								att_data['custom_leave_type_2'] = old_att.get('custom_leave_type_2')
							if old_att.get('custom_leave_application_2'):
								att_data['custom_leave_application_2'] = old_att.get('custom_leave_application_2')

							# Calculate abbreviation if not already set
							if old_att.get('custom_leave_application_abbreviation'):
								att_data['custom_leave_application_abbreviation'] = old_att.get('custom_leave_application_abbreviation')
							elif old_att.get('leave_type'):
								# Calculate abbreviation from leave type
								leave_abbr = ref_data.get('leave_type_abbreviations', {}).get(
									old_att.get('leave_type'),
									old_att.get('leave_type', '')[:2].upper()
								)
								if old_att.get('status') == 'Half Day':
									att_data['custom_leave_application_abbreviation'] = f"{leave_abbr}/2"
								else:
									att_data['custom_leave_application_abbreviation'] = leave_abbr

							# Status logic based on leave type and checkin:
							# - Half Day leave → always "Half Day"
							# - Full Day leave (On Leave) + has checkin → "Present"
							# - Full Day leave (On Leave) + no checkin → "On Leave"
							has_checkin = att_data.get('working_hours', 0) > 0 or att_data.get('in_time')

							if old_att.get('status') == 'Half Day':
								# Half Day leave: always preserve "Half Day"
								att_data['status'] = 'Half Day'
								# When employee has checkin on Half Day → half_day_status = "Present"
								if has_checkin:
									att_data['half_day_status'] = 'Present'
									att_data['modify_half_day_status'] = 1
							elif old_att.get('status') == 'On Leave':
								# Full Day leave: status depends on checkin
								if has_checkin:
									att_data['status'] = 'Present'  # Has checkin → Present
								else:
									att_data['status'] = 'On Leave'  # No checkin → On Leave

						# CHECK IF DATA HAS CHANGED before adding to update list
						has_changes = _check_attendance_changes(old_att, att_data)
						if has_changes:
							attendance_to_update.append(att_data)
							updated_keys.add(key)  # Mark as updated
						else:
							# No changes, but still mark as processed
							updated_keys.add(key)
					# else: Incremental mode already filtered by attendance="not set", shouldn't reach here
				else:
					# New attendance - will be inserted
					attendance_to_insert.append(att_data)

			# CRITICAL FIX: When fore_get_logs=True, if attendance exists but has NO checkins,
			# it should be updated to Absent (checkins were deleted)
			if fore_get_logs:
				for (employee, att_date), old_att in ref_data['existing_attendance'].items():
					key = (employee, att_date)
					# Only process attendance for this shift
					# Handle case where attendance has no shift (default to employee's default shift)
					old_shift = old_att.get('shift')
					if old_shift and old_shift != shift_name:
						# Has shift but doesn't match → skip
						continue
					elif not old_shift:
						# No shift → use HRMS standard logic (Shift Assignment → Employee.default_shift)
						emp_shift = get_employee_shift_cached(employee, att_date, ref_data)
						if emp_shift != shift_name:
							continue

					# If attendance exists but was NOT updated (no checkins found), mark as Absent
					if key not in updated_keys:
						# Check if should mark attendance for this employee/date
						if should_mark_attendance_cached(employee, att_date, shift_name, ref_data):
							# No checkins found → Check leave, then mark as Absent if no leave
							emp_data = ref_data['employees'].get(employee, {})
							shift_data = ref_data['shifts'].get(shift_name, {})

							# Step 1: Check maternity status (for custom_maternity_benefit only)
							maternity_status, custom_maternity_benefit = check_maternity_status_cached(employee, att_date, ref_data)

							# Step 2: Check Leave Application (PRIORITY 1)
							# Based on HRMS attendance.py:check_leave_record() logic
							leave_status = check_leave_status_cached(employee, att_date, ref_data)

							# Step 3: Determine attendance status
							if leave_status:
								# Has approved leave → "On Leave" or "Half Day"
								status = leave_status['status']
								leave_type = leave_status['leave_type']
								leave_application = leave_status['leave_application']
								leave_abbreviation = leave_status.get('abbreviation')
							else:
								# No leave, no checkins → "Absent"
								# Note: maternity_status is NOT a valid attendance status
								# It's only used for custom_maternity_benefit field
								status = 'Absent'
								leave_type = None
								leave_application = None
								leave_abbreviation = None

							# Step 4: Handle half_day_status for Half Day leave (per HRMS logic)
							# Per HRMS attendance.py:357 - Default half_day_status = "Absent" for Half Day
							# When employee has NO checkin → half_day_status = "Absent"
							if status == 'Half Day':
								half_day_status = 'Absent'
								modify_half_day_status = 0
							else:
								half_day_status = None
								modify_half_day_status = 0

							# Determine correct shift from Shift Assignment
							correct_shift = get_employee_shift_cached(employee, att_date, ref_data)
							if not correct_shift:
								correct_shift = shift_name  # Fallback to current shift

							absence_data = {
								'employee': employee,
								'attendance_date': att_date,
								'attendance_name': old_att['name'],
								'shift': correct_shift,  # Use correct shift from Shift Assignment
								'status': status,
								'leave_type': leave_type,
								'leave_application': leave_application,
								'custom_leave_application_abbreviation': leave_abbreviation,
								'half_day_status': half_day_status,
								'modify_half_day_status': modify_half_day_status,
								'in_time': None,
								'out_time': None,
								'working_hours': 0,
								'late_entry': 0,
								'early_exit': 0,
								'custom_maternity_benefit': custom_maternity_benefit,
								'actual_overtime_duration': 0,
								'custom_approved_overtime_duration': 0,
								'custom_final_overtime_duration': 0,
								'overtime_type': None,
								'standard_working_hours': shift_data.get('custom_standard_working_hours', 0),
								'log_names': []  # No checkins
							}
							# Check if data has actually changed before adding to update list
							if _check_attendance_changes(old_att, absence_data):
								attendance_to_update.append(absence_data)
							updated_keys.add(key)

			# Update existing attendance records (fore_get_logs=True only)
			# CRITICAL: Must RECALCULATE from ALL checkins (matches custom_create_or_update_attendance)
			if attendance_to_update:
				print(f"      🔄 Updating {len(attendance_to_update)} existing attendance records")
				for att_data in attendance_to_update:
					try:
						# NOTE: All items in attendance_to_update are pre-filtered by _check_attendance_changes()
						# so we know they have actual changes. No need to check again here.

						# Update using SQL (faster, avoids "Cannot edit cancelled document" issue)
						# Must cancel first, then update all fields, then resubmit in single operation
						att_name = att_data['attendance_name']

						# CRITICAL: Ensure correct shift from Shift Assignment is used
						correct_shift = att_data.get('shift')  # Already set from get_employee_shift_cached above

						# Build update query with all fields at once
						update_data = {
							"docstatus": 1,  # Keep submitted (or set to 1 if cancelled)
							"shift": correct_shift,  # Use correct shift from Shift Assignment
							"status": att_data.get('status', 'Present'),
							"leave_type": att_data.get('leave_type'),
							"leave_application": att_data.get('leave_application'),
							"custom_leave_application_abbreviation": att_data.get('custom_leave_application_abbreviation'),
							"custom_leave_type_2": att_data.get('custom_leave_type_2'),
							"custom_leave_application_2": att_data.get('custom_leave_application_2'),
							"half_day_status": att_data.get('half_day_status'),
							"modify_half_day_status": att_data.get('modify_half_day_status', 0),
							"in_time": att_data.get('in_time'),
							"out_time": att_data.get('out_time'),
							"working_hours": att_data.get('working_hours', 0),
							"late_entry": att_data.get('late_entry', 0),
							"early_exit": att_data.get('early_exit', 0),
							"custom_maternity_benefit": att_data.get('custom_maternity_benefit', 0),
							"actual_overtime_duration": att_data.get('actual_overtime_duration', 0),
							"custom_approved_overtime_duration": att_data.get('custom_approved_overtime_duration', 0),
							"custom_final_overtime_duration": att_data.get('custom_final_overtime_duration', 0),
							"overtime_type": att_data.get('overtime_type'),
							"standard_working_hours": att_data.get('standard_working_hours', 0)
						}

						# Direct SQL update (bypass validation, faster)
						frappe.db.sql("""
							UPDATE `tabAttendance`
							SET docstatus = %(docstatus)s,
								shift = %(shift)s,
								status = %(status)s,
								leave_type = %(leave_type)s,
								leave_application = %(leave_application)s,
								custom_leave_application_abbreviation = %(custom_leave_application_abbreviation)s,
								custom_leave_type_2 = %(custom_leave_type_2)s,
								custom_leave_application_2 = %(custom_leave_application_2)s,
								half_day_status = %(half_day_status)s,
								modify_half_day_status = %(modify_half_day_status)s,
								in_time = %(in_time)s,
								out_time = %(out_time)s,
								working_hours = %(working_hours)s,
								late_entry = %(late_entry)s,
								early_exit = %(early_exit)s,
								custom_maternity_benefit = %(custom_maternity_benefit)s,
								actual_overtime_duration = %(actual_overtime_duration)s,
								custom_approved_overtime_duration = %(custom_approved_overtime_duration)s,
								custom_final_overtime_duration = %(custom_final_overtime_duration)s,
								overtime_type = %(overtime_type)s,
								standard_working_hours = %(standard_working_hours)s,
								modified = NOW(),
								modified_by = %(user)s
							WHERE name = %(name)s
						""", {**update_data, 'name': att_name, 'user': frappe.session.user})

						# Link/Unlink checkins to attendance (using bulk update for performance)
						if att_data.get('log_names'):
							# Link checkins to this attendance
							log_names_str = "', '".join(att_data['log_names'])
							frappe.db.sql(f"""
								UPDATE `tabEmployee Checkin`
								SET attendance = '{att_name}'
								WHERE name IN ('{log_names_str}')
							""")
						# else:
						# 	# No checkins → Unlink any previously linked checkins
						# 	frappe.db.sql(f"""
						# 		UPDATE `tabEmployee Checkin`
						# 		SET attendance = NULL
						# 		WHERE attendance = '{att_name}'
						# 	""")
					except Exception as e:
						print(f"         ⚠️  Failed to update {att_data.get('attendance_name', 'unknown')}: {str(e)}")

				# CRITICAL: Commit the UPDATE changes to database
				if attendance_to_update:
					frappe.db.commit()
					print(f"      💾 Committed {len(attendance_to_update)} attendance updates to database")

			# Bulk insert new attendance records
			created = bulk_insert_attendance_records(attendance_to_insert, ref_data)

			stats["shifts_processed"] += 1
			shift_elapsed = time.time() - shift_start
			print(f"      ✓ Completed {shift_name} in {shift_elapsed:.2f}s ({created} records)")

		except Exception as e:
			stats["errors"] += 1
			frappe.log_error(message=str(e), title=f"Process Auto Attendance Error - {shift_name}")
			print(f"      ❌ Error processing {shift_name}: {str(e)}")

	# ========================================================================
	# STEP 4: MARK ABSENT/MATERNITY (Optimized Batching)
	# ========================================================================
	print(f"\n{'='*80}")
	print(f"📋 MARKING ABSENT/MATERNITY LEAVE")
	print(f"{'='*80}")

	try:
		absent_to_create = []

		# Process in larger batches
		for batch in create_batch(employees, EMPLOYEE_CHUNK_SIZE_OPTIMIZED):
			for employee in batch:
				emp_data = ref_data['employees'].get(employee)
				if not emp_data:
					continue

				for day in days:
					# Skip if already has attendance
					key = (employee, day)
					if key in ref_data['existing_attendance']:
						continue

					# Check if employee was active on this date
					if emp_data.date_of_joining and emp_data.date_of_joining > day:
						continue

					if emp_data.status == "Left" and emp_data.relieving_date:
						if emp_data.relieving_date <= day:
							continue

					# Get shift for this date
					shift = get_employee_shift_cached(employee, day, ref_data)
					if not shift:
						# Use employee's default_shift, fallback to 'Day' only if no default
						shift = emp_data.get('default_shift') or 'Day'

					# Check maternity status using cached data (for custom_maternity_benefit only)
					maternity_status, custom_maternity_benefit = check_maternity_status_cached(employee, day, ref_data)

					# Check Leave Application (PRIORITY 1)
					leave_status = check_leave_status_cached(employee, day, ref_data)

					# Determine attendance status based on priority
					if leave_status:
						# Has approved leave → "On Leave" or "Half Day"
						status = leave_status['status']
						leave_type = leave_status['leave_type']
						leave_application = leave_status['leave_application']
						leave_abbreviation = leave_status.get('abbreviation')
					else:
						# No leave, no checkins → "Absent"
						status = 'Absent'
						leave_type = None
						leave_application = None
						leave_abbreviation = None

					# Get shift details for standard_working_hours
					shift_data = ref_data['shifts'].get(shift, {})

					absent_to_create.append({
						'employee': employee,
						'employee_name': emp_data.get('employee_name'),
						'attendance_date': day,
						'shift': shift,
						'status': status,
						'leave_type': leave_type,
						'leave_application': leave_application,
						'custom_leave_application_abbreviation': leave_abbreviation,
						'company': emp_data.get('company'),
						'department': emp_data.get('department'),
						'working_hours': 0,
						'custom_maternity_benefit': custom_maternity_benefit,
						'standard_working_hours': shift_data.get('custom_standard_working_hours', 0)
					})

		# Bulk insert absent records
		absent_created = bulk_insert_attendance_records(absent_to_create, ref_data)
		print(f"   ✓ Marked {absent_created} absent/maternity records")

	except Exception as e:
		stats["errors"] += 1
		frappe.log_error(message=str(e), title="Mark Absent Error (Optimized)")
		print(f"   ❌ Error marking absent: {str(e)}")

	# ========================================================================
	# STEP 4b: CLEANUP ATTENDANCE FOR LEFT EMPLOYEES
	# ========================================================================
	# Delete attendance records created after employee's relieving_date (if no checkins).
	# This handles race condition: hook runs before Data Import updates employee status.
	print(f"\n{'='*80}")
	print(f"🧹 CLEANUP ATTENDANCE FOR LEFT EMPLOYEES")
	print(f"{'='*80}")
	try:
		# Find attendance after relieving_date that have NO linked checkins
		invalid_attendance = frappe.db.sql("""
			SELECT a.name, a.employee, a.employee_name, a.attendance_date, e.relieving_date
			FROM `tabAttendance` a
			JOIN `tabEmployee` e ON a.employee = e.name
			WHERE e.status = 'Left'
			  AND e.relieving_date IS NOT NULL
			  AND a.attendance_date > e.relieving_date
			  AND a.docstatus = 1
			  AND a.attendance_date BETWEEN %(from_date)s AND %(to_date)s
			  AND NOT EXISTS (
				SELECT 1 FROM `tabEmployee Checkin` ec
				WHERE ec.attendance = a.name
			  )
		""", {"from_date": from_date_str, "to_date": to_date_str}, as_dict=True)

		if invalid_attendance:
			att_names = [a.name for a in invalid_attendance]
			# Delete attendance records (no checkins linked, safe to remove)
			frappe.db.sql("""
				DELETE FROM `tabAttendance`
				WHERE name IN %(names)s
			""", {"names": att_names})
			print(f"   ✓ Deleted {len(att_names)} attendance records for left employees (no checkins)")
			for a in invalid_attendance:
				print(f"      - {a.employee} ({a.employee_name}): {a.attendance_date} (relieving: {a.relieving_date})")

		# Find attendance after relieving_date that HAVE linked checkins → tag with warning
		has_checkin_attendance = frappe.db.sql("""
			SELECT a.name, a.employee, a.employee_name, a.attendance_date, e.relieving_date
			FROM `tabAttendance` a
			JOIN `tabEmployee` e ON a.employee = e.name
			WHERE e.status = 'Left'
			  AND e.relieving_date IS NOT NULL
			  AND a.attendance_date > e.relieving_date
			  AND a.docstatus = 1
			  AND a.attendance_date BETWEEN %(from_date)s AND %(to_date)s
			  AND EXISTS (
				SELECT 1 FROM `tabEmployee Checkin` ec
				WHERE ec.attendance = a.name
			  )
		""", {"from_date": from_date_str, "to_date": to_date_str}, as_dict=True)

		if has_checkin_attendance:
			print(f"   ⚠️ {len(has_checkin_attendance)} attendance records for left employees WITH checkins (tagging)")
			for a in has_checkin_attendance:
				print(f"      - {a.employee} ({a.employee_name}): {a.attendance_date} (relieving: {a.relieving_date})")

		if not invalid_attendance and not has_checkin_attendance:
			print(f"   ✓ No cleanup needed")

		frappe.db.commit()
	except Exception as e:
		frappe.log_error(message=str(e), title="Cleanup Left Employee Attendance Error")
		print(f"   ❌ Error during cleanup: {str(e)}")

	# ========================================================================
	# STEP 5: CALCULATE STATISTICS FROM DATABASE (Accurate count after processing)
	# ========================================================================
	print(f"\n{'='*80}")
	print(f"📊 CALCULATING FINAL STATISTICS (OPTIMIZED)")
	print(f"{'='*80}")

	# Query actual counts from database after processing (more accurate than cache)
	count_after = {}
	for shift_name in ref_data['shifts'].keys():
		count_after[shift_name] = frappe.db.count("Attendance", {
			"shift": shift_name,
			"attendance_date": ["between", [from_date, to_date]],
			"docstatus": ["!=", 2]
		})

	# Get employees with attendance from database
	employees_with_attendance_set = set(frappe.get_all(
		"Attendance",
		filters={
			"attendance_date": ["between", [from_date, to_date]],
			"docstatus": ["!=", 2]
		},
		pluck="employee"
	))

	# Build per_shift statistics
	for shift_name in ref_data['shifts'].keys():
		before_count = count_before.get(shift_name, 0)
		after_count = count_after.get(shift_name, 0)
		stats["per_shift"][shift_name] = {
			"before": before_count,
			"after": after_count,
			"new_or_updated": after_count - before_count
		}

	# Add shifts that existed before but not in shifts list
	for shift_name in count_before:
		if shift_name not in stats["per_shift"]:
			stats["per_shift"][shift_name] = {
				"before": count_before[shift_name],
				"after": count_before[shift_name],
				"new_or_updated": 0
			}

	# ========================================================================
	# STEP 6: CALCULATE FINAL METRICS (From cached data)
	# ========================================================================
	processing_time = round(time.time() - overall_start, 2)

	total_new_or_updated = sum(s["new_or_updated"] for s in stats["per_shift"].values())
	total_after = sum(s["after"] for s in stats["per_shift"].values())

	# Use cached employee count instead of expensive DISTINCT query
	employees_with_attendance = len(employees_with_attendance_set)
	employees_processed = stats["total_employees"]
	employees_skipped = employees_processed - employees_with_attendance

	stats.update({
		"processing_time": processing_time,
		"actual_records": total_new_or_updated,
		"total_records_in_db": total_after,
		"employees_with_attendance": employees_with_attendance,
		"employees_skipped": employees_skipped,
		"records_per_second": round(total_new_or_updated / processing_time, 2) if processing_time > 0 else 0
	})

	print(f"\n{'='*80}")
	print(f"✅ OPTIMIZED PROCESSING COMPLETE")
	print(f"{'='*80}")
	print(f"   📊 Records created/updated: {total_new_or_updated}")
	print(f"   👥 Employees processed: {employees_with_attendance}/{employees_processed}")
	print(f"   ⏱️  Total time: {processing_time}s")
	print(f"   🚀 Throughput: {stats['records_per_second']:.0f} records/sec")
	print(f"{'='*80}\n")

	return stats


# ============================================================================
# OPTIMIZED ENTRY POINT
# ============================================================================

@frappe.whitelist()
def bulk_update_attendance_optimized(from_date, to_date, employees=None, batch_size=100, force_sync=0):
	"""
	OPTIMIZED bulk update attendance with hybrid approach.

	This is a drop-in replacement for bulk_update_attendance with ~75% better performance.

	Args:
		from_date: Start date (string)
		to_date: End date (string)
		employees: Optional employee list as JSON string
		batch_size: Batch size (default 100, increased from 20)
		force_sync: Force synchronous processing (default 0)

	Returns:
		Same format as original bulk_update_attendance
	"""
	import json
	from datetime import timedelta

	# ========================================================================
	# LOCK MECHANISM - Prevent concurrent bulk updates
	# ========================================================================
	lock_name = "bulk_update_attendance_lock"

	# Check if another bulk update is already running
	existing_lock = frappe.cache.get_value(lock_name)
	if existing_lock:
		lock_info = f"Started by {existing_lock.get('user', 'unknown')} at {existing_lock.get('started_at', 'unknown')}"
		frappe.throw(
			f"Another bulk update is already in progress. {lock_info}. Please wait for it to complete.",
			title="Bulk Update In Progress"
		)

	# Set lock with 30 minute expiry (in case of crash)
	frappe.cache.set_value(lock_name, {
		"user": frappe.session.user,
		"started_at": frappe.utils.now(),
		"from_date": str(from_date),
		"to_date": str(to_date)
	}, expires_in_sec=1800)

	# Parse employees
	employee_list = None
	if employees:
		if isinstance(employees, str):
			employee_list = json.loads(employees)
		elif isinstance(employees, list):
			employee_list = employees

	# Convert dates
	from_date = getdate(from_date)
	to_date = getdate(to_date)

	# Validate
	if from_date > to_date:
		# Release lock before throwing
		frappe.cache.delete_value(lock_name)
		frappe.throw("From Date cannot be greater than To Date")

	# Estimate workload
	days_count = (to_date - from_date).days + 1

	if employee_list:
		employees_count = len(employee_list)
	else:
		from customize_erpnext.api.employee.employee_utils import get_employees_active_in_date_range
		active_employees = get_employees_active_in_date_range(
			from_date=str(from_date),
			to_date=str(to_date)
		)
		employees_count = len(active_employees) if active_employees else 0

	estimated_records = employees_count * days_count

	print(f"📊 Workload estimation: {employees_count} employees × {days_count} days = {estimated_records} records")

	# Build days list
	days = []
	current = from_date
	while current <= to_date:
		days.append(current)
		current += timedelta(days=1)

	# ALWAYS run synchronously with optimized version
	# (Optimized version is fast enough to handle large datasets)
	print(f"⚡ Running OPTIMIZED processing for {estimated_records} records...")

	# Backup shift parameters (same as original)
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

	try:
		# Set temporary parameters
		temp_process_after = from_date
		temp_last_sync = str(to_date) + " 23:59:59"

		for shift_name in shift_backups.keys():
			frappe.db.set_value("Shift Type", shift_name, {
				"process_attendance_after": temp_process_after,
				"last_sync_of_checkin": temp_last_sync
			}, update_modified=False)

		frappe.db.commit()

		# Use optimized core logic with fore_get_logs=True (full day mode for UI)
		stats = _core_process_attendance_logic_optimized(
			employee_list, days, from_date, to_date, fore_get_logs=True
		)

		result = {
			"success": True,
			"total_operations": estimated_records,
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

	except Exception as e:
		# Release lock on error
		frappe.cache.delete_value(lock_name)
		frappe.log_error(f"Bulk update attendance error: {str(e)}", "Bulk Update Error")
		raise

	finally:
		# Restore original parameters
		print("🔙 Restoring original shift parameters...")
		for shift_name, backup_values in shift_backups.items():
			try:
				frappe.db.set_value("Shift Type", shift_name, {
					"process_attendance_after": backup_values["process_attendance_after"],
					"last_sync_of_checkin": backup_values["last_sync_of_checkin"]
				}, update_modified=False)
			except Exception as e:
				print(f"✗ Error restoring {shift_name}: {str(e)}")

		frappe.db.commit()

	# Release lock after successful completion
	frappe.cache.delete_value(lock_name)

	return {
		"success": True,
		"background_job": False,
		"result": result,
		"optimized": True  # Flag to indicate this used optimized version
	}


# ============================================================================
# WRAPPER FOR HRMS HOURLY HOOK (Monkey Patch Replacement)
# ============================================================================

def custom_process_auto_attendance_for_all_shifts(employees=None, days=None):
	"""
	OPTIMIZED wrapper for HRMS hourly hook.

	This function replaces the original HRMS process_auto_attendance_for_all_shifts
	via monkey patching in __init__.py.

	When called by HRMS hourly_long hook without parameters:
	- employees = all active employees
	- days = derived from each shift's Process Attendance After & Last Sync of Checkin

	Args:
		employees: Optional list of employee IDs
		days: Optional list of date objects to process

	Returns:
		Same format as original function for compatibility
	"""
	from datetime import timedelta

	# Determine date range from shift type settings
	# HRMS uses each shift's process_attendance_after and last_sync_of_checkin
	# We get the earliest process_attendance_after and latest last_sync_of_checkin
	if days is None:
		# Get all shifts with auto attendance enabled
		shifts = frappe.get_all(
			"Shift Type",
			filters={"enable_auto_attendance": 1},
			fields=["process_attendance_after", "last_sync_of_checkin"]
		)

		if shifts:
			# Get min process_attendance_after and max last_sync_of_checkin
			process_after_dates = [s.process_attendance_after for s in shifts if s.process_attendance_after]
			last_sync_dates = [s.last_sync_of_checkin for s in shifts if s.last_sync_of_checkin]

			if process_after_dates:
				from_date = min(getdate(d) for d in process_after_dates)
			else:
				from_date = getdate(frappe.utils.add_days(frappe.utils.nowdate(), -30))

			if last_sync_dates:
				# last_sync_of_checkin is datetime, get date part
				to_date = max(getdate(d) for d in last_sync_dates)
			else:
				to_date = getdate(frappe.utils.nowdate())
		else:
			# No auto-enabled shifts, use default range
			from_date = getdate(frappe.utils.add_days(frappe.utils.nowdate(), -30))
			to_date = getdate(frappe.utils.nowdate())

		# CRITICAL FIX: Extend to_date to current day when running at special hours
		# When hook runs at 8AM before shift ends, last_sync is still previous day
		# but we need to process current day's partial attendance
		current_datetime_check = frappe.flags.current_datetime or frappe.utils.now_datetime()
		current_hour = current_datetime_check.hour
		is_web_request = hasattr(frappe.local, 'request') and frappe.local.request
		is_special_hour = current_hour in [8, 23]  # 8AM or 11PM

		if (is_web_request or is_special_hour):
			current_date = getdate(current_datetime_check)
			if to_date < current_date:
				print(f"   ⚠️  Extending to_date from {to_date} to {current_date} (special hour {current_hour} or UI)")
				to_date = current_date

		# Build days list
		days_list = []
		current = from_date
		while current <= to_date:
			days_list.append(current)
			current += timedelta(days=1)

		print(f"📅 Auto date range: {from_date} to {to_date} ({len(days_list)} days)")
	else:
		# Normalize provided days to date objects
		normalized_days = []
		for day in days:
			if isinstance(day, str):
				normalized_days.append(getdate(day))
			elif isinstance(day, date):
				normalized_days.append(day)
			else:
				# datetime object
				normalized_days.append(day.date() if hasattr(day, 'date') else day)

		# Get min and max dates
		from_date = min(normalized_days)
		to_date = max(normalized_days)
		days_list = normalized_days

		print(f"📅 Provided date range: {from_date} to {to_date} ({len(days_list)} days)")

	# Get employee list
	employee_list = employees
	if not employee_list:
		# Get all active employees for the date range
		from customize_erpnext.api.employee.employee_utils import get_employees_active_in_date_range
		active_employees = get_employees_active_in_date_range(
			from_date=str(from_date),
			to_date=str(to_date)
		)
		# get_employees_active_in_date_range returns list of strings (employee IDs)
		employee_list = active_employees if active_employees else []

		print(f"👥 Active employees: {len(employee_list)}")
	else:
		print(f"👥 Filtered employees: {len(employee_list)}")

	# Call optimized core logic
	print(f"\n🔄 HRMS Hourly Hook → Using OPTIMIZED CODE")

	stats = _core_process_attendance_logic_optimized(
		employees=employee_list,
		days=days_list,
		from_date=from_date,
		to_date=to_date
	)

	# NOTE: KHÔNG GỌI update_last_sync_of_checkin ở đây
	# Lý do: HRMS hooks đã gọi update_last_sync_of_checkin TRƯỚC process_auto_attendance_for_all_shifts
	# Thứ tự trong hooks.py:
	#   1. update_last_sync_of_checkin
	#   2. process_auto_attendance_for_all_shifts
	# Nên không cần gọi lại để tránh update 2 lần

	# Return in original format
	return {
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


print("✅ Shift Type Optimized (Hybrid) loaded successfully")
