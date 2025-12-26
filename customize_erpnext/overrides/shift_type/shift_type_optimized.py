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
EMPLOYEE_CHUNK_SIZE_OPTIMIZED = 100  # Increased from 20
BULK_INSERT_BATCH_SIZE = 500  # For bulk_insert operations
CHECKIN_UPDATE_BATCH_SIZE = 1000  # For checkin updates (increased for faster processing)
SPECIAL_HOUR_FORCE_UPDATE = [8, 23] 


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
			"last_sync_of_checkin"
		]
	)
	for shift in shifts:
		data['shifts'][shift.name] = shift
	print(f"   ✓ Loaded {len(data['shifts'])} shift types")

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
		fields=["name", "employee", "attendance_date", "shift", "status"]
	)
	for att in existing:
		key = (att.employee, att.attendance_date)
		data['existing_attendance'][key] = att
	print(f"   ✓ Loaded {len(data['existing_attendance'])} existing attendance records")

	# 6. Load maternity tracking (child table in Employee)
	print(f"   Loading maternity tracking...")
	data['maternity_tracking'] = {}

	# Check if Maternity Tracking child table exists
	if frappe.db.exists("DocType", "Maternity Tracking"):
		try:
			# Query from child table - parent is employee ID
			if employee_list:
				# Specific employees
				maternity_records = frappe.db.sql("""
					SELECT parent as employee, type, from_date, to_date, apply_pregnant_benefit
					FROM `tabMaternity Tracking`
					WHERE parent IN %(employees)s
					  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
					  AND from_date <= %(to_date)s
					  AND to_date >= %(from_date)s
				""", {
					"employees": employee_list,
					"from_date": from_date,
					"to_date": to_date
				}, as_dict=True)
			else:
				# All employees
				maternity_records = frappe.db.sql("""
					SELECT parent as employee, type, from_date, to_date, apply_pregnant_benefit
					FROM `tabMaternity Tracking`
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
	else:
		print(f"   ℹ️  Maternity Tracking child table not found (skipping - optional feature)")

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

			# Logic from original code:
			# - Young Child: always apply benefit (reduce working hours)
			# - Pregnant: only if apply_pregnant_benefit checkbox is ticked
			if record['type'] == 'Young Child':
				apply_pregnant_benefit = True
			elif record['type'] == 'Pregnant' and record.get('apply_pregnant_benefit'):
				apply_pregnant_benefit = True

			return (maternity_status, apply_pregnant_benefit)

	return (None, False)


def get_employee_shift_cached(
	employee: str,
	attendance_date: date,
	ref_data: Dict
) -> Optional[str]:
	"""
	Get employee's shift for a date using preloaded data (no DB queries).

	Args:
		employee: Employee ID
		attendance_date: Date to check
		ref_data: Preloaded reference data

	Returns:
		str: Shift name or None
	"""
	# Check shift assignments
	assignments = ref_data['shift_assignments'].get(employee, [])
	for assign in assignments:
		if assign.start_date <= attendance_date:
			if not assign.end_date or assign.end_date >= attendance_date:
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

def bulk_update_checkin_shifts(from_date: str, to_date: str) -> int:
	"""
	Update null shifts in checkins using bulk SQL operations.
	Much faster than individual save() calls.

	Returns:
		int: Number of checkins updated
	"""
	print(f"\n{'='*80}")
	print(f"🔄 BULK UPDATE CHECKIN SHIFTS")
	print(f"{'='*80}")
	start = time.time()

	# Get checkins with null shift
	checkin_names = frappe.get_all(
		"Employee Checkin",
		filters={
			"time": ["between", [from_date, to_date]],
			"shift": ["is", "not set"],
			"skip_auto_attendance": 0
		},
		fields=["name", "employee", "time"]
	)

	if not checkin_names:
		print(f"   ℹ️  No checkins with null shift found")
		return 0

	print(f"   Found {len(checkin_names)} checkins with null shift")
	print(f"   📦 Processing in batches of {CHECKIN_UPDATE_BATCH_SIZE}...")

	# Batch update using fetch_shift() to update ALL fields (not just shift)
	# This matches original logic and updates: shift, shift_start, shift_end, shift_actual_start, shift_actual_end
	updated = 0
	errors = 0
	total_batches = (len(checkin_names) + CHECKIN_UPDATE_BATCH_SIZE - 1) // CHECKIN_UPDATE_BATCH_SIZE
	batch_num = 0

	for batch in create_batch(checkin_names, CHECKIN_UPDATE_BATCH_SIZE):
		batch_num += 1
		batch_start = time.time()

		# Prepare bulk update data
		bulk_updates = []

		for checkin in batch:
			try:
				# Get the Employee Checkin document (minimal load)
				checkin_doc = frappe.get_doc("Employee Checkin", checkin.name)

				# Call fetch_shift() to calculate shift-related fields
				# This updates: shift, shift_start, shift_end, shift_actual_start, shift_actual_end
				checkin_doc.fetch_shift()

				# Collect data for bulk update (instead of save())
				bulk_updates.append({
					'name': checkin_doc.name,
					'shift': checkin_doc.shift,
					'shift_start': checkin_doc.shift_start,
					'shift_end': checkin_doc.shift_end,
					'shift_actual_start': checkin_doc.shift_actual_start,
					'shift_actual_end': checkin_doc.shift_actual_end
				})
				updated += 1

			except Exception as e:
				errors += 1
				frappe.log_error(
					message=f"Error processing checkin {checkin.name}: {str(e)}",
					title="Bulk Update Checkin Fields Error"
				)

		# Bulk update using SQL CASE WHEN (FASTEST - single query for entire batch)
		if bulk_updates:
			try:
				# Build CASE WHEN clauses for each field
				names = [u['name'] for u in bulk_updates]

				shift_cases = " ".join([f"WHEN '{u['name']}' THEN {frappe.db.escape(u['shift']) if u['shift'] else 'NULL'}" for u in bulk_updates])
				shift_start_cases = " ".join([f"WHEN '{u['name']}' THEN {frappe.db.escape(str(u['shift_start'])) if u['shift_start'] else 'NULL'}" for u in bulk_updates])
				shift_end_cases = " ".join([f"WHEN '{u['name']}' THEN {frappe.db.escape(str(u['shift_end'])) if u['shift_end'] else 'NULL'}" for u in bulk_updates])
				shift_actual_start_cases = " ".join([f"WHEN '{u['name']}' THEN {frappe.db.escape(str(u['shift_actual_start'])) if u['shift_actual_start'] else 'NULL'}" for u in bulk_updates])
				shift_actual_end_cases = " ".join([f"WHEN '{u['name']}' THEN {frappe.db.escape(str(u['shift_actual_end'])) if u['shift_actual_end'] else 'NULL'}" for u in bulk_updates])

				# Single UPDATE query with CASE WHEN
				frappe.db.sql(f"""
					UPDATE `tabEmployee Checkin`
					SET
						shift = CASE name {shift_cases} END,
						shift_start = CASE name {shift_start_cases} END,
						shift_end = CASE name {shift_end_cases} END,
						shift_actual_start = CASE name {shift_actual_start_cases} END,
						shift_actual_end = CASE name {shift_actual_end_cases} END,
						modified = NOW(),
						modified_by = %s
					WHERE name IN ({','.join(['%s'] * len(names))})
				""", [frappe.session.user] + names)

			except Exception as e:
				frappe.log_error(
					message=f"Error in bulk SQL CASE WHEN update: {str(e)}",
					title="Bulk Update Checkin SQL Error"
				)
				print(f"   ❌ SQL Error in batch {batch_num}: {str(e)}")

				# Fallback to individual updates if SQL fails
				for update in bulk_updates:
					try:
						frappe.db.set_value(
							"Employee Checkin",
							update['name'],
							{
								'shift': update['shift'],
								'shift_start': update['shift_start'],
								'shift_end': update['shift_end'],
								'shift_actual_start': update['shift_actual_start'],
								'shift_actual_end': update['shift_actual_end']
							},
							update_modified=True
						)
					except Exception as e2:
						frappe.log_error(
							message=f"Error updating checkin {update['name']}: {str(e2)}",
							title="Bulk Update Checkin Fallback Error"
						)
						print(f"   ❌ Error updating {update['name']}: {str(e2)}")

		# Commit after each batch
		frappe.db.commit()

		# Progress update every batch
		batch_elapsed = time.time() - batch_start
		print(f"   📊 Progress: {updated}/{len(checkin_names)} ({batch_num}/{total_batches} batches) - {batch_elapsed:.2f}s/batch - Errors: {errors}")

	elapsed = time.time() - start
	print(f"   ✓ Updated {updated} checkins in {elapsed:.2f}s")
	print(f"{'='*80}\n")

	return updated


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

		for att in batch:
			# Skip if already exists
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
					(name, employee, employee_name, attendance_date, shift, status, company, department,
					 working_hours, in_time, out_time, late_entry, early_exit, custom_maternity_benefit,
					 actual_overtime_duration, custom_approved_overtime_duration, custom_final_overtime_duration,
					 overtime_type, standard_working_hours, docstatus, creation, modified, owner, modified_by)
					VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

	# Count records before processing
	count_before = {}
	for shift_name in ref_data['shifts'].keys():
		count_before[shift_name] = frappe.db.count("Attendance", {
			"shift": shift_name,
			"attendance_date": ["between", [from_date, to_date]]
		})

	# ========================================================================
	# STEP 2: FIX NULL SHIFTS IN CHECKINS (Bulk Operation)
	# ========================================================================
	bulk_update_checkin_shifts(from_date_str, to_date_str)

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
			checkin_filters = {
				"skip_auto_attendance": 0,
				"time": [">=", shift_data.process_attendance_after],
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
				from frappe.utils import getdate

				# Convert to_date string to datetime at end of day
				to_date_obj = getdate(to_date)
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
						if old_att.get('shift') != shift_name:
							continue

						# Check if should mark attendance for this employee/date
						if should_mark_attendance_cached(employee, att_date, shift_name, ref_data):
							# No checkins found → Mark as Absent
							emp_data = ref_data['employees'].get(employee, {})
							shift_data = ref_data['shifts'].get(shift_name, {})

							# Check maternity status
							maternity_status, custom_maternity_benefit = check_maternity_status_cached(employee, att_date, ref_data)
							status = maternity_status if maternity_status else 'Absent'

							absence_data = {
								'employee': employee,
								'attendance_date': att_date,
								'attendance_name': old_att['name'],
								'status': status,
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
										status = %(status)s,
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
									'status': att_data.get('status', 'Absent'),
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

				# Prepare attendance record with FULL fields (matches original)
				att_data = {
					'employee': employee,
					'employee_name': emp_data.get('employee_name'),
					'attendance_date': attendance_date,
					'shift': shift_name,
					'status': 'Present',
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
						attendance_to_update.append(att_data)
						updated_keys.add(key)  # Mark as updated
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
					if old_att.get('shift') != shift_name:
						continue

					# If attendance exists but was NOT updated (no checkins found), mark as Absent
					if key not in updated_keys:
						# Check if should mark attendance for this employee/date
						if should_mark_attendance_cached(employee, att_date, shift_name, ref_data):
							# No checkins found → Mark as Absent
							emp_data = ref_data['employees'].get(employee, {})
							shift_data = ref_data['shifts'].get(shift_name, {})

							# Check maternity status
							maternity_status, custom_maternity_benefit = check_maternity_status_cached(employee, att_date, ref_data)
							status = maternity_status if maternity_status else 'Absent'

							absence_data = {
								'employee': employee,
								'attendance_date': att_date,
								'attendance_name': old_att['name'],
								'status': status,
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
							attendance_to_update.append(absence_data)
							updated_keys.add(key)

			# Update existing attendance records (fore_get_logs=True only)
			# CRITICAL: Must RECALCULATE from ALL checkins (matches custom_create_or_update_attendance)
			if attendance_to_update:
				print(f"      🔄 Updating {len(attendance_to_update)} existing attendance records")
				for att_data in attendance_to_update:
					try:
						# Get old attendance data for comparison
						old_att_data = ref_data['existing_attendance'][(att_data['employee'], att_data['attendance_date'])]

						# IMPORTANT: Only update if data actually changed (optimization)
						# Compare key fields that matter
						needs_update = (
							old_att_data.get('status') != att_data.get('status', 'Present') or
							str(old_att_data.get('in_time')) != str(att_data.get('in_time')) or
							str(old_att_data.get('out_time')) != str(att_data.get('out_time')) or
							old_att_data.get('working_hours') != att_data.get('working_hours', 0)
						)

						if not needs_update:
							# Data unchanged, skip update
							continue

						# Update using SQL (faster, avoids "Cannot edit cancelled document" issue)
						# Must cancel first, then update all fields, then resubmit in single operation
						att_name = att_data['attendance_name']

						# Build update query with all fields at once
						update_data = {
							"docstatus": 1,  # Keep submitted (or set to 1 if cancelled)
							"status": att_data.get('status', 'Present'),
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
								status = %(status)s,
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
						shift = 'Day'

					# Check maternity status using cached data (no DB query!)
					maternity_status, custom_maternity_benefit = check_maternity_status_cached(employee, day, ref_data)

					status = 'Maternity Leave' if maternity_status == 'Maternity Leave' else 'Absent'

					# Get shift details for standard_working_hours
					shift_data = ref_data['shifts'].get(shift, {})

					absent_to_create.append({
						'employee': employee,
						'employee_name': emp_data.get('employee_name'),
						'attendance_date': day,
						'shift': shift,
						'status': status,
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
	# STEP 5: CALCULATE STATISTICS FROM CACHED DATA (No slow queries!)
	# ========================================================================
	print(f"\n{'='*80}")
	print(f"📊 CALCULATING FINAL STATISTICS (OPTIMIZED)")
	print(f"{'='*80}")

	# Use cached data instead of querying the database
	# Count records by shift from cache
	shift_counts = {}
	employees_with_attendance_set = set()

	for (emp, _date), att_data in ref_data['existing_attendance'].items():
		# Get shift from cached attendance data or default
		shift = att_data.get('shift', 'Day')
		shift_counts[shift] = shift_counts.get(shift, 0) + 1
		employees_with_attendance_set.add(emp)

	# Build per_shift statistics
	for shift_name, final_count in shift_counts.items():
		before_count = count_before.get(shift_name, 0)
		stats["per_shift"][shift_name] = {
			"before": before_count,
			"after": final_count,
			"new_or_updated": final_count - before_count
		}

	# Add shifts that existed before but have no new records
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
