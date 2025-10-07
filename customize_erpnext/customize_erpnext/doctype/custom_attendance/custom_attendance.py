# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt
# custom_attendance.py

import frappe
from frappe import _
from frappe.utils import (
    getdate, 
    add_days, 
    today, 
    get_datetime, 
    nowdate,
    time_diff_in_hours,
    flt,
    cint,         
    now_datetime  
)
from frappe.model.document import Document 
from datetime import datetime, timedelta, time

# Import từ modules folder
from .modules.overtime_calculator import get_overtime_details_for_doc, get_approved_overtime_requests_for_doc
from .modules.attendance_sync import sync_attendance_from_checkin_data, extract_in_out_times
from .modules.attendance_utils import timedelta_to_time_helper, parse_time_field_helper
from .modules.validators import validate_duplicate_attendance, validate_employee_active_on_date


def get_registered_shift_for_employee(employee, attendance_date):
    """
    Kiểm tra employee có shift registration cho ngày này không
    Return: shift name hoặc None
    """
    try:
        target_date = getdate(attendance_date)
        
        # Query shift registration đã submit
        result = frappe.db.sql("""
            SELECT sr.shift
            FROM `tabShift Registration` sr
            INNER JOIN `tabShift Registration Detail` srd ON srd.parent = sr.name
            WHERE srd.employee = %s
            AND sr.docstatus = 1
            AND %s BETWEEN srd.begin_date AND srd.end_date
            ORDER BY sr.creation DESC
            LIMIT 1
        """, (employee, target_date), as_dict=True)
        
        if result:
            return result[0].shift
        return None
        
    except Exception as e:
        frappe.log_error(f"Error getting registered shift: {str(e)}", "Shift Registration")
        return None


class CustomAttendance(Document):
    """
    Main Custom Attendance Document Class
    Handles core attendance functionality
    """
    
    def validate(self):
        """Validate attendance data"""
        # Check for duplicate attendance - including drafts
        validate_duplicate_attendance(self)
        
        # UPDATE: Check và set shift từ registration trước khi calculate
        self.update_shift_from_registration()
        
        if self.check_in and self.check_out:
            self.calculate_working_hours()
            # Auto-calculate overtime
            self.auto_calculate_overtime()

        # Update employee checkin links after validation
        self.update_employee_checkin_links()

    def before_save(self):
        """Before saving the document"""
        # Set company from employee if not set
        if not self.company and self.employee:
            employee = frappe.get_doc("Employee", self.employee)
            self.company = employee.company
            
    def on_submit(self):
        """After submitting the document"""
        # Update all related employee checkins to link to this attendance
        self.update_employee_checkin_links()

    def on_cancel(self):
        """When cancelling the document"""
        # Remove attendance links from employee checkins
        self.remove_employee_checkin_links()

    def update_shift_from_registration(self):
        """
        NEW METHOD: Update shift field from shift registration if available
        """
        try:
            if not self.employee or not self.attendance_date:
                return
                
            # Lấy registered shift
            registered_shift = get_registered_shift_for_employee(self.employee, self.attendance_date)
            
            if registered_shift:
                old_shift = self.shift
                self.shift = registered_shift
                
                if old_shift != registered_shift:
                    frappe.logger().info(f"Updated shift from {old_shift} to {registered_shift} for {self.employee}")
                    
        except Exception as e:
            frappe.log_error(f"Error updating shift from registration: {str(e)}", "Shift Update")
            # Don't block save on error
            pass

    def calculate_working_hours(self):
        """Calculate working hours using realistic calculation logic"""
        if self.check_in and self.check_out:
            check_in_time = get_datetime(self.check_in)
            check_out_time = get_datetime(self.check_out)
            
            if check_out_time > check_in_time:
                # Sử dụng logic tính thực tế
                self.working_hours = self.calculate_realistic_working_hours(check_in_time, check_out_time)
            else:
                frappe.throw("Check-out time cannot be earlier than check-in time")

    def calculate_break_overlap_safe(self, shift_doc, effective_start, effective_end):
        """
        SAFE VERSION: Calculate break overlap without complex errors
        """
        try:
            # Simple approach: if working > 4h, deduct 1h break
            working_duration = time_diff_in_hours(effective_end, effective_start)
            
            # Check if shift has break settings
            has_break = getattr(shift_doc, 'has_break', False)
            
            if has_break and working_duration > 4:
                return 1.0  # Standard 1-hour break
            elif working_duration > 6:
                return 1.0  # Assume 1-hour break for long shifts
            else:
                return 0.0  # No break for short shifts
                
        except Exception as e:
            frappe.logger().warning(f"Error in break calculation: {e}")
            # If working > 4h, assume 1h break
            try:
                working_duration = time_diff_in_hours(effective_end, effective_start)
                return 1.0 if working_duration > 4 else 0.0
            except:
                return 0.0

    def calculate_realistic_working_hours(self, in_time, out_time):
        """
        FIXED VERSION: Tính working hours an toàn với fallback logic
        """
        try:
            # Basic validation
            if not in_time or not out_time:
                return 0.0
                
            if out_time <= in_time:
                frappe.logger().warning(f"Invalid time range: {in_time} to {out_time}")
                return 0.0
            
            # Calculate basic total hours
            total_hours = time_diff_in_hours(out_time, in_time)
            
            # Validation: reasonable time range
            if total_hours <= 0 or total_hours > 24:
                frappe.logger().warning(f"Unreasonable total hours: {total_hours}")
                return 0.0
            
            # FALLBACK FIRST: Simple calculation if no shift
            if not self.shift:
                # Simple: total time - 1h break (if > 4h)
                working_hours = total_hours - (1 if total_hours > 4 else 0)
                return max(0, flt(working_hours, 2))
            
            # Try shift-based calculation
            try:
                shift_doc = frappe.get_cached_doc("Shift Type", self.shift)
                
                if not shift_doc.start_time or not shift_doc.end_time:
                    # Fallback: simple calculation
                    working_hours = total_hours - (1 if total_hours > 4 else 0)
                    return max(0, flt(working_hours, 2))
                
                # Convert shift times safely
                shift_start_time = timedelta_to_time_helper(shift_doc.start_time)
                shift_end_time = timedelta_to_time_helper(shift_doc.end_time)
                
                if not shift_start_time or not shift_end_time:
                    # Fallback: simple calculation
                    working_hours = total_hours - (1 if total_hours > 4 else 0)
                    return max(0, flt(working_hours, 2))
                
                # Calculate with shift constraints
                work_date = in_time.date()
                shift_start_datetime = datetime.combine(work_date, shift_start_time)
                shift_end_datetime = datetime.combine(work_date, shift_end_time)
                
                # Handle overnight shifts
                if shift_end_datetime <= shift_start_datetime:
                    if in_time.time() >= shift_start_time:
                        shift_end_datetime += timedelta(days=1)
                    else:
                        shift_start_datetime -= timedelta(days=1)
                
                # Calculate effective working time
                effective_start = max(in_time, shift_start_datetime)
                effective_end = min(out_time, shift_end_datetime)
                
                # CRITICAL FIX: Check for valid effective time range
                if effective_end <= effective_start:
                    # KHÔNG return 0! Dùng fallback calculation
                    frappe.logger().warning(f"No overlap with shift {self.shift}, using simple calculation")
                    working_hours = total_hours - (1 if total_hours > 4 else 0)
                    return max(0, flt(working_hours, 2))
                
                # Calculate effective working hours
                effective_working_hours = time_diff_in_hours(effective_end, effective_start)
                
                # Calculate break overlap safely
                break_overlap_hours = self.calculate_break_overlap_safe(shift_doc, effective_start, effective_end)
                
                final_hours = effective_working_hours - break_overlap_hours
                
                # Validation: final hours should be reasonable
                if final_hours <= 0:
                    # Fallback: use simple calculation
                    frappe.logger().warning(f"Calculated hours <= 0, using fallback")
                    working_hours = total_hours - (1 if total_hours > 4 else 0)
                    return max(0, flt(working_hours, 2))
                
                # Don't exceed total actual time
                if final_hours > total_hours:
                    final_hours = total_hours
                
                return flt(final_hours, 2)
                
            except Exception as shift_error:
                frappe.log_error(f"Error with shift calculation: {str(shift_error)}", "Shift Calculation")
                # Fallback: simple calculation
                working_hours = total_hours - (1 if total_hours > 4 else 0)
                return max(0, flt(working_hours, 2))
            
        except Exception as e:
            frappe.log_error(f"Error in calculate_realistic_working_hours: {str(e)}", "Working Hours Calc")
            # Ultimate fallback
            if out_time and in_time and out_time > in_time:
                total_hours = time_diff_in_hours(out_time, in_time)
                working_hours = total_hours - (1 if total_hours > 4 else 0)
                return max(0, flt(working_hours, 2))
            return 0.0

    def calculate_break_overlap_realistic(self, shift_doc, effective_start, effective_end):
        """Tính break overlap với thời gian làm việc hiệu quả"""
        
        # Kiểm tra có break time không
        has_custom_break = getattr(shift_doc, 'custom_has_break', False)
        break_start_time = getattr(shift_doc, 'custom_break_start_time', None)
        break_end_time = getattr(shift_doc, 'custom_break_end_time', None)
        
        # Nếu không có custom break, check ERPNext standard break
        if not has_custom_break and not break_start_time and not break_end_time:
            # Check standard ERPNext break field
            if not getattr(shift_doc, 'has_break', False):
                return 0.0
            
            # Dùng standard break time từ shift config
            break_start_time = getattr(shift_doc, 'break_start_time', None)
            break_end_time = getattr(shift_doc, 'break_end_time', None)
            
            # Nếu vẫn không có, dùng default 12:00-13:00
            if not break_start_time or not break_end_time:
                break_start_time = time(12, 0, 0)
                break_end_time = time(13, 0, 0)
        
        # Nếu không có break time gì cả
        if not break_start_time or not break_end_time:
            return 0.0
        
        try:
            # Convert timedelta to time nếu cần
            break_start_time = timedelta_to_time_helper(break_start_time)
            break_end_time = timedelta_to_time_helper(break_end_time)
            
            # Thời gian break trong ngày làm việc
            work_date = effective_start.date()
            break_start_datetime = datetime.combine(work_date, break_start_time)
            break_end_datetime = datetime.combine(work_date, break_end_time)
            
            # Xử lý break qua ngày
            if break_end_datetime <= break_start_datetime:
                break_end_datetime += timedelta(days=1)
            
            # Tính overlap giữa break time và working time
            overlap_start = max(break_start_datetime, effective_start)
            overlap_end = min(break_end_datetime, effective_end)
            
            if overlap_start < overlap_end:
                overlap_hours = time_diff_in_hours(overlap_end, overlap_start)
                return flt(overlap_hours, 2)
            else:
                return 0.0
        except Exception as e:
            frappe.log_error(f"Error calculating break overlap: {str(e)}", "Custom Attendance Break Overlap")
            return 0.0

    def auto_calculate_overtime(self):
        """Auto-calculate overtime"""
        try:
            if not self.employee or not self.attendance_date:
                return
                
            # Only calculate if we have check times
            if not self.check_in or not self.check_out:
                self.overtime_hours = 0.0
                return
                
            # Get OT requests
            ot_requests = get_approved_overtime_requests_for_doc(self)
            
            if ot_requests:
                # Calculate overtime
                overtime_details = get_overtime_details_for_doc(self)
                overtime_hours = overtime_details.get('total_actual_ot_hours', 0.0)
                
                if overtime_hours > 0:
                    # Store current regular hours
                    current_working = self.working_hours or 8.0
                    
                    # Update fields
                    self.overtime_hours = flt(overtime_hours, 2)
                    self.working_hours = flt(current_working + overtime_hours, 2)
                    
                    frappe.logger().info(f"Auto-calculated OT for {self.name}: {overtime_hours}h overtime, total {self.working_hours}h")
                else:
                    self.overtime_hours = 0.0
            else:
                self.overtime_hours = 0.0
                
        except Exception as e:
            frappe.log_error(f"Auto-calculate overtime error: {str(e)}", "Auto Overtime")
            # Don't block save on error
            pass

    def update_employee_checkin_links(self):
        """Update Employee Checkin records to link to this Custom Attendance via custom field"""
        if not self.employee or not self.attendance_date:
            return
        
        try:
            # Get all checkins for this employee on this date
            checkins = frappe.get_all("Employee Checkin",
                filters={
                    "employee": self.employee,
                    "time": ["between", [
                        f"{self.attendance_date} 00:00:00",
                        f"{self.attendance_date} 23:59:59"
                    ]]
                },
                fields=["name"]
            )
            
            # Update each checkin to link to this Custom Attendance via custom field
            for checkin in checkins:
                frappe.db.set_value("Employee Checkin", checkin.name, "custom_attendance_link", self.name)
            
            frappe.db.commit()
            frappe.logger().info(f"Updated {len(checkins)} checkins with custom attendance link: {self.name}")
            
        except Exception as e:
            frappe.log_error(f"Error updating employee checkin custom links: {str(e)}", "Custom Attendance")

    def remove_employee_checkin_links(self):
        """Remove custom attendance links from Employee Checkin records"""
        if not self.employee or not self.attendance_date:
            return
            
        try:
            # Get all checkins linked to this Custom Attendance
            checkins = frappe.get_all("Employee Checkin",
                filters={
                    "custom_attendance_link": self.name
                },
                fields=["name"]
            )
            
            # Remove custom attendance link from each checkin
            for checkin in checkins:
                frappe.db.set_value("Employee Checkin", checkin.name, "custom_attendance_link", "")
            
            frappe.db.commit()
            frappe.logger().info(f"Removed custom attendance links from {len(checkins)} checkins")
            
        except Exception as e:
            frappe.log_error(f"Error removing employee checkin custom links: {str(e)}", "Custom Attendance")

    def check_late_early(self):
        """Check for late entry and early exit based on shift timings"""
        if not self.shift:
            return
            
        try:
            shift = frappe.get_doc("Shift Type", self.shift)
            
            if self.check_in and shift.start_time:
                check_in_time = get_datetime(self.check_in).time()
                shift_start_time = timedelta_to_time_helper(shift.start_time)
                
                if shift_start_time and isinstance(shift_start_time, time):
                    if check_in_time > shift_start_time:
                        self.late_entry = 1
                else:
                    frappe.log_error(f"Invalid shift_start_time type: {type(shift_start_time)}", "Custom Attendance Late Check")
            
            if self.check_out and shift.end_time:
                check_out_time = get_datetime(self.check_out).time()
                shift_end_time = timedelta_to_time_helper(shift.end_time)
                
                if shift_end_time and isinstance(shift_end_time, time):
                    if check_out_time < shift_end_time:
                        self.early_exit = 1
                else:
                    frappe.log_error(f"Invalid shift_end_time type: {type(shift_end_time)}", "Custom Attendance Early Check")
                    
        except Exception as e:
            frappe.log_error(f"Error checking late/early: {str(e)}", "Custom Attendance Late/Early Check")

    @frappe.whitelist()
    def manual_sync(self):
        """Manual sync method triggered by button"""
        return sync_attendance_from_checkin_data(self)

    @frappe.whitelist()
    def get_employee_checkins(self):
        """Get all Employee Checkin records for this attendance with both links"""
        if not self.employee or not self.attendance_date:
            return []
            
        checkins = frappe.get_all("Employee Checkin",
            filters={
                "employee": self.employee,
                "time": ["between", [
                    f"{self.attendance_date} 00:00:00",
                    f"{self.attendance_date} 23:59:59"
                ]]
            },
            fields=[
                "name", 
                "time", 
                "log_type", 
                "device_id", 
                "shift", 
                "custom_attendance_link"
            ],
            order_by="time asc"
        )
        
        return checkins

    @frappe.whitelist()
    def get_connections_data(self):
        """Get connections data for display in form with enhanced info"""
        checkins = self.get_employee_checkins()
        return {
            "checkins": checkins,
            "total_count": len(checkins),
            "custom_linked_count": len([c for c in checkins if c.get('custom_attendance_link') == self.name]),
            "standard_linked_count": len([c for c in checkins if c.get('attendance')]),
            "unlinked_count": len([c for c in checkins if not c.get('attendance') and not c.get('custom_attendance_link')])
        }

    @frappe.whitelist()
    def get_overtime_details(self):
        """Get detailed overtime information"""
        return get_overtime_details_for_doc(self)

    @frappe.whitelist()
    def calculate_with_overtime(self):
        """Method to be called from Custom Attendance document"""
        from .modules.overtime_calculator import calculate_working_hours_with_overtime_for_doc
        
        result = calculate_working_hours_with_overtime_for_doc(self)
        
        # Save if successful
        if result["working_hours"] > 0:
            self.flags.ignore_validate_update_after_submit = True
            self.save(ignore_permissions=True)
            
        return result

    @frappe.whitelist()
    def recalculate_with_shift_registration(self):
        """
        NEW METHOD: Recalculate working hours với shift registration
        """
        try:
            # Update shift from registration
            self.update_shift_from_registration()
            
            # Recalculate working hours
            if self.check_in and self.check_out:
                self.calculate_working_hours()
                
                # Recalculate overtime
                self.auto_calculate_overtime()
                
                # Save changes
                self.flags.ignore_validate_update_after_submit = True
                self.save(ignore_permissions=True)
                
                return {
                    "success": True,
                    "working_hours": self.working_hours,
                    "overtime_hours": self.overtime_hours,
                    "shift_used": self.shift,
                    "message": f"Successfully recalculated with shift: {self.shift}"
                }
            else:
                return {
                    "success": False,
                    "message": "Check-in and check-out times required"
                }
                
        except Exception as e:
            error_msg = f"Error recalculating with shift registration: {str(e)}"
            frappe.log_error(error_msg, "Recalculate Shift Registration")
            return {
                "success": False,
                "message": error_msg
            }

    def recalculate_working_hours_with_overtime(self):
        """Update working hours including overtime"""
        try:
            if not self.check_in or not self.check_out:
                return False
                
            from .modules.overtime_calculator import calculate_working_hours_with_overtime_for_doc
            result = calculate_working_hours_with_overtime_for_doc(self)
            
            if result["working_hours"] > 0:
                self.working_hours = result["working_hours"]
                self.overtime_hours = result["overtime_hours"]
                return True
                
            return False
            
        except Exception as e:
            frappe.log_error(f"Error in recalculate_working_hours_with_overtime: {str(e)}", "Custom Attendance Overtime")
            return False


# Utility functions for backwards compatibility
def check_attendance_exists(employee, attendance_date, exclude_name=None):
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


# Hook handlers
def on_checkin_creation(doc, method):
    """Automatically create or update attendance when checkin is created"""
    if doc.log_type not in ["IN", "OUT"]:
        return
        
    attendance_date = getdate(doc.time)
    
    # Check if Custom Attendance record exists
    existing_attendance = frappe.db.exists("Custom Attendance", {
        "employee": doc.employee,
        "attendance_date": attendance_date,
        "docstatus": ["!=", 2]
    })
    
    if existing_attendance:
        # Update existing record
        try:
            attendance_doc = frappe.get_doc("Custom Attendance", existing_attendance)
            if attendance_doc.auto_sync_enabled:
                sync_attendance_from_checkin_data(attendance_doc)
        except Exception as e:
            frappe.log_error(f"Failed to update attendance: {str(e)}")
    else:
        # Create new attendance record only if auto_sync is desired
        try:
            employee_doc = frappe.get_doc("Employee", doc.employee)
            
            # Check if employee wants auto attendance creation
            if not getattr(employee_doc, 'create_auto_attendance', True):
                return
                
            new_attendance = frappe.new_doc("Custom Attendance")
            new_attendance.employee = doc.employee
            new_attendance.employee_name = employee_doc.employee_name
            new_attendance.attendance_date = attendance_date
            new_attendance.company = employee_doc.company
            new_attendance.auto_sync_enabled = 1
            new_attendance.status = "Absent"  # Default status
            
            # UPDATED: Set shift từ registration hoặc default
            registered_shift = get_registered_shift_for_employee(doc.employee, attendance_date)
            if registered_shift:
                new_attendance.shift = registered_shift
            elif hasattr(employee_doc, 'default_shift') and employee_doc.default_shift:
                new_attendance.shift = employee_doc.default_shift
            
            # Skip duplicate check during auto creation
            new_attendance.flags.ignore_auto_sync = True
            new_attendance.flags.ignore_duplicate_check = True
            
            new_attendance.save()
            sync_attendance_from_checkin_data(new_attendance)
            
        except Exception as e:
            frappe.log_error(f"Failed to create attendance from checkin: {str(e)}")

# Bulk Update Attendance Shift & Working Hours
# Thêm vào cuối file custom_attendance.py

@frappe.whitelist()
def update_submitted_attendance_with_shift_registration(attendance_name):
    """
    FIXED VERSION: Update 1 attendance record đã submit với shift registration mới
    """
    try:
        # Validate input
        if not attendance_name:
            return {
                "success": False,
                "message": "Attendance name is required"
            }
        
        # Check if attendance exists
        if not frappe.db.exists("Custom Attendance", attendance_name):
            return {
                "success": False,
                "message": f"Attendance record {attendance_name} not found"
            }
        
        # Get attendance document
        attendance_doc = frappe.get_doc("Custom Attendance", attendance_name)
        
        if attendance_doc.docstatus != 1:
            return {
                "success": False,
                "message": "Only submitted attendance can be updated"
            }
        
        # Check shift registration
        old_shift = attendance_doc.shift or ""
        registered_shift = get_registered_shift_for_employee(
            attendance_doc.employee, 
            attendance_doc.attendance_date
        )
        
        if not registered_shift:
            return {
                "success": False,
                "message": "No shift registration found for this employee/date"
            }
        
        if old_shift == registered_shift:
            return {
                "success": False,
                "message": f"Shift already set to {registered_shift}"
            }
        
        # Store old values
        old_working_hours = attendance_doc.working_hours or 0
        old_overtime_hours = attendance_doc.overtime_hours or 0
        
        # Update submitted document safely
        frappe.db.set_value("Custom Attendance", attendance_name, "shift", registered_shift)
        
        # Recalculate working hours if check times exist
        new_working_hours = old_working_hours
        new_overtime_hours = old_overtime_hours
        
        if attendance_doc.check_in and attendance_doc.check_out:
            try:
                # Create temporary doc for calculation
                temp_doc = frappe.get_doc("Custom Attendance", attendance_name)
                temp_doc.reload()  # Reload to get updated shift
                
                # Recalculate
                temp_doc.calculate_working_hours()
                new_working_hours = temp_doc.working_hours or 0
                
                # Update working hours in database
                frappe.db.set_value("Custom Attendance", attendance_name, "working_hours", new_working_hours)
                
                # Recalculate overtime
                temp_doc.auto_calculate_overtime()
                new_overtime_hours = temp_doc.overtime_hours or 0
                frappe.db.set_value("Custom Attendance", attendance_name, "overtime_hours", new_overtime_hours)
                
            except Exception as calc_error:
                frappe.log_error(f"Error recalculating hours for {attendance_name}: {str(calc_error)}", "Recalculation Error")
                # Continue with shift update even if calculation fails
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": f"Updated shift from '{old_shift}' to '{registered_shift}'",
            "old_shift": old_shift,
            "new_shift": registered_shift,
            "old_working_hours": old_working_hours,
            "new_working_hours": new_working_hours,
            "old_overtime_hours": old_overtime_hours,
            "new_overtime_hours": new_overtime_hours
        }
        
    except Exception as e:
        error_msg = f"Error updating submitted attendance: {str(e)}"
        frappe.log_error(error_msg, "Update Submitted Attendance Error")
        return {
            "success": False,
            "message": error_msg,
            "old_shift": "",
            "new_shift": "",
            "old_working_hours": 0,
            "new_working_hours": 0
        }


@frappe.whitelist()
def bulk_update_attendance_with_shift_registration(filters=None):
    """
    FIXED VERSION: Bulk update multiple attendance records với shift registration
    """
    try:
        # FIX: Ensure filters is dict
        if filters is None:
            filters = {}
        elif isinstance(filters, str):
            import json
            try:
                filters = json.loads(filters)
            except:
                filters = {}
        
        if not isinstance(filters, dict):
            filters = {}
        
        # Ensure only submitted documents
        filters["docstatus"] = 1
        
        # Get attendance records
        attendance_records = frappe.get_all("Custom Attendance",
            filters=filters,
            fields=["name", "employee", "employee_name", "attendance_date", "shift", "working_hours"]
        )
        
        if not attendance_records:
            return {
                "success": False,
                "message": "No attendance records found with given filters",
                "total_records": 0,
                "results": []
            }
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        results = []
        
        for record in attendance_records:
            try:
                # Check if employee has shift registration for this date
                registered_shift = get_registered_shift_for_employee(
                    record.employee, 
                    record.attendance_date
                )
                
                if not registered_shift:
                    skipped_count += 1
                    results.append({
                        "name": record.name,
                        "employee": record.employee,
                        "employee_name": record.employee_name,
                        "date": str(record.attendance_date),
                        "status": "skipped",
                        "reason": "No shift registration found"
                    })
                    continue
                
                if record.shift == registered_shift:
                    skipped_count += 1
                    results.append({
                        "name": record.name,
                        "employee": record.employee,
                        "employee_name": record.employee_name,
                        "date": str(record.attendance_date),
                        "status": "skipped",
                        "reason": f"Already has correct shift: {registered_shift}"
                    })
                    continue
                
                # FIX: Update the record with proper error handling
                update_result = update_submitted_attendance_with_shift_registration(record.name)
                
                # FIX: Ensure update_result is dict
                if not isinstance(update_result, dict):
                    error_count += 1
                    results.append({
                        "name": record.name,
                        "employee": record.employee,
                        "employee_name": record.employee_name,
                        "date": str(record.attendance_date),
                        "status": "error",
                        "reason": f"Invalid response from update function: {str(update_result)}"
                    })
                    continue
                
                # Check if update was successful
                if update_result.get("success", False):
                    updated_count += 1
                    results.append({
                        "name": record.name,
                        "employee": record.employee,
                        "employee_name": record.employee_name,
                        "date": str(record.attendance_date),
                        "status": "updated",
                        "old_shift": update_result.get("old_shift", ""),
                        "new_shift": update_result.get("new_shift", ""),
                        "old_working_hours": update_result.get("old_working_hours", 0),
                        "new_working_hours": update_result.get("new_working_hours", 0)
                    })
                else:
                    error_count += 1
                    results.append({
                        "name": record.name,
                        "employee": record.employee,
                        "employee_name": record.employee_name,
                        "date": str(record.attendance_date),
                        "status": "error",
                        "reason": update_result.get("message", "Unknown error")
                    })
                    
            except Exception as record_error:
                error_count += 1
                frappe.log_error(f"Error processing record {record.name}: {str(record_error)}", "Bulk Update Record Error")
                results.append({
                    "name": record.name,
                    "employee": record.employee,
                    "employee_name": getattr(record, 'employee_name', ''),
                    "date": str(record.attendance_date),
                    "status": "error",
                    "reason": f"Processing error: {str(record_error)}"
                })
        
        return {
            "success": True,
            "total_records": len(attendance_records),
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "results": results,
            "message": f"Processed {len(attendance_records)} records: {updated_count} updated, {skipped_count} skipped, {error_count} errors"
        }
        
    except Exception as e:
        error_msg = f"Bulk update failed: {str(e)}"
        frappe.log_error(error_msg, "Bulk Update Attendance Error")
        return {
            "success": False,
            "message": error_msg,
            "total_records": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "results": []
        }



@frappe.whitelist()
def get_attendance_records_for_update(employee=None, from_date=None, to_date=None):
    """
    Get list of attendance records that can be updated với shift registration
    """
    try:
        filters = {
            "docstatus": 1  # Only submitted
        }
        
        if employee:
            filters["employee"] = employee
            
        if from_date and to_date:
            filters["attendance_date"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["attendance_date"] = [">=", from_date]
        elif to_date:
            filters["attendance_date"] = ["<=", to_date]
        
        attendance_records = frappe.get_all("Custom Attendance",
            filters=filters,
            fields=[
                "name", "employee", "employee_name", "attendance_date", 
                "shift", "working_hours", "overtime_hours", "status"
            ],
            order_by="attendance_date desc"
        )
        
        # Check each record for potential shift updates
        updateable_records = []
        
        for record in attendance_records:
            registered_shift = get_registered_shift_for_employee(
                record.employee, 
                record.attendance_date
            )
            
            if registered_shift and registered_shift != record.shift:
                record["has_registration"] = True
                record["registered_shift"] = registered_shift
                record["can_update"] = True
                updateable_records.append(record)
            else:
                record["has_registration"] = bool(registered_shift)
                record["registered_shift"] = registered_shift
                record["can_update"] = False
                # Add to list anyway for display
                updateable_records.append(record)
        
        return {
            "success": True,
            "records": updateable_records,
            "total_count": len(updateable_records),
            "updateable_count": len([r for r in updateable_records if r["can_update"]])
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error getting records: {str(e)}"
        }


# Thêm method này vào class CustomAttendance

@frappe.whitelist()
def update_shift_and_recalculate(self):
    """
    Method để update shift và recalculate cho submitted document
    """
    try:
        if self.docstatus != 1:
            return {
                "success": False,
                "message": "Document must be submitted to update"
            }
        
        # Get registered shift
        registered_shift = get_registered_shift_for_employee(self.employee, self.attendance_date)
        
        if not registered_shift:
            return {
                "success": False,
                "message": "No shift registration found"
            }
        
        old_shift = self.shift
        old_working_hours = self.working_hours
        
        if old_shift == registered_shift:
            return {
                "success": False,
                "message": f"Shift already set to {registered_shift}"
            }
        
        # Update fields in database (bypass submit validation)
        frappe.db.set_value("Custom Attendance", self.name, "shift", registered_shift)
        
        # Reload and recalculate
        self.reload()
        if self.check_in and self.check_out:
            self.calculate_working_hours()
            self.auto_calculate_overtime()
            
            # Update in database
            frappe.db.set_value("Custom Attendance", self.name, "working_hours", self.working_hours)
            frappe.db.set_value("Custom Attendance", self.name, "overtime_hours", self.overtime_hours)
        
        frappe.db.commit()
        
        return {
            "success": True,
            "old_shift": old_shift,
            "new_shift": registered_shift,
            "old_working_hours": old_working_hours,
            "new_working_hours": self.working_hours,
            "message": f"Updated shift and recalculated working hours"
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }