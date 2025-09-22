# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, add_days, today, flt
from .overtime_calculator import (
    get_overtime_details_for_doc,
    calculate_working_hours_with_overtime_for_doc
)
from .attendance_sync import sync_attendance_from_checkin_data
from .bulk_operations import (
    bulk_recalculate_overtime,
    bulk_process_from_shift_date,
    bulk_sync_custom_attendance,
    get_bulk_process_preview_data,
    migrate_existing_attendance_records,
    bulk_daily_completion_range
)
from .scheduler_jobs import (
    daily_attendance_completion_for_date,
    auto_submit_custom_attendance
)
from .attendance_utils import check_attendance_exists_helper


@frappe.whitelist()
def recalculate_attendance_with_overtime(attendance_name):
    """API method to recalculate specific attendance with overtime"""
    try:
        frappe.logger().info(f"=== RECALCULATING OVERTIME for {attendance_name} ===")
        
        doc = frappe.get_doc("Custom Attendance", attendance_name)
        
        if not doc.check_in or not doc.check_out:
            return {"success": False, "message": "Check-in and check-out times required"}
        
        frappe.logger().info(f"Employee: {doc.employee}")
        frappe.logger().info(f"Date: {doc.attendance_date}")
        frappe.logger().info(f"Check-in: {doc.check_in}")
        frappe.logger().info(f"Check-out: {doc.check_out}")
        
        # Get OT requests
        from .overtime_calculator import get_approved_overtime_requests_for_doc
        ot_requests = get_approved_overtime_requests_for_doc(doc)
        frappe.logger().info(f"Found {len(ot_requests)} OT requests")
        
        # Store old values
        old_working_hours = doc.working_hours or 0
        old_overtime_hours = doc.overtime_hours or 0
        
        if ot_requests:
            # Calculate with OT
            calculate_working_hours_with_overtime_for_doc(doc)
        else:
            # No OT, only calculate regular hours
            frappe.logger().info("No OT requests found, calculating regular hours only")
            doc.calculate_working_hours()  # Original method
            doc.overtime_hours = 0
        
        # Save changes
        doc.save()
        
        frappe.logger().info(f"Results:")
        frappe.logger().info(f"  Old working hours: {old_working_hours}")
        frappe.logger().info(f"  New working hours: {doc.working_hours}")
        frappe.logger().info(f"  Old overtime hours: {old_overtime_hours}")
        frappe.logger().info(f"  New overtime hours: {doc.overtime_hours}")
        
        # Get detailed OT info
        overtime_details = get_overtime_details_for_doc(doc)
        
        return {
            "success": True,
            "message": f"Recalculated! Total: {doc.working_hours}h (OT: {doc.overtime_hours or 0}h)",
            "working_hours": doc.working_hours,
            "overtime_hours": doc.overtime_hours or 0,
            "overtime_details": overtime_details,
            "ot_requests_found": len(ot_requests)
        }
         
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(f"Recalculate overtime error: {error_msg}", "Recalculate Overtime")
        frappe.logger().error(f"RECALCULATE ERROR: {error_msg}")
        return {"success": False, "message": error_msg}


@frappe.whitelist()
def calculate_working_hours_with_overtime_for_doc_api(docname):
    """
    API wrapper for calculate_working_hours_with_overtime_for_doc
    Called from client script - HANDLES SUBMITTED DOCUMENTS
    """
    try:
        doc = frappe.get_doc("Custom Attendance", docname)
        old_working_hours = doc.working_hours
        old_overtime_hours = doc.overtime_hours
        
        result = calculate_working_hours_with_overtime_for_doc(doc)
        
        # Update document with new values
        if result["working_hours"] > 0 and (result["working_hours"] != old_working_hours or result["overtime_hours"] != old_overtime_hours):
            
            if doc.docstatus == 1:  # Submitted document
                # Method 1: Use database update for submitted docs
                frappe.db.set_value("Custom Attendance", docname, {
                    "overtime_hours": result["overtime_hours"],
                    "working_hours": result["working_hours"]
                })
                frappe.db.commit()
                
                # Update doc object for return values
                doc.overtime_hours = result["overtime_hours"]
                doc.working_hours = result["working_hours"]
                
                result["update_method"] = "database_direct"
                result["message"] += " (Updated via database - document was submitted)"
                
            else:  # Draft document
                # Method 2: Normal save for draft docs
                doc.flags.ignore_validate_update_after_submit = True
                doc.save(ignore_permissions=True)
                result["update_method"] = "document_save"
                result["message"] += " (Updated via document save)"
            
            result["updated"] = True
            result["old_working_hours"] = old_working_hours
            result["old_overtime_hours"] = old_overtime_hours
        else:
            result["updated"] = False
            result["message"] += " (No changes needed)"
            
        return result
        
    except Exception as e:
        error_msg = f"API error calculating working hours for {docname}: {str(e)}"
        frappe.log_error(error_msg, "Calculate Working Hours API")
        return {"error": error_msg}


@frappe.whitelist()
def sync_attendance_from_checkin(doc_name):
    """API method to sync attendance from checkin"""
    try:
        doc = frappe.get_doc("Custom Attendance", doc_name)
        result = sync_attendance_from_checkin_data(doc)
        return result
    except Exception as e:
        frappe.log_error(f"API sync error: {str(e)}")
        return f"Error: {str(e)}"


@frappe.whitelist()
def check_attendance_exists(employee, attendance_date, exclude_name=None):
    """Check if attendance record exists for employee on date"""
    return check_attendance_exists_helper(employee, attendance_date, exclude_name)


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
        check_result = check_attendance_exists_helper(employee, attendance_date)
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
        import json
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


@frappe.whitelist()
def manual_auto_update(date=None):
    """Manual trigger để test auto update"""
    try:
        if not date:
            date = getdate()
        else:
            date = getdate(date)
            
        # Run auto update cho specific date
        result = daily_attendance_completion_for_date(date)
        
        return result
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def api_get_attendance_summary_for_date(date=None):
    """
    Lấy summary attendance cho ngày cụ thể để kiểm tra
    """
    try:
        target_date = getdate(date) if date else today()
        
        # Total active employees
        total_employees = frappe.db.count("Employee", {
            "status": "Active",
            "date_of_joining": ["<=", target_date],
            "relieving_date": ["is", "not set"]
        })
        
        # Custom Attendance records
        attendance_summary = frappe.db.sql("""
            SELECT 
                status,
                COUNT(*) as count
            FROM `tabCustom Attendance`
            WHERE attendance_date = %s
            AND docstatus != 2
            GROUP BY status
        """, (target_date,), as_dict=True)
        
        # Employees with checkins
        employees_with_checkins = frappe.db.sql("""
            SELECT COUNT(DISTINCT employee) as count
            FROM `tabEmployee Checkin`
            WHERE DATE(time) = %s
        """, (target_date,), as_dict=True)
        
        checkin_count = employees_with_checkins[0]['count'] if employees_with_checkins else 0
        
        # Calculate missing attendance
        total_attendance = sum([row['count'] for row in attendance_summary])
        missing_attendance = total_employees - total_attendance
        
        return {
            "success": True,
            "date": str(target_date),
            "total_employees": total_employees,
            "total_attendance_records": total_attendance,
            "missing_attendance": missing_attendance,
            "employees_with_checkins": checkin_count,
            "attendance_breakdown": attendance_summary
        }
        
    except Exception as e: 
        frappe.log_error(f"Error in get_attendance_summary_for_date: {str(e)}", "Custom Attendance Summary")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def identify_missing_attendance(date=None):
    """
    Identify employees thiếu Custom Attendance records
    """
    try:
        target_date = getdate(date) if date else today()
        
        missing_employees = frappe.db.sql("""
            SELECT 
                e.name as employee,
                e.employee_name,
                e.company,
                e.department,
                e.default_shift,
                CASE 
                    WHEN ec.employee IS NOT NULL THEN 'Has Check-ins'
                    ELSE 'No Check-ins'
                END as checkin_status
            FROM `tabEmployee` e
            LEFT JOIN (
                SELECT DISTINCT employee 
                FROM `tabEmployee Checkin` 
                WHERE DATE(time) = %s
            ) ec ON ec.employee = e.name
            WHERE e.status = 'Active'
            AND (e.date_of_joining IS NULL OR e.date_of_joining <= %s)
            AND (e.relieving_date IS NULL OR e.relieving_date >= %s)
            AND NOT EXISTS (
                SELECT 1 FROM `tabCustom Attendance` ca 
                WHERE ca.employee = e.name 
                AND ca.attendance_date = %s
                AND ca.docstatus != 2
            )
            ORDER BY e.name
        """, (target_date, target_date, target_date, target_date), as_dict=True)
        
        return {
            "success": True,
            "date": str(target_date),
            "missing_count": len(missing_employees),
            "missing_employees": missing_employees
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def api_get_attendance_summary_for_range(start_date=None, end_date=None):
    """
    Lấy summary attendance cho date range
    """
    try:
        start_date = getdate(start_date) if start_date else add_days(today(), -7)
        end_date = getdate(end_date) if end_date else today()
        
        if start_date > end_date:
            return {"success": False, "message": "Start date cannot be after end date"}
        
        # Calculate total days
        from frappe.utils import date_diff
        total_days = date_diff(end_date, start_date) + 1
        
        if total_days > 90:  # Limit để tránh overload
            return {"success": False, "message": "Date range too large (maximum 90 days)"}
        
        # Build daily breakdown
        daily_breakdown = []
        current_date = start_date
        total_employee_days = 0
        total_attendance_records = 0
        
        while current_date <= end_date:
            # Get active employees for this date
            active_employees_count = frappe.db.count("Employee", {
                "status": "Active",
                "date_of_joining": ["<=", current_date],
                "relieving_date": ["is", "not set"]
            })
            
            # Get attendance records for this date
            attendance_records_count = frappe.db.count("Custom Attendance", {
                "attendance_date": current_date,
                "docstatus": ["!=", 2]
            })
            
            daily_breakdown.append({
                "date": str(current_date),
                "total_employees": active_employees_count,
                "attendance_records": attendance_records_count
            })
            
            total_employee_days += active_employees_count
            total_attendance_records += attendance_records_count
            
            current_date = add_days(current_date, 1)
        
        # Calculate totals
        total_missing = total_employee_days - total_attendance_records
        
        completion_percentage = 0
        if total_employee_days > 0:
            completion_percentage = round((total_attendance_records / total_employee_days) * 100, 1)
        
        return {
            "success": True,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "total_days": total_days,
            "total_employee_days": total_employee_days,
            "total_attendance_records": total_attendance_records,
            "total_missing": total_missing,
            "completion_percentage": completion_percentage,
            "daily_breakdown": daily_breakdown
        }
        
    except Exception as e:
        frappe.log_error(f"Error in get_attendance_summary_for_range: {str(e)}", "Attendance Range Summary")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def test_shift_processing_logic():
    """Test function để verify shift processing logic"""
    try:
        from frappe.utils import now_datetime
        from .scheduler_jobs import get_shifts_ready_for_processing, get_employees_for_shift_processing
        
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


# Bulk operation APIs
@frappe.whitelist()
def api_bulk_recalculate_overtime(date_from, date_to):
    """API wrapper for bulk recalculate overtime"""
    if not frappe.has_permission("Custom Attendance", "write"):
        frappe.throw(_("Not permitted to modify Custom Attendance"))
    
    return bulk_recalculate_overtime(date_from, date_to)


@frappe.whitelist()
def api_bulk_process_from_shift_date(shift_name=None, start_date=None, end_date=None):
    """API wrapper for bulk process from shift date"""
    if not frappe.has_permission("Custom Attendance", "create"):
        frappe.throw(_("Not permitted to create Custom Attendance"))
    
    return bulk_process_from_shift_date(shift_name, start_date, end_date)


@frappe.whitelist()
def api_bulk_sync_custom_attendance(date_from, date_to):
    """API wrapper for bulk sync"""
    if not frappe.has_permission("Custom Attendance", "write"):
        frappe.throw(_("Not permitted to modify Custom Attendance"))
    
    return bulk_sync_custom_attendance(date_from, date_to)


@frappe.whitelist()
def api_manual_daily_completion(date=None):
    """
    Manual trigger cho daily attendance completion
    """
    try:
        if not frappe.has_permission("Custom Attendance", "create"):
            frappe.throw(_("Not permitted to create Custom Attendance"))
            
        target_date = getdate(date) if date else add_days(today(), -1)
        
        result = daily_attendance_completion_for_date(target_date)
        return result
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def bulk_daily_completion(start_date, end_date):
    """
    Bulk daily completion cho nhiều ngày
    """
    try:
        if not frappe.has_permission("Custom Attendance", "create"):
            frappe.throw(_("Not permitted to create Custom Attendance"))
        
        return bulk_daily_completion_range(start_date, end_date)
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def manual_submit_bulk():
    """
    Manual trigger để test auto submit function
    """
    if not frappe.has_permission("Custom Attendance", "write"):
        frappe.throw(_("Not permitted to submit Custom Attendance"))
    
    result = auto_submit_custom_attendance()
    return result


@frappe.whitelist()
def get_bulk_process_preview(shift_name=None, start_date=None, end_date=None):
    """Preview data trước khi bulk process"""
    try:
        return get_bulk_process_preview_data(shift_name, start_date, end_date)
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def migrate_existing_attendance_with_overtime():
    """Migrate existing Custom Attendance records to include overtime calculation"""
    try:
        if not frappe.has_permission("Custom Attendance", "write"):
            frappe.throw(_("Not permitted to modify Custom Attendance"))
        
        return migrate_existing_attendance_records()
        
    except Exception as e:
        return {"success": False, "message": str(e)}


# Additional utility APIs
@frappe.whitelist()
def get_employee_attendance_data(employee, date_from, date_to):
    """Get attendance data for specific employee and date range"""
    try:
        if not frappe.has_permission("Custom Attendance", "read"):
            frappe.throw(_("Not permitted to read Custom Attendance"))
        
        attendance_data = frappe.get_all("Custom Attendance",
            filters={
                "employee": employee,
                "attendance_date": ["between", [date_from, date_to]],
                "docstatus": ["!=", 2]
            },
            fields=[
                "name", "attendance_date", "status", "check_in", "check_out",
                "working_hours", "overtime_hours", "late_entry", "early_exit"
            ],
            order_by="attendance_date asc"
        )
        
        return {
            "success": True,
            "employee": employee,
            "date_from": date_from,
            "date_to": date_to,
            "total_records": len(attendance_data),
            "attendance_data": attendance_data
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def get_department_attendance_summary(department, date_from, date_to):
    """Get attendance summary for specific department"""
    try:
        if not frappe.has_permission("Custom Attendance", "read"):
            frappe.throw(_("Not permitted to read Custom Attendance"))
        
        # Get employees in department
        employees = frappe.get_all("Employee",
            filters={"department": department, "status": "Active"},
            fields=["name", "employee_name"]
        )
        
        if not employees:
            return {"success": True, "message": "No employees found in department", "summary": {}}
        
        employee_list = [emp.name for emp in employees]
        
        # Get attendance summary
        attendance_summary = frappe.db.sql("""
            SELECT 
                ca.status,
                COUNT(*) as count,
                AVG(ca.working_hours) as avg_working_hours,
                SUM(ca.overtime_hours) as total_overtime_hours
            FROM `tabCustom Attendance` ca
            WHERE ca.employee IN ({})
            AND ca.attendance_date BETWEEN %s AND %s
            AND ca.docstatus != 2
            GROUP BY ca.status
        """.format(','.join(['%s'] * len(employee_list))), 
        employee_list + [date_from, date_to], as_dict=True)
        
        return {
            "success": True,
            "department": department,
            "date_from": date_from,
            "date_to": date_to,
            "total_employees": len(employees),
            "summary": attendance_summary
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}

@frappe.whitelist()
def sync_from_checkin(attendance_name):
    """
    Sync attendance data from Employee Checkin records
    FIXED: Đã sửa để hoạt động như API function
    """
    try:
        if not attendance_name:
            return {"success": False, "message": "Attendance name is required"}
        
        # LOAD DOCUMENT từ attendance_name (string)
        doc = frappe.get_doc("Custom Attendance", attendance_name)
        
        if not doc.employee or not doc.attendance_date:
            return {"success": False, "message": "Employee and attendance date required"}
        
        # Get all checkins for the employee on the attendance date
        checkins = frappe.db.sql("""
            SELECT name, time, log_type, device_id, shift
            FROM `tabEmployee Checkin`
            WHERE employee = %s 
            AND DATE(time) = %s
            ORDER BY time ASC
        """, (doc.employee, doc.attendance_date), as_dict=True)  # ← SỬA: dùng doc.employee

        if not checkins:
            return {"success": False, "message": "No check-in records found for this date"}

        # Get shift check-in/out type
        shift_doc = None
        check_in_out_type = "Alternating entries as IN and OUT during the same shift"

        if checkins[0].get('shift'):
            try:
                shift_doc = frappe.get_doc("Shift Type", checkins[0].shift)
                check_in_out_type = getattr(shift_doc, 'determine_check_in_and_check_out', 
                                            "Alternating entries as IN and OUT during the same shift")
                doc.shift = checkins[0].shift  # ← SỬA: dùng doc.shift
            except:
                pass

        # Extract in_time và out_time
        in_time, out_time = extract_in_out_times_api(checkins, check_in_out_type)

        # Update attendance record
        changes_made = []
        
        if in_time:
            old_check_in = doc.check_in
            doc.check_in = in_time
            doc.in_time = in_time.time() if in_time else None
            if str(old_check_in) != str(in_time):
                changes_made.append("Check-in updated")

        if out_time:
            old_check_out = doc.check_out
            doc.check_out = out_time
            doc.out_time = out_time.time() if out_time else None
            if str(old_check_out) != str(out_time):
                changes_made.append("Check-out updated")

        # Calculate working hours and status
        old_status = doc.status
        
        if doc.check_in and doc.check_out:
            doc.calculate_working_hours()
            doc.status = "Present"
        elif doc.check_in:
            doc.status = "Present"
        else:
            doc.status = "Absent"

        if old_status != doc.status:
            changes_made.append(f"Status: {old_status} → {doc.status}")

        # Check for late entry and early exit
        check_late_early_api(doc)

        # Update sync time
        from frappe.utils import now_datetime
        doc.last_sync_time = now_datetime()

        # Save without triggering validation conflicts
        try:
            doc.flags.ignore_validate_update_after_submit = True
            doc.flags.ignore_auto_sync = True
            doc.flags.ignore_version = True
            
            if doc.docstatus == 1:  # Submitted document
                doc.save(ignore_permissions=True)
            else:  # Draft document
                doc.save()

            # Update employee checkin links after sync
            if hasattr(doc, 'update_employee_checkin_links'):
                doc.update_employee_checkin_links()

            return {
                "success": True,
                "message": f"Synced successfully! Changes: {'; '.join(changes_made) if changes_made else 'No changes'}",
                "changes": changes_made,
                "working_hours": doc.working_hours,
                "status": doc.status,
                "checkins_found": len(checkins)
            }
            
        except Exception as save_error:
            return {
                "success": False,
                "message": f"Sync completed but save failed: {str(save_error)}"
            }

    except Exception as e:
        error_msg = str(e)
        frappe.log_error(f"Error syncing attendance {attendance_name}: {error_msg}", "API Sync From Checkin")
        
        # Simplify common error messages for users
        if "Document has been modified" in error_msg:
            simplified_msg = "Please refresh the page and try again"
        elif "Duplicate entry" in error_msg:
            simplified_msg = "This attendance record already exists"
        else:
            simplified_msg = f"Sync failed: {error_msg[:100]}..."

        return {
            "success": False,
            "message": simplified_msg,
            "error": error_msg
        }


def extract_in_out_times_api(logs, check_in_out_type):
    """
    Extract in_time và out_time từ logs
    FIXED: Standalone function version
    """
    from frappe.utils import get_datetime
    
    try:
        # Try to import ERPNext function
        try:
            from hrms.hr.doctype.employee_checkin.employee_checkin import find_index_in_dict
        except ImportError:
            # Fallback function
            def find_index_in_dict(lst, key, value):
                for i, item in enumerate(lst):
                    if item.get(key) == value:
                        return i
                return None

        in_time = None
        out_time = None

        if not logs:
            return in_time, out_time

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

        # Validation
        if in_time and out_time and out_time <= in_time:
            frappe.logger().warning(f"Invalid time order: out_time {out_time} <= in_time {in_time}")
            out_time = None

        return in_time, out_time

    except Exception as e:
        frappe.log_error(f"Error extracting in/out times: {str(e)}", "Extract Times API")
        if logs:
            return get_datetime(logs[0].time), get_datetime(logs[-1].time) if len(logs) > 1 else None
        return None, None


def check_late_early_api(doc):
    """
    Check for late entry and early exit based on shift timings
    FIXED: Standalone function version
    """
    from frappe.utils import get_datetime
    from datetime import time
    
    if not doc.shift:
        return

    try:
        shift = frappe.get_doc("Shift Type", doc.shift)

        # Reset flags
        doc.late_entry = 0
        doc.early_exit = 0

        if doc.check_in and shift.start_time:
            check_in_time = get_datetime(doc.check_in).time()
            shift_start_time = timedelta_to_time_helper(shift.start_time)

            if shift_start_time and isinstance(shift_start_time, time):
                if check_in_time > shift_start_time:
                    doc.late_entry = 1
            else:
                frappe.log_error(f"Invalid shift_start_time type: {type(shift_start_time)}", "API Late Check")

        if doc.check_out and shift.end_time:
            check_out_time = get_datetime(doc.check_out).time()
            shift_end_time = timedelta_to_time_helper(shift.end_time)

            if shift_end_time and isinstance(shift_end_time, time):
                if check_out_time < shift_end_time:
                    doc.early_exit = 1
            else:
                frappe.log_error(f"Invalid shift_end_time type: {type(shift_end_time)}", "API Early Check")

    except Exception as e:
        frappe.log_error(f"Error checking late/early: {str(e)}", "API Late/Early Check")


def timedelta_to_time_helper(td):
    """
    Helper function to convert timedelta to time object
    COPIED từ attendance_utils để tránh import error
    """
    from datetime import time
    
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

@frappe.whitelist()
def get_overtime_details_standalone(employee, attendance_date, check_in=None, check_out=None):
    """Standalone API để tránh TimestampMismatchError"""
    try:
        # Tạo temporary doc object
        temp_doc = frappe._dict({
            'employee': employee,
            'attendance_date': attendance_date,
            'check_in': check_in,
            'check_out': check_out
        })
        
        from .overtime_calculator import get_overtime_details_for_doc
        result = get_overtime_details_for_doc(temp_doc)
        return result
        
    except Exception as e:
        frappe.log_error(f"Standalone overtime details error: {str(e)}")
        return {"has_overtime": False, "error": str(e)}