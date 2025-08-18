# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

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


class CustomAttendance(Document):
    """
    Main Custom Attendance Document Class
    Handles core attendance functionality
    """
    
    def validate(self):
        """Validate attendance data"""
        # Check for duplicate attendance - including drafts
        validate_duplicate_attendance(self)
        
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

    def calculate_realistic_working_hours(self, in_time, out_time):
        """
        Tính working hours theo logic thực tế:
        1. Effective start = max(check_in, shift_start)
        2. Effective end = min(check_out, shift_end)  
        3. Trừ break chỉ khi overlap
        """
        
        if not self.shift:
            # Fallback: tính theo thời gian thực tế
            total_hours = time_diff_in_hours(out_time, in_time)
            return max(0, flt(total_hours, 2))
        
        try:
            # Lấy shift document
            shift_doc = frappe.get_cached_doc("Shift Type", self.shift)
            
            if not shift_doc.start_time or not shift_doc.end_time:
                # Fallback: tính theo thời gian thực tế
                total_hours = time_diff_in_hours(out_time, in_time)
                return max(0, flt(total_hours, 2))
            
            # Lấy ngày làm việc
            work_date = in_time.date()
            
            # Convert timedelta to time (ERPNext stores time as timedelta)
            shift_start_time = timedelta_to_time_helper(shift_doc.start_time)
            shift_end_time = timedelta_to_time_helper(shift_doc.end_time)
            
            # Thời gian shift trong ngày
            shift_start_datetime = datetime.combine(work_date, shift_start_time)
            shift_end_datetime = datetime.combine(work_date, shift_end_time)
            
            # Xử lý shift qua ngày (VD: 22:00-06:00)
            if shift_end_datetime <= shift_start_datetime:
                if in_time.time() >= shift_start_time:
                    # Check-in trong ngày hiện tại, end time sang ngày mai
                    shift_end_datetime += timedelta(days=1)
                else:
                    # Check-in vào ngày mai, start time là ngày hôm trước
                    shift_start_datetime -= timedelta(days=1)
            
            # Tính effective working time
            effective_start = max(in_time, shift_start_datetime)
            effective_end = min(out_time, shift_end_datetime)
            
            # Nếu effective_end <= effective_start → không có thời gian làm việc
            if effective_end <= effective_start:
                return 0.0
            
            # Tính tổng thời gian làm việc
            total_working_hours = time_diff_in_hours(effective_end, effective_start)
            
            # Trừ break time nếu overlap
            break_overlap_hours = self.calculate_break_overlap_realistic(shift_doc, effective_start, effective_end)
            
            final_hours = total_working_hours - break_overlap_hours
            
            return max(0, flt(final_hours, 2))
            
        except Exception as e:
            frappe.log_error(f"Error in calculate_realistic_working_hours: {str(e)}", "Custom Attendance")
            # Fallback: tính theo thời gian thực tế
            total_hours = time_diff_in_hours(out_time, in_time)
            return max(0, flt(total_hours, 2))

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
            
            # Skip duplicate check during auto creation
            new_attendance.flags.ignore_auto_sync = True
            new_attendance.flags.ignore_duplicate_check = True
            
            new_attendance.save()
            sync_attendance_from_checkin_data(new_attendance)
            
        except Exception as e:
            frappe.log_error(f"Failed to create attendance from checkin: {str(e)}")