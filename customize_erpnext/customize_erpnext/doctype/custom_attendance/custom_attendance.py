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
            # KHÔNG can thiệp vào field 'attendance' gốc
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
                "custom_attendance_link"  # Link mới đến Custom Attendance
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
            
            return f"Synced successfully!"
            
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

# Scheduler Logic:

# Thêm vào file custom_attendance.py

def daily_custom_attendance_sync():
    """Daily job để sync tất cả Custom Attendance records chưa được sync"""
    try:
        yesterday = getdate() - timedelta(days=1)
        
        # Get all Custom Attendance records từ hôm qua cần sync
        records_to_sync = frappe.get_all("Custom Attendance",
            filters={
                "attendance_date": yesterday,
                "auto_sync_enabled": 1,
                "docstatus": 0,
                # Chỉ sync những record chưa có data hoặc chưa sync gần đây
                "last_sync_time": ["is", "not set"]
            },
            fields=["name", "employee", "attendance_date"]
        )
        
        synced_count = 0
        failed_count = 0
        
        for record in records_to_sync:
            try:
                doc = frappe.get_doc("Custom Attendance", record.name)
                result = doc.sync_from_checkin()
                
                if "successfully" in str(result).lower():
                    synced_count += 1
                else:
                    failed_count += 1
                    
                frappe.db.commit()
                
            except Exception as e:
                failed_count += 1
                frappe.log_error(f"Daily sync failed for {record.name}: {str(e)}", "Daily Custom Attendance Sync")
                continue
        
        frappe.logger().info(f"Daily Custom Attendance Sync completed: {synced_count} synced, {failed_count} failed")
        
    except Exception as e:
        frappe.log_error(f"Error in daily_custom_attendance_sync: {str(e)}", "Daily Custom Attendance Sync")

def on_checkin_update(doc, method):
    """Trigger khi Employee Checkin được update"""
    try:
        if not doc.time or not doc.employee:
            return
            
        attendance_date = getdate(doc.time)
        
        # Tìm Custom Attendance record tương ứng
        custom_attendance = frappe.db.get_value("Custom Attendance", {
            "employee": doc.employee,
            "attendance_date": attendance_date,
            "auto_sync_enabled": 1,
            "docstatus": 0
        })
        
        if custom_attendance:
            # Auto sync nếu có Custom Attendance record
            try:
                ca_doc = frappe.get_doc("Custom Attendance", custom_attendance)
                ca_doc.sync_from_checkin()
                frappe.logger().info(f"Auto-synced Custom Attendance {custom_attendance} after checkin update")
            except Exception as e:
                frappe.log_error(f"Auto-sync failed after checkin update: {str(e)}", "Custom Attendance Auto Sync")
                
    except Exception as e:
        frappe.log_error(f"Error in on_checkin_update: {str(e)}", "Custom Attendance Checkin Update")

def on_shift_update(doc, method):
    """Trigger khi Shift Type được update"""
    try:
        # Nếu shift times thay đổi, có thể cần re-calculate working hours
        if doc.has_value_changed("start_time") or doc.has_value_changed("end_time"):
            # Get Custom Attendance records sử dụng shift này từ 7 ngày qua
            recent_date = getdate() - timedelta(days=7)
            
            affected_records = frappe.get_all("Custom Attendance",
                filters={
                    "shift": doc.name,
                    "attendance_date": [">=", recent_date],
                    "docstatus": 0
                },
                fields=["name"]
            )
            
            # Re-calculate working hours cho affected records
            for record in affected_records:
                try:
                    ca_doc = frappe.get_doc("Custom Attendance", record.name)
                    if ca_doc.check_in and ca_doc.check_out:
                        ca_doc.calculate_working_hours()
                        ca_doc.save(ignore_permissions=True)
                except Exception as e:
                    frappe.log_error(f"Error recalculating hours for {record.name}: {str(e)}", "Shift Update Impact")
                    continue
                    
            if affected_records:
                frappe.logger().info(f"Recalculated working hours for {len(affected_records)} Custom Attendance records after shift update")
                
    except Exception as e:
        frappe.log_error(f"Error in on_shift_update: {str(e)}", "Custom Attendance Shift Update")

# Thêm configuration options
@frappe.whitelist()
def get_auto_attendance_settings():
    """Get auto attendance settings"""
    return {
        "enabled": frappe.db.get_single_value("HR Settings", "auto_attendance") or False,
        "tolerance_minutes": frappe.db.get_single_value("HR Settings", "attendance_tolerance") or 30,
        "auto_sync_enabled": True  # Default cho Custom Attendance
    }

@frappe.whitelist()
def configure_auto_attendance(settings):
    """Configure auto attendance settings"""
    try:
        if isinstance(settings, str):
            settings = json.loads(settings)
            
        # Update HR Settings nếu cần
        if "tolerance_minutes" in settings:
            frappe.db.set_single_value("HR Settings", "attendance_tolerance", settings["tolerance_minutes"])
            
        # Log configuration change
        frappe.logger().info(f"Auto attendance settings updated: {settings}")
        
        return {"success": True, "message": "Settings updated successfully"}
        
    except Exception as e:
        frappe.log_error(f"Error configuring auto attendance: {str(e)}", "Auto Attendance Config")
        return {"success": False, "message": str(e)}

# Manual trigger functions for testing
@frappe.whitelist()
def manual_auto_update(date=None):
    """Manual trigger để test auto update"""
    try:
        if not date:
            date = getdate()
        else:
            date = getdate(date)
            
        # Run auto update cho specific date
        current_time = now_datetime()
        
        # Simulate shift completion cho tất cả shifts
        shifts = frappe.get_all("Shift Type", 
            filters={"disabled": 0, "enable_auto_attendance": 1},
            fields=["name", "start_time", "end_time"]
        )
        
        processed = 0
        for shift in shifts:
            employees = get_employees_for_auto_update(shift.name, date)
            for employee in employees:
                if process_employee_auto_attendance(employee, date, shift.name):
                    processed += 1
        
        return {"success": True, "message": f"Processed {processed} records for {date}"}
        
    except Exception as e:
        return {"success": False, "message": str(e)}

@frappe.whitelist()
def bulk_sync_custom_attendance(date_from, date_to):
    """Bulk sync Custom Attendance records trong date range"""
    try:
        from frappe.utils import getdate
        
        date_from = getdate(date_from)
        date_to = getdate(date_to)
        
        records = frappe.get_all("Custom Attendance",
            filters={
                "attendance_date": ["between", [date_from, date_to]],
                "auto_sync_enabled": 1,
                "docstatus": 0
            },
            fields=["name", "employee", "attendance_date"]
        )
        
        success_count = 0
        error_count = 0
        
        for record in records:
            try:
                doc = frappe.get_doc("Custom Attendance", record.name)
                doc.sync_from_checkin()
                success_count += 1
                frappe.db.commit()
            except Exception as e:
                error_count += 1
                frappe.log_error(f"Bulk sync error for {record.name}: {str(e)}", "Bulk Sync Custom Attendance")
                continue
        
        return {
            "success": True, 
            "message": f"Bulk sync completed: {success_count} success, {error_count} errors",
            "success_count": success_count,
            "error_count": error_count
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}

def smart_auto_update_custom_attendance():
    """
    Smart scheduler - chỉ chạy khi shifts thực sự kết thúc + tolerance time
    Thay vì chạy mỗi 15 phút, chỉ chạy khi cần thiết
    """
    try:
        current_time = now_datetime()
        current_date = getdate()
        
        # Get all active shifts có auto attendance enabled
        shifts = get_shifts_ready_for_processing(current_time)
        
        if not shifts:
            return  # Không có shift nào cần process
            
        processed_count = 0
        
        for shift_info in shifts:
            try:
                employees = get_employees_for_shift_processing(shift_info)
                
                for employee in employees:
                    if process_employee_custom_attendance(employee, shift_info):
                        processed_count += 1
                        
            except Exception as e:
                frappe.log_error(f"Error processing shift {shift_info['name']}: {str(e)}", "Smart Auto Custom Attendance")
                continue
        
        if processed_count > 0:
            frappe.logger().info(f"Smart auto-update processed {processed_count} Custom Attendance records")
            
    except Exception as e:
        frappe.log_error(f"Error in smart_auto_update_custom_attendance: {str(e)}", "Smart Auto Custom Attendance")

def get_shifts_ready_for_processing(current_time):
    """
    Get shifts sẵn sàng để process based on end time + tolerance
    Chỉ return shifts thực sự cần process ngay bây giờ
    """
    try:
        # Get all active shifts with auto attendance enabled
        shifts = frappe.db.sql("""
            SELECT 
                name, 
                start_time, 
                end_time, 
                allow_check_out_after_shift_end_time,
                process_attendance_after,
                last_sync_of_checkin
            FROM `tabShift Type`
            WHERE disabled = 0 
            AND enable_auto_attendance = 1
        """, as_dict=True)
        
        ready_shifts = []
        
        for shift in shifts:
            if is_shift_ready_for_processing(shift, current_time):
                # Add processing info
                shift['processing_date'] = calculate_processing_date(shift, current_time)
                shift['tolerance_minutes'] = cint(shift.get('allow_check_out_after_shift_end_time', 60))
                ready_shifts.append(shift)
        
        return ready_shifts
        
    except Exception as e:
        frappe.log_error(f"Error getting ready shifts: {str(e)}", "Smart Auto Custom Attendance")
        return []

def is_shift_ready_for_processing(shift, current_time):
    """
    Check if shift is ready for processing dựa trên ERPNext logic:
    1. Shift đã kết thúc + tolerance time
    2. Sau process_attendance_after date
    3. Chưa process gần đây (tránh duplicate)
    """
    try:
        # Check process_attendance_after date
        if shift.process_attendance_after and getdate() < getdate(shift.process_attendance_after):
            return False
            
        if not shift.end_time:
            return False
            
        # Calculate actual shift end time + tolerance
        tolerance_minutes = cint(shift.get('allow_check_out_after_shift_end_time', 60))
        
        # Convert shift end time to datetime
        end_time = shift.end_time
        if hasattr(end_time, 'total_seconds'):
            total_seconds = int(end_time.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            end_time = datetime.min.time().replace(hour=hours, minute=minutes)
        
        # Determine which date this shift ended
        shift_date = current_time.date()
        
        # Handle overnight shifts
        if shift.start_time and shift.end_time <= shift.start_time:
            # Overnight shift - end time is next day
            if current_time.time() < end_time:
                # We're in the next day, shift ended today
                shift_end_datetime = datetime.combine(shift_date, end_time)
            else:
                # We're still in same day, shift will end tomorrow
                shift_end_datetime = datetime.combine(shift_date + timedelta(days=1), end_time)
        else:
            # Regular shift - same day
            shift_end_datetime = datetime.combine(shift_date, end_time)
        
        # Add tolerance time
        processing_time = shift_end_datetime + timedelta(minutes=tolerance_minutes)
        
        # Check if it's time to process (within 5-minute window để avoid missing)
        time_diff = (current_time - processing_time).total_seconds()
        
        # Ready if:
        # 1. Current time is after processing_time
        # 2. But not more than 30 minutes late (to avoid old processing)
        return 0 <= time_diff <= 1800  # 0-30 minutes after processing time
        
    except Exception as e:
        frappe.log_error(f"Error checking shift readiness: {str(e)}", "Smart Auto Custom Attendance")
        return False

def calculate_processing_date(shift, current_time):
    """Calculate which date this shift should be processed for"""
    try:
        if not shift.start_time or not shift.end_time:
            return current_time.date()
            
        # Convert times
        start_time = shift.start_time
        end_time = shift.end_time
        
        if hasattr(start_time, 'total_seconds'):
            total_seconds = int(start_time.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            start_time = datetime.min.time().replace(hour=hours, minute=minutes)
            
        if hasattr(end_time, 'total_seconds'):
            total_seconds = int(end_time.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            end_time = datetime.min.time().replace(hour=hours, minute=minutes)
        
        current_date = current_time.date()
        
        if end_time <= start_time:
            # Overnight shift
            if current_time.time() < end_time:
                # We're in the "next day" part of shift
                return current_date - timedelta(days=1)  # Attendance date is previous day
            else:
                return current_date  # Attendance date is today
        else:
            # Regular shift
            return current_date
            
    except Exception as e:
        frappe.log_error(f"Error calculating processing date: {str(e)}", "Smart Auto Custom Attendance")
        return current_time.date()

def get_employees_for_shift_processing(shift_info):
    """Get employees cần process cho shift này"""
    try:
        processing_date = shift_info['processing_date']
        
        # Get employees có checkins trong shift này và chưa có Custom Attendance
        employees = frappe.db.sql("""
            SELECT DISTINCT ec.employee, e.employee_name, e.company
            FROM `tabEmployee Checkin` ec
            JOIN `tabEmployee` e ON ec.employee = e.name
            WHERE DATE(ec.time) = %s
            AND (ec.shift = %s OR e.default_shift = %s)
            AND e.status = 'Active'
            AND NOT EXISTS (
                SELECT 1 FROM `tabCustom Attendance` ca 
                WHERE ca.employee = ec.employee 
                AND ca.attendance_date = %s
                AND ca.docstatus != 2
            )
        """, (processing_date, shift_info['name'], shift_info['name'], processing_date), as_dict=True)
        
        return employees
        
    except Exception as e:
        frappe.log_error(f"Error getting employees for shift processing: {str(e)}", "Smart Auto Custom Attendance")
        return []

def process_employee_custom_attendance(employee_info, shift_info):
    """Process Custom Attendance cho employee với shift info"""
    try:
        processing_date = shift_info['processing_date']
        
        # Create Custom Attendance
        custom_attendance = frappe.new_doc("Custom Attendance")
        custom_attendance.employee = employee_info['employee']
        custom_attendance.employee_name = employee_info['employee_name']
        custom_attendance.attendance_date = processing_date
        custom_attendance.company = employee_info['company']
        custom_attendance.shift = shift_info['name']
        custom_attendance.auto_sync_enabled = 1
        custom_attendance.status = "Absent"  # Will be updated after sync
        
        # Skip validations during auto creation
        custom_attendance.flags.ignore_validate = True
        custom_attendance.flags.ignore_auto_sync = True
        custom_attendance.flags.ignore_duplicate_check = True
        
        # Save
        custom_attendance.save(ignore_permissions=True)
        
        # Auto sync from checkins
        sync_result = custom_attendance.sync_from_checkin()
        
        frappe.logger().info(f"Auto-created Custom Attendance {custom_attendance.name} for {employee_info['employee']} (Shift: {shift_info['name']}, Date: {processing_date}): {sync_result}")
        
        return True
        
    except Exception as e:
        frappe.log_error(f"Error processing employee custom attendance: {str(e)}", "Smart Auto Custom Attendance")
        return False

# Updated hooks configuration
def get_smart_scheduler_events():
    """
    Return scheduler events based on shift timing
    Thay vì cron mỗi 15 phút, tính toán thời gian cần thiết
    """
    try:
        # Get all unique shift end times + tolerance
        shifts = frappe.db.sql("""
            SELECT DISTINCT 
                end_time, 
                allow_check_out_after_shift_end_time
            FROM `tabShift Type`
            WHERE disabled = 0 
            AND enable_auto_attendance = 1
            AND end_time IS NOT NULL
        """, as_dict=True)
        
        scheduler_times = []
        
        for shift in shifts:
            tolerance = cint(shift.get('allow_check_out_after_shift_end_time', 60))
            end_time = shift.end_time
            
            if hasattr(end_time, 'total_seconds'):
                total_seconds = int(end_time.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                
                # Calculate processing time = end_time + tolerance
                processing_minutes = minutes + tolerance
                processing_hours = hours + (processing_minutes // 60)
                processing_minutes = processing_minutes % 60
                processing_hours = processing_hours % 24
                
                # Create cron expression
                cron_expr = f"{processing_minutes} {processing_hours} * * *"
                scheduler_times.append(cron_expr)
        
        return scheduler_times
        
    except Exception as e:
        frappe.log_error(f"Error generating smart scheduler events: {str(e)}", "Smart Scheduler")
        return ["0 */2 * * *"]  # Fallback: every 2 hours

# Manual function để test logic
@frappe.whitelist()
def test_shift_processing_logic():
    """Test function để verify shift processing logic"""
    try:
        current_time = now_datetime()
        shifts = get_shifts_ready_for_processing(current_time)
        
        result = {
            "current_time": str(current_time),
            "ready_shifts": []
        }
        
        for shift in shifts:
            shift_info = {
                "name": shift['name'],
                "processing_date": str(shift['processing_date']),
                "tolerance_minutes": shift['tolerance_minutes'],
                "employees_count": len(get_employees_for_shift_processing(shift))
            }
            result["ready_shifts"].append(shift_info)
        
        return result
        
    except Exception as e:
        return {"error": str(e)}

# Thêm vào file custom_attendance.py

@frappe.whitelist()
def bulk_process_from_shift_date(shift_name=None, start_date=None, end_date=None):
    """
    Bulk create và sync Custom Attendance từ Process Attendance After date
    """
    try:
        from frappe.utils import getdate, date_diff
        
        results = {
            "success": True,
            "total_days": 0,
            "total_employees": 0,
            "created_count": 0,
            "synced_count": 0,
            "error_count": 0,
            "details": [],
            "errors": []
        }
        
        # Get date range
        if shift_name:
            # Lấy từ shift settings
            shift_doc = frappe.get_doc("Shift Type", shift_name)
            start_date = shift_doc.process_attendance_after or getdate() - timedelta(days=30)
        elif start_date:
            start_date = getdate(start_date)
        else:
            start_date = getdate() - timedelta(days=30)  # Default 30 ngày trước
            
        if not end_date:
            end_date = getdate()  # Đến hôm nay
        else:
            end_date = getdate(end_date)
            
        # Validate date range
        if start_date > end_date:
            return {"success": False, "message": "Start date cannot be after end date"}
            
        days_count = date_diff(end_date, start_date) + 1
        if days_count > 90:  # Limit để tránh overload
            return {"success": False, "message": "Date range too large (maximum 90 days)"}
        
        results["total_days"] = days_count
        
        frappe.logger().info(f"Starting bulk process from {start_date} to {end_date}")
        
        # Process từng ngày
        current_date = start_date
        while current_date <= end_date:
            try:
                day_result = process_single_day_bulk(current_date, shift_name)
                
                results["total_employees"] += day_result["employees_processed"]
                results["created_count"] += day_result["created_count"]
                results["synced_count"] += day_result["synced_count"]  
                results["error_count"] += day_result["error_count"]
                
                if day_result["created_count"] > 0 or day_result["error_count"] > 0:
                    results["details"].append({
                        "date": str(current_date),
                        "created": day_result["created_count"],
                        "synced": day_result["synced_count"],
                        "errors": day_result["error_count"]
                    })
                
                results["errors"].extend(day_result["errors"])
                
                # Commit sau mỗi ngày để tránh timeout
                frappe.db.commit()
                
            except Exception as e:
                error_msg = f"Error processing {current_date}: {str(e)}"
                results["errors"].append(error_msg)
                results["error_count"] += 1
                frappe.log_error(error_msg, "Bulk Process Custom Attendance")
                
            current_date += timedelta(days=1)
        
        # Summary message
        results["message"] = f"""Bulk processing completed:
        rocessed {results['total_days']} days
        Found {results['total_employees']} employee-days with check-ins
        Created {results['created_count']} Custom Attendance records
        Synced {results['synced_count']} records successfully
        {results['error_count']} errors encountered"""
        
        frappe.logger().info(f"Bulk process completed: {results['message']}")
        
        return results
        
    except Exception as e:
        error_msg = f"Error in bulk_process_from_shift_date: {str(e)}"
        frappe.log_error(error_msg, "Bulk Process Custom Attendance")
        return {"success": False, "message": error_msg}

def process_single_day_bulk(date, shift_name=None):
    """Process Custom Attendance cho một ngày cụ thể"""
    try:
        result = {
            "employees_processed": 0,
            "created_count": 0,
            "synced_count": 0,
            "error_count": 0,
            "errors": []
        }
        
        # Get employees có check-ins trong ngày này
        filters = {
            "DATE(time)": date,
            "employee": ["!=", ""]
        }
        
        if shift_name:
            # Lọc theo shift cụ thể
            filters["shift"] = shift_name
            
        # Query employees có checkins
        employees_with_checkins = frappe.db.sql("""
            SELECT DISTINCT 
                ec.employee, 
                e.employee_name, 
                e.company,
                COALESCE(ec.shift, e.default_shift) as shift_type
            FROM `tabEmployee Checkin` ec
            JOIN `tabEmployee` e ON ec.employee = e.name
            WHERE DATE(ec.time) = %s
            AND e.status = 'Active'
            {}
            AND NOT EXISTS (
                SELECT 1 FROM `tabCustom Attendance` ca 
                WHERE ca.employee = ec.employee 
                AND ca.attendance_date = %s
                AND ca.docstatus != 2
            )
        """.format("AND (ec.shift = %s OR e.default_shift = %s)" if shift_name else ""),
        (date, shift_name, shift_name, date) if shift_name else (date, date), as_dict=True)
        
        result["employees_processed"] = len(employees_with_checkins)
        
        # Tạo Custom Attendance cho từng employee
        for emp in employees_with_checkins:
            try:
                # Create Custom Attendance
                custom_attendance = frappe.new_doc("Custom Attendance")
                custom_attendance.employee = emp.employee
                custom_attendance.employee_name = emp.employee_name
                custom_attendance.attendance_date = date
                custom_attendance.company = emp.company
                custom_attendance.shift = emp.shift_type
                custom_attendance.auto_sync_enabled = 1
                custom_attendance.status = "Absent"  # Will be updated after sync
                
                # Skip validations during bulk creation
                custom_attendance.flags.ignore_validate = True
                custom_attendance.flags.ignore_auto_sync = True
                custom_attendance.flags.ignore_duplicate_check = True
                
                # Save
                custom_attendance.save(ignore_permissions=True)
                result["created_count"] += 1
                
                # Auto sync from checkins
                try:
                    sync_result = custom_attendance.sync_from_checkin()
                    if "successfully" in str(sync_result).lower() or "success" in str(sync_result).lower():
                        result["synced_count"] += 1
                    else:
                        result["errors"].append(f"{emp.employee} ({date}): Sync issue - {sync_result}")
                        
                except Exception as sync_error:
                    result["errors"].append(f"{emp.employee} ({date}): Sync failed - {str(sync_error)}")
                    
            except Exception as create_error:
                result["error_count"] += 1
                error_msg = f"{emp.employee} ({date}): Create failed - {str(create_error)}"
                result["errors"].append(error_msg)
                frappe.log_error(error_msg, "Bulk Process Single Employee")
                
        return result
        
    except Exception as e:
        return {
            "employees_processed": 0,
            "created_count": 0, 
            "synced_count": 0,
            "error_count": 1,
            "errors": [f"Day processing failed: {str(e)}"]
        }

@frappe.whitelist()
def get_bulk_process_preview(shift_name=None, start_date=None, end_date=None):
    """Preview data trước khi bulk process"""
    try:
        from frappe.utils import getdate, date_diff
        
        # Get date range
        if shift_name:
            shift_doc = frappe.get_doc("Shift Type", shift_name)
            start_date = shift_doc.process_attendance_after or getdate() - timedelta(days=30)
        elif start_date:
            start_date = getdate(start_date)
        else:
            start_date = getdate() - timedelta(days=30)
            
        if not end_date:
            end_date = getdate()
        else:
            end_date = getdate(end_date)
            
        # Get summary data
        preview_data = frappe.db.sql("""
            SELECT 
                DATE(ec.time) as attendance_date,
                COUNT(DISTINCT ec.employee) as employee_count,
                COUNT(ec.name) as checkin_count,
                COUNT(DISTINCT COALESCE(ec.shift, e.default_shift)) as shift_count
            FROM `tabEmployee Checkin` ec
            JOIN `tabEmployee` e ON ec.employee = e.name
            WHERE DATE(ec.time) BETWEEN %s AND %s
            AND e.status = 'Active'
            {}
            AND NOT EXISTS (
                SELECT 1 FROM `tabCustom Attendance` ca 
                WHERE ca.employee = ec.employee 
                AND ca.attendance_date = DATE(ec.time)
                AND ca.docstatus != 2
            )
            GROUP BY DATE(ec.time)
            ORDER BY DATE(ec.time)
        """.format("AND (ec.shift = %s OR e.default_shift = %s)" if shift_name else ""),
        (start_date, end_date, shift_name, shift_name) if shift_name else (start_date, end_date), as_dict=True)
        
        total_employees = sum([row.employee_count for row in preview_data])
        total_days = len(preview_data)
        
        return {
            "success": True,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "total_days": total_days,
            "total_employees": total_employees,  
            "daily_breakdown": preview_data,
            "shift_name": shift_name
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}