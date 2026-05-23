"""
Shift Assignment Overrides
Automatically recalculate Attendance when Shift Assignment is submitted, cancelled, or dates are changed.

Requirements:
1. On submit/cancel: Recalculate Attendance from Start Date to End Date (or today if End Date is null)
2. On date change: Recalculate Attendance from min(old_start, new_start) to max(old_end, new_end)
3. Run in background to avoid timeout
"""

import frappe
from frappe.utils import getdate, today
from datetime import timedelta
from typing import List, Optional
from datetime import date


def _get_date_range(from_date: date, to_date: date) -> List[date]:
	"""
	Generate list of dates from from_date to to_date.

	Args:
		from_date: Start date
		to_date: End date

	Returns:
		List of date objects
	"""
	days = []
	current = from_date
	while current <= to_date:
		days.append(current)
		current += timedelta(days=1)
	return days


def _recalculate_attendance_job(employee: str, from_date_str: str, to_date_str: str, trigger: str = ""):
	"""
	Background job to recalculate attendance for an employee.
	This function is called by frappe.enqueue().

	Args:
		employee: Employee ID
		from_date_str: Start date as string (YYYY-MM-DD)
		to_date_str: End date as string (YYYY-MM-DD)
		trigger: Description of what triggered this job
	"""
	from customize_erpnext.overrides.shift_type.shift_type_optimized import (
		_core_process_attendance_logic_optimized
	)

	# Convert to date objects
	from_date = getdate(from_date_str)
	to_date = getdate(to_date_str)

	# Ensure to_date doesn't exceed today
	today_date = getdate(today())
	if to_date > today_date:
		to_date = today_date

	# Skip if from_date > to_date (nothing to process)
	if from_date > to_date:
		print(f"   ℹ️  Skipping: from_date ({from_date}) > to_date ({to_date})")
		return

	days = _get_date_range(from_date, to_date)

	print(f"\n{'='*60}")
	print(f"🔄 SHIFT ASSIGNMENT [BACKGROUND]: Recalculating Attendance")
	print(f"   Trigger: {trigger}")
	print(f"   Employee: {employee}")
	print(f"   Date Range: {from_date} to {to_date} ({len(days)} days)")
	print(f"{'='*60}")

	try:
		stats = _core_process_attendance_logic_optimized(
			employees=[employee],
			days=days,
			from_date=str(from_date),
			to_date=str(to_date),
			fore_get_logs=True  # Full recalculation mode
		)

		print(f"   ✅ Recalculation complete: {stats.get('actual_records', 0)} records processed")

	except Exception as e:
		frappe.log_error(
			message=f"Error recalculating attendance for {employee}: {str(e)}",
			title="Shift Assignment Attendance Recalculation Error"
		)
		print(f"   ❌ Error: {str(e)}")


def _calculate_job_timeout(from_date, to_date) -> int:
	"""
	Calculate appropriate timeout based on date range.

	Formula: base_timeout + (days * seconds_per_day)
	- Base timeout: 60 seconds (startup, preload data)
	- Per day: 3 seconds (processing 1 employee × 1 day)
	- Min: 60 seconds
	- Max: 600 seconds (10 minutes)

	Args:
		from_date: Start date
		to_date: End date

	Returns:
		int: Timeout in seconds
	"""
	from_date_obj = getdate(from_date)
	to_date_obj = getdate(to_date)

	# Calculate number of days
	days = (to_date_obj - from_date_obj).days + 1

	# Calculate timeout
	BASE_TIMEOUT = 30  # seconds for startup/preload
	SECONDS_PER_DAY = 2  # seconds per day per employee
	MIN_TIMEOUT = 60
	MAX_TIMEOUT = 600  # 10 minutes max

	timeout = BASE_TIMEOUT + (days * SECONDS_PER_DAY)
	timeout = max(MIN_TIMEOUT, min(timeout, MAX_TIMEOUT))

	return timeout


def _recalculate_attendance(employee: str, from_date, to_date, trigger: str = ""):
	"""
	Enqueue background job to recalculate attendance for an employee.
	Runs asynchronously to avoid timeout.

	Args:
		employee: Employee ID
		from_date: Start date (date or string)
		to_date: End date (date or string)
		trigger: Description of what triggered this recalculation
	"""
	# Convert to string for serialization
	from_date_str = str(getdate(from_date))
	to_date_str = str(getdate(to_date))

	# Calculate appropriate timeout based on date range
	timeout = _calculate_job_timeout(from_date, to_date)

	print(f"\n📤 Enqueueing attendance recalculation job...")
	print(f"   Employee: {employee}")
	print(f"   Date Range: {from_date_str} to {to_date_str}")
	print(f"   Timeout: {timeout}s")
	print(f"   Trigger: {trigger}")

	# Enqueue background job
	frappe.enqueue(
		"customize_erpnext.overrides.shift_assignment.shift_assignment._recalculate_attendance_job",
		queue="default",  # Use default queue
		timeout=timeout,  # Dynamic timeout based on date range
		employee=employee,
		from_date_str=from_date_str,
		to_date_str=to_date_str,
		trigger=trigger,
		now=frappe.flags.in_test  # Run immediately if in test mode
	)

	frappe.msgprint(
		f"Đang tính toán lại Attendance cho {employee} từ {from_date_str} đến {to_date_str}. Vui lòng đợi...",
		indicator="blue",
		alert=True
	)


def recalculate_attendance_on_submit(doc, method=None):
	"""
	Hook: on_submit
	Recalculate Attendance from Start Date to End Date (or today if End Date is null).

	Args:
		doc: Shift Assignment document
		method: Hook method name
	"""
	employee = doc.employee
	from_date = getdate(doc.start_date)
	to_date = getdate(doc.end_date) if doc.end_date else getdate(today())

	print(f"\n📝 Shift Assignment SUBMITTED: {doc.name}")
	print(f"   Employee: {employee}, Shift: {doc.shift_type}")
	print(f"   Period: {from_date} to {to_date}")

	trigger = f"Submit Shift Assignment {doc.name} ({doc.shift_type})"
	_recalculate_attendance(employee, from_date, to_date, trigger)


def recalculate_attendance_on_cancel(doc, method=None):
	"""
	Hook: on_cancel
	Recalculate Attendance from Start Date to End Date (or today if End Date is null).

	Args:
		doc: Shift Assignment document
		method: Hook method name
	"""
	employee = doc.employee
	from_date = getdate(doc.start_date)
	to_date = getdate(doc.end_date) if doc.end_date else getdate(today())

	print(f"\n🚫 Shift Assignment CANCELLED: {doc.name}")
	print(f"   Employee: {employee}, Shift: {doc.shift_type}")
	print(f"   Period: {from_date} to {to_date}")

	trigger = f"Cancel Shift Assignment {doc.name} ({doc.shift_type})"
	_recalculate_attendance(employee, from_date, to_date, trigger)


def capture_old_dates_before_save(doc, method=None):
	"""
	Hook: before_save (for on_update_after_submit)
	Capture old Start Date and End Date before the document is saved.
	This is needed to compare with new dates and determine the recalculation range.

	Args:
		doc: Shift Assignment document
		method: Hook method name
	"""
	# Only capture for submitted documents (amendments/updates after submit)
	if doc.docstatus != 1:
		return

	# Skip if document is new (not yet in database)
	if not doc.name or doc.is_new():
		return

	# Get old values from database BEFORE the save
	old_values = frappe.db.get_value(
		"Shift Assignment",
		doc.name,
		["start_date", "end_date"],
		as_dict=True
	)

	if old_values:
		# Store old dates in flags for use in on_update_after_submit
		doc.flags.old_start_date = old_values.start_date
		doc.flags.old_end_date = old_values.end_date

		print(f"\n📌 Captured old dates for {doc.name}:")
		print(f"   Old Start: {old_values.start_date}, Old End: {old_values.end_date}")
		print(f"   New Start: {doc.start_date}, New End: {doc.end_date}")


def recalculate_attendance_on_date_change(doc, method=None):
	"""
	Hook: on_update_after_submit
	Recalculate Attendance when Start Date or End Date changes.
	Range: min(old_start, new_start) to max(old_end, new_end)

	Args:
		doc: Shift Assignment document
		method: Hook method name
	"""
	print(f"\n🔍 on_update_after_submit triggered for {doc.name}")

	# Method 1: Get old dates from flags (set in before_save)
	old_start = getattr(doc.flags, 'old_start_date', None)
	old_end = getattr(doc.flags, 'old_end_date', None)

	# Method 2: Use Frappe's get_doc_before_save() if flags not available
	if old_start is None:
		old_doc = doc.get_doc_before_save()
		if old_doc:
			old_start = old_doc.start_date
			old_end = old_doc.end_date
			print(f"   Using get_doc_before_save(): Old Start={old_start}, Old End={old_end}")

	# If still no old values, skip (can't determine what changed)
	if old_start is None:
		print(f"   ⚠️  Could not determine old dates, skipping recalculation")
		return

	# Current values (new values after save)
	new_start = doc.start_date
	new_end = doc.end_date

	print(f"   Old: {old_start} to {old_end}")
	print(f"   New: {new_start} to {new_end}")

	# Convert to date objects
	old_start_date = getdate(old_start) if old_start else None
	old_end_date = getdate(old_end) if old_end else None
	new_start_date = getdate(new_start) if new_start else None
	new_end_date = getdate(new_end) if new_end else None

	# Use today if end_date is null
	today_date = getdate(today())
	if old_end_date is None:
		old_end_date = today_date
	if new_end_date is None:
		new_end_date = today_date

	# Check if dates have changed
	dates_changed = (old_start_date != new_start_date) or (old_end_date != new_end_date)

	if not dates_changed:
		print(f"   📌 No date changes detected, skipping recalculation")
		return

	# Calculate recalculation range
	# from_date = min(old_start, new_start)
	# to_date = max(old_end, new_end)
	from_date = min(old_start_date, new_start_date) if old_start_date and new_start_date else (old_start_date or new_start_date)
	to_date = max(old_end_date, new_end_date) if old_end_date and new_end_date else (old_end_date or new_end_date)

	print(f"\n📝 Shift Assignment DATE CHANGED: {doc.name}")
	print(f"   Employee: {doc.employee}, Shift: {doc.shift_type}")
	print(f"   Old Period: {old_start_date} to {old_end_date}")
	print(f"   New Period: {new_start_date} to {new_end_date}")
	print(f"   Recalculation Range: {from_date} to {to_date}")

	trigger = f"Date Change Shift Assignment {doc.name} ({doc.shift_type})"
	_recalculate_attendance(doc.employee, from_date, to_date, trigger)


print("✅ Shift Assignment Overrides loaded successfully")
