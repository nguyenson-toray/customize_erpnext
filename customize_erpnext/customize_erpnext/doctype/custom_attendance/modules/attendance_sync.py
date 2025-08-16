# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, get_datetime, now_datetime, time_diff_in_hours, flt
from datetime import datetime, timedelta
from .attendance_utils import (
    extract_in_out_times_helper, 
    get_shift_type_info, 
    validate_time_range,
    sanitize_time_input
)


def sync_attendance_from_checkin_data(doc):
    """Sync attendance data from Employee Checkin records"""
    try:
        # Get all checkins for the employee on the attendance date
        checkins = frappe.db.sql("""
            SELECT name, time, log_type, device_id, shift
            FROM `tabEmployee Checkin`
            WHERE employee = %s 
            AND DATE(time) = %s
            ORDER BY time ASC
        """, (doc.employee, doc.attendance_date), as_dict=True)
        
        if not checkins:
            return "No check-in records found for this date"
        
        # Get shift check-in/out type
        shift_info = None
        check_in_out_type = "Alternating entries as IN and OUT during the same shift"
        
        if checkins[0].get('shift'):
            shift_info = get_shift_type_info(checkins[0].shift)
            if shift_info:
                check_in_out_type = shift_info.get('determine_check_in_and_check_out', 
                                                  "Alternating entries as IN and OUT during the same shift")
                doc.shift = checkins[0].shift
        
        # Extract in_time và out_time using logic
        in_time, out_time = extract_in_out_times(checkins, check_in_out_type)
        
        # Update attendance record
        if in_time:
            doc.check_in = in_time
            doc.in_time = in_time.time() if in_time else None
            
        if out_time:
            doc.check_out = out_time
            doc.out_time = out_time.time() if out_time else None
        
        # Calculate working hours using realistic method
        if doc.check_in and doc.check_out:
            doc.calculate_working_hours()
            doc.status = "Present"
        elif doc.check_in:
            doc.status = "Present"
        else:
            doc.status = "Absent"
        
        # Check for late entry and early exit
        check_late_early_for_doc(doc, shift_info)
        
        # Update sync time
        doc.last_sync_time = now_datetime()
        
        # Save without triggering validation conflicts
        doc.flags.ignore_validate_update_after_submit = True
        doc.flags.ignore_auto_sync = True
        doc.db_update()
        
        # Update employee checkin links after sync
        doc.update_employee_checkin_links()
        
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


def extract_in_out_times(logs, check_in_out_type):
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


def check_late_early_for_doc(doc, shift_info=None):
    """Check for late entry and early exit based on shift timings"""
    if not doc.shift and not shift_info:
        return
        
    try:
        if not shift_info:
            shift_info = get_shift_type_info(doc.shift)
        
        if not shift_info:
            return
        
        from .attendance_utils import timedelta_to_time_helper
        
        if doc.check_in and shift_info.get('start_time'):
            check_in_time = get_datetime(doc.check_in).time()
            shift_start_time = timedelta_to_time_helper(shift_info['start_time'])
            
            if shift_start_time and check_in_time > shift_start_time:
                doc.late_entry = 1
        
        if doc.check_out and shift_info.get('end_time'):
            check_out_time = get_datetime(doc.check_out).time()
            shift_end_time = timedelta_to_time_helper(shift_info['end_time'])
            
            if shift_end_time and check_out_time < shift_end_time:
                doc.early_exit = 1
                
    except Exception as e:
        frappe.log_error(f"Error checking late/early: {str(e)}", "Custom Attendance Late/Early Check")


def auto_sync_attendance_from_checkin(employee, attendance_date):
    """Auto sync attendance when new checkin is created"""
    try:
        # Check if Custom Attendance record exists
        existing_attendance = frappe.db.exists("Custom Attendance", {
            "employee": employee,
            "attendance_date": attendance_date,
            "docstatus": ["!=", 2]
        })
        
        if existing_attendance:
            # Update existing record if auto_sync is enabled
            attendance_doc = frappe.get_doc("Custom Attendance", existing_attendance)
            if attendance_doc.auto_sync_enabled:
                result = sync_attendance_from_checkin_data(attendance_doc)
                frappe.logger().info(f"Auto-synced attendance {existing_attendance}: {result}")
                return {"updated": True, "attendance": existing_attendance, "message": result}
        else:
            # Create new attendance record
            result = create_attendance_from_checkin(employee, attendance_date)
            return result
            
    except Exception as e:
        frappe.log_error(f"Error in auto sync: {str(e)}", "Auto Sync Attendance")
        return {"updated": False, "message": str(e)}


def create_attendance_from_checkin(employee, attendance_date):
    """Create new Custom Attendance from checkin data"""
    try:
        employee_doc = frappe.get_doc("Employee", employee)
        
        # Check if employee wants auto attendance creation
        if not getattr(employee_doc, 'create_auto_attendance', True):
            return {"created": False, "message": "Auto attendance creation disabled for employee"}
            
        new_attendance = frappe.new_doc("Custom Attendance")
        new_attendance.employee = employee
        new_attendance.employee_name = employee_doc.employee_name
        new_attendance.attendance_date = attendance_date
        new_attendance.company = employee_doc.company
        new_attendance.auto_sync_enabled = 1
        new_attendance.status = "Absent"  # Default status, will be updated after sync
        
        # Skip duplicate check during auto creation
        new_attendance.flags.ignore_auto_sync = True
        new_attendance.flags.ignore_duplicate_check = True
        
        new_attendance.save()
        
        # Sync from checkins
        result = sync_attendance_from_checkin_data(new_attendance)
        
        frappe.logger().info(f"Created and synced attendance {new_attendance.name}: {result}")
        
        return {
            "created": True, 
            "attendance": new_attendance.name, 
            "message": f"Created and {result}"
        }
        
    except Exception as e:
        frappe.log_error(f"Error creating attendance from checkin: {str(e)}", "Create Attendance From Checkin")
        return {"created": False, "message": str(e)}


def batch_sync_attendance_records(date_from, date_to, employee=None):
    """Batch sync multiple attendance records"""
    try:
        filters = {
            "attendance_date": ["between", [date_from, date_to]],
            "auto_sync_enabled": 1,
            "docstatus": 0
        }
        
        if employee:
            filters["employee"] = employee
        
        attendance_records = frappe.get_all("Custom Attendance",
            filters=filters,
            fields=["name", "employee", "attendance_date"]
        )
        
        results = {
            "total_records": len(attendance_records),
            "synced_count": 0,
            "error_count": 0,
            "errors": []
        }
        
        for record in attendance_records:
            try:
                doc = frappe.get_doc("Custom Attendance", record.name)
                sync_result = sync_attendance_from_checkin_data(doc)
                
                if "successfully" in sync_result.lower():
                    results["synced_count"] += 1
                else:
                    results["error_count"] += 1
                    results["errors"].append(f"{record.name}: {sync_result}")
                    
            except Exception as e:
                results["error_count"] += 1
                results["errors"].append(f"{record.name}: {str(e)}")
                
        frappe.db.commit()
        
        return results
        
    except Exception as e:
        frappe.log_error(f"Batch sync error: {str(e)}", "Batch Sync Attendance")
        return {"total_records": 0, "synced_count": 0, "error_count": 1, "errors": [str(e)]}


def smart_sync_based_on_checkin_changes(checkin_doc):
    """Smart sync only when checkin actually changes attendance"""
    try:
        attendance_date = getdate(checkin_doc.time)
        
        # Check if this checkin would actually change the attendance
        current_attendance = frappe.db.get_value("Custom Attendance", {
            "employee": checkin_doc.employee,
            "attendance_date": attendance_date,
            "docstatus": ["!=", 2]
        }, ["name", "check_in", "check_out", "auto_sync_enabled"], as_dict=True)
        
        if not current_attendance or not current_attendance.auto_sync_enabled:
            return {"synced": False, "reason": "No attendance record or auto sync disabled"}
        
        # Get all checkins for this date to determine new in/out times
        all_checkins = frappe.db.sql("""
            SELECT time, log_type, shift
            FROM `tabEmployee Checkin`
            WHERE employee = %s 
            AND DATE(time) = %s
            ORDER BY time ASC
        """, (checkin_doc.employee, attendance_date), as_dict=True)
        
        if not all_checkins:
            return {"synced": False, "reason": "No checkins found"}
        
        # Determine new in/out times
        shift_info = get_shift_type_info(all_checkins[0].get('shift'))
        check_in_out_type = "Alternating entries as IN and OUT during the same shift"
        if shift_info:
            check_in_out_type = shift_info.get('determine_check_in_and_check_out', check_in_out_type)
        
        new_in_time, new_out_time = extract_in_out_times(all_checkins, check_in_out_type)
        
        # Check if times actually changed
        current_in = current_attendance.check_in
        current_out = current_attendance.check_out
        
        times_changed = False
        if (not current_in and new_in_time) or (current_in and not new_in_time):
            times_changed = True
        elif current_in and new_in_time and abs((current_in - new_in_time).total_seconds()) > 60:  # 1 minute tolerance
            times_changed = True
        elif (not current_out and new_out_time) or (current_out and not new_out_time):
            times_changed = True
        elif current_out and new_out_time and abs((current_out - new_out_time).total_seconds()) > 60:  # 1 minute tolerance
            times_changed = True
        
        if times_changed:
            # Sync the attendance
            attendance_doc = frappe.get_doc("Custom Attendance", current_attendance.name)
            result = sync_attendance_from_checkin_data(attendance_doc)
            return {"synced": True, "message": result}
        else:
            return {"synced": False, "reason": "No significant time changes detected"}
            
    except Exception as e:
        frappe.log_error(f"Smart sync error: {str(e)}", "Smart Sync Attendance")
        return {"synced": False, "reason": str(e)}


def validate_sync_data(doc):
    """Validate data before syncing"""
    try:
        validation_results = []
        
        # Check if employee exists and is active
        if not frappe.db.exists("Employee", {"name": doc.employee, "status": "Active"}):
            validation_results.append("Employee not found or inactive")
        
        # Check if attendance date is valid
        from .attendance_utils import validate_employee_attendance_date
        date_validation = validate_employee_attendance_date(doc.employee, doc.attendance_date)
        if not date_validation["valid"]:
            validation_results.append(date_validation["message"])
        
        # Check for reasonable time ranges
        if doc.check_in and doc.check_out:
            time_validation = validate_time_range(doc.check_in, doc.check_out)
            if not time_validation["valid"]:
                validation_results.append(time_validation["message"])
        
        return {
            "valid": len(validation_results) == 0,
            "errors": validation_results
        }
        
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"Validation error: {str(e)}"]
        }


def get_sync_statistics(date_from, date_to):
    """Get synchronization statistics for reporting"""
    try:
        # Total attendance records in date range
        total_attendance = frappe.db.count("Custom Attendance", {
            "attendance_date": ["between", [date_from, date_to]],
            "docstatus": ["!=", 2]
        })
        
        # Records with auto_sync enabled
        auto_sync_enabled = frappe.db.count("Custom Attendance", {
            "attendance_date": ["between", [date_from, date_to]],
            "auto_sync_enabled": 1,
            "docstatus": ["!=", 2]
        })
        
        # Records with sync timestamp
        synced_records = frappe.db.count("Custom Attendance", {
            "attendance_date": ["between", [date_from, date_to]],
            "last_sync_time": ["is", "set"],
            "docstatus": ["!=", 2]
        })
        
        # Records with checkin data
        with_checkin_data = frappe.db.count("Custom Attendance", {
            "attendance_date": ["between", [date_from, date_to]],
            "check_in": ["is", "set"],
            "docstatus": ["!=", 2]
        })
        
        return {
            "date_range": f"{date_from} to {date_to}",
            "total_attendance_records": total_attendance,
            "auto_sync_enabled": auto_sync_enabled,
            "synced_records": synced_records,
            "with_checkin_data": with_checkin_data,
            "sync_coverage": round((synced_records / total_attendance * 100), 1) if total_attendance > 0 else 0
        }
        
    except Exception as e:
        frappe.log_error(f"Error getting sync statistics: {str(e)}", "Sync Statistics")
        return {"error": str(e)}


def cleanup_orphaned_checkin_links():
    """Clean up orphaned checkin links (checkins linked to deleted attendance)"""
    try:
        # Find checkins with custom_attendance_link pointing to non-existent records
        orphaned_links = frappe.db.sql("""
            SELECT ec.name, ec.custom_attendance_link
            FROM `tabEmployee Checkin` ec
            WHERE ec.custom_attendance_link IS NOT NULL
            AND ec.custom_attendance_link != ''
            AND NOT EXISTS (
                SELECT 1 FROM `tabCustom Attendance` ca 
                WHERE ca.name = ec.custom_attendance_link
            )
        """, as_dict=True)
        
        cleanup_count = 0
        for link in orphaned_links:
            frappe.db.set_value("Employee Checkin", link.name, "custom_attendance_link", "")
            cleanup_count += 1
        
        frappe.db.commit()
        
        return {
            "success": True,
            "cleaned_up": cleanup_count,
            "message": f"Cleaned up {cleanup_count} orphaned checkin links"
        }
        
    except Exception as e:
        frappe.log_error(f"Error cleaning up orphaned links: {str(e)}", "Cleanup Orphaned Links")
        return {"success": False, "message": str(e)}


# Hook handlers for ERPNext integration
def on_checkin_update(doc, method):
    """Trigger khi Employee Checkin được update"""
    try:
        if not doc.time or not doc.employee:
            return
            
        # Smart sync to avoid unnecessary updates
        result = smart_sync_based_on_checkin_changes(doc)
        
        if result.get("synced"):
            frappe.logger().info(f"Auto-synced attendance after checkin update: {result.get('message')}")
            
    except Exception as e:
        frappe.log_error(f"Error in on_checkin_update: {str(e)}", "Checkin Update Handler")


def on_checkin_delete(doc, method):
    """Trigger when Employee Checkin is deleted"""
    try:
        if not doc.time or not doc.employee:
            return
        
        attendance_date = getdate(doc.time)
        
        # Find and update related attendance
        attendance = frappe.db.get_value("Custom Attendance", {
            "employee": doc.employee,
            "attendance_date": attendance_date,
            "auto_sync_enabled": 1,
            "docstatus": 0
        })
        
        if attendance:
            # Re-sync to update times after checkin deletion
            attendance_doc = frappe.get_doc("Custom Attendance", attendance)
            sync_result = sync_attendance_from_checkin_data(attendance_doc)
            frappe.logger().info(f"Re-synced attendance {attendance} after checkin deletion: {sync_result}")
            
    except Exception as e:
        frappe.log_error(f"Error in on_checkin_delete: {str(e)}", "Checkin Delete Handler")