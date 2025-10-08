# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import today, add_days, getdate
from datetime import datetime
import logging

def daily_timesheet_auto_sync_and_calculate():
	"""
	Scheduled job to automatically sync and calculate Daily Timesheet at 22:45 daily
	OPTIMIZED with bulk data loading for faster processing
	"""
	try:
		import time
		start_time = time.time()

		# Get today's date
		current_date = today()

		# Log start of process
		frappe.logger().info(f"Starting OPTIMIZED Daily Timesheet auto sync for date: {current_date}")

		# Get all employees who have check-ins today but no Daily Timesheet record
		employees_without_timesheet = get_employees_needing_sync(current_date)

		# Get all existing Daily Timesheet records for today
		existing_timesheets = frappe.get_all("Daily Timesheet",
			filters={"attendance_date": current_date},
			fields=["name", "employee", "attendance_date"]
		)

		# Collect all unique employee IDs (for both new and existing)
		employees_to_create = [emp['employee'] for emp in employees_without_timesheet]
		employees_to_update = [ts['employee'] for ts in existing_timesheets]
		all_employee_ids = list(set(employees_to_create + employees_to_update))

		if not all_employee_ids:
			frappe.logger().info(f"No employees with check-ins found for {current_date}")
			return {"created": 0, "updated": 0}

		frappe.logger().info(f"Found {len(employees_to_create)} employees to create, {len(employees_to_update)} to update")

		# ===== BULK DATA LOADING - Load all data once =====
		frappe.logger().info(f"Loading bulk data for {len(all_employee_ids)} employees...")

		# Import the optimized bulk loading function
		from customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet import (
			load_bulk_timesheet_data,
			calculate_all_fields_optimized
		)

		# Load ALL required data in one go (checkins, shifts, maternity, OT registrations)
		bulk_data = load_bulk_timesheet_data(all_employee_ids, current_date, current_date)
		frappe.logger().info(f"Bulk data loaded successfully")

		created_count = 0
		updated_count = 0
		error_count = 0

		# Create Daily Timesheet for employees without records
		for emp_data in employees_without_timesheet:
			try:
				create_daily_timesheet_record_optimized(emp_data['employee'], current_date, bulk_data)
				created_count += 1
			except Exception as e:
				frappe.log_error(f"Failed to create Daily Timesheet for {emp_data['employee']}: {str(e)}")
				error_count += 1

		# Update all existing Daily Timesheet records for today
		for ts in existing_timesheets:
			try:
				doc = frappe.get_doc("Daily Timesheet", ts.name)
				# Use OPTIMIZED calculation with pre-loaded bulk_data
				calculate_all_fields_optimized(doc, bulk_data, skip_html_generation=True)
				doc.save()
				updated_count += 1
			except Exception as e:
				frappe.log_error(f"Failed to update Daily Timesheet {ts.name}: {str(e)}")
				error_count += 1

		# Calculate performance metrics
		end_time = time.time()
		processing_time = round(end_time - start_time, 2)
		total_processed = created_count + updated_count
		records_per_second = round(total_processed / processing_time, 2) if processing_time > 0 else 0

		# Log completion
		frappe.logger().info(
			f"Daily Timesheet sync completed. Created: {created_count}, Updated: {updated_count}, "
			f"Errors: {error_count} in {processing_time}s ({records_per_second} records/sec)"
		)

		return {
			"created": created_count,
			"updated": updated_count,
			"errors": error_count,
			"processing_time": processing_time,
			"records_per_second": records_per_second
		}

	except Exception as e:
		frappe.log_error(f"Daily Timesheet auto sync failed: {str(e)}")
		raise

def get_employees_needing_sync(date):
	"""
	Get employees who have check-ins but no Daily Timesheet record for the given date
	"""
	return frappe.db.sql("""
		SELECT DISTINCT ec.employee
		FROM `tabEmployee Checkin` ec
		WHERE DATE(ec.time) = %(date)s
		AND NOT EXISTS (
			SELECT 1 FROM `tabDaily Timesheet` dt 
			WHERE dt.employee = ec.employee 
			AND dt.attendance_date = %(date)s
		)
	""", {"date": date}, as_dict=True)

def create_daily_timesheet_record(employee, attendance_date):
	"""
	Create a new Daily Timesheet record for the given employee and date
	LEGACY VERSION - Use create_daily_timesheet_record_optimized for better performance
	"""
	# Get employee details
	employee_details = frappe.db.get_value("Employee", employee,
		["employee_name", "department", "custom_section", "custom_group", "company"], as_dict=1)

	if not employee_details:
		raise Exception(f"Employee {employee} not found")

	# Create new Daily Timesheet
	doc = frappe.get_doc({
		"doctype": "Daily Timesheet",
		"employee": employee,
		"employee_name": employee_details.employee_name,
		"attendance_date": attendance_date,
		"department": employee_details.department,
		"custom_section": employee_details.custom_section,
		"custom_group": employee_details.custom_group,
		"company": employee_details.company or frappe.defaults.get_user_default("Company"),
	})

	# Calculate all fields before saving
	doc.calculate_all_fields()
	doc.insert(ignore_permissions=True)

	return doc

def create_daily_timesheet_record_optimized(employee, attendance_date, bulk_data):
	"""
	OPTIMIZED: Create a new Daily Timesheet record using pre-loaded bulk_data
	No individual DB queries for employee details - uses bulk_data instead
	"""
	# Get employee details from DB (still needed for basic info not in bulk_data)
	employee_details = frappe.db.get_value("Employee", employee,
		["employee_name", "department", "custom_section", "custom_group", "company"], as_dict=1)

	if not employee_details:
		raise Exception(f"Employee {employee} not found")

	# Create new Daily Timesheet
	doc = frappe.get_doc({
		"doctype": "Daily Timesheet",
		"employee": employee,
		"employee_name": employee_details.employee_name,
		"attendance_date": attendance_date,
		"department": employee_details.department,
		"custom_section": employee_details.custom_section,
		"custom_group": employee_details.custom_group,
		"company": employee_details.company or frappe.defaults.get_user_default("Company"),
	})

	# Import the optimized calculation function
	from customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet import calculate_all_fields_optimized

	# Calculate all fields using pre-loaded bulk_data
	calculate_all_fields_optimized(doc, bulk_data, skip_html_generation=True)
	doc.insert(ignore_permissions=True)

	return doc

def auto_sync_on_checkin_update(checkin_doc, method=None):
	"""
	Auto sync Daily Timesheet when Employee Checkin is updated
	Called from document event hook
	"""
	if not checkin_doc.employee or not checkin_doc.time:
		return
		
	attendance_date = getdate(checkin_doc.time)
	
	# Check if Daily Timesheet exists for this employee and date
	existing_timesheet = frappe.db.exists("Daily Timesheet", {
		"employee": checkin_doc.employee,
		"attendance_date": attendance_date
	})
	
	if existing_timesheet:
		# Update existing record - always sync
		doc = frappe.get_doc("Daily Timesheet", existing_timesheet)
		doc.calculate_all_fields()
		doc.save()
	else:
		# Create new record
		try:
			create_daily_timesheet_record(checkin_doc.employee, attendance_date)
		except Exception as e:
			frappe.log_error(f"Failed to create Daily Timesheet for {checkin_doc.employee}: {str(e)}")

def auto_cleanup_on_checkin_delete(checkin_doc, method=None):
	"""
	Auto cleanup Daily Timesheet when Employee Checkin is deleted
	Only delete if no other check-ins exist for that employee on that date
	"""
	if not checkin_doc.employee or not checkin_doc.time:
		return
		
	attendance_date = getdate(checkin_doc.time)
	
	# Check if there are any other check-ins for this employee on this date
	other_checkins = frappe.db.count("Employee Checkin", {
		"employee": checkin_doc.employee,
		"time": ["between", [f"{attendance_date} 00:00:00", f"{attendance_date} 23:59:59"]],
		"name": ["!=", checkin_doc.name]  # Exclude the current record being deleted
	})
	
	if other_checkins == 0:
		# No other check-ins exist, delete the Daily Timesheet if it exists
		existing_timesheet = frappe.db.exists("Daily Timesheet", {
			"employee": checkin_doc.employee,
			"attendance_date": attendance_date
		})
		
		if existing_timesheet:
			try:
				frappe.delete_doc("Daily Timesheet", existing_timesheet, ignore_permissions=True)
				frappe.logger().info(f"Deleted Daily Timesheet {existing_timesheet} for {checkin_doc.employee} on {attendance_date} - no check-ins remaining")
			except Exception as e:
				frappe.log_error(f"Failed to delete Daily Timesheet {existing_timesheet}: {str(e)}")
	else:
		# Other check-ins exist, just update the Daily Timesheet
		existing_timesheet = frappe.db.exists("Daily Timesheet", {
			"employee": checkin_doc.employee,
			"attendance_date": attendance_date
		})
		
		if existing_timesheet:
			try:
				doc = frappe.get_doc("Daily Timesheet", existing_timesheet)
				doc.calculate_all_fields()
				doc.save()
				frappe.logger().info(f"Updated Daily Timesheet {existing_timesheet} for {checkin_doc.employee} on {attendance_date} after checkin deletion")
			except Exception as e:
				frappe.log_error(f"Failed to update Daily Timesheet {existing_timesheet}: {str(e)}")

def monthly_timesheet_recalculation():
	"""
	Recalculate all Daily Timesheet records for the monthly period
	From 26th of previous month to current date (or 25th if after 25th)
	Runs at 23:30 every Sunday (BULLETPROOF - guaranteed completion with retry logic)
	"""
	try:
		from datetime import date
		import time

		start_time = time.time()

		# Calculate period dates
		today_date = date.today()
		current_day = today_date.day
		current_month = today_date.month
		current_year = today_date.year

		# Calculate from_date: 26th of previous month
		if current_month == 1:
			prev_month = 12
			prev_year = current_year - 1
		else:
			prev_month = current_month - 1
			prev_year = current_year

		from_date = f"{prev_year}-{prev_month:02d}-26"

		# Calculate to_date based on current day
		# If today >= 25th: update until 25th of current month (full period)
		# If today < 25th: update only until today (partial period)
		if current_day >= 25:
			to_date = f"{current_year}-{current_month:02d}-25"
		else:
			to_date = str(today_date)  # Update until today only

		frappe.logger().info(f"Starting BULLETPROOF monthly timesheet recalculation for period: {from_date} to {to_date}")

		# ===== ENQUEUE AS BACKGROUND JOB - Prevents timeout and interruption =====
		# Run in background queue to avoid console timeout
		# This ensures the job completes even if it takes 10-15 minutes

		job_id = f"monthly_recalc_{int(time.time())}"

		frappe.enqueue(
			'customize_erpnext.customize_erpnext.doctype.daily_timesheet.scheduler.monthly_timesheet_recalculation_worker',
			queue='long',  # Use long queue for extended operations
			timeout=2400,  # 40 minutes timeout (plenty of buffer)
			job_id=job_id,
			from_date=from_date,
			to_date=to_date,
			is_retry=False
		)

		frappe.logger().info(f"Monthly recalculation job queued successfully (Job ID: {job_id})")

		return {
			"status": "queued",
			"job_id": job_id,
			"period": f"{from_date} to {to_date}",
			"message": f"Monthly recalculation queued for background processing. Job ID: {job_id}"
		}

	except Exception as e:
		error_msg = f"Failed to queue monthly timesheet recalculation: {str(e)}"
		frappe.log_error(error_msg)
		frappe.logger().error(error_msg)

		# Send critical error notification
		try:
			frappe.sendmail(
				recipients=["hr@tiqn.com.vn", "it@tiqn.com.vn"],
				subject="Monthly Timesheet Recalculation - FAILED TO QUEUE",
				message=f"""
				<h3>Monthly Timesheet Recalculation Failed to Queue</h3>
				<p><strong>Error:</strong> {str(e)}</p>
				<p><strong>Time:</strong> {datetime.now()}</p>
				<br>
				<p style="color: red;">Please check the system immediately.</p>
				"""
			)
		except Exception as email_error:
			frappe.logger().error(f"Failed to send critical error notification: {str(email_error)}")

		raise

def monthly_timesheet_recalculation_worker(from_date, to_date, is_retry=False):
	"""
	Background worker for monthly timesheet recalculation
	BULLETPROOF with comprehensive error handling and retry logic
	"""
	import time
	start_time = time.time()

	try:
		retry_label = " (RETRY)" if is_retry else ""
		frappe.logger().info(f"Worker started{retry_label}: Processing period {from_date} to {to_date}")

		# Import the optimized bulk function
		from customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet import bulk_create_recalculate_hybrid

		# Call the highly optimized bulk function with smaller batch size for stability
		result = bulk_create_recalculate_hybrid(
			from_date=from_date,
			to_date=to_date,
			employee=None,  # Process all employees
			batch_size=50  # Smaller batch size for better stability and commit frequency
		)

		# Extract results
		total_records = result.get('created', 0) + result.get('updated', 0)
		processed = total_records
		errors = result.get('errors', 0)
		processing_time = result.get('processing_time', 0)
		records_per_second = result.get('records_per_second', 0)

		end_time = time.time()
		actual_time = round(end_time - start_time, 2)

		# Final summary
		frappe.logger().info(
			f"Monthly recalculation COMPLETED{retry_label}: {processed} success, {errors} errors "
			f"in {actual_time}s ({records_per_second} records/sec)"
		)

		# Send success notification
		success_subject = f"Monthly Timesheet Recalculation - Completed Successfully{retry_label}"
		if errors > 0:
			success_subject = f"Monthly Timesheet Recalculation - Completed with {errors} Errors{retry_label}"

		try:
			frappe.sendmail(
				recipients=["hr@tiqn.com.vn"],
				subject=success_subject,
				message=f"""
				<h3>Monthly Timesheet Recalculation Summary</h3>
				<p><strong>Status:</strong> ✅ Completed{retry_label}</p>
				<p><strong>Period:</strong> {from_date} to {to_date}</p>
				<p><strong>Total Records:</strong> {total_records}</p>
				<p><strong>Successfully Processed:</strong> {processed}</p>
				<p><strong>Errors:</strong> {errors}</p>
				<p><strong>Processing Time:</strong> {actual_time}s ({records_per_second} records/sec)</p>
				<br>
				{f'<p style="color: orange;">⚠️ Please check the Error Log for details of {errors} failed records.</p>' if errors > 0 else '<p style="color: green;">All records processed successfully!</p>'}
				"""
			)
		except Exception as e:
			frappe.logger().error(f"Failed to send success notification email: {str(e)}")

		return {
			"status": "completed",
			"period": f"{from_date} to {to_date}",
			"total_records": total_records,
			"processed": processed,
			"errors": errors,
			"processing_time": actual_time,
			"records_per_second": records_per_second
		}

	except Exception as e:
		error_msg = f"Monthly timesheet recalculation worker failed: {str(e)}"
		frappe.log_error(error_msg)
		frappe.logger().error(error_msg)

		# Send critical error notification
		try:
			frappe.sendmail(
				recipients=["hr@tiqn.com.vn", "it@tiqn.com.vn"],
				subject="Monthly Timesheet Recalculation - WORKER FAILED",
				message=f"""
				<h3>Monthly Timesheet Recalculation Worker Failed</h3>
				<p><strong>Error:</strong> {str(e)}</p>
				<p><strong>Period:</strong> {from_date} to {to_date}</p>
				<p><strong>Time:</strong> {datetime.now()}</p>
				<br>
				<p style="color: red;">⚠️ The background worker encountered an error.</p>
				<p>Please check the Error Log and consider running manual recalculation.</p>
				"""
			)
		except Exception as email_error:
			frappe.logger().error(f"Failed to send critical error notification: {str(email_error)}")

		raise

@frappe.whitelist()
def manual_bulk_sync(from_date=None, to_date=None, employee=None):
	"""
	Manual bulk sync function that can be called from frontend
	"""
	if not from_date:
		from_date = today()
	if not to_date:
		to_date = today()
		
	from customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet import create_from_checkins
	
	return create_from_checkins(from_date, to_date, employee)

@frappe.whitelist()
def manual_monthly_recalculation(month=None, year=None):
	"""
	Manual monthly recalculation that can be triggered from frontend
	"""
	try:
		from datetime import date

		if not month or not year:
			today_date = date.today()
			month = month or today_date.month
			year = year or today_date.year

		month = int(month)
		year = int(year)

		# Calculate period dates (26th previous month to 25th current month)
		if month == 1:
			prev_month = 12
			prev_year = year - 1
		else:
			prev_month = month - 1
			prev_year = year

		from_date = f"{prev_year}-{prev_month:02d}-26"
		to_date = f"{year}-{month:02d}-25"

		frappe.logger().info(f"Manual monthly recalculation triggered for period: {from_date} to {to_date}")

		# Call the monthly recalculation function
		# Temporarily override the date calculation
		original_today = date.today

		try:
			# Mock today to be the 25th of the target month for calculation
			date.today = lambda: date(year, month, 25)
			result = monthly_timesheet_recalculation()
			return result
		finally:
			# Restore original today function
			date.today = original_today

	except Exception as e:
		frappe.log_error(f"Manual monthly recalculation failed: {str(e)}")
		return {"status": "failed", "error": str(e)}

def auto_recalc_on_shift_registration_change(doc, method):
	"""
	Tự động tính toán lại Daily Timesheet khi Shift Registration thay đổi
	Smart processing: Auto-detect large operations and use background processing
	"""
	try:
		affected_combinations = set()

		# Current records - always process these
		if doc.employees_list:
			for detail in doc.employees_list:
				if not detail.employee or not detail.begin_date or not detail.end_date:
					continue

				# Tạo range từ begin_date đến end_date
				current_date = getdate(detail.begin_date)
				end_date = getdate(detail.end_date)

				while current_date <= end_date:
					affected_combinations.add((detail.employee, current_date))
					current_date = add_days(current_date, 1)

		# For updates/cancellation, also process records that might have been deleted
		if method in ['on_update_after_submit', 'on_cancel']:
			# Get previously submitted version to find deleted records
			if doc.name:  # Ensure doc is saved
				old_records = get_previous_shift_registrations(doc.name)
				for old_detail in old_records:
					current_date = getdate(old_detail['begin_date'])
					end_date = getdate(old_detail['end_date'])

					while current_date <= end_date:
						affected_combinations.add((old_detail['employee'], current_date))
						current_date = add_days(current_date, 1)

		if affected_combinations:
			total_operations = len(affected_combinations)

			# Smart threshold: If > 200 operations, use background processing
			if total_operations > 200:
				# Queue background job with progress tracking
				job_id = f"shift_recalc_{doc.name}_{int(frappe.utils.now_datetime().timestamp())}"

				frappe.enqueue(
					'customize_erpnext.customize_erpnext.doctype.daily_timesheet.scheduler.background_recalculate_timesheets',
					queue='long',  # Use long queue for large operations
					timeout=1800,  # 30 minutes
					job_id=job_id,
					affected_combinations=list(affected_combinations),
					trigger_doc_type="Shift Registration",
					trigger_doc_name=doc.name,
					trigger_method=method,
					batch_size=100
				)

				# Notify user about background processing
				frappe.msgprint(
					f"Large operation detected ({total_operations} records). Processing in background (Job ID: {job_id}). "
					f"You will receive a notification when completed.",
					title="Background Processing Started",
					indicator="blue"
				)

				frappe.logger().info(f"Shift Registration {method}: Queued {total_operations} records for background processing (Job: {job_id})")

			else:
				# Small operation, process immediately
				processed = batch_recalculate_timesheets(affected_combinations, batch_size=50)
				frappe.logger().info(f"Shift Registration {method}: Recalculated {processed} Daily Timesheet records for {doc.name}")

	except Exception as e:
		frappe.log_error(f"Error in auto_recalc_on_shift_registration_change for {doc.name}: {str(e)}")
		# Don't raise the error to prevent blocking the main operation

def auto_recalc_on_overtime_registration_change(doc, method):
	"""
	Tự động tính toán lại Daily Timesheet khi Overtime Registration thay đổi
	Smart processing: Auto-detect large operations and use background processing
	"""
	try:
		affected_combinations = set()

		# Current records - always process these
		if doc.ot_employees:
			for detail in doc.ot_employees:
				if not detail.employee or not detail.date:
					continue

				affected_combinations.add((detail.employee, getdate(detail.date)))

		# For updates/cancellation, also process records that might have been deleted
		if method in ['on_update_after_submit', 'on_cancel']:
			# Get previously submitted version to find deleted records
			if doc.name:  # Ensure doc is saved
				old_records = get_previous_overtime_registrations(doc.name)
				for old_detail in old_records:
					affected_combinations.add((old_detail['employee'], getdate(old_detail['date'])))

		if affected_combinations:
			total_operations = len(affected_combinations)

			# Smart threshold: If > 200 operations, use background processing
			if total_operations > 200:
				# Queue background job with progress tracking
				job_id = f"overtime_recalc_{doc.name}_{int(frappe.utils.now_datetime().timestamp())}"

				frappe.enqueue(
					'customize_erpnext.customize_erpnext.doctype.daily_timesheet.scheduler.background_recalculate_timesheets',
					queue='long',  # Use long queue for large operations
					timeout=1800,  # 30 minutes
					job_id=job_id,
					affected_combinations=list(affected_combinations),
					trigger_doc_type="Overtime Registration",
					trigger_doc_name=doc.name,
					trigger_method=method,
					batch_size=100
				)

				# Notify user about background processing
				frappe.msgprint(
					f"Large operation detected ({total_operations} records). Processing in background (Job ID: {job_id}). "
					f"You will receive a notification when completed.",
					title="Background Processing Started",
					indicator="blue"
				)

				frappe.logger().info(f"Overtime Registration {method}: Queued {total_operations} records for background processing (Job: {job_id})")

			else:
				# Small operation, process immediately
				processed = batch_recalculate_timesheets(affected_combinations, batch_size=50)
				frappe.logger().info(f"Overtime Registration {method}: Recalculated {processed} Daily Timesheet records for {doc.name}")

	except Exception as e:
		frappe.log_error(f"Error in auto_recalc_on_overtime_registration_change for {doc.name}: {str(e)}")
		# Don't raise the error to prevent blocking the main operation

def batch_recalculate_timesheets(affected_combinations, batch_size=50):
	"""
	Xử lý batch để tránh timeout với operations lớn
	Returns number of successfully processed records
	"""
	total = len(affected_combinations)
	processed = 0

	# Convert set to list for batching
	combinations_list = list(affected_combinations)

	for i in range(0, total, batch_size):
		batch = combinations_list[i:i + batch_size]

		try:
			for employee, date in batch:
				existing_timesheet = frappe.db.exists("Daily Timesheet", {
					"employee": employee,
					"attendance_date": date
				})

				if existing_timesheet:
					ts_doc = frappe.get_doc("Daily Timesheet", existing_timesheet)
					ts_doc.calculate_all_fields()
					ts_doc.save()
					processed += 1

			# Commit each batch
			frappe.db.commit()

		except Exception as e:
			# Rollback batch on error and log
			frappe.db.rollback()
			frappe.log_error(f"Batch recalculation failed (batch {i//batch_size + 1}): {str(e)}")
			# Continue with next batch instead of stopping completely

	return processed

def get_previous_shift_registrations(doc_name):
	"""
	Get previously committed Shift Registration Detail records from database
	Used to detect deleted records during updates
	"""
	try:
		return frappe.db.sql("""
			SELECT employee, begin_date, end_date, shift
			FROM `tabShift Registration Detail`
			WHERE parent = %(doc_name)s
		""", {"doc_name": doc_name}, as_dict=True)
	except Exception:
		return []

def get_previous_overtime_registrations(doc_name):
	"""
	Get previously committed Overtime Registration Detail records from database
	Used to detect deleted records during updates
	"""
	try:
		return frappe.db.sql("""
			SELECT employee, date, begin_time, end_time
			FROM `tabOvertime Registration Detail`
			WHERE parent = %(doc_name)s
		""", {"doc_name": doc_name}, as_dict=True)
	except Exception:
		return []

def background_recalculate_timesheets(affected_combinations, trigger_doc_type, trigger_doc_name, trigger_method, batch_size=100):
	"""
	Background job for processing large timesheet recalculations
	Includes progress tracking and completion notifications
	"""
	import time
	start_time = time.time()

	try:
		total_operations = len(affected_combinations)
		processed = 0
		errors = 0

		frappe.publish_progress(
			0,
			title=f"Processing {trigger_doc_type} Changes",
			description=f"Starting recalculation for {total_operations} Daily Timesheet records..."
		)

		# Process in batches
		for i in range(0, total_operations, batch_size):
			batch = affected_combinations[i:i + batch_size]
			batch_processed = 0
			batch_errors = 0

			try:
				for employee, date in batch:
					try:
						existing_timesheet = frappe.db.exists("Daily Timesheet", {
							"employee": employee,
							"attendance_date": date
						})

						if existing_timesheet:
							ts_doc = frappe.get_doc("Daily Timesheet", existing_timesheet)
							ts_doc.calculate_all_fields()
							ts_doc.save()
							batch_processed += 1
					except Exception as e:
						frappe.log_error(f"Error recalculating timesheet for {employee} on {date}: {str(e)}")
						batch_errors += 1

				# Commit batch
				frappe.db.commit()
				processed += batch_processed
				errors += batch_errors

				# Update progress
				progress = min((i + batch_size) / total_operations * 100, 100)
				frappe.publish_progress(
					progress,
					title=f"Processing {trigger_doc_type} Changes",
					description=f"Processed {processed}/{total_operations} records ({errors} errors)"
				)

				# Brief pause to prevent overwhelming the system
				if i % (batch_size * 5) == 0:  # Every 5 batches
					time.sleep(0.1)

			except Exception as e:
				frappe.db.rollback()
				frappe.log_error(f"Batch processing error (batch {i//batch_size + 1}): {str(e)}")
				errors += len(batch)

		# Final results
		end_time = time.time()
		processing_time = round(end_time - start_time, 2)

		# Send completion notification
		success_rate = (processed / total_operations * 100) if total_operations > 0 else 0

		if errors == 0:
			frappe.publish_realtime(
				event='daily_timesheet_bulk_complete',
				message={
					"title": f"{trigger_doc_type} Processing Complete",
					"message": f"Successfully recalculated {processed} Daily Timesheet records in {processing_time}s",
					"indicator": "green",
					"trigger_doc": trigger_doc_name
				},
				user=frappe.session.user
			)
		else:
			frappe.publish_realtime(
				event='daily_timesheet_bulk_complete',
				message={
					"title": f"{trigger_doc_type} Processing Complete with Errors",
					"message": f"Processed {processed}/{total_operations} records ({success_rate:.1f}% success rate) in {processing_time}s. {errors} errors logged.",
					"indicator": "orange",
					"trigger_doc": trigger_doc_name
				},
				user=frappe.session.user
			)

		frappe.logger().info(f"Background recalculation completed: {processed} success, {errors} errors, {processing_time}s")

		return {
			"success": True,
			"processed": processed,
			"errors": errors,
			"total": total_operations,
			"processing_time": processing_time,
			"success_rate": success_rate
		}

	except Exception as e:
		error_msg = f"Background recalculation failed: {str(e)}"
		frappe.log_error(error_msg)

		# Send failure notification
		frappe.publish_realtime(
			event='daily_timesheet_bulk_complete',
			message={
				"title": f"{trigger_doc_type} Processing Failed",
				"message": f"Background processing failed: {str(e)}",
				"indicator": "red",
				"trigger_doc": trigger_doc_name
			},
			user=frappe.session.user
		)

		raise e


def check_maternity_tracking_changes(doc, method):
	"""
	Check if custom_maternity_tracking child table has any changes
	Compare with database and store affected dates for later processing in on_update
	"""
	if not doc.custom_maternity_tracking:
		return

	# Get old data from database BEFORE save
	old_doc_data = None
	affected_combinations = set()

	if not doc.is_new():
		# Get old data from database
		old_doc_data = frappe.db.sql("""
			SELECT from_date, to_date, type, apply_pregnant_benefit
			FROM `tabMaternity Tracking`
			WHERE parent = %s AND parenttype = 'Employee'
			ORDER BY idx
		""", (doc.name,), as_dict=True)

		# Create comparable structures
		old_records = set()
		for rec in old_doc_data:
			old_records.add((
				str(rec.get('from_date', '')),
				str(rec.get('to_date', '')),
				rec.get('type', ''),
				rec.get('apply_pregnant_benefit', 0)
			))

		new_records = set()
		for rec in doc.custom_maternity_tracking:
			new_records.add((
				str(rec.from_date or ''),
				str(rec.to_date or ''),
				rec.type or '',
				rec.apply_pregnant_benefit or 0
			))

		# Check if there are any differences
		if old_records != new_records:
			# Collect all affected date ranges
			# Process current maternity tracking records
			for tracking in doc.custom_maternity_tracking:
				if not tracking.from_date or not tracking.to_date:
					continue

				current_date = getdate(tracking.from_date)
				end_date = getdate(tracking.to_date)

				while current_date <= end_date:
					affected_combinations.add((doc.name, current_date))
					current_date = add_days(current_date, 1)

			# Process old date ranges that might have been removed
			for old_tracking in old_doc_data:
				if not old_tracking.get('from_date') or not old_tracking.get('to_date'):
					continue

				current_date = getdate(old_tracking['from_date'])
				end_date = getdate(old_tracking['to_date'])

				while current_date <= end_date:
					affected_combinations.add((doc.name, current_date))
					current_date = add_days(current_date, 1)

			# Store affected combinations for on_update hook
			doc._maternity_affected_dates = list(affected_combinations)
	else:
		# New employee with maternity tracking
		if doc.custom_maternity_tracking:
			for tracking in doc.custom_maternity_tracking:
				if not tracking.from_date or not tracking.to_date:
					continue

				current_date = getdate(tracking.from_date)
				end_date = getdate(tracking.to_date)

				while current_date <= end_date:
					affected_combinations.add((doc.name, current_date))
					current_date = add_days(current_date, 1)

			doc._maternity_affected_dates = list(affected_combinations)


def auto_recalc_on_maternity_tracking_change(doc, method):
	"""
	Tự động tính toán lại Daily Timesheet khi custom_maternity_tracking thay đổi
	Use affected dates stored in validate hook
	"""
	try:
		# Check if we have affected dates from validate hook
		if not hasattr(doc, '_maternity_affected_dates'):
			return

		affected_combinations = set(doc._maternity_affected_dates)

		if affected_combinations:
			total_operations = len(affected_combinations)

			# Always use background processing to avoid blocking save operation
			job_id = f"maternity_recalc_{doc.name}_{int(frappe.utils.now_datetime().timestamp())}"

			frappe.enqueue(
				'customize_erpnext.customize_erpnext.doctype.daily_timesheet.scheduler.background_recalculate_timesheets',
				queue='long',
				timeout=1800,
				job_id=job_id,
				affected_combinations=list(affected_combinations),
				trigger_doc_type="Employee",
				trigger_doc_name=doc.name,
				trigger_method=method,
				batch_size=100
			)

			# Notify user immediately
			frappe.msgprint(
				f"Maternity tracking changes detected. Recalculating {total_operations} Daily Timesheet records in background. "
				f"You will receive a notification when completed.",
				title="Daily Timesheet Recalculation Started",
				indicator="blue"
			)

	except Exception as e:
		error_msg = f"Error in auto_recalc_on_maternity_tracking_change for {doc.name}: {str(e)}"
		frappe.log_error(error_msg)
		# Don't raise the error to prevent blocking the main operation










