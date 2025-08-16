# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, get_datetime, flt
from datetime import datetime, timedelta, time


def timedelta_to_time_helper(td):
    """Helper function to convert timedelta to time object"""
    if td is None:
        return None
    if hasattr(td, 'total_seconds'):
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return time(hours, minutes, seconds)
    else:
        return td


def parse_time_field_helper(time_field):
    """FIXED: Helper function to parse time field từ Overtime Registration"""
    try:
        if time_field is None:
            return None
            
        # Handle different time field types
        if isinstance(time_field, time):
            return time_field
            
        if hasattr(time_field, 'total_seconds'):
            # timedelta object (ERPNext sometimes stores time as timedelta)
            total_seconds = int(time_field.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return time(hours % 24, minutes, seconds)  # Ensure hours < 24
            
        if isinstance(time_field, str):
            # String format "HH:MM:SS" or "HH:MM"
            if ':' in time_field:
                time_parts = time_field.split(':')
                hours = int(time_parts[0])
                minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
                seconds = int(time_parts[2]) if len(time_parts) > 2 else 0
                return time(hours % 24, minutes, seconds)
            else:
                # Try to parse as integer (HHMM format)
                if time_field.isdigit() and len(time_field) >= 3:
                    hours = int(time_field[:2])
                    minutes = int(time_field[2:4]) if len(time_field) >= 4 else 0
                    return time(hours % 24, minutes, 0)
                    
        if isinstance(time_field, datetime):
            # datetime object, extract time part
            return time_field.time()
            
        # Try to convert to string and parse
        str_time = str(time_field)
        if ':' in str_time:
            time_parts = str_time.split(':')
            hours = int(float(time_parts[0]))
            minutes = int(float(time_parts[1])) if len(time_parts) > 1 else 0
            return time(hours % 24, minutes, 0)
            
        return None
        
    except Exception as e:
        frappe.logger().error(f"Error parsing time field {time_field} (type: {type(time_field)}): {str(e)}")
        return None


def get_active_employees_for_date(target_date):
    """
    Lấy tất cả nhân viên active cho ngày cụ thể
    """
    try:
        employees = frappe.db.sql("""
            SELECT 
                e.name,
                e.employee_name,
                e.company,
                e.department,
                e.default_shift,
                e.date_of_joining,
                e.relieving_date,
                e.status
            FROM `tabEmployee` e
            WHERE e.status = 'Active'
            AND (e.date_of_joining IS NULL OR e.date_of_joining <= %s)
            AND (e.relieving_date IS NULL OR e.relieving_date >= %s)
            ORDER BY e.name
        """, (target_date, target_date), as_dict=True)
        
        return employees
        
    except Exception as e:
        frappe.log_error(f"Error getting active employees: {str(e)}", "Active Employees Utility")
        return []


def extract_in_out_times_helper(logs, check_in_out_type):
    """Extract in_time và out_time từ logs using ERPNext logic"""
    try:
        from hrms.hr.doctype.employee_checkin.employee_checkin import find_index_in_dict
    except ImportError:
        # Fallback function nếu không import được
        def find_index_in_dict(lst, key, value):
            for i, item in enumerate(lst):
                if item.get(key) == value:
                    return i
            return None
    
    in_time = None
    out_time = None
    
    if check_in_out_type == "Alternating entries as IN and OUT during the same shift":
        in_time = get_datetime(logs[0].time)
        if len(logs) >= 2:
            out_time = get_datetime(logs[-1].time)

    elif check_in_out_type == "Strictly based on Log Type in Employee Checkin":
        # Tìm first IN log
        first_in_log_index = find_index_in_dict(logs, "log_type", "IN")
        if first_in_log_index is not None:
            in_time = get_datetime(logs[first_in_log_index].time)
        
        # Tìm last OUT log (duyệt ngược)
        last_out_log_index = find_index_in_dict(list(reversed(logs)), "log_type", "OUT")
        if last_out_log_index is not None:
            out_time = get_datetime(logs[len(logs) - 1 - last_out_log_index].time)
    
    return in_time, out_time


def check_attendance_exists_helper(employee, attendance_date, exclude_name=None):
    """Check if attendance record exists for employee on date"""
    filters = {
        "employee": employee,
        "attendance_date": attendance_date,
        "docstatus": ["!=", 2]
    }
    
    if exclude_name:
        filters["name"] = ["!=", exclude_name]
    
    existing = frappe.db.exists("Custom Attendance", filters)
    return {"exists": bool(existing), "record": existing}


def validate_time_range(check_in_time, check_out_time):
    """Validate check-in and check-out time range"""
    if not check_in_time or not check_out_time:
        return {"valid": False, "message": "Missing check-in or check-out time"}
    
    if check_out_time <= check_in_time:
        return {"valid": False, "message": "Check-out time must be after check-in time"}
    
    # Check if time range is reasonable (not more than 24 hours)
    from frappe.utils import time_diff_in_hours
    total_hours = time_diff_in_hours(check_out_time, check_in_time)
    if total_hours > 24:
        return {"valid": False, "message": "Working hours cannot exceed 24 hours"}
    
    return {"valid": True, "message": "Valid time range"}


def calculate_time_difference_in_hours(start_time, end_time):
    """Calculate time difference in hours with proper handling"""
    try:
        if not start_time or not end_time:
            return 0.0
        
        # Ensure datetime objects
        if isinstance(start_time, str):
            start_time = get_datetime(start_time)
        if isinstance(end_time, str):
            end_time = get_datetime(end_time)
        
        # Handle overnight periods
        if end_time <= start_time:
            end_time += timedelta(days=1)
        
        from frappe.utils import time_diff_in_hours
        return flt(time_diff_in_hours(end_time, start_time), 2)
        
    except Exception as e:
        frappe.log_error(f"Error calculating time difference: {str(e)}", "Time Calculation Utility")
        return 0.0


def format_time_for_display(time_value):
    """Format time value for consistent display"""
    try:
        if not time_value:
            return ""
        
        if isinstance(time_value, datetime):
            return time_value.strftime("%H:%M:%S")
        elif isinstance(time_value, time):
            return time_value.strftime("%H:%M:%S")
        elif hasattr(time_value, 'total_seconds'):
            # timedelta object
            time_obj = timedelta_to_time_helper(time_value)
            return time_obj.strftime("%H:%M:%S") if time_obj else ""
        else:
            return str(time_value)
            
    except Exception as e:
        frappe.log_error(f"Error formatting time: {str(e)}", "Time Format Utility")
        return str(time_value)


def get_shift_type_info(shift_name):
    """Get shift type information with proper error handling"""
    try:
        if not shift_name:
            return None
        
        shift_doc = frappe.get_cached_doc("Shift Type", shift_name)
        
        return {
            "name": shift_doc.name,
            "start_time": shift_doc.start_time,
            "end_time": shift_doc.end_time,
            "has_break": getattr(shift_doc, 'has_break', False),
            "break_start_time": getattr(shift_doc, 'break_start_time', None),
            "break_end_time": getattr(shift_doc, 'break_end_time', None),
            "custom_has_break": getattr(shift_doc, 'custom_has_break', False),
            "custom_break_start_time": getattr(shift_doc, 'custom_break_start_time', None),
            "custom_break_end_time": getattr(shift_doc, 'custom_break_end_time', None),
            "determine_check_in_and_check_out": getattr(shift_doc, 'determine_check_in_and_check_out', 
                                                      "Alternating entries as IN and OUT during the same shift")
        }
        
    except Exception as e:
        frappe.log_error(f"Error getting shift info: {str(e)}", "Shift Info Utility")
        return None


def is_overnight_shift(shift_info):
    """Check if shift is overnight based on start/end times"""
    try:
        if not shift_info or not shift_info.get('start_time') or not shift_info.get('end_time'):
            return False
        
        start_time = timedelta_to_time_helper(shift_info['start_time'])
        end_time = timedelta_to_time_helper(shift_info['end_time'])
        
        if not start_time or not end_time:
            return False
        
        return end_time <= start_time
        
    except Exception as e:
        frappe.log_error(f"Error checking overnight shift: {str(e)}", "Overnight Shift Utility")
        return False


def calculate_working_date_for_shift(current_datetime, shift_info):
    """Calculate the correct working date for a shift (handles overnight shifts)"""
    try:
        if not shift_info or not is_overnight_shift(shift_info):
            return current_datetime.date()
        
        # For overnight shifts, determine the correct working date
        shift_start_time = timedelta_to_time_helper(shift_info['start_time'])
        
        if current_datetime.time() >= shift_start_time:
            # We're in the first part of the overnight shift
            return current_datetime.date()
        else:
            # We're in the second part of the overnight shift (next day)
            return current_datetime.date() - timedelta(days=1)
            
    except Exception as e:
        frappe.log_error(f"Error calculating working date: {str(e)}", "Working Date Utility")
        return current_datetime.date()


def sanitize_time_input(time_input):
    """Sanitize and validate time input from various sources"""
    try:
        if not time_input:
            return None
        
        # If already a time object
        if isinstance(time_input, time):
            return time_input
        
        # If datetime object
        if isinstance(time_input, datetime):
            return time_input.time()
        
        # If timedelta object
        if hasattr(time_input, 'total_seconds'):
            return timedelta_to_time_helper(time_input)
        
        # If string
        if isinstance(time_input, str):
            # Try different string formats
            formats = ["%H:%M:%S", "%H:%M", "%H%M", "%I:%M %p", "%I:%M:%S %p"]
            
            for fmt in formats:
                try:
                    parsed_time = datetime.strptime(time_input.strip(), fmt).time()
                    return parsed_time
                except ValueError:
                    continue
        
        return None
        
    except Exception as e:
        frappe.log_error(f"Error sanitizing time input: {str(e)}", "Time Sanitize Utility")
        return None


def get_employee_default_shift(employee_id):
    """Get employee's default shift with error handling"""
    try:
        if not employee_id:
            return None
        
        employee = frappe.get_cached_doc("Employee", employee_id)
        return getattr(employee, 'default_shift', None)
        
    except Exception as e:
        frappe.log_error(f"Error getting employee shift: {str(e)}", "Employee Shift Utility")
        return None


def create_datetime_from_date_and_time(date_obj, time_obj):
    """Create datetime object from separate date and time objects"""
    try:
        if not date_obj or not time_obj:
            return None
        
        # Ensure proper types
        if isinstance(date_obj, str):
            date_obj = getdate(date_obj)
        if isinstance(time_obj, str):
            time_obj = sanitize_time_input(time_obj)
        
        if not time_obj:
            return None
        
        return datetime.combine(date_obj, time_obj)
        
    except Exception as e:
        frappe.log_error(f"Error creating datetime: {str(e)}", "DateTime Creation Utility")
        return None


def round_time_to_minutes(time_obj, minutes=15):
    """Round time to nearest specified minutes"""
    try:
        if not time_obj:
            return None
        
        if isinstance(time_obj, datetime):
            dt = time_obj
        else:
            dt = datetime.combine(datetime.today(), time_obj)
        
        # Round to nearest interval
        delta = timedelta(minutes=minutes)
        remainder = dt.minute % minutes
        
        if remainder < minutes / 2:
            # Round down
            rounded_dt = dt - timedelta(minutes=remainder)
        else:
            # Round up
            rounded_dt = dt + timedelta(minutes=minutes - remainder)
        
        # Reset seconds and microseconds
        rounded_dt = rounded_dt.replace(second=0, microsecond=0)
        
        if isinstance(time_obj, datetime):
            return rounded_dt
        else:
            return rounded_dt.time()
            
    except Exception as e:
        frappe.log_error(f"Error rounding time: {str(e)}", "Time Rounding Utility")
        return time_obj


def validate_employee_attendance_date(employee_id, attendance_date):
    """Validate if employee can have attendance on specific date"""
    try:
        employee = frappe.get_cached_doc("Employee", employee_id)
        target_date = getdate(attendance_date)
        
        # Check joining date
        if employee.date_of_joining and getdate(employee.date_of_joining) > target_date:
            return {"valid": False, "message": "Attendance date is before employee joining date"}
        
        # Check relieving date
        if employee.relieving_date and getdate(employee.relieving_date) < target_date:
            return {"valid": False, "message": "Attendance date is after employee relieving date"}
        
        # Check employee status
        if employee.status != "Active":
            return {"valid": False, "message": f"Employee status is {employee.status}, not Active"}
        
        return {"valid": True, "message": "Valid"}
        
    except Exception as e:
        return {"valid": False, "message": f"Validation error: {str(e)}"}


def get_attendance_summary_data(start_date, end_date, employee=None):
    """Get attendance summary data for reporting"""
    try:
        filters = {
            "attendance_date": ["between", [start_date, end_date]],
            "docstatus": ["!=", 2]
        }
        
        if employee:
            filters["employee"] = employee
        
        attendance_data = frappe.get_all("Custom Attendance",
            filters=filters,
            fields=[
                "employee", "employee_name", "attendance_date", "status",
                "working_hours", "overtime_hours", "late_entry", "early_exit"
            ]
        )
        
        # Group by status
        summary = {}
        for record in attendance_data:
            status = record.get('status', 'Unknown')
            if status not in summary:
                summary[status] = 0
            summary[status] += 1
        
        return {
            "total_records": len(attendance_data),
            "status_breakdown": summary,
            "records": attendance_data
        }
        
    except Exception as e:
        frappe.log_error(f"Error getting attendance summary: {str(e)}", "Attendance Summary Utility")
        return {"total_records": 0, "status_breakdown": {}, "records": []}