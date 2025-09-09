# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import today, add_days, getdate
from datetime import datetime
import logging

def daily_timesheet_auto_sync_and_calculate():
	"""
	Scheduled job to automatically sync and calculate Daily Timesheet at 21:00 daily
	"""
	try:
		# Get today's date
		current_date = today()
		
		# Log start of process
		frappe.logger().info(f"Starting Daily Timesheet auto sync for date: {current_date}")
		
		# Get all employees who have check-ins today but no Daily Timesheet record
		employees_without_timesheet = get_employees_needing_sync(current_date)
		
		created_count = 0
		updated_count = 0
		
		# Create Daily Timesheet for employees without records
		for emp_data in employees_without_timesheet:
			try:
				create_daily_timesheet_record(emp_data['employee'], current_date)
				created_count += 1
			except Exception as e:
				frappe.log_error(f"Failed to create Daily Timesheet for {emp_data['employee']}: {str(e)}")
		
		# Update all existing Daily Timesheet records for today
		existing_timesheets = frappe.get_all("Daily Timesheet", 
			filters={"attendance_date": current_date},
			fields=["name"]
		)
		
		for ts in existing_timesheets:
			try:
				doc = frappe.get_doc("Daily Timesheet", ts.name)
				# Always sync - no need for auto_sync_enabled check
				doc.calculate_all_fields()
				doc.save()
				updated_count += 1
			except Exception as e:
				frappe.log_error(f"Failed to update Daily Timesheet {ts.name}: {str(e)}")
		
		# Log completion
		frappe.logger().info(f"Daily Timesheet sync completed. Created: {created_count}, Updated: {updated_count}")
		
		return {"created": created_count, "updated": updated_count}
		
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
	From 26th of previous month to 25th of current month
	Runs at 22:00 on 25th of every month
	"""
	try:
		from datetime import date
		
		# Calculate period dates
		today_date = date.today()
		current_month = today_date.month
		current_year = today_date.year
		
		# Period: 26th previous month to 25th current month
		if current_month == 1:
			prev_month = 12
			prev_year = current_year - 1
		else:
			prev_month = current_month - 1
			prev_year = current_year
			
		from_date = f"{prev_year}-{prev_month:02d}-26"
		to_date = f"{current_year}-{current_month:02d}-25"
		
		frappe.logger().info(f"Starting monthly timesheet recalculation for period: {from_date} to {to_date}")
		
		# Get all Daily Timesheet records in period
		timesheet_records = frappe.get_all(
			"Daily Timesheet",
			filters={
				"attendance_date": ["between", [from_date, to_date]]
			},
			fields=["name", "employee", "attendance_date"],
			order_by="attendance_date, employee"
		)
		
		total_records = len(timesheet_records)
		frappe.logger().info(f"Found {total_records} timesheet records to recalculate")
		
		if total_records == 0:
			frappe.logger().info("No timesheet records found for the period")
			return {"status": "completed", "processed": 0, "errors": 0}
		
		# Process in batches to avoid memory issues
		batch_size = 100
		processed = 0
		errors = 0
		
		for i in range(0, total_records, batch_size):
			batch = timesheet_records[i:i + batch_size]
			
			for record in batch:
				try:
					# Get and recalculate timesheet record
					doc = frappe.get_doc("Daily Timesheet", record.name)
					
					# Recalculate all fields
					doc.calculate_all_fields()
					doc.save()
					
					processed += 1
					
					# Log progress every 50 records
					if processed % 50 == 0:
						frappe.logger().info(f"Monthly recalculation progress: {processed}/{total_records}")
					
				except Exception as e:
					errors += 1
					frappe.log_error(f"Error recalculating Daily Timesheet {record.name}: {str(e)}")
			
			# Commit batch to database
			frappe.db.commit()
			frappe.logger().info(f"Processed batch {i//batch_size + 1}/{(total_records-1)//batch_size + 1}: {len(batch)} records")
		
		# Final summary
		frappe.logger().info(f"Monthly recalculation completed: {processed} success, {errors} errors")
		
		# Send notification if there were errors
		if errors > 0:
			try:
				frappe.sendmail(
					recipients=["hr@tiqn.com.vn"],
					subject=f"Monthly Timesheet Recalculation - Completed with {errors} Errors",
					message=f"""
					<h3>Monthly Timesheet Recalculation Summary</h3>
					<p><strong>Period:</strong> {from_date} to {to_date}</p>
					<p><strong>Total Records:</strong> {total_records}</p>
					<p><strong>Successfully Processed:</strong> {processed}</p>
					<p><strong>Errors:</strong> {errors}</p>
					<br>
					<p>Please check the Error Log for details of failed records.</p>
					"""
				)
			except Exception as e:
				frappe.logger().error(f"Failed to send error notification email: {str(e)}")
		else:
			frappe.logger().info("Monthly recalculation completed successfully with no errors")
			
		return {
			"status": "completed", 
			"period": f"{from_date} to {to_date}",
			"total_records": total_records,
			"processed": processed, 
			"errors": errors
		}
			
	except Exception as e:
		error_msg = f"Monthly timesheet recalculation failed: {str(e)}"
		frappe.log_error(error_msg)
		frappe.logger().error(error_msg)
		
		# Send critical error notification
		try:
			frappe.sendmail(
				recipients=["hr@tiqn.com.vn", "it@tiqn.com.vn"],
				subject="Monthly Timesheet Recalculation - CRITICAL FAILURE",
				message=f"""
				<h3>Monthly Timesheet Recalculation Failed</h3>
				<p><strong>Error:</strong> {str(e)}</p>
				<p><strong>Time:</strong> {datetime.now()}</p>
				<br>
				<p style="color: red;">Please check the system immediately and run manual recalculation if needed.</p>
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