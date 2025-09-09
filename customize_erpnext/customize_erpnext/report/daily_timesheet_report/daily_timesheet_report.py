# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, add_days, get_first_day, get_last_day, formatdate
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

# Constant for decimal rounding precision
DECIMAL_ROUND_NUMBER = 2

def decimal_round(value, places=DECIMAL_ROUND_NUMBER):
	"""Làm tròn số sử dụng decimal để đồng nhất với JavaScript"""
	if value is None:
		return 0.0
	try:
		decimal_value = Decimal(str(value))
		# Tạo pattern cho số chữ số thập phân
		if places == 1:
			pattern = Decimal('0.1')
		elif places == 2:
			pattern = Decimal('0.01')
		else:
			pattern = Decimal('0.' + '0' * (places - 1) + '1')
		
		return float(decimal_value.quantize(pattern, rounding=ROUND_HALF_UP))
	except (ValueError, TypeError):
		return 0.0


def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)
	
	return columns, data, None, None


def get_columns(filters=None):
	is_summary = filters and filters.get("summary")
	show_detail_columns = filters and filters.get("detail_columns")
	
	# Debug: Check if we're in single date mode and not summary mode
	is_single_date = filters and filters.get("date_type") == "Single Date"
	
	# Base columns - always shown
	columns = [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 110
		},
		{
			"fieldname": "employee_name",
			"label": _("Employee Name"),
			"fieldtype": "Data",
			"width": 170
		},
		{
			"fieldname": "custom_group",
			"label": _("Group"),
			"fieldtype": "Data",
			"width": 110
		}
	]
	
	# Add date column only if not summary
	if not is_summary:
		columns.extend([
			{
				"fieldname": "attendance_date",
				"label": _("Attendance Date"),
				"fieldtype": "Date",
				"width": 100
			},
			{
				"fieldname": "shift",
				"label": _("Shift"),
				"fieldtype": "Link",
				"options": "Shift Type",
				"width": 70
			}
		])
	
	# Department, Section columns - only when Detail Columns checked
	if show_detail_columns:
		columns.extend([
			{
				"fieldname": "department",
				"label": _("Department"),
				"fieldtype": "Link",
				"options": "Department",
				"width": 120
			},
			{
				"fieldname": "custom_section",
				"label": _("Section"),
				"fieldtype": "Data",
				"width": 100
			}
		])
	
	# Check in/out columns - always shown when not summary mode
	if not is_summary:
		columns.extend([
			{
				"fieldname": "check_in",
				"label": _("Check In"),
				"fieldtype": "Data",
				"width": 90
			},
			{
				"fieldname": "check_out",
				"label": _("Check Out"),
				"fieldtype": "Data",
				"width": 90
			}
		])
	
	# Core hour columns - always shown
	columns.extend([
		{
			"fieldname": "working_hours",
			"label": _("Working Hours"),
			"fieldtype": "Float",
			"precision": DECIMAL_ROUND_NUMBER,
			"width": 100
		}
	])
	
	# Working Day column - only in summary mode
	if is_summary:
		columns.append({
			"fieldname": "working_day",
			"label": _("Working Day"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 100,
			"description": _("Working Hours / 8")
		})
	
	# Basic overtime columns - always shown
	columns.extend([
		{
			"fieldname": "actual_overtime",
			"label": _("Actual OT"),
			"fieldtype": "Float",
			"precision": DECIMAL_ROUND_NUMBER,
			"width": 90
		},
		{
			"fieldname": "approved_overtime",
			"label": _("Registered OT"),
			"fieldtype": "Float",
			"precision": DECIMAL_ROUND_NUMBER,
			"width": 100
		},
		{
			"fieldname": "overtime_hours",
			"label": _("Final OT"),
			"fieldtype": "Float",
			"precision": DECIMAL_ROUND_NUMBER,
			"width": 90
		}
	])
	
	# Detail columns controlled by Detail Columns checkbox
	if show_detail_columns:
		columns.extend([
			{
				"fieldname": "overtime_coefficient",
				"label": _("Overtime Coefficient"),
				"fieldtype": "Float",
				"precision": DECIMAL_ROUND_NUMBER,
				"width": 130
			},
			{
				"fieldname": "final_ot_with_coefficient",
				"label": _("Final OT - With Coefficient"),
				"fieldtype": "Float",
				"precision": DECIMAL_ROUND_NUMBER,
				"width": 160
			}
		])
		
		# Status columns - only when Detail Columns checked and not summary
		if not is_summary:
			columns.extend([
				{
					"fieldname": "late_entry",
					"label": _("Late Entry"),
					"fieldtype": "Check",
					"width": 80
				},
				{
					"fieldname": "early_exit",
					"label": _("Early Exit"),
					"fieldtype": "Check",
					"width": 80
				},
				{
					"fieldname": "maternity_benefit",
					"label": _("Maternity Benefit"),
					"fieldtype": "Check",
					"width": 110
				}
			])
	
	# Other detail columns - only when Detail Columns checked
	if show_detail_columns and not is_summary:
		columns.extend([
			{
				"fieldname": "shift_determined_by",
				"label": _("Shift Determined By"),
				"fieldtype": "Data",
				"width": 100
			}
		])
	
	# Employee date columns - only if detail_columns=true
	if show_detail_columns:
		columns.extend([
			{
				"fieldname": "date_of_joining",
				"label": _("Date of Joining"),
				"fieldtype": "Date",
				"width": 100
			},
			{
				"fieldname": "relieving_date",
				"label": _("Relieving Date"),
				"fieldtype": "Date",
				"width": 100
			}
		])
	
	# Status column - always shown  
	if not is_summary:
		columns.append({
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 110
		})
	
	# ID column - always shown at the end
	if not is_summary:
		columns.append({
			"fieldname": "name",
			"label": _("ID"),
			"fieldtype": "Link",
			"options": "Daily Timesheet",
			"width": 120
		})
	
	return columns


def get_data(filters):
	is_summary = filters and filters.get("summary")
	show_detail_columns = filters and filters.get("detail_columns")
	show_zero = filters and filters.get("show_zero", 1)  # Default to True (1)
	
	# Get date range conditions for filtering active employees
	date_conditions = get_date_range_conditions(filters)
	employee_conditions = get_employee_filter_conditions(filters)
	
	if is_summary:
		# Summary mode - Show active employees + inactive employees with timesheet data
		employee_fields = ""
		if show_detail_columns:
			employee_fields = ", emp.date_of_joining, emp.relieving_date"
		
		if show_zero:
			# Show all employees who were active during any part of the period + employees with timesheet data
			
			# Calculate period dates
			if filters.get("date_type") == "Single Date" and filters.get("single_date"):
				period_start = filters.get('single_date')
				period_end = filters.get('single_date')
			elif filters.get("date_type") == "Date Range":
				period_start = filters.get("from_date", "1900-01-01")
				period_end = filters.get("to_date", "2099-12-31")
			elif filters.get("date_type") == "Monthly" and filters.get("month") and filters.get("year"):
				month = int(filters.get("month"))
				year = int(filters.get("year"))
				if month == 1:
					prev_month = 12
					prev_year = year - 1
				else:
					prev_month = month - 1
					prev_year = year
				period_start = f"{prev_year}-{prev_month:02d}-26"
				period_end = f"{year}-{month:02d}-25"
			else:
				period_start = "1900-01-01"
				period_end = "2099-12-31"
			
			# Get all employees who were active during the period + employees with timesheet data
			data = frappe.db.sql(f"""
				SELECT
					emp.name as employee,
					emp.employee_name,
					emp.department,
					emp.custom_section,
					emp.custom_group,
					COALESCE(SUM(dt.working_hours), 0) as working_hours,
					COALESCE(SUM(dt.actual_overtime), 0) as actual_overtime,
					COALESCE(SUM(dt.approved_overtime), 0) as approved_overtime,
					COALESCE(SUM(dt.overtime_hours), 0) as overtime_hours,
					COALESCE(SUM(dt.working_hours + dt.overtime_hours), 0) as total_hours
					{employee_fields}
				FROM `tabEmployee` emp
				LEFT JOIN `tabDaily Timesheet` dt ON emp.name = dt.employee 
					AND ({date_conditions if date_conditions else '1=1'})
				WHERE (
					-- Show employees who were active during any part of the period
					((emp.date_of_joining IS NULL OR emp.date_of_joining <= '{period_end}')
					 AND (emp.relieving_date IS NULL OR emp.relieving_date >= '{period_start}'))
					OR 
					-- Show employees with timesheet data in the period
					(emp.name IN (
						SELECT DISTINCT employee 
						FROM `tabDaily Timesheet` 
						WHERE ({date_conditions if date_conditions else '1=1'})
					))
				)
				{employee_conditions}
				GROUP BY emp.name, emp.employee_name, emp.department, emp.custom_section, emp.custom_group
				{', emp.date_of_joining, emp.relieving_date' if show_detail_columns else ''}
				ORDER BY emp.name
			""", filters, as_dict=1)
		else:
			# Show only employees with timesheet data (existing behavior when Show Zero is off)
			data = frappe.db.sql(f"""
				SELECT
					emp.name as employee,
					emp.employee_name,
					emp.department,
					emp.custom_section,
					emp.custom_group,
					COALESCE(SUM(dt.working_hours), 0) as working_hours,
					COALESCE(SUM(dt.actual_overtime), 0) as actual_overtime,
					COALESCE(SUM(dt.approved_overtime), 0) as approved_overtime,
					COALESCE(SUM(dt.overtime_hours), 0) as overtime_hours,
					COALESCE(SUM(dt.working_hours + dt.overtime_hours), 0) as total_hours
					{employee_fields}
				FROM `tabEmployee` emp
				INNER JOIN `tabDaily Timesheet` dt ON emp.name = dt.employee 
					AND ({date_conditions if date_conditions else '1=1'})
				WHERE 1=1
				{employee_conditions}
				GROUP BY emp.name, emp.employee_name, emp.department, emp.custom_section, emp.custom_group
				{', emp.date_of_joining, emp.relieving_date' if show_detail_columns else ''}
				ORDER BY emp.name
			""", filters, as_dict=1)
		
		# Apply decimal rounding to summary data and calculate working_day + coefficients
		for row in data:
			working_hours = decimal_round(row.get('working_hours'))
			row['working_hours'] = working_hours
			row['working_day'] = decimal_round(working_hours / 8, 2) if working_hours else 0.0
			row['actual_overtime'] = decimal_round(row.get('actual_overtime'))
			row['approved_overtime'] = decimal_round(row.get('approved_overtime'))
			row['overtime_hours'] = decimal_round(row.get('overtime_hours'))
			row['total_hours'] = decimal_round(row.get('total_hours'))
			
			# Calculate final_ot_with_coefficient by summing individual daily calculations
			employee = row.get('employee')
			if employee:
				# Get all records for this employee in the date range to calculate coefficient total
				individual_records = frappe.db.sql(f"""
					SELECT dt.overtime_hours, dt.overtime_coefficient, dt.final_ot_with_coefficient
					FROM `tabDaily Timesheet` dt
					WHERE dt.employee = %(employee)s AND ({date_conditions if date_conditions else '1=1'})
				""", dict(filters, employee=employee), as_dict=1)
				
				total_final_ot_with_coeff = sum([
					decimal_round((r.get('overtime_hours') or 0) * (r.get('overtime_coefficient') or 1.5))
					for r in individual_records
				])
				
				row['final_ot_with_coefficient'] = decimal_round(total_final_ot_with_coeff)
				
				# For coefficient, show average (for display purposes)
				if individual_records:
					avg_coefficient = sum([r.get('overtime_coefficient') or 1.5 for r in individual_records]) / len(individual_records)
					row['overtime_coefficient'] = decimal_round(avg_coefficient)
				else:
					row['overtime_coefficient'] = 1.5
	else:
		# Detail mode - show individual records
		if show_zero:
			# Show all employees who were active during any part of the period + employees with timesheet data
			
			# Calculate period dates (same logic as summary mode)
			if filters.get("date_type") == "Single Date" and filters.get("single_date"):
				period_start = filters.get('single_date')
				period_end = filters.get('single_date')
			elif filters.get("date_type") == "Date Range":
				period_start = filters.get("from_date", "1900-01-01")
				period_end = filters.get("to_date", "2099-12-31")
			elif filters.get("date_type") == "Monthly" and filters.get("month") and filters.get("year"):
				month = int(filters.get("month"))
				year = int(filters.get("year"))
				if month == 1:
					prev_month = 12
					prev_year = year - 1
				else:
					prev_month = month - 1
					prev_year = year
				period_start = f"{prev_year}-{prev_month:02d}-26"
				period_end = f"{year}-{month:02d}-25"
			else:
				period_start = "1900-01-01"
				period_end = "2099-12-31"
			
			# Get all employees who were active during the period + employees with timesheet/attendance data
			# Use UNION to combine timesheet records with attendance-only records
			data = frappe.db.sql(f"""
				(
					SELECT
						emp.name as employee,
						emp.employee_name,
						emp.department,
						emp.custom_section,
						emp.custom_group,
						dt.attendance_date,
						dt.shift,
						dt.shift_determined_by,
						dt.check_in,
						dt.check_out,
						COALESCE(dt.working_hours, 0) as working_hours,
						COALESCE(dt.actual_overtime, 0) as actual_overtime,
						COALESCE(dt.approved_overtime, 0) as approved_overtime,
						COALESCE(dt.overtime_hours, 0) as overtime_hours,
						COALESCE(dt.overtime_coefficient, 1.5) as overtime_coefficient,
						COALESCE(dt.final_ot_with_coefficient, 0) as final_ot_with_coefficient,
						COALESCE(dt.working_hours + dt.overtime_hours, 0) as total_hours,
						dt.late_entry,
						dt.early_exit,
						dt.maternity_benefit,
						dt.status,
						emp.date_of_joining,
						emp.relieving_date,
						dt.name,
						'timesheet' as source_type
					FROM `tabEmployee` emp
					INNER JOIN `tabDaily Timesheet` dt ON emp.name = dt.employee 
						AND (dt.docstatus <= 1) 
						AND ({date_conditions if date_conditions else '1=1'})
					WHERE (
						-- Show employees who were active during any part of the period
						((emp.date_of_joining IS NULL OR emp.date_of_joining <= '{period_end}')
						 AND (emp.relieving_date IS NULL OR emp.relieving_date >= '{period_start}'))
					)
					{employee_conditions}
				)
				UNION ALL
				(
					SELECT
						emp.name as employee,
						emp.employee_name,
						emp.department,
						emp.custom_section,
						emp.custom_group,
						att.attendance_date,
						att.shift,
						NULL as shift_determined_by,
						NULL as check_in,
						NULL as check_out,
						0 as working_hours,
						0 as actual_overtime,
						0 as approved_overtime,
						0 as overtime_hours,
						1.5 as overtime_coefficient,
						0 as final_ot_with_coefficient,
						0 as total_hours,
						att.late_entry,
						att.early_exit,
						NULL as maternity_benefit,
						att.status,
						emp.date_of_joining,
						emp.relieving_date,
						NULL as name,
						'attendance' as source_type
					FROM `tabEmployee` emp
					INNER JOIN `tabAttendance` att ON emp.name = att.employee 
						AND (att.docstatus <= 1) 
						AND ({date_conditions.replace('dt.attendance_date', 'att.attendance_date') if date_conditions else '1=1'})
					WHERE (
						-- Show employees who were active during any part of the period
						((emp.date_of_joining IS NULL OR emp.date_of_joining <= '{period_end}')
						 AND (emp.relieving_date IS NULL OR emp.relieving_date >= '{period_start}'))
					)
					{employee_conditions}
					-- Only include attendance records that don't have corresponding timesheet records
					AND NOT EXISTS (
						SELECT 1 FROM `tabDaily Timesheet` dt2 
						WHERE dt2.employee = emp.name 
						AND dt2.attendance_date = att.attendance_date
						AND (dt2.docstatus <= 1)
					)
				)
				ORDER BY attendance_date, employee
			""", filters, as_dict=1)
		else:
			# Show only employees with timesheet data (existing behavior when Show Zero is off)
			dt_conditions = ["dt.docstatus <= 1"]
			if date_conditions:
				dt_conditions.append(date_conditions)
			if employee_conditions:
				dt_conditions.append(employee_conditions.replace('emp.', 'dt.'))
			
			where_clause = " AND ".join(dt_conditions)
			
			data = frappe.db.sql(f"""
				SELECT
					dt.employee,
					dt.employee_name,
					dt.department,
					dt.custom_section,
					dt.custom_group,
					dt.attendance_date,
					dt.shift,
					dt.shift_determined_by,
					dt.check_in,
					dt.check_out,
					dt.working_hours,
					dt.actual_overtime,
					dt.approved_overtime,
					dt.overtime_hours,
					dt.overtime_coefficient,
					dt.final_ot_with_coefficient,
					(dt.working_hours + dt.overtime_hours) as total_hours,
					dt.late_entry,
					dt.early_exit,
					dt.maternity_benefit,
					dt.status,
					emp.date_of_joining,
					emp.relieving_date,
					dt.name
				FROM `tabDaily Timesheet` dt
				LEFT JOIN `tabEmployee` emp ON dt.employee = emp.name
				WHERE {where_clause}
				ORDER BY dt.attendance_date, dt.employee
			""", filters, as_dict=1)
		
		# Apply decimal rounding to detail data and format time
		for row in data:
			row['working_hours'] = decimal_round(row.get('working_hours'))
			row['actual_overtime'] = decimal_round(row.get('actual_overtime'))
			row['approved_overtime'] = decimal_round(row.get('approved_overtime'))
			row['overtime_hours'] = decimal_round(row.get('overtime_hours'))
			row['overtime_coefficient'] = decimal_round(row.get('overtime_coefficient'))
			
			# Calculate final_ot_with_coefficient for individual records
			overtime_hours = row.get('overtime_hours') or 0
			overtime_coefficient = row.get('overtime_coefficient') or 1.5
			row['final_ot_with_coefficient'] = decimal_round(overtime_hours * overtime_coefficient)
			
			row['total_hours'] = decimal_round(row.get('total_hours'))
			
			# Format check_in and check_out to show only time (HH:MM:SS)
			if row.get('check_in'):
				try:
					if hasattr(row['check_in'], 'strftime'):
						row['check_in'] = row['check_in'].strftime('%H:%M:%S')
					else:
						# Handle string datetime format
						check_in_str = str(row['check_in'])
						if ' ' in check_in_str:
							row['check_in'] = check_in_str.split(' ')[1]  # Get time part
						elif ':' in check_in_str:
							row['check_in'] = check_in_str  # Already time format
				except:
					pass  # Keep original value if formatting fails
					
			if row.get('check_out'):
				try:
					if hasattr(row['check_out'], 'strftime'):
						row['check_out'] = row['check_out'].strftime('%H:%M:%S')
					else:
						# Handle string datetime format
						check_out_str = str(row['check_out'])
						if ' ' in check_out_str:
							row['check_out'] = check_out_str.split(' ')[1]  # Get time part
						elif ':' in check_out_str:
							row['check_out'] = check_out_str  # Already time format
				except:
					pass  # Keep original value if formatting fails
	
	return data






def get_date_range_conditions(filters):
	"""Get SQL conditions for date range based on filter type"""
	conditions = []
	
	if filters.get("date_type") == "Single Date":
		if filters.get("single_date"):
			return f"dt.attendance_date = '{filters.get('single_date')}'"
	elif filters.get("date_type") == "Date Range":
		if filters.get("from_date"):
			conditions.append(f"dt.attendance_date >= '{filters.get('from_date')}'")
		if filters.get("to_date"):
			conditions.append(f"dt.attendance_date <= '{filters.get('to_date')}'")
		return " AND ".join(conditions) if conditions else "1=1"
	elif filters.get("date_type") == "Monthly":
		if filters.get("month") and filters.get("year"):
			month = int(filters.get("month"))
			year = int(filters.get("year"))
			
			# Calculate previous month for monthly range (26th to 25th)
			if month == 1:
				prev_month = 12
				prev_year = year - 1
			else:
				prev_month = month - 1
				prev_year = year
			
			from_date = f"{prev_year}-{prev_month:02d}-26"
			to_date = f"{year}-{month:02d}-25"
			
			return f"dt.attendance_date >= '{from_date}' AND dt.attendance_date <= '{to_date}'"
	
	return None


def get_employee_filter_conditions(filters):
	"""Get SQL conditions for employee filtering"""
	conditions = []
	
	if filters.get("department"):
		if isinstance(filters.get("department"), list):
			dept_list = "', '".join(filters.get("department"))
			conditions.append(f"emp.department IN ('{dept_list}')")
		else:
			conditions.append(f"emp.department = '{filters.get('department')}'")
	
	if filters.get("custom_section"):
		if isinstance(filters.get("custom_section"), list):
			section_list = "', '".join(filters.get("custom_section"))
			conditions.append(f"emp.custom_section IN ('{section_list}')")
		else:
			conditions.append(f"emp.custom_section = '{filters.get('custom_section')}'")
	
	if filters.get("custom_group"):
		if isinstance(filters.get("custom_group"), list):
			group_list = "', '".join(filters.get("custom_group"))
			conditions.append(f"emp.custom_group IN ('{group_list}')")
		else:
			conditions.append(f"emp.custom_group = '{filters.get('custom_group')}'")
	
	if filters.get("employee"):
		conditions.append(f"emp.name = '{filters.get('employee')}'")
	
	return " AND " + " AND ".join(conditions) if conditions else ""




def get_chart_data(data, filters):
	"""Generate chart data for the report"""
	if not data:
		return None
	
	# Group by department for chart
	dept_data = {}
	for row in data:
		dept = row.get("department") or "No Department"
		if dept not in dept_data:
			dept_data[dept] = {
				"working_hours": 0,
				"overtime_hours": 0,
				"total_hours": 0
			}
		
		dept_data[dept]["working_hours"] += row.get("working_hours", 0)
		dept_data[dept]["overtime_hours"] += row.get("overtime_hours", 0)
		dept_data[dept]["total_hours"] += row.get("total_hours", 0)
	
	# Apply decimal rounding to chart data
	for dept in dept_data:
		dept_data[dept]["working_hours"] = decimal_round(dept_data[dept]["working_hours"])
		dept_data[dept]["overtime_hours"] = decimal_round(dept_data[dept]["overtime_hours"])
		dept_data[dept]["total_hours"] = decimal_round(dept_data[dept]["total_hours"])
	
	return {
		"data": {
			"labels": list(dept_data.keys()),
			"datasets": [
				{
					"name": "Working Hours",
					"values": [dept_data[dept]["working_hours"] for dept in dept_data.keys()]
				},
				{
					"name": "Overtime Hours", 
					"values": [dept_data[dept]["overtime_hours"] for dept in dept_data.keys()]
				}
			]
		},
		"type": "bar",
		"height": 300
	}