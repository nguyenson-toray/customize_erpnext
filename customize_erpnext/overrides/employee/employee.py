# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, getdate, today
import json


def check_maternity_tracking_changes_for_attendance(doc, method):
	"""
	Check if custom_maternity_tracking child table has any changes
	Compare with database and store affected dates for later processing in on_update
	Called in validate hook
	"""
	if not doc.custom_maternity_tracking:
		return

	# Get old data from database BEFORE save
	old_doc_data = None
	affected_dates = set()

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
			# Skip deleted rows
			if hasattr(rec, '__deleted') or hasattr(rec, '__isdeleted'):
				if getattr(rec, '__deleted', False) or getattr(rec, '__isdeleted', False):
					continue

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
				# Skip deleted rows
				if hasattr(tracking, '__deleted') or hasattr(tracking, '__isdeleted'):
					if getattr(tracking, '__deleted', False) or getattr(tracking, '__isdeleted', False):
						continue

				if not tracking.from_date or not tracking.to_date:
					continue

				current_date = getdate(tracking.from_date)
				end_date = getdate(tracking.to_date)

				# Limit to today if end_date is in the future
				today_date = getdate(today())
				if end_date > today_date:
					end_date = today_date

				# Limit to relieving date if employee has left
				if doc.relieving_date:
					relieving = getdate(doc.relieving_date)
					# relieving_date is when employee LEFT, so last working day is relieving_date - 1
					last_working_day = add_days(relieving, -1)
					if end_date > last_working_day:
						end_date = last_working_day

				while current_date <= end_date:
					affected_dates.add(str(current_date))
					current_date = add_days(current_date, 1)

			# Process old date ranges that might have been removed
			for old_tracking in old_doc_data:
				if not old_tracking.get('from_date') or not old_tracking.get('to_date'):
					continue

				current_date = getdate(old_tracking['from_date'])
				end_date = getdate(old_tracking['to_date'])

				# Same limits as above
				today_date = getdate(today())
				if end_date > today_date:
					end_date = today_date

				if doc.relieving_date:
					relieving = getdate(doc.relieving_date)
					last_working_day = add_days(relieving, -1)
					if end_date > last_working_day:
						end_date = last_working_day

				while current_date <= end_date:
					affected_dates.add(str(current_date))
					current_date = add_days(current_date, 1)

			# Store affected dates for on_update hook
			doc._maternity_affected_dates = list(affected_dates)
	else:
		# New employee with maternity tracking
		if doc.custom_maternity_tracking:
			for tracking in doc.custom_maternity_tracking:
				if not tracking.from_date or not tracking.to_date:
					continue

				current_date = getdate(tracking.from_date)
				end_date = getdate(tracking.to_date)

				# Same limits
				today_date = getdate(today())
				if end_date > today_date:
					end_date = today_date

				if doc.relieving_date:
					relieving = getdate(doc.relieving_date)
					last_working_day = add_days(relieving, -1)
					if end_date > last_working_day:
						end_date = last_working_day

				while current_date <= end_date:
					affected_dates.add(str(current_date))
					current_date = add_days(current_date, 1)

			doc._maternity_affected_dates = list(affected_dates)


def auto_update_attendance_on_maternity_change(doc, method):
	"""
	Automatically update Attendance when custom_maternity_tracking changes
	Uses affected dates stored in validate hook
	Queues background job for processing
	"""
	try:
		# Check if we have affected dates from validate hook
		if not hasattr(doc, '_maternity_affected_dates'):
			return

		affected_dates = doc._maternity_affected_dates

		if not affected_dates or len(affected_dates) == 0:
			return

		# Calculate date range
		affected_dates_sorted = sorted([getdate(d) for d in affected_dates])
		from_date = str(affected_dates_sorted[0])
		to_date = str(affected_dates_sorted[-1])

		total_days = len(affected_dates)

		# Queue background job to update attendance
		job_id = f"maternity_attendance_{doc.name}_{int(frappe.utils.now_datetime().timestamp())}"

		frappe.enqueue(
			'customize_erpnext.overrides.employee.employee.background_update_attendance_for_maternity',
			queue='long',
			timeout=1800,  # 30 minutes
			job_id=job_id,
			employee=doc.name,
			from_date=from_date,
			to_date=to_date,
			total_days=total_days
		)

		# Notify user with msgprint
		frappe.msgprint(
			msg=f'Maternity period changed ➡️ Updating attendance for {total_days} days ({from_date} to {to_date})...',
			title='Attendance Update',
			indicator='blue'
		)

		frappe.logger().info(
			f"Maternity tracking changed for employee {doc.name}. "
			f"Queued background job to update attendance for {total_days} days ({from_date} to {to_date}). "
			f"Job ID: {job_id}"
		)

	except Exception as e:
		error_msg = f"Error in auto_update_attendance_on_maternity_change for {doc.name}: {str(e)}"
		frappe.log_error(error_msg, "Maternity Tracking Attendance Update Error")
		# Don't raise the error to prevent blocking the main operation


def background_update_attendance_for_maternity(employee, from_date, to_date, total_days):
	"""
	Background job for updating attendance when maternity tracking changes
	Calls the optimized bulk_update_attendance_optimized function
	"""
	import time
	start_time = time.time()

	try:
		frappe.logger().info(
			f"Background attendance update started for employee {employee} "
			f"from {from_date} to {to_date} ({total_days} days)"
		)

		# Import the optimized bulk update function
		from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized

		# Call the bulk update function with force_sync=1
		result = bulk_update_attendance_optimized(
			from_date=from_date,
			to_date=to_date,
			employees=json.dumps([employee]),
			force_sync=1
		)

		# Extract results
		end_time = time.time()
		processing_time = round(end_time - start_time, 2)

		# Log results (no user notification needed - runs silently in background)
		if result and result.get('status') == 'success':
			stats = result.get('stats', {})
			new_attendance = stats.get('new_attendance', 0)
			updated_attendance = stats.get('updated_attendance', 0)

			frappe.logger().info(
				f"Background attendance update completed for {employee}. "
				f"Created: {new_attendance}, Updated: {updated_attendance} in {processing_time}s"
			)
		else:
			# Error occurred
			error_message = result.get('message', 'Unknown error') if result else 'No response from update function'

			frappe.logger().error(
				f"Background attendance update failed for {employee}: {error_message}"
			)

		return result

	except Exception as e:
		error_msg = f"Background attendance update failed for employee {employee}: {str(e)}"
		frappe.log_error(error_msg, "Maternity Attendance Update Background Job Error")
		# No user notification needed - error logged for admin review
		raise e
