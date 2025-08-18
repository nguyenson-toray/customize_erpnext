# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, get_datetime, time_diff_in_hours, flt
from datetime import datetime, timedelta


def validate_duplicate_attendance(doc):
    """Check for duplicate attendance records - block ANY existing record for same employee + date"""
    if not doc.employee or not doc.attendance_date:
        return
        
    # Skip check if flagged to ignore
    if getattr(doc.flags, 'ignore_duplicate_check', False):
        return
    
    # Check for ANY record (Draft, Submitted, Cancelled) for same employee + date
    existing_records = frappe.db.sql("""
        SELECT name, docstatus, status 
        FROM `tabCustom Attendance` 
        WHERE employee = %s 
        AND attendance_date = %s 
        AND name != %s
    """, (doc.employee, doc.attendance_date, doc.name or ""), as_dict=True)
    
    if existing_records:
        existing_record = existing_records[0]
        status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
        record_status = status_map.get(existing_record.docstatus, "Unknown")
        
        frappe.throw(
            f"Attendance record already exists for {doc.employee} on {doc.attendance_date}<br>"
            f"Existing record: <strong>{existing_record.name}</strong> ({record_status})<br>"
            f"Please edit the existing record instead of creating a new one.",
            title="Duplicate Attendance Record"
        )


def validate_employee_active_on_date(employee_id, attendance_date):
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


def validate_before_submit(doc):
    """
    Validate Custom Attendance record trước khi submit
    """
    try:
        # Basic validation
        if not doc.employee:
            return {"valid": False, "message": "Missing employee"}
            
        if not doc.attendance_date:
            return {"valid": False, "message": "Missing attendance date"}
            
        if not doc.status:
            return {"valid": False, "message": "Missing status"}
            
        # Business logic validation
        if doc.status == "Present":
            # Nếu Present mà không có check_in hoặc working_hours = 0, có thể cảnh báo nhưng vẫn cho submit
            if not doc.check_in and not doc.working_hours:
                frappe.logger().warning(f"Present record without check-in or working hours: {doc.name}")
                
        elif doc.status == "Absent":
            # Absent records should not have check-in/out or working hours
            if doc.check_in or doc.check_out or doc.working_hours:
                frappe.logger().warning(f"Absent record has check-in/out data: {doc.name}")
                
        # Check for duplicate (same employee + date)
        existing = frappe.db.exists("Custom Attendance", {
            "employee": doc.employee,
            "attendance_date": doc.attendance_date,
            "name": ["!=", doc.name],
            "docstatus": ["!=", 2]  # Not cancelled
        })
        
        if existing:
            return {"valid": False, "message": f"Duplicate attendance exists: {existing}"}
            
        # Check if employee was active on that date
        employee_validation = validate_employee_active_on_date(doc.employee, doc.attendance_date)
        if not employee_validation["valid"]:
            return employee_validation
            
        return {"valid": True, "message": "Valid"}
        
    except Exception as e:
        return {"valid": False, "message": f"Validation error: {str(e)}"}


def validate_time_range(check_in_time, check_out_time):
    """Validate check-in and check-out time range"""
    if not check_in_time or not check_out_time:
        return {"valid": False, "message": "Missing check-in or check-out time"}
    
    # Convert to datetime if string
    if isinstance(check_in_time, str):
        check_in_time = get_datetime(check_in_time)
    if isinstance(check_out_time, str):
        check_out_time = get_datetime(check_out_time)
    
    if check_out_time <= check_in_time:
        return {"valid": False, "message": "Check-out time must be after check-in time"}
    
    # Check if time range is reasonable (not more than 24 hours)
    total_hours = time_diff_in_hours(check_out_time, check_in_time)
    if total_hours > 24:
        return {"valid": False, "message": "Working hours cannot exceed 24 hours"}
    
    return {"valid": True, "message": "Valid time range"}


def validate_working_hours(working_hours, max_hours=24):
    """Validate working hours value"""
    try:
        if working_hours is None:
            return {"valid": True, "message": "No working hours to validate"}
        
        hours = flt(working_hours)
        
        if hours < 0:
            return {"valid": False, "message": "Working hours cannot be negative"}
        
        if hours > max_hours:
            return {"valid": False, "message": f"Working hours cannot exceed {max_hours} hours"}
        
        return {"valid": True, "message": "Valid working hours"}
        
    except Exception as e:
        return {"valid": False, "message": f"Invalid working hours format: {str(e)}"}


def validate_overtime_hours(overtime_hours, max_overtime=12):
    """Validate overtime hours value"""
    try:
        if overtime_hours is None:
            return {"valid": True, "message": "No overtime hours to validate"}
        
        hours = flt(overtime_hours)
        
        if hours < 0:
            return {"valid": False, "message": "Overtime hours cannot be negative"}
        
        if hours > max_overtime:
            return {"valid": False, "message": f"Overtime hours cannot exceed {max_overtime} hours"}
        
        return {"valid": True, "message": "Valid overtime hours"}
        
    except Exception as e:
        return {"valid": False, "message": f"Invalid overtime hours format: {str(e)}"}


def validate_attendance_date(attendance_date):
    """Validate attendance date"""
    try:
        if not attendance_date:
            return {"valid": False, "message": "Attendance date is required"}
        
        date_obj = getdate(attendance_date)
        today_date = getdate()
        
        # Check if date is not too far in the past (configurable limit)
        max_past_days = frappe.db.get_single_value("HR Settings", "max_attendance_past_days") or 365
        earliest_date = today_date - timedelta(days=max_past_days)
        
        if date_obj < earliest_date:
            return {"valid": False, "message": f"Attendance date cannot be more than {max_past_days} days in the past"}
        
        # Check if date is not in the future (beyond today)
        if date_obj > today_date:
            return {"valid": False, "message": "Attendance date cannot be in the future"}
        
        return {"valid": True, "message": "Valid attendance date"}
        
    except Exception as e:
        return {"valid": False, "message": f"Invalid date format: {str(e)}"}


def validate_shift_assignment(employee, shift, attendance_date):
    """Validate if employee is assigned to the shift on the date"""
    try:
        if not shift:
            return {"valid": True, "message": "No shift to validate"}
        
        # Check if shift exists
        if not frappe.db.exists("Shift Type", shift):
            return {"valid": False, "message": f"Shift '{shift}' does not exist"}
        
        # Get employee's default shift
        employee_doc = frappe.get_cached_doc("Employee", employee)
        default_shift = getattr(employee_doc, 'default_shift', None)
        
        # Check if shift matches employee's default shift
        if default_shift and shift != default_shift:
            # Check for shift assignment on the specific date
            shift_assignment = frappe.db.exists("Shift Assignment", {
                "employee": employee,
                "shift_type": shift,
                "start_date": ["<=", attendance_date],
                "end_date": [">=", attendance_date],
                "docstatus": 1
            })
            
            if not shift_assignment:
                frappe.logger().warning(f"Employee {employee} not assigned to shift {shift} on {attendance_date}")
                # Don't block, just warn
        
        return {"valid": True, "message": "Valid shift assignment"}
        
    except Exception as e:
        return {"valid": False, "message": f"Shift validation error: {str(e)}"}


def validate_status_consistency(doc):
    """Validate that attendance status is consistent with check-in/out data"""
    try:
        status = doc.status
        has_check_in = bool(doc.check_in)
        has_check_out = bool(doc.check_out)
        has_working_hours = bool(doc.working_hours)
        
        validation_warnings = []
        
        if status == "Present":
            if not has_check_in and not has_working_hours:
                validation_warnings.append("Present status but no check-in time or working hours")
                
        elif status == "Absent":
            if has_check_in or has_check_out or has_working_hours:
                validation_warnings.append("Absent status but has check-in/out data or working hours")
                
        elif status == "Half Day":
            if has_working_hours and doc.working_hours > 4:
                validation_warnings.append("Half Day status but working hours exceed 4 hours")
                
        # Log warnings but don't block
        for warning in validation_warnings:
            frappe.logger().warning(f"Status consistency warning for {doc.name}: {warning}")
        
        return {"valid": True, "warnings": validation_warnings}
        
    except Exception as e:
        return {"valid": False, "message": f"Status validation error: {str(e)}"}


def validate_late_early_flags(doc):
    """Validate late entry and early exit flags against shift timings"""
    try:
        if not doc.shift:
            return {"valid": True, "message": "No shift to validate against"}
        
        shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)
        
        warnings = []
        
        # Validate late entry
        if doc.late_entry and doc.check_in and shift_doc.start_time:
            from .attendance_utils import timedelta_to_time_helper
            
            check_in_time = get_datetime(doc.check_in).time()
            shift_start_time = timedelta_to_time_helper(shift_doc.start_time)
            
            if shift_start_time and check_in_time <= shift_start_time:
                warnings.append("Late entry flag set but check-in is not late")
        
        # Validate early exit
        if doc.early_exit and doc.check_out and shift_doc.end_time:
            from .attendance_utils import timedelta_to_time_helper
            
            check_out_time = get_datetime(doc.check_out).time()
            shift_end_time = timedelta_to_time_helper(shift_doc.end_time)
            
            if shift_end_time and check_out_time >= shift_end_time:
                warnings.append("Early exit flag set but check-out is not early")
        
        # Log warnings
        for warning in warnings:
            frappe.logger().warning(f"Late/Early validation warning for {doc.name}: {warning}")
        
        return {"valid": True, "warnings": warnings}
        
    except Exception as e:
        return {"valid": False, "message": f"Late/Early validation error: {str(e)}"}


def validate_company_assignment(employee, company):
    """Validate if employee belongs to the company"""
    try:
        if not company:
            return {"valid": True, "message": "No company to validate"}
        
        employee_doc = frappe.get_cached_doc("Employee", employee)
        employee_company = getattr(employee_doc, 'company', None)
        
        if employee_company and employee_company != company:
            return {"valid": False, "message": f"Employee belongs to {employee_company}, not {company}"}
        
        return {"valid": True, "message": "Valid company assignment"}
        
    except Exception as e:
        return {"valid": False, "message": f"Company validation error: {str(e)}"}


def validate_comprehensive(doc):
    """
    Comprehensive validation that runs all validation checks
    Returns summary of all validation results
    """
    try:
        validation_results = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "checks_performed": []
        }
        
        # Employee active validation
        if doc.employee and doc.attendance_date:
            employee_validation = validate_employee_active_on_date(doc.employee, doc.attendance_date)
            validation_results["checks_performed"].append("Employee Active Check")
            if not employee_validation["valid"]:
                validation_results["valid"] = False
                validation_results["errors"].append(employee_validation["message"])
        
        # Attendance date validation
        if doc.attendance_date:
            date_validation = validate_attendance_date(doc.attendance_date)
            validation_results["checks_performed"].append("Attendance Date Check")
            if not date_validation["valid"]:
                validation_results["valid"] = False
                validation_results["errors"].append(date_validation["message"])
        
        # Time range validation
        if doc.check_in and doc.check_out:
            time_validation = validate_time_range(doc.check_in, doc.check_out)
            validation_results["checks_performed"].append("Time Range Check")
            if not time_validation["valid"]:
                validation_results["valid"] = False
                validation_results["errors"].append(time_validation["message"])
        
        # Working hours validation
        if doc.working_hours is not None:
            hours_validation = validate_working_hours(doc.working_hours)
            validation_results["checks_performed"].append("Working Hours Check")
            if not hours_validation["valid"]:
                validation_results["valid"] = False
                validation_results["errors"].append(hours_validation["message"])
        
        # Overtime hours validation
        if doc.overtime_hours is not None:
            overtime_validation = validate_overtime_hours(doc.overtime_hours)
            validation_results["checks_performed"].append("Overtime Hours Check")
            if not overtime_validation["valid"]:
                validation_results["valid"] = False
                validation_results["errors"].append(overtime_validation["message"])
        
        # Shift assignment validation
        if doc.employee and doc.shift and doc.attendance_date:
            shift_validation = validate_shift_assignment(doc.employee, doc.shift, doc.attendance_date)
            validation_results["checks_performed"].append("Shift Assignment Check")
            if not shift_validation["valid"]:
                validation_results["errors"].append(shift_validation["message"])
        
        # Company assignment validation
        if doc.employee and doc.company:
            company_validation = validate_company_assignment(doc.employee, doc.company)
            validation_results["checks_performed"].append("Company Assignment Check")
            if not company_validation["valid"]:
                validation_results["valid"] = False
                validation_results["errors"].append(company_validation["message"])
        
        # Status consistency validation
        status_validation = validate_status_consistency(doc)
        validation_results["checks_performed"].append("Status Consistency Check")
        if status_validation.get("warnings"):
            validation_results["warnings"].extend(status_validation["warnings"])
        
        # Late/Early flags validation
        if doc.shift:
            late_early_validation = validate_late_early_flags(doc)
            validation_results["checks_performed"].append("Late/Early Flags Check")
            if late_early_validation.get("warnings"):
                validation_results["warnings"].extend(late_early_validation["warnings"])
        
        return validation_results
        
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"Comprehensive validation error: {str(e)}"],
            "warnings": [],
            "checks_performed": ["Error occurred during validation"]
        }


def validate_bulk_operation_safety(operation_type, record_count, date_range_days):
    """Validate safety constraints for bulk operations"""
    try:
        # Define safety limits
        limits = {
            "max_records_per_operation": 1000,
            "max_date_range_days": 90,
            "max_delete_records": 500,
            "max_cancel_records": 300
        }
        
        validation_results = {
            "safe": True,
            "warnings": [],
            "errors": []
        }
        
        # Check record count limits
        max_records = limits["max_records_per_operation"]
        if operation_type in ["delete", "cancel"]:
            max_records = limits[f"max_{operation_type}_records"]
        
        if record_count > max_records:
            validation_results["safe"] = False
            validation_results["errors"].append(
                f"Record count ({record_count}) exceeds safety limit ({max_records}) for {operation_type} operation"
            )
        
        # Check date range
        if date_range_days > limits["max_date_range_days"]:
            validation_results["safe"] = False
            validation_results["errors"].append(
                f"Date range ({date_range_days} days) exceeds safety limit ({limits['max_date_range_days']} days)"
            )
        
        # Operation-specific warnings
        if operation_type == "delete" and record_count > 100:
            validation_results["warnings"].append(
                f"Deleting {record_count} records is irreversible. Please ensure you have backups."
            )
        
        if operation_type == "submit" and record_count > 500:
            validation_results["warnings"].append(
                f"Submitting {record_count} records will make them read-only. Ensure data is correct."
            )
        
        return validation_results
        
    except Exception as e:
        return {
            "safe": False,
            "errors": [f"Bulk operation validation error: {str(e)}"],
            "warnings": []
        }


# Utility validation functions
def is_valid_employee(employee_id):
    """Quick check if employee exists and is active"""
    try:
        return frappe.db.exists("Employee", {"name": employee_id, "status": "Active"})
    except:
        return False


def is_valid_shift(shift_name):
    """Quick check if shift exists and is enabled"""
    try:
        return frappe.db.exists("Shift Type", {"name": shift_name, "disabled": 0})
    except:
        return False


def is_valid_company(company_name):
    """Quick check if company exists"""
    try:
        return frappe.db.exists("Company", company_name)
    except:
        return False


def get_validation_summary(doc):
    """Get a summary of validation status for display"""
    try:
        validation = validate_comprehensive(doc)
        
        summary = {
            "overall_status": "Valid" if validation["valid"] else "Invalid",
            "error_count": len(validation["errors"]),
            "warning_count": len(validation["warnings"]),
            "checks_count": len(validation["checks_performed"]),
            "errors": validation["errors"][:5],  # First 5 errors
            "warnings": validation["warnings"][:3]  # First 3 warnings
        }
        
        return summary
        
    except Exception as e:
        return {
            "overall_status": "Validation Failed",
            "error_count": 1,
            "warning_count": 0,
            "checks_count": 0,
            "errors": [str(e)],
            "warnings": []
        }


def validate_employee_permission(employee):
    """Validate if current user has permission to access employee data"""
    try:
        # Check if user has general access to employee
        if not frappe.has_permission("Employee", "read", employee):
            return {"valid": False, "message": "No permission to access this employee"}
        
        # Additional checks for department/company restrictions
        user = frappe.session.user
        user_employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
        
        if user_employee:
            # Check if same department or company
            user_emp_doc = frappe.get_doc("Employee", user_employee)
            target_emp_doc = frappe.get_doc("Employee", employee)
            
            # HR Manager can access all employees
            if "HR Manager" in frappe.get_roles(user):
                return {"valid": True, "message": "HR Manager access"}
            
            # Same department access
            if user_emp_doc.department == target_emp_doc.department:
                return {"valid": True, "message": "Same department access"}
            
            # Same company access for managers
            if "Manager" in frappe.get_roles(user) and user_emp_doc.company == target_emp_doc.company:
                return {"valid": True, "message": "Manager company access"}
        
        return {"valid": True, "message": "Access granted"}
        
    except Exception as e:
        return {"valid": False, "message": f"Permission validation error: {str(e)}"}


def validate_date_range_permissions(start_date, end_date):
    """Validate if user has permission to access data in date range"""
    try:
        user = frappe.session.user
        
        # HR Manager has access to all dates
        if "HR Manager" in frappe.get_roles(user):
            return {"valid": True, "message": "HR Manager access"}
        
        # Check if date range is within allowed limits
        max_past_days = frappe.db.get_single_value("HR Settings", "max_user_access_days") or 90
        
        from frappe.utils import date_diff, today
        days_back = date_diff(today(), start_date)
        
        if days_back > max_past_days:
            return {"valid": False, "message": f"Cannot access data older than {max_past_days} days"}
        
        # Check if accessing future dates (only HR can do this)
        if getdate(end_date) > getdate():
            return {"valid": False, "message": "Cannot access future dates"}
        
        return {"valid": True, "message": "Date range access granted"}
        
    except Exception as e:
        return {"valid": False, "message": f"Date range validation error: {str(e)}"}