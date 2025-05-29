# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, get_datetime, now_datetime, time_diff_in_hours, flt
from datetime import datetime, timedelta, time


class CustomAttendance(Document):
    def validate(self):
        """Validate attendance data"""
        # Check for duplicate attendance - including drafts
        self.check_duplicate_attendance()
        
        if self.check_in and self.check_out:
            self.calculate_working_hours()
        
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
            shift_start_time = self.timedelta_to_time(shift_doc.start_time)
            shift_end_time = self.timedelta_to_time(shift_doc.end_time)
            
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

    def timedelta_to_time(self, td):
        """Convert timedelta to time object (ERPNext stores time as timedelta)"""
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
            break_start_time = self.timedelta_to_time(break_start_time)
            break_end_time = self.timedelta_to_time(break_end_time)
            
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

    def check_duplicate_attendance(self):
        """Check for duplicate attendance records - block ANY existing record for same employee + date"""
        if not self.employee or not self.attendance_date:
            return
            
        # Skip check if flagged to ignore
        if getattr(self.flags, 'ignore_duplicate_check', False):
            return
        
        # Check for ANY record (Draft, Submitted, Cancelled) for same employee + date
        existing_records = frappe.db.sql("""
            SELECT name, docstatus, status 
            FROM `tabCustom Attendance` 
            WHERE employee = %s 
            AND attendance_date = %s 
            AND name != %s
        """, (self.employee, self.attendance_date, self.name or ""), as_dict=True)
        
        if existing_records:
            existing_record = existing_records[0]
            status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
            record_status = status_map.get(existing_record.docstatus, "Unknown")
            
            frappe.throw(
                f"Attendance record already exists for {self.employee} on {self.attendance_date}<br>"
                f"Existing record: <strong>{existing_record.name}</strong> ({record_status})<br>"
                f"Please edit the existing record instead of creating a new one.",
                title="Duplicate Attendance Record"
            )

    def update_employee_checkin_links(self):
        """Update Employee Checkin records to link to this attendance"""
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
            
            # Update each checkin to link to this attendance
            for checkin in checkins:
                frappe.db.set_value("Employee Checkin", checkin.name, "attendance", self.name)
            
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(f"Error updating employee checkin links: {str(e)}", "Custom Attendance")

    def remove_employee_checkin_links(self):
        """Remove attendance links from Employee Checkin records"""
        if not self.employee or not self.attendance_date:
            return
            
        try:
            # Get all checkins linked to this attendance
            checkins = frappe.get_all("Employee Checkin",
                filters={
                    "attendance": self.name
                },
                fields=["name"]
            )
            
            # Remove attendance link from each checkin
            for checkin in checkins:
                frappe.db.set_value("Employee Checkin", checkin.name, "attendance", "")
            
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(f"Error removing employee checkin links: {str(e)}", "Custom Attendance")

    @frappe.whitelist()
    def get_employee_checkins(self):
        """Get all Employee Checkin records for this attendance"""
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
            fields=["name", "time", "log_type", "device_id", "shift", "attendance"],
            order_by="time asc"
        )
        
        return checkins

    @frappe.whitelist()
    def get_connections_data(self):
        """Get connections data for display in form"""
        checkins = self.get_employee_checkins()
        return {
            "checkins": checkins,
            "total_count": len(checkins),
            "linked_count": len([c for c in checkins if c.get('attendance') == self.name])
        }

    @frappe.whitelist()
    def sync_from_checkin(self):
        """Sync attendance data from Employee Checkin records"""
        try:
            # Get all checkins for the employee on the attendance date
            checkins = frappe.db.sql("""
                SELECT name, time, log_type, device_id, shift
                FROM `tabEmployee Checkin`
                WHERE employee = %s 
                AND DATE(time) = %s
                ORDER BY time ASC
            """, (self.employee, self.attendance_date), as_dict=True)
            
            if not checkins:
                return "No check-in records found for this date"
            
            # Get shift check-in/out type
            shift_doc = None
            check_in_out_type = "Alternating entries as IN and OUT during the same shift"
            
            if checkins[0].get('shift'):
                try:
                    shift_doc = frappe.get_doc("Shift Type", checkins[0].shift)
                    check_in_out_type = getattr(shift_doc, 'determine_check_in_and_check_out', 
                                              "Alternating entries as IN and OUT during the same shift")
                    self.shift = checkins[0].shift
                except:
                    pass
            
            # Extract in_time và out_time using your logic
            in_time, out_time = self.extract_in_out_times(checkins, check_in_out_type)
            
            # Update attendance record
            if in_time:
                self.check_in = in_time
                self.in_time = in_time.time() if in_time else None
                
            if out_time:
                self.check_out = out_time
                self.out_time = out_time.time() if out_time else None
            
            # Calculate working hours using realistic method
            if self.check_in and self.check_out:
                self.calculate_working_hours()
                self.status = "Present"
            elif self.check_in:
                self.status = "Present"
            else:
                self.status = "Absent"
            
            # Check for late entry and early exit
            self.check_late_early()
            
            # Update sync time
            self.last_sync_time = now_datetime()
            
            # Save without triggering validation conflicts
            self.flags.ignore_validate_update_after_submit = True
            self.flags.ignore_auto_sync = True
            self.db_update()
            
            # Update employee checkin links after sync
            self.update_employee_checkin_links()
            
            return f"Synced successfully! IN: {in_time}, OUT: {out_time}"
            
        except Exception as e:
            error_msg = str(e)
            # Simplify common error messages for users
            if "Document has been modified" in error_msg:
                simplified_msg = "Please refresh the page and try again"
            elif "Duplicate entry" in error_msg:
                simplified_msg = "This attendance record already exists"
            else:
                simplified_msg = f"Sync failed: {error_msg[:100]}..."
            
            frappe.log_error(f"Error syncing attendance: {error_msg}", "Custom Attendance Sync")
            return simplified_msg

    def extract_in_out_times(self, logs, check_in_out_type):
        """Extract in_time và out_time từ logs using your logic"""
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

    def check_late_early(self):
        """Check for late entry and early exit based on shift timings"""
        if not self.shift:
            return
            
        try:
            shift = frappe.get_doc("Shift Type", self.shift)
            
            if self.check_in and shift.start_time:
                check_in_time = get_datetime(self.check_in).time()
                shift_start_time = self.timedelta_to_time(shift.start_time)
                
                # Thêm validation để đảm bảo shift_start_time là time object
                if shift_start_time and isinstance(shift_start_time, time):
                    if check_in_time > shift_start_time:
                        self.late_entry = 1
                else:
                    frappe.log_error(f"Invalid shift_start_time type: {type(shift_start_time)}", "Custom Attendance Late Check")
            
            if self.check_out and shift.end_time:
                check_out_time = get_datetime(self.check_out).time()
                shift_end_time = self.timedelta_to_time(shift.end_time)
                
                # Thêm validation để đảm bảo shift_end_time là time object
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
        return self.sync_from_checkin()


# Utility functions
@frappe.whitelist()
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

@frappe.whitelist()
def create_attendance_force(employee, attendance_date, company=None):
    """Force create attendance without any validation"""
    try:
        # Get employee details
        employee_doc = frappe.get_doc("Employee", employee)
        
        # Create new record
        new_attendance = frappe.new_doc("Custom Attendance")
        new_attendance.employee = employee
        new_attendance.employee_name = employee_doc.employee_name
        new_attendance.attendance_date = attendance_date
        new_attendance.company = company or employee_doc.company
        new_attendance.auto_sync_enabled = 1
        new_attendance.status = "Absent"
        
        # Skip ALL validations
        new_attendance.flags.ignore_validate = True
        new_attendance.flags.ignore_mandatory = True
        new_attendance.flags.ignore_auto_sync = True
        new_attendance.flags.ignore_duplicate_check = True
        
        new_attendance.insert(ignore_permissions=True)
        
        return {"success": True, "record": new_attendance.name, "message": "Created successfully"}
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def create_attendance_safely(employee, attendance_date, company=None):
    """Create attendance record safely with duplicate check"""
    try:
        # Check for existing record
        check_result = check_attendance_exists(employee, attendance_date)
        if check_result["exists"]:
            return {"success": False, "message": f"Record already exists: {check_result['record']}"}
        
        # Get employee details
        employee_doc = frappe.get_doc("Employee", employee)
        
        # Create new record
        new_attendance = frappe.new_doc("Custom Attendance")
        new_attendance.employee = employee
        new_attendance.employee_name = employee_doc.employee_name
        new_attendance.attendance_date = attendance_date
        new_attendance.company = company or employee_doc.company
        new_attendance.auto_sync_enabled = 1
        new_attendance.status = "Absent"
        
        # Skip validations during creation
        new_attendance.flags.ignore_auto_sync = True
        new_attendance.flags.ignore_duplicate_check = True
        
        new_attendance.save()
        
        return {"success": True, "record": new_attendance.name, "message": "Created successfully"}
        
    except Exception as e:
        return {"success": False, "message": str(e)}


# API method to sync attendance from checkin
@frappe.whitelist()
def sync_attendance_from_checkin(doc_name):
    """API method to sync attendance from checkin"""
    try:
        doc = frappe.get_doc("Custom Attendance", doc_name)
        result = doc.sync_from_checkin()
        return result
    except Exception as e:
        frappe.log_error(f"API sync error: {str(e)}")
        return f"Error: {str(e)}"


# Scheduled job to auto-sync attendance records
def auto_sync_attendance():
    """Scheduled job to automatically sync attendance from checkins"""
    # Get all attendance records with auto_sync_enabled for yesterday
    yesterday = getdate() - timedelta(days=1)
    
    attendance_records = frappe.get_all("Custom Attendance", 
        filters={
            "auto_sync_enabled": 1,
            "attendance_date": yesterday,
            "docstatus": 0
        }, 
        fields=["name"]
    )
    
    for record in attendance_records:
        try:
            doc = frappe.get_doc("Custom Attendance", record.name)
            doc.sync_from_checkin()
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Auto sync failed for {record.name}: {str(e)}")
            continue


# Hook for Employee Checkin creation
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
                attendance_doc.sync_from_checkin()
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
            new_attendance.sync_from_checkin()
        except Exception as e:
            frappe.log_error(f"Failed to create attendance from checkin: {str(e)}")

@frappe.whitelist()
def debug_employee_checkins(employee, attendance_date):
    """Debug method to get employee checkins"""
    try:
        # Kiểm tra parameter
        if not employee or not attendance_date:
            return {
                "success": False, 
                "message": "Missing employee or attendance_date",
                "checkins": []
            }
        
        # Get checkins using direct SQL query
        checkins = frappe.db.sql("""
            SELECT 
                name, 
                time, 
                log_type, 
                device_id, 
                shift, 
                attendance,
                employee
            FROM `tabEmployee Checkin`
            WHERE employee = %s 
            AND DATE(time) = %s
            ORDER BY time ASC
        """, (employee, attendance_date), as_dict=True)
        
        # Format time for better display
        for checkin in checkins:
            if checkin.time:
                checkin.formatted_time = frappe.utils.format_datetime(checkin.time)
        
        return {
            "success": True,
            "message": f"Found {len(checkins)} checkin records",
            "checkins": checkins,
            "employee": employee,
            "attendance_date": attendance_date
        }
        
    except Exception as e:
        frappe.log_error(f"Debug employee checkins error: {str(e)}", "Custom Attendance Debug")
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "checkins": []
        }