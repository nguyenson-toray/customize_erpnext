# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt
# shift_registration_integration.py

import frappe
from frappe.utils import getdate, get_datetime, flt
from datetime import datetime, timedelta


def get_registered_shift_for_employee_date(employee, attendance_date):
    """
    Kiểm tra xem nhân viên có đăng ký shift cho ngày cụ thể không
    
    Args:
        employee: Employee ID
        attendance_date: Ngày cần kiểm tra
        
    Returns:
        dict: {
            "has_registration": bool,
            "shift": str hoặc None,
            "registration_name": str hoặc None,
            "begin_time": time object hoặc None,
            "end_time": time object hoặc None,
            "registration_details": dict
        }
    """
    try:
        target_date = getdate(attendance_date)
        
        frappe.logger().info(f"=== Checking Shift Registration for {employee} on {target_date} ===")
        
        # Query để tìm shift registration
        registrations = frappe.db.sql("""
            SELECT 
                sr.name as registration_name,
                sr.shift,
                sr.docstatus,
                sr.request_date,
                srd.begin_date,
                srd.end_date,
                srd.begin_time,
                srd.end_time,
                srd.employee,
                srd.employee_name
            FROM `tabShift Registration` sr
            INNER JOIN `tabShift Registration Detail` srd ON srd.parent = sr.name
            WHERE srd.employee = %s
            AND sr.docstatus = 1
            AND %s BETWEEN srd.begin_date AND srd.end_date
            ORDER BY sr.creation DESC
            LIMIT 1
        """, (employee, target_date), as_dict=True)
        
        if not registrations:
            frappe.logger().info(f"No shift registration found for {employee} on {target_date}")
            return {
                "has_registration": False,
                "shift": None,
                "registration_name": None,
                "begin_time": None,
                "end_time": None,
                "registration_details": {}
            }
        
        registration = registrations[0]
        
        frappe.logger().info(f"Found shift registration: {registration['registration_name']}")
        frappe.logger().info(f"Registered shift: {registration['shift']}")
        frappe.logger().info(f"Period: {registration['begin_date']} to {registration['end_date']}")
        
        # Parse begin_time và end_time nếu có
        begin_time = None
        end_time = None
        
        if registration.get('begin_time'):
            begin_time = parse_time_field_helper(registration['begin_time'])
        if registration.get('end_time'):
            end_time = parse_time_field_helper(registration['end_time'])
        
        return {
            "has_registration": True,
            "shift": registration['shift'],
            "registration_name": registration['registration_name'],
            "begin_time": begin_time,
            "end_time": end_time,
            "registration_details": {
                "begin_date": registration['begin_date'],
                "end_date": registration['end_date'],
                "request_date": registration['request_date'],
                "docstatus": registration['docstatus']
            }
        }
        
    except Exception as e:
        error_msg = f"Error checking shift registration: {str(e)}"
        frappe.log_error(error_msg, "Shift Registration Check")
        frappe.logger().error(error_msg)
        
        return {
            "has_registration": False,
            "shift": None,
            "registration_name": None,
            "begin_time": None,
            "end_time": None,
            "registration_details": {}
        }


def parse_time_field_helper(time_field):
    """Helper function to parse time field"""
    try:
        if time_field is None:
            return None
            
        # Handle different time field types
        if isinstance(time_field, time):
            return time_field
            
        if hasattr(time_field, 'total_seconds'):
            # timedelta object
            total_seconds = int(time_field.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return time(hours % 24, minutes, seconds)
            
        if isinstance(time_field, str):
            # String format "HH:MM:SS" or "HH:MM"
            if ':' in time_field:
                time_parts = time_field.split(':')
                hours = int(time_parts[0])
                minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
                seconds = int(time_parts[2]) if len(time_parts) > 2 else 0
                return time(hours % 24, minutes, seconds)
                    
        if isinstance(time_field, datetime):
            return time_field.time()
            
        return None
        
    except Exception as e:
        frappe.logger().error(f"Error parsing time field {time_field}: {str(e)}")
        return None


def get_effective_shift_for_attendance(doc):
    """
    Lấy shift hiệu quả cho Custom Attendance
    Ưu tiên: Shift Registration > Employee Default Shift
    
    Args:
        doc: Custom Attendance document
        
    Returns:
        dict: {
            "shift": str,
            "source": str, # "registration" hoặc "default"
            "registration_info": dict hoặc None
        }
    """
    try:
        if not doc.employee or not doc.attendance_date:
            return {"shift": None, "source": "none", "registration_info": None}
        
        frappe.logger().info(f"=== Getting Effective Shift for {doc.employee} on {doc.attendance_date} ===")
        
        # Step 1: Kiểm tra Shift Registration
        registration_info = get_registered_shift_for_employee_date(doc.employee, doc.attendance_date)
        
        if registration_info["has_registration"] and registration_info["shift"]:
            frappe.logger().info(f"Using registered shift: {registration_info['shift']}")
            return {
                "shift": registration_info["shift"],
                "source": "registration",
                "registration_info": registration_info
            }
        
        # Step 2: Fallback to default shift
        employee_doc = frappe.get_cached_doc("Employee", doc.employee)
        default_shift = getattr(employee_doc, 'default_shift', None)
        
        frappe.logger().info(f"Using default shift: {default_shift}")
        return {
            "shift": default_shift,
            "source": "default", 
            "registration_info": None
        }
        
    except Exception as e:
        error_msg = f"Error getting effective shift: {str(e)}"
        frappe.log_error(error_msg, "Effective Shift")
        frappe.logger().error(error_msg)
        
        return {"shift": None, "source": "error", "registration_info": None}


def calculate_working_hours_with_registered_shift(doc):
    """
    Tính giờ làm việc sử dụng shift từ registration hoặc default
    
    Args:
        doc: Custom Attendance document
        
    Returns:
        dict: Kết quả tính toán working hours
    """
    try:
        if not doc.check_in or not doc.check_out:
            return {
                "working_hours": 0.0,
                "shift_used": None,
                "shift_source": "none",
                "message": "Missing check-in or check-out times"
            }
        
        check_in_time = get_datetime(doc.check_in)
        check_out_time = get_datetime(doc.check_out)
        
        if check_out_time <= check_in_time:
            return {
                "working_hours": 0.0,
                "shift_used": None,
                "shift_source": "none",
                "message": "Invalid time range"
            }
        
        # Lấy effective shift
        shift_info = get_effective_shift_for_attendance(doc)
        effective_shift = shift_info["shift"]
        
        if not effective_shift:
            # Fallback: tính theo thời gian thực tế
            total_hours = time_diff_in_hours(check_out_time, check_in_time)
            working_hours = max(0, total_hours - 1)  # Trừ 1h break
            
            return {
                "working_hours": flt(working_hours, 2),
                "shift_used": None,
                "shift_source": shift_info["source"],
                "message": "Calculated without shift constraints"
            }
        
        # Tính theo shift
        working_hours = calculate_realistic_working_hours_with_shift(
            doc, check_in_time, check_out_time, effective_shift, shift_info
        )
        
        return {
            "working_hours": working_hours,
            "shift_used": effective_shift,
            "shift_source": shift_info["source"],
            "registration_info": shift_info.get("registration_info"),
            "message": f"Calculated using {shift_info['source']} shift: {effective_shift}"
        }
        
    except Exception as e:
        error_msg = f"Error calculating working hours with registered shift: {str(e)}"
        frappe.log_error(error_msg, "Working Hours Calculation")
        
        return {
            "working_hours": 0.0,
            "shift_used": None,
            "shift_source": "error",
            "message": f"Calculation failed: {str(e)}"
        }


def calculate_realistic_working_hours_with_shift(doc, in_time, out_time, shift_name, shift_info):
    """ 
    Tính working hours theo shift cụ thể
    """
    try:
        from frappe.utils import time_diff_in_hours
        from .attendance_utils import timedelta_to_time_helper
        
        # Lấy shift document
        shift_doc = frappe.get_cached_doc("Shift Type", shift_name)
        
        if not shift_doc.start_time or not shift_doc.end_time: 
            # Fallback calculation
            total_hours = time_diff_in_hours(out_time, in_time)
            return max(0, flt(total_hours - 1, 2))  # Trừ 1h break
        
        # Convert shift times
        shift_start_time = timedelta_to_time_helper(shift_doc.start_time)
        shift_end_time = timedelta_to_time_helper(shift_doc.end_time)
        
        work_date = in_time.date()
        shift_start_datetime = datetime.combine(work_date, shift_start_time)
        shift_end_datetime = datetime.combine(work_date, shift_end_time)
        
        # Handle overnight shifts
        if shift_end_datetime <= shift_start_datetime:
            if in_time.time() >= shift_start_time:
                shift_end_datetime += timedelta(days=1)
            else:
                shift_start_datetime -= timedelta(days=1)
        
        # Calculate effective working time (within shift bounds)
        effective_start = max(in_time, shift_start_datetime)
        effective_end = min(out_time, shift_end_datetime)
        
        if effective_end <= effective_start:
            return 0.0
        
        # Calculate total working hours
        total_working_hours = time_diff_in_hours(effective_end, effective_start)
        
        # Deduct break time if overlap
        break_overlap_hours = calculate_break_overlap_for_shift(
            shift_doc, effective_start, effective_end
        )
        
        final_hours = total_working_hours - break_overlap_hours
        
        frappe.logger().info(f"Shift calculation: {total_working_hours}h total - {break_overlap_hours}h break = {final_hours}h")
        
        return max(0, flt(final_hours, 2))
        
    except Exception as e:
        frappe.log_error(f"Error in realistic hours calculation: {str(e)}", "Shift Hours Calc")
        # Fallback
        total_hours = time_diff_in_hours(out_time, in_time)
        return max(0, flt(total_hours - 1, 2))


def calculate_break_overlap_for_shift(shift_doc, effective_start, effective_end):
    """Calculate break overlap with working time"""
    try:
        from .attendance_utils import timedelta_to_time_helper
        from frappe.utils import time_difours
        
        # Check for break settings
        has_break = getattr(shift_doc, 'has_break', False)
        break_start_time = getattr(shift_doc, 'break_start_time', None)
        break_end_time = getattr(shift_doc, 'break_end_time', None)
        
        # Check custom break settings
        custom_has_break = getattr(shift_doc, 'custom_has_break', False)
        if custom_has_break:
            break_start_time = getattr(shift_doc, 'custom_break_start_time', None)
            break_end_time = getattr(shift_doc, 'custom_break_end_time', None)
        
        if not (has_break or custom_has_break) or not break_start_time or not break_end_time:
            return 0.0
         
        # Parse break times
        break_start = timedelta_to_time_helper(break_start_time)
        break_end = timedelta_to_time_helper(break_end_time)
        
        if not break_start or not break_end:
            return 0.0
       
        # Calculate break period
        work_date = effective_start.date()
        break_start_datetime = datetime.combine(work_date, break_start)
        break_end_datetime = datetime.combine(work_date, break_end)
        
        if break_end_datetime <= break_start_datetime:
            break_end_datetime += timedelta(days=1)
        
        # Calculate overlap
        overlap_start = max(break_start_datetime, effective_start)
        overlap_end = min(break_end_datetime, effective_end)
        
        if overlap_start < overlap_end:
            return flt(time_diff_in_hours(overlap_end, overlap_start), 2)
        
        return 0.0
        
    except Exception as e:
        frappe.log_error(f"Error calculating break overlap: {str(e)}", "Break Overlap")
        return 0.0


def update_custom_attendance_with_registered_shift(doc):
    """
    Update Custom Attendance document với shift đã đăng ký
    
    Args:
        doc: Custom Attendance document
        
    Returns:
        dict: Kết quả update
    """
    try:
        # Lấy shift hiệu quả
        shift_info = get_effective_shift_for_attendance(doc)
        
        # Update shift field trong document
        if shift_info["shift"]:
            doc.shift = shift_info["shift"]
        
        # Tính lại working hours12,0000
        if doc.check_in and doc.check_out:
            calculation_result = calculate_working_hours_with_registered_shift(doc)
            doc.working_hours = calculation_result["working_hours"]
        
        # Thêm thông tin registration vào custom field nếu cần
        if shift_info["source"] == "registration" and shift_info["registration_info"]:
            reg_info = shift_info["registration_info"]
            doc.custom_shift_registration = reg_info["registration_name"]
            doc.custom_shift_source = "Shift Registration"
        else:
            doc.custom_shift_source = "Default Shift"
        
        frappe.logger().info(f"Updated attendance with shift: {shift_info['shift']} from {shift_info['source']}")
        
        return {
            "success": True,
            "shift_used": shift_info["shift"],
            "shift_source": shift_info["source"],
            "working_hours": doc.working_hours,
            "message": f"Successfully updated with {shift_info['source']} shift"
        }
        
    except Exception as e:
        error_msg = f"Error updating attendance with registered shift: {str(e)}"
        frappe.log_error(error_msg, "Update Attendance Shift")
        
        return {
            "success": False,
            "message": error_msg
        }


# Utility function for time calculation
def time_diff_in_hours(end_time, start_time):
    """Calculate time difference in hours"""
    try:
        from frappe.utils import time_diff_in_hours as frappe_time_diff
        return frappe_time_diff(end_time, start_time)
    except:
        delta = end_time - start_time
        return delta.total_seconds() / 3600